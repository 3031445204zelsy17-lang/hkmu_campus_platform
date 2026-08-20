"""Seed courses table with DSAI programme data and create test account."""
import asyncio
import asyncpg
import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import init_db  # noqa: E402 — sys.path set above
from app.data.ge_courses import GE_COURSES  # noqa: E402 — real 2026/27 GE pool
from app.data.programme_rules import (  # noqa: E402 — 54-programme rules (T33)
    PROGRAMME_RULES,
    RULE_COURSE_CREDITS,
)
from app.data.programmes import PROGRAMMES  # noqa: E402 — 批次 3 骨架实体名
from app.data.programme_year_map import (  # noqa: E402 — 批次 2/3 补池/种池/课名
    ADDITION_CREDITS,
    COURSE_NAME_BACKFILL,
    POOL_ADDITIONS,
    POOL_SEED_CREDITS,
    PROGRAMME_POOL_SEED,
)
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── 学分裁定表(选课数据修复批次 1)─────────────────────────────────────────
# 依据:docs/ops/选课选课/advice_sheets/复核报告-2026-08-19.md 第五节。15 门为
# 三方一致(官方 yr 年级表 = RCC(programme-requirements PDF) = skill.md 叶标题
# 尾数)直修;NURS1313NCF 官方源自相矛盾(yr 表 6 vs RCC/skill.md 标记 3),
# 2026-08-19 人工裁定取 yr 表的 6。
# 错值根源:skill.md 的 [学分:N] 标记被 PDF 页码污染(吃进 "Page N of M" 尾数),
# 经 T34「catalogue 学分优先」传播进 courses 表。
CREDIT_FIXES = {
    "TC4019SEF": 3,    # catalogue 错值 4
    "TC4026SEF": 3,    # 5
    "CHIN3004ACF": 3,  # 6
    "CHIN4243ECF": 3,  # 8
    "CHIN4383ECF": 3,  # 8
    "COMP4570SEF": 6,  # 2
    "TC4094SEF": 12,   # 5
    "CHIN4009ACF": 6,  # 5
    "CAMD2000AEF": 3,  # 5
    "CCA4002ACF": 3,   # 5
    "IDDA2001AEF": 3,  # 6
    "TRM3013BEF": 3,   # 6
    "SCI4063SEF": 3,   # 4
    "ASM4057BEF": 9,   # 6
    "SPM4098BEF": 9,   # 5
    "NURS1313NCF": 6,  # 3;官方源矛盾,人工裁定 yr 表
}

# ── 批次 5 选修目录收尾(选课数据修复,2026-08-20)─────────────────────────────
# UG 选修目录(3cr 版,verify/elec_catalog.json 双引擎 451 门)全库缺口最后 2 门。
# 人眼核原文(UG_elective_catalog_3cru.pdf p105-106):两门均有 TOC 行 + 正文
# 完整条目(學分 3 / 程度 1000·4000 / 授課語言 中文 / 不可兼修 -)→ 真课,按
# 条目导入。advice sheet / skill.md catalogue / 规则池均不收它们:ECF 后缀 =
# 中文授课班,skill.md 收的是 EBF 英文班变体(DRAM 1000EBF/4244EBF,与
# NURS1050NEF/NCF 双班别同构),故此前字符串级差集恰好剩这两门。
# 目录无学期数据 → semester="any"(GE/BATCH4 同款哨兵);year 走 _level_year。
ELECTIVE_CATALOG_IMPORT = [
    {"id": "DRAM1000ECF", "code": "DRAM 1000ECF", "credits": 3,
     "category": "elective", "name": "Basic Acting for Speech and Reading"},
    {"id": "DRAM4244ECF", "code": "DRAM 4244ECF", "credits": 3,
     "category": "elective", "name": "Dramatic Literature From East and West"},
]

