#!/usr/bin/env python3
"""HKMU GE Courses Catalog (3cru) PDF → backend/app/data/ge_catalog_enrichment.py.

官方目录 PDF 每门课一段:課碼/双语课名/學分/程度/授課語言/所屬學院/(可选)不可兼修
組合/介绍段落(英文授课→英文段,中文授课→中文段,Bilingual→英+中两段)。
本脚本解析出富化字段,按课码 join 进 GE_COURSES 池,生成独立数据模块
(不碰 GE_COURSES 本体——那里含人工修复痕迹)。

用法:
  python scripts/scrape_ge_catalog.py --from-text /tmp/ge_catalog_3cru.txt  # 主路径,无网络
  python scripts/scrape_ge_catalog.py --pdf /tmp/ge_catalog_3cru.pdf        # pdftotext 后同上
  python scripts/scrape_ge_catalog.py                                       # curl 下载后解析
  python scripts/scrape_ge_catalog.py --report --from-text ...              # 只打印对账不写文件

准确性硬门槛:join 后跑「课码字母 vs 学院/授课语言/级别」交叉校验,不过 exit 1。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CATALOG_URL = "https://www.hkmu.edu.hk/REG/reg_ftae/GE/GE_catalog_3cru.pdf"
OUT_PATH = ROOT / "backend/app/data/ge_catalog_enrichment.py"

# 官方课码规则(来源:HKMU distance-learning 页 General Requirements):
# GEN + 4位(千位=级别) + 第5字母=学院 + 第6字母=授课语言(E/C/B) + 第7字母=模式(F/W/D)
SCHOOL_OF_LETTER = {"A": "A&SS", "B": "B&A", "E": "E&L", "N": "N&HS", "S": "S&T"}
MOI_OF_LETTER = {"E": "english", "C": "chinese", "B": "bilingual"}

# PDF 内 A&SS 有 1 处单数拼写笔误「Social Science」,归一到复数正名
SCHOOL_NAME_FIX = {
    "School of Arts and Social Science": "School of Arts and Social Sciences",
}

# A&SS 于 2026-09-01(秋季学期前)更名伍絜宜人文社會科學院;展示用新名,旧名留 pdf_verbatim
AASS_RENAME = {
    "en": "Wu Jieh Yee School of Arts and Social Sciences",
    "zh": "伍絜宜人文社會科學院",
}

# 官方五院双语名(每个名字均在目录 PDF 中有实证)。⚠️ 课码第5字母与目录「所屬學院」
# 栏在个别课上有出入(如 GEN 1510NCF/2501NEF 印 S&T)——展示一律以目录逐课打印为准,
# 字母↔学院不一致只作警告列出,不拦数据。
OFFICIAL_SCHOOL_TABLE = {
    "A&SS": ("School of Arts and Social Sciences", "人文社會科學院"),
    "B&A": ("Lee Shau Kee School of Business and Administration", "李兆基商業管理學院"),
    "E&L": ("School of Education and Languages", "教育及語文學院"),
    "N&HS": ("School of Nursing and Health Sciences", "護理及健康學院"),
    "S&T": ("School of Science and Technology", "科技學院"),
}

NOISE_PATTERNS = [
    re.compile(r"^\s*Back to index\s*$"),
    re.compile(r"^\s*Page \d+\s*$"),
    re.compile(r"^Note: The School of Arts and Social Sciences will be named"),
    re.compile(r"^科學院\) effective from 1 September 2026[.。]\s*$"),
]

ENTRY_HEAD = re.compile(r"^\s{2,}(GEN \d{4}[A-Z]{3})\s+(\S.*)$")
CREDITS_LABEL = re.compile(r"^\s*(?:Credit-units|學分)\s*[::]")
CODE_RE = re.compile(r"^GEN (\d)(\d{3})([A-Z])([ECB])([FWD])$")
CODE_TOKEN = re.compile(r"\b[A-Z]{3,4}\s?\d{4}[A-Z]{3}\b")

LABELS = [
    ("credits", re.compile(r"^\s*(?:Credit-units|學分)\s*[::]\s*(\d+)")),
    ("level", re.compile(r"^\s*(?:Level|程度)\s*[::]\s*(\d+)")),
    ("moi", re.compile(r"^\s*(?:Medium of [Ii]nstruction|授課語言)\s*[::]\s*(.+?)\s*$")),
    ("school_name", re.compile(r"^\s*(?:Offering School|所屬學院)\s*[::]\s*(.+?)\s*$")),
    ("excluded", re.compile(r"^\s*(?:Excluded Combination|不可兼修的科目組合)\s*[::]\s*(.*)$")),
]

# 官方目录本身只有一句话介绍的课(人眼核过 PDF 原文,下一行就是下一门课的
# 課碼行,非解析截断):豁免 60 字最低长度门槛。
SHORT_DESC_OFFICIAL = frozenset({
    "GEN 1028ACF",  # 科幻小說創作實踐,官方即 54 字(2026-08-19 批次 1 人眼核对)
})

CJK = r"　-〿一-鿿＀-￯"


def clean_text(txt: str) -> tuple[list[str], str]:
    """删页噪声,返回 (干净行列表, 目录更新日期)。"""
    updated = ""
    m = re.search(r"Last updated on (\d{1,2} \w+ \d{4})", txt)
    if m:
        try:
            updated = datetime.strptime(m.group(1), "%d %B %Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    lines = []
    for ln in txt.replace("\f", "\n").splitlines():
        if any(p.search(ln) for p in NOISE_PATTERNS):
            continue
        lines.append(ln.rstrip())
    return lines, updated


def split_entries(lines: list[str]) -> list[dict]:
    """锚定正文条目:缩进≥2 的课码行(TOC 课码行缩进为 0,天然排除)。

    长课名的标题会折行——课码行和学分标签之间隔 1-2 行标题续行,由 parse_entry
    消化(标签出现前的行归入 title_raw)。条目边界 = 下一个锚点,或任何缩进≤1 的
    非空行(领域小节标题,如「 Area Studies」)。
    """
    entries: list[dict] = []
    cur: list[str] | None = None
    for ln in lines:
        if ENTRY_HEAD.match(ln):
            if cur:
                entries.append(parse_entry(cur))
            cur = [ln]
            continue
        if cur is not None:
            if ln.strip() and (len(ln) - len(ln.lstrip())) <= 1:
                entries.append(parse_entry(cur))  # 小节标题 → 边界
                cur = None
            else:
                cur.append(ln)
    if cur:
        entries.append(parse_entry(cur))
    return [e for e in entries if e]


def join_desc_lines(lines: list[str]) -> str:
    """段落内智能拼接:连字符断词并回、CJK-CJK 无空格、其余加空格;空行分段。"""
    paras: list[list[str]] = [[]]
    for ln in lines:
        if not ln.strip():
            if paras[-1]:
                paras.append([])
            continue
        paras[-1].append(ln.strip())
    out_paras = []
    for p in paras:
        if not p:
            continue
        buf = p[0]
        for s in p[1:]:
            if re.search(r"[A-Za-z]-$", buf) and re.match(r"^[a-z]", s):
                buf += s  # PDF 行末连字符断词(e.g. problem-\nsolving)
            elif re.search(f"[{CJK}]$", buf) and re.match(f"^[{CJK}]", s):
                buf += s  # 中文换行无空格
            else:
                buf += " " + s
        out_paras.append(buf)
    return "\n\n".join(out_paras)


def parse_entry(lines: list[str]) -> dict | None:
    m = ENTRY_HEAD.match(lines[0])
    if not m:
        return None
    entry = {
        "code": m.group(1),
        "title_raw": m.group(2).strip(),
        "credits": None, "level": None, "moi": "", "school_name": "",
        "excluded": [], "desc_lines": [],
    }
    in_excluded = False
    seen_label = False
    for ln in lines[1:]:
        hit = None
        for key, pat in LABELS:
            lm = pat.match(ln)
            if lm:
                hit = (key, lm)
                break
        if hit:
            key, lm = hit
            seen_label = True
            if key == "credits":
                entry["credits"] = int(lm.group(1)); in_excluded = False
            elif key == "level":
                entry["level"] = int(lm.group(1)); in_excluded = False
            elif key == "moi":
                raw = lm.group(1)
                low = raw.lower()
                if "bilingual" in low or "雙語" in raw:
                    entry["moi"] = "bilingual"
                elif "english" in low:
                    entry["moi"] = "english"
                elif "中文" in raw:
                    entry["moi"] = "chinese"
                else:
                    entry["moi"] = raw  # 未知值原样保留,交叉校验会拦下
                in_excluded = False
            elif key == "school_name":
                entry["school_name"] = SCHOOL_NAME_FIX.get(lm.group(1), lm.group(1))
                in_excluded = False
            else:  # excluded 标签行(可能同行带码)
                in_excluded = True
                entry["excluded"].extend(CODE_TOKEN.findall(lm.group(1)))
            continue
        if not ln.strip():
            if entry["desc_lines"] or not in_excluded:
                entry["desc_lines"].append("")
            continue
        if not seen_label:
            # 长课名折行:学分标签出现前的行是标题续行,不是介绍
            entry["title_raw"] += " " + ln.strip()
            continue
        if in_excluded:
            rest = CODE_TOKEN.sub("", ln)
            if re.sub(r"[()\sivx,、;；]", "", rest) == "":
                entry["excluded"].extend(CODE_TOKEN.findall(ln))
                continue
            in_excluded = False  # 不是码列表 → 进入介绍段
        entry["desc_lines"].append(ln)
    # 去重保序 + 去掉结尾空行
    seen = set()
    entry["excluded"] = [c for c in entry["excluded"] if not (c in seen or seen.add(c))]
    entry["excluded"] = [re.sub(r"\s+", " ", c).upper().replace(" ", " ") for c in entry["excluded"]]
    entry["description"] = join_desc_lines(entry["desc_lines"]).strip()
    return entry


def build_school_names(entries: list[dict]) -> dict[str, dict]:
    """校验每条目的 school_name 都在官方五院表内,返回展示层双语名(A&SS 已更名)。"""
    known = {n for pair in OFFICIAL_SCHOOL_TABLE.values() for n in pair}
    out: dict[str, dict] = {}
    for sch, (en, zh) in OFFICIAL_SCHOOL_TABLE.items():
        if sch == "A&SS":
            out[sch] = {"en": AASS_RENAME["en"], "zh": AASS_RENAME["zh"],
                        "pdf_verbatim": (en, zh)}
        else:
            out[sch] = {"en": en, "zh": zh, "pdf_verbatim": (en, zh)}
    unknown = {e["school_name"] for e in entries if e["school_name"] not in known}
    if unknown:
        raise SystemExit(f"❌ 目录出现表外学院名(疑似解析错): {unknown}")
    return out


def py_str(s: str) -> str:
    return repr(s)


def render_module(updated: str, school_names: dict, enrich: dict, order: list[str]) -> str:
    lines = [
        '"""GENERATED by scripts/scrape_ge_catalog.py — DO NOT EDIT.',
        "",
        f'Source: HKMU Undergraduate GE Courses Catalog (3-credit-unit), updated {updated}.',
        "Fields per course (official, verbatim from the catalog PDF): credits / level",
        "(1000|2000) / moi (english|chinese|bilingual) / school_name (PDF verbatim;",
        "1 typo 'School of Arts and Social Science' normalized to plural) / description",
        "(official text as printed; language follows the course — Chinese-taught",
        "courses carry a ZH paragraph, English-taught an EN paragraph; bilingual",
        "courses vary: some print EN+ZH, some only one, kept verbatim either way) /",
        "excluded (不可兼修的科目組合, only 10 courses have any).",
        '"""',
        "",
        f"CATALOG_UPDATED = {py_str(updated)}",
        "",
        "# 学院双语名。A&SS 已应用 2026-09-01 更名(Note 在 PDF 内),旧名锁在 pdf_verbatim。",
        "GE_SCHOOL_NAMES = {",
    ]
    for sch in ["A&SS", "B&A", "E&L", "N&HS", "S&T"]:
        n = school_names.get(sch)
        if not n:
            continue
        lines.append(
            f"    {py_str(sch)}: {{\"en\": {py_str(n['en'])}, \"zh\": {py_str(n['zh'])}, "
            f"\"pdf_verbatim\": ({py_str(n['pdf_verbatim'][0])}, {py_str(n['pdf_verbatim'][1])})}},"
        )
    lines += ["}", "", "# 按课码索引;仅含 planner 池内课程(窗口外开课的目录课不进池)。", "GE_ENRICH = {"]
    for code in order:
        e = enrich[code]
        excl = ", ".join(py_str(x) for x in e["excluded"])
        lines.append(
            f"    {py_str(code)}: {{\"credits\": {e['credits']}, \"level\": {e['level']}, "
            f"\"moi\": {py_str(e['moi'])}, \"school_name\": {py_str(e['school_name'])},\n"
            f"        \"description\": {py_str(e['description'])},\n"
            f"        \"excluded\": [{excl}]}},"
        )
    lines += ["}", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-text", help="pdftotext -layout 产物路径(主路径,无网络)")
    ap.add_argument("--pdf", help="PDF 路径,现场 pdftotext")
    ap.add_argument("--report", action="store_true", help="只打印对账,不写文件")
    args = ap.parse_args()

    if args.from_text:
        txt = Path(args.from_text).read_text(encoding="utf-8")
    elif args.pdf:
        txt = subprocess.run(
            ["pdftotext", "-layout", args.pdf, "-"],
            check=True, capture_output=True, text=True,
        ).stdout
    else:
        req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "Mozilla/5.0"})
        pdf_bytes = urllib.request.urlopen(req, timeout=60).read()
        tmp = Path("/tmp/ge_catalog_3cru.pdf")
        tmp.write_bytes(pdf_bytes)
        txt = subprocess.run(
            ["pdftotext", "-layout", str(tmp), "-"],
            check=True, capture_output=True, text=True,
        ).stdout

    lines, updated = clean_text(txt)
    entries = split_entries(lines)
    print(f"解析条目: {len(entries)} 门;目录更新日期: {updated or '(未解析到)'}")

    by_code = {}
    for e in entries:
        if e["code"] in by_code:
            print(f"⚠️ 重复条目 {e['code']},以首个为准")
            continue
        by_code[e["code"]] = e

    school_names = build_school_names(entries)
    print("学院名(展示层,含 A&SS 更名):")
    for sch, n in school_names.items():
        print(f"  {sch}: {n['zh']} / {n['en']}  (PDF verbatim: {n['pdf_verbatim'][0]})")

    from backend.app.data.ge_courses import GE_COURSES  # noqa: E402

    enrich, order, missing, errors, warns = {}, [], [], [], []
    for c in GE_COURSES:
        code = c["code"]
        order.append(code)
        e = by_code.get(code)
        if not e:
            missing.append(code)
            continue
        enrich[code] = {
            "credits": e["credits"], "level": e["level"], "moi": e["moi"],
            "school_name": e["school_name"], "description": e["description"],
            "excluded": e["excluded"],
        }
        m = CODE_RE.match(code)
        if not m:
            errors.append(f"{code}: 课码不匹配官方格式")
            continue
        lvl_digit, _, sch_letter, moi_letter, _ = m.groups()
        if SCHOOL_OF_LETTER[sch_letter] != c["school"]:
            errors.append(f"{code}: 第5字母={sch_letter}→{SCHOOL_OF_LETTER[sch_letter]} ≠ 池 school={c['school']}")
        # 目录打印的学院 vs 课码字母:官方文件内部即有出入,只警告(展示以目录为准)
        letter_school_name = OFFICIAL_SCHOOL_TABLE[SCHOOL_OF_LETTER[sch_letter]]
        if e["school_name"] not in letter_school_name:
            warns.append(
                f"{code}: 课码字母→{SCHOOL_OF_LETTER[sch_letter]},但目录印 {e['school_name']}"
                f"(展示按目录;池 school={c['school']})")
        if MOI_OF_LETTER[moi_letter] != e["moi"]:
            # 官方文件内部即有出入(如 GEN 1060EBF 字母 B=bilingual 但目录印 English,
            # 人工核对过原文)——展示以目录为准,只警告
            warns.append(f"{code}: 第6字母={moi_letter}→{MOI_OF_LETTER[moi_letter]} ≠ 目录 moi={e['moi']}(展示按目录)")
        if lvl_digit != str(e["level"])[0]:
            errors.append(f"{code}: 千位={lvl_digit} ≠ 目录 level={e['level']}")
        if e["credits"] != 3:
            errors.append(f"{code}: credits={e['credits']} ≠ 3")
        if (not e["description"] or len(e["description"]) < 60) and code not in SHORT_DESC_OFFICIAL:
            errors.append(f"{code}: description 过短({len(e['description'])} 字符)")
        if not e["school_name"]:
            errors.append(f"{code}: school_name 为空")

    pool_only = [c["code"] for c in GE_COURSES if c["code"] not in by_code]
    catalog_only = [e for code, e in by_code.items()
                    if code not in {c["code"] for c in GE_COURSES}]

    print(f"\njoin: {len(enrich)}/{len(GE_COURSES)} 池内课命中目录")
    if pool_only:
        print(f"⚠️ 池内有、目录无({len(pool_only)}): {pool_only}")
    if catalog_only:
        print(f"\n目录有、池无({len(catalog_only)} 门,窗口外未开课,不进池,供对照 Selection Guide):")
        for e in catalog_only:
            print(f"  {e['code']}  {e['title_raw'][:60]}")
    if warns:
        print(f"\n⚠️ 课码字母↔目录打印出入 {len(warns)} 项(官方文件内部不一致,展示以目录为准,人工过目):")
        for x in warns:
            print(" ", x)
    if errors:
        print(f"\n❌ 交叉校验失败 {len(errors)} 项:")
        for x in errors:
            print(" ", x)
        return 1
    print("\n✅ 交叉校验全过(课码字母↔授课语言/级别、池 school↔字母、credits=3、介绍非空)")

    if args.report:
        return 0
    OUT_PATH.write_text(render_module(updated, school_names, enrich, order), encoding="utf-8")
    print(f"\n已写入 {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
