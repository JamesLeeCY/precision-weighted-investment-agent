"""I082 現金公開收購套利（點子卡 research/ideas/I082-cash-tender-offer-arbitrage.md，檢定計畫看結果前固定）。

用法（於專案根目錄）：
    .venv/Scripts/python analysis/tender_offer.py fetch      # 公開資訊觀測站主旨 keyWord=公開收購（2019–2026，上市／上櫃）＋內文
    .venv/Scripts/python analysis/tender_offer.py            # 檢定，輸出 docs/tender_offer.md
研究結果，非投資建議。
"""
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
sys.path.insert(0, str(ROOT))
import fetch_corp_events as fc  # noqa: E402

HEAD = ROOT / "data_cache" / "events" / "tender_headlines.csv"
T05 = fc.RAW / "t05"
T162 = fc.RAW / "t162"
URL162 = "https://mopsov.twse.com.tw/mops/web/ajax_t162sb01"
REF162 = "https://mopsov.twse.com.tw/mops/web/t162sb02"


def clean(t: str) -> str:
    import html
    t = re.sub(r"<script.*?</script>", "", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "|", t))
    return re.sub(r"\s+", " ", re.sub(r"\|[\s|]*\|", "|", t))


def official_list() -> pd.DataFrame:
    """公開收購統計彙總表（t162sb02），依收購開始年度。"""
    import html
    out = []
    for y in range(107, 116):
        t = fc.cached(f"t162/t162_{y}.html", lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t162sb02",
                      {"encodeURIComponent": 1, "step": 1, "firstin": "ture", "off": 1, "year": str(y)}, REF162))
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S | re.I):
            c = [re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", x))) for x in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)]
            if len(c) >= 6 and c[0].isdigit():
                out.append({"roc_year": y, "acquirer": c[1], "target_name": c[2], "target_id": c[3], "filed": fc.roc(c[5])})
    return pd.DataFrame(out)


def official_details(lst: pd.DataFrame) -> None:
    """每件收購的公告清單（表一、表二）與表一中每則「詳細資料」。"""
    for (co, y) in lst[["target_id", "roc_year"]].drop_duplicates().itertuples(index=False):
        t = fc.cached(f"t162/d_{co}_{y}.html", lambda: fc.post(URL162, {"encodeURIComponent": 1, "step": 1, "firstin": 1, "co_id": co,
                                                                        "year": str(y), "id": "", "key": "", "TYPEK": ""}, REF162))
        for m in re.finditer(r'COMPANY_ID2\.value="(\w+)"; document\.form2\.SEQ_NO\.value="(\d+)"; document\.form2\.DATE\.value="(\d+)"; '
                             r'document\.form2\.TYPE\.value="(\w+)"', t):
            c2, seq, d, ty = m.groups()
            fc.cached(f"t162/n_{c2}_{d}_{seq}_{ty}.html", lambda: fc.post(URL162, {"encodeURIComponent": 1, "step": 2, "off": 1, "firstin": 1,
                                                                                  "COMPANY_ID2": c2, "TYPE": ty, "DATE": d, "SEQ_NO": seq}, REF162))
        print(f"{co} {y}", flush=True)


def year_rows(kind: str, y: int) -> list[dict]:
    rows, page = [], 1
    while True:
        data = {"pagenum": str(page), "Stp": "4", "r1": "1", "KIND": kind, "CODE": "", "month1": "0", "begin_day": "1", "end_day": "31",
                "keyWord": "公開收購", "Condition2": "1", "keyWord2": "", "Orderby": "", "step": "2", "colorchg": "1", "co_id": "",
                "TYPEK": "", "off": "1", "firstin": "1", "i": "", "year": str(y), "month": "0", "spoke_date": "", "spoke_time": "",
                "seq_no": "", "b_date": "1", "e_date": "31", "PCount": "100"}
        t = fc.cached(f"t51_tender_{kind}_{y}_p{page}.html",
                      lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t51sb10", data, "https://mopsov.twse.com.tw/mops/web/t51sb10_q1"))
        if "資料筆數過多" in t:
            raise RuntimeError(f"公開收購 {kind} {y} 資料過多")
        got = fc.parse_headlines(t)
        rows += got
        pages = [int(x) for x in re.findall(r"pagenum\.value='(\d+)'", t)]
        if len(got) < 100 or not pages or page >= max(pages):
            return rows
        page += 1


def contents(h: pd.DataFrame) -> None:
    T05.mkdir(parents=True, exist_ok=True)
    for i, r in enumerate(h.itertuples()):
        d = pd.Timestamp(r.date).strftime("%Y%m%d")
        name = f"{r.stock_id}_{d}_{r.seq}_{r.spoke_time}.html"
        if (T05 / name).exists():
            continue
        data = {"encodeURIComponent": 1, "step": 2, "firstin": 1, "off": 1, "co_id": r.stock_id, "TYPEK": r.market or "sii",
                "spoke_date": d, "spoke_time": str(r.spoke_time), "seq_no": str(r.seq)}
        try:
            fc.cached(f"t05/{name}", lambda: fc.post("https://mopsov.twse.com.tw/mops/web/ajax_t05st01", data, "https://mopsov.twse.com.tw/mops/web/t05st01"))
        except RuntimeError as e:
            print(f"跳過 {name}：{e}", flush=True)
            time.sleep(60)
        if i % 50 == 0:
            print(f"內文 {i}/{len(h)}", flush=True)


def body(r) -> str:
    import html
    d = pd.Timestamp(r.date).strftime("%Y%m%d")
    p = T05 / f"{r.stock_id}_{d}_{r.seq}_{r.spoke_time}.html"
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\r\xa0　]+", " ", t)


def cmd_fetch():
    if not HEAD.exists():
        rows = []
        for kind in ("L", "O"):
            for y in range(2019, 2027):
                rows += year_rows(kind, y)
                print(f"{kind} {y}：累計 {len(rows)}", flush=True)
        h = pd.DataFrame(rows).drop_duplicates(["stock_id", "date", "seq", "subject"])
        h = h[h["stock_id"].astype(str).str.fullmatch(r"\d{4}")]
        h.to_csv(HEAD, index=False)
        print(f"主旨 {len(h)}", flush=True)
    h = pd.read_csv(HEAD, dtype={"stock_id": str, "spoke_time": str, "seq": str}, parse_dates=["date"])
    contents(h)
    print("DONE", flush=True)


# ---------------------------------------------------------------------------
# 檢定（依點子卡；補充以「補」標示）
# ---------------------------------------------------------------------------
START, END = "2019-01-01", "2026-05-01"
SPLIT = "2023-01-01"
BUY, SELL, TENDER = 0.001425, 0.0029625, 0.003 + 0.001425   # 買進手續費；賣出單邊（同 fv5）；應賣：證交稅 0.3% ＋ 手續費
RF = 0.015
# 全面收購：預定收購數量 = 全部已發行股份（或扣除收購人與其關係人已持有後的全部流通股），且應賣者全數收購。
# 逐件人工判定（依觀測站公開收購人公告第 11 點「預定公開收購之最高及最低數量」）。
FULL = {
    "1507": "已發行 410,820,000 股扣除日立集團持有 47,725,739 股後全部收購",
    "1787": "全部已發行股份 67,888,504 股",
    "3144": "扣除有沢已持有 52,633,181 股後剩餘全部股份",
    "4725": "扣除台泥及關係人持有 56,119,874 股後全部流通股",
    "5304": "扣除收購人持有及董監承諾不應賣股份後全部流通股",
    "5820": "全部已發行股份 3,772,452,281 股（100%）",
    "6553": "全部已發行股份 72,171,000 股（100%）",
    "8497": "扣除庫藏股與第一大股東集保股份後全部流通股",
    "4987": "全部已發行股份 31,878,000 股（100%）",
    "6470": "全部已發行股份 37,694,100 股（100%）",
    "5277": "扣除收購人及關係人持有後全部流通股（目標為興櫃，不列入主樣本）",
    "6764": "扣除收購人持有與庫藏股後全部流通股（目標為興櫃，不列入主樣本）",
}
# 收購當時為興櫃（價格無漲跌幅限制、FinMind TaiwanStockInfo 為 emerging）
EMERGING = {"5277", "6764", "6599", "6518", "6938", "7566", "6897", "7555"}
TWO_STEP = {"4180": "安成藥：部分收購 43.57% 後以股份轉換取得其餘股份（列在部分收購）"}


def roc_d(y, m, d):
    y = int(y)
    try:
        return pd.Timestamp(y + 1911 if y < 1000 else y, int(m), int(d))
    except ValueError:
        print(f"  日期無法解析：{y}/{m}/{d}", flush=True)
        return pd.NaT


def notices() -> pd.DataFrame:
    recs = []
    for p in sorted(T162.glob("n_*.html")):
        _, co, d, seq, ty = p.stem.split("_")
        s = re.sub(r"\s+", "", clean(p.read_text(encoding="utf-8")))
        acq = re.search(r"公開收購人名稱：\|([^|]*)\|", s)
        recs.append(dict(co=co, date=pd.Timestamp(d), seq=seq, ty=int(ty), acq=acq.group(1) if acq else "", body=s[s.find("內容："):]))
    return pd.DataFrame(recs)


def num(x):
    return float(x.replace(",", "")) if x else float("nan")


def deal_table(N: pd.DataFrame) -> pd.DataFrame:
    h = pd.read_csv(HEAD, dtype={"stock_id": str, "spoke_time": str, "seq": str}, parse_dates=["date"])
    lst = official_list()
    short = dict(zip(lst["target_id"], lst["target_name"]))
    t1 = N[(N.ty == 1) & (N.date >= START) & (N.date < END)].sort_values("date")
    rows = []
    for r in t1.itertuples():
        b = r.body
        price = re.search(r"預定收購之有價證券價格[:：]?[^0-9]{0,12}([\d.]+)元", b)
        qty = re.search(r"被收購之有價證券數量[:：]?([\d,]+)股", b) or re.search(r"預定收購(?:最高)?(?:股)?數量(?:為|總計)?([\d,]{6,})股", b)
        total = re.search(r"已發行(?:普通股)?(?:股份)?(?:總數|總額)?(?:[（(][^）)]{0,12}[）)])?(?:為)?([\d,]{6,})股", b)
        key = (r.co, price.group(1) if price else "", qty.group(1) if qty else "")
        if any(x["key"] == key and (r.date - x["filed"]).days <= 30 for x in rows):
            continue                                           # 共同收購人分別申報、或同一收購案重複公告
        rows.append(dict(key=key, target=r.co, name=short.get(r.co, ""), acq=r.acq, filed=r.date,
                         offer0=num(price.group(1)) if price else float("nan"), qty=num(qty.group(1)) if qty else float("nan"),
                         total=num(total.group(1)) if total else float("nan")))
    out = []
    for d in rows:
        co, filed = d["target"], d["filed"]
        ak = re.sub(r"(股份)?有限公司.*|等.*|、.*|/.*|\(.*", "", d["acq"])[:4]
        later = N[(N.co == co) & (N.date >= filed) & (N.date <= filed + pd.Timedelta(days=250))].sort_values("date")
        mine = later[later.body.str.contains(re.escape(ak)) | later.acq.str.contains(re.escape(ak))]
        offer = d["offer0"]
        for b in mine[mine.ty == 5].body:
            m = re.findall(r"提高為每股(?:現金)?新?[臺台]?幣?([\d.]+)元", b)
            if m:
                offer = float(m[-1])
        r9 = mine[mine.ty == 9]
        end = pay = pd.NaT
        tendered = accepted = float("nan")
        if len(r9):
            b = r9.iloc[0].body
            m = re.search(r"收購期間屆滿之日期[:：]?(?:民國)?(?:[（(](?:以)?下同[)）])?(\d{2,4})[年/](\d{1,2})[月/](\d{1,2})", b)
            end = roc_d(*m.groups()) if m else r9.iloc[0].date
            m = re.search(r"(?:應賣有價證券之數量|應賣(?:股份|股數)總數為?|參與應賣之?[^0-9。]{0,40}?(?:股份|股數|數量|總數)為)[:：]?([\d,]+)股", b)
            tendered = num(m.group(1)) if m else float("nan")
            m = re.findall(r"實際成交(?:之)?數量(?:[:：]|為)([\d,]+)股", b)
            accepted = num(m[-1]) if m else float("nan")
            if not m and re.search(r"實際成交(?:之)?數量[:：]?(?:[（(]?\d[)）])?應賣有價證券之數量", b) is None:
                m2 = re.search(r"實際成交(?:之)?數量[:：為]?(?:[^0-9]{0,20}?)([\d,]+)股", b)
                accepted = num(m2.group(1)) if m2 else float("nan")
            m = re.search(r"(?:支付|撥付|交割)[^。]{0,80}?即(?:民國)?(\d{2,4})年(\d{1,2})月(\d{1,2})日", b) or \
                re.search(r"即(?:民國)?(\d{2,4})年(\d{1,2})月(\d{1,2})日", b)
            pay = roc_d(*m.groups()) if m else pd.NaT
        nm = d["name"]
        # 公告日：公告內容的 DATE 是事實發生日，不一定已公開；改用「重大訊息主旨最早一則」與「統計彙總表申報日期」較早者
        ls = lst[(lst["target_id"] == co) & (lst["filed"] >= filed - pd.Timedelta(days=5))]["filed"]
        listed_on = ls.min() if len(ls) else filed
        hh = h[((h["stock_id"] == co) | h["subject"].str.contains(nm or "@@", regex=False))
               & (h["date"] >= filed - pd.Timedelta(days=20)) & (h["date"] <= listed_on)]
        ann = min([listed_on] + list(hh["date"]))
        out.append(dict(target=co, name=nm, acq=d["acq"][:16], ann=ann, filed=filed, offer0=d["offer0"], offer=offer, qty=d["qty"], total=d["total"],
                        end=end, pay=pay, tendered=tendered, accepted=accepted, full=co in FULL, listed=co not in EMERGING))
    D = pd.DataFrame(out)
    D["success"] = D["accepted"] > 0
    return D


def prices(client, sid: str) -> pd.DataFrame:
    p = client.get("TaiwanStockPrice", sid, "2018-10-01", "2026-10-31")
    if p.empty:
        return p
    p = p[p["close"] > 0].copy()
    p["date"] = pd.to_datetime(p["date"])
    return p.set_index("date")


def deal_returns(D: pd.DataFrame, client, cal: pd.DatetimeIndex) -> pd.DataFrame:
    """每件：進場 = 公告日後第一個交易日收盤（漲停則順延；進場價 ≥ 收購價不進場）；成功 → 交付日領到收購價扣稅費；
    失敗 → 屆滿日次一交易日收盤賣出。部分收購（只報告）：以實際成交 ÷ 應賣比例成交，其餘在交付日次一交易日收盤賣出。"""
    res = []
    for r in D.itertuples(index=False):
        rec = r._asdict()
        p = prices(client, r.target)
        if p.empty or pd.isna(r.end):
            res.append(rec | {"status": "無價格或無結果"})
            continue
        px, money = p["close"].astype(float), p["Trading_money"].astype(float)
        after = px[px.index > r.ann]
        prev = px[px.index <= r.ann]
        last = prev.iloc[-1] if len(prev) else float("nan")
        entry_d = None
        for d in after.index:
            pc = px[px.index < d]
            if len(pc) == 0 or after.loc[d] / pc.iloc[-1] - 1 < 0.095:
                entry_d = d
                break
        if entry_d is None or entry_d >= r.end:
            res.append(rec | {"status": "收購期間內無法進場"})
            continue
        e = after.loc[entry_d]
        rec |= {"entry_d": entry_d, "entry": e, "pre_close": last, "prem_pre": r.offer / last - 1, "spread": r.offer / e - 1,
                "cap": 0.10 * money.get(entry_d, float("nan")), "limit_days": int((after.index < entry_d).sum())}
        if e >= r.offer:
            res.append(rec | {"status": "進場價≥收購價（不進場）", "ret": 0.0, "days": 0})
            continue
        cost = e * (1 + BUY)

        def outcome(frac):
            if not r.success:
                nx = px.index[px.index > r.end]
                d = nx[0] if len(nx) else px.index[-1]
                return d, px.loc[d] * (1 - SELL) / cost - 1
            ok = pd.notna(r.pay) and r.end <= r.pay <= r.end + pd.Timedelta(days=30)   # 解析錯誤時改用屆滿後第 5 個交易日
            pay = r.pay if ok else cal[cal > r.end][4]
            rest_d = px.index[px.index > pay]
            if frac < 1 and len(rest_d):
                d, rest = rest_d[0], px.loc[rest_d[0]]
            else:
                d, rest = pay, (px.loc[:pay].iloc[-1] if frac < 1 else 0.0)
            return d, (frac * r.offer * (1 - TENDER) + (1 - frac) * rest * (1 - SELL)) / cost - 1

        # 計畫：部分收購以預定收購比例（預定收購數量 ÷ 已發行股數）當作成交比例；另報告實際成交 ÷ 應賣比例
        plan = 1.0 if r.full else (min(1.0, r.qty / r.total) if r.qty > 0 and r.total > 0 else float("nan"))
        actual = 1.0 if r.full else (min(1.0, r.accepted / r.tendered) if r.tendered > 0 else
                                     (1.0 if r.accepted < 0.999 * r.qty else float("nan")))
        frac = plan if pd.notna(plan) else actual
        if not r.success:
            frac = actual = 0.0
        exit_d, ret = outcome(frac)
        ret_act = outcome(actual)[1] if pd.notna(actual) else float("nan")
        days = (exit_d - entry_d).days
        res.append(rec | {"status": "成功" if r.success else "失敗", "frac": frac, "frac_act": actual, "exit_d": exit_d, "days": days, "ret": ret,
                          "ret_act": ret_act, "ann_ret": ret * 365 / max(days, 1), "excess": ret - RF * days / 365})
    return pd.DataFrame(res)


def daily_portfolio(R: pd.DataFrame, client, cal: pd.DatetimeIndex) -> pd.Series:
    """日曆時間組合（只描述）：持有期間每日以收盤價計值（全面收購在屆滿後以收購價計值），最後一天跳到實際出場價值；無持有日為無風險利率。"""
    paths = {}
    for r in R[R["status"].isin(["成功", "失敗"])].itertuples():
        px = prices(client, r.target)["close"].astype(float)
        days = cal[(cal >= r.entry_d) & (cal <= r.exit_d)]
        v = px.reindex(days).ffill()
        if r.status == "成功" and r.frac == 1.0:
            v[v.index > r.end] = r.offer * (1 - TENDER)
        v.iloc[0] = r.entry * (1 + BUY)
        v.iloc[-1] = (1 + r.ret) * r.entry * (1 + BUY)
        paths[f"{r.target}_{r.ann.date()}"] = v.pct_change().iloc[1:]
    port = pd.DataFrame(paths).reindex(cal).mean(axis=1)
    return port.fillna(RF / 252) - RF / 252


def cmd_test():
    import dotenv
    from data.fetch_financials import FinMindClient
    from sue_attention import nw_t
    dotenv.load_dotenv(ROOT / ".env")
    client = FinMindClient()
    t = client.get("TaiwanStockTotalReturnIndex", "TAIEX", "2018-10-01", "2026-10-31")
    tri = pd.Series(t["price"].astype(float).to_numpy(), index=pd.to_datetime(t["date"])).sort_index()
    cal = tri.index
    D = deal_table(notices())
    R = deal_returns(D, client, cal)
    R["mkt"] = [tri.asof(r.exit_d) / tri.asof(r.entry_d) - 1 if isinstance(r.exit_d, pd.Timestamp) and isinstance(r.entry_d, pd.Timestamp)
                and pd.notna(r.exit_d) and pd.notna(r.entry_d) else float("nan") for r in R.itertuples()]
    R.to_csv(ROOT / "data_cache" / "events" / "tender_deals.csv", index=False)
    main = R[R["full"] & R["listed"]]
    L = []
    w = L.append
    w("# I082 現金公開收購套利：逐件結果（analysis/tender_offer.py 產生）\n")
    w("研究結果，非投資建議。資料：公開資訊觀測站「公開收購統計彙總表」（t162sb02）與每件收購的公告內容；價格 FinMind。\n")
    w(f"- 2019-01 ~ 2026-04 申報的公開收購 {len(D)} 件（同一案的共同收購人或重複申報合併為一件）；"
      f"全面收購 {int(D['full'].sum())} 件，其中目標為上市櫃 {len(main)} 件。")
    w(f"- 主判定前提：全面現金收購 ≥ 40 件。實際 {len(main)} 件 < 40 → **依計畫停止，只報告描述統計，不做 Holm 檢定。**\n")

    def fmt(v, k="{:+.1%}"):
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else k.format(v)

    def dt(v):
        return "" if not isinstance(v, pd.Timestamp) or pd.isna(v) else v.strftime("%Y-%m-%d")

    def table(X, title):
        w(f"## {title}\n")
        w("| 代號 | 目標 | 收購人 | 公告日 | 收購價 | 公告前收盤 | 溢價 | 進場日 | 進場價 | 進場價差 | 屆滿 | 出場 | 天數 | 結果 | 成交比例（計畫／實際） | 報酬（扣成本） | 報酬（實際比例） | 年化 | 超額（扣 1.5%） | 同期大盤 | 可投入（萬元） |")
        w("|" + "---|" * 21)
        for r in X.sort_values("ann").itertuples():
            w(f"| {r.target} | {r.name} | {r.acq} | {dt(r.ann)} | {r.offer:g} | {fmt(r.pre_close, '{:g}')} | {fmt(r.prem_pre)} | {dt(r.entry_d)} | "
              f"{fmt(r.entry, '{:g}')} | {fmt(r.spread)} | {dt(r.end)} | {dt(r.exit_d)} | {fmt(r.days, '{:.0f}')} | {r.status} | {fmt(r.frac, '{:.0%}')}／{fmt(r.frac_act, '{:.0%}')} | "
              f"{fmt(r.ret)} | {fmt(r.ret_act)} | {fmt(r.ann_ret)} | {fmt(r.excess)} | {fmt(r.mkt)} | {fmt(r.cap / 1e4, '{:,.0f}')} |")
        w("")

    def summary(X, label):
        X = X[X["status"].isin(["成功", "失敗", "進場價≥收購價（不進場）"])]
        if X.empty:
            return
        a = X[X["days"] > 0]
        w(f"- {label}：{len(X)} 件（進場 {len(a)}；成功 {(X['status'] == '成功').sum()}、失敗 {(X['status'] == '失敗').sum()}、"
          f"不進場 {X['status'].str.startswith('進場價').sum()}）。每件報酬平均 {X['ret'].mean():+.2%}、中位數 {X['ret'].median():+.2%}；"
          f"平均持有 {a['days'].mean():.0f} 天；總報酬 ÷ 總持有天數年化 {a['ret'].sum() / a['days'].sum() * 365:+.1%}；"
          f"扣 1.5% 後每件平均超額 {a['excess'].mean():+.2%}；同期大盤平均 {a['mkt'].mean():+.2%}；最差一件 {X['ret'].min():+.1%}"
          f"（以實際成交比例計：每件平均 {X['ret_act'].fillna(X['ret']).mean():+.2%}）。")

    table(main, "主樣本：全面現金收購、目標上市櫃（計畫中的主判定樣本）")
    w("### 摘要\n")
    summary(main, "全期")
    summary(main[main["ann"] < SPLIT], "2019–2022")
    summary(main[main["ann"] >= SPLIT], "2023–2026/04")
    ex = daily_portfolio(main, client, cal)
    ex = ex[(ex.index >= main["entry_d"].min()) & (ex.index <= main["exit_d"].max())]
    w(f"- 日曆時間組合（只描述）：{ex.index[0].date()} ~ {ex.index[-1].date()} 共 {len(ex)} 個交易日，有持股 {int((ex != 0).sum())} 日；"
      f"年化超額 {ex.mean() * 252:+.2%}，Newey-West t（落後 5）{nw_t(ex, 5):.2f}。\n")
    part = R[~R["full"] & R["listed"]]
    table(part, "只報告：部分收購（以實際成交 ÷ 應賣比例成交，其餘在交付日次一交易日收盤賣出）")
    w("### 摘要\n")
    summary(part, "部分收購全期")
    summary(part[part["ann"] < SPLIT], "部分收購 2019–2022")
    summary(part[part["ann"] >= SPLIT], "部分收購 2023–2026/04")
    w("")
    table(R[~R["listed"]], "只報告：目標為興櫃")
    w("## 全面收購判定\n")
    for k, v in FULL.items():
        w(f"- {k}：{v}")
    w(f"- 兩段式：{TWO_STEP['4180']}")
    (ROOT / "docs" / "tender_offer.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        cmd_fetch()
    elif sys.argv[1:] == ["official"]:
        official_details(official_list())
        print("DONE", flush=True)
    else:
        cmd_test()
