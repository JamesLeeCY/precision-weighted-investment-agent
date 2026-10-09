"""樣本內 / 樣本外績效：哪些期間對財報 Agent 的規則算樣本外、各段 Sharpe、前瞻期、Deflated Sharpe。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/oos_report.py daily_pit.csv config/tickers_pit.yaml   # 輸出 docs/oos_report.md

樣本切分依「規則是用哪段資料訂的」：財報 Agent 的 5 個特徵、縮放係數與財報公告遞延在 2026-07-03 的 MVP
（5 檔被動元件、2023-01 ~ 2026-05 資料）訂定後從未改過，因此
- 2019-01 ~ 2022-12：規則樣本外（時間上 MVP 沒看過；股票池 271 檔中 266 檔不在 MVP 的 5 檔內）
- 2023-01 ~ 2026-05：與 MVP 開發期重疊（樣本內）
- 2026-06 ~：前瞻驗證（規格 fv1 凍結後才產生的預測，最乾淨的樣本外）
注意：「門檻 → 連續輸出」「只放財報 Agent」「產業中性」是看過 2019–2026 全期結果後才做的決定，
所以只有「MVP 原規則（門檻模式、看多就持有）」在 2019–2022 是乾淨的樣本外。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from statistics import NormalDist

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import sector_neutral_portfolio as snp  # noqa: E402
from backtest.portfolio import max_drawdown  # noqa: E402
from data.fetch_financials import FinMindClient, get_total_return_prices  # noqa: E402

PPY = 252 / 21
_N = NormalDist()
SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022（規則樣本外）", lambda d: d < SPLIT), ("2023–2026/05（開發期重疊）", lambda d: d >= SPLIT)]


def stats(r: np.ndarray) -> dict:
    r = np.asarray(r, dtype=float)
    total = float(np.prod(1 + r) - 1)
    ann = (1 + total) ** (PPY / len(r)) - 1 if total > -1 else -1.0
    vol = r.std(ddof=1) * math.sqrt(PPY)
    return {"ann": ann, "sharpe": ann / vol if vol else float("nan"), "mdd": max_drawdown(r)}


def info_ratio(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    return float(x.mean() / x.std(ddof=1) * math.sqrt(PPY)) if x.std(ddof=1) else float("nan")


def bench_20d(df: pd.DataFrame) -> pd.Series:
    """每個預測日起 20 個交易日的 0050 含息報酬，結束日用與回測相同的共用市場日曆
    （每日輸出的 i 就是共用日曆的位置；最後 20 天之後的日期改用 0050 自己的交易日）。"""
    px = get_total_return_prices(FinMindClient(), "0050.TW", "2019-01-01", "2026-05-31")
    adj = pd.Series(px["adj_close"].astype(float).to_numpy(), index=pd.DatetimeIndex(px["date"]))
    cal = df.groupby("i")["date"].first()
    out = {}
    for i, d0 in cal.items():
        if i + 20 in cal.index:
            d1 = cal[i + 20]
        else:
            pos = adj.index.searchsorted(d0)
            if pos + 20 >= len(adj):
                continue
            d1 = adj.index[pos + 20]
        out[d0] = adj.asof(d1) / adj.asof(d0) - 1
    return pd.Series(out)


def deflated_sharpe(x: np.ndarray, n_trials: int) -> tuple[float, float]:
    """Bailey & López de Prado (2014)：在 n_trials 次嘗試下，觀察到的每期 Sharpe 高於「最佳雜訊」的機率。

    回傳 (每期 Sharpe, DSR)。虛無假設下每次嘗試的 Sharpe 估計變異以 1/T 近似。
    """
    x = np.asarray(x, dtype=float)
    t = len(x)
    sr = x.mean() / x.std(ddof=1)
    skew = float(pd.Series(x).skew())
    kurt = float(pd.Series(x).kurt()) + 3
    gamma = 0.5772156649
    sr0 = math.sqrt(1 / t) * ((1 - gamma) * _N.inv_cdf(1 - 1 / n_trials) + gamma * _N.inv_cdf(1 - 1 / (n_trials * math.e)))
    z = (sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return sr, float(_N.cdf(z))


def segment_table(phases: list[pd.DataFrame], cols: dict[str, str]) -> list[str]:
    lines = ["| 策略 | " + " | ".join(f"{name} 年化 / Sharpe / 最大回撤" for name, _ in SEGMENTS)
             + " | 相對等權 IR：樣本外 / 樣本內 |", "|---|" + "---|" * (len(SEGMENTS) + 1)]
    for label, col in cols.items():
        cells = []
        for _, fn in SEGMENTS:
            st = [stats(p[fn(p["d"])][col].to_numpy()) for p in phases]
            cells.append(f"{np.median([x['ann'] for x in st]) * 100:+.1f}% / {np.median([x['sharpe'] for x in st]):.2f} / "
                         f"{np.median([x['mdd'] for x in st]) * 100:.0f}%")
        if col in ("ew_net", "bench"):
            ir = "—"
        else:
            parts = []
            for _, fn in SEGMENTS:
                irs = [info_ratio((p[fn(p["d"])][col] - p[fn(p["d"])]["ew_net"]).to_numpy()) for p in phases]
                parts.append(f"{np.median(irs):+.2f}（{sum(i > 0 for i in irs)}/21）")
            ir = " / ".join(parts)
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {ir} |")
    return lines


def forward_section() -> list[str]:
    import forward.run_forward as fw

    pre = pd.read_csv(fw.PREDICTIONS, dtype={"ticker": str})
    oc = pd.read_csv(fw.OUTCOMES, dtype={"ticker": str})
    df = pre.merge(oc, on=["as_of_date", "ticker"]).rename(columns={"forward_return": "ret"})
    rows = []
    for d, g in df.groupby("as_of_date"):
        g = g.reset_index(drop=True)
        w_sn = snp.sector_neutral_weights(g, "p", 1 / 3, 3, +1)
        held = g[g["p"] > 0.5]
        l, s = snp.long_short_weights(g, "p", 1 / 3, 3)
        ew = g["ret"].mean()
        rows.append({"d": d, "ew": ew, "sn": snp.portfolio_return(g, w_sn) - ew,
                     "p50": held["ret"].mean() - ew if len(held) else -ew,
                     "ls": snp.portfolio_return(g, l) - snp.portfolio_return(g, s)})
    f = pd.DataFrame(rows)
    lines = ["| 預測日 | 股票池等權報酬 | 產業中性做多 − 等權 | p > 0.5 持有 − 等權 | 產業內多空 |", "|---|---|---|---|---|"]
    for r in f.itertuples():
        lines.append(f"| {r.d} | {r.ew * 100:+.1f}% | {r.sn * 100:+.2f}% | {r.p50 * 100:+.2f}% | {r.ls * 100:+.2f}% |")
    lines.append(f"| **平均（{len(f)} 期）** | {f.ew.mean() * 100:+.1f}% | {f.sn.mean() * 100:+.2f}% | "
                 f"{f.p50.mean() * 100:+.2f}% | {f.ls.mean() * 100:+.2f}% |")
    return lines


def main(daily_csv, config):
    df = pd.read_csv(daily_csv, parse_dates=["date"])
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    df["sector"] = df["ticker"].map({u["ticker"]: u["segment"] for u in cfg["universe"]})
    df = df.dropna(subset=["sector", "ret"])
    bench = bench_20d(df)

    out = ["# 樣本內 / 樣本外績效與過度擬合控制（自動產生）", "",
           "由 [analysis/oos_report.py](../analysis/oos_report.py) 產生。說明與面試用的回答見 "
           "[overfitting_controls.md](overfitting_controls.md)。", "",
           "數字為 21 種取樣起點（每 21 個交易日換倉、持有 20 個交易日）各自計算後的**中位數**，含息總報酬、扣交易成本；"
           "Sharpe = 年化報酬 ÷ 年化波動（無風險利率 0）；IR = 相對等權持有的每期超額報酬年化後除以追蹤誤差。", ""]
    variants = [
        ("p_fundamentals_agent", "MVP 原規則（門檻模式）", {"看多就持有（MVP 原規則）": "p50_net"}),
        ("pc_fundamentals_agent", "連續輸出（事後決定）",
         {"看多機率 > 0.5 就持有": "p50_net", "產業中性做多 前 1/3": "sn_net", "等權持有全部": "ew_net", "0050": "bench"}),
    ]
    for signal, title, cols in variants:
        phases = []
        for ph in range(snp.STEP):
            p = snp.phase_series(df, signal, 1 / 3, 3, ph)
            p["d"] = pd.to_datetime(p["date"]).dt.strftime("%Y-%m-%d")
            p["bench"] = pd.to_datetime(p["date"]).map(bench)
            phases.append(p.dropna(subset=["bench"]))
        out += [f"## 財報 Agent：{title}", ""] + segment_table(phases, cols) + [""]
        if signal == "pc_fundamentals_agent":
            sn_ex = [p[p["d"] < SPLIT]["sn_net"] - p[p["d"] < SPLIT]["ew_net"] for p in phases]
            dsr = {n: np.median([deflated_sharpe(x.to_numpy(), n)[1] for x in sn_ex]) for n in (5, 20, 50)}
            full = [deflated_sharpe((p["sn_net"] - p["ew_net"]).to_numpy(), n)[1] for p in phases for n in (20,)]
            out += ["### Deflated Sharpe（產業中性做多相對等權的超額報酬）", "",
                    "在嘗試過 N 種設定的前提下，觀察到的超額 Sharpe 高於「N 次嘗試中最好的純雜訊」的機率"
                    "（Bailey & López de Prado 2014；21 起點中位數）：", "",
                    f"- 2019–2022：N = 5 → {dsr[5]:.2f}；N = 20 → {dsr[20]:.2f}；N = 50 → {dsr[50]:.2f}",
                    f"- 全期 2019–2026：N = 20 → {np.median(full):.2f}",
                    "", "一般以 > 0.95 視為顯著。", ""]
    out += ["## 前瞻驗證（規格凍結後才產生的預測，2026-06 ~ 09 回填 4 期）", "",
            "財報 Agent 連續輸出，未扣成本；只有 4 期，不足以計算有意義的 Sharpe，列出逐期結果。", ""] + forward_section() + [""]
    path = ROOT / "docs" / "oos_report.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
