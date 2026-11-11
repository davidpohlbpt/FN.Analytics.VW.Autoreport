from pptx import presentation
from pptx.slide import Slide


def create_slide_subtitle(
    prs: presentation.Presentation, slide: Slide, config_dict: dict
) -> presentation.Presentation:

    subtitle = config_dict.get("subtitle_substring")
    if not subtitle:
        return prs

    placeholder = _find_subtitle_placeholder(slide)
    if placeholder is None:
        return prs

    placeholder.text_frame.text = subtitle

    return prs


def _find_subtitle_placeholder(slide: Slide):
    """First non-title text placeholder of the layout, mirroring how the title is found."""
    title = slide.shapes.title
    # python-pptx builds a new proxy per access, so compare ids rather than identity
    title_id = title.shape_id if title is not None else None
    for placeholder in slide.placeholders:
        if placeholder.shape_id == title_id or not placeholder.has_text_frame:
            continue
        return placeholder
    return None
