"""Lambda 3: e-mail a rendered deck.

in:  the RenderResult of Lambda 2 (optionally with a "recipients" override)
out: SendResult {"status": "sent" | "skipped", "message_id", ...}
Raises on failure so that Step Functions retries / catches it.
"""

from __future__ import annotations

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.creator.graph_steer_creation_process import RenderResult, send_deck  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402


class SendFailed(RuntimeError):
    """Raised so that Step Functions sees a task failure."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    render = RenderResult(**{k: v for k, v in event.items() if k in RenderResult.__dataclass_fields__})
    recipients = event.get("recipients")  # optional override
    result = send_deck(render, recipients)

    request = render.request or {}
    run_log.update_status(
        request.get("run_id"),
        request.get("brand", ""),
        request.get("reference_period", ""),
        status="sent" if result.status == "sent" else ("rendered" if result.status == "skipped" else "failed"),
        message_id=result.message_id,
        error=result.error,
    )
    if result.status == "failed":
        raise SendFailed(result.error or "send failed")
    return result.as_dict()
