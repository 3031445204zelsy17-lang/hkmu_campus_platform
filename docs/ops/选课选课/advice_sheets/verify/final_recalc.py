"""终版独立重算:v8 解析器(N/A 支持+占位行)×我们侧独立重建。"""
import re, os, subprocess, json, sys
from collections import defaultdict

AS = "/Users/yifanshi/Desktop/hkmu-campus-platform/docs/ops/选课选课/advice_sheets"
YR = f"{AS}/yr"
REPO = "/Users/yifanshi/Desktop/hkmu-campus-platform"
sys.path.insert(0, f"{REPO}/backend")

CODE = re.compile(r'\b([A-Z]{2,5})\s(\d{3,4}[A-Z]{3})\b')
TAIL = re.compile(r'(?<![0-9,:])(\d)\s+(\d{1,2})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE|N/A)\b')
END = re.compile(r'Courses for the term|No\. of courses to take|\*\s*Enrolment Arrangement|Advice On Course Selection|^\s*Note:\s*$')
TERM = re.compile(r'(20\d{2})\s*(Autumn|Spring|Summer)')
PLACEHOLDER = re.compile(r'\b(GE|ENG)(\s*\([IVX]+\))?\s+(?=\S)')

def parse_file(path):
    txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    lines = txt.split('\n')
    plan = level = None
    for l in lines[:12]:
        m = re.search(r'Acad\. Plan Code:\s*(\S+)', l)
        if m: plan = m.group(1)
        m = re.search(r'Academic Level:\s*Year (\d)', l)
        if m: level = int(m.group(1))
    rows, placeholders = [], 0
    hidx = [i for i, l in enumerate(lines) if 'Course Code' in l and 'E.g.' not in l and re.search(r'\bYear\b', l)]
    for h in hidx:
        col = lines[h].find('Course Code')
        end = next((j for j in range(h + 1, len(lines)) if END.search(lines[j])), len(lines))
        cur_term = None; i = h + 1
        while i < end:
            ln = lines[i]
            tm = TERM.search(ln)
            if tm: cur_term = f"{tm.group(1)} {tm.group(2)}"
            m = next((cm for cm in CODE.finditer(ln) if abs(cm.start() - col) <= 10), None)
            if not m:
                # 占位行:GE (I) / GE / ENG 在码列位置(课号后)
                pm = re.search(r'\d{1,2}(?:[,.]\d{1,2})*\s+((?:GE|ENG)(?:\s*\([IVX]+\))?)\s', ln[:col + 30])
                if pm and abs(pm.start(1) - col) < 15: placeholders += 1
                i += 1; continue
            region, j2 = [ln], i + 1
            while j2 < end:
                if any(abs(cm.start() - col) <= 10 for cm in CODE.finditer(lines[j2])) or TERM.search(lines[j2]): break
                region.append(lines[j2]); j2 += 1
            t = TAIL.search(' '.join(x.strip() for x in region))
            ym = re.match(r'\s*(\d)\s+20\d{2}[\s/]', ln)
            r = {'code': m.group(1) + m.group(2), 'yr': int(ym.group(1)) if ym else level, 'term': cur_term}
            if t: r.update(dur=int(t.group(1)), cr=int(t.group(2)), type=t.group(3), enrol=t.group(4))
            else: r['fail'] = True; r['raw'] = ' '.join(region).strip()[:130]
            rows.append(r); i = j2
    return plan, level, rows, placeholders

# ── 我们侧重建 ──────────────────────────────────────────────
from app.data.programmes import PROGRAMMES
from app.data.programme_rules import PROGRAMME_RULES, RULE_COURSE_CREDITS
from app.data.ge_courses import GE_COURSES
import ast
_tree = ast.parse(open(f"{REPO}/scripts/seed_courses.py").read())
DSAI_SEED = next(ast.literal_eval(n.value) for n in _tree.body
                 if isinstance(n, ast.Assign) and n.targets[0].id == 'COURSES')

def level_year(cid):
    m = re.search(r'\d', cid)
    return min(int(m.group()), 4) if m and 1 <= int(m.group()) <= 4 else 4

# catalogue 学分(skill.md 官方树)
CAT_CREDS = {}
for line in open(f"{REPO}/docs/ops/选课选课/skill.md", encoding="utf-8"):
    m = re.search(r'\[代码: (.+?)\]\s*\[学分: (\d+)\]', line)
    if m:
        cid = m.group(1).replace(' ', '')
        cr = int(m.group(2))
        if cid in CAT_CREDS and CAT_CREDS[cid] != cr:
            CAT_CREDS.setdefault('_conflicts', {})[cid] = {CAT_CREDS[cid], cr}
        CAT_CREDS[cid] = cr

YEAR, CRED = {}, {}
for c in DSAI_SEED:
    YEAR[c['id']] = c['year']; CRED[c['id']] = c['credits']
