"""批次 4:规则建模 — 手工规则层(选课数据修复,2026-08-19)。

与生成文件 programme_rules.py(DO NOT HAND-EDIT)分家:本文件承载四类
无法从 Requirements PDF 表格机械生成的官方规则,每条规则在 RULES_EVIDENCE
登记官方出处(哪份 PDF、哪一页/哪个区块、原文摘句)——验收标准.md 批次 4
第 5 条明文要求,缺出处即打回。

四类规则:
  1. MHFA 自修课(NURS1050NEF/NCF):2025/26 起 Y1 入学必修,0 学分但
     影响毕业判定。按用户 entry_term(入学学年)注入伪分类,非静态类别。
  2. 层级学分约束(1000 级上限 / 3000、4000 级下限):官方 Requirements
     PDF 表格附注,per-programme 挂靠。
  3. 互斥组合(不可兼修):官方标注 excluded / 不可同时修读的课组,
     同时标记 → 冲突提示(警告不拦截,学生可能 legitimately 双标)。
  4. WSJ 五 Stream 分档:BSSCHWSJ 伞形实体的真实毕业规则(批次 3 挂账,
     各 Stream 分档互不相同,伞码无法单一断言)。

cohort 闸(验收第 4 条):users.entry_term("2025-autumn"/"2025-spring",
T06 引导写入)解析出入学学年 → 2022/23 及以前 = 5 学分制(本 planner 全部
基于 3 学分制,老 cohort 展示提示不硬拦截);2023/24+ 正常 3cr。
"""

import re

# ── cohort 解析 ───────────────────────────────────────────────────────────────

_ENTRY_TERM_RE = re.compile(r"^(\d{4})-(autumn|spring)$")

# 3 学分制起点:2023/24 学年入学的 FT 本科生起(官方 3CRU 系列 PDF 适用面;
# 2022/23 及以前入学的存量学生仍是 5 学分制,见 RULES_EVIDENCE["cohort-3cr"])
THREE_CR_FROM_AY = 2023

# MHFA 必修起点:2025/26 学年起入学的 Y1 学生(NURS1050 自修课,页眉 Note;
# 见 RULES_EVIDENCE["mhfa-nurs1050"])
MHFA_FROM_AY = 2025


def parse_entry_ay(entry_term: str | None) -> tuple[int, int] | None:
    """entry_term("2025-autumn"/"2025-spring")→ 学年 (起始年, 结束年)。

    HKMU 两学期制:秋入学 Y 归属 AY Y/(Y+1);春入学 Y 归属 AY (Y-1)/Y
    (1 月入学属上一学年春季学期,与小程序 computeStudyInfo 同口径)。
    缺失/格式错 → None(老用户未走引导;消费方降级,不猜默认值)。
    """
    m = _ENTRY_TERM_RE.match(str(entry_term or "").strip())
    if not m:
        return None
    year, sem = int(m.group(1)), m.group(2)
    return (year, year + 1) if sem == "autumn" else (year - 1, year)


def cohort_profile(entry_term: str | None) -> dict:
    """entry_term → cohort 判定(学制 + MHFA 适用)。

    返回 {"entry_term", "ay"("2025/26"|None), "credit_system"("3cr"|"5cr"|None),
    "mhfa_required": bool}。entry_term 缺失 → 学制 None + MHFA False:
    宁可少判不误判(验收纪律:不让默认值悄悄错)。
    """
    ay = parse_entry_ay(entry_term)
    if ay is None:
        return {
            "entry_term": entry_term or None,
            "ay": None,
            "credit_system": None,
            "mhfa_required": False,
        }
    start = ay[0]
    return {
        "entry_term": entry_term,
        # HKMU 惯例两位尾年(2023/24)
        "ay": f"{start}/{(start + 1) % 100:02d}",
        "credit_system": "3cr" if start >= THREE_CR_FROM_AY else "5cr",
        "mhfa_required": start >= MHFA_FROM_AY,
    }


# ── 规则证据表(验收第 5 条:每条规则附官方出处)────────────────────────────
# rule_id → {"source": 文件+页码, "quote": 原文摘句, "checked": 核对日期}
# 所有下述规则结构按 rule_id 引用本表;CI 断言每条规则都能在此找到出处。
# 证据提取:2026-08-19 子代理全库扫描(pdfplumber,433 份 yr PDF/921 页零失败,
# 关键引文逐页人眼核对;方法与缓存见 docs/ops/选课选课/advice_sheets/yr/)。

