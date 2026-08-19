"""解析 advice sheet 年级课表 PDF → 结构化课行 v3"""
import re, sys, json
from pypdf import PdfReader

CODE = r'[A-Z]{2,5}\s+\d{3,4}[A-Z]{3}'
PLACEHOLDER = r'GE(?:\s*\([IVX]+\))?|ENG(?:\s*\([IVX]+\))?'
ROWHEAD = re.compile(
    rf'^\s*(?:(\d)\s+)?(?:(20\d{{2}})\s+(Autumn|Spring|Summer)\s+|20\d{{2}}/\d{{2}}\s+AY\s*)?(\d{{1,2}})\s+({CODE}|{PLACEHOLDER})\s*(.*)$'
)
TAIL = re.compile(r'\s+(\d)\s+(\d{1,3})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE)\b\s*(.*)$')
STOP = re.compile(r'^(\* Enrolment|Advice On Course|No\. of courses|According to|^P\.\s*\d|^\d{4}/\d{2}\s+AY$|Note:|^E\.g\.|^[0-9]+:|Type Code|Course Type|Relevant Link|^[A-Z]: )')

def parse(path):
    text = '\n'.join((p.extract_text() or '') for p in PdfReader(path).pages)
    lines = [l.strip() for l in text.split('\n')]
    rows, i, n = [], 0, len(lines)
    cur_year, cur_term = None, None
    while i < n:
        l = lines[i]
        if STOP.match(l): i += 1; continue
        m = ROWHEAD.match(l)
        if not m: i += 1; continue
        if m.group(1): cur_year = int(m.group(1))
        if m.group(3): cur_term = m.group(3)
        buf = [m.group(6) or '']
        j = i + 1
        while j < n:
            nl = lines[j]
            if STOP.match(nl) or ROWHEAD.match(nl) or re.match(r'^\d+\s*$', nl): break
            buf.append(nl); j += 1
        raw = ' '.join(buf).strip()
        t = TAIL.search(raw)
        code_raw = m.group(5)
        base = {
            'yr': cur_year, 'term': cur_term, 'no': int(m.group(4)),
            'code': code_raw.replace(' ', '') if re.fullmatch(CODE, code_raw) else code_raw,
        }
        if t:
            base.update(title=re.sub(r'\s+',' ',raw[:t.start()])[:60],
                        dur=int(t.group(1)), cr=int(t.group(2)),
                        type=t.group(3), enrol=t.group(4),
                        remark=re.sub(r'\s+',' ',t.group(5))[:90])
        else:
            base.update(parse='fail', raw=raw[:90])
        rows.append(base)
        i = j
    return rows

if __name__ == '__main__':
    rs = parse(sys.argv[1])
    print(f'解析 {len(rs)} 行,失败 {sum(1 for r in rs if r.get("parse")=="fail")}', file=sys.stderr)
    for r in rs: print(json.dumps(r, ensure_ascii=False))
