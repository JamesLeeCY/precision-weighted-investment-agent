"""I041 計數：PTT Stock 板標題提及市值前 1000 名股票的每日篇數（只看標題，不看報酬）。

用法（於專案根目錄；先執行 analysis/fetch_ptt_titles.py）：
    .venv/Scripts/python analysis/ptt_counts.py            # 產生每日計數與股名比對診斷
輸出：
- data_cache/events/ptt_daily_counts.csv：交易日 × 股票代號的提及篇數（交易日 D 計入台北時間 D 前一交易日 13:30 之後、D 當日 13:30 以前的文章）
- docs/ptt_name_check.md：各股名的提及總數與例句（用來在看報酬前人工固定歧義排除名單）

規則（點子卡 research/ideas/I041-ptt-discussion-surge-attention.md）：
- 比對對象：文章所在年度的市值前 1000 名成員股名（config/universe_mcap_membership.csv），最長優先、不重複計算；
  四碼代號只在 2000–2030 以外使用（避免與年份衝突），且前後不可接數字。每篇對同一股票只算 1 次；含 Re: 回文。
- 排除名單 AMBIGUOUS（股名在標題中多半不是指該公司）在看報酬前固定，見 docs/ptt_name_check.md。
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TITLES = ROOT / "data_cache" / "events" / "ptt_stock_titles.csv"
OUT = ROOT / "data_cache" / "events" / "ptt_daily_counts.csv"
CHECK = ROOT / "docs" / "ptt_name_check.md"
MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"
# 看報酬前、依 docs/ptt_name_check.md 人工固定（股名在標題中多半指別的東西）
AMBIGUOUS: set[str] = {   # 2026-10-22 依 docs/ptt_name_check.md 例句與 151–600 名股名清單固定（尚未看任何報酬）
    "三星", "世界", "國產", "統一", "大量", "數字", "中華", "大成", "聯合", "全新", "全台", "冠軍", "新興", "恆大", "中天",
    "全國", "幸福", "傳奇", "信義", "台南", "南港", "大樹", "大田", "帝寶", "大華", "華夏", "藍天", "佳能", "正文", "至上",
    "中化", "華東", "大中", "長興", "東森"}


def trading_days() -> pd.DatetimeIndex:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "analysis"))
    import leg_probe as lp
    from data.fetch_financials import FinMindClient

    return pd.DatetimeIndex(lp.market_tri(FinMindClient()).index)


def matchers(mem: pd.DataFrame) -> dict[int, tuple[re.Pattern, dict]]:
    out = {}
    for y, g in mem.groupby("year"):
        g = g[g["rank"] <= 1000]
        names = {r.stock_name: r.stock_id for r in g.itertuples() if r.stock_name not in AMBIGUOUS and len(r.stock_name) >= 2}
        codes = {r.stock_id: r.stock_id for r in g.itertuples() if not (2000 <= int(r.stock_id) <= 2030)}
        alt = sorted(names, key=len, reverse=True)
        pat = re.compile("(" + "|".join(re.escape(n) for n in alt) + r")|(?<!\d)(" + "|".join(codes) + r")(?!\d)")
        out[int(y)] = (pat, {**names, **codes})
    return out


def article_hits(df: pd.DataFrame, mem: pd.DataFrame) -> pd.DataFrame:
    M = matchers(mem)
    rows = []
    years = sorted(M)
    for r in df.itertuples():
        y = min(max(r.local.year, years[0]), years[-1])
        pat, lut = M[y]
        hit = set()
        for m in pat.finditer(str(r.title)):
            hit.add(lut[m.group(1) or m.group(2)])
        rows += [(r.aid, r.local, sid) for sid in hit]
    return pd.DataFrame(rows, columns=["aid", "local", "stock_id"])


def main():
    t = pd.read_csv(TITLES, dtype={"aid": str, "title": str}).drop_duplicates("aid")
    t["local"] = pd.to_datetime(t["ts"], unit="s") + pd.Timedelta(hours=8)
    t = t[t["local"] >= "2018-06-01"]
    mem = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str})
    hits = article_hits(t, mem)
    days = trading_days()
    # 交易日 D：前一交易日 13:30 < 文章時間 ≤ D 13:30
    cut = days + pd.Timedelta(hours=13, minutes=30)
    k = cut.searchsorted(hits["local"].to_numpy(), side="left")
    hits = hits[k < len(days)].assign(day=days[k[k < len(days)]])
    cnt = hits.groupby(["day", "stock_id"]).size().unstack(fill_value=0).reindex(days[(days >= t["local"].min().normalize()) & (days <= t["local"].max())], fill_value=0)
    cnt.to_csv(OUT)
    # 診斷：各股名提及總數與例句
    names = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["stock_name"]
    tot = hits.groupby("stock_id").size().sort_values(ascending=False)
    ex = t.set_index("aid")["title"]
    L = ["# I041 PTT 股名比對診斷（只看標題，未看報酬）", "",
         f"文章 {len(t):,} 篇（{t['local'].min():%Y-%m-%d} ~ {t['local'].max():%Y-%m-%d}），有提及前 1000 名者 {hits['aid'].nunique():,} 篇、提及 {len(hits):,} 次。", "",
         "提及最多的 150 檔與 3 則例句（用來檢查股名歧義）：", "", "| 代號 | 股名 | 篇數 | 例句 |", "|---|---|---|---|"]
    for sid, n in tot.head(150).items():
        aids = hits.loc[hits["stock_id"] == sid, "aid"].sample(min(3, n), random_state=0)
        L.append(f"| {sid} | {names.get(sid, '')} | {n} | " + "；".join(str(ex.get(a, ""))[:40].replace("|", "／") for a in aids) + " |")
    CHECK.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[ptt] 計數 → {OUT}（{cnt.shape[0]} 日 × {cnt.shape[1]} 檔）；診斷 → {CHECK}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
