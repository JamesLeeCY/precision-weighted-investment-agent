"""I031 用股票期貨執行 fv5（點子卡 research/ideas/I031-fv5-single-stock-futures-execution.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/futures_exec.py
輸出 docs/futures_exec.md。FinMind 約 400 次（每個有股票期貨的前 500 名成員 1 次，可中斷續抓）＋期交所標的清單 1 次。

設計（依點子卡；補充以「補」標示）：
- 標的對照：期交所「股票期貨、選擇權商品代碼」清單（/cht/2/stockLists），標準型（2,000 股）股票期貨，期貨代號 = 商品代碼 + "F"。
  清單只有目前上市中的商品，已下市的期貨視為不可用（保守，補）。
- 期貨報酬：一般交易時段、月契約；持有「到期日（該月第三個星期三，遇休市取之後第一個交易日）前第 3 個交易日以前」最近月的契約，
  之後轉到次月。日報酬 = 持有契約的結算價變動（結算價缺值用收盤價，補）；轉倉日記一次轉倉。
- 追蹤誤差檢查（看策略結果前）：每檔每月期貨報酬與現股含息報酬的差，絕對值中位數需 < 0.5%，否則停止。
- 期貨可用（換倉日當時，只用過去資料）：有持有契約資料、該檔持有契約前 20 日平均成交量 ≥ 50 口、擬建口數 ≤ 前一日未平倉量 10%；
  擬建口數 = 每份資金（V1：2 億 ÷ 3；V2：2 億，補）× |權重| ÷（2,000 × 換倉日收盤價）。
- 成本：期貨每邊 = 期交稅 0.00002 ＋ 手續費 50 元 ÷ 每口名目 ＋ 滑價 0.10%（前 20 日平均成交量 < 200 口時 0.20%）；轉倉日兩邊都計；
  保證金現金報酬 0。現股部分沿用 fv5（單邊 0.29625%、借券費逐日；期貨放空不付借券費）。
- 版本：V1 混合執行（fv5 名單與權重不變、每 3 個換倉日換倉、三份錯開；可用期貨者多空皆改用期貨）；V2 同 V1 但每月全部換倉。
  基準 fv5 用同一個模擬程式全部以現股執行（應接近 1.45 / 1.87）。
- 通過：V1 兩段 Sharpe ≥ fv5 且全期 ≥ fv5 全期 + 0.10；V2 兩段都 ≥ V1 才考慮每月換倉。
- 只報告：期貨執行占做多／放空權重比例、成本拆解（年化）、追蹤誤差分布、放空候選中「借不到但有可用期貨」的檔數。
研究結果，非投資建議。
"""
import html
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402

LIST = ROOT / "data_cache" / "events" / "taifex_stocklists.html"
TAX, COMM, SLIP, SLIP_THIN = 0.00002, 50.0, 0.0010, 0.0020
MULT = 2000
CAP = 2e8


