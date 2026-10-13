"""下載借券賣出與融券的每日餘額／額度（TaiwanDailyShortSaleBalances），供可借量檢查。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fetch_short_balances.py 300
每檔 1 次呼叫；資料只到 2026-05-31。客戶端遇額度上限會自動等待，可中斷後重跑接續。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient  # noqa: E402

START, END = "2018-06-01", "2026-05-31"


def main(top_n: int):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    ids = sorted(m.loc[m["rank"] <= top_n, "stock_id"].unique())
    client = FinMindClient()
    empty = 0
    for k, sid in enumerate(ids):
        if client.get("TaiwanDailyShortSaleBalances", sid, START, END).empty:
            empty += 1
        if k % 50 == 0:
            print(f"  {k}/{len(ids)} {sid}", flush=True)
    print(f"前 {top_n}：{len(ids)} 檔完成；空資料 {empty} 檔")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
