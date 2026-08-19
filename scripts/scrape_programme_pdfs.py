#!/usr/bin/env python3
"""Scrape HKMU undergraduate programme-requirements PDFs → categories JSON.

Pipeline (verified 2026-08-13 on DSAI, BSCHDSAIJ):
  1. Playwright (real Chrome) navigates a /REG/ HTML page to pass Cloudflare.
  2. fetch() the programme PDF in-page (same-origin, credentials) → bytes.
  3. pdfplumber parses text → categories dict (Table headings + course rows).

Usage:
  python scripts/scrape_programme_pdfs.py --code BSCHDSAIJ --school ST        # one programme
  python scripts/scrape_programme_pdfs.py --code BSCHDSAIJ --school ST --text # dump raw text (debug)
  python scripts/scrape_programme_pdfs.py --all                               # all 57 (Phase C)
  python scripts/scrape_programme_pdfs.py --from-text-dir scripts/out/hkmu_pr/text  # local reparse (T32)
  python scripts/scrape_programme_pdfs.py --audit scripts/out/programmes_raw.json   # sanity table

PDF URL pattern: https://www.hkmu.edu.hk/REG/reg_grad/PR/3CRU_FTU_<school>_<code>.pdf
  schools: AS (Arts & Social Sciences), BA (Business & Administration),
           EL (Education & Languages), NHS (Nursing & Health Sciences),
           ST (Science & Technology).

⚠️ Network: HKMU is behind Cloudflare AND some local networks/VPNs intermittently
  throw ERR_TUNNEL_CONNECTION_FAILED (verified 2026-08-13: DSAI 200 OK, but BA/AS
  PDFs failed on the same warm-up session). The script retries with backoff; if
  failures persist, switch network (mobile hotspot / HK or JP VPN node) — see
  memory [[vpn-azure-https-block]].

Parser: categories_from_text() handles the 5 schools' heading variants via an
  ordered first-match pattern list (see HEADING_PATTERNS) — T32. Local re-parse
  needs no Cloudflare pass:  --from-text-dir scripts/out/hkmu_pr/text
"""
import sys
import os
import io
import json
import argparse
import re
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

PDF_BASE = "https://www.hkmu.edu.hk/REG/reg_grad/PR/"
CF_WARMUP = "https://www.hkmu.edu.hk/REG/reg_ftae/GE/"  # any /REG/ HTML page passes CF

# 64 full-time undergraduate 3cru programmes (code, school). Sourced from the
# programme-requirements-3cru index (extracted 2026-08-13) + 2026-08-17 URL 探测
# 补齐 7 个索引漏收的(5 个社科 J 码 + 2 个护理高级文凭,PDF 直接存在于
# 3CRU_FTU_{school}_{code}.pdf 模式)。
PROGRAMMES = [
    # School of Science & Technology (ST)
    ("BASCHRAEJ", "ST"), ("BASCHTICJ", "ST"), ("BENGHBSEJ", "ST"), ("BENGHCEJ", "ST"),
    ("BENGHECEJ", "ST"), ("BSCHATSJ", "ST"), ("BSCHBEMJ", "ST"), ("BSCHBSBJ", "ST"),
    ("BSCHCCSJ", "ST"), ("BSCHCEF", "ST"), ("BSCHCMQSJ", "ST"), ("BSCHCOMPF", "ST"),
    ("BSCHCSJ", "ST"), ("BSCHDSAIJ", "ST"), ("BSCHESGMJ", "ST"), ("BSCHFTSJ", "ST"),
    ("BSCHSTAMJ", "ST"), ("BSCHSTEMJ", "ST"),
    # School of Arts & Social Sciences (AS)
    ("BAHCAMDJ", "AS"), ("BAHCLLJ", "AS"), ("BAHCWFAJ", "AS"), ("BAHELCJ", "AS"),
    ("BAHLTJ", "AS"), ("BAHNMIEJ", "AS"), ("BFAHAVEJ", "AS"), ("BFAHIDDAJ", "AS"),
    ("BSSCHPWSJ", "AS"),
    ("BSSCHAGSJ", "AS"), ("BSSCHECJ", "AS"), ("BSSCHJ", "AS"),
    ("BSSCHGCSJ", "AS"), ("BSSCHPAJ", "AS"),
    # Lee Shau Kee School of Business & Administration (BA)
    ("BAPHBMJ", "BA"), ("BBAHASMJ", "BA"), ("BBAHCGSJ", "BA"), ("BBAHFFTJ", "BA"),
    ("BBAHGBJ", "BA"), ("BBAHGMSMJ", "BA"), ("BBAHHRMJ", "BA"), ("BBAHIHAMJ", "BA"),
    ("BBAHMGTJ", "BA"), ("BBAHMKTJ", "BA"), ("BBAHPAJ", "BA"), ("BBAHRESJ", "BA"),
    ("BBAHSEMJ", "BA"), ("BBAHSRMJ", "BA"), ("BBAHSTHMJ", "BA"), ("BBAHWBJ", "BA"),
    # School of Education & Languages (EL)
    ("BEDELSEHJ", "EL"), ("BEDHACLSJ", "EL"), ("BEDHECEJ", "EL"), ("BEDHPCLSJ", "EL"),
    ("BLSEHJ", "EL"), ("BLSHACLSJ", "EL"), ("BLSHBSADJ", "EL"),
    # School of Nursing & Health Sciences (NHS)
    ("BNHGJ", "NHS"), ("BNHMJ", "NHS"), ("BSCHDRJ", "NHS"), ("BSCHMLSJ", "NHS"),
    ("BSCHPTJ", "NHS"), ("HDNGF", "NHS"), ("HDNMF", "NHS"),
]


