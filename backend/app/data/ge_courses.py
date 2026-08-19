"""HKMU General Education (GE) courses — 3-credit-unit system.

Source: HKMU "GE Courses Selection Guide" PDF (3-credit-unit edition,
last updated 2026-08-07), at
hkmu.edu.hk/REG/reg_ftae/GE/General Education Courses Selection Guide_3cru.pdf
The PDF sits behind Cloudflare, so it was fetched with Playwright (real Chrome
passes the JS challenge) and parsed with pdf.js — see the scraper notes in
memory [[course-system-overhaul]].

GE rule (official): a student must take GE courses each from a DIFFERENT
'field of study', and those fields must differ from their own programme's
field(s). So the planner filters out the student's own field and requires
field-diverse picks. Each GE course is 3 credit-units in the 3cru system.

Offering terms (`terms`, 2026 Autumn → 2027 Summer window) were parsed at
coordinate level from the same PDF's per-term tables (2026-08-14); empty
list = not offered in the window. Re-check each academic year.

⚠️ 2026-08-19 批次 1(复核报告):池扩为官方目录全集 89 门 = 73 门本学年开课
+ 16 门不开课(terms=[],见 MISSING_16/复核报告第一节;含 GEN2045ECF——它只在
春表 Remarks 里作为 GEN2045EEF 的不可兼修对象出现,本学年不开课)。16 门的
双语课名/field/school 取自 GE_catalog_3cru.pdf 正文条目;新增 3 个官方领域
(Gender Studies / History / Student Wellness)进 GE_FIELD_ORDER。

⚠️ DATA QUALITY: 62 unique course codes were extracted automatically; ~7 more
were recovered by splitting merged table cells (Creative Arts / Performance
Studies rows render side-by-side in the PDF). Course titles were
hand-corrected where the table merged them. This is a faithful draft —
please spot-check against the PDF before relying on every title, and re-run
the scrape each academic year (course offerings change).
"""