def stock_futures_map() -> dict:
    if not LIST.exists():
        r = requests.get("https://www.taifex.com.tw/cht/2/stockLists", headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        LIST.write_text(r.text, encoding="utf-8")
    t = LIST.read_text(encoding="utf-8")
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
        c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        if len(c) >= 12 and re.fullmatch(r"[A-Z]{2,3}", c[0]) and re.fullmatch(r"\d{4}", c[2]) and "是股票期貨標的" in c[4] and c[11].replace(",", "") == "2000":
            out[c[2]] = c[0] + "F"
    return out


def expiry(ym: str, days: pd.DatetimeIndex) -> pd.Timestamp:
    y, m = int(ym[:4]), int(ym[4:])
    d = pd.Timestamp(y, m, 1)
    wed = d + pd.Timedelta(days=(2 - d.weekday()) % 7 + 14)
    k = int(days.searchsorted(wed))
    return days[k] if k < len(days) else wed


def fut_series(client, fid: str, days: pd.DatetimeIndex):
    """回傳 DataFrame（index = days）：ret（持有契約日報酬）、roll（當日是否轉倉）、vol20、oi_prev、avail。"""
    d = client.get("TaiwanFuturesDaily", fid, "2019-01-01", "2026-05-31")
    if d.empty:
        return None
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}")].copy()
    if d.empty:
        return None
    d["date"] = pd.to_datetime(d["date"])
    d["px"] = d["settlement_price"].astype(float).where(d["settlement_price"].astype(float) > 0, d["close"].astype(float))
    px = d.pivot_table(index="date", columns="contract_date", values="px")
    vol = d.pivot_table(index="date", columns="contract_date", values="volume")
    oi = d.pivot_table(index="date", columns="contract_date", values="open_interest")
    idx = days[(days >= px.index.min()) & (days <= px.index.max())]
    px, vol, oi = px.reindex(idx), vol.reindex(index=idx, columns=px.columns), oi.reindex(index=idx, columns=px.columns)
    exp = {c: expiry(str(c), days) for c in px.columns}
    held = []
    for t in idx:
        k = int(days.searchsorted(t))
        lim = days[min(k + 3, len(days) - 1)]
        cands = sorted(c for c in px.columns if exp[c] > lim and px.at[t, c] == px.at[t, c])
        held.append(cands[0] if cands else None)
    ret = pd.Series(np.nan, index=idx)
    roll = pd.Series(False, index=idx)
    hv = pd.Series(np.nan, index=idx)
    ho = pd.Series(np.nan, index=idx)
    for i, t in enumerate(idx):
        c = held[i]
        if c is not None:
            hv.iat[i] = vol.at[t, c]
            ho.iat[i] = oi.at[t, c]
        if i == 0:
            continue
        p = held[i - 1]
        if p is not None and px.at[idx[i - 1], p] > 0 and px.at[t, p] == px.at[t, p]:
            ret.iat[i] = px.at[t, p] / px.at[idx[i - 1], p] - 1
        roll.iat[i] = p is not None and c is not None and c != p
    out = pd.DataFrame({"ret": ret, "roll": roll, "vol20": hv.rolling(20, min_periods=15).mean().shift(1),
                        "oi_prev": ho.shift(1), "has": pd.Series([h is not None for h in held], index=idx)})
    return out.reindex(days)


