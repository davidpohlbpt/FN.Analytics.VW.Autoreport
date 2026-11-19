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

from pptcreator.models.models import AutoreportRuns


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
