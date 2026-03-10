from __future__ import annotations
import pandas as pd

def time_train_valid_split(df: pd.DataFrame, date_col: str, valid_days: int = 252):
    df = df.sort_values(date_col)
    dates = df[date_col].drop_duplicates().sort_values()

    if len(dates) <= valid_days + 10:
        raise ValueError("Not enough data for split.")

    split_date = dates.iloc[-valid_days]
    train = df[df[date_col] < split_date]
    valid = df[df[date_col] >= split_date]

    return train, valid