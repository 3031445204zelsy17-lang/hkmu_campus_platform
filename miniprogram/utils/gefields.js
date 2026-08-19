// GE 'field of study'（后端 /courses/ge 返回英文 field）→ 三语展示。
// 与 backend GE_FIELD_ORDER 对齐；未覆盖的 field fallback 到英文原值。
// T23 从 planner.js 抽出共享：planner GE 浮层与 ge-guide 教程页共用。
const FIELD_I18N = {
  "Area Studies": { en: "Area Studies", "zh-Hans": "区域研究", "zh-Hant": "區域研究" },
  "Accounting and Corporate Governance": { en: "Accounting & Corporate Governance", "zh-Hans": "会计与企业管治", "zh-Hant": "會計與企業管治" },
  "Business Innovation & Intelligence": { en: "Business Innovation & Intelligence", "zh-Hans": "商业创新与智能", "zh-Hant": "商業創新與智能" },
  "Chinese Language Studies & Literature": { en: "Chinese Language & Literature", "zh-Hans": "中国语言文学", "zh-Hant": "中國語言文學" },
  "Computing/Electronic & Computer Engineering": { en: "Computing / Electronic & Computer Eng.", "zh-Hans": "计算/电子与计算机工程", "zh-Hant": "計算/電子與計算機工程" },
  "Creative Arts": { en: "Creative Arts", "zh-Hans": "创意艺术", "zh-Hant": "創意藝術" },
  "Digital Business": { en: "Digital Business", "zh-Hans": "数字商业", "zh-Hant": "數碼商業" },
  "Education": { en: "Education", "zh-Hans": "教育", "zh-Hant": "教育" },
  "English Language Studies & Literature": { en: "English Language & Literature", "zh-Hans": "英语语言文学", "zh-Hant": "英語語言文學" },
  "Environmental Studies": { en: "Environmental Studies", "zh-Hans": "环境研究", "zh-Hant": "環境研究" },
  "Finance and Fintech": { en: "Finance & Fintech", "zh-Hans": "金融与金融科技", "zh-Hant": "金融與金融科技" },
  "Health Sciences": { en: "Health Sciences", "zh-Hans": "健康科学", "zh-Hant": "健康科學" },
  "Hospitality and Tourism Management": { en: "Hospitality & Tourism Management", "zh-Hans": "酒店与旅游管理", "zh-Hant": "酒店與旅遊管理" },
  "International Business": { en: "International Business", "zh-Hans": "国际商业", "zh-Hant": "國際商業" },
  "Life Sciences": { en: "Life Sciences", "zh-Hans": "生命科学", "zh-Hant": "生命科學" },
  "Management": { en: "Management", "zh-Hans": "管理", "zh-Hant": "管理" },
  "Marketing": { en: "Marketing", "zh-Hans": "市场营销", "zh-Hant": "市場營銷" },
  "Mathematics & Statistics": { en: "Mathematics & Statistics", "zh-Hans": "数学与统计", "zh-Hant": "數學與統計" },
  "Performance Studies": { en: "Performance Studies", "zh-Hans": "表演研究", "zh-Hant": "表演研究" },
  "Social Sciences": { en: "Social Sciences", "zh-Hans": "社会科学", "zh-Hant": "社會科學" },
  "Sports and eSports Management": { en: "Sports & eSports Management", "zh-Hans": "体育与电竞管理", "zh-Hant": "體育與電競管理" },
  "Student Development": { en: "Student Development", "zh-Hans": "学生发展", "zh-Hant": "學生發展" },
  "Testing and Certification": { en: "Testing & Certification", "zh-Hans": "检测与认证", "zh-Hant": "檢測與認證" },
};

// FIELD_I18N 的键即小程序 locale 名（en / zh-Hans / zh-Hant），直接取。
// （原 planner.js 版本误用 LOCALE_NAME_KEY 的 zh-CN/zh-TW 去查，中文永远
// fallback 英文 — 抽出时修正。）
function localizeField(field, locale) {
  const m = FIELD_I18N[field];
  if (!m) return field;
  return m[locale] || m.en || field;
}

module.exports = { FIELD_I18N, localizeField };
