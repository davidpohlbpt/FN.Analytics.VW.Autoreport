import pytest

from pptcreator.creator.get_config import get_config_center_config as cc_module
from pptcreator.creator.get_config.graph_get_config import graph_get_config
from pptcreator.models.enum import Languages, TextAlignments
from pptcreator.models.models import Mappings, Recipients, Templates


@pytest.fixture
def tiles_response():
    return [
        {
            "TileName": "SC_StatusChart",
            "TitleTK": "TK_SC_StatusChart",
            "TileID": 7011,
            "ReportDataSourceID": 704,
        },
        {
            "TileName": "SCO_EDIConnectionChart",
            "TitleTK": "TK_SCO_EDIConnectionChart",
            "TileID": 7014,
            "ReportDataSourceID": 704,
        },
    ]


@pytest.fixture
def tile_7011_response():
    return {
        "translations": {
            "DE": {
                "TK_SC_StatusChart": "Supplier Readiness",
                "TK_Helpertitle_SC_StatusChart": "Lieferanten",
                "TK_HelpertitleUnit_SC_StatusChart": "Anzahl",
            },
            "EN": {
                "TK_SC_StatusChart": "Supplier Readiness",
                "TK_Helpertitle_SC_StatusChart": "Suppliers",
                "TK_HelpertitleUnit_SC_StatusChart": "Count",
            },
        },
    }


@pytest.fixture
def tile_7014_response():
    return {
        "translations": {
            "DE": {
                "TK_Helpertitle_SCO_EDIConnectionChart": "Lieferanten",
                "TK_HelpertitleUnit_SCO_EDIConnectionChart": "Anzahl",
                "TK_SCO_EDIConnectionChart": "EDI Connection",
            },
            "EN": {
                "TK_Helpertitle_SCO_EDIConnectionChart": "Suppliers",
                "TK_HelpertitleUnit_SCO_EDIConnectionChart": "Count",
                "TK_SCO_EDIConnectionChart": "EDI Connection",
            },
        },
    }


@pytest.fixture
def chart_70110_aesthetic_response():
    return [
        {
            "Aesthetic": "label",
            "DimID": 701100,
            "GeomID": 7011000,
            "AestheticID": 7011000,
        },
        {
            "Aesthetic": "value",
            "DimID": 701101,
            "GeomID": 7011000,
            "AestheticID": 7011001,
        },
        {
            "Aesthetic": "fillColor",
            "DimID": 701100,
            "GeomID": 7011000,
            "AestheticID": 7011002,
        },
    ]


@pytest.fixture
def chart_aesthetic_7011002_response():
    return [
        {
            "Option": "Evaluation ongoing",
            "Value": "rgb(217, 217, 217)",
            "Language": None,
            "AestheticOptionID": 70110001,
        },
        {
            "Option": "12-month forecast confirmed",
            "Value": "rgb(255, 255, 0)",
            "Language": None,
            "AestheticOptionID": 70110002,
        },
        {
            "Option": "Not relevant",
            "Value": "rgb(127, 127, 127)",
            "Language": None,
            "AestheticOptionID": 70110003,
        },
        {
            "Option": "12-month forecast not confirmed",
            "Value": "rgb(255, 0, 0)",
            "Language": None,
            "AestheticOptionID": 70110004,
        },
        {
            "Option": "Supply readiness\xa0confirmed",
            "Value": "rgb(146, 208, 80)",
            "Language": None,
            "AestheticOptionID": 70110005,
        },
        {
            "Option": "values.innerLabel.color",
            "Value": "rgba(0, 0, 0, 1)",
            "Language": None,
            "AestheticOptionID": 70110006,
        },
        {
            "Option": "Not relevant",
            "Value": "rgb(127, 127, 127)",
            "Language": None,
            "AestheticOptionID": 70110007,
        },
    ]


