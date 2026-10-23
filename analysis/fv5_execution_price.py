"""I054 fv5 換倉日的成交價格（點子卡 research/ideas/I054-fv5-entry-execution-price.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fv5_execution_price.py
輸出 docs/fv5_execution_price.md。

設計（依點子卡；補充以「補」標示）：
- fv5 名單、權重、借券條件 D、三份錯開、台指期對沖完全不變（hedge_construction.simulate_weights，以換倉日收盤成交 = P0）。
- 替代版本：P1 隔日開盤；P2 隔日 (O+H+L+C)/4；P3 當日、隔日、第三日收盤各 1/3。台指期同步（近月合約同一時點價格）。
- 損益調整（補，等價寫法）：換倉日 d 每檔權重變動 Δw（帶正負號，買進／回補為正）若以價格 P 而非收盤 C_d 成交，
  組合多（少）賺 −Δw × (P ÷ C_d − 1)；台指期空單變動 Δβ 以 F 而非 F_d 成交，多賺 Δβ × (F ÷ F_d − 1)。調整加在換倉後第一個交易日。
  價格以同日還原因子換算（還原收盤 ÷ 原始收盤），避免除權息造成假差。
- 漲跌停：買進時該版本價格 ≥ 前一日收盤 × 1.095（賣出 ≤ × 0.905）順延到下一日同版本，最多 3 日；仍不成交以第 3 日同版本價格計（補：
  不另做現金部位）；報告順延比例。
- 指標：(1) 每次換倉的配對差（全部權重變動的加權執行價差，正值 = 較有利），平均與 Newey-West t（落後 2）；(2) 年化淨報酬、Sharpe、最大回撤。
- 通過：年化淨報酬差 ≥ +0.3%、兩段同號、配對差單尾 t > 2，三個版本 Holm 校正（家族 5%）。
- 附帶：多空腿分開；SUE 分數前 10%（產業內）與其餘分開的執行價差。
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
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from sue_attention import nw_t  # noqa: E402

VERS = ("P1 隔日開盤", "P2 隔日 OHLC 均價", "P3 三日收盤分批")


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def ohlc(c):
    O, H, L, C = {}, {}, {}, {}
    for sid in c.ids:
        px = c.client.get("TaiwanStockPrice", sid, lp.PX_START)
        if px.empty:
            continue
        px = px.assign(date=pd.to_datetime(px["date"])).drop_duplicates("date").set_index("date")
        px = px[px["close"].astype(float) > 0]
        t = sid + ".TW"
        O[t], H[t], L[t], C[t] = (px[k].astype(float) for k in ("open", "max", "min", "close"))
    f = lambda d: pd.DataFrame(d).reindex(index=c.adj.index, columns=c.tickers)  # noqa: E731
    O, H, L, C = f(O), f(H), f(L), f(C)
    adjf = c.adj / C                                          # 同日還原因子
    return O * adjf, H * adjf, L * adjf, C * adjf, C


def tx_ohlc(client):
    d = client.get("TaiwanFuturesDaily", "TX", "2019-01-01", lp.EV_END)
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}")].copy()
    d["date"] = pd.to_datetime(d["date"])
    for k in ("open", "max", "min", "close", "volume"):
        d[k] = d[k].astype(float)
    d = d[d["close"] > 0]
    return d


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    sue = lp.leg_scores(c, "sue")
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    O, H, L, C, Craw = ohlc(c)
    prevC = Craw.shift(1)
    raw_open = O / (c.adj / Craw)
    tx = tx_ohlc(c.client)
    front = tx.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"]
    txp = {k: tx.pivot_table(index="date", columns="contract_date", values=k) for k in ("open", "max", "min", "close")}

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def exec_price(v, k, names, dw):
        if v == 0:
            return C.iloc[k][names], 0
        if v == 3:
            idx = [min(k + i, len(days) - 1) for i in range(3)]
            return C.iloc[idx][names].mean(), 0
        res = pd.Series(np.nan, index=names)
        n_delay = 0
        pending = list(names)
        for j in range(1, 4):
            kk = min(k + j, len(days) - 1)
            if v == 1:
                p, rp = O.iloc[kk][pending], raw_open.iloc[kk][pending]
            else:
                p = (O.iloc[kk][pending] + H.iloc[kk][pending] + L.iloc[kk][pending] + C.iloc[kk][pending]) / 4
                rp = p / (c.adj.iloc[kk][pending] / Craw.iloc[kk][pending])
            pc = prevC.iloc[kk][pending]
            blocked = ((dw[pending] > 0) & (rp >= pc * 1.095)) | ((dw[pending] < 0) & (rp <= pc * 0.905))
            ok = ~blocked.fillna(False) | (j == 3)
            res.loc[ok[ok].index] = p[ok]
            if j > 1:
                n_delay += int(ok.sum())
            pending = list(ok[~ok].index)
            if not pending:
                break
        return res, n_delay

    def fut_price(v, k):
        cdate = front.get(days[k])
        if cdate is None:
            return np.nan, np.nan
        get = lambda f, kk: txp[f].at[days[kk], cdate] if days[kk] in txp[f].index and cdate in txp[f].columns else np.nan  # noqa: E731
        f0 = get("close", k)
        if v == 0:
            return f0, f0
        if v == 1:
            return get("open", k + 1), f0
        if v == 2:
            return np.mean([get(x, k + 1) for x in ("open", "max", "min", "close")]), f0
        return np.mean([get("close", k + i) for i in range(3)]), f0

    base_parts, adj_parts = [], {v: [] for v in (1, 2, 3)}
    per_reb = {v: [] for v in (1, 2, 3)}
    delays = {v: [0, 0] for v in (1, 2, 3)}
    for off in range(3):
        wd = {d: lt.ew_ls_buffer(sue[d], sector, shortable_at(d), q_keep=None) for d in sched[off::3]}
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)
        base_parts.append(sim["ret"])
        prev, prev_b = pd.Series(dtype=float), 0.0
        adj = {v: pd.Series(0.0, index=sim.index) for v in (1, 2, 3)}
        for d in wd:
            w = wd[d][wd[d] != 0]
            names = w.index.union(prev.index)
            dw = w.reindex(names).fillna(0.0) - prev.reindex(names).fillna(0.0)
            dw = dw[dw != 0]
            b = float(np.nansum(w.to_numpy() * c.betas.loc[d, list(w.index)].fillna(1.0).to_numpy()))
            k = int(days.searchsorted(d))
            p0 = C.iloc[k][dw.index]
            sc = sue[d].reindex(dw.index)
            top = (sc.groupby(sector.reindex(dw.index)).rank(pct=True) >= 0.9).fillna(False)
            side = np.sign(w.reindex(dw.index).fillna(0.0) + prev.reindex(dw.index).fillna(0.0))
            first = sim.index[sim.index > d]
            for v in (1, 2, 3):
                pv, nd = exec_price(v, k, list(dw.index), dw)
                rel = (pv / p0 - 1).fillna(0.0)
                pnl = float(-(dw * rel).sum())
                fv, f0 = fut_price(v, k)
                db = b - prev_b
                if fv == fv and f0 == f0 and f0 > 0:
                    pnl += db * (fv / f0 - 1)
                if len(first):
                    adj[v].loc[first[0]] += pnl
                gross = float(dw.abs().sum())
                fav = -np.sign(dw) * rel                              # 正值 = 較有利
                wts = dw.abs()
                per_reb[v].append({"d": d, "pnl": pnl, "fav": float((fav * wts).sum() / gross) if gross else 0.0,
                                   "fav_long": float((fav * wts)[side > 0].sum() / max(wts[side > 0].sum(), 1e-12)),
                                   "fav_short": float((fav * wts)[side < 0].sum() / max(wts[side < 0].sum(), 1e-12)),
                                   "fav_top": float((fav * wts)[top.to_numpy(bool)].sum() / max(wts[top.to_numpy(bool)].sum(), 1e-12)),
                                   "fav_rest": float((fav * wts)[~top.to_numpy(bool)].sum() / max(wts[~top.to_numpy(bool)].sum(), 1e-12))})
                delays[v][0] += nd
                delays[v][1] += len(dw)
            prev, prev_b = w, b
        for v in (1, 2, 3):
            adj_parts[v].append(sim["ret"] + adj[v])
    start = sched[2]
    agg = lambda parts: (lambda x: x[x.index > start])(pd.concat(parts, axis=1).mean(axis=1))  # noqa: E731
    base = agg(base_parts)
    res = {"P0 當日收盤（現行）": hc.stats(base) | {"full": lp.sharpe(base.dropna())}}
    series = {}
    for v, nm in zip((1, 2, 3), VERS):
        x = agg(adj_parts[v])
        series[nm] = x
        res[nm] = hc.stats(x) | {"full": lp.sharpe(x.dropna())}
    b0 = res["P0 當日收盤（現行）"]
    rows, pvals = [], {}
    for v, nm in zip((1, 2, 3), VERS):
        pr = pd.DataFrame(per_reb[v]).set_index("d").sort_index()
        pr = pr[pr.index > sched[0]]
        t = nw_t(pr["fav"], 2)
        pvals[nm] = 1 - phi(t) if t == t else 1.0
        diff_ann = res[nm]["ann"] - b0["ann"]
        seg = {s: float((series[nm] - base)[(series[nm].index < lp.SPLIT) == (s == 0)].mean() * 252) for s in (0, 1)}
        rows.append((nm, pr, t, diff_ann, seg, delays[v]))
    # Holm（家族 5%）
    order = sorted(pvals, key=pvals.get)
    holm, still = {}, True
    for i, nm in enumerate(order):
        ok = still and pvals[nm] <= 0.05 / (len(order) - i)
        holm[nm] = ok
        still = ok
    L = ["# I054 fv5 換倉日的成交價格（自動產生）", "",
         "由 [analysis/fv5_execution_price.py](../analysis/fv5_execution_price.py) 產生；設計見程式開頭（看結果前固定）。"
         "執行價差 = 以該版本價格取代換倉日收盤成交的價格差（正值 = 對組合較有利），以權重變動加權；Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後，"
         "格式 2019–2022 / 2023–2026/04；各版本成本相同。研究結果，非投資建議。", "",
         "| 版本 | Sharpe | 全期 | 年化淨報酬 | 最大回撤 |", "|---|---|---|---|---|"]
    for k, s in res.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.2%} | {s['mdd']:.1%} |")
    L += ["", "| 版本 | 每次換倉執行價差平均（t，次數） | 多方腿 | 空方腿 | SUE 前 10% | 其餘 | 年化淨報酬差（2019–2022 / 2023–2026/04） | 漲跌停順延比例 | Holm（家族 5%） |",
          "|---|---|---|---|---|---|---|---|---|"]
    passed = []
    for nm, pr, t, diff_ann, seg, dl in rows:
        ok = diff_ann >= 0.003 and np.sign(seg[0]) == np.sign(seg[1]) and seg[0] > 0 and holm[nm]
        if ok:
            passed.append(nm)
        L.append(f"| {nm} | {pr['fav'].mean():+.3%}（{t:.2f}，{len(pr)}） | {pr['fav_long'].mean():+.3%} | {pr['fav_short'].mean():+.3%} | "
                 f"{pr['fav_top'].mean():+.3%} | {pr['fav_rest'].mean():+.3%} | {diff_ann:+.2%}（{seg[0]:+.2%} / {seg[1]:+.2%}） | "
                 f"{dl[0] / max(dl[1], 1):.2%} | {'✓' if holm[nm] else '✗'} |")
    L += ["", "## 判定", "", "通過條件：年化淨報酬差 ≥ +0.3%、兩段同為正、執行價差單尾 t 通過 Holm 校正。", "",
          f"**結論：{'、'.join(passed) + ' 通過（另立執行變體或由使用者決定）' if passed else '三個替代版本皆未通過，維持換倉日收盤成交'}**"]
    (ROOT / "docs" / "fv5_execution_price.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
