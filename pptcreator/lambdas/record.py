"""Lambda 4: write the outcome of every deck of a run to the run log.

Runs once after the Map of the state machine, so the send Lambda needs no database.

in:  {"run_id": "...", "results": [one entry per deck, as produced by the Map]}
     entry = send result {"status": "sent" | "skipped", "request", "message_id", "error"}
          or catch result {"status": "failed", "step": "render" | "send", "request",
                           "error": {"Error", "Cause"}}
out: {"run_id", "recorded", "sent", "skipped", "failed"}
"""

from __future__ import annotations

import json
import logging

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.utils import run_log  # noqa: E402

# Run-log status per deck outcome; a skipped mail leaves the deck 'rendered'
_RUN_STATUS = {"sent": "sent", "skipped": "rendered", "failed": "failed"}


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    counts = {"sent": 0, "skipped": 0, "failed": 0}
    for entry in event.get("results") or []:
        status = entry.get("status") if entry.get("status") in _RUN_STATUS else "failed"
        counts[status] += 1
        request = entry.get("request") or {}
        run_log.update_status(
            request.get("run_id") or event.get("run_id"),
            request.get("brand", ""),
            request.get("reference_period", ""),
            status=_RUN_STATUS[status],
            message_id=entry.get("message_id"),
            error=error_text(entry.get("error")),
        )

    result = {"run_id": event.get("run_id"), "recorded": sum(counts.values()), **counts}
    logging.info(f"Recorded run {result}")
    return result


def error_text(error) -> str | None:
    """Plain text of a Lambda error or a Step Functions catch ({"Error", "Cause"})."""
    if not error:
        return None
    if not isinstance(error, dict):
        return str(error)
    cause = error.get("Cause")
    try:
        cause = json.loads(cause).get("errorMessage", cause)
    except (TypeError, ValueError, AttributeError):
        pass
    return ": ".join(str(part) for part in (error.get("Error"), cause) if part)
