import copy
import io

from pycore.easy import storage

from pptcreator.creator.create_ppt.add_slide import add_slide
from pptcreator.creator.create_ppt.create_boxes import create_boxes
from pptcreator.creator.create_ppt.create_chart_headlines import create_chart_headlines
from pptcreator.creator.create_ppt.create_charts import create_charts
from pptcreator.creator.create_ppt.create_legend import create_legend
from pptcreator.creator.create_ppt.create_slide_headline import create_slide_headline
from pptcreator.creator.create_ppt.create_slide_subtitle import create_slide_subtitle
from pptcreator.creator.create_ppt.create_totals import create_totals
from pptcreator.creator.create_ppt.delete_template_slide import delete_template_slide
from pptcreator.models.enum import ChartObjects
from pptcreator.utils.get_presentation import get_presentation


def graph_create_ppt(config_dict: dict) -> dict:
    try:
        prs = get_presentation(config_dict)
        template_slide_count = len(prs.slides)

        if "output_slides" in config_dict:
            prs = _create_output_slides(prs, config_dict)
        else:
            prs = _create_filter_slides(prs, config_dict)

        # Remove the original template slides
        prs = delete_template_slide(prs, template_slide_count)

        # Save in Blob Storage
        blob_name = f"{config_dict['target_file_name']}.pptx"
        container = config_dict["target_blob_container"]

        buffer = io.BytesIO()
        prs.save(buffer)

        storage.write_blob(
            blob_name=blob_name,
            container_name=container,
            blob_data=buffer.getvalue(),
        )

        return config_dict
    except Exception as e:
        print(f"Failed to create PPT: {e}")
        raise


def _create_filter_slides(prs, config_dict: dict):
    """One output slide per filter value, all built from the first template slide."""
    for slide_filter in config_dict["filter"]:
        prs, new_slide = add_slide(prs)
        prs = _populate_slide(prs, new_slide, config_dict, slide_filter)
    return prs


def _create_output_slides(prs, config_dict: dict):
    """One output slide per configured slide; template slides can repeat, e.g. per KPI."""
    template_layouts = [slide.slide_layout for slide in prs.slides]

    for output_slide in config_dict["output_slides"]:
        template_index = output_slide["template_slide"]
        if not 0 <= template_index < len(template_layouts):
            raise ValueError(
                f"Template slide {template_index + 1} does not exist; the template "
                f"has {len(template_layouts)} slides."
            )

        prs, new_slide = add_slide(prs, template_layouts[template_index])

        slide_view = {
            **config_dict,
            "charts": _build_slide_charts(config_dict["charts"], output_slide),
            "headline_substring": output_slide.get("title", ""),
            "subtitle_substring": output_slide.get("subtitle"),
        }

        prs = _populate_slide(prs, new_slide, slide_view, None)
        prs = create_legend(
            prs, new_slide, slide_view, config_dict["template_slides"][template_index]
        )

    return prs


def _build_slide_charts(template_charts: dict, output_slide: dict) -> dict:
    """Template positions and fonts plus the slide's own data; unlisted charts stay empty."""
    template_index = output_slide["template_slide"]
    charts = {}

    for name, settings in output_slide.get("charts", {}).items():
        template_object = template_charts.get(name)
        if (
            template_object is None
            or template_object.get("slide_index") != template_index
            or ChartObjects.CHART.value not in template_object
        ):
            raise ValueError(
                f"{name!r} is not a chart on template slide {template_index + 1}."
            )

        # Copied because the same template object is reused on several output slides
        object_config = copy.deepcopy(template_object)
        object_config["chart_type"] = settings["chart_type"]
        object_config["filters"] = settings.get("filters", {})

        chart_config = object_config[ChartObjects.CHART.value]
        chart_config["fillColor"] = settings["fillColor"]
        chart_config["rows"] = settings["rows"]
        if "has_data_labels" in settings:
            chart_config["has_data_labels"] = settings["has_data_labels"]

        headline = object_config.get(ChartObjects.HEADLINE.value)
        if headline is not None:
            headline["translation"] = settings.get("headline", "")

        charts[name] = object_config

    return charts


def _populate_slide(prs, slide, config_dict: dict, slide_filter: str | None):
    prs = create_slide_headline(prs, slide, config_dict, slide_filter)
    prs = create_slide_subtitle(prs, slide, config_dict)
    prs = create_chart_headlines(prs, slide, config_dict)
    prs = create_boxes(prs, slide, config_dict)
    prs = create_charts(prs, slide, config_dict, slide_filter)
    prs = create_totals(prs, slide, config_dict, slide_filter)
    return prs
