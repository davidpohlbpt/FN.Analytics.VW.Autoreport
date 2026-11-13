"""Reads the T_Control_Autoreport_* tables into typed configuration objects.

Counterpart of ``get_database_config`` (legacy control tables). Nothing here touches
S3, the DQN API or the template file; it only turns table rows into
``TemplateConfig`` / ``KpiDefinition`` / recipient groups so the rest of the pipeline
is independent of the storage layout of ReportDB.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
from urllib.parse import urlparse

import pandas as pd

from pptcreator.config import settings
from pptcreator.kpi.base import KpiDefinition, ReportPeriod
from pptcreator.models.enum import Languages
from pptcreator.models.models import (
    AutoreportBrands,
    AutoreportMappings,
    AutoreportRecipients,
    AutoreportTemplates,
)
from pptcreator.utils.read_data import read_data

VALID_SOURCES = ("leitstand", "frontend", "backend", "stub")
"""leitstand: Control Center chart config + T_RESULT_Leitstand_Overview (needs chart_id)."""


@dataclasses.dataclass(frozen=True)
class StorageLocation:
    """Either an S3 object/prefix or a pycore storage container + blob."""

    bucket: str | None
    key: str
    container: str | None = None

    @property
    def is_s3(self) -> bool:
        return self.bucket is not None

    @property
    def file_name(self) -> str:
        return self.key.rsplit("/", 1)[-1]

    def to_event(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_event(cls, event: dict) -> StorageLocation:
        return cls(bucket=event.get("bucket"), key=event["key"], container=event.get("container"))

    @classmethod
    def parse(cls, link: str, *, default_container: str) -> StorageLocation:
        link = (link or "").strip().replace("\\", "/")
        if not link:
            raise ValueError("Empty storage link.")
        if link.startswith("s3://"):
            parsed = urlparse(link)
            if not parsed.netloc or not parsed.path.strip("/"):
                raise ValueError(f"Invalid S3 link {link!r}; expected s3://bucket/key")
            return cls(bucket=parsed.netloc, key=parsed.path.lstrip("/"))
        container, _, blob = link.partition("/")
        if not blob:
            return cls(bucket=None, key=link, container=default_container)
        return cls(bucket=None, key=blob, container=container)


@dataclasses.dataclass
class TemplateConfig:
    id: int
    name: str
    template: StorageLocation
    language: Languages
    target_file_name: str
    target: StorageLocation | None
    commodity_charts_per_slide: int | None
    email_subject: str | None
    kpis: list[KpiDefinition]

    def render_file_name(self, brand: str, current: ReportPeriod, reference: ReportPeriod) -> str:
        from pptcreator.creator.get_config.get_kpi_deck_config import safe_file_name

        pattern = self.target_file_name or "VW_KPI_Report_{brand}_{current}_vs_{reference}"
        name = pattern.format(brand=brand, current=current, reference=reference)
        return safe_file_name(name.removesuffix(".pptx"))

    def render_subject(self, brand: str, current: ReportPeriod, reference: ReportPeriod) -> str:
        pattern = self.email_subject or "VW KPI Report {brand}: {current} vs. {reference}"
        return pattern.format(brand=brand, current=current, reference=reference)

    def to_event(self) -> dict:
        """JSON snapshot handed from the plan Lambda to the render Lambda."""
        return {
            "id": self.id,
            "name": self.name,
            "template": self.template.to_event(),
            "language": self.language.value,
            "target_file_name": self.target_file_name,
            "target": self.target.to_event() if self.target else None,
            "commodity_charts_per_slide": self.commodity_charts_per_slide,
            "email_subject": self.email_subject,
            "kpis": [dataclasses.asdict(kpi) for kpi in self.kpis],
        }

    @classmethod
    def from_event(cls, event: dict) -> TemplateConfig:
        kpis = [KpiDefinition(**kpi) for kpi in event["kpis"]]
        # The render Lambda's own override still applies to a planned snapshot
        if settings.kpi_source_override:
            kpis = [dataclasses.replace(k, source=settings.kpi_source_override) for k in kpis]
        return cls(
            id=int(event["id"]),
            name=event.get("name") or f"template {event['id']}",
            template=StorageLocation.from_event(event["template"]),
            language=Languages(event.get("language") or settings.report_language),
            target_file_name=event.get("target_file_name") or "",
            target=StorageLocation.from_event(event["target"]) if event.get("target") else None,
            commodity_charts_per_slide=event.get("commodity_charts_per_slide"),
            email_subject=event.get("email_subject"),
            kpis=kpis,
        )


# ------------------------------------------------------------------------------ #


def list_active_template_ids() -> list[int]:
    rows = read_data(AutoreportTemplates, ["is_active"], [True])
    if rows is None or rows.empty:
        return []
    return sorted(int(i) for i in rows["id"].unique())


# ------------------------------------------------------------------------------ #


def get_template_config(template_id: int | None = None) -> TemplateConfig:
    """Load one active template and its KPI mappings."""
    template_row = _load_template_row(template_id)
    template_id = int(template_row["id"])

    mappings = read_data(AutoreportMappings, ["template_id", "is_active"], [template_id, True])
    if mappings.empty:
        raise ValueError(f"Template {template_id} has no active KPI mappings.")

    kpis = [_mapping_to_kpi(row) for row in mappings.sort_values("kpi_order").to_dict("records")]
    keys = [k.id for k in kpis]
    if len(keys) != len(set(keys)):
        raise ValueError(f"Template {template_id}: duplicate kpi_key in mappings ({keys}).")

    target_link = _str_or_none(template_row.get("target_location"))
    config = TemplateConfig(
        id=template_id,
        name=str(template_row.get("name") or f"template {template_id}"),
        template=StorageLocation.parse(
            template_row["template_link"], default_container=settings.storage_container
        ),
        language=Languages(str(template_row.get("language") or settings.report_language)),
        target_file_name=str(template_row.get("target_file_name") or ""),
        target=(
            StorageLocation.parse(target_link, default_container=settings.storage_container)
            if target_link
            else None
        ),
        commodity_charts_per_slide=(
            int(v) if (v := _num_or(template_row.get("commodity_charts_per_slide"), None)) else None
        ),
        email_subject=_str_or_none(template_row.get("email_subject")),
        kpis=kpis,
    )
    logging.info(f"Template {config.id} '{config.name}': {len(kpis)} KPI(s), template at {config.template}")
    return config


def _load_template_row(template_id: int | None) -> dict:
    template_id = template_id or settings.default_template_id
    if template_id is not None:
        rows = read_data(AutoreportTemplates, ["id", "is_active"], [int(template_id), True])
        if rows.empty:
            raise ValueError(f"Template {template_id} not found or inactive.")
        return rows.iloc[0].to_dict()

    rows = read_data(AutoreportTemplates, ["is_active"], [True])
    if rows.empty:
        raise ValueError("No active template in T_Control_Autoreport_Templates.")
    if len(rows) > 1:
        raise ValueError(
            f"{len(rows)} active templates found; pass template_id or set default_template_id."
        )
    return rows.iloc[0].to_dict()


def _mapping_to_kpi(row: dict) -> KpiDefinition:
    source = str(row.get("source") or "stub").strip().lower()
    if settings.kpi_source_override:
        source = settings.kpi_source_override
    if source not in VALID_SOURCES:
        raise ValueError(f"Mapping {row.get('id')}: unknown source {source!r}; expected {VALID_SOURCES}.")

    palette = _parse_palette(row.get("palette_json"), row.get("id"))
    if source == "leitstand" and not _num_or(row.get("chart_id"), None):
        raise ValueError(f"Mapping {row.get('id')} ({row.get('kpi_key')}): leitstand source needs chart_id.")
    if source not in ("frontend", "leitstand") and not palette:
        raise ValueError(
            f"Mapping {row.get('id')} ({row.get('kpi_key')}): palette_json is required for source {source!r}."
        )
    if source == "frontend" and not all(
        _num_or(row.get(c), None) for c in ("menu_item_id", "report_id", "tile_id", "chart_id")
    ):
        raise ValueError(
            f"Mapping {row.get('id')} ({row.get('kpi_key')}): frontend source needs "
            "menu_item_id, report_id, tile_id and chart_id."
        )
    if source == "backend" and not _str_or_none(row.get("query_key")):
        raise ValueError(f"Mapping {row.get('id')} ({row.get('kpi_key')}): backend source needs query_key.")

    avg = _str_or_none(row.get("average_label"))
    return KpiDefinition(
        id=str(row["kpi_key"]).strip(),
        name=str(row.get("kpi_name") or row["kpi_key"]),
        title=str(row.get("slide_title") or row.get("kpi_name") or row["kpi_key"]),
        subtitle=str(row.get("slide_subtitle") or ""),
        palette=palette or {},
        average_label=avg,
        source=source,
        menu_item_id=_int_or_none(row.get("menu_item_id")),
        report_id=_int_or_none(row.get("report_id")),
        tile_id=_int_or_none(row.get("tile_id")),
        chart_id=_int_or_none(row.get("chart_id")),
        query_key=_str_or_none(row.get("query_key")),
        order=int(_num_or(row.get("kpi_order"), 0)),
    )


def _parse_palette(raw, mapping_id) -> dict[str, str]:
    raw = _str_or_none(raw)
    if not raw:
        return {}
    try:
        palette = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mapping {mapping_id}: palette_json is not valid JSON ({exc}).") from exc
    if not isinstance(palette, dict) or not all(isinstance(v, str) for v in palette.values()):
        raise ValueError(f"Mapping {mapping_id}: palette_json must be an object of category -> 'rgb(r, g, b)'.")
    return palette


# ------------------------------------------------------------------------------ #
# Recipients
# ------------------------------------------------------------------------------ #


@dataclasses.dataclass
class RecipientGroup:
    """One recipient row = one deck. ``emails`` holds the single row's address."""

    template_id: int
    brand: str
    """Brand filter value (EK_ORG), used for the data query, file name and headlines"""
    primary_date: str
    """Current snapshot as stored by the frontend, e.g. '2025-11-28'"""
    reference_date: str
    """Comparison snapshot as stored by the frontend"""
    emails: list[str]
    recipient_ids: list[int]

    @property
    def current_period(self) -> ReportPeriod:
        return ReportPeriod.parse(self.primary_date)

    @property
    def reference_period(self) -> ReportPeriod:
        return ReportPeriod.parse(self.reference_date)


