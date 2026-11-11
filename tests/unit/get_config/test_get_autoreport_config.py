import json

import pandas as pd
import pytest

from pptcreator.config import settings
from pptcreator.creator.get_config.get_autoreport_config import (
    StorageLocation,
    get_template_config,
    group_recipients,
    read_recipients,
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
    assert [k.id for k in config.kpis] == ["bka_age", "kpi2", "kpi3", "kpi4", "kpi5", "kpi6"]
    assert config.kpis[0].palette["> 6 Jahre"] == "rgb(255, 0, 0)"
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
    monkeypatch.setattr(settings, "kpi_source_override", "backend")
    config = get_template_config(TEMPLATE_ID)
    assert {k.source for k in config.kpis} == {"backend"}


def test_recipient_grouping(seed_control_tables):  # noqa: F811
    seed_control_tables("VW.pptx")

    groups = group_recipients(read_recipients(TEMPLATE_ID), TEMPLATE_ID)
    by_key = {(g.brand, str(g.reference_period) if g.reference_period else None): g for g in groups}

    assert set(by_key) == {("Audi", "KW37"), ("Seat", None)}
    assert by_key[("Audi", "KW37")].emails == ["a@x.de", "b@x.de"]  # A@x.de deduplicated
    assert by_key[("Audi", "KW37")].recipient_ids == [1, 2, 6]
    assert by_key[("Seat", None)].emails == ["c@x.de"]

    adhoc = group_recipients(read_recipients(TEMPLATE_ID, only_send_now=True), TEMPLATE_ID)
    assert [(g.brand, g.emails, g.recipient_ids) for g in adhoc] == [("Audi", ["b@x.de"], [2])]
