"""End-to-end through the render Lambda and the all-in-one handler.

Control tables in pycore's in-memory SQLite, template in moto S3, decks in moto S3, KPI
data from the stub source. Writes decks to tests/result/.
"""

import datetime as dt
import json
from pathlib import Path

import pandas as pd
import pytest
from pptx import Presentation

from pptcreator import lambda_handler
from pptcreator.config import settings
from pptcreator.creator.graph_steer_creation_process import current_calendar_week
from pptcreator.kpi.registry import KPIS, as_mapping_rows
from pptcreator.models.models import (
    AutoreportBrandCommodities,
    AutoreportBrandFeatures,
    AutoreportBrands,
    AutoreportMappings,
    AutoreportRecipients,
    AutoreportRuns,
    AutoreportTemplates,
)
from pptcreator.utils.read_data import read_data
from tests.unit.autoreport_fixtures import TEMPLATE_ID, seed_control_tables, template_rows  # noqa: F401
from tests.unit.infra.conftest import BUCKET, aws  # noqa: F401

VW_PKW_ID = 42

TEMPLATE = Path(__file__).resolve().parent / "test_data" / "VW_Template_Overview_DE.pptx"
RESULT_DIR = Path(__file__).resolve().parents[1] / "result"
TEMPLATE_KEY = "templates/VW_Template_Overview.pptx"


@pytest.fixture
def stack(aws, seed_control_tables, easy_test):  # noqa: F811
    aws["s3"].put_object(Bucket=BUCKET, Key=TEMPLATE_KEY, Body=TEMPLATE.read_bytes())
    seed_control_tables(f"s3://{BUCKET}/{TEMPLATE_KEY}", target_location=f"s3://{BUCKET}/reports/dev")
    return aws


def _request(recipient_id=2, email="b@x.de", brand="Audi", **extra) -> dict:
    """One state machine item, as built by vw-autoreport-detect."""
    return {
        "template_id": TEMPLATE_ID, "brand": brand,
        "current_period": "2025-11-28", "reference_period": "2025-11-18",
        "recipients": [email], "recipient_ids": [recipient_id], "run_id": "run-1", **extra,
    }


def _deck(stack, key: str) -> Presentation:
    data = stack["s3"].get_object(Bucket=BUCKET, Key=key)["Body"].read()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULT_DIR / key.rsplit("/", 1)[-1]
    out.write_bytes(data)
    return Presentation(str(out))


def _runs() -> pd.DataFrame:
    return read_data(AutoreportRuns, [], [])


def test_render_accepts_the_state_machine_input(stack):
    request = _request(kpi_ids=["bka_aktualisierung"])  # keep the test deck small

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


def test_english_template_renders_an_english_deck(stack, data_repo):
    en_key = "templates/VW_Template_Overview_EN.pptx"
    stack["s3"].put_object(Bucket=BUCKET, Key=en_key, Body=TEMPLATE.with_name("VW_Template_Overview_EN.pptx").read_bytes())
    en_row = {**template_rows(f"s3://{BUCKET}/{en_key}", f"s3://{BUCKET}/reports/dev")[0],
              "id": 2, "name": "VW KPI Weekly EN", "language": "EN",
              "target_file_name": "VW_KPI_Report_{brand}_{current}_vs_{reference}_EN"}
    data_repo.write_table(model=AutoreportTemplates, df=pd.DataFrame([en_row]))
    mappings = pd.DataFrame(as_mapping_rows(2, source="stub"))
    mappings["id"] += 100
    data_repo.write_table(model=AutoreportMappings, df=mappings)

    out = lambda_handler.render_handler(
        {"template_id": 2, "brand": "Audi", "current_period": "KW45", "reference_period": "KW37",
         "recipients": ["a@example.com"], "recipient_ids": [1], "kpi_ids": ["bka_aktualisierung"]},
        None,
    )

    assert out["language"] == "EN"
    assert out["file_name"] == "VW_KPI_Report_Audi_KW45_vs_KW37_EN.pptx"
    prs = _deck(stack, out["s3_key"])
    overview = [s.text_frame.text for s in prs.slides[0].shapes if s.has_text_frame]
    assert any(t.startswith("CW37 – Audi") for t in overview)
    detail = [s.text_frame.text for s in prs.slides[1].shapes if s.has_text_frame]
    assert any("Filtered on purchasing organization Audi, all BKAs, CW45" in t for t in detail)

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


def test_brand_policy_is_applied_by_render(stack, data_repo):  # noqa: F811
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
            [{"id": 1, "brand_id": VW_PKW_ID, "feature_key": "footnote_text_de", "feature_value": "Nur sieben COMs.", "is_active": True}]
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

    # kpi_ids is a render-time parameter; keep the test deck small
    request = _request(99, "vw@example.com", "VW PKW", kpi_ids=["bka_aktualisierung"])

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
    request = _request()

    out = json.loads(json.dumps(lambda_handler.render_handler(request, None)))  # as passed by Step Functions

    assert set(out) == {
        "recipient", "recipient_id", "run_id", "brand", "bucket", "s3_key", "file_name", "email_subject",
        "language",
    }
    assert out["language"] == "DE"
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
