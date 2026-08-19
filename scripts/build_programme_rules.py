#!/usr/bin/env python3
"""Generate backend/app/data/programme_rules.py from the scraped raw JSON.

Inputs (all local, deterministic — re-run any time after T32 reparse):
  * scripts/out/programmes_raw.json — parser output (categories + min_credits
    + per-course credits + total_credits), one entry per programme.
  * docs/ops/选课选课/skill.md — official programme tree: school membership +
    English programme names (also fixes the scrape-time school mislabels).
  * backend/app/data/programmes.py — existing hand-curated entries (trilingual
    name overlay where present).

Output shape mirrors a PROGRAMMES entry exactly (see DSAI), so programmes.py
can merge them 1:1:
    {code, name{en[,zh-CN,zh-TW]}, school, total_credits, categories, template}

Category modelling (user decisions, 2026-08-14):
  * elective  → pool:"credits"  (credit-based satisfaction — handles both the
    small "pick 9cr" pools and the 150-course STEAM menus)
  * general-ed → pool:"ge", courses [] (resolved live from ge_courses_for)
  * non-standard PDF sections were already folded by the parser
    (concentration/clinical practicum/… → core; periphery/specialization → elective)
  * a course listed in BOTH core and elective is dropped from elective — it is
    already required, and may not double as an elective pick
  * BSCHDSAIJ is EXCLUDED: the hand-curated entry stays authoritative
    (its PDF/parse diff is the documented COMP4610SEF project split)

Usage:
  python scripts/build_programme_rules.py            # write + summary
  python scripts/build_programme_rules.py --check    # summary only, no write
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
RAW_JSON = os.path.join(ROOT, "scripts", "out", "programmes_raw.json")
SKILL_MD = os.path.join(ROOT, "docs", "ops", "选课选课", "skill.md")
OUT_PY = os.path.join(ROOT, "backend", "app", "data", "programme_rules.py")
TEXT_DIR = os.path.join(ROOT, "scripts", "out", "hkmu_pr", "text")

EXCLUDE = {"BSCHDSAIJ"}  # hand-curated entry is authoritative

CATEGORY_COLORS = {
    "core": "blue",
    "elective": "purple",
    "english": "emerald",
    "general-ed": "pink",
    "university-core": "indigo",
}
# Emission order (matches the DSAI entry's category order).
CATEGORY_ORDER = ["core", "elective", "english", "general-ed", "university-core"]

SCHOOL_BY_SEG = {
    "AS": "School of Arts and Social Sciences",
    "BA": "Lee Shau Kee School of Business and Administration",
    "EL": "School of Education and Languages",
    "NHS": "School of Nursing and Health Sciences",
    "ST": "School of Science and Technology",
}

# A&SS 于 2026-09-01 更名伍絜宜人文社會科學院(与 ge_catalog_enrichment 的
# GE_SCHOOL_NAMES / scrape_ge_catalog.py AASS_RENAME 同口径)。skill.md 是官方
# PDF 逐字导出、保留旧名,故在装配层统一换成新名,再生成不会回退。
SCHOOL_RENAME = {
    "School of Arts and Social Sciences": "Wu Jieh Yee School of Arts and Social Sciences",
}

_PROG_RE = re.compile(r"^\|\s*\+-- (.+?)\s*\(([A-Z0-9]{4,})\)/\s*$")
_SCHOOL_RE = re.compile(r"^\+-- (.+)/\s*$")


def skill_md_index():
    """{code: {en, school}} from the official tree (school = tree parent)."""
    out = {}
    school = None
    with open(SKILL_MD, encoding="utf-8") as f:
        for line in f:
            m = _SCHOOL_RE.match(line)
            if m:
                school = m.group(1).strip()
                continue
            m = _PROG_RE.match(line)
            if m:
                out[m.group(2)] = {"en": m.group(1).strip(), "school": school}
    return out


def pdf_text_name(code):
    """Fallback English name: the lines after 'Programme Requirements for'."""
    p = os.path.join(TEXT_DIR, f"{code}.txt")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        txt = f.read()
    m = re.search(r"Programme Requirements for\s*\n(.+?)\n\s*\n", txt, re.S)
    if not m:
        return None
    name = " ".join(x.strip() for x in m.group(1).splitlines() if x.strip())
    name = re.sub(r"\s+", " ", name).strip()
    # Some intros continue into non-name prose; keep it to two sentences max.
    return name.split(". ")[0].strip() or None


def build_entry(code, raw, skill, existing):
    """Assemble one PROGRAMMES-shaped entry from all sources."""
    base = existing.get(code, {})
    sk = skill.get(code, {})

    name = dict(base.get("name") or {})
    if not name.get("en"):
        name["en"] = sk.get("en") or pdf_text_name(code) or code
    # zh names only where an authoritative source already had them — never
    # invent official translations (programme_name() falls back to English).

    school = sk.get("school") or base.get("school") \
        or SCHOOL_BY_SEG.get(raw.get("school", "")) or "HKMU"
    school = SCHOOL_RENAME.get(school, school)

    cats_out = {}
    core_courses = set(raw["categories"].get("core", {}).get("courses", []))
    for key in CATEGORY_ORDER:
        cat = raw["categories"].get(key)
        if not cat:
            continue
        if key == "general-ed":
            # pick_n mirrors DSAI's hand entry: GE courses are all 3cr, and
            # the pool satisfies on "pick_n distinct-field courses AND min
            # credits" — without pick_n an empty-course GE pool can never
            # satisfy (empty-pool branch: required == 0).
            ge_min = cat.get("min_credits", 0)
            cats_out[key] = {"min_credits": ge_min,
                             "color": CATEGORY_COLORS[key],
                             "courses": [], "pool": "ge",
                             "pick_n": max(1, ge_min // 3)}
            continue
        courses = list(cat.get("courses", []))
        if key == "elective":
            # Required-core courses may not double as elective picks.
            courses = [c for c in courses if c not in core_courses]
            cats_out[key] = {"min_credits": cat.get("min_credits", 0),
                             "color": CATEGORY_COLORS[key],
                             "courses": courses, "pool": "credits"}
            continue
        # Required pool (core / english / university-core): the PDF table is
        # shared across cohorts/streams at the document tail, so its rows can
        # over-list (e.g. BSCHSTAMJ core table 74cr vs the 2026/27-cohort min
        # 48). Trust the prose min_credits (cohort-correct, agent-verified) and
        # TRIM the list to the first courses summing to it — table order is
        # cohort-grouped, so the prefix is the primary cohort's requirement.
        cc = cat.get("course_credits", {})
        min_cr = cat.get("min_credits", 0)
        kept = []
        running = 0
        for cid in courses:
            if min_cr and running >= min_cr:
                break
            kept.append(cid)
            running += cc.get(cid, 3)
        cats_out[key] = {"min_credits": min_cr,
                         "color": CATEGORY_COLORS[key],
                         "courses": kept}

    # 范围措辞的 elective("3 to 6" + "12 to 15" cr)各自计上限,但配对范围是
    # 合计恒定的两条路径(做/不做毕业课题)→ Σmin 超 PDF 总分。按余数 gap 校正
    # elective 学分池(BSSCHPAJ 21→18)。仅当 parser 标记了 _ranged_elective。
    if raw.get("_ranged_elective"):
        smin = sum(c["min_credits"] for c in cats_out.values())
        total = raw.get("total_credits") or 0
        if "elective" in cats_out and total and smin > total:
            cats_out["elective"]["min_credits"] -= smin - total

    # course_credits: required pools trimmed to the kept courses; elective keeps
    # its full menu (seed needs every menu course's credits, and graduation's
    # credit-pool math reads them). GE is dynamic — omitted.
    trimmed_cc = {}
    for key, cat in cats_out.items():
        if key == "general-ed":
            continue
        raw_cc = raw["categories"].get(key, {}).get("course_credits", {})
        trimmed_cc[key] = {cid: raw_cc.get(cid, 3) for cid in cat["courses"]}

    return ({"code": code, "name": name, "school": school,
             "total_credits": raw.get("total_credits"),
             "categories": cats_out, "template": {}},
            trimmed_cc)


def py_literal(obj, indent=0):
    """Compact, stable python literal (dicts/lists, str/int/None/bool)."""
    pad = "    " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        items = [f'{pad}    "{k}": {py_literal(v, indent + 1)}' for k, v in obj.items()]
        return "{\n" + ",\n".join(items) + f"\n{pad}}}"
    if isinstance(obj, list):
        if not obj:
            return "[]"
        if all(isinstance(x, str) for x in obj):
            return "[" + ", ".join(f'"{x}"' for x in obj) + "]"
        return "[\n" + f",{chr(10)}".join(pad + "    " + py_literal(x, indent + 1) for x in obj) + f"\n{pad}]"
    return repr(obj)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="summarize without writing")
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "backend"))
    from app.data.programmes import PROGRAMMES  # noqa: E402 — pure dict

    raw = json.load(open(RAW_JSON, encoding="utf-8"))
    skill = skill_md_index()

    rules = {}
    course_credits = {}  # code -> {category: {course_id: credits}} (seed fallback)
    problems = []
    for code in sorted(raw):
        if code in EXCLUDE or "_error" in raw[code]:
            continue
        # BSSCHJ(Y1 段)Table 1 的 SOCI2003AEF 勾选列仅 Year-2 入学适用
        # (Wingdings 勾在 pdfplumber 文本抽取中丢失,行级不可判),prose 69cr
        # ÷3=23 门也证 24 行含杂。从 core 剔除后:截断自动保回真 Y1 必修
        # SOCI4008AEF,其 Y1 身份(Table 2 主修选修)由 core/elective 去重器
        # 保留在选修菜单。2026-08-17 子代理逐行核对裁定,唯一一处类别错置。
        if code == "BSSCHJ":
            c = raw[code]["categories"]["core"]["courses"]
            if "SOCI2003AEF" in c:
                c.remove("SOCI2003AEF")
        entry, cc = build_entry(code, raw[code], skill, PROGRAMMES)
        # sanity: non-ge categories must list courses; sums must match total.
        smin = sum(c["min_credits"] for c in entry["categories"].values())
        for key, cat in entry["categories"].items():
            if key != "general-ed" and not cat["courses"]:
                problems.append(f"{code}: {key} has no courses")
        if entry["total_credits"] != smin:
            problems.append(f"{code}: Σmin={smin} ≠ total={entry['total_credits']}")
        rules[code] = entry
        course_credits[code] = cc

    n_courses = sum(len(c["courses"]) for e in rules.values()
                    for c in e["categories"].values())
    print(f"programmes: {len(rules)} (excluded: {sorted(EXCLUDE & set(raw))})")
    print(f"courses referenced: {n_courses}")
    print(f"problems: {len(problems)}")
    for p in problems:
        print(f"  ⚠️ {p}")

    if args.check:
        return
    if problems:
        sys.exit("refusing to write with sanity problems — fix the parser first")

    header = f'''"""Auto-generated by scripts/build_programme_rules.py — DO NOT HAND-EDIT.

