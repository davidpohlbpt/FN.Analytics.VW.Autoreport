import io
from pathlib import Path

import pytest
from pptx import Presentation

from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.models.enum import Languages, TextAlignments

RESULT_DIR = Path(__file__).resolve().parents[2] / "result"


@pytest.fixture
def config_dict():
    return {
        "charts": {
            "Chart 1": {
                "tile_id": 7011,
                "chart_id": 70110,
                "report_data_source_id": 704,
                "chart_type": "doughnut",
                "Box": {
                    "name": "Chart 1 Box",
                    "position": {
                        "left_emu": 268529,
                        "top_emu": 3161145,
                        "width_emu": 3571227,
                        "height_emu": 458720,
                    },
                },
                "Chart": {
                    "name": "Chart 1 Chart",
                    "position": {
                        "left_emu": 288747,
                        "top_emu": 1019372,
                        "width_emu": 3530790,
                        "height_emu": 2190094,
                    },
                    "font": {"size_pt": 9.0, "is_bold": None},
                    "fillColor": {
                        "Evaluation ongoing": "rgb(217, 217, 217)",
                        "12-month forecast confirmed": "rgb(255, 255, 0)",
                        "Not relevant": "rgb(127, 127, 127)",
                        "12-month forecast not confirmed": "rgb(255, 0, 0)",
                        "Supply readiness\xa0confirmed": "rgb(146, 208, 80)",
                        "values.innerLabel.color": "rgba(0, 0, 0, 1)",
                    },
                    "data": {
                        "P102718": [
                            {
                                "supplier_status_long": "Evaluation ongoing",
                                "count_supplier": 68.0,
                            }
                        ],
                        "P102719": [
                            {
                                "supplier_status_long": "Evaluation ongoing",
                                "count_supplier": 116.0,
                            }
                        ],
                        "P103165": [
                            {
                                "supplier_status_long": "Evaluation ongoing",
                                "count_supplier": 17.0,
                            }
                        ],
                    },
                },
                "Headline": {
                    "name": "Chart 1 Headline",
                    "position": {
                        "left_emu": 478987,
                        "top_emu": 908720,
                        "width_emu": 3150310,
                        "height_emu": 215444,
                    },
                    "font": {
                        "size_pt": 14.0,
                        "is_bold": True,
                        "h_align": TextAlignments.CENTER,
                    },
                    "translation": "Supplier Readiness",
                },
            },
            "Chart 4": {
                "tile_id": 7014,
                "chart_id": 70140,
                "report_data_source_id": 704,
                "chart_type": "doughnut",
                "Box": {
                    "name": "Chart 4 Box",
                    "position": {
                        "left_emu": 268529,
                        "top_emu": 5994616,
                        "width_emu": 3571227,
                        "height_emu": 458720,
                    },
                },
                "Chart": {
                    "name": "Chart 4 Chart",
                    "position": {
                        "left_emu": 288747,
                        "top_emu": 3827684,
                        "width_emu": 3530790,
                        "height_emu": 2190094,
                    },
                    "font": {"size_pt": 9.0, "is_bold": None},
                    "fillColor": {
                        "No": "rgba(233, 89, 73, 1)",
                        "Yes": "rgba(85, 204, 62, 1)",
                        " ": "rgba(237, 237, 237, 1)",
                        "Not relevant": "rgb(127, 127, 127)",
                        "Done": "rgb(146, 208, 80)",
                        "Open": "rgb(255, 0, 0)",
                        "values.innerLabel.color": "rgba(0, 0, 0, 1)",
                    },
                    "data": {
                        "P102718": [
                            {"supplier_status_long": "Done", "count_supplier": 10.0},
                            {"supplier_status_long": "Open", "count_supplier": 4.0},
                            {
                                "supplier_status_long": "Not relevant",
                                "count_supplier": 2.0,
                            },
                        ],
                        "P102719": [
                            {"supplier_status_long": "Done", "count_supplier": 5.0},
                            {"supplier_status_long": "Open", "count_supplier": 10.0},
                            {
                                "supplier_status_long": "Not relevant",
                                "count_supplier": 2.0,
                            },
                        ],
                        "P103165": [
                            {"supplier_status_long": "Done", "count_supplier": 20.0}
                        ],
                    },
                },
                "Headline": {
                    "name": "Chart 4 Headline",
                    "position": {
                        "left_emu": 236553,
                        "top_emu": 3717032,
                        "width_emu": 3635179,
                        "height_emu": 215444,
                    },
                    "font": {
                        "size_pt": 14.0,
                        "is_bold": True,
                        "h_align": TextAlignments.CENTER,
                    },
                    "translation": "EDI Connection",
                },
            },
        },
        "file": "Test_PPT.pptx",
        "file_container": "ppt_creator",
        "headline_substring": "Test Headline Substring",
        "target_file_name": "Customer_Report",
        "target_blob_container": "ppt_creator",
        "filter_column": "project_name",
        "language": Languages.DE,
        "recipients": ["prm.lead@example.com"],
        "menu_item_id": 704,
        "report_id": 704,
        "filter": [
            "P102718",
            "P102719",
            "P103165",
        ],
    }


def test_graph_create_ppt(storage, cont, config_dict):

    # -------------------------------- Arrange --------------------------------- #
    test_file_1 = "Test_PPT.pptx"

    with open(f"./tests/unit/test_data/{test_file_1}", "rb") as f:
        file_data = f.read()

    storage.write_blob(
        container_name=cont,
        blob_name=test_file_1,
        blob_data=file_data,
    )

    # ---------------------------------- Act ----------------------------------- #
    graph_create_ppt(config_dict)

    # -------------------------------- Assert ---------------------------------- #

    # Check if file exists
    blob = storage.read_blob(
        container_name=config_dict["target_blob_container"],
        blob_name=f"{config_dict['target_file_name']}.pptx",
        decode=False,
    )

    # Persist the deck outside the temp storage so it can be inspected manually
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result_file = RESULT_DIR / f"{config_dict['target_file_name']}.pptx"
    result_file.write_bytes(blob)

    prs = Presentation(io.BytesIO(blob))

    # Check number of slides
    assert len(prs.slides) == len(config_dict["filter"])

    # Check number of objects on each slide
    for slide in prs.slides:
        charts = [s for s in slide.shapes if s.has_chart]
        textboxes = [s for s in slide.shapes if s.has_text_frame and not s.has_chart]
        assert len(charts) == len(config_dict["charts"])  # 2 Charts
        assert len(textboxes) == 5  # 1 Slide Headline + 2 Chart Headlines + 2 Boxen

    # Check content of first chart
    chart_0 = [s for s in prs.slides[0].shapes if s.has_chart][0].chart
    plot = chart_0.plots[0]
    assert list(plot.categories) == ["Evaluation ongoing"]
    assert list(plot.series[0].values) == [68.0]

    exp_headline = config_dict["headline_substring"] + " - " + config_dict["filter"][0]
    assert prs.slides[0].shapes.title.text == exp_headline
