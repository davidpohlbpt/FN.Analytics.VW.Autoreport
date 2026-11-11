"""Deterministic dummy data, used until the DQN KPI table is wired in.

Numbers are derived from a hash of (kpi, brand, period, commodity) so that every
combination gives a stable but different picture; this makes decks reviewable and
tests reproducible without any network access.
"""

import hashlib

from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod, Rows

DEFAULT_COMMODITIES: dict[str, list[str]] = {
    # The VW template example used these commodity codes on the detail slide
    "_default": ["BC", "BI", "BM", "BN", "BX", "CB", "ZB"],
    # More than one detail slide, to exercise pagination
    "Audi": ["BC", "BI", "BM", "BN", "BX", "CB", "ZB", "ZE", "ZF", "ZG"],
}


class StubKpiSource:

    def __init__(self, commodities: dict[str, list[str]] | None = None):
        self.commodities = commodities or DEFAULT_COMMODITIES

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult:
        result = KpiResult(
            definition=definition,
            brand=brand,
            current=self._snapshot(definition, brand, current),
            reference=self._snapshot(definition, brand, reference),
        )
        result.validate()
        return result

    def _commodities_for(self, brand: str) -> list[str]:
        return self.commodities.get(brand) or self.commodities["_default"]

    def _snapshot(self, definition: KpiDefinition, brand: str, period: ReportPeriod) -> KpiSnapshot:
        commodities = self._commodities_for(brand)
        commodity_rows = {
            com: _rows(definition, f"{brand}|{period}|{com}") for com in commodities
        }
        total_rows = _sum_rows(definition, commodity_rows.values())
        has_avg = definition.average_label is not None
        return KpiSnapshot(
            period=period,
            total_rows=total_rows,
            commodity_rows=commodity_rows,
            average_text=_avg_text(f"{definition.id}|{brand}|{period}") if has_avg else None,
            commodity_average_text=(
                {com: _avg_text(f"{definition.id}|{brand}|{period}|{com}") for com in commodities}
                if has_avg
                else {}
            ),
        )


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _rows(definition: KpiDefinition, key: str) -> Rows:
    seed = _seed(f"{definition.id}|{key}")
    rows = []
    for index, category in enumerate(definition.categories):
        value = 20 + (seed >> (index * 4)) % 180
        rows.append({"category": category, "value": float(value)})
    return rows


def _sum_rows(definition: KpiDefinition, parts) -> Rows:
    totals = {category: 0.0 for category in definition.categories}
    for rows in parts:
        for row in rows:
            totals[row["category"]] += row["value"]
    return [{"category": c, "value": v} for c, v in totals.items()]


def _avg_text(key: str) -> str:
    months = _seed(key) % 60
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} Jahr" if years == 1 else f"{years} Jahre")
    if rest or not years:
        parts.append(f"{rest} Monat" if rest == 1 else f"{rest} Monate")
    return ", ".join(parts)
