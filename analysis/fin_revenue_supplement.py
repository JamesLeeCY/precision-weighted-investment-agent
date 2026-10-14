"""延後申報（15 日前）的金控月營收補充預測：依 2026-10-13 前瞻預測的金融保險股，看這些金控落在產業內的哪一段。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/fin_revenue_supplement.py 2026-09
輸出 docs/fin_supplement_{營收月份}.md。

背景：具保險子公司的金控依規定於 15 日前申報月營收，晚於一般公司的 10 日；前瞻規格 fv2–fv5 依事先登錄的規則只採用公告期限前收錄的營收，
這些金控在 10/13 的預測中沒有分數（不會納入，也不修改凍結紀錄）。本程式只作補充參考。

做法：
- 抓 10 家金控的月營收（新的快照，不用研究快取），算 SUE 與營收創新高（前 24 個月最高），與研究相同的定義（data/revenue_signal、max_rec_robust.rec_n）。
- 與 fv5（市值前 500 檔）、fv4（前 300 檔）在 2026-10-13 已有分數的金融保險股合併，在產業內算百分位排名：前 1/3 = 模型偏多、後 1/3 = 偏空。
- 金控營收含保費與投資收益，月營收波動大，SUE 的意義與一般製造業不同，解讀要保守。
- FinMind 隔日才收錄新申報的營收；當月營收尚未進 FinMind 時，改向公開資訊觀測站即時查詢（t05st10_ifrs，單位仟元 × 1000），
  歷史月份仍用 FinMind。每次執行用新的快取目錄（日期＋時間），同一天重跑不會沿用舊結果。
"""
import datetime as dt
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))
import max_rec_robust as mr  # noqa: E402
from data import revenue_signal as rsig  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from forward import run_forward as fv1  # noqa: E402
from forward import run_forward_fv4 as fv4  # noqa: E402
from forward import run_forward_fv5 as fv5  # noqa: E402

FIN = {"2881": "富邦金", "2882": "國泰金", "2891": "中信金", "2883": "凱基金", "2885": "元大金", "2886": "兆豐金",
       "2892": "第一金", "2880": "華南金", "5880": "合庫金", "2887": "台新新光金"}
AS_OF = "2026-10-13"


def mops_revenue(sid: str, ym: pd.Timestamp) -> float | None:
    """公開資訊觀測站即時查詢單月營收（元）；尚未申報回傳 None。"""
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
                      "Origin": "https://mops.twse.com.tw", "Referer": "https://mops.twse.com.tw/mops/",
                      "Accept": "application/json, text/plain, */*"})
    body = {"apiName": "ajax_t05st10_ifrs", "parameters": {
        "co_id": sid, "year": str(ym.year - 1911), "month": f"{ym.month:02d}", "TYPEK": "all", "isnew": "false",
        "encodeURIComponent": 1, "step": 0, "firstin": 1, "off": 1, "queryName": "co_id", "inpuType": "co_id"}}
    url = s.post("https://mops.twse.com.tw/mops/api/redirectToOld", json=body, timeout=30).json()["result"]["url"]
    h = s.get(url, timeout=60, headers={"Accept": "text/html"})
    h.encoding = "utf-8"
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>|&nbsp;", " ", h.text))
    want = f"民國{ym.year - 1911}年{ym.month:02d}月"
    m = re.search(r"本月\s+([\d,]+)", txt)
    if want not in txt or not m:
        return None
    return float(m.group(1).replace(",", "")) * 1000


