import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest

DETECT_FILE = Path(__file__).resolve().parents[3] / "functions" / "vw-autoreport-detect.py"
ARN = "arn:aws:states:eu-west-1:123456789012:stateMachine:vw-autoreport"


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = [(name,) for name in ("id", "template_id", "email", "brand", "report_week", "comparison_week")]

    def execute(self, statement, params=None):
        self.connection.statements.append((" ".join(statement.split()), params))

    def fetchall(self):
        return self.connection.rows

    def fetchone(self):
        return self.connection.latest_snapshot

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.latest_snapshot = (" V01-D ", "48/2025 ")

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakeAws:
    def __init__(self, start_error=None):
        self.start_error = start_error
        self.executions = []
        self.alerts = []

    def client(self, service):
        return self

    def start_execution(self, **execution):
        if self.start_error:
            raise self.start_error
        self.executions.append(execution)
        return {"executionArn": f"{ARN}:execution:{execution['name']}"}

    def publish(self, **alert):
        self.alerts.append(alert)
        return {"MessageId": "alert-1"}


class SqliteCursorWithLatestSnapshot:
    def __init__(self, connection):
        self.cursor = connection.cursor()
        self.description = None

    def execute(self, statement, params=None):
        self.latest_lookup = "SELECT TOP(1)" in statement
        if not self.latest_lookup:
            self.cursor.execute(statement, params or ())
            self.description = self.cursor.description

    def fetchone(self):
        return ("V01-D", "48/2025")

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        self.cursor.close()


