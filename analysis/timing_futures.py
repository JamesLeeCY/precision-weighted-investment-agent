"""擇時規則改用台指期執行：持有 100% 0050 不動，以放空台指期把淨曝險調到規則要求的比例。

用法（於專案根目錄；需 reports/txo_vix.csv 與 data_cache/ndc/ 的景氣燈號）：
    .venv/Scripts/python analysis/timing_futures.py
輸出 docs/timing_futures.md 與 reports/timing_futures.csv。

設計（看結果前固定）：
- 淨曝險 e_t（各規則以第 t−1 日收盤以前的資訊決定）；避險部位 h_t = 1 − e_t（放空台指期，以持有市值比例計）。
- 每日報酬 = 0050 含息報酬 − h_t × 台指期近月報酬 − 成本；成本 = |h_t − h_{t−1}| × 0.005%（單邊，含期交稅與手續費、滑價的估計）
  + 每月到期日（第三個星期三）轉倉 2 × h_t × 0.005%。保證金所需現金與其利息不計（需另備約 1–2 成的現金）。
- 台指期近月連續報酬：一般交易時段、成交量最大的月合約（同 analysis/leg_probe.tx_continuous），2008 ~ 2026/04。
- 規則（與先前研究相同的定義）：200 日線 ±2% 緩衝帶、200 日線（analysis/timing_oos）；景氣燈號 A、B（analysis/business_cycle_timing）；
  台指 VIX A1、A2、B、B′（analysis/vix_timing）。
- 對照：0050 長期持有；固定淨曝險（= 規則平均曝險，同樣用期貨，只有轉倉成本）。
- 先前以賣出 0050 執行（單邊 0.29625%）的結果見各報告；此處另列「以 0050 執行」的同規則結果作對照。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import allocation_study as al  # noqa: E402
import business_cycle_timing as bct  # noqa: E402
import timing_oos as tos  # noqa: E402
import vix_timing as vt  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402

FUT_COST = 0.00005
START, END = "2008-01-01", "2026-04-30"


def tx_returns(client) -> pd.Series:
    """台指期近月連續日報酬（分年下載）。"""
    parts = []
    for y in range(2007, 2027):
        d = client.get("TaiwanFuturesDaily", "TX", f"{y}-01-01", f"{y}-12-31")
        if not d.empty:
            parts.append(d)
    d = pd.concat(parts)
    d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}") & (d["close"].astype(float) > 0)].copy()
    d["date"] = pd.to_datetime(d["date"])
    d["close"] = d["close"].astype(float)
    front = d.sort_values(["date", "volume"]).groupby("date").tail(1).set_index("date")["contract_date"]
    px = d.pivot_table(index="date", columns="contract_date", values="close")
    dates = list(px.index)
    out = {}
    for k in range(1, len(dates)):
        c = front[dates[k]]
        p0 = px.at[dates[k - 1], c] if c in px.columns else np.nan
        out[dates[k]] = px.at[dates[k], c] / p0 - 1 if p0 == p0 and p0 > 0 else 0.0
    return pd.Series(out)


def roll_days(index: pd.DatetimeIndex) -> pd.Series:
    """每月第三個星期三（或其後第一個交易日）標記為轉倉日。"""
    flag = pd.Series(False, index=index)
    for p in pd.period_range(index.min(), index.max(), freq="M"):
        d = p.start_time
        tw = d + pd.Timedelta(days=(2 - d.weekday()) % 7 + 14)
        nxt = index[index >= tw]
        if len(nxt):
            flag[nxt[0]] = True
    return flag


def futures_overlay(expo: pd.Series, r0050: pd.Series, rtx: pd.Series) -> pd.Series:
    e = expo.reindex(r0050.index)
    h = (1 - e).clip(lower=0)
    tx = rtx.reindex(r0050.index).fillna(0.0)
    cost = h.diff().abs().fillna(h.abs()) * FUT_COST + roll_days(r0050.index).astype(float) * 2 * h * FUT_COST
    return r0050 - h * tx - cost


def stock_exec(expo: pd.Series, r0050: pd.Series) -> pd.Series:
    e = expo.reindex(r0050.index)
    return e * r0050 - e.diff().abs().fillna(0.0) * al.COST


def summary(x: pd.Series) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    return {"sharpe": float(x.mean() / x.std() * math.sqrt(252)), "ann": float(eq.iloc[-1] ** (252 / len(x)) - 1),
            "mdd": float((eq / eq.cummax() - 1).min())}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    px = get_total_return_prices(client, "0050.TW", "2003-06-30", "2026-05-31").set_index("date")["adj_close"].astype(float)
    r_all = px.pct_change()
    rtx = tx_returns(client)
    r = r_all[(r_all.index >= START) & (r_all.index <= END)]

    lights = bct.load_lights()
    vix = pd.read_csv(ROOT / "reports" / "txo_vix.csv", index_col=0, parse_dates=True)["vix"]
    vr = vt.rules(vix, r_all)
    expos = {
        "200 日線 ±2% 緩衝帶": tos.positions(px, ("ma", 200, 0.02)),
        "200 日線": tos.positions(px, ("ma", 200, 0.0)),
        "景氣燈號 A（依燈號）": bct.daily_exposure(lights["light"].map(bct.MAP_A), r_all.index),
        "景氣燈號 B（連續燈號）": bct.daily_exposure(bct.exposure_rule_b(lights["light"]), r_all.index),
        **{f"VIX {k}": v for k, v in vr.items()},
    }
    expos = {k: v.reindex(r.index) for k, v in expos.items()}

    S = {"0050 長期持有": r}
    rows = []
    for k, e in expos.items():
        avg = float(e.mean())
        fut, stk = futures_overlay(e, r, rtx), stock_exec(e, r)
        fixed = futures_overlay(pd.Series(avg, index=r.index), r, rtx)
        S[f"{k}（期貨）"], S[f"{k}（0050）"], S[f"固定 {avg:.0%}（期貨，對照 {k}）"] = fut, stk, fixed
        h = (1 - e).clip(lower=0)
        to = float(h.diff().abs().sum() / (len(r) / 252))
        d = (fut - fixed).dropna()
        rows.append((k, avg, to, summary(fut), summary(stk), summary(fixed),
                     {seg: summary(fut[m]) for seg, m in (("a", fut.index < "2016-01-01"), ("b", fut.index >= "2016-01-01"))},
                     {seg: summary(fixed[m]) for seg, m in (("a", fixed.index < "2016-01-01"), ("b", fixed.index >= "2016-01-01"))},
                     d.mean() * 252, d.mean() / (d.std() / math.sqrt(len(d)))))
    pd.DataFrame(S).to_csv(ROOT / "reports" / "timing_futures.csv")
    bh = summary(r)
    bha, bhb = summary(r[r.index < "2016-01-01"]), summary(r[r.index >= "2016-01-01"])

    lines = ["# 擇時規則改用台指期執行（自動產生）", "",
             "由 [analysis/timing_futures.py](../analysis/timing_futures.py) 產生；設計見程式開頭。持有 100% 0050，以放空台指期調整淨曝險；"
             "Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0），期間 2008 ~ 2026/04。研究結果，非投資建議。", "",
             f"0050 長期持有：Sharpe {bh['sharpe']:.2f}（2008–2015 {bha['sharpe']:.2f}、2016 ~ 2026/04 {bhb['sharpe']:.2f}）、年化 {bh['ann']:+.1%}、最大回撤 {bh['mdd']:.1%}。", "",
             "| 規則 | 平均淨曝險 | 期貨年換手 | Sharpe：期貨執行 | 0050 執行 | 固定曝險（期貨） | 期貨執行 2008–15 / 2016–26 | 固定 2008–15 / 2016–26 | 年化報酬：期貨 / 0050 / 固定 | 最大回撤：期貨 / 固定 | 期貨 − 固定（年化，t） |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, avg, to, f, s, fx, fs, fxs, dm, dt in rows:
        lines.append(f"| {k} | {avg:.0%} | {to:.1f} | {f['sharpe']:.2f} | {s['sharpe']:.2f} | {fx['sharpe']:.2f} | "
                     f"{fs['a']['sharpe']:.2f} / {fs['b']['sharpe']:.2f} | {fxs['a']['sharpe']:.2f} / {fxs['b']['sharpe']:.2f} | "
                     f"{f['ann']:+.1%} / {s['ann']:+.1%} / {fx['ann']:+.1%} | {f['mdd']:.1%} / {fx['mdd']:.1%} | {dm:+.2%}（{dt:+.2f}） |")
    (ROOT / "docs" / "timing_futures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
