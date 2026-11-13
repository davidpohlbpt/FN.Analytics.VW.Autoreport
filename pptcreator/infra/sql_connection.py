"""SQL Server connection string from AWS SSM Parameter Store.

The SSM parameter holds an ADO.NET style string, e.g.
``Server=host,1433;Initial Catalog=ReportDB;User ID=user;Password=secret``.
It is converted to an ODBC string and exported as ``LOCAL_SQLSERVER_CONN_STR`` /
``LOCAL_SQLSERVER_DB`` *before* pycore is imported, because pycore reads both at
import time.

Environment variables:
    SQL_CONN_SSM_PARAM   name of the SSM parameter; unset -> nothing happens
    SQL_ODBC_DRIVER      default 'ODBC Driver 18 for SQL Server' (installed in the image)
    SQL_ENCRYPT          default 'yes'
    SQL_TRUST_SERVER_CERTIFICATE  default 'yes' (RDS CA is not in the image trust store)
"""

from __future__ import annotations

import logging
import os

_KEYS = {
    "server": ("server", "data source", "address", "addr"),
    "database": ("initial catalog", "database"),
    "user": ("user id", "uid", "user"),
    "password": ("password", "pwd"),
}


def parse_connection_string(value: str) -> dict[str, str]:
    """``Key=Value;...`` -> {'server', 'database', 'user', 'password'}.

    Keys are case-insensitive and may contain spaces ('Initial Catalog', 'User ID').
    Values are kept as-is, so passwords may contain spaces or '='.
    """
    raw: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        key, _, val = part.partition("=")
        raw[" ".join(key.strip().lower().split())] = val.strip()

    result = {}
    for name, aliases in _KEYS.items():
        found = next((raw[a] for a in aliases if raw.get(a)), None)
        if found is None:
            raise ValueError(f"Connection string has no {name} (expected one of {aliases}).")
        result[name] = found
    return result


def to_odbc(parts: dict[str, str]) -> str:
    driver = os.environ.get("SQL_ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
    encrypt = os.environ.get("SQL_ENCRYPT", "yes")
    trust = os.environ.get("SQL_TRUST_SERVER_CERTIFICATE", "yes")
    # Braces protect values containing ';' or '}' (doubled inside braces).
    pwd = "{" + parts["password"].replace("}", "}}") + "}"
    return (
        f"Driver={{{driver}}};Server={parts['server']};Database={parts['database']};"
        f"Uid={parts['user']};Pwd={pwd};Encrypt={encrypt};TrustServerCertificate={trust};"
    )


def configure_from_ssm() -> None:
    """Export LOCAL_SQLSERVER_CONN_STR/DB from SSM if SQL_CONN_SSM_PARAM is set."""
    name = os.environ.get("SQL_CONN_SSM_PARAM")
    if not name:
        return

    import boto3

    region = os.environ.get("AWS_REGION_NAME") or os.environ.get("AWS_REGION")
    response = boto3.client("ssm", region_name=region).get_parameter(Name=name, WithDecryption=True)
    parts = parse_connection_string(response["Parameter"]["Value"])

    os.environ["LOCAL_SQLSERVER_CONN_STR"] = to_odbc(parts)
    os.environ.setdefault("LOCAL_SQLSERVER_DB", parts["database"])
    os.environ.setdefault("APP_DB_NAME", parts["database"])
    logging.info(f"SQL connection from SSM {name}: server {parts['server']}, database {parts['database']}")