RULES_EVIDENCE: dict[str, dict] = {
    "level-university": {
        "source": "advice_sheets/yr/BBAHMGTJ1-HMGTJ1-18_Yr1.pdf p1 页眉 Note "
                  "(433/433 份逐字相同)+ pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AS.pdf p1-p2 §1.1.1",
        "quote": "1. Year 1 entry students should complete no more than 30 "
                 "credit-units of courses at 1000-level; 2. Students should "
                 "complete at least 24 credit-units of courses at 3000-level; "
                 "3. Students should complete at least 24 credit-units of "
                 "courses at 4000-level. … (including all core, elective, "
                 "University English, GE and University Core courses) / "
                 "§1.1.1 … no more than 30 credit-units shall be at 1000-level, "
                 "at least 24 credit-units shall be at 3000-level and at least "
                 "24 credit-units shall be at 4000-level",
        "checked": "2026-08-19",
    },
    "level-hd-exempt": {
        "source": "推断(结构性):HDNGF/HDNMF 全课池 3000 级仅 9cr、4000 级 0cr,"
                  "2 年制副学士不可能满足 24/24 下限 → 层级下限按学士结构解读,"
                  "HD 不套用。yr Note 虽为全校 boilerplate,数字以 120cr 学士为语境。",
        "quote": "(无正面原文;基于课池结构的推断,置信中)",
        "checked": "2026-08-19",
    },
    "level-stamj-stemj-suspended": {
        "source": "推断(数据伪影):BSCHSTAMJ/BSCHSTEMJ 必修池自身 1000 级 "
                  "35/33cr > 30 帽,疑 Requirements 解析把「二选一」课压平成全必修;"
                  "在数据修复前对这两专业挂起 1000 帽(3000/4000 下限照常),",
        "quote": "(无正面原文;必修池矛盾的工程处置,待其 Requirements PDF 复核)",
        "checked": "2026-08-19",
    },
    "mhfa-nurs1050": {
        "source": "advice_sheets/yr/BBAHMGTJ1-HMGTJ1-18_Yr1.pdf p1 页眉 Note 第 4 点 "
                  "(433/433 份逐字相同)+ pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AS.pdf p2 §1.1.2",
        "quote": "From 2025/26 Academic Year onwards, students admitted via "
                 "Year-1 entry are required to complete the mandatory course of "
                 "Mental Health First Aid (MHFA) Training within first year of "
                 "studies. Students who fail to complete this course will not "
                 "meet the programme requirements for graduation. You should "
                 "complete the enrolment of MHFA Training by self-enrolment on "
                 "MyHKMU. • NURS 1050NEF (MHFA Training offered in English); OR "
                 "• NURS 1050NCF (MHFA Training offered in Chinese) / §1.1.2 … "
                 "(only applicable to Year 1 entry students admitted in and "
                 "after 2025/26 cohort)",
        "checked": "2026-08-19",
    },
    "cohort-3cr": {
        "source": "advice_sheets/GE_selection_guide_3cru.pdf p1(标题 For 3-credit-unit system)",
        "quote": "This guide applies only to undergraduate students admitted "
                 "under the following academic cohorts: … Year-1 entry students "
                 "admitted in the 2023/24AY and thereafter; Year-2 entry "
                 "students admitted in the 2024/25AY and thereafter …",
        "checked": "2026-08-19",
    },
    "excl-bus2000-bus2001": {
        "source": "advice_sheets/yr/BBAHMGTJ1-HMGTJ1-18_Yr1.pdf p1",
        "quote": "BUS 2000BEF 行:Excluded combination: BUS 2001BEF",
        "checked": "2026-08-19",
    },
    "excl-bus2020-mkt2050": {
        "source": "advice_sheets/yr/BBAHGBJ1-HGBJ1-18_Yr2.pdf p1",
        "quote": "BUS 2020BEF INTEGRATED BUSINESS FUNCTIONS 行:Excluded "
                 "combination: MKT 2050BEF",
        "checked": "2026-08-19",
    },
    "excl-gip200-gip201": {
        "source": "advice_sheets/yr/BBAHGBJ1-HGBJ1-18_Yr2.pdf p1 与 "
                  "BBAHASMJ1-HASMJ1-18_Yr2.pdf p1(双向)",
        "quote": "GIP 201BEF 行:Excluded combination: GIP 200BEF;"
                 "另一文件 GIP 200BEF 行:Excluded combination: GIP 201BEF",
        "checked": "2026-08-19",
    },
    "excl-act3031-act3011": {
        "source": "advice_sheets/yr/BBAHPAJ1-HPAJ1-18_Yr3.pdf p1",
        "quote": "ACT 3031BEF COMPANY ACCOUNTING 行:Excluded combination: ACT 3011BEF",
        "checked": "2026-08-19",
    },
    "excl-amve3003-cca3009": {
        "source": "advice_sheets/yr/BAHCAMDJ1_Yr3.pdf p1",
        "quote": "AMVE 3003ABF CINEMATIC SOUND DESIGN 行:Excluded combination: "
                 "CCA 3009ABF",
        "checked": "2026-08-19",
    },
    "excl-edu1150-gen2045": {
        "source": "advice_sheets/yr/BEDELSEHJ1_Yr1.pdf p1",
        "quote": "EDU 1150EEF INFORMATION TECHNOLOGY FOR LEARNING 行:Excluded "
                 "combination: GEN 2045EEF, GEN 2045ECF",
        "checked": "2026-08-19",
    },
    "excl-engl1101-bus1003": {
        "source": "advice_sheets/yr/BSCHBSBJ1_Yr1.pdf p1",
        "quote": "ENGL 1101AEF 行(原文拼错 UNVERSITY):Excluded Combination: "
                 "BUS 1003BEF, BUS 1004BEF, ENGL 2210EEF",
        "checked": "2026-08-19",
    },
    # ── WSJ 五 Stream 分档(pr_wsj/ 官方 Requirements PDF,202607_V5)─────
    "wsj-stream-ags": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AGS.pdf p1 §1.1.1 + p2 "
                  "§2.1.1/§3.1.1 + p3-p6 分档表(core 表勾选解码 24/19/14 行 "
                  "= 72/57/42cr,算术校验过)",
        "quote": "Y1: obtain 120 credit-units … core 72 (Table 1) + 9 cu major "
                 "electives (Table 2) + 15 cu electives in specific area "
                 "(Table 3, of which at least 6 credit-units must be at "
                 "4000-level) + UC 9 + UE 6 + GE 9;Y2 obtain 93;Y3 obtain 66 "
                 "(ME 9* + EA 6*,*Among the 15 … at least 6 at 4000-level)",
        "checked": "2026-08-19",
    },
    "wsj-stream-econ": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-ECON.pdf p1 §1.1.1 + p2 "
                  "§2.1.1/§3.1.1 + p3-p5 分档表(core 勾选 25/21/14 = 75/63/42cr)",
        "quote": "Y1: core 75 + 6 cu ME from Table 2 (2000-level) + 3 cu ME "
                 "from Table 3 + 15 cu EA (Table 4) + UC 9 + UE 6 + GE 6;"
                 "*Among the 18 (1.1.1.3+1.1.1.4) at least 6 at 4000-level;"
                 "Y2 obtain 90 credit-units;Y3 obtain 63 credit-units"
                 "(⚠️ 与其余 Stream 的 93/66 不同,官方原文)",
        "checked": "2026-08-19",
    },
    "wsj-stream-as": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AS.pdf p1 §1.1.1 + p2 "
                  "§2.1.1/§3.1.1 + p3-p7 分档表(core 勾选 23/19/14 = 69/57/42cr)",
        "quote": "Y1: core 69 + ME 12* + EA 15* + UC 9 + UE 6 + GE 9;"
                 "*Among the 27 (1.1.1.2+1.1.1.3) at least 9 cu at 4000-level;"
                 "Y2 obtain 93(core 57 + ME 9* + EA 15* + UC 9 + GE 3,无 UE);"
                 "Y3 obtain 66(无 UE 无 GE)。⚠️ AS 另有 ASCH/ASCR/ASSY 三个 "
                 "specialization 与无特化并列(独立 core 表 + 18cr spec),v1 建 "
                 "无特化主路径,特化挂账",
        "checked": "2026-08-19",
    },
    "wsj-stream-gcs": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-GCS.pdf p1 §1.1.1 + p2 "
                  "§2.1.1/§3.1.1 + p3-p5 分档表(core 勾选 19/14/10 = 57/42/30cr)",
        "quote": "Y1: core 57 + 6 cu Specialisation course (GCST3005ABF Summer "
                 "Immersive Programme) + ME 18* + EA 18* + UC 9 + UE 6 + GE 6;"
                 "*Among the 36 (1.1.1.3+1.1.1.4) at least 9 cu at 3000-level "
                 "and at least of 9 cu at 4000-level(官方原文 at least of);"
                 "Y2 obtain 93;Y3 obtain 66",
        "checked": "2026-08-19",
    },
    "wsj-stream-ppa": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ-SCHJ-PPA.pdf p1 §1.1.1 + p2 "
                  "§2.1.1/§3.1.1 + p3-p5 分档表(core 勾选 27/22/16 = 81/66/48cr)",
        "quote": "Y1: core 81 + 3 to 6 cu ME (6 cu for students taking POLS "
                 "4005AEF Final Year Research Project) + 12 to 15 cu EA "
                 "(12 cu for FYRP takers) + UC 9 + UE 6 + GE 6;恒和 "
                 "81+18+9+6+6=120;Y2 obtain 93;Y3 obtain 66(EA 3-6)。"
                 "v1 取标准路径 ME3+EA15,FYRP 路径学生在 EA 见保守偏差",
        "checked": "2026-08-19",
    },
    "level-ags-major": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AGS.pdf p1 §1.1.1(T3 附注;"
                  "Y1 措辞挂 EA,Y3 同式为 ME+EA 联合——按联合建模,记歧义)",
        "quote": "15 cu electives in specific area (Table 3), of which at "
                 "least 6 credit-units must be at 4000-level",
        "checked": "2026-08-19",
    },
    "level-as-major": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-AS.pdf p1 §1.1.1 脚注",
        "quote": "* Among the 27 credit-units obtained from 1.1.1.2 and "
                 "1.1.1.3, students must complete at least 9 credit-units at "
                 "4000-level",
        "checked": "2026-08-19",
    },
    "level-econ-major": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-ECON.pdf p1 §1.1.1 脚注",
        "quote": "* Among the 18 credit-units obtained from 1.1.1.3 and "
                 "1.1.1.4, students must complete at least 6 credit-units at "
                 "4000-level",
        "checked": "2026-08-19",
    },
    "level-gcs-major": {
        "source": "pr_wsj/3CRU_FTU_AS_BSSCHWSJ_SCHJ-GCS.pdf p1 §1.1.1 脚注",
        "quote": "* Among the 36 credit-units gained from 1.1.1.3 and 1.1.1.4, "
                 "students must complete at least 9 credit-units at 3000-level "
                 "and at least of 9 credit-units at 4000-level",
        "checked": "2026-08-19",
    },
}

