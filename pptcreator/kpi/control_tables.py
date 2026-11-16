"""Reads control-table rows for the brand policy, from pycore or an explicit engine.

The Lambdas use pycore's ``data_repo`` (``engine=None``); local tools such as
``python -m pptcreator.preview`` run with ``RESOURCE_TYPE=MEMORY`` and pass the ReportDB
engine so the policy is read from the real control tables.
"""

from __future__ import annotations

import logging

import pandas as pd
import sqlalchemy as sa
from pycore.easy import data_repo
from pycore.schemas import Filter, FilterOperator
from sqlalchemy.orm import DeclarativeBase


def read_control_table(
    model: type[DeclarativeBase],
    columns: list[str],
    values: list,
    engine=None,
) -> pd.DataFrame:
    """Rows of ``model`` where ``columns[i] == values[i]``; empty frame on any failure."""
    if engine is not None:
        table = model.__table__
        stmt = sa.select(table).where(
            *(table.c[column] == value for column, value in zip(columns, values))
        )
        with engine.connect() as con:
            return pd.read_sql(stmt, con)

    filters = [
        Filter(type=FilterOperator.equal, name=column, value=value)
        for column, value in zip(columns, values)
    ]
    data = data_repo.read_table_with_filters(table=model, filters=filters)
    return pd.DataFrame() if data is None else data


def read_control_table_safe(
    model: type[DeclarativeBase],
    columns: list[str],
    values: list,
    engine=None,
) -> pd.DataFrame:
    """Like ``read_control_table`` but never raises; a missing table means "not configured"."""
    try:
        return read_control_table(model, columns, values, engine)
    except Exception as exc:  # missing table, no DB, transient connection error
        logging.warning(
            f"Could not read {model.__tablename__} for {dict(zip(columns, values))}: {exc}"
        )
        return pd.DataFrame()
