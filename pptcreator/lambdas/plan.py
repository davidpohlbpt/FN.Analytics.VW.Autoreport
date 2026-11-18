"""Lambda 1: read the recipient table and hand one work item per deck to the render Lambda.

in:  {}  (all optional)
     {"trigger": "adhoc" | "scheduled",               default adhoc: only send_now = 1
      "template_ids": [1, 3] | "template_id": 1,     else PLAN_TEMPLATE_IDS / all active
      "recipient_ids": [7, 8]}                        only these rows
out: {"has_requests": true,
      "count": 1,
      "requests": [{"template_id", "brand", "current_period", "reference_period",
                    "recipients": ["a@x.de"], "recipient_ids": [3]}],
      "errors": [{"template_id", "error"}]}           templates that could not be planned
     "has_requests" is false when nothing is to be sent: a Step Functions Choice state
     can end the execution there. Each request is the input of the render Lambda, which
     reads the template and KPI mappings itself and passes recipients on to the send step.
     recipient_ids identify the row for the run log and for clearing send_now (record).

``adhoc`` picks the recipient rows with ``send_now = 1``; that flag is set and cleared by
the frontend and by the record step, never here. Every request is one recipient row:
the two runs come from ``report_week`` / ``comparison_week`` (e.g. 'V01-B (46/2025)')
and are resolved to snapshots by the KPI source.

Side effects: one run-log row per deck with status 'processing' (the claim that stops
the 5-10 minute poller from sending a row twice), written only after the payload is
known to fit into the Step Functions state limit.
"""

from __future__ import annotations

import json
import logging
import uuid

from pptcreator.lambdas._bootstrap import log_start, normalise_event

from pptcreator.config import settings  # noqa: E402
from pptcreator.creator.get_config.get_autoreport_config import (  # noqa: E402
    get_template_config,
    list_active_template_ids,
)
from pptcreator.creator.graph_steer_creation_process import plan_decks  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402

TRIGGERS = ("scheduled", "adhoc")

OUTPUT_FIELDS = ("template_id", "brand", "current_period", "reference_period", "recipients", "recipient_ids")
"""Per deck in the output. recipient_ids identifies the row for the run log and send_now."""

# Step Functions limit for a state's input/output is 256 KiB; keep room for the wrapper.
MAX_PAYLOAD_BYTES = 240 * 1024


class PlanFailed(RuntimeError):
    """No template could be planned; raised so that Step Functions marks the run failed."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    trigger = event.get("trigger") or event.get("mode") or "adhoc"
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, got {trigger!r}.")
    template_ids = resolve_template_ids(event)
    if not template_ids:
        raise PlanFailed("No template to plan: none configured and none active.")

    run_id = event.get("run_id") or str(uuid.uuid4())

    requests, items, errors = [], [], []
    for template_id in template_ids:
        try:
            template = get_template_config(template_id)
            planned = plan_decks(trigger=trigger, template=template, run_id=run_id)
        except Exception as exc:
            # One broken template must not block the reports of the others
            logging.exception(f"Planning template {template_id} failed: {exc}")
            errors.append({"template_id": template_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        requests.extend(planned)
        items.extend(_output_item(r) for r in planned)

    if len(errors) == len(template_ids):
        raise PlanFailed(f"All templates failed: {errors}")

    if event.get("recipient_ids"):
        wanted = {int(i) for i in event["recipient_ids"]}
        requests = [r for r in requests if r.recipient_id in wanted]
        items = [i for i in items if i.get("recipient_ids") and i["recipient_ids"][0] in wanted]

    # A row that is still being processed by an earlier run is left alone: retrying it
    # automatically would send the same deck again on every poll.
    claimed = run_log.open_recipient_ids([r.recipient_id for r in requests])
    if claimed:
        logging.warning(f"Skipping {len(claimed)} recipient row(s) with an open claim: {sorted(claimed)}")
    selected = [r for r in requests if r.recipient_id not in claimed]
    items = [i for i in items if i.get("recipient_ids") and i["recipient_ids"][0] not in claimed]

    result = {
        "has_requests": bool(items),
        "count": len(items),
        "requests": items,
        "errors": errors,
    }
    _check_payload_size(result)

    run_log.log_processing(selected)

    for item in items:
        logging.info(
            f"Planned: recipient {item['recipient_ids']} {item['brand']} "
            f"{item['current_period']} vs. {item['reference_period']} -> {item['recipients']}"
        )
    logging.info(
        f"Run {run_id}: planned {len(items)} deck(s) for {trigger} from template(s) {template_ids}; "
        f"skipped {len(claimed)} claimed row(s)."
    )
    return result


def _output_item(request) -> dict:
    """The fields the next steps read: render (deck) and record (recipient_ids)."""
    event = request.to_event()
    return {key: event[key] for key in OUTPUT_FIELDS}


def resolve_template_ids(event: dict) -> list[int]:
    """Event ``template_ids``/``template_id`` > PLAN_TEMPLATE_IDS > DEFAULT_TEMPLATE_ID > all active."""
    for raw in (
        event.get("template_ids"),
        event.get("template_id"),
        settings.plan_template_ids,
        settings.default_template_id,
    ):
        if raw is None or raw == [] or (isinstance(raw, str) and not raw.strip()):
            continue
        if isinstance(raw, str) and raw.strip().lower() == "all":
            return list_active_template_ids()
        parts = raw.replace(";", ",").split(",") if isinstance(raw, str) else raw
        if not isinstance(parts, list):
            parts = [parts]
        ids: list[int] = []
        for part in parts:
            try:
                template_id = int(str(part).strip())
            except ValueError as exc:
                raise ValueError(f"Invalid template id {part!r} in {raw!r}.") from exc
            if template_id not in ids:
                ids.append(template_id)
        return ids
    return list_active_template_ids()


def _check_payload_size(result: dict) -> None:
    size = len(json.dumps(result, default=str).encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        raise PlanFailed(
            f"Plan output is {size} bytes for {result['count']} deck(s), above the Step Functions "
            f"limit of {MAX_PAYLOAD_BYTES} bytes. Split the run, e.g. one template per execution."
        )
