"""Orchestration of the report creation.

Three processes live here, one per Lambda of the state machine, plus the legacy
per-template report:

* ``plan_decks``     (Lambda 1) recipients table -> list of ReportRequest
* ``render_deck``    (Lambda 2) ReportRequest -> deck in S3 (the core of the system)
* ``send_deck``      (Lambda 3) deck in S3 -> e-mail via SES
* ``run_deck``       all three in one process, for local runs and the single-Lambda mode
* ``graph_steer_creation_process`` -- legacy per-template report (control tables +
  DQN Config Center, one slide per filter value)
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging
import uuid

from pycore.schemas import TrackerLoadInformation

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
from pptcreator.creator.get_config.graph_get_config import graph_get_config
from pptcreator.creator.send_email.send_email import send_email
from pptcreator.infra import mailer, s3_sync
from pptcreator.kpi.base import KpiSource, ReportPeriod
from pptcreator.kpi.router import RoutingKpiSource
from pptcreator.models.models import Templates
from pptcreator.utils.read_data import read_data

# ------------------------------------------------------------------------------ #
# Legacy process (per template, Config Center data)
# ------------------------------------------------------------------------------ #


def graph_steer_creation_process(load_info: TrackerLoadInformation):

    template_ids = _get_template_ids()
    logging.info(f"Found template ids: {template_ids} for load_info: {load_info}")

    if template_ids is None:
        return

    logging.info(
        f"Starting graph steer creation process for template_id: {template_ids} and load_info: {load_info}"
    )
    for template_id in template_ids:
        logging.info(
            f"Processing template_id: {template_id} and load_info: {load_info}"
        )

        # Extract_config
        config_dict = graph_get_config(template_id)
        logging.info(
            f"Extracted config for template_id: {template_id} and load_info: {load_info}"
        )

        # Create slides
        config_dict = graph_create_ppt(config_dict)
        logging.info(
            f"Created slides for template_id: {template_id} and load_info: {load_info}"
        )

        # Send email
        send_email(config_dict)
        logging.info(
            f"Sent email for template_id: {template_id} and load_info: {load_info}"
        )


def _get_template_ids():
    data = read_data(Templates, ["is_active"], [True])
    try:
        template_ids = data["id"].unique()
    except Exception as exc:
        logging.exception(f"Error getting duplicate template ids {list(data['id'])}")
        raise RuntimeError(
            f"Error getting duplicate template ids for {list(data['id'])}"
        ) from exc

    return template_ids


# ------------------------------------------------------------------------------ #
# Shared result types
# ------------------------------------------------------------------------------ #


@dataclasses.dataclass
class RenderResult:
    """Output of Lambda 2; everything Lambda 3 needs is in here (no DB access needed)."""

    status: str  # "rendered" | "failed"
    request: dict
    file_name: str | None = None
    bucket: str | None = None
    s3_key: str | None = None
    container: str | None = None
    slides: int | None = None
    size_bytes: int | None = None
    email_subject: str | None = None
    email_intro: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class SendResult:
    status: str  # "sent" | "skipped" | "failed"
    request: dict
    message_id: str | None = None
    recipients: list[str] = dataclasses.field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


# ------------------------------------------------------------------------------ #
# Lambda 1: plan
# ------------------------------------------------------------------------------ #


def plan_decks(
    *,
    trigger: str,
    template_id: int | None = None,
    current_period: str | ReportPeriod | None = None,
    run_id: str | None = None,
) -> list[ReportRequest]:
    """Read the recipient table and build one ReportRequest per (brand, reference period).

    Every recipient row carries its own (mandatory) reference week; there is no default.
    ``trigger='adhoc'`` only picks rows with ``send_now = 1``. The flag is NOT cleared
    here; the caller (planner Lambda) does that once the requests were handed over.
    """
    template = get_template_config(template_id)
    current = ReportPeriod.parse(current_period or current_calendar_week())
    run_id = run_id or str(uuid.uuid4())

    recipients = read_recipients(template.id, only_send_now=(trigger == "adhoc"))
    groups = group_recipients(recipients, template.id)
    logging.info(f"{trigger}: {len(recipients)} recipient rows -> {len(groups)} group(s) for template {template.id}")

    requests: list[ReportRequest] = []
    for group in groups:
        reference = group.reference_period
        try:
            requests.append(
                ReportRequest.create(
                    brand=group.brand,
                    current_period=current,
                    reference_period=reference,
                    recipients=group.emails,
                    template_id=template.id,
                    run_id=run_id,
                    trigger=trigger,
                    recipient_ids=group.recipient_ids,
                )
            )
        except ValueError as exc:
            logging.warning(f"Group {group.brand}/{reference} skipped: {exc}")
    return requests


# ------------------------------------------------------------------------------ #
# Lambda 2: render
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
        target = template.target
        s3_key = s3_sync.upload_output(
            container,
            file_name,
            key_prefix=target.key if target and target.is_s3 else None,
            bucket=target.bucket if target and target.is_s3 else None,
        )

        from pycore.easy import storage

        size = len(storage.read_blob(container_name=container, blob_name=file_name, decode=False))

        result.status = "rendered"
        result.file_name = file_name
        result.container = container
        result.bucket = (target.bucket if target and target.is_s3 else settings.s3_bucket) if s3_key else None
        result.s3_key = s3_key
        result.slides = len(config_dict.get("output_slides", []))
        result.size_bytes = size
        result.email_subject = config_dict.get("email_subject")
        result.email_intro = config_dict.get("email_intro")

    except Exception as exc:
        logging.exception(f"Render for {request.brand} failed: {exc}")
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"

    return result


def _fetch_template(location: StorageLocation, container: str) -> str:
    if location.is_s3:
        return s3_sync.download_template(
            container, location.file_name, bucket=location.bucket, key=location.key
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
# Lambda 3: send
# ------------------------------------------------------------------------------ #


def send_deck(render: RenderResult | dict, recipients: list[str] | None = None) -> SendResult:
    """E-mail a rendered deck. Reads the file from S3 (or pycore storage in local runs)."""
    if isinstance(render, dict):
        render = RenderResult(**render)
    request = render.request
    recipients = recipients if recipients is not None else list(request.get("recipients") or [])
    result = SendResult(status="failed", request=request, recipients=recipients)

    try:
        if render.status != "rendered" or not render.file_name:
            result.status = "skipped"
            result.error = f"Nothing to send: render status is {render.status!r} ({render.error})."
            return result
        if not recipients:
            result.status = "skipped"
            result.error = "No recipients."
            return result
        if not settings.mail_enabled:
            result.status = "skipped"
            result.error = "mail_enabled is false."
            logging.warning(f"mail_enabled is false; '{render.file_name}' not sent to {recipients}.")
            return result

        if render.s3_key and render.bucket:
            data = s3_sync.download_bytes(render.bucket, render.s3_key)
        else:
            from pycore.easy import storage

            data = storage.read_blob(
                container_name=render.container or settings.storage_container,
                blob_name=render.file_name,
                decode=False,
            )

        subject = render.email_subject or f"Report: {render.file_name}"
        intro = render.email_intro or "Please find the attached PowerPoint report:"
        result.message_id = mailer.send_pptx(
            recipients=recipients,
            subject=subject,
            html_body=f"<p>{intro} <strong>{render.file_name}</strong>.</p>",
            text_body=f"{intro} {render.file_name}",
            attachment_name=render.file_name,
            attachment_bytes=data,  # type: ignore[arg-type]
        )
        result.status = "sent"
    except Exception as exc:
        logging.exception(f"Send for {request.get('brand')} failed: {exc}")
        result.status = "failed"
        result.error = f"{type(exc).__name__}: {exc}"
    return result


# ------------------------------------------------------------------------------ #
# All-in-one (local runs, single-Lambda deployment)
# ------------------------------------------------------------------------------ #


@dataclasses.dataclass
class DeckOutcome:
    brand: str
    current_period: str
    reference_period: str
    recipients: list[str]
    status: str  # "sent" | "rendered" | "failed"
    file_name: str | None = None
    s3_key: str | None = None
    message_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def run_deck(
    request: ReportRequest,
    source: KpiSource | None = None,
    template: TemplateConfig | None = None,
) -> DeckOutcome:
    render = render_deck(request, source, template)
    outcome = DeckOutcome(
        brand=request.brand,
        current_period=str(request.current_period),
        reference_period=str(request.reference_period),
        recipients=list(request.recipients),
        status=render.status,
        file_name=render.file_name,
        s3_key=render.s3_key,
        error=render.error,
    )
    if render.status != "rendered":
        return outcome

    sent = send_deck(render)
    if sent.status == "sent":
        outcome.status = "sent"
        outcome.message_id = sent.message_id
    elif sent.status == "failed":
        outcome.status = "failed"
        outcome.error = sent.error
    else:
        outcome.status = "rendered"
    return outcome


def steer_kpi_deck_process(request: ReportRequest, source: KpiSource | None = None) -> DeckOutcome:
    """Backwards compatible name for ``run_deck``."""
    return run_deck(request, source)


def steer_scheduled_kpi_decks(
    source: KpiSource | None = None,
    *,
    trigger: str = "scheduled",
    template_id: int | None = None,
    current_period: str | ReportPeriod | None = None,
) -> list[DeckOutcome]:
    requests = plan_decks(
        trigger=trigger,
        template_id=template_id,
        current_period=current_period,
    )
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
    "SendResult",
    "current_calendar_week",
    "graph_steer_creation_process",
    "plan_decks",
    "render_deck",
    "run_deck",
    "send_deck",
    "steer_kpi_deck_process",
    "steer_scheduled_kpi_decks",
]