@pytest.fixture
def chart_70140_aesthetic_response():
    return [
        {
            "Aesthetic": "label",
            "DimID": 701400,
            "GeomID": 7014000,
            "AestheticID": 7014000,
        },
        {
            "Aesthetic": "value",
            "DimID": 701401,
            "GeomID": 7014000,
            "AestheticID": 7014001,
        },
        {
            "Aesthetic": "fillColor",
            "DimID": 701400,
            "GeomID": 7014000,
            "AestheticID": 7014002,
        },
    ]


@pytest.fixture
def chart_aesthetic_7014002_response():
    return [
        {
            "Option": "No",
            "Value": "rgba(233, 89, 73, 1)",
            "Language": None,
            "AestheticOptionID": 40430662,
        },
        {
            "Option": "Yes",
            "Value": "rgba(85, 204, 62, 1)",
            "Language": None,
            "AestheticOptionID": 40430663,
        },
        {
            "Option": " ",
            "Value": "rgba(237, 237, 237, 1)",
            "Language": None,
            "AestheticOptionID": 40430664,
        },
        {
            "Option": "Not relevant",
            "Value": "rgb(127, 127, 127)",
            "Language": None,
            "AestheticOptionID": 70120007,
        },
        {
            "Option": "Done",
            "Value": "rgb(146, 208, 80)",
            "Language": None,
            "AestheticOptionID": 70140001,
        },
        {
            "Option": "Open",
            "Value": "rgb(255, 0, 0)",
            "Language": None,
            "AestheticOptionID": 70140002,
        },
        {
            "Option": "values.innerLabel.color",
            "Value": "rgba(0, 0, 0, 1)",
            "Language": None,
            "AestheticOptionID": 70140006,
        },
    ]


@pytest.fixture
def filter_response():
    return ["P102718", "P102719", "P103165"]


@pytest.fixture
def filter_id_response():
    return {
        "reportId": 704,
        "hasMask": True,
        "isLazyLoaded": True,
        "allowUnfilteredAccess": False,
        "reportFilters": [
            {
                "reportLinkFilterID": 7040,
                "reportLinkID": 704,
                "filterType": "IN",
                "filterField": "project_number",
                "defaultValue": None,
                "allowMultipleValues": False,
            },
            {
                "reportLinkFilterID": 7041,
                "reportLinkID": 704,
                "filterType": "IN",
                "filterField": "project_name",
                "defaultValue": None,
                "allowMultipleValues": False,
            },
        ],
        "columns": [],
    }


@pytest.fixture
def chart_type_response():
    return {
        "configuration": {
            "tiles": [
                {"tileID": 7011, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7012, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7013, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7014, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7015, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7016, "genericCharts": [{"chartType": "doughnut"}]},
                {"tileID": 7017, "genericCharts": [{"chartType": "doughnut"}]},
            ]
        }
    }


@pytest.fixture
def data_responses():
    return {
        (70110, "P102718"): {
            "result": [
                {
                    "geometryData": [
                        {
                            "supplier_status_long": "Evaluation ongoing",
                            "count_supplier": 68.0,
                        }
                    ]
                }
            ]
        },
        (70110, "P102719"): {
            "result": [
                {
                    "geometryData": [
                        {
                            "supplier_status_long": "Evaluation ongoing",
                            "count_supplier": 116.0,
                        }
                    ]
                }
            ]
        },
        (70110, "P103165"): {
            "result": [
                {
                    "geometryData": [
                        {
                            "supplier_status_long": "Evaluation ongoing",
                            "count_supplier": 17.0,
                        }
                    ]
                }
            ]
        },
        (70140, "P102718"): {
            "result": [
                {
                    "geometryData": [
                        {"supplier_status_long": "Done", "count_supplier": 10.0},
                        {"supplier_status_long": "Open", "count_supplier": 25.0},
                    ]
                }
            ]
        },
        (70140, "P102719"): {
            "result": [
                {
                    "geometryData": [
                        {"supplier_status_long": "Open", "count_supplier": 5.0}
                    ]
                }
            ]
        },
        (70140, "P103165"): {
            "result": [
                {
                    "geometryData": [
                        {"supplier_status_long": "Done", "count_supplier": 20.0}
                    ]
                }
            ]
        },
    }


