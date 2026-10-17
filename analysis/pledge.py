"""I023 董監事持股設質比率（縮小版；點子卡 research/ideas/I023-director-share-pledging.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/pledge.py fetch     # 公開資訊觀測站 ajax_stapap1，逐家逐年（約 2,400 次，每次間隔約 3 秒，可中斷續抓）
    .venv/Scripts/python analysis/pledge.py           # 檢定，輸出 docs/pledge.md

設計（依點子卡的縮小版；點子卡沒寫清楚、在看結果前補上的細節以「補」標示）：
- 抓取：每年 6 月（資料年月 YYY06）的董監事持股與設質；股票 = 該資料年用來評估的市值前 300 名
  （2018-06 的資料用 2019 年成員，其餘用同年成員，補）。原始頁快取在 data_cache/events/corp_raw/stapap1/。
- PR = 職稱含「董事」且為「本人」（董事長、副董事長、董事、獨立董事本人；不含法人代表人、經理人、大股東）的設質股數合計 ÷ 目前持股合計。
- 使用時點：6 月資料在 7 月 15 日後的第一個交易日起使用，保持到下一年同一時點（縮小版一年一期）。
- 高設質（主定義）= PR ≥ 50%；另報產業內前 20%（PR > 0 者中）。
- 前置條件：任一年的前 300 名中，PR ≥ 50% 的股票少於 30 檔則停止（依點子卡）。
- 崩跌檢定：2019-01 ~ 2026-04 每月，高設質股與同產業 PR = 0 股票的下個月報酬差（產業內先相減再平均，補）；
  加權指數含息月報酬 ≤ −5% 的月份與其他月份分開，t 值以月份計；另報兩組的月報酬偏態。
- 濾網檢定：fv5 建構，做多名單排除高設質股（只有前 300 名有資料，其餘不排除），與 fv5 原版比較 Sharpe 與最大回撤。
- 通過：(1) 大跌月份差額兩段 < 0、全期 t < −2（大跌月份少，只作方向性證據）；(2) 濾網版兩段 Sharpe 不低於 fv5、全期最大回撤較小。
研究結果，非投資建議。
"""
import html
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import fetch_corp_events as fc  # noqa: E402

MEM = ROOT / "config" / "universe_mcap_membership.csv"
YEARS = range(2018, 2026)


def targets() -> list[tuple[int, str]]:
    m = pd.read_csv(MEM, dtype={"stock_id": str})
    out = []
    for y in YEARS:
        g = m[(m["year"] == max(y, 2019)) & (m["rank"] <= 300)]
        out += [(y, s) for s in sorted(g["stock_id"].unique())]
    return out


