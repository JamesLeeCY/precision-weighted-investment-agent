"""短期反轉、過度反應、產業內領先落後：5 日預測期、每 5 個交易日換倉。

用法（於專案根目錄；輸入為 technical_timing.py 產生的 daily_pit_val_tech.csv，用其中的成員、產業與日期）：
    .venv/Scripts/python analysis/short_term_reversal.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/short_term_reversal_data.md。

設計（看結果前固定）：
- 報酬：預測日 d 收盤進場、第 5 個交易日收盤出場（含息還原價）。
- 時序（主要）：訊號只用 d 前一個交易日以前的資料（隔一天才成交，保守）；
  上限版本：訊號用到 d 當天收盤、並以同一收盤價成交（實務上難以完全做到）。
- 短期反轉（Jegadeesh 1990、Lehmann 1990）：rev_1d / rev_5d / rev_10d = 過去 1 / 5 / 10 日報酬的負值。
  另做「減產業平均」版本：產業內排序不受影響，只在跨產業（全體）IC 有差別。
- 過度反應（Cooper 1999 等：無量的價格變動較會回補）：依 5 日均量 / 60 日均量分成低量、高量兩半（當日全體中位數），
  分別計算 rev_5d 的產業內 IC；組合只在低量那半裡做反轉。
- 產業內領先落後（Hou 2007）：每個產業依市值取前 1/3 為領先股，領先股過去 5 日平均報酬 = 該產業的領先訊號；
  檢驗領先訊號能否預測同產業追隨股（其餘 2/3）接下來 5 日報酬（跨產業比較；只有 7 個產業，檢定力弱）。
  在產業內，所有追隨股面對同一個領先訊號，排序只剩自身報酬的負值，等同反轉。
- 組合：產業中性做多（產業內前 1/3）、產業內多空；成本 = 換手量 × 單邊 0.29625%（賣出含 0.3% 證交稅，兩邊均攤）。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import sector_neutral_portfolio as snp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.fetch_technical import FinMindTechnicalProvider  # noqa: E402

H = 5                 # 預測期與換倉間隔（交易日）
PPY = 252 / H
COST = snp.COST_PER_SIDE
SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]


def price_features(tickers) -> pd.DataFrame:
    prov = FinMindTechnicalProvider(FinMindClient(), "2019-01-01", "2026-05-31")
    parts = []
    for t in tickers:
        ind = prov.indicators(t)
        if ind.empty:
            continue
        c, v = ind["close"], ind["volume"]
        parts.append(pd.DataFrame({
            "date": ind["date"], "ticker": t,
            "r1": c / c.shift(1) - 1, "r5": c / c.shift(5) - 1, "r10": c / c.shift(10) - 1,
            "vol_shock": v.rolling(5, min_periods=5).mean() / v.rolling(60, min_periods=60).mean() - 1,
            "fwd5": c.shift(-H) / c - 1,
        }))
    return pd.concat(parts, ignore_index=True)


def attach(df: pd.DataFrame, feats: pd.DataFrame, skip: bool) -> pd.DataFrame:
    """skip=True：訊號用 d 之前最後一列；False：用 d 當天。報酬一律為 d 收盤起 5 日。"""
    left = df.sort_values("date")
    past = feats[["date", "ticker", "r1", "r5", "r10", "vol_shock"]].sort_values("date")
    out = pd.merge_asof(left, past, on="date", by="ticker", allow_exact_matches=not skip)
    out = out.merge(feats[["date", "ticker", "fwd5"]], on=["date", "ticker"], how="left")
    for n in (1, 5, 10):
        out[f"rev_{n}d"] = -out[f"r{n}"]
        out[f"rev_{n}d_dm"] = -(out[f"r{n}"] - out.groupby("date")[f"r{n}"].transform("mean"))
        out[f"rev_{n}d_ind"] = -(out[f"r{n}"] - out.groupby(["date", "sector"])[f"r{n}"].transform("mean"))
    return out.dropna(subset=["fwd5"]).sort_values(["i", "ticker"]).reset_index(drop=True)


def spearman(a, b):
    return a.rank().corr(b.rank()) if a.nunique() > 1 and b.nunique() > 1 else np.nan


def ic_series(df, col, within=True, mask=None):
    rows = {}
    for i, g in df.groupby("i"):
        if mask is not None:
            g = g[mask.loc[g.index]]
        g = g.dropna(subset=[col])
        if within:
            vals, w = [], []
            for _, s in g.groupby("sector"):
                if len(s) >= 3:
                    v = spearman(s[col], s["fwd5"])
                    if not np.isnan(v):
                        vals.append(v)
                        w.append(len(s))
            rows[i] = np.average(vals, weights=w) if vals else np.nan
        else:
            rows[i] = spearman(g[col], g["fwd5"]) if len(g) >= 10 else np.nan
    return pd.Series(rows)


def summarize_ic(ic, dates):
    cells = []
    for _, fn in SEGMENTS:
        sub = ic[[fn(dates[i]) for i in ic.index]].dropna()
        nonover = [sub[sub.index % H == ph] for ph in range(H)]
        ts = [x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) for x in nonover if len(x) > 2]
        cells.append(f"{sub.mean():+.3f}（t {np.median(ts):+.1f}）")
    return cells


def portfolios(df, col, phase, low_vol_only=False):
    rows, prev = [], {k: {} for k in ("sn", "ew", "l", "s")}
    for i in sorted(df["i"].unique()):
        if i % H != phase:
            continue
        g = df[df["i"] == i].dropna(subset=[col]).rename(columns={"fwd5": "ret_"})
        g = g.assign(ret=g["ret_"])
        if low_vol_only:
            g = g[g["vol_shock"] <= g["vol_shock"].median()]
        if len(g) < 10:
            continue
        w = {"sn": snp.sector_neutral_weights(g, col, 1 / 3, 3, +1), "ew": {t: 1 / len(g) for t in g["ticker"]}}
        w["l"], w["s"] = snp.long_short_weights(g, col, 1 / 3, 3)
        r = {k: snp.portfolio_return(g, w[k]) for k in w}
        to = {k: snp.turnover(w[k], prev[k]) for k in w}
        rows.append({
            "d": g["date"].iloc[0].strftime("%Y-%m-%d"),
            "sn_ex_gross": r["sn"] - r["ew"], "sn_ex_net": (r["sn"] - to["sn"] * COST) - (r["ew"] - to["ew"] * COST),
            "ls_gross": r["l"] - r["s"], "ls_net": r["l"] - r["s"] - (to["l"] + to["s"]) * COST,
            "sn_to": to["sn"], "ls_to": to["l"] + to["s"],
        })
        prev = w
    return pd.DataFrame(rows)


def port_summary(df, col, low_vol_only=False):
    ph = [portfolios(df, col, p, low_vol_only) for p in range(H)]
    out = {}
    for name, fn in SEGMENTS:
        seg = [p[p["d"].map(fn)] for p in ph]
        for m in ("sn_ex_gross", "sn_ex_net", "ls_gross", "ls_net"):
            means = [s[m].mean() for s in seg]
            ann_ir = [s[m].mean() / s[m].std(ddof=1) * math.sqrt(PPY) for s in seg]
            out[(name, m)] = (np.median(means), np.median(ann_ir), sum(x > 0 for x in means))
    out["to"] = (np.median([p["sn_to"].mean() for p in ph]), np.median([p["ls_to"].mean() for p in ph]))
    return out


def lead_lag(df):
    """產業領先股過去 5 日報酬 → 同產業追隨股接下來 5 日報酬（跨產業 IC，只用追隨股）。"""
    d = df.copy()
    d["cap_rank"] = d.groupby(["date", "sector"])["cap"].rank(pct=True)
    d["leader"] = d["cap_rank"] > 2 / 3
    lead = d[d["leader"]].groupby(["date", "sector"])["r5"].mean().rename("leader_r5")
    d = d.join(lead, on=["date", "sector"])
    f = d[~d["leader"]].dropna(subset=["leader_r5", "r5"]).copy()
    f["ll_gap"] = f["leader_r5"] - f["r5"]
    return f


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    base = pd.read_csv(path, parse_dates=["date"], usecols=["i", "date", "ticker", "sector"])
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    feats = price_features(tickers)
    sys.path.insert(0, str(ROOT / "analysis"))
    from valuation_signal import load_panel

    cap = load_panel(tickers)[["date", "ticker", "cap"]]
    out = ["# 短期反轉、過度反應、產業內領先落後（自動產生）", "",
           "由 [analysis/short_term_reversal.py](../analysis/short_term_reversal.py) 產生；解讀見 "
           "[short_term_reversal_report.md](short_term_reversal_report.md)。5 日預測期、每 5 個交易日換倉，"
           "5 種取樣起點；IC 為每日平均（括號內為 5 個不重疊起點的 t 值中位數）；組合為 5 起點中位數。", ""]
    for skip, title in ((True, "主要：訊號用前一日以前資料（隔日成交）"), (False, "上限：訊號與成交用同一收盤價")):
        df = attach(base, feats, skip).merge(cap, on=["date", "ticker"], how="left")
        dates = df.groupby("i")["date"].first().dt.strftime("%Y-%m-%d")
        out += [f"## {title}", "", "### 產業內 IC 與全體 IC", "",
                "| 訊號 | 產業內 IC 2019–2022 | 產業內 IC 2023–2026 | 全體 IC 2019–2022 | 全體 IC 2023–2026 |", "|---|---|---|---|---|"]
        for col, label in (("rev_1d", "反轉 1 日"), ("rev_5d", "反轉 5 日"), ("rev_10d", "反轉 10 日"),
                           ("rev_5d_dm", "反轉 5 日（減全體平均）"), ("rev_5d_ind", "反轉 5 日（減產業平均）")):
            w = summarize_ic(ic_series(df, col, True), dates)
            a = summarize_ic(ic_series(df, col, False), dates)
            out.append(f"| {label} | {w[0]} | {w[1]} | {a[0]} | {a[1]} |")
            print(out[-1], flush=True)
        low = df["vol_shock"] <= df.groupby("i")["vol_shock"].transform("median")
        lo = summarize_ic(ic_series(df, "rev_5d", True, low), dates)
        hi = summarize_ic(ic_series(df, "rev_5d", True, ~low & df["vol_shock"].notna()), dates)
        out += ["", "### 過度反應：依量能分組的反轉 5 日（產業內 IC）", "",
                "| 分組 | 2019–2022 | 2023–2026 |", "|---|---|---|",
                f"| 低量（5 日均量 / 60 日均量 ≤ 當日中位數） | {lo[0]} | {lo[1]} |",
                f"| 高量 | {hi[0]} | {hi[1]} |"]
        print(out[-2:], flush=True)
        f = lead_lag(df)
        fdates = f.groupby("i")["date"].first().dt.strftime("%Y-%m-%d")
        out += ["", "### 產業內領先落後（只用追隨股，跨產業 IC）", "",
                "| 訊號 | 2019–2022 | 2023–2026 |", "|---|---|---|"]
        for col, label in (("leader_r5", "領先股過去 5 日報酬"), ("ll_gap", "領先股 − 自身過去 5 日報酬")):
            c = summarize_ic(ic_series(f, col, False), fdates)
            out.append(f"| {label} | {c[0]} | {c[1]} |")
        print(out[-2:], flush=True)
        out += ["", "### 組合（每期 5 日；均值／年化 IR／為正起點數）", "",
                "| 訊號 | 期間 | 產業中性做多 − 等權（未扣成本） | 扣成本 | 產業內多空（未扣成本） | 扣成本 |", "|---|---|---|---|---|---|"]
        for col, label, lv in (("rev_1d", "反轉 1 日", False), ("rev_5d", "反轉 5 日", False),
                               ("rev_10d", "反轉 10 日", False), ("rev_5d", "反轉 5 日（只在低量股）", True)):
            s = port_summary(df, col, lv)
            for name, _ in SEGMENTS:
                cells = [f"{s[(name, m)][0] * 100:+.2f}%／{s[(name, m)][1]:+.2f}／{s[(name, m)][2]}/5"
                         for m in ("sn_ex_gross", "sn_ex_net", "ls_gross", "ls_net")]
                out.append(f"| {label} | {name} | " + " | ".join(cells) + " |")
            out.append(f"| {label} | 每期換手 | 做多 {s['to'][0]:.2f} | | 多空 {s['to'][1]:.2f} | |")
            print(out[-3:], flush=True)
        out.append("")
    (ROOT / "docs" / "short_term_reversal_data.md").write_text("\n".join(out), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
