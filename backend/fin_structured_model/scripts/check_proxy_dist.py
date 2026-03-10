import pandas as pd
from pathlib import Path

files = [
    ("2023","Q1"),("2023","H1"),("2023","Q3"),("2023","FY"),
    ("2024","Q1"),("2024","H1"),("2024","Q3"),("2024","FY"),
]

for y, k in files:
    p = Path(f"data/processed/fin_core_norm_{y}_{k}_CONSOL.parquet")
    df = pd.read_parquet(p)

    if "net_income_proxy" not in df.columns:
        print(y, k, "NO_COL")
        continue

    vc = df["net_income_proxy"].value_counts(dropna=False).to_dict()
    print(y, k, vc)