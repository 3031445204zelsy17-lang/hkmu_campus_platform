"""GE 目录独立复核:双引擎(pdftotext/pypdf)×双锚点(TOC点线/正文Credit-units)。
输出:各法计数、TOC-only/body-only 差集、与我们池的差集。"""
import re, subprocess, sys, json
from collections import OrderedDict

PDF = "/Users/yifanshi/Desktop/hkmu-campus-platform/docs/ops/选课选课/advice_sheets/GE_catalog_3cru.pdf"
CODE = re.compile(r'GEN\s*(\d{4}[A-Z]{3})')

def get_text(engine):
    if engine == "poppler":
        return subprocess.run(["pdftotext", "-layout", PDF, "-"], capture_output=True, text=True).stdout
    from pypdf import PdfReader
    return "\n".join((p.extract_text() or "") for p in PdfReader(PDF).pages)

def strip_all(s):  # 已知坑:折行 → 去全部空白再匹配
    return re.sub(r'\s+', '', s)

def analyze(engine):
    text = get_text(engine)
    lines = text.split('\n')
    toc_codes, body_codes = [], []
    in_body = False
    for i, l in enumerate(lines):
        ls = l.strip()
        if not in_body:
            # 正文起点:第一次出现 Credit-units 标签
            if re.match(r'^Credit-units\s*:', ls):
                in_body = True
            # TOC 行:点线 + 尾页码,行首 GEN 码
            m = re.match(r'^(GEN\s*\d{4}[A-Z]{3})\b', ls)
            if m and re.search(r'\.{6,}\s*\d+\s*$', ls):
                toc_codes.append(re.sub(r'\s', '', m.group(1)))
            continue
        # 正文区:结构锚 = GEN 码行,其后 8 行内出现 Credit-units:
        m = re.match(r'^(GEN\s*\d{4}[A-Z]{3})\b', ls)
        if m:
            window = strip_all(' '.join(lines[i:i+8]))
            # 去空白后找 "此码+Credit-units" 紧邻结构,防止误抓正文叙述里的码
            cm = re.match(r'^(GEN\d{4}[A-Z]{3})', strip_all(ls))
            if cm and re.search(r'Credit-units:', ' '.join(lines[i:i+8])):
                body_codes.append(cm.group(1))
    # 方法C(仅正文区):全文去空白后数 "GENxxxxCredit-units" 相邻对 —— 最抗折行
    body_text_nospace = None
    # 找正文区起点(第一个 Credit-units 行)
    first_cu = next(i for i, l in enumerate(lines) if re.match(r'^\s*Credit-units\s*:', l))
    body_nospace = strip_all('\n'.join(lines[first_cu:]))
    adj = re.findall(r'(GEN\d{4}[A-Z]{3})(?=Credit-units:)', body_nospace)
    return {
        'toc': toc_codes, 'toc_unique': sorted(set(toc_codes)),
        'body': body_codes, 'body_unique': sorted(set(body_codes)),
        'adjacent': sorted(set(adj)), 'adjacent_n_all': len(adj),
    }

res = {e: analyze(e) for e in ('poppler', 'pypdf')}
for e, r in res.items():
    print(f"[{e}] TOC行 {len(r['toc'])} / 去重 {len(r['toc_unique'])} | 正文锚 {len(r['body'])} / 去重 {len(r['body_unique'])} | 相邻对法 {len(r['adjacent'])}")

for e, r in res.items():
    print(f"[{e}] TOC-unique == body-unique? {set(r['toc_unique']) == set(r['body_unique'])}")
    print(f"  TOC-only: {sorted(set(r['toc_unique']) - set(r['body_unique']))}")
    print(f"  body-only: {sorted(set(r['body_unique']) - set(r['toc_unique']))}")
    print(f"  相邻对法 vs 正文锚 一致? {set(r['adjacent']) == set(r['body_unique'])}")

# 引擎间交叉
print("poppler vs pypdf TOC 一致?", set(res['poppler']['toc_unique']) == set(res['pypdf']['toc_unique']))
print("poppler vs pypdf body 一致?", set(res['poppler']['body_unique']) == set(res['pypdf']['body_unique']))

# 与我们池比对
sys.path.insert(0, '/Users/yifanshi/Desktop/hkmu-campus-platform/backend')
from app.data.ge_courses import GE_COURSES
pool = sorted(c['code'].replace(' ', '') for c in GE_COURSES)
official = set(res['poppler']['toc_unique']) | set(res['poppler']['body_unique'])
print(f"\n官方全集(TOC∪body) {len(official)} | 我们池 {len(pool)}")
missing = sorted(official - set(pool))
extra = sorted(set(pool) - official)
print(f"缺({len(missing)}): {missing}")
print(f"我们多({len(extra)}): {extra}")
json.dump({'official': sorted(official), 'missing': missing, 'extra': extra},
          open('/tmp/verify/ge_diff.json', 'w'), ensure_ascii=False, indent=1)
