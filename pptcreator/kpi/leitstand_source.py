"""KPI data for the IDM Control Center ("Leitstand", report/menu item 1200).

Source of truth is ReportDB, read-only:

* chart metadata from the Control Center configuration, per donut chart id
    T_Chart_Dimension            one numeric column per slice (sum aggregation)
    T_Chart_Aesthetic            links a slice (DimID) to its geometry (GeomID)
    T_Chart_GeometryOption       'background.color' = '(r,g,b)' per slice
    T_Chart_ChartOption          'legend.sorting' = slice order
    Translation.dbo.Translation  DE/EN label, keyed by the column name
* numbers from T_RESULT_Leitstand_Overview, aggregated like the frontend:
    WHERE AnalyseZeitpunkt = :date AND MOD = 'Alle' AND EK_ORG = :brand
    (grouped by COM for the commodity view)

The six donut charts of the Control Center (mapping ``chart_id``):
    12000  BKA nach Aktualisierung         12006   Rote BKAs
    12002  BKA nach Bearbeitungsstatus      120013  BKA nach Abgleichstatus
    12004  UVB Fehler nach Fehlercode       120017  Saisonalität von Kapazitäten

A ReportPeriod (ISO week) is resolved to the latest AnalyseZeitpunkt within that
week; if the week has no snapshot, the latest snapshot before the end of the week
is used and logged. Snapshots are not strictly weekly (monthly in older data).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import functools
import logging
import os
import re

import sqlalchemy as sa
from pycore.easy import database

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod, Rows

OVERVIEW_TABLE = os.getenv("LEITSTAND_TABLE", "ReportDB.dbo.T_RESULT_Leitstand_Overview")
CONFIG_DB = os.getenv("LEITSTAND_CONFIG_DB", "ReportDB")
TRANSLATION_TABLE = os.getenv("LEITSTAND_TRANSLATION_TABLE", "Translation.dbo.Translation")
CONFIG_TABLES = {
    "dimension": f"{CONFIG_DB}.dbo.T_Chart_Dimension",
    "aesthetic": f"{CONFIG_DB}.dbo.T_Chart_Aesthetic",
    "geometry_option": f"{CONFIG_DB}.dbo.T_Chart_GeometryOption",
    "chart_option": f"{CONFIG_DB}.dbo.T_Chart_ChartOption",
}
MOD_ALL = os.getenv("LEITSTAND_MOD_ALL", "Alle")
AVG_AGE_COLUMN = "UpdatedAvgAge"
"""Average BKA age in days per row; weighted by the row's BKA count for the 'Ø' text."""

AGE_COLUMNS = (
    "UpdatedPastYear",
    "UpdatedPast1to2Years",
    "UpdatedPast2To4Years",
    "UpdatedPast4To6Years",
    "UpdatedOver6Years",
)

_SAFE_COLUMN = re.compile(r"^[A-Za-z0-9_\u00C0-\u017F]+$")


@dataclasses.dataclass(frozen=True)
class Slice:
    column: str
    label: str
    color: str  # 'rgb(r, g, b)'


@dataclasses.dataclass(frozen=True)
class ChartMeta:
    chart_id: int
    slices: tuple[Slice, ...]

    @property
    def palette(self) -> dict[str, str]:
        return {s.label: s.color for s in self.slices}


