"""SQL Server engines for the two DQN servers (INT and PROD).

pycore builds one engine from ``LOCAL_SQLSERVER_CONN_STR`` (``database.engine``); that
stays the *primary* server and is used for the control tables and the Control Center
data. ``secondary_engine`` adds the second server, configured with
``LOCAL_SQLSERVER_CONN_STR_2``, for sources that live there (e.g. the backend KPI table
in ``MasterDataDB``). Without the second connection string both point at the primary
server, so local runs keep working with a single server.

Never write through these engines in this project: the DQN databases are read-only,
especially the PROD one on port 9435.
"""

from __future__ import annotations

import logging
import os
import pathlib
import urllib.parse

import sqlalchemy as sa
from pycore.easy import database

_CACHE: dict[str, sa.Engine] = {}
_LOADED_ENV = False


def _load_env() -> None:
    """Make ``.env`` visible as real environment variables (pycore only does this when
    it is imported first, which is not guaranteed for ad-hoc scripts)."""
    global _LOADED_ENV
    if _LOADED_ENV:
        return
    _LOADED_ENV = True
    path = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def _engine_from_conn_str(name: str, conn_str: str) -> sa.Engine:
    if name not in _CACHE:
        url = "mssql+pyodbc:///?odbc_connect=" + urllib.parse.quote_plus(conn_str)
        _CACHE[name] = sa.create_engine(url, pool_pre_ping=True)
    return _CACHE[name]


def primary_engine() -> sa.Engine:
    """The server pycore uses: control tables and Control Center data."""
    return database.engine


def secondary_engine() -> sa.Engine:
    """The second server (``LOCAL_SQLSERVER_CONN_STR_2``); falls back to the primary."""
    _load_env()
    conn_str = os.getenv("LOCAL_SQLSERVER_CONN_STR_2")
    if not conn_str or conn_str.startswith("Driver={ODBC Driver 18 for SQL Server};Server=<"):
        return primary_engine()
    return _engine_from_conn_str("secondary", conn_str)


def engine_for(name: str | None = None) -> sa.Engine:
    """``'secondary'`` for the second server, anything else -> the primary one."""
    if (name or "").strip().lower() in ("secondary", "prod", "2"):
        return secondary_engine()
    return primary_engine()


def describe() -> dict[str, str]:
    """Server/database of both engines, for logging and the check script (no secrets)."""
    _load_env()
    out: dict[str, str] = {}
    for name, engine in (("primary", primary_engine()), ("secondary", secondary_engine())):
        try:
            with engine.connect() as con:
                row = con.execute(sa.text("SELECT @@SERVERNAME, DB_NAME()")).first()
                out[name] = f"{row[0]} / {row[1]}"
        except Exception as exc:  # reported, not raised: a check must not crash
            out[name] = f"unavailable ({type(exc).__name__})"
    return out
