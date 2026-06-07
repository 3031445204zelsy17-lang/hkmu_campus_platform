/**
 * HKMU Programme definitions — graduation requirements & course mappings.
 *
 * Each programme defines:
 *  - name (trilingual), school, totalCredits
 *  - categories: { [catKey]: { minCredits, color, courses[], pickN? } }
 *  - template: default progress for new users
 *
 * Course IDs must match the `id` field in seed_courses.py / courses table.
 */

export const PROGRAMMES = {
  /* ─── DSAI (Data Science & AI) — fully populated ──────────────────── */
  BSCHDSAIJ: {
    code: "BSCHDSAIJ",
    name: {
      en: "BSc (Hons) Data Science & Artificial Intelligence",
      "zh-CN": "数据科学及人工智能理学士",
      "zh-TW": "數據科學及人工智能理學士",
    },
    school: "School of Science and Technology",
    totalCredits: 120,
    categories: {
      core: {
        minCredits: 84,
        color: "blue",
        courses: [
          // Year 1
          "COMP1080SEF", "IT1020SEF", "MATH1410SEF",
          "COMP2090SEF", "IT1030SEF", "STAT1510SEF", "STAT2610SEF",
          // Year 2
          "COMP2020SEF", "COMP2640SEF", "MATH2150SEF", "STAT2510SEF",
          "COMP2030SEF", "IT2900SEF", "STAT2520SEF", "STAT2630SEF",
          // Year 3
          "COMP3200SEF", "COMP3500SEF", "STAT3660SEF", "COMP3130SEF",
          "COMP3510SEF", "COMP3920SEF", "STAT3110SEF", "COMP4820SEF",
          // Year 4
          "COMP3810SEF", "COMP4330SEF", "COMP4610SEF", "COMP4930SEF",
          "COMP4210SEF", "COMP4600SEF",
        ],
      },
      elective: {
        minCredits: 12,
        color: "purple",
        pickN: 4, // pick 4 of 6
        courses: [
          "ELEC3050SEF", "COMP4630SEF", "MATH4950SEF",
          "ELEC4310SEF", "ELEC3250SEF", "ELEC4710SEF",
        ],
      },
      project: {
        minCredits: 6,
        color: "amber",
        courses: ["COMP4610SEF"],
      },
      english: {
        minCredits: 6,
        color: "emerald",
        courses: ["ENGL1101AEF", "ENGL1202EEF"],
      },
      "general-ed": {
        minCredits: 6,
        color: "pink",
        courses: ["GEN001", "GEN002"],
      },
      "university-core": {
        minCredits: 9,
        color: "indigo",
        courses: ["UNI1002ABW", "UNI1012ABW", "UNI2002BEW", "UNI3002BEW"],
      },
    },
    template: {
      COMP1080SEF: "completed",
      IT1020SEF: "completed",
      MATH1410SEF: "completed",
      ENGL1101AEF: "completed",
      GEN001: "completed",
      UNI1002ABW: "completed",
      UNI1012ABW: "completed",
      COMP2090SEF: "in_progress",
      IT1030SEF: "in_progress",
      STAT1510SEF: "in_progress",
      STAT2610SEF: "in_progress",
      ENGL1202EEF: "in_progress",
      GEN002: "in_progress",
    },
  },

  /* ─── Computer Science — placeholder ───────────────────────────────── */
  BSCHCSJ: {
    code: "BSCHCSJ",
    name: {
      en: "BSc (Hons) Computer Science",
      "zh-CN": "计算机科学理学士",
      "zh-TW": "計算機科學理學士",
    },
    school: "School of Science and Technology",
    totalCredits: 120,
    comingSoon: true,
    categories: {
      core: {
        minCredits: 0,
        color: "blue",
        courses: [],
      },
      elective: {
        minCredits: 0,
        color: "purple",
        courses: [],
      },
      project: {
        minCredits: 0,
        color: "amber",
        courses: [],
      },
      english: {
        minCredits: 0,
        color: "emerald",
        courses: [],
      },
      "general-ed": {
        minCredits: 0,
        color: "pink",
        courses: [],
      },
      "university-core": {
        minCredits: 0,
        color: "indigo",
        courses: [],
      },
    },
    template: {},
  },

  /* ─── Cyber & Computer Security — placeholder ─────────────────────── */
  BSCHCCSJ: {
    code: "BSCHCCSJ",
    name: {
      en: "BSc (Hons) Cyber and Computer Security",
      "zh-CN": "网络安全及计算机保安理学士",
      "zh-TW": "網絡安全及計算機保安理學士",
    },
    school: "School of Science and Technology",
    totalCredits: 120,
    comingSoon: true,
    categories: {
      core: {
        minCredits: 0,
        color: "blue",
        courses: [],
      },
      elective: {
        minCredits: 0,
        color: "purple",
        courses: [],
      },
      project: {
        minCredits: 0,
        color: "amber",
        courses: [],
      },
      english: {
        minCredits: 0,
        color: "emerald",
        courses: [],
      },
      "general-ed": {
        minCredits: 0,
        color: "pink",
        courses: [],
      },
      "university-core": {
        minCredits: 0,
        color: "indigo",
        courses: [],
      },
    },
    template: {},
  },
};

/** Return localised programme name */
export function programmeName(prog, lang) {
  return prog?.name?.[lang] || prog?.name?.en || prog?.code || "";
}
