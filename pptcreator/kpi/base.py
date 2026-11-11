"""Data contracts for the KPI deck.

A ``KpiSource`` returns, for one KPI, one brand and two points in time, the category
distribution of the brand total and of each commodity. The renderer only needs
``[{"category": ..., "value": ...}]`` rows (first key category, second value, see
``create_charts.py``), so this is the shape kept here.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Protocol

Rows = list[dict]


@dataclasses.dataclass(frozen=True)
class KpiDefinition:
    """Static description of one KPI; the dynamic data comes from a KpiSource."""

    id: str
    """Stable identifier, e.g. ``kpi1``; also used as filter value in the KPI table."""

    name: str
    """Short name shown in chart headlines, e.g. ``BKA Alter``."""

    title: str
    """Slide title."""

    subtitle: str
    """Slide subtitle (question the KPI answers)."""

    palette: dict[str, str]
    """Category -> ``rgb(r, g, b)``. Defines category order in legends and charts."""

    average_label: str | None = "Ø"
    """Prefix for the average text in headlines; ``None`` if the KPI has no average."""

    @property
    def categories(self) -> list[str]:
        return list(self.palette)


@dataclasses.dataclass(frozen=True)
class ReportPeriod:
    """A calendar week identifier such as ``KW37`` (optionally with year, ``2026-KW37``)."""

    label: str

    @classmethod
    def parse(cls, value: str | ReportPeriod) -> ReportPeriod:
        if isinstance(value, ReportPeriod):
            return value
        text = str(value).strip()
        if not text:
            raise ValueError("Report period must not be empty.")
        if not re.fullmatch(r"(\d{4}-)?KW\d{1,2}", text, flags=re.IGNORECASE):
            raise ValueError(
                f"Unsupported period {value!r}; expected e.g. 'KW37' or '2026-KW37'."
            )
        year, _, week = text.upper().rpartition("KW")
        return cls(label=f"{year}KW{int(week):02d}")

    def __str__(self) -> str:
        return self.label


@dataclasses.dataclass
class KpiSnapshot:
    """The category distribution of one KPI for one brand at one period."""

    period: ReportPeriod
    total_rows: Rows
    commodity_rows: dict[str, Rows]
    """Commodity -> rows. Insertion order defines the chart order on the detail slides."""

    average_text: str | None = None
    """Already formatted, e.g. ``2 Jahre, 5 Monate``; None if not applicable."""

    commodity_average_text: dict[str, str] = dataclasses.field(default_factory=dict)

    def validate(self, definition: KpiDefinition) -> None:
        _validate_rows(self.total_rows, definition, f"{definition.id}/{self.period}/total")
        for commodity, rows in self.commodity_rows.items():
            _validate_rows(rows, definition, f"{definition.id}/{self.period}/{commodity}")


@dataclasses.dataclass
class KpiResult:
    definition: KpiDefinition
    brand: str
    current: KpiSnapshot
    reference: KpiSnapshot

    def validate(self) -> None:
        self.current.validate(self.definition)
        self.reference.validate(self.definition)


class KpiSource(Protocol):
    """Pluggable data access; ``StubKpiSource`` now, ``SqlKpiSource`` once the table is known."""

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult: ...


def _validate_rows(rows: Rows, definition: KpiDefinition, context: str) -> None:
    if not rows:
        raise ValueError(f"{context}: no data rows.")
    for row in rows:
        if not isinstance(row, dict) or len(row) < 2:
            raise ValueError(f"{context}: row {row!r} must have a category and a value.")
        category, value = list(row.values())[:2]
        if category not in definition.palette:
            raise ValueError(
                f"{context}: category {category!r} is not in the palette of {definition.id} "
                f"({definition.categories})."
            )
        if value is None or not isinstance(value, (int, float)) or value < 0:
            raise ValueError(f"{context}: value {value!r} for {category!r} is not a non-negative number.")