# ── 1) MHFA 自修课(2025/26+ Y1 入学)─────────────────────────────────────────
# 0 学分自修课(NURS 1050 从不出现在带学分的选课表里——「不计学分」为基于
# 缺席的推断,置信中,见 RULES_EVIDENCE["mhfa-nurs1050"]);NEF/NCF = 同一门课
# 的英文班/中文班,完成其一即满足;经 MyHKMU 自登记。
# 以伪分类注入毕业判定(不进静态 categories——它只对 2025/26+ cohort 生效)。
# ⚠️ 条款原文限 Year-1 entry;系统无入学点(Y1/Y2/Y3)字段,对 2025/26+ 全部
# 入学者生效(高年级入学者被多要求——保守方向,误放行风险为零)。

MHFA_COURSES: list[str] = ["NURS1050NEF", "NURS1050NCF"]

# ── 2) 层级学分约束 ──────────────────────────────────────────────────────────
# 全校统一(General Requirements,433/433 份 yr Note 逐字相同,无专业变体):
# 1000 级 ≤30(原文限 Year-1 entry;同 MHFA 的入学点未建模备注)+ 3000 级
# ≥24 + 4000 级 ≥24,统计口径 = 全部计入学分的课(core/elective/English/
# GE/University Core)。HD 副学士结构性不可能满足 24/24 → 豁免;STAMJ/STEMJ
# 必修池数据伪影挂起 1000 帽(见 RULES_EVIDENCE)。
# 另有 per-programme 作用域规则(WSJ Stream 的「ME+EA 合计内 ≥N@4000/3000」
# 官方脚注):scope_categories 限定只聚合该组分类里已完成的课。
# level_rules_for(code) 返回规则列表:全校默认 + 该专业的 scoped 附加。

