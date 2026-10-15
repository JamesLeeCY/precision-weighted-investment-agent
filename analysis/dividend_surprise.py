"""I006 股利政策公告驚奇（點子卡 research/ideas/I006-dividend-policy-surprise-drift.md 的檢定計畫，看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/dividend_surprise.py
輸出 docs/dividend_surprise.md 與 reports/legs/dividend_surprise.csv。

資料：公開資訊觀測站「股利分派情形彙總表」（t05st09sub，107–115 年 × 上市／上櫃，共 18 次請求，快取在 data_cache/events/mops_dividend/）。
欄位含董事會決議日、股利所屬年度與期間、本期淨利、每股現金股利、現金股利總額。價格與除權息資料沿用快取（dividend_events.load_sample）。

設計（依點子卡；與卡片不同處標「調整」）：
- 事件：決議日 2019-01 ~ 2026-04 的「年度」現金股利決議（股利所屬期間為全年；季配／半年配公司不列入判定，只報告件數）；
  主樣本 = 決議當年市值前 500 名，驗證 = 第 501–1000 名；兩段 2019–2022 / 2023–2026/04。去年與今年都未配的不算事件。
  同一公司同一年度若有多筆（修正案），取最早的決議日。
- 事件日 t0 = 決議日（視為盤後公告），第 +1 日收盤進場；視窗 [−1, +1]（只報告）、[+2, +20]、[+2, +40]（主要）。
- 股利驚奇 DS_payout =（今年現金股利總額 − 去年配息率 × 今年本期淨利）÷ t0−1 日市值；去年配息率 = 去年現金股利總額 ÷ 去年本期淨利，
  限制在 [0, 1.5]；去年淨利 ≤ 0 時改用 DS_raw =（今年 − 去年現金股利總額）÷ 市值。
  （調整：卡片以每股 DPS、EPS 定義；這裡用總額與淨利，股數不變時等價，且全部來自同一張表。市值 = 前一日收盤 × 股數，
  股數 = 現金股利總額 ÷ 每股現金股利，今年未配時用去年。）初次配息、停配單獨報告。
- 分組：每年事件樣本內 DS_payout 前 30%（加配）、後 30%（減配）；主要比較前 30% − 後 30%。
- 異常報酬：還原報酬 − β × 加權指數含息報酬；t 值以決議日聚集（event_study.date_clustered 的寫法）。
- 持有期上限：除權息交易日公告日之前截止。（調整：FinMind 的除權息公告日只有少數股票有快取，改用除息日往前 15 個交易日
  作為上限——之前抽樣公告到除息的中位數為 11 個交易日、82% ≥ 11 日。）報告截止比例。
- 控制盈餘驚奇：合併迴歸 CAR[+2,+40] = DS 排名 + 盈餘變動排名 + SUE 排名 + 殖利率排名 + log 市值 + 產業與年度虛擬變數，標準誤依決議日分群。
  （調整：卡片的 ES 需要約 1,400 次季報請求；改用同表的本期淨利年變動 ÷ 市值作為年度盈餘驚奇，使用者已同意。）
  SUE = 決議日前最新可得的月營收 SUE（只做主樣本）。
- 可交易版本：第 +1 日收盤等權做多加配組、放空減配組（只放空前 60 日有借券成交者，扣借券費），持有到上限；另報只做多（台指期對沖）。
  （調整：未套用 borrow_capacity 的額度條件 D，可借性偏樂觀。）
- 通過（全部成立）：(1) 主樣本 CAR[+2,+40] 前 30% − 後 30% 兩段皆 > 0、全期 t > 2；(2) 控制後 DS 係數兩段皆 > 0、合併 t > 2；
  (3) 驗證樣本 (1) 的全期同號且 t > 2；(4) 多空或只做多扣成本後兩段 Sharpe 皆 > 0。
  (1)(3) 成立但 (2) 不成立 → 「股利驚奇只是盈餘驚奇的代理」＝未通過；(1)–(3) 成立但 (4) 不成立 → partial。
研究結果，非投資建議。
"""
import html
import math
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import dividend_events as de  # noqa: E402
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402
from data.fetch_financials import FinMindClient  # noqa: E402
from data.revenue_signal import revenue_surprise  # noqa: E402

CACHE = ROOT / "data_cache" / "events" / "mops_dividend"
YEARS = range(107, 116)
WINDOWS = {"[−1, +1] 公告反應": (-1, 1), "[+2, +20]": (2, 20), "[+2, +40]": (2, 40)}
EX_LEAD = 15


