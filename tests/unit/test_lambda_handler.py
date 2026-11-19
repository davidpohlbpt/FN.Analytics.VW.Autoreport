"""End-to-end through the plan and render Lambdas and the all-in-one handler.

Control tables in pycore's in-memory SQLite, template in moto S3, decks in moto S3, KPI
data from the stub source. Writes decks to tests/result/.
"""

import datetime as dt
import json
from pathlib import Path

import boto3
import pandas as pd
import pytest
import sqlalchemy as sa
from pptx import Presentation
from pycore.easy import database

from pptcreator import lambda_handler
from pptcreator.config import settings
from pptcreator.creator.graph_steer_creation_process import current_calendar_week
from pptcreator.kpi.registry import KPIS
from pptcreator.models.models import (
    AutoreportBrandCommodities,
    AutoreportBrandFeatures,
    AutoreportBrands,
    AutoreportRecipients,
    AutoreportRuns,
)
from pptcreator.utils import run_log
from pptcreator.utils.read_data import read_data
from tests.unit.autoreport_fixtures import TEMPLATE_ID, seed_control_tables  # noqa: F401
from tests.unit.infra.conftest import BUCKET, REGION, aws  # noqa: F401

VW_PKW_ID = 42

TEMPLATE = Path(__file__).resolve().parent / "test_data" / "VW_Template_Overview.pptx"
RESULT_DIR = Path(__file__).resolve().parents[1] / "result"
TEMPLATE_KEY = "templates/VW_Template_Overview.pptx"


@pytest.fixture
def stack(aws, seed_control_tables, easy_test, monkeypatch):  # noqa: F811
    aws["s3"].put_object(Bucket=BUCKET, Key=TEMPLATE_KEY, Body=TEMPLATE.read_bytes())
    seed_control_tables(f"s3://{BUCKET}/{TEMPLATE_KEY}", target_location=f"s3://{BUCKET}/reports/dev")
    sfn = boto3.client("stepfunctions", region_name=REGION)
    arn = sfn.create_state_machine(
        name="vw-autoreport-test", definition=json.dumps({"StartAt": "X", "States": {"X": {"Type": "Succeed"}}}),
        roleArn="arn:aws:iam::123456789012:role/sfn",
    )["stateMachineArn"]
    monkeypatch.setattr(settings, "state_machine_arn", arn)
    return {**aws, "sfn": sfn, "state_machine_arn": arn}


def _deck(stack, key: str) -> Presentation:
    data = stack["s3"].get_object(Bucket=BUCKET, Key=key)["Body"].read()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULT_DIR / key.rsplit("/", 1)[-1]
    out.write_bytes(data)
    return Presentation(str(out))


def _runs() -> pd.DataFrame:
    return read_data(AutoreportRuns, [], [])


def _set_send_now(*recipient_ids: int) -> None:
    table = AutoreportRecipients.__table__
    with database.engine.begin() as con:
        con.execute(sa.update(table).where(table.c.id.in_(recipient_ids)).values(send_now=True))


# ------------------------------------------------------------------------------ #
# Lambda 1
# ------------------------------------------------------------------------------ #


def test_plan_picks_send_now_rows_of_active_templates(stack):
    out = lambda_handler.plan_handler({}, None)

    assert out["count"] == 2  # rows 2 (Audi) and 4 (Seat) have send_now = 1
    assert out["has_requests"] is True
    by_email = {r["recipients"][0]: r for r in out["requests"]}
    assert set(by_email) == {"b@x.de", "d@x.de"}
    # exactly what render and vw-autoreport-sendemail need, nothing else
    run_id = by_email["b@x.de"]["run_id"]
    assert run_id and by_email["d@x.de"]["run_id"] == run_id
    assert by_email["b@x.de"] == {
        "template_id": TEMPLATE_ID, "brand": "Audi",
        "current_period": "2025-11-28", "reference_period": "2025-11-18",
        "recipients": ["b@x.de"], "recipient_ids": [2], "run_id": run_id,
    }
    assert set(out) == {"has_requests", "count", "requests", "execution_arn"}

    # plan claims the rows but does not touch send_now; the send Lambda resets it
    runs = _runs()
    assert len(runs) == 2 and set(runs["status"]) == {"processing"}
    assert set(runs["run_id"]) == {run_id}
    assert set(runs["recipient_id"]) == {2, 4}
    assert read_data(AutoreportRecipients, ["id"], [2])["send_now"].iloc[0]


