"""下載單腿探針需要的逐檔資料（全市場市值股票池前 N 名的 8 年聯集）。

用法（於專案根目錄；先執行 analysis/build_universe_mcap.py）：
    .venv/Scripts/python analysis/fetch_leg_data.py 300      # 前 300 名（之後可再跑 500、1000，已抓過的會命中快取）

每檔 7 次呼叫（除權息、分割、月營收、融資融券、借券、三大法人、外資持股）；價量資料在建股票池時已抓。
資料只到 2026-05-31（之後保留給前瞻驗證）。客戶端遇額度上限會自動等待，可中斷後重跑接續。
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient, get_adjustment_events  # noqa: E402

START, END = "2018-06-01", "2026-05-31"
DATASETS = [
    ("TaiwanStockMonthRevenue", "2017-01-01", None),
    ("TaiwanStockMarginPurchaseShortSale", START, END),
    ("TaiwanStockSecuritiesLending", START, END),
    ("TaiwanStockInstitutionalInvestorsBuySell", START, END),
    ("TaiwanStockShareholding", START, END),
]


def main(top_n: int):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    m = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    ids = sorted(m.loc[m["rank"] <= top_n, "stock_id"].unique())
    client = FinMindClient()
    empty = {ds: 0 for ds, _, _ in DATASETS}
    for k, sid in enumerate(ids):
        get_adjustment_events(client, sid + ".TW", START, END)
        for ds, s, e in DATASETS:
            if client.get(ds, sid, s, e).empty:
                empty[ds] += 1
        if k % 50 == 0:
            print(f"  {k}/{len(ids)} {sid}", flush=True)
    print(f"前 {top_n}：{len(ids)} 檔完成；空資料檔數 {empty}")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
