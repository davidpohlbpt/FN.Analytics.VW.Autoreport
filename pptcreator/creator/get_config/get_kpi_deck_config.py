"""Builds the ``config_dict`` for a KPI deck (one brand, current vs. reference period).

Counterpart of ``graph_get_config`` for the legacy per-filter report: instead of the
legacy control tables and the Config Center, the data comes from a ``KpiSource`` and
the slide layout from ``build_output_slides``. The result goes straight into
``graph_create_ppt`` and ``send_email``.
"""

from __future__ import annotations

import dataclasses
import logging
import re

from pptcreator.config import settings
from pptcreator.creator.get_config.get_autoreport_config import TemplateConfig
from pptcreator.creator.get_config.get_template_config import get_template_config
from pptcreator.kpi.base import KpiDefinition, KpiResult, KpiSource, ReportPeriod
from pptcreator.kpi.build_output_slides import build_output_slides, discover_chart_slots
from pptcreator.models.enum import Languages
from pptcreator.utils.get_presentation import get_presentation


@dataclasses.dataclass
class ReportRequest:
    """One deck to render: the unit of work handed from the planner to the renderer."""

    brand: str
    current_period: ReportPeriod
    reference_period: ReportPeriod
    recipients: list[str]
    template_id: int | None = None
    kpi_ids: list[str] | None = None
    language: Languages | None = None
    target_file_name: str | None = None
    run_id: str | None = None
    trigger: str = "manual"
    recipient_ids: list[int] = dataclasses.field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        brand: str,
        current_period: str | ReportPeriod,
        reference_period: str | ReportPeriod,
        recipients: list[str] | None = None,
        template_id: int | None = None,
        kpi_ids: list[str] | None = None,
        language: str | Languages | None = None,
        target_file_name: str | None = None,
        run_id: str | None = None,
        trigger: str = "manual",
        recipient_ids: list[int] | None = None,
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
            recipients=[r for r in (recipients or []) if r],
            template_id=int(template_id) if template_id is not None else None,
            kpi_ids=list(kpi_ids) if kpi_ids else None,
            language=Languages(language) if language else None,
            target_file_name=target_file_name,
            run_id=run_id,
            trigger=trigger,
            recipient_ids=list(recipient_ids or []),
        )

    @classmethod
    def from_event(cls, event: dict) -> ReportRequest:
        """Parse the JSON passed between the Lambdas / Step Functions states."""
        return cls.create(
            brand=event["brand"],
            current_period=event["current_period"],
            reference_period=event["reference_period"],
            recipients=event.get("recipients"),
            template_id=event.get("template_id"),
            kpi_ids=event.get("kpi_ids"),
            language=event.get("language"),
            target_file_name=event.get("target_file_name"),
            run_id=event.get("run_id"),
            trigger=event.get("trigger") or "manual",
            recipient_ids=event.get("recipient_ids"),
        )

    def to_event(self) -> dict:
        return {
            "template_id": self.template_id,
            "brand": self.brand,
            "current_period": str(self.current_period),
            "reference_period": str(self.reference_period),
            "recipients": list(self.recipients),
            "recipient_ids": list(self.recipient_ids),
            "kpi_ids": self.kpi_ids,
            "language": self.language.value if self.language else None,
            "target_file_name": self.target_file_name,
            "run_id": self.run_id,
            "trigger": self.trigger,
        }

    @property
    def group_key(self) -> tuple[str, str, str]:
        return (self.brand, str(self.current_period), str(self.reference_period))

    @property
    def recipient_id(self) -> int | None:
        """Row of T_Control_Autoreport_Recipients that requested this deck."""
        return self.recipient_ids[0] if self.recipient_ids else None

    def default_file_name(self) -> str:
        return safe_file_name(
            f"VW_KPI_Report_{self.brand}_{self.current_period}_vs_{self.reference_period}"
        )


def safe_file_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")
    return cleaned or "report"


def select_kpis(template: TemplateConfig, kpi_ids: list[str] | None) -> list[KpiDefinition]:
    kpis = sorted(template.kpis, key=lambda k: k.order)
    if not kpi_ids:
        return kpis
    by_id = {k.id: k for k in kpis}
    unknown = [i for i in kpi_ids if i not in by_id]
    if unknown:
        raise ValueError(f"Unknown KPI ids {unknown}; template {template.id} has {list(by_id)}.")
    return [by_id[i] for i in kpi_ids]


def fetch_kpi_results(request: ReportRequest, source: KpiSource, kpis: list[KpiDefinition]) -> list[KpiResult]:
    results = []
    for definition in kpis:
        logging.info(
            f"Fetching {definition.id} ({definition.source}) for {request.brand} "
            f"({request.current_period} vs. {request.reference_period})"
        )
        results.append(source.fetch(definition, request.brand, request.current_period, request.reference_period))
    return results


def get_kpi_deck_config(
    request: ReportRequest,
    source: KpiSource,
    template: TemplateConfig,
    *,
    template_file: str,
    container: str,
    show_data_labels: bool | None = None,
) -> dict:
    """``template_file``/``container`` locate the .pptx inside pycore storage."""
    try:
        language = request.language or template.language
        target_file_name = request.target_file_name or template.render_file_name(
            request.brand, request.current_period, request.reference_period
        )

        config_dict: dict = {
            "file": template_file,
            "file_container": container,
            "target_file_name": target_file_name,
            "target_blob_container": container,
            "language": language,
            "recipients": request.recipients,
            "brand": request.brand,
            "current_period": str(request.current_period),
            "reference_period": str(request.reference_period),
            "template_id": template.id,
            "email_subject": template.render_subject(
                request.brand, request.current_period, request.reference_period
            ),
            "email_intro": (
                f"Anbei der KPI-Report für {request.brand} "
                f"({request.current_period} im Vergleich zu {request.reference_period}):"
            ),
        }

        logging.info(f"Reading template slots from {container}/{template_file}")
        template_slots = discover_chart_slots(get_presentation(config_dict))

        kpis = select_kpis(template, request.kpi_ids)
        results = fetch_kpi_results(request, source, kpis)
        config_dict["output_slides"] = build_output_slides(
            results,
            template_slots=template_slots,
            charts_per_detail_slide=template.commodity_charts_per_slide
            or settings.commodity_charts_per_slide,
            show_data_labels=show_data_labels,
        )

        logging.info("Reading template object positions and fonts")
        config_dict = get_template_config(config_dict)
        return config_dict

    except Exception as e:
        logging.exception(f"Error building KPI deck config for {request.brand}: {e}")
        raise ValueError(f"Error building KPI deck config for {request.brand}: {e}") from e
