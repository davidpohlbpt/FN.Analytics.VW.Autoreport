"""KPI data from the DQN frontend chart API (``source = 'frontend'``).

Uses the same endpoints and payloads as the legacy ``get_config_center_config``:
the chart's ``ReportDataSourceID`` from the tile list, the fill colours from the
chart aesthetics, and ``ReportContent/chart`` with mask filters for the data rows.

Assumptions that must be confirmed against the DQN report of each KPI (see
``FrontendFilterNames``): the names of the mask filter fields for brand, commodity
and period, and that the chart returns ``geometryData`` rows of
``{category_column: ..., value_column: ...}``.
"""

from __future__ import annotations

import dataclasses
import logging
import os

import requests

from pptcreator.configs.endpoints import endpoint_urls
from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSnapshot, ReportPeriod, Rows
from pptcreator.utils.get_session import get_session
from pptcreator.utils.send_request import send_request


@dataclasses.dataclass(frozen=True)
class FrontendFilterNames:
    """``filterField`` names of the report mask; overridable via env for each deployment."""

    brand: str = os.getenv("DQN_FILTER_BRAND", "brand")
    commodity: str = os.getenv("DQN_FILTER_COMMODITY", "commodity")
    period: str = os.getenv("DQN_FILTER_PERIOD", "calendar_week")


class FrontendKpiSource:

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str | None = None,
        filter_names: FrontendFilterNames | None = None,
        language: str = "DE",
    ):
        self._session = session
        self.base_url = base_url or os.getenv("base_request_url")
        self.filters = filter_names or FrontendFilterNames()
        self.language = language

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = get_session()
        return self._session

    # -------------------------------------------------------------------------- #

    def fetch(
        self,
        definition: KpiDefinition,
        brand: str,
        current: ReportPeriod,
        reference: ReportPeriod,
    ) -> KpiResult:
        self._require_ids(definition)
        headers = {"MenuItemId": str(definition.menu_item_id)}

        data_source_id = self._report_data_source_id(definition, headers)
        filter_ids = self._mask_filter_ids(definition)
        palette = definition.palette or self._fill_colors(definition, headers)
        commodities = self._commodities(definition, headers)

        # The palette must be known before rows are validated; frontend colours win
        # only when the mapping row has none configured.
        resolved = dataclasses.replace(definition, palette=palette)

        result = KpiResult(
            definition=resolved,
            brand=brand,
            current=self._snapshot(resolved, brand, current, data_source_id, filter_ids, commodities),
            reference=self._snapshot(resolved, brand, reference, data_source_id, filter_ids, commodities),
        )
        result.validate()
        return result

    # -------------------------------------------------------------------------- #

    def _snapshot(self, definition, brand, period, data_source_id, filter_ids, commodities) -> KpiSnapshot:
        total = self._rows(definition, data_source_id, filter_ids, brand=brand, period=period)
        by_commodity = {
            com: self._rows(definition, data_source_id, filter_ids, brand=brand, period=period, commodity=com)
            for com in commodities
        }
        by_commodity = {com: rows for com, rows in by_commodity.items() if rows}
        return KpiSnapshot(period=period, total_rows=total, commodity_rows=by_commodity)

    def _rows(self, definition, data_source_id, filter_ids, *, brand, period, commodity=None) -> Rows:
        mask = [
            {"id": filter_ids[self.filters.brand], "values": [brand]},
            {"id": filter_ids[self.filters.period], "values": [str(period)]},
        ]
        if commodity is not None:
            mask.append({"id": filter_ids[self.filters.commodity], "values": [commodity]})
        payload = {
            "reportId": definition.report_id,
            "chartId": definition.chart_id,
            "maskFilters": mask,
            "menuItemId": definition.menu_item_id,
            "reportDataSourceId": data_source_id,
        }
        url = endpoint_urls.data_url.format(REQUEST_URL=self.base_url)
        response = send_request(self.session, url, {}, "POST", payload)
        results = response.get("result") or []
        geometry = results[0].get("geometryData", []) if results else []
        rows = []
        for row in geometry:
            category, value = list(row.values())[:2]
            rows.append({"category": category, "value": float(value or 0)})
        rows.sort(key=lambda r: definition.categories.index(r["category"]) if r["category"] in definition.categories else 999)
        return rows

    def _report_data_source_id(self, definition, headers) -> int:
        url = endpoint_urls.tile_url.format(REQUEST_URL=self.base_url, menu_item_id=definition.menu_item_id)
        for tile in send_request(self.session, url, headers):
            if tile.get("TileID") == definition.tile_id:
                return tile["ReportDataSourceID"]
        raise ValueError(f"{definition.id}: tile {definition.tile_id} not found in menu item {definition.menu_item_id}.")

    def _mask_filter_ids(self, definition) -> dict[str, int]:
        url = endpoint_urls.filter_id.format(REQUEST_URL=self.base_url, menu_item_id=definition.menu_item_id)
        response = send_request(self.session, url, {})
        ids = {f["filterField"]: f["reportLinkFilterID"] for f in response.get("reportFilters", [])}
        missing = [n for n in (self.filters.brand, self.filters.period, self.filters.commodity) if n not in ids]
        if missing:
            raise ValueError(
                f"{definition.id}: report mask has no filters {missing}; available: {sorted(ids)}. "
                "Set DQN_FILTER_BRAND / DQN_FILTER_PERIOD / DQN_FILTER_COMMODITY."
            )
        return ids

    def _fill_colors(self, definition, headers) -> dict[str, str]:
        url = endpoint_urls.chart_aesthetic_url.format(REQUEST_URL=self.base_url, chart_id=definition.chart_id)
        aesthetics = send_request(self.session, url, headers)
        fill_ids = [a["AestheticID"] for a in aesthetics if a.get("Aesthetic") == "fillColor"]
        if not fill_ids:
            raise ValueError(f"{definition.id}: chart {definition.chart_id} has no fillColor aesthetic.")
        url = endpoint_urls.chart_aesthetic_option_url.format(REQUEST_URL=self.base_url, chart_aesthetic_id=fill_ids[0])
        options = send_request(self.session, url, headers)
        return {item["Option"]: item["Value"] for item in options}

    def _commodities(self, definition, headers) -> list[str]:
        url = endpoint_urls.filter_url.format(REQUEST_URL=self.base_url)
        payload = {
            "reportId": definition.report_id,
            "menuItemId": definition.menu_item_id,
            "filterColumn": self.filters.commodity,
        }
        values = send_request(self.session, url, {}, "POST", payload) or []
        commodities = [str(v) for v in values if v not in (None, "")]
        logging.info(f"{definition.id}: {len(commodities)} commodities from the frontend filter.")
        return commodities

    @staticmethod
    def _require_ids(definition: KpiDefinition) -> None:
        missing = [n for n in ("menu_item_id", "report_id", "tile_id", "chart_id") if getattr(definition, n) is None]
        if missing:
            raise ValueError(f"{definition.id}: frontend source needs {missing}.")
