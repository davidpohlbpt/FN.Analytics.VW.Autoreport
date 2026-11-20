"""Lambda 2: render one deck.

in:  one request of the plan output: {"template_id", "brand", "current_period",
     "reference_period", "recipients", "recipient_ids"}; optional "kpi_ids",
     "language", "target_file_name". Template and KPI mappings are read from the
     control tables.
out: the event for the next Step Functions state, vw-autoreport-sendemail:
     {"recipient", "recipient_id", "run_id", "brand", "bucket", "s3_key", "file_name",
     "email_subject"} (one recipient per Map item).
Raises on failure so that Step Functions catches it.
"""

from __future__ import annotations

import logging

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import render_deck  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402


class RenderFailed(RuntimeError):
    """Raised so that Step Functions sees a task failure."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    request = ReportRequest.from_event(event)
    logging.info(
        f"Rendering run {request.run_id}, recipient {request.recipient_ids}: {request.brand} "
        f"{request.current_period} vs. {request.reference_period}."
    )

    result = render_deck(request)
    update_run_log(request, result)

    if result.status != "rendered":
        logging.error(f"Render failed for recipient {request.recipient_ids}: {result.error}")
        raise RenderFailed(result.error or "render failed")

    logging.info(f"Rendered {result.file_name} ({result.slides} slides, {result.size_bytes} bytes) -> {result.s3_key}")
    output = build_send_email_event(request, result)
    logging.info(f"Handing s3://{output['bucket']}/{output['s3_key']} to vw-autoreport-sendemail for recipient id {output['recipient_id']}.")
    return output


def update_run_log(request: ReportRequest, result) -> None:
    status = "rendered" if result.status == "rendered" else "failed"
    run_log.update_status(
        request.run_id,
        request.brand,
        str(request.reference_period),
        status=status,
        recipient_id=request.recipient_id,
        error=result.error,
    )
    logging.info(f"Run log for recipient {request.recipient_id}: {status}.")


def build_send_email_event(request: ReportRequest, result) -> dict:
    """Exactly the fields read by vw-autoreport-sendemail."""
    return {
        "recipient": request.recipients[0] if len(request.recipients) == 1 else None,
        "recipient_id": request.recipient_id if len(request.recipient_ids) == 1 else None,
        "run_id": request.run_id,
        "brand": request.brand,
        "bucket": result.bucket,
        "s3_key": result.s3_key,
        "file_name": result.file_name,
        "email_subject": result.email_subject,
    }
