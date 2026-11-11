from pptcreator.models.enum import ChartObjects, SlideObjects, TextAlignments
from pptcreator.utils.get_presentation import get_presentation


def get_template_config(config_dict: dict) -> dict:

    prs = get_presentation(config_dict)

    # Multi-slide decks read every template object; legacy configs only mapped ones
    multi_slide = "output_slides" in config_dict
    if multi_slide:
        config_dict.setdefault("charts", {})
        config_dict["template_slides"] = [{} for _ in prs.slides]

    for slide_index, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if multi_slide and shape.name == SlideObjects.LEGEND.value:
                config_dict["template_slides"][slide_index][
                    SlideObjects.LEGEND.value
                ] = get_config(shape)
                continue

            for role in ChartObjects:
                if not shape.name.endswith(role.value):
                    continue
                shape_name = shape.name.removesuffix(role.value).rstrip()

                if multi_slide:
                    object_config = config_dict["charts"].setdefault(
                        shape_name, {"slide_index": slide_index}
                    )
                    if object_config["slide_index"] != slide_index:
                        raise ValueError(
                            f"{shape_name!r} appears on template slides "
                            f"{object_config['slide_index'] + 1} and {slide_index + 1}; "
                            "object names must be unique across the template."
                        )

                # Shapes without a mapping entry are not part of the report
                if shape_name in config_dict["charts"]:
                    config_dict["charts"][shape_name][role.value] = get_config(shape)
                break

    return config_dict


def get_config(shape):

    config = {}
    config["name"] = shape.name
    config["position"] = {
        "left_emu": shape.left,
        "top_emu": shape.top,
        "width_emu": shape.width,
        "height_emu": shape.height,
    }

    # Get font size, alignments etc from text boxes
    if shape.has_text_frame:
        tf = shape.text_frame
        para = tf.paragraphs[0]
        run = para.runs[0] if para.runs else None
        if run is not None and run.font.size is not None:
            config["font"] = {
                "size_pt": run.font.size.pt,
                "is_bold": run.font.bold,
                "h_align": (
                    TextAlignments(para.alignment.name) if para.alignment else None
                ),
            }

    # Get font size, alignments etc from charts
    if shape.has_chart:
        chart = shape.chart
        config["has_legend"] = chart.has_legend
        config["has_data_labels"] = bool(chart.plots and chart.plots[0].has_data_labels)
        # Without a legend the chart-level defaults are the only font source
        font = chart.legend.font if chart.has_legend else chart.font
        config["font"] = {
            "size_pt": font.size.pt if font.size is not None else None,
            "is_bold": font.bold,
        }

    return config
