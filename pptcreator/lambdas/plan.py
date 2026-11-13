"""Lambda 1: read the control tables and hand one work item per deck to the render Lambda.

in:  {"trigger": "scheduled" | "adhoc",
      "template_ids": [1, 3] | "template_id": 1,     optional, else PLAN_TEMPLATE_IDS
      "current_period": "2026-KW45",                  optional, else this week
      "run_id": "..."}                                optional
out: {"run_id", "trigger", "template_ids", "count", "errors",
      "requests": [ReportRequest + {"template": TemplateConfig snapshot}, ...]}

Each request carries the full template config (template link, KPI definitions, file
name and subject pattern), so the whole run uses one consistent snapshot and the render
Lambda does not re-read the template and mapping tables.

Side effects: run log rows 'queued'; send_now cleared for ad hoc rows. Both only happen
after the payload is known to fit into the Step Functions state limit.
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
from pptcreator.creator.graph_steer_creation_process import (  # noqa: E402
    current_calendar_week,
    plan_decks,
)
from pptcreator.utils import run_log  # noqa: E402

TRIGGERS = ("scheduled", "adhoc")

# Step Functions limit for a state's input/output is 256 KiB; keep room for the wrapper.
MAX_PAYLOAD_BYTES = 240 * 1024


class PlanFailed(RuntimeError):
    """No template could be planned; raised so that Step Functions marks the run failed."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    trigger = event.get("trigger") or event.get("mode") or "scheduled"
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, got {trigger!r}.")
    template_ids = resolve_template_ids(event)
    if not template_ids:
        raise PlanFailed("No template to plan: none configured and none active.")

    run_id = event.get("run_id") or str(uuid.uuid4())
    current = event.get("current_period") or current_calendar_week()

    requests, items, errors = [], [], []
    for template_id in template_ids:
        try:
            template = get_template_config(template_id)
            planned = plan_decks(
                trigger=trigger, template=template, current_period=current, run_id=run_id
            )
        except Exception as exc:
            # One broken template must not block the reports of the others
            logging.exception(f"Planning template {template_id} failed: {exc}")
            errors.append({"template_id": template_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        snapshot = template.to_event()
        requests.extend(planned)
        items.extend({**r.to_event(), "template": snapshot} for r in planned)

    if len(errors) == len(template_ids):
        raise PlanFailed(f"All templates failed: {errors}")

    result = {
        "run_id": run_id,
        "trigger": trigger,
        "template_ids": template_ids,
        "count": len(items),
        "errors": errors,
        "requests": items,
    }
    _check_payload_size(result)

    run_log.log_queued(requests)
    if trigger == "adhoc":
        run_log.clear_send_now(sorted({i for r in requests for i in r.recipient_ids}))

    logging.info(f"Planned {len(items)} deck(s) for {trigger} from template(s) {template_ids}.")
    return result


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
