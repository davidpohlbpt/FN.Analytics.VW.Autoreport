import pandas as pd


def get_unique_value(df: pd.DataFrame, column: str, template_id: int):
    values = df[column].unique()
    if len(values) != 1:
        raise ValueError(
            f"Expected one {column} for template {template_id}, got {len(values)}"
        )
    return values[0]
