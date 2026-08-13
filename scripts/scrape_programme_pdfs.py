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

PDF URL pattern: https://www.hkmu.edu.hk/REG/reg_grad/PR/3CRU_FTU_<school>_<code>.pdf
  schools: AS (Arts & Social Sciences), BA (Business & Administration),
           EL (Education & Languages), NHS (Nursing & Health Sciences),
           ST (Science & Technology).

⚠️ Network: HKMU is behind Cloudflare AND some local networks/VPNs intermittently
  throw ERR_TUNNEL_CONNECTION_FAILED (verified 2026-08-13: DSAI 200 OK, but BA/AS
  PDFs failed on the same warm-up session). The script retries with backoff; if
  failures persist, switch network (mobile hotspot / HK or JP VPN node) — see
  memory [[vpn-azure-https-block]].

⚠️ Parser: categories_from_text() is tuned to the DSAI (ST) layout
  ("Table N: <Category>" heading + course rows "Code Title Credits"). Other
  schools' PDFs may vary — re-check the parser output against each school's PDF
  on first run (dump with --text) before trusting batch results.
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

# 57 full-time undergraduate 3cru programmes (code, school). Sourced from the
# programme-requirements-3cru index (extracted 2026-08-13).
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
    ("BSCHPTJ", "NHS"),
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

# "Table N: <Category>" heading → our category key
TABLE_CATEGORY = {
    "core courses": "core",
    "elective courses": "elective",
    "university core courses": "university-core",
    "university english courses": "english",
    "english courses": "english",
    "general education": "general-ed",
}


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
    """Parse 'Table N: <Category>' sections into {category: {courses, credits_seen}}.

    NOTE: tuned to DSAI (ST) layout. Each non-header row beginning with a course
    code yields one course; the credit value is the trailing integer on the row.
    GE has no table (it's a prose requirement) → handled by the caller as pool:'ge'.
    """
    categories = {}
    # Iterate 'Table N: <Title>' headings and capture the body until the next heading.
    headings = list(re.finditer(r"Table\s+\d+\s*:\s*([^\n]+)", text))
    for i, h in enumerate(heads := headings):
        title = h.group(1).strip().lower()
        cat_key = next((v for k, v in TABLE_CATEGORY.items() if k in title), None)
        if not cat_key:
            continue
        body = text[h.end(): (heads[i + 1].start() if i + 1 < len(heads) else len(text))]
        courses = []
        credit_total = 0
        for line in body.splitlines():
            line = line.strip()
            if not line or line.lower().startswith(("course code", "course title", "credit")):
                continue
            m = CODE_RE.search(line)
            if not m:
                continue
            code = _norm_code(line)
            # credits = last integer token on the row (skip ✔ / Year-Entry marks)
            nums = re.findall(r"\b(\d+)\b", line[m.end():])
            credits = int(nums[-1]) if nums else 3
            courses.append(code)
            credit_total += credits
        if cat_key not in categories:
            categories[cat_key] = {"courses": [], "credits_seen": 0}
        categories[cat_key]["courses"].extend(courses)
        categories[cat_key]["credits_seen"] += credit_total
    return categories


def ge_credits_from_prose(text):
    """GE is stated in prose ('6 credit-units of General Education'), no table."""
    m = re.search(r"(\d+)\s+credit-units?\s+of\s+General\s+Education", text, re.I)
    return int(m.group(1)) if m else None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Scrape HKMU programme-requirements PDFs.")
    ap.add_argument("--code", help="single programme code, e.g. BSCHDSAIJ")
    ap.add_argument("--school", help="school segment for --code: AS/BA/EL/NHS/ST")
    ap.add_argument("--all", action="store_true", help="scrape all 57 programmes")
    ap.add_argument("--text", action="store_true", help="dump raw extracted text (debug)")
    args = ap.parse_args()

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
            txt = extract_text(data)
            cats = categories_from_text(txt)
            ge = ge_credits_from_prose(txt)
            if ge is not None and "general-ed" not in cats:
                cats["general-ed"] = {"pool": "ge", "min_credits": ge}
            out[code] = {"school": school, "categories": cats}
            n = sum(len(c.get("courses", [])) for c in cats.values())
            print(f"  {code} ({school}): {len(cats)} categories, {n} courses", file=sys.stderr)
        browser.close()

    if not args.text:
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
