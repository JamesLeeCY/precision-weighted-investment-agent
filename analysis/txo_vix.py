"""用台指選擇權（TXO）每日結算價自行計算台指 VIX（依期交所／Cboe VIX 公式的近似）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/txo_vix.py
輸出 reports/txo_vix.csv（date, vix, vix_near, vix_next, n_strikes）。

期交所官方 VIX 只免費提供近 3 個月，完整歷史需付費申請，因此自行計算。與官方的差異：
- 用每日結算價，不是報價的買賣中價；無風險利率以 0 計；到期時間以日曆天計（每年 365 天）。
- 只用月選擇權（不含週選擇權）；近月距到期剩 2 個交易日（含）以下時，改用次近月與第 2 個次近月。
公式（Cboe VIX）：σ² = (2/T) Σ ΔK/K² · Q(K) − (1/T)(F/K₀ − 1)²；F 由價平附近買賣權價差推得；
價外選擇權：K₀ 以下用賣權、以上用買權、K₀ 取兩者平均；遇連續兩個結算價為 0 即停止；兩個到期月內插到 30 天。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_financials import FinMindClient  # noqa: E402

START, END = "2007-01-01", "2026-10-14"


def third_wednesday(ym: str) -> pd.Timestamp:
    d = pd.Timestamp(f"{ym[:4]}-{ym[4:6]}-01")
    first_wed = d + pd.Timedelta(days=(2 - d.weekday()) % 7)
    return first_wed + pd.Timedelta(days=14)


def load_txo(client) -> pd.DataFrame:
    out = []
    for m in pd.period_range(START, END, freq="M"):
        s = max(pd.Timestamp(START), m.start_time).strftime("%Y-%m-%d")
        e = min(pd.Timestamp(END), m.end_time).strftime("%Y-%m-%d")
        d = client.get("TaiwanOptionDaily", "TXO", s, e)
        if not d.empty:
            d = d[(d["trading_session"] == "position") & d["contract_date"].astype(str).str.fullmatch(r"\d{6}")]
            out.append(d[["date", "contract_date", "strike_price", "call_put", "settlement_price"]])
        if m.month == 12:
            print(f"  {m.year} 完成", flush=True)
    d = pd.concat(out)
    d["date"] = pd.to_datetime(d["date"])
    d["strike_price"] = d["strike_price"].astype(float)
    d["settlement_price"] = d["settlement_price"].astype(float)
    return d


def term_variance(g: pd.DataFrame, T: float) -> tuple[float, int]:
    """單一到期月的變異數（Cboe 公式，r = 0）。g：該日該月所有履約價的 call / put 結算價。"""
    p = g.pivot_table(index="strike_price", columns="call_put", values="settlement_price", aggfunc="last").sort_index()
    if not {"call", "put"} <= set(p.columns):
        return np.nan, 0
    both = p.dropna(subset=["call", "put"])
    both = both[(both["call"] > 0) & (both["put"] > 0)]
    if both.empty:
        return np.nan, 0
    k_atm = (both["call"] - both["put"]).abs().idxmin()
    F = k_atm + both.loc[k_atm, "call"] - both.loc[k_atm, "put"]
    below = p.index[p.index <= F]
    if len(below) == 0:
        return np.nan, 0
    k0 = below.max()
    q = {}
    zeros = 0
    for k in sorted(p.index[p.index < k0], reverse=True):        # 價外賣權，往下
        v = p.loc[k, "put"]
        if not (v > 0):
            zeros += 1
            if zeros >= 2:
                break
            continue
        zeros = 0
        q[k] = v
    zeros = 0
    for k in sorted(p.index[p.index > k0]):                       # 價外買權，往上
        v = p.loc[k, "call"]
        if not (v > 0):
            zeros += 1
            if zeros >= 2:
                break
            continue
        zeros = 0
        q[k] = v
    c0, p0 = p.loc[k0].get("call", np.nan), p.loc[k0].get("put", np.nan)
    q[k0] = np.nanmean([c0, p0])
    ks = np.array(sorted(q))
    if len(ks) < 3:
        return np.nan, len(ks)
    qv = np.array([q[k] for k in ks])
    dk = np.empty_like(ks)
    dk[1:-1] = (ks[2:] - ks[:-2]) / 2
    dk[0], dk[-1] = ks[1] - ks[0], ks[-1] - ks[-2]
    var = 2 / T * np.sum(dk / ks ** 2 * qv) - (F / k0 - 1) ** 2 / T
    return float(var), len(ks)


def compute(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dt, g in d.groupby("date"):
        exps = sorted(g["contract_date"].unique(), key=third_wednesday)
        exps = [e for e in exps if third_wednesday(e) >= dt]
        # 近月距到期剩 ≤ 2 個交易日（之後到到期日，含到期日，以週一至週五計）：改用次近月與第 2 個次近月
        # （用日曆計算，不依賴資料中已有的日期，否則序列最後幾天會誤判換月）
        if exps:
            ex0 = third_wednesday(exps[0])
            remaining = int(np.busday_count((dt + pd.Timedelta(days=1)).date(), (ex0 + pd.Timedelta(days=1)).date()))
            if remaining <= 2:
                exps = exps[1:]
        if len(exps) < 2:
            continue
        e1, e2 = exps[0], exps[1]
        t1 = (third_wednesday(e1) - dt).days / 365
        t2 = (third_wednesday(e2) - dt).days / 365
        v1, n1 = term_variance(g[g["contract_date"] == e1], t1)
        v2, n2 = term_variance(g[g["contract_date"] == e2], t2)
        if not (v1 == v1 and v2 == v2) or t2 <= t1:
            continue
        n30 = 30 / 365
        w1 = (t2 - n30) / (t2 - t1)
        var30 = (t1 * v1 * w1 + t2 * v2 * (1 - w1)) / n30
        rows.append({"date": dt, "vix": 100 * np.sqrt(max(var30, 0)), "vix_near": 100 * np.sqrt(max(v1, 0)),
                     "vix_next": 100 * np.sqrt(max(v2, 0)), "n_strikes": n1 + n2})
    return pd.DataFrame(rows).set_index("date")


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    d = load_txo(FinMindClient())
    v = compute(d)
    v.to_csv(ROOT / "reports" / "txo_vix.csv")
    print(v.describe().round(2).to_string())
    print(v.tail(10).round(2).to_string())
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
