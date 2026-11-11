from pptx import presentation
from pptx.slide import Slide
from pptx.util import Emu

from pptcreator.models.enum import ChartObjects
from pptcreator.utils.apply_font import apply_font


def create_chart_headlines(
    prs: presentation.Presentation, slide: Slide, config_dict: dict
):

    for _, template_object_config in config_dict["charts"].items():
        headline_config = template_object_config.get(ChartObjects.HEADLINE.value)
        if headline_config is None:
            continue

        position = headline_config["position"]

        textbox = slide.shapes.add_textbox(
            left=Emu(position["left_emu"]),
            top=Emu(position["top_emu"]),
            width=Emu(position["width_emu"]),
            height=Emu(position["height_emu"]),
        )
        text_frame = textbox.text_frame
        # "\n" in the text starts a new paragraph
        text_frame.text = headline_config["translation"]
        apply_font(text_frame, headline_config.get("font"))

    return prs
