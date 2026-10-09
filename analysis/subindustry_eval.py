"""子產業分類的效果：財報 Agent、產業內相對估值、產業內領先落後，比較「大產業」與「子產業」分組。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/subindustry_eval.py daily_pit_val_tech.csv config/tickers_pit.yaml
輸出 docs/subindustry_data.md。

分組（看結果前固定）：子產業（config/subindustry_pit.csv）在當日有 ≥ 5 檔成員時單獨成組，不足 5 檔併回大產業。
評估：
- 財報 Agent（20 日）：組內 IC、組內中性做多（前 1/3，產業權重 = 股票池權重）與加緩衝版本，21 起點。
- 產業內相對估值（20 日）：原式在「組 × 市值五分位」中性化（valuation_signal.compute_valuation）。
- 領先落後（5 日）：組內市值前 1/3 為領先股，領先股過去 5 日報酬 → 追隨股接下來 5 日報酬（跨組 IC）。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import sector_neutral_portfolio as snp  # noqa: E402
import short_term_reversal as st  # noqa: E402
from valuation_signal import compute_valuation, load_panel  # noqa: E402

SPLIT = "2023-01-01"
SEGMENTS = [("2019–2022", lambda d: d < SPLIT), ("2023–2026/05", lambda d: d >= SPLIT)]
MIN_SUB = 5


def add_groups(df: pd.DataFrame, sub: dict) -> pd.DataFrame:
    df = df.copy()
    df["sub"] = df["ticker"].str.split(".").str[0].map(sub).fillna("")
    n = df.groupby(["date", "sub"])["ticker"].transform("count")
    df["subgroup"] = np.where((df["sub"] != "") & ~df["sub"].str.startswith("未分類") & (n >= MIN_SUB), df["sub"], df["sector"])
    return df


def within_ic(df, col, group, ret="ret"):
    def one(g):
        vals, w = [], []
        for _, s in g.groupby(group):
            s = s.dropna(subset=[col, ret])
            if len(s) >= 3 and s[col].nunique() > 1:
                vals.append(s[col].rank().corr(s[ret].rank()))
                w.append(len(s))
        return np.average(vals, weights=w) if vals else np.nan
    return df.groupby("i").apply(one)


def ic_cells(ic, dates, step):
    cells = []
    for _, fn in SEGMENTS:
        sub = ic[[fn(dates[i]) for i in ic.index]].dropna()
        by = sub.groupby(sub.index % step).mean()
        cells.append(f"{by.median():+.3f}（{(by > 0).sum()}/{step}）")
    return cells


def sn_cells(df, col, group, keep=None):
    d = df.dropna(subset=[col]).copy()
    d["sector"] = d[group]  # sector_neutral_portfolio 以 sector 欄分組
    phases = [snp.phase_series(d, col, 1 / 3, 3, ph, keep) for ph in range(snp.STEP)]
    cells = []
    for _, fn in SEGMENTS:
        m = [p[pd.to_datetime(p["date"]).dt.strftime("%Y-%m-%d").map(fn)]["sn_excess_net"].mean() for p in phases]
        cells.append(f"{np.median(m) * 100:+.2f}%（{sum(x > 0 for x in m)}/21）")
    return cells, np.median([p["sn_to"].mean() for p in phases])


def main(path, config):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    tickers = [u["ticker"] for u in cfg["universe"]]
    subtab = pd.read_csv(ROOT / "config" / "subindustry_pit.csv", dtype={"stock_id": str})
    sub = dict(zip(subtab["stock_id"], subtab["subindustry"]))
    df = pd.read_csv(path, parse_dates=["date"], usecols=["i", "date", "ticker", "ret", "sector", "pc_fundamentals_agent", "val_signal"])
    df = add_groups(df.dropna(subset=["sector", "ret"]), sub)
    dates = df.groupby("i")["date"].first().dt.strftime("%Y-%m-%d")
    per_day = df.groupby("i").agg(n_groups=("subgroup", "nunique"), n_sector=("sector", "nunique"))
    own = (df["subgroup"] != df["sector"]).mean()

    out = ["# 子產業分類的效果（自動產生）", "",
           "由 [analysis/subindustry_eval.py](../analysis/subindustry_eval.py) 產生；解讀見 [subindustry_report.md](subindustry_report.md)。", "",
           f"- 分組：每日平均 {per_day['n_groups'].mean():.1f} 組（大產業 {per_day['n_sector'].mean():.1f} 組）；"
           f"{own:.0%} 的股票落在獨立成組的子產業（≥ {MIN_SUB} 檔），其餘併回大產業", ""]

    # 估值：子產業 × 市值五分位
    panel = load_panel(tickers)[["date", "ticker", "PER", "PBR", "dividend_yield", "cap"]]
    dv = df.merge(panel, on=["date", "ticker"], how="left")
    dv = compute_valuation(dv, "subgroup").rename(columns={"val_signal": "val_signal_sub"})
    df = df.merge(dv[["i", "ticker", "val_signal_sub"]], on=["i", "ticker"], how="left")

    out += ["## 20 日訊號：組內 IC 與組內中性做多（扣成本，相對等權）", "",
            "| 訊號 | 分組 | 組內 IC 2019–2022 | 2023–2026 | 做多 − 等權 2019–2022 | 2023–2026 | 每期換手 |", "|---|---|---|---|---|---|---|"]
    rows = [("財報 Agent", "pc_fundamentals_agent", "sector", None, "大產業"),
            ("財報 Agent", "pc_fundamentals_agent", "subgroup", None, "子產業"),
            ("財報 Agent + 緩衝", "pc_fundamentals_agent", "sector", 0.5, "大產業"),
            ("財報 Agent + 緩衝", "pc_fundamentals_agent", "subgroup", 0.5, "子產業"),
            ("產業內相對估值", "val_signal", "sector", None, "大產業"),
            ("產業內相對估值", "val_signal_sub", "subgroup", None, "子產業 × 市值五分位")]
    for label, col, group, keep, gname in rows:
        ic = ic_cells(within_ic(df, col, group), dates, snp.STEP)
        sn, to = sn_cells(df, col, group, keep)
        out.append(f"| {label} | {gname} | {ic[0]} | {ic[1]} | {sn[0]} | {sn[1]} | {to:.2f} |")
        print(out[-1], flush=True)

    # 領先落後（5 日）
    feats = st.price_features(tickers)
    base = df[["i", "date", "ticker", "sector", "subgroup"]]
    out += ["", "## 5 日領先落後（只用追隨股，跨組 IC；括號為 5 個不重疊起點的 t 值中位數）", "",
            "| 分組 | 領先股過去 5 日報酬 2019–2022 | 2023–2026 |", "|---|---|---|"]
    for group, gname in (("sector", "大產業"), ("subgroup", "子產業")):
        b = base.drop(columns=[c for c in ("sector", "subgroup") if c != group]).rename(columns={group: "sector"})
        d5 = st.attach(b, feats, skip=True).merge(panel[["date", "ticker", "cap"]], on=["date", "ticker"], how="left")
        f = st.lead_lag(d5)
        fdates = f.groupby("i")["date"].first().dt.strftime("%Y-%m-%d")
        c = st.summarize_ic(st.ic_series(f, "leader_r5", False), fdates)
        out.append(f"| {gname} | {c[0]} | {c[1]} |")
        print(out[-1], flush=True)
    (ROOT / "docs" / "subindustry_data.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
