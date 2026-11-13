from unittest.mock import Mock

import pandas as pd
import pytest
import sqlalchemy as sa

from pptcreator.kpi.base import KpiDefinition, ReportPeriod
from pptcreator.kpi.frontend_source import FrontendFilterNames, FrontendKpiSource
from pptcreator.kpi.router import RoutingKpiSource
from pptcreator.kpi.sql_source import SqlKpiSource

PALETTE = {"a": "rgb(1, 2, 3)", "b": "rgb(4, 5, 6)"}
KW45, KW37 = ReportPeriod.parse("KW45"), ReportPeriod.parse("KW37")


# ------------------------------------------------------------------------------ #
# backend / SQL
# ------------------------------------------------------------------------------ #


@pytest.fixture
def kpi_engine():
    engine = sa.create_engine("sqlite:///:memory:")
    rows = []
    for period in ("KW45", "KW37"):
        rows.append(("t", "Audi", period, "", "a", 10.0, "1 Jahr"))
        rows.append(("t", "Audi", period, "", "b", 20.0, "1 Jahr"))
        for com in ("BC", "BI"):
            rows.append(("t", "Audi", period, com, "a", 1.0, "2 Monate"))
            rows.append(("t", "Audi", period, com, "b", 2.0, "2 Monate"))
    # Seat has no total rows -> summed from commodities
    rows.append(("t", "Seat", "KW45", "BC", "a", 5.0, None))
    rows.append(("t", "Seat", "KW45", "BM", "a", 7.0, None))
    rows.append(("t", "Seat", "KW37", "BC", "b", 1.0, None))
    frame = pd.DataFrame(rows, columns=["kpi_key", "brand", "period", "commodity", "category", "value", "avg_text"])
    frame.to_sql("kpi_values", engine, index=False)
    return engine


QUERY = {
    "default": """
        SELECT commodity, category, value, avg_text FROM kpi_values
        WHERE kpi_key = :kpi_key AND brand = :brand AND period = :period
    """
}


def test_sql_source_splits_total_and_commodities(kpi_engine):
    source = SqlKpiSource(queries=QUERY, engine=kpi_engine)
    definition = KpiDefinition(id="t", name="t", title="t", subtitle="", palette=PALETTE, source="backend", query_key="default")

    result = source.fetch(definition, "Audi", KW45, KW37)

    assert result.current.total_rows == [{"category": "a", "value": 10.0}, {"category": "b", "value": 20.0}]
    assert list(result.current.commodity_rows) == ["BC", "BI"]
    assert result.current.commodity_rows["BC"] == [{"category": "a", "value": 1.0}, {"category": "b", "value": 2.0}]
    assert result.current.average_text == "1 Jahr"
    assert result.current.commodity_average_text == {"BC": "2 Monate", "BI": "2 Monate"}


def test_sql_source_sums_when_no_total_rows(kpi_engine):
    source = SqlKpiSource(queries=QUERY, engine=kpi_engine)
    definition = KpiDefinition(id="t", name="t", title="t", subtitle="", palette=PALETTE, source="backend", query_key="default")

    result = source.fetch(definition, "Seat", KW45, KW37)

    assert result.current.total_rows == [{"category": "a", "value": 12.0}]
    assert result.current.average_text is None
    assert result.reference.total_rows == [{"category": "b", "value": 1.0}]


def test_sql_source_errors(kpi_engine):
    source = SqlKpiSource(queries=QUERY, engine=kpi_engine)
    definition = KpiDefinition(id="t", name="t", title="t", subtitle="", palette=PALETTE, source="backend", query_key="nope")
    with pytest.raises(ValueError, match="unknown query_key"):
        source.fetch(definition, "Audi", KW45, KW37)

    definition = KpiDefinition(id="t", name="t", title="t", subtitle="", palette=PALETTE, source="backend", query_key="default")
    with pytest.raises(ValueError, match="no rows"):
        source.fetch(definition, "Skoda", KW45, KW37)

    definition = KpiDefinition(id="t", name="t", title="t", subtitle="", palette={"a": "rgb(1,1,1)"}, source="backend", query_key="default")
    with pytest.raises(ValueError, match="not in the palette"):
        source.fetch(definition, "Audi", KW45, KW37)


