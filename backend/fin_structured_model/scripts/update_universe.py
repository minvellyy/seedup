from pathlib import Path
from src.config import SETTINGS
from src.universe import download_corp_codes, parse_corp_codes, save_universe_parquet
from src.utils import ensure_dir

def main():
    base = Path(SETTINGS.data_dir)
    raw = ensure_dir(base / "raw")
    processed = ensure_dir(base / "processed")

    xml_path = download_corp_codes(raw / "corpCode.xml")
    df = parse_corp_codes(xml_path)

    # 최소 유니버스: ticker-corp_code-name
    df = df[["ticker", "corp_code", "corp_name", "modify_date"]].drop_duplicates()
    save_universe_parquet(df, processed / "universe.parquet")
    print(f"Saved universe: {processed / 'universe.parquet'} rows={len(df)}")

if __name__ == "__main__":
    main()