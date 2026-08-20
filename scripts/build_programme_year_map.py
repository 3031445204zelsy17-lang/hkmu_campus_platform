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

批次 5(2026-08-20)新增双系列 cohort 轴:
  * 系列 = 入学点(plan 尾数字 N = 页眉 "Year N Entry",420/420 文件核对),
    不是入学年份 —— Y2/Y3 入学(advanced standing)与 Y1 入学是同届不同路径。
  * PROGRAMME_ENTRY_SERIES 记各专业可用入学点 + 官方 cohort 标签(max-AY);
    SERIES_YEAR_OVERRIDES 只存「该系列官方修读年 ≠ 默认合并图」的差分课
    (BEDHACLSJ 系列2 UNI2002BCW=Y3 vs 默认 Y2 等 125 课次/36 专业),
    per-系列合并口径与默认图相同(非 E 行 > 年小)。

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
# 表注/说明行(码行前置兜底时不得当标题收,实测 MATH1410SEF 吃进 Table 4 注文)
CAPTION = re.compile(r"^Table \d|Advisory Prerequisite|Prerequisite Requirement")
# 终名垃圾过滤:advice sheet 的先修建议注记/表引用跨行混进标题列(行级守卫
# 挡不住跨行包裹),凡命中一律拒收该名(课留待其他文件或裸码回退)
JUNK_TITLE = re.compile(
    r"Table \d|Advisory Prerequisite|Prerequisite Requirement|Can Be Found|^Advisory:",
    re.IGNORECASE,
)
GE_SLOT = re.compile(r"\bGE\s*\(([IVX]+)\)")
STOP_TITLE = re.compile(
    r"Courses for the term|No\. of courses to take|\*\s*Enrolment Arrangement"
    r"|Advice On Course Selection|^\s*Note:|^P\.\s*\d|E\.g\.|Type Code|Course Type"
    r"|Enrolment Arrangement|Relevant Link|According to"
)
SEM = {"Autumn": "autumn", "Spring": "spring", "Summer": "summer"}


def norm_plan(plan: str, programmes: dict, aliases: dict | None = None) -> str | None:
    """plan 码 → PROGRAMMES 主码(final_recalc2 同款口径 + 别名归一)。

    别名码(BAPHBMJ1 等)本身在 PROGRAMMES 里,直接命中会把映射灌到别名键下;
    而运行时(courses._placements_for)按「别名 → 主码」查表,键必须是主码。"""
    hit = None
    if plan in programmes:
        hit = plan
    else:
        base = plan.split("-")[0]
        if base in programmes:
            hit = base
        else:
            s = re.sub(r"\d+$", "", base)
            hit = s if s in programmes else None
    if hit and aliases:
        hit = aliases.get(hit, hit)
    return hit


def series_of(plan: str) -> str:
    """plan 首 token 的末位数字(cohort 系列);无数字返回 '~' 排最后。"""
    head = plan.split("-")[0]
    return head[-1] if head[-1].isdigit() else "~"


def read_rows():
    with open(os.path.join(AS, "verify/my_rows.json"), encoding="utf-8") as f:
        return json.load(f)


