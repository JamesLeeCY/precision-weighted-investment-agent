"""I032 先公告同業的營收驚奇對後公告者的預測（點子卡 research/ideas/I032-early-peer-revenue-transfer-late-announc.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/peer_transfer.py
輸出 docs/peer_transfer.md。

設計（依點子卡；補充以「補」標示）：
- 公告習慣：FinMind 月營收 create_time 的日（2026-05 ~ 2026-10 收錄、同月且 ≤ 16 日，同 analysis/sue_event_entry.announce_habits）；
  先公告者 = 觀察到的每一次都在 7 日（含）以前；後公告者 = 每一次都在 9 日（含）以後；至少要有 4 次觀察（補）。
- PeerSUE：同產業先公告者 SUE（同一可得月份）的平均，至少 2 檔。
- (1) 基本面移轉：每月 Fama-MacBeth，後公告者 SUE = a + b·PeerSUE + c·上月 SUE（皆為原始值，補），b > 0 且全期 t > 2 才繼續 (2)。
- (2) 擴散：後公告者窗口報酬 = 可得月份第 8 日（當天或之前最後一個交易日）收盤 → 公告期限次一交易日（schedule）收盤，減加權指數含息同期報酬；
  PeerReact = 前一月最後交易日收盤 → 第 8 日收盤的個股 − 加權指數報酬（補：以前一日收盤近似第 1 日開盤）。
  每月 Fama-MacBeth：窗口報酬 = a + b1·PeerSUE + b2·PeerReact + log 市值 + 前 20 日報酬（皆為橫斷面百分位 − 0.5）。
- 通過：b1（> 0）或 b2（< 0）兩段同號、全期 |t| > 2 且方向如預期，驗證樣本同號；且依該變數分三組的前後報酬差 > 0.6%。
- 只報告：PeerSUE 對後公告者 schedule 後 20 日報酬的產業內 IC（檢查是否只是 I005 產業動能）。子產業版本未做（補）。
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
import sue_event_entry as see  # noqa: E402
import sue_streak as ss  # noqa: E402


def classify(client, tickers):
    ann = see.announce_habits(client, tickers)
    g = ann.assign(day=ann["ct"].dt.day).groupby("ticker")["day"].agg(["min", "max", "size"])
    g = g[g["size"] >= 4]
    return set(g[g["max"] <= 7].index), set(g[g["min"] >= 9].index)


def build(adj, member, sector, sue, sched, limit, mkt, logcap, early, late):
    rows = []
    days = adj.index
    m = mkt.reindex(days).ffill()
    for d in sched:
        k = int(days.searchsorted(d))
        mo = d.to_period("M").to_timestamp()
        if k + 20 >= limit or mo not in sue.index:
            continue
        prev = mo - pd.offsets.MonthBegin(1)
        k8 = int(days.searchsorted(mo + pd.Timedelta(days=8), side="left")) - 1
        k0 = int(days.searchsorted(mo, side="left")) - 1
        if not (0 <= k0 < k8 < k):
            continue
        mem = member.loc[d]
        s = sue.loc[mo]
        ear = [t for t in early if t in mem.index and bool(mem[t]) and s.get(t) == s.get(t)]
        es = pd.Series({t: s[t] for t in ear})
        peer = es.groupby(sector.reindex(es.index)).agg(["mean", "size"])
        for t in late:
            if t not in mem.index or not bool(mem[t]):
                continue
            sec = sector.get(t)
            if sec not in peer.index or peer.at[sec, "size"] < 2:
                continue
            j = adj.columns.get_loc(t)
            pa = adj.iloc
            win = pa[k, j] / pa[k8, j] - 1 - (m.iloc[k] / m.iloc[k8] - 1)
            react = pa[k8, j] / pa[k0, j] - 1 - (m.iloc[k8] / m.iloc[k0] - 1)
            rows.append({"d": d, "t": t, "sec": sec, "peer": peer.at[sec, "mean"], "sue": s.get(t, np.nan),
                         "sue_lag": sue.loc[prev].get(t, np.nan) if prev in sue.index else np.nan,
                         "win": win, "react": react, "f20": pa[k + 20, j] / pa[k, j] - 1,
                         "lm": logcap.iat[k, j] if logcap is not None else np.nan,
                         "p20": pa[k, j] / pa[max(k - 20, 0), j] - 1})
    return pd.DataFrame(rows)


def fm(df, y, xs):
    out = {}
    for d, g in df.groupby("d"):
        g = g.dropna(subset=[y] + xs)
        if len(g) < 15:
            continue
        X = np.column_stack([np.ones(len(g))] + [g[x].to_numpy(float) for x in xs])
        beta, *_ = np.linalg.lstsq(X, g[y].to_numpy(float), rcond=None)
        out[d] = beta[1:]
    return pd.DataFrame(out, index=xs).T


def tstat(x):
    x = pd.Series(x, dtype=float).dropna()
    return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))


def segs(x):
    return {"2019–2022": tstat(x[x.index < lp.SPLIT]), "2023–2026/04": tstat(x[x.index >= lp.SPLIT]), "全期": tstat(x)}


def ranks(df, cols):
    df = df.copy()
    for c in cols:
        df["r_" + c] = df.groupby("d")[c].rank(pct=True) - 0.5
    return df


def tercile_spread(df, col):
    out = {}
    for d, g in df.groupby("d"):
        g = g.dropna(subset=[col, "win"])
        if len(g) < 9:
            continue
        r = g[col].rank(pct=True)
        out[d] = g.loc[r > 2 / 3, "win"].mean() - g.loc[r <= 1 / 3, "win"].mean()
    return pd.Series(out, dtype=float)


def main():
    import dotenv

    c = lp.prepare(500)
    limit = int(c.adj.index.searchsorted(lp.HOLDOUT))
    mkt = lp.market_tri(c.client)
    early, late = classify(c.client, c.tickers)
    D = build(c.adj, c.member, c.sector, c.sue, c.schedule, limit, mkt, c.logcap, early, late)
    F1 = fm(D, "sue", ["peer", "sue_lag"])
    s1 = segs(F1["peer"])
    D = ranks(D, ["peer", "react", "lm", "p20"])
    F2 = fm(D, "win", ["r_peer", "r_react", "r_lm", "r_p20"])
    s_peer, s_react = segs(F2["r_peer"]), segs(F2["r_react"])
    ic20 = pd.Series({d: lp.within_ic(g.set_index("t")["peer"], g.set_index("t")["f20"], g.set_index("t")["sec"]) if g["sec"].nunique() < len(g) else np.nan
                      for d, g in D.groupby("d")}).dropna()
    dotenv.load_dotenv(ROOT / ".env")
    V = ce.Sample(c.client, 501, 1000, mkt, lp.tx_continuous(c.client))
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vearly, vlate = classify(c.client, V.tickers)
    VD = build(V.adj, V.member, vsec, ss.sue_monthly(c.client, V.tickers), [d for d in c.schedule if d in V.days], V.limit, mkt, V.lmcap, vearly, vlate)
    v1 = segs(fm(VD, "sue", ["peer", "sue_lag"])["peer"])
    VD = ranks(VD, ["peer", "react", "lm", "p20"])
    VF2 = fm(VD, "win", ["r_peer", "r_react", "r_lm", "r_p20"])
    vp, vr = segs(VF2["r_peer"]), segs(VF2["r_react"])

    c1 = s1["全期"][0] > 0 and s1["全期"][1] > 2
    ok_peer = c1 and s_peer["2019–2022"][0] > 0 and s_peer["2023–2026/04"][0] > 0 and s_peer["全期"][1] > 2 and vp["全期"][0] > 0
    ok_react = c1 and s_react["2019–2022"][0] < 0 and s_react["2023–2026/04"][0] < 0 and s_react["全期"][1] < -2 and vr["全期"][0] < 0
    sp_peer, sp_react = segs(tercile_spread(D, "peer")), segs(-tercile_spread(D, "react"))
    cost_ok = (ok_peer and sp_peer["全期"][0] > 0.006) or (ok_react and sp_react["全期"][0] > 0.006)
    fmt = lambda x, p=False: "—" if x[0] != x[0] else (f"{x[0]:+.2%}" if p else f"{x[0]:+.3f}") + f"（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    L = ["# I032 先公告同業的營收驚奇對後公告者的預測（自動產生）", "",
         "由 [analysis/peer_transfer.py](../analysis/peer_transfer.py) 產生；設計見程式開頭（看結果前固定）。"
         "括號為（t 值，月份數）。窗口報酬 = 可得月第 8 日收盤 → 公告期限次一交易日收盤，扣加權指數含息。研究結果，非投資建議。", "",
         f"前 500 名：先公告者 {len(early)} 檔、後公告者 {len(late)} 檔；有 ≥ 2 檔先公告同業的後公告者公司月 {len(D):,} 筆（每月平均 {D.groupby('d').size().mean():.0f} 檔）。"
         f"驗證樣本：先公告 {len(vearly)}、後公告 {len(vlate)}、公司月 {len(VD):,}。", "",
         "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| (1) 後公告者 SUE 對 PeerSUE 係數（控制上月 SUE） | " + " | ".join(fmt(s1[k]) for k in s1) + " |",
         "| (2) 窗口報酬對 PeerSUE（百分位，預期 > 0） | " + " | ".join(fmt(s_peer[k], True) for k in s_peer) + " |",
         "| (2) 窗口報酬對 PeerReact（百分位，預期 < 0） | " + " | ".join(fmt(s_react[k], True) for k in s_react) + " |",
         "| 窗口報酬：PeerSUE 前 − 後三分之一 | " + " | ".join(fmt(sp_peer[k], True) for k in sp_peer) + " |",
         "| 窗口報酬：PeerReact 後 − 前三分之一 | " + " | ".join(fmt(sp_react[k], True) for k in sp_react) + " |",
         "| 驗證 (1) SUE 對 PeerSUE | " + " | ".join(fmt(v1[k]) for k in v1) + " |",
         "| 驗證 (2) PeerSUE | " + " | ".join(fmt(vp[k], True) for k in vp) + " |",
         "| 驗證 (2) PeerReact | " + " | ".join(fmt(vr[k], True) for k in vr) + " |",
         "| 只報告：PeerSUE 對之後 20 日報酬的產業內 IC | " + " | ".join(fmt(v) for v in segs(ic20).values()) + " |", "",
         "## 判定", "",
         f"1. 基本面移轉（PeerSUE 係數 > 0、全期 t > 2）：{fmt(s1['全期'])} → {'✓' if c1 else '✗'}",
         f"2a. 擴散（PeerSUE 兩段 > 0、全期 t > 2、驗證同號）→ {'✓' if ok_peer else '✗'}",
         f"2b. 過度反應（PeerReact 兩段 < 0、全期 t < −2、驗證同號）→ {'✓' if ok_react else '✗'}",
         f"3. 前後三分之一報酬差 > 0.6%（現股來回成本）→ {'✓' if cost_ok else '✗'}", "",
         f"**結論：{'通過' if (ok_peer or ok_react) and cost_ok else ('訊號成立但不足以支付成本' if ok_peer or ok_react else '未通過')}**"]
    (ROOT / "docs" / "peer_transfer.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
