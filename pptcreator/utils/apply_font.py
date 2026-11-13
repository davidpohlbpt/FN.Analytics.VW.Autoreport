from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.text import PP_ALIGN
from pptx.text.text import TextFrame
from pptx.util import Pt


def apply_font(text_frame: TextFrame, font_config: dict | None) -> None:
    """Applies the template font to every paragraph, so multi-line text stays consistent."""
    font_config = font_config or {}
    h_align = font_config.get("h_align")

    for paragraph in text_frame.paragraphs:
        if h_align is not None:
            paragraph.alignment = getattr(PP_ALIGN, h_align.name)
        for run in paragraph.runs:
            apply_run_style(run, font_config)


def apply_run_style(run, style: dict | None) -> None:
    """Size, bold, colour and typeface from a style dict as produced by get_template_config."""
    style = style or {}
    if style.get("size_pt") is not None:
        run.font.size = Pt(style["size_pt"])
    if style.get("is_bold") is not None:
        run.font.bold = style["is_bold"]
    if style.get("name"):
        run.font.name = style["name"]
    color = style.get("color")
    if color:
        if "rgb" in color:
            run.font.color.rgb = RGBColor.from_string(color["rgb"])
        elif "theme" in color:
            run.font.color.theme_color = MSO_THEME_COLOR(color["theme"])
            if color.get("brightness"):
                run.font.color.brightness = color["brightness"]


def write_styled_lines(text_frame: TextFrame, lines: list, font_config: dict | None) -> None:
    """Write lines, each either a str or a list of (text, part) tuples with part 'first'/'rest'.

    Uses the template's per-paragraph styles (``font_config['paragraph_styles']``) so that
    e.g. the week is bold and the brand regular, as in the template text box. Falls back
    to ``apply_font`` when the template has no per-paragraph styles.
    """
    font_config = font_config or {}
    styles = font_config.get("paragraph_styles") or []
    h_align = font_config.get("h_align")

    text_frame.text = ""
    for index, line in enumerate(lines):
        paragraph = text_frame.paragraphs[0] if index == 0 else text_frame.add_paragraph()
        if h_align is not None:
            paragraph.alignment = getattr(PP_ALIGN, h_align.name)
        parts = [(line, "first")] if isinstance(line, str) else line
        para_style = styles[min(index, len(styles) - 1)] if styles else None
        for text, part in parts:
            run = paragraph.add_run()
            run.text = text
            if para_style:
                # Size/bold fall back to the base font; colour and typeface belong to the
                # line (e.g. grey second line) and must not inherit the first line's.
                style = dict(para_style[part])
                if style.get("size_pt") is None:
                    style["size_pt"] = font_config.get("size_pt")
                if style.get("is_bold") is None:
                    # Unset bold in the template run means regular text
                    style["is_bold"] = False
                apply_run_style(run, style)
            else:
                apply_run_style(run, font_config)
