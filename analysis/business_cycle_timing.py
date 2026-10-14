"""景氣對策信號（國發會景氣燈號）逆向擇時：藍燈多持股、紅燈少持股，與 0050 長期持有比較。

用法（於專案根目錄；資料 data_cache/ndc/extracted/景氣指標與燈號.csv 來自 data.gov.tw/dataset/6099）：
    .venv/Scripts/python analysis/business_cycle_timing.py
輸出 docs/business_cycle_timing.md 與 reports/business_cycle_timing.csv。

設計（看結果前固定，使用者 2026-10-14 提出的逆向邏輯，不挑參數）：
- 燈號時點：第 m 月的燈號（實際約在 m+1 月下旬公布）從 m+2 月第一個交易日才開始使用；開放資料為修訂後數值，可能與當年公布值略有差異。
- 規則 A（依燈號）：藍 100%、黃藍 100%、綠 80%、黃紅 60%、紅 40%。
- 規則 B（連續燈號）：平時 70%；連續 2 個月藍燈 → 100%；連續 2 個月紅燈 → 40%；其他維持上一期。
- 持股比例在每月第一個交易日調整，調整量 × 單邊成本（同 allocation_study.COST）；空手報酬 0。
- 對照：0050 長期持有（100%）；固定持股（比例 = 該規則全期平均持股）——區分「擇時」與「平均持股較低」的效果。
- 期間：2004-01 ~ 2026-04，另分 2004–2015 / 2016 ~ 2026/04 兩段。
- 補充：各燈號之後 12 個月的 0050 報酬（描述用）；把同樣規則套在月營收驚奇做多組合（市值前 500 檔，2019-03 ~ 2026-04，只作參考）。
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
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402

CSV = ROOT / "data_cache" / "ndc" / "extracted" / "景氣指標與燈號.csv"
MAP_A = {"藍": 1.0, "黃藍": 1.0, "綠": 0.8, "黃紅": 0.6, "紅": 0.4}
LAG_MONTHS = 2


def load_lights() -> pd.DataFrame:
    d = pd.read_csv(CSV, encoding="utf-8-sig", dtype={"Date": str})
    d["light"] = d["景氣對策信號"].astype(str).str.strip()
    d = d[d["light"].isin(MAP_A)].copy()
    d["month"] = pd.to_datetime(d["Date"], format="%Y%m")
    d["score"] = pd.to_numeric(d["景氣對策信號綜合分數"], errors="coerce")
    return d.set_index("month")[["light", "score"]]


def exposure_rule_b(lights: pd.Series) -> pd.Series:
    out, pos = [], 0.7
    prev = None
    for lt in lights:
        if lt == "藍" and prev == "藍":
            pos = 1.0
        elif lt == "紅" and prev == "紅":
            pos = 0.4
        out.append(pos)
        prev = lt
    return pd.Series(out, index=lights.index)


def daily_exposure(monthly: pd.Series, days: pd.DatetimeIndex) -> pd.Series:
    """第 m 月的值從 m+LAG 月第一個交易日起適用。"""
    eff = monthly.copy()
    eff.index = eff.index + pd.DateOffset(months=LAG_MONTHS)
    by_month = pd.Series(eff.to_numpy(), index=eff.index.to_period("M"))
    return pd.Series(days.to_period("M").map(by_month), index=days).astype(float)


def run(exposure: pd.Series, r: pd.Series) -> pd.Series:
    e = exposure.reindex(r.index)
    turn = e.diff().abs().fillna(0.0)
    return e * r - turn * al.COST


def summary(x: pd.Series) -> dict:
    x = x.dropna()
    eq = (1 + x).cumprod()
    return {"sharpe": float(x.mean() / x.std() * math.sqrt(252)), "ann": float(eq.iloc[-1] ** (252 / len(x)) - 1),
            "vol": float(x.std() * math.sqrt(252)), "mdd": float((eq / eq.cummax() - 1).min())}


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    lights = load_lights()
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2003-06-30", "2026-05-31").set_index("date")["adj_close"].astype(float)
    r = px.pct_change()
    r = r[(r.index >= "2004-01-01") & (r.index <= "2026-04-30")]
    exp_a = daily_exposure(lights["light"].map(MAP_A), r.index)
    exp_b = daily_exposure(exposure_rule_b(lights["light"]), r.index)
    S = {"0050 長期持有": r, "規則 A：依燈號": run(exp_a, r), "規則 B：連續燈號": run(exp_b, r)}
    avg = {"規則 A：依燈號": float(exp_a.mean()), "規則 B：連續燈號": float(exp_b.mean())}
    for k, a in avg.items():
        S[f"固定持股 {a:.0%}（同{k[:4]}平均）"] = run(pd.Series(a, index=r.index), r)
    P = pd.DataFrame(S)
    P.to_csv(ROOT / "reports" / "business_cycle_timing.csv")

    segs = [("2004–2015", P.index < "2016-01-01"), ("2016 ~ 2026/04", P.index >= "2016-01-01"), ("全期 2004 ~ 2026/04", P.index == P.index)]
    lines = ["# 景氣對策信號逆向擇時 vs 0050 長期持有（自動產生）", "",
             "由 [analysis/business_cycle_timing.py](../analysis/business_cycle_timing.py) 產生；設計見程式開頭。資料：國發會「景氣指標及燈號」開放資料（data.gov.tw/dataset/6099，修訂後數值）。"
             f"第 m 月燈號從 m+{LAG_MONTHS} 月起使用。Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0，空手報酬 0），已扣調整成本。研究結果，非投資建議。", ""]
    for seg, m in segs:
        lines += [f"## {seg}", "", "| 策略 | 平均持股 | Sharpe | 年化報酬 | 年化波動 | 最大回撤 |", "|---|---|---|---|---|---|"]
        for k in P.columns:
            s = summary(P.loc[m, k])
            e = 1.0 if k.startswith("0050") else (exp_a if "A" in k and k.startswith("規則") else exp_b if k.startswith("規則") else
                                                  pd.Series(float(k.split("固定持股 ")[1].split("%")[0]) / 100, index=r.index))
            lines.append(f"| {k} | {float(np.mean(e[m])) if hasattr(e, '__len__') else e:.0%} | {s['sharpe']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} |")
        lines.append("")
    for k, a in avg.items():
        fixed = P[f"固定持股 {a:.0%}（同{k[:4]}平均）"]
        d = (P[k] - fixed).dropna()
        lines.append(f"- {k} 相對同平均持股的固定比例：年化 {d.mean() * 252:+.2%}（t {d.mean() / (d.std() / math.sqrt(len(d))):+.2f}）")

    # 各燈號之後 12 個月 0050 報酬（以可用月份計）
    m_px = px.resample("ME").last()
    fwd12 = m_px.shift(-12) / m_px - 1
    lt_eff = lights["light"].copy()
    lt_eff.index = (lt_eff.index + pd.DateOffset(months=LAG_MONTHS) - pd.DateOffset(days=1)).to_period("M").to_timestamp("M")
    df = pd.DataFrame({"light": lt_eff, "fwd12": fwd12.reindex(lt_eff.index)}).dropna()
    df = df[(df.index >= "2004-01-01")]
    lines += ["", "## 各燈號可用後的 0050 未來 12 個月報酬（描述用，月資料重疊）", "", "| 燈號 | 月數 | 平均 | 中位數 | 為正比例 |", "|---|---|---|---|---|"]
    for lt in ("藍", "黃藍", "綠", "黃紅", "紅"):
        x = df.loc[df["light"] == lt, "fwd12"]
        if len(x):
            lines.append(f"| {lt} | {len(x)} | {x.mean():+.1%} | {x.median():+.1%} | {(x > 0).mean():.0%} |")

    # 套用在月營收驚奇做多（前 500 檔）
    bl = ROOT / "reports" / "legs" / "blend_longonly_top500.csv"
    if bl.exists():
        L = pd.read_csv(bl, index_col=0, parse_dates=True)["做多：每月"].dropna()
        ea, eb = daily_exposure(lights["light"].map(MAP_A), L.index), daily_exposure(exposure_rule_b(lights["light"]), L.index)
        T = {"月營收驚奇做多（100%）": L, "× 規則 A": run(ea, L), "× 規則 B": run(eb, L),
             f"固定 {ea.mean():.0%}": run(pd.Series(ea.mean(), index=L.index), L), f"固定 {eb.mean():.0%}": run(pd.Series(eb.mean(), index=L.index), L)}
        lines += ["", "## 補充：套用在月營收驚奇做多（市值前 500 檔，2019-03 ~ 2026-04，只作參考）", "",
                  "| 策略 | Sharpe | 年化報酬 | 最大回撤 |", "|---|---|---|---|"]
        for k, x in T.items():
            s = summary(x)
            lines.append(f"| {k} | {s['sharpe']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} |")
    (ROOT / "docs" / "business_cycle_timing.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