# ── fetch (Playwright passes Cloudflare) ──────────────────────────────────────

def fetch_pdf_bytes(page, code, school, retries=4):
    """Fetch one programme PDF as bytes. Returns (bytes, None) or (None, error)."""
    url = f"{PDF_BASE}3CRU_FTU_{school}_{code}.pdf"
    for attempt in range(retries):
        try:
            res = page.evaluate("""async (url) => {
                const r = await fetch(url, {credentials:'include'});
                if (!r.ok) return {status: r.status};
                const buf = await r.arrayBuffer();
                return {bytes: Array.from(new Uint8Array(buf))};
            }""", url)
            if "bytes" in res:
                return bytes(res["bytes"]), None
            return None, f"HTTP {res.get('status')}"
        except Exception as e:
            # ERR_TUNNEL_CONNECTION_FAILED / CF jitter — backoff and retry
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return None, f"{type(e).__name__}: {e}"


# ── parse (pdfplumber) ────────────────────────────────────────────────────────

# Course code: "COMP 1080SEF", "IT 1020SEF", "UNI 1002ABW", "ENGL 1101AEF"
CODE_RE = re.compile(r"([A-Z]{2,5})\s?(\d{4}[A-Z]{2,3})")
# Course ROWS start with the code. Footnote/Notes prose embeds codes mid-line
# ("* Students who have completed CHEM 2034SEF is deemed…", "1. BIOL 3051SEF
# has been removed from Table 2…") and must not yield courses — so row
# detection is anchored at line start.
CODE_ROW_RE = re.compile(r"\s*([A-Z]{2,5})\s?(\d{4}[A-Z]{2,3})")
# Post-table footnote block ("Note:" / "Notes:"), swept into the last table's
# body otherwise (BASCHTICJ english gained 9 removed-course codes from it).
NOTES_RE = re.compile(r"(?m)^\s*Notes?\s*:")

