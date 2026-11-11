"""AWS Lambda entry point and local CLI.

Event formats
-------------
Scheduled (EventBridge cron)::

    {"mode": "scheduled", "current_period": "2026-KW45", "reference_period": "2026-KW37"}

``current_period`` defaults to the current ISO week, ``reference_period`` to eight
weeks earlier. Recipients are read from the recipient table.

Manual (testing, re-sends)::

    {"mode": "manual", "brand": "Audi", "current_period": "KW45",
     "reference_period": "KW37", "recipients": ["a@b.de"], "kpi_ids": ["kpi1"]}

Ad hoc (``send_now`` rows only)::

    {"mode": "adhoc"}

The response is a JSON summary with one entry per deck.
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

from pptcreator.config import settings  # noqa: E402
from pptcreator.creator.get_config.get_kpi_deck_config import ReportRequest  # noqa: E402
from pptcreator.creator.graph_steer_creation_process import (  # noqa: E402
    DeckOutcome,
    current_calendar_week,
    default_reference_week,
    steer_kpi_deck_process,
    steer_scheduled_kpi_decks,
)
from pptcreator.kpi.base import KpiSource  # noqa: E402

logging.getLogger().setLevel(logging.INFO)

MODES = ("scheduled", "manual", "adhoc")


def get_kpi_source() -> KpiSource:
    if settings.kpi_source == "sql":
        raise NotImplementedError(
            "kpi_source='sql' is not available yet; the DQN KPI table schema is pending."
        )
    from pptcreator.kpi.stub_source import StubKpiSource

    return StubKpiSource()


def run(event: dict | None, source: KpiSource | None = None) -> dict:
    event = _normalise_event(event)
    mode = event.get("mode", "scheduled")
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode!r}; expected one of {MODES}.")

    source = source or get_kpi_source()
    current = event.get("current_period") or current_calendar_week()
    reference = event.get("reference_period") or default_reference_week()

    if mode == "manual":
        request = ReportRequest.create(
            brand=event["brand"],
            current_period=current,
            reference_period=event.get("reference_period") or reference,
            recipients=event.get("recipients") or [],
            kpi_ids=event.get("kpi_ids"),
            language=event.get("language"),
            target_file_name=event.get("target_file_name"),
        )
        outcomes = [steer_kpi_deck_process(request, source)]
    else:
        outcomes = steer_scheduled_kpi_decks(
            source,
            current_period=current,
            default_reference_period=reference,
            only_send_now=(mode == "adhoc"),
        )

    return _summary(mode, outcomes)


def handler(event, context):
    request_id = getattr(context, "aws_request_id", None)
    logging.info(f"Invocation {request_id} with event: {json.dumps(event, default=str)}")
    try:
        summary = run(event)
    except Exception as exc:
        logging.exception(f"Invocation {request_id} failed: {exc}")
        raise
    logging.info(f"Invocation {request_id} finished: {json.dumps(summary, default=str)}")
    return summary


# ------------------------------------------------------------------------------ #


def _normalise_event(event) -> dict:
    if event is None:
        return {}
    if isinstance(event, str):
        event = json.loads(event)
    if not isinstance(event, dict):
        raise ValueError(f"Unsupported event type {type(event).__name__}.")
    # EventBridge scheduled rules wrap custom input in "detail" only for custom events;
    # a plain constant input arrives as the event itself. Support both.
    if "mode" not in event and isinstance(event.get("detail"), dict):
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
# CLI for local runs: `poetry run pptcreator manual --brand Audi --reference KW37`
# ------------------------------------------------------------------------------ #


def cli():
    import typer

    app = typer.Typer(add_completion=False, help="VW Autoreport local runner")

    @app.command()
    def manual(
        brand: str = typer.Option(..., help="Brand, e.g. Audi"),
        reference: str = typer.Option(..., help="Reference period, e.g. KW37"),
        current: str | None = typer.Option(None, help="Current period, default: this week"),
        recipient: list[str] = typer.Option([], help="Recipient e-mail (repeatable)"),
        kpi: list[str] = typer.Option([], help="KPI id subset (repeatable)"),
    ):
        event = {
            "mode": "manual",
            "brand": brand,
            "reference_period": reference,
            "current_period": current,
            "recipients": recipient,
            "kpi_ids": kpi or None,
        }
        typer.echo(json.dumps(run(event), indent=2, default=str))

    @app.command()
    def scheduled(
        current: str | None = typer.Option(None),
        reference: str | None = typer.Option(None),
    ):
        event = {"mode": "scheduled", "current_period": current, "reference_period": reference}
        typer.echo(json.dumps(run(event), indent=2, default=str))

    app()


if __name__ == "__main__":
    cli()
