import importlib.util
import json
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

    def close(self):
        pass


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

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
    assert len(state["connection"].statements) == 1  # only the SELECT
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

    inserts = [params for statement, params in state["connection"].statements if statement.startswith("INSERT")]
    assert [params[3] for params in inserts] == [42, 43]
    assert all(params[0] == run_id for params in inserts)
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
    select = state["connection"].statements[0][0]
    assert "LOWER(LTRIM(RTRIM(run.user_email))) = LOWER(LTRIM(RTRIM(r.email)))" in select
    assert "run.primary_date = LTRIM(RTRIM(r.report_week))" in select
    assert "run.recipient_id = r.id" not in select


def test_state_machine_start_failure_marks_claims_failed(detect):
    module, state = detect
    state["connection"] = FakeConnection([_row(42)])
    state["aws"].start_error = RuntimeError("AccessDenied")

    with pytest.raises(RuntimeError, match="AccessDenied"):
        module.lambda_handler({}, None)

    update = state["connection"].statements[-1]
    assert update[0].startswith("UPDATE control.T_Control_Autoreport_Runs SET status = 'failed'")
    assert update[1][0] == "State machine start failed: AccessDenied"
    assert state["connection"].closed


def test_missing_state_machine_arn_fails_before_reading_the_database(detect, monkeypatch):
    module, state = detect
    monkeypatch.delenv("STATE_MACHINE_ARN")

    with pytest.raises(ValueError, match="STATE_MACHINE_ARN"):
        module.lambda_handler({}, None)

    assert state["connection"].statements == []
