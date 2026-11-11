"""KPI data from the backend KPI table in ReportDB (``source = 'backend'``).

Each mapping row names a query in ``QUERIES`` via ``query_key``. A query returns the
category distribution in long format; the source then splits it into brand total and
per commodity. Queries receive the bound parameters ``:kpi_key``, ``:brand`` and
``:period`` and must return the columns

    commodity   NULL/'' for the brand total, otherwise the commodity code
    category    the category label (must match the mapping's palette)
    value       numeric
    avg_text    optional, formatted average (e.g. '2 Jahre, 5 Monate'); NULL if n/a

The ``default`` query targets a generic long-format table; replace its table and
column names once the real KPI table is known. Adding a KPI with a different layout
is a matter of adding one more query here and referencing it in the mapping row.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import sqlalchemy as sa
from pycore.easy import database

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod, Rows

KPI_TABLE = os.getenv("KPI_TABLE", "control.T_Autoreport_KpiValues")

QUERIES: dict[str, str] = {
    # Generic long-format table: one row per (kpi, brand, commodity, period, category)
    "default": f"""
        SELECT
            commodity,
            category,
            CAST([value] AS FLOAT) AS value,
            avg_text
        FROM {KPI_TABLE}
        WHERE kpi_key = :kpi_key
          AND brand = :brand
          AND period = :period
    """,
}

REQUIRED_COLUMNS = ("commodity", "category", "value")


class SqlKpiSource:

    def __init__(self, queries: dict[str, str] | None = None, engine=None):
        self.queries = queries or QUERIES
        self._engine = engine

    @property
    def engine(self):
        return self._engine if self._engine is not None else database.engine

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult:
        key = definition.query_key or "default"
        if key not in self.queries:
            raise ValueError(f"{definition.id}: unknown query_key {key!r}; known: {sorted(self.queries)}.")
        sql = sa.text(self.queries[key])

        result = KpiResult(
            definition=definition,
            brand=brand,
            current=self._snapshot(sql, definition, brand, current),
            reference=self._snapshot(sql, definition, brand, reference),
        )
        result.validate()
        return result

    # -------------------------------------------------------------------------- #

    def _snapshot(self, sql, definition: KpiDefinition, brand: str, period: ReportPeriod) -> KpiSnapshot:
        params = {"kpi_key": definition.id, "brand": brand, "period": str(period)}
        with self.engine.connect() as con:
            frame = pd.read_sql_query(sql, con, params=params)

        missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(f"{definition.id}: query returned no columns {missing}; got {list(frame.columns)}.")
        if frame.empty:
            raise ValueError(f"{definition.id}: no rows for brand={brand!r}, period={period}.")
        if "avg_text" not in frame.columns:
            frame["avg_text"] = None

        frame["commodity"] = frame["commodity"].where(frame["commodity"].notna(), "").astype(str).str.strip()
        total = frame[frame["commodity"] == ""]
        detail = frame[frame["commodity"] != ""]

        if total.empty:
            logging.info(f"{definition.id}/{period}: no explicit total rows, summing commodities.")
            total_rows = _sum_by_category(detail, definition)
            avg_total = None
        else:
            total_rows = _to_rows(total, definition)
            avg_total = _first_text(total["avg_text"])

        commodity_rows: dict[str, Rows] = {}
        commodity_avg: dict[str, str] = {}
        for commodity, part in detail.groupby("commodity", sort=True):
            commodity_rows[str(commodity)] = _to_rows(part, definition)
            avg = _first_text(part["avg_text"])
            if avg:
                commodity_avg[str(commodity)] = avg

        return KpiSnapshot(
            period=period,
            total_rows=total_rows,
            commodity_rows=commodity_rows,
            average_text=avg_total,
            commodity_average_text=commodity_avg,
        )


def _to_rows(frame: pd.DataFrame, definition: KpiDefinition) -> Rows:
    grouped = frame.groupby("category", sort=False)["value"].sum()
    ordered = [c for c in definition.categories if c in grouped.index]
    extra = [c for c in grouped.index if c not in definition.categories]
    if extra:
        raise ValueError(f"{definition.id}: categories {extra} are not in the palette {definition.categories}.")
    return [{"category": c, "value": float(grouped[c])} for c in ordered]


def _sum_by_category(frame: pd.DataFrame, definition: KpiDefinition) -> Rows:
    return _to_rows(frame, definition) if not frame.empty else []


def _first_text(series: pd.Series) -> str | None:
    for value in series:
        if value is not None and not (isinstance(value, float) and pd.isna(value)) and str(value).strip():
            return str(value).strip()
    return None
