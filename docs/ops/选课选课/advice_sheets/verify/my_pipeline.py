"""独立复核管线:自解析 433 份 yr 表(poppler -layout)vs 独立重建的我们侧数据。
不 import 上一会话的 parse_yr/compare_all。"""
import re, os, subprocess, json, sys
from collections import defaultdict

AS = "/Users/yifanshi/Desktop/hkmu-campus-platform/docs/ops/选课选课/advice_sheets"
YR = f"{AS}/yr"
REPO = "/Users/yifanshi/Desktop/hkmu-campus-platform"
sys.path.insert(0, f"{REPO}/backend")

CODE = re.compile(r'\b([A-Z]{2,5})\s(\d{3,4}[A-Z]{3})\b')
TAIL = re.compile(r'(?<![0-9,:])(\d)\s+(\d{1,2})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE)\b')
SUMMARY = re.compile(r'Courses for the term|No\. of courses to take')
STOP = re.compile(r'^(\* Enrolment|Advice On Course Selection|P\.\s*\d|According to|Note:|E\.g\.|\d:|Type Code|Course Type|Relevant Link|[A-Z]: |Enrolment Arrangement)')
TERM = re.compile(r'(20\d{2})\s*(Autumn|Spring|Summer)')

def parse_file(path):
    txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    lines = [l for l in txt.split('\n')]
    plan = level = None
    for l in lines[:12]:
        m = re.search(r'Acad\. Plan Code:\s*(\S+)', l)
        if m: plan = m.group(1)
        m = re.search(r'Academic Level:\s*Year (\d)', l)
        if m: level = int(m.group(1))
    rows, cur_term = [], None
    i = 0
    while i < len(lines):
        l = lines[i]
        m = CODE.search(l)
        if not m:
            tm = TERM.search(l)
            if tm: cur_term = f"{tm.group(1)} {tm.group(2)}"
            i += 1; continue
        # 行区域:到下一个码行/汇总行/停止行
        region = [l]; j = i + 1
        while j < len(lines):
            nl = lines[j]
            if CODE.search(nl) or SUMMARY.search(nl) or STOP.match(nl.strip()) or TERM.search(nl):
                break
            region.append(nl); j += 1
        code = (m.group(1) + m.group(2))
        joined = ' '.join(region)
        t = TAIL.search(' '.join(x.rstrip() for x in region))
        # 年份:码行前导 Year 列数字(行首独立数字)或文件级 level
        ym = re.match(r'\s*(\d)\s+\d{4}\s+(Autumn|Spring|Summer)', l) or re.match(r'\s*(\d)\s+20\d{2}/\d{2}', l)
        yr = int(ym.group(1)) if ym else level
        base = {'code': code, 'yr': yr, 'term': cur_term, 'line': i}
        if t:
            base.update(dur=int(t.group(1)), cr=int(t.group(2)),
                        type=t.group(3), enrol=t.group(4))
        else:
            base['fail'] = True
            base['raw'] = joined.strip()[:120]
        rows.append(base)
        i = j
    return plan, level, rows

def main():
    files = sorted(os.listdir(YR))
    all_rows, fails = [], []
    by_plan = defaultdict(list)
    for fn in files:
        if not fn.endswith('.pdf'): continue
        plan, level, rows = parse_file(f"{YR}/{fn}")
        for r in rows:
            r['file'] = fn; r['plan'] = plan
            all_rows.append(r)
            if r.get('fail'): fails.append(r)
            else: by_plan[plan].append(r)
    print(f"文件 {len([f for f in files if f.endswith('.pdf')])} | 课行总数 {len(all_rows)} | 失败 {len(fails)}")
    print(f"plan 码去重 {len(by_plan)}")
    for f in fails[:15]:
        print("  FAIL:", f['file'], f['code'], '|', f['raw'][:90])
    json.dump([r for r in all_rows], open('/tmp/verify/my_rows.json', 'w'), ensure_ascii=False)

if __name__ == '__main__':
    main()
