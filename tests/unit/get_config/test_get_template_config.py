import pytest

from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.models.enum import Languages, TextAlignments


@pytest.fixture
def exp_config():
    return {
        "charts": {
            "Chart 1": {
                "tile_id": 301,
                "chart_id": 401,
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
                    "has_legend": True,
                    "has_data_labels": True,
                    "font": {"size_pt": 9.0, "is_bold": None},
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
                },
            },
            "Chart 4": {
                "tile_id": 302,
                "chart_id": 402,
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
                    "has_legend": True,
                    "has_data_labels": True,
                    "font": {"size_pt": 9.0, "is_bold": None},
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
                },
            },
        },
        "file": "Test_PPT.pptx",
        "file_container": "ppt_creator",
        "filter_column": "project_name",
        "language": Languages.DE,
        "recipients": ["prm.lead@example.com"],
        "menu_item_id": 704,
        "report_id": 201,
    }


def test_get_template_config(storage, cont, exp_config):

    # -------------------------------- Arrange --------------------------------- #

    test_file_1 = "Test_PPT.pptx"

    with open(f"./tests/unit/test_data/{test_file_1}", "rb") as f:
        file_data = f.read()

    storage.write_blob(
        container_name=cont,
        blob_name=test_file_1,
        blob_data=file_data,
    )

    config_dict = {
        "charts": {
            "Chart 1": {"tile_id": 301, "chart_id": 401},
            "Chart 4": {"tile_id": 302, "chart_id": 402},
        },
        "file": "Test_PPT.pptx",
        "file_container": "ppt_creator",
        "filter_column": "project_name",
        "language": Languages.DE,
        "recipients": ["prm.lead@example.com"],
        "menu_item_id": 704,
        "report_id": 201,
    }

    # ---------------------------------- Act ----------------------------------- #
    config = get_template_config(config_dict=config_dict)
    # -------------------------------- Assert ---------------------------------- #
    assert config == exp_config