# "Table N: <Category>" heading → our category key. Ordered FIRST-match list
# (T32): the 5 schools name their tables differently — AS "Elective courses in
# specific area", BA concentration tables, EL "Periphery Course", NHS
# "Theoretical Courses"/"Specialized Professional courses"/"Clinical
# Practicum", ST-STEAM menu electives. Order matters:
#   - university core/english MUST precede the generic core/elective patterns
#   - NHS "Theoretical courses (elective)" MUST precede bare "theoretical
#     courses" (= core)
# Non-credit-bearing extras (Global Immersion Programme) map to None → skipped.
HEADING_PATTERNS = [
    (re.compile(r"university\s+core", re.I), "university-core"),
    (re.compile(r"university\s+english", re.I), "english"),
    (re.compile(r"general\s+education", re.I), "general-ed"),
    (re.compile(r"theoretical\s+courses?\s*\(elective\)", re.I), "elective"),
    (re.compile(r"elective", re.I), "elective"),
    (re.compile(r"periphery", re.I), "elective"),
    (re.compile(r"synergy", re.I), "elective"),
    (re.compile(r"speciali[sz]ation", re.I), "elective"),  # choice menus (WBJ/ASMJ; GCSJ 用 s 拼写)
    (re.compile(r"clinical\s+practicum", re.I), "core"),
    (re.compile(r"practicum", re.I), "core"),
    (re.compile(r"specialized\s+professional", re.I), "core"),
    (re.compile(r"core\s+science", re.I), "core"),
    (re.compile(r"theoretical\s+courses?", re.I), "core"),
    (re.compile(r"concentration", re.I), "core"),
    (re.compile(r"core\s+strategy", re.I), "core"),
    (re.compile(r"mathematics", re.I), "core"),
    (re.compile(r"integrated\s+ste(?:a)?m", re.I), "core"),
    (re.compile(r"global\s+immersion", re.I), None),
    (re.compile(r"core\s+courses?", re.I), "core"),
]


def _heading_category(title):
    """First matching pattern wins; None → skip this table."""
    for rx, key in HEADING_PATTERNS:
        if rx.search(title):
            return key
    return None


# Cohort/entry sets. Some PDFs carry TWO complete requirement sets — EL e.g.
# pages 1-4 for the 2023/24 cohort and pages 5-8 for "in or after 2024/25";
# ST-STEAM/FTS print the NEWEST cohort first and the older one second. Every
# set opens with "N. Programme Requirement – Year 1 Entry" (numbering may
# restart or continue) and is preceded by a "Year 1 20XX/YY" admission marker.
# Position in the file is NOT reliable (both orders occur), so each Y1 section
# is scored by its nearest preceding admission year and the HIGHEST year wins;
# ties (same-cohort dual-stream docs like BSSCHPWSJ) go to the EARLIEST
# section, i.e. the primary/default stream. Docs with one set, or with no
# admission markers at all, degrade to the whole text / last section.
Y1_SECTION = re.compile(
    r"\n\s*\d+\.\s+Programme\s+Requirement\s*[–-]\s*Year\s+1\s+Entry", re.I)
YEAR1_COHORT = re.compile(r"Year\s+1\s+(20\d{2})/\d{2}")


def latest_cohort_text(text):
    heads = list(Y1_SECTION.finditer(text))
    if len(heads) <= 1:
        return text
    scored = []
    for h in heads:
        years = [int(m.group(1)) for m in YEAR1_COHORT.finditer(text[:h.start()])]
        scored.append((years[-1] if years else None, h.start()))
    dated = [(y, s) for y, s in scored if y is not None]
    if dated:
        best = max(y for y, _ in dated)
        start = min(s for y, s in dated if y == best)  # tie → primary stream
    else:
        start = heads[-1].start()  # no admission markers → position fallback
    return text[start:]


def _norm_code(raw):
    """'COMP 1080SEF' / 'COMP1080SEF' → 'COMP1080SEF' (courses-table id form)."""
    m = CODE_RE.search(raw)
    return (m.group(1) + m.group(2)) if m else None


def extract_text(pdf_bytes):
    import pdfplumber
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for pg in pdf.pages:
            pages.append(pg.extract_text() or "")
    return "\n".join(pages)


