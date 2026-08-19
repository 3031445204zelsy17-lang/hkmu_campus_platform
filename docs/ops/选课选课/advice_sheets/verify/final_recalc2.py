"""终版并集解析:主解析(表头区段+列对齐)∪ 后扫(无表头页 码+尾同现行)。"""
import re, os, subprocess, json, sys
from collections import defaultdict, Counter

AS = "/Users/yifanshi/Desktop/hkmu-campus-platform/docs/ops/选课选课/advice_sheets"
YR = f"{AS}/yr"
REPO = "/Users/yifanshi/Desktop/hkmu-campus-platform"
sys.path.insert(0, f"{REPO}/backend")

CODE = re.compile(r'\b([A-Z]{2,5})\s(\d{3,4}[A-Z]{3})\b')
TAIL = re.compile(r'(?<![0-9,:])(\d)\s+(\d{1,2})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE|N/A)\b')
END = re.compile(r'Courses for the term|No\. of courses to take|\*\s*Enrolment Arrangement|Advice On Course Selection|^\s*Note:\s*$')
TERM = re.compile(r'(20\d{2})\s*(Autumn|Spring|Summer)')

def parse_file(path):
    txt = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True).stdout
    lines = txt.split('\n')
    plan = None
    level = None
    head = '\n'.join(lines[:16])
    m = re.search(r'Acad\.\s*Plan Code:\s*(\S+)', head)
    if m: plan = m.group(1)
    m = re.search(r'Academic\s*Level\s*:?\s*Year\s*(\d)', head)
    if m: level = int(m.group(1))
    fm = re.search(r'_Yr(\d)', os.path.basename(path))
    sheet_yr = int(fm.group(1)) if fm else None
    if level is None: level = sheet_yr  # 文件名兜底
    out = {}          # (code) -> row (同文件同码只留一条;文件内重复码合并年份/学分集)
    ph = 0
    def add(code, yr, term, t, src, raw=''):
        r = out.setdefault(code, {'code': code, 'yrs': set(), 'crs': set(), 'types': set(), 'terms': set(), 'src': set()})
        if yr is not None: r['yrs'].add(yr)
        if t:
            r['crs'].add(int(t.group(2))); r['types'].add(t.group(3))
        r['terms'].add(term); r['src'].add(src)
        if not t: r['fail'] = raw[:110]
    # 主解析
    hidx = [i for i, l in enumerate(lines) if 'Course Code' in l and 'E.g.' not in l and re.search(r'\bYear\b', l)]
    for h in hidx:
        col = lines[h].find('Course Code')
        end = next((j for j in range(h + 1, len(lines)) if END.search(lines[j])), len(lines))
        cur = None; i = h + 1
        while i < end:
            ln = lines[i]
            tm = TERM.search(ln)
            if tm: cur = f"{tm.group(1)} {tm.group(2)}"
            m = next((cm for cm in CODE.finditer(ln) if abs(cm.start() - col) <= 10), None)
            if not m:
                pm = re.search(r'\d{1,2}(?:[,.]\d{1,2})*\s+((?:GE|ENG)(?:\s*\([IVX]+\))?)\s', ln)
                if pm and ln.find(pm.group(1)) < col + 12 and 'GENERAL EDUCATION' in ln.upper() or (pm and 'UNIVERSITY' in ln.upper()):
                    ph += 1
                i += 1; continue
            region, j2 = [ln], i + 1
            while j2 < end:
                if any(abs(cm.start() - col) <= 10 for cm in CODE.finditer(lines[j2])) or TERM.search(lines[j2]): break
                region.append(lines[j2]); j2 += 1
            t = TAIL.search(' '.join(x.strip() for x in region))
            ym = re.match(r'\s*(\d)\s+20\d{2}[\s/]', ln)
            add(m.group(1) + m.group(2), int(ym.group(1)) if ym else level, cur, t, 'main', ' '.join(region))
            i = j2
    # 后扫:全文件 码+尾 同现行(排除图例/示例),只要主解析没抓到该码
    in_legend = False
    for i, ln in enumerate(lines):
        if re.match(r'\s*\*\s*Enrolment Arrangement', ln): in_legend = True
        if in_legend or 'E.g.' in ln: continue
        cm = CODE.search(ln); tm = TAIL.search(ln)
        if cm and tm and cm.start() < tm.start():
            code = cm.group(1) + cm.group(2)
            if code in out and 'main' in out[code]['src']: continue
            ym = re.match(r'\s*(\d)\s+20\d{2}[\s/]', ln)
            tt = TERM.search(ln)
            add(code, int(ym.group(1)) if ym else level, f"{tt.group(1)} {tt.group(2)}" if tt else None, tm, 'post', ln)
    return plan, level, out, ph

# ── 我们侧(同 final_recalc) ──
from app.data.programmes import PROGRAMMES, PROGRAMME_ALIASES
from app.data.programme_rules import PROGRAMME_RULES, RULE_COURSE_CREDITS
from app.data.ge_courses import GE_COURSES
import ast
_tree = ast.parse(open(f"{REPO}/scripts/seed_courses.py").read())
DSAI_SEED = next(ast.literal_eval(n.value) for n in _tree.body
                 if isinstance(n, ast.Assign) and n.targets[0].id == 'COURSES')

def level_year(cid):
    m = re.search(r'\d', cid)
    return min(int(m.group()), 4) if m and 1 <= int(m.group()) <= 4 else 4

