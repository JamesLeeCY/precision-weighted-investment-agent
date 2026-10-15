"""I011／I012：主旨分類、轉讓方式分組、三分位。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))
import corp_event_study as ce  # noqa: E402
import insider_transfer_events as ie  # noqa: E402
import seo_cb_events as sc  # noqa: E402


def test_classify_headlines():
    assert sc.classify("公告本公司董事會決議發行國內第八次有擔保轉換公司債") == "CB"
    assert sc.classify("公告本公司董事會決議辦理現金增資發行新股") == "SEO"
    assert sc.classify("代重要子公司華新特殊鋼控股有限公司公告其董事會決議現金增資發行新股") == ""
    assert sc.classify("本公司董事會決議以現金增資辦理私募普通股方式籌措資金案") == ""
    assert sc.classify("公告本公司董事會決議調整107年現金增資發行新股之發行股數及發行價格") == ""
    assert sc.classify("公告本公司董事會決議除息基準日及國內第一次無擔保轉換公司債停止轉換期間") == ""
    assert sc.classify("補充公告本公司董事會決議發行國內第一次無擔保轉換公司債") == ""


def test_insider_groups():
    assert ie.group_of("一般交易") == "賣出" and ie.group_of("鉅額逐筆交易") == "賣出" and ie.group_of("盤後定價交易") == "賣出"
    assert ie.group_of("贈與") == "安慰劑" and ie.group_of("信託") == "安慰劑"
    assert ie.group_of("洽特定人") == "" and ie.group_of("轉讓私募股票") == ""


def test_terciles_respect_mask():
    x = np.arange(9, dtype=float)
    mask = np.ones(9, dtype=bool)
    t = ce.terciles(x, mask)
    assert list(t) == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    mask[0] = False
    assert ce.terciles(x, mask)[0] == -1