def num(s: str) -> float:
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def roc_date(s: str):
    m = re.match(r"^\s*(\d{2,3})/(\d{1,2})/(\d{1,2})\s*$", s or "")
    return pd.Timestamp(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))) if m else pd.NaT


def parse_table(text: str) -> list[dict]:
    """t05st09sub 的 HTML → 每列一筆；19 欄（108–109）與 21 欄（110 起）兩種格式。"""
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        c = [html.unescape(re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S | re.I)]
        if not c or not re.match(r"^\d{4}[A-Z]? - ", c[0]):
            continue
        sid = c[0].split(" - ")[0]
        if len(c) >= 21:
            cash_ps = num(c[11]) + num(c[12]) + num(c[13])
            total = num(c[14])
        else:
            cash_ps = num(c[11]) + num(c[12])
            total = num(c[13])
        period = c[2]
        fy = re.match(r"(\d{2,3})年", period)
        out.append({"stock_id": sid, "status": c[1], "period": period, "annual": "年度" in period and "半" not in period,
                    "fy": int(fy.group(1)) + 1911 if fy else np.nan, "board": roc_date(c[5]), "ni": num(c[8]),
                    "cash_ps": cash_ps, "cash_total": total})
    return out


def fetch_mops() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in YEARS:
        for typek in ("sii", "otc"):
            p = CACHE / f"t05st09_{y}_{typek}.html"
            if not p.exists():
                r = requests.get("https://mopsov.twse.com.tw/server-java/t05st09sub",
                                 params={"YEAR": str(y), "qryType": "1", "TYPEK": typek, "step": "1"},
                                 headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
                r.raise_for_status()
                tmp = p.with_name(p.name + ".tmp")
                tmp.write_text(r.content.decode("cp950", errors="replace"), encoding="utf-8")
                tmp.replace(p)
                time.sleep(3)
            rows += [x | {"query_year": y, "market": typek} for x in parse_table(p.read_text(encoding="utf-8"))]
    return pd.DataFrame(rows)


def build_events(mops: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    m = mops[mops["stock_id"].str.fullmatch(r"\d{4}")].copy()
    n_quarterly = int((~m["annual"] & m["board"].between("2019-01-01", "2026-04-30")).sum())
    a = m[m["annual"] & m["fy"].notna()].copy()
    a["fy"] = a["fy"].astype(int)
    first_board = a.dropna(subset=["board"]).sort_values("board").groupby(["stock_id", "fy"])["board"].first()
    amounts = a.sort_values("query_year").groupby(["stock_id", "fy"])[["ni", "cash_ps", "cash_total"]].last()
    ev = amounts.join(first_board).reset_index()
    prev = amounts.reset_index().assign(fy=lambda x: x["fy"] + 1).rename(columns={"ni": "ni_prev", "cash_ps": "ps_prev", "cash_total": "tot_prev"})
    ev = ev.merge(prev, on=["stock_id", "fy"], how="left")
    ev = ev.dropna(subset=["board", "tot_prev"])
    ev = ev[(ev["board"] >= "2019-01-01") & (ev["board"] < lp.HOLDOUT)]
    ev = ev[(ev["cash_total"] > 0) | (ev["tot_prev"] > 0)]
    ev["shares"] = np.where(ev["cash_ps"] > 0, ev["cash_total"] / ev["cash_ps"].replace(0, np.nan),
                            ev["tot_prev"] / ev["ps_prev"].replace(0, np.nan))
    ev["kind"] = np.select([(ev["tot_prev"] == 0) & (ev["cash_total"] > 0), (ev["tot_prev"] > 0) & (ev["cash_total"] == 0)],
                           ["初次配息", "停配"], "一般")
    return ev.reset_index(drop=True), n_quarterly


def latest_sue(client, sid: str, t0: pd.Timestamp) -> float:
    rev = client.get("TaiwanStockMonthRevenue", sid, "2017-01-01")
    if rev.empty:
        return np.nan
    s = revenue_surprise(rev).set_index("avail_month")["sue"]
    mo = t0.to_period("M").to_timestamp()
    avail = mo if t0.day > 10 else mo - pd.offsets.MonthBegin(1)   # 10 日（公告期限）後才用當月公告的營收
    s = s[s.index <= avail].dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def ols_cluster(y: np.ndarray, X: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ beta
    XtX_inv = np.linalg.pinv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in np.unique(groups):
        idx = groups == g
        s = X[idx].T @ e[idx]
        meat += np.outer(s, s)
    G, n, k = len(np.unique(groups)), len(y), X.shape[1]
    adj = G / max(G - 1, 1) * (n - 1) / max(n - k, 1)
    se = np.sqrt(np.diag(XtX_inv @ meat @ XtX_inv) * adj)
    return beta, se


def analyse_sample(client, events: pd.DataFrame, lo: int, hi: int, mkt_tri, tx, with_controls: bool):
    adj, close, member, divs = de.load_sample(client, lo, hi)
    rets = adj.pct_change()
    days = rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    m = mkt_tri.pct_change().reindex(days)
    betas = rets.rolling(250, min_periods=120).cov(m).div(m.rolling(250, min_periods=120).var(), axis=0).shift(1)
    ar = (rets - betas.fillna(1.0).mul(m, axis=0)).to_numpy()
    col = {t: j for j, t in enumerate(adj.columns)}
    mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
    sector = mem.drop_duplicates("stock_id", keep="last").set_index("stock_id")["sector"]

    ev = events.copy()
    ev["ticker"] = ev["stock_id"] + ".TW"
    ev = ev[ev["ticker"].isin(col)]
    ev["k0"] = [int(days.searchsorted(d, side="right")) - 1 for d in ev["board"]]
    ev = ev[(ev["k0"] >= 1) & (ev["k0"] < limit - 2)]
    ev["t0"] = days[ev["k0"].to_numpy()]
    ev = ev[[bool(member.at[t, tk]) for t, tk in zip(ev["t0"], ev["ticker"])]].copy()
    ev["px"] = [close.iat[k - 1, col[t]] for t, k in zip(ev["ticker"], ev["k0"])]
    ev["mcap"] = ev["px"] * ev["shares"]
    ev = ev[ev["mcap"] > 0]
    payout = (ev["tot_prev"] / ev["ni_prev"]).clip(0, 1.5)
    ds_payout = (ev["cash_total"] - payout * ev["ni"]) / ev["mcap"]
    ds_raw = (ev["cash_total"] - ev["tot_prev"]) / ev["mcap"]
    ev["ds"] = np.where(ev["ni_prev"] > 0, ds_payout, ds_raw)
    ev["ds_raw"] = ds_raw
    ev["es"] = (ev["ni"] - ev["ni_prev"]) / ev["mcap"]
    ev["yield"] = ev["cash_total"] / ev["mcap"]
    ev["seg"] = np.where(ev["t0"] < lp.SPLIT, "2019–2022", "2023–2026/04")
    ev["year"] = ev["t0"].dt.year

    # 持有期上限：該年度除息日往前 EX_LEAD 個交易日
    d = divs.copy()
    d["date"] = pd.to_datetime(d["date"])
    exd = d.groupby("ticker")["date"].apply(lambda s: sorted(s))
    caps, capped = [], []
    for t, k in zip(ev["ticker"], ev["k0"]):
        cap = k + 40
        for x in exd.get(t, []):
            kx = int(days.searchsorted(x))
            if kx > k + 1:
                if kx - EX_LEAD < cap:
                    cap = max(kx - EX_LEAD, k + 2)
                break
        caps.append(min(cap, limit - 1))
        capped.append(cap < k + 40)
    ev["k_end"] = caps
    ev["capped"] = capped
    for name, (a, b) in WINDOWS.items():
        if a < 0:
            ev[name] = [es.car(ar[:, col[t]], k, a, b, limit) for t, k in zip(ev["ticker"], ev["k0"])]
        else:
            ev[name] = [np.nansum(ar[k + a:min(k + b, e) + 1, col[t]]) if min(k + b, e) >= k + a else np.nan
                        for t, k, e in zip(ev["ticker"], ev["k0"], ev["k_end"])]
    ev["up1"] = [rets.iat[k + 1, col[t]] >= 0.095 for t, k in zip(ev["ticker"], ev["k0"])]
    ev["dn1"] = [rets.iat[k + 1, col[t]] <= -0.095 for t, k in zip(ev["ticker"], ev["k0"])]
    ev["grp"] = "中間"
    for y, g in ev.groupby("year"):
        r = g["ds"].rank(pct=True)
        ev.loc[g.index[r > 0.7], "grp"] = "加配（前 30%）"
        ev.loc[g.index[r <= 0.3], "grp"] = "減配（後 30%）"

    reg = None
    if with_controls:
        ev["sue"] = [latest_sue(client, s, t) for s, t in zip(ev["stock_id"], ev["t0"])]
        reg = {}
        for seg, g in [("2019–2022", ev[ev["seg"] == "2019–2022"]), ("2023–2026/04", ev[ev["seg"] == "2023–2026/04"]), ("全期", ev)]:
            g = g.dropna(subset=["[+2, +40]", "ds", "es", "sue", "yield", "mcap"]).copy()
            for v in ("ds", "es", "sue", "yield"):
                g[v + "_r"] = g.groupby("year")[v].rank(pct=True) - 0.5
            X = pd.concat([pd.Series(1.0, index=g.index, name="const"), g[["ds_r", "es_r", "sue_r", "yield_r"]],
                           np.log(g["mcap"]).rename("lmcap") - np.log(g["mcap"]).mean(),
                           pd.get_dummies(g["stock_id"].map(sector).fillna("NA"), drop_first=True, dtype=float),
                           pd.get_dummies(g["year"], drop_first=True, dtype=float, prefix="y")], axis=1)
            beta, se = ols_cluster(g["[+2, +40]"].to_numpy(float), X.to_numpy(float), g["t0"].astype(str).to_numpy())
            reg[seg] = {"b_ds": beta[1], "t_ds": beta[1] / se[1], "b_es": beta[2], "t_es": beta[2] / se[2], "n": len(g),
                        "corr_es": float(g["ds"].rank().corr(g["es"].rank())), "corr_sue": float(g["ds"].rank().corr(g["sue"].rank()))}

    # 策略
    fee = hc.lending_fees(client, list(adj.columns), days) if lo == 1 else None
    cs = SimpleNamespace(rets=rets, betas=betas, tx=tx)

    def book(g_long, g_short):
        pos = {}
        for df, sign in ((g_long, 1), (g_short, -1)):
            for r in df.itertuples():
                for k in range(r.k0 + 1, r.k_end):
                    if sign < 0 and fee is not None and not (fee.iat[k, col[r.ticker]] == fee.iat[k, col[r.ticker]]):
                        continue
                    pos.setdefault(days[k], []).append((r.ticker, sign))
        out = {}
        for dd, lst in pos.items():
            L = sorted({t for t, s in lst if s > 0})
            S = sorted({t for t, s in lst if s < 0} - set(L))
            out[dd] = pd.Series({t: 1 / len(L) for t in L} | {t: -1 / len(S) for t in S}, dtype=float)
        return out
    up, dn = ev[ev["grp"] == "加配（前 30%）"], ev[ev["grp"] == "減配（後 30%）"]
    sims = {"多空：做多加配、放空減配": es.simulate_daily(book(up, dn), cs, fee),
            "只做多加配（台指期對沖）": es.simulate_daily(book(up, up.iloc[0:0]), cs, None)}
    return ev, reg, sims


def spread(ev: pd.DataFrame, col: str) -> tuple[float, float, int]:
    vals = {}
    for t0, g in ev.dropna(subset=[col]).groupby("t0"):
        a, b = g.loc[g["grp"] == "加配（前 30%）", col], g.loc[g["grp"] == "減配（後 30%）", col]
        if len(a) or len(b):
            vals[t0] = (a.mean() if len(a) else 0.0) - (b.mean() if len(b) else 0.0)
    v = pd.Series(vals, dtype=float)
    if len(v) < 5:
        return float("nan"), float("nan"), len(v)
    return float(v.mean()), float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))), len(v)


