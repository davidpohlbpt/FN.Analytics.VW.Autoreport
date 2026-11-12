"""End-to-end through the three Lambda handlers and the all-in-one handler.

Control tables in pycore's in-memory SQLite, template in moto S3, decks in moto S3,
e-mails via moto SES, KPI data from the stub source. Writes decks to tests/result/.
"""

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest
from pptx import Presentation

from pptcreator import lambda_handler
from pptcreator.config import settings
from pptcreator.creator.graph_steer_creation_process import (
    current_calendar_week,
    default_reference_week,
)
from pptcreator.kpi.registry import KPIS
from pptcreator.models.models import AutoreportRecipients, AutoreportRuns
from pptcreator.utils.read_data import read_data
from tests.unit.autoreport_fixtures import TEMPLATE_ID, seed_control_tables  # noqa: F401
from tests.unit.infra.conftest import BUCKET, aws  # noqa: F401

TEMPLATE = Path(__file__).resolve().parent / "test_data" / "VW_Template_Overview.pptx"
RESULT_DIR = Path(__file__).resolve().parents[1] / "result"
TEMPLATE_KEY = "templates/VW_Template_Overview.pptx"


@pytest.fixture
def stack(aws, seed_control_tables, easy_test):  # noqa: F811
    aws["s3"].put_object(Bucket=BUCKET, Key=TEMPLATE_KEY, Body=TEMPLATE.read_bytes())
    seed_control_tables(f"s3://{BUCKET}/{TEMPLATE_KEY}", target_location=f"s3://{BUCKET}/reports/dev")
    return aws


def _deck(stack, key: str) -> Presentation:
    data = stack["s3"].get_object(Bucket=BUCKET, Key=key)["Body"].read()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULT_DIR / key.rsplit("/", 1)[-1]
    out.write_bytes(data)
    return Presentation(str(out))


def _runs() -> pd.DataFrame:
    return read_data(AutoreportRuns, [], [])


# ------------------------------------------------------------------------------ #
# Lambda 1
# ------------------------------------------------------------------------------ #


def test_plan_scheduled(stack):
    out = lambda_handler.plan_handler(
        {"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "KW45", "reference_period": "KW40"}, None
    )

    assert out["count"] == 2
    by_brand = {r["brand"]: r for r in out["requests"]}
    assert by_brand["Audi"]["reference_period"] == "KW37"
    assert by_brand["Audi"]["recipients"] == ["a@x.de", "b@x.de"]
    assert by_brand["Seat"]["reference_period"] == "KW40"  # template default from event
    assert all(r["run_id"] == out["run_id"] and r["trigger"] == "scheduled" for r in out["requests"])

    runs = _runs()
    assert len(runs) == 2 and set(runs["status"]) == {"queued"}
    # scheduled run must not touch send_now
    assert read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]


def test_plan_adhoc_clears_send_now(stack):
    out = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID, "current_period": "KW45"}, None)

    assert out["count"] == 1
    assert out["requests"][0]["recipients"] == ["b@x.de"]
    assert out["requests"][0]["recipient_ids"] == [2]
    assert not read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]
    assert read_data(AutoreportRecipients, ["id"], [4])["send_now"].iloc[0]  # inactive row untouched


def test_plan_rejects_bad_trigger(stack):
    with pytest.raises(ValueError, match="trigger must be"):
        lambda_handler.plan_handler({"trigger": "manual"}, None)


# ------------------------------------------------------------------------------ #
# Lambda 2
# ------------------------------------------------------------------------------ #


def test_render_handler_end_to_end(stack):
    event = {
        "template_id": TEMPLATE_ID,
        "brand": "Audi",
        "current_period": "KW45",
        "reference_period": "KW37",
        "recipients": ["a@example.com"],
        "run_id": "run-1",
        "trigger": "manual",
    }

    out = lambda_handler.render_handler(event, None)

    assert out["status"] == "rendered"
    assert out["file_name"] == "VW_KPI_Report_Audi_KW45_vs_KW37.pptx"
    assert out["bucket"] == BUCKET
    assert out["s3_key"] == f"reports/dev/{out['file_name']}"  # target_location from the template table
    assert out["slides"] == len(KPIS) * 3  # Audi stub: 10 commodities -> 2 detail slides per KPI
    assert out["size_bytes"] > 1_000_000
    assert out["email_subject"] == "VW KPI Report Audi: KW45 vs. KW37"
    assert out["request"]["brand"] == "Audi"

    prs = _deck(stack, out["s3_key"])
    assert len(prs.slides) == out["slides"]
    first = prs.slides[0]
    assert first.shapes.title.text == KPIS[0].title
    texts = [s.text_frame.text for s in first.shapes if s.has_text_frame]
    assert any(t.startswith("KW37 - Audi") for t in texts)
    assert any(t.startswith("KW45 - Audi") for t in texts)
    assert prs.slides[1].shapes.title.text == f"{KPIS[0].title} (1/2)"
    assert len([s for s in prs.slides[1].shapes if s.has_chart]) == 7
    assert len([s for s in prs.slides[2].shapes if s.has_chart]) == 3

    # No run-log row exists for "run-1" (planner did not run) -> update is a no-op, no error
    assert _runs().empty


