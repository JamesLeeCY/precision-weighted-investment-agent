"""I007 年度盈餘驚奇改用實際董事會決議日（點子卡 research/ideas/I007-annual-earnings-surprise-actual-board-da.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/earnings_board_date.py
輸出 docs/earnings_board_date.md 與 reports/legs/earnings_board_date_{main,val}.csv。

- 資料：公開資訊觀測站股利分派彙總表（dividend_surprise.fetch_mops，已快取）的「年度」列（不論是否配息、是否虧損），
  每家公司每個會計年度取最早的決議日；去年本期淨利缺值者剔除。決議日 2019-01 ~ 2026-04。
- 主檢定只用決議日 ≤ 當年 3/31 的事件；晚於 3/31 的單獨報告。t0 = 決議日（非交易日取下一個交易日），第 +1 日收盤進場。
- ES =（今年 − 去年本期淨利）÷ t0−1 日市值；市值 = 當年股票池建檔市值（universe_mcap_membership.csv 的 mcap，年初）× 股價變動
  （點子卡：不配息公司沒有每股股利，無法由股利推股數）。次要 ES_g = 淨利年變動 ÷ |去年淨利|，限制 [−1, 1]（只報告）。
- 分組：每年依 ES 前 30% − 後 30%；視窗 [−1,+1]（只報告）、[+2,+20]、[+2,+40]（主要）、[+2,+60]（只報告）；
  有配息者持有期在除息日往前 15 個交易日截止（同 I006）。
- 迴歸：CAR[+2,+40] ~ ES、SUE、全年營收年增率、股利驚奇 DS（不配息者 0）、殖利率、公告提前天數（排名 −0.5～+0.5）、log 市值、產業與年度；
  標準誤依決議日分群。SUE 與營收年增率需要月營收（驗證樣本約 580 次 FinMind 請求，客戶端自動等待額度）。
- 可交易：只做多前 30%（台指期對沖）；主樣本另做多空（放空後 30% 中符合可借條件 D 者，扣借券費）。
- 通過（全部成立）：(1) 主樣本前 30% − 後 30% 兩段 > 0、全期 t > 2；(2) 主樣本控制後 ES 係數兩段 > 0、全期 t > 3；
  (3) 驗證樣本組差 > 0 且 t > 2，含 SUE 控制的係數 > 0、t > 2；(4) 只做多扣成本後主樣本兩段 Sharpe > 0、驗證全期 Sharpe > 0。
  (1)–(3) 成立而 (4) 不成立 → partial；(1)(3) 成立但控制 SUE 後不顯著 → 只是營收驚奇的代理（未通過）。
- 未做（只報告原因）：ES_q4、ES_sd 需 FinMind 財報（約 1,400 次）；2021 年後改用每日重大訊息財報日的穩健性與 I008 共用，留待 I008。
研究結果，非投資建議。
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import borrow_capacity as bc  # noqa: E402
import dividend_events as de  # noqa: E402
import dividend_surprise as dsu  # noqa: E402
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.revenue_signal import revenue_surprise  # noqa: E402

WINDOWS = {"[−1, +1] 公告反應": (-1, 1), "[+2, +20]": (2, 20), "[+2, +40]": (2, 40), "[+2, +60]": (2, 60)}
MAIN = "[+2, +40]"
EX_LEAD = 15


def annual_events(mops: pd.DataFrame) -> pd.DataFrame:
    m = mops[mops["stock_id"].str.fullmatch(r"\d{4}") & mops["annual"] & mops["fy"].notna()].copy()
    m["fy"] = m["fy"].astype(int)
    first = m.dropna(subset=["board"]).sort_values("board").groupby(["stock_id", "fy"])["board"].first()
    amt = m.sort_values("query_year").groupby(["stock_id", "fy"])[["ni", "cash_ps", "cash_total"]].last()
    ev = amt.join(first).reset_index()
    prev = amt.join(first).reset_index().assign(fy=lambda x: x["fy"] + 1).rename(
        columns={"ni": "ni_prev", "cash_ps": "ps_prev", "cash_total": "tot_prev", "board": "board_prev"})
    ev = ev.merge(prev, on=["stock_id", "fy"], how="left").dropna(subset=["board", "ni", "ni_prev"])
    ev = ev[(ev["board"] >= "2019-01-01") & (ev["board"] < lp.HOLDOUT)].copy()
    ev["early"] = ev["board"] <= pd.to_datetime(ev["board"].dt.year.astype(str) + "-03-31")
    adv = (ev["board_prev"] + pd.DateOffset(years=1) - ev["board"]).dt.days
    ev["advance"] = adv.where(ev["board_prev"].notna())
    ev["tot_prev"] = ev["tot_prev"].fillna(0.0)
    return ev.reset_index(drop=True)


def revenue_controls(client, sid: str, t0: pd.Timestamp, fy: int) -> tuple[float, float]:
    rev = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
    if rev.empty:
        return np.nan, np.nan
    s = revenue_surprise(rev).set_index("avail_month")["sue"]
    mo = t0.to_period("M").to_timestamp()
    avail = mo if t0.day > 10 else mo - pd.offsets.MonthBegin(1)
    s = s[s.index <= avail].dropna()
    sue = float(s.iloc[-1]) if len(s) else np.nan
    r = rev.assign(revenue=rev["revenue"].astype(float))
    a, b = r[r["revenue_year"] == fy], r[r["revenue_year"] == fy - 1]
    g = float(a["revenue"].sum() / b["revenue"].sum() - 1) if len(a) == 12 and len(b) == 12 and b["revenue"].sum() > 0 else np.nan
    return sue, g


def spread(ev: pd.DataFrame, col: str, gcol: str = "grp") -> tuple[float, float, int]:
    vals = {}
    for t0, g in ev.dropna(subset=[col]).groupby("t0"):
        a, b = g.loc[g[gcol] == "好消息（前 30%）", col], g.loc[g[gcol] == "壞消息（後 30%）", col]
        if len(a) or len(b):
            vals[t0] = (a.mean() if len(a) else 0.0) - (b.mean() if len(b) else 0.0)
    v = pd.Series(vals, dtype=float)
    if len(v) < 5:
        return float("nan"), float("nan"), len(v)
    return float(v.mean()), float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))), len(v)


def assign_groups(ev: pd.DataFrame, col: str, gcol: str = "grp") -> pd.DataFrame:
    ev[gcol] = "中間"
    for _, g in ev.groupby("year"):
        r = g[col].rank(pct=True)
        ev.loc[g.index[r > 0.7], gcol] = "好消息（前 30%）"
        ev.loc[g.index[r <= 0.3], gcol] = "壞消息（後 30%）"
    return ev


def analyse(client, events: pd.DataFrame, lo: int, hi: int, mkt_tri, tx) -> dict:
    adj, close, member, divs = de.load_sample(client, lo, hi)
    rets = adj.pct_change()
    days = rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    m = mkt_tri.pct_change().reindex(days)
    betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
    ar = (rets - betas.fillna(1.0).mul(m, axis=0)).to_numpy()
    col = {t: j for j, t in enumerate(adj.columns)}
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str}, parse_dates=["rebalance_date"])
    mem = mem[(mem["rank"] >= lo) & (mem["rank"] <= hi)]
    base = mem.set_index(["year", "stock_id"])[["mcap", "rebalance_date", "sector", "market_type"]]
    sector = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["sector"]

    ev = events.copy()
    ev["ticker"] = ev["stock_id"] + ".TW"
    ev = ev[ev["ticker"].isin(col)].copy()
    ev["k0"] = [int(days.searchsorted(d, side="left")) for d in ev["board"]]
    ev = ev[(ev["k0"] >= 1) & (ev["k0"] < limit - 2)]
    ev["t0"] = days[ev["k0"].to_numpy()]
    ev["year"] = ev["t0"].dt.year
    ev = ev[[(y, s) in base.index for y, s in zip(ev["year"], ev["stock_id"])]].copy()
    b = base.loc[list(zip(ev["year"], ev["stock_id"]))]
    k_base = [int(days.searchsorted(d, side="right")) - 1 for d in b["rebalance_date"]]
    ev["mcap"] = [mc * close.iat[k - 1, col[t]] / close.iat[kb, col[t]] if kb >= 0 and close.iat[kb, col[t]] > 0 else np.nan
                  for mc, k, kb, t in zip(b["mcap"].to_numpy(), ev["k0"], k_base, ev["ticker"])]
    ev["market"] = b["market_type"].to_numpy()
    ev = ev[ev["mcap"] > 0].copy()
    ev["es"] = (ev["ni"] - ev["ni_prev"]) / ev["mcap"]
    ev["es_g"] = ((ev["ni"] - ev["ni_prev"]) / ev["ni_prev"].abs().replace(0, np.nan)).clip(-1, 1)
    payout = (ev["tot_prev"] / ev["ni_prev"]).clip(0, 1.5)
    ds = np.where(ev["ni_prev"] > 0, ev["cash_total"] - payout * ev["ni"], ev["cash_total"] - ev["tot_prev"]) / ev["mcap"]
    ev["ds"] = np.where((ev["cash_total"] == 0) & (ev["tot_prev"] == 0), 0.0, ds)
    ev["yield"] = ev["cash_total"] / ev["mcap"]
    ev["payer"] = ev["cash_total"] > 0
    ev["fin"] = ev["stock_id"].map(sector).fillna("").str.contains("金融")
    ev["seg"] = np.where(ev["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")

    d = divs.copy()
    d["date"] = pd.to_datetime(d["date"])
    exd = d.groupby("ticker")["date"].apply(lambda s: sorted(s))
    ends, capped = [], []
    for t, k, pay in zip(ev["ticker"], ev["k0"], ev["payer"]):
        cap = k + 60
        if pay:
            for x in exd.get(t, []):
                kx = int(days.searchsorted(x))
                if kx > k + 1:
                    cap = min(cap, max(kx - EX_LEAD, k + 2))
                    break
        ends.append(min(cap, limit - 1))
        capped.append(cap < k + 40)
    ev["k_end"], ev["capped"] = ends, capped
    for name, (a, bb) in WINDOWS.items():
        if a < 0:
            ev[name] = [es.car(ar[:, col[t]], k, a, bb, limit) for t, k in zip(ev["ticker"], ev["k0"])]
        else:
            ev[name] = [np.nansum(ar[k + a:min(k + bb, e) + 1, col[t]]) if min(k + bb, e) >= k + a else np.nan
                        for t, k, e in zip(ev["ticker"], ev["k0"], ev["k_end"])]
    ev["up1"] = [rets.iat[k + 1, col[t]] >= 0.095 for t, k in zip(ev["ticker"], ev["k0"])]

    early = assign_groups(ev[ev["early"]].copy(), "es")
    late = assign_groups(ev[~ev["early"]].copy(), "es")
    early = assign_groups(early, "es_g", "grp_g")

    # 控制變數與迴歸（只用 3/31 前的事件）
    ctrl = [revenue_controls(client, s, t, fy) for s, t, fy in zip(early["stock_id"], early["t0"], early["fy"])]
    early["sue"], early["rev_g"] = [x[0] for x in ctrl], [x[1] for x in ctrl]
    reg = {}
    for seg, g in [("2019–2022", early[early["seg"] == "2019–2022"]), ("2023–2026/04", early[early["seg"] == "2023–2026/04"]), ("全期", early)]:
        g = g.dropna(subset=[MAIN, "es", "sue", "rev_g", "ds", "yield"]).copy()
        g["advance"] = g["advance"].fillna(0.0)
        for v in ("es", "sue", "rev_g", "ds", "yield", "advance"):
            g[v + "_r"] = g.groupby("year")[v].rank(pct=True) - 0.5
        X = pd.concat([pd.Series(1.0, index=g.index, name="c"), g[["es_r", "sue_r", "rev_g_r", "ds_r", "yield_r", "advance_r"]],
                       (np.log(g["mcap"]) - np.log(g["mcap"]).mean()).rename("lm"),
                       pd.get_dummies(g["stock_id"].map(sector).fillna("NA"), drop_first=True, dtype=float),
                       pd.get_dummies(g["year"], drop_first=True, dtype=float, prefix="y")], axis=1)
        beta, se = dsu.ols_cluster(g[MAIN].to_numpy(float), X.to_numpy(float), g["t0"].astype(str).to_numpy())
        reg[seg] = {"b": beta[1], "t": beta[1] / se[1], "b_sue": beta[2], "t_sue": beta[2] / se[2], "n": len(g),
                    "c_sue": float(g["es"].rank().corr(g["sue"].rank())), "c_rev": float(g["es"].rank().corr(g["rev_g"].rank())),
                    "c_ds": float(g["es"].rank().corr(g["ds"].rank()))}
    # ES 對營收年增率的殘差排序（只報告）
    gg = early.dropna(subset=["es", "rev_g"]).copy()
    if len(gg) > 30:
        A = np.column_stack([np.ones(len(gg)), gg["rev_g"].rank(pct=True)])
        bres, *_ = np.linalg.lstsq(A, gg["es"].rank(pct=True).to_numpy(), rcond=None)
        gg["es_res"] = gg["es"].rank(pct=True) - A @ bres
        gg = assign_groups(gg, "es_res", "grp_res")
        resid_spread = spread(gg, MAIN, "grp_res")
    else:
        resid_spread = (np.nan, np.nan, 0)

    # 可交易版本
    cs = SimpleNamespace(rets=rets, betas=betas, tx=tx)
    fee = shortable = None
    if lo == 1:
        fee = hc.lending_fees(client, list(adj.columns), days)
        quota, lend60 = bc.load_short_data(client, list(adj.columns), days)

        def shortable(k, t):
            need = 2e8 / 30 / close.iat[k, col[t]]
            return (lend60.iat[k, col[t]] > 0 and quota.iat[k, col[t]] >= need and need <= bc.DEPTH_FRAC * lend60.iat[k, col[t]]
                    and fee.iat[k, col[t]] <= bc.FEE_MAX)

    def book(longs, shorts):
        pos = {}
        for df, sign in ((longs, 1), (shorts, -1)):
            for r in df.itertuples():
                if sign < 0 and not shortable(r.k0 + 1, r.ticker):
                    continue
                for k in range(r.k0 + 1, min(r.k0 + 40, r.k_end)):
                    pos.setdefault(days[k], []).append((r.ticker, sign))
        out = {}
        for dd, lst in pos.items():
            L = sorted({t for t, s in lst if s > 0})
            S = sorted({t for t, s in lst if s < 0} - set(L))
            out[dd] = pd.Series({t: 1 / len(L) for t in L} | {t: -1 / len(S) for t in S}, dtype=float)
        return out
    good, bad = early[early["grp"] == "好消息（前 30%）"], early[early["grp"] == "壞消息（後 30%）"]
    sims = {"只做多好消息（台指期對沖）": es.simulate_daily(book(good, good.iloc[0:0]), cs, None)}
    if lo == 1:
        sims["多空：做多好消息、放空壞消息（可借條件 D）"] = es.simulate_daily(book(good, bad), cs, fee)

    # 樣本選擇：股票池成員中沒有年度列的比例與市值占比
    sel = []
    ann_keys = set(zip(events["stock_id"], events["board"].dt.year))
    for y, g in mem.groupby("year"):
        if y < 2019 or y > 2026:
            continue
        has = g["stock_id"].map(lambda s: (s, y) in ann_keys)
        sel.append((y, float((~has).mean()), float(g.loc[~has, "mcap"].sum() / g["mcap"].sum())))
    return {"early": early, "late": late, "reg": reg, "sims": sims, "sel": sel, "resid": resid_spread, "n_all": len(ev)}


def fmt(x):
    return "—" if x[0] != x[0] else f"{x[0]:+.2%}（{x[1]:.1f}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    events = annual_events(dsu.fetch_mops())
    mkt_tri, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for name, (lo, hi) in (("前 500 名（主樣本）", (1, 500)), ("第 501–1000 名（驗證）", (501, 1000))):
        res[name] = analyse(client, events, lo, hi, mkt_tri, tx)
        print(name, "done", flush=True)

    lines = ["# I007 年度盈餘驚奇改用實際董事會決議日（自動產生）", "",
             "由 [analysis/earnings_board_date.py](../analysis/earnings_board_date.py) 產生；檢定計畫見點子卡 "
             "[I007](../research/ideas/I007-annual-earnings-surprise-actual-board-da.md)（看結果前固定；主樣本的盈餘變動已在 I006 事後看過，判定以驗證樣本為主）。"
             "CAR = 累積異常報酬（還原報酬 − β × 加權指數含息），括號為 t 值（同一決議日先平均）。研究結果，非投資建議。", "",
             f"公開資訊觀測站股利分派彙總表的年度列（含不配息、虧損公司），決議日 2019-01 ~ 2026-04、有去年淨利者：{len(events)} 筆。", ""]
    out = {}
    for name, r in res.items():
        e, l = r["early"], r["late"]
        lines += [f"## {name}", "",
                  f"事件 {r['n_all']} 筆，其中決議日 ≤ 3/31（主檢定）{len(e)} 筆、晚於 3/31 {len(l)} 筆；"
                  f"不配息 {int((~e['payer']).sum())} 筆；持有期因除息提前截止 {e['capped'].mean():.0%}；第 +1 日漲停 {e['up1'].mean():.1%}。", "",
                  "樣本選擇（股票池成員中沒有年度列者，多為季配／半年配）：" +
                  "、".join(f"{y} {p:.0%}（市值占 {w:.0%}）" for y, p, w in r["sel"]) + "。", "",
                  "| 分組（決議日 ≤ 3/31） | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|" + "---|" * len(WINDOWS)]
        for g in ("好消息（前 30%）", "中間", "壞消息（後 30%）"):
            x = e[e["grp"] == g]
            lines.append(f"| {g} | {len(x)} | " + " | ".join(fmt(es.date_clustered(x, w)) for w in WINDOWS) + " |")
        lines += ["", "好消息 − 壞消息（前 30% − 後 30%）：", "", "| 版本 | 期間 | " + " | ".join(WINDOWS) + " |", "|---|---|" + "---|" * len(WINDOWS)]
        sp = {}
        for seg, g in (("2019–2022", e[e["seg"] == "2019–2022"]), ("2023–2026/04", e[e["seg"] == "2023–2026/04"]), ("全期", e)):
            sp[seg] = spread(g, MAIN)
            lines.append(f"| 主定義 ES | {seg} | " + " | ".join(fmt(spread(g, w)) for w in WINDOWS) + " |")
        for lab, g, gc in (("只看有配息公司", assign_groups(e[e["payer"]].copy(), "es"), "grp"),
                           ("排除金融業", assign_groups(e[~e["fin"]].copy(), "es"), "grp"),
                           ("上市", assign_groups(e[e["market"] == "twse"].copy(), "es"), "grp"),
                           ("上櫃", assign_groups(e[e["market"] != "twse"].copy(), "es"), "grp"),
                           ("次要定義 ES_g（÷ |去年淨利|）", e, "grp_g"),
                           ("決議日晚於 3/31（單獨報告）", l, "grp")):
            lines.append(f"| {lab} | 全期 | " + " | ".join(fmt(spread(g, w, gc)) for w in WINDOWS) + " |")
        lines.append(f"| ES 對全年營收年增率的殘差排序 | 全期 | — | — | {fmt(r['resid'])} | — |")
        lines += ["", "控制 SUE、全年營收年增率、股利驚奇、殖利率、公告提前天數、市值、產業與年度後的 CAR[+2,+40] 迴歸（排名 −0.5～+0.5，依決議日分群）：", "",
                  "| 期間 | 事件數 | ES 係數（t） | SUE 係數（t） | ES 與 SUE 相關 | 與營收年增率相關 | 與股利驚奇相關 |", "|---|---|---|---|---|---|---|"]
        for seg, x in r["reg"].items():
            lines.append(f"| {seg} | {x['n']} | {x['b']:+.2%}（{x['t']:.1f}） | {x['b_sue']:+.2%}（{x['t_sue']:.1f}） | {x['c_sue']:+.2f} | {x['c_rev']:+.2f} | {x['c_ds']:+.2f} |")
        lines += ["", "策略（扣交易成本；台指期對沖；Sharpe 格式 2019–2022 / 2023–2026/04）：", "",
                  "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 全期 | 年化報酬 | 年化波動 | 最大回撤 | 有持股的日子 |", "|---|---|---|---|---|---|---|---|"]
        st = {}
        for sn, sim in r["sims"].items():
            s = hc.stats(sim["ret"])
            full = lp.sharpe(sim["ret"].dropna())
            st[sn] = s | {"full": full}
            lines.append(f"| {sn} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {full:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | {(sim['n'] > 0).mean():.0%} |")
        lines.append("")
        out[name] = {"sp": sp, "reg": r["reg"], "st": st}
        pd.DataFrame({k: v["ret"] for k, v in r["sims"].items()}).to_csv(
            ROOT / "reports" / "legs" / f"earnings_board_date_{'main' if name.startswith('前') else 'val'}.csv")

    v, w = out["前 500 名（主樣本）"], out["第 501–1000 名（驗證）"]
    c1 = v["sp"]["2019–2022"][0] > 0 and v["sp"]["2023–2026/04"][0] > 0 and v["sp"]["全期"][1] > 2
    c2 = v["reg"]["2019–2022"]["b"] > 0 and v["reg"]["2023–2026/04"]["b"] > 0 and v["reg"]["全期"]["t"] > 3
    c3a = w["sp"]["全期"][0] > 0 and w["sp"]["全期"][1] > 2
    c3b = w["reg"]["全期"]["b"] > 0 and w["reg"]["全期"]["t"] > 2
    lo_m = v["st"]["只做多好消息（台指期對沖）"]
    c4 = lo_m["sh_oos"] > 0 and lo_m["sh_is"] > 0 and w["st"]["只做多好消息（台指期對沖）"]["full"] > 0
    if c1 and c2 and c3a and c3b and c4:
        overall = "通過"
    elif c1 and c2 and c3a and c3b:
        overall = "partial（有預測力、可交易性不足）"
    elif c1 and c3a and not (c2 and c3b):
        overall = "未通過（年度盈餘變動只是營收驚奇等已知訊號的代理）"
    else:
        overall = "未通過"
    lines += ["## 判定", "",
              f"1. 主樣本前 30% − 後 30% 兩段 > 0、全期 t > 2：{'✓' if c1 else '✗'}",
              f"2. 主樣本控制後 ES 係數兩段 > 0、全期 t > 3：{'✓' if c2 else '✗'}",
              f"3. 驗證樣本組差 > 0 且 t > 2：{'✓' if c3a else '✗'}；含 SUE 控制的係數 > 0 且 t > 2：{'✓' if c3b else '✗'}",
              f"4. 只做多扣成本後主樣本兩段 Sharpe > 0、驗證全期 Sharpe > 0：{'✓' if c4 else '✗'}", "", f"**結論：{overall}**", "",
              "未做：ES_q4、ES_sd（需約 1,400 次財報請求）；2021 年後改用每日重大訊息財報日（與 I008 共用）。與 fv3 合成只在通過 (1)–(4) 後才做。"]
    (ROOT / "docs" / "earnings_board_date.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
