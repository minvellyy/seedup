from __future__ import annotations

from scripts.t_90_daily.t_00_build_signal_pack import build_signal_pack


def run_daily(run_pipeline: bool = False, latest_only: bool = True) -> str:
    """
    Daily runner:
    - run_pipeline=False: 이미 생성된 predictions를 사용해 signal_pack만 생성
    - run_pipeline=True : market/stock/etf 예측까지 전부 돌리고 signal_pack 생성
    """
    p = build_signal_pack(run_pipeline=run_pipeline, latest_only=latest_only)
    return str(p)


if __name__ == "__main__":
    out = run_daily(run_pipeline=False, latest_only=True)
    print(out)