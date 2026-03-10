import json

def show(name, p):
    with open(p, "r", encoding="utf-8") as f:
        m = json.load(f)
    feats = m.get("features", [])
    print(f"\n--- {name} ---")
    print("n_features:", m.get("n_features"))
    print("features_count:", len(feats))
    print("features:", feats)

show("STOCK", "data/outputs/models/stock_lgbm_bin_y_5.meta.json")
show("ETF", "data/outputs/models/etf_lgbm_bin_y_5.meta.json")
show("MARKET", "data/outputs/models/market_bin_y_5.meta.json")