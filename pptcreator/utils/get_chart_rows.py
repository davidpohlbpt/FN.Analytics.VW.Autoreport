from pptcreator.models.enum import ChartObjects


def get_chart_rows(object_config: dict, slide_filter: str | None) -> list[dict]:
    chart_config = object_config[ChartObjects.CHART.value]
    # Multi-slide decks carry one row set per chart instead of one per filter value
    if slide_filter is None:
        return chart_config["rows"]
    return chart_config["data"][slide_filter]