for g in GE_COURSES:
    gid = g['code'].replace(' ', '')
    YEAR[gid] = 0; CRED.setdefault(gid, 3)
for code, entry in PROGRAMME_RULES.items():
    for cat, v in entry['categories'].items():
        if v.get('pool') == 'ge': continue
        for cid in v['courses']:
            if cid not in YEAR: YEAR[cid] = level_year(cid)
            if cid not in CRED:
                CRED[cid] = CAT_CREDS.get(cid, RULE_COURSE_CREDITS.get(code, {}).get(cat, {}).get(cid, 3))

def norm_plan(plan):
    if plan in PROGRAMMES: return plan
    base = plan.split('-')[0]
    if base in PROGRAMMES: return base
    stripped = re.sub(r'\d+$', '', base)
    if stripped in PROGRAMMES: return stripped
    return None

def main():
    files = sorted(f for f in os.listdir(YR) if f.endswith('.pdf'))
    all_rows, fails, ph_total = [], [], 0
    for fn in files:
        plan, level, rows, ph = parse_file(f"{YR}/{fn}")
        ph_total += ph
        for r in rows:
            r['file'] = fn; r['plan'] = plan
            all_rows.append(r)
            if r.get('fail'): fails.append(r)
    ok = [r for r in all_rows if not r.get('fail')]
    print(f"== 解析 ==\n文件 {len(files)} | 码行 {len(all_rows)} | 成功 {len(ok)} | 失败 {len(fails)} | GE/ENG占位行 {ph_total}")
    for f in fails: print("  FAIL:", f['file'], f['code'])

    # 官方集聚合(按规范化专业码)
    official = defaultdict(lambda: defaultdict(lambda: {'yr': set(), 'cr': set(), 'types': set(), 'terms': set()}))
    unmapped = set()
    for r in ok:
        p = norm_plan(r['plan'])
        if p is None: unmapped.add(r['plan']); continue
        d = official[p][r['code']]
        d['yr'].add(r['yr']); d['cr'].add(r['cr']); d['types'].add(r['type']); d['terms'].add(r['term'])
    print(f"plan 码 {len(set(r['plan'] for r in ok))} → 专业码 {len(official)} | 无法映射: {sorted(unmapped)}")

    # 我们池
    pools = {}
    for p, e in PROGRAMMES.items():
        s = set()
        for cat, v in e.get('categories', {}).items():
            if v.get('pool') == 'ge': continue
            s.update(v.get('courses', []))
        pools[p] = s

    # ① 缺课
    missing = {p: sorted(set(official[p]) - pools.get(p, set())) for p in official}
    missing = {p: v for p, v in missing.items() if v}
    n_missing = sum(len(v) for v in missing.values())
    gip = sum(1 for v in missing.values() for c in v if c.startswith('GIP'))
    print(f"\n== 缺课 ==\n专业数 {len(missing)} | 课次 {n_missing} | 其中 GIP {gip}")
    print("非 GIP 明细(前 40):", [c for v in missing.values() for c in v if not c.startswith('GIP')][:40])

    # ② 年份错位(hard=非E行年份;soft=仅E行的年份错位)
    rowidx = defaultdict(lambda: {'yrE': set(), 'yrC': set()})
    for r in ok:
        p = norm_plan(r['plan'])
        if p is None: continue
        rowidx[(p, r['code'])]['yrE' if r['type'] == 'E' else 'yrC'].add(r['yr'])
    hard, soft = [], []
    for (p, c), ys in rowidx.items():
        if p not in pools or c not in pools[p]: continue
        my = YEAR.get(c)
        if my is None: continue
        if ys['yrC'] and my not in ys['yrC']:
            hard.append((p, c, my, sorted(ys['yrC'])))
        elif not ys['yrC'] and ys['yrE'] and my not in ys['yrE']:
            soft.append((p, c, my, sorted(ys['yrE'])))
    print(f"\n== 年份 ==\n硬错位(非E行) {len(hard)} 课次 / {len(set(x[0] for x in hard))} 专业 | soft(仅E行) {len(soft)}")
    print("样例:", hard[:6])

    # ③ 学分
    cred_bad = []
    for p in official:
        for c in sorted(set(official[p]) & pools.get(p, set())):
            if c not in CRED: continue
            if CRED[c] not in official[p][c]['cr']:
                cred_bad.append((p, c, CRED[c], sorted(official[p][c]['cr'])))
    print(f"\n== 学分 ==\n不一致 {len(cred_bad)} 课次")
    for b in cred_bad[:20]: print("  ", b)
    json.dump({'rows': len(all_rows), 'ok': len(ok), 'fails': len(fails), 'placeholders': ph_total,
               'missing': missing, 'hard': hard, 'cred_bad': cred_bad},
              open('/tmp/verify/final_result.json', 'w'), ensure_ascii=False, indent=1, default=list)

if __name__ == '__main__':
    main()
