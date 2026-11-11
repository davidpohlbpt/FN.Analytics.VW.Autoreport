"""Turns KpiResults into the ``output_slides`` consumed by ``graph_create_ppt``.

Template contract (VW_Template_Overview.pptx):
  slide 1 (index 0): overview  -> ``Chart 1`` = reference period, ``Chart 2`` = current
  slide 2 (index 1): detail    -> ``Chart 3`` .. ``Chart 9`` = one commodity each

When a brand has more commodities than detail slots, the detail slide is repeated
and the title gets a ``(n/m)`` suffix. Template objects are discovered from the
presentation so that renaming/adding chart slots in the template does not require
code changes, as long as the overview slide keeps exactly two charts.
"""

from __future__ import annotations

import logging
import re

from pptx import Presentation

from pptcreator.kpi.base import KpiResult, KpiSnapshot, ReportPeriod, Rows
from pptcreator.models.enum import ChartObjects, ChartType

OVERVIEW_SLIDE = 0
DETAIL_SLIDE = 1


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def discover_chart_slots(prs: Presentation) -> dict[int, list[str]]:
    """Template slide index -> chart object names on it, in natural name order."""
    slots: dict[int, list[str]] = {}
    for slide_index, slide in enumerate(prs.slides):
        names = [
            shape.name.removesuffix(ChartObjects.CHART.value).rstrip()
            for shape in slide.shapes
            if shape.has_chart and shape.name.endswith(ChartObjects.CHART.value)
        ]
        slots[slide_index] = sorted(set(names), key=_natural_key)
    return slots


def validate_template_slots(slots: dict[int, list[str]]) -> None:
    if len(slots.get(OVERVIEW_SLIDE, [])) != 2:
        raise ValueError(
            f"Template slide {OVERVIEW_SLIDE + 1} must contain exactly two charts "
            f"(reference, current); found {slots.get(OVERVIEW_SLIDE)}."
        )
    if not slots.get(DETAIL_SLIDE):
        raise ValueError(f"Template slide {DETAIL_SLIDE + 1} must contain at least one chart.")


def build_output_slides(
    results: list[KpiResult],
    *,
    template_slots: dict[int, list[str]],
    charts_per_detail_slide: int | None = None,
    show_data_labels: bool | None = None,
) -> list[dict]:
    validate_template_slots(template_slots)
    overview_slots = template_slots[OVERVIEW_SLIDE]
    detail_slots = template_slots[DETAIL_SLIDE]
    per_slide = min(charts_per_detail_slide or len(detail_slots), len(detail_slots))
    if per_slide < 1:
        raise ValueError("charts_per_detail_slide must be at least 1.")

    output_slides: list[dict] = []
    for result in results:
        result.validate()
        output_slides.append(_overview_slide(result, overview_slots, show_data_labels))
        output_slides.extend(_detail_slides(result, detail_slots, per_slide, show_data_labels))

    logging.info(f"Built {len(output_slides)} output slides for {len(results)} KPI(s).")
    return output_slides


# ------------------------------------------------------------------------------ #


def _chart(result: KpiResult, rows: Rows, headline: str, filters: dict, show_data_labels) -> dict:
    chart = {
        "chart_type": ChartType.DOUGHNUT,
        "filters": filters,
        "fillColor": result.definition.palette,
        "rows": _ordered_rows(rows, result.definition.categories),
        "headline": headline,
    }
    if show_data_labels is not None:
        chart["has_data_labels"] = show_data_labels
    return chart


def _ordered_rows(rows: Rows, categories: list[str]) -> Rows:
    """Rows in palette order so that colours and legends line up across charts."""
    by_category = {}
    for row in rows:
        category, value = list(row.values())[:2]
        by_category[category] = by_category.get(category, 0.0) + float(value)
    return [{"category": c, "value": by_category[c]} for c in categories if c in by_category]


def _avg_line(result: KpiResult, text: str | None) -> str:
    label = result.definition.average_label
    if label is None or not text:
        return ""
    return f"\n{label} {text}"


def _overview_slide(result: KpiResult, slots: list[str], show_data_labels) -> dict:
    ref, cur = result.reference, result.current
    brand = result.brand
    charts = {
        slots[0]: _chart(
            result,
            ref.total_rows,
            f"{ref.period} - {brand}{_avg_line(result, ref.average_text)}",
            {"period": str(ref.period), "brand": brand, "role": "reference"},
            show_data_labels,
        ),
        slots[1]: _chart(
            result,
            cur.total_rows,
            f"{cur.period} - {brand}{_avg_line(result, cur.average_text)}",
            {"period": str(cur.period), "brand": brand, "role": "current"},
            show_data_labels,
        ),
    }
    return {
        "kpi": result.definition.id,
        "template_slide": OVERVIEW_SLIDE,
        "title": result.definition.title,
        "subtitle": result.definition.subtitle,
        "charts": charts,
    }


def _detail_slides(result: KpiResult, slots: list[str], per_slide: int, show_data_labels) -> list[dict]:
    cur: KpiSnapshot = result.current
    ref: KpiSnapshot = result.reference
    commodities = list(cur.commodity_rows)
    if not commodities:
        logging.warning(f"{result.definition.id}/{result.brand}: no commodities, detail slide skipped.")
        return []

    pages = [commodities[i : i + per_slide] for i in range(0, len(commodities), per_slide)]
    slides = []
    for page_number, page in enumerate(pages, start=1):
        charts = {}
        for slot, commodity in zip(slots, page):
            headline = _commodity_headline(result, commodity, cur, ref)
            charts[slot] = _chart(
                result,
                cur.commodity_rows[commodity],
                headline,
                {
                    "period": str(cur.period),
                    "reference_period": str(ref.period),
                    "brand": result.brand,
                    "commodity": commodity,
                },
                show_data_labels,
            )
        title = result.definition.title
        if len(pages) > 1:
            title = f"{title} ({page_number}/{len(pages)})"
        slides.append(
            {
                "kpi": result.definition.id,
                "template_slide": DETAIL_SLIDE,
                "title": title,
                "subtitle": result.definition.subtitle,
                "charts": charts,
            }
        )
    return slides


def _commodity_headline(result: KpiResult, commodity: str, cur: KpiSnapshot, ref: KpiSnapshot) -> str:
    label = result.definition.average_label
    cur_avg = cur.commodity_average_text.get(commodity)
    ref_avg = ref.commodity_average_text.get(commodity)
    if label is None or not cur_avg:
        return f"{commodity} - {cur.period}\n{ref.period}"
    first = f"{commodity} {label} {cur_avg}"
    second = f"{ref.period}: {label} {ref_avg}" if ref_avg else f"{ref.period}: -"
    return f"{first}\n{second}"


def describe_periods(current: ReportPeriod, reference: ReportPeriod) -> str:
    return f"{current} vs. {reference}"