def read_series_labels():
    """yr/*.pdf 页眉「Admit Cohort: 2026/27 Year N Entry」→ {plan: label}。

    佐证系列尾数字 = 入学点(Year N Entry):420/420 可解析文件逐一吻合
    (2026-08-20 全库核对;13 份大小写/版式差异文件修正正则后同样吻合)。
    同一 plan 码的不同 Yr 文件各对应一届入学(Yr1=本学年入、Yr4=三学年前
    入),取 max-AY 标注 = 「本学年以 N 点入学」的 cohort 标签。
    """
    pat_cohort = re.compile(
        r"Admit\s*Cohort:\s*(20\d{2}/\d{2})\s*Year\s*(\d)\s*entry", re.IGNORECASE)
    pat_plan = re.compile(r"Acad\.\s*Plan\s*Code:\s*(\S+)")
    best: dict[str, tuple[int, str]] = {}
    for fn in sorted(os.listdir(YR)):
        if not fn.endswith(".pdf"):
            continue
        txt = subprocess.run(
            ["pdftotext", "-layout", "-l", "1", os.path.join(YR, fn), "-"],
            capture_output=True, text=True,
        ).stdout
        mc = pat_cohort.search(txt)
        mp = pat_plan.search(txt)
        if not mc or not mp:
            continue
        ay, level = mc.group(1), int(mc.group(2))
        # plan 码取页眉(文件名可带子计划后缀,如 BBAHMGTJ1-HMGTJ1-18_Yr1.pdf)
        plan = mp.group(1)
        start = int(ay.split("/")[0])
        label = f"{ay} Year {level} Entry"
        if plan not in best or start > best[plan][0]:
            best[plan] = (start, label)
    return {p: label for p, (_, label) in best.items()}


def build_series_axes(rows, programmes, year_map, labels, aliases=None):
    """双系列 cohort 轴(批次 5):per-(专业, 入学点系列) 年份差异。

    返回 (PROGRAMME_ENTRY_SERIES, SERIES_YEAR_OVERRIDES):
      PROGRAMME_ENTRY_SERIES      {主码: {系列: {"entry_level", "label"}}}
      SERIES_YEAR_OVERRIDES {主码: {系列: {课码: {"year","term"}}}} —— 该系列的
        官方修读年/学期 ≠ 合并默认图(PROGRAMME_YEAR_MAP)的课,仅存差分。
    per-系列合并口径与 build_year_map 相同(非 E 行 > 年小;term 取选中行),
    只是作用域收窄到单系列行。官方语义:系列 = 入学点(J1/J2/J3 = Year 1/2/3
    Entry,见 read_series_labels),BEDHACLSJ2 类 Y2 入学者在 Y3 才修
    UNI2002BCW,而默认图(系列 1 口径)给 Y2 —— 批次 2 验收遗留②。
    """
    by_plan = collections.defaultdict(list)
    for r in rows:
        by_plan[r["plan"]].append(r)
    prog_plans = collections.defaultdict(set)
    for plan in by_plan:
        p = norm_plan(plan, programmes, aliases)
        if p is not None:
            prog_plans[p].add(plan)

    series_meta: dict[str, dict] = {}
    overrides: dict[str, dict] = {}
    for p, plans in sorted(prog_plans.items()):
        default = year_map.get(p)
        if default is None:
            continue
        plan_by_series = collections.defaultdict(set)
        for pl in plans:
            s = series_of(pl)
            if s.isdigit():
                plan_by_series[s].add(pl)
        meta: dict[str, dict] = {}
        for s in sorted(plan_by_series):
            per_course = collections.defaultdict(list)
            for pl in plan_by_series[s]:
                for r in by_plan[pl]:
                    if r.get("yr") is None:
                        continue
                    per_course[r["code"]].append((0 if r.get("type") != "E" else 1, r))
            entry: dict[str, dict] = {}
            for code, pairs in per_course.items():
                best_kind = min(k for k, _ in pairs)
                pool = [r for k, r in pairs if k == best_kind]
                year = min(r["yr"] for r in pool)
                same = [r for r in pool if r["yr"] == year]
                m = TERM.search(same[0].get("term") or "")
                entry[code] = {
                    "year": int(year),
                    "term": SEM.get(m.group(2), "autumn") if m else "autumn",
                }
            label = next((labels[pl] for pl in sorted(plan_by_series[s])
                          if labels.get(pl)), None)
            meta[s] = {"entry_level": int(s),
                       "label": label or f"Year {s} Entry"}
            diff = {c: v for c, v in sorted(entry.items())
                    if c in default and default[c] != v}
            if diff:
                overrides.setdefault(p, {})[s] = diff
        if meta:
            series_meta[p] = meta
    return series_meta, overrides


def build_year_map(rows, programmes, aliases=None):
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
        p = norm_plan(plan, programmes, aliases)
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