# BUS1003BEF/BUS1004BEF(批次 5 人眼定性,2026-08-20):选修目录全文只在
# ENGL 1101AEF 条目的 Excluded Combination 引用块出现(p31,带官方双语课名),
# 无 TOC 行、无正文条目、无学分;朴素正则 479 集含两码、锚定 451 集不含
# (verify/elec_catalog_check.py 双引擎),「引用无条目」坐实。批次 4 互斥组
# excl-engl1101-bus1003(BSCHBSBJ)已引用两码 → 照 BUS2001BEF 先例灌 0 学分
# 说明名占位:仅供互斥标记可解析,不计学分、不进任何池、picker 不露出。
BUS_EXCLUSION_PLACEHOLDERS = [
    {"id": "BUS1003BEF", "code": "BUS 1003BEF", "credits": 0, "category": "elective",
     "name": "Excluded combination of ENGL 1101AEF (no catalog entry; official "
             "title: Introduction to Business English 基礎商業英語)"},
    {"id": "BUS1004BEF", "code": "BUS 1004BEF", "credits": 0, "category": "elective",
     "name": "Excluded combination of ENGL 1101AEF (no catalog entry; official "
             "title: Essential Business Communications 商業英語傳意概念)"},
]

COURSES = [
    {"id":"COMP1080SEF","code":"COMP 1080SEF","name":"Introduction to Computer Programming","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Fundamental programming concepts using Python."},
    {"id":"IT1020SEF","code":"IT 1020SEF","name":"Computing Fundamentals","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Introduction to computer systems, hardware, software, and basic IT concepts."},
    {"id":"MATH1410SEF","code":"MATH 1410SEF","name":"Algebra and Calculus","credits":3,"category":"core","year":1,"semester":"autumn","prerequisites":[],"description":"Mathematical foundations including linear algebra, differential and integral calculus."},
    {"id":"ENGL1101AEF","code":"ENGL 1101AEF","name":"University English: Reading and Writing","credits":3,"category":"english","year":1,"semester":"autumn","prerequisites":[],"description":"Academic English reading and writing skills for university-level coursework."},
    {"id":"UNI1002ABW","code":"UNI 1002ABW","name":"University Core Values","credits":2,"category":"university-core","year":1,"semester":"autumn","prerequisites":[],"description":"Introduction to university core values and academic integrity."},
    {"id":"UNI1012ABW","code":"UNI 1012ABW","name":"Social Responsibilities","credits":1,"category":"university-core","year":1,"semester":"autumn","prerequisites":[],"description":"Understanding social responsibilities and civic engagement."},
    {"id":"COMP2090SEF","code":"COMP 2090SEF","name":"Data Structures, Algorithms & Problem Solving","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":["COMP1080SEF"],"description":"Advanced data structures and algorithms for efficient problem solving."},
    {"id":"IT1030SEF","code":"IT 1030SEF","name":"Introduction to Internet Application Development","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Web development fundamentals including HTML, CSS, and JavaScript."},
    {"id":"STAT1510SEF","code":"STAT 1510SEF","name":"Probability & Distributions","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Probability theory and statistical distributions."},
    {"id":"STAT2610SEF","code":"STAT 2610SEF","name":"Data Analytics with Applications","credits":3,"category":"core","year":1,"semester":"spring","prerequisites":[],"description":"Introduction to data analytics methods and tools."},
    {"id":"ENGL1202EEF","code":"ENGL 1202EEF","name":"University English: Listening and Speaking","credits":3,"category":"english","year":1,"semester":"spring","prerequisites":[],"description":"Academic English listening and speaking skills."},
    {"id":"COMP2020SEF","code":"COMP 2020SEF","name":"Java Programming Fundamentals","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Object-oriented programming with Java."},
    {"id":"COMP2640SEF","code":"COMP 2640SEF","name":"Discrete Mathematics","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Discrete mathematical structures for computer science."},
    {"id":"MATH2150SEF","code":"MATH 2150SEF","name":"Linear Algebra","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Advanced linear algebra concepts."},
    {"id":"STAT2510SEF","code":"STAT 2510SEF","name":"Statistical Data Analysis","credits":3,"category":"core","year":2,"semester":"autumn","prerequisites":[],"description":"Statistical methods for data analysis."},
    {"id":"COMP2030SEF","code":"COMP 2030SEF","name":"Intermediate Java Programming & UI Design","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Advanced Java programming and user interface design."},
    {"id":"IT2900SEF","code":"IT 2900SEF","name":"Human Computer Interaction & UX Design","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Principles of human-computer interaction and user experience design."},
    {"id":"STAT2520SEF","code":"STAT 2520SEF","name":"Applied Statistical Methods","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Applied statistical methods for real-world problems."},
    {"id":"STAT2630SEF","code":"STAT 2630SEF","name":"Big Data Analytics with Applications","credits":3,"category":"core","year":2,"semester":"spring","prerequisites":[],"description":"Big data technologies and analytics applications."},
    {"id":"UNI2002BEW","code":"UNI 2002BEW","name":"Effective Communication and Teamwork","credits":3,"category":"university-core","year":2,"semester":"spring","prerequisites":[],"description":"Communication and teamwork skills for professional environments."},
    {"id":"COMP3200SEF","code":"COMP 3200SEF","name":"Database Management","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Database design, SQL, and database management systems."},
    {"id":"COMP3500SEF","code":"COMP 3500SEF","name":"Software Engineering","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Software engineering principles and practices."},
    {"id":"STAT3660SEF","code":"STAT 3660SEF","name":"SAS Programming","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Statistical analysis using SAS software."},
    {"id":"COMP3130SEF","code":"COMP 3130SEF","name":"Mobile Application Programming","credits":3,"category":"core","year":3,"semester":"autumn","prerequisites":[],"description":"Mobile app development for iOS and Android platforms."},
    {"id":"ELEC3050SEF","code":"ELEC 3050SEF","name":"Computer Networking","credits":3,"category":"elective","year":3,"semester":"autumn","prerequisites":[],"description":"Computer network fundamentals and protocols."},
    {"id":"COMP3510SEF","code":"COMP 3510SEF","name":"Software Project Management","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":["COMP3500SEF"],"description":"Project management methodologies for software development."},
    {"id":"COMP3920SEF","code":"COMP 3920SEF","name":"Machine Learning","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Machine learning algorithms and applications."},
    {"id":"STAT3110SEF","code":"STAT 3110SEF","name":"Time Series Analysis & Forecasting","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Time series analysis and forecasting methods."},
    {"id":"COMP4820SEF","code":"COMP 4820SEF","name":"Data Mining And Analytics","credits":3,"category":"core","year":3,"semester":"spring","prerequisites":[],"description":"Data mining techniques and analytics."},
    {"id":"COMP4630SEF","code":"COMP 4630SEF","name":"Distributed Systems & Parallel Computing","credits":3,"category":"elective","year":3,"semester":"spring","prerequisites":[],"description":"Distributed systems and parallel computing concepts."},
    {"id":"MATH4950SEF","code":"MATH 4950SEF","name":"Professional Placement","credits":3,"category":"elective","year":3,"semester":"summer","prerequisites":[],"description":"Professional work placement in data science industry."},
    {"id":"COMP3810SEF","code":"COMP 3810SEF","name":"Server-side Technologies and Cloud Computing","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Server-side development and cloud computing platforms."},
    {"id":"COMP4330SEF","code":"COMP 4330SEF","name":"Advanced Programming & AI Algorithms","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Advanced AI algorithms and programming techniques."},
    {"id":"COMP4610SEF","code":"COMP 4610SEF","name":"Data Science Project","credits":6,"category":"project","year":4,"semester":"autumn","prerequisites":[],"description":"Capstone project in data science."},
    {"id":"COMP4930SEF","code":"COMP 4930SEF","name":"Deep Learning","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":[],"description":"Deep learning and neural networks."},
    {"id":"COMP4210SEF","code":"COMP 4210SEF","name":"Advanced Database & Data Warehousing","credits":3,"category":"core","year":4,"semester":"autumn","prerequisites":["COMP3200SEF"],"description":"Advanced database systems and data warehousing."},
    {"id":"ELEC4310SEF","code":"ELEC 4310SEF","name":"Blockchain Technologies","credits":3,"category":"elective","year":4,"semester":"autumn","prerequisites":[],"description":"Blockchain technology and applications."},
    {"id":"UNI3002BEW","code":"UNI 3002BEW","name":"Entrepreneurial Mindset and Leadership for Sustainability","credits":3,"category":"university-core","year":4,"semester":"autumn","prerequisites":[],"description":"Entrepreneurship and leadership skills."},
    {"id":"ELEC3250SEF","code":"ELEC 3250SEF","name":"Computer & Network Security","credits":3,"category":"elective","year":4,"semester":"spring","prerequisites":["ELEC3050SEF"],"description":"Computer and network security principles."},
    {"id":"COMP4600SEF","code":"COMP 4600SEF","name":"Advanced Topics in Data Mining","credits":3,"category":"core","year":4,"semester":"spring","prerequisites":[],"description":"Advanced topics in data mining and knowledge discovery."},
    {"id":"ELEC4710SEF","code":"ELEC 4710SEF","name":"Digital Forensics","credits":3,"category":"elective","year":4,"semester":"spring","prerequisites":[],"description":"Digital forensics investigation techniques."},
]


