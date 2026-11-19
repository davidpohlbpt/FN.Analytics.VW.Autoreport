"""Lambda 1: find the decks to send and start the Step Function for them.

Called every few minutes by EventBridge (input ``{}``). Reads the recipient rows with
``send_now = 1``; if there are any and STATE_MACHINE_ARN is set, it starts that Step
Function (render -> send -> record) with the output below as its input.

in:  {} or {"template_id": 1 | "template_ids": [1, 3], "recipient_ids": [7]}
out: {"has_requests", "count", "errors": [{"template_id", "error"}],
      "requests": [{"template_id", "brand", "current_period", "reference_period",
                    "recipients", "recipient_ids", "run_id"}],
      "execution_arn"}                                 only when a Step Function was started

Every planned row gets a 'processing' claim in T_Control_Autoreport_Runs, so the next
poll does not send it again while it is still running; vw-autoreport-sendemail resets
send_now after sending.
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

OUTPUT_FIELDS = ("template_id", "brand", "current_period", "reference_period", "recipients", "recipient_ids", "run_id")

# Step Functions limit for an execution input is 256 KiB; keep room for the wrapper.
MAX_PAYLOAD_BYTES = 240 * 1024


class PlanFailed(ValueError):
    """Nothing could be planned or handed over; the invocation fails."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)
    template_ids = resolve_template_ids(event)
    run_id = event.get("run_id") or str(uuid.uuid4())

    requests, errors = [], []
    for template_id in template_ids:
        try:
            template = get_template_config(template_id)
            requests += plan_decks(template=template, run_id=run_id)
        except Exception as exc:  # one broken template must not block the others
            logging.exception(f"Planning template {template_id} failed: {exc}")
            errors.append({"template_id": template_id, "error": f"{type(exc).__name__}: {exc}"})
    if len(errors) == len(template_ids):
        raise PlanFailed(f"All templates failed: {errors}")

    if event.get("recipient_ids"):
        wanted = {int(i) for i in event["recipient_ids"]}
        requests = [r for r in requests if r.recipient_id in wanted]

    # Rows still running from an earlier poll are left alone, otherwise they are sent twice
    claimed = run_log.open_recipient_ids([r.recipient_id for r in requests])
    requests = [r for r in requests if r.recipient_id not in claimed]

    items = [{key: r.to_event()[key] for key in OUTPUT_FIELDS} for r in requests]
    result = {"has_requests": bool(items), "count": len(items), "requests": items, "errors": errors}
    _check_payload_size(result)
    run_log.log_processing(requests)

    for item in items:
        logging.info(
            f"Planned: recipient {item['recipient_ids']} {item['brand']} "
            f"{item['current_period']} vs. {item['reference_period']} -> {item['recipients']}"
        )
    logging.info(f"Run {run_id}: {len(items)} deck(s) to send, {len(claimed)} still running {sorted(claimed)}.")

    if items and settings.state_machine_arn:
        result["execution_arn"] = _start_execution(run_id, result, requests)
    return result


def _start_execution(run_id: str, result: dict, requests: list) -> str:
    """Start the Step Function. On failure the claims are closed as 'failed' (send_now
    stays set), so the next poll retries these rows."""
    from pptcreator.infra.aws_clients import stepfunctions_client

    try:
        arn = stepfunctions_client().start_execution(
            stateMachineArn=settings.state_machine_arn, name=run_id, input=json.dumps(result)
        )["executionArn"]
    except Exception as exc:
        for r in requests:
            run_log.update_status(
                r.run_id, r.brand, str(r.reference_period), status="failed",
                recipient_id=r.recipient_id, error=f"Step Function start failed: {exc}",
            )
        raise PlanFailed(f"Could not start {settings.state_machine_arn}: {exc}") from exc
    logging.info(f"Started Step Function execution {arn}.")
    return arn


def resolve_template_ids(event: dict) -> list[int]:
    """Event template_ids/template_id > PLAN_TEMPLATE_IDS > DEFAULT_TEMPLATE_ID > all active."""
    raw = event.get("template_ids") or event.get("template_id") or settings.plan_template_ids or settings.default_template_id
    if raw is None or str(raw).strip().lower() == "all":
        return list_active_template_ids()
    parts = raw if isinstance(raw, list) else str(raw).replace(";", ",").split(",")
    return list(dict.fromkeys(int(str(p).strip()) for p in parts if str(p).strip()))


def _check_payload_size(result: dict) -> None:
    size = len(json.dumps(result).encode("utf-8"))
    if size > MAX_PAYLOAD_BYTES:
        raise PlanFailed(
            f"Plan output is {size} bytes for {result['count']} deck(s), above the Step Functions "
            f"limit of {MAX_PAYLOAD_BYTES} bytes. Split the run, e.g. one template per execution."
        )
