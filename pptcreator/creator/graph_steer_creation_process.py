"""Orchestration of the report creation.

Two processes live here:

* ``graph_steer_creation_process`` -- the legacy per-template report driven by the
  control tables and the DQN Config Center (one slide per filter value).
* ``steer_kpi_deck_process`` / ``steer_scheduled_kpi_decks`` -- the VW KPI deck: one
  deck per (brand, current period, reference period), built from a ``KpiSource`` and
  sent to the recipients registered for that brand.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import logging

import pandas as pd
from pycore.schemas import TrackerLoadInformation

from pptcreator.config import settings
from pptcreator.creator.create_ppt.graph_create_ppt import graph_create_ppt
from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest, get_kpi_deck_config
from pptcreator.creator.get_config.graph_get_config import graph_get_config
from pptcreator.creator.send_email.send_email import send_email
from pptcreator.infra import s3_sync
from pptcreator.kpi.base import KpiSource, ReportPeriod
from pptcreator.models.models import ReportRecipients, Templates
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
# KPI deck process
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


def steer_kpi_deck_process(request: ReportRequest, source: KpiSource) -> DeckOutcome:
    """Render and send one deck. Never raises; failures are reported in the outcome."""
    outcome = DeckOutcome(
        brand=request.brand,
        current_period=str(request.current_period),
        reference_period=str(request.reference_period),
        recipients=list(request.recipients),
        status="failed",
    )
    try:
        logging.info(f"KPI deck: {request.brand} {request.current_period} vs. {request.reference_period}")

        # Template into pycore storage (from S3 when enabled)
        s3_sync.download_template(settings.storage_container, settings.template_file_name)

        # Config: data + slide layout + template positions
        config_dict = get_kpi_deck_config(request, source)
        outcome.file_name = f"{config_dict['target_file_name']}.pptx"

        # Render
        config_dict = graph_create_ppt(config_dict)
        logging.info(f"Rendered {outcome.file_name}")

        # Persist
        outcome.s3_key = s3_sync.upload_output(
            config_dict["target_blob_container"], outcome.file_name
        )
        outcome.status = "rendered"

        # Send
        if not request.recipients:
            logging.warning(f"No recipients for {request.brand}; deck rendered but not sent.")
        elif not settings.mail_enabled:
            logging.warning(f"mail_enabled is false; deck for {request.brand} rendered but not sent.")
        else:
            outcome.message_id = send_email(config_dict)
            outcome.status = "sent"

    except Exception as exc:
        logging.exception(f"KPI deck for {request.brand} failed: {exc}")
        outcome.status = "failed"
        outcome.error = f"{type(exc).__name__}: {exc}"

    return outcome


def steer_scheduled_kpi_decks(
    source: KpiSource,
    *,
    current_period: str | ReportPeriod,
    default_reference_period: str | ReportPeriod,
    only_send_now: bool = False,
) -> list[DeckOutcome]:
    """Read the recipient table, group by (brand, periods) and run one deck per group."""
    recipients = read_active_recipients(only_send_now=only_send_now)
    requests = group_recipients(
        recipients,
        current_period=current_period,
        default_reference_period=default_reference_period,
    )
    logging.info(f"{len(recipients)} recipient rows -> {len(requests)} deck(s)")

    outcomes = [steer_kpi_deck_process(request, source) for request in requests]

    if only_send_now:
        processed_ids = _recipient_ids_for(recipients, outcomes)
        reset_send_now(processed_ids)

    return outcomes


def read_active_recipients(*, only_send_now: bool = False) -> pd.DataFrame:
    columns, values = ["is_active"], [True]
    if only_send_now:
        columns.append("send_now")
        values.append(True)
    data = read_data(ReportRecipients, columns, values)
    if data is None or data.empty:
        return pd.DataFrame(columns=["id", "email", "brand", "reference_timestamp", "send_now"])
    return data


def group_recipients(
    recipients: pd.DataFrame,
    *,
    current_period: str | ReportPeriod,
    default_reference_period: str | ReportPeriod,
) -> list[ReportRequest]:
    """One ReportRequest per distinct (brand, reference period); invalid rows are skipped."""
    current = ReportPeriod.parse(current_period)
    default_reference = ReportPeriod.parse(default_reference_period)

    groups: dict[tuple[str, str], list[str]] = {}
    for row in recipients.to_dict("records"):
        email = str(row.get("email") or "").strip()
        brand = str(row.get("brand") or "").strip()
        if not email or not brand:
            logging.warning(f"Recipient row {row.get('id')} skipped: missing email or brand.")
            continue
        raw_reference = row.get("reference_timestamp")
        try:
            reference = (
                ReportPeriod.parse(raw_reference)
                if raw_reference and not pd.isna(raw_reference)
                else default_reference
            )
        except ValueError as exc:
            logging.warning(f"Recipient row {row.get('id')} skipped: {exc}")
            continue
        groups.setdefault((brand, str(reference)), [])
        if email not in groups[(brand, str(reference))]:
            groups[(brand, str(reference))].append(email)

    requests = []
    for (brand, reference), emails in groups.items():
        try:
            requests.append(
                ReportRequest.create(
                    brand=brand,
                    current_period=current,
                    reference_period=reference,
                    recipients=emails,
                )
            )
        except ValueError as exc:
            logging.warning(f"Group {brand}/{reference} skipped: {exc}")
    return requests


def _recipient_ids_for(recipients: pd.DataFrame, outcomes: list[DeckOutcome]) -> list[int]:
    sent = {
        (o.brand, o.reference_period, email)
        for o in outcomes
        if o.status == "sent"
        for email in o.recipients
    }
    ids = []
    for row in recipients.to_dict("records"):
        ref = row.get("reference_timestamp")
        ref_label = str(ReportPeriod.parse(ref)) if ref and not pd.isna(ref) else None
        key = (str(row.get("brand")).strip(), ref_label, str(row.get("email")).strip())
        if key in sent or (ref_label is None and any(k[0] == key[0] and k[2] == key[2] for k in sent)):
            ids.append(int(row["id"]))
    return ids


def reset_send_now(recipient_ids: list[int]) -> None:
    """Clear the ad hoc flag for processed rows. Implemented once ad hoc is in scope."""
    if recipient_ids:
        logging.info(f"send_now reset requested for ids {recipient_ids} (not implemented yet)")


def current_calendar_week(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    year, week, _ = today.isocalendar()
    return f"{year}-KW{week:02d}"


def default_reference_week(today: dt.date | None = None, weeks_back: int = 8) -> str:
    today = today or dt.date.today()
    reference = today - dt.timedelta(weeks=weeks_back)
    year, week, _ = reference.isocalendar()
    return f"{year}-KW{week:02d}"