RECIPIENT_COLUMNS = [
    "id", "template_id", "email", "brand_id", "primary_date", "reference_date", "send_now", "brand",
]


def read_recipients(template_id: int, *, only_send_now: bool = False) -> pd.DataFrame:
    """Recipient rows of a template joined with their active brand.

    Adds a ``brand`` column holding the brand's ``filter_value``. Rows whose brand is
    unknown or inactive are dropped with a warning. The table has no ``is_active``
    column any more; ``send_now`` is the only trigger.
    """
    columns, values = ["template_id"], [template_id]
    if only_send_now:
        columns.append("send_now")
        values.append(True)
    data = read_data(AutoreportRecipients, columns, values)
    if data is None or data.empty:
        return pd.DataFrame(columns=RECIPIENT_COLUMNS)

    brands = read_data(AutoreportBrands, ["is_active"], [True])
    if brands is None or brands.empty:
        logging.warning("No active brands in T_Control_Autoreport_Brands; all recipients skipped.")
        return pd.DataFrame(columns=RECIPIENT_COLUMNS)
    brand_by_id = {int(r["id"]): _str_or_none(r["filter_value"]) for r in brands.to_dict("records")}

    data = data.copy()
    data["brand"] = [brand_by_id.get(_int_or_none(b)) for b in data["brand_id"]]
    unknown = data[data["brand"].isna()]
    for row in unknown.to_dict("records"):
        logging.warning(f"Recipient {row.get('id')} skipped: brand_id {row.get('brand_id')} unknown or inactive.")
    return data[data["brand"].notna()]


