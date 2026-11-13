"""Lambda 2: render one deck.

in:  one item of the plan output: ReportRequest fields + optional "template" snapshot.
     Without "template" (hand-written / manual events) the template and KPI mappings
     are read from the control tables.
out: RenderResult {"status": "rendered", "bucket", "s3_key", "file_name", ...}; its
     "request" echoes the ReportRequest without the template snapshot.
Raises on failure so that Step Functions retries / catches it.
"""

from __future__ import annotations

import logging

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.creator.get_config.get_autoreport_config import TemplateConfig  # noqa: E402
from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import render_deck  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402


class RenderFailed(RuntimeError):
    """Raised so that Step Functions sees a task failure."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)
    request = ReportRequest.from_event(event)
    template = _template_snapshot(event, request)

    result = render_deck(request, template=template)
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


def _template_snapshot(event: dict, request: ReportRequest) -> TemplateConfig | None:
    if not event.get("template"):
        return None
    template = TemplateConfig.from_event(event["template"])
    if request.template_id is not None and request.template_id != template.id:
        raise ValueError(
            f"template_id {request.template_id} does not match the template snapshot ({template.id})."
        )
    return template
