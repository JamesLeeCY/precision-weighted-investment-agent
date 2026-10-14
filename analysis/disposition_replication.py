"""處置股做多的獨立驗證：市值第 501–1000 名（與 event_study.py 的前 500 名樣本不重疊）。

用法（於專案根目錄；先執行 fetch_events.py）：
    .venv/Scripts/python analysis/disposition_replication.py
輸出 docs/disposition_replication.md 與 reports/legs/disposition_replication.csv。

規則（在前 500 名看過結果後、跑本樣本前凍結，與 event_study.py 第 4 節相同）：
- 樣本：2019-01 ~ 2026-04 的處置公告，事件當年該股票市值排名 501–1000（config/universe_mcap_membership.csv）。
- 事件日 = 公布日期（遇非交易日取之前最後一個交易日）；第 +1 日收盤進場、持有 20 個交易日（[+2, +21]）。
- 異常報酬 = r − β × 加權指數含息報酬（β 250 日，只用前一日以前）；t 值以事件日聚集。
- 策略：處置股做多（全部、只做第二次以上），同時持有者等權，台指期對沖，換手 × 單邊 0.29625%；沒有事件時持有現金。
- 判定（事前寫下）：[+2, +21] CAR 在 2019–2022 與 2023–2026/04 兩段都為正且 t > 2 才算通過。
只載入價格與除權息／分割（不需要籌碼與營收），第一次執行約 1,200 次 FinMind 請求。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402

RANK_LO, RANK_HI = 501, 1000


def prepare_slim():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    mem = mem[(mem["rank"] >= RANK_LO) & (mem["rank"] <= RANK_HI)]
    ids = sorted(mem["stock_id"].unique())
    adj = {}
    for k, sid in enumerate(ids):
        s = lp.load_stock(client, sid)
        if s is not None:
            adj[sid + ".TW"] = s["adj"]
        if k % 50 == 0:
            print(f"  載入 {k}/{len(ids)}", flush=True)
    adj = pd.DataFrame(adj).sort_index()
    adj = adj[adj.index <= pd.Timestamp(lp.EV_END)]
    tickers = list(adj.columns)
    member = pd.DataFrame(False, index=adj.index, columns=tickers)
    for y, g in mem.groupby("year"):
        cols = [s + ".TW" for s in g["stock_id"] if s + ".TW" in member.columns]
        member.loc[member.index.year == y, cols] = True
    member &= adj.notna()
    rets = adj.pct_change()
    m = lp.market_tri(client).pct_change().reindex(rets.index)
    betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
    return SimpleNamespace(client=client, tickers=tickers, member=member, rets=rets, betas=betas, mkt=m, tx=lp.tx_continuous(client))


def main():
    c = prepare_slim()
    days = c.rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    ar = (c.rets - c.betas.fillna(1.0).mul(c.mkt, axis=0)).to_numpy()
    col = {t: j for j, t in enumerate(c.rets.columns)}

    disp = pd.read_csv(ROOT / "data_cache" / "events" / "disposition.csv", dtype={"stock_id": str}, parse_dates=["announce"])
    disp = disp.rename(columns={"announce": "date"}).drop_duplicates(["stock_id", "date"])
    disp = disp[(disp["date"] >= es.EV_FROM) & (disp["date"] < lp.HOLDOUT)].copy()
    disp["ticker"] = disp["stock_id"] + ".TW"
    disp = disp[disp["ticker"].isin(c.tickers)]
    disp["k0"] = [es.event_index(days, d) for d in disp["date"]]
    disp["t0"] = days[disp["k0"].to_numpy()]
    disp = disp[[bool(c.member.at[t, tk]) for t, tk in zip(disp["t0"], disp["ticker"])]].reset_index(drop=True)
    disp["seg"] = np.where(disp["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    for name, (a, b) in es.WINDOWS.items():
        disp[name] = [es.car(ar[:, col[t]], k, a, b, limit) for t, k in zip(disp["ticker"], disp["k0"])]

    w = "[+2, +21]"
    lines = [f"# 處置股做多：市值第 {RANK_LO}–{RANK_HI} 名的獨立驗證（自動產生）", "",
             "由 [analysis/disposition_replication.py](../analysis/disposition_replication.py) 產生；規則在跑本樣本前凍結（見程式開頭），"
             "與前 500 名的 [event_study_top500.md](event_study_top500.md) 第 4 節相同。CAR = 累積異常報酬，括號為 t 值。研究結果，非投資建議。", "",
             f"判定：[+2, +21] CAR 在兩段都為正且 t > 2 才算通過。樣本 {len(disp)} 筆處置（第二次以上 {int(disp['second'].sum())} 筆）。", "",
             "| 分組 | 事件數 | " + " | ".join(es.WINDOWS) + " |", "|---|---|" + "---|" * len(es.WINDOWS)]
    groups = [("全部", disp)] + [(s, disp[disp["seg"] == s]) for s in ("2019–2022", "2023–2026/04")] + \
             [("第一次", disp[~disp["second"]]), ("第二次以上", disp[disp["second"]])] + \
             [(f"第二次以上 {s}", disp[disp["second"] & (disp["seg"] == s)]) for s in ("2019–2022", "2023–2026/04")]
    for gname, g in groups:
        cells = []
        for win in es.WINDOWS:
            m, t, _ = es.date_clustered(g, win)
            cells.append(f"{m:+.2%}（{t:.1f}）" if m == m else "—")
        lines.append(f"| {gname} | {len(g)} | " + " | ".join(cells) + " |")
    x = disp.dropna(subset=[w])
    passed = all((lambda r: r[0] > 0 and r[1] > 2)(es.date_clustered(disp[disp["seg"] == s], w)) for s in ("2019–2022", "2023–2026/04"))
    lines += ["", f"[+2, +21]：平均 {x[w].mean():+.2%}、中位數 {x[w].median():+.2%}、為正的比例 {(x[w] > 0).mean():.0%}。"
              f"逐年：" + "、".join(f"{y}:{g[w].mean():+.1%}（{len(g)}）" for y, g in x.groupby(x['t0'].dt.year)), "",
              f"**判定：{'通過' if passed else '未通過'}**", "",
              "## 策略（台指期對沖，扣交易成本；2019 ~ 2026/04）", "",
              "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 平均持有檔數 | 有持股的日子 |", "|---|---|---|---|---|---|---|---|"]
    sims = {"處置股做多（持有 20 日）": es.simulate_daily(es.calendar_portfolio(disp, 1.0, days, limit), c, None),
            "只做第二次以上": es.simulate_daily(es.calendar_portfolio(disp[disp["second"]], 1.0, days, limit), c, None)}
    for name, sim in sims.items():
        s = hc.stats(sim["ret"])
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{sim.loc[sim['n'] > 0, 'n'].mean():.1f} | {(sim['n'] > 0).mean():.0%} |")
    lines += ["", "逐年 Sharpe：", ""]
    for name, sim in sims.items():
        lines.append(f"- {name}：" + "、".join(f"{y}:{v:+.1f}" for y, v in hc.stats(sim["ret"])["yearly"].items() if v == v))
    pd.DataFrame({k: v["ret"] for k, v in sims.items()}).to_csv(ROOT / "reports" / "legs" / "disposition_replication.csv")
    (ROOT / "docs" / "disposition_replication.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