def fetch_one(y: int, sid: str) -> str:
    data = {"encodeURIComponent": 1, "step": 1, "firstin": 1, "off": 1, "queryName": "co_id", "inpuType": "co_id", "TYPEK": "all",
            "isnew": "false", "co_id": sid, "year": str(y - 1911), "month": "06"}
    return fc.cached(f"stapap1/{sid}_{y}06.html",
                     lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_stapap1", data, "https://mopsov.twse.com.tw/mops/web/stapap1"))


def cmd_fetch():
    (fc.RAW / "stapap1").mkdir(parents=True, exist_ok=True)
    tg = targets()
    print(f"共 {len(tg)} 次", flush=True)
    fail = 0
    for i, (y, sid) in enumerate(tg):
        if (fc.RAW / "stapap1" / f"{sid}_{y}06.html").exists():
            continue
        try:
            fetch_one(y, sid)
        except RuntimeError as e:
            fail += 1
            print(f"跳過 {sid} {y}：{e}", flush=True)
            time.sleep(60)
        time.sleep(0.5)
        if (i + 1) % 100 == 0:
            print(f"{i + 1}/{len(tg)}（失敗 {fail}）", flush=True)
    print(f"DONE（失敗 {fail}）", flush=True)


def parse(t: str) -> float:
    held = pledged = 0.0
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", t, flags=re.S | re.I):
        c = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        if len(c) >= 6 and "董事" in c[0] and "本人" in c[0] and "代表人" not in c[0]:
            num = lambda s: float(re.sub(r"[^\d.]", "", s) or 0)  # noqa: E731
            held += num(c[3])
            pledged += num(c[4])
    return pledged / held if held > 0 else np.nan


def pr_table() -> pd.DataFrame:
    rows = []
    for y, sid in targets():
        p = fc.RAW / "stapap1" / f"{sid}_{y}06.html"
        if p.exists():
            rows.append({"year": y, "stock_id": sid, "pr": parse(p.read_text(encoding="utf-8"))})
    return pd.DataFrame(rows)


def main():
    import corp_event_study as ce
    import borrow_capacity as bc
    import hedge_construction as hc
    import leg_probe as lp
    import ls_turnover as lt
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    pr = pr_table()
    cnt = pr[pr["pr"] >= 0.5].groupby("year").size().reindex(YEARS, fill_value=0)
    L = ["# I023 董監事持股設質比率（縮小版，自動產生）", "",
         "由 [analysis/pledge.py](../analysis/pledge.py) 產生；設計見程式開頭（看結果前固定）。PR = 董事本人設質股數合計 ÷ 持股合計（每年 6 月資料）。研究結果，非投資建議。", "",
         f"已解析 {len(pr):,} 筆（{pr['stock_id'].nunique()} 家）；PR 有值 {int(pr['pr'].notna().sum()):,} 筆。", "",
         "| 資料年（6 月） | " + " | ".join(str(y) for y in YEARS) + " |", "|---" * (len(YEARS) + 1) + "|",
         "| 前 300 名中 PR ≥ 50% 的檔數 | " + " | ".join(str(int(v)) for v in cnt) + " |",
         "| PR > 0 的檔數 | " + " | ".join(str(int(((pr['year'] == y) & (pr['pr'] > 0)).sum())) for y in YEARS) + " |", ""]
    if cnt.max() < 30:
        L += [f"**前置條件未過**：任一年 PR ≥ 50% 的檔數最多 {int(cnt.max())} 檔（< 30），依點子卡停止，不做崩跌與濾網檢定（未看任何報酬）。"]
        (ROOT / "docs" / "pledge.md").write_text("\n".join(L) + "\n", encoding="utf-8")
        print("STOP", flush=True)
        return
    from data.fetch_financials import FinMindClient
    client = FinMindClient()
    mkt, tx = lp.market_tri(client), lp.tx_continuous(client)
    S = ce.Sample(client, 1, 300, mkt, tx)
    sector = pd.Series({t: S.sector.get(t.split(".")[0], "NA") for t in S.tickers})
    days = S.days

    def pr_at(d):
        y = d.year if (d.month > 7 or (d.month == 7 and d.day > 15)) else d.year - 1
        g = pr[pr["year"] == y].set_index("stock_id")["pr"]
        return pd.Series({t: g.get(t.split(".")[0], np.nan) for t in S.tickers})
    rows = []
    for m in pd.period_range("2019-01", "2026-03", freq="M"):
        k0 = int(days.searchsorted(m.to_timestamp(how="end").normalize(), side="right")) - 1
        k1 = int(days.searchsorted((m + 1).to_timestamp(how="end").normalize(), side="right")) - 1
        if k1 >= S.limit or k0 < 0:
            continue
        d = days[k0]
        p = pr_at(d)[S.member.iloc[k0].to_numpy(bool)]
        r = S.adj.iloc[k1] / S.adj.iloc[k0] - 1
        df = pd.DataFrame({"pr": p, "r": r.reindex(p.index), "sec": sector.reindex(p.index)}).dropna()
        pos = df[df["pr"] > 0]
        top20 = pos.groupby("sec")["pr"].transform(lambda x: x >= x.quantile(0.8)) if len(pos) else pd.Series(dtype=bool)
        diffs = {}
        for lab, hi_mask in (("PR ≥ 50%", df["pr"] >= 0.5), ("產業內前 20%", df.index.isin(pos.index[top20.astype(bool)]) if len(pos) else df["pr"] < -1)):
            hi = df[hi_mask]
            vals = [g["r"].mean() - df[(df["sec"] == s) & (df["pr"] == 0)]["r"].mean() for s, g in hi.groupby("sec")
                    if ((df["sec"] == s) & (df["pr"] == 0)).any()]
            diffs[lab] = float(np.mean(vals)) if vals else np.nan
        rows.append({"m": m, "mkt": float(mkt.asof(days[k1]) / mkt.asof(days[k0]) - 1),
                     **diffs, "hi_r": df[df["pr"] >= 0.5]["r"].tolist(), "zero_r": df[df["pr"] == 0]["r"].tolist()})
    R = pd.DataFrame(rows).set_index("m")
    crash = R["mkt"] <= -0.05

    def ts(x):
        x = x.dropna()
        return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x))
    fm = lambda x: "—" if x[0] != x[0] else f"{x[0]:+.2%}（{x[1]:.1f}，{x[2]}）"  # noqa: E731
    seg = lambda idx: np.array([p.year <= 2022 for p in idx])  # noqa: E731
    L += ["## 崩跌檢定：高設質 − 同產業零設質的下個月報酬差", "",
          "| 定義 | 月份 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|---|"]
    res = {}
    for lab in ("PR ≥ 50%", "產業內前 20%"):
        for mlab, mask in (("大跌月份（加權指數 ≤ −5%）", crash), ("其他月份", ~crash)):
            x = R.loc[mask, lab]
            a, b, f = ts(x[seg(x.index)]), ts(x[~seg(x.index)]), ts(x)
            res[(lab, mlab)] = (a, b, f)
            L.append(f"| {lab} | {mlab} | {fm(a)} | {fm(b)} | {fm(f)} |")
    hi_all = pd.Series(sum(R["hi_r"].tolist(), []))
    zero_all = pd.Series(sum(R["zero_r"].tolist(), []))
    L += ["", f"月報酬偏態：高設質 {hi_all.skew():+.2f}（{len(hi_all):,} 個股月）、零設質 {zero_all.skew():+.2f}（{len(zero_all):,} 個股月）。", ""]
    # 濾網
    c = lp.prepare(500)
    sched = c.schedule
    fee = hc.lending_fees(c.client, c.tickers, c.adj.index)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, c.adj.index)
    close = bc.raw_close(c)
    sue = lp.leg_scores(c, "sue")
    import sue_exdiv_filter as sf

    def shortable_at(d):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = lt.K_CAPITAL / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)

    def hi_flags(d):
        y = d.year if (d.month > 7 or (d.month == 7 and d.day > 15)) else d.year - 1
        g = pr[(pr["year"] == y) & (pr["pr"] >= 0.5)]["stock_id"]
        return pd.Series(c.member.columns.isin([s + ".TW" for s in g]), index=c.member.columns)
    out, shares = {}, []
    for name, filt in (("fv5 原版", False), ("排除高設質（PR ≥ 50%）", True)):
        parts = []
        for off in range(3):
            wd = {}
            for d in sched[off::3]:
                w = lt.ew_ls_buffer(sue[d], c.sector, shortable_at(d), q_keep=None)
                if filt:
                    w, s = sf.filter_long(w, hi_flags(d))
                    shares.append(s)
                wd[d] = w
            parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
        x = pd.concat(parts, axis=1).mean(axis=1)
        x = x[x.index > sched[2]]
        out[name] = hc.stats(x) | {"full": lp.sharpe(x.dropna())}
    b0, b1 = out["fv5 原版"], out["排除高設質（PR ≥ 50%）"]
    L += [f"## 濾網：fv5 做多名單排除高設質股（平均排除做多權重 {np.mean(shares) if shares else 0:.1%}）", "",
          "| 版本 | Sharpe 2019–2022 / 2023–2026/04 | 全期 | 最大回撤 |", "|---|---|---|---|"]
    for k, s in out.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['full']:.2f} | {s['mdd']:.1%} |")
    a, b, f = res[("PR ≥ 50%", "大跌月份（加權指數 ≤ −5%）")]
    c1 = a[0] < 0 and b[0] < 0 and f[1] < -2
    c2 = b1["sh_oos"] >= b0["sh_oos"] and b1["sh_is"] >= b0["sh_is"] and b1["mdd"] > b0["mdd"]
    L += ["", "## 判定", "",
          f"1. 大跌月份差額兩段 < 0、全期 t < −2：{fm(a)}、{fm(b)}、全期 {fm(f)} → {'✓' if c1 else '✗'}",
          f"2. 濾網兩段 Sharpe 不低於 fv5 且最大回撤較小：{b1['sh_oos']:.2f} / {b1['sh_is']:.2f}（回撤 {b1['mdd']:.1%}）vs "
          f"{b0['sh_oos']:.2f} / {b0['sh_is']:.2f}（{b0['mdd']:.1%}）→ {'✓' if c2 else '✗'}", "",
          f"**結論：{'通過' if c1 and c2 else '未通過'}**"]
    (ROOT / "docs" / "pledge.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        cmd_fetch()
    else:
        main()
