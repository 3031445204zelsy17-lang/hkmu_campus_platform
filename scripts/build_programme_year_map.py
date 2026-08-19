"""Build backend/app/data/programme_year_map.py — per-专业年份映射(选课数据修复批次 2)。

架构动机(docs/ops/选课选课/advice_sheets/复核报告-2026-08-19.md 第四节):
  courses 表全局单一年份列 vs 官方按专业分年修读 → 模型级冲突。DSAI 手工年份
  (UNI3002BEW=Y4 等)全局外溢撞 16+ 专业,只 UPDATE 全局列修不完还会再错。
  本模块产出 per-(专业, 课) 年份/学期映射;courses.year 降级为映射缺失时的回退值。

数据源(验收标准.md 批次 2 约束:只许 verify/ 产物 + 复核报告 + 官方 PDF 原文;
results/ 旧 JSON 一律禁用——产自丢行解析器,CI 有断言锁):
  verify/my_rows.json       2795 行官方课行(my_pipeline.py 并集解析,plan/yr/term/type/cr)
  verify/final_result2.json 施工清单(final_recalc2.py 产物:missing 78 / hard 159)
  yr/*.pdf                  官方 advice sheet 原文(GE 占位行年份 + 课名提取)

建模决策(2026-08-19):
  * 系列语义:同专业多套 plan 码(BAHCAMDJ1/2/3 = 2026/27 时 Y1/Y2/Y3 入学 cohort,
    PDF 头部 Admit Cohort 自证)。行合并优先级 = 非 E 行 > 系列新(1→2→3)> 年小:
    系列 1 是最新课程结构(默认口径),旧系列行只兜两类缺 —— 系列 1 无该课行
    (UNI1002ABW 类)或系列 1 仅 E 行而旧系列有 C 行(LANG3138AEF 类,非 E 口径
    优先于系列新旧,复核报告第七节)。
  * 同课多年:非 E 行口径;同口径仍多年取最小年(官方推荐最早修读年)。
  * term 归一:"2026 Autumn"→autumn / "2027 Spring"→spring / "2026 Summer"→summer
    (与 courses.semester、schedule API 同词表)。
  * 补池分类(missing 78 课次):按官方行 type — C→core、E→elective、C+E 同现→core
    (非 E 口径)、无行(STAMJ/STEM 横版菜单页 3 门)→elective。
  * 课名:码行与 dur/cr/type 尾块之间的标题列(多行标题向前/向后拼接),仅回填
    裸码课(seed 侧判定,不覆盖已有好名)。

Regenerate: python3 scripts/build_programme_year_map.py
"""
import collections
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "backend"))

AS = os.path.join(REPO, "docs/ops/选课选课/advice_sheets")
YR = os.path.join(AS, "yr")
OUT = os.path.join(REPO, "backend/app/data/programme_year_map.py")

CODE = re.compile(r"\b([A-Z]{2,5})\s(\d{3,4}[A-Z]{3})\b")
TAIL = re.compile(r"(?<![0-9,:])(\d)\s+(\d{1,2})\s+(C|E|ENG|GE|UNI)\s+(PN|PC|SE|N/A)\b")
TERM = re.compile(r"(20\d{2})\s*(Autumn|Spring|Summer)")
GE_SLOT = re.compile(r"\bGE\s*\(([IVX]+)\)")
STOP_TITLE = re.compile(
    r"Courses for the term|No\. of courses to take|\*\s*Enrolment Arrangement"
    r"|Advice On Course Selection|^\s*Note:|^P\.\s*\d|E\.g\.|Type Code|Course Type"
    r"|Enrolment Arrangement|Relevant Link|According to"
)
SEM = {"Autumn": "autumn", "Spring": "spring", "Summer": "summer"}


def norm_plan(plan: str, programmes: dict) -> str | None:
    """plan 码 → PROGRAMMES 主码(与 final_recalc2.py 同款口径)。"""
    if plan in programmes:
        return plan
    base = plan.split("-")[0]
    if base in programmes:
        return base
    s = re.sub(r"\d+$", "", base)
    return s if s in programmes else None


def series_of(plan: str) -> str:
    """plan 首 token 的末位数字(cohort 系列);无数字返回 '~' 排最后。"""
    head = plan.split("-")[0]
    return head[-1] if head[-1].isdigit() else "~"


def read_rows():
    with open(os.path.join(AS, "verify/my_rows.json"), encoding="utf-8") as f:
        return json.load(f)


