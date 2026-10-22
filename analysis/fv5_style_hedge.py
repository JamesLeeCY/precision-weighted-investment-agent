"""I049 fv5 的未定價風格風險對沖（點子卡 research/ideas/I049-fv5-unpriced-style-risk-hedge.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_style_hedge.py
輸出 docs/fv5_style_hedge.md。

設計（依點子卡；補充以「補」標示）：
- 基準 fv5：前 500 名、SUE 產業內前／後 1/3 等權（ls_turnover.ew_ls_buffer，不含緩衝、放空只用條件 D 可借者）、三份錯開、每 3 個換倉日換倉、
  台指期對沖、單邊 0.29625% + 借券費（hedge_construction.simulate_weights）。
- 風格因子（5 個）：每日在前 500 名內，依前一日的 12-1 動能、60 日波動、帳面市值比（同季權益 ÷ 市值，法定期限後可用）、前 20 日報酬、
  250 日 β 做產業內前／後 1/3（各產業內百分位 > 2/3 為多、≤ 1/3 為空），多空各等權，得 5 條日報酬（只用於估計負荷）。
- 前置診斷：fv5 日淨報酬對 5 條因子迴歸的 R²（兩段、全期）；全期 R² < 0.10 → 停止。
- H1：每個換倉日，用前 250 個交易日（至少 120 日）估計名單內每檔對 5 條因子的多元迴歸負荷，向名單內橫斷面中位數收縮 50%（補：中位數取該份名單）；
  在既有名單內求最接近等權的權重，使 5 個組合負荷為 0，且每個產業的多方、空方權重和不變，單檔介於等權的 1/3 ~ 3 倍。
  補：因子報酬歷史不足、負荷有缺值的換倉日（2019 年前段）維持原權重。沒有 scipy，用 Dykstra 交替投影（仿射等式集合與上下限盒）求最小距離投影，300 次迭代；若不可行，結果為兩集合間近似最近點
  （等同「放寬為負荷絕對值盡量小」），報告投影後的平均剩餘負荷。放空端依新權重重查條件 D（需借 = 2 億 × |權重| ÷ 收盤價），剔除後空方重新正規化一次。
- 只報告：H2 特徵中性（以 5 個特徵的名單內百分位 − 0.5 取代負荷）；H3 先做 I033 逆標準差權重再做 H1；負荷估計期 120 日；收縮 0% / 100%。
- 通過（H1）：全期 Sharpe ≥ fv5 + 0.10；兩段 Sharpe 都不低於 fv5；年化波動低於 fv5；年化報酬少不超過 1 個百分點；年換手多不超過 20%。
研究結果，非投資建議。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import asset_growth as agm  # noqa: E402
import borrow_capacity as bc  # noqa: E402
import fv5_invvol as iv  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import margin_surprise as msm  # noqa: E402

FACTORS = ["12-1 動能", "60 日波動", "帳面市值比", "前 20 日報酬", "250 日 β"]


def sector_terciles(X: pd.DataFrame, member: pd.DataFrame, sector: pd.Series) -> pd.DataFrame:
    """每日產業內百分位。"""
    Xm = X.where(member)
    out = pd.DataFrame(np.nan, index=X.index, columns=X.columns)
    for _, cols in sector.groupby(sector).groups.items():
        cols = [c for c in cols if c in X.columns]
        if cols:
            out[cols] = Xm[cols].rank(axis=1, pct=True)
    return out


def factor_returns(chars: dict, member, sector, rets) -> pd.DataFrame:
    out = {}
    for k, X in chars.items():
        P = sector_terciles(X, member, sector).shift(1)
        lw = (P > 2 / 3).astype(float)
        sw = (P <= 1 / 3).astype(float)
        out[k] = (rets * lw).sum(axis=1) / lw.sum(axis=1).replace(0, np.nan) - (rets * sw).sum(axis=1) / sw.sum(axis=1).replace(0, np.nan)
    return pd.DataFrame(out)


def loadings(rets: pd.DataFrame, F: pd.DataFrame, names, d, win: int) -> pd.DataFrame:
    k = int(rets.index.searchsorted(d))
    R = rets.iloc[max(0, k - win):k][list(names)]
    Fx = F.reindex(R.index)
    ok_f = Fx.notna().all(axis=1)
    R, Fx = R[ok_f], Fx[ok_f]
    X = np.column_stack([np.ones(len(Fx)), Fx.to_numpy()])
    B = {}
    for t in R.columns:
        y = R[t].to_numpy()
        m = np.isfinite(y)
        if m.sum() >= 120:
            b, *_ = np.linalg.lstsq(X[m], y[m], rcond=None)
            B[t] = b[1:]
    return pd.DataFrame(B, index=F.columns).T


def project(w0: pd.Series, A: np.ndarray, sector: pd.Series, iters: int = 300) -> tuple[pd.Series, float]:
    """在 {A w = 0、各產業多空權重和不變} ∩ {等權 1/3~3 倍} 上求最接近 w0 的點（Dykstra）。"""
    names = w0.index
    sec = sector.reindex(names).fillna("NA").to_numpy()
    long = (w0 > 0).to_numpy()
    rows, rhs = [A.T[i] for i in range(A.shape[1])], [0.0] * A.shape[1]
    for s in np.unique(sec):
        for side in (long, ~long):
            m = (sec == s) & side
            if m.any():
                rows.append(m.astype(float))
                rhs.append(float(w0.to_numpy()[m].sum()))
    E, e = np.vstack(rows), np.array(rhs)
    Ep = np.linalg.pinv(E)
    x0 = w0.to_numpy().astype(float)
    lo = np.where(long, x0 / 3, x0 * 3)
    hi = np.where(long, x0 * 3, x0 / 3)
    x, p, q = x0.copy(), np.zeros_like(x0), np.zeros_like(x0)
    for _ in range(iters):
        y = x + p
        y_aff = y - Ep @ (E @ y - e)
        p = y - y_aff
        z = y_aff + q
        x = np.clip(z, lo, hi)
        q = z - x
    resid = float(np.abs(A.T @ x).mean())
    return pd.Series(x, index=names), resid


def main():
    c = lp.prepare(500)
    sched = c.schedule
    days = c.adj.index
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    sue = lp.leg_scores(c, "sue")
    sector = c.sector
    eq = {}
    for t in c.tickers:
        e = msm.balance_equity(c.client, t.split(".")[0])
        if len(e):
            eq[t] = e[e.index.month.isin([3, 6, 9, 12])]
    equity = agm.to_daily(pd.DataFrame(eq).sort_index(), days).reindex(columns=c.tickers).astype(float)
    chars = {"12-1 動能": c.adj.shift(21) / c.adj.shift(252) - 1, "60 日波動": c.rets.rolling(60, min_periods=40).std(),
             "帳面市值比": equity / np.exp(c.logcap), "前 20 日報酬": c.adj / c.adj.shift(20) - 1, "250 日 β": c.betas}
    F = factor_returns(chars, c.member, sector, c.rets)
    pct_chars = {k: sector_terciles(v, c.member, sector) for k, v in chars.items()}
    vol60 = c.rets.rolling(60, min_periods=40).std().shift(1)

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def recheck(w, d):
        s = -w[w < 0]
        need = lt.K_CAPITAL * s / close.loc[d].reindex(s.index)
        ok = (lend60.loc[d].reindex(s.index) > 0) & (quota.loc[d].reindex(s.index) >= need) \
            & (need <= bc.DEPTH_FRAC * lend60.loc[d].reindex(s.index)) & (fee.loc[d].reindex(s.index) <= bc.FEE_MAX)
        s = s[ok.to_numpy(bool)]
        s = s / s.sum() * float(-w[w < 0].sum()) if len(s) else s
        return pd.concat([w[w > 0], -s])

    resid_log = {}

    def make(kind, win=250, shrink=0.5, inv=False):
        key = (kind, win, shrink, inv)
        resid_log[key] = []

        def apply(d, w0):
            w = w0.copy()
            if inv:
                parts = []
                for sign in (1, -1):
                    x = w[w * sign > 0].abs()
                    s = vol60.loc[d].reindex(x.index)
                    s = s.fillna(s.median())
                    parts.append(iv.capped(1 / s, float(x.sum())) * sign)
                w = pd.concat(parts)
            if kind == "load":
                B = loadings(c.rets, F, w.index, d, win)
                B = B.reindex(w.index)
                med = B.median()
                B = B.fillna(med)
                B = (1 - shrink) * B + shrink * med
                A = B.to_numpy()
            else:
                A = np.column_stack([(pct_chars[k].loc[d].reindex(w.index) - 0.5).fillna(0.0).to_numpy() for k in FACTORS])
            if not np.isfinite(A).all():                     # 因子歷史不足（2019 年前段）估不出負荷：維持原權重
                resid_log[key].append((np.nan, np.nan))
                return w if inv else w0
            wn, r = project(w, A, sector)
            resid_log[key].append((r, float(np.abs(A.T @ w.to_numpy()).mean())))
            return recheck(wn, d)
        return apply

    def book(fn):
        parts, tos = [], []
        for off in range(3):
            wd = {d: fn(d, lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None)) for d in sched[off::3]}
            sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
            parts.append(sim["ret"])
            tos.append(sim["turnover"].sum() / (len(sim) / 252))
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        return x, hc.stats(x) | {"full": lp.sharpe(x.dropna()), "to": float(np.mean(tos)) / 3}

    base_x, base = book(lambda d, w: w)
    # 前置診斷
    df = pd.concat([base_x.rename("y"), F], axis=1).dropna()

    def r2(sub):
        X = np.column_stack([np.ones(len(sub)), sub[FACTORS].to_numpy()])
        b, *_ = np.linalg.lstsq(X, sub["y"].to_numpy(), rcond=None)
        e = sub["y"].to_numpy() - X @ b
        return float(1 - e.var() / sub["y"].var()), b[1:]
    r2s = {"2019–2022": r2(df[df.index < lp.SPLIT]), "2023–2026/04": r2(df[df.index >= lp.SPLIT]), "全期": r2(df)}
    stop = r2s["全期"][0] < 0.10
    L = ["# I049 fv5 的未定價風格風險對沖（自動產生）", "",
         "由 [analysis/fv5_style_hedge.py](../analysis/fv5_style_hedge.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，格式 2019–2022 / 2023–2026/04；換手為每份資金年換手（單邊權重變動合計）。研究結果，非投資建議。", "",
         "## 前置診斷：fv5 日淨報酬對 5 個風格因子的迴歸", "",
         "| 期間 | R² | " + " | ".join(f"{k} 係數" for k in FACTORS) + " |", "|---|---|" + "---|" * len(FACTORS)]
    for k, (r, b) in r2s.items():
        L.append(f"| {k} | {r:.3f} | " + " | ".join(f"{x:+.3f}" for x in b) + " |")
    L += ["", f"門檻：全期 R² ≥ 0.10 才繼續 → {'未達，停止（不做對沖）' if stop else '繼續'}", ""]
    res = {"fv5（基準）": base}
    if not stop:
        variants = {"H1 負荷中性（主）": dict(kind="load"), "只報告：H2 特徵中性": dict(kind="char"),
                    "只報告：H3 H1 + 逆標準差權重": dict(kind="load", inv=True), "只報告：H1 估計期 120 日": dict(kind="load", win=120),
                    "只報告：H1 收縮 0%": dict(kind="load", shrink=0.0), "只報告：H1 收縮 100%": dict(kind="load", shrink=1.0)}
        for nm, kw in variants.items():
            _, res[nm] = book(make(**kw))
            print(nm, res[nm]["sh_oos"], res[nm]["sh_is"], flush=True)
        L += ["## 組合結果", "", "| 版本 | Sharpe | 全期 | 年化報酬 | 年化波動 | 最大回撤 | 年換手 |", "|---|---|---|---|---|---|---|"]
        for k, s in res.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | {s['to']:.1f} |")
        rl = {k: np.array(v) for k, v in resid_log.items() if len(v)}
        L += ["", "投影前後的平均組合負荷絕對值（越接近 0 越中性）：" + "；".join(
            f"{k[0]}{'+逆波動' if k[3] else ''}（估計 {k[1]} 日、收縮 {k[2]:.0%}）{np.nanmean(v[:, 1]):.4f} → {np.nanmean(v[:, 0]):.4f}（{int(np.isnan(v[:, 0]).sum())} 次維持原權重）" for k, v in rl.items())]
        h = res["H1 負荷中性（主）"]
        c1 = h["full"] >= base["full"] + 0.10
        c2 = h["sh_oos"] >= base["sh_oos"] and h["sh_is"] >= base["sh_is"]
        c3 = h["vol"] < base["vol"]
        c4 = h["ann"] >= base["ann"] - 0.01
        c5 = h["to"] <= base["to"] * 1.2
        L += ["", "## 判定（H1）", "",
              f"1. 全期 Sharpe ≥ fv5 + 0.10（{h['full']:.2f} vs {base['full']:.2f}）→ {'✓' if c1 else '✗'}",
              f"2. 兩段不低於 fv5（{h['sh_oos']:.2f} / {h['sh_is']:.2f} vs {base['sh_oos']:.2f} / {base['sh_is']:.2f}）→ {'✓' if c2 else '✗'}",
              f"3. 年化波動低於 fv5（{h['vol']:.1%} vs {base['vol']:.1%}）→ {'✓' if c3 else '✗'}",
              f"4. 年化報酬少不超過 1 個百分點（{h['ann']:+.1%} vs {base['ann']:+.1%}）→ {'✓' if c4 else '✗'}",
              f"5. 年換手多不超過 20%（{h['to']:.1f} vs {base['to']:.1f}）→ {'✓' if c5 else '✗'}", "",
              f"**結論：{'通過（另立平行前瞻規格 fv5h）' if all((c1, c2, c3, c4, c5)) else '未通過'}**"]
    else:
        L += [f"fv5 基準：{base['sh_oos']:.2f} / {base['sh_is']:.2f}，全期 {base['full']:.2f}。", "", "**結論：未通過（前置診斷停止）**"]
    (ROOT / "docs" / "fv5_style_hedge.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
