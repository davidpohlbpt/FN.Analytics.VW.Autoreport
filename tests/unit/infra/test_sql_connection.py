import os

import pytest

from pptcreator.infra import sql_connection


def test_parse_ado_connection_string_with_spaces_in_keys_and_password():
    parts = sql_connection.parse_connection_string(
        "Server=db.rds.amazonaws.com,1433; Initial Catalog=ReportDB;User ID=svc;Password=a b=c;"
    )

    assert parts == {"server": "db.rds.amazonaws.com,1433", "database": "ReportDB", "user": "svc", "password": "a b=c"}


def test_parse_rejects_missing_password():
    with pytest.raises(ValueError, match="password"):
        sql_connection.parse_connection_string("Server=x;Initial Catalog=y;User ID=z")


def test_configure_from_ssm_exports_odbc_string(monkeypatch):
    class FakeSsm:
        def get_parameter(self, Name, WithDecryption):
            assert (Name, WithDecryption) == ("Database-ReportDB", True)
            return {"Parameter": {"Value": "Server=host;Initial Catalog=ReportDB;User ID=u;Password=p}w"}}

    monkeypatch.setattr("boto3.client", lambda service, region_name=None: FakeSsm())
    monkeypatch.setenv("SQL_CONN_SSM_PARAM", "Database-ReportDB")
    # delenv records the original state, so values set by the code are undone afterwards
    for key in ("LOCAL_SQLSERVER_CONN_STR", "LOCAL_SQLSERVER_DB", "APP_DB_NAME", "SQL_ODBC_DRIVER"):
        monkeypatch.delenv(key, raising=False)

    sql_connection.configure_from_ssm()

    assert os.environ["LOCAL_SQLSERVER_CONN_STR"] == (
        "Driver={ODBC Driver 18 for SQL Server};Server=host;Database=ReportDB;"
        "Uid=u;Pwd={p}}w};Encrypt=yes;TrustServerCertificate=yes;"
    )
    assert os.environ["LOCAL_SQLSERVER_DB"] == "ReportDB"