CAT_CREDS, CAT_SRC = {}, {}
for ln in open(f"{REPO}/docs/ops/选课选课/skill.md", encoding="utf-8"):
    m = re.search(r'\[代码: (.+?)\]\s*\[学分: (\d+)\]', ln)
    if m:
        cid, cr = m.group(1).replace(' ', ''), int(m.group(2))
        if cid in CAT_CREDS and CAT_CREDS[cid] != cr:
            CAT_SRC.setdefault('_conflict', {}).setdefault(cid, set()).update({CAT_CREDS[cid], cr})
        else:
            CAT_CREDS[cid] = cr; CAT_SRC[cid] = 'skill.md'

YEAR, CRED, CRED_SRC = {}, {}, {}
for c in DSAI_SEED:
    YEAR[c['id']] = c['year']; CRED[c['id']] = c['credits']; CRED_SRC[c['id']] = 'DSAI手工表'
for g in GE_COURSES:
    gid = g['code'].replace(' ', '')
    YEAR[gid] = 0
    if gid not in CRED: CRED[gid] = 3; CRED_SRC[gid] = 'GE默认3'
for code, entry in PROGRAMME_RULES.items():
    for cat, v in entry['categories'].items():
        if v.get('pool') == 'ge': continue
        for cid in v['courses']:
            if cid not in YEAR: YEAR[cid] = level_year(cid);
            if cid not in CRED:
                if cid in CAT_CREDS: CRED[cid] = CAT_CREDS[cid]; CRED_SRC[cid] = 'catalogue(skill.md)'
                else:
                    rcc = RULE_COURSE_CREDITS.get(code, {}).get(cat, {}).get(cid)
                    if rcc is not None: CRED[cid] = rcc; CRED_SRC[cid] = f'RCC[{code}.{cat}]'
                    else: CRED[cid] = 3; CRED_SRC[cid] = '默认3'

def norm_plan(plan):
    if plan in PROGRAMMES: return plan
    base = plan.split('-')[0]
    if base in PROGRAMMES: return base
    s = re.sub(r'\d+$', '', base)
    return s if s in PROGRAMMES else None

def main():
    files = sorted(f for f in os.listdir(YR) if f.endswith('.pdf'))
    official = defaultdict(lambda: defaultdict(lambda: {'yr': set(), 'cr': set(), 'types': set()}))
    tot_codes = fails = ph_total = 0
    unmapped = Counter()
    for fn in files:
        plan, level, rows, ph = parse_file(f"{YR}/{fn}")
        ph_total += ph
        tot_codes += len(rows)
        fails += sum(1 for r in rows.values() if 'fail' in r)
        p = norm_plan(plan)
        if p is None: unmapped[plan] += len(rows); continue
        for c, r in rows.items():
            d = official[p][c]
            d['yr'] |= r['yrs']; d['cr'] |= {x for x in r['crs'] if x}; d['types'] |= r['types']
    print(f"== 解析(并集)==\n文件 {len(files)} | 文件×码对 {tot_codes} | 无尾 {fails} | 占位行 {ph_total} | 无法映射plan {dict(unmapped)}")
    print(f"专业数 {len(official)}")

    pools = {}
    for p, e in PROGRAMMES.items():
        s = set()
        for cat, v in e.get('categories', {}).items():
            if v.get('pool') == 'ge': continue
            s.update(v.get('courses', []))
        pools[p] = s

    missing = {p: sorted(set(official[p]) - pools.get(p, set())) for p in official}
    missing = {p: v for p, v in missing.items() if v}
    n_missing = sum(len(v) for v in missing.values())
    gip = sum(1 for v in missing.values() for c in v if c.startswith('GIP'))
    print(f"\n== 缺课 ==\n专业 {len(missing)} | 课次 {n_missing} | GIP {gip}")
    for p, v in sorted(missing.items(), key=lambda x: -len(x[1])):
        print(f"  {p}: {len(v)} → {v[:10]}{'…' if len(v) > 10 else ''}")

    rowidx = defaultdict(lambda: {'yrE': set(), 'yrC': set()})
    for p in official:
        for c, d in official[p].items():
            pass
    # 年份:非E行年份集
    for fn in files:
        plan, level, rows, ph = parse_file(f"{YR}/{fn}")
        p = norm_plan(plan)
        if p is None: continue
        for c, r in rows.items():
            for y in r['yrs']:
                for t in r['types']:
                    if t == 'E': rowidx[(p, c)]['yrE'].add(y)
                    else: rowidx[(p, c)]['yrC'].add(y)
    hard, soft = [], []
    for (p, c), ys in rowidx.items():
        if p not in pools or c not in pools[p]: continue
        my = YEAR.get(c)
        if my is None: continue
        if ys['yrC'] and my not in ys['yrC']: hard.append((p, c, my, sorted(ys['yrC'])))
        elif not ys['yrC'] and ys['yrE'] and my not in ys['yrE']: soft.append((p, c, my, sorted(ys['yrE'])))
    print(f"\n== 年份 ==\n硬 {len(hard)}/{len(set(x[0] for x in hard))} 专业 | soft {len(soft)}")

    cred_bad = []
    for p in official:
        for c in sorted(set(official[p]) & pools.get(p, set())):
            if c in CRED and CRED[c] not in official[p][c]['cr']:
                cred_bad.append((p, c, CRED[c], sorted(official[p][c]['cr']), CRED_SRC[c]))
    print(f"\n== 学分 ==\n不一致 {len(cred_bad)} 课次")
    for b in sorted(cred_bad, key=lambda x: x[4]): print("  ", b)
    json.dump({'missing': {k: v for k, v in missing.items()}, 'hard': hard, 'soft': soft,
               'cred_bad': cred_bad, 'tot_codes': tot_codes},
              open('/tmp/verify/final_result2.json', 'w'), ensure_ascii=False, indent=1, default=list)

if __name__ == '__main__':
    main()