def build_year_map(rows, programmes):
    """{主码: {课码: {"year","term"}}} — 跨系列行合并,非 E 行 > 系列新 > 年小。

    优先级依据:复核报告第四/七节(年份按非 E 行口径) + 系列 = cohort 新旧
    (后缀 1 = 2026/27 Y1-entry,最新课程结构)。旧系列行只兜两类缺:
    系列 1 无该课的行(UNI1002ABW 类 23 课次)或系列 1 只有 E 行而旧系列有
    C 行(LANG3138AEF 类,非 E 口径优先于系列新旧)。
    """
    by_plan = collections.defaultdict(list)
    for r in rows:
        by_plan[r["plan"]].append(r)

    # 主码 → 各系列 plan 码;unmapped 计数(BSSCHWSJ 批次 3 处理)
    prog_plans = collections.defaultdict(list)
    unmapped = collections.Counter()
    for plan, rs in by_plan.items():
        p = norm_plan(plan, programmes)
        if p is None:
            unmapped[plan] += len(rs)
            continue
        prog_plans[p].append(plan)

    year_map: dict[str, dict[str, dict]] = {}
    for p, plans in prog_plans.items():
        per_course = collections.defaultdict(list)
        for pl in sorted(plans, key=series_of):
            srank = int(series_of(pl)) if series_of(pl).isdigit() else 9
            for r in by_plan[pl]:
                if r.get("yr") is None:
                    continue
                # kind_rank:非 E 行 0 / E 行 1;系列并入行内
                per_course[r["code"]].append(
                    (0 if r.get("type") != "E" else 1, srank, r))
        entry: dict[str, dict] = {}
        for code, triples in per_course.items():
            best_key = min((k, s) for k, s, _ in triples)
            pool = [r for k, s, r in triples if (k, s) == best_key]
            year = min(r["yr"] for r in pool)
            same = [r for r in pool if r["yr"] == year]
            m = TERM.search(same[0].get("term") or "")
            entry[code] = {
                "year": int(year),
                "term": SEM.get(m.group(2), "autumn") if m else "autumn",
            }
        year_map[p] = dict(sorted(entry.items()))
    return year_map, unmapped


def titlecase(title: str) -> str:
    words = title.split()
    cap = []
    for w in words:
        m = re.search(r"[A-Za-z]", w)
        if m and m.start() > 0:  # 前置标点(如 "(UNDERGRADUATE")不吞首字母
            w = w[: m.start()] + w[m.start()].upper() + w[m.start() + 1:].lower()
        else:
            w = w[:1].upper() + w[1:].lower()
        cap.append(w)
    fixed = " ".join(cap)
    # 常见缩写还原(title-case 会把 AI 打成 Ai 等)
    for bad, good in _ACRONYMS.items():
        fixed = re.sub(rf"(?<!\w){re.escape(bad)}(?!\w)", good, fixed)
    return fixed


_ACRONYMS = {
    "Ai": "AI", "Ii": "II", "Iii": "III", "Iv": "IV", "Vi": "VI",
    "It": "IT", "Hr": "HR", "Hrm": "HRM", "Esg": "ESG", "Ux": "UX",
    "Ui": "UI", "Km": "KM", "Csr": "CSR", "Sas": "SAS", "Spss": "SPSS",
    "Gis": "GIS", "Hci": "HCI", "Lgbt": "LGBT",
}


def _clusters(line: str) -> list[tuple[int, str]]:
    """-layout 行按 3+ 空格切列簇:[(起始列, 文本)]。"""
    out = []
    for m in re.finditer(r"\S(?:.*?\S)?(?=\s{3,}|$)", line):
        out.append((m.start(), m.group(0)))
    return out


def _title_cluster(line: str, code_x: int) -> str:
    """取该行标题列的簇:列位在码列右侧 150 列内、取最左者(避开右侧备注列)。"""
    cands = [t for x, t in _clusters(line) if code_x < x <= code_x + 150]
    return cands[0] if cands else ""


