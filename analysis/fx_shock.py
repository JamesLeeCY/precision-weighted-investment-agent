"""I019 匯率衝擊的延遲反應（台股版 FOREXS；點子卡 research/ideas/I019-fx-shock-revenue-exposure.md，檢定計畫看結果前固定）。

用法（於專案根目錄；資料皆已快取）：
    .venv/Scripts/python analysis/fx_shock.py
輸出 docs/fx_shock.md。

設計（依點子卡；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 匯率：FinMind TaiwanExchangeRate USD 即期買賣中價；ΔFX_m = ln(月底 USDTWD_m ÷ 月底 USDTWD_m−1)，正值 = 新台幣貶值。
- 彈性：每檔在月 m，用營收月份 m−24 ~ m−1（至少 18 個月，補）迴歸 g_t = a + β·x_t + e；
  g = 單月營收 log 年增率 − 同產業（同樣本當月成員）中位數，x = 同月月底 USDTWD 的 12 個月 log 變動。β 在產業內轉成百分位 − 0.5。
- 訊號：FXS = β 百分位 × ΔFX_m；m 月最後一個交易日收盤後計算，下一個交易日收盤進場，持有 20 個交易日（報酬為還原含息收盤）。
- 樣本：市值前 500 名成員（進場日），排除產業「金融保險」「金融業」；2020-01 ~ 2026-04（形成月），兩段 2020–2022 / 2023–2026/04；驗證第 501–1000 名。
- 主檢定：每月產業內 Spearman IC（FXS vs 之後 20 日報酬），兩段平均與 Newey-West t（落後 1）；另報 |ΔFX_m| ≥ 1.5% 月份的平均 IC。
- 增量：每月橫斷面 r = a + b·FXS + c·SUE（進場日最新月營收驚奇）+ 產業固定效果（補：FXS、SUE 用當月橫斷面百分位 − 0.5），Fama-MacBeth（NW 落後 1）；報告 FXS 與 SUE 的平均橫斷面等級相關。
- 可交易：只在 |ΔFX_m| ≥ 1.5% 的月份進場；產業內 FXS 前 20% 做多、後 20% 放空（ls_turnover.ew_ls_buffer，q_in = 0.2、不含緩衝；
  借券條件 D、2 億），持有 20 個交易日後平倉（下一次進場早於平倉日時直接換倉，補）；台指期對沖；單邊 0.29625% ＋ 借券費；空手時報酬 0。
- 通過：(1) 全部月份 IC 兩段 > 0、全期 t > 2，或大幅變動月份 IC 兩段 > 0、全期 t > 2；(2) Fama-MacBeth b 全期 t > 2、兩段同號；
  (3) 驗證樣本全期 IC 同號（> 0）；(4) 可交易版本兩段 Sharpe > 0。大幅變動月份在 2020–2022 少於 10 個時，該段只報告方向。
- 未做（只報告的探索項，補）：股價對匯率週 β 的次要定義、SUE 拆成匯率可解釋與殘差兩部分。
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
import corp_event_study as ce  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import ls_turnover as lt  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from sue_attention import nw_t  # noqa: E402

FIN = ("金融保險", "金融業")
BIG = 0.015
HOLD = 20
START_M, END_M = pd.Period("2020-01", "M"), pd.Period("2026-03", "M")   # 形成月；2026-04 底進場的持有期跨入保留期，不用（補）


def fx_monthly(client) -> pd.Series:
    d = client.get("TaiwanExchangeRate", "USD", "2016-01-01", "2026-05-31")
    s = pd.Series(((d["spot_buy"].astype(float) + d["spot_sell"].astype(float)) / 2).to_numpy(), index=pd.to_datetime(d["date"]))
    s = s[s > 0].sort_index()
    return s.resample("ME").last().to_period("M")


def revenue_growth(client, tickers) -> pd.DataFrame:
    out = {}
    for t in tickers:
        r = client.get("TaiwanStockMonthRevenue", t.split(".")[0], "2017-01-01")
        if r.empty:
            continue
        p = pd.PeriodIndex([pd.Period(year=int(y), month=int(m), freq="M") for y, m in zip(r["revenue_year"], r["revenue_month"])])
        v = pd.Series(r["revenue"].astype(float).to_numpy(), index=p)
        v = v[~v.index.duplicated(keep="last")].sort_index()
        v = v.reindex(pd.period_range(v.index.min(), v.index.max(), freq="M"))
        out[t] = np.log(v.where(v > 0) / v.shift(12).where(v.shift(12) > 0))
    return pd.DataFrame(out)


def betas(g: pd.DataFrame, x: pd.Series, sector: pd.Series, member_m: dict) -> dict:
    """{形成月 m: β Series}；g 先減同產業（當月成員）中位數。"""
    gd = g.copy()
    for p in gd.index:
        mem = member_m.get(p)
        cols = [c for c in gd.columns if mem is None or c in mem]
        row = gd.loc[p, cols]
        med = row.groupby(sector.reindex(row.index)).transform("median")
        gd.loc[p, cols] = row - med
    out = {}
    for m in pd.period_range(START_M, END_M, freq="M"):
        win = pd.period_range(m - 24, m - 1, freq="M")
        X = x.reindex(win)
        G = gd.reindex(win)
        ok_x = X.notna().to_numpy()
        b = {}
        for t in G.columns:
            y = G[t].to_numpy()
            ok = ok_x & np.isfinite(y)
            if ok.sum() >= 18:
                xx, yy = X.to_numpy()[ok], y[ok]
                vx = xx.var()
                if vx > 0:
                    b[t] = float(((xx - xx.mean()) * (yy - yy.mean())).mean() / vx)
        out[m] = pd.Series(b)
    return out


def run_sample(S: ce.Sample, fx: pd.Series, client) -> dict:
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    keep = [t for t in S.tickers if sector[t] not in FIN]
    g = revenue_growth(client, keep)
    x = np.log(fx / fx.shift(12))
    dfx = np.log(fx / fx.shift(1))
    days = S.days
    member_m = {}
    for p in g.index:
        k = int(days.searchsorted(p.to_timestamp(how="end").normalize(), side="right")) - 1
        if 0 <= k < len(days):
            member_m[p] = set(S.member.columns[S.member.iloc[k].to_numpy(bool)])
    B = betas(g, x, sector, member_m)
    rows = []
    for m, b in B.items():
        k = int(days.searchsorted(m.to_timestamp(how="end").normalize(), side="right")) - 1   # m 月最後一個交易日
        ke = k + 1
        if ke + HOLD >= S.limit:
            continue
        mem = S.member.iloc[ke]
        b = b[[t for t in b.index if t in mem.index and bool(mem[t]) and t in keep]]
        if len(b) < 30:
            continue
        rank = b.groupby(sector.reindex(b.index)).rank(pct=True) - 0.5
        fxs = rank * float(dfx.get(m, np.nan))
        fwd = S.adj.iloc[ke + HOLD] / S.adj.iloc[ke] - 1
        rows.append({"m": m, "ke": ke, "dfx": float(dfx.get(m, np.nan)), "fxs": fxs, "fwd": fwd.reindex(fxs.index),
                     "sue": S.sue.iloc[ke].reindex(fxs.index)})
    return {"rows": rows, "sector": sector}


def seg(p: pd.Period) -> str:
    return "2020–2022" if p.year <= 2022 else "2023–2026/04"


def tstat(x: pd.Series, lag=1) -> tuple:
    x = x.dropna()
    return (float(x.mean()) if len(x) else float("nan"), nw_t(x, lag) if len(x) >= 5 else float("nan"), len(x))


def f3(x, d=3) -> str:
    m, t, n = x
    if m != m:
        return "—"
    s = f"{m:+.{d}f}" if d else f"{m:+.2%}"
    return f"{s}（{t:.1f}，{n}）" if t == t else f"{s}（—，{n}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    fx = fx_monthly(client)
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 500, mkt, tx)
    res = run_sample(S, fx, client)
    sector = res["sector"]
    ic = pd.Series({r["m"]: lp.within_ic(r["fxs"], r["fwd"], sector) for r in res["rows"]})
    big = pd.Series({r["m"]: abs(r["dfx"]) >= BIG for r in res["rows"]})
    corr = pd.Series({r["m"]: r["fxs"].rank().corr(r["sue"].rank()) for r in res["rows"]})
    # Fama-MacBeth
    fm = {}
    for r in res["rows"]:
        df = pd.DataFrame({"y": r["fwd"], "fxs": r["fxs"], "sue": r["sue"], "sec": sector.reindex(r["fxs"].index)}).dropna()
        if len(df) < 50:
            continue
        X = np.column_stack([np.ones(len(df)), df["fxs"].rank(pct=True) - 0.5, df["sue"].rank(pct=True) - 0.5,
                             pd.get_dummies(df["sec"], drop_first=True, dtype=float).to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df["y"].to_numpy(float), rcond=None)
        fm[r["m"]] = beta[1]
    fm = pd.Series(fm)
    # 驗證
    V = ce.Sample(client, 501, 1000, mkt, tx)
    vres = run_sample(V, fx, client)
    vic = pd.Series({r["m"]: lp.within_ic(r["fxs"], r["fwd"], vres["sector"]) for r in vres["rows"]})
    vbig = pd.Series({r["m"]: abs(r["dfx"]) >= BIG for r in vres["rows"]})
    # 可交易
    fee = hc.lending_fees(client, S.tickers, S.days)
    quota, lend60 = bc.load_short_data(client, S.tickers, S.days)

    def shortable_at(k):
        d = S.days[k]
        n_short = max(1, int(S.member.iloc[k].sum() / 5))
        need = 2e8 / n_short / S.close.iloc[k]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)
    wd, sched = {}, []
    trades = [r for r in res["rows"] if abs(r["dfx"]) >= BIG]
    for i, r in enumerate(trades):
        d_in, d_out = S.days[r["ke"]], S.days[r["ke"] + HOLD]
        wd[d_in] = lt.ew_ls_buffer(r["fxs"], sector, shortable_at(r["ke"]), q_in=0.2, q_keep=None)
        sched.append(d_in)
        nxt = S.days[trades[i + 1]["ke"]] if i + 1 < len(trades) else None
        if nxt is None or nxt > d_out:
            wd[d_out] = pd.Series(dtype=float)
            sched.append(d_out)
    sim = hc.simulate_weights(wd, S.rets, S.betas, S.tx, sched, fee=fee)
    full_idx = S.days[(S.days > S.days[res["rows"][0]["ke"]]) & (S.days < lp.HOLDOUT)]
    ret = sim["ret"].reindex(full_idx).fillna(0.0)
    st = hc.stats(ret)

    def by_seg(x: pd.Series, mask=None):
        x = x if mask is None else x[mask.reindex(x.index).fillna(False).astype(bool)]
        return {s: tstat(x[[seg(p) == s for p in x.index]]) for s in ("2020–2022", "2023–2026/04")} | {"全期": tstat(x)}
    a_all, a_big, a_fm, a_v, a_vbig = by_seg(ic), by_seg(ic, big), by_seg(fm), by_seg(vic), by_seg(vic, vbig)
    n_big = {s: int(sum(1 for p, v in big.items() if v and seg(p) == s)) for s in ("2020–2022", "2023–2026/04")}

    L = ["# I019 匯率衝擊的延遲反應（自動產生）", "",
         "由 [analysis/fx_shock.py](../analysis/fx_shock.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（FXS vs 進場後 20 個交易日報酬，−1～1，0 為無預測力），括號為（Newey-West t 值，月份數）；"
         "Fama-MacBeth 係數為 FXS 百分位差 1 對應的 20 日報酬差；Sharpe 為扣成本與台指期對沖後，格式 2020–2022 / 2023–2026/04。研究結果，非投資建議。", "",
         f"形成月 {len(res['rows'])} 個（{res['rows'][0]['m']} ~ {res['rows'][-1]['m']}）；|ΔFX| ≥ 1.5% 的月份：2020–2022 {n_big['2020–2022']} 個、"
         f"2023–2026/04 {n_big['2023–2026/04']} 個。FXS 與 SUE 的平均橫斷面等級相關 {corr.mean():+.3f}。", "",
         "| 統計量 | 2020–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|",
         "| 主樣本 IC：全部月份 | " + " | ".join(f3(a_all[s]) for s in a_all) + " |",
         "| 主樣本 IC：大幅變動月份 | " + " | ".join(f3(a_big[s]) for s in a_big) + " |",
         "| Fama-MacBeth FXS 係數（控制 SUE、產業） | " + " | ".join(f3(a_fm[s], 0) for s in a_fm) + " |",
         "| 驗證樣本 IC：全部月份 | " + " | ".join(f3(a_v[s]) for s in a_v) + " |",
         "| 驗證樣本 IC：大幅變動月份 | " + " | ".join(f3(a_vbig[s]) for s in a_vbig) + " |", "",
         f"**可交易版本**（只在大幅變動月份進場，產業內前／後 20%，借券條件 D、2 億，持有 20 日；{len(trades)} 次進場）："
         f"Sharpe {st['sh_oos']:.2f} / {st['sh_is']:.2f}，年化 {st['ann']:+.1%}，最大回撤 {st['mdd']:.1%}。", ""]
    c1a = a_all["2020–2022"][0] > 0 and a_all["2023–2026/04"][0] > 0 and a_all["全期"][1] > 2
    short_seg = n_big["2020–2022"] < 10
    c1b = (a_big["2023–2026/04"][0] > 0 and (short_seg or a_big["2020–2022"][0] > 0)) and a_big["全期"][1] > 2
    c1 = c1a or c1b
    c2 = a_fm["全期"][1] > 2 and np.sign(a_fm["2020–2022"][0]) == np.sign(a_fm["2023–2026/04"][0])
    c3 = a_v["全期"][0] > 0
    c4 = st["sh_oos"] > 0 and st["sh_is"] > 0
    L += ["## 判定", "",
          f"1. 全部月份 IC 兩段 > 0、全期 t > 2：{'✓' if c1a else '✗'}；或大幅變動月份兩段 > 0、全期 t > 2"
          f"{'（2020–2022 不足 10 個月，只看方向）' if short_seg else ''}：{'✓' if c1b else '✗'} → {'✓' if c1 else '✗'}",
          f"2. Fama-MacBeth 全期 t > 2、兩段同號：{f3(a_fm['全期'], 0)} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本全期 IC > 0：{f3(a_v['全期'])} → {'✓' if c3 else '✗'}",
          f"4. 可交易版本兩段 Sharpe > 0：{st['sh_oos']:.2f} / {st['sh_is']:.2f} → {'✓' if c4 else '✗'}", "",
          f"**結論：{'訊號有效' + ('、可交易版本通過' if c4 else '、可交易版本未通過') if c1 and c2 else '未通過'}**"]
    (ROOT / "docs" / "fx_shock.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
