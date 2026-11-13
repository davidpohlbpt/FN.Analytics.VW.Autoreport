import json

import pandas as pd
import pytest

from pptcreator.config import settings
from pptcreator.creator.get_config.get_autoreport_config import (
    StorageLocation,
    get_template_config,
    group_recipients,
    period_of,
    read_recipients,
    reference_period_of,
)
from pptcreator.kpi.base import ReportPeriod
from pptcreator.models.models import AutoreportMappings, AutoreportTemplates
from tests.unit.autoreport_fixtures import TEMPLATE_ID, seed_control_tables  # noqa: F401


def test_storage_location_parsing():
    s3 = StorageLocation.parse("s3://bucket/templates/x.pptx", default_container="c")
    assert s3.is_s3 and s3.bucket == "bucket" and s3.key == "templates/x.pptx" and s3.file_name == "x.pptx"

    local = StorageLocation.parse("ppt_creator\\VW.pptx", default_container="c")
    assert not local.is_s3 and local.container == "ppt_creator" and local.key == "VW.pptx"

    bare = StorageLocation.parse("VW.pptx", default_container="c")
    assert bare.container == "c" and bare.key == "VW.pptx"

    with pytest.raises(ValueError):
        StorageLocation.parse("s3://bucket", default_container="c")


def test_template_config_from_tables(seed_control_tables):  # noqa: F811
    seed_control_tables("s3://bucket/templates/VW.pptx", target_location="s3://bucket/reports")

    config = get_template_config(TEMPLATE_ID)

    assert config.id == TEMPLATE_ID
    assert config.template.is_s3 and config.template.key == "templates/VW.pptx"
    assert config.target.is_s3 and config.target.key == "reports"
    assert [k.id for k in config.kpis] == ["bka_aktualisierung", "bka_bearbeitungsstatus", "uvb_fehlercode", "rote_bka", "bka_abgleichstatus", "kapazitaet_saisonalitaet"]
    assert config.kpis[0].palette["> 6 Jahre"] == "rgb(247, 48, 33)"
    assert config.kpis[0].average_label == "Ø"
    assert config.kpis[2].average_label is None
    assert config.kpis[0].source == "stub"
    assert config.render_file_name("Audi", ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37")) == "VW_KPI_Report_Audi_KW45_vs_KW37"
    assert config.render_subject("Audi", ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37")) == "VW KPI Report Audi: KW45 vs. KW37"


def test_template_config_uses_only_active_template(seed_control_tables):  # noqa: F811
    seed_control_tables("VW.pptx")
    assert get_template_config(None).id == TEMPLATE_ID


def test_template_config_errors(seed_control_tables, data_repo):  # noqa: F811
    seed_control_tables("VW.pptx")
    with pytest.raises(ValueError, match="not found or inactive"):
        get_template_config(99)

    # second active template -> ambiguous without id
    data_repo.write_table(
        model=AutoreportTemplates,
        df=pd.DataFrame([{"id": 2, "name": "x", "template_link": "a.pptx", "language": "DE", "target_file_name": "f", "is_active": True}]),
    )
    with pytest.raises(ValueError, match="active templates"):
        get_template_config(None)


def test_mapping_validation(seed_control_tables, data_repo):  # noqa: F811
    seed_control_tables("VW.pptx")
    data_repo.write_table(
        model=AutoreportMappings,
        df=pd.DataFrame(
            [
                {"id": 50, "template_id": TEMPLATE_ID, "kpi_key": "fe", "kpi_order": 9, "kpi_name": "fe", "slide_title": "fe", "source": "frontend", "is_active": True},
            ]
        ),
    )
    with pytest.raises(ValueError, match="frontend source needs"):
        get_template_config(TEMPLATE_ID)


def test_backend_mapping_needs_query_key(seed_control_tables, data_repo):  # noqa: F811
    seed_control_tables("VW.pptx")
    data_repo.write_table(
        model=AutoreportMappings,
        df=pd.DataFrame(
            [
                {"id": 51, "template_id": TEMPLATE_ID, "kpi_key": "be", "kpi_order": 9, "kpi_name": "be", "slide_title": "be", "source": "backend", "palette_json": json.dumps({"a": "rgb(1,1,1)"}), "is_active": True},
            ]
        ),
    )
    with pytest.raises(ValueError, match="needs query_key"):
        get_template_config(TEMPLATE_ID)


def test_source_override(seed_control_tables, monkeypatch):  # noqa: F811
    seed_control_tables("VW.pptx")
    monkeypatch.setattr(settings, "kpi_source_override", "leitstand")
    config = get_template_config(TEMPLATE_ID)
    assert {k.source for k in config.kpis} == {"leitstand"}
    assert [k.chart_id for k in config.kpis] == [12000, 12002, 12004, 12006, 120013, 120017]

    # backend needs a query_key, which the seeded rows do not have
    monkeypatch.setattr(settings, "kpi_source_override", "backend")
    with pytest.raises(ValueError, match="needs query_key"):
        get_template_config(TEMPLATE_ID)


def test_recipient_grouping(seed_control_tables):  # noqa: F811
    seed_control_tables("VW.pptx")

    recipients = read_recipients(TEMPLATE_ID)
    assert 7 not in set(recipients["id"])  # inactive brand dropped
    assert 5 not in set(recipients["id"]) or not recipients[recipients["id"] == 5].empty

    groups = group_recipients(recipients, TEMPLATE_ID)
    # one deck per row: two Audi rows with identical dates stay two decks
    assert [(g.brand, g.primary_date, g.reference_date, g.emails, g.recipient_ids) for g in groups] == [
        ("Audi", "2025-11-28", "2025-11-18", ["a@x.de"], [1]),
        ("Audi", "2025-11-28", "2025-11-18", ["b@x.de"], [2]),
        ("Seat", "2025-11-11", "2025-09-24", ["c@x.de"], [3]),
        ("Seat", "2025-10-28", "2025-08-29", ["d@x.de"], [4]),
        ("Audi", "2025-11-18", "2025-11-11", ["A@x.de"], [6]),
    ]

    adhoc = group_recipients(read_recipients(TEMPLATE_ID, only_send_now=True), TEMPLATE_ID)
    assert [(g.brand, g.emails, g.recipient_ids) for g in adhoc] == [
        ("Audi", ["b@x.de"], [2]),
        ("Seat", ["d@x.de"], [4]),
    ]


def test_recipient_rows_are_not_merged():
    """Two identical rows stay two decks; each keeps its own recipient id."""
    rows = pd.DataFrame(
        [
            {"id": 1, "email": "a@x.de", "brand": "Audi", "primary_date": "2025-11-28", "reference_date": "2025-11-18"},
            {"id": 2, "email": "A@X.de", "brand": "Audi", "primary_date": "2025-11-28", "reference_date": "2025-11-18"},
        ]
    )
    assert [(g.recipient_ids, g.emails) for g in group_recipients(rows, TEMPLATE_ID)] == [([1], ["a@x.de"]), ([2], ["A@X.de"])]


def test_recipient_rows_with_bad_dates_are_skipped(caplog):
    rows = pd.DataFrame(
        [
            {"id": 1, "email": "a@x.de", "brand": "Audi", "primary_date": None, "reference_date": "2025-11-18"},
            {"id": 2, "email": "b@x.de", "brand": "Audi", "primary_date": "uuid", "reference_date": "2025-11-18"},
            {"id": 3, "email": "c@x.de", "brand": "Audi", "primary_date": "2025-11-18", "reference_date": "2025-11-18"},
            {"id": 4, "email": "d@x.de", "brand": "Audi", "primary_date": "2025-11-28", "reference_date": "2025-11-18"},
        ]
    )
    groups = group_recipients(rows, TEMPLATE_ID)
    assert [g.recipient_ids for g in groups] == [[4]]  # missing, unparsable and identical dates skipped
    assert "primary_date is mandatory" in caplog.text
    assert "identical" in caplog.text


def test_period_of_passes_the_frontend_string_through():
    # no validation against the available snapshots: the KPI source reports a missing one
    assert str(period_of({"primary_date": "2025-11-28"}, "primary_date")) == "2025-11-28"
    assert str(period_of({"reference_date": "2026-KW37"}, "reference_date")) == "2026-KW37"
    assert reference_period_of({"reference_date": "2025-10-28"}) == ReportPeriod.parse("2025-10-28")

    with pytest.raises(ValueError, match="mandatory"):
        period_of({"primary_date": "  "}, "primary_date")
    with pytest.raises(ValueError, match="Unsupported period"):
        period_of({"primary_date": "last week"}, "primary_date")