class LeitstandKpiSource:
    """KpiSource for mapping rows with ``source = 'leitstand'`` (needs ``chart_id``)."""

    def __init__(self, engine=None, *, language: str = "DE", with_average: bool = True):
        self._engine = engine
        self.language = language.upper()
        self.with_average = with_average
        self._dates: list[dt.date] | None = None

    @property
    def engine(self):
        return self._engine if self._engine is not None else database.engine

    # -------------------------------------------------------------------------- #

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult:
        if definition.chart_id is None:
            raise ValueError(f"{definition.id}: leitstand source needs chart_id.")
        meta = self.chart_meta(int(definition.chart_id))

        # Palette: mapping row wins only if it covers all labels; otherwise frontend colours
        palette = meta.palette
        if definition.palette and set(meta.palette) <= set(definition.palette):
            palette = {label: definition.palette[label] for label in meta.palette}
        resolved = dataclasses.replace(definition, palette=palette)

        is_age_kpi = set(AGE_COLUMNS) <= {s.column for s in meta.slices}
        with_avg = self.with_average and is_age_kpi and definition.average_label is not None

        result = KpiResult(
            definition=resolved,
            brand=brand,
            current=self._snapshot(meta, brand, current, with_avg),
            reference=self._snapshot(meta, brand, reference, with_avg),
        )
        result.validate()
        return result

    # -------------------------------------------------------------------------- #
    # Periods
    # -------------------------------------------------------------------------- #

    def available_dates(self) -> list[dt.date]:
        if self._dates is None:
            sql = sa.text(f"SELECT DISTINCT AnalyseZeitpunkt FROM {OVERVIEW_TABLE} ORDER BY AnalyseZeitpunkt")
            with self.engine.connect() as con:
                self._dates = [_as_date(r[0]) for r in con.execute(sql) if r[0] is not None]
        return self._dates

    def resolve_date(self, period: ReportPeriod) -> dt.date:
        start, end = period_bounds(period)
        dates = self.available_dates()
        in_week = [d for d in dates if start <= d <= end]
        if in_week:
            return in_week[-1]
        before = [d for d in dates if d <= end]
        if not before:
            raise ValueError(f"No Control Center snapshot on or before {period} (earliest: {dates[0] if dates else '-'}).")
        logging.warning(f"No snapshot in {period}; using latest before: {before[-1]}")
        return before[-1]

    # -------------------------------------------------------------------------- #
    # Data
    # -------------------------------------------------------------------------- #

    def _snapshot(self, meta: ChartMeta, brand: str, period: ReportPeriod, with_avg: bool) -> KpiSnapshot:
        snapshot_date = self.resolve_date(period)
        columns = [s.column for s in meta.slices]
        sums = ", ".join(f"SUM(COALESCE({_q(c)}, 0)) AS {_q(c)}" for c in columns)
        avg_sql = ""
        if with_avg:
            weight = " + ".join(f"COALESCE({_q(c)}, 0)" for c in AGE_COLUMNS)
            avg_sql = (
                f", SUM(CAST({_q(AVG_AGE_COLUMN)} AS FLOAT) * ({weight})) / NULLIF(SUM({weight}), 0) AS avg_age_days"
            )
        where = "WHERE AnalyseZeitpunkt = :d AND MOD = :mod AND EK_ORG = :brand"
        params = {"d": snapshot_date, "mod": MOD_ALL, "brand": brand}

        total_sql = sa.text(f"SELECT {sums}{avg_sql} FROM {OVERVIEW_TABLE} {where}")
        com_sql = sa.text(
            f"SELECT COM, {sums}{avg_sql} FROM {OVERVIEW_TABLE} {where} GROUP BY COM ORDER BY COM"
        )
        with self.engine.connect() as con:
            total = con.execute(total_sql, params).mappings().first()
            by_com = list(con.execute(com_sql, params).mappings())

        total_rows = _rows(meta, total)
        if not any(r["value"] for r in total_rows):
            raise ValueError(f"chart {meta.chart_id}: no data for brand={brand!r} on {snapshot_date} ({period}).")

        commodity_rows: dict[str, Rows] = {}
        commodity_avg: dict[str, str] = {}
        for row in by_com:
            com = (row["COM"] or "").strip() or "ohne COM"
            rows = _rows(meta, row)
            if not any(r["value"] for r in rows):
                continue
            commodity_rows[com] = rows
            if with_avg and row.get("avg_age_days") is not None:
                commodity_avg[com] = format_age(row["avg_age_days"])

        logging.info(
            f"chart {meta.chart_id} {brand} {period} -> {snapshot_date}: "
            f"{sum(r['value'] for r in total_rows):.0f} total, {len(commodity_rows)} commodities"
        )
        return KpiSnapshot(
            period=ReportPeriod(label=_period_label(period, snapshot_date)),
            total_rows=total_rows,
            commodity_rows=commodity_rows,
            average_text=format_age(total["avg_age_days"]) if with_avg and total.get("avg_age_days") is not None else None,
            commodity_average_text=commodity_avg,
        )

    # -------------------------------------------------------------------------- #
    # Chart metadata
    # -------------------------------------------------------------------------- #

    def chart_meta(self, chart_id: int) -> ChartMeta:
        return _chart_meta_cached(self.engine, chart_id, self.language)


