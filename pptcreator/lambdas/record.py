"""Lambda 4: write the outcome of every deck of a run and clear ``send_now`` when sent.

Runs once after the Map of the state machine, so the send Lambda needs no database.
This is also the only place where ``send_now`` is cleared: a row keeps the flag when
rendering or sending failed, so the user can fix the reason and press send again, or
the frontend can clear it.

in:  {"run_id": "...", "results": [one entry per deck, as produced by the Map]}
     entry = send result {"status": "sent" | "skipped", "request", "message_id", "error"}
          or catch result {"status": "failed", "step": "render" | "send", "request",
                           "error": {"Error", "Cause"}}
out: {"run_id", "recorded", "sent", "skipped", "failed", "cleared"}
"""

from __future__ import annotations

import json
import logging

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.utils import run_log  # noqa: E402

# Run-log status per deck outcome. 'skipped' (MAIL_ENABLED false, no recipients) still
# clears send_now: the deck was produced and the user can resend it deliberately.
_RUN_STATUS = {"sent": "sent", "skipped": "skipped", "failed": "failed"}


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    counts = {"sent": 0, "skipped": 0, "failed": 0}
    sent_rows: list[int] = []
    for entry in event.get("results") or []:
        outcome = entry.get("status") if entry.get("status") in _RUN_STATUS else "failed"
        counts[outcome] += 1
        request = entry.get("request") or {}
        recipient_id = (request.get("recipient_ids") or [None])[0]
        run_log.update_status(
            request.get("run_id") or event.get("run_id"),
            request.get("brand", ""),
            request.get("reference_period", ""),
            status=_RUN_STATUS[outcome],
            recipient_id=recipient_id,
            message_id=entry.get("message_id"),
            error=error_text(entry.get("error")),
        )
        if outcome != "failed" and recipient_id is not None:
            sent_rows.append(int(recipient_id))

    cleared = run_log.clear_send_now(sent_rows)
    result = {
        "run_id": event.get("run_id"),
        "recorded": sum(counts.values()),
        "sent": counts["sent"],
        "skipped": counts["skipped"],
        "failed": counts["failed"],
        "cleared": cleared,
    }
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