@pytest.fixture
def expected_config(filter_response):
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
                    "has_legend": True,
                    "has_data_labels": True,
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
                    "has_legend": True,
                    "has_data_labels": True,
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
                            {"supplier_status_long": "Open", "count_supplier": 25.0},
                        ],
                        "P102719": [
                            {"supplier_status_long": "Open", "count_supplier": 5.0}
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
        "filter": filter_response,
        "filter_id": 7041,
    }


def test_graph_get_config(
    mocker,
    storage,
    cont,
    data_repo,
    templates_data,
    mappings_data,
    recipients_data,
    tiles_response,
    tile_7011_response,
    tile_7014_response,
    chart_70110_aesthetic_response,
    chart_aesthetic_7011002_response,
    chart_70140_aesthetic_response,
    chart_aesthetic_7014002_response,
    filter_response,
    filter_id_response,
    chart_type_response,
    data_responses,
    expected_config,
):

    # -------------------------------- Arrange --------------------------------- #
    test_file_1 = "Test_PPT.pptx"

    with open(f"./tests/unit/test_data/{test_file_1}", "rb") as f:
        file_data = f.read()

    storage.write_blob(
        container_name=cont,
        blob_name=test_file_1,
        blob_data=file_data,
    )

    data_repo.database.create_all_tables()
    data_repo.write_table(model=Templates, df=templates_data)
    data_repo.write_table(model=Mappings, df=mappings_data)
    data_repo.write_table(model=Recipients, df=recipients_data)

    mocker.patch.object(cc_module, "BASE_REQUEST_URL", "dev.url")
    mocker.patch(
        "pptcreator.creator.get_config.get_config_center_config.get_session",
        return_value=mocker.Mock(),
    )

    url_map = {
        "https://dev.url/apigw/api/v1/Objects/GenericReport/704/related?targets=LayoutTiles&hierarchyName=GenericReport": tiles_response,
        "https://dev.url/apigw/api/v1/Objects/LayoutTiles/7011?hierarchyName=GenericReport": tile_7011_response,
        "https://dev.url/apigw/api/v1/Objects/LayoutTiles/7014?hierarchyName=GenericReport": tile_7014_response,
        "https://dev.url/apigw/api/v1/Objects/Chart/70110/related?targets=ChartAesthetic&hierarchyName=GenericReport": chart_70110_aesthetic_response,
        "https://dev.url/apigw/api/v1/Objects/ChartAesthetic/7011002/related?targets=ChartAestheticOption&hierarchyName=GenericReport": chart_aesthetic_7011002_response,
        "https://dev.url/apigw/api/v1/Objects/Chart/70140/related?targets=ChartAesthetic&hierarchyName=GenericReport": chart_70140_aesthetic_response,
        "https://dev.url/apigw/api/v1/Objects/ChartAesthetic/7014002/related?targets=ChartAestheticOption&hierarchyName=GenericReport": chart_aesthetic_7014002_response,
        "https://dev.url/apigw/api/v1/GenericReport/mask?menuItemId=704": filter_id_response,
    }
    filter_url = "https://dev.url/apigw/api/v1/ReportMetadata/filter"
    data_url = "https://dev.url/apigw/api/v1/ReportContent/chart/"
    chart_type_url = "https://dev.url/apigw/api/v1/GenericReport"

    def mock_send_request(session, url, headers, method="GET", json=None):
        if url == filter_url:
            return filter_response
        if url == chart_type_url:
            return chart_type_response
        if url == data_url:
            chart_id = json["chartId"]
            filter_val = json["maskFilters"][0]["values"][0]
            return data_responses[(chart_id, filter_val)]
        return url_map[url]

    mocker.patch(
        "pptcreator.creator.get_config.get_config_center_config.send_request",
        side_effect=mock_send_request,
    )

    # ---------------------------------- Act ----------------------------------- #
    config = graph_get_config(template_id=1)

    # -------------------------------- Assert ---------------------------------- #
    assert config == expected_config
