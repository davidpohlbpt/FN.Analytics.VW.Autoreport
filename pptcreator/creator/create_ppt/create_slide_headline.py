from pptx import presentation
from pptx.slide import Slide


def create_slide_headline(
    prs: presentation.Presentation,
    slide: Slide,
    config_dict: dict,
    slide_filter: str | None,
):

    headline = config_dict["headline_substring"]
    if slide_filter is not None:
        headline = f"{headline} - {slide_filter}"
    slide.shapes.title.text = headline

    return prs