def parse_pdf(fn: str):
    """返回 (ge_slots, titles):GE 占位 (year, term) 集 + 码行课名。

    已知版式病(复核报告第三节同源):
      * 学期头行("3  2026 Autumn  1  IB 3091BEF …")同时载着该段首行课码;
      * 多行标题的单元格把首行吐在码行前、续行吐在码行后(UNI3002BEW/GIP 类),
        同一行的右侧备注列(Excluded combination 等)按列位隔离。
    """
    txt = subprocess.run(
        ["pdftotext", "-layout", os.path.join(YR, fn), "-"],
        capture_output=True, text=True,
    ).stdout
    lines = txt.split("\n")

    slots, titles = set(), {}
    cur_year, cur_term = None, None
    in_legend = False
    for i, ln in enumerate(lines):
        if re.match(r"\s*\*\s*Enrolment Arrangement", ln):
            in_legend = True
        if in_legend or "E.g." in ln:
            continue
        tm = TERM.search(ln)
        if tm:
            ym = re.match(r"\s*(\d)\s+20\d{2}", ln)
            if ym:
                cur_year = int(ym.group(1))
            cur_term = SEM.get(tm.group(2))
            # 注意:不 continue —— 学期头行还载着该段第一行课码
        gs = GE_SLOT.search(ln)
        if gs and re.search(r"\bGE\s+(SE|PN|PC|N/A)\b", ln) and cur_year is not None:
            slots.add((cur_year, cur_term or "autumn"))
        cm = CODE.search(ln)
        if not cm:
            continue
        code_x = cm.start()
        # 码行自身的标题:码后到尾块之间
        region, j = [ln], i + 1
        while j < len(lines):
            nl = lines[j]
            if CODE.search(nl) or TERM.search(nl) or STOP_TITLE.search(nl):
                break
            region.append(nl)
            j += 1
        joined = " ".join(x.strip() for x in region)
        jm = CODE.search(joined)
        t = TAIL.search(joined)
        title = re.sub(r"\s+", " ", joined[jm.end():t.start()].strip()) if jm and t else ""
        if not title:
            # 标题行前置:取码行前一行标题列簇 + 码行后 1 行续簇
            # (续簇上限 1:第 2 行起无法与「下一行的前置标题」区分,宁缺勿贪)
            parts = []
            if i > 0:
                prev = lines[i - 1]
                if not (CODE.search(prev) or TERM.search(prev)
                        or STOP_TITLE.search(prev) or TAIL.search(prev)):
                    parts.append(_title_cluster(prev, code_x))
            k = i + 1
            taken = 0
            while k < len(lines) and taken < 1:
                nl = lines[k]
                if CODE.search(nl) or TERM.search(nl) or STOP_TITLE.search(nl) or TAIL.search(nl):
                    break
                frag = _title_cluster(nl, code_x)
                if frag:
                    parts.append(frag)
                    taken += 1
                k += 1
            title = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
        if title:
            titles.setdefault(cm.group(1) + cm.group(2), titlecase(title))
    return slots, titles


def build_ge_slots_and_names(rows, programmes, year_map):
    """只解析选定系列的文件(全 433 份逐份 pdftotext 太慢且无必要)。"""
    by_plan_files = collections.defaultdict(set)
    for r in rows:
        by_plan_files[r["plan"]].add(r["file"])

    plans_by_prog = collections.defaultdict(list)
    for plan in by_plan_files:
        p = norm_plan(plan, programmes)
        if p is not None:
            plans_by_prog[p].append(plan)

    ge_slots: dict[str, list] = {}
    all_titles: dict[str, str] = {}
    for p, plans in plans_by_prog.items():
        if p not in year_map:
            continue
        chosen = [pl for pl in plans if series_of(pl) == "1"] or \
                 [min(plans, key=series_of)]
        slots = set()
        for pl in chosen:
            for fn in sorted(by_plan_files[pl]):
                s, t = parse_pdf(fn)
                slots |= s
                all_titles.update(t)
        ge_slots[p] = [{"year": y, "term": t} for y, t in sorted(slots)]
    return ge_slots, all_titles


def build_additions(rows, programmes):
    """missing 78 → {主码: {cat: [课码]}} + 官方学分 {课码: cr}。"""
    with open(os.path.join(AS, "verify/final_result2.json"), encoding="utf-8") as f:
        missing = json.load(f)["missing"]

    # (主码, 课码) → type 集 / cr 计数(跨全部系列)
    types = collections.defaultdict(set)
    crs = collections.defaultdict(collections.Counter)
    for r in rows:
        p = norm_plan(r["plan"], programmes)
        if p is None or not r.get("type"):
            continue
        types[(p, r["code"])].add(r["type"])
        if r.get("cr") is not None:
            crs[(p, r["code"])][r["cr"]] += 1

    additions: dict[str, dict[str, list]] = {}
    credits: dict[str, int] = {}
    no_type = []
    for p, codes in sorted(missing.items()):
        cats: dict[str, list] = collections.defaultdict(list)
        for c in sorted(codes):
            ts = types.get((p, c), set())
            if not ts:
                cats["elective"].append(c)  # STAMJ/STEM 横版菜单页无表头行
                no_type.append((p, c))
            elif "C" in ts:
                cats["core"].append(c)      # 含 C+E 同现 → 非 E 口径
            else:
                cats["elective"].append(c)
            vote = crs.get((p, c))
            if vote:
                # 官方多行冲突时取众数,再平票取小(保守学分)
                credits[c] = min(vote, key=lambda v: (-vote[v], v))
        additions[p] = {k: v for k, v in sorted(cats.items())}
    return additions, credits, no_type