_LEVEL_UNIVERSITY_RULES = {
    "max": {"1000": 30},
    "min": {"3000": 24, "4000": 24},
    "rule_id": "level-university",
}
_LEVEL_CAP_SUSPENDED = frozenset({
    # 1000 帽挂起(必修池 35/33cr 自身超帽,疑解析压平二选一;3000/4000 照常)
    "BSCHSTAMJ", "BSCHSTEMJ",
})
_WSJ_MAJOR_CATS = ["major-elective", "area-elective"]

LEVEL_CREDIT_RULES: dict[str, list[dict]] = {
    # WSJ 各 Stream 的主修选修脚注(Y1 入学;scope=ME+EA 两池联合):
    #   AGS  T3 附注「of which at least 6 cu at 4000-level」(Y1 措辞挂 EA,
    #        Y3 同式为 ME+EA 联合,按联合建模并记歧义)
    #   AS   「Among the 27 (1.1.1.2+1.1.1.3) at least 9 at 4000」
    #   ECON 「Among the 18 (1.1.1.3+1.1.1.4) at least 6 at 4000」
    #   GCS  「Among the 36 (1.1.1.3+1.1.1.4) ≥9@3000 + ≥9@4000」
    "BSSCHWSJ-AGS": [{"min": {"4000": 6}, "scope_categories": _WSJ_MAJOR_CATS,
                       "rule_id": "level-ags-major"}],
    "BSSCHWSJ-AS": [{"min": {"4000": 9}, "scope_categories": _WSJ_MAJOR_CATS,
                      "rule_id": "level-as-major"}],
    "BSSCHWSJ-ECON": [{"min": {"4000": 6}, "scope_categories": _WSJ_MAJOR_CATS,
                        "rule_id": "level-econ-major"}],
    "BSSCHWSJ-GCS": [{"min": {"3000": 9, "4000": 9}, "scope_categories": _WSJ_MAJOR_CATS,
                       "rule_id": "level-gcs-major"}],
}

# ── 3) 互斥组合(不可兼修)───────────────────────────────────────────────────
# 官方「Excluded combination」列(433 份中 195 份含该列值;术语全库唯一,无
# not-be-taken/equivalent 等其他表述)。清单是 per-sheet 的(同一门课在不同
# 专业 sheet 的互斥清单不同,如 UNI 2002BEW)→ 每组挂 attested 专业 scope,
# 别名码(BBAHMGTJ1 等)经 PROGRAMME_ALIASES 折叠后匹配。
# 语义与「等价课」严格分开:本语料不存在 same-as/equivalent 表述(0 命中),
# 新旧码关系只以互斥面目出现(BIOL S203 等旧码目标暂不建模——涉 5cr cohort)。

EXCLUDED_COMBINATIONS: list[dict] = [
    {"courses": ["BUS2000BEF", "BUS2001BEF"], "rule_id": "excl-bus2000-bus2001",
     "programmes": ["BBAHMGTJ"]},
    {"courses": ["BUS2020BEF", "MKT2050BEF"], "rule_id": "excl-bus2020-mkt2050",
     "programmes": ["BBAHGBJ"]},
    {"courses": ["GIP200BEF", "GIP201BEF"], "rule_id": "excl-gip200-gip201",
     "programmes": ["BBAHGBJ", "BBAHASMJ"]},
    {"courses": ["ACT3031BEF", "ACT3011BEF"], "rule_id": "excl-act3031-act3011",
     "programmes": ["BBAHPAJ"]},
    {"courses": ["AMVE3003ABF", "CCA3009ABF"], "rule_id": "excl-amve3003-cca3009",
     "programmes": ["BAHCAMDJ"]},
    {"courses": ["EDU1150EEF", "GEN2045EEF", "GEN2045ECF"], "rule_id": "excl-edu1150-gen2045",
     "programmes": ["BEDELSEHJ"]},
    {"courses": ["ENGL1101AEF", "BUS1003BEF", "BUS1004BEF", "ENGL2210EEF"],
     "rule_id": "excl-engl1101-bus1003", "programmes": ["BSCHBSBJ"]},
]

