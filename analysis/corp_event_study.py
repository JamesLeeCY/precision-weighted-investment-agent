"""公司事件研究的共用引擎（點子卡 I011 內部人轉讓、I012 現金增資／可轉債）：配對控制 SUE 與動能、日期分群 t、可交易版本。

設計（兩張點子卡共同、看結果前固定）：
- 異常報酬：還原報酬 − β × 加權指數含息報酬（β 250 日，只用前一日以前）。
- 配對：每個事件在事件日找同產業、當日為股票池成員、前後一段期間內沒有同類事件的股票，
  且「最新可得月營收 SUE」與「事件前 60 日報酬」在當日股票池中的三分位都與事件股相同；配對 CAR 取這些股票的平均，
  主統計量 = 事件 CAR − 配對 CAR。t 值：同一事件日先平均，再對事件日做 t 檢定。
- 截面迴歸：事件與配對股（每個事件最多 10 檔）合併，CAR ~ 事件啞變數 + SUE + 事件前 20／60 日報酬 + log 市值（排名 −0.5～+0.5），
  標準誤依事件日分群；看事件啞變數係數。
- 可交易 A（放空）：第 +1 日收盤放空、持有 H 日，同時持有者等權，只放空借券條件 D（同 borrow_capacity.py）通過者，
  資金 1,000 萬與 2 億；台指期對沖；扣成本與借券費；報告可放空比例。
- 可交易 B（濾網）：fv5 建構（前 500 名 SUE 等權多空、每 3 個月三份錯開、不含緩衝、條件 D、台指期對沖）的做多名單排除過去 L 個交易日內
  有事件的股票（做多總權重不變），比較兩段 Sharpe。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MEMBERSHIP = ROOT / "config" / "universe_mcap_membership.csv"   # 第 1001 名以後的樣本可改指 universe_mcap_membership_1500.csv
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import dividend_events as de  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
import sue_exdiv_filter as sf  # noqa: E402
from data.revenue_signal import revenue_surprise  # noqa: E402

MAX_CONTROLS = 10


def sue_matrix(client, tickers: list, days: pd.DatetimeIndex) -> pd.DataFrame:
    """每日可得的最新月營收 SUE（每月 10 日後才用當月公告值）。"""
    key = pd.Series([(d.to_period("M").to_timestamp() if d.day > 10 else d.to_period("M").to_timestamp() - pd.offsets.MonthBegin(1))
                     for d in days], index=days)
    out = {}
    for t in tickers:
        rev = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if rev.empty:
            continue
        s = revenue_surprise(rev).set_index("avail_month")["sue"].dropna()
        out[t] = s.reindex(s.index.union(key.unique())).sort_index().ffill().reindex(key.to_numpy()).to_numpy()
    return pd.DataFrame(out, index=days).reindex(columns=tickers)


class Sample:
    """一個股票池樣本（市值排名 lo–hi）的價格、異常報酬、成員、產業、SUE、市值。"""

    def __init__(self, client, lo: int, hi: int, mkt_tri, tx):
        self.client, self.lo = client, lo
        adj, close, member, _ = de.load_sample(client, lo, hi)
        self.adj, self.close, self.member = adj, close, member
        self.rets = adj.pct_change()
        self.days = self.rets.index
        self.limit = int(self.days.searchsorted(lp.HOLDOUT))
        m = mkt_tri.pct_change().reindex(self.days)
        self.betas = self.rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
        ar = (self.rets - self.betas.fillna(1.0).mul(m, axis=0)).to_numpy(copy=True)
        ar[self.limit:] = np.nan
        self.cs = np.vstack([np.zeros((1, ar.shape[1])), np.nancumsum(np.nan_to_num(ar), axis=0)])   # cs[k+1] = Σ ar[0..k]
        self.valid = np.vstack([np.zeros((1, ar.shape[1])), np.cumsum(np.isfinite(ar), axis=0)])
        self.col = {t: j for j, t in enumerate(adj.columns)}
        self.tickers = list(adj.columns)
        mem = pd.read_csv(MEMBERSHIP, dtype={"stock_id": str}, parse_dates=["rebalance_date"])
        self.sector = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["sector"]
        self.sec_arr = np.array([self.sector.get(t.split(".")[0], "NA") for t in self.tickers])
        self.pre60 = (adj / adj.shift(60) - 1).shift(1)
        self.pre20 = (adj / adj.shift(20) - 1).shift(1)
        mem = mem[(mem["rank"] >= lo) & (mem["rank"] <= hi)]
        mc = pd.DataFrame(np.nan, index=self.days, columns=self.tickers)
        for y, g in mem.groupby("year"):
            kb = int(self.days.searchsorted(g["rebalance_date"].iloc[0], side="right")) - 1
            rows = self.days.year == y
            for _, r in g.iterrows():
                t = r["stock_id"] + ".TW"
                if t in self.col and kb >= 0 and close.iat[kb, self.col[t]] > 0:
                    mc.loc[rows, t] = r["mcap"] * close.loc[rows, t] / close.iat[kb, self.col[t]]
        self.lmcap = np.log(mc.shift(1))
        self.sue = sue_matrix(client, self.tickers, self.days)
        self.tx = tx

    def car(self, j, a: int, b: int):
        """j：欄位（int 或陣列）；[a, b] 為絕對交易日位置；只算到 limit 之前。"""
        b = min(b, self.limit - 1)
        if a < 0 or b < a:
            return np.full(np.shape(j), np.nan) if np.ndim(j) else np.nan
        s = self.cs[b + 1, j] - self.cs[a, j]
        n = self.valid[b + 1, j] - self.valid[a, j]
        return np.where(n > 0, s, np.nan)

    def events(self, ev: pd.DataFrame) -> pd.DataFrame:
        """ev：[stock_id, date, ...]；回傳加上 ticker、k0、t0、seg，且當日為成員者。"""
        ev = ev.copy()
        ev["ticker"] = ev["stock_id"].astype(str) + ".TW"
        ev = ev[ev["ticker"].isin(self.col)]
        ev["k0"] = [int(self.days.searchsorted(d, side="left")) for d in ev["date"]]
        ev = ev[(ev["k0"] >= 61) & (ev["k0"] < self.limit - 2)].copy()
        ev["t0"] = self.days[ev["k0"].to_numpy()]
        ev = ev[[bool(self.member.iat[k, self.col[t]]) for k, t in zip(ev["k0"], ev["ticker"])]].copy()
        ev["seg"] = np.where(ev["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
        return ev.reset_index(drop=True)


def terciles(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(len(x), -1)
    ok = mask & np.isfinite(x)
    if ok.sum() < 6:
        return out
    q1, q2 = np.nanquantile(x[ok], [1 / 3, 2 / 3])
    out[ok] = np.where(x[ok] <= q1, 0, np.where(x[ok] <= q2, 1, 2))
    return out


def matched(S: Sample, ev: pd.DataFrame, all_events: pd.DataFrame, windows: dict, exclude_span: int) -> pd.DataFrame:
    """為每個事件算各視窗的 CAR、配對 CAR 與差額；all_events 用來排除配對股中有同類事件者。"""
    ev = ev.copy()
    near = {}
    for t, k in zip(all_events["ticker"], all_events["k0"]):
        near.setdefault(t, []).append(k)
    res = {f"{w}": [] for w in windows} | {f"{w}_ctrl": [] for w in windows} | {"n_ctrl": [], "ctrl_cols": []}
    sue_np, pre_np, mem_np = S.sue.to_numpy(), S.pre60.to_numpy(), S.member.to_numpy()
    for t, k in zip(ev["ticker"], ev["k0"]):
        j = S.col[t]
        mem = mem_np[k].astype(bool)
        st = terciles(sue_np[k], mem)
        pt = terciles(pre_np[k], mem)
        cand = np.where(mem & (S.sec_arr == S.sec_arr[j]) & (st == st[j]) & (pt == pt[j]) & (st >= 0) & (pt >= 0))[0]
        cand = np.array([c for c in cand if c != j and not any(abs(kk - k) <= exclude_span for kk in near.get(S.tickers[c], []))], dtype=int)
        res["n_ctrl"].append(len(cand))
        res["ctrl_cols"].append(cand[:MAX_CONTROLS])
        for w, (a, b) in windows.items():
            res[w].append(float(S.car(j, k + a, k + b)))
            res[f"{w}_ctrl"].append(float(np.nanmean(S.car(cand, k + a, k + b))) if len(cand) else np.nan)
    for w in windows:
        ev[w] = res[w]
        ev[f"{w}_ctrl"] = res[f"{w}_ctrl"]
        ev[f"{w}_diff"] = ev[w] - ev[f"{w}_ctrl"]
    ev["n_ctrl"], ev["ctrl_cols"] = res["n_ctrl"], res["ctrl_cols"]
    return ev


def clustered(df: pd.DataFrame, col: str) -> tuple[float, float, int]:
    g = df.dropna(subset=[col]).groupby("t0")[col].mean()
    if len(g) < 5 or g.std(ddof=1) == 0:
        return (float(g.mean()) if len(g) else float("nan")), float("nan"), len(g)
    return float(g.mean()), float(g.mean() / g.std(ddof=1) * math.sqrt(len(g))), len(g)


def fmt(x):
    return "—" if x[0] != x[0] else (f"{x[0]:+.2%}（{x[1]:.1f}）" if x[1] == x[1] else f"{x[0]:+.2%}")


def regression(S: Sample, ev: pd.DataFrame, w: str, window: tuple[int, int]) -> dict:
    rows = []
    for r in ev.itertuples():
        k, j = r.k0, S.col[r.ticker]
        for col, is_ev in [(j, 1.0)] + [(c, 0.0) for c in r.ctrl_cols]:
            rows.append({"t0": r.t0, "ev": is_ev, "car": float(S.car(col, k + window[0], k + window[1])),
                         "sue": S.sue.iat[k, col], "p20": S.pre20.iat[k, col], "p60": S.pre60.iat[k, col], "lm": S.lmcap.iat[k, col]})
    df = pd.DataFrame(rows).dropna()
    if len(df) < 50 or df["ev"].sum() < 10:
        return {"b": np.nan, "t": np.nan, "n": int(df["ev"].sum()) if len(df) else 0}
    for v in ("sue", "p20", "p60", "lm"):
        df[v] = df[v].rank(pct=True) - 0.5
    X = np.column_stack([np.ones(len(df)), df[["ev", "sue", "p20", "p60", "lm"]].to_numpy(float)])
    beta, se = dsu.ols_cluster(df["car"].to_numpy(float), X, df["t0"].astype(str).to_numpy())
    return {"b": float(beta[1]), "t": float(beta[1] / se[1]), "n": int(df["ev"].sum())}


def short_version(S: Sample, ev: pd.DataFrame, hold: int, fee, quota, lend60) -> dict:
    active = np.zeros(len(S.days))
    for k in ev["k0"]:
        active[k + 1:min(k + 1 + hold, S.limit)] += 1
    out = {}
    cs = SimpleNamespace(rets=S.rets, betas=S.betas, tx=S.tx)
    for lab, K in (("1,000 萬", 1e7), ("2 億", 2e8)):
        ok = []
        for t, k in zip(ev["ticker"], ev["k0"]):
            j, kk = S.col[t], k + 1
            px = S.close.iat[kk, j]
            need = K / max(active[kk], 1) / px if px > 0 else np.inf
            f = fee.iat[kk, j]
            ok.append(bool(lend60.iat[kk, j] > 0 and quota.iat[kk, j] >= need and need <= bc.DEPTH_FRAC * lend60.iat[kk, j]
                           and f == f and f <= bc.FEE_MAX))
        sub = ev[np.array(ok, dtype=bool)]
        pos = {}
        for r in sub.itertuples():
            for k in range(r.k0 + 1, min(r.k0 + 1 + hold, S.limit - 1)):
                pos.setdefault(S.days[k], set()).add(r.ticker)
        wmap = {d: pd.Series(-1 / len(v), index=sorted(v)) for d, v in pos.items()}
        sim = es.simulate_daily(wmap, cs, fee)
        out[lab] = {"cover": float(np.mean(ok)) if ok else np.nan, "stats": hc.stats(sim["ret"]), "ret": sim["ret"], "active": float((sim["n"] > 0).mean())}
    return out


def fv5_filter(ev_dates: pd.DataFrame, lookback: int) -> dict:
    """fv5 建構的做多名單排除過去 lookback 個交易日內有事件的股票。ev_dates：[ticker, t0]。"""
    c = lp.prepare(500)
    scores = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    days = c.adj.index
    E = pd.DataFrame(0, index=days, columns=c.tickers)
    for t, d in zip(ev_dates["ticker"], ev_dates["t0"]):
        if t in E.columns and d in E.index:
            E.loc[d, t] = 1
    flags = E.rolling(lookback, min_periods=1).sum().shift(1).fillna(0) > 0

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)
    sched = c.schedule
    start = sched[2]
    out, shares = {}, []
    for name, filt in (("fv5 建構（基準）", False), ("濾網版", True)):
        sims = []
        for off in (0, 1, 2):
            wd = {}
            for d in sched[off::3]:
                w = lt.ew_ls_buffer(scores[d], c.sector, shortable_at(d), q_keep=None)
                if filt:
                    w, s = sf.filter_long(w, flags.loc[d])
                    shares.append(s)
                wd[d] = w
            sims.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee))
        r = pd.concat([s["ret"][s.index > start] for s in sims], axis=1).mean(axis=1)
        out[name] = hc.stats(r) | {"full": lp.sharpe(r.dropna())}
    out["share"] = float(np.mean(shares)) if shares else 0.0
    return out
