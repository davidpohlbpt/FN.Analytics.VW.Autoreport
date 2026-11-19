"""Lambda 1: find the decks to send and start the Step Function for them.

Called every few minutes by EventBridge (input ``{}``). Reads the recipient rows with
``send_now = 1``; if there are any and STATE_MACHINE_ARN is set, it starts that Step
Function (render -> send email) with the output below as its input.

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


class PlanFailed(ValueError):
    """Nothing could be planned or handed over; the invocation fails."""


def handler(event, context):
    event = normalise_event(event)
    log_start(context, event)

    template_ids = resolve_template_ids(event)
    run_id = event.get("run_id") or str(uuid.uuid4())
    logging.info(f"Run {run_id}: planning template(s) {template_ids}.")

    requests, errors = plan_templates(template_ids, run_id)
    requests = filter_recipient_ids(requests, event.get("recipient_ids"))
    requests, claimed = skip_open_claims(requests)

    result = build_output(requests, errors)
    check_payload_size(result)
    run_log.log_processing(requests)
    logging.info(f"Run {run_id}: wrote {len(requests)} processing claim(s).")

    for item in result["requests"]:
        logging.info(
            f"Planned: recipient {item['recipient_ids']} {item['brand']} "
            f"{item['current_period']} vs. {item['reference_period']} -> {item['recipients']}"
        )
    logging.info(f"Run {run_id}: {result['count']} deck(s) to send, {len(claimed)} still running {sorted(claimed)}.")

    if result["requests"] and settings.state_machine_arn:
        result["execution_arn"] = start_execution(run_id, result, requests)
    elif result["requests"]:
        logging.info("STATE_MACHINE_ARN is not set; returning the plan without starting a Step Function.")
    else:
        logging.info("Nothing to send; no Step Function started.")
    return result


def resolve_template_ids(event: dict) -> list[int]:
    """Event template_ids/template_id > PLAN_TEMPLATE_IDS > DEFAULT_TEMPLATE_ID > all active."""
    raw = event.get("template_ids") or event.get("template_id") or settings.plan_template_ids or settings.default_template_id
    if raw is None or str(raw).strip().lower() == "all":
        template_ids = list_active_template_ids()
        logging.info(f"Using all active templates: {template_ids}.")
        return template_ids
    parts = raw if isinstance(raw, list) else str(raw).replace(";", ",").split(",")
    return list(dict.fromkeys(int(str(p).strip()) for p in parts if str(p).strip()))


def plan_templates(template_ids: list[int], run_id: str) -> tuple[list, list[dict]]:
    """One broken template must not block the others; all failing stops the run."""
    requests, errors = [], []
    for template_id in template_ids:
        try:
            template = get_template_config(template_id)
            planned = plan_decks(template=template, run_id=run_id)
            requests += planned
            logging.info(f"Template {template_id}: {len(planned)} deck(s) planned.")
        except Exception as exc:
            logging.exception(f"Planning template {template_id} failed: {exc}")
            errors.append({"template_id": template_id, "error": f"{type(exc).__name__}: {exc}"})
    if len(errors) == len(template_ids):
        raise PlanFailed(f"All templates failed: {errors}")
    return requests, errors


def filter_recipient_ids(requests: list, recipient_ids) -> list:
    if not recipient_ids:
        return requests
    wanted = {int(i) for i in recipient_ids}
    filtered = [r for r in requests if r.recipient_id in wanted]
    logging.info(f"Recipient filter {sorted(wanted)}: {len(filtered)} of {len(requests)} deck(s) kept.")
    return filtered


def skip_open_claims(requests: list) -> tuple[list, set[int]]:
    """Rows still running from an earlier poll are left alone, otherwise they are sent twice."""
    claimed = run_log.open_recipient_ids([r.recipient_id for r in requests])
    if claimed:
        logging.info(f"Skipping recipient(s) with an open claim: {sorted(claimed)}.")
    return [r for r in requests if r.recipient_id not in claimed], claimed


def build_output(requests: list, errors: list[dict]) -> dict:
    output_fields = (
        "template_id", "brand", "current_period", "reference_period", "recipients", "recipient_ids", "run_id"
    )
    items = [{key: r.to_event()[key] for key in output_fields} for r in requests]
    return {"has_requests": bool(items), "count": len(items), "requests": items, "errors": errors}


def check_payload_size(result: dict, max_bytes: int = 240 * 1024) -> None:
    """Step Functions allows 256 KiB execution input; keep room for the wrapper."""
    size = len(json.dumps(result).encode("utf-8"))
    logging.info(f"Plan output size: {size} bytes.")
    if size > max_bytes:
        raise PlanFailed(
            f"Plan output is {size} bytes for {result['count']} deck(s), above the Step Functions "
            f"limit of {max_bytes} bytes. Split the run, e.g. one template per execution."
        )


def start_execution(run_id: str, result: dict, requests: list) -> str:
    """Start the Step Function. On failure the claims are closed as 'failed' (send_now
    stays set), so the next poll retries these rows."""
    from pptcreator.infra.aws_clients import stepfunctions_client

    logging.info(f"Starting Step Function {settings.state_machine_arn} for run {run_id}.")
    try:
        arn = stepfunctions_client().start_execution(
            stateMachineArn=settings.state_machine_arn, name=run_id, input=json.dumps(result)
        )["executionArn"]
    except Exception as exc:
        logging.exception(f"Starting the Step Function failed; closing {len(requests)} claim(s) as failed.")
        for r in requests:
            run_log.update_status(
                r.run_id, r.brand, str(r.reference_period), status="failed",
                recipient_id=r.recipient_id, error=f"Step Function start failed: {exc}",
            )
        raise PlanFailed(f"Could not start {settings.state_machine_arn}: {exc}") from exc
    logging.info(f"Started Step Function execution {arn}.")
    return arn
