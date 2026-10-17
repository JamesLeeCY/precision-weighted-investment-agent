"""I009 當沖比（點子卡 research/ideas/I009-day-trading-ratio.md，檢定計畫看結果前固定）。

用法（於專案根目錄；先執行 analysis/fetch_daytrading.py）：
    .venv/Scripts/python analysis/daytrading_leg.py
輸出 docs/daytrading_leg.md。

設計（依點子卡；點子卡沒寫清楚、或資料限制而調整的細節以「補」標示）：
- 樣本：每年市值前 500 名（主樣本）、第 501–1000 名（驗證）；2019 ~ 2026/04 的換倉日（每月營收公告期限後的下一個交易日）。
- DTR = 當沖成交股數（TaiwanStockDayTrading.Volume）÷ 總成交股數（TaiwanStockPrice.Trading_Volume）；
  處置期間（data_cache/events/disposition.csv 起迄）與當日無當沖資料的股票日設為缺值。
- 腿：dt20 = −（DTR 20 日平均，至少 15 天）；dtjump = −（DTR 20 日平均 − 120 日平均，至少 80 天）；只用 t−1 日以前。
  標準包裝：產業內 z → 20 日平均 → 換倉日對產業與 log 市值取殘差（leg_probe.wrap / neutralize）。
  驗證樣本的 log 市值用 corp_event_study.Sample.lmcap（成員檔市值 × 收盤價比例，補：避免另抓股本）。
- IC：產業內 Spearman（20 日，另報 60 日），兩段平均與 t 值（以換倉日為單位）。
- Fama-MacBeth：每個換倉日，之後 20 日報酬的產業內百分位 − 0.5 對 dt20 及控制變數（周轉率、abvol60、amihud20、MAX（21 日最大日報酬）、
  resvol60、過去 20 日報酬、12-1 動能、log 市值、最新 SUE；皆為當日橫斷面百分位 − 0.5）迴歸，係數的時間序列平均與 t 值。
- 組合：產業內前 1/3 做多、後 1/3 放空（ls_turnover.ew_ls_buffer、不含緩衝），每個換倉日換倉，放空須通過借券條件 D
  （1,000 萬與 2 億兩種）；台指期對沖；單邊 0.29625% ＋ 借券費。另報 fv3 式（每 3 個換倉日、三份錯開，2 億）。
- 通過：(1) 主樣本 dt20 的 20 日 IC 兩段皆 > 0 且 t > 2；(2) Fama-MacBeth dt20 係數全期 t > 2、兩段同號；
  (3) 驗證樣本全期 IC > 0 且 t > 2；(4) 主樣本多空（條件 D、2 億）兩段 Sharpe > 0。
  (1)(3) 成立但 (2) 不成立 → 當沖比只是周轉率／彩券型的代理（failed）；(1)–(3) 成立但 (4) 不成立 → partial，再做 SUE 合成。
  dtjump 只在 (1)–(3) 皆以 t > 3 成立時才視為獨立通過，否則只報告。
- 與 SUE 合成（只在 (1)–(3) 成立時執行）：fv5 建構，SUE 與 dt20 的 z 分數平均；兩段都高於 SUE 單獨（1.45 / 1.87）才採用。
- 穩健性（只報告）：(b) 金額版當沖比；(c) 上市／上櫃；(d) 排除電子股；(e) 全市場當沖比高／低月份。
  點子卡的 (a) 2015–2018 與 (f) 漲跌停比例因快取價格從 2018-06 起而未做（補）；全額交割股未另外排除（補：成員檔為市值前 1000 名，幾乎沒有）。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import corp_event_study as ce  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
import lending_legs as ll  # noqa: E402
import ls_turnover as lt  # noqa: E402

ELEC = ("半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "通信網路業", "電子通路業", "資訊服務業", "其他電子業")


def dtr_frames(client, tickers, index) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """回傳（股數版 DTR、金額版 DTR、總成交股數）。"""
    disp = pd.read_csv(ROOT / "data_cache" / "events" / "disposition.csv", dtype={"stock_id": str}, parse_dates=["start", "end"])
    dv, da, tv = {}, {}, {}
    for t in tickers:
        sid = t.split(".")[0]
        px = client.get("TaiwanStockPrice", sid, lp.PX_START)
        if px.empty:
            continue
        px = px.assign(date=pd.to_datetime(px["date"])).set_index("date")
        vol, money = px["Trading_Volume"].astype(float), px["Trading_money"].astype(float)
        tv[t] = vol
        d = client.get("TaiwanStockDayTrading", sid, "2014-01-01", "2026-05-31")
        if d.empty:
            continue
        d = d.assign(date=pd.to_datetime(d["date"])).drop_duplicates("date").set_index("date")
        r1 = (d["Volume"].astype(float) / vol.reindex(d.index)).where(vol.reindex(d.index) > 0)
        r2 = ((d["BuyAmount"].astype(float) + d["SellAmount"].astype(float)) / 2 / money.reindex(d.index)).where(money.reindex(d.index) > 0)
        for x in (r1, r2):
            for g in disp[disp["stock_id"] == sid].itertuples():
                x[(x.index >= g.start) & (x.index <= g.end)] = np.nan
        dv[t], da[t] = r1.clip(upper=1.0), r2.clip(upper=1.0)
    f = lambda m: pd.DataFrame(m).reindex(index=index, columns=tickers)  # noqa: E731
    return f(dv), f(da), f(tv)


def legs(dtr: pd.DataFrame) -> dict:
    m20 = dtr.rolling(20, min_periods=15).mean()
    m120 = dtr.rolling(120, min_periods=80).mean()
    return {"dt20": -m20.shift(1), "dtjump": -(m20 - m120).shift(1)}


def scores_of(raw, member, sector, logcap, sched) -> dict:
    wz = lp.wrap(raw.replace([np.inf, -np.inf], np.nan), member, sector)
    return {d: lp.neutralize(wz.loc[d], sector, logcap.loc[d]) for d in sched}


def ic_stats(scores, fwd, sector, sched, mask_fn=None) -> list:
    ics = pd.Series({d: lp.within_ic(scores[d] if mask_fn is None else scores[d][mask_fn(scores[d].index)], fwd.loc[d], sector)
                     for d in sched}).dropna()
    out = []
    for m in (ics.index < lp.SPLIT, ics.index >= lp.SPLIT, np.ones(len(ics), bool)):
        x = ics[m]
        out.append((float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 else float("nan"), len(x)))
    return out


def fmt_ic(x) -> str:
    return f"{x[0]:+.3f}（{x[1]:.1f}）"


def main():
    c = lp.prepare(500)
    days, sched, sector = c.adj.index, c.schedule, c.sector
    dtr, dtr_amt, vol = dtr_frames(c.client, c.tickers, days)
    L0 = legs(dtr)
    sc = {k: scores_of(v, c.member, sector, c.logcap, sched) for k, v in L0.items()}
    fwd60 = c.adj.shift(-60) / c.adj - 1
    cov = float(np.mean([sc["dt20"][d].notna().sum() / max(1, c.member.loc[d].sum()) for d in sched]))
    ic = {k: (ic_stats(v, c.fwd20, sector, sched), ic_stats(v, fwd60, sector, sched)) for k, v in sc.items()}

    # Fama-MacBeth
    shares = ll.load_shares(c.client, c.tickers, days)
    r = c.adj.pct_change()
    ctrl_raw = {"周轉率": (vol.rolling(20, min_periods=15).sum() / shares).shift(1), "abvol60": c.raws["abvol60"], "amihud20": c.raws["amihud20"],
                "MAX": r.rolling(21, min_periods=15).max().shift(1), "resvol60": c.raws["resvol60"], "過去 20 日報酬": (c.adj / c.adj.shift(20) - 1).shift(1),
                "12-1 動能": (c.adj.shift(21) / c.adj.shift(252) - 1).shift(1), "log 市值": c.logcap}
    sue = lp.leg_scores(c, "sue")
    fm, corr = [], {}
    for d in sched:
        mem = c.member.loc[d]
        df = pd.DataFrame({"y": c.fwd20.loc[d], "dt20": L0["dt20"].loc[d], **{k: v.loc[d] for k, v in ctrl_raw.items()}, "SUE": sue[d]})
        df = df[mem.reindex(df.index).fillna(False)].replace([np.inf, -np.inf], np.nan).dropna()
        if len(df) < 50:
            continue
        df["y"] = df["y"].groupby(sector.reindex(df.index)).rank(pct=True) - 0.5
        X = df.drop(columns="y").rank(pct=True) - 0.5
        beta, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(X)), X.to_numpy()]), df["y"].to_numpy(), rcond=None)
        fm.append(pd.Series(beta[1:], index=X.columns, name=d))
        for k in X.columns[1:]:
            corr.setdefault(k, []).append(X["dt20"].rank().corr(X[k].rank()))
    fm = pd.DataFrame(fm)

    def tser(x):
        x = x.dropna()
        return (float(x.mean()), float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))), len(x))
    fm_dt = [tser(fm.loc[fm.index < lp.SPLIT, "dt20"]), tser(fm.loc[fm.index >= lp.SPLIT, "dt20"]), tser(fm["dt20"])]

    # 驗證樣本（第 501–1000 名）
    import dotenv
    dotenv.load_dotenv(ROOT / ".env")
    mkt, tx = lp.market_tri(c.client), lp.tx_continuous(c.client)
    V = ce.Sample(c.client, 501, 1000, mkt, tx)
    vsec = pd.Series({t: V.sector.get(t.split(".")[0], "NA") for t in V.tickers})
    vdtr, _, _ = dtr_frames(c.client, V.tickers, V.days)
    vsched = [d for d in sched if d in V.days]
    vfwd = V.adj.shift(-20) / V.adj - 1
    vL = legs(vdtr)
    vic = {k: ic_stats(scores_of(v, V.member, vsec, V.lmcap, vsched), vfwd, vsec, vsched) for k, v in vL.items()}

    # 組合
    fee = hc.lending_fees(c.client, c.tickers, days)
    quota, lend60 = bc.load_short_data(c.client, c.tickers, days)
    close = bc.raw_close(c)

    def shortable_at(d, K):
        n_short = max(1, int(c.member.loc[d].sum() / 3))
        need = K / n_short / close.loc[d]
        return (lend60.loc[d] > 0) & (quota.loc[d] >= need) & (need <= bc.DEPTH_FRAC * lend60.loc[d]) & (fee.loc[d] <= bc.FEE_MAX)
    port = {}
    for K, lab in ((1e7, "1,000 萬"), (2e8, "2 億")):
        wd = {d: lt.ew_ls_buffer(sc["dt20"][d], sector, shortable_at(d, K), q_keep=None) for d in sched}
        sim = hc.simulate_weights(wd, c.rets, c.betas, c.tx, sched, fee=fee)
        port[f"每月換倉（{lab}）"] = hc.stats(sim["ret"], sim)
    parts = []
    for off in range(3):
        wd = {d: lt.ew_ls_buffer(sc["dt20"][d], sector, shortable_at(d, 2e8), q_keep=None) for d in sched[off::3]}
        parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
    x = pd.concat(parts, axis=1).mean(axis=1)
    port["每 3 個月、三份錯開（2 億）"] = hc.stats(x[x.index > sched[2]])

    # 判定
    i20 = ic["dt20"][0]
    c1 = i20[0][0] > 0 and i20[0][1] > 2 and i20[1][0] > 0 and i20[1][1] > 2
    c2 = fm_dt[2][1] > 2 and np.sign(fm_dt[0][0]) == np.sign(fm_dt[1][0])
    c3 = vic["dt20"][2][0] > 0 and vic["dt20"][2][1] > 2
    p2 = port["每月換倉（2 億）"]
    c4 = p2["sh_oos"] > 0 and p2["sh_is"] > 0

    # 穩健性
    amt_sc = scores_of(legs(dtr_amt)["dt20"], c.member, sector, c.logcap, sched)
    mkt_type = c.mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["market_type"]
    mt = pd.Series({t: mkt_type.get(t.split(".")[0], "") for t in c.tickers})
    mkt_dtr = dtr.where(c.member).mean(axis=1)
    hi_month = mkt_dtr.resample("ME").mean()
    hi_set = set(hi_month[hi_month > hi_month.median()].index.to_period("M"))
    rob = {"金額版當沖比": ic_stats(amt_sc, c.fwd20, sector, sched),
           "只看上市": ic_stats(sc["dt20"], c.fwd20, sector, sched, lambda idx: mt.reindex(idx).astype(str).str.contains("sii|上市|twse", case=False).to_numpy()),
           "只看上櫃": ic_stats(sc["dt20"], c.fwd20, sector, sched, lambda idx: mt.reindex(idx).astype(str).str.contains("otc|上櫃|tpex", case=False).to_numpy()),
           "排除電子股": ic_stats(sc["dt20"], c.fwd20, sector, sched, lambda idx: ~sector.reindex(idx).isin(ELEC).to_numpy())}
    ics_all = pd.Series({d: lp.within_ic(sc["dt20"][d], c.fwd20.loc[d], sector) for d in sched}).dropna()
    hm = ics_all[[d.to_period("M") in hi_set for d in ics_all.index]]
    lm = ics_all[[d.to_period("M") not in hi_set for d in ics_all.index]]

    synth = None
    if c1 and c2 and c3:
        def zs(s):
            s = s.dropna()
            return (s - s.mean()) / s.std() if len(s) > 2 and s.std() > 0 else s * 0
        comb = {d: pd.concat([zs(sue[d]), zs(sc["dt20"][d])], axis=1).mean(axis=1, skipna=False).dropna() for d in sched}
        res = {}
        for nm, scs in (("SUE 單獨（fv5 建構）", sue), ("SUE + dt20", comb)):
            parts = []
            for off in range(3):
                wd = {d: lt.ew_ls_buffer(scs[d], sector, shortable_at(d, 2e8), q_keep=None) for d in sched[off::3]}
                parts.append(hc.simulate_weights(wd, c.rets, c.betas, c.tx, list(wd), fee=fee)["ret"])
            x = pd.concat(parts, axis=1).mean(axis=1)
            res[nm] = hc.stats(x[x.index > sched[2]])
        synth = res

    L = ["# I009 當沖比（自動產生）", "",
         "由 [analysis/daytrading_leg.py](../analysis/daytrading_leg.py) 產生；設計見程式開頭（看結果前固定）。"
         "IC 為產業內 Spearman（−1～1，0 為無預測力），括號為 t 值（以換倉日為單位）；Sharpe 為扣成本（單邊 0.29625% ＋ 借券費）與台指期對沖後的年化值，"
         "格式 2019–2022 / 2023–2026/04。腿為負號（當沖比越高分數越低）。研究結果，非投資建議。", "",
         f"主樣本換倉日 {len(sched)} 個；dt20 有值比例 {cov:.0%}（成員中）；驗證換倉日 {len(vsched)} 個。", "",
         "## 1. 產業內 IC", "", "| 腿 | 樣本 | 20 日：2019–2022 | 2023–2026/04 | 全期 | 60 日：2019–2022 | 2023–2026/04 |", "|---|---|---|---|---|---|---|"]
    for k in ("dt20", "dtjump"):
        a, b = ic[k]
        L.append(f"| {k} | 前 500 名 | {fmt_ic(a[0])} | {fmt_ic(a[1])} | {fmt_ic(a[2])} | {fmt_ic(b[0])} | {fmt_ic(b[1])} |")
        v = vic[k]
        L.append(f"| {k} | 第 501–1000 名 | {fmt_ic(v[0])} | {fmt_ic(v[1])} | {fmt_ic(v[2])} | — | — |")
    L += ["", "## 2. Fama-MacBeth（之後 20 日產業內報酬百分位；係數為百分位差 1 對應的百分位變化）", "",
          "| 變數 | 2019–2022 | 2023–2026/04 | 全期 | 與 dt20 的等級相關 |", "|---|---|---|---|---|"]
    for k in fm.columns:
        s = [tser(fm.loc[fm.index < lp.SPLIT, k]), tser(fm.loc[fm.index >= lp.SPLIT, k]), tser(fm[k])]
        L.append(f"| {k} | {s[0][0]:+.3f}（{s[0][1]:.1f}） | {s[1][0]:+.3f}（{s[1][1]:.1f}） | {s[2][0]:+.3f}（{s[2][1]:.1f}） | "
                 f"{'—' if k == 'dt20' else f'{np.nanmean(corr[k]):+.2f}'} |")
    L += ["", "## 3. 多空組合（dt20）", "", "| 建構 | Sharpe | 年化報酬 | 最大回撤 | 年換手 |", "|---|---|---|---|---|"]
    for k, s in port.items():
        L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['mdd']:.1%} | {(f"{s['turnover']:.1f}" if 'turnover' in s else '—')} |")
    L += ["", "## 4. 穩健性（dt20 的 20 日 IC，只報告）", "", "| 版本 | 2019–2022 | 2023–2026/04 | 全期 |", "|---|---|---|---|"]
    for k, v in rob.items():
        L.append(f"| {k} | {fmt_ic(v[0])} | {fmt_ic(v[1])} | {fmt_ic(v[2])} |")
    tt = lambda x: f"{x.mean():+.3f}（{x.mean() / (x.std(ddof=1) / math.sqrt(len(x))):.1f}，{len(x)}）"  # noqa: E731
    L.append(f"| 全市場當沖比高的月份 | — | — | {tt(hm)} |")
    L.append(f"| 全市場當沖比低的月份 | — | — | {tt(lm)} |")
    if synth:
        L += ["", "## 5. 與 SUE 合成（fv5 建構）", "", "| 版本 | Sharpe | 年化報酬 |", "|---|---|---|"]
        for k, s in synth.items():
            L.append(f"| {k} | {s['sh_oos']:.2f} / {s['sh_is']:.2f} | {s['ann']:+.1%} |")
    L += ["", "## 判定（dt20）", "",
          f"1. 主樣本 20 日 IC 兩段 > 0 且 t > 2：{fmt_ic(i20[0])} / {fmt_ic(i20[1])} → {'✓' if c1 else '✗'}",
          f"2. Fama-MacBeth 控制後全期 t > 2、兩段同號：{fm_dt[0][0]:+.3f} / {fm_dt[1][0]:+.3f}，全期 t {fm_dt[2][1]:.1f} → {'✓' if c2 else '✗'}",
          f"3. 驗證樣本全期 IC > 0 且 t > 2：{fmt_ic(vic['dt20'][2])} → {'✓' if c3 else '✗'}",
          f"4. 多空（條件 D、2 億）兩段 Sharpe > 0：{p2['sh_oos']:.2f} / {p2['sh_is']:.2f} → {'✓' if c4 else '✗'}", ""]
    if c1 and c3 and not c2:
        concl = "未通過：IC 成立但控制周轉率等後不成立，當沖比只是同族變數的代理"
    elif c1 and c2 and c3 and not c4:
        concl = "部分通過（partial）：訊號成立但多空扣成本後不賺錢"
    elif c1 and c2 and c3 and c4:
        concl = "通過"
    else:
        concl = "未通過"
    L.append(f"**結論：{concl}**")
    (ROOT / "docs" / "daytrading_leg.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
