import datetime

from pycore.schemas import ProcessState, TrackerLoadInformation

from pptcreator.creator.get_config.get_config_center_config import (
    get_config_center_config,
)
from pptcreator.models.enum import Languages, TextAlignments


def main() -> None:

    config_dict = {
        "charts": {
            "Chart 1": {
                "tile_id": 7011,
                "chart_id": 70110,
                "report_data_source_id": 704,
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
        "filter_column": "project_name",
        "language": Languages.DE,
        "recipients": ["prm.lead@example.com"],
        "menu_item_id": 704,
        "report_id": 704,
    }

    config_dict = get_config_center_config(config_dict)


if __name__ == "__main__":
    main()
