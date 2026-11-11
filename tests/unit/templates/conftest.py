"""Render a report template through the real creation pipeline.

Builds on tests/conftest.py (storage, cont, easy_test) so a template can be validated
and previewed without database or Config Center access.
"""

from pathlib import Path

import pytest
from pptx import Presentation

from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.models.enum import ChartObjects, ChartType, Languages, SlideObjects

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "test_data"
RESULT_DIR = Path(__file__).resolve().parents[2] / "result"


def discover_objects(prs) -> dict[str, set[str]]:
    """Mirrors the suffix matching in get_template_config to find template_object_names."""
    found: dict[str, set[str]] = {}
    for slide in prs.slides:
        for shape in slide.shapes:
            for role in ChartObjects:
                if shape.name.endswith(role.value):
                    name = shape.name.removesuffix(role.value).rstrip()
                    found.setdefault(name, set()).add(role.value)
                    break
    return found


def _dummy_data(palette: dict, filter_values: list[str], offset: int) -> dict:
    return {
        value: [
            # First key is the category, second is the value -- see create_charts.py
            {"category": category, "value": float(10 + 5 * i + f + offset)}
            for i, category in enumerate(palette)
        ]
        for f, value in enumerate(filter_values)
    }


def _inspect(prs, template_name: str) -> dict[str, set[str]]:
    print(f"\n--- {template_name} | {len(prs.slides)} slide(s) ---")
    for slide_number, slide in enumerate(prs.slides, start=1):
        print(f"Shape names on slide {slide_number}:")
        for shape in slide.shapes:
            marker = ""
            if shape.has_chart:
                marker = f"  [chart, legend={shape.chart.has_legend}]"
            elif shape.has_text_frame:
                para = shape.text_frame.paragraphs[0]
                run = para.runs[0] if para.runs else None
                size = run.font.size.pt if run is not None and run.font.size else None
                marker = f"  [text, size={size}]"
            print(f"  - {shape.name!r}{marker}")

    discovered = discover_objects(prs)
    print(f"Detected template objects: {sorted(discovered)}")
    return discovered