# ── 4) WSJ 五 Stream 分档(批次 3 挂账)──────────────────────────────────────
# BSSCHWSJ 伞形单实体 → 五个 Stream 子实体(BSSCHWSJ-AGS 等),picker 仍单入口,
# 选伞码后由 planner 子选择器细化;programme_code 持久化 Stream 限定码。
# 建模口径(证据:pr_wsj/ 8 份官方 Requirements PDF,202607_V5,2026-08-19
# 子代理双引擎提取 + 24/24 算术校验,课码勾选位置字符坐标解码):
#   * v1 = Y1 入学路径(120cr);Y2/Y3 入学总分记入 entry_level_credits,
#     完整 Y2/Y3 分档(Y2 无 UE/Y3 无 UE 无 GE 的减免结构)挂账后续批次;
#   * 菜单按勾选年份过滤到 Y1 可修([1]/[1,2]/[1,3]/[1,2,3] 的并集);
#   * ECON 的 ME 拆两张表(T2 6cr@2000 + T3 3cr@3/4k)压平为一个 9cr 联合池
#     (T3 仅 2 门课,压平损失 = 少强制 3cr@3000+,记档);
#   * GCS 的 Specialisation(单门必修 GCST3005ABF 6cr)并入 core;
#   * PPA 的 ME/EA 范围档(3-6/12-15,FYRP 双路径)取标准路径 ME3+EA15,
#     FYRP(POLS4005AEF 6cr→ME6+EA12)路径学生会在 EA 见 12/15 的保守偏差,
#     记档待入学点字段(Y1/Y2/Y3)建模后精修;
#   * AS 三个 specialization(ASCH/ASCR/ASSY)是与「无特化」并列的独立
#     四选一路径(core 表互不相同,各含 18cr spec),v1 建无特化主路径;
#   * University English 的 ENGL1002/1003 替代(DSE 5+)未建模,记档。
# 流派名称中文为站内翻译(PDF 为英文版,官方中文名待官网核对)。

WSJ_STREAM_META: list[dict] = [
    {"code": "BSSCHWSJ-AGS", "key": "AGS",
     "name": {"en": "Ageing Society and Services Studies",
              "zh-CN": "长者社会及服务研究", "zh-TW": "長者社會及服務研究"}},
    {"code": "BSSCHWSJ-ECON", "key": "ECON",
     "name": {"en": "Applied Economics",
              "zh-CN": "应用经济学", "zh-TW": "應用經濟學"}},
    {"code": "BSSCHWSJ-AS", "key": "AS",
     "name": {"en": "Applied Social Studies",
              "zh-CN": "应用社会研究", "zh-TW": "應用社會研究"}},
    {"code": "BSSCHWSJ-GCS", "key": "GCS",
     "name": {"en": "Global and China Studies",
              "zh-CN": "全球与中国研究", "zh-TW": "全球與中國研究"}},
    {"code": "BSSCHWSJ-PPA", "key": "PPA",
     "name": {"en": "Politics and Public Administration",
              "zh-CN": "政治与公共行政", "zh-TW": "政治與公共行政"}},
]

_SCHOOL_SS = "Wu Jieh Yee School of Arts and Social Sciences"
_UNI_CORE_9 = ["UNI1002ABW", "UNI1012ABW", "UNI2002BEW", "UNI3002BEW"]
_WSJ_ENGLISH = ["ENGL1101AEF", "ENGL1102AEF"]

# Stream 课的学分补遗(POOL_SEED_CREDITS 之外的官方值;advice sheet 不含
# GCST3005ABF Summer Immersive,POLS4005AEF 在 POOL_SEED_CREDITS 已有 6)
WSJ_EXTRA_CREDITS = {"GCST3005ABF": 6}


def _wsj_stream(code, key, en, zh_cn, zh_tw, total, entry_credits, categories,
                rule_id):
    return {
        "code": code,
        "name": {"en": en, "zh-CN": zh_cn, "zh-TW": zh_tw},
        "school": _SCHOOL_SS,
        "total_credits": total,
        "entry_level_credits": entry_credits,
        "streams": list(WSJ_STREAM_META),
        "rule_id": rule_id,
        "categories": categories,
        "template": {},
    }


