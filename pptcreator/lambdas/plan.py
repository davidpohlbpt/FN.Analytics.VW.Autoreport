"""Lambda 1: find the decks to send and start the Step Function for them.

Called every few minutes by EventBridge. Reads the recipient rows with ``send_now = 1``
of all active templates and starts STATE_MACHINE_ARN with one request per row.

out: {"has_requests", "count",
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

from pptcreator.lambdas._bootstrap import log_start

from pptcreator.config import settings  # noqa: E402
from pptcreator.creator.get_config.get_autoreport_config import list_active_template_ids  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import plan_decks  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402


class PlanFailed(ValueError):
    """The planned decks could not be handed over; the invocation fails."""


def handler(event, context):
    log_start(context, event)
    run_id = str(uuid.uuid4())

    requests = []
    for template_id in list_active_template_ids():
        planned = plan_decks(template_id=template_id, run_id=run_id)
        logging.info(f"Template {template_id}: {len(planned)} deck(s) planned.")
        requests += planned

    requests, claimed = skip_open_claims(requests)
    result = build_output(requests)
    if not requests:
        logging.info(f"Run {run_id}: nothing to send, {len(claimed)} still running {sorted(claimed)}.")
        return result

    if not settings.state_machine_arn:
        raise PlanFailed("STATE_MACHINE_ARN is not set.")

    run_log.log_processing(requests)
    for item in result["requests"]:
        logging.info(
            f"Planned: recipient {item['recipient_ids']} {item['brand']} "
            f"{item['current_period']} vs. {item['reference_period']}"
        )
    logging.info(f"Run {run_id}: {result['count']} deck(s) to send, {len(claimed)} still running {sorted(claimed)}.")

    result["execution_arn"] = start_execution(run_id, result, requests)
    return result


def skip_open_claims(requests: list) -> tuple[list, set[int]]:
    """Rows still running from an earlier poll are left alone, otherwise they are sent twice."""
    claimed = run_log.open_recipient_ids([r.recipient_id for r in requests])
    if claimed:
        logging.info(f"Skipping recipient(s) with an open claim: {sorted(claimed)}.")
    return [r for r in requests if r.recipient_id not in claimed], claimed


def build_output(requests: list) -> dict:
    output_fields = (
        "template_id", "brand", "current_period", "reference_period", "recipients", "recipient_ids", "run_id"
    )
    items = [{key: r.to_event()[key] for key in output_fields} for r in requests]
    return {"has_requests": bool(items), "count": len(items), "requests": items}


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
