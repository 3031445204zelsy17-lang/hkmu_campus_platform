"""GE 目录富化数据完整性(官方 GE_catalog_3cru.pdf,2026-08-07 版)。

纯函数、无 DB。锁三件事:
  1. 每门池内课都有完整富化字段(credits/level/moi/school_name/description)
  2. 课码字母交叉校验(官方规则:第5字母=学院、第6字母=授课语言、千位=级别)
     ——自动暴露抓取错;官方文件内部已知出入以显式例外锁死(人工核对过原文)
  3. 学院表与 PDF verbatim 双向锁定(含 A&SS 2026-09-01 更名)
另锁介绍段无页噪声残留(Back to index/Page N/标签行),防解析退化。
"""
import re

from backend.app.data.ge_courses import GE_COURSES, ge_course_by_id
from backend.app.data.ge_catalog_enrichment import (
    CATALOG_UPDATED, GE_ENRICH, GE_SCHOOL_NAMES,
)

SCHOOL_OF_LETTER = {"A": "A&SS", "B": "B&A", "E": "E&L", "N": "N&HS", "S": "S&T"}
MOI_OF_LETTER = {"E": "english", "C": "chinese", "B": "bilingual"}
CODE_RE = re.compile(r"^GEN (\d)(\d{3})([A-Z])([ECB])([FWD])$")
EXCLUDED_RE = re.compile(r"^[A-Z]{3,4} \d{4}[A-Z]{3}$")

# 官方文件内部已知出入(目录打印 vs 课码字母;人工对照过 PDF 原文,展示以目录为准)
KNOWN_SCHOOL_CONFLICTS = {
    "GEN 1510NCF": "科技學院",            # 字母 N,目录印 S&T
    "GEN 2501NEF": "School of Science and Technology",
}
KNOWN_MOI_CONFLICTS = {
    "GEN 1060EBF": "english",             # 字母 B=bilingual,目录印 English
}


def test_every_ge_course_enriched():
    assert CATALOG_UPDATED == "2026-08-07"
    # 批次 1(2026-08-19):池=官方目录全集 89(73 开课 + 16 不开 terms=[])
    assert len(GE_COURSES) == 89
    for c in GE_COURSES:
        e = GE_ENRICH.get(c["code"])
        assert e, f"{c['code']}: 不在 GE_ENRICH"
        assert e["credits"] == 3, f"{c['code']}: credits={e['credits']}"
        assert e["level"] in (1000, 2000), f"{c['code']}: level={e['level']}"
        assert e["moi"] in ("english", "chinese", "bilingual"), f"{c['code']}: moi={e['moi']}"
        assert e["school_name"], f"{c['code']}: school_name 空"
        # GEN 1028ACF 官方介绍即 54 字(人眼核过原文,非截断),豁免门槛
        min_len = 54 if c["code"] == "GEN 1028ACF" else 60
        assert len(e["description"]) >= min_len, (
            f"{c['code']}: description 过短({len(e['description'])})"
        )
        for x in e["excluded"]:
            assert EXCLUDED_RE.match(x), f"{c['code']}: excluded 格式坏 {x}"


def test_code_letter_cross_validation():
    """官方课码规则 vs 抓取值。已知出入以例外锁死;新出入 = 抓取回归,立即红。"""
    for c in GE_COURSES:
        code = c["code"]
        m = CODE_RE.match(code)
        assert m, f"{code}: 课码不匹配官方格式"
        lvl_digit, _, sch_letter, moi_letter, _ = m.groups()
        e = GE_ENRICH[code]
        assert ("1" if e["level"] == 1000 else "2") == lvl_digit, f"{code}: 千位≠level"
        assert SCHOOL_OF_LETTER[sch_letter] == c["school"], f"{code}: 第5字母≠池 school"
        if code in KNOWN_MOI_CONFLICTS:
            assert e["moi"] == KNOWN_MOI_CONFLICTS[code], f"{code}: moi 例外值变了"
        else:
            assert MOI_OF_LETTER[moi_letter] == e["moi"], f"{code}: 第6字母≠moi"
        if code in KNOWN_SCHOOL_CONFLICTS:
            assert e["school_name"] == KNOWN_SCHOOL_CONFLICTS[code], f"{code}: school 例外值变了"


def test_school_names_table_matches_pdf():
    """五院双语表完整;A&SS 已应用 2026-09-01 更名且旧名锁在 pdf_verbatim;
    每条富化的 school_name 原文都在官方表内(表外值=解析错)。"""
    assert set(GE_SCHOOL_NAMES) == {"A&SS", "B&A", "E&L", "N&HS", "S&T"}
    aass = GE_SCHOOL_NAMES["A&SS"]
    assert aass["en"] == "Wu Jieh Yee School of Arts and Social Sciences"
    assert aass["zh"] == "伍絜宜人文社會科學院"
    assert aass["pdf_verbatim"] == ("School of Arts and Social Sciences", "人文社會科學院")

    known_names = set()
    for n in GE_SCHOOL_NAMES.values():
        known_names.update(n["pdf_verbatim"])
    for code, e in GE_ENRICH.items():
        assert e["school_name"] in known_names, f"{code}: 表外学院名 {e['school_name']!r}"


def test_descriptions_have_no_page_noise():
    """介绍段不得残留页噪声/字段标签——防跨页/噪声清理退化。"""
    label_bits = (
        "Back to index", "Note: The School", "Credit-units:", "學分:",
        "Medium of", "授課語言", "Offering School", "所屬學院",
        "Excluded Combination", "不可兼修",
    )
    for code, e in GE_ENRICH.items():
        d = e["description"]
        for bit in label_bits:
            assert bit not in d, f"{code}: description 残留 {bit!r}"
        assert not re.search(r"^Page \d+$", d, re.M), f"{code}: 残留页码行"
        assert not re.search(r"^Level:|^程度:", d, re.M), f"{code}: 残留级别标签行"


def test_description_languages_and_bilingual():
    """官方介绍单语/双语形态:中文授课→中文段;英文授课→英文段;Bilingual→英+中。
    抽真实样本锁死(含双语课程两段都在)。"""
    zh = GE_ENRICH["GEN 1042ECF"]["description"]   # 中文授课
    assert zh.startswith("本科") and not re.search(r"[A-Za-z]{10,}", zh)
    en = GE_ENRICH["GEN 1022AEF"]["description"]   # 英文授课
    assert en.startswith("This course") and not re.search(r"[一-鿿]", en)
    bi = [e for e in GE_ENRICH.values() if e["moi"] == "bilingual"]
    assert bi, "池内应有 Bilingual 课程"
    dual = [e for e in bi if "\n\n" in e["description"]
            and re.search(r"[一-鿿]", e["description"])
            and re.search(r"[A-Za-z]", e["description"])]
    assert dual, "至少一门 Bilingual 课应带英+中两段介绍"


def test_ge_course_by_id_lookup():
    hit = ge_course_by_id("GEN1042ECF")
    assert hit and hit["level"] == 1000 and hit["moi"] == "chinese"
    assert hit["terms"] == ["autumn", "spring"]
    assert ge_course_by_id("COMP1080SEF") is None
    assert ge_course_by_id("") is None
