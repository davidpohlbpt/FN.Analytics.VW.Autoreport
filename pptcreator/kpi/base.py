"""Data contracts for the KPI deck.

A ``KpiSource`` returns, for one KPI, one brand and two points in time, the category
distribution of the brand total and of each commodity. The renderer only needs
``[{"category": ..., "value": ...}]`` rows (first key category, second value, see
``create_charts.py``), so this is the shape kept here.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
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

    source: str = "stub"
    """``frontend`` (DQN chart API), ``backend`` (SQL) or ``stub``."""

    menu_item_id: int | None = None
    report_id: int | None = None
    tile_id: int | None = None
    chart_id: int | None = None
    """DQN identifiers, used by the frontend source."""

    query_key: str | None = None
    """Name of the query in ``sql_source.QUERIES``, used by the backend source."""

    order: int = 0

    @property
    def categories(self) -> list[str]:
        return list(self.palette)


@dataclasses.dataclass(frozen=True)
class ReportPeriod:
    """A calendar week (``KW37``, ``2026-KW37``) or an exact snapshot date (``2025-11-18``).

    Dates address one AnalyseZeitpunkt directly; weeks are resolved by the source.
    """

    label: str

    @classmethod
    def parse(cls, value: str | ReportPeriod | dt.date) -> ReportPeriod:
        if isinstance(value, ReportPeriod):
            return value
        if isinstance(value, dt.date):
            return cls(label=value.isoformat()[:10])
        text = str(value).strip()
        if not text:
            raise ValueError("Report period must not be empty.")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            try:
                dt.date.fromisoformat(text)
            except ValueError as exc:
                raise ValueError(f"Invalid date {value!r}.") from exc
            return cls(label=text)
        if not re.fullmatch(r"(\d{4}-)?KW\d{1,2}", text, flags=re.IGNORECASE):
            raise ValueError(
                f"Unsupported period {value!r}; expected e.g. 'KW37', '2026-KW37' or '2025-11-18'."
            )
        year, _, week = text.upper().rpartition("KW")
        return cls(label=f"{year}KW{int(week):02d}")

    @property
    def date(self) -> dt.date | None:
        """The exact date for date periods, else None."""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.label):
            return dt.date.fromisoformat(self.label)
        return None

    @property
    def display(self) -> str:
        """Short label for headlines: 'KW47/2025' for dates, the label for weeks."""
        if self.date is not None:
            year, week, _ = self.date.isocalendar()
            return f"KW{week:02d}/{year}"
        return self.label

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
