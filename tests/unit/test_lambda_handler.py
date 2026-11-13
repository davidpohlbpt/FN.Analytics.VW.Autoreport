"""End-to-end through the three Lambda handlers and the all-in-one handler.

Control tables in pycore's in-memory SQLite, template in moto S3, decks in moto S3,
e-mails via moto SES, KPI data from the stub source. Writes decks to tests/result/.
"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy as sa
from pptx import Presentation
from pycore.easy import database
from sender import app as send_app

from pptcreator import lambda_handler
from pptcreator.config import settings
from pptcreator.creator.graph_steer_creation_process import current_calendar_week
from pptcreator.kpi.registry import KPIS
from pptcreator.lambdas import plan
from pptcreator.models.models import AutoreportRecipients, AutoreportRuns, AutoreportTemplates
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


def test_plan_adhoc_picks_send_now_rows(stack):
    out = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)

    assert out["count"] == 2  # rows 2 (Audi) and 4 (Seat) have send_now = 1
    by_email = {r["recipients"][0]: r for r in out["requests"]}
    assert set(by_email) == {"b@x.de", "d@x.de"}
    assert by_email["b@x.de"]["current_period"] == "2025-11-28"
    assert by_email["b@x.de"]["reference_period"] == "2025-11-18"
    assert by_email["b@x.de"]["recipient_ids"] == [2]
    assert all(r["run_id"] == out["run_id"] and r["trigger"] == "adhoc" for r in out["requests"])

    # plan claims the rows but does not touch send_now; the record step clears it
    runs = _runs()
    assert len(runs) == 2 and set(runs["status"]) == {"processing"}
    assert set(runs["recipient_id"]) == {2, 4}
    assert read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]


def test_plan_skips_rows_with_an_open_claim(stack):
    first = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    assert first["count"] == 2

    # the poller runs again before the first run finished: those rows must not be sent twice
    second = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    assert second["count"] == 0 and second["skipped"] == 2 and second["requests"] == []
    assert len(_runs()) == 2

    # once recorded, the row is free again (a deliberate resend by the frontend)
    lambda_handler.record_handler({"run_id": first["run_id"], "results": [
        {"status": "failed", "step": "send", "request": r, "error": {"Error": "SendFailed", "Cause": "x"}}
        for r in first["requests"]
    ]}, None)
    third = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    assert third["count"] == 2


def test_plan_scheduled_plans_every_row(stack):
    out = lambda_handler.plan_handler({"trigger": "scheduled", "template_id": TEMPLATE_ID}, None)

    assert out["count"] == 5  # every valid row, one deck each
    assert len({tuple(r["recipient_ids"]) for r in out["requests"]}) == 5


def test_plan_recipient_id_filter(stack):
    out = lambda_handler.plan_handler(
        {"trigger": "scheduled", "template_id": TEMPLATE_ID, "recipient_ids": [3]}, None
    )
    assert out["count"] == 1 and out["requests"][0]["recipients"] == ["c@x.de"]


def test_plan_default_trigger_is_adhoc(stack):
    out = lambda_handler.plan_handler({"template_id": TEMPLATE_ID}, None)
    assert out["trigger"] == "adhoc" and out["count"] == 2


def test_plan_rejects_bad_trigger(stack):
    with pytest.raises(ValueError, match="trigger must be"):
        lambda_handler.plan_handler({"trigger": "manual"}, None)


def test_plan_template_ids_from_env_and_partial_failure(stack, monkeypatch):
    monkeypatch.setattr(settings, "plan_template_ids", f"{TEMPLATE_ID}, 99")

    out = lambda_handler.plan_handler({"trigger": "adhoc"}, None)

    assert out["template_ids"] == [TEMPLATE_ID, 99]
    assert out["count"] == 2  # template 99 does not exist, the others are still planned
    assert [e["template_id"] for e in out["errors"]] == [99]

    # the event wins over the environment
    with pytest.raises(lambda_handler.PlanFailed, match="All templates failed"):
        lambda_handler.plan_handler({"trigger": "scheduled", "template_ids": [99]}, None)


def test_plan_template_ids_all_and_default(stack, monkeypatch):
    monkeypatch.setattr(settings, "default_template_id", None)
    monkeypatch.setattr(settings, "plan_template_ids", "all")
    assert plan.resolve_template_ids({}) == [TEMPLATE_ID]
    monkeypatch.setattr(settings, "plan_template_ids", None)
    monkeypatch.setattr(settings, "default_template_id", 7)
    assert plan.resolve_template_ids({}) == [7]
    assert plan.resolve_template_ids({"template_id": "3;5;3"}) == [3, 5]


def test_plan_payload_too_large_has_no_side_effects(stack, monkeypatch):
    monkeypatch.setattr(plan, "MAX_PAYLOAD_BYTES", 100)
    with pytest.raises(lambda_handler.PlanFailed, match="Step Functions"):
        lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    assert _runs().empty  # no claim written when the payload would not fit


def test_render_uses_template_snapshot_from_plan(stack):
    request = lambda_handler.plan_handler(
        {"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"}, None
    )["requests"][0]
    assert request["template"]["id"] == TEMPLATE_ID and len(request["template"]["kpis"]) == len(KPIS)

    # The control tables change after planning: the run keeps its snapshot
    table = AutoreportTemplates.__table__
    with database.engine.begin() as con:
        con.execute(sa.update(table).values(is_active=False))

    out = lambda_handler.render_handler(request, None)
    assert out["status"] == "rendered"
    assert "template" not in out["request"]  # Step Functions payload stays small

    without_snapshot = {k: v for k, v in request.items() if k != "template"}
    with pytest.raises(lambda_handler.RenderFailed, match="not found or inactive"):
        lambda_handler.render_handler(without_snapshot, None)


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
    assert any(t.startswith("KW37 – Audi") for t in texts)
    assert any(t.startswith("KW45 – Audi") for t in texts)
    for slide in (first, prs.slides[1]):
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
        assert "Target – Marke Audi\n \n " in texts
        assert "IDM, Filterung auf Einkaufsorganisation Audi, alle BKAs, KW45, V11 " in texts
    assert prs.slides[1].shapes.title.text == f"{KPIS[0].title} (1/2)"
    assert len([s for s in prs.slides[1].shapes if s.has_chart]) == 5  # 10 commodities -> 5 + 5
    assert len([s for s in prs.slides[2].shapes if s.has_chart]) == 5

    # No run-log row exists for "run-1" (planner did not run) -> update is a no-op, no error
    assert _runs().empty


def test_render_handler_kpi_subset(stack):
    out = lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37", "kpi_ids": ["bka_aktualisierung"]},
        None,
    )
    assert out["slides"] == 2  # Seat: 7 commodities -> one detail slide


def test_render_handler_output_bucket_env_overrides_template_row(stack, monkeypatch):
    stack["s3"].create_bucket(Bucket="client-output", CreateBucketConfiguration={"LocationConstraint": "eu-central-1"})
    monkeypatch.setattr(settings, "s3_output_bucket", "client-output")
    monkeypatch.setattr(settings, "s3_output_prefix", "autoreport")

    out = lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37", "kpi_ids": ["bka_aktualisierung"]},
        None,
    )

    assert out["bucket"] == "client-output"
    assert out["s3_key"] == f"autoreport/{out['file_name']}"
    stack["s3"].head_object(Bucket="client-output", Key=out["s3_key"])


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
# Lambda 3 (separate ZIP package): contract with the render output
# ------------------------------------------------------------------------------ #


def _seat_render(**extra):
    return lambda_handler.render_handler(
        {"template_id": TEMPLATE_ID, "brand": "Seat", "current_period": "KW45", "reference_period": "KW37",
         "kpi_ids": ["bka_aktualisierung"], **extra},
        None,
    )


def test_send_handler_sends_render_output_from_s3(stack):
    render = _seat_render(recipients=["a@x.de", "b@x.de"])

    out = send_app.handler(json.loads(json.dumps(render)), None)  # as passed by Step Functions

    assert out["status"] == "sent"
    assert out["message_id"]
    assert out["recipients"] == ["a@x.de", "b@x.de"]
    assert stack["ses"].get_send_quota()["SentLast24Hours"] == 2


def test_send_handler_recipient_override_and_skip(stack, monkeypatch):
    render = _seat_render()
    out = send_app.handler({**render, "recipients": ["x@x.de"]}, None)
    assert out["status"] == "sent" and out["recipients"] == ["x@x.de"]

    out = send_app.handler(render, None)  # no recipients at all
    assert out["status"] == "skipped"

    monkeypatch.setenv("MAIL_ENABLED", "false")
    out = send_app.handler({**render, "recipients": ["x@x.de"]}, None)
    assert out["status"] == "skipped" and "MAIL_ENABLED" in out["error"]


def test_send_handler_raises_when_deck_is_missing(stack):
    render = _seat_render(recipients=["a@x.de"])
    stack["s3"].delete_object(Bucket=render["bucket"], Key=render["s3_key"])
    with pytest.raises(send_app.SendFailed, match="NoSuchKey"):
        send_app.handler(render, None)


def test_send_handler_failed_render_is_skipped():
    out = send_app.handler(
        {"status": "failed", "request": {"brand": "Audi"}, "error": "boom", "recipients": ["x@x.de"]}, None
    )
    assert out["status"] == "skipped"


# ------------------------------------------------------------------------------ #
# Step Functions round trip: plan -> Map(render -> send) -> record
# ------------------------------------------------------------------------------ #


def test_state_machine_round_trip(stack):
    plan = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)

    decks = []
    for request in plan["requests"]:
        render = lambda_handler.render_handler(request, None)
        decks.append(send_app.handler(render, None))
    # what the Catch of a failed render deck hands to the record step: a row with
    # send_now = 0 that this run also claimed, so the run log already has its row
    pending = lambda_handler.plan_handler(
        {"trigger": "scheduled", "template_id": TEMPLATE_ID, "recipient_ids": [3]}, None
    )["requests"][0]
    decks.append({
        "status": "failed", "step": "render", "request": pending,
        "error": {"Error": "RenderFailed", "Cause": json.dumps({"errorMessage": "no data"})},
    })

    assert [d["status"] for d in decks[:2]] == ["sent", "sent"]
    # render updated its claim, the extra row is still only claimed; send has no DB access
    assert set(_runs()["status"]) == {"rendered", "processing"}

    out = lambda_handler.record_handler({"run_id": plan["run_id"], "results": decks}, None)

    assert out == {"run_id": plan["run_id"], "recorded": 3, "sent": 2, "skipped": 0, "failed": 1, "cleared": 2}
    runs = _runs().set_index("recipient_id")
    assert runs.loc[2, "status"] == "sent" and runs.loc[2, "message_id"]
    assert runs.loc[2, "user_email"] == "b@x.de"
    assert runs.loc[2, "s3_key"].endswith("VW_KPI_Report_Audi_2025-11-28_vs_2025-11-18.pptx")
    assert runs.loc[4, "status"] == "sent"
    assert runs.loc[3, "status"] == "failed"
    assert "no data" in runs.loc[3, "error"]
    assert stack["ses"].get_send_quota()["SentLast24Hours"] == 2

    # send_now of the sent rows is gone; nothing else was touched
    send_now = read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]
    assert not send_now
    assert not read_data(AutoreportRecipients, ["id"], [4])["send_now"].iloc[0]
    assert not read_data(AutoreportRecipients, ["id"], [1])["send_now"].iloc[0]  # was already false


def test_skip_leaves_send_now_cleared_but_row_not_resent(stack):
    plan = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    request = plan["requests"][0]

    # MAIL_ENABLED=false in the send Lambda -> skipped, still a finished run
    out = lambda_handler.record_handler({"run_id": plan["run_id"], "results": [
        {"status": "skipped", "request": request, "error": "MAIL_ENABLED is false."}
    ]}, None)

    assert out["sent"] == 0 and out["skipped"] == 1 and out["cleared"] == 1
    assert _runs().set_index("recipient_id").loc[request["recipient_ids"][0], "status"] == "skipped"
    assert not read_data(AutoreportRecipients, ["id"], [request["recipient_ids"][0]])["send_now"].iloc[0]


def test_record_handler_failure_keeps_send_now(stack):
    plan = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID}, None)
    by_email = {r["recipients"][0]: r for r in plan["requests"]}

    lambda_handler.record_handler({"run_id": plan["run_id"], "results": [
        {"status": "failed", "step": "send", "request": by_email["d@x.de"],
         "error": {"Error": "SendFailed", "Cause": json.dumps({"errorMessage": "SES down"})}},
    ]}, None)

    runs = _runs().set_index("recipient_id")
    assert runs.loc[4, "status"] == "failed" and runs.loc[4, "error"] == "SendFailed: SES down"
    assert runs.loc[2, "status"] == "processing"  # not part of this record call
    # the failed row keeps send_now, so the user sees it was not delivered (no auto retry,
    # the claim row is closed which is what stops the poller from looping)
    assert read_data(AutoreportRecipients, ["id"], [4])["send_now"].iloc[0]


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
    summary = lambda_handler.run({"mode": "scheduled", "template_id": TEMPLATE_ID})
    assert summary["decks"] == 5 and summary["sent"] == 5  # one deck per recipient row


def test_all_in_one_errors():
    with pytest.raises(ValueError, match="Unknown mode"):
        lambda_handler.run({"mode": "nope"})
    with pytest.raises(ValueError, match="identical"):
        lambda_handler.run({"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW45"})


def test_week_helpers():
    assert current_calendar_week(dt.date(2026, 11, 11)) == "2026-KW46"