@functools.lru_cache(maxsize=64)
def _chart_meta_cached(engine, chart_id: int, language: str) -> ChartMeta:
    t = CONFIG_TABLES
    # "Option" is a reserved word in T-SQL; double quotes work in SQL Server (QUOTED_IDENTIFIER
    # is ON for ODBC connections) and in SQLite (tests).
    sql = sa.text(
        f"""
        SELECT d.DimID, d.ColumnName, d.DataType, d.Aggregation,
               MAX(g.Value) AS color, MAX(tr.Value) AS label
        FROM {t['dimension']} d
        JOIN {t['aesthetic']} a
             ON a.DimID = d.DimID AND a.ChartID = d.ChartID AND a.Aesthetic = 'value'
        LEFT JOIN {t['geometry_option']} g
             ON g.GeomID = a.GeomID AND g."Option" = 'background.color'
        LEFT JOIN {TRANSLATION_TABLE} tr
             ON tr.TranslationKey = d.ColumnName AND tr.LanguageCode = :lang
        WHERE d.ChartID = :chart_id
        GROUP BY d.DimID, d.ColumnName, d.DataType, d.Aggregation
        ORDER BY d.DimID
        """
    )
    order_sql = sa.text(
        f"""SELECT Value FROM {t['chart_option']} WHERE ChartID = :chart_id AND "Option" = 'legend.sorting'"""
    )
    with engine.connect() as con:
        rows = list(con.execute(sql, {"chart_id": chart_id, "lang": language}).mappings())
        order_row = con.execute(order_sql, {"chart_id": chart_id}).first()

    slices = []
    for row in rows:
        if (row["DataType"] or "").lower() != "numeric":
            continue  # e.g. the AnalyseZeitpunkt dimension
        column = row["ColumnName"]
        if not _SAFE_COLUMN.match(column or ""):
            raise ValueError(f"chart {chart_id}: unexpected column name {column!r}")
        slices.append(Slice(column=column, label=(row["label"] or column).strip(), color=parse_color(row["color"], column)))
    if not slices:
        raise ValueError(f"chart {chart_id}: no numeric dimensions found in T_Chart_Dimension.")

    if order_row and order_row[0]:
        order = [c.strip() for c in str(order_row[0]).split(",") if c.strip()]
        rank = {c: i for i, c in enumerate(order)}
        slices.sort(key=lambda s: rank.get(s.column, len(rank)))

    labels = [s.label for s in slices]
    if len(labels) != len(set(labels)):
        raise ValueError(f"chart {chart_id}: duplicate slice labels {labels}.")
    return ChartMeta(chart_id=chart_id, slices=tuple(slices))


# ------------------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------------------ #


def parse_color(value: str | None, column: str) -> str:
    """'(82,197,172)' -> 'rgb(82, 197, 172)'. Grey when missing."""
    if not value:
        logging.warning(f"No colour for {column}; using grey.")
        return "rgb(128, 128, 128)"
    numbers = re.findall(r"\d+", value)
    if len(numbers) < 3:
        raise ValueError(f"Unsupported colour {value!r} for {column}")
    r, g, b = (int(n) for n in numbers[:3])
    return f"rgb({r}, {g}, {b})"


def format_age(days) -> str:
    """Average age in days -> '2 Jahre, 9 Monate' (frontend headline style)."""
    months = int(round(float(days) / 30.4375))
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append("1 Jahr" if years == 1 else f"{years} Jahre")
    if rest or not years:
        parts.append("1 Monat" if rest == 1 else f"{rest} Monate")
    return ", ".join(parts)


def period_bounds(period: ReportPeriod, today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """ISO week bounds. 'KW37' without year -> the most recent KW37 not in the future."""
    match = re.fullmatch(r"(?:(\d{4})-)?KW(\d{2})", str(period))
    if not match:
        raise ValueError(f"Unsupported period {period}")
    week = int(match.group(2))
    if match.group(1):
        year = int(match.group(1))
    else:
        today = today or dt.date.today()
        year = today.isocalendar()[0]
        if dt.date.fromisocalendar(year, week, 1) > today:
            year -= 1
    start = dt.date.fromisocalendar(year, week, 1)
    return start, start + dt.timedelta(days=6)


def _period_label(period: ReportPeriod, snapshot: dt.date) -> str:
    """Headline label; the actual snapshot week when it differs from the requested one."""
    year, week, _ = snapshot.isocalendar()
    actual = f"KW{week:02d}"
    requested = str(period).split("-")[-1]
    if actual == requested:
        return str(period)
    return f"{actual}/{year}"


def _rows(meta: ChartMeta, record) -> Rows:
    if record is None:
        return [{"category": s.label, "value": 0.0} for s in meta.slices]
    return [{"category": s.label, "value": float(record[s.column] or 0)} for s in meta.slices]


def _q(column: str) -> str:
    if not _SAFE_COLUMN.match(column):
        raise ValueError(f"Unsafe column name {column!r}")
    return f"[{column}]"


def _as_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])
