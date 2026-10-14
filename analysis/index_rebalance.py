"""指數成分股調整的事件研究：臺灣50（I001）、MSCI 臺灣（I002）、高股息 ETF（I003）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/index_rebalance.py tw50
    .venv/Scripts/python analysis/index_rebalance.py msci
    .venv/Scripts/python analysis/index_rebalance.py hidiv
輸出 docs/index_rebalance_{tw50,msci,hidiv}.md 與 reports/legs/index_rebalance_{...}.csv（策略每日報酬）。
點子卡：research/ideas/I001–I003。研究結果，非投資建議。

資料：
- 臺灣50：config/index_changes/tw50_changes.csv（維基百科「臺灣50指數」成分股變動表，2023-06 依新聞更正），
  以 tw50_base_2025-09.txt（2025-09-30 成分）前後推回各期成分，每期皆為 50 檔、刪除者必在成分內（一致性已檢查）。
  日期依規則：生效 = 審核月第三個星期五（遇休市取之前最後交易日）收盤；公布約在生效前 14–16 天
  （2025-09 為 9/3、2026-09 為 9/4），保守取「生效前 14 天之後的第一個交易日」收盤為可進場日；
  資料基準日 = 生效前 25 天（2023-06 為 5/22、2025-09 為 8/25）。
- MSCI、高股息 ETF：config/index_changes/msci_tw_changes.csv、hidiv_etf_changes.csv（由新聞與公告整理，含公布與生效日、來源網址）。

設計（看結果前固定）：
- 樣本：生效日在 2019-01 ~ 2026-04 的審核；報酬只用到 2026/04。
- 異常報酬：r − β × 加權指數含息報酬（β 250 日，只用前一日以前）；t 值以審核聚集（同一次審核的事件先平均）。
- 視窗（k_entry = 可進場日，公告後第一個可用收盤；k_eff = 生效日）：
  公告前 [k_entry−20, k_entry−1]、公告反應 [k_entry]（盤後公告者的隔日跳空，收盤進場拿不到）、
  公告到生效 [k_entry+1, k_eff]（可交易）、生效後 [k_eff+1, k_eff+20]（反轉）。
  MSCI 於台灣時間清晨公布，當天收盤即可進場，k_entry = 公布日。
- 臺灣50 另做事前預測：資料基準日收盤依「全額市值」排名上市股（股票池內），非成分股排名 ≤ 40 → 預測納入；
  成分股排名 > 60 → 預測刪除；再依排名補足或刪減到 50 檔。計算命中率（預測與實際相符的比例），
  並計算預測名單從基準日隔日收盤到生效日的 CAR。FTSE 另有流通量、流動性篩選，本預測未納入。
- 策略（台指期對沖，換手 × 單邊 0.29625%，放空扣借券費）：
  A 公告後做多納入、放空刪除，持有到生效日收盤；B 生效後反向（放空納入、做多刪除）持有 20 日；
  臺灣50 另有 P：預測名單從基準日隔日收盤做多納入／放空刪除到生效日。
- 判定（事前寫下）：公告到生效（或預測期）的納入減刪除 CAR 差，全期 t > 2，且 2019–2022 與 2023–2026/04 兩段同號。
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
import event_study as es  # noqa: E402
import hedge_construction as hc  # noqa: E402
import leg_probe as lp  # noqa: E402

CH = ROOT / "config" / "index_changes"
EFF_FROM, EFF_TO = pd.Timestamp("2019-01-01"), lp.HOLDOUT


def third_friday(year: int, month: int) -> pd.Timestamp:
    d = pd.Timestamp(year, month, 1)
    first_fri = d + pd.Timedelta(days=(4 - d.weekday()) % 7)
    return first_fri + pd.Timedelta(days=14)


def last_on_or_before(days: pd.DatetimeIndex, d: pd.Timestamp) -> int:
    return int(days.searchsorted(d, side="right")) - 1


def first_after(days: pd.DatetimeIndex, d: pd.Timestamp, strict: bool = True) -> int:
    return int(days.searchsorted(d, side="right" if strict else "left"))


def tw50_constituents(changes: pd.DataFrame, base: set, base_review: str = "2025-09") -> dict:
    """{審核: 審核前的成分}；以 base（base_review 之後的成分）前後推回。"""
    reviews = sorted(changes["review"].unique())
    before, s = {}, set(base)
    for r in reversed([x for x in reviews if x <= base_review]):
        g = changes[changes["review"] == r]
        s = (s - set(g.loc[g["action"] == "add", "stock_id"])) | set(g.loc[g["action"] == "del", "stock_id"])
        before[r] = set(s)
    s = set(base)
    for r in [x for x in reviews if x > base_review]:
        before[r] = set(s)
        g = changes[changes["review"] == r]
        s = (s - set(g.loc[g["action"] == "del", "stock_id"])) | set(g.loc[g["action"] == "add", "stock_id"])
    return before


def predict_tw50(cap: pd.Series, constituents: set, n: int = 50, add_rank: int = 40, del_rank: int = 60) -> tuple[set, set]:
    """cap：基準日各上市股全額市值。回傳（預測納入, 預測刪除）。"""
    rank = cap.dropna().rank(ascending=False, method="first")
    ids = {t.split(".")[0]: r for t, r in rank.items()}
    cons = {c for c in constituents if c in ids}
    adds = {s for s, r in ids.items() if r <= add_rank and s not in cons}
    dels = {s for s in cons if ids[s] > del_rank}
    keep = cons - dels
    while len(keep) + len(adds) < n:                      # 補足：排名最高的非成分股
        cand = sorted((r, s) for s, r in ids.items() if s not in keep and s not in adds)
        adds.add(cand[0][1])
    while len(keep) + len(adds) > n:                      # 刪減：排名最低的成分股
        worst = max(keep, key=lambda s: ids[s])
        keep.discard(worst)
        dels.add(worst)
    return adds, dels


def load_events(kind: str, days: pd.DatetimeIndex) -> pd.DataFrame:
    if kind == "tw50":
        ch = pd.read_csv(CH / "tw50_changes.csv", dtype={"stock_id": str})
        rows = []
        for r in sorted(ch["review"].unique()):
            y, m = map(int, r.split("-"))
            eff = third_friday(y, m)
            if not (EFF_FROM <= eff < EFF_TO):
                continue
            ke = last_on_or_before(days, eff)
            k_entry = first_after(days, eff - pd.Timedelta(days=14))
            k_cut = last_on_or_before(days, eff - pd.Timedelta(days=25))
            for _, x in ch[ch["review"] == r].iterrows():
                rows.append({"review": r, "action": x["action"], "stock_id": x["stock_id"], "k_entry": k_entry, "k_eff": ke, "k_cut": k_cut})
        return pd.DataFrame(rows)
    path = CH / ("msci_tw_changes.csv" if kind == "msci" else "hidiv_etf_changes.csv")
    ch = pd.read_csv(path, dtype={"stock_id": str, "etf": str})
    ch = ch[ch["action"].isin(["add", "del"])].copy()
    ch["announce_date"], ch["effective_date"] = pd.to_datetime(ch["announce_date"]), pd.to_datetime(ch["effective_date"])
    ch = ch[(ch["effective_date"] >= EFF_FROM) & (ch["effective_date"] < EFF_TO)]
    same_day = kind == "msci"                                  # MSCI 台灣時間清晨公布
    ch["k_entry"] = [first_after(days, d, strict=not same_day) for d in ch["announce_date"]]
    ch["k_eff"] = [last_on_or_before(days, d) for d in ch["effective_date"]]
    ch["stock_id"] = ch["stock_id"].str.zfill(4)
    keep = ["review", "action", "stock_id", "k_entry", "k_eff"] + (["etf"] if "etf" in ch.columns else [])
    return ch[keep].reset_index(drop=True)


def add_cars(ev: pd.DataFrame, ar: np.ndarray, col: dict, limit: int) -> pd.DataFrame:
    ev = ev[ev["stock_id"].map(lambda s: s + ".TW" in col)].copy()
    ev["ticker"] = ev["stock_id"] + ".TW"

    def rng(t, a, b):
        if a < 0 or b >= limit or b < a:
            return np.nan
        seg = ar[a:b + 1, col[t]]
        return float(np.nansum(seg)) if np.isfinite(seg).any() else np.nan
    ev["公告前 20 日"] = [rng(t, k - 20, k - 1) for t, k in zip(ev["ticker"], ev["k_entry"])]
    ev["公告反應"] = [rng(t, k, k) for t, k in zip(ev["ticker"], ev["k_entry"])]
    ev["公告到生效"] = [rng(t, a + 1, b) for t, a, b in zip(ev["ticker"], ev["k_entry"], ev["k_eff"])]
    ev["生效後 20 日"] = [rng(t, b + 1, b + 20) for t, b in zip(ev["ticker"], ev["k_eff"])]
    if "k_cut" in ev.columns:
        ev["基準日到公告"] = [rng(t, c + 2, a) for t, c, a in zip(ev["ticker"], ev["k_cut"], ev["k_entry"])]
    return ev


WINDOWS = ["公告前 20 日", "公告反應", "公告到生效", "生效後 20 日"]


def clustered(df: pd.DataFrame, colname: str) -> tuple[float, float, int]:
    g = df.dropna(subset=[colname]).groupby("review")[colname].mean()
    if len(g) < 4 or g.std(ddof=1) == 0:
        return (float(g.mean()) if len(g) else float("nan")), float("nan"), len(g)
    return float(g.mean()), float(g.mean() / g.std(ddof=1) * math.sqrt(len(g))), len(g)


def spread(df: pd.DataFrame, colname: str) -> tuple[float, float, int]:
    """每次審核的（納入平均 − 刪除平均），再對審核做 t 檢定；只有一邊時取該邊（刪除取負號）。"""
    vals = []
    for _, g in df.dropna(subset=[colname]).groupby("review"):
        a, d = g.loc[g["action"] == "add", colname], g.loc[g["action"] == "del", colname]
        if len(a) and len(d):
            vals.append(a.mean() - d.mean())
        elif len(a):
            vals.append(a.mean())
        elif len(d):
            vals.append(-d.mean())
    v = pd.Series(vals, dtype=float)
    if len(v) < 4 or v.std(ddof=1) == 0:
        return float(v.mean()) if len(v) else float("nan"), float("nan"), len(v)
    return float(v.mean()), float(v.mean() / v.std(ddof=1) * math.sqrt(len(v))), len(v)


def fmt(x):
    m, t, n = x
    return "—" if m != m else (f"{m:+.2%}（{t:.1f}）" if t == t else f"{m:+.2%}")


def holding(ev: pd.DataFrame, start_col: str, end_col: str, days, limit, reverse: bool = False) -> dict:
    """第 start 日收盤建立、持有到第 end 日收盤；納入做多、刪除放空（reverse 時相反）；兩邊各 100%（只有一邊時該邊 100%）。"""
    pos = {}
    for r in ev.itertuples():
        s, e = getattr(r, start_col), min(getattr(r, end_col), limit - 1)
        sign = (1 if r.action == "add" else -1) * (-1 if reverse else 1)
        for k in range(max(s, 0), e):
            pos.setdefault(days[k], []).append((r.ticker, sign))
    out = {}
    for d, lst in pos.items():
        longs = sorted({t for t, s in lst if s > 0})
        shorts = sorted({t for t, s in lst if s < 0} - set(longs))
        w = {t: 1 / len(longs) for t in longs} | {t: -1 / len(shorts) for t in shorts}
        out[d] = pd.Series(w, dtype=float)
    return out


def main(kind: str):
    c = lp.prepare(500)
    days = c.rets.index
    limit = int(days.searchsorted(lp.HOLDOUT))
    m = lp.market_tri(c.client).pct_change().reindex(days)
    ar = (c.rets - c.betas.fillna(1.0).mul(m, axis=0)).to_numpy()
    col = {t: j for j, t in enumerate(c.rets.columns)}
    ev = add_cars(load_events(kind, days), ar, col, limit)
    ev["seg"] = np.where(days[ev["k_eff"].to_numpy()] < lp.SPLIT, "2019–2022", "2023–2026/04")
    title = {"tw50": "臺灣50（0050）季度調整", "msci": "MSCI 臺灣指數季度調整", "hidiv": "高股息 ETF 換股"}[kind]
    lines = [f"# 指數成分股調整：{title}（自動產生）", "",
             "由 [analysis/index_rebalance.py](../analysis/index_rebalance.py) 產生；資料、設計與判定見程式開頭。"
             "CAR = 累積異常報酬（個股 − β × 加權指數含息），括號為 t 值（同一次審核先平均）。研究結果，非投資建議。", "",
             f"審核 {ev['review'].nunique()} 次；納入 {int((ev['action'] == 'add').sum())} 筆、刪除 {int((ev['action'] == 'del').sum())} 筆"
             "（只計入股票池市值前 500 名內、有價格資料者）。", ""]
    groups = [("全部", ev)] + [(s, ev[ev["seg"] == s]) for s in ("2019–2022", "2023–2026/04")]
    if "etf" in ev.columns:
        groups += [(f"ETF {e}", ev[ev["etf"] == e]) for e in sorted(ev["etf"].unique())]
    lines += ["## 1. 累積異常報酬", "", "| 分組 | 動作 | 事件數 | " + " | ".join(WINDOWS) + " |", "|---|---|---|" + "---|" * len(WINDOWS)]
    for gname, g in groups:
        for act, lab in (("add", "納入"), ("del", "刪除")):
            x = g[g["action"] == act]
            lines.append(f"| {gname} | {lab} | {len(x)} | " + " | ".join(fmt(clustered(x, w)) for w in WINDOWS) + " |")
        lines.append(f"| {gname} | 納入 − 刪除 | — | " + " | ".join(fmt(spread(g, w)) for w in WINDOWS) + " |")

    ev["k_entry_end"] = ev["k_eff"]
    ev["k_post_end"] = ev["k_eff"] + 20
    sims = {"A 公告後：做多納入／放空刪除，持有到生效": holding(ev, "k_entry", "k_entry_end", days, limit),
            "B 生效後反向：放空納入／做多刪除，持有 20 日": holding(ev, "k_eff", "k_post_end", days, limit, reverse=True)}

    test_col = "公告到生效"
    if kind == "tw50":
        ch = pd.read_csv(CH / "tw50_changes.csv", dtype={"stock_id": str})
        base = set((CH / "tw50_base_2025-09.txt").read_text(encoding="utf-8").split())
        before = tw50_constituents(ch, base)
        mem = pd.read_csv(ROOT / "config" / "universe_mcap_membership.csv", dtype={"stock_id": str})
        twse = set(mem.loc[mem["market_type"] == "twse", "stock_id"])
        cap = np.exp(c.logcap.shift(-1))                    # logcap[d] 為 d−1 收盤市值 → 對齊到當日
        pred_rows, hit = [], []
        for r, g in ev.groupby("review"):
            kc = int(g["k_cut"].iloc[0])
            cp = cap.iloc[kc]
            cp = cp[[t for t in cp.index if t.split(".")[0] in twse]]
            p_add, p_del = predict_tw50(cp, before[r])
            a_add = set(ch.loc[(ch["review"] == r) & (ch["action"] == "add"), "stock_id"])
            a_del = set(ch.loc[(ch["review"] == r) & (ch["action"] == "del"), "stock_id"])
            hit.append({"review": r, "pred": len(p_add) + len(p_del), "actual": len(a_add) + len(a_del),
                        "correct": len(p_add & a_add) + len(p_del & a_del)})
            for s, act in [(s, "add") for s in p_add] + [(s, "del") for s in p_del]:
                pred_rows.append({"review": r, "action": act, "stock_id": s, "k_cut": kc,
                                  "k_entry": int(g["k_entry"].iloc[0]), "k_eff": int(g["k_eff"].iloc[0])})
        H = pd.DataFrame(hit)
        pe = add_cars(pd.DataFrame(pred_rows), ar, col, limit)
        pe["seg"] = np.where(days[pe["k_eff"].to_numpy()] < lp.SPLIT, "2019–2022", "2023–2026/04")
        pe["基準日到生效"] = pe["基準日到公告"] + pe["公告到生效"]
        pe["k_start"] = pe["k_cut"] + 1
        lines += ["", "## 2. 事前預測（資料基準日的全額市值排名）", "",
                  f"命中率：預測 {H['pred'].sum()} 筆中 {H['correct'].sum()} 筆與實際相符（精確率 {H['correct'].sum() / max(H['pred'].sum(), 1):.0%}）；"
                  f"實際 {H['actual'].sum()} 筆中被預測到 {H['correct'].sum() / max(H['actual'].sum(), 1):.0%}（召回率）。", "",
                  "| 分組 | 動作 | 事件數 | 基準日到公告 | 公告到生效 | 基準日到生效 | 生效後 20 日 |", "|---|---|---|---|---|---|---|"]
        for gname, g in [("全部", pe)] + [(s, pe[pe["seg"] == s]) for s in ("2019–2022", "2023–2026/04")]:
            for act, lab in (("add", "預測納入"), ("del", "預測刪除")):
                x = g[g["action"] == act]
                lines.append(f"| {gname} | {lab} | {len(x)} | " + " | ".join(fmt(clustered(x, w)) for w in ("基準日到公告", "公告到生效", "基準日到生效", "生效後 20 日")) + " |")
            lines.append(f"| {gname} | 納入 − 刪除 | — | " + " | ".join(fmt(spread(g, w)) for w in ("基準日到公告", "公告到生效", "基準日到生效", "生效後 20 日")) + " |")
        sims["P 事前預測：基準日隔日收盤做多預測納入／放空預測刪除，持有到生效"] = holding(pe, "k_start", "k_eff", days, limit)
        pred_ev = pe

    fee = hc.lending_fees(c.client, c.tickers, days)
    cs = SimpleNamespace(rets=c.rets, betas=c.betas, tx=c.tx)
    lines += ["", "## 3. 策略（台指期對沖，扣交易成本與借券費；2019 ~ 2026/04）", "",
              "| 策略 | Sharpe 2019–2022 | 2023–2026/04 | 年化報酬 | 年化波動 | 最大回撤 | 有持股的日子 | 持有期間年化報酬（扣成本前） |", "|---|---|---|---|---|---|---|---|"]
    out = {}
    for name, wmap in sims.items():
        sim = es.simulate_daily(wmap, cs, fee)
        s = hc.stats(sim["ret"])
        gross = sim["ret"] + sim["turnover"] * lp.STOCK_COST
        active = sim["n"] > 0
        lines.append(f"| {name} | {s['sh_oos']:.2f} | {s['sh_is']:.2f} | {s['ann']:+.1%} | {s['vol']:.1%} | {s['mdd']:.1%} | "
                     f"{active.mean():.0%} | {gross[active].mean() * 252:+.1%} |")
        out[name] = sim["ret"]
    pd.DataFrame(out).to_csv(ROOT / "reports" / "legs" / f"index_rebalance_{kind}.csv")

    # ---- 判定 ----
    lines += ["", "## 4. 判定（納入 − 刪除的 CAR 差：全期 t > 2，且兩段同號）", "", "| 檢定 | 全期 | 2019–2022 | 2023–2026/04 | 判定 |", "|---|---|---|---|---|"]
    tests = [("公告到生效（實際名單）", ev, test_col), ("生效後 20 日（實際名單，負值 = 反轉）", ev, "生效後 20 日")]
    if kind == "tw50":
        tests.append(("基準日到生效（預測名單）", pred_ev, "基準日到生效"))
    for name, df, w in tests:
        a, b1, b2 = spread(df, w), spread(df[df["seg"] == "2019–2022"], w), spread(df[df["seg"] == "2023–2026/04"], w)
        ok = a[1] == a[1] and abs(a[1]) > 2 and np.sign(b1[0]) == np.sign(b2[0]) == np.sign(a[0])
        lines.append(f"| {name} | {fmt(a)} | {fmt(b1)} | {fmt(b2)} | {'通過' if ok else '未通過'} |")
    (ROOT / "docs" / f"index_rebalance_{kind}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
