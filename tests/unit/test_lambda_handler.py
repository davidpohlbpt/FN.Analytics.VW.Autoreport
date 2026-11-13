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


def test_plan_scheduled(stack):
    out = lambda_handler.plan_handler(
        {"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"}, None
    )

    assert out["count"] == 3
    by_key = {(r["brand"], r["reference_period"]): r for r in out["requests"]}
    assert by_key[("Audi", "2026-KW37")]["recipients"] == ["a@x.de", "b@x.de"]
    assert by_key[("Audi", "2025-KW37")]["recipients"] == ["A@x.de"]  # same brand, other week
    assert by_key[("Seat", "2026-KW40")]["recipients"] == ["c@x.de"]
    assert all(r["run_id"] == out["run_id"] and r["trigger"] == "scheduled" for r in out["requests"])

    runs = _runs()
    assert len(runs) == 3 and set(runs["status"]) == {"queued"}
    # scheduled run must not touch send_now
    assert read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]


def test_plan_adhoc_clears_send_now(stack):
    out = lambda_handler.plan_handler({"trigger": "adhoc", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"}, None)

    assert out["count"] == 1
    assert out["requests"][0]["recipients"] == ["b@x.de"]
    assert out["requests"][0]["recipient_ids"] == [2]
    assert not read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]
    assert read_data(AutoreportRecipients, ["id"], [4])["send_now"].iloc[0]  # inactive row untouched


def test_plan_rejects_bad_trigger(stack):
    with pytest.raises(ValueError, match="trigger must be"):
        lambda_handler.plan_handler({"trigger": "manual"}, None)


def test_plan_template_ids_from_env_and_partial_failure(stack, monkeypatch):
    monkeypatch.setattr(settings, "plan_template_ids", f"{TEMPLATE_ID}, 99")

    out = lambda_handler.plan_handler({"trigger": "scheduled", "current_period": "2026-KW45"}, None)

    assert out["template_ids"] == [TEMPLATE_ID, 99]
    assert out["count"] == 3  # template 99 does not exist, the others are still planned
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
    assert _runs().empty
    assert read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]


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
    plan = lambda_handler.plan_handler({"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"}, None)

    decks = []
    for request in plan["requests"]:
        render = lambda_handler.render_handler(request, None)
        decks.append(send_app.handler(render, None))
    # what the Catch of a failed render deck hands to the record step
    decks.append({
        "status": "failed", "step": "render",
        "request": {"run_id": plan["run_id"], "brand": "Skoda", "reference_period": "2026-KW30"},
        "error": {"Error": "RenderFailed", "Cause": json.dumps({"errorMessage": "no data"})},
    })

    assert [d["status"] for d in decks[:3]] == ["sent", "sent", "sent"]
    assert set(_runs()["status"]) == {"rendered"}  # the send Lambda has no database access

    out = lambda_handler.record_handler({"run_id": plan["run_id"], "results": decks}, None)

    assert out == {"run_id": plan["run_id"], "recorded": 4, "sent": 3, "skipped": 0, "failed": 1}
    runs = _runs().set_index(["brand", "reference_period"])
    assert set(runs["status"]) == {"sent"}  # the Skoda deck has no queued row, so nothing to update
    assert runs.loc[("Audi", "2026-KW37"), "s3_key"].endswith("VW_KPI_Report_Audi_2026-KW45_vs_2026-KW37.pptx")
    assert runs.loc[("Audi", "2025-KW37"), "s3_key"].endswith("VW_KPI_Report_Audi_2026-KW45_vs_2025-KW37.pptx")
    assert runs.loc[("Seat", "2026-KW40"), "message_id"]
    assert stack["ses"].get_send_quota()["SentLast24Hours"] == 4  # 2 + 1 Audi, 1 Seat


def test_record_handler_maps_skipped_and_failed(stack):
    plan = lambda_handler.plan_handler({"trigger": "scheduled", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"}, None)
    by_key = {(r["brand"], r["reference_period"]): r for r in plan["requests"]}
    audi, other_audi, seat = by_key[("Audi", "2026-KW37")], by_key[("Audi", "2025-KW37")], by_key[("Seat", "2026-KW40")]

    lambda_handler.record_handler({"run_id": plan["run_id"], "results": [
        {"status": "skipped", "request": audi, "error": "MAIL_ENABLED is false."},
        {"status": "failed", "step": "send", "request": seat,
         "error": {"Error": "SendFailed", "Cause": json.dumps({"errorMessage": "SES down"})}},
    ]}, None)

    runs = _runs().set_index(["brand", "reference_period"])
    assert runs.loc[(audi["brand"], audi["reference_period"]), "status"] == "rendered"
    assert runs.loc[(other_audi["brand"], other_audi["reference_period"]), "status"] == "queued"
    assert runs.loc[(seat["brand"], seat["reference_period"]), "status"] == "failed"
    assert runs.loc[(seat["brand"], seat["reference_period"]), "error"] == "SendFailed: SES down"


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
    summary = lambda_handler.run({"mode": "scheduled", "template_id": TEMPLATE_ID, "current_period": "2026-KW45"})
    assert summary["decks"] == 3 and summary["sent"] == 3


def test_all_in_one_errors():
    with pytest.raises(ValueError, match="Unknown mode"):
        lambda_handler.run({"mode": "nope"})
    with pytest.raises(ValueError, match="identical"):
        lambda_handler.run({"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW45"})


def test_week_helpers():
    assert current_calendar_week(dt.date(2026, 11, 11)) == "2026-KW46"
