"""Builds the ``config_dict`` for a KPI deck (one brand, current vs. reference period).

Counterpart of ``graph_get_config`` for the legacy per-filter report: instead of the
control tables and the Config Center, the data comes from a ``KpiSource`` and the
slide layout from ``build_output_slides``. The result goes straight into
``graph_create_ppt`` and ``send_email``.
"""

from __future__ import annotations

import dataclasses
import logging
import re

from pptcreator.config import settings
from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSource, ReportPeriod
from pptcreator.kpi.build_output_slides import build_output_slides, discover_chart_slots
from pptcreator.kpi.registry import get_kpis
from pptcreator.models.enum import Languages
from pptcreator.utils.get_presentation import get_presentation


@dataclasses.dataclass
class ReportRequest:
    brand: str
    current_period: ReportPeriod
    reference_period: ReportPeriod
    recipients: list[str]
    kpi_ids: list[str] | None = None
    language: Languages = Languages.DE
    target_file_name: str | None = None

    @classmethod
    def create(
        cls,
        *,
        brand: str,
        current_period: str | ReportPeriod,
        reference_period: str | ReportPeriod,
        recipients: list[str],
        kpi_ids: list[str] | None = None,
        language: str | Languages | None = None,
        target_file_name: str | None = None,
    ) -> ReportRequest:
        brand = (brand or "").strip()
        if not brand:
            raise ValueError("brand must not be empty.")
        current = ReportPeriod.parse(current_period)
        reference = ReportPeriod.parse(reference_period)
        if current == reference:
            raise ValueError(f"current and reference period are identical ({current}).")
        return cls(
            brand=brand,
            current_period=current,
            reference_period=reference,
            recipients=list(recipients or []),
            kpi_ids=list(kpi_ids) if kpi_ids else None,
            language=Languages(language or settings.report_language),
            target_file_name=target_file_name,
        )

    @property
    def group_key(self) -> tuple[str, str, str]:
        return (self.brand, str(self.current_period), str(self.reference_period))

    def default_file_name(self) -> str:
        return safe_file_name(
            f"VW_KPI_Report_{self.brand}_{self.current_period}_vs_{self.reference_period}"
        )


def safe_file_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "report"


def fetch_kpi_results(
    request: ReportRequest, source: KpiSource, kpis: list[KpiDefinition] | None = None
) -> list[KpiResult]:
    kpis = kpis or get_kpis(request.kpi_ids)
    results = []
    for definition in kpis:
        logging.info(f"Fetching {definition.id} for {request.brand} ({request.current_period} vs. {request.reference_period})")
        results.append(
            source.fetch(definition, request.brand, request.current_period, request.reference_period)
        )
    return results


def get_kpi_deck_config(
    request: ReportRequest,
    source: KpiSource,
    *,
    template_file: str | None = None,
    container: str | None = None,
    show_data_labels: bool | None = None,
) -> dict:
    try:
        container = container or settings.storage_container
        template_file = template_file or settings.template_file_name
        target_file_name = request.target_file_name or request.default_file_name()

        config_dict: dict = {
            "file": template_file,
            "file_container": container,
            "target_file_name": target_file_name,
            "target_blob_container": container,
            "language": request.language,
            "recipients": request.recipients,
            "brand": request.brand,
            "current_period": str(request.current_period),
            "reference_period": str(request.reference_period),
            "email_subject": (
                f"VW KPI Report {request.brand}: {request.current_period} "
                f"vs. {request.reference_period}"
            ),
            "email_intro": (
                f"Anbei der KPI-Report für {request.brand} "
                f"({request.current_period} im Vergleich zu {request.reference_period}):"
            ),
        }

        logging.info(f"Reading template slots from {container}/{template_file}")
        template_slots = discover_chart_slots(get_presentation(config_dict))

        results = fetch_kpi_results(request, source)
        config_dict["output_slides"] = build_output_slides(
            results,
            template_slots=template_slots,
            charts_per_detail_slide=settings.commodity_charts_per_slide,
            show_data_labels=show_data_labels,
        )

        logging.info("Reading template object positions and fonts")
        config_dict = get_template_config(config_dict)
        return config_dict

    except Exception as e:
        logging.exception(f"Error building KPI deck config for {request.brand}: {e}")
        raise ValueError(f"Error building KPI deck config for {request.brand}: {e}") from e
