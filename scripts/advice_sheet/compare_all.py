"""官方 advice sheets vs 我们的 planner 数据 全量比对"""
import sys, os, re, json, glob
sys.path.insert(0, '/Users/yifanshi/Desktop/hkmu-campus-platform/backend')
from pypdf import PdfReader
from app.data.programmes import PROGRAMMES
from app.data.programme_rules import RULE_COURSE_CREDITS
sys.path.insert(0, '/tmp')
from parse_yr import parse as parse_yr

COVERS = '/tmp/advice_sheets/covers'
YRDIR = '/tmp/advice_sheets/yr'

# 1) 封面码 → 年级表文件(保留关联)
cover_to_yr = {}
for f in sorted(glob.glob(f'{COVERS}/*.pdf')):
    code = f.rsplit('/',1)[-1][:-4]
    urls = set()
    for page in PdfReader(f).pages:
        for a in (page.get('/Annots') or []):
            A = a.get_object().get('/A')
            u = A.get('/URI') if A else None
            if u and '_Yr' in u: urls.add(u.replace('http://','https://'))
    cover_to_yr[code] = sorted(u.rsplit('/',1)[-1] for u in urls)

# 2) 解析每份年级表
def level_year(cid):
    m = re.search(r'\d', cid)
    return min(int(m.group()), 4) if m and 1 <= int(m.group()) <= 4 else 4

result = {}
tot_rows = tot_fail = 0
for code, files in cover_to_yr.items():
    prog = PROGRAMMES.get(code)
    ours = {}
    if prog and prog.get('categories'):
        for cat, v in prog['categories'].items():
            for c in v.get('courses', []):
                ours.setdefault(c, cat)
    ours_full = dict(ours)  # 码 → category
    # 双胞胎老码合并(如 BNHGJ rules 挂在老码)
    if not ours_full and prog is None:
        pass
    official = {}  # code → {yr:set, terms:set, cr:set, type:set}
    rows_n = fails = 0
    for fn in files:
        yr_file = os.path.join(YRDIR, fn)
        m = re.search(r'_Yr(\d)', fn)
        sheet_yr = int(m.group(1)) if m else None
        if not os.path.exists(yr_file) or sheet_yr is None: continue
        for r in parse_yr(yr_file):
            rows_n += 1
            if r.get('parse') == 'fail': fails += 1; continue
            c = r['code']
            if not re.fullmatch(r'[A-Z]{2,5}\d{3,4}[A-Z]{3}', c): continue  # 占位符行跳过
            d = official.setdefault(c, {'yr': set(), 'terms': set(), 'cr': set(), 'types': set()})
            d['yr'].add(r['yr'] or sheet_yr); d['terms'].add(r.get('term'))
            d['cr'].add(r['cr']); d['types'].add(r['type'])
    tot_rows += rows_n; tot_fail += fails
    # 3) 比对
    missing = sorted(set(official) - set(ours_full))
    extra_core = sorted(c for c, cat in ours_full.items() if cat in ('core','university-core') and c not in official)
    year_mismatch, credit_mismatch = [], []
    for c in sorted(set(official) & set(ours_full)):
        oy = sorted(official[c]['yr'])
        my = level_year(c)  # 我们库里的年份=码级启发式(非 DSAI)
        if my not in oy: year_mismatch.append((c, my, oy))
    # 学分比对走 RULE_COURSE_CREDITS(扁平查找)
    rcc = {}
    for cat, m2 in RULE_COURSE_CREDITS.get(code, {}).items():
        for cid, cr in m2.items(): rcc[cid] = cr
    for c2 in sorted(set(official) & set(rcc)):
        if rcc[c2] not in official[c2]['cr']: credit_mismatch.append((c2, rcc[c2], sorted(official[c2]['cr'])))
    absent = prog is None or not prog.get('categories')
    result[code] = {
        'programme_absent': absent,
        'official_courses': len(official), 'rows': rows_n, 'parse_fail': fails,
        'missing': [] if absent else missing, 'missing_all_if_absent': missing if absent else [],
        'extra_core': extra_core,
        'year_mismatch': [(c, m, y) for c, m, y in year_mismatch],
        'credit_mismatch': credit_mismatch,
    }

# 4) 汇总
N = len(result)
absent = [k for k, v in result.items() if v.get('programme_absent')]
agg_missing = {k: v['missing'] for k, v in result.items() if v['missing']}
agg_year = {k: v['year_mismatch'] for k, v in result.items() if v['year_mismatch']}
agg_cred = {k: v['credit_mismatch'] for k, v in result.items() if v['credit_mismatch']}
agg_extra = {k: v['extra_core'] for k, v in result.items() if v['extra_core']}
print(f'专业数 {N}(其中我们整体缺失: {absent}) | 官方课行 {tot_rows} | 解析失败行 {tot_fail}')
# 缺课模式归类
from collections import Counter
pat = Counter()
for v in result.values():
    for c in v['missing']:
        if c.startswith('GIP'): pat['GIP 浸入课'] += 1
        elif c.startswith(('ENGL','CHIN','PTH','LANG')): pat['语言课'] += 1
        elif c.startswith('UNI'): pat['大学核心'] += 1
        elif c.startswith('NURS') and '1050' in c: pat['MHFA'] += 1
        else: pat['其他专业课'] += 1
print('缺课模式:', dict(pat))
print(f'官方课我们缺: 专业数 {len(agg_missing)}, 课次 {sum(len(v) for v in agg_missing.values())}')
print(f'年份不一致: 专业数 {len(agg_year)}, 课次 {sum(len(v) for v in agg_year.values())}')
print(f'学分不一致: 专业数 {len(agg_cred)}, 课次 {sum(len(v) for v in agg_cred.values())}')
print(f'※核心池有但秋季表无(含春季才开的课,仅信息参考,非错误): 专业数 {len(agg_extra)}, 课次 {sum(len(v) for v in agg_extra.values())}')
print()
print('== 缺课最多的 8 个专业 ==')
for k, v in sorted(agg_missing.items(), key=lambda x: -len(x[1]))[:8]:
    print(f'  {k}: {len(v)} 门缺 → {v[:8]}{"..." if len(v)>8 else ""}')
print()
print('== 年份不一致最多的 6 个专业 ==')
for k, v in sorted(agg_year.items(), key=lambda x: -len(x[1]))[:6]:
    print(f'  {k}: {len(v)} 门 → {v[:6]}')
json.dump(result, open('/tmp/advice_sheets/compare_result.json','w'), ensure_ascii=False, indent=1, default=list)
