"""Check both SQL Server connections (INT 9434 / PROD 9435) and read a sample row.

    python -m pptcreator.utils.check_db

Read-only: only SELECTs, and only on the control tables. Prints server, database and
the newest recipient row of each server so that a missing table or a wrong login is
visible immediately. Exit code 0 when both servers answer.
"""

from __future__ import annotations

import sqlalchemy as sa

from pptcreator.utils.db import describe, primary_engine, secondary_engine

QUERY = """
SELECT TOP 1 id, template_id, email, brand_id, brand_name, report_week, comparison_week,
       send_now, IsDeleted, last_report_time
FROM control.T_Control_Autoreport_Recipients
ORDER BY id DESC
"""


def main() -> int:
    ok = True
    for name, engine in (("primary (INT)", primary_engine()), ("secondary (PROD)", secondary_engine())):
        print(f"--- {name} ---")
        try:
            with engine.connect() as con:
                server, db = con.execute(sa.text("SELECT @@SERVERNAME, DB_NAME()")).first()
                print(f"connected: {server} / {db}")
                try:
                    row = con.execute(sa.text(QUERY)).mappings().first()
                except Exception as exc:
                    print(f"control table not readable: {type(exc).__name__}: {exc}")
                    ok = False
                    continue
                print(f"recipient row: {dict(row) if row else '(table empty)'}")
        except Exception as exc:
            print(f"NOT reachable: {type(exc).__name__}: {exc}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
