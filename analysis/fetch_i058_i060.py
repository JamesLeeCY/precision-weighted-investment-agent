"""I058、I060、I061 資料：TaiwanStockDividend（前 1500 名聯集＋主要 ETF）與第 1001–1500 名融資融券（只抓未快取者，FinMind 額度不足自動等待）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fetch_i058_i060.py
研究用資料蒐集，非投資建議。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

ETFS = ["0050", "0056", "006208", "00878", "00919", "00929", "00713", "00940", "00939", "00850", "00692", "00900", "00915", "00918", "00934", "00936"]
DIV_START = "2005-01-01"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    c = FinMindClient()
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership_1500.csv", dtype={"stock_id": str})
    ids = sorted(m["stock_id"].unique())
    tail = sorted(m.loc[m["rank"] > 1000, "stock_id"].unique())
    for i, sid in enumerate(tail):
        c.get("TaiwanStockMarginPurchaseShortSale", sid, lp.EV_START, lp.EV_END)
        if i % 100 == 0:
            print(f"融資融券 {i}/{len(tail)}", flush=True)
    for i, sid in enumerate(ETFS + ids):
        c.get("TaiwanStockDividend", sid, DIV_START)
        if i % 100 == 0:
            print(f"股利 {i}/{len(ids) + len(ETFS)}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
