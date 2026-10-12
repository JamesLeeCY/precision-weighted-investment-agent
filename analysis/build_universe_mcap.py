"""建立全市場市值股票池 config/universe_mcap_membership.csv（每年前 1000 檔）。

用法（於專案根目錄；約 3,500 次 FinMind 呼叫，客戶端遇額度上限會自動等待，可中斷後重跑接續）：
    .venv/Scripts/python analysis/build_universe_mcap.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.fetch_financials import FinMindClient  # noqa: E402
from data.universe_mcap import build_membership  # noqa: E402


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    m = build_membership(FinMindClient(), range(2019, 2027))
    out = ROOT / "config" / "universe_mcap_membership.csv"
    m.to_csv(out, index=False, encoding="utf-8")
    print(f"寫入 {out}：{len(m)} 列；各年檔數 {m.groupby('year').size().to_dict()}")
    for n in (300, 500, 1000):
        print(f"前 {n}：8 年聯集 {m[m['rank'] <= n]['stock_id'].nunique()} 檔")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
