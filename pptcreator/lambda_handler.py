"""AWS Lambda entry points and local CLI.

Three handlers, one per Lambda of the state machine (see deployment/state_machine.asl.json):

``plan_handler``  (Lambda 1, EventBridge every N minutes and weekly)
    in:  {"trigger": "adhoc" | "scheduled", "template_id": 1,
          "current_period": "2026-KW45"}   (current_period optional)
    The reference week always comes from the recipient row (mandatory there).
    out: {"run_id": "...", "requests": [ReportRequest, ...]}
    Side effects: run log rows with status 'queued'; send_now cleared for ad hoc rows.

``render_handler``  (Lambda 2)
    in:  one ReportRequest (as produced by the planner, or written by hand)
    out: RenderResult {"status": "rendered", "bucket", "s3_key", "file_name", ...}
    Raises on failure so that Step Functions retries / catches it.

``send_handler``  (Lambda 3)
    in:  the RenderResult of Lambda 2 (optionally with "recipients" override)
    out: SendResult {"status": "sent", "message_id", ...}

``handler``  (all-in-one, for local runs and a single-Lambda deployment)
    in:  {"mode": "scheduled" | "adhoc" | "manual", ...}
    out: summary with one entry per deck
"""

from __future__ import annotations

import json
import logging
import os

# pycore reads these at import; set sane Lambda defaults before importing it.
os.environ.setdefault("APP_NAME", "VwAutoreport")
os.environ.setdefault("RESOURCE_TYPE", "LOCAL")
if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and not os.environ.get("LOCAL_BLOB_DIR"):
    os.environ["LOCAL_BLOB_DIR"] = "/tmp/autoreport_data"

# Optional internal CA bundle baked into the image (deployment/certs/*.pem). Only
# activated when the file exists, so images without certs keep the system defaults.
_ca_bundle = os.environ.get("CA_BUNDLE_PATH")
if _ca_bundle and os.path.isfile(_ca_bundle):
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _ca_bundle)
    os.environ.setdefault("SSL_CERT_FILE", _ca_bundle)

# Must run before pycore is imported (it reads LOCAL_SQLSERVER_CONN_STR at import).
from pptcreator.infra.sql_connection import configure_from_ssm  # noqa: E402

configure_from_ssm()

from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import (  # noqa: E402
    DeckOutcome,
    RenderResult,
    current_calendar_week,
    plan_decks,
    render_deck,
    run_deck,
    send_deck,
    steer_scheduled_kpi_decks,
)
from pptcreator.kpi.base import KpiSource  # noqa: E402
from pptcreator.utils import run_log  # noqa: E402

logging.getLogger().setLevel(logging.INFO)

MODES = ("scheduled", "manual", "adhoc")


class RenderFailed(RuntimeError):
    """Raised by render_handler so that Step Functions sees a task failure."""


# ------------------------------------------------------------------------------ #
# Lambda 1: plan
# ------------------------------------------------------------------------------ #


def plan_handler(event, context):
    event = _normalise_event(event)
    trigger = event.get("trigger") or event.get("mode") or "scheduled"
    if trigger not in ("scheduled", "adhoc"):
        raise ValueError(f"trigger must be 'scheduled' or 'adhoc', got {trigger!r}.")
    _log_start(context, event)

    requests = plan_decks(
        trigger=trigger,
        template_id=event.get("template_id"),
        current_period=event.get("current_period"),
        run_id=event.get("run_id"),
    )
    run_log.log_queued(requests)
    if trigger == "adhoc":
        ids = sorted({i for r in requests for i in r.recipient_ids})
        run_log.clear_send_now(ids)

    result = {
        "run_id": requests[0].run_id if requests else event.get("run_id"),
        "trigger": trigger,
        "count": len(requests),
        "requests": [r.to_event() for r in requests],
    }
    logging.info(f"Planned {len(requests)} deck(s) for trigger {trigger}.")
    return result


# ------------------------------------------------------------------------------ #
# Lambda 2: render
# ------------------------------------------------------------------------------ #


def render_handler(event, context):
    event = _normalise_event(event)
    _log_start(context, event)
    request = ReportRequest.from_event(event)

    result = render_deck(request)
    run_log.update_status(
        request.run_id,
        request.brand,
        str(request.reference_period),
        status=result.status,
        s3_key=result.s3_key,
        error=result.error,
    )
    if result.status != "rendered":
        raise RenderFailed(result.error or "render failed")
    logging.info(f"Rendered {result.file_name} ({result.slides} slides, {result.size_bytes} bytes) -> {result.s3_key}")
    return result.as_dict()


# ------------------------------------------------------------------------------ #
# Lambda 3: send
# ------------------------------------------------------------------------------ #


