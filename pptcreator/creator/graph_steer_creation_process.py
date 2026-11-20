"""Orchestration of the report creation.

The render Lambda uses ``render_deck``; detecting requests and sending e-mails are the
separate ZIP functions ``vw-autoreport-detect`` and ``vw-autoreport-sendemail``.

* ``render_deck``    ReportRequest -> deck in S3 (the core of the system)
* ``run_deck`` / ``steer_send_now_decks``  local runs (render only, no e-mail)
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import uuid

from pptcreator.config import settings
from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.get_autoreport_config import (
    RecipientGroup,
    StorageLocation,
    TemplateConfig,
    get_template_config,
    group_recipients,
    read_recipients,
)
from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest, get_kpi_deck_config
from pptcreator.infra import s3_sync
from pptcreator.kpi.base import KpiSource
from pptcreator.kpi.router import RoutingKpiSource

# ------------------------------------------------------------------------------ #
# Shared result types
# ------------------------------------------------------------------------------ #


@dataclasses.dataclass
class RenderResult:
    """Result of ``render_deck``. The render Lambda turns it into the event read by
    functions/vw-autoreport-sendemail/lambda_function.py; keep both sides in sync."""

    status: str  # "rendered" | "failed"
    request: dict
    file_name: str | None = None
    bucket: str | None = None
    s3_key: str | None = None
    container: str | None = None
    slides: int | None = None
    size_bytes: int | None = None
    email_subject: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# ------------------------------------------------------------------------------ #
# Local runs: recipient rows with send_now = 1
# ------------------------------------------------------------------------------ #


def plan_decks(
    *,
    template_id: int | None = None,
    run_id: str | None = None,
    template: TemplateConfig | None = None,
) -> list[ReportRequest]:
    """One ReportRequest per recipient row with ``send_now = 1`` (local adhoc runs).

    In AWS, vw-autoreport-detect finds these rows instead.
    """
    template = template or get_template_config(template_id)
    run_id = run_id or str(uuid.uuid4())

    recipients = read_recipients(template.id)
    groups = group_recipients(recipients, template.id)
    logging.info(f"{len(recipients)} recipient row(s) with send_now -> {len(groups)} deck(s) for template {template.id}")

    requests: list[ReportRequest] = []
    for group in groups:
        try:
            requests.append(
                ReportRequest.create(
                    brand=group.brand,
                    current_period=group.current_period,
                    reference_period=group.reference_period,
                    recipients=group.emails,
                    template_id=template.id,
                    run_id=run_id,
                    trigger="adhoc",
                    recipient_ids=group.recipient_ids,
                )
            )
        except ValueError as exc:
            logging.warning(f"Recipient {group.recipient_ids} skipped: {exc}")
    return requests


# ------------------------------------------------------------------------------ #
# Render Lambda
# ------------------------------------------------------------------------------ #


def render_deck(
    request: ReportRequest,
    source: KpiSource | None = None,
    template: TemplateConfig | None = None,
) -> RenderResult:
    """Render one deck and store it. Never raises; failures are reported in the result."""
    result = RenderResult(status="failed", request=request.to_event())
    try:
        template = template or get_template_config(request.template_id)
        source = source or RoutingKpiSource()
        container = settings.storage_container
        logging.info(
            f"Render: template {template.id}, {request.brand} "
            f"{request.current_period} vs. {request.reference_period}"
        )

        # 1. Template into pycore storage
        template_file = _fetch_template(template.template, container)

        # 2. Data + layout + template positions
        config_dict = get_kpi_deck_config(
            request, source, template, template_file=template_file, container=container
        )
        file_name = f"{config_dict['target_file_name']}.pptx"

        # 3. Render
        config_dict = graph_create_ppt(config_dict)
        logging.info(f"Rendered {file_name}")

        # 4. Persist
        if settings.s3_output_bucket:
            bucket, key_prefix = settings.s3_output_bucket, None  # None -> s3_output_prefix
        elif template.target and template.target.is_s3:
            bucket, key_prefix = template.target.bucket, template.target.key
        else:
            bucket, key_prefix = None, None
        s3_key = s3_sync.upload_output(container, file_name, key_prefix=key_prefix, bucket=bucket)

        from pycore.easy import storage

        size = len(storage.read_blob(container_name=container, blob_name=file_name, decode=False))

        result.status = "rendered"
        result.file_name = file_name
        result.container = container
        result.bucket = (bucket or settings.s3_bucket) if s3_key else None
        result.s3_key = s3_key
        result.slides = len(config_dict.get("output_slides", []))
        result.size_bytes = size
        result.email_subject = config_dict.get("email_subject")

    except Exception as exc:
        logging.exception(f"Render for {request.brand} failed: {exc}")
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def _fetch_template(location: StorageLocation, container: str) -> str:
    if location.is_s3:
        return s3_sync.download_template(
            container, location.file_name, bucket=location.bucket, key=location.key,
            force=settings.s3_enabled,
        )
    # Non-S3 link: the file is expected in pycore storage already (local runs)
    source_container = location.container or container
    if source_container != container:
        from pycore.easy import storage

        s3_sync.ensure_container(container)
        if not s3_sync.blob_exists(container, location.file_name):
            data = storage.read_blob(container_name=source_container, blob_name=location.key, decode=False)
            storage.write_blob(container_name=container, blob_name=location.file_name, blob_data=data)
        return location.file_name
    return s3_sync.download_template(container, location.key)


# ------------------------------------------------------------------------------ #
# All-in-one (local runs)
# ------------------------------------------------------------------------------ #


@dataclasses.dataclass
class DeckOutcome:
    brand: str
    current_period: str
    reference_period: str
    recipients: list[str]
    status: str  # "rendered" | "failed"
    file_name: str | None = None
    s3_key: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def run_deck(
    request: ReportRequest,
    source: KpiSource | None = None,
    template: TemplateConfig | None = None,
) -> DeckOutcome:
    render = render_deck(request, source, template)
    return DeckOutcome(
        brand=request.brand,
        current_period=str(request.current_period),
        reference_period=str(request.reference_period),
        recipients=list(request.recipients),
        status=render.status,
        file_name=render.file_name,
        s3_key=render.s3_key,
        error=render.error,
    )


def steer_kpi_deck_process(request: ReportRequest, source: KpiSource | None = None) -> DeckOutcome:
    """Backwards compatible name for ``run_deck``."""
    return run_deck(request, source)


def steer_send_now_decks(
    source: KpiSource | None = None, *, template_id: int | None = None
) -> list[DeckOutcome]:
    """Local all-in-one run: render every deck with ``send_now = 1``."""
    requests = plan_decks(template_id=template_id)
    if not requests:
        return []
    template = get_template_config(requests[0].template_id)
    return [run_deck(request, source, template) for request in requests]


# ------------------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------------------ #


def current_calendar_week(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-KW{week:02d}"


__all__ = [
    "DeckOutcome",
    "RecipientGroup",
    "RenderResult",
    "current_calendar_week",
    "plan_decks",
    "render_deck",
    "run_deck",
    "steer_kpi_deck_process",
    "steer_send_now_decks",
]
