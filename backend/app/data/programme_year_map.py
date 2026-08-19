"""Per-专业修读年份映射(选课数据修复 · 批次 2)— 本提交为空骨架,数据由批次 2b 灌入。

架构动机(docs/ops/选课选课/advice_sheets/复核报告-2026-08-19.md 第四节):
  courses 表全局单一年份列 vs 官方按专业分年修读 → 模型级冲突。DSAI 手工年份
  (UNI3002BEW=Y4 等)全局外溢撞 16+ 专业,只 UPDATE 全局列修不完还会再错;
  per-(专业, 课) 映射才是终态,courses.year 降级为映射缺失时的回退值。

Regenerate: python3 scripts/build_programme_year_map.py
  数据源约束(验收标准.md 批次 2):verify/ 产物 + 复核报告 + 官方 PDF 原文;
  results/ 旧 JSON 禁用(丢行解析器产物,CI 断言锁)。
"""

# {专业码: {课码: {"year": 1-4, "term": "autumn|spring|summer"}}}
# 键为主码;别名码(BAPHBMJ1 等)经 PROGRAMME_ALIASES 归一后在 courses.py 侧解析,
# 本模块保持零 import(纯静态数据,生成器可整文件覆写)。
PROGRAMME_YEAR_MAP: dict[str, dict[str, dict]] = {}

# 官方 GE 占位行(GE (I)/(II)…,advice sheet 无课码的通识行):按 (year, term) 去重,
# 前端在对应学年学期渲染「通识待选」占位卡(对照官方 Yr 表)。
PROGRAMME_GE_SLOTS: dict[str, list] = {}

# 官方课名(advice sheet 标题列,首字母大写);seed 仅回填裸码课,不覆盖好名。
COURSE_NAME_BACKFILL: dict[str, str] = {}

# 批次 2 补池(复核报告 missing 78 课次;C→core / E→elective / 无行→elective),
# 由 programmes.py 在 import 时并入 PROGRAMMES(seed 侧同源插 courses 行)。
POOL_ADDITIONS: dict[str, dict[str, list]] = {}

# 补池课官方学分(GIP 类 = 0;多行冲突取众数平票取小)。
ADDITION_CREDITS: dict[str, int] = {}
