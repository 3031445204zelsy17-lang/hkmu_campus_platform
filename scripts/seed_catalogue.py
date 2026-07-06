"""Seed read-only course catalogue from HKMU's public programme-course tree.

Parses ``docs/ops/选课选课/skill.md`` (an export of HKMU's official Programme
Requirements PDFs) into two read-only reference tables:

  * ``programmes_catalogue`` — one row per programme (~107-115), with
    ``has_full_planning`` derived from ``PROGRAMMES`` membership and trilingual
    names overlaid for the tech-school programmes that already live there.
  * ``course_catalogue`` — one row per (programme, group, course) leaf.

The catalogue is intentionally separate from the planning ``courses`` table:
public PDFs lack term / prerequisite / per-category credit info, so these rows
cannot drive graduation math — they are a browse-only "official course list".

Idempotent: a single transaction ``DELETE`` then bulk ``INSERT``. Re-run after
refreshing skill.md to regenerate.

Use ``--check`` to parse + print stats WITHOUT touching the database (parser
validation / CI gate). Any parse failure exits non-zero.
"""
import asyncio
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.data.programmes import PROGRAMMES  # noqa: E402  — pure dict, safe to import
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

SKILL_MD = os.path.join(
    os.path.dirname(__file__), "..", "docs", "ops", "选课选课", "skill.md"
)

# ── Line classification ───────────────────────────────────────────────────────
# Tree shape (single-pass, depth implied by leading pipes + trailing markers):
#   HKMU                         (root)
#   +-- School Name/             (school:  no leading pipe, ends '/')
#   |   +-- Prog Name (CODE)/    (programme: leading pipe, '(CODE)/')
#   |   |   +-- Group Name/      (group:   ends '/', no '[代码:]', no '(CODE)/')
#   |   |   |   +-- Name [代码: X] [学分: N]   (course leaf)
_COURSE_RE = re.compile(r"\[代码: (.+?)\]\s*\[学分: (\d+)\]")
_PROG_RE = re.compile(r"^\|\s+\+-- .+\(([A-Z0-9]{4,})\)/\s*$")
_SCHOOL_RE = re.compile(r"^\+-- (.+)/\s*$")
_PROGCLOSE_RE = re.compile(r"\([A-Z0-9]{4,}\)/\s*$")

_SCHOOL_ORDER = {
    "Lee Shau Kee School of Business and Administration": 1,
    "School of Arts and Social Sciences": 2,
    "School of Education and Languages": 3,
    "School of Nursing and Health Sciences": 4,
    "School of Science and Technology": 5,
}

# First-match-wins (order-sensitive: 'university core' before 'core').
# (substring_in_lowered_group, canonical_bucket, bucket_order)
_BUCKET_RULES = [
    ("university core", "university-core", 10),
    ("language enhancement", "language", 20),
    ("english", "language", 20),
    ("language", "language", 20),
    ("general education", "general-ed", 30),
    ("purpose-designed", "general-ed", 30),
    ("foundation", "foundation", 40),
    ("core", "core", 50),
    ("concentration", "concentration", 60),
    ("major", "concentration", 60),
    ("option", "elective", 70),
    ("outside discipline", "elective", 70),
    ("elective", "elective", 70),
    ("synergy", "synergy", 80),
    ("project", "capstone", 90),
    ("applied research", "capstone", 90),
    ("work-based", "capstone", 90),
    ("honours thesis", "capstone", 90),
    ("dissertation", "capstone", 90),
    ("practicum", "capstone", 90),
    ("clinical", "capstone", 90),
    ("internship", "capstone", 90),
    ("immersion", "immersion", 100),
    ("immitation", "immersion", 100),  # source typo
]


def canonical_bucket(official_group: str) -> tuple[str, int]:
    low = official_group.lower()
    for sub, bucket, order in _BUCKET_RULES:
        if sub in low:
            return bucket, order
    return "other", 110