def main(rev_month: str):
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    ym = pd.Timestamp(rev_month + "-01")
    avail = ym + pd.offsets.MonthBegin(1)
    client = FinMindClient(cache_dir=fv1.SNAPSHOT_ROOT / "fin_supplement" / dt.datetime.now().strftime("%Y-%m-%d_%H%M"))
    new, missing = {}, []
    for sid, nm in FIN.items():
        rev = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
        r = rev.copy()
        r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1)) if not r.empty else pd.Series(dtype="datetime64[ns]")
        row = r[r["ym"] == ym] if not r.empty else r
        source = "FinMind"
        if row.empty:
            v = mops_revenue(sid, ym)
            if v is None:
                missing.append(f"{sid} {nm}")
                continue
            add = {"date": (ym + pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d"), "stock_id": sid, "revenue": v,
                   "revenue_month": ym.month, "revenue_year": ym.year, "create_time": dt.date.today().isoformat()}
            rev = pd.concat([rev, pd.DataFrame([add])], ignore_index=True)
            r = rev.copy()
            r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
            row = r[r["ym"] == ym]
            source = "公開資訊觀測站"
        s = rsig.revenue_surprise(rev).set_index("avail_month")
        rec = mr.rec_n(rev, 24)
        prev = r.set_index("ym")["revenue"].astype(float)
        new[sid + ".TW"] = {"name": nm, "sue": s.loc[avail, "sue"] if avail in s.index else np.nan,
                            "rec24": rec.loc[avail] if avail in rec.index else np.nan,
                            "yoy": float(prev.get(ym) / prev.get(ym - pd.DateOffset(years=1)) - 1) if prev.get(ym - pd.DateOffset(years=1)) else np.nan,
                            "revenue": float(prev.get(ym)), "source": source, "create_time": str(row["create_time"].iloc[0]) if "create_time" in row else ""}
    lines = [f"# 延後申報金控的 {rev_month} 月營收補充預測（自動產生，{dt.date.today().isoformat()}）", "",
             "由 [analysis/fin_revenue_supplement.py](../analysis/fin_revenue_supplement.py) 產生。具保險子公司的金控於 15 日前申報月營收，"
             f"晚於前瞻規格的公告期限；它們在 {AS_OF} 的前瞻預測中沒有分數（依事先登錄的規則不補入）。本表只作補充參考，不是投資建議。", "",
             "百分位 = 在該股票池的金融保險股中（含 10/13 已有分數者）的產業內排名，1 = 最高；前 1/3 為模型偏多、後 1/3 為偏空。"
             "金控營收含保費與投資收益，月營收波動大，SUE 的意義與製造業不同，解讀應保守。", ""]
    if missing:
        lines += [f"**尚未取得營收**：{'、'.join(missing)}（可能尚未申報或 FinMind 尚未更新）。", ""]
    for label, mod, cols in (("fv5 股票池（市值前 500）：依 SUE", fv5, ["sue"]), ("fv4 股票池（市值前 300）：依 SUE + 營收創新高", fv4, ["sue", "rec24"])):
        p = fv1.read_csv(mod.PREDICTIONS, mod.PRED_COLUMNS)
        p = p[(p["as_of_date"] == AS_OF) & (p["sector"] == "金融保險")].set_index("ticker")
        base = p[cols].copy()
        for t, v in new.items():
            if t in base.index:
                for c in cols:
                    base.loc[t, c] = v[c]
        base = base.dropna()
        z = (base - base.mean()) / base.std()
        comp = z.mean(axis=1)
        pct = comp.rank(pct=True)
        lines += [f"## {label}", "", f"金融保險股中有分數者 {len(base)} 檔（10/13 已有 {int(p[cols].notna().all(axis=1).sum())} 檔 + 本次補入）。", "",
                  "| 股票 | 9 月營收年增 | SUE | 營收 ÷ 前 24 個月最高 | 產業內百分位 | 模型分段 | 營收來源 |", "|---|---|---|---|---|---|---|"]
        for t, v in new.items():
            if t not in pct.index:
                continue
            q = pct[t]
            seg = "前 1/3（偏多）" if q > 2 / 3 else ("後 1/3（偏空）" if q <= 1 / 3 else "中間")
            lines.append(f"| {t[:4]} {v['name']} | {v['yoy']:+.1%} | {v['sue']:+.2f} | {v['rec24'] + 1:.2f} | {q:.0%} | {seg} | {v['source']} |")
        lines.append("")
    out = ROOT / "docs" / f"fin_supplement_{rev_month}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"MISSING={len(missing)}")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
