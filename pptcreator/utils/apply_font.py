from pptx.enum.text import PP_ALIGN
from pptx.text.text import TextFrame
from pptx.util import Pt


def apply_font(text_frame: TextFrame, font_config: dict | None) -> None:
    """Applies the template font to every paragraph, so multi-line text stays consistent."""
    font_config = font_config or {}
    h_align = font_config.get("h_align")
    size_pt = font_config.get("size_pt")
    is_bold = font_config.get("is_bold")

    for paragraph in text_frame.paragraphs:
        if h_align is not None:
            paragraph.alignment = getattr(PP_ALIGN, h_align.name)
        for run in paragraph.runs:
            if size_pt is not None:
                run.font.size = Pt(size_pt)
            if is_bold is not None:
                run.font.bold = is_bold
