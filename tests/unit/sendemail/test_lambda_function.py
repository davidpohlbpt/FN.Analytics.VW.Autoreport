import importlib
import json
import sys
import types
from pathlib import Path

import pytest

FUNCTION_DIR = Path(__file__).resolve().parents[3] / "functions" / "vw-autoreport-sendemail"
MODULES = ("lambda_function", "send_email", "get_file", "get_token", "settings", "pyodbc")
BUCKET = "reports-bucket"
KEY = "reports/dev/VW_KPI_Report.pptx"


@pytest.fixture
def sendemail(monkeypatch):
    for name in MODULES:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=None))
    monkeypatch.syspath_prepend(str(FUNCTION_DIR))
    modules = types.SimpleNamespace(
        lambda_function=importlib.import_module("lambda_function"),
        send_email=importlib.import_module("send_email"),
    )
    yield modules
    for name in MODULES:
        sys.modules.pop(name, None)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, params):
        self.connection.statements.append((statement, params))

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class FakeAws:
    def __init__(self):
        self.deleted = []
        self.alerts = []

    def client(self, service):
        return self

    def get_parameter(self, Name, WithDecryption):
        assert WithDecryption is True
        return {"Parameter": {"Value": Name.rsplit("/", 1)[1]}}

    def get_object(self, Bucket, Key):
        self.read = (Bucket, Key)
        return {"Body": types.SimpleNamespace(read=lambda: b"PK")}

    def delete_object(self, Bucket, Key):
        self.deleted.append((Bucket, Key))

    def publish(self, **message):
        self.alerts.append(message)
        return {"MessageId": "alert-1"}


@pytest.fixture
def handler(sendemail, monkeypatch):
    module = sendemail.lambda_function
    state = {"aws": FakeAws(), "connections": [], "sent": [], "send_error": None}

    def send_email(*args):
        if state["send_error"]:
            raise state["send_error"]
        state["sent"].append(args)

    def get_pyodbc_connection(ssm_client, param, time_out):
        connection = FakeConnection()
        state["connections"].append(connection)
        return connection

    monkeypatch.setenv("ACCOUNT", "Prod")
    monkeypatch.setenv("REPORT_BUCKET", BUCKET)
    monkeypatch.setenv("REPORT_PREFIX", "reports")
    monkeypatch.setenv("REPORT_PARAM", "Database-Report")
    monkeypatch.setattr(module, "boto3", state["aws"])
    monkeypatch.setattr(module, "get_token", lambda tenant, client, secret: "token")
    monkeypatch.setattr(module, "send_email", send_email)
    monkeypatch.setattr(module, "get_pyodbc_connection", get_pyodbc_connection)
    return module, state


def _event(**extra):
    return {
        "run_id": "run-1",
        "brand": "Audi & <Test>",
        "recipient": "a@example.com",
        "recipient_id": 7,
        "bucket": BUCKET,
        "s3_key": KEY,
        "file_name": "VW_KPI_Report.pptx",
        "email_subject": "VW KPI Report Audi",
        **extra,
    }


def test_render_event_sends_report_updates_database_and_deletes_report(handler):
    module, state = handler

    assert module.lambda_handler(_event(), None)["statusCode"] == 200

    recipients, token, file, file_name, sender, html, subject = state["sent"][0]
    assert (recipients, token, file, file_name, sender, subject) == (
        ["a@example.com"], "token", b"PK", "VW_KPI_Report.pptx", "sender_email", "VW KPI Report Audi"
    )
    assert "Audi &amp; &lt;Test&gt;" in html
    assert "Lieber IDM-Nutzer" in html
    statements = state["connections"][0].statements
    assert "SET send_now = 0, last_report_time = " in statements[0][0]
    assert statements[0][0].endswith("WHERE id = ?")
    assert statements[0][1] == 7
    assert "WHERE recipient_id = ? AND run_id = ?" in statements[1][0]
    assert statements[1][1] == ["sent", None, 7, "run-1"]
    assert state["connections"][0].closed
    assert state["aws"].read == (BUCKET, KEY)
    assert state["aws"].deleted == [(BUCKET, KEY)]