def emit(year_map, ge_slots, titles, additions, credits, unmapped):
    def py(v):
        return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))

    L = []
    L.append('"""Auto-generated by scripts/build_programme_year_map.py — DO NOT HAND-EDIT.')
    L.append("")
    L.append("Per-专业修读年份映射(选课数据修复 · 批次 2)。架构动机/建模决策/数据源")
    L.append("见生成器 docstring;官方依据 = advice sheet PDF(2026/27)+ 复核报告-2026-08-19.md。")
    L.append("")
    L.append("Regenerate: python3 scripts/build_programme_year_map.py")
    L.append('"""')
    L.append("")
    L.append(f"# {len(year_map)} 专业 / {sum(len(v) for v in year_map.values())} 课次映射;"
             f" GE 占位 {sum(len(v) for v in ge_slots.values())} 槽;"
             f" 课名 {len(titles)};补池 {sum(len(c) for v in additions.values() for c in v.values())} 课次"
             f"({len(additions)} 专业)。未映射 plan:{dict(unmapped) or '无'}。")
    L.append("")
    L.append('# {专业码: {课码: {"year": 1-4, "term": "autumn|spring|summer"}}};别名码经')
    L.append("# PROGRAMME_ALIASES 归一到主码后在 courses.py 侧解析(模块保持零 import)。")
    L.append("PROGRAMME_YEAR_MAP = {")
    for p in sorted(year_map):
        inner = ", ".join(
            f'{py(c)}: {{"year": {v["year"]}, "term": "{v["term"]}"}}'
            for c, v in year_map[p].items()
        )
        L.append(f"    {py(p)}: {{{inner}}},")
    L.append("}")
    L.append("")
    L.append("# 官方 GE 占位行(GE (I)/(II)…):按 (year, term) 去重,前端在对应学年学期渲染占位卡。")
    L.append("PROGRAMME_GE_SLOTS = {")
    for p in sorted(ge_slots):
        if not ge_slots[p]:
            continue
        inner = ", ".join(f'{{"year": {s["year"]}, "term": "{s["term"]}"}}' for s in ge_slots[p])
        L.append(f"    {py(p)}: [{inner}],")
    L.append("}")
    L.append("")
    L.append("# 官方课名(advice sheet 标题列,首字母大写);seed 仅回填裸码课,不覆盖好名。")
    L.append("COURSE_NAME_BACKFILL = {")
    items = sorted(titles.items())
    for c, n in items:
        L.append(f"    {py(c)}: {py(n)},")
    L.append("}")
    L.append("")
    L.append("# 批次 2 补池(missing 78 课次;C→core / E→elective / 无行→elective),")
    L.append("# 由 programmes.py 在 import 时并入 PROGRAMMES(seed 侧同源插 courses 行)。")
    L.append("POOL_ADDITIONS = {")
    for p in sorted(additions):
        cats = ", ".join(f'{py(k)}: {py(v)}' for k, v in additions[p].items())
        L.append(f"    {py(p)}: {{{cats}}},")
    L.append("}")
    L.append("")
    L.append("# 补池课官方学分(GIP=0;多行冲突取众数平票取小)。")
    L.append("ADDITION_CREDITS = {")
    for c in sorted(credits):
        L.append(f"    {py(c)}: {credits[c]},")
    L.append("}")
    L.append("")
    return "\n".join(L)


def main():
    from app.data.programmes import PROGRAMMES

    rows = read_rows()
    year_map, unmapped = build_year_map(rows, PROGRAMMES)
    ge_slots, titles = build_ge_slots_and_names(rows, PROGRAMMES, year_map)
    additions, credits, no_type = build_additions(rows, PROGRAMMES)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(emit(year_map, ge_slots, titles, additions, credits, unmapped))

    print(f"year_map: {len(year_map)} 专业 / {sum(len(v) for v in year_map.values())} 课次")
    print(f"ge_slots: {sum(len(v) for v in ge_slots.values())} 槽 / {len(ge_slots)} 专业")
    print(f"titles: {len(titles)}")
    print(f"additions: {sum(len(c) for v in additions.values() for c in v.values())} 课次 / {len(additions)} 专业")
    print(f"credits: {len(credits)}(GIP 类 0 学分:{sum(1 for v in credits.values() if v == 0)} 门)")
    print(f"无 type 行(→elective): {no_type}")
    print(f"unmapped plans: {dict(unmapped)}")
    # 抽查:硬错位修复闭环(以 hard 清单为对账锚点,仅报告;断言在测试里)
    with open(os.path.join(AS, "verify/final_result2.json"), encoding="utf-8") as f:
        hard = json.load(f)["hard"]
    fixed = miss = 0
    for p, c, _my, official in hard:
        got = year_map.get(p, {}).get(c)
        if got and got["year"] in official:
            fixed += 1
        else:
            miss += 1
    print(f"hard 清单对账: {fixed} 命中 / {miss} 未覆盖(测试断言口径)")


if __name__ == "__main__":
    main()
