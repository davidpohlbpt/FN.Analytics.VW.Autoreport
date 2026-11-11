"""End-to-end: Lambda event -> deck rendered from the VW template -> S3 -> SES.

Uses the stub KPI source, moto for AWS and pycore's in-memory SQLite for the recipient
table. Writes the manual-mode deck to tests/result/ for visual inspection.
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
    group_recipients,
)
from pptcreator.kpi.registry import KPIS
from pptcreator.models.models import ReportRecipients
from tests.unit.infra.conftest import BUCKET, aws  # noqa: F401  (fixture re-export)

TEMPLATE = Path(__file__).resolve().parent / "test_data" / "VW_Template_Overview.pptx"
RESULT_DIR = Path(__file__).resolve().parents[1] / "result"


@pytest.fixture
def template_in_s3(aws):  # noqa: F811
    aws["s3"].put_object(Bucket=BUCKET, Key=settings.s3_template_key, Body=TEMPLATE.read_bytes())
    return aws


def _deck_from_storage(easy_test, file_name: str) -> Presentation:
    data = easy_test.storage.read_blob(
        container_name=settings.storage_container, blob_name=file_name, decode=False
    )
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULT_DIR / file_name
    out.write_bytes(data)
    return Presentation(str(out))


def test_manual_mode_end_to_end(template_in_s3, easy_test):
    event = {
        "mode": "manual",
        "brand": "Audi",
        "current_period": "KW45",
        "reference_period": "KW37",
        "recipients": ["a@example.com", "b@example.com"],
    }

    summary = lambda_handler.handler(event, context=None)

    assert summary["decks"] == 1
    assert summary["sent"] == 1, summary
    result = summary["results"][0]
    assert result["status"] == "sent"
    assert result["file_name"] == "VW_KPI_Report_Audi_KW45_vs_KW37.pptx"
    assert result["s3_key"] == f"{settings.s3_output_prefix}/{result['file_name']}"
    assert result["message_id"]

    # Deck uploaded to S3
    head = template_in_s3["s3"].head_object(Bucket=BUCKET, Key=result["s3_key"])
    assert head["ContentLength"] > 0

    # Deck structure: per KPI 1 overview + 2 detail slides (Audi stub has 10 commodities)
    prs = _deck_from_storage(easy_test, result["file_name"])
    assert len(prs.slides) == len(KPIS) * 3
    first = prs.slides[0]
    assert first.shapes.title.text == KPIS[0].title
    charts = [s for s in first.shapes if s.has_chart]
    assert len(charts) == 2
    texts = [s.text_frame.text for s in first.shapes if s.has_text_frame]
    assert any(t.startswith("KW37 - Audi") for t in texts)
    assert any(t.startswith("KW45 - Audi") for t in texts)
    assert any(s.name == "Legend" for s in first.shapes)

    second = prs.slides[1]
    assert second.shapes.title.text == f"{KPIS[0].title} (1/2)"
    assert len([s for s in second.shapes if s.has_chart]) == 7
    third = prs.slides[2]
    assert third.shapes.title.text == f"{KPIS[0].title} (2/2)"
    assert len([s for s in third.shapes if s.has_chart]) == 3

    # SES received one message per recipient
    assert template_in_s3["ses"].get_send_quota()["SentLast24Hours"] == 2


def test_manual_mode_kpi_subset_without_recipients(template_in_s3, easy_test):
    event = {
        "mode": "manual",
        "brand": "Seat",
        "current_period": "KW45",
        "reference_period": "KW37",
        "kpi_ids": ["kpi1"],
    }
    summary = lambda_handler.run(event)
    assert summary["rendered"] == 1 and summary["sent"] == 0
    prs = _deck_from_storage(easy_test, summary["results"][0]["file_name"])
    assert len(prs.slides) == 2  # Seat uses the 7-commodity default -> no pagination


def test_mail_disabled_reports_rendered(template_in_s3, easy_test, monkeypatch):
    monkeypatch.setattr(settings, "mail_enabled", False)
    summary = lambda_handler.run(
        {
            "mode": "manual",
            "brand": "Seat",
            "current_period": "KW45",
            "reference_period": "KW37",
            "recipients": ["a@example.com"],
            "kpi_ids": ["kpi1"],
        }
    )
    assert summary["rendered"] == 1 and summary["sent"] == 0
    assert summary["results"][0]["message_id"] is None
    assert template_in_s3["ses"].get_send_quota()["SentLast24Hours"] == 0


def test_failure_is_reported_not_raised(template_in_s3, easy_test, monkeypatch):
    monkeypatch.setattr(settings, "template_file_name", "does_not_exist.pptx")
    monkeypatch.setattr(settings, "s3_template_key", "missing/key.pptx")
    summary = lambda_handler.run(
        {"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW37"}
    )
    assert summary["failed"] == 1
    assert "S3SyncError" in summary["results"][0]["error"]


def test_invalid_mode_and_periods():
    with pytest.raises(ValueError, match="Unknown mode"):
        lambda_handler.run({"mode": "nope"})
    with pytest.raises(ValueError, match="identical"):
        lambda_handler.run({"mode": "manual", "brand": "Audi", "current_period": "KW45", "reference_period": "KW45"})


def test_scheduled_mode_groups_recipients(template_in_s3, easy_test, data_repo):
    data_repo.database.create_all_tables()
    data_repo.write_table(
        model=ReportRecipients,
        df=pd.DataFrame(
            [
                {"id": 1, "email": "a@x.de", "brand": "Audi", "reference_timestamp": "KW37", "send_now": False, "is_active": True, "lasteditedat": None},
                {"id": 2, "email": "b@x.de", "brand": "Audi", "reference_timestamp": "KW37", "send_now": False, "is_active": True, "lasteditedat": None},
                {"id": 3, "email": "c@x.de", "brand": "Seat", "reference_timestamp": None, "send_now": False, "is_active": True, "lasteditedat": None},
                {"id": 4, "email": "d@x.de", "brand": "Seat", "reference_timestamp": "KW30", "send_now": False, "is_active": False, "lasteditedat": None},
                {"id": 5, "email": "", "brand": "Skoda", "reference_timestamp": "KW30", "send_now": False, "is_active": True, "lasteditedat": None},
            ]
        ),
    )

    summary = lambda_handler.run(
        {"mode": "scheduled", "current_period": "KW45", "reference_period": "KW40"}
    )

    assert summary["decks"] == 2, summary
    by_brand = {r["brand"]: r for r in summary["results"]}
    assert by_brand["Audi"]["recipients"] == ["a@x.de", "b@x.de"]
    assert by_brand["Audi"]["reference_period"] == "KW37"
    assert by_brand["Seat"]["recipients"] == ["c@x.de"]
    assert by_brand["Seat"]["reference_period"] == "KW40"  # default applied
    assert all(r["status"] == "sent" for r in summary["results"])


def test_group_recipients_skips_bad_reference():
    df = pd.DataFrame(
        [
            {"id": 1, "email": "a@x.de", "brand": "Audi", "reference_timestamp": "garbage"},
            {"id": 2, "email": "b@x.de", "brand": "Audi", "reference_timestamp": "KW45"},  # == current
            {"id": 3, "email": "c@x.de", "brand": "Audi", "reference_timestamp": "KW10"},
        ]
    )
    requests = group_recipients(df, current_period="KW45", default_reference_period="KW40")
    assert len(requests) == 1
    assert requests[0].recipients == ["c@x.de"]


def test_week_helpers():
    assert current_calendar_week(dt.date(2026, 11, 11)) == "2026-KW46"
    assert default_reference_week(dt.date(2026, 11, 11), weeks_back=8) == "2026-KW38"