# ------------------------------------------------------------------------------ #
# frontend / DQN API
# ------------------------------------------------------------------------------ #


def _fake_send_request(session, url, headers, method="GET", payload=None):
    if "/GenericReport/7/related" in url:
        return [{"TileID": 70, "ReportDataSourceID": 900, "TitleTK": "TK"}]
    if "/GenericReport/mask" in url:
        return {"reportFilters": [
            {"filterField": "brand", "reportLinkFilterID": 1},
            {"filterField": "commodity", "reportLinkFilterID": 2},
            {"filterField": "calendar_week", "reportLinkFilterID": 3},
        ]}
    if "/ReportMetadata/filter" in url:
        return ["BC", "BI", ""]
    if "/Chart/700/related" in url:
        return [{"AestheticID": 5, "Aesthetic": "fillColor"}]
    if "/ChartAesthetic/5/related" in url:
        return [{"Option": "a", "Value": "rgb(9, 9, 9)"}, {"Option": "b", "Value": "rgb(8, 8, 8)"}]
    if "/ReportContent/chart/" in url:
        mask = {m["id"]: m["values"][0] for m in payload["maskFilters"]}
        scale = 10 if 2 not in mask else 1
        return {"result": [{"geometryData": [{"cat": "b", "cnt": 2 * scale}, {"cat": "a", "cnt": 1 * scale}]}]}
    raise AssertionError(f"unexpected url {url}")


def test_frontend_source(monkeypatch):
    monkeypatch.setattr("pptcreator.kpi.frontend_source.send_request", _fake_send_request)
    source = FrontendKpiSource(session=Mock(), base_url="dqn.test", filter_names=FrontendFilterNames("brand", "commodity", "calendar_week"))
    definition = KpiDefinition(
        id="fe", name="fe", title="fe", subtitle="", palette={}, source="frontend",
        menu_item_id=7, report_id=7, tile_id=70, chart_id=700,
    )

    result = source.fetch(definition, "Audi", KW45, KW37)

    assert result.definition.palette == {"a": "rgb(9, 9, 9)", "b": "rgb(8, 8, 8)"}  # from the frontend
    assert result.current.total_rows == [{"category": "a", "value": 10.0}, {"category": "b", "value": 20.0}]
    assert list(result.current.commodity_rows) == ["BC", "BI"]  # empty filter value dropped
    assert result.current.commodity_rows["BC"] == [{"category": "a", "value": 1.0}, {"category": "b", "value": 2.0}]


def test_frontend_source_missing_filter(monkeypatch):
    monkeypatch.setattr("pptcreator.kpi.frontend_source.send_request", _fake_send_request)
    source = FrontendKpiSource(session=Mock(), base_url="dqn.test", filter_names=FrontendFilterNames("marke", "commodity", "calendar_week"))
    definition = KpiDefinition(id="fe", name="fe", title="fe", subtitle="", palette={}, source="frontend", menu_item_id=7, report_id=7, tile_id=70, chart_id=700)
    with pytest.raises(ValueError, match="no filters \\['marke'\\]"):
        source.fetch(definition, "Audi", KW45, KW37)


# ------------------------------------------------------------------------------ #
# router
# ------------------------------------------------------------------------------ #


def test_router_dispatches_by_definition_source():
    stub, backend = Mock(), Mock()
    router = RoutingKpiSource({"stub": stub, "backend": backend})
    d_stub = KpiDefinition(id="s", name="s", title="s", subtitle="", palette=PALETTE, source="stub")
    d_be = KpiDefinition(id="b", name="b", title="b", subtitle="", palette=PALETTE, source="backend")

    router.fetch(d_stub, "Audi", KW45, KW37)
    router.fetch(d_be, "Audi", KW45, KW37)

    stub.fetch.assert_called_once()
    backend.fetch.assert_called_once()
    with pytest.raises(ValueError, match="Unknown KPI source"):
        router.source_for("nope")
