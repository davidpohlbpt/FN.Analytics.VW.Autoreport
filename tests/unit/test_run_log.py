from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sqlalchemy as sa

from pptcreator.models.models import AutoreportRecipients, AutoreportRuns
from pptcreator.utils import run_log


@pytest.fixture
def runs_engine(monkeypatch):
    engine = sa.create_engine("sqlite://").execution_options(
        schema_translate_map={"control": None}
    )
    table = AutoreportRuns.__table__
    table.create(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                {
                    "run_id": "run-1",
                    "template_id": 1,
                    "recipients": "a@example.com",
                    "recipient_id": recipient_id,
                    "brand": "Audi",
                    "current_period": "KW45",
                    "reference_period": reference_period,
                    "status": "processing",
                }
                for recipient_id, reference_period in [(42, "KW37"), (43, "KW38")]
            ],
        )
    monkeypatch.setattr(run_log, "database", SimpleNamespace(engine=engine))
    yield engine
    engine.dispose()


@pytest.mark.parametrize("recipient_id", [42, None])
def test_status_update_uses_the_simplified_runs_schema(runs_engine, recipient_id):
    run_log.update_status(
        "run-1", "Audi", "KW37", status="rendered", recipient_id=recipient_id
    )

    with runs_engine.connect() as connection:
        rows = connection.execute(
            sa.select(AutoreportRuns.__table__).order_by(AutoreportRuns.id)
        ).mappings().all()
    assert [row["status"] for row in rows] == ["rendered", "processing"]
    assert rows[0]["updated_at"] is not None
    assert rows[0]["recipients"] == "a@example.com"
    assert rows[0]["current_period"] == "KW45"
    assert rows[0]["reference_period"] == "KW37"


def test_status_update_leaves_older_runs_of_the_recipient_untouched(runs_engine):
    table = AutoreportRuns.__table__
    with runs_engine.begin() as connection:
        connection.execute(
            table.insert(),
            {
                "run_id": "run-0",
                "template_id": 1,
                "recipients": "a@example.com",
                "recipient_id": 42,
                "brand": "Audi",
                "current_period": "KW44",
                "reference_period": "KW37",
                "status": "sent",
            },
        )

    run_log.update_status("run-1", "Audi", "KW37", status="rendered", recipient_id=42)

    with runs_engine.connect() as connection:
        statuses = dict(
            connection.execute(
                sa.select(table.c.run_id, table.c.status).where(table.c.recipient_id == 42)
            ).all()
        )
    assert statuses == {"run-0": "sent", "run-1": "rendered"}


def test_render_updates_run_without_persisting_the_s3_key(runs_engine):
    from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest
    from pptcreator.lambdas.render import update_run_log

    request = ReportRequest.from_event(
        {
            "template_id": 1,
            "brand": "Audi",
            "current_period": "KW45",
            "reference_period": "KW37",
            "recipients": ["a@example.com"],
            "recipient_ids": [42],
            "run_id": "run-1",
        }
    )
    update_run_log(
        request, SimpleNamespace(status="rendered", s3_key="reports/deck.pptx", error=None)
    )

    with runs_engine.connect() as connection:
        status = connection.execute(
            sa.select(AutoreportRuns.status).where(AutoreportRuns.recipient_id == 42)
        ).scalar_one()
    assert status == "rendered"


@pytest.fixture
def render_event():
    return {
        "template_id": 1,
        "brand": "Audi",
        "current_period": "KW45",
        "reference_period": "KW37",
        "recipients": ["a@example.com"],
        "recipient_ids": [42],
        "run_id": "run-1",
    }


