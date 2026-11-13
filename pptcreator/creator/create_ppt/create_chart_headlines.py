from pptx import presentation
from pptx.enum.text import MSO_ANCHOR
from pptx.slide import Slide
from pptx.util import Emu

from pptcreator.models.enum import ChartObjects
from pptcreator.utils.apply_font import apply_font, write_styled_lines
from pptcreator.utils.text_fit import fit_font_size

LINE_HEIGHT = 1.2
EMU_PER_PT = 12700


def create_chart_headlines(
    prs: presentation.Presentation, slide: Slide, config_dict: dict
):
    items = []
    for _, template_object_config in config_dict["charts"].items():
        headline_config = template_object_config.get(ChartObjects.HEADLINE.value)
        if headline_config is None:
            continue
        left, width = _headline_span(headline_config, template_object_config.get(ChartObjects.CHART.value))
        items.append((headline_config, left, width))

    # One font size for all structured headlines of the slide, so they look uniform
    shared_size = _shared_size(items)

    for headline_config, left, width in items:
        position = headline_config["position"]
        textbox = slide.shapes.add_textbox(
            left=Emu(left),
            top=Emu(position["top_emu"]),
            width=Emu(width),
            height=Emu(position["height_emu"]),
        )
        text_frame = textbox.text_frame
        text_frame.word_wrap = True
        text_frame.vertical_anchor = MSO_ANCHOR.TOP

        lines = headline_config.get("lines")
        font = dict(headline_config.get("font") or {})
        if lines:
            if shared_size is not None and font.get("size_pt"):
                font = _scale_font(font, shared_size)
            # Structured headline: per-line / per-part styles from the template
            write_styled_lines(text_frame, lines, font)
        else:
            # "\n" in the text starts a new paragraph
            text_frame.text = headline_config["translation"]
            apply_font(text_frame, font)

    return prs


def _shared_size(items) -> float | None:
    sizes = []
    for headline_config, _, width in items:
        lines = headline_config.get("lines")
        font = headline_config.get("font") or {}
        if not lines or not font.get("size_pt"):
            continue
        plain = [_plain(line) for line in lines]
        size = fit_font_size(plain, width, font["size_pt"], bold=bool(font.get("is_bold")))
        # The template box is sized for its lines; do not grow into the legend below
        height = headline_config["position"]["height_emu"]
        if len(plain) * size * LINE_HEIGHT * EMU_PER_PT > height * 1.35:
            size = max(9.0, min(size, height * 1.35 / (len(plain) * LINE_HEIGHT * EMU_PER_PT)))
        sizes.append(size)
    return min(sizes) if sizes else None


def _plain(line) -> str:
    return line if isinstance(line, str) else "".join(text for text, _ in line)


def _headline_span(headline_config: dict, chart_config: dict | None) -> tuple[int, int]:
    """Headline box at least as wide as its chart, centred on the template headline."""
    position = headline_config["position"]
    left, width = position["left_emu"], position["width_emu"]
    if chart_config:
        chart_width = chart_config["position"]["width_emu"]
        if chart_width > width:
            center = left + width // 2
            width = chart_width
            left = center - width // 2
    return left, width


def _scale_font(font: dict, size_pt: float) -> dict:
    """Apply the fitted size to the base font and every per-paragraph style."""
    original = font.get("size_pt") or size_pt
    ratio = size_pt / original
    scaled = {**font, "size_pt": size_pt}
    styles = []
    for style in font.get("paragraph_styles") or []:
        new_style = {}
        for part, values in style.items():
            values = dict(values)
            if values.get("size_pt"):
                values["size_pt"] = round(values["size_pt"] * ratio * 2) / 2
            new_style[part] = values
        styles.append(new_style)
    if styles:
        scaled["paragraph_styles"] = styles
    return scaled
