"""I030 小型股版月營收驚奇（點子卡 research/ideas/I030-smallcap-sue-501-1000.md，檢定計畫看結果前固定）——階段一。

用法（於專案根目錄；資料皆已快取，0 次請求）：
    .venv/Scripts/python analysis/smallcap_sue.py
輸出 docs/smallcap_sue.md。

設計（依點子卡；補充以「補」標示）：
- 樣本：每年市值前 1000 名（成員檔），依當年名次分四組：1–300、301–500、501–750、751–1000；另報 1–500 與 501–1000。
- 訊號：SUE（data/revenue_signal.revenue_surprise，原始值），換倉日 = 營收公告期限次一交易日（event_dates），產業內排序；不調參數。
- 產業內 Spearman IC（20 日、60 日）；t 值：20 日用一般 t、60 日用 Newey-West（落後 3，補）。
- 不扣成本的產業內前／後 30% 等權報酬差（20 日）。
- 階段一通過：第 501–1000 名 20 日 IC 兩段 > 0、全期 t > 2，且全期 IC ≥ 前 500 名全期 IC − 0.005。不成立即停止（不抓借券資料、不做階段二）。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import corp_event_study as ce  # noqa: E402
import leg_probe as lp  # noqa: E402
import sue_streak as ss  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.revenue_signal import event_dates  # noqa: E402
from sue_attention import nw_t  # noqa: E402

GROUPS = {"1–300": (1, 300), "301–500": (301, 500), "501–750": (501, 750), "751–1000": (751, 1000), "1–500": (1, 500), "501–1000": (501, 1000)}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    S = ce.Sample(client, 1, 1000, lp.market_tri(client), lp.tx_continuous(client))
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    rank = {(int(r.year), r.stock_id + ".TW"): int(r.rank) for r in mem.itertuples()}
    sue = ss.sue_monthly(client, S.tickers)
    sched = [d for d in event_dates(S.days) if pd.Timestamp("2019-01-01") <= d < lp.HOLDOUT]
    ic = {g: {20: {}, 60: {}} for g in GROUPS}
    ls = {g: {} for g in GROUPS}
    for d in sched:
        k = int(S.days.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if k + 20 >= S.limit or mo not in sue.index:
            continue
        m = S.member.iloc[k]
        s = sue.loc[mo].reindex(S.tickers)[m.to_numpy(bool)].dropna()
        rk = pd.Series({t: rank.get((d.year, t), np.nan) for t in s.index})
        f20 = (S.adj.iloc[k + 20] / S.adj.iloc[k] - 1)
        f60 = (S.adj.iloc[k + 60] / S.adj.iloc[k] - 1) if k + 60 < S.limit else None
        for g, (lo, hi) in GROUPS.items():
            x = s[(rk >= lo) & (rk <= hi)]
            if len(x) < 30:
                continue
            ic[g][20][d] = lp.within_ic(x, f20, sector)
            if f60 is not None:
                ic[g][60][d] = lp.within_ic(x, f60, sector)
            r = x.groupby(sector.reindex(x.index)).rank(pct=True)
            a, b = f20.reindex(x.index)[r > 0.7].dropna(), f20.reindex(x.index)[r <= 0.3].dropna()
            if len(a) and len(b):
                ls[g][d] = a.mean() - b.mean()

    def segs(x: dict, lag=None):
        x = pd.Series(x, dtype=float).dropna()
        def t(y):
            if len(y) < 3:
                return (float("nan"), float("nan"), len(y))
            tv = nw_t(y, lag) if lag else float(y.mean() / (y.std(ddof=1) / math.sqrt(len(y))))
            return (float(y.mean()), tv, len(y))
        return {"2019–2022": t(x[x.index < lp.SPLIT]), "2023–2026/04": t(x[x.index >= lp.SPLIT]), "全期": t(x)}
    fic = lambda v: "—" if v[0] != v[0] else f"{v[0]:+.3f}（{v[1]:.1f}，{v[2]}）"  # noqa: E731
    fls = lambda v: "—" if v[0] != v[0] else f"{v[0]:+.2%}（{v[1]:.1f}）"  # noqa: E731
    L = ["# I030 小型股版月營收驚奇——階段一（自動產生）", "",
         "由 [analysis/smallcap_sue.py](../analysis/smallcap_sue.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（SUE vs 換倉後報酬，−1～1），括號為（t 值，換倉日數；60 日用 Newey-West）；"
         "多空差 = 產業內 SUE 前 30% − 後 30% 的 20 日等權報酬，未扣成本。研究結果，非投資建議。", "",
         "| 名次組 | IC 20 日：2019–2022 | 2023–2026/04 | 全期 | IC 60 日：全期 | 多空差 20 日（未扣成本）：全期 |", "|---|---|---|---|---|---|"]
    res = {}
    for g in GROUPS:
        a, b = segs(ic[g][20]), segs(ic[g][60], 3)
        c = segs(ls[g])
        res[g] = a
        L.append(f"| {g} | {fic(a['2019–2022'])} | {fic(a['2023–2026/04'])} | {fic(a['全期'])} | {fic(b['全期'])} | {fls(c['全期'])} |")
    sm, big = res["501–1000"], res["1–500"]
    c1 = sm["2019–2022"][0] > 0 and sm["2023–2026/04"][0] > 0 and sm["全期"][1] > 2
    c2 = sm["全期"][0] >= big["全期"][0] - 0.005
    L += ["", "## 階段一判定", "",
          f"1. 第 501–1000 名 20 日 IC 兩段 > 0、全期 t > 2：{fic(sm['全期'])} → {'✓' if c1 else '✗'}",
          f"2. 全期 IC 不低於前 500 名 − 0.005：{sm['全期'][0]:+.3f} vs {big['全期'][0]:+.3f} − 0.005 → {'✓' if c2 else '✗'}", "",
          f"**結論：{'階段一通過，進行階段二（需抓第 501–1000 名借券資料約 1,222 次）' if c1 and c2 else '階段一未通過，停止'}**"]
    (ROOT / "docs" / "smallcap_sue.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