WSJ_STREAM_PROGRAMMES: dict[str, dict] = {
    # ── Stream I AGS:core72 + ME9 + EA15 + UC9 + UE6 + GE9(pick 3)───────
    "BSSCHWSJ-AGS": _wsj_stream(
        "BSSCHWSJ-AGS", "AGS",
        "BSSCHWSJ Stream I: Ageing Society and Services Studies",
        "社会科学荣誉学士( Stream I:长者社会及服务研究)",
        "社會科學榮譽學士( Stream I:長者社會及服務研究)",
        120, {1: 120, 2: 93, 3: 66},
        {
            "core": {"min_credits": 72, "color": "blue", "courses": [
                # [1]
                "ECON1001AEF", "POLS1001AEF", "PSYC1001AEF", "SOCI1001AEF",
                "STAT2003AEF",
                # [1,2]
                "SOCI2004AEF", "SOSC2001AEF", "SOSC3001AEF", "STAT2001AEF",
                "STAT2002AEF",
                # [1,2,3]
                "ECON3009AEF", "PSYC3010AEF", "PSYC4010AEF", "PUAD3001AEF",
                "SOCI3001AEF", "SOCI3007AEF", "SOCI3008AEF", "SOCI4003AEF",
                "SOCI4004AEF", "SOCI4006AEF", "SOSC3002AEF", "SOSC3003AEF",
                "SOSC4001AEF", "SOSC4002AEF",
            ]},
            "major-elective": {"min_credits": 9, "color": "purple",
                               "pool": "credits", "courses": [
                "COUN2002AEF", "ECON2001AEF", "ECON2002AEF", "POLS2003AEF",
                "PSYC2001AEF", "PUAD2001AEF", "SOCI2003AEF", "SOCI2005AEF",
                "SOSC2002AEF",
            ]},
            "area-elective": {"min_credits": 15, "color": "violet",
                              "pool": "credits", "courses": [
                "COUN2001AEF", "ECON3004AEF", "ECON3006AEF", "ECON3007AEF",
                "ECON3008AEF", "GCST4006AEF", "POLS3002AEF", "POLS3004AEF",
                "POLS4006AEF", "PSYC3004AEF", "PSYC3005AEF", "PSYC4001AEF",
                "PSYC4003AEF", "PSYC4005AEF", "PSYC4007AEF", "SOCI2001AEF",
                "SOCI3002AEF", "SOCI3003AEF", "SOCI3004AEF", "SOCI3005AEF",
                "SOCI3006AEF", "SOCI3009AEF", "SOCI4001AEF", "SOCI4007AEF",
                "SOCI4008AEF", "SOCI4009AEF", "SOSC2003AEF", "SOSC3004AEF",
            ]},
            "english": {"min_credits": 6, "color": "emerald",
                        "courses": list(_WSJ_ENGLISH)},
            "general-ed": {"min_credits": 9, "color": "pink", "pool": "ge",
                           "pick_n": 3, "courses": []},
            "university-core": {"min_credits": 9, "color": "indigo",
                                "courses": list(_UNI_CORE_9)},
        },
        "wsj-stream-ags",
    ),
    # ── Stream II ECON:core75 + ME9(压平)+ EA15 + UC9 + UE6 + GE6 ──────
    # ⚠️ Y2/Y3 = 90/63(官方原文,与其余 Stream 的 93/66 不同)
    "BSSCHWSJ-ECON": _wsj_stream(
        "BSSCHWSJ-ECON", "ECON",
        "BSSCHWSJ Stream II: Applied Economics",
        "社会科学荣誉学士( Stream II:应用经济学)",
        "社會科學榮譽學士( Stream II:應用經濟學)",
        120, {1: 120, 2: 90, 3: 63},
        {
            "core": {"min_credits": 75, "color": "blue", "courses": [
                "ECON1001AEF", "POLS1001AEF", "PSYC1001AEF", "SOCI1001AEF",
                "ECON2001AEF", "ECON2002AEF", "SOSC2002AEF", "SOSC2003AEF",
                "STAT2001AEF", "STAT2002AEF", "STAT2003AEF",
                "ECON3001AEF", "ECON3002AEF", "ECON3003AEF", "ECON3004AEF",
                "ECON3005AEF", "ECON3006AEF", "ECON3007AEF", "ECON3009AEF",
                "ECON4001AEF", "ECON4003AEF", "ECON4004AEF", "ECON4005AEF",
                "ECON4006AEF", "ECON4007AEF",
            ]},
            "major-elective": {"min_credits": 9, "color": "purple",
                               "pool": "credits", "courses": [
                # T2(6cr@2000)∪ T3(3cr@3/4k)压平
                "ECON2003AEF", "GCST2001AEF", "POLS2001AEF", "POLS2003AEF",
                "PSYC2001AEF", "PUAD2001AEF", "SOCI2002AEF", "SOCI2004AEF",
                "ECON3008AEF", "ECON4002AEF",
            ]},
            "area-elective": {"min_credits": 15, "color": "violet",
                              "pool": "credits", "courses": [
                "GCST3001AEF", "GCST3002AEF", "GCST3003AEF", "GCST3004AEF",
                "GCST4001AEF", "GCST4002AEF", "GCST4003AEF", "GCST4004AEF",
                "GCST4005AEF", "GCST4006AEF", "POLS3001AEF", "POLS3002AEF",
                "POLS3003AEF", "POLS3004AEF", "POLS3005AEF", "POLS4001AEF",
                "POLS4002AEF", "POLS4006AEF", "POLS4008AEF", "POLS4009AEF",
                "POLS4010AEF", "PSYC3001AEF", "PSYC3003AEF", "PSYC3004AEF",
                "PSYC3005AEF", "PSYC3006AEF", "PSYC3007AEF", "PSYC3010AEF",
                "PSYC4001AEF", "PSYC4003AEF", "PSYC4005AEF", "PSYC4007AEF",
                "PSYC4010AEF", "PUAD3001AEF", "PUAD4001AEF", "SOCI3003AEF",
                "SOCI3004AEF", "SOCI3005AEF", "SOCI3006AEF", "SOCI3007AEF",
                "SOCI3009AEF", "SOCI4007AEF", "SOCI4008AEF", "SOSC4001AEF",
            ]},
            "english": {"min_credits": 6, "color": "emerald",
                        "courses": list(_WSJ_ENGLISH)},
            "general-ed": {"min_credits": 6, "color": "pink", "pool": "ge",
                           "pick_n": 2, "courses": []},
            "university-core": {"min_credits": 9, "color": "indigo",
                                "courses": list(_UNI_CORE_9)},
        },
        "wsj-stream-econ",
    ),
    # ── Stream III AS(无特化):core69 + ME12 + EA15 + UC9 + UE6 + GE9 ────
    "BSSCHWSJ-AS": _wsj_stream(
        "BSSCHWSJ-AS", "AS",
        "BSSCHWSJ Stream III: Applied Social Studies",
        "社会科学荣誉学士( Stream III:应用社会研究)",
        "社會科學榮譽學士( Stream III:應用社會研究)",
        120, {1: 120, 2: 93, 3: 66},
        {
            "core": {"min_credits": 69, "color": "blue", "courses": [
                "ECON1001AEF", "POLS1001AEF", "PSYC1001AEF", "SOCI1001AEF",
                "STAT2003AEF",
                "SOCI2002AEF", "SOCI2004AEF", "STAT2001AEF", "STAT2002AEF",
                "ECON3007AEF", "PSYC3010AEF", "PUAD3001AEF", "SOCI2001AEF",
                "SOCI3003AEF", "SOCI3004AEF", "SOCI3006AEF", "SOCI3008AEF",
                "SOCI4002AEF", "SOCI4003AEF", "SOCI4004AEF", "SOCI4006AEF",
                "SOCI4008AEF", "SOSC3003AEF",
            ]},
            "major-elective": {"min_credits": 12, "color": "purple",
                               "pool": "credits", "courses": [
                # Y1 菜单 = [1]+[1,2]+[1,3]+[1,2,3]
                "ECON2002AEF", "PUAD2001AEF", "SOSC2002AEF",
                "COUN2002AEF", "ECON2001AEF", "POLS2003AEF", "PSYC2001AEF",
                "ECON3008AEF", "SOCI2005AEF", "SOCI3001AEF", "SOCI3007AEF",
                "SOCI3009AEF", "SOCI2003AEF",
            ]},
            "area-elective": {"min_credits": 15, "color": "violet",
                              "pool": "credits", "courses": [
                "COUN2001AEF", "ECON3004AEF", "ECON3006AEF", "ECON3009AEF",
                "GCST3002AEF", "GCST4006AEF", "POLS2002AEF", "POLS3002AEF",
                "POLS3003AEF", "POLS3004AEF", "POLS3005AEF", "POLS4006AEF",
                "PSYC3004AEF", "PSYC3005AEF", "PSYC3008AEF", "PSYC4001AEF",
                "PSYC4003AEF", "PSYC4005AEF", "PSYC4007AEF", "PSYC4010AEF",
                "PUAD4001AEF", "SOCI3002AEF", "SOCI3005AEF", "SOCI4001AEF",
                "SOCI4005AEF", "SOCI4007AEF", "SOCI4009AEF", "SOSC2001AEF",
                "SOSC3002AEF", "SOSC3004AEF", "SOSC4001AEF",
            ]},
            "english": {"min_credits": 6, "color": "emerald",
                        "courses": list(_WSJ_ENGLISH)},
            "general-ed": {"min_credits": 9, "color": "pink", "pool": "ge",
                           "pick_n": 3, "courses": []},
            "university-core": {"min_credits": 9, "color": "indigo",
                                "courses": list(_UNI_CORE_9)},
        },
        "wsj-stream-as",
    ),
    # ── Stream IV GCS:core63(含 spec GCST3005ABF)+ ME18 + EA18 + UC9 +
    #    UE6 + GE6 ────────────────────────────────────────────────────────
    "BSSCHWSJ-GCS": _wsj_stream(
        "BSSCHWSJ-GCS", "GCS",
        "BSSCHWSJ Stream IV: Global and China Studies",
        "社会科学荣誉学士( Stream IV:全球与中国研究)",
        "社會科學榮譽學士( Stream IV:全球與中國研究)",
        120, {1: 120, 2: 93, 3: 66},
        {
            "core": {"min_credits": 63, "color": "blue", "courses": [
                "ECON1001AEF", "POLS1001AEF", "PSYC1001AEF", "SOCI1001AEF",
                "STAT2003AEF",
                "POLS2002AEF", "POLS2003AEF", "STAT2001AEF", "STAT2002AEF",
                "ECON2003AEF", "GCST2001AEF", "GCST3002AEF", "GCST3004AEF",
                "GCST4001AEF", "GCST4002AEF", "GCST4003AEF", "GCST4006AEF",
                "POLS2001AEF", "SOCI4002AEF",
                # T2 Specialisation:GCST3005ABF Summer Immersive(6cr,必修单门)
                "GCST3005ABF",
            ]},
            "major-elective": {"min_credits": 18, "color": "purple",
                               "pool": "credits", "courses": [
                "ECON3006AEF", "ECON3007AEF", "GCST3001AEF", "GCST3003AEF",
                "GCST4004AEF", "GCST4005AEF", "POLS3001AEF", "POLS3003AEF",
                "POLS4006AEF", "POLS4010AEF", "SOCI3008AEF",
            ]},
            "area-elective": {"min_credits": 18, "color": "violet",
                              "pool": "credits", "courses": [
                "ECON2002AEF", "ECON3002AEF", "ECON3004AEF", "ECON3005AEF",
                "ECON4004AEF", "ECON4005AEF", "POLS3002AEF", "POLS3005AEF",
                "POLS4001AEF", "POLS4002AEF", "POLS4009AEF", "PSYC2001AEF",
                "PSYC3005AEF", "PUAD2001AEF", "PUAD4001AEF", "SOCI2004AEF",
                "SOCI3004AEF", "SOCI3005AEF", "SOCI4008AEF", "SOSC2002AEF",
                "SOSC3004AEF", "SOSC4001AEF",
            ]},
            "english": {"min_credits": 6, "color": "emerald",
                        "courses": list(_WSJ_ENGLISH)},
            "general-ed": {"min_credits": 6, "color": "pink", "pool": "ge",
                           "pick_n": 2, "courses": []},
            "university-core": {"min_credits": 9, "color": "indigo",
                                "courses": list(_UNI_CORE_9)},
        },
        "wsj-stream-gcs",
    ),
    # ── Stream V PPA:core81 + ME3 + EA15(标准路径)+ UC9 + UE6 + GE6 ────
    # ME/EA 官方范围 3-6/12-15(FYRP 双路径):标准路径建模,FYRP 见模块注
    "BSSCHWSJ-PPA": _wsj_stream(
        "BSSCHWSJ-PPA", "PPA",
        "BSSCHWSJ Stream V: Politics and Public Administration",
        "社会科学荣誉学士( Stream V:政治与公共行政)",
        "社會科學榮譽學士( Stream V:政治與公共行政)",
        120, {1: 120, 2: 93, 3: 66},
        {
            "core": {"min_credits": 81, "color": "blue", "courses": [
                "ECON1001AEF", "POLS1001AEF", "PSYC1001AEF", "SOCI1001AEF",
                "STAT2003AEF",
                "POLS2001AEF", "POLS2002AEF", "POLS2003AEF", "PUAD2001AEF",
                "STAT2001AEF", "STAT2002AEF",
                "ECON3005AEF", "ECON3007AEF", "POLS3001AEF", "POLS3002AEF",
                "POLS3003AEF", "POLS3004AEF", "POLS3005AEF", "POLS4001AEF",
                "POLS4002AEF", "POLS4003AEF", "POLS4007AEF", "POLS4008AEF",
                "POLS4010AEF", "PUAD3001AEF", "PUAD4001AEF", "SOCI3007AEF",
            ]},
            "major-elective": {"min_credits": 3, "color": "purple",
                               "pool": "credits", "courses": [
                "POLS4004AEF", "POLS4005AEF", "POLS4006AEF", "POLS4009AEF",
            ]},
            "area-elective": {"min_credits": 15, "color": "violet",
                              "pool": "credits", "courses": [
                "ECON2001AEF", "ECON2002AEF", "GCST2001AEF", "PSYC2001AEF",
                "SOCI2001AEF", "SOCI2002AEF", "SOCI2003AEF", "SOCI2004AEF",
                "SOSC2002AEF", "SOSC2003AEF",
                "ECON3001AEF", "ECON3002AEF", "ECON3003AEF", "ECON3006AEF",
                "ECON4001AEF", "GCST3001AEF", "GCST3002AEF", "GCST3003AEF",
                "GCST3004AEF", "GCST4001AEF", "GCST4002AEF", "GCST4003AEF",
                "GCST4004AEF", "GCST4006AEF", "PSYC3003AEF", "PSYC3004AEF",
                "PSYC3005AEF", "PSYC3006AEF", "PSYC3010AEF", "SOCI3004AEF",
                "SOCI4006AEF", "SOCI4007AEF",
            ]},
            "english": {"min_credits": 6, "color": "emerald",
                        "courses": list(_WSJ_ENGLISH)},
            "general-ed": {"min_credits": 6, "color": "pink", "pool": "ge",
                           "pick_n": 2, "courses": []},
            "university-core": {"min_credits": 9, "color": "indigo",
                                "courses": list(_UNI_CORE_9)},
        },
        "wsj-stream-ppa",
    ),
}


