"""I015 每月自結損益：解析重大訊息內文（點子卡 research/ideas/I015-monthly-self-reported-earnings-surprise.md）。

用法（於專案根目錄；先執行 analysis/fetch_self_earnings.py 取得主旨與內文）：
    .venv/Scripts/python analysis/self_earnings_parse.py
輸出 data_cache/events/self_earnings_values.csv（每則公告一列）、self_earnings_series.csv（每家公司每月一列，ESUE 用）
與 docs/self_earnings_parse_check.md（解析檢查）。

解析規則（看報酬前固定）：
- 只解析「按月公告」的公司：主旨不含季、半年、全年，且至少 24 個不同公告月份（48 家）。
- 排除代子公司公告、關係人交易、資金貸與，以及「更正」「誤植」「差異」（點子卡：更正以第一次公告為準）。
- 資料月份取主旨的「民國年／西元年 + 月」；主旨沒有月份時取公告日的前一個月。
- 從內文抽出四個數字：當月稅前（m_pre）、當月稅後（m_post；有「歸屬母公司業主」者取之）、累計稅前（c_pre）、累計稅後（c_post），
  單位統一為新台幣千元（億元 ×100,000、百萬元 ×1,000、萬元 ×10）。
  1. 表格列（「合併稅前淨利 351,132 2,225,746」）：第一個數字為當月、第二個為累計；少數公司另列去年同期，欄位順序在 COLS 個別設定。
  2. 公司別表格（金控、銀行：一列一家子公司）：取第一列（母公司／合併），欄位順序在 ENTITY 個別設定。
  3. 句子（「本月合併稅前淨利為17.14億元」「6月份稅後淨損158,119仟元」）：依關鍵字判斷當月或累計、稅前或稅後，淨損、損失取負號。
- 每家公司固定一個衡量（ESUE 用）：有當月稅後的月份 ≥ 80% 時用稅後，否則用稅前；當月數缺漏但有累計數時，用「本月累計 − 上月累計」補（1 月的累計即當月）。
- 檢查：同時有當月與累計的月份，核對「當月 ≈ 本月累計 − 上月累計」；結果列於 docs/self_earnings_parse_check.md。
研究用資料處理，非投資建議。
"""
import html
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "data_cache" / "events"
T05 = EV / "corp_raw" / "t05"
UNIT = {"億": 100000.0, "百萬": 1000.0, "佰萬": 1000.0, "萬": 10.0, "仟": 1.0, "千": 1.0}
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
NUM = r"\(?-?\$?\s?\d[\d,]*(?:\.\d+)?\)?%?"

# 表格列中，「當月」與「累計」不是第 1、2 個數字的公司（欄位位置從 0 起算）
# 「當月、去年同月、累計、去年累計」四欄的公司：四個數字時累計取第 3 欄
COLS4 = {"2015", "6581", "9802"}
# 公司別表格：第一列的欄位意義（None = 不使用）；可依年份分段 [(起始日, 欄位)]
FH = ["m_pre", "m_post", "c_pre", "c_post"]
ENTITY = {s: [("2000-01-01", FH)] for s in ("2880", "2881", "2882", "2884", "2885", "2886", "2891", "2892", "5880", "2889")}
ENTITY["2883"] = [("2000-01-01", [None, "m_post", None, None, "c_post"])]
ENTITY["2890"] = [("2000-01-01", ["m_post", "c_post"])]
ENTITY["2838"] = [("2000-01-01", FH)]
ENTITY["2476"] = [("2000-01-01", FH)]
ENTITY["5876"] = [("2000-01-01", FH)]
ENTITY["1702"] = [("2000-01-01", [None, None, "m_pre", "c_pre", "m_post", "c_post"])]
# 當月、累計分成上下兩塊、各一列純數字（稅前、稅後、歸屬母公司）
BLOCK = {"5871": ["pre", "post", "par"], "9941": ["pre", "post", "par"]}