@pytest.mark.parametrize("failure, sns_fails", [
    ("reported", False),
    ("raised", False),
    ("invalid_input", False),
    ("reported", True),
])
def test_render_failure_alert_preserves_error_and_updates_claim(
    runs_engine, render_event, monkeypatch, caplog, failure, sns_fails
):
    from pptcreator.lambdas import render

    original_error = RuntimeError("broken deck")
    renderer = Mock(return_value=SimpleNamespace(status="failed", error="broken deck"))
    if failure == "raised":
        renderer.side_effect = original_error
    if failure == "invalid_input":
        render_event["reference_period"] = "invalid"
    monkeypatch.setattr(render, "render_deck", renderer)
    sns = Mock()
    sns.publish.return_value = {"MessageId": "alert-1"}
    if sns_fails:
        sns.publish.side_effect = RuntimeError("SNS unavailable")
    monkeypatch.setattr(render, "boto3", SimpleNamespace(client=Mock(return_value=sns)))
    topic = "arn:aws:sns:eu-west-1:123456789012:render-alerts"
    monkeypatch.setenv("SNS_URL", topic)
    expected_error = ValueError if failure == "invalid_input" else RuntimeError

    with pytest.raises(expected_error) as raised:
        render.handler(render_event, None)

    if failure == "raised":
        assert raised.value is original_error
    elif failure == "reported":
        assert isinstance(raised.value, render.RenderFailed)
        assert str(raised.value) == "broken deck"
    else:
        renderer.assert_not_called()
    sns.publish.assert_called_once()
    alert = sns.publish.call_args.kwargs
    assert alert["TopicArn"] == topic
    assert str(raised.value) in alert["Message"]
    assert "run_id=run-1" in alert["Message"]
    assert "recipient_id=42" in alert["Message"]
    assert "recipient_email=a@example.com" in alert["Message"]
    if sns_fails:
        assert "Could not send render failure alert" in caplog.text
    with runs_engine.connect() as connection:
        rows = connection.execute(
            sa.select(AutoreportRuns.status, AutoreportRuns.error).order_by(AutoreportRuns.id)
        ).all()
    if failure == "invalid_input":
        assert rows[0][0] == "failed"
        assert "Unsupported period 'invalid'" in rows[0][1]
        assert rows[1] == ("processing", None)
    else:
        assert rows == [("failed", "broken deck"), ("processing", None)]


def test_render_failure_resets_send_now(runs_engine, render_event, monkeypatch):
    from pptcreator.lambdas import render

    recipients = AutoreportRecipients.__table__
    recipients.create(runs_engine)
    with runs_engine.begin() as connection:
        connection.execute(
            recipients.insert(),
            [
                {"id": recipient_id, "template_id": 1, "email": "a@example.com", "brand_id": 1,
                 "report_week": "KW45", "comparison_week": "KW37", "send_now": True}
                for recipient_id in (42, 43)
            ],
        )
    monkeypatch.setattr(
        render, "render_deck", Mock(return_value=SimpleNamespace(status="failed", error="broken deck"))
    )
    monkeypatch.delenv("SNS_URL", raising=False)

    with pytest.raises(render.RenderFailed):
        render.handler(render_event, None)

    with runs_engine.connect() as connection:
        send_now = dict(connection.execute(sa.select(recipients.c.id, recipients.c.send_now)).all())
    assert send_now == {42: False, 43: True}


def test_render_failure_without_sns_url_still_updates_the_run(
    runs_engine, render_event, monkeypatch, caplog
):
    from pptcreator.lambdas import render

    monkeypatch.delenv("SNS_URL", raising=False)
    monkeypatch.setattr(
        render, "render_deck", Mock(return_value=SimpleNamespace(status="failed", error="broken deck"))
    )
    client = Mock()
    monkeypatch.setattr(render, "boto3", SimpleNamespace(client=client))

    with pytest.raises(render.RenderFailed, match="broken deck"):
        render.handler(render_event, None)

    client.assert_not_called()
    assert "SNS_URL not set" in caplog.text
    with runs_engine.connect() as connection:
        status = connection.execute(
            sa.select(AutoreportRuns.status).where(AutoreportRuns.recipient_id == 42)
        ).scalar_one()
    assert status == "failed"


def test_render_success_does_not_send_an_alert(runs_engine, render_event, monkeypatch):
    from pptcreator.lambdas import render

    monkeypatch.setenv("SNS_URL", "arn:aws:sns:eu-west-1:123456789012:render-alerts")
    monkeypatch.setattr(render, "render_deck", Mock(return_value=SimpleNamespace(
        status="rendered", error=None, file_name="deck.pptx", slides=1,
        size_bytes=100, bucket="reports", s3_key="deck.pptx", email_subject="Report", language="DE",
    )))
    client = Mock()
    monkeypatch.setattr(render, "boto3", SimpleNamespace(client=client))

    output = render.handler(render_event, None)

    client.assert_not_called()
    assert output["s3_key"] == "deck.pptx"
    assert output["recipient_id"] == 42
    with runs_engine.connect() as connection:
        status = connection.execute(
            sa.select(AutoreportRuns.status).where(AutoreportRuns.recipient_id == 42)
        ).scalar_one()
    assert status == "rendered"
