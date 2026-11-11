from pptx import presentation
from pptx.slide import Slide, SlideLayout


def add_slide(
    prs: presentation.Presentation, layout: SlideLayout | None = None
) -> tuple[presentation.Presentation, Slide]:

    # Default to the layout of the first template slide
    if layout is None:
        layout = prs.slides[0].slide_layout
    new_slide = prs.slides.add_slide(layout)

    return prs, new_slide