def categories_from_text(text):
    """Parse 'Table N: <Category>' sections into
    {category: {courses, course_credits, credits_seen}}.

    Multi-school (T32): heading→category via HEADING_PATTERNS; only the latest
    cohort's requirement set is parsed (EL PDFs carry two). Each non-header row
    beginning with a course code yields one course; credits = trailing integer.
    Courses repeating within a category (Year-1/2/3 entry columns re-listing the
    same course) are deduped — first occurrence wins.
    GE has no table (it's a prose requirement) → handled by the caller as pool:'ge'.
    """
    categories = {}
    text = latest_cohort_text(text)
    # Iterate 'Table N: <Title>' headings and capture the body until the next heading.
    headings = list(re.finditer(r"Table\s+\d+\s*:\s*([^\n]+)", text))
    for i, h in enumerate(headings):
        title = h.group(1).strip().lower()
        cat_key = _heading_category(title)
        if not cat_key:
            continue
        body = text[h.end(): (headings[i + 1].start() if i + 1 < len(headings) else len(text))]
        # "Note:" ends a table only when it FOLLOWS at least one course row.
        # HD/NHS PDFs open their tables with a preamble attendance Note —
        # truncating at the first Note: would swallow the whole table
        # (HDNGF parsed 0 courses before this guard).
        lines = body.splitlines()
        for li, ln in enumerate(lines):
            if NOTES_RE.match(ln) and any(
                CODE_ROW_RE.match(x.strip()) for x in lines[:li]
            ):
                body = "\n".join(lines[:li])
                break
        cat = categories.setdefault(
            cat_key, {"courses": [], "course_credits": {}, "credits_seen": 0})
        for line in body.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(("course code", "course title", "credit")):
                continue
            m = CODE_ROW_RE.match(line)
            if not m:
                continue
            code = _norm_code(line)
            if not code or code in cat["course_credits"]:
                continue
            # credits = last integer token on the row (skip ✔ / Year-Entry marks)
            nums = re.findall(r"\b(\d+)\b", line[m.end():])
            credits = int(nums[-1]) if nums else 3
            cat["courses"].append(code)
            cat["course_credits"][code] = credits
            cat["credits_seen"] += credits
    return categories


def ge_credits_from_prose(text):
    """GE is stated in prose ('6 credit-units of General Education'), no table."""
    m = re.search(r"(\d+)\s+credit-units?\s+of\s+General\s+Education", text, re.I)
    return int(m.group(1)) if m else None


# Prose "X credit-units of <Category> courses" → min_credits, from the FIRST
# (Year-1-entry) requirement list of the latest cohort only — later sections
# are Year-2/3-entry advanced-standing variants and grade-condition restatements
# ("1.1.2 attain grade C … for all 114 credit-units of core courses") we must
# not double-count. Within that list, ALL matches per pattern SUM (BASCHTICJ
# lists five elective lines; BED lists five "an elective course" lines), and
# matched spans are masked so a later, more generic pattern can't re-claim the
# same line ("University Core" must not be eaten by generic core). Filler
# `[\w&\-/ ]` covers "3000-level", "an/a", "marketing/supply chain management",
# "testing & certification" … but not \n, so matches stay on one line (some
# lines wrap right after the category word — hence the optional "courses").
# `credits-units` plural and a footnote `*` appear in some PDFs.
PROSE_MIN = [
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+University\s+Core\s+courses?", re.I), "university-core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+University\s+English(?:\s+language)?\s+courses?", re.I), "english"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+General\s+Education", re.I), "general-ed"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Theoretical\s+courses?\s*\(elective\)", re.I), "elective"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?elective(?:\s+courses?)?", re.I), "elective"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?periphery\s+courses?", re.I), "elective"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?synergy\s+courses?", re.I), "elective"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?speciali[sz]ation\s+courses?", re.I), "elective"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+from\s+one\s+of\s+the\s+following", re.I), "elective"),  # option group
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Theoretical\s+courses?\s*\(core\)", re.I), "core"),
    # HD 文凭的 Theoretical 无 (core)/(elective) 后缀("63 credit-units of
    # Theoretical courses in Table 1")→ 计入 core(Clinical Practicum 同折 core)
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Theoretical\s+courses?(?!\s*\()", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Clinical\s+Practicum", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?practicum\s+courses?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Core\s+Science\s+courses?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Specialized\s+Professional\s+courses?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?concentration\s+core(?:\s+courses?)?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?concentration\s+courses?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+core\s+strategy\s+course", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?mathematics\s+courses?", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+Integrated\s+STE(?:A)?M\s+training", re.I), "core"),
    (re.compile(r"(\d+)\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?core\s+courses?", re.I), "core"),
]