_CJK = re.compile(r"[一-鿿]")
_DANGLING = re.compile(r"\s(&|,|AND|OF|FOR|TO|IN|THE)$", re.IGNORECASE)


def _cjk_ratio(s: str) -> float:
    if not s:
        return 0.0
    cjk = len(_CJK.findall(s))
    return cjk / max(len(re.sub(r"\s", "", s)), 1)


def _clean_title_parts(parts: list[str]) -> str:
    """中英混排去重(码行上中文名、下行英文名 → 留英;纯中 → 留中)+ 悬尾修剪。"""
    parts = [p for p in (x.strip() for x in parts) if p]
    if any(_cjk_ratio(p) > 0.3 for p in parts) and any(_cjk_ratio(p) <= 0.3 for p in parts):
        parts = [p for p in parts if _cjk_ratio(p) <= 0.3]
    title = re.sub(r"\s+", " ", " ".join(parts)).strip()
    while _DANGLING.search(title):
        title = _DANGLING.sub("", title)
    return title


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

        def _next_frag(k: int) -> str:
            """码行后第 k 行的标题列簇(空行/结构行返回空)。"""
            if k >= len(lines):
                return ""
            nl = lines[k]
            if (CODE.search(nl) or TERM.search(nl) or STOP_TITLE.search(nl)
                    or TAIL.search(nl)):
                return ""
            return _title_cluster(nl, code_x)

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
        on_line = re.sub(r"\s+", " ", joined[jm.end():t.start()].strip()) if jm and t else ""
        parts = [on_line] if on_line else []
        if not parts:
            # 标题行前置(多行标题单元格把首行吐在码行前,UNI3002BEW/GIP 类);
            # 中文课名行同位 —— _clean_title_parts 负责中英混排去重
            if i > 0:
                prev = lines[i - 1]
                if not (CODE.search(prev) or TERM.search(prev)
                        or STOP_TITLE.search(prev) or TAIL.search(prev)
                        or CAPTION.search(prev)):
                    parts.append(_title_cluster(prev, code_x))
        # 续行:标题在码行外(前置路径)/为空/悬尾连接词/括号未闭合时,补 1 行
        # (上限 1:第 2 行起无法与「下一行的前置标题」区分,宁缺勿贪)
        probe = _clean_title_parts(parts)
        need_more = (not on_line) or not probe or _DANGLING.search(probe) \
            or probe.count("(") > probe.count(")")
        if _next_frag(i + 1) and need_more:
            parts.append(_next_frag(i + 1))
        title = _clean_title_parts(parts)
        if title and not JUNK_TITLE.search(title):
            titles.setdefault(cm.group(1) + cm.group(2), titlecase(title))
    return slots, titles


def build_ge_slots_and_names(rows, programmes, year_map, aliases=None):
    """只解析选定系列的文件(全 433 份逐份 pdftotext 太慢且无必要)。"""
    by_plan_files = collections.defaultdict(set)
    for r in rows:
        by_plan_files[r["plan"]].add(r["file"])

    plans_by_prog = collections.defaultdict(list)
    for plan in by_plan_files:
        p = norm_plan(plan, programmes, aliases)
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


def build_additions(rows, programmes, aliases=None):
    """missing 78 → {主码: {cat: [课码]}} + 官方学分 {课码: cr}。"""
    with open(os.path.join(AS, "verify/final_result2.json"), encoding="utf-8") as f:
        missing = json.load(f)["missing"]

    # (主码, 课码) → type 集 / cr 计数(跨全部系列)
    types = collections.defaultdict(set)
    crs = collections.defaultdict(collections.Counter)
    for r in rows:
        p = norm_plan(r["plan"], programmes, aliases)
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


def build_programme_pool_seed(rows, programmes, year_map, aliases=None):
    """空规则实体(批次 3,BSSCHWSJ)→ 从官方 advice 行种课池 + 学分。

    触发:programmes.py 实体带显式 ``pool_seed: True`` 标记(骨架实体的
    静态声明;不能用「课池为空」判定——本生成器的输出会被 programmes.py
    在 import 时并回 PROGRAMMES,二次重生成时空池已被上一轮种子填上,
    判据会失效导致种子从输出中消失)。
    分类口径与 build_additions 同源:type C(含 C∩E,非 E 口径)→core、
    E→elective、ENG→english;UNI 前缀码强制归 university-core(advice 表
    把 University Core 行也打 C)。min_credits 不在生成器侧改(0 = 实体
    不裁学分,伞形八专修的毕业数学归批次 4)。学分 = 官方行众数平票取小。
    """
    types = collections.defaultdict(set)
    crs = collections.defaultdict(collections.Counter)
    for r in rows:
        p = norm_plan(r["plan"], programmes, aliases)
        if p is None or not r.get("type"):
            continue
        types[(p, r["code"])].add(r["type"])
        if r.get("cr") is not None:
            crs[(p, r["code"])][r["cr"]] += 1

    seed: dict[str, dict[str, list]] = {}
    credits: dict[str, int] = {}
    for main in sorted(year_map):
        prog = programmes.get(main)
        if not prog or not prog.get("pool_seed"):
            continue
        pools: dict[str, list] = collections.defaultdict(list)
        for (p, code), ts in sorted(types.items()):
            if p != main:
                continue
            if code.startswith("UNI"):
                pools["university-core"].append(code)
            elif "C" in ts:
                pools["core"].append(code)
            elif "ENG" in ts:
                pools["english"].append(code)
            elif ts == {"E"}:
                pools["elective"].append(code)
        pools = {k: v for k, v in sorted(pools.items()) if v}
        if not pools:
            continue
        seed[main] = pools
        for code in (c for pool in pools.values() for c in pool):
            vote = crs.get((main, code))
            if vote:
                credits[code] = min(vote, key=lambda v: (-vote[v], v))
    return seed, credits


def emit(year_map, ge_slots, titles, additions, credits, unmapped,
         pool_seed=None, seed_credits=None, series_meta=None, series_overrides=None):
    def py(v):
        return json.dumps(v, ensure_ascii=False, separators=(", ", ": "))

    pool_seed = pool_seed or {}
    seed_credits = seed_credits or {}
    series_meta = series_meta or {}
    series_overrides = series_overrides or {}
    L = []
    L.append('"""Auto-generated by scripts/build_programme_year_map.py — DO NOT HAND-EDIT.')
    L.append("")
    L.append("Per-专业修读年份映射(选课数据修复 · 批次 2/3/5)。架构动机/建模决策/数据源")
    L.append("见生成器 docstring;官方依据 = advice sheet PDF(2026/27)+ 复核报告-2026-08-19.md。")
    L.append("")
    L.append("Regenerate: python3 scripts/build_programme_year_map.py")
    L.append('"""')
    L.append("")
    L.append(f"# {len(year_map)} 专业 / {sum(len(v) for v in year_map.values())} 课次映射;"
             f" GE 占位 {sum(len(v) for v in ge_slots.values())} 槽;"
             f" 课名 {len(titles)};补池 {sum(len(c) for v in additions.values() for c in v.values())} 课次"
             f"({len(additions)} 专业);骨架实体种池 {sum(len(c) for v in pool_seed.values() for c in v.values())} 课次"
             f"({len(pool_seed)} 专业);系列轴差分 {sum(len(c) for v in series_overrides.values() for c in v.values())} 课次"
             f"({len(series_overrides)} 专业)。未映射 plan:{dict(unmapped) or '无'}。")
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
    L.append("# 批次 3 骨架实体课池(无 Requirements 规则的实体,BSSCHWSJ 类):advice 行")
    L.append("# 官方 type 分类灌入(min_credits 保持 0 = 不裁学分,毕业数学归批次 4)。")
    L.append("PROGRAMME_POOL_SEED = {")
    for p in sorted(pool_seed):
        cats = ", ".join(f'{py(k)}: {py(v)}' for k, v in pool_seed[p].items())
        L.append(f"    {py(p)}: {{{cats}}},")
    L.append("}")
    L.append("")
    L.append("# 骨架实体课官方学分(advice 行众数平票取小)。")
    L.append("POOL_SEED_CREDITS = {")
    for c in sorted(seed_credits):
        L.append(f"    {py(c)}: {seed_credits[c]},")
    L.append("}")
    L.append("")
    L.append("# 批次 5 双系列 cohort 轴:各专业的入学点系列(页眉 Admit Cohort 佐证,")
    L.append("# 尾数字 N = Year N Entry,420/420 文件核对)。onboarding 采入学点后,")
    L.append("# courses._placements_for 按用户 entry_level 取对应系列视图。")
    L.append("PROGRAMME_ENTRY_SERIES = {")
    for p in sorted(series_meta):
        inner = ", ".join(
            f'{py(s)}: {{"entry_level": {m["entry_level"]}, "label": {py(m["label"])}}}'
            for s, m in sorted(series_meta[p].items())
        )
        L.append(f"    {py(p)}: {{{inner}}},")
    L.append("}")
    L.append("")
    L.append("# 系列年份差分:该入学点系列的官方修读年/学期 ≠ 默认合并图(系列 1 口径)")
    L.append("# 的课,只存差分(全量 = my_rows.json 按 per-系列同口径重算;CI 有全等锁)。")
    L.append("# 例:BEDHACLSJ 系列 2(Y2 入学)的 UNI2002BCW 在 Y3,默认图是 Y2。")
    L.append("SERIES_YEAR_OVERRIDES = {")
    for p in sorted(series_overrides):
        parts = []
        for s, diff in sorted(series_overrides[p].items()):
            courses = ", ".join(
                f'{py(c)}: {{"year": {v["year"]}, "term": "{v["term"]}"}}'
                for c, v in diff.items()
            )
            parts.append(f"{py(s)}: {{{courses}}}")
        L.append(f"    {py(p)}: {{{', '.join(parts)}}},")
    L.append("}")
    L.append("")
    return "\n".join(L)


def main():
    from app.data.programmes import PROGRAMMES, PROGRAMME_ALIASES

    rows = read_rows()
    year_map, unmapped = build_year_map(rows, PROGRAMMES, PROGRAMME_ALIASES)
    ge_slots, titles = build_ge_slots_and_names(rows, PROGRAMMES, year_map, PROGRAMME_ALIASES)
    additions, credits, no_type = build_additions(rows, PROGRAMMES, PROGRAMME_ALIASES)
    pool_seed, seed_credits = build_programme_pool_seed(
        rows, PROGRAMMES, year_map, PROGRAMME_ALIASES)
    labels = read_series_labels()
    series_meta, series_overrides = build_series_axes(
        rows, PROGRAMMES, year_map, labels, PROGRAMME_ALIASES)

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(emit(year_map, ge_slots, titles, additions, credits, unmapped,
                     pool_seed, seed_credits, series_meta, series_overrides))

    print(f"year_map: {len(year_map)} 专业 / {sum(len(v) for v in year_map.values())} 课次")
    print(f"ge_slots: {sum(len(v) for v in ge_slots.values())} 槽 / {len(ge_slots)} 专业")
    print(f"titles: {len(titles)}")
    print(f"additions: {sum(len(c) for v in additions.values() for c in v.values())} 课次 / {len(additions)} 专业")
    print(f"credits: {len(credits)}(GIP 类 0 学分:{sum(1 for v in credits.values() if v == 0)} 门)")
    print(f"pool_seed: {sum(len(c) for v in pool_seed.values() for c in v.values())} 课次 / {len(pool_seed)} 专业 {sorted(pool_seed)}")
    print(f"series_meta: {len(series_meta)} 专业 / labels {len(labels)} plan 码")
    print(f"series_overrides: {sum(len(c) for v in series_overrides.values() for c in v.values())} 课次差分 / {len(series_overrides)} 专业")
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
