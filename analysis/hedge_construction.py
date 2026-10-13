"""對沖結構差：產業內市值加權做多、市值加權多空（含借券成本）。

用法（於專案根目錄；先完成 leg_probe.py 需要的資料）：
    .venv/Scripts/python analysis/hedge_construction.py 300
輸出 docs/hedge_construction_top{N}.md 與 reports/legs/hedge_top{N}.csv（各版本每日報酬）。

背景（docs/leg_pool_report.md）：產業內等權做多 − β × 台指期，股票池基準本身就是 −0.25 / −0.67，
因為台指期追蹤的是市值加權、台積電占比高的指數。

設計（看結果前固定）：
- 同一套腿分數（leg_probe.leg_scores）、同樣換倉日、同樣 2026-05 之後保留。
- EW 做多：原版（產業內前 1/3 等權，產業權重 = 檔數占比），β × 台指期對沖。
- CW 做多：產業內前 1/3 依市值（前一日）加權，產業權重 = 該產業成員市值占股票池市值；β × 台指期對沖。
  對照基準 = 全部成員市值加權（產業權重同上），應接近加權指數 → 結構差應消失。
- CW 多空：做多產業內前 1/3、放空產業內後 1/3（只放空可借券的股票），兩邊都依市值加權，
  只用成員 ≥ 3 檔的產業，產業權重 = 這些產業的市值占比；多空各 100%；剩餘 β（多 − 空）以台指期對沖。
- 可借券與借券費率：TaiwanStockSecuritiesLending 逐筆成交（議借、競價）的 fee_rate（年化 %），
  取前 60 個交易日（到 t−1）成交量加權平均；這 60 日沒有任何借券成交的股票視為借不到，不放空。
  借券費 = Σ 放空權重 × 費率 / 252，逐日計；壓力測試：費率 × 2。
- 成本：股票換手（多空兩邊）× 單邊 0.29625%（放空賣出同樣課 0.3% 證交稅），期貨部位變動 × 0.005%。
- 指標：年化 Sharpe（2019–2022 / 2023–2026/04、逐年）、年化報酬與波動、最大回撤、年換手、借券成本／年、
  做多端有效檔數（1 / Σw²）與最大單檔權重。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import leg_probe as lp  # noqa: E402

Q = 1 / 3
FEE_WINDOW = 60


# ---------------------------------------------------------------------------
# 權重
# ---------------------------------------------------------------------------

def cap_weights(names: pd.Index, cap: pd.Series) -> pd.Series:
    c = cap.reindex(names).fillna(0.0)
    return c / c.sum() if c.sum() > 0 else pd.Series(1.0 / len(names), index=names)


def cw_long(score: pd.Series, sector: pd.Series, cap: pd.Series, q: float = Q) -> pd.Series:
    """產業內前 q 依市值加權；產業權重 = 產業成員市值占比。"""
    s = score.dropna()
    sec = sector.reindex(s.index)
    sec_cap = cap.reindex(s.index).groupby(sec).sum()
    sec_w = sec_cap / sec_cap.sum()
    out = []
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        top = sub.index if len(sub) < 3 or q >= 1 else sub[sub.rank(pct=True) > 1 - q].index
        out.append(cap_weights(top, cap) * sec_w[name])
    return pd.concat(out) if out else pd.Series(dtype=float)


def cw_long_short(score: pd.Series, sector: pd.Series, cap: pd.Series, borrowable: pd.Series, q: float = Q) -> pd.Series:
    """多：產業內前 q；空：產業內後 q 中可借券者；兩邊市值加權，各 100%。只用成員 ≥ 3 檔、且有可放空股票的產業。"""
    s = score.dropna()
    sec = sector.reindex(s.index)
    legs = {}
    for name, idx in s.groupby(sec).groups.items():
        sub = s.loc[idx]
        if len(sub) < 3:
            continue
        r = sub.rank(pct=True)
        top, bot = sub[r > 1 - q].index, sub[r <= q].index
        bot = bot[borrowable.reindex(bot).fillna(False).to_numpy(bool)]
        if len(top) and len(bot):
            legs[name] = (top, bot, cap.reindex(sub.index).sum())
    if not legs:
        return pd.Series(dtype=float)
    total = sum(v[2] for v in legs.values())
    out = []
    for top, bot, c in legs.values():
        out.append(cap_weights(top, cap) * c / total)
        out.append(-cap_weights(bot, cap) * c / total)
    return pd.concat(out)


# ---------------------------------------------------------------------------
# 模擬
# ---------------------------------------------------------------------------

def simulate_weights(weights: dict, rets: pd.DataFrame, betas: pd.DataFrame, tx: pd.Series, schedule: list,
                     fee: pd.DataFrame | None = None, fee_mult: float = 1.0) -> pd.DataFrame:
    """weights：{換倉日: 帶正負號的權重}；每日報酬 = Σw·r − β·台指期 − 借券費；回傳 [ret, beta, turnover, borrow, long_n, long_max]。"""
    rows, w_prev, b_prev = [], pd.Series(dtype=float), 0.0
    days = rets.index
    for k, d in enumerate(schedule):
        nxt = schedule[k + 1] if k + 1 < len(schedule) else lp.HOLDOUT
        w = weights[d]
        w = w[w != 0]
        names = list(w.index)
        b = float(np.nansum(w.to_numpy() * betas.loc[d, names].fillna(1.0).to_numpy())) if names else 0.0
        to = float(w.sub(w_prev, fill_value=0.0).abs().sum())
        cost = to * lp.STOCK_COST + abs(b - b_prev) * lp.FUT_COST
        period = days[(days > d) & (days <= nxt)]
        R = rets.loc[period, names].fillna(0.0).to_numpy()
        gross = R @ w.to_numpy()
        ret = gross - b * tx.reindex(period).fillna(0.0).to_numpy()
        borrow = np.zeros(len(period))
        short = -w[w < 0]
        if fee is not None and len(short):
            rate = fee.loc[d, short.index].fillna(fee.loc[d].median()).to_numpy() / 100 * fee_mult
            borrow[:] = float(short.to_numpy() @ rate) / 252
            ret = ret - borrow
        if len(period):
            ret[0] -= cost
        long = w[w > 0]
        long = long / long.sum() if long.sum() > 0 else long
        df = pd.DataFrame({"ret": ret, "beta": b, "turnover": 0.0, "borrow": borrow,
                           "long_n": 1.0 / float((long ** 2).sum()) if len(long) else 0.0,
                           "long_max": float(long.max()) if len(long) else 0.0}, index=period)
        if len(period):
            df.iloc[0, df.columns.get_loc("turnover")] = to
        rows.append(df)
        w_prev, b_prev = w, b
    return pd.concat(rows)


def lending_fees(client, tickers: list, index: pd.DatetimeIndex) -> pd.DataFrame:
    """每檔前 60 個交易日（到 t−1）的借券成交量加權費率（年化 %）；沒有成交 → NaN（借不到）。"""
    vol_fee, vol = {}, {}
    for t in tickers:
        d = client.get("TaiwanStockSecuritiesLending", t.split(".")[0], lp.EV_START, lp.EV_END)
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"]), v=d["volume"].astype(float), f=d["fee_rate"].astype(float))
        g = d.assign(vf=d["v"] * d["f"]).groupby("date")[["vf", "v"]].sum()
        vol_fee[t], vol[t] = g["vf"], g["v"]
    VF = pd.DataFrame(vol_fee).reindex(index=index, columns=tickers).fillna(0.0)
    V = pd.DataFrame(vol).reindex(index=index, columns=tickers).fillna(0.0)
    rate = VF.rolling(FEE_WINDOW, min_periods=1).sum() / V.rolling(FEE_WINDOW, min_periods=1).sum().replace(0, np.nan)
    return rate.shift(1)


def stats(x: pd.Series, sim: pd.DataFrame | None = None) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    out = {"sh_oos": lp.sharpe(x[x.index < lp.SPLIT]), "sh_is": lp.sharpe(x[x.index >= lp.SPLIT]),
           "ann": float((1 + x).prod() ** (252 / len(x)) - 1), "vol": float(x.std() * math.sqrt(252)),
           "mdd": float((eq / eq.cummax() - 1).min()),
           "yearly": {int(y): lp.sharpe(g) for y, g in x.groupby(x.index.year)}}
    if sim is not None:
        yrs = len(sim) / 252
        out.update(turnover=float(sim["turnover"].sum() / yrs), borrow=float(sim["borrow"].sum() / yrs),
                   long_n=float(sim["long_n"].mean()), long_max=float(sim["long_max"].mean()))
    return out


# ---------------------------------------------------------------------------
# 主程式
# ---------------------------------------------------------------------------

def main(top_n: int):
    c = lp.prepare(top_n)
    cap = np.exp(c.logcap)
    fee = lending_fees(c.client, c.tickers, c.adj.index)
    borrowable = fee.notna()
    sched = c.schedule
    members = {d: c.member.columns[c.member.loc[d]] for d in sched}

    # 基準
    ew_base = lp.simulate({d: pd.Series(1.0, index=members[d]) for d in sched}, c.rets, c.betas, c.tx, sched, c.sector, q=1.0)
    cw_base_w = {d: cw_long(pd.Series(1.0, index=members[d]), c.sector, cap.loc[d], q=1.0) for d in sched}
    cw_base = simulate_weights(cw_base_w, c.rets, c.betas, c.tx, sched)
    series = {"base_ew": ew_base["alpha"], "base_cw": cw_base["ret"]}
    table = {"基準：等權（原版）": stats(ew_base["alpha"]), "基準：市值加權": stats(cw_base["ret"], cw_base)}

    leg_names = ["sue"] + [n for n in lp.LEGS_PRICE + lp.LEGS_CHIP if n in c.raws]
    rows = []
    for name in leg_names:
        scores = lp.leg_scores(c, name)
        ew = lp.simulate(scores, c.rets, c.betas, c.tx, sched, c.sector)
        wl = {d: cw_long(scores[d], c.sector, cap.loc[d]) for d in sched}
        cwl = simulate_weights(wl, c.rets, c.betas, c.tx, sched)
        wls = {d: cw_long_short(scores[d], c.sector, cap.loc[d], borrowable.loc[d]) for d in sched}
        ls = simulate_weights(wls, c.rets, c.betas, c.tx, sched, fee=fee)
        ls2 = simulate_weights(wls, c.rets, c.betas, c.tx, sched, fee=fee, fee_mult=2.0)
        r = {"leg": name, "ew": stats(ew["alpha"]), "cw": stats(cwl["ret"], cwl),
             "cw_ex": stats(cwl["ret"] - cw_base["ret"].reindex(cwl.index)),
             "ls": stats(ls["ret"], ls), "ls2": stats(ls2["ret"], ls2)}
        rows.append(r)
        for k, s in (("ew", ew["alpha"]), ("cw", cwl["ret"]), ("ls", ls["ret"]), ("ls_fee2x", ls2["ret"])):
            series[f"{name}_{k}"] = s
        print(f"  {name}: EW {r['ew']['sh_oos']:.2f}/{r['ew']['sh_is']:.2f}  CW {r['cw']['sh_oos']:.2f}/{r['cw']['sh_is']:.2f}  "
              f"多空 {r['ls']['sh_oos']:.2f}/{r['ls']['sh_is']:.2f}（借券 {r['ls']['borrow']:.2%}/年）", flush=True)

    out_dir = ROOT / "reports" / "legs"
    pd.DataFrame(series).to_csv(out_dir / f"hedge_top{top_n}.csv")

    def yearly(d):
        return "、".join(f"{y}:{v:+.1f}" for y, v in d["yearly"].items() if v == v)

    lines = [f"# 對沖結構差：市值加權與多空（全市場市值前 {top_n} 檔，自動產生）", "",
             "由 [analysis/hedge_construction.py](../analysis/hedge_construction.py) 產生；設計見程式開頭。"
             "Sharpe 為年化（無風險利率 0），兩段為 2019–2022 / 2023–2026/04；所有版本都已扣股票、期貨成本，多空另扣借券費。", "",
             "## 基準（持有整個股票池、β × 台指期對沖）", "",
             "| 基準 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 逐年 Sharpe |", "|---|---|---|---|---|---|---|"]
    for k, d in table.items():
        lines.append(f"| {k} | {d['sh_oos']:.2f} | {d['sh_is']:.2f} | {d['ann']:+.1%} | {d['vol']:.1%} | {d['mdd']:.1%} | {yearly(d)} |")
    lines += ["", "## 各腿：三種建構的 Sharpe", "",
              "| 腿 | 等權做多（原版） | 市值加權做多 | 市值加權做多 − 市值加權基準 | 市值加權多空 | 多空（借券費 × 2） |",
              "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['leg']} | " + " | ".join(f"{r[k]['sh_oos']:.2f} / {r[k]['sh_is']:.2f}" for k in ("ew", "cw", "cw_ex", "ls", "ls2")) + " |")
    lines += ["", "## 月營收驚奇（sue）細節", "",
              "| 版本 | 年化報酬 | 年化波動 | 最大回撤 | 年換手（倍） | 借券成本／年 | 做多有效檔數 | 做多最大單檔權重 | 逐年 Sharpe |",
              "|---|---|---|---|---|---|---|---|---|"]
    s = rows[0]
    for k, label in (("ew", "等權做多"), ("cw", "市值加權做多"), ("ls", "市值加權多空"), ("ls2", "多空（借券費 × 2）")):
        d = s[k]
        lines.append(f"| {label} | {d['ann']:+.1%} | {d['vol']:.1%} | {d['mdd']:.1%} | {d.get('turnover', float('nan')):.1f} | "
                     f"{d.get('borrow', 0.0):.2%} | {d.get('long_n', float('nan')):.0f} | {d.get('long_max', float('nan')):.0%} | {yearly(d)} |")
    lines += ["", f"可借券（前 {FEE_WINDOW} 日有借券成交）的成員比例：{float(borrowable.where(c.member).stack().mean()):.0%}；"
              f"成員的借券費率中位數 {float(fee.where(c.member).stack().median()):.2f}%／年。"]
    (ROOT / "docs" / f"hedge_construction_top{top_n}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]))