def _validate_template(discovered: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Returns (blocking errors, non-blocking warnings)."""
    errors, warnings = [], []

    if not discovered:
        errors.append(
            "No shapes ending in "
            + ", ".join(f"'{role.value}'" for role in ChartObjects)
            + ". Rename them via Home > Select > Selection Pane -- the keyword must "
            "be at the END of the name."
        )

    for name, roles in sorted(discovered.items()):
        if ChartObjects.CHART.value not in roles:
            warnings.append(
                f"{name!r} has {sorted(roles)} but no chart, so it is skipped. Add a "
                f"shape named '{name} {ChartObjects.CHART.value}', or rename these "
                "shapes to match the object they belong to."
            )

    if discovered and all(
        ChartObjects.CHART.value not in roles for roles in discovered.values()
    ):
        errors.append("No template object has a Chart shape, nothing to render.")

    return errors, warnings


@pytest.fixture
def render_template(storage, cont):

    def _render(
        template_name: str,
        *,
        slide_title: str,
        filter_values: list[str],
        palette: dict[str, str],
        slide_subtitle: str | None = None,
        chart_titles: dict[str, str] | None = None,
        chart_data: dict[str, dict[str, list[dict]]] | None = None,
        output_name: str | None = None,
        language: Languages = Languages.DE,
        show_data_labels: bool | None = None,
    ) -> tuple[Path, dict]:

        template_path = TEMPLATE_DIR / template_name
        if not template_path.is_file():
            pytest.fail(f"Template not found: {template_path}")

        storage.write_blob(
            container_name=cont,
            blob_name=template_name,
            blob_data=template_path.read_bytes(),
        )

        prs = Presentation(template_path)
        discovered = _inspect(prs, template_name)

        errors, warnings = _validate_template(discovered)
        for warning in warnings:
            print(f"WARNING: {warning}")
        if errors:
            pytest.fail(
                "Template cannot be rendered:\n"
                + "\n".join(f"  {i + 1}. {msg}" for i, msg in enumerate(errors)),
                pytrace=False,
            )

        renderable = [
            name
            for name, roles in discovered.items()
            if ChartObjects.CHART.value in roles
        ]

        config_dict = {
            "charts": {name: {} for name in renderable},
            "file": template_name,
            "file_container": cont,
            "headline_substring": slide_title,
            "subtitle_substring": slide_subtitle,
            "target_file_name": output_name or f"{template_path.stem}_preview",
            "target_blob_container": cont,
            "filter": filter_values,
            "language": language,
        }

        config_dict = get_template_config(config_dict)

        chart_titles = chart_titles or {}
        chart_data = chart_data or {}

        for offset, (name, cfg) in enumerate(config_dict["charts"].items()):
            data = chart_data.get(name) or _dummy_data(palette, filter_values, offset)
            for value in filter_values:
                categories = {next(iter(row.values())) for row in data[value]}
                missing = categories - set(palette)
                assert (
                    not missing
                ), f"{name!r}/{value}: categories {sorted(missing)} are not in the palette."

            cfg["chart_type"] = ChartType.DOUGHNUT
            cfg[ChartObjects.CHART.value]["fillColor"] = palette
            cfg[ChartObjects.CHART.value]["data"] = data
            if show_data_labels is not None:
                cfg[ChartObjects.CHART.value]["has_data_labels"] = show_data_labels

            headline = cfg.get(ChartObjects.HEADLINE.value)
            if headline is not None:
                headline["translation"] = chart_titles.get(name, name)

        graph_create_ppt(config_dict)

        blob = storage.read_blob(
            container_name=cont,
            blob_name=f"{config_dict['target_file_name']}.pptx",
            decode=False,
        )

        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        result_file = RESULT_DIR / f"{config_dict['target_file_name']}.pptx"
        result_file.write_bytes(blob)
        print(f"Wrote {result_file}")

        return result_file, config_dict

    return _render


def _template_rows(prs) -> dict[str, list[dict]]:
    """Category/value rows of every chart in the template, keyed by object name."""
    rows = {}
    for slide in prs.slides:
        for shape in slide.shapes:
            if not (shape.has_chart and shape.name.endswith(ChartObjects.CHART.value)):
                continue
            name = shape.name.removesuffix(ChartObjects.CHART.value).rstrip()
            plot = shape.chart.plots[0]
            rows[name] = [
                {"category": category, "value": float(value)}
                for category, value in zip(plot.categories, plot.series[0].values)
            ]
    return rows


def _object_slides(prs) -> dict[str, int]:
    """0-based template slide of every object that has a Chart shape."""
    return {
        shape.name.removesuffix(ChartObjects.CHART.value).rstrip(): slide_index
        for slide_index, slide in enumerate(prs.slides)
        for shape in slide.shapes
        if shape.has_chart and shape.name.endswith(ChartObjects.CHART.value)
    }


def _plural_headline_warnings(prs) -> list[str]:
    return [
        f"Slide {slide_number}: {shape.name!r} ends in 'Headlines' and is ignored. "
        "Rename it to end in 'Headline'."
        for slide_number, slide in enumerate(prs.slides, start=1)
        for shape in slide.shapes
        if shape.name.endswith(f"{ChartObjects.HEADLINE.value}s")
    ]


def _build_output_slides(
    prs, kpis: list[dict], show_data_labels: bool | None
) -> tuple[list[dict], list[str], list[str]]:
    """Turns the KPI config into output slides. Returns (slides, errors, warnings)."""
    object_slides = _object_slides(prs)
    template_rows = _template_rows(prs)
    output_slides, errors, warnings = [], [], []

    for kpi in kpis:
        kpi_name = kpi["name"]
        palette = kpi["palette"]
        explicit_rows = kpi.get("data", {})

        for slide in kpi["slides"]:
            template_index = slide["template_slide"] - 1
            if not 0 <= template_index < len(prs.slides):
                errors.append(
                    f"{kpi_name}: template_slide {slide['template_slide']} does not "
                    f"exist, the template has {len(prs.slides)} slides."
                )
                continue

            charts = {}
            for name, settings in slide["charts"].items():
                if object_slides.get(name) != template_index:
                    errors.append(
                        f"{kpi_name}: {name!r} is not a chart on template slide "
                        f"{slide['template_slide']}."
                    )
                    continue

                rows = explicit_rows.get(name) or template_rows.get(name)
                if not rows:
                    errors.append(f"{kpi_name}: {name!r} has no data.")
                    continue

                missing = {next(iter(row.values())) for row in rows} - set(palette)
                if missing:
                    errors.append(
                        f"{kpi_name}: {name!r} uses {sorted(missing)}, not in its palette."
                    )
                    continue

                chart = {
                    "chart_type": ChartType.DOUGHNUT,
                    "filters": {
                        key: settings[key]
                        for key in ("week", "brand")
                        if key in settings
                    },
                    "fillColor": palette,
                    "rows": rows,
                    "headline": settings.get("headline", ""),
                }
                if show_data_labels is not None:
                    chart["has_data_labels"] = show_data_labels
                charts[name] = chart

            empty = sorted(
                name
                for name, index in object_slides.items()
                if index == template_index and name not in slide["charts"]
            )
            if empty:
                warnings.append(
                    f"{kpi_name}, template slide {slide['template_slide']}: "
                    f"{empty} not configured, left empty."
                )

            output_slides.append(
                {
                    "kpi": kpi_name,
                    "template_slide": template_index,
                    "title": slide.get("title", ""),
                    "subtitle": slide.get("subtitle"),
                    "charts": charts,
                }
            )

    return output_slides, errors, warnings


@pytest.fixture
def render_deck(storage, cont):
    """Renders a deck from reusable template slides, e.g. the same slides once per KPI."""

    def _render(
        template_name: str,
        *,
        kpis: list[dict],
        output_name: str | None = None,
        language: Languages = Languages.DE,
        show_data_labels: bool | None = None,
    ) -> tuple[Path, dict]:

        template_path = TEMPLATE_DIR / template_name
        if not template_path.is_file():
            pytest.fail(f"Template not found: {template_path}")

        storage.write_blob(
            container_name=cont,
            blob_name=template_name,
            blob_data=template_path.read_bytes(),
        )

        prs = Presentation(template_path)
        _inspect(prs, template_name)

        output_slides, errors, warnings = _build_output_slides(
            prs, kpis, show_data_labels
        )
        for warning in _plural_headline_warnings(prs) + warnings:
            print(f"WARNING: {warning}")
        if errors:
            pytest.fail(
                "Deck cannot be rendered:\n"
                + "\n".join(f"  {i + 1}. {msg}" for i, msg in enumerate(errors)),
                pytrace=False,
            )

        config_dict = {
            "output_slides": output_slides,
            "file": template_name,
            "file_container": cont,
            "target_file_name": output_name or f"{template_path.stem}_preview",
            "target_blob_container": cont,
            "language": language,
        }

        config_dict = get_template_config(config_dict)

        for slide_number, template_slide in enumerate(
            config_dict["template_slides"], start=1
        ):
            legend = template_slide.get(SlideObjects.LEGEND.value)
            if legend is not None and not (legend.get("font") or {}).get("size_pt"):
                pytest.fail(
                    f"Template slide {slide_number}: the 'Legend' box has no explicit "
                    "font size. Type text into it and set a point size.",
                    pytrace=False,
                )

        graph_create_ppt(config_dict)

        blob = storage.read_blob(
            container_name=cont,
            blob_name=f"{config_dict['target_file_name']}.pptx",
            decode=False,
        )

        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        result_file = RESULT_DIR / f"{config_dict['target_file_name']}.pptx"
        result_file.write_bytes(blob)
        print(f"Wrote {result_file}")

        return result_file, config_dict

    return _render
