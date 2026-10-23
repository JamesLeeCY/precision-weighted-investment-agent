"""I055 股票期貨基差隱含的放空需求（點子卡 research/ideas/I055-ssf-basis-implied-short-demand.md，檢定計畫看結果前固定）。

用法（於專案根目錄；股票期貨資料已在 I031 快取）：
    .venv/Scripts/python analysis/ssf_basis.py
輸出 docs/ssf_basis.md。

設計（依點子卡；補充以「補」標示）：
- 樣本：前 500 名中有標準型股票期貨（analysis/futures_exec.stock_futures_map）、選用契約前一日未平倉 ≥ 50 口者；2019-03 ~ 2026-04。
- 選用契約：到期日（futures_exec.expiry）距今 ≥ 10 個交易日的最近月；F = 結算價（缺值用收盤），S = 現股收盤（未還原）。
- B = ln(F ÷ S) × 365 ÷ 到期日曆天數；5 個交易日平均（補：至少 3 日）；每日橫斷面減中位數。
- 前置 (a)（看報酬前）：觀察日到到期日之間有除息日（TaiwanStockDividendResult，含「息」）者與其他者的 B 中位數差，
  與「已公告現金股利 D ÷ S × 365 ÷ 天數」的中位數比較；差的絕對值 > 該股利項一半 → 改用扣股利版 B' = ln((F + D) ÷ S) × 365 ÷ 天數。
  補：D = 除息前收盤 − 除息參考價（只用「息」事件；「權息」以同法估計，含少量股票股利誤差）。
- 前置 (b)：每日可用檔數中位數 ≥ 100，否則停止。
- 主檢定：換倉日（leg_probe schedule），B 與之後 20／60 日報酬的產業內 Spearman IC（同產業 < 3 檔者併入「其他」）；Newey-West 落後 2。
  Fama-MacBeth（60 日報酬產業內百分位 − 0.5）控制 SUE、60 日借券費率、S1（借券賣出餘額比 ts_rank）、log 市值、20 日反轉（百分位 − 0.5）。
- 通過：(1) 60 日 IC 兩段皆 > 0 且 t > 2、全期 t > 3；(2) Fama-MacBeth 全期 t > 2；(3) 0.75 × SUE + 0.25 × B（無期貨者 B 百分位 0.5）的 fv5 建構兩段 Sharpe 都不低於 fv5。
- 只報告：B 最低與最高 10% 分開；未平倉 20 日變化率的 IC。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import futures_exec as fx  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import ts_rank_chips as trc  # noqa: E402
from sue_attention import nw_t  # noqa: E402


def basis_frame(client, fid: str, days: pd.DatetimeIndex, S: pd.Series):
    d = client.get("TaiwanFuturesDaily", fid, "2019-01-01", "2026-05-31")
    if d.empty:
        return None
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}")].copy()
    if d.empty:
        return None
    d["date"] = pd.to_datetime(d["date"])
    d["px"] = d["settlement_price"].astype(float).where(d["settlement_price"].astype(float) > 0, d["close"].astype(float))
    px = d.pivot_table(index="date", columns="contract_date", values="px")
    oi = d.pivot_table(index="date", columns="contract_date", values="open_interest")
    idx = days[(days >= px.index.min()) & (days <= px.index.max())]
    px, oi = px.reindex(idx), oi.reindex(index=idx, columns=px.columns)
    exp = {c: fx.expiry(str(c), days) for c in px.columns}
    rows = []
    for i, t in enumerate(idx):
        k = int(days.searchsorted(t))
        lim = days[min(k + 10, len(days) - 1)]
        cands = sorted(c for c in px.columns if exp[c] >= lim and px.at[t, c] == px.at[t, c])
        if not cands:
            continue
        c = cands[0]
        prev_oi = oi.at[idx[i - 1], c] if i > 0 else np.nan
        rows.append((t, float(px.at[t, c]), exp[c], prev_oi))
    if not rows:
        return None
    f = pd.DataFrame(rows, columns=["date", "F", "exp", "oi_prev"]).set_index("date")
    f["S"] = S.reindex(f.index)
    f["T"] = ((pd.to_datetime(f["exp"]).to_numpy() - f.index.to_numpy()) / np.timedelta64(1, "D")).clip(min=1)
    return f


def dividends(client, sid: str) -> pd.DataFrame:
    d = client.get("TaiwanStockDividendResult", sid, lp.EV_START, lp.EV_END)
    if d.empty:
        return pd.DataFrame(columns=["date", "D"])
    d = d[d["stock_or_cache_dividend"].astype(str).str.contains("息")]
    return pd.DataFrame({"date": pd.to_datetime(d["date"]), "D": d["before_price"].astype(float) - d["after_price"].astype(float)})


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    close = bc.raw_close(c)
    fmap = fx.stock_futures_map()
    frames = {}
    for t in c.tickers:
        sid = t.split(".")[0]
        if sid not in fmap:
            continue
        f = basis_frame(c.client, fmap[sid], days, close[t])
        if f is None:
            continue
        dv = dividends(c.client, sid)
        Dsum = []
        for dd, ex in zip(f.index, f["exp"]):
            m = dv[(dv["date"] > dd) & (dv["date"] <= ex)]
            Dsum.append(float(m["D"].sum()) if len(m) else 0.0)
        f["D"] = Dsum
        frames[t] = f
    B, Badj, OK, HASD, DTERM = {}, {}, {}, {}, {}
    for t, f in frames.items():
        B[t] = np.log(f["F"] / f["S"]) * 365 / f["T"]
        Badj[t] = np.log((f["F"] + f["D"]) / f["S"]) * 365 / f["T"]
        OK[t] = f["oi_prev"] >= 50
        HASD[t] = f["D"] > 0
        DTERM[t] = f["D"] / f["S"] * 365 / f["T"]
    fr = lambda d: pd.DataFrame(d).reindex(index=days, columns=c.tickers)  # noqa: E731
    B, Badj, OK, HASD, DTERM = fr(B), fr(Badj), fr(OK).fillna(False).astype(bool), fr(HASD).fillna(False).astype(bool), fr(DTERM)
    mem = c.member.reindex(columns=c.tickers).fillna(False).astype(bool)
    use = OK & mem & B.notna()
    in_range = (days >= pd.Timestamp("2019-03-01")) & (days < lp.HOLDOUT)
    n_daily = use[in_range].sum(axis=1)
    # 前置 (a)
    Bx = B.where(use)
    dmed = Bx.sub(Bx.median(axis=1), axis=0)
    gap = float(np.nanmedian(dmed.where(HASD).to_numpy()) - np.nanmedian(dmed.where(~HASD).to_numpy()))
    dterm = float(np.nanmedian(DTERM.where(use & HASD).to_numpy()))
    use_adj = abs(gap) > 0.5 * dterm
    raw = (Badj if use_adj else B).where(use)
    sig = raw.rolling(5, min_periods=3).mean().where(use)
    sig = sig.sub(sig.median(axis=1), axis=0)
    stop = float(n_daily.median()) < 100
    L = ["# I055 股票期貨基差（自動產生）", "",
         "由 [analysis/ssf_basis.py](../analysis/ssf_basis.py) 產生；設計見程式開頭（看結果前固定）。B = ln(期貨 ÷ 現貨) 年化、5 日平均、減當日中位數；"
         "IC 為產業內 Spearman（−1～1，0 為無預測力；正值代表折價深的股票之後較差），括號為（Newey-West t，換倉日數）。研究結果，非投資建議。", "",
         "## 前置檢查（看報酬前）", "",
         f"- 有股票期貨資料的前 500 名成員 {len(frames)} 檔；每日可用（未平倉 ≥ 50 口）檔數中位數 {n_daily.median():.0f}（門檻 100）→ {'停止' if stop else '繼續'}。",
         f"- 到期前有除息者的 B 比其他者低 {gap:+.2%}（年化），已公告股利項中位數 {dterm:.2%} → {'改用扣股利版 B′' if use_adj else '維持原始 B'}。", ""]
    if stop:
        L += ["**結論：未通過（前置檢查 (b) 停止）**"]
        (ROOT / "docs" / "ssf_basis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("\n".join(L))
        return
    fwd20, fwd60 = c.fwd20, c.adj.shift(-60) / c.adj - 1
    limit = int(days.searchsorted(lp.HOLDOUT))
    fee = hc.lending_fees(c.client, c.tickers, days)
    X, _ = trc.raw_fields(c)
    ts1 = trc.ts_rank(X["x1"]).where(X["x1"].rolling(250, min_periods=120).max() > 0)
    s1 = -ts1.shift(1)
    rev20 = (c.adj / c.adj.shift(20) - 1)
    sue = lp.leg_scores(c, "sue")

    def grp(names):
        g = sector.reindex(names)
        cnt = g.map(g.value_counts())
        return g.where(cnt >= 3, "其他")
    ic20, ic60, fm, lo10, hi10, oic = {}, {}, {}, {}, {}, {}
    oi_all = {}
    for t, f in frames.items():
        oi_all[t] = f["oi_prev"]
    OI = fr(oi_all)
    oichg = OI / OI.shift(20) - 1
    for d in sched:
        k = int(days.searchsorted(d))
        s = sig.loc[d].dropna()
        if len(s) < 30:
            continue
        g = grp(s.index)
        if k + 20 < limit:
            ic20[d] = lp.within_ic(s, fwd20.loc[d], g)
            oic[d] = lp.within_ic(oichg.loc[d].reindex(s.index), fwd20.loc[d], g)
        if k + 60 < limit:
            ic60[d] = lp.within_ic(s, fwd60.loc[d], g)
            df = pd.DataFrame({"y": fwd60.loc[d].reindex(s.index), "b": s, "sue": sue[d].reindex(s.index), "fee": fee.loc[d].reindex(s.index),
                               "s1": s1.loc[d].reindex(s.index), "lm": c.logcap.loc[d].reindex(s.index), "rev": rev20.loc[d].reindex(s.index)}).dropna(subset=["y", "b"])
            if len(df) >= 30:
                y = df["y"].groupby(g.reindex(df.index)).rank(pct=True) - 0.5
                Z = (df.drop(columns="y").rank(pct=True) - 0.5).fillna(0.0)
                bta, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(Z)), Z.to_numpy()]), y.to_numpy(), rcond=None)
                fm[d] = bta[1]
                q = df["b"].rank(pct=True)
                med = fwd60.loc[d].reindex(df.index).median()
                lo10[d] = float(fwd60.loc[d].reindex(df.index[q <= 0.1]).mean() - med)
                hi10[d] = float(fwd60.loc[d].reindex(df.index[q > 0.9]).mean() - med)

    def segs(x, lag=2):
        x = pd.Series(x).dropna()
        f = lambda y: (float(y.mean()), nw_t(y, lag), len(y))  # noqa: E731
        return {"2019–2022": f(x[x.index < lp.SPLIT]), "2023–2026/04": f(x[x.index >= lp.SPLIT]), "全期": f(x)}
    fmt = lambda v, pct=False: "—" if v[0] != v[0] else (f"{v[0]:+.2%}" if pct else f"{v[0]:+.3f}") + f"（{v[1]:.1f}，{v[2]}）"  # noqa: E731
    a20, a60, afm = segs(ic20), segs(ic60), segs(fm)
    c1 = all(a60[s][0] > 0 and a60[s][1] > 2 for s in ("2019–2022", "2023–2026/04")) and a60["全期"][1] > 3
    c2 = afm["全期"][1] > 2
    L += ["## 主檢定", "", "| 統計量 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
          "| **B 的 IC 60 日** | " + " | ".join(fmt(v) for v in a60.values()) + " |",
          "| B 的 IC 20 日 | " + " | ".join(fmt(v) for v in a20.values()) + " |",
          "| **Fama-MacBeth（控制 SUE、借券費率、S1、市值、20 日反轉）** | " + " | ".join(fmt(v) for v in afm.values()) + " |",
          "| 只報告：B 最低 10% 減中位數的 60 日報酬 | " + " | ".join(fmt(v, True) for v in segs(lo10).values()) + " |",
          "| 只報告：B 最高 10% 減中位數的 60 日報酬 | " + " | ".join(fmt(v, True) for v in segs(hi10).values()) + " |",
          "| 只報告：未平倉 20 日變化率 IC 20 日 | " + " | ".join(fmt(v) for v in segs(oic).values()) + " |", ""]
    c3 = None
    if c1 and c2:
        quota, lend60 = bc.load_short_data(c.client, c.tickers, days)

        def shortable_at(d):
            n_short = max(1, int(c.member.loc[d].sum() / 3))
            need = lt.K_CAPITAL / n_short / close.loc[d]
            return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

        def comp(d):
            s = sue[d].dropna()
            gg = sector.reindex(s.index)
            return 0.75 * s.groupby(gg).rank(pct=True) + 0.25 * sig.loc[d].reindex(s.index).groupby(gg).rank(pct=True).fillna(0.5)

        def book(fn):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(fn(d), sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            x = x[x.index > sched[2]]
            return hc.stats(x) | {"full": lp.sharpe(x.dropna())}
        b0, b1 = book(lambda d: sue[d]), book(comp)
        c3 = b1["sh_oos"] >= b0["sh_oos"] and b1["sh_is"] >= b0["sh_is"]
        L += ["| 建構 | Sharpe | 全期 | 年化報酬 | 最大回撤 |", "|---|---|---|---|---|",
              f"| fv5（SUE） | {b0['sh_oos']:.2f} / {b0['sh_is']:.2f} | {b0['full']:.2f} | {b0['ann']:+.1%} | {b0['mdd']:.1%} |",
              f"| 0.75 SUE ＋ 0.25 B | {b1['sh_oos']:.2f} / {b1['sh_is']:.2f} | {b1['full']:.2f} | {b1['ann']:+.1%} | {b1['mdd']:.1%} |", ""]
    mark = lambda b: "—（未執行）" if b is None else ("✓" if b else "✗")  # noqa: E731
    L += ["## 判定", "",
          f"1. 60 日 IC 兩段 > 0 且 t > 2、全期 t > 3 → {mark(c1)}",
          f"2. Fama-MacBeth 全期 t > 2 → {mark(c2)}",
          f"3. 合成兩段 Sharpe 不低於 fv5 → {mark(c3)}", "",
          f"**結論：{'通過（建議另立前瞻規格）' if c1 and c2 and c3 else '未通過'}**"]
    (ROOT / "docs" / "ssf_basis.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