def _spaced_code(cid: str) -> str:
    r"""裸码兜底名:字母与数字之间加空格。三位数码(GIP100BEF)同样成立
    (批次 5 修复:旧 `\d{4}` 正则漏网,三位码得不到空格、也永远匹配不上
    课名回填层的 WHERE 模式)。"""
    return re.sub(r"^([A-Z]{2,5})(\d{3,4})", r"\1 \2", cid)


async def apply_existing_row_fixes(conn) -> dict:
    """存量行修正层(批次 5):对 courses 表已存在的行做三类显式 UPDATE。

    为什么必须有(坑 11/12,azure-deploy-method memory):本脚本所有 INSERT
    都是 ON CONFLICT DO NOTHING + existing_ids 跳过,v1.11 REST 导入时代的
    预存行会永远绕过 INSERT 路径的学分/课名裁定 —— prod 曾因此残留 9 门学分
    错(GIP100/101/200/300/400=0、COUN4008=6、SOCI4004/SOSC2002/POLS4009=3,
    官方值早已在 ADDITION_CREDITS/POOL_SEED_CREDITS 里)+ 裸码脏名,靠手工
    UPDATE 收掉。本层让 seed 重跑可重现 prod 终态。

    顺序:补池学分(官方 advice 行众数)→ CREDIT_FIXES(人工裁定)最后跑,
    与前两本字典无键冲突(CI 可证),若有冲突人工裁定胜。
    """
    # 课名回填:裸码课(空格/不空格裸码,或名字混进 Wingdings 私用区字符的
    # 脏行)换成官方 advice sheet 标题列。只动裸码/脏码行,不覆盖任何真名
    # (catalogue/GE/手工表)。
    names_fixed = 0
    for cid, name in COURSE_NAME_BACKFILL.items():
        res = await conn.execute(
            "UPDATE courses SET name = $1 WHERE id = $2"
            " AND (name ~ $3 OR name ~ $4)",
            name, cid,
            r"^[A-Z]{2,5} ?[0-9]{3,4}[A-Z]{3}$",
            f"[{chr(0xE000)}-{chr(0xF8FF)}]",  # Wingdings 对勾等私用区脏字符(PDF 提取伪影,坑 12)
        )
        names_fixed += int(res.split()[-1])

    # 补池学分对存量行显式 UPDATE(批次 5 新增):INSERT 路径早已用这两本
    # 字典,此前存量行吃不到 → prod 9 门学分残留的根因。
    pool_credit_fixed = 0
    for table in (ADDITION_CREDITS, POOL_SEED_CREDITS):
        for cid, cr in table.items():
            res = await conn.execute(
                "UPDATE courses SET credits = $1 WHERE id = $2 AND credits <> $1",
                cr, cid,
            )
            pool_credit_fixed += int(res.split()[-1])

    # CREDIT_FIXES(复核报告第五节,16 门人工裁定)。
    credit_fixed = 0
    for cid, cr in CREDIT_FIXES.items():
        res = await conn.execute(
            "UPDATE courses SET credits = $1 WHERE id = $2 AND credits <> $1",
            cr, cid,
        )
        credit_fixed += int(res.split()[-1])
    return {
        "names_fixed": names_fixed,
        "pool_credit_fixed": pool_credit_fixed,
        "credit_fixed": credit_fixed,
    }


