"""I009 當沖比：抓 FinMind TaiwanStockDayTrading（逐檔，2014-01 起全歷史；點子卡 research/ideas/I009-day-trading-ratio.md）。

用法（於專案根目錄；可中斷，已快取的股票不重抓；FinMind 額度不足時 client 會自動等待）：
    .venv/Scripts/python analysis/fetch_daytrading.py
股票：config/universe_mcap_membership.csv 中曾為市值前 1000 名的所有股票（主樣本前 500、驗證第 501–1000 名）。
研究用資料蒐集，非投資建議。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient  # noqa: E402


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    ids = sorted(mem.loc[mem["rank"] <= 1000, "stock_id"].unique())
    print(f"共 {len(ids)} 檔", flush=True)
    empty = 0
    for k, sid in enumerate(ids):
        d = client.get("TaiwanStockDayTrading", sid, "2014-01-01", "2026-05-31")
        empty += d.empty
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/{len(ids)}（無資料 {empty} 檔）", flush=True)
    print(f"DONE（無資料 {empty} 檔）", flush=True)


if __name__ == "__main__":
    main()
