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
                    # Year 4
                    "COMP3810SEF", "COMP4330SEF", "COMP4610SEF", "COMP4930SEF",
                    "COMP4210SEF", "COMP4600SEF",
                ],
            },
            "elective": {
                "min_credits": 12,
                "color": "purple",
                "pick_n": 4,  # pick 4 of 6
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
                "courses": ["GEN001", "GEN002"],
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
            "GEN001": "completed",
            "UNI1002ABW": "completed",
            "UNI1012ABW": "completed",
            "COMP2090SEF": "in_progress",
            "IT1030SEF": "in_progress",
            "STAT1510SEF": "in_progress",
            "STAT2610SEF": "in_progress",
            "ENGL1202EEF": "in_progress",
            "GEN002": "in_progress",
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
}

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
