"""建立無偏誤股票池的子產業對照表 config/subindustry_pit.csv（來源：櫃買中心產業價值鏈資訊平台）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/build_subindustry.py config/tickers_pit.yaml
"""
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data.fetch_subindustry import classify  # noqa: E402


def main(config):
    cfg = yaml.safe_load(open(config, encoding="utf-8"))
    rows, maps = [], {}
    for k, u in enumerate(cfg["universe"]):
        sid = u["ticker"].split(".")[0]
        try:
            r = classify(sid, maps, u["segment"])
        except Exception as exc:  # 網路錯誤：標為未取得，之後可重跑（已取得的頁面有快取）
            r = {"stock_id": sid, "chain": "", "group": "", "segment": "", "all_entries": "", "found": False,
                 "error": type(exc).__name__}
        r.update({"name": u.get("name", ""), "broad_sector": u["segment"]})
        r["subindustry"] = f"{r['chain']}/{r['group']}" if r["found"] else f"未分類（{u['segment']}）"
        rows.append(r)
        if k % 25 == 0:
            print(f"  {k}/{len(cfg['universe'])} {sid} {r['subindustry']}", flush=True)
    df = pd.DataFrame(rows)[["stock_id", "name", "broad_sector", "subindustry", "chain", "group", "segment", "all_entries", "found"]]
    out = ROOT / "config" / "subindustry_pit.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"寫入 {out}：{len(df)} 檔，找到 {df['found'].sum()} 檔，子產業 {df['subindustry'].nunique()} 種")
    print(df["subindustry"].value_counts().head(40).to_string())


if __name__ == "__main__":
    main(sys.argv[1])