def test_plan_starts_one_execution_and_skips_open_claims(stack):
    sfn, arn = stack["sfn"], stack["state_machine_arn"]

    first = lambda_handler.plan_handler({}, None)

    executions = sfn.list_executions(stateMachineArn=arn)["executions"]
    assert [e["executionArn"] for e in executions] == [first["execution_arn"]]
    started_with = json.loads(sfn.describe_execution(executionArn=first["execution_arn"])["input"])
    assert started_with == {key: first[key] for key in ("has_requests", "count", "requests")}

    # the poller runs again before the first run finished: those rows must not be sent twice
    second = lambda_handler.plan_handler({}, None)
    assert second == {"has_requests": False, "count": 0, "requests": []}
    assert len(sfn.list_executions(stateMachineArn=arn)["executions"]) == 1
    assert len(_runs()) == 2

    # once the send Lambda wrote a final status, the row is free again
    for r in first["requests"]:
        run_log.update_status(None, r["brand"], r["reference_period"], status="failed", recipient_id=r["recipient_ids"][0])
    assert lambda_handler.plan_handler({}, None)["count"] == 2


def test_plan_without_state_machine_fails_before_claiming(stack, monkeypatch):
    monkeypatch.setattr(settings, "state_machine_arn", None)

    with pytest.raises(lambda_handler.PlanFailed, match="STATE_MACHINE_ARN"):
        lambda_handler.plan_handler({}, None)

    assert _runs().empty


def test_failed_step_function_start_releases_the_claims(stack, monkeypatch):
    monkeypatch.setattr(settings, "state_machine_arn", f"arn:aws:states:{REGION}:123456789012:stateMachine:missing")

    with pytest.raises(lambda_handler.PlanFailed, match="Could not start"):
        lambda_handler.plan_handler({}, None)

    assert set(_runs()["status"]) == {"failed"}  # claims closed, send_now still set
    monkeypatch.setattr(settings, "state_machine_arn", stack["state_machine_arn"])
    assert lambda_handler.plan_handler({}, None)["count"] == 2  # next poll retries


def test_render_accepts_the_plan_output(stack):
    planned = lambda_handler.plan_handler({}, None)["requests"]
    request = next(r for r in planned if r["recipient_ids"] == [2])
    request["kpi_ids"] = ["bka_aktualisierung"]  # keep the test deck small

    out = lambda_handler.render_handler(request, None)
    assert out["recipient"] == "b@x.de"  # passed on to the send step


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

    assert out["file_name"] == "VW_KPI_Report_Audi_KW45_vs_KW37.pptx"
    assert out["bucket"] == BUCKET
    assert out["s3_key"] == f"reports/dev/{out['file_name']}"  # target_location from the template table
    assert out["email_subject"] == "VW KPI Report Audi: KW45 vs. KW37"
    assert out["brand"] == "Audi"
    assert stack["s3"].head_object(Bucket=out["bucket"], Key=out["s3_key"])["ContentLength"] > 1_000_000

    prs = _deck(stack, out["s3_key"])
    assert len(prs.slides) == len(KPIS) * 3  # Audi stub: 10 commodities -> 2 detail slides per KPI
    first = prs.slides[0]
    assert first.shapes.title.text == KPIS[0].title
    texts = [s.text_frame.text for s in first.shapes if s.has_text_frame]
    assert any(t.startswith("KW37 – Audi") for t in texts)
    assert any(t.startswith("KW45 – Audi") for t in texts)
    for slide in (first, prs.slides[1]):
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
        # stub source has no LAUFKENNUNG: {datenquelle_run} falls back to the week label
        assert any("Filterung auf Einkaufsorganisation Audi, alle BKAs, KW45" in t for t in texts)
        assert not any("{datenquelle_run}" in t or "{brand}" in t for t in texts)
    # Audi has no footnote row -> the template's {footnote} shape is not copied at all
    for slide in prs.slides:
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
        assert not any("{footnote}" in t for t in texts)
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
    assert len(_deck(stack, out["s3_key"]).slides) == 2  # Seat: 7 commodities -> one detail slide

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


