import re

from pptx import presentation
from pptx.chart.chart import Chart
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.oxml.ns import qn
from pptx.slide import Slide
from pptx.util import Emu, Pt

from pptcreator.models.enum import ChartObjects as CHART_OBJECTS
from pptcreator.models.enum import ChartType as CHART_TYPE
from pptcreator.utils.get_chart_rows import get_chart_rows

_RGB_PATTERN = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")
_DONUT_HOLE_SIZE_PERCENT = 50


def create_charts(
    prs: presentation.Presentation,
    slide: Slide,
    config_dict: dict,
    slide_filter: str | None,
) -> presentation.Presentation:

    for object_name, template_object_config in config_dict["charts"].items():
        chart_config = template_object_config[CHART_OBJECTS.CHART.value]
        chart_data = get_chart_rows(template_object_config, slide_filter)

        if template_object_config["chart_type"] == CHART_TYPE.DOUGHNUT:
            add_donut_chart(slide, chart_config, chart_data, object_name=object_name)
        else:
            raise ValueError(
                f"{object_name!r}: unsupported chart type "
                f"{template_object_config['chart_type']!r}"
            )

    return prs


def add_donut_chart(
    slide: Slide, chart_config: dict, chart_data: list, object_name: str = "chart"
) -> None:

    chart_position = chart_config["position"]
    chart_fill_color = chart_config["fillColor"]
    font_config = chart_config.get("font") or {}
    font_size_pt = font_config.get("size_pt")
    has_legend = chart_config.get("has_legend", True)
    has_data_labels = chart_config.get("has_data_labels", True)

    if not chart_data:
        raise ValueError(f"{object_name!r}: no data rows to render.")
    if any(not isinstance(row, dict) or len(row) < 2 for row in chart_data):
        raise ValueError(
            f"{object_name!r}: every row needs a category and a value, got {chart_data!r}"
        )

    # Key assumption: First key is category, second key is value
    category_key, value_key = list(chart_data[0])[:2]
    missing_colors = [row[category_key] for row in chart_data if row[category_key] not in chart_fill_color]
    if missing_colors:
        raise ValueError(
            f"{object_name!r}: no fill colour for categories {missing_colors}; "
            f"palette has {list(chart_fill_color)}"
        )

    chart_input = CategoryChartData()
    categories = [row[category_key] for row in chart_data]
    chart_input.categories = categories
    values = [row[value_key] for row in chart_data]
    chart_input.add_series("Series 1", values)

    graphic_frame = slide.shapes.add_chart(
        XL_CHART_TYPE.DOUGHNUT,
        Emu(chart_position["left_emu"]),
        Emu(chart_position["top_emu"]),
        Emu(chart_position["width_emu"]),
        Emu(chart_position["height_emu"]),
        chart_input,
    )
    chart = graphic_frame.chart
    chart.has_title = False
    doughnut = chart._chartSpace.find(".//" + qn("c:doughnutChart"))
    if doughnut is not None:
        hole_size = doughnut.find(qn("c:holeSize"))
        if hole_size is None:
            hole_size = doughnut.makeelement(qn("c:holeSize"), {})
            doughnut.append(hole_size)
        hole_size.set("val", str(_DONUT_HOLE_SIZE_PERCENT))

    # Add legend
    chart.has_legend = has_legend
    if has_legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        if font_size_pt is not None:
            chart.legend.font.size = Pt(font_size_pt)

    # Change colors
    series = chart.plots[0].series[0]
    for point, category in zip(series.points, categories):
        point.format.fill.solid()
        point.format.fill.fore_color.rgb = parse_rgb(chart_fill_color[category])

    # Add data labels
    plot = chart.plots[0]
    plot.has_data_labels = has_data_labels
    if has_data_labels:
        data_labels = plot.data_labels
        data_labels.show_value = True
        if font_size_pt is not None:
            data_labels.font.size = Pt(font_size_pt)


def parse_rgb(value: str) -> RGBColor:
    match = _RGB_PATTERN.match(value)
    if not match:
        raise ValueError(f"Unsupported color format: {value!r}")
    r, g, b = (int(channel) for channel in match.groups())
    return RGBColor(r, g, b)
