"""独立复核管线 v2:表头锚定区段解析 433 份 yr 表。"""
import re, os, subprocess, json
from collections import defaultdict

AS = "/Users/yifanshi/Desktop/hkmu-campus-platform/docs/ops/选课选课/advice_sheets"
YR = f"{AS}/yr"
CODE = re.compile(r'\b([A-Z]{2,5})\s(\d{3,4}[A-Z]{3})\b')
TAIL = re.compile(r'(?<![0-9,:])(\d)\s+(\d{1,2})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE)\b')
HEADER = re.compile(r'Course No\.\d?\s+Course Code')
END = re.compile(r'Courses for the term|No\. of courses to take|\*\s*Enrolment Arrangement|Advice On Course Selection|^\s*Note:\s*$')
TERM = re.compile(r'(20\d{2})\s*(Autumn|Spring|Summer)')

def parse_file(path):
    txt = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    lines = txt.split('\n')
    plan = level = None
    for l in lines[:12]:
        m = re.search(r'Acad\. Plan Code:\s*(\S+)', l)
        if m: plan = m.group(1)
        m = re.search(r'Academic Level:\s*Year (\d)', l)
        if m: level = int(m.group(1))
    rows = []
    headers = [i for i, l in enumerate(lines) if HEADER.search(l)]
    for hi, h in enumerate(headers):
        end = len(lines)
        for j in range(h + 1, len(lines)):
            if END.search(lines[j]): end = j; break
        cur_term = None
        i = h + 1
        while i < end:
            l = lines[i]
            tm = TERM.search(l)
            if tm: cur_term = f"{tm.group(1)} {tm.group(2)}"
            m = CODE.search(l)
            if not m: i += 1; continue
            region, j = [l], i + 1
            while j < end:
                if CODE.search(lines[j]) or TERM.search(lines[j]): break
                region.append(lines[j]); j += 1
            t = TAIL.search(' '.join(x.strip() for x in region))
            ym = re.match(r'\s*(\d)\s+20\d{2}\s', l) or re.match(r'\s*(\d)\s+20\d{2}/\d{2}', l)
            r = {'code': m.group(1) + m.group(2), 'yr': int(ym.group(1)) if ym else level,
                 'term': cur_term, 'line': i}
            if t: r.update(dur=int(t.group(1)), cr=int(t.group(2)), type=t.group(3), enrol=t.group(4))
            else: r['fail'] = True; r['raw'] = ' '.join(region).strip()[:130]
            rows.append(r)
            i = j
    return plan, level, rows, len(headers)

def main():
    files = sorted(f for f in os.listdir(YR) if f.endswith('.pdf'))
    all_rows, fails, n_headers = [], [], 0
    for fn in files:
        plan, level, rows, nh = parse_file(f"{YR}/{fn}")
        n_headers += nh
        for r in rows:
            r['file'] = fn; r['plan'] = plan; r.pop('line', None)
            all_rows.append(r)
            if r.get('fail'): fails.append(r)
    print(f"文件 {len(files)} | 表头段 {n_headers} | 码行 {len(all_rows)} | 其中带尾(成功) {len(all_rows)-len(fails)} | 失败 {len(fails)}")
    for f in fails[:20]:
        print("  FAIL:", f['file'], f['code'], '|', f['raw'][:100])
    json.dump(all_rows, open('/tmp/verify/my_rows.json', 'w'), ensure_ascii=False)

if __name__ == '__main__':
    main()