# ── 计算辅助(供 courses.py 与前端镜像共用语义)────────────────────────────

_LEVEL_RE = re.compile(r"(\d{3,4})")


def level_of_course(course_id: str) -> int:
    """课码 → 层级千位(1000/2000/3000/4000);无千位数字(GIP100BEF 等
    百位码 / 非码串)→ 0(不参与层级约束统计)。"""
    m = _LEVEL_RE.search(course_id or "")
    if not m:
        return 0
    n = int(m.group(1))
    if n < 1000:
        return 0
    return min(n // 1000, 9) * 1000


def level_rules_for(programme_code: str) -> list[dict]:
    """专业适用的层级约束规则列表:全校默认 + per-programme scoped 附加。

    * HD 副学士豁免(2 年制结构性不可能满足 24/24,见 RULES_EVIDENCE);
    * STAMJ/STEMJ 挂起 1000 帽(必修池数据伪影),3000/4000 下限照常;
    * Stream 限定码(BSSCHWSJ-AGS)自带 scoped 规则且不受伞码影响;
      其余专业(含别名码)落 "*" 全校默认。
    """
    if programme_code in LEVEL_CREDIT_RULES:
        rules = list(LEVEL_CREDIT_RULES[programme_code])
    else:
        rules = []
    base = programme_code.split("-")[0]
    if base in LEVEL_CREDIT_RULES and base != programme_code:
        rules += LEVEL_CREDIT_RULES[base]
    if programme_code.startswith("HD") or base.startswith("HD"):
        return rules  # HD 豁免全校层级约束
    uni = dict(_LEVEL_UNIVERSITY_RULES)
    if base in _LEVEL_CAP_SUSPENDED:
        uni = {"min": dict(_LEVEL_UNIVERSITY_RULES["min"]),
               "rule_id": "level-university"}
    return rules + [uni]


def excluded_conflicts(progress: dict, programme_code: str | None = None) -> list[dict]:
    """互斥组里任意两门都被标记(任意非空状态)→ 冲突。警告语义,不拦截。

    互斥清单是 per-sheet 的(同一门课在不同专业 advice sheet 的清单不同),
    只对 attested 专业生效;programme_code 折别名后匹配,Stream 限定码取伞码。
    (PROGRAMME_ALIASES 惰性导入——programmes.py 合并本模块,顶层导入会成环)
    """
    if programme_code:
        from .programmes import PROGRAMME_ALIASES  # noqa: PLC0415 — 防循环导入
        main = PROGRAMME_ALIASES.get(programme_code, programme_code).split("-")[0]
    else:
        main = None
    conflicts = []
    for group in EXCLUDED_COMBINATIONS:
        if main is not None and main not in group.get("programmes", []):
            continue
        marked = [c for c in group["courses"] if progress.get(c)]
        if len(marked) >= 2:
            conflicts.append({
                "courses": group["courses"],
                "marked": marked,
                "rule_id": group["rule_id"],
            })
    return conflicts