def fmt(x):
    return "—" if x[0] != x[0] else f"{x[0]:+.2%}（{x[1]:.1f}）"


def main():
    import dotenv

    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    mops = fetch_mops()
    events, n_q = build_events(mops)
    mkt_tri, tx = lp.market_tri(client), lp.tx_continuous(client)
    res = {}
    for name, (lo, hi), ctrl in (("前 500 名（主樣本）", (1, 500), True), ("第 501–1000 名（驗證）", (501, 1000), False)):
        res[name] = analyse_sample(client, events, lo, hi, mkt_tri, tx, ctrl)
        print(name, "done", flush=True)

    lines = ["# I006 股利政策公告驚奇（自動產生）", "",
             "由 [analysis/dividend_surprise.py](../analysis/dividend_surprise.py) 產生；檢定計畫見點子卡 "
             "[I006](../research/ideas/I006-dividend-policy-surprise-drift.md)，與卡片不同處見程式開頭「調整」。"
             "CAR = 累積異常報酬（還原報酬 − β × 加權指數含息），括號為 t 值（同一決議日先平均）。研究結果，非投資建議。", "",
             f"公開資訊觀測站股利分派彙總表 107–115 年共 {len(mops)} 列；年度現金股利事件（決議日 2019-01 ~ 2026-04、去年或今年有配）{len(events)} 筆；"
             f"季配／半年配決議 {n_q} 筆（不列入判定）。", ""]
    verdict = {}
    for name, (ev, reg, sims) in res.items():
        lines += [f"## {name}", "",
                  f"事件 {len(ev)} 筆（初次配息 {int((ev['kind'] == '初次配息').sum())}、停配 {int((ev['kind'] == '停配').sum())}）；"
                  f"持有期因除息而提前截止的比例 {ev['capped'].mean():.0%}；第 +1 日漲停 {ev['up1'].mean():.1%}、跌停 {ev['dn1'].mean():.1%}。", "",
                  "| 分組 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|" + "---|" * len(WINDOWS)]
        for g in ("加配（前 30%）", "中間", "減配（後 30%）"):
            x = ev[ev["grp"] == g]
            lines.append(f"| {g} | {len(x)} | " + " | ".join(fmt(es.date_clustered(x, w)) for w in WINDOWS) + " |")
        for k in ("初次配息", "停配"):
            x = ev[ev["kind"] == k]
            lines.append(f"| {k} | {len(x)} | " + " | ".join(fmt(es.date_clustered(x, w)) if len(x) >= 5 else "—" for w in WINDOWS) + " |")
        lines += ["", "加配 − 減配（前 30% − 後 30%）：", "", "| 期間 | " + " | ".join(WINDOWS) + " |", "|---|" + "---|" * len(WINDOWS)]
        sp = {}
        for seg, g in (("2019–2022", ev[ev["seg"] == "2019–2022"]), ("2023–2026/04", ev[ev["seg"] == "2023–2026/04"]), ("全期", ev)):
            sp[seg] = spread(g, "[+2, +40]")
            lines.append(f"| {seg} | " + " | ".join(fmt(spread(g, w)) for w in WINDOWS) + " |")
        if reg:
            lines += ["", "控制盈餘變動、月營收 SUE、殖利率、市值、產業與年度後的 CAR[+2,+40] 迴歸（排名 −0.5 ~ +0.5，標準誤依決議日分群）：", "",
                      "| 期間 | 事件數 | 股利驚奇係數（t） | 盈餘變動係數（t） | 股利驚奇與盈餘變動相關 | 與 SUE 相關 |", "|---|---|---|---|---|---|"]
            for seg, r in reg.items():
                lines.append(f"| {seg} | {r['n']} | {r['b_ds']:+.2%}（{r['t_ds']:.1f}） | {r['b_es']:+.2%}（{r['t_es']:.1f}） | {r['corr_es']:+.2f} | {r['corr_sue']:+.2f} |")
        lines += ["", "策略（扣交易成本；台指期對沖；Sharpe 格式 2019–2022 / 2023–2026/04）：", "",
                  "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 有持股的日子 |", "|---|---|---|---|---|---|---|"]
        st = {}
        for sn, sim in sims.items():
            s = hc.stats(sim["ret"])
            st[sn] = s
            lines.append(f"| {sn} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | {(sim['n'] > 0).mean():.0%} |")
        lines.append("")
        verdict[name] = {"sp": sp, "reg": reg, "st": st}
        pd.DataFrame({k: v["ret"] for k, v in sims.items()}).to_csv(ROOT / "reports" / "legs" / f"dividend_surprise_{'main' if reg else 'val'}.csv")

    v, w = verdict["前 500 名（主樣本）"], verdict["第 501–1000 名（驗證）"]
    c1 = v["sp"]["2019–2022"][0] > 0 and v["sp"]["2023–2026/04"][0] > 0 and v["sp"]["全期"][1] > 2
    c2 = v["reg"]["2019–2022"]["b_ds"] > 0 and v["reg"]["2023–2026/04"]["b_ds"] > 0 and v["reg"]["全期"]["t_ds"] > 2
    c3 = w["sp"]["全期"][0] > 0 and w["sp"]["全期"][1] > 2
    c4 = any(s["sh_oos"] > 0 and s["sh_is"] > 0 for s in v["st"].values())
    if c1 and c2 and c3 and c4:
        overall = "通過"
    elif c1 and c3 and not c2:
        overall = "未通過（股利驚奇只是盈餘驚奇的代理）"
    elif c1 and c2 and c3:
        overall = "partial（有預測力、可交易性不足）"
    else:
        overall = "未通過"
    lines += ["## 判定", "",
              f"1. 主樣本 CAR[+2,+40] 加配 − 減配兩段 > 0、全期 t > 2：{'✓' if c1 else '✗'}",
              f"2. 控制盈餘變動、SUE、殖利率後股利驚奇係數兩段 > 0、全期 t > 2：{'✓' if c2 else '✗'}",
              f"3. 驗證樣本全期同號且 t > 2：{'✓' if c3 else '✗'}",
              f"4. 多空或只做多扣成本後兩段 Sharpe > 0：{'✓' if c4 else '✗'}", "", f"**結論：{overall}**"]
    (ROOT / "docs" / "dividend_surprise.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
