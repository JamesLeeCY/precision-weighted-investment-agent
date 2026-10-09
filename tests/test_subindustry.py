"""子產業分類：公司頁解析、產業鏈中層分類對照、主要子產業選擇規則。"""
from data.fetch_subindustry import parse_chain, parse_company, primary_entry

COMPANY = (
    '<h4>2308&nbsp;台達電 所屬產業鏈如下:</h4>'
    '<h4><span class="icon-blue">&#9658;</span>&nbsp;<a href="introduce.php?ic=8100">休閒娛樂</a>&nbsp;&gt;&nbsp;休閒車業</h4>'
    '<h4><span class="icon-blue">&#9658;</span>&nbsp;<a href="introduce.php?ic=J000">被動元件</a>&nbsp;&gt;&nbsp;電阻器</h4>'
    '<h4><span class="icon-blue">&#9658;</span>&nbsp;<a href="introduce.php?ic=F000">電腦及週邊設備</a>&nbsp;&gt;&nbsp;電源供應器</h4>'
    '<h4><span class="icon-blue">&#9658;</span>&nbsp;<a href="introduce.php?ic=F000">電腦及週邊設備</a>&nbsp;&gt;&nbsp;散熱模組</h4>'
    '</div>'
)

CHAIN = (
    '<div id="ic_link_D100" class="company-chain-panel">IC設計</div>'
    '<div id="ic_link_D300" class="company-chain-panel">IC/晶圓製造</div>'
    '<table id="sc_industry_D100"><tr><td id="sc_link_D110" class="subchain">&#9658;LED驅動IC&nbsp;(12家)&nbsp;'
    '電源管理IC&nbsp;(37家)本國上市公司(3家)</td></tr></table>'
)


def test_parse_company_keeps_declared_order():
    entries = parse_company(COMPANY)
    assert entries[0] == ("8100", "休閒娛樂", "休閒車業")
    assert len(entries) == 4


def test_parse_chain_maps_segments_to_groups():
    m = parse_chain(CHAIN)
    assert m["電源管理IC"] == "IC設計" and m["LED驅動IC"] == "IC設計"
    assert m["IC/晶圓製造"] == "IC/晶圓製造"  # 沒有細項的中層分類對應到自己


def test_primary_entry_prefers_main_business_chain():
    entries = parse_company(COMPANY)
    # 電子零組件業可選被動元件或電腦及週邊；電腦及週邊申報 2 筆 > 被動元件 1 筆；非電子的休閒娛樂不考慮
    assert primary_entry(entries, "電子零組件業") == ("F000", "電腦及週邊設備", "電源供應器")
    assert primary_entry(entries, "未知大產業") == ("F000", "電腦及週邊設備", "電源供應器")