Source: HKMU official programme-requirements PDFs (3-credit-unit system),
scraped 2026-08-14 via scripts/scrape_programme_pdfs.py (T31) and parsed with
the five-school category mapping (T32). Names/schools cross-checked against
docs/ops/选课选课/skill.md; hand-curated names reused where available.

Modelling decisions (2026-08-14):
  * elective → pool:"credits": satisfied by earned ≥ min_credits, any course
    combination (covers small pick pools and 150-course STEAM menus alike)
  * general-ed → pool:"ge": courses resolved live from ge_courses_for()
  * PDF sections outside the standard set are folded (concentration / clinical
    practicum / specialized professional / integrated STEAM(M) → core;
    periphery / specialization → elective); Global Immersion (non-credit) skipped
  * BSCHDSAIJ is absent on purpose — the hand-curated PROGRAMMES entry
    (with its COMP4610SEF project split) stays authoritative.

Regenerate: python scripts/scrape_programme_pdfs.py --from-text-dir \\
                scripts/out/hkmu_pr/text > scripts/out/programmes_raw.json
            python scripts/build_programme_rules.py
"""

PROGRAMME_RULES = '''

    body = py_literal(rules) + "\n"
    body += ('\n# Per-course credit-units parsed from the PDF tables — NOT part of'
             '\n# the graduation data; seed_courses.py uses it to seed courses-table'
             '\n# rows for rule courses the catalogue has no name/credits for.\n'
             'RULE_COURSE_CREDITS = ') + py_literal(course_credits) + "\n"
    with open(OUT_PY, "w", encoding="utf-8") as f:
        f.write(header + body)
    print(f"wrote {OUT_PY} ({os.path.getsize(OUT_PY)} bytes)")


if __name__ == "__main__":
    main()