# Official GE catalog (3-credit-unit system), 89 courses: 73 offered in the
# 2026/27 AY + 16 not offered this year (terms=[]).
# fields: see the 'field of study' column in the PDF. school: offering school.
GE_COURSES = [
    # ── Area Studies ──
    {"code": "GEN 1022AEF", "name_en": "Contemporary China", "name_zh": "當代中國", "field": "Area Studies", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2019ABF", "name_en": "Introduction to South China Studies", "name_zh": "華南研究概論", "field": "Area Studies", "school": "A&SS", "terms": []},
    # ── Business Innovation & Intelligence ──
    {"code": "GEN 2034BCF", "name_en": "Unleashing Innovation in Business", "name_zh": "無限創意在商界", "field": "Business Innovation & Intelligence", "school": "B&A", "terms": ["autumn"]},
    # ── Chinese Language Studies & Literature ──
    {"code": "GEN 1042ECF", "name_en": "Chinese: From Language to Culture", "name_zh": "趣味語文與妙趣文化", "field": "Chinese Language Studies & Literature", "school": "E&L", "terms": ["autumn", "spring"]},
    {"code": "GEN 1043ECF", "name_en": "Investigating Lyrics of Hong Kong Popular Songs", "name_zh": "香港流行歌詞探究", "field": "Chinese Language Studies & Literature", "school": "E&L", "terms": ["autumn"]},
    {"code": "GEN 2005ACF", "name_en": "Discovering Cultures in China", "name_zh": "中國文化探索", "field": "Chinese Language Studies & Literature", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2255ECF", "name_en": "Comprehensive Preparation for PSC", "name_zh": "普通話水平測試備考精研", "field": "Chinese Language Studies & Literature", "school": "E&L", "terms": ["autumn", "spring"]},
    {"code": "GEN 2001ACF", "name_en": "Hong Kong Literature and Society", "name_zh": "香港文學與社會", "field": "Chinese Language Studies & Literature", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1005ACF", "name_en": "Love in Literature", "name_zh": "愛情與文學", "field": "Chinese Language Studies & Literature", "school": "A&SS", "terms": []},
    {"code": "GEN 1013ACF", "name_en": "The Art of Humour and Daily Life", "name_zh": "幽默語言與生活", "field": "Chinese Language Studies & Literature", "school": "A&SS", "terms": []},
    # ── Computing / Electronic & Computer Engineering ──
    {"code": "GEN 1100SEW", "name_en": "Introduction to Digital Technologies and Tools", "name_zh": "數碼技術及工具", "field": "Computing/Electronic & Computer Engineering", "school": "S&T", "terms": ["autumn"]},
    {"code": "GEN 1110SEW", "name_en": "AI in Action: Practical Applications Across Fields", "name_zh": "人工智能實踐：跨領域應用", "field": "Computing/Electronic & Computer Engineering", "school": "S&T", "terms": ["spring"]},
    # ── Creative Arts ──
    {"code": "GEN 1001ABF", "name_en": "Film and Popular Culture", "name_zh": "電影與流行文化", "field": "Creative Arts", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1016ACF", "name_en": "Perspectives on Japanese Anime and Manga Culture", "name_zh": "日本動漫文化面面觀", "field": "Creative Arts", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2007AEF", "name_en": "Mobile Culture and Communication in the Digital Era", "name_zh": "數碼時代的移動文化與傳訊", "field": "Creative Arts", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1010ABF", "name_en": "The Art and Practice of Digital Photography", "name_zh": "數碼攝影藝術與實踐", "field": "Creative Arts", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1011ABF", "name_en": "Colour, Culture and Art", "name_zh": "色彩、文化與藝術", "field": "Creative Arts", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1012ACF", "name_en": "Women in Hong Kong Cantonese Films", "name_zh": "香港粵語電影中的女性", "field": "Creative Arts", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1144ECF", "name_en": "Enhancing Creativity Through Drama", "name_zh": "透過戲劇提升創意", "field": "Creative Arts", "school": "E&L", "terms": ["spring"]},
    {"code": "GEN 2003ABF", "name_en": "Science Fiction Films", "name_zh": "科幻電影", "field": "Creative Arts", "school": "A&SS", "terms": ["spring"]},
    # ── Digital Business ──
    {"code": "GEN 1066BCF", "name_en": "Flip the KOL Classroom", "name_zh": "翻轉 KOL 教室", "field": "Digital Business", "school": "B&A", "terms": ["autumn"]},
    # ── Education ──
    {"code": "GEN 2045EEF", "name_en": "Smart Learning and Teaching with AI", "name_zh": "智慧學習與教學", "field": "Education", "school": "E&L", "terms": ["spring"]},
    # 中文授课孪生码(ECF):本学年不开课;目录明确与 EEF 互斥
    {"code": "GEN 2045ECF", "name_en": "Smart Learning and Teaching with AI", "name_zh": "智慧學習與教學", "field": "Education", "school": "E&L", "terms": []},
    # ── English Language Studies & Literature ──
    {"code": "GEN 1003ABF", "name_en": "Language, Society and Culture", "name_zh": "語言、社會與文化", "field": "English Language Studies & Literature", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1024AEF", "name_en": "Creative English: Hong Kong Literature and Popular Culture", "name_zh": "創意英語：香港文學及流行文化", "field": "English Language Studies & Literature", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 2043EEF", "name_en": "Creativity in Everyday English", "name_zh": "日用英語中的創意", "field": "English Language Studies & Literature", "school": "E&L", "terms": ["spring"]},
    {"code": "GEN 2205EEF", "name_en": "Essential Skills for IELTS", "name_zh": "雅思重點技巧", "field": "English Language Studies & Literature", "school": "E&L", "terms": ["spring"]},
    # ── Environmental Studies ──
    {"code": "GEN 1009SEF", "name_en": "Environment and Health", "name_zh": "環境與健康", "field": "Environmental Studies", "school": "S&T", "terms": ["autumn"]},
    {"code": "GEN 2013SEF", "name_en": "Nature Conservation: Exploring Biodiversity and Natural Landscapes of Hong Kong", "name_zh": "自然保育︰探索香港的生物多樣性和自然景觀", "field": "Environmental Studies", "school": "S&T", "terms": ["spring"]},
    {"code": "GEN 2037SEF", "name_en": "Environmental Control and Management", "name_zh": "環境控制及管理", "field": "Environmental Studies", "school": "S&T", "terms": ["summer"]},
    # ── Finance and Fintech ──
    {"code": "GEN 1088BEF", "name_en": "Stock Investing Made Easy", "name_zh": "股票投資入門", "field": "Finance and Fintech", "school": "B&A", "terms": ["autumn"]},
    {"code": "GEN 1067BCF", "name_en": "Investment Fundamentals", "name_zh": "基礎投資知識", "field": "Finance and Fintech", "school": "B&A", "terms": ["spring"]},
    # ── Gender Studies (官方目录领域,批次 1 新增) ──
    {"code": "GEN 1025AEF", "name_en": "Gender, Sexuality, and Intimacy in Modern Societies", "name_zh": "現代社會的性別、性與親密關係", "field": "Gender Studies", "school": "A&SS", "terms": []},
    # ── Health Sciences ──
    {"code": "GEN 1508NEF", "name_en": "Pandemics and Humans", "name_zh": "人類與大流行病", "field": "Health Sciences", "school": "N&HS", "terms": ["autumn"]},
    {"code": "GEN 1510NCF", "name_en": "Exercise and Health", "name_zh": "運動與健康", "field": "Health Sciences", "school": "N&HS", "terms": ["autumn"]},
    {"code": "GEN 2501NEF", "name_en": "Understanding Health Through Statistics", "name_zh": "從統計學了解健康", "field": "Health Sciences", "school": "N&HS", "terms": ["autumn"]},
    {"code": "GEN 1502NCF", "name_en": "Strive to Be Healthy", "name_zh": "向健康出發", "field": "Health Sciences", "school": "N&HS", "terms": ["spring"]},
    {"code": "GEN 2504NEF", "name_en": "Unravelling the Cancer Odyssey From Bench to Bedside: an Introduction to Translational Oncology", "name_zh": "揭秘癌症從實驗室到臨床的征程：轉化腫瘤學簡介", "field": "Health Sciences", "school": "N&HS", "terms": ["spring"]},
    # ── History (官方目录领域,批次 1 新增) ──
    {"code": "GEN 2002AEF", "name_en": "Highlights in World Civilizations", "name_zh": "世界文明精粹", "field": "History", "school": "A&SS", "terms": []},
    # ── Hospitality and Tourism Management ──
    {"code": "GEN 2033BCF", "name_en": "Gastronomy and Business", "name_zh": "美食中尋商機", "field": "Hospitality and Tourism Management", "school": "B&A", "terms": ["spring"]},
    {"code": "GEN 2001BCF", "name_en": "Cultural Heritage and Tourism: Practising the Fundamentals", "name_zh": "文化遺產與旅遊: 理論實務初探", "field": "Hospitality and Tourism Management", "school": "B&A", "terms": ["summer"]},
    # ── International Business ──
    {"code": "GEN 2035BCF", "name_en": "Surviving in a Cross-Cultural Workplace", "name_zh": "跨文化工作間求生錦囊", "field": "International Business", "school": "B&A", "terms": ["summer"]},
    # ── Life Sciences ──
    {"code": "GEN 2034SEF", "name_en": "The Scientific Basis of Food and Health", "name_zh": "食物與健康的科學基礎", "field": "Life Sciences", "school": "S&T", "terms": ["spring"]},
    # ── Management ──
    {"code": "GEN 1068BEF", "name_en": "You Have a Choice: Career Decision-Making", "name_zh": "個人職業生涯規劃", "field": "Management", "school": "B&A", "terms": ["autumn"]},
    {"code": "GEN 2088BCF", "name_en": "Startup Bootcamp", "name_zh": "創業特訓班", "field": "Management", "school": "B&A", "terms": ["autumn"]},
    # ── Marketing ──
    {"code": "GEN 1064BEF", "name_en": "Social Media and Content Marketing", "name_zh": "社交媒體及內容營銷", "field": "Marketing", "school": "B&A", "terms": ["spring"]},
    {"code": "GEN 1500SEF", "name_en": "Data Visualization for Impressive Presentations", "name_zh": "精彩悅目的數據圖像演示", "field": "Marketing", "school": "S&T", "terms": []},
    # ── Mathematics & Statistics  (DSAI's own field → DSAI students CANNOT take these) ──
    {"code": "GEN 2503NEF", "name_en": "AI Superpowers for Health Heroes", "name_zh": "智健康的 AI 新世界", "field": "Mathematics & Statistics", "school": "N&HS", "terms": ["summer"]},
    {"code": "GEN 1000SEF", "name_en": "Mathematics in Daily Life", "name_zh": "生活數學", "field": "Mathematics & Statistics", "school": "S&T", "terms": []},
    # ── Performance Studies ──
    {"code": "GEN 1020ACF", "name_en": "Cantonese Opera Culture: Appreciation and Experience", "name_zh": "粵劇文化：導賞與體驗", "field": "Performance Studies", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1026ACF", "name_en": "Musical Culture of Hong Kong I: Chinese Music", "name_zh": "香港音樂文化 (一)：中國音樂", "field": "Performance Studies", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2018ACF", "name_en": "Chinese Song Lyric Writing", "name_zh": "中文歌詞創作", "field": "Performance Studies", "school": "A&SS", "terms": ["autumn"]},  # *not available for self-enrol; contact A&SS
    {"code": "GEN 1023ACW", "name_en": "Introduction to Cantonese Opera Art and Skills", "name_zh": "粵劇藝術及曲藝概論", "field": "Performance Studies", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1027ACF", "name_en": "Musical Culture of Hong Kong II: Film Music and Popular Music", "name_zh": "香港音樂文化 (二)：電影音樂、流行音樂", "field": "Performance Studies", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 2009AEF", "name_en": "Music in Popular Media", "name_zh": "流行媒體中的音樂", "field": "Performance Studies", "school": "A&SS", "terms": ["summer"]},
    # ── Social Sciences ──
    {"code": "GEN 1015AEF", "name_en": "Understanding World Politics Through Photojournalism", "name_zh": "從新聞攝影看世界政治", "field": "Social Sciences", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1041EEF", "name_en": "Stress and Well-Being", "name_zh": "壓力與身心健康", "field": "Social Sciences", "school": "E&L", "terms": ["autumn"]},
    {"code": "GEN 2016AEF", "name_en": "Myths of the Property Market in Hong Kong", "name_zh": "樓市點睇", "field": "Social Sciences", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1014AEF", "name_en": "Psychology of Intimate Relationships", "name_zh": "親密關係心理學", "field": "Social Sciences", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1503NEF", "name_en": "Food for Shape", "name_zh": "營養 ∙ 養型", "field": "Social Sciences", "school": "N&HS", "terms": ["spring"]},
    {"code": "GEN 2044EBF", "name_en": "Developing Media Literacy", "name_zh": "媒體素養的建立", "field": "Social Sciences", "school": "E&L", "terms": ["spring", "summer"]},
    {"code": "GEN 2042EEF", "name_en": "Society and Interpersonal Relationships", "name_zh": "社會與人際關係", "field": "Social Sciences", "school": "E&L", "terms": ["summer"]},
    {"code": "GEN 2013AEF", "name_en": "Cultures and Strategies of Games of Chance", "name_zh": "機率遊戲的文化與策略", "field": "Social Sciences", "school": "A&SS", "terms": []},
    # ── Sports and eSports Management ──
    {"code": "GEN 1078BEF", "name_en": "Cultivating Employee Wellness in the Workplace", "name_zh": "建立康健的職場文化", "field": "Sports and eSports Management", "school": "B&A", "terms": ["spring"]},
    {"code": "GEN 2078BCF", "name_en": "E-Sports: Game-Changing Business", "name_zh": "電競：玩 • 轉商業", "field": "Sports and eSports Management", "school": "B&A", "terms": ["summer"]},
    # ── Student Development ──
    {"code": "GEN 1017AEF", "name_en": "Psychology of Work and Internship Preparation", "name_zh": "工作的心理學與實習準備", "field": "Student Development", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1018ACF", "name_en": "Chinese Literature and Culture", "name_zh": "中國文學與文化", "field": "Student Development", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 1050EBF", "name_en": "Japanese Language and Pop Culture", "name_zh": "日本語與流行文化", "field": "Student Development", "school": "E&L", "terms": ["autumn", "spring"]},
    {"code": "GEN 1060EBF", "name_en": "Francaise Fantaisie: Exploring French Language and Culture", "name_zh": "探索法國語言與文化", "field": "Student Development", "school": "E&L", "terms": ["autumn", "spring"]},
    {"code": "GEN 1070EBF", "name_en": "Korean Language and Culture in the Global Era", "name_zh": "全球化時代的韓語與文化", "field": "Student Development", "school": "E&L", "terms": ["autumn"]},
    {"code": "GEN 2011ACF", "name_en": "Culture and Everyday Life in Ancient China", "name_zh": "古代中國文化與日常生活", "field": "Student Development", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2017AEF", "name_en": "Film Festivals, Exhibition, and Curation", "name_zh": "電影節、展映與策展", "field": "Student Development", "school": "A&SS", "terms": ["autumn"]},
    {"code": "GEN 2245ECF", "name_en": "Dramatic Tension", "name_zh": "戲劇的張力", "field": "Student Development", "school": "E&L", "terms": ["autumn"]},
    {"code": "GEN 1019ACF", "name_en": "Traveling and Writing of Classical Chinese Literati", "name_zh": "中國古代文人的旅遊與寫作", "field": "Student Development", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1029ACF", "name_en": "Fieldwork on Intangible Cultural Heritage in Hong Kong", "name_zh": "香港非物質文化遺產的實地考察", "field": "Student Development", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1110EBF", "name_en": "Speak and Connect: a Trilingual Approach to Success", "name_zh": "演說・連繫：三語之道，成功之路", "field": "Student Development", "school": "E&L", "terms": ["spring"]},
    {"code": "GEN 1507NCF", "name_en": "Healing Key From Herbs (Chinese Medicines Series)", "name_zh": "大自然的藥匙 (中藥篇)", "field": "Student Development", "school": "N&HS", "terms": ["spring"]},
    {"code": "GEN 2012ACF", "name_en": "What Did the Ancient Chinese Think?", "name_zh": "中國古人想什麼?", "field": "Student Development", "school": "A&SS", "terms": ["spring"]},
    {"code": "GEN 1080EBF", "name_en": "Hallyu: Language, K-Pop and Culture", "name_zh": "韓流: 語言、流行音樂與文化", "field": "Student Development", "school": "E&L", "terms": ["summer"]},
    {"code": "GEN 1509NEF", "name_en": "Challenges in \"Changing\" Global Health", "name_zh": "全球衛生演變與應對之挑戰", "field": "Student Development", "school": "N&HS", "terms": ["summer"]},
    {"code": "GEN 1021AEF", "name_en": "A Journey to Master Your Life Through Interdisciplinary Navigation", "name_zh": "掌握你的人生：從跨學科探索開始", "field": "Student Development", "school": "A&SS", "terms": []},
    {"code": "GEN 1028ACF", "name_en": "Science Fiction Writing", "name_zh": "科幻小說創作實踐", "field": "Student Development", "school": "A&SS", "terms": []},
    {"code": "GEN 1501NEF", "name_en": "Positive Education and Mental Health", "name_zh": "正向教育和精神健康", "field": "Student Development", "school": "N&HS", "terms": []},
    {"code": "GEN 2014ABF", "name_en": "Death and Dying: the Personal and the Social", "name_zh": "生命的衰與亡：個人與社會視野", "field": "Student Development", "school": "A&SS", "terms": []},
    {"code": "GEN 2015ACF", "name_en": "Foodways, Local Society and Globalization", "name_zh": "飲食方式、在地社會與全球化", "field": "Student Development", "school": "A&SS", "terms": []},
    # ── Student Wellness (官方目录领域,批次 1 新增) ──
    {"code": "GEN 1504NEF", "name_en": "Rock, Paper, Scissors: Path to Mental Wellbeing", "name_zh": "猜情尋", "field": "Student Wellness", "school": "N&HS", "terms": []},
    {"code": "GEN 2502NEF", "name_en": "Mindfulness and Wellbeing in Global Society", "name_zh": "全球社會的正念與幸福", "field": "Student Wellness", "school": "N&HS", "terms": []},
    # ── Testing and Certification ──
    {"code": "GEN 2001SEF", "name_en": "Testing and Certification in Daily Life", "name_zh": "日常生活中的檢測和認證", "field": "Testing and Certification", "school": "S&T", "terms": ["autumn"]},
    # ── Accounting and Corporate Governance ──
    {"code": "GEN 2068BEF", "name_en": "How to Start Your Business", "name_zh": "如何創業", "field": "Accounting and Corporate Governance", "school": "B&A", "terms": ["summer"]},
]

GE_FIELD_ORDER = [
    "Area Studies", "Accounting and Corporate Governance",
    "Business Innovation & Intelligence", "Chinese Language Studies & Literature",
    "Computing/Electronic & Computer Engineering", "Creative Arts", "Digital Business",
    "Education", "English Language Studies & Literature", "Environmental Studies",
    "Finance and Fintech", "Gender Studies", "Health Sciences", "History",
    "Hospitality and Tourism Management",
    "International Business", "Life Sciences", "Management", "Marketing",
    "Mathematics & Statistics", "Performance Studies", "Social Sciences",
    "Sports and eSports Management", "Student Development", "Student Wellness",
    "Testing and Certification",
]

# Programme code -> its GE 'field(s) of study' (PDF P.2-6). A student may NOT
# take GE courses from their own programme's field(s). Programmes with more
# than one field are listed as a list. Only programmes with full-planning or
# common ones are mapped here; others fall back to no exclusion.
PROGRAMME_GE_FIELDS = {
    "BSCHDSAIJ": ["Mathematics & Statistics"],
    "BSCHCSJ": ["Computing/Electronic & Computer Engineering"],
    "BSCHCCSJ": ["Computing/Electronic & Computer Engineering"],
    "BSCHSTEMJ": ["Computing/Electronic & Computer Engineering", "Environmental Studies", "Mathematics & Statistics", "Testing and Certification"],
    "BSCHSTAMJ": ["Computing/Electronic & Computer Engineering", "Environmental Studies", "Mathematics & Statistics", "Testing and Certification"],
    "BSCHESGMJ": ["Environmental Studies"],
    "BSCHFTSJ": ["Testing and Certification"],
    "BSCHATSJ": ["Testing and Certification"],
    "BSCHBEMJ": ["Construction Management"],
    "BSCHBSBJ": ["Health Sciences"],
    "BSCHCMQSJ": ["Construction", "Quantity Surveying"],
    "BASCHTICJ": ["Testing and Certification"],
    "BASCHRAEJ": ["Computing/Electronic & Computer Engineering"],
    "BENGHECEJ": ["Computing/Electronic & Computer Engineering"],
    "BENGHBSEJ": ["Testing and Certification"],
    "BENGHCEJ": ["Testing and Certification"],
    "BNHGJ": ["Health Sciences"],
    "BNHMJ": ["Health Sciences"],
    "BSCHDRJ": ["Health Sciences"],
    "BSCHMLSJ": ["Testing and Certification"],
    "BSCHPTJ": ["Health Sciences"],
    "BAHCAMDJ": ["Creative Arts"],
    "BAHCLLJ": ["Chinese Language Studies & Literature"],
    "BAHCWFAJ": ["Creative Arts"],
    "BAHELCJ": ["English Language Studies & Literature"],
    "BAHLTJ": ["English Language Studies & Literature"],
    "BAHNMIEJ": ["Creative Arts"],
    "BFAHAVEJ": ["Creative Arts"],
    "BFAHIDDAJ": ["Creative Arts"],
    "BSSCHPWSJ": ["Social Sciences"],
    "BSSCHWSJ": ["Social Sciences"],
    # 批次 4 WSJ Stream 限定码(同伞码,社科领域 GE 禁选)
    "BSSCHWSJ-AGS": ["Social Sciences"],
    "BSSCHWSJ-ECON": ["Social Sciences"],
    "BSSCHWSJ-AS": ["Social Sciences"],
    "BSSCHWSJ-GCS": ["Social Sciences"],
    "BSSCHWSJ-PPA": ["Social Sciences"],
    "BBAHASMJ": ["Aviation Services Management"],
    "BBAHCGSJ": ["Accounting and Corporate Governance"],
    "BBAHFFTJ": ["Finance and Fintech", "Business Innovation & Intelligence"],
    "BBAHGBJ": ["International Business"],
    "BBAHGMSMJ": ["Marketing"],
    "BBAHHRMJ": ["Management"],
    "BBAHIHAMJ": ["Hospitality and Tourism Management"],
    "BBAHMGTJ": ["Management"],
    "BBAHMKTJ": ["Marketing"],
    "BBAHPAJ": ["Accounting and Corporate Governance"],
    "BBAHSEMJ": ["Sports and eSports Management"],
    "BBAHSRMJ": ["Sports and eSports Management"],
    "BBAHSTHMJ": ["Hospitality and Tourism Management"],
    "BAPHBMJ": ["Management", "Social Sciences"],
    "BEDELSEHJ": ["Education", "English Language Studies & Literature"],
    "BEDHACLSJ": ["Education", "Chinese Language Studies & Literature"],
    "BEDHPCLSJ": ["Education", "Chinese Language Studies & Literature"],
    "BEDHECEJ": ["Education"],
    "BLSEHJ": ["English Language Studies & Literature"],
    "BLSHACLSJ": ["Chinese Language Studies & Literature"],
    "BLSHBSADJ": ["Applied Drama", "Bilingual Studies"],
}


def ge_courses_for(programme_code: str | None) -> list[dict]:
    """All GE courses, tagged with whether the programme is BLOCKED from it
    (course is in the programme's own field). Order follows GE_FIELD_ORDER.

    Each course is merged with its official catalog enrichment (credits/level/
    moi/school_name/description/excluded from GE_ENRICH — generated by
    scripts/scrape_ge_catalog.py from the GE Courses Catalog PDF). Pool keys
    always win; enrichment only adds keys."""
    from .ge_catalog_enrichment import GE_ENRICH

    own = set(PROGRAMME_GE_FIELDS.get(programme_code or "", []))
    ranked = {f: i for i, f in enumerate(GE_FIELD_ORDER)}
    out = []
    for c in GE_COURSES:
        # `id` mirrors the courses-table PK (code with spaces stripped) so the
        # frontend GE picker can PUT /courses/progress and _compute_graduation
        # can join GE picks back to their credits via course_rows.
        out.append({
            **GE_ENRICH.get(c["code"], {}),
            **c,
            "blocked": c["field"] in own,
            "id": c["code"].replace(" ", ""),
        })
    out.sort(key=lambda c: (ranked.get(c["field"], 99), c["code"]))
    return out


def ge_course_by_id(course_id: str) -> dict | None:
    """courses-table PK (code w/o spaces, e.g. GEN1042ECF) → the GE course with
    official catalog enrichment merged in; None if not a GE course."""
    from .ge_catalog_enrichment import GE_ENRICH

    for c in GE_COURSES:
        if c["code"].replace(" ", "") == course_id:
            return {**GE_ENRICH.get(c["code"], {}), **c}
    return None


def ge_course_codes() -> set[str]:
    return {c["code"] for c in GE_COURSES}


if __name__ == "__main__":
    from collections import Counter
    print(f"GE courses: {len(GE_COURSES)} unique")
    print(f"fields: {len(set(c['field'] for c in GE_COURSES))}")
    print("by school:", dict(Counter(c["school"] for c in GE_COURSES)))
    print("by field:", dict(Counter(c["field"] for c in GE_COURSES)))
    d = ge_courses_for("BSCHDSAIJ")
    print(f"DSAI: {sum(c['blocked'] for c in d)} blocked (own field Mathematics & Statistics)")