def period_of(row: dict, column: str) -> ReportPeriod:
    """Snapshot date of a recipient row -> ReportPeriod. Mandatory, not validated.

    The frontend guarantees the values exist in the data; the KPI source resolves them
    (and reports a clear error if a snapshot is missing).
    """
    value = _str_or_none(row.get(column))
    if not value:
        raise ValueError(f"{column} is mandatory.")
    return ReportPeriod.parse(value)


def reference_period_of(row: dict) -> ReportPeriod:
    """Backwards compatible name for the comparison date of a recipient row."""
    return period_of(row, "reference_date")


def group_recipients(recipients: pd.DataFrame, template_id: int) -> list[RecipientGroup]:
    """One group (= one deck) per recipient row; rows with bad data are skipped.

    Deliberately no merging: two rows with the same brand and dates still produce two
    decks, so each user's row keeps its own history and file name.
    """
    groups: list[RecipientGroup] = []
    for row in recipients.to_dict("records"):
        email = _str_or_none(row.get("email"))
        brand = _str_or_none(row.get("brand"))
        if not email or not brand:
            logging.warning(f"Recipient {row.get('id')} skipped: missing email or brand.")
            continue
        try:
            primary = period_of(row, "primary_date")
            reference = period_of(row, "reference_date")
        except ValueError as exc:
            logging.warning(f"Recipient {row.get('id')} skipped: {exc}")
            continue
        if primary == reference:
            logging.warning(f"Recipient {row.get('id')} skipped: primary_date and reference_date are identical ({primary}).")
            continue
        groups.append(
            RecipientGroup(
                template_id=template_id,
                brand=brand,
                primary_date=str(primary),
                reference_date=str(reference),
                emails=[email],
                recipient_ids=[int(row["id"])],
            )
        )
    return groups


# ------------------------------------------------------------------------------ #


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _num_or(value, default):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _int_or_none(value) -> int | None:
    value = _num_or(value, None)
    return int(value) if value is not None else None
