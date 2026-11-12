from pptx import presentation
from pptx.enum.text import MSO_ANCHOR
from pptx.slide import Slide
from pptx.util import Emu

from pptcreator.models.enum import ChartObjects, Languages
from pptcreator.utils.apply_font import apply_font
from pptcreator.utils.get_chart_rows import get_chart_rows


def create_totals(
    prs: presentation.Presentation,
    slide: Slide,
    config_dict: dict,
    slide_filter: str | None,
) -> presentation.Presentation:

    for _, template_object_config in config_dict["charts"].items():
        total_config = template_object_config.get(ChartObjects.TOTAL.value)
        if total_config is None:
            continue

        chart_data = get_chart_rows(template_object_config, slide_filter)
        if not chart_data:
            continue

        position = total_config["position"]
        textbox = slide.shapes.add_textbox(
            left=Emu(position["left_emu"]),
            top=Emu(position["top_emu"]),
            width=Emu(position["width_emu"]),
            height=Emu(position["height_emu"]),
        )
        text_frame = textbox.text_frame
        text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        text_frame.text = _format_total(
            _sum_values(chart_data), config_dict.get("language")
        )
        apply_font(text_frame, total_config.get("font"))

    return prs


def _sum_values(chart_data: list[dict]) -> float:
    # Second key holds the value, same assumption as create_charts
    value_key = list(chart_data[0])[1]
    return sum(row[value_key] for row in chart_data)


def _format_total(total: float, language: Languages | None) -> str:
    text = f"{total:,.0f}"
    return text if language == Languages.EN else text.replace(",", ".")
