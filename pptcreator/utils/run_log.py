"""Writes to T_Control_Autoreport_Runs and clears ad hoc flags.

pycore's DataRepository has no UPDATE helper, so the statements are built with
SQLAlchemy Core against ``easy.database.engine``. All functions are safe to call when
the tables do not exist yet (they log and return) so that a missing audit table never
blocks a report.
"""

from __future__ import annotations

import datetime as dt
import logging

import sqlalchemy as sa
from pycore.easy import data_repo, database

from pptcreator.models.models import AutoreportRecipients, AutoreportRuns


def log_queued(requests: list) -> None:
    """One row per ReportRequest with status 'queued'."""
    if not requests:
        return
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "run_id": r.run_id,
            "template_id": r.template_id,
            "brand": r.brand,
            "current_period": str(r.current_period),
            "reference_period": str(r.reference_period),
            "recipients": ";".join(r.recipients)[:4000],
            "trigger": r.trigger,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }
        for r in requests
    ]
    try:
        data_repo.write_table(model=AutoreportRuns, df=rows)
    except Exception as exc:
        logging.warning(f"Could not write run log ({len(rows)} rows): {exc}")


def update_status(
    run_id: str | None,
    brand: str,
    reference_period: str,
    *,
    status: str,
    s3_key: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
) -> None:
    if not run_id:
        return
    table = AutoreportRuns.__table__
    values = {"status": status, "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)}
    if s3_key is not None:
        values["s3_key"] = s3_key[:1000]
    if message_id is not None:
        values["message_id"] = message_id[:200]
    if error is not None:
        values["error"] = error[:4000]
    stmt = (
        sa.update(table)
        .where(table.c.run_id == run_id, table.c.brand == brand, table.c.reference_period == reference_period)
        .values(**values)
    )
    try:
        with database.engine.begin() as con:
            con.execute(stmt)
    except Exception as exc:
        logging.warning(f"Could not update run log for {run_id}/{brand}: {exc}")


def clear_send_now(recipient_ids: list[int]) -> int:
    """Reset ``send_now`` for the given recipient rows. Returns the number of rows updated."""
    if not recipient_ids:
        return 0
    table = AutoreportRecipients.__table__
    stmt = sa.update(table).where(table.c.id.in_(list(recipient_ids))).values(send_now=False)
    try:
        with database.engine.begin() as con:
            count = con.execute(stmt).rowcount
        logging.info(f"send_now cleared for {count} recipient row(s).")
        return count
    except Exception as exc:
        logging.warning(f"Could not clear send_now for {recipient_ids}: {exc}")
        return 0