def send_handler(event, context):
    event = _normalise_event(event)
    _log_start(context, event)

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
        raise RuntimeError(result.error or "send failed")
    return result.as_dict()


# ------------------------------------------------------------------------------ #
# All-in-one
# ------------------------------------------------------------------------------ #


def run(event: dict | None, source: KpiSource | None = None) -> dict:
    event = _normalise_event(event)
    mode = event.get("mode", "scheduled")
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}.")

    if mode == "manual":
        request = ReportRequest.create(
            brand=event["brand"],
            current_period=event.get("current_period") or current_calendar_week(),
            reference_period=event["reference_period"],
            recipients=event.get("recipients") or [],
            template_id=event.get("template_id"),
            kpi_ids=event.get("kpi_ids"),
            language=event.get("language"),
            target_file_name=event.get("target_file_name"),
            trigger="manual",
        )
        outcomes = [run_deck(request, source)]
    else:
        outcomes = steer_scheduled_kpi_decks(
            source,
            trigger=mode,
            template_id=event.get("template_id"),
            current_period=event.get("current_period"),
        )

    return _summary(mode, outcomes)


def handler(event, context):
    _log_start(context, event)
    try:
        summary = run(event)
    except Exception as exc:
        logging.exception(f"Invocation failed: {exc}")
        raise
    logging.info(f"Finished: {json.dumps(summary, default=str)}")
    return summary


# ------------------------------------------------------------------------------ #


def _log_start(context, event) -> None:
    request_id = getattr(context, "aws_request_id", None)
    logging.info(f"Invocation {request_id} with event: {json.dumps(event, default=str)[:2000]}")


def _normalise_event(event) -> dict:
    if event is None:
        return {}
    if isinstance(event, str):
        event = json.loads(event)
    if not isinstance(event, dict):
        raise ValueError(f"Unsupported event type {type(event).__name__}.")
    # EventBridge custom events carry the payload in "detail"; constant inputs do not.
    if "mode" not in event and "trigger" not in event and "brand" not in event and isinstance(event.get("detail"), dict):
        return event["detail"]
    return event


def _summary(mode: str, outcomes: list[DeckOutcome]) -> dict:
    counts = {"sent": 0, "rendered": 0, "failed": 0}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    return {
        "mode": mode,
        "decks": len(outcomes),
        **counts,
        "results": [o.as_dict() for o in outcomes],
    }


# ------------------------------------------------------------------------------ #
# CLI for local runs: `poetry run pptcreator scheduled --current 2025-KW48`
# ------------------------------------------------------------------------------ #


def cli(argv: list[str] | None = None) -> int:
    """Local runner; same entry points as the Lambdas, output as JSON."""
    import argparse

    parser = argparse.ArgumentParser(prog="pptcreator", description="VW Autoreport local runner")
    commands = parser.add_subparsers(dest="command", required=True)

    manual = commands.add_parser("manual", help="Render one deck for a brand and reference period")
    manual.add_argument("--brand", required=True, help="EK_ORG value, e.g. Audi")
    manual.add_argument("--reference", required=True, help="Reference period, e.g. KW37 or 2025-KW37")
    manual.add_argument("--current", default=None, help="Current period, default: this week")
    manual.add_argument("--template-id", type=int, default=None, help="Template id; default: the only active one")
    manual.add_argument("--recipient", action="append", default=[], help="Recipient e-mail (repeatable)")
    manual.add_argument("--kpi", action="append", default=[], help="KPI key subset (repeatable)")

    scheduled = commands.add_parser("scheduled", help="One deck per recipient/brand from the control tables")
    scheduled.add_argument("--current", default=None, help="Current period, default: this week")
    scheduled.add_argument("--template-id", type=int, default=None, help="Template id; default: the only active one")
    scheduled.add_argument("--adhoc", action="store_true", help="Only rows with send_now = 1")

    render = commands.add_parser("render", help="Render the ReportRequest stored in a JSON file")
    render.add_argument("event_file", help="JSON file with one ReportRequest")

    args = parser.parse_args(argv)

    if args.command == "manual":
        event = {
            "mode": "manual",
            "brand": args.brand,
            "reference_period": args.reference,
            "current_period": args.current,
            "template_id": args.template_id,
            "recipients": args.recipient,
            "kpi_ids": args.kpi or None,
        }
        result = run(event)
    elif args.command == "scheduled":
        event = {
            "mode": "adhoc" if args.adhoc else "scheduled",
            "current_period": args.current,
            "template_id": args.template_id,
        }
        result = run(event)
    else:
        with open(args.event_file, encoding="utf-8") as fh:
            result = render_handler(json.load(fh), None)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