def body(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t　\xa0]+", " ", t)
    a, b = t.find("說明"), t.find("以上資料均由")
    t = t[a if a >= 0 else 0: b if b > 0 else len(t)]
    t = re.sub(r"\d\.(事實發生日|公司名稱|與公司關係|相互持股比例|傳播媒體名稱|報導內容)[^\n]*\n", "", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def tonum(s: str) -> float:
    neg = s.strip().startswith("(") or "-" in s
    v = float(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


def doc_unit(t: str) -> float:
    m = re.search(r"單\s*位[^\n]{0,20}?(億|百萬|佰萬|萬|仟|千)", t) or re.search(r"[（(](億|百萬|佰萬|萬|仟|千)元?[)）]", t)
    return UNIT[m.group(1)] if m else np.nan


def data_month(subject: str, date: pd.Timestamp) -> pd.Period:
    s = subject.replace(" ", "")
    m = re.search(r"(20\d\d|\d{2,3})年(?:度)?(?:累計)?(\d{1,2})月", s)
    if m:
        y = int(m.group(1))
        return pd.Period(year=y if y > 1900 else y + 1911, month=int(m.group(2)), freq="M")
    m = re.search(r"(\d{2,3}|一[一二〇○零][一二三四五六七八九〇○零])年(?:度)?(十[一二]|[一二三四五六七八九十])月", s)
    if m and m.group(1).isdigit():
        return pd.Period(year=int(m.group(1)) + 1911, month=CN[m.group(2)], freq="M")
    return (date - pd.offsets.MonthBegin(1)).to_period("M") if date.day < 28 else date.to_period("M")


def kind(label: str):
    """表格列或句子片段的衡量：pre / par / post；EPS、營業利益等回傳 None。"""
    if re.search(r"EPS|每股|營業(利益|損益|淨利|毛利|收入)|毛利|綜合損益|提存前|其他|非控制|營收", label):
        return None
    if "稅前" in label:
        return "pre"
    if re.search(r"歸屬|母公司|業主", label):
        return "par"
    if re.search(r"稅後|本期淨利|淨利|純益", label):
        return "post"
    return None


TOK = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?%?\)?(?:%|(?:億|百萬|佰萬|萬|仟|千)?元)?|\$")


def split_row(line: str):
    """「標籤 數字 數字 …」：由右往左取純數字欄，回傳（標籤, [字串]）；不是這種格式回傳 None。"""
    parts = [x for x in re.split(r"[\s：:;；]+", line.strip()) if x]
    vals = []
    while parts and (TOK.fullmatch(parts[-1]) or parts[-1] == "-"):
        vals.insert(0, parts.pop())
    lab = " ".join(parts)
    vals = [x for x in vals if x not in ("$", "-")]
    if not vals or not re.search(r"[一-鿿]", lab):
        return None
    return lab, vals


def rows(t: str, sid: str, unit: float) -> dict:
    out = {}
    for line in t.split("\n"):
        sp = split_row(line)
        if sp is None:
            continue
        lab, toks = sp
        lab = re.sub(r"^\(?\d+\)[\.、]?|^\d+[\.、]", "", lab)
        k = kind(lab)
        if k is None:
            continue
        vals = []
        for x in toks:
            if "%" in x:
                continue
            u = re.search(r"(億|百萬|佰萬|萬|仟|千)元", x)
            vals.append(tonum(re.sub(r"(億|百萬|佰萬|萬|仟|千)?元", "", x)) * (UNIT[u.group(1)] if u else unit))
        if not vals:
            continue
        if re.search(r"累計|累積|1\s*[-~至]\s*\d+\s*月|本年", lab):
            out.setdefault(f"c_{k}", vals[0])
        elif re.search(r"本月|當月|單月|\d+\s*月", lab):
            out.setdefault(f"m_{k}", vals[0])
        else:
            out.setdefault(f"m_{k}", vals[0])
            ci = 2 if sid in COLS4 and len(vals) >= 4 else 1
            if len(vals) > ci:
                out.setdefault(f"c_{k}", vals[ci])
    return out


SENT = re.compile(r"(歸屬(?:於|予)?[^\d，,。；;]{0,10}?(?:業主|股東|公司)(?:之)?(?:稅後)?|稅前|稅後|本期)"
                  r"(淨利\(損\)|淨利|淨損|盈餘|損益|利益|純益|虧損|淨額)?([^\d\-，,。；;]{0,12}?)(-?\d[\d,]*(?:\.\d+)?)\s*"
                  r"(?:\((億|百萬|佰萬|萬|仟|千)元\)|(億|百萬|佰萬|萬|仟|千)?元)")
CUM = r"累計|累積|本年|1\s*[-~至]\s*\d+\s*月|1月至|至\d+月"


def sentences(t: str, unit: float) -> dict:
    """句子：本子句（逗號分隔）有期間字樣者依之；否則看整句（句號、分號分隔）是否有累計字樣；都沒有視為當月。"""
    out = {}
    flat = t.replace("\n", "")
    for m in SENT.finditer(flat):
        if re.search(r"EPS|每股|提存前|營業|綜合|其他|非控制", m.group(0) + flat[max(0, m.start() - 6): m.start()]) or (m.group(1) == "本期" and m.group(2) not in ("淨利", "淨損", "淨利(損)")):
            continue
        head = flat[: m.start()]
        sent = re.split(r"。", head)[-1]
        clause = re.split(r"[，,、；;]", sent)[-1]
        per = "c" if re.search(CUM, clause) else ("m" if re.search(r"本月|當月|單月|\d+\s*月", clause) else ("c" if re.search(CUM, sent) else "m"))
        k = "pre" if m.group(1) == "稅前" else ("par" if m.group(1).startswith("歸屬") else "post")
        u = m.group(5) or m.group(6)
        v = float(m.group(4).replace(",", "")) * (UNIT[u] if u else unit)
        if ((m.group(2) or "") in ("淨損", "虧損") or "損失" in m.group(3)) and v > 0:
            v = -v
        out.setdefault(f"{per}_{k}", v)
    return out


def entity(t: str, sid: str, date: pd.Timestamp, unit: float, jan: bool) -> dict:
    spec = [c for d, c in ENTITY[sid] if date >= pd.Timestamp(d)][-1]
    if jan:                                                         # 1 月常只有當月欄：只取當月欄位
        spec = [c if c and c.startswith("m_") else None for c in spec]
        spec = spec[: max(i for i, c in enumerate(spec) if c) + 1]
    for line in t.split("\n"):
        sp = split_row(line) or numeric_line(line)
        if sp is None or len(sp[1]) < len(spec) or re.search(r"單\s*位|EPS|每股|\(元\)", sp[0]) or any("%" in x for x in sp[1]):
            continue
        vals = [tonum(x) * unit for x in sp[1]]
        return {c: v for c, v in zip(spec, vals) if c}
    return {}


def numeric_line(line: str):
    parts = re.split(r"[\s：:]+", line.strip())
    if parts and all(TOK.fullmatch(x) for x in parts) and not all(x == "$" for x in parts):
        return "", [x for x in parts if x != "$"]
    return None


def block(t: str, sid: str, unit: float) -> dict:
    out, per = {}, None
    for line in t.split("\n"):
        if re.search(CUM, line) and re.search(r"損益|盈餘", line):
            per = "c"
        elif re.search(r"\d+\s*月", line) and re.search(r"損益|盈餘", line):
            per = "m"
        sp = numeric_line(line)
        if per and sp and len(sp[1]) >= 3 and f"{per}_pre" not in out:
            out.update({f"{per}_{k}": tonum(x) * unit for k, x in zip(BLOCK[sid], sp[1])})
    return out


def parse_doc(r) -> dict:
    p = T05 / f"{r.stock_id}_{r.date:%Y%m%d}_{r.seq}_{r.spoke_time}.html"
    t = body(p)
    t = re.sub(r"\$\s*", "", t)
    t = re.sub(r"\(\s+(?=\d)", "(", t)                               # 「( $ 7,359)」
    t = re.sub(r"USD\s*\(?-?[\d,]+\)?\s*TWD\s*", "", t)               # 慧洋：美元與新台幣並列，只取新台幣
    t = re.sub(r"([\d)])\s*\((億|百萬|佰萬|萬|仟|千)元\)", r"\1\2元", t)  # 「84,645(仟元)」
    t = re.sub(r"\(註[^)]*\)", "", t)                                  # 「0.94(註1,3)」
    t = re.sub(r"(-?\d+)億(\d{1,4})萬元", lambda m: f"{int(m.group(1)) * 10000 + int(m.group(2)) * (1 if int(m.group(1)) >= 0 else -1)}萬元", t)  # 「1億8135萬元」
    unit = doc_unit(t)
    u = 1.0 if np.isnan(unit) else unit
    out = {}
    if r.stock_id in BLOCK:
        out.update(block(t, r.stock_id, u))
    if r.stock_id in ENTITY:
        out.update(entity(t, r.stock_id, r.date, u, data_month(r.subject, r.date).month == 1))
    gen = rows(t, r.stock_id, u)
    for k, v in sentences(t, u).items():
        gen.setdefault(k, v)
    for per in ("m", "c"):                                          # 稅後優先取歸屬母公司業主
        if f"{per}_par" in gen:
            gen[f"{per}_post"] = gen.pop(f"{per}_par")
        if f"{per}_par" in out:
            out[f"{per}_post"] = out.pop(f"{per}_par")
    for k, v in gen.items():                                        # 公司別表格、分塊表格優先
        out.setdefault(k, v)
    return out


def monthly_firms(h: pd.DataFrame) -> pd.DataFrame:
    q = h["subject"].str.contains(r"季|Q[1-4]|半年|上半|全年")
    m = h[~q].copy()
    m["ym"] = m["date"].dt.to_period("M")
    n = m.groupby("stock_id")["ym"].nunique()
    return m[m["stock_id"].isin(n[n >= 24].index)]


def firm_month(v: pd.DataFrame) -> pd.DataFrame:
    """每家公司每個資料月份一列：取第一則有數字的公告（數字）與該月最早的公告時間（事件時點另在分析程式決定）。"""
    v = v.sort_values(["stock_id", "date", "spoke_time"])
    has = v[["m_pre", "m_post", "c_pre", "c_post"]].notna().any(axis=1)
    return v[has].drop_duplicates(["stock_id", "data_ym"]).reset_index(drop=True)


def check(v: pd.DataFrame) -> pd.DataFrame:
    """核對 當月 ≈ 本月累計 − 上月累計（同一年、非 1 月）；1 月核對 當月 ≈ 累計。"""
    f = firm_month(v)
    f["p"] = pd.PeriodIndex(f["data_ym"], freq="M")
    out = []
    for sid, g in f.groupby("stock_id"):
        g = g.set_index("p").sort_index()
        row = {"stock_id": sid, "name": g["name"].iloc[0], "months": len(g)}
        for k in ("pre", "post"):
            m, c = g[f"m_{k}"], g[f"c_{k}"]
            prev = c.reindex([p - 1 for p in g.index]).to_numpy()
            d = np.where(g.index.month == 1, c.to_numpy(), c.to_numpy() - prev)
            ok = ~np.isnan(m.to_numpy()) & ~np.isnan(d)
            bad = np.abs(m.to_numpy() - d) > 0.05 * np.maximum(np.abs(m.to_numpy()), np.abs(d)) + 1000
            row[f"{k}_cov"] = round(float(m.notna().mean()), 2)
            row[f"{k}_n_chk"] = int(ok.sum())
            row[f"{k}_bad"] = int((bad & ok).sum())
        out.append(row)
    return pd.DataFrame(out)


def series(v: pd.DataFrame) -> pd.DataFrame:
    """每家公司每月一列：[stock_id, name, data_ym, date, spoke_time, measure, x]。
    measure：當月稅後涵蓋率 ≥ 80% 用稅後（post），否則稅前（pre）；當月缺漏時用「本月累計 − 上月累計」補（1 月即累計）。"""
    f = firm_month(v)
    out = []
    for sid, g in f.groupby("stock_id"):
        k = "post" if g["m_post"].notna().mean() >= 0.8 else "pre"
        g = g.assign(p=pd.PeriodIndex(g["data_ym"], freq="M")).set_index("p").sort_index()
        c = g[f"c_{k}"]
        prev = c.reindex([p - 1 for p in g.index]).to_numpy()
        fill = np.where(g.index.month == 1, c.to_numpy(), c.to_numpy() - prev)
        x = g[f"m_{k}"].to_numpy()
        x = np.where(np.isnan(x), fill, x)
        out.append(pd.DataFrame({"stock_id": sid, "name": g["name"].to_numpy(), "data_ym": g["data_ym"].to_numpy(), "date": g["date"].to_numpy(),
                                 "spoke_time": g["spoke_time"].to_numpy(), "subject": g["subject"].to_numpy(), "measure": k, "x": x}))
    return pd.concat(out, ignore_index=True)


def write_check(chk: pd.DataFrame, s: pd.DataFrame) -> None:
    meas = s.drop_duplicates("stock_id").set_index("stock_id")["measure"].map({"post": "稅後", "pre": "稅前"})
    lines = ["# I015 自結損益公告解析檢查（自動產生）", "",
             "由 [analysis/self_earnings_parse.py](../analysis/self_earnings_parse.py) 產生；解析規則見程式開頭（看報酬前固定）。",
             "「核對」= 同時解析到當月數與累計數的月份，檢查 當月 ≈ 本月累計 − 上月累計（容許 5% 加 100 萬元）；"
             "不一致多半是公司在季報核閱後修正累計數（常見於 4、7、10 月），不一定是解析錯誤。研究用資料處理，非投資建議。", "",
             f"按月公告公司 {len(chk)} 家、公司月份 {int(chk['months'].sum()):,} 筆；"
             f"稅前核對 {int(chk['pre_n_chk'].sum()):,} 筆、不一致 {int(chk['pre_bad'].sum())} 筆；稅後核對 {int(chk['post_n_chk'].sum()):,} 筆、不一致 {int(chk['post_bad'].sum())} 筆。", "",
             "| 代號 | 名稱 | 月份數 | ESUE 用的衡量 | 當月稅前涵蓋率 | 稅前核對／不一致 | 當月稅後涵蓋率 | 稅後核對／不一致 |", "|---|---|---|---|---|---|---|---|"]
    for r in chk.itertuples():
        lines.append(f"| {r.stock_id} | {r.name} | {r.months} | {meas.get(r.stock_id, '—')} | {r.pre_cov:.0%} | {r.pre_n_chk}／{r.pre_bad} | {r.post_cov:.0%} | {r.post_n_chk}／{r.post_bad} |")
    (ROOT / "docs" / "self_earnings_parse_check.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    h = pd.read_csv(EV / "self_earnings_headlines.csv", dtype={"stock_id": str, "seq": str, "spoke_time": str}, parse_dates=["date"])
    m = monthly_firms(h)
    m = m[~m["subject"].str.contains("代子公司|子公司.*銀行公告|關係人|資金貸與|更正|誤植|差異")]          # 更正以第一次公告為準
    recs = []
    for r in m.itertuples():
        d = parse_doc(r)
        recs.append({"stock_id": r.stock_id, "name": r.name, "date": r.date, "spoke_time": r.spoke_time, "seq": r.seq, "subject": r.subject,
                     "data_ym": str(data_month(r.subject, r.date)), **d})
    v = pd.DataFrame(recs)
    jan = v["data_ym"].str.endswith("-01")
    for k in ("pre", "post"):                                       # 1 月的累計就是當月（部分公司 1 月第二欄是去年同月）
        v.loc[jan & v[f"m_{k}"].notna(), f"c_{k}"] = v.loc[jan & v[f"m_{k}"].notna(), f"m_{k}"]
    v.to_csv(EV / "self_earnings_values.csv", index=False)
    chk = check(v)
    s = series(v)
    s.to_csv(EV / "self_earnings_series.csv", index=False)
    write_check(chk, s)
    print(chk.to_string())
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
