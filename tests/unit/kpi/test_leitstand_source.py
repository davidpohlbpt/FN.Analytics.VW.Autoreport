"""LeitstandKpiSource against an SQLite replica of the ReportDB / Translation tables.

SQLite has no three-part names, so the module's table-name constants are pointed at
tables in attached SQLite databases; the SQL itself is unchanged.
"""

import datetime as dt

import pytest
import sqlalchemy as sa

from pptcreator.kpi import leitstand_source as ls
from pptcreator.kpi.base import KpiDefinition, ReportPeriod

CHART = 12000
COLUMNS = ["UpdatedPastYear", "UpdatedPast1to2Years", "UpdatedPast2To4Years", "UpdatedPast4To6Years", "UpdatedOver6Years", "NoUpdateData"]
LABELS = ["< 1 Jahr", "1-2 Jahre", "2 - 4 Jahre", "4 - 6 Jahre", "> 6 Jahre", "ohne Daten"]


@pytest.fixture
def engine(monkeypatch, tmp_path):
    eng = sa.create_engine("sqlite://")

    @sa.event.listens_for(eng, "connect")
    def _attach(dbapi_con, _):
        dbapi_con.execute(f"ATTACH DATABASE '{tmp_path / 'cfg.db'}' AS cfg")
        dbapi_con.execute(f"ATTACH DATABASE '{tmp_path / 'tr.db'}' AS tr")

    monkeypatch.setattr(ls, "OVERVIEW_TABLE", "cfg.overview")
    monkeypatch.setattr(ls, "TRANSLATION_TABLE", "tr.translation")
    monkeypatch.setattr(
        ls,
        "CONFIG_TABLES",
        {"dimension": "cfg.dim", "aesthetic": "cfg.aes", "geometry_option": "cfg.geomopt", "chart_option": "cfg.chartopt"},
    )
    ls._chart_meta_cached.cache_clear()

    with eng.begin() as con:
        con.exec_driver_sql(
            "CREATE TABLE cfg.overview (AnalyseZeitpunkt DATE, EK_ORG TEXT, MOD TEXT, COM TEXT, "
            + ", ".join(f"{c} INT" for c in COLUMNS)
            + ", UpdatedAvgAge REAL)"
        )
        rows = []
        for date, factor in (("2025-11-28", 1), ("2025-09-24", 2)):
            for com in ("BC", "BI"):
                rows.append((date, "Audi", "Alle", com, *(factor * v for v in (10, 5, 4, 3, 2, 1)), 400.0))
            rows.append((date, "Audi", "OT", "BC", *(99,) * 6, 1.0))  # other MOD, must be ignored
            rows.append((date, "SEAT", "Alle", "BC", *(1,) * 6, 100.0))
        con.exec_driver_sql(
            "INSERT INTO cfg.overview VALUES (" + ",".join("?" * (4 + len(COLUMNS) + 1)) + ")", rows
        )
        con.exec_driver_sql("CREATE TABLE cfg.dim (DimID INT, ChartID INT, ColumnName TEXT, DataType TEXT, Aggregation TEXT)")
        con.exec_driver_sql("CREATE TABLE cfg.aes (AestheticID INT, ChartID INT, Aesthetic TEXT, DimID INT, GeomID INT)")
        con.exec_driver_sql("CREATE TABLE cfg.geomopt (GeomOptionID INT, GeomID INT, Option TEXT, Value TEXT)")
        con.exec_driver_sql("CREATE TABLE cfg.chartopt (ChartOptionID INT, ChartID INT, Option TEXT, Value TEXT, Language TEXT)")
        con.exec_driver_sql("CREATE TABLE tr.translation (TranslationKey TEXT, LanguageCode TEXT, Value TEXT)")
        # Insert dims in a different order than the legend to test sorting
        for i, (col, label) in enumerate(reversed(list(zip(COLUMNS, LABELS)))):
            dim = 100 + i
            con.exec_driver_sql("INSERT INTO cfg.dim VALUES (?,?,?,?,?)", (dim, CHART, col, "numeric", "sum"))
            con.exec_driver_sql("INSERT INTO cfg.aes VALUES (?,?,?,?,?)", (dim, CHART, "value", dim, dim))
            con.exec_driver_sql("INSERT INTO cfg.aes VALUES (?,?,?,?,?)", (dim + 1000, CHART, "label", dim, dim))
            con.exec_driver_sql("INSERT INTO cfg.geomopt VALUES (?,?,?,?)", (dim, dim, "background.color", f"({i},{i},{i})"))
            con.exec_driver_sql("INSERT INTO tr.translation VALUES (?,?,?)", (col, "DE", label))
        con.exec_driver_sql("INSERT INTO cfg.dim VALUES (?,?,?,?,?)", (999, CHART, "AnalyseZeitpunkt", "date", None))
        con.exec_driver_sql("INSERT INTO cfg.chartopt VALUES (?,?,?,?,?)", (1, CHART, "legend.sorting", ",".join(COLUMNS), "DE"))
    return eng