def y1_prose(text):
    """The first requirement list of the latest cohort: from its 'obtain N
    credit-units' up to the next clause heading (1.1.2 / 2.1.2 …), with
    five-level numbered option-children (1.1.1.4.x — mutually-exclusive
    alternatives, e.g. BBAHASMJ's three 33cr tracks) blanked out."""
    m = re.search(r"obtain\s+(\d+)\s+credit-units", text, re.I)
    if not m:
        return text
    rest = text[m.end():]
    nxt = re.search(r"(?m)^\s*\d+(?:\.\d+){2}\.?\s", rest)
    sec = rest[:nxt.start()] if nxt else rest
    return re.sub(r"(?m)^\s*\d+(?:\.\d+){4,}[.\s][^\n]*", " ", sec)


def prose_min_credits(text):
    """min_credits per category from the Year-1-entry prose (sum + mask)."""
    sec = y1_prose(latest_cohort_text(text))
    out = {}
    for rx, key in PROSE_MIN:
        spans = [(m.span(), int(m.group(1))) for m in rx.finditer(sec)]
        if spans:
            out[key] = out.get(key, 0) + sum(v for _, v in spans)
            chars = list(sec)
            for (a, b), _ in spans:
                for i in range(a, b):
                    chars[i] = " "
            sec = "".join(chars)
    return out


def total_credits_from_prose(text):
    """'obtain N credit-units' — the Year-1-entry programme total (first match)."""
    text = latest_cohort_text(text)
    m = re.search(r"obtain\s+(\d+)\s+credit-units", text, re.I)
    return int(m.group(1)) if m else None


# ── CLI ───────────────────────────────────────────────────────────────────────

# Mandatory Mental Health First Aid course: a 3cr requirement stated ONLY in
# prose ("1.1.2 complete the mandatory course on Mental Health First Aid
# (either … NURS1050NEF … or … NURS 1050NCF…)") and counted inside the prose
# category total, but never a table row — so the parsed table sum can land 3cr
# short (BSCHFTSJ core: table 96 vs prose 99). Add the English-version code to
# the short category so required pools stay satisfiable.
MHFA_RE = re.compile(
    r"mandatory\s+course\s+on\s+Mental\s+Health\s+First\s+Aid.*?"
    r"([A-Z]{2,5})\s?(\d{4}[A-Z]{2,3})", re.I | re.S)


def apply_mhfa_mandate(text, cats):
    m = MHFA_RE.search(text)
    if not m:
        return
    code = m.group(1) + m.group(2)
    for cat in cats.values():
        mc = cat.get("min_credits")
        cs = cat.get("credits_seen", 0)
        if (mc and cs < mc and mc - cs == 3
                and code not in cat.get("course_credits", {})):
            cat["courses"].append(code)
            cat["course_credits"][code] = 3
            cat["credits_seen"] = cs + 3
            return


def parse_text_to_entry(txt, school):
    """Full local parse of one programme's PDF text → raw-JSON entry."""
    cats = categories_from_text(txt)   # {cat: {courses, course_credits, credits_seen}}
    for key, mc in prose_min_credits(txt).items():
        cats.setdefault(key, {"courses": [], "course_credits": {}, "credits_seen": 0})
        cats[key]["min_credits"] = mc
        if key == "general-ed":
            cats[key]["pool"] = "ge"
    apply_mhfa_mandate(txt, cats)
    # 范围措辞标记("3 to 6 credit-units of … elective"):prose 正则取上限,
    # 但配对范围是两条合计恒定的路径(做/不做毕业课题),Σmin 会超 PDF 总分
    # ——builder 据此标记做 gap 校正(BSSCHPAJ 21→18)
    ranged = bool(re.search(
        r"\d+\s+to\s+\d+\s+credits?-units?\*?\s+of\s+[\w&\-/ ]*?elective",
        y1_prose(latest_cohort_text(txt)), re.I))
    return {"school": school, "total_credits": total_credits_from_prose(txt),
            "categories": cats, "_ranged_elective": ranged}


