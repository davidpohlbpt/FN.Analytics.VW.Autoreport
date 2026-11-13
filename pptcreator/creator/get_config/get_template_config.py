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
                "color": _run_color(run),
                "name": run.font.name,
            }
            # Per-line styles, e.g. "{week} – {brand}" (bold + regular) / "{kpi}" (grey)
            config["font"]["paragraph_styles"] = [
                {"first": _run_style(p.runs[0]), "rest": _run_style(p.runs[-1])}
                for p in tf.paragraphs
                if p.runs
            ]

    # Get font size, alignments etc from charts
    if shape.has_chart:
        chart = shape.chart
        config["has_legend"] = chart.has_legend
        config["has_data_labels"] = _labels_visible(chart)
        hole = chart._chartSpace.xpath(".//c:holeSize/@val")
        if hole:
            config["hole_size"] = int(hole[0])
        border = chart._chartSpace.xpath(".//c:ser/c:dPt/c:spPr/a:ln")
        if border:
            width = border[0].get("w")
            color = border[0].xpath("./a:solidFill/a:srgbClr/@val")
            if color:
                config["slice_border"] = {
                    "width_emu": int(width) if width else None,
                    "rgb": color[0],
                }
        # Without a legend the chart-level defaults are the only font source
        font = chart.legend.font if chart.has_legend else chart.font
        config["font"] = {
            "size_pt": font.size.pt if font.size is not None else None,
            "is_bold": font.bold,
        }

    return config


def _labels_visible(chart) -> bool:
    """True only if a data label actually shows something.

    python-pptx's ``has_data_labels`` is True whenever a <c:dLbls> element exists, even
    if all its show* flags are 0 (as in the VW template, where labels are off).
    """
    flags = chart._chartSpace.xpath(
        ".//c:dLbls/c:showVal/@val | .//c:dLbls/c:showPercent/@val | .//c:dLbls/c:showCatName/@val"
    )
    return any(str(v) in ("1", "true") for v in flags)


def _run_color(run) -> dict | None:
    """Explicit RGB or theme colour of a run, as plain data (no python-pptx objects)."""
    try:
        color = run.font.color
        if color.type is None:
            return None
        if color.type == 1:  # MSO_COLOR_TYPE.RGB
            return {"rgb": str(color.rgb)}
        return {"theme": int(color.theme_color), "brightness": color.brightness}
    except (AttributeError, ValueError, TypeError):
        return None


def _run_style(run) -> dict:
    return {
        "size_pt": run.font.size.pt if run.font.size is not None else None,
        "is_bold": run.font.bold,
        "color": _run_color(run),
        "name": run.font.name,
    }
