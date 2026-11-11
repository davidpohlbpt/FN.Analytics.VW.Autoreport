from pptx import Presentation

from pptcreator.creator.create_ppt.create_charts import parse_rgb

# ------------------------------ CONFIGURE HERE ------------------------------ #

TEMPLATE_NAME = "VW_Template_Overview.pptx"
OUTPUT_NAME = "VW_KPI_Report"

BKA_SUBTITLE = (
    "Wann wurden BKAs das letzte Mal bearbeitet und wie ist das durchschnittliche "
    "BKA Alter?"
)

KPI1_PALETTE = {
    "< 1 Jahr": "rgb(146, 208, 80)",
    "1-2 Jahre": "rgb(197, 224, 180)",
    "2 - 4 Jahre": "rgb(255, 230, 153)",
    "4 - 6 Jahre": "rgb(244, 177, 131)",
    "> 6 Jahre": "rgb(255, 0, 0)",
    "ohne Daten": "rgb(127, 127, 127)",
}

# Example only -- replace with the real KPI 2 colours
KPI2_PALETTE = {
    "< 1 Jahr": "rgb(0, 51, 102)",
    "1-2 Jahre": "rgb(0, 102, 178)",
    "2 - 4 Jahre": "rgb(102, 163, 224)",
    "4 - 6 Jahre": "rgb(178, 210, 240)",
    "> 6 Jahre": "rgb(230, 240, 250)",
    "ohne Daten": "rgb(127, 127, 127)",
}

# The deck is built in this order. Each KPI reuses the template slides:
#   template_slide  1-based slide number in the template
#   charts          key = shape-name prefix; charts left out stay empty on the slide
#   headline        "\n" starts the second line
#   data            optional {shape-name prefix: [{"category": ..., "value": ...}]},
#                   charts without data reuse the numbers stored in the template
KPIS: list[dict] = [
    {
        "name": "KPI 1",
        "palette": KPI1_PALETTE,
        "slides": [
            {
                "template_slide": 1,
                "title": "BKAs nach Aktualisierung",
                "subtitle": BKA_SUBTITLE,
                "charts": {
                    "Chart 1": {
                        "week": "KW02",
                        "brand": "Gesamt VW PKW",
                        "headline": "KW02 - Gesamt VW PKW\nØ 2 Jahre, 5 Monate",
                    },
                    "Chart 2": {
                        "week": "KW37",
                        "brand": "Gesamt VW PKW",
                        "headline": "KW37 - Gesamt VW PKW\nØ 1 Jahr, 7 Monate",
                    },
                },
            },
            {
                "template_slide": 2,
                "title": "BKAs nach Aktualisierung",
                "subtitle": BKA_SUBTITLE,
                "charts": {
                    "Chart 3": {
                        "week": "KW37",
                        "brand": "BC",
                        "headline": "BC Ø 1 Jahr, 3 Monate\nKW02: Ø 1 Jahr, 2 Monate",
                    },
                    "Chart 4": {
                        "week": "KW37",
                        "brand": "BI",
                        "headline": "BI Ø 1 Jahr, 5 Monate\nKW02: Ø 2 Jahre, 6 Monate",
                    },
                    "Chart 5": {
                        "week": "KW37",
                        "brand": "BM",
                        "headline": "BM Ø 1 Jahr, 6 Monate\nKW02: Ø 2 Jahre, 1 Monat",
                    },
                    "Chart 6": {
                        "week": "KW37",
                        "brand": "BN",
                        "headline": "BN Ø 7 Monate\nKW02: Ø 9 Monate",
                    },
                    "Chart 7": {
                        "week": "KW37",
                        "brand": "BX",
                        "headline": "BX Ø 2 Jahre, 5 Monate\nKW02: Ø 3 Jahre, 1 Monat",
                    },
                    "Chart 8": {
                        "week": "KW37",
                        "brand": "CB",
                        "headline": "CB Ø 1 Jahre, 4 Monate\nKW02: Ø 3 Jahre, 6 Monate",
                    },
                    "Chart 9": {
                        "week": "KW37",
                        "brand": "ZB",
                        "headline": "ZB Ø 11 Monate\nKW02: Ø 1 Jahr, 2 Monate",
                    },
                },
            },
        ],
    },
    # Example only -- shows a different palette and a detail slide with 6 brands
    {
        "name": "KPI 2 (Beispiel)",
        "palette": KPI2_PALETTE,
        "slides": [
            {
                "template_slide": 1,
                "title": "KPI 2 Beispiel",
                "subtitle": "Beispiel-Untertitel KPI 2",
                "charts": {
                    "Chart 1": {"week": "KW02", "headline": "KW02\nBeispiel"},
                    "Chart 2": {"week": "KW37", "headline": "KW37\nBeispiel"},
                },
            },
            {
                "template_slide": 2,
                "title": "KPI 2 Beispiel - Details",
                "subtitle": "Nur 6 Marken: die siebte Position bleibt leer",
                "charts": {
                    "Chart 3": {"week": "KW37", "brand": "BC", "headline": "BC"},
                    "Chart 4": {"week": "KW37", "brand": "BI", "headline": "BI"},
                    "Chart 5": {"week": "KW37", "brand": "BM", "headline": "BM"},
                    "Chart 6": {"week": "KW37", "brand": "BN", "headline": "BN"},
                    "Chart 7": {"week": "KW37", "brand": "BX", "headline": "BX"},
                    "Chart 8": {"week": "KW37", "brand": "CB", "headline": "CB"},
                },
            },
        ],
    },
]

SHOW_DATA_LABELS = False

# ---------------------------------------------------------------------------- #


def _format_total(rows: list[dict]) -> str:
    return f"{sum(row['value'] for row in rows):,.0f}".replace(",", ".")


def test_vw_kpi_deck(render_deck):

    result_file, config_dict = render_deck(
        TEMPLATE_NAME,
        kpis=KPIS,
        output_name=OUTPUT_NAME,
        show_data_labels=SHOW_DATA_LABELS,
    )

    output_slides = config_dict["output_slides"]
    prs = Presentation(result_file)
    assert len(prs.slides) == sum(len(kpi["slides"]) for kpi in KPIS)

    for slide, output_slide in zip(prs.slides, output_slides):
        charts_config = output_slide["charts"]

        assert slide.shapes.title.text == output_slide["title"]
        assert output_slide["subtitle"] in [
            ph.text_frame.text for ph in slide.placeholders if ph.has_text_frame
        ]

        charts = [shape.chart for shape in slide.shapes if shape.has_chart]
        assert len(charts) == len(charts_config)
        for chart in charts:
            assert not chart.has_legend
            assert chart.plots[0].has_data_labels is SHOW_DATA_LABELS

        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
        for chart_config in charts_config.values():
            assert chart_config["headline"] in texts
            assert _format_total(chart_config["rows"]) in texts

        expected_legend = list(
            dict.fromkeys(
                row["category"]
                for chart_config in charts_config.values()
                for row in chart_config["rows"]
            )
        )
        palette = next(iter(charts_config.values()))["fillColor"]
        legends = [shape for shape in slide.shapes if shape.name == "Legend"]
        assert len(legends) == 1
        runs = legends[0].text_frame.paragraphs[0].runs
        # Runs alternate between a coloured swatch and its label
        assert [run.text.strip() for run in runs[1::2]] == expected_legend
        assert [str(run.font.color.rgb) for run in runs[0::2]] == [
            str(parse_rgb(palette[category])) for category in expected_legend
        ]