def test_render_handler_kpi_subset(stack):
    out = lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37", "kpi_ids": ["bka_aktualisierung"]},
        None,
    )
    assert out["slides"] == 2  # Seat: 7 commodities -> one detail slide


def test_render_handler_raises_on_failure(stack, monkeypatch):
    monkeypatch.setattr(settings, "kpi_source_override", "backend")  # no KPI table in SQLite
    with pytest.raises(lambda_handler.RenderFailed):
        lambda_handler.render_handler(
            {"template_id": TEMPLATE_ID, "brand": "Audi", "current_period": "KW45", "reference_period": "KW37"}, None
        )


def test_render_handler_missing_template_in_s3(stack):
    stack["s3"].delete_object(Bucket=BUCKET, Key=TEMPLATE_KEY)
    with pytest.raises(lambda_handler.RenderFailed, match="S3SyncError"):
        lambda_handler.render_handler(
            {"template_id": TEMPLATE_ID, "brand": "Audi", "current_period": "KW45", "reference_period": "KW37"}, None
        )


# ------------------------------------------------------------------------------ #
# Lambda 3
# ------------------------------------------------------------------------------ #


def test_send_handler_sends_from_s3(stack):
    render = lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37",
         "recipients": ["a@x.de", "b@x.de"], "kpi_ids": ["bka_aktualisierung"]},
        None,
    )

    out = lambda_handler.send_handler(render, None)

    assert out["status"] == "sent"
    assert out["message_id"]
    assert out["recipients"] == ["a@x.de", "b@x.de"]
    assert stack["ses"].get_send_quota()["SentLast24Hours"] == 2


def test_send_handler_recipient_override_and_skip(stack, monkeypatch):
    render = lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37", "kpi_ids": ["bka_aktualisierung"]},
        None,
    )
    out = lambda_handler.send_handler({**render, "recipients": ["x@x.de"]}, None)
    assert out["status"] == "sent" and out["recipients"] == ["x@x.de"]

    out = lambda_handler.send_handler(render, None)  # no recipients at all
    assert out["status"] == "skipped"

    monkeypatch.setattr(settings, "mail_enabled", False)
    out = lambda_handler.send_handler({**render, "recipients": ["x@x.de"]}, None)
    assert out["status"] == "skipped" and "mail_enabled" in out["error"]


def test_send_handler_failed_render_is_skipped(stack):
    out = lambda_handler.send_handler(
        {"status": "failed", "request": {"brand": "Audi"}, "error": "boom", "recipients": ["x@x.de"]}, None
    )
    assert out["status"] == "skipped"


# ------------------------------------------------------------------------------ #
# Step Functions round trip: plan -> render -> send, with run log
# ------------------------------------------------------------------------------ #


def test_state_machine_round_trip(stack):
    plan = lambda_handler.plan_handler({"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "KW45"}, None)

    sent = []
    for request in plan["requests"]:
        render = lambda_handler.render_handler(request, None)
        sent.append(lambda_handler.send_handler(render, None))

    assert [s["status"] for s in sent] == ["sent", "sent"]
    runs = _runs().set_index("brand")
    assert set(runs["status"]) == {"sent"}
    assert runs.loc["Audi", "s3_key"].endswith("VW_KPI_Report_Audi_KW45_vs_KW37.pptx")
    assert runs.loc["Seat", "message_id"]
    assert stack["ses"].get_send_quota()["SentLast24Hours"] == 3  # 2 Audi + 1 Seat


# ------------------------------------------------------------------------------ #
# All-in-one handler
# ------------------------------------------------------------------------------ #


def test_all_in_one_manual(stack):
    summary = lambda_handler.handler(
        {"mode": "manual", "template_id": TEMPLATE_ID, "brand": "Audi", "current_period": "KW45",
         "reference_period": "KW37", "recipients": ["a@example.com"]},
        None,
    )
    assert summary["sent"] == 1 and summary["results"][0]["s3_key"]


def test_all_in_one_scheduled(stack):
    summary = lambda_handler.run({"mode": "scheduled", "template_id": TEMPLATE_ID, "current_period": "KW45"})
    assert summary["decks"] == 2 and summary["sent"] == 2


def test_all_in_one_errors():
    with pytest.raises(ValueError, match="Unknown mode"):
        lambda_handler.run({"mode": "nope"})
    with pytest.raises(ValueError, match="identical"):
        lambda_handler.run({"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW45"})


def test_week_helpers():
    assert current_calendar_week(dt.date(2026, 11, 11)) == "2026-KW46"
    assert default_reference_week(dt.date(2026, 11, 11), weeks_back=8) == "2026-KW38"
