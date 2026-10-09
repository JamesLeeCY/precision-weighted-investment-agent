"""產生研究網站：從本機設定、前瞻紀錄與資料快照抽出數據，嵌入單一 HTML。

    .venv/Scripts/python site/build_site.py                 # 重新抽資料並組頁
    .venv/Scripts/python site/build_site.py --skip-extract  # 只用既有 data.json 組頁

抽資料使用 data_cache/forward/<snapshot>/ 的 FinMind 快照；快照缺的資料會向 FinMind 補抓（耗額度）。
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
sys.path.insert(0, str(ROOT))

FEATURE_KEYS = ["revenue_yoy_pct", "revenue_mom_pct", "revenue_yoy_slope", "gross_margin_pct",
                "gross_margin_slope", "inventory_days_yoy_pct", "receivable_days_yoy_pct"]


def extract(snapshot: str | None = None, year: int | None = None) -> dict:
    """snapshot 預設用最新的 data_cache/forward/<日期>；year 預設為最新預測日所屬年度。"""
    from agents.fundamentals_agent import FundamentalsAgent
    from data.fetch_financials import FinMindClient, FinMindFundamentalsProvider
    import forward.run_forward as fw

    def universe(path):
        cfg = yaml.safe_load(open(ROOT / path, encoding="utf-8"))["universe"]
        return [{"t": u["ticker"][:4], "n": u["name"], "s": u["segment"]} for u in cfg]

    out = {"original": universe("config/tickers.yaml"), "expanded": universe("config/tickers_expanded.yaml")}
    m = pd.read_csv(ROOT / "config/universe_pit_membership.csv", dtype={"stock_id": str})
    out["pit_years"] = {int(y): int(len(g)) for y, g in m.groupby("year")}
    out["pit_unique"] = int(m.stock_id.nunique())
    out["pit_sector_by_year"] = {int(y): g.sector.value_counts().to_dict() for y, g in m.groupby("year")}

    pre = pd.read_csv(fw.PREDICTIONS, dtype={"ticker": str})
    oc = pd.read_csv(fw.OUTCOMES, dtype={"ticker": str})
    latest = sorted(pre.as_of_date.unique())[-1]
    if snapshot is None:  # 最新一批預測當天的快照已含所需財報資料，不必再呼叫 API
        run = pre.loc[pre.as_of_date == latest, "run_utc"].iloc[0]
        snapshot = dt.datetime.fromisoformat(run.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        if not (fw.SNAPSHOT_ROOT / snapshot).is_dir():
            snapshot = sorted(p.name for p in fw.SNAPSHOT_ROOT.iterdir() if p.is_dir())[-1]
    year = year or int(latest[:4])
    if not (m.year == year).any():
        year = int(m.year.max())
    out.update({"generated": dt.date.today().isoformat(), "latest": latest, "year": year,
                "snapshot": snapshot, "n_predictions": int(pre.as_of_date.nunique())})
    client = FinMindClient(cache_dir=str(ROOT / "data_cache/forward" / snapshot))
    agent = FundamentalsAgent(FinMindFundamentalsProvider(client, history_start="2017-01-01"), output_mode="continuous")

    rows = []
    for r in m[m.year == year].itertuples():
        t = r.stock_id + ".TW"
        f = agent.analyze(t, latest).raw_features
        row = {"t": r.stock_id, "n": r.stock_name, "s": r.sector, "rank": int(r.rank),
               "tv": round(r.avg_trading_value / 1e8, 2)}
        for k in FEATURE_KEYS:
            v = f.get(k)
            row[k] = None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 2)
        row["score"] = round(f.get("rule_score", 0), 3)
        row["cov"] = f.get("evidence")
        hist = {}
        for d in sorted(pre.as_of_date.unique()):
            pp = pre[(pre.as_of_date == d) & (pre.ticker == t)]
            rr = oc[(oc.as_of_date == d) & (oc.ticker == t)]
            hist[d] = {"p": round(float(pp.p.iloc[0]), 3) if len(pp) else None,
                       "r": round(float(rr.forward_return.iloc[0]), 4) if len(rr) else None}
        row["h"], row["p"] = hist, hist[latest]["p"]
        rows.append(row)
    out["stocks"] = rows

    df = pre.merge(oc, on=["as_of_date", "ticker"], how="left")
    per = fw.period_metrics(df)
    out["forward"] = [{"d": r.as_of_date, "mode": r.mode, "ic": round(r.ic_within, 3), "ex": round(r.excess_long, 4),
                       "nl": int(r.n_long), "n": int(r.n),
                       "um": round(float(df[df.as_of_date == r.as_of_date].forward_return.mean()), 4)}
                      for r in per.itertuples()]
    out["forward_pending"] = sorted(set(pre.as_of_date) - set(per.as_of_date))
    return out


def build(data: dict) -> Path:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    head = (SITE / "template/head.html").read_text(encoding="utf-8")
    body = (SITE / "template/body.html").read_text(encoding="utf-8").replace("__DATA__", payload)
    out = SITE / "research-dashboard.html"
    out.write_text('<meta charset="utf-8">\n' + head + body, encoding="utf-8")
    return out


def update(snapshot: str | None = None, year: int | None = None) -> Path:
    """重新抽資料並組頁（給 forward/run_forward.py auto 呼叫）。"""
    data = extract(snapshot, year)
    (SITE / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return build(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-extract", action="store_true")
    ap.add_argument("--snapshot", default=None, help="data_cache/forward/ 底下的快照日期（預設最新）")
    ap.add_argument("--year", type=int, default=None, help="逐股表使用的股票池年度（預設最新預測日的年度）")
    args = ap.parse_args(argv)
    if args.skip_extract:
        print(build(json.loads((SITE / "data.json").read_text(encoding="utf-8"))))
    else:
        print(update(args.snapshot, args.year))


if __name__ == "__main__":
    main()