def audit(raw):
    """Per-programme sanity table — spot parse breakage (0-course categories,
    absurd counts, Σmin_credits ≠ total) at a glance."""
    print(f"{'code':12} {'sch':4} {'tot':>4} {'Σmin':>5}  categories(courses/min_credits)")
    print("-" * 104)
    for code, e in raw.items():
        if "_error" in e:
            print(f"{code:12} {e.get('school', '?'):4}  ERROR {e['_error']}")
            continue
        cats = e.get("categories", {})
        total = e.get("total_credits")
        smin = sum(c.get("min_credits", 0) for c in cats.values())
        detail = "  ".join(
            f"{k}:{len(c.get('courses', []))}/{c.get('min_credits', '?')}"
            for k, c in cats.items())
        flag = "" if total in (None, smin) else "  ⚠️ sum≠total"
        print(f"{code:12} {e['school']:4} {str(total):>4} {smin:>5}  {detail}{flag}")


def main():
    ap = argparse.ArgumentParser(description="Scrape HKMU programme-requirements PDFs.")
    ap.add_argument("--code", help="single programme code, e.g. BSCHDSAIJ")
    ap.add_argument("--school", help="school segment for --code: AS/BA/EL/NHS/ST")
    ap.add_argument("--all", action="store_true", help="scrape all 57 programmes")
    ap.add_argument("--text", action="store_true", help="dump raw extracted text (debug)")
    ap.add_argument("--outdir", help="save each PDF + extracted text under this dir "
                                     "(pdfs/<code>.pdf, text/<code>.txt) so T32 parser "
                                     "iteration can reparse locally without re-passing Cloudflare")
    ap.add_argument("--from-text-dir", dest="from_text_dir", metavar="DIR",
                    help="re-parse local <DIR>/<code>.txt files for all programmes "
                         "(no Cloudflare / playwright), e.g. scripts/out/hkmu_pr/text")
    ap.add_argument("--audit", metavar="RAW_JSON",
                    help="print the sanity-audit table for an existing raw JSON")
    args = ap.parse_args()

    if args.audit:
        with open(args.audit) as f:
            audit(json.load(f))
        return

    if args.from_text_dir:
        out = {}
        for code, school in PROGRAMMES:
            p = os.path.join(args.from_text_dir, f"{code}.txt")
            if not os.path.exists(p):
                out[code] = {"school": school, "_error": "no local text file"}
                print(f"  {code} ({school}): no local text", file=sys.stderr)
                continue
            with open(p) as f:
                txt = f.read()
            out[code] = parse_text_to_entry(txt, school)
            n = sum(len(c.get("courses", [])) for c in out[code]["categories"].values())
            print(f"  {code} ({school}): {len(out[code]['categories'])} categories, {n} courses",
                  file=sys.stderr)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if args.all:
        targets = PROGRAMMES
    elif args.code and args.school:
        targets = [(args.code, args.school)]
    else:
        ap.error("specify --code & --school, or --all")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed: pip install playwright && playwright install chromium")

    out = {}
    if args.outdir:
        os.makedirs(os.path.join(args.outdir, "pdfs"), exist_ok=True)
        os.makedirs(os.path.join(args.outdir, "text"), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"warming up Cloudflare: {CF_WARMUP}", file=sys.stderr)
        page.goto(CF_WARMUP, wait_until="domcontentloaded")
        for code, school in targets:
            data, err = fetch_pdf_bytes(page, code, school)
            if err:
                print(f"  {code} ({school}): FAIL {err}", file=sys.stderr)
                out[code] = {"_error": err}
                continue
            if args.text:
                txt = extract_text(data)
                print(f"=== {code} ({school}) ===\n{txt}\n")
                continue
            if args.outdir:
                with open(os.path.join(args.outdir, "pdfs", f"{code}.pdf"), "wb") as f:
                    f.write(data)
            txt = extract_text(data)
            if args.outdir:
                with open(os.path.join(args.outdir, "text", f"{code}.txt"), "w") as f:
                    f.write(txt)
            out[code] = parse_text_to_entry(txt, school)
            n = sum(len(c.get("courses", [])) for c in out[code]["categories"].values())
            print(f"  {code} ({school}): {len(out[code]['categories'])} categories, {n} courses",
                  file=sys.stderr)
        browser.close()

    if not args.text:
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