@pytest.fixture
def detect(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyodbc", types.SimpleNamespace(connect=None))
    spec = importlib.util.spec_from_file_location("vw_autoreport_detect", DETECT_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    state = {"aws": FakeAws(), "connection": FakeConnection([])}
    monkeypatch.setenv("STATE_MACHINE_ARN", ARN)
    monkeypatch.setenv("REPORT_PARAM", "Database-Report")
    monkeypatch.setenv("TIME_OUT", "30")
    monkeypatch.setattr(module, "boto3", types.SimpleNamespace(client=lambda service: state["aws"]))
    monkeypatch.setattr(module, "get_pyodbc_connection", lambda ssm, param, timeout: state["connection"])
    return module, state


def _row(recipient_id, email="a@example.com", report_week="V01-D (48/2025)", comparison_week="V03-F (5/2025)"):
    return (recipient_id, 1, email, "VW PKW", report_week, comparison_week)


def test_no_new_recipients_does_nothing(detect):
    module, state = detect

    out = module.lambda_handler({}, None)

    assert out == {"statusCode": 200, "body": "No report request found"}
    assert len(state["connection"].statements) == 2  # latest snapshot and recipients
    assert state["aws"].executions == []
    assert state["connection"].closed


def test_new_recipients_are_claimed_and_sent_to_the_state_machine(detect):
    module, state = detect
    state["connection"] = FakeConnection([_row(42), _row(43, email=" b@example.com "), _row(44, report_week="")])

    out = module.lambda_handler({}, None)

    execution = state["aws"].executions[0]
    payload = json.loads(execution["input"])
    run_id = execution["name"]
    assert execution["stateMachineArn"] == ARN
    assert out["execution_arn"].endswith(run_id)
    assert payload == {
        "has_requests": True,
        "count": 2,
        "requests": [
            {
                "template_id": 1, "brand": "VW PKW",
                "current_period": "V01-D (48/2025)", "reference_period": "V03-F (5/2025)",
                "recipients": ["a@example.com"], "recipient_ids": [42], "run_id": run_id,
            },
            {
                "template_id": 1, "brand": "VW PKW",
                "current_period": "V01-D (48/2025)", "reference_period": "V03-F (5/2025)",
                "recipients": ["b@example.com"], "recipient_ids": [43], "run_id": run_id,
            },
        ],
    }
    # every item is valid render input
    assert [ReportRequest.from_event(item).recipient_id for item in payload["requests"]] == [42, 43]

    insert_statements = [statement for statement, _ in state["connection"].statements if statement.startswith("INSERT")]
    assert all(
        "(run_id, template_id, recipients, recipient_id, brand, current_period, reference_period, status, created_at, updated_at)"
        in statement
        for statement in insert_statements
    )
    inserts = [params for statement, params in state["connection"].statements if statement.startswith("INSERT")]
    assert [params[3] for params in inserts] == [42, 43]
    assert all(params[0] == run_id for params in inserts)
    assert inserts[0][2] == "a@example.com"
    assert inserts[0][5:] == ("V01-D (48/2025)", "V03-F (5/2025)")
    assert state["connection"].commits == 1


def test_identical_requests_in_one_poll_are_sent_once(detect):
    module, state = detect
    state["connection"] = FakeConnection([
        _row(42, email="A@example.com"),
        _row(43, email="a@example.com "),
        _row(44, email="a@example.com", comparison_week="V11-D (39/2025)"),
    ])

    module.lambda_handler({}, None)

    payload = json.loads(state["aws"].executions[0]["input"])
    assert [item["recipient_ids"] for item in payload["requests"]] == [[42], [44]]
    select = state["connection"].statements[1][0]
    assert "LOWER(LTRIM(RTRIM(run.recipients))) = LOWER(LTRIM(RTRIM(r.email)))" in select
    assert "ELSE LTRIM(RTRIM(r.report_week))" in select
    assert "run.reference_period = LTRIM(RTRIM(r.comparison_week))" in select
    assert "run.recipient_id = r.id" not in select
    assert "run.template_id = r.template_id" in select


def test_german_and_english_deck_of_the_same_request_are_both_sent(detect):
    module, state = detect
    english = (43, 2, "a@example.com", "VW PKW", "V01-D (48/2025)", "V03-F (5/2025)")
    state["connection"] = FakeConnection([_row(42), english])

    module.lambda_handler({}, None)

    payload = json.loads(state["aws"].executions[0]["input"])
    assert [(item["template_id"], item["recipient_ids"]) for item in payload["requests"]] == [(1, [42]), (2, [43])]


@pytest.mark.parametrize("status", ["processing", "rendered"])
def test_processing_snapshot_blocks_duplicates_with_the_simplified_columns(detect, status):
    module, _ = detect
    with sqlite3.connect(":memory:") as connection:
        connection.executescript("""
            ATTACH DATABASE ':memory:' AS control;
            CREATE TABLE control.T_Control_Autoreport_Templates (id INT, is_active INT);
            CREATE TABLE control.T_Control_Autoreport_Brands
                (id INT, filter_value TEXT, is_active INT);
            CREATE TABLE control.T_Control_Autoreport_Recipients
                (id INT, template_id INT, email TEXT, brand_id INT,
                 report_week TEXT, comparison_week TEXT, send_now INT, IsDeleted INT);
            CREATE TABLE control.T_Control_Autoreport_Runs
                (recipient_id INT, template_id INT, recipients TEXT, brand TEXT,
                 current_period TEXT, reference_period TEXT, status TEXT);
            INSERT INTO control.T_Control_Autoreport_Templates VALUES (1, 1);
            INSERT INTO control.T_Control_Autoreport_Brands VALUES (1, 'VW PKW', 1);
            INSERT INTO control.T_Control_Autoreport_Recipients VALUES
                (42, 1, ' a@example.com ', 1, ' Aktuelle Woche V01-D (46/2026) ', ' KW37 ', 1, 0),
                (43, 1, 'a@example.com', 1, 'V01-D (48/2025)', 'KW38', 1, 0);
            INSERT INTO control.T_Control_Autoreport_Runs VALUES
                (99, 1, 'A@example.com', 'VW PKW', 'V01-D (48/2025)', 'KW37', 'processing');
        """)
        connection.execute(
            "UPDATE control.T_Control_Autoreport_Runs SET status = ?", (status,)
        )
        report_conn = types.SimpleNamespace(
            cursor=lambda: SqliteCursorWithLatestSnapshot(connection)
        )

        recipients = module.get_new_recipients(report_conn)
        assert [recipient["id"] for recipient in recipients] == [43]

        connection.execute(
            "UPDATE control.T_Control_Autoreport_Runs SET status = 'sent'"
        )
        recipients = module.get_new_recipients(report_conn)
        assert [recipient["id"] for recipient in recipients] == [42, 43]


def test_current_week_uses_one_resolution_for_sql_claims_and_payload(detect):
    module, state = detect
    state["connection"] = FakeConnection([
        _row(42, report_week="Aktuelle Woche V01-D (46/2026)"),
        _row(43),
        _row(44, email="b@example.com", report_week="Aktuelle Woche"),
    ])

    module.lambda_handler({}, None)

    statements = state["connection"].statements
    assert sum("SELECT TOP(1)" in statement for statement, _ in statements) == 1
    assert statements[1][1] == ("V01-D (48/2025)",)
    inserts = [params for statement, params in statements if statement.startswith("INSERT")]
    assert [params[3] for params in inserts] == [42, 44]
    assert all(params[5] == "V01-D (48/2025)" for params in inserts)
    payload = json.loads(state["aws"].executions[0]["input"])
    assert all(request["current_period"] == "V01-D (48/2025)" for request in payload["requests"])
    assert state["connection"].rows[0][4] == "Aktuelle Woche V01-D (46/2026)"


@pytest.mark.parametrize("snapshot", [None, (None, None), (" ", "48/2025")])
@pytest.mark.parametrize(
    "report_week", ["Aktuelle Woche", "Aktuelle Woche V01-D (46/2026)"]
)
def test_current_week_without_valid_snapshot_fails_before_claiming(
    detect, snapshot, report_week
):
    module, state = detect
    state["connection"] = FakeConnection([_row(42, report_week=report_week)])
    state["connection"].latest_snapshot = snapshot

    with pytest.raises(ValueError, match="No valid latest snapshot"):
        module.lambda_handler({}, None)

    assert state["connection"].commits == 0
    assert state["aws"].executions == []
    assert state["connection"].closed


def test_missing_state_machine_arn_fails_before_reading_the_database(detect, monkeypatch):
    module, state = detect
    monkeypatch.delenv("STATE_MACHINE_ARN")

    with pytest.raises(ValueError, match="STATE_MACHINE_ARN"):
        module.lambda_handler({}, None)

    assert state["connection"].statements == []
