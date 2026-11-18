"""Lambda 2: render one deck.

in:  one request of the plan output: {"template_id", "brand", "current_period",
     "reference_period", "recipients", "recipient_ids"}; optional "kpi_ids",
     "language", "target_file_name". Template and KPI mappings are read from the
     control tables.
out: RenderResult {"status": "rendered", "bucket", "s3_key", "file_name", ...}; its
     "request" echoes the input, so the send step gets the recipients from it.
Raises on failure so that Step Functions retries / catches it.
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

    result = render_deck(request)
    run_log.update_status(
        request.run_id,
        request.brand,
        str(request.reference_period),
        status="rendered" if result.status == "rendered" else "failed",
        recipient_id=request.recipient_id,
        s3_key=result.s3_key,
        error=result.error,
    )
    if result.status != "rendered":
        raise RenderFailed(result.error or "render failed")
    logging.info(f"Rendered {result.file_name} ({result.slides} slides, {result.size_bytes} bytes) -> {result.s3_key}")
    return result.as_dict()
