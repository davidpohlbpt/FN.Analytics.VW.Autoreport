"""Writes to T_Control_Autoreport_Runs: the claim before a deck is built, the outcome after.

pycore's DataRepository has no UPDATE helper, so the statements are built with
SQLAlchemy Core against ``easy.database.engine``. All functions are safe to call when
the table does not exist yet (they log and return) so that a missing audit table never
blocks a report.

The claim is what keeps the 5-10 minute poller from sending the same row twice: Plan
inserts a row with status 'processing' for every recipient row it hands over, and the
next poll skips rows that already have an open claim.
"""

from __future__ import annotations

import datetime as dt
import logging

import sqlalchemy as sa
from pycore.easy import data_repo, database

from pptcreator.models.models import AutoreportRecipients, AutoreportRuns

OPEN_STATUS = "processing"
"""Rows with this status are claimed; the poller must not pick them up again."""


def log_processing(requests: list) -> None:
    """Claim every deck: one row per ReportRequest with status 'processing'."""
    if not requests:
        return
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "run_id": r.run_id,
            "template_id": r.template_id,
            "recipient_id": r.recipient_id,
            "user_email": ";".join(r.recipients)[:1000] or None,
            "brand": r.brand,
            "primary_date": str(r.current_period),
            "reference_date": str(r.reference_period),
            "trigger": r.trigger,
            "status": OPEN_STATUS,
            "created_at": now,
            "updated_at": now,
        }
        for r in requests
    ]
    try:
        data_repo.write_table(model=AutoreportRuns, df=rows)
    except Exception as exc:
        logging.warning(f"Could not write the run log claim ({len(rows)} rows): {exc}")


def update_status(
    run_id: str | None,
    brand: str,
    reference_period: str,
    *,
    status: str,
    recipient_id: int | None = None,
    s3_key: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
) -> None:
    """Update the claimed row of one deck.

    The recipient id identifies the row; without it (manual runs) brand and reference
    date are used.
    """
    if not run_id and recipient_id is None:
        return
    table = AutoreportRuns.__table__
    values = {"status": status, "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)}
    if s3_key is not None:
        values["s3_key"] = s3_key[:1000]
    if message_id is not None:
        values["message_id"] = message_id[:200]
    if error is not None:
        values["error"] = error[:4000]

    conditions = []
    if recipient_id is not None:
        conditions.append(table.c.recipient_id == recipient_id)
    else:
        conditions.append(table.c.run_id == run_id)
        conditions.append(table.c.brand == brand)
        conditions.append(table.c.reference_date == reference_period)
    stmt = sa.update(table).where(*conditions).values(**values)
    try:
        with database.engine.begin() as con:
            con.execute(stmt)
    except Exception as exc:
        logging.warning(f"Could not update run log for {run_id}/{brand}/{reference_period}: {exc}")


def open_recipient_ids(recipient_ids: list[int]) -> set[int]:
    """Recipient rows that already have an open claim (status 'processing')."""
    if not recipient_ids:
        return set()
    table = AutoreportRuns.__table__
    stmt = sa.select(table.c.recipient_id).where(
        table.c.recipient_id.in_(list(recipient_ids)), table.c.status == OPEN_STATUS
    )
    try:
        with database.engine.connect() as con:
            return {int(row[0]) for row in con.execute(stmt) if row[0] is not None}
    except Exception as exc:
        logging.warning(f"Could not read open claims for {recipient_ids}: {exc}")
        return set()


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