def simulate(wd: dict, sched: list, c, F: dict, close, fee, cap: float, use_fut: bool):
    """回傳（日報酬, 統計 dict）。wd：{換倉日: 權重}；F：{ticker: fut DataFrame}。"""
    days = c.rets.index
    rows, prev = [], {"S": pd.Series(dtype=float), "F": pd.Series(dtype=float)}
    b_prev = 0.0
    acc = {"stock_cost": 0.0, "fut_cost": 0.0, "roll_cost": 0.0, "borrow": 0.0, "fut_long": [], "fut_short": []}
    for k, d in enumerate(sched):
        nxt = sched[k + 1] if k + 1 < len(sched) else lp.HOLDOUT
        w = wd[d]
        w = w[w != 0]
        fset = set()
        if use_fut:
            for t, x in w.items():
                f = F.get(t)
                if f is None or d not in f.index or not bool(f.at[d, "has"]) or not f.at[d, "vol20"] >= 50:
                    continue
                pxd = close.at[d, t] if t in close.columns else np.nan
                n = cap * abs(x) / (MULT * pxd) if pxd == pxd and pxd > 0 else np.inf
                if n <= 0.10 * f.at[d, "oi_prev"]:
                    fset.add(t)
        wf, ws = w[[t in fset for t in w.index]], w[[t not in fset for t in w.index]]
        acc["fut_long"].append(float(wf[wf > 0].sum() / max(w[w > 0].sum(), 1e-12)))
        acc["fut_short"].append(float(-wf[wf < 0].sum() / max(-w[w < 0].sum(), 1e-12)))
        b = float(np.nansum(w.to_numpy() * c.betas.loc[d, list(w.index)].fillna(1.0).to_numpy())) if len(w) else 0.0
        to_s = float(ws.sub(prev["S"], fill_value=0.0).abs().sum())
        dfu = wf.sub(prev["F"], fill_value=0.0).abs()

        def fcost(t):
            f = F[t]
            pxd = close.at[d, t]
            slip = SLIP_THIN if f.at[d, "vol20"] < 200 else SLIP
            return TAX + COMM / (MULT * pxd) + slip if pxd == pxd and pxd > 0 else TAX + SLIP_THIN
        fc = float(sum(v * fcost(t) for t, v in dfu.items() if t in F and d in F[t].index and v > 0)) if len(dfu) else 0.0
        cost = to_s * lp.STOCK_COST + fc + abs(b - b_prev) * lp.FUT_COST
        acc["stock_cost"] += to_s * lp.STOCK_COST
        acc["fut_cost"] += fc
        period = days[(days > d) & (days <= nxt)]
        Rs = c.rets.reindex(index=period, columns=list(ws.index)).fillna(0.0).to_numpy() @ ws.to_numpy() if len(ws) else np.zeros(len(period))
        Rf = np.zeros(len(period))
        rc = np.zeros(len(period))
        for t, x in wf.items():
            f = F[t].reindex(period)
            Rf += f["ret"].fillna(c.rets.reindex(period)[t].fillna(0.0)).to_numpy() * x
            rc += f["roll"].fillna(False).to_numpy(bool) * 2 * abs(x) * fcost(t)
        ret = Rs + Rf - b * c.tx.reindex(period).fillna(0.0).to_numpy() - rc
        short = -ws[ws < 0]
        if len(short):
            rate = fee.loc[d, short.index].fillna(fee.loc[d].median()).to_numpy() / 100
            daily_b = float(short.to_numpy() @ rate) / 252
            ret = ret - daily_b
            acc["borrow"] += daily_b * len(period)
        acc["roll_cost"] += float(rc.sum())
        if len(period):
            ret[0] -= cost
        rows.append(pd.Series(ret, index=period))
        prev, b_prev = {"S": ws, "F": wf}, b
    r = pd.concat(rows)
    return r, acc


