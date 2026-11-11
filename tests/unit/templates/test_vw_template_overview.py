from pptx import Presentation

# ------------------------------ CONFIGURE HERE ------------------------------ #

TEMPLATE_NAME = "VW_Template_Overview.pptx"
OUTPUT_NAME = "VW_Overview_Report"

# Slide title -- rendered as "<SLIDE_TITLE> - <filter value>"
SLIDE_TITLE = "BKAs nach Aktualisierung"

# Slide subtitle -- written into the layout's text placeholder, None to leave it empty
SLIDE_SUBTITLE = "Wann wurden BKAs das letzte Mal aktualisiert?"

# One slide is generated per entry
FILTER_VALUES = ["KW02", "KW37"]

# Every category used in the chart data must appear here
PALETTE = {
    "< 1 Jahr": "rgb(146, 208, 80)",
    "1-2 Jahre": "rgb(197, 224, 180)",
    "2 - 4 Jahre": "rgb(255, 230, 153)",
    "4 - 6 Jahre": "rgb(244, 177, 131)",
    "> 6 Jahre": "rgb(255, 0, 0)",
    "ohne Daten": "rgb(127, 127, 127)",
}

# Headline above each chart. Key = template_object_name (the shape-name prefix).
CHART_TITLES: dict[str, str] = {
    "Chart 1": "KW02",
    "Chart 2": "KW37",
}

# Optional explicit data: {object_name: {filter_value: [{"category": ..., "value": ...}]}}
# Omit an object to fall back to generated dummy data.
CHART_DATA: dict[str, dict[str, list[dict]]] = {}

# None = inherit from the template, True/False = force
SHOW_DATA_LABELS = False

# ---------------------------------------------------------------------------- #


def test_vw_template_overview(render_template):

    result_file, _ = render_template(
        TEMPLATE_NAME,
        slide_title=SLIDE_TITLE,
        slide_subtitle=SLIDE_SUBTITLE,
        filter_values=FILTER_VALUES,
        palette=PALETTE,
        chart_titles=CHART_TITLES,
        chart_data=CHART_DATA,
        output_name=OUTPUT_NAME,
        show_data_labels=SHOW_DATA_LABELS,
    )

    prs = Presentation(result_file)
    assert len(prs.slides) == len(FILTER_VALUES)
    assert prs.slides[0].shapes.title.text == f"{SLIDE_TITLE} - {FILTER_VALUES[0]}"
