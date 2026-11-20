"""Updates T_Control_Autoreport_Runs after rendering a deck.

pycore's DataRepository has no UPDATE helper, so the statement is built with SQLAlchemy
Core against ``easy.database.engine``. It is safe to call when the table does not exist
yet (it logs and returns), so a missing audit table never blocks a report.

The 'processing' claim is written by vw-autoreport-detect before the state machine starts.
"""

from __future__ import annotations

import datetime as dt
import logging

import sqlalchemy as sa
from pycore.easy import database

from pptcreator.models.models import AutoreportRecipients, AutoreportRuns


def reset_send_now(recipient_id: int | None) -> None:
    """Set send_now = 0 after a failed render, so detect does not pick it up again."""
    if recipient_id is None:
        return
    table = AutoreportRecipients.__table__
    stmt = sa.update(table).where(table.c.id == recipient_id, table.c.send_now == True).values(send_now=False)  # noqa: E712
    try:
        with database.engine.begin() as con:
            con.execute(stmt)
    except Exception as exc:
        logging.warning(f"Could not reset send_now for recipient {recipient_id}: {exc}")


def update_status(
    run_id: str | None,
    brand: str,
    reference_period: str,
    *,
    status: str,
    recipient_id: int | None = None,
    error: str | None = None,
) -> None:
    """Update the claimed row of one deck.

    Run id plus recipient id identify the row, so older runs of the same recipient are
    left untouched; without a recipient id (manual runs) brand and reference period are used.
    """
    if not run_id and recipient_id is None:
        return
    table = AutoreportRuns.__table__
    values = {"status": status, "updated_at": dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)}
    if error is not None:
        values["error"] = error[:4000]

    conditions = []
    if run_id:
        conditions.append(table.c.run_id == run_id)
    if recipient_id is not None:
        conditions.append(table.c.recipient_id == recipient_id)
    else:
        conditions.append(table.c.brand == brand)
        conditions.append(table.c.reference_period == reference_period)
    stmt = sa.update(table).where(*conditions).values(**values)
    try:
        with database.engine.begin() as con:
            con.execute(stmt)
    except Exception as exc:
        logging.warning(f"Could not update run log for {run_id}/{brand}/{reference_period}: {exc}")
