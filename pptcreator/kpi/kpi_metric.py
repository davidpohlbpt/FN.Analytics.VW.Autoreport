"""The value shown under each donut, e.g. 'Ø 2 Jahre, 5 Monate', '45 %' or '120 / 30'.

One row per KPI in ``T_Control_Autoreport_KpiMetrics`` describes the value in structured
form (never as SQL): which columns of ``T_RESULT_Leitstand_Overview`` are summed for the
numerator and the denominator, how the result is formatted, its label and the
explanation shown on the overview slide (``{kpi_explanation}``).

A KPI without an (active, valid) row, or a stage without the table, keeps the previous
behaviour driven by ``T_Control_Autoreport_Mappings.average_label``.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from decimal import ROUND_HALF_UP, Decimal

import pandas as pd

from pptcreator.models.models import AutoreportKpiMetrics
from pptcreator.utils.read_data import read_data

METRIC_AVG_AGE = "avg_age"
METRIC_PERCENT = "percent"
METRIC_RATIO = "ratio"
METRIC_COUNT = "count"
METRIC_TYPES = (METRIC_AVG_AGE, METRIC_PERCENT, METRIC_RATIO, METRIC_COUNT)

# Same rule as leitstand_source._SAFE_COLUMN; kept here so the table can be validated on load
_SAFE_COLUMN = re.compile(r"^[A-Za-z0-9_\u00C0-\u017F]+$")


@dataclasses.dataclass(frozen=True)
class KpiMetric:
    kpi_key: str
    metric_type: str
    numerator_columns: tuple[str, ...] = ()
    """Summed per row; empty -> the donut total (sum of the chart's slices)."""

    numerator_not_null_column: str | None = None
    """Only rows where this column IS NOT NULL count towards the numerator."""

    denominator_columns: tuple[str, ...] = ()
    """Summed per row; empty -> the donut total."""

    label: str = ""
    """Prefix in front of the value, e.g. 'Ø'; may be empty."""

    explanation_text: str = ""

    showed_bkas: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "numerator_columns", tuple(self.numerator_columns))
        object.__setattr__(self, "denominator_columns", tuple(self.denominator_columns))
        if self.metric_type not in METRIC_TYPES:
            raise ValueError(
                f"{self.kpi_key}: unknown metric_type {self.metric_type!r}; expected {METRIC_TYPES}."
            )
        columns = [*self.numerator_columns, *self.denominator_columns]
        if self.numerator_not_null_column:
            columns.append(self.numerator_not_null_column)
        unsafe = [c for c in columns if not _SAFE_COLUMN.match(c)]
        if unsafe:
            raise ValueError(f"{self.kpi_key}: invalid column name(s) {unsafe}.")

    @property
    def empty_text(self) -> str | None:
        """Value text when there is no data / the denominator is 0.

        ``None`` for avg_age: the headline falls back to the previous behaviour.
        """
        return {
            METRIC_PERCENT: format_percent(0, 0),
            METRIC_RATIO: format_ratio(0, 0),
            METRIC_COUNT: format_count(0),
        }.get(self.metric_type)

    def format(self, numerator: float | None, denominator: float | None) -> str:
        """Format a ratio/percent/count value (avg_age is formatted by the source)."""
        if self.metric_type == METRIC_PERCENT:
            return format_percent(numerator, denominator)
        if self.metric_type == METRIC_RATIO:
            return format_ratio(numerator, denominator)
        if self.metric_type == METRIC_COUNT:
            return format_count(numerator)
        raise ValueError(f"{self.kpi_key}: {self.metric_type} values are formatted by the source.")

    def render(self, text: str) -> str:
        return f"{self.label} {text}".strip() if self.label else text


def format_percent(numerator: float | None, denominator: float | None) -> str:
    """Whole percent, half up: '45 %'. A denominator of 0 / no data gives '0 %'."""
    if not denominator:
        return "0 %"
    percent = Decimal(str(float(numerator or 0) * 100 / float(denominator)))
    return f"{int(percent.quantize(Decimal('1'), rounding=ROUND_HALF_UP))} %"


def format_ratio(numerator: float | None, denominator: float | None) -> str:
    """'120 / 30' (absolute numbers, not a percentage)."""
    return f"{format_count(numerator)} / {format_count(denominator)}"


def format_count(value: float | None) -> str:
    return f"{float(value or 0):,.0f}".replace(",", ".")


# ------------------------------------------------------------------------------ #
# Loading
# ------------------------------------------------------------------------------ #


def load_kpi_metrics() -> dict[str, KpiMetric]:
    """kpi_key -> metric of all active, valid rows. A missing table means "none"."""
    try:
        rows = read_data(AutoreportKpiMetrics, ["is_active"], [True])
    except Exception as exc:  # stage without 005_kpi_metrics.sql
        logging.warning(f"Could not read T_Control_Autoreport_KpiMetrics: {exc}")
        return {}
    if rows is None or rows.empty:
        return {}

    metrics: dict[str, KpiMetric] = {}
    for row in rows.to_dict("records"):
        key = _text(row.get("kpi_key"))
        if not key:
            continue
        try:
            metric = KpiMetric(
                kpi_key=key,
                metric_type=(_text(row.get("metric_type")) or "").lower(),
                numerator_columns=_columns(row.get("numerator_columns")),
                numerator_not_null_column=_text(row.get("numerator_not_null_column")),
                denominator_columns=_columns(row.get("denominator_columns")),
                label=_text(row.get("label")) or "",
                explanation_text=_text(row.get("explanation_text")) or "",
                showed_bkas=_text(row.get("showed_bkas")) or "",
            )
        except ValueError as exc:
            logging.warning(f"Ignoring KPI metric row {row.get('id')}: {exc}")
            continue
        if key in metrics:
            logging.warning(f"Duplicate active KPI metric rows for {key!r}; using the first one.")
            continue
        metrics[key] = metric
    logging.info(f"KPI metrics configured for {sorted(metrics)}")
    return metrics


def attach_metrics(kpis: list, metrics: dict[str, KpiMetric]) -> list:
    """Return the KpiDefinitions with their metric set (unchanged when not configured)."""
    return [
        dataclasses.replace(kpi, metric=metrics[kpi.id]) if kpi.id in metrics else kpi
        for kpi in kpis
    ]


def _columns(value) -> tuple[str, ...]:
    text = _text(value)
    if not text:
        return ()
    return tuple(part.strip() for part in text.split(",") if part.strip())


def _text(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None
