from pydantic_settings import BaseSettings


class Endpoints(BaseSettings):

    tile_url: str = (
        "https://{REQUEST_URL}/apigw/api/v1/Objects/GenericReport/{menu_item_id}/related?targets=LayoutTiles&hierarchyName=GenericReport"
    )

    layout_tiles_url: str = (
        "https://{REQUEST_URL}/apigw/api/v1/Objects/LayoutTiles/{tile_id}?hierarchyName=GenericReport"
    )

    chart_aesthetic_url: str = (
        "https://{REQUEST_URL}/apigw/api/v1/Objects/Chart/{chart_id}/related?targets=ChartAesthetic&hierarchyName=GenericReport"
    )

    chart_aesthetic_option_url: str = (
        "https://{REQUEST_URL}/apigw/api/v1/Objects/ChartAesthetic/{chart_aesthetic_id}/related?targets=ChartAestheticOption&hierarchyName=GenericReport"
    )

    filter_url: str = "https://{REQUEST_URL}/apigw/api/v1/ReportMetadata/filter"

    data_url: str = "https://{REQUEST_URL}/apigw/api/v1/ReportContent/chart/"

    chart_type: str = "https://{REQUEST_URL}/apigw/api/v1/GenericReport"

    filter_id: str = (
        "https://{REQUEST_URL}/apigw/api/v1/GenericReport/mask?menuItemId={menu_item_id}"
    )


endpoint_urls = Endpoints()