def main():
    c = lp.prepare(500)
    days = c.adj.index
    sched = c.schedule
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)
    sue = lp.leg_scores(c, "sue")
    fmap = stock_futures_map()
    F = {}
    for i, t in enumerate(c.tickers):
        sid = t.split(".")[0]
        if sid in fmap:
            s = fut_series(c.client, fmap[sid], days)
            if s is not None:
                F[t] = s
        if i % 100 == 0:
            print(f"期貨 {i}/{len(c.tickers)}（已有 {len(F)} 檔）", flush=True)
    # 追蹤誤差檢查
    te = []
    for t, f in F.items():
        g = pd.DataFrame({"f": f["ret"], "s": c.rets[t]}).dropna()
        g = g[(g.index >= "2019-01-01") & (g.index < lp.HOLDOUT)]
        if len(g) < 20:
            continue
        m = g.groupby(g.index.to_period("M")).apply(lambda x: (1 + x["f"]).prod() - (1 + x["s"]).prod())
        te += list(m.abs().to_numpy())
    te = np.array(te)
    L = ["# I031 用股票期貨執行 fv5（自動產生）", "",
         "由 [analysis/futures_exec.py](../analysis/futures_exec.py) 產生；設計見程式開頭（看結果前固定）。"
         "Sharpe 為扣成本與台指期對沖後，格式 2019–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         f"期交所標準型股票期貨標的 {len(fmap)} 檔；其中曾為前 500 名且 FinMind 有資料者 {len(F)} 檔。", "",
         f"**追蹤誤差**（期貨月報酬 − 現股含息月報酬，{len(te):,} 個股票月）：絕對值中位數 {np.median(te):.2%}、"
         f"第 75 百分位 {np.percentile(te, 75):.2%}、第 95 百分位 {np.percentile(te, 95):.2%}（門檻：中位數 < 0.5%）。", ""]
    if not np.median(te) < 0.005:
        L.append("**追蹤誤差超過門檻，依點子卡停止。**")
        (ROOT / "docs" / "futures_exec.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("STOP te", flush=True)
        return

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def run(step_all: bool, use_fut: bool):
        if step_all:
            wd = {d: lt.ew_ls_buffer(sue[d], c.sector, shortable_at(d), q_keep=None) for d in sched}
            r, acc = simulate(wd, sched, c, F, close, fee, CAP, use_fut)
            r = r[r.index > sched[2]]
            return r, acc
        parts, accs = [], []
        for off in range(3):
            sub = sched[off::3]
            wd = {d: lt.ew_ls_buffer(sue[d], c.sector, shortable_at(d), q_keep=None) for d in sub}
            r, acc = simulate(wd, sub, c, F, close, fee, CAP / 3, use_fut)
            parts.append(r)
            accs.append(acc)
        x = pd.concat(parts, axis=1).mean(axis=1)
        acc = {k: (np.mean([a[k] for a in accs]) if not isinstance(accs[0][k], list) else sum((a[k] for a in accs), [])) for k in accs[0]}
        return x[x.index > sched[2]], acc
    res = {}
    for name, step_all, uf in (("fv5（全部現股，同一模擬）", False, False), ("V1 混合執行（每 3 個月、三份錯開）", False, True),
                               ("V2 混合執行、每月全部換倉", True, True), ("只報告：每月全部換倉、全部現股", True, False)):
        r, acc = run(step_all, uf)
        yrs = len(r) / 252
        res[name] = hc.stats(r) | {"full": lp.sharpe(r.dropna()), "acc": acc, "yrs": yrs}
    # 借不到但有期貨的放空候選
    extra = []
    for d in sched:
        s = sue[d].dropna()
        r = s.groupby(c.sector.reindex(s.index)).rank(pct=True)
        cand = r[r <= 1 / 3].index
        sh = shortable_at(d).reindex(cand).fillna(False)
        extra.append(sum(1 for t in cand[~sh.to_numpy(bool)] if t in F and d in F[t].index and F[t].at[d, "has"] and F[t].at[d, "vol20"] >= 50))
    b, v1, v2 = res["fv5（全部現股，同一模擬）"], res["V1 混合執行（每 3 個月、三份錯開）"], res["V2 混合執行、每月全部換倉"]
    p1 = v1["sh_oos"] >= b["sh_oos"] and v1["sh_is"] >= b["sh_is"] and v1["full"] >= b["full"] + 0.10
    p2 = v2["sh_oos"] >= v1["sh_oos"] and v2["sh_is"] >= v1["sh_is"]
    L += ["| 版本 | Sharpe | 全期 | 年化報酬 | 最大回撤 | 期貨占做多／放空權重 | 年化成本：現股／期貨換倉／轉倉／借券 |", "|---|---|---|---|---|---|---|"]
    for k, s in res.items():
        a, y = s["acc"], s["yrs"]
        fl = f"{np.mean(a['fut_long']):.0%} / {np.mean(a['fut_short']):.0%}" if a["fut_long"] else "—"
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {fl} | "
                 f"{a['stock_cost'] / y:.2%} / {a['fut_cost'] / y:.2%} / {a['roll_cost'] / y:.2%} / {a['borrow'] / y:.2%} |")
    L += ["", f"放空候選（產業內後 1/3）中借券條件 D 不通過、但有可用期貨的股票：每個換倉日平均 {np.mean(extra):.1f} 檔（V1 名單不變，未加入，只報告）。", "",
          "## 判定", "",
          f"1. V1 兩段 Sharpe ≥ fv5（{b['sh_oos']:.2f} / {b['sh_is']:.2f}）且全期 ≥ {b['full'] + 0.10:.2f}：{v1['sh_oos']:.2f} / {v1['sh_is']:.2f}、全期 {v1['full']:.2f} → {'✓' if p1 else '✗'}",
          f"2. V2 兩段 ≥ V1：{v2['sh_oos']:.2f} / {v2['sh_is']:.2f} → {'✓' if p2 else '✗'}", "",
          f"**結論：{'V1 通過' if p1 else 'V1 未通過'}；{'V2 優於 V1' if p2 else 'V2 未優於 V1'}**"]
    (ROOT / "docs" / "futures_exec.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