DEFINITION = KpiDefinition(
    id="bka_aktualisierung", name="BKA nach Aktualisierung", title="t", subtitle="s",
    palette={}, average_label="Ø", source="leitstand", chart_id=CHART,
)


def test_chart_meta_from_config(engine):
    source = ls.LeitstandKpiSource(engine)
    meta = source.chart_meta(CHART)
    assert [s.column for s in meta.slices] == COLUMNS  # legend.sorting applied
    assert [s.label for s in meta.slices] == LABELS
    assert meta.slices[0].color == "rgb(5, 5, 5)"  # '(5,5,5)' normalised


def test_fetch_current_vs_reference(engine):
    source = ls.LeitstandKpiSource(engine)
    result = source.fetch(DEFINITION, "Audi", ReportPeriod.parse("2025-KW48"), ReportPeriod.parse("2025-KW39"))

    assert result.definition.palette and list(result.definition.palette) == LABELS
    assert result.current.total_rows == [{"category": l, "value": float(v)} for l, v in zip(LABELS, (20, 10, 8, 6, 4, 2))]
    assert result.reference.total_rows[0] == {"category": "< 1 Jahr", "value": 40.0}
    assert list(result.current.commodity_rows) == ["BC", "BI"]
    assert result.current.commodity_rows["BC"][0] == {"category": "< 1 Jahr", "value": 10.0}
    assert result.current.average_text == "1 Jahr, 1 Monat"  # 400 days
    assert result.current.commodity_average_text["BI"] == "1 Jahr, 1 Monat"
    assert str(result.current.period) == "2025-KW48"


def test_week_without_snapshot_uses_latest_before(engine):
    source = ls.LeitstandKpiSource(engine)
    result = source.fetch(DEFINITION, "Audi", ReportPeriod.parse("2025-KW45"), ReportPeriod.parse("2025-KW39"))
    assert str(result.current.period) == "KW39/2025"  # 2025-09-24 is the latest before KW45
    with pytest.raises(ValueError, match="No Control Center snapshot"):
        source.resolve_date(ReportPeriod.parse("2020-KW01"))


def test_unknown_brand_raises(engine):
    source = ls.LeitstandKpiSource(engine)
    with pytest.raises(ValueError, match="no data for brand='Skoda'"):
        source.fetch(DEFINITION, "Skoda", ReportPeriod.parse("2025-KW48"), ReportPeriod.parse("2025-KW39"))


def test_no_average_for_other_kpis(engine):
    source = ls.LeitstandKpiSource(engine)
    no_avg = KpiDefinition(**{**DEFINITION.__dict__, "average_label": None})
    result = source.fetch(no_avg, "Audi", ReportPeriod.parse("2025-KW48"), ReportPeriod.parse("2025-KW39"))
    assert result.current.average_text is None


def test_helpers():
    assert ls.parse_color("(82,197,172)", "x") == "rgb(82, 197, 172)"
    assert ls.parse_color(None, "x") == "rgb(128, 128, 128)"
    assert ls.format_age(1019.35) == "2 Jahre, 9 Monate"
    assert ls.format_age(10) == "0 Monate"
    assert ls.period_bounds(ReportPeriod.parse("2025-KW48")) == (dt.date(2025, 11, 24), dt.date(2025, 11, 30))
    # without year: the most recent such week not in the future
    assert ls.period_bounds(ReportPeriod.parse("KW50"), today=dt.date(2026, 1, 10))[0].year == 2025
    with pytest.raises(ValueError):
        ls._q("x; DROP TABLE y")
