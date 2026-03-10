import pandas as pd

def main():
    path = "data/processed/market/kospi_features.parquet"
    df = pd.read_parquet(path)

    for h in [5, 10]:
        col = f"y_{h}"
        if col not in df.columns:
            print(f"[MISS] {col} not found in {path}")
            continue

        vc = df[col].value_counts(dropna=False).sort_index()
        ratio = (vc / vc.sum()).round(3)

        print(f"== {col} value_counts ==")
        print(vc.to_string())
        print(f"== {col} ratio ==")
        print(ratio.to_string())
        print("")

if __name__ == "__main__":
    main()