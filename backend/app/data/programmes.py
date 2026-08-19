"""HKMU programme definitions — graduation requirements & course mappings.

Backend mirror of ``frontend/js/data/programmes.js``. Kept as a Python module
(rather than a DB table) because programme curricula change rarely and the web
client already ships the same data statically. The two copies MUST stay in
sync; a deferred cleanup is to point the web client at ``GET /courses/programmes``
and retire the JS copy.

Each programme:
  - code, name (trilingual: en / zh-CN / zh-TW), school, total_credits
  - coming_soon: True for placeholder programmes with no curriculum yet
  - categories: { cat_key: { min_credits, color, pick_n?, courses: [ids] } }
  - template: default {course_id: status} seed for new users

Course IDs must match the ``id`` column in the ``courses`` table
(seed_courses.py).
"""

PROGRAMMES = {
    # ── DSAI (Data Science & AI) — fully populated ────────────────────────
    # Graduation requirements mirror HKMU's official Programme Requirements
    # PDF (3CRU_FTU_ST_BSCHDSAIJ.pdf). Verified 2026-08-13 against the PDF:
    # 90 core (incl. 6cr Data Science Project) + 9 elective + 9 university-core
    # + 6 english + 6 GE = 120 (self-consistent). We split the 6cr project out
    # of core into its own `project` category (core 84 + project 6 = 90) to
    # avoid double-counting. Elective is pick 3 of 6 (9cr), per PDF Table 2.
    "BSCHDSAIJ": {
        "code": "BSCHDSAIJ",
        "name": {
            "en": "BSc (Hons) Data Science & Artificial Intelligence",
            "zh-CN": "数据科学及人工智能理学士",
            "zh-TW": "數據科學及人工智能理學士",
        },
        "school": "School of Science and Technology",
        "total_credits": 120,
        "categories": {
            "core": {
                "min_credits": 84,
                "color": "blue",
                "courses": [
                    # Year 1
                    "COMP1080SEF", "IT1020SEF", "MATH1410SEF",
                    "COMP2090SEF", "IT1030SEF", "STAT1510SEF", "STAT2610SEF",
                    # Year 2
                    "COMP2020SEF", "COMP2640SEF", "MATH2150SEF", "STAT2510SEF",
                    "COMP2030SEF", "IT2900SEF", "STAT2520SEF", "STAT2630SEF",
                    # Year 3
                    "COMP3200SEF", "COMP3500SEF", "STAT3660SEF", "COMP3130SEF",
                    "COMP3510SEF", "COMP3920SEF", "STAT3110SEF", "COMP4820SEF",
                    # Year 4 (COMP4610SEF is the 6-cr Project — see `project`
                    # category below; it must NOT also live in core, or its
                    # credits get double-counted toward graduation.)
                    "COMP3810SEF", "COMP4330SEF", "COMP4930SEF",
                    "COMP4210SEF", "COMP4600SEF",
                ],
            },
            "elective": {
                "min_credits": 9,
                "color": "purple",
                "pick_n": 3,  # pick 3 of 6 (9cr per PDF Table 2)
                "courses": [
                    "ELEC3050SEF", "COMP4630SEF", "MATH4950SEF",
                    "ELEC4310SEF", "ELEC3250SEF", "ELEC4710SEF",
                ],
            },
            "project": {
                "min_credits": 6,
                "color": "amber",
                "courses": ["COMP4610SEF"],
            },
            "english": {
                "min_credits": 6,
                "color": "emerald",
                "courses": ["ENGL1101AEF", "ENGL1202EEF"],
            },
            "general-ed": {
                "min_credits": 6,
                "color": "pink",
                "pick_n": 2,  # take 2 GE courses, each from a DIFFERENT field
                # Dynamic GE pool: _compute_graduation resolves the real GE
                # course list from ge_courses_for() + the courses table (seeded
                # by seed_courses.py). GEN001/GEN002 were placeholders — retired
                # (kept harmlessly in seed, no longer referenced here).
                "pool": "ge",
                "courses": [],
            },
            "university-core": {
                "min_credits": 9,
                "color": "indigo",
                "courses": ["UNI1002ABW", "UNI1012ABW", "UNI2002BEW", "UNI3002BEW"],
            },
        },
        "template": {
            "COMP1080SEF": "completed",
            "IT1020SEF": "completed",
            "MATH1410SEF": "completed",
            "ENGL1101AEF": "completed",
            "UNI1002ABW": "completed",
            "UNI1012ABW": "completed",
            "COMP2090SEF": "in_progress",
            "IT1030SEF": "in_progress",
            "STAT1510SEF": "in_progress",
            "STAT2610SEF": "in_progress",
            "ENGL1202EEF": "in_progress",
        },
    },

    # ── Computer Science — placeholder ────────────────────────────────────
    "BSCHCSJ": {
        "code": "BSCHCSJ",
        "name": {
            "en": "BSc (Hons) Computer Science",
            "zh-CN": "计算机科学理学士",
            "zh-TW": "計算機科學理學士",
        },
        "school": "School of Science and Technology",
        "total_credits": 120,
        "coming_soon": True,
        "categories": {
            "core": {"min_credits": 0, "color": "blue", "courses": []},
            "elective": {"min_credits": 0, "color": "purple", "courses": []},
            "project": {"min_credits": 0, "color": "amber", "courses": []},
            "english": {"min_credits": 0, "color": "emerald", "courses": []},
            "general-ed": {"min_credits": 0, "color": "pink", "courses": []},
            "university-core": {"min_credits": 0, "color": "indigo", "courses": []},
        },
        "template": {},
    },

    # ── Cyber & Computer Security — placeholder ──────────────────────────
    "BSCHCCSJ": {
        "code": "BSCHCCSJ",
        "name": {
            "en": "BSc (Hons) Cyber and Computer Security",
            "zh-CN": "网络安全及计算机保安理学士",
            "zh-TW": "網絡安全及計算機保安理學士",
        },
        "school": "School of Science and Technology",
        "total_credits": 120,
        "coming_soon": True,
        "categories": {
            "core": {"min_credits": 0, "color": "blue", "courses": []},
            "elective": {"min_credits": 0, "color": "purple", "courses": []},
            "project": {"min_credits": 0, "color": "amber", "courses": []},
            "english": {"min_credits": 0, "color": "emerald", "courses": []},
            "general-ed": {"min_credits": 0, "color": "pink", "courses": []},
            "university-core": {"min_credits": 0, "color": "indigo", "courses": []},
        },
        "template": {},
    },

    # ── Social Sciences (generic, five streams) — 批次 3 ──────────────────
    # BSSCHWSJ 是 HKMU 社科大类学位(官方:「Bachelor of Social Sciences
    # with Honours — New Programme from 2023 Autumn」,五大 Stream:I AGS /
    # II ECON / III AS(再分 Criminology/Cultural&Heritage/Social Policy&
    # Youth 三 specialization)/ IV GCS / V PPA;源 = 招生列表注脚 12 +
    # hkmu.edu.hk/ss/programmes/undergraduate/bachelor-of-social-sciences-
    # with-honours-with-streams/,繁中官名「社會科學榮譽學士」)。2023 秋重组
    # 起 Year-1 统一大类入学(JS9009 / BSSCHWSJ1),学年末选 Stream,毕业证
    # 按 Stream 授名 —— 原 5 个独立码(BSSCHAGSJ/ECHJ/GCSJ/J/PAJ)随之停招
    # (见 DISCONTINUED_CODES 批次 3 注)。advice sheet 按 BSSCHWSJ1/2/3 三套
    # 入学系列出 57 份年表(covers/BSSCHWSJ.pdf 封面:「Programme Code:
    # BSSCHWSJ1 / BSSCHWSJ2 / BSSCHWSJ3」)。
    # 此前 skill.md 目录树把 8 个伞码段(BSSCHWSJ_SCHJ-AGS 等)误当组名,
    # 463 行官方课整段挂到前一个专业(BFAHIDDAJ)名下,且专业本体不在
    # PROGRAMMES → 不可搜不可规划(复核报告声明 12)。批次 3 建实体:课池由
    # 生成器从官方 advice sheet 行(my_rows.json, type C/E/ENG)按「C(含
    # C∩E,非 E 口径)→core / E→elective / ENG→english / UNI 前缀→
    # university-core」灌入(PROGRAMME_POOL_SEED,programmes.py import 时并入)。
    # ⚠️ min_credits 全 0 = 本实体不裁毕业学分:各 Stream 构成互不相同
    # (官方 Requirements PDF 3CRU_FTU_AS_BSSCHWSJ_{SCHJ-AGS,SCHJ-AS,
    # SCHJ-PPA}_202607_V5,Y1 入学:AGS=core72+ME9+EA15+UC9+UE6+GE9,
    # AS=core69+ME12+EA15+UC9+UE6+GE9,PPA=core81+ME3-6+EA12-15+UC9+UE6+
    # GE6),伞形单实体无法断言单一分档;各 Stream 分档 + 1000-level≤30 /
    # 3000≥24 / 4000≥24 层级约束 + PPA FYRP 双路径,归批次 4 规则建模。
    # total_credits=120 依据 = 上述官方 PDF Y1 入学「obtain 120 credit-units」
    # (三个 Stream 恒和验证;Y2/Y3 入学为 93/66)。
    "BSSCHWSJ": {
        "code": "BSSCHWSJ",
        "name": {
            "en": "Bachelor of Social Sciences with Honours",
            "zh-CN": "社会科学荣誉学士",
            "zh-TW": "社會科學榮譽學士",
        },
        "school": "Wu Jieh Yee School of Arts and Social Sciences",
        "total_credits": 120,
        # 骨架实体标记:build_programme_year_map.py 据此为该实体生成
        # PROGRAMME_POOL_SEED(官方 advice 行种池),本文件 import 时并回
        "pool_seed": True,
        "categories": {
            "core": {"min_credits": 0, "color": "blue", "courses": []},
            "elective": {"min_credits": 0, "color": "purple", "courses": []},
            "project": {"min_credits": 0, "color": "amber", "courses": []},
            "english": {"min_credits": 0, "color": "emerald", "courses": []},
            "general-ed": {"min_credits": 0, "color": "pink", "pool": "ge", "pick_n": 2, "courses": []},
            "university-core": {"min_credits": 0, "color": "indigo", "courses": []},
        },
        "template": {},
    },
}

# ── Auto-generated graduation rules for the other 54 FT undergraduate
# programmes (T33/T34). See programme_rules.py for provenance and the
# modelling decisions (elective → credit pool; PDF sections folded into the
# standard categories). Merged AFTER the hand-curated block above: DSAI is
# deliberately absent from PROGRAMME_RULES so its hand-verified entry (with
# the COMP4610SEF project split) stays authoritative, and the former
# coming_soon placeholders (BSCHCSJ/BSCHCCSJ) are replaced wholesale.
from .programme_rules import PROGRAMME_RULES  # noqa: E402

PROGRAMMES.update(PROGRAMME_RULES)

# ── 批次 2 补池(选课数据修复,advice sheet 缺课 78 课次)─────────────────────
# 官方 Course Advice Sheets 列出但 PROGRAMME_RULES(Requirements PDF)没覆盖的课
# (GIP 系列 / UNI3002BEW 外溢课 / STAMJ 菜单页课等,清单与口径见
# programme_year_map.py 的 POOL_ADDITIONS)。在别名复制前并入,别名专业同步生效。
# 幂等:courses 列表按去重追加,重复调用不会重复插入(测试用)。
from .programme_year_map import POOL_ADDITIONS, PROGRAMME_POOL_SEED  # noqa: E402


def _apply_pool_additions(additions: dict) -> None:
    for _code, _cats in additions.items():
        _prog = PROGRAMMES.get(_code)
        if not _prog or _prog.get("coming_soon"):
            continue
        _pcats = _prog.setdefault("categories", {})
        for _cat_key, _courses in _cats.items():
            _cat = _pcats.setdefault(
                _cat_key, {"min_credits": 0, "color": "blue", "courses": []}
            )
            _ids = _cat.setdefault("courses", [])
            for _cid in _courses:
                if _cid not in _ids:
                    _ids.append(_cid)


_apply_pool_additions(POOL_ADDITIONS)
# 批次 3 骨架实体种池(BSSCHWSJ:官方 advice 行 type 分类),幂等同上
_apply_pool_additions(PROGRAMME_POOL_SEED)

# ── 同专业变体码别名 ─────────────────────────────────────────────────
# 官方 Requirements PDF 每个专业只印一个主码,但课程目录 PDF 多收了 cohort
# 变体码(J1/F3 等入学批次编码差异)——目录里同名专业两行,一行有毕业规则
# 一行没有,学生会选到"没有"的那行。变体码直接复用主码规则(同名同专业,
# 课程表略有出入不影响毕业要求计算)。BSSCHPJ/BSSCHPWSJ 是同名的异码对。
PROGRAMME_ALIASES = {
    "BAPHBMJ1": "BAPHBMJ",
    "BEDHACLSJ1": "BEDHACLSJ",
    "BNHGJ1": "BNHGJ",
    "BNHMJ1": "BNHMJ",
    "BSCHPTJ1": "BSCHPTJ",
    "BENGHECEJ1": "BENGHECEJ",
    "BSCHCEF3": "BSCHCEF",
    "BSSCHPJ": "BSSCHPWSJ",
    "HDNGF1": "HDNGF",
    "HDNMF1": "HDNMF",
    # 批次 3:BSCHCOMPF3 = BSc (Hons) Computing 的 Y3 入学(senior entry)在招
    # 码——官方指南 57 封面之一(BSCHCOMPF3.pdf,内文仅此一码);4 年制裸码
    # BSCHCOMPF 的 Requirements 规则(63cr,FTU_ST_BSCHCOMPF_202403_V1)同样
    # 适用。年份映射侧 my_rows 的 BSCHCOMPF3 17 行批次 2 已经裸码回退灌在
    # BSCHCOMPF 名下,此处补上规划入口。
    "BSCHCOMPF3": "BSCHCOMPF",
}
for _alias, _main in PROGRAMME_ALIASES.items():
    if _alias not in PROGRAMMES and _main in PROGRAMMES:
        _entry = dict(PROGRAMMES[_main])
        _entry["code"] = _alias
        PROGRAMMES[_alias] = _entry

# 伞形专业的官方入学系列码(covers/ 封面「Programme Code」行原样):非变体
# (同专业同规则),仅作 picker 搜索别名与旧保存码解析提示,不复制规则实体。
PROGRAMME_SERIES_HINTS = {
    "BSSCHWSJ": ["BSSCHWSJ1", "BSSCHWSJ2", "BSSCHWSJ3"],
}

# ── 停招专业(2026-08-17 子代理核查:全部不在 2026/27 招生表、官方专业页 404、
# 站内搜索无;毕业要求只剩旧 5 学分制 Prog_req_{CODE}.pdf,不建 3cru 规则)──
# 目录里保留(存量 phase-out 学生仍可浏览课程目录),选课器挂「已停招」徽标。
DISCONTINUED_CODES = frozenset({
    "BBAACTF", "BBABFF", "BBACAF", "BBAHRMF", "BBAIBF", "BBAMGTF",
    "BBAMKTF", "BBAHATJ", "BBAHBIAJ", "BBAHCGJ", "BBAHDBJ", "BBAHFJ",
    "BBAHFREJ", "BBAHFRMJ", "BBAHFTIJ", "BBAHGBMJ", "BBAHHSTMJ", "BBAHREFMJ",
    "BHMF", "BIHAMHJ", "BSRMHJ", "BTPMF", "BAHCIEF3", "BAHECLJ",
    "BFAHPDAJ", "BSSCHEPAJ", "BSSCHPMHJ", "BLSBCGBHJ1", "BCOMPHITJ", "BENGHCEEJ",
    "BENGHTCJ", "BSCHDSJ", "BSCHENSF3", "BSCHLSJ", "BSCHTSFF3", "BSCHTSCJ",
    # ── 批次 3(2026-08-19 官方招生页核查,admissions.hkmu.edu.hk)──────────
    # 社科 5 个独立学位 2023 秋重组为 BSSCHWSJ 大类学位的五个 Stream
    # (招生总列表 admissions.hkmu.edu.hk/ug/programmes/ 已无此 5 行;详情页
    # hkmu.edu.hk/ss/programmes/undergraduate/bachelor-of-social-sciences-
    # with-honours-with-streams/ Streams 表逐一对应;「New Programme from
    # 2023 Autumn」;毕业证按 Stream 授名,故在读存量仍按旧规则规划):
    "BSSCHAGSJ",   # → BSSCHWSJ Stream I(旧招生页 /ug/as/ageing-society…/ 存档)
    "BSSCHECJ",    # → Stream II(Applied Economics)
    "BSSCHJ",      # → Stream III(Applied Social Studies,3 specialization)
    "BSSCHGCSJ",   # → Stream IV(Global and China Studies)
    "BSSCHPAJ",    # → Stream V(Politics and Public Administration)
    # 定性但**不挂标**:BBAHWBJ(World Business,Requirements PDF 202607_V1)
    # 2026/27 招生面三锚均无(总列表/BA 学院 Y1+Senior 列表/招生站搜索),
    # 疑 2027/28 新开——非停招,无目录行,不进本集合;BAPHBMJ1 经核查为
    # **在招**现行码(JUPAS JS9280,admissions.hkmu.edu.hk/ug/inter-school/
    # applied-psychology-business-management/),维持 PROGRAMME_ALIASES 变体。
})

DEFAULT_PROGRAMME_CODE = "BSCHDSAIJ"


def get_programme(code: str | None) -> dict:
    """Return the programme dict for ``code``, falling back to the default."""
    if code and code in PROGRAMMES:
        return PROGRAMMES[code]
    return PROGRAMMES[DEFAULT_PROGRAMME_CODE]


def programme_name(prog: dict, lang: str | None = None) -> str:
    """Return the localised programme name (mirrors the JS helper)."""
    name = prog.get("name", {}) if prog else {}
    if lang and lang in name:
        return name[lang]
    return name.get("en") or prog.get("code", "") if prog else ""