async def seed():
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return

    conn = await asyncpg.connect(database_url)

    try:
        # Insert courses
        inserted = 0
        for c in COURSES:
            try:
                await conn.execute(
                    """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT (id) DO NOTHING""",
                    c["id"], c["code"], c["name"], c["credits"], c["category"],
                    c["year"], c["semester"], str(c["prerequisites"]), c["description"],
                )
                inserted += 1
            except Exception as e:
                print(f"  skip {c['id']}: {e}")

        # Insert GE courses (real 2026/27 pool from ge_courses.py — gives each
        # a courses-table id so PUT /courses/progress can mark them, and the
        # graduation calc can count them toward general-ed). GE courses are
        # cross-programme, so year/semester carry sentinel defaults that the
        # planner's by-year grouping ignores.
        ge_inserted = 0
        for g in GE_COURSES:
            gid = g["code"].replace(" ", "")
            try:
                await conn.execute(
                    """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT (id) DO NOTHING""",
                    gid, g["code"], g["name_en"], 3, "general-ed",
                    0, "any", "[]", f"{g['name_zh']} · {g['field']}",
                )
                ge_inserted += 1
            except Exception as e:
                print(f"  skip GE {gid}: {e}")

        # Insert rule-referenced courses missing from the table (T34): every
        # course listed in PROGRAMME_RULES needs a courses-table row, or
        # _compute_graduation silently skips it (course_rows lookup fails).
        # Name still prefers course_catalogue (official tree, with display
        # names). Credits priority was CORRECTED 2026-08-19 (复核报告第五节):
        # the catalogue [学分:N] markers are polluted by PDF page numbers, so
        # RCC (RULE_COURSE_CREDITS, PDF-parsed per course) now wins over
        # catalogue; CREDIT_FIXES (human-adjudicated) beats both. Note
        # MATH1410SEF carries a known RCC dirty value (STAMJ=2) but is always
        # inserted first by the DSAI hand table above, so the existing_ids
        # check keeps the RCC chain away from it.
        # Public PDFs carry no term data, so year defaults to the course-code
        # LEVEL (HKMU convention: 1xxx→Y1 … 4xxx→Y4) and semester to autumn —
        # the planner's year tabs filter on course.year, so year=0 sentinels
        # would render every new programme as 「无课程」. Users can move any
        # course via the schedule picker (planned placement overrides).
        def _level_year(cid):
            m = re.search(r"\d", cid)
            return min(int(m.group()), 4) if m and 1 <= int(m.group()) <= 4 else 4

        existing_ids = {r["id"] for r in await conn.fetch("SELECT id FROM courses")}
        cat_rows = await conn.fetch(
            """SELECT DISTINCT REPLACE(course_code, ' ', '') AS cid,
                      display_name, credits
               FROM course_catalogue"""
        )
        catalogue = {r["cid"]: (r["display_name"], r["credits"]) for r in cat_rows}
        rules_inserted = 0
        rules_missing_name = 0
        for code, entry in PROGRAMME_RULES.items():
            for cat_key, cat in entry["categories"].items():
                if cat.get("pool") == "ge":
                    continue  # GE pool resolves dynamically via ge_courses_for
                for cid in cat["courses"]:
                    if cid in existing_ids:
                        continue
                    name = catalogue.get(cid, (None, None))[0]
                    # CREDIT_FIXES(人工裁定)> RCC > catalogue(标记被页码污染) > 3
                    credits = CREDIT_FIXES.get(cid)
                    if credits is None:
                        credits = RULE_COURSE_CREDITS.get(code, {}).get(cat_key, {}).get(cid)
                    if credits is None:
                        credits = catalogue.get(cid, (None, None))[1]
                    if credits is None:
                        credits = 3
                    if not name:
                        # No official display name anywhere — use the spaced
                        # code so the UI at least shows a stable identifier.
                        name = _spaced_code(cid)
                        rules_missing_name += 1
                    try:
                        await conn.execute(
                            """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                               ON CONFLICT (id) DO NOTHING""",
                            cid, name, name, credits, cat_key,
                            _level_year(cid), "autumn", "[]",
                            f"{entry['name']['en']} · {cat_key}",
                        )
                        rules_inserted += 1
                    except Exception as e:
                        print(f"  skip rule course {cid}: {e}")

        # ── 批次 2 补池(选课数据修复,advice sheet 缺课 78 课次)─────────────
        # GIP100-400BEF 等:官方 Course Advice Sheet 列出、Requirements PDF 规则
        # 没覆盖的课。courses 行要进表(_compute_graduation 的 course_rows 查找),
        # 学分取官方行值(GIP 类 0);名称优先官方标题列。幂等:ON CONFLICT DO
        # NOTHING + existing_ids 跳过,重跑零重复(生产灌库脚本要求)。
        existing_ids = {r["id"] for r in await conn.fetch("SELECT id FROM courses")}
        additions_inserted = 0
        for prog_code, cats in POOL_ADDITIONS.items():
            entry_name = PROGRAMME_RULES.get(prog_code, {}).get("name", {}).get("en", prog_code)
            for cat_key, courses in cats.items():
                for cid in courses:
                    if cid in existing_ids:
                        continue
                    name = COURSE_NAME_BACKFILL.get(cid) or catalogue.get(cid, (None, None))[0]
                    if not name:
                        name = _spaced_code(cid)
                    credits = ADDITION_CREDITS.get(cid)
                    if credits is None:
                        credits = CREDIT_FIXES.get(cid)
                    if credits is None:
                        credits = catalogue.get(cid, (None, None))[1]
                    if credits is None:
                        credits = 3
                    try:
                        await conn.execute(
                            """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                               ON CONFLICT (id) DO NOTHING""",
                            cid, name, name, credits, cat_key,
                            _level_year(cid), "autumn", "[]",
                            f"{entry_name} · {cat_key} · advice sheet",
                        )
                        existing_ids.add(cid)
                        additions_inserted += 1
                    except Exception as e:
                        print(f"  skip addition {cid}: {e}")

        # ── 批次 3 骨架实体种池(BSSCHWSJ 类)──────────────────────────────────
        # 无 Requirements 规则的实体,课池来自官方 advice 行(PROGRAMME_POOL_SEED),
        # courses 行同源进表;学分取官方行值(POOL_SEED_CREDITS)。幂等同上。
        seed_inserted = 0
        for prog_code, cats in PROGRAMME_POOL_SEED.items():
            entry = PROGRAMMES.get(prog_code) or PROGRAMME_RULES.get(prog_code) or {}
            entry_name = entry.get("name", {}).get("en", prog_code)
            for cat_key, courses in cats.items():
                for cid in courses:
                    if cid in existing_ids:
                        continue
                    name = COURSE_NAME_BACKFILL.get(cid) or catalogue.get(cid, (None, None))[0]
                    if not name:
                        name = _spaced_code(cid)
                    credits = POOL_SEED_CREDITS.get(cid)
                    if credits is None:
                        credits = ADDITION_CREDITS.get(cid)
                    if credits is None:
                        credits = CREDIT_FIXES.get(cid)
                    if credits is None:
                        credits = catalogue.get(cid, (None, None))[1]
                    if credits is None:
                        credits = 3
                    try:
                        await conn.execute(
                            """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                               ON CONFLICT (id) DO NOTHING""",
                            cid, name, name, credits, cat_key,
                            _level_year(cid), "autumn", "[]",
                            f"{entry_name} · {cat_key} · advice sheet",
                        )
                        existing_ids.add(cid)
                        seed_inserted += 1
                    except Exception as e:
                        print(f"  skip pool-seed {cid}: {e}")
        print(f"  pool-seed inserted: {seed_inserted}")

        # ── 批次 4 规则层课(选课数据修复,programme_rules_extra.py)──────────
        # MHFA 自修课(NURS1050 英文/中文班,2025/26+ Y1 入学必修):官方 yr
        # Note/Requirements §1.1.2 从未给学分(不出现在学分表)→ 0 学分是基于
        # 缺席的推断,见 RULES_EVIDENCE["mhfa-nurs1050"]。GCST3005ABF = GCS
        # Stream 的 Summer Immersive 单门必修 6cr(Requirements T2)。
        # 幂等:existing_ids 跳过 + ON CONFLICT DO NOTHING。
        BATCH4_COURSES = [
            {"id": "NURS1050NEF", "code": "NURS 1050NEF", "credits": 0,
             "category": "mhfa", "name": "Mental Health First Aid Training"},
            {"id": "NURS1050NCF", "code": "NURS 1050NCF", "credits": 0,
             "category": "mhfa", "name": "Mental Health First Aid Training"},
            {"id": "GCST3005ABF", "code": "GCST 3005ABF", "credits": 6,
             "category": "core", "name": "Summer Immersive Programme"},
            # BUS2001BEF:多份商院 sheet 的 BUS 2000BEF 行 Excluded combination
            # 列出现(BBAHMGTJ1/BBAHIHAMJ1 p1),官方码但任何目录/年表均无独立
            # 课行(无课名无学分)→ 0 学分 + 说明名,仅供互斥标记用,不计学分。
            # 对比:BUS1003/1004BEF 批次 5 人眼定性后同样占位(见文件头
            # BUS_EXCLUSION_PLACEHOLDERS,依据 Excluded 引用 + 互斥组引用)。
            {"id": "BUS2001BEF", "code": "BUS 2001BEF", "credits": 0,
             "category": "elective",
             "name": "Excluded combination of BUS 2000BEF (no official course row)"},
        ]
        batch4_inserted = 0
        for c in BATCH4_COURSES:
            if c["id"] in existing_ids:
                continue
            try:
                await conn.execute(
                    """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT (id) DO NOTHING""",
                    c["id"], c["code"], c["name"], c["credits"], c["category"],
                    1, "any", "[]", f"批次4规则层 · {c['category']}",
                )
                existing_ids.add(c["id"])
                batch4_inserted += 1
            except Exception as e:
                print(f"  skip batch4 {c['id']}: {e}")
        print(f"  batch4 rule courses inserted: {batch4_inserted}")

        # ── 批次 5:选修目录收尾 + 互斥引用占位(见文件头两个常量的依据)──────
        batch5_inserted = 0
        for c in ELECTIVE_CATALOG_IMPORT + BUS_EXCLUSION_PLACEHOLDERS:
            if c["id"] in existing_ids:
                continue
            try:
                await conn.execute(
                    """INSERT INTO courses (id, code, name, credits, category, year, semester, prerequisites, description)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                       ON CONFLICT (id) DO NOTHING""",
                    c["id"], c["code"], c["name"], c["credits"], c["category"],
                    _level_year(c["id"]), "any", "[]",
                    "批次5 · UG选修目录条目(3cr 版 p105-106)" if c["credits"]
                    else "批次5 · Excluded Combination 引用占位(0 学分,不计学分)",
                )
                existing_ids.add(c["id"])
                batch5_inserted += 1
            except Exception as e:
                print(f"  skip batch5 {c['id']}: {e}")
        print(f"  batch5 elective-catalog/placeholder courses inserted: {batch5_inserted}")

        # 存量行修正层(批次 5,坑 11/12):裸码课名回填 + 补池学分 + 人工裁定
        # 学分,见 apply_existing_row_fixes 的 docstring。
        fixes = await apply_existing_row_fixes(conn)
        names_fixed = fixes["names_fixed"]
        credit_fixed = fixes["credit_fixed"]
        print(f"  existing-row fixes: {fixes['pool_credit_fixed']} pool credits, "
              f"{names_fixed} names, {credit_fixed} adjudicated credits")

        # Create test user
        test_pw = pwd_ctx.hash("test123456")
        try:
            await conn.execute(
                """INSERT INTO users (username, password_hash, nickname, student_id, identity)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (username) DO NOTHING""",
                "testuser", test_pw, "Test User", "12345678", "student",
            )
        except Exception as e:
            print(f"  skip test user: {e}")

        # Verify
        count = await conn.fetchval("SELECT COUNT(*) FROM courses")
        ge_count = await conn.fetchval("SELECT COUNT(*) FROM courses WHERE category = 'general-ed'")
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        print(f"Seeded {inserted} courses + {ge_inserted} GE + {rules_inserted} rule courses "
              f"+ {additions_inserted} advice-sheet additions ({names_fixed} names backfilled, "
              f"{credit_fixed} credit fixes) "
              f"({count} in DB, {ge_count} GE), {user_count} users")

    finally:
        await conn.close()


if __name__ == "__main__":
    # Ensure schema exists before seeding. Idempotent (CREATE TABLE IF NOT
    # EXISTS) so it's safe on both a fresh CI/dev DB and an existing prod DB.
    # Without this, running on an empty DB fails with "relation courses does
    # not exist" — which is what broke the deploy.yml CI gate.
    asyncio.run(init_db())
    asyncio.run(seed())
