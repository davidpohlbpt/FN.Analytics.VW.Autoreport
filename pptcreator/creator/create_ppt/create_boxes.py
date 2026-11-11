from pptx import presentation
from pptx.dml.color import RGBColor
from pptx.slide import Slide
from pptx.util import Emu

from pptcreator.models.enum import ChartObjects


def create_boxes(prs: presentation.Presentation, slide: Slide, config_dict: dict):

    for _, template_object_config in config_dict["charts"].items():
        box_config = template_object_config.get(ChartObjects.BOX.value)
        if box_config is None:
            continue

        position = box_config["position"]

        textbox = slide.shapes.add_textbox(
            left=Emu(position["left_emu"]),
            top=Emu(position["top_emu"]),
            width=Emu(position["width_emu"]),
            height=Emu(position["height_emu"]),
        )

        textbox.fill.solid()
        textbox.fill.fore_color.rgb = RGBColor(0xEA, 0xEA, 0xEA)

    return prs