def test_english_deck_gets_the_english_email(handler):
    module, state = handler

    module.lambda_handler(_event(language="EN"), None)

    html = state["sent"][0][5]
    assert "Dear IDM user" in html and "Lieber" not in html
    assert "Audi &amp; &lt;Test&gt;" in html


def test_send_failure_marks_run_failed_resets_send_now_and_keeps_report(handler):
    module, state = handler
    state["send_error"] = RuntimeError("Graph down")

    with pytest.raises(RuntimeError, match="Graph down"):
        module.lambda_handler(_event(), None)

    statements = state["connections"][0].statements
    assert len(statements) == 2
    assert "T_Control_Autoreport_Recipients] SET send_now = 0 WHERE" in statements[0][0]
    assert "last_report_time" not in statements[0][0]
    assert "T_Control_Autoreport_Runs" in statements[1][0]
    assert statements[1][1][:2] == ["failed", "Graph down"]
    assert state["aws"].deleted == []


@pytest.mark.parametrize("event", [_event(recipient=None), _event(recipient_id=None)])
def test_event_without_one_recipient_is_rejected_before_sending(handler, event):
    module, state = handler

    with pytest.raises(ValueError, match="exactly one recipient"):
        module.lambda_handler(event, None)

    assert state["sent"] == []
    assert state["aws"].deleted == []


@pytest.fixture
def graph(sendemail, monkeypatch):
    module = sendemail.send_email
    calls, responses = [], []

    def fake_open(method, url, headers, data):
        calls.append({"method": method, "url": url, "headers": headers, "data": data})
        status, body = responses.pop(0)
        return status, json.dumps(body).encode("utf-8") if body is not None else b""

    monkeypatch.setattr(module, "_open", fake_open)
    return module, calls, responses


def _send(module, size):
    module.send_email(["a@example.com"], "token", b"x" * size, "deck.pptx", "sender@example.com", "<p>Hi</p>", "Report")


def test_small_file_is_sent_with_send_mail_and_bcc(graph):
    module, calls, responses = graph
    responses.append((202, None))

    _send(module, 10)

    body = json.loads(calls[0]["data"])
    assert calls[0]["url"].endswith("/users/sender@example.com/sendMail")
    assert body["message"]["bccRecipients"] == [{"emailAddress": {"address": "a@example.com"}}]
    assert body["message"]["attachments"][0]["name"] == "deck.pptx"


def test_large_file_uses_draft_upload_session_and_send(graph):
    module, calls, responses = graph
    size = module.UPLOAD_CHUNK_SIZE + 5
    responses += [
        (201, {"id": "draft-1"}),
        (201, {"uploadUrl": "https://outlook.office.com/upload"}),
        (200, {"nextExpectedRanges": [str(module.UPLOAD_CHUNK_SIZE)]}),
        (201, None),
        (202, None),
    ]

    _send(module, size)

    uploads = [call for call in calls if call["method"] == "PUT"]
    assert [call["headers"]["Content-Range"] for call in uploads] == [
        f"bytes 0-{module.UPLOAD_CHUNK_SIZE - 1}/{size}",
        f"bytes {module.UPLOAD_CHUNK_SIZE}-{size - 1}/{size}",
    ]
    assert all("Authorization" not in call["headers"] for call in uploads)
    assert calls[-1]["url"].endswith("/messages/draft-1/send")


def test_failed_large_upload_deletes_draft_and_does_not_send(graph):
    module, calls, responses = graph
    responses += [
        (201, {"id": "draft-1"}),
        (403, {"error": {"code": "ErrorAccessDenied"}}),
        (204, None),
    ]

    with pytest.raises(RuntimeError, match="403"):
        _send(module, module.SMALL_FILE_LIMIT)

    assert calls[-1]["method"] == "DELETE"
    assert not any(call["url"].endswith("/send") for call in calls)
