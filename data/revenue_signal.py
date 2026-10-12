"""月營收驚奇（SUE）訊號：公告期限、進場日、SUE 計算（研究與前瞻規格 fv2 共用；fv2 凍結本模組的程式碼指紋）。

- 上市櫃公司須於次月 10 日前公告上月營收（遇假日順延）。進場日 = 當月「10 日或之後第一個交易日」（期限）的下一個交易日。
- FinMind TaiwanStockMonthRevenue 的 date 欄為營收月份的次月 1 日；create_time 為收錄時間（只有近期資料才有值）。
- SUE = (R_m − R_{m−12} − μ) / σ，μ、σ 為過去 24 個月 (R_k − R_{k−12}) 的平均與標準差（至少 12 個月）。
"""
from __future__ import annotations

import pandas as pd


def deadline_and_entry(month_days: list[pd.Timestamp]) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """某個月份的交易日（已排序）→（公告期限交易日, 進場日）；當月交易日不足時回傳 None。"""
    k = next((j for j, d in enumerate(month_days) if d.day >= 10), None)
    if k is None or k + 1 >= len(month_days):
        return None
    return month_days[k], month_days[k + 1]


def event_dates(trading_days: pd.DatetimeIndex) -> list[pd.Timestamp]:
    out = []
    s = pd.Series(trading_days, index=trading_days)
    for _, days in s.groupby([trading_days.year, trading_days.month]):
        de = deadline_and_entry(list(days))
        if de is not None:
            out.append(de[1])
    return out


def revenue_surprise(rev: pd.DataFrame, cutoff: pd.Timestamp | None = None) -> pd.DataFrame:
    """rev：FinMind 月營收；回傳 [avail_month（公告月份第一天）, sue, yoy_timely]。

    cutoff：前瞻使用時，只採用 create_time ≤ cutoff 的資料（create_time 缺值的歷史資料照常使用）。
    """
    r = rev.copy()
    if cutoff is not None and "create_time" in r.columns:
        ct = pd.to_datetime(r["create_time"], errors="coerce")
        r = r[ct.isna() | (ct <= cutoff)]
    r["ym"] = pd.to_datetime(dict(year=r["revenue_year"], month=r["revenue_month"], day=1))
    r = r.drop_duplicates("ym", keep="last").set_index("ym")["revenue"].astype(float).asfreq("MS")
    diff = r - r.shift(12)
    mu = diff.shift(1).rolling(24, min_periods=12).mean()
    sd = diff.shift(1).rolling(24, min_periods=12).std()
    sue = (diff - mu) / sd.where(sd > 0)
    yoy = r / r.shift(12) - 1
    out = pd.DataFrame({"sue": sue, "yoy_timely": yoy})
    out.index = out.index + pd.offsets.MonthBegin(1)  # 營收月份 m → 次月可用
    return out.rename_axis("avail_month").reset_index()
