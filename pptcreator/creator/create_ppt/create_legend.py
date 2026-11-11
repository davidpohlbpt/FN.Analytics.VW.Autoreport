from pptx import presentation
from pptx.enum.text import MSO_ANCHOR
from pptx.slide import Slide
from pptx.util import Emu

from pptcreator.creator.create_ppt.create_charts import parse_rgb
from pptcreator.models.enum import ChartObjects, SlideObjects
from pptcreator.utils.apply_font import apply_font
from pptcreator.utils.get_chart_rows import get_chart_rows

SWATCH = "\u25a0"
_ENTRY_SPACING = "\u2003\u2003"


def create_legend(
    prs: presentation.Presentation,
    slide: Slide,
    config_dict: dict,
    slide_config: dict,
) -> presentation.Presentation:

    legend_config = slide_config.get(SlideObjects.LEGEND.value)
    if legend_config is None:
        return prs

    entries = _collect_entries(config_dict["charts"])
    if not entries:
        return prs

    position = legend_config["position"]
    textbox = slide.shapes.add_textbox(
        Emu(position["left_emu"]),
        Emu(position["top_emu"]),
        Emu(position["width_emu"]),
        Emu(position["height_emu"]),
    )
    textbox.name = SlideObjects.LEGEND.value

    text_frame = textbox.text_frame
    text_frame.word_wrap = True
    text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    paragraph = text_frame.paragraphs[0]

    # One paragraph lets PowerPoint lay out the row, so entries can never overlap
    for index, (category, color) in enumerate(entries):
        swatch = paragraph.add_run()
        swatch.text = SWATCH if index == 0 else f"{_ENTRY_SPACING}{SWATCH}"
        swatch.font.color.rgb = parse_rgb(color)

        label = paragraph.add_run()
        label.text = f" {category}"

    apply_font(text_frame, legend_config.get("font"))

    return prs


def _collect_entries(charts: dict) -> list[tuple[str, str]]:
    """Union of categories across the slide's charts, in first-seen order."""
    entries: dict[str, str] = {}
    for object_config in charts.values():
        fill_colors = object_config[ChartObjects.CHART.value]["fillColor"]
        for row in get_chart_rows(object_config, None):
            # First key is the category, same assumption as create_charts
            category = next(iter(row.values()))
            if category not in entries:
                entries[category] = fill_colors[category]
    return list(entries.items())
