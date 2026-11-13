"""Local CLI, all-in-one handler and backwards compatible Lambda entry points.

The state machine Lambdas from the render image live in ``pptcreator.lambdas``:

``pptcreator.lambdas.plan.handler``    Lambda 1  (alias ``plan_handler``)
``pptcreator.lambdas.render.handler``  Lambda 2  (alias ``render_handler``)
``pptcreator.lambdas.record.handler``  Lambda 4  (alias ``record_handler``)

Lambda 3 (send) is the separate ZIP package ``functions/send/sender``.

``handler``  (all-in-one, for local runs; needs the sender package on the path)
    in:  {"mode": "scheduled" | "adhoc" | "manual", ...}
    out: summary with one entry per deck
"""

from __future__ import annotations

import json
import logging

from pptcreator.lambdas._bootstrap import log_start as _log_start
from pptcreator.lambdas._bootstrap import normalise_event as _normalise_event

from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import (  # noqa: E402
    DeckOutcome,
    current_calendar_week,
    run_deck,
    steer_scheduled_kpi_decks,
)
from pptcreator.kpi.base import KpiSource  # noqa: E402
from pptcreator.lambdas.plan import PlanFailed  # noqa: E402,F401
from pptcreator.lambdas.plan import handler as plan_handler  # noqa: E402,F401
from pptcreator.lambdas.record import handler as record_handler  # noqa: E402,F401
from pptcreator.lambdas.render import RenderFailed  # noqa: E402,F401
from pptcreator.lambdas.render import handler as render_handler  # noqa: E402

MODES = ("scheduled", "manual", "adhoc")


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
