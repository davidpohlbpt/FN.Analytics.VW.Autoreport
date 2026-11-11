import os

import requests

from pptcreator.configs.endpoints import endpoint_urls
from pptcreator.models.enum import ChartObjects
from pptcreator.utils.get_session import get_session
from pptcreator.utils.send_request import send_request

BASE_REQUEST_URL = os.getenv("base_request_url")


def get_config_center_config(config_dict: dict):

    session = get_session()

    config_dict = get_tiles(session, config_dict)

    config_dict = get_filter(session, config_dict)

    config_dict = get_chart_type(session, config_dict)

    for template_object_name in config_dict["charts"]:

        config_dict = get_aesthetic(session, config_dict, template_object_name)

        config_dict = get_data(session, config_dict, template_object_name)

    return config_dict


def get_chart_type(session: requests.Session, config_dict: dict) -> dict:

    url = endpoint_urls.chart_type.format(REQUEST_URL=BASE_REQUEST_URL)

    payload = {"menuItemId": config_dict["menu_item_id"], "reportFilters": []}
    response = send_request(session, url, {}, "POST", payload)

    for response_tile in response["configuration"]["tiles"]:
        for template_object_name, vals in config_dict["charts"].items():
            if response_tile["tileID"] == vals["tile_id"]:
                config_dict["charts"][template_object_name]["chart_type"] = (
                    response_tile["genericCharts"][0]["chartType"]
                )

    return config_dict


def get_filter(session: requests.Session, config_dict: dict) -> dict:

    # Filter id
    menu_item_id = config_dict["menu_item_id"]
    url = endpoint_urls.filter_id.format(
        REQUEST_URL=BASE_REQUEST_URL, menu_item_id=menu_item_id
    )
    response = send_request(session, url, {})
    config_dict["filter_id"] = next(
        f["reportLinkFilterID"]
        for f in response["reportFilters"]
        if f["filterField"] == config_dict["filter_column"]
    )

    # Filter values
    report_id = config_dict["report_id"]
    filter_col = config_dict["filter_column"]
    url = endpoint_urls.filter_url.format(REQUEST_URL=BASE_REQUEST_URL)
    payload = {
        "reportId": report_id,
        "menuItemId": menu_item_id,
        "filterColumn": filter_col,
    }
    config_dict["filter"] = send_request(session, url, {}, "POST", payload)

    return config_dict


def get_tiles(session: requests.Session, config_dict: dict) -> dict:

    # Get Tile TK for Headline
    menu_item_id = config_dict["menu_item_id"]
    url = endpoint_urls.tile_url.format(
        REQUEST_URL=BASE_REQUEST_URL, menu_item_id=menu_item_id
    )
    headers = {"MenuItemId": str(menu_item_id)}
    response = send_request(session, url, headers)

    for tile in response:
        for template_object_name, vals in config_dict["charts"].items():
            if vals["tile_id"] == tile["TileID"]:

                config_dict["charts"][template_object_name]["report_data_source_id"] = (
                    tile["ReportDataSourceID"]
                )
                # Get value of TK
                config_dict = get_layout_tiles(
                    session,
                    config_dict,
                    template_object_name,
                    tile,
                )

    return config_dict


def get_layout_tiles(
    session: requests.Session,
    config_dict: dict,
    template_object_name: str,
    tile: dict,
) -> dict:

    menu_item_id = config_dict["menu_item_id"]
    tile_id = config_dict["charts"][template_object_name]["tile_id"]
    language = config_dict["language"]

    url = endpoint_urls.layout_tiles_url.format(
        REQUEST_URL=BASE_REQUEST_URL, tile_id=tile_id
    )
    headers = {"MenuItemId": str(menu_item_id)}
    response = send_request(session, url, headers)

    title_tk = tile["TitleTK"]
    headline = config_dict["charts"][template_object_name].get(
        ChartObjects.HEADLINE.value
    )
    if headline is not None:
        headline["translation"] = response["translations"][language][title_tk]

    return config_dict


def get_aesthetic(
    session: requests.Session, config_dict: dict, template_object_name: str
) -> dict:

    chart_id = config_dict["charts"][template_object_name]["chart_id"]
    menu_item_id = config_dict["menu_item_id"]
    url = endpoint_urls.chart_aesthetic_url.format(
        REQUEST_URL=BASE_REQUEST_URL, chart_id=chart_id
    )
    headers = {"MenuItemId": str(menu_item_id)}
    response = send_request(session, url, headers)
    chart_aesthetic_id = [
        item["AestheticID"] for item in response if item["Aesthetic"] == "fillColor"
    ][0]

    url = endpoint_urls.chart_aesthetic_option_url.format(
        REQUEST_URL=BASE_REQUEST_URL, chart_aesthetic_id=chart_aesthetic_id
    )
    headers = {"MenuItemId": str(menu_item_id)}
    response = send_request(session, url, headers)

    config_dict["charts"][template_object_name][ChartObjects.CHART.value][
        "fillColor"
    ] = {item["Option"]: item["Value"] for item in response}

    return config_dict


def get_data(
    session: requests.Session, config_dict: dict, template_object_name: str
) -> dict:

    url = endpoint_urls.data_url.format(REQUEST_URL=BASE_REQUEST_URL)

    report_id = config_dict["report_id"]
    chart_id = config_dict["charts"][template_object_name]["chart_id"]
    menu_item_id = config_dict["menu_item_id"]
    report_data_source_id = config_dict["charts"][template_object_name][
        "report_data_source_id"
    ]

    config_dict["charts"][template_object_name]["Chart"]["data"] = {}

    for filter_val in config_dict["filter"]:

        payload = {
            "reportId": report_id,
            "chartId": chart_id,
            "maskFilters": [{"id": config_dict["filter_id"], "values": [filter_val]}],
            "menuItemId": menu_item_id,
            "reportDataSourceId": report_data_source_id,
        }
        response = send_request(session, url, {}, "POST", payload)
        geometry_data = response["result"][0]["geometryData"]
        geometry_data.sort(key=lambda row: next(iter(row.values())))
        config_dict["charts"][template_object_name]["Chart"]["data"][
            filter_val
        ] = geometry_data

    return config_dict
