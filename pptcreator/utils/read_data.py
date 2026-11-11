import pandas as pd
from pycore.easy import data_repo
from pycore.schemas import Filter, FilterOperator
from sqlalchemy.orm import DeclarativeBase


def read_data(
    table: type[DeclarativeBase], columns: list, values: list
) -> pd.DataFrame:

    filters = [
        Filter(type=FilterOperator.equal, name=col, value=val)
        for col, val in zip(columns, values)
    ]
    data = data_repo.read_table_with_filters(table=table, filters=filters)
    return data