def clean_name(raw_name: str, code_token: str) -> str:
    """Strip leaked PDF artifacts; fall back to the code when unrecoverable."""
    name = raw_name
    name = re.sub(r"^\d{1,2}\s+", "", name)  # stray leading digit ('3 ')
    name = re.sub(r"\s*\d*\s*\d-credit-unit system.*$", "", name)
    name = re.sub(r"\s*\d*CRU_[A-Z_]+_V\d+ Page \d+ of.*$", "", name)
    name = re.sub(r"\s*\d{4}\s+(Autumn|Spring|Summer)\s+\d+\..*$", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    if not name or len(name) > 200 or re.match(r"^[A-Z]{2,4}\s+[A-Z]\d", name):
        return code_token
    return name


def detect_code_system(code_token: str) -> str:
    parts = code_token.split(" ", 1)
    rest = parts[1] if len(parts) > 1 else code_token
    return "3CRU" if rest[:1].isdigit() else "5credit"


def _after_plus(line: str) -> str:
    m = re.search(r"\+--\s+(.+)", line)
    return m.group(1) if m else ""


def parse_skill_md(path: str):
    """Return (programmes dict, ordered code list, courses list, failures list)."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    start = next((i for i, ln in enumerate(lines) if ln.strip() == "HKMU"), 0)

    programmes: dict[str, dict] = {}
    order: list[str] = []
    courses: list[dict] = []
    failures: list[tuple] = []

    state = {
        "school": "",
        "school_order": 99,
        "prog_code": None,
        "group": "Uncategorised",
    }

    for idx in range(start, len(lines)):
        line = lines[idx].rstrip()
        s = line.strip()
        if not s or s == "HKMU":
            continue
        if not (line.startswith("|") or line.startswith("+")):
            continue  # markdown commentary above/around the tree

        # COURSE first: a course row has leading pipes but is distinguished by
        # the [代码:]/[学分:] tokens (must precede the GROUP fallback).
        mc = _COURSE_RE.search(line)
        if mc:
            code_token = mc.group(1).strip()
            credits = int(mc.group(2))
            if state["prog_code"] is None:
                failures.append((idx + 1, "course outside programme", line[:80]))
                continue
            before = line.split("[代码:")[0]
            name_raw = re.sub(r"^[| +\-]+", "", before).strip()
            bucket, border = canonical_bucket(state["group"])
            courses.append({
                "programme_code": state["prog_code"],
                "school": state["school"],
                "official_group": state["group"],
                "canonical_bucket": bucket,
                "bucket_order": border,
                "course_code": code_token,
                "course_code_sort": code_token.replace(" ", ""),
                "display_name": clean_name(name_raw, code_token),
                "raw_name": name_raw[:500],
                "credits": credits,
                "code_system": detect_code_system(code_token),
                "source_line_no": idx + 1,
            })
            continue

        mp = _PROG_RE.match(line)
        if mp:
            code = mp.group(1)
            prog_name = re.sub(r"\s*\([A-Z0-9]{4,}\)/?\s*$", "", _after_plus(line)).strip()
            if code not in programmes:
                programmes[code] = {
                    "programme_code": code,
                    "programme_name": prog_name or code,
                    "school": state["school"],
                    "school_order": state["school_order"],
                    "prog_order": len(order),
                }
                order.append(code)
            state["prog_code"] = code
            state["group"] = "Uncategorised"
            continue

        ms = _SCHOOL_RE.match(line)
        if ms:
            state["school"] = ms.group(1).strip()
            state["school_order"] = _SCHOOL_ORDER.get(state["school"], 99)
            state["prog_code"] = None  # back at school level
            continue

        # GROUP: trailing '/', contains '+--', no course tokens, no '(CODE)/'.
        if (
            line.endswith("/")
            and "+--" in line
            and "[代码:" not in line
            and not _PROGCLOSE_RE.search(line)
        ):
            g = re.sub(r"^[| +\-]+", "", _after_plus(line)).rstrip("/").strip()
            g = g.split("|")[-1].strip()
            state["group"] = g or "Uncategorised"
            continue
        # else: tree connector line ('|', '|   |') — skip silently.

    # Aggregate per-programme stats + overlay trilingual / has_full_planning.
    counts = Counter(c["programme_code"] for c in courses)
    sys_by_prog: dict[str, Counter] = defaultdict(Counter)
    for c in courses:
        sys_by_prog[c["programme_code"]][c["code_system"]] += 1
    for code, prog in programmes.items():
        prog["course_count"] = counts.get(code, 0)
        ctr = sys_by_prog[code]
        prog["source_code_system"] = ctr.most_common(1)[0][0] if ctr else None
        known = PROGRAMMES.get(code)
        if known:
            names = known.get("name", {})
            prog["name_zh_cn"] = names.get("zh-CN")
            prog["name_zh_tw"] = names.get("zh-TW")
            prog["has_full_planning"] = not known.get("coming_soon", False)
        else:
            prog["name_zh_cn"] = None
            prog["name_zh_tw"] = None
            prog["has_full_planning"] = False

    return programmes, order, courses, failures


def print_stats(programmes, order, courses, failures):
    print("=== seed_catalogue parse stats ===")
    print(f"programmes: {len(programmes)} unique")
    print(f"courses:    {len(courses)}")
    print(f"failures:   {len(failures)}")
    print(f"code_systems: {dict(Counter(c['code_system'] for c in courses))}")
    print(f"buckets:      {dict(Counter(c['canonical_bucket'] for c in courses))}")
    school_ctr = Counter(p["school"] for p in programmes.values())
    print(f"schools ({len(school_ctr)}):")
    for sch, n in sorted(school_ctr.items(), key=lambda kv: programmes[next(c for c, p in programmes.items() if p['school'] == kv[0])]['school_order']):
        print(f"    {n:3d}  {sch}")
    print("top 8 programmes by course_count:")
    for p in sorted(programmes.values(), key=lambda p: -p["course_count"])[:8]:
        print(f"    {p['programme_code']:14s} {p['course_count']:4d}  {p['programme_name'][:54]}")
    full = [c for c, p in programmes.items() if p["has_full_planning"]]
    print(f"has_full_planning=true: {full}")
    if failures:
        print("FAILURES (first 15):")
        for ln, why, txt in failures[:15]:
            print(f"    L{ln} {why}: {txt}")


async def seed(programmes, order, courses):
    import asyncpg  # lazy import keeps --check DB-free

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            await conn.execute("DELETE FROM course_catalogue")
            await conn.execute("DELETE FROM programmes_catalogue")

            prog_rows = [
                (
                    programmes[c]["programme_code"], programmes[c]["programme_name"],
                    programmes[c]["name_zh_cn"], programmes[c]["name_zh_tw"],
                    programmes[c]["school"], programmes[c]["school_order"],
                    programmes[c]["prog_order"], programmes[c]["course_count"],
                    programmes[c]["has_full_planning"], programmes[c]["source_code_system"],
                )
                for c in order
            ]
            await conn.executemany(
                """INSERT INTO programmes_catalogue
                   (programme_code, programme_name, name_zh_cn, name_zh_tw, school,
                    school_order, prog_order, course_count, has_full_planning,
                    source_code_system)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                prog_rows,
            )

            course_rows = [
                (
                    c["programme_code"], c["school"], c["official_group"],
                    c["canonical_bucket"], c["bucket_order"], c["course_code"],
                    c["course_code_sort"], c["display_name"], c["raw_name"],
                    c["credits"], c["code_system"], c["source_line_no"],
                )
                for c in courses
            ]
            BATCH = 500
            for i in range(0, len(course_rows), BATCH):
                await conn.executemany(
                    """INSERT INTO course_catalogue
                       (programme_code, school, official_group, canonical_bucket,
                        bucket_order, course_code, course_code_sort, display_name,
                        raw_name, credits, code_system, source_line_no)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                       ON CONFLICT (programme_code, course_code, official_group)
                       DO NOTHING""",
                    course_rows[i:i + BATCH],
                )

        pc = await conn.fetchval("SELECT COUNT(*) FROM programmes_catalogue")
        cc = await conn.fetchval("SELECT COUNT(*) FROM course_catalogue")
        print(f"Seeded {pc} programmes, {cc} courses into catalogue.")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    if not os.path.exists(SKILL_MD):
        print(f"ERROR: skill.md not found at {SKILL_MD}")
        sys.exit(2)

    programmes, order, courses, failures = parse_skill_md(SKILL_MD)
    print_stats(programmes, order, courses, failures)

    if failures:
        print("\nAborting: parse failures detected (see above).")
        sys.exit(1)

    if check_only:
        print("\n--check: DB not touched. OK.")
        sys.exit(0)

    # Ensure schema exists (idempotent) then seed.
    from app.database import init_db  # noqa: E402 — lazy so --check stays DB-free
    asyncio.run(init_db())
    sys.exit(asyncio.run(seed(programmes, order, courses)))