def test_brand_policy_travels_from_plan_to_render(stack, data_repo):  # noqa: F811
    """The plan snapshot carries the policy, so render never re-reads the brand tables."""
    data_repo.write_table(
        model=AutoreportBrands,
        df=pd.DataFrame(
            [{"id": VW_PKW_ID, "brand_name": "Volkswagen PKW", "filter_value": "VW PKW", "is_active": True}]
        ),
    )
    data_repo.write_table(
        model=AutoreportBrandCommodities,
        df=pd.DataFrame(
            [
                {
                    "id": i,
                    "brand_id": VW_PKW_ID,
                    "com_source": source,
                    "com_label": label,
                    "sort_order": order,
                    "show_if_zero": True,
                    "is_active": True,
                }
                for i, (source, label, order) in enumerate(
                    [("BC", "BC", 10), ("BI", "BI", 20), ("BM", "BM", 30), ("BN", "BN", 40),
                     ("BX", "BX", 50), ("BP", "CB", 60), ("BL", "ZB", 70)],
                    start=1,
                )
            ]
        ),
    )
    data_repo.write_table(
        model=AutoreportBrandFeatures,
        df=pd.DataFrame(
            [{"id": 1, "brand_id": VW_PKW_ID, "feature_key": "footnote_text", "feature_value": "Nur sieben COMs.", "is_active": True}]
        ),
    )
    data_repo.write_table(
        model=AutoreportRecipients,
        df=pd.DataFrame(
            [
                {
                    "id": 99,
                    "template_id": TEMPLATE_ID,
                    "email": "vw@example.com",
                    "brand_id": VW_PKW_ID,
                    "report_week": "2025-11-28",
                    "comparison_week": "2025-11-18",
                    "send_now": True,
                    "IsDeleted": False,
                }
            ]
        ),
    )

    planned = lambda_handler.plan_handler({}, None)
    request = next(r for r in planned["requests"] if r["recipient_ids"] == [99])
    # kpi_ids is a render-time parameter; keep the test deck small
    request["kpi_ids"] = ["bka_aktualisierung"]

    out = lambda_handler.render_handler(request, None)

    prs = _deck(stack, out["s3_key"])
    assert len(prs.slides) == 2  # 7 configured commodities -> one detail slide
    detail_texts = [s.text_frame.text for s in prs.slides[1].shapes if s.has_text_frame]
    assert "Nur sieben COMs." in detail_texts
    assert sum(1 for s in prs.slides[1].shapes if s.has_chart) == 7
    # The renamed commodities are shown under their VW PKW labels
    assert any(t.startswith("CB") for t in detail_texts)
    assert any(t.startswith("ZB") for t in detail_texts)
    assert not any(t.startswith("BP") for t in detail_texts)
    assert not any(t.startswith("BL") for t in detail_texts)


# ------------------------------------------------------------------------------ #
# Step Functions: render output is the vw-autoreport-sendemail event
# ------------------------------------------------------------------------------ #


def test_render_output_contains_the_send_email_event(stack):
    plan = lambda_handler.plan_handler({}, None)
    request = plan["requests"][0]

    out = json.loads(json.dumps(lambda_handler.render_handler(request, None)))  # as passed by Step Functions

    assert set(out) == {
        "recipient", "recipient_id", "run_id", "brand", "bucket", "s3_key", "file_name", "email_subject"
    }
    assert out["bucket"] == BUCKET
    assert out["s3_key"].startswith("reports/dev/") and out["s3_key"].endswith(".pptx")
    assert out["file_name"] == out["s3_key"].rsplit("/", 1)[1]
    assert out["recipient"] == request["recipients"][0]
    assert out["recipient_id"] == request["recipient_ids"][0]
    assert out["brand"] == request["brand"]
    assert out["run_id"] == request["run_id"]
    assert out["email_subject"]
    stack["s3"].head_object(Bucket=out["bucket"], Key=out["s3_key"])
    # render never changes send_now; the send Lambda resets it after sending
    assert read_data(AutoreportRecipients, ["id"], [request["recipient_ids"][0]])["send_now"].iloc[0]


# ------------------------------------------------------------------------------ #
# All-in-one handler
# ------------------------------------------------------------------------------ #


def test_all_in_one_manual(stack):
    summary = lambda_handler.handler(
        {"mode": "manual", "template_id": TEMPLATE_ID, "brand": "Audi", "current_period": "KW45",
         "reference_period": "KW37", "recipients": ["a@example.com"]},
        None,
    )
    assert summary["rendered"] == 1 and summary["results"][0]["s3_key"]


def test_all_in_one_adhoc(stack):
    summary = lambda_handler.run({"mode": "adhoc", "template_id": TEMPLATE_ID})
    assert summary["decks"] == 2 and summary["rendered"] == 2  # one deck per send_now row


def test_all_in_one_errors():
    with pytest.raises(ValueError, match="Unknown mode"):
        lambda_handler.run({"mode": "nope"})
    with pytest.raises(ValueError, match="identical"):
        lambda_handler.run({"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW45"})


def test_week_helpers():
    assert current_calendar_week(dt.date(2026, 11, 11)) == "2026-KW46"
