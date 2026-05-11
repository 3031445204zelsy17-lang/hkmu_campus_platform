import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";

// ── State ────────────────────────────────────────────────────────────────────

let _courses = [];
let _progress = [];
let _view = "overview";

const DSAI_TEMPLATE = {
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
};

const STATUS_LABELS = {
  not_started: "Not Started",
  in_progress: "In Progress",
  completed: "Completed",
};

const STATUS_COLORS = {
  not_started: "bg-gray-100 text-gray-600",
  in_progress: "bg-orange-100 text-orange-800",
  completed: "bg-green-100 text-green-800",
};

const STATUS_ICONS = {
  completed: "check-circle",
  in_progress: "clock",
  not_started: "circle",
};

const SEMESTER_ORDER = { autumn: 0, spring: 1, summer: 2 };

const CATEGORY_LABELS = {
  core: "Core",
  elective: "Elective",
  "general-ed": "General Ed",
  english: "English",
  "university-core": "University Core",
  project: "Project",
};

const CATEGORY_COLORS = {
  core: "bg-blue-100 text-blue-800",
  elective: "bg-purple-100 text-purple-800",
  "general-ed": "bg-pink-100 text-pink-800",
  english: "bg-emerald-100 text-emerald-800",
  "university-core": "bg-indigo-100 text-indigo-800",
  project: "bg-amber-100 text-amber-800",
};

// ── Icon helpers ──────────────────────────────────────────────────────────────

function LucideIcon(name, className = "w-5 h-5") {
  const i = document.createElement("i");
  i.setAttribute("data-lucide", name);
  i.className = className;
  return i;
}

function _refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

// ── UI Components ─────────────────────────────────────────────────────────────

function ViewTab(label, viewId, iconName) {
  const btn = document.createElement("button");
  btn.className = `planner-tab flex items-center gap-2 ${
    _view === viewId ? "tab-active" : ""
  }`;
  btn.appendChild(LucideIcon(iconName, "w-4 h-4"));
  const span = document.createElement("span");
  span.textContent = label;
  btn.appendChild(span);
  btn.addEventListener("click", () => {
    _view = viewId;
    _render();
  });
  return btn;
}

function ProgressBar(pct, label, size = "sm") {
  const wrap = document.createElement("div");
  wrap.className = "mb-3";

  if (label) {
    const lbl = document.createElement("div");
    lbl.className = "flex justify-between text-sm mb-1";
    const left = document.createElement("span");
    left.className = "font-medium text-gray-700";
    left.textContent = label;
    const right = document.createElement("span");
    right.className = "text-gray-500";
    right.textContent = `${Math.round(pct)}%`;
    lbl.appendChild(left);
    lbl.appendChild(right);
    wrap.appendChild(lbl);
  }

  const track = document.createElement("div");
  track.className = `progress-bar-track ${size === "sm" ? "progress-bar-track-sm" : ""} relative overflow-hidden rounded-full bg-gray-200`;
  const fill = document.createElement("div");
  fill.className = "progress-bar-fill absolute top-0 left-0 h-full rounded-full";
  fill.style.width = `${pct}%`;
  track.appendChild(fill);
  wrap.appendChild(track);
  return wrap;
}

function CourseCard(course, showStatus = false) {
  const status = _getProgress(course.id);
  const card = document.createElement("div");
  card.className = "course-card cursor-pointer";
  card.dataset.courseId = course.id;

  // Top row: course code + status icon
  const header = document.createElement("div");
  header.className = "flex justify-between items-start mb-3";

  const code = document.createElement("span");
  code.className = "text-sm font-bold";
  code.style.color = "#0066CC";
  code.textContent = course.code;
  header.appendChild(code);

  if (showStatus && status) {
    const iconColor =
      status === "completed" ? "text-green-500" :
      status === "in_progress" ? "text-orange-500" : "text-blue-500";
    header.appendChild(LucideIcon(STATUS_ICONS[status] || "circle", `w-5 h-5 ${iconColor}`));
  }
  card.appendChild(header);

  // Course name
  const name = document.createElement("h3");
  name.className = "font-semibold mb-2";
  name.textContent = course.name;
  card.appendChild(name);

  // Category badge + credits
  const badges = document.createElement("div");
  badges.className = "flex items-center gap-2 mb-3";

  const catBadge = document.createElement("span");
  catBadge.className = `text-xs px-2 py-1 rounded-full ${CATEGORY_COLORS[course.category] || "bg-gray-100 text-gray-600"}`;
  catBadge.textContent = CATEGORY_LABELS[course.category] || course.category;
  badges.appendChild(catBadge);

  const credits = document.createElement("span");
  credits.className = "text-xs text-gray-500";
  credits.textContent = `${course.credits} cr`;
  badges.appendChild(credits);
  card.appendChild(badges);

  // Prerequisites
  const prereqs = _parsePrereqs(course.prerequisites);
  if (prereqs.length > 0) {
    const met = _prereqsMet(prereqs);
    const prereqRow = document.createElement("div");
    prereqRow.className = `text-xs ${met ? "text-green-600 font-medium" : "text-gray-500"}`;
    prereqRow.textContent = met
      ? "Prerequisites met"
      : `Pre: ${prereqs.map((id) => _getCourseName(id)).join(", ")}`;
    card.appendChild(prereqRow);
  }

  card.addEventListener("click", () => _onCourseClick(course));
  return card;
}

function SemesterGroup(year, semester, courses) {
  const group = document.createElement("div");
  group.className = "mb-6";

  const title = document.createElement("h3");
  title.className = "text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 pb-1 border-b border-gray-100";
  title.textContent = `Year ${year} — ${semester.charAt(0).toUpperCase() + semester.slice(1)}`;
  group.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4";
  courses.forEach((c) => grid.appendChild(CourseCard(c, true)));
  group.appendChild(grid);
  return group;
}

function StatCard(label, value, colorClass, iconName) {
  const card = document.createElement("div");
  card.className = "bg-white rounded-2xl p-6 shadow-md text-center";

  if (iconName) {
    card.appendChild(LucideIcon(iconName, `w-8 h-8 ${colorClass} mx-auto mb-2`));
  }

  const val = document.createElement("div");
  val.className = `text-4xl font-bold ${colorClass} mb-1`;
  val.textContent = value;
  card.appendChild(val);

  const lbl = document.createElement("div");
  lbl.className = "text-gray-500";
  lbl.textContent = label;
  card.appendChild(lbl);

  return card;
}

function FeatureCard(iconName, label, desc, fromColor, toColor, onClick) {
  const card = document.createElement("div");
  card.className = "feature-card";
  card.addEventListener("click", onClick);

  const iconWrap = document.createElement("div");
  iconWrap.className = `w-14 h-14 bg-gradient-to-br ${fromColor} ${toColor} rounded-xl flex items-center justify-center mb-5`;
  iconWrap.appendChild(LucideIcon(iconName, "w-7 h-7 text-white"));
  card.appendChild(iconWrap);

  const title = document.createElement("h3");
  title.className = "text-xl font-bold mb-3";
  title.textContent = label;
  card.appendChild(title);

  const descEl = document.createElement("p");
  descEl.className = "text-gray-500";
  descEl.textContent = desc;
  card.appendChild(descEl);

  return card;
}

function StatusDropdown(courseId, currentStatus) {
  const select = document.createElement("select");
  select.className = "text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:outline-none focus:border-blue-400";

  ["not_started", "in_progress", "completed"].forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = STATUS_LABELS[s];
    if (s === currentStatus) opt.selected = true;
    select.appendChild(opt);
  });

  select.addEventListener("change", async () => {
    await _updateProgress(courseId, select.value);
  });
  return select;
}

// ── Views ─────────────────────────────────────────────────────────────────────

function _renderOverview(container) {
  const total = _courses.length;
  const completed = _progress.filter((p) => p.status === "completed").length;
  const inProgress = _progress.filter((p) => p.status === "in_progress").length;
  const totalCredits = _courses.reduce((sum, c) => sum + c.credits, 0);
  const completedCredits = _courses
    .filter((c) => _getProgress(c.id) === "completed")
    .reduce((sum, c) => sum + c.credits, 0);
  const pct = total > 0 ? (completed / total) * 100 : 0;

  // ── 1. Hero section ──────────────────────────────────────────────────────
  const hero = document.createElement("section");
  hero.className = "animated-gradient relative overflow-hidden rounded-2xl mb-8";

  // Floating shapes
  const shape1 = document.createElement("div");
  shape1.className = "absolute top-10 right-10 w-32 h-32 bg-white/10 rounded-full float-shape";
  hero.appendChild(shape1);

  const shape2 = document.createElement("div");
  shape2.className = "absolute bottom-10 left-10 w-24 h-24 bg-white/10 rounded-full float-shape";
  shape2.style.animationDelay = "2s";
  hero.appendChild(shape2);

  // Inner content
  const inner = document.createElement("div");
  inner.className = "max-w-3xl mx-auto text-center py-16 px-4 relative z-10";

  // Sparkle pill label
  const pill = document.createElement("span");
  pill.className = "inline-flex items-center gap-2 px-4 py-2 bg-white/20 rounded-full text-white text-sm font-medium mb-6";
  pill.appendChild(LucideIcon("sparkles", "w-4 h-4"));
  const pillText = document.createElement("span");
  pillText.textContent = "HKMU Data Science & AI Program";
  pill.appendChild(pillText);
  inner.appendChild(pill);

  // Title
  const h1 = document.createElement("h1");
  h1.className = "text-4xl sm:text-5xl font-bold text-white mb-6";
  h1.textContent = "DSAI Course Planner";
  inner.appendChild(h1);

  // Description
  const desc = document.createElement("p");
  desc.className = "text-xl text-white/90 mb-8";
  desc.textContent = "Your comprehensive companion for navigating the Data Science and AI programme at HKMU.";
  inner.appendChild(desc);

  // CTA buttons
  const ctaRow = document.createElement("div");
  ctaRow.className = "flex flex-col sm:flex-row gap-4 justify-center";

  const btn1 = document.createElement("button");
  btn1.className = "bg-white px-8 py-4 rounded-xl font-semibold flex items-center justify-center gap-2 hover:opacity-90 transition-opacity";
  btn1.style.color = "#0066CC";
  btn1.appendChild(LucideIcon("bar-chart-2", "w-5 h-5"));
  const btn1Text = document.createElement("span");
  btn1Text.textContent = "View Progress";
  btn1.appendChild(btn1Text);
  btn1.addEventListener("click", () => { _view = "progress"; _render(); });
  ctaRow.appendChild(btn1);

  const btn2 = document.createElement("button");
  btn2.className = "bg-white/20 text-white border-2 border-white/50 px-8 py-4 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-white/30 transition-colors";
  btn2.appendChild(LucideIcon("book-open", "w-5 h-5"));
  const btn2Text = document.createElement("span");
  btn2Text.textContent = "Browse Courses";
  btn2.appendChild(btn2Text);
  btn2.addEventListener("click", () => { _view = "browse"; _render(); });
  ctaRow.appendChild(btn2);

  inner.appendChild(ctaRow);
  hero.appendChild(inner);

  // SVG wave divider
  const waveDiv = document.createElement("div");
  waveDiv.className = "absolute bottom-0 left-0 right-0";
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 1440 120");
  svg.setAttribute("fill", "none");
  svg.style.display = "block";
  const path = document.createElementNS(svgNS, "path");
  path.setAttribute("d", "M0 120L60 110C120 100 240 80 360 70C480 60 600 60 720 65C840 70 960 80 1080 85C1200 90 1320 90 1380 90L1440 90V120H0Z");
  path.setAttribute("fill", "#F5F7FA");
  svg.appendChild(path);
  waveDiv.appendChild(svg);
  hero.appendChild(waveDiv);

  container.appendChild(hero);

  // ── 2. Stats section ─────────────────────────────────────────────────────
  const statsSection = document.createElement("div");
  statsSection.className = "py-8";
  const statsGrid = document.createElement("div");
  statsGrid.className = "grid grid-cols-2 lg:grid-cols-4 gap-6";
  statsGrid.appendChild(StatCard("Total Courses", total, "text-blue-600", "book-open"));
  statsGrid.appendChild(StatCard("Total Credits", totalCredits, "text-green-600", "award"));
  statsGrid.appendChild(StatCard("Completed", completed, "text-green-500", "check-circle"));
  statsGrid.appendChild(StatCard("Credits Earned", `${completedCredits}/${totalCredits}`, "text-blue-600", "graduation-cap"));
  statsSection.appendChild(statsGrid);
  container.appendChild(statsSection);

  // ── 3. Feature cards ─────────────────────────────────────────────────────
  const featureSection = document.createElement("div");
  featureSection.className = "py-8";
  const featureTitle = document.createElement("h2");
  featureTitle.className = "text-3xl font-bold text-center mb-12";
  featureTitle.textContent = "Everything You Need";
  featureSection.appendChild(featureTitle);

  const featureGrid = document.createElement("div");
  featureGrid.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6";
  featureGrid.appendChild(FeatureCard("bar-chart-2", "Track Progress", "Monitor your degree completion with visual progress indicators.", "from-blue-500", "to-blue-600", () => { _view = "progress"; _render(); }));
  featureGrid.appendChild(FeatureCard("book-open", "Browse Courses", "Explore the full DSAI curriculum with search and filters.", "from-orange-500", "to-orange-600", () => { _view = "browse"; _render(); }));
  featureGrid.appendChild(FeatureCard("git-branch", "Prerequisites", "Check course requirements and plan your academic path.", "from-purple-600", "to-purple-700", () => { _view = "plan"; _render(); }));
  featureGrid.appendChild(FeatureCard("calendar", "Study Plan", "Organize courses by semester and track your schedule.", "from-green-500", "to-green-600", () => { _view = "plan"; _render(); }));
  featureSection.appendChild(featureGrid);
  container.appendChild(featureSection);

  // ── 4. Year-by-year progress ─────────────────────────────────────────────
  const yearSection = document.createElement("div");
  yearSection.className = "py-8";

  const yearTitle = document.createElement("h2");
  yearTitle.className = "text-2xl font-bold mb-6";
  yearTitle.textContent = "Year-by-Year Progress";
  yearSection.appendChild(yearTitle);

  [1, 2, 3, 4].forEach((y) => {
    const yearCourses = _courses.filter((c) => c.year === y);
    if (yearCourses.length === 0) return;

    const yearCompleted = yearCourses.filter((c) => _getProgress(c.id) === "completed").length;
    const yearPct = yearCourses.length > 0 ? (yearCompleted / yearCourses.length) * 100 : 0;
    const yearCredits = yearCourses.reduce((s, c) => s + c.credits, 0);
    const completedYearCredits = yearCourses
      .filter((c) => _getProgress(c.id) === "completed")
      .reduce((s, c) => s + c.credits, 0);

    const yearCard = document.createElement("div");
    yearCard.className = "section-card";

    const yearHeader = document.createElement("div");
    yearHeader.className = "flex justify-between items-center mb-4";
    const yearLabel = document.createElement("h3");
    yearLabel.className = "text-lg font-bold";
    yearLabel.textContent = `Year ${y}`;
    const yearCreditsLabel = document.createElement("span");
    yearCreditsLabel.className = "text-sm text-gray-500";
    yearCreditsLabel.textContent = `${completedYearCredits}/${yearCredits} credits`;
    yearHeader.appendChild(yearLabel);
    yearHeader.appendChild(yearCreditsLabel);
    yearCard.appendChild(yearHeader);

    yearCard.appendChild(ProgressBar(yearPct, `${yearCompleted}/${yearCourses.length} courses`));
    yearSection.appendChild(yearCard);
  });
  container.appendChild(yearSection);

  // ── 5. DSAI template tip ─────────────────────────────────────────────────
  if (isLoggedIn() && _progress.length === 0) {
    const tip = document.createElement("div");
    tip.className = "template-tip mt-6";

    const tipHeader = document.createElement("div");
    tipHeader.className = "flex items-center gap-3 mb-3";
    tipHeader.appendChild(LucideIcon("info", "w-5 h-5 text-blue-500"));
    const tipTitle = document.createElement("span");
    tipTitle.className = "font-semibold text-gray-800";
    tipTitle.textContent = "New here?";
    tipHeader.appendChild(tipTitle);
    tip.appendChild(tipHeader);

    const tipText = document.createElement("p");
    tipText.className = "text-sm text-gray-600 mb-4 ml-8";
    tipText.textContent = "Load the DSAI standard template to get started with course tracking.";
    tip.appendChild(tipText);

    const loadBtn = document.createElement("button");
    loadBtn.className = "ml-8 bg-blue-600 text-white px-5 py-2.5 rounded-xl hover:bg-blue-700 transition-colors text-sm font-semibold flex items-center gap-2";
    loadBtn.appendChild(LucideIcon("download", "w-4 h-4"));
    const loadBtnText = document.createElement("span");
    loadBtnText.textContent = "Load DSAI Template";
    loadBtn.appendChild(loadBtnText);
    loadBtn.addEventListener("click", _loadDSAITemplate);
    tip.appendChild(loadBtn);

    container.appendChild(tip);
  }
}

function _renderProgress(container) {
  if (_courses.length === 0) {
    const empty = document.createElement("p");
    empty.className = "text-gray-400 text-center py-8";
    empty.textContent = "No courses loaded.";
    container.appendChild(empty);
    return;
  }

  const heading = document.createElement("div");
  heading.className = "mb-6";
  const h1 = document.createElement("h1");
  h1.className = "text-3xl font-bold mb-2";
  h1.textContent = "My Progress";
  heading.appendChild(h1);
  const subtitle = document.createElement("p");
  subtitle.className = "text-gray-500";
  subtitle.textContent = "Track your progress through the DSAI programme year by year.";
  heading.appendChild(subtitle);
  container.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "space-y-6";

  [1, 2, 3, 4].forEach((y) => {
    const semesters = ["autumn", "spring", "summer"];
    semesters.forEach((sem) => {
      const courses = _courses.filter((c) => c.year === y && c.semester === sem);
      if (courses.length === 0) return;
      grid.appendChild(SemesterGroup(y, sem, courses));
    });
  });

  container.appendChild(grid);
}

function _renderBrowse(container) {
  const heading = document.createElement("div");
  heading.className = "mb-6";
  const h1 = document.createElement("h1");
  h1.className = "text-3xl font-bold mb-2";
  h1.textContent = "All Courses";
  heading.appendChild(h1);
  const subtitle = document.createElement("p");
  subtitle.className = "text-gray-500";
  subtitle.textContent = "Browse the complete DSAI curriculum.";
  heading.appendChild(subtitle);
  container.appendChild(heading);

  // Filter bar in card
  const filterCard = document.createElement("div");
  filterCard.className = "section-card";

  const filterGrid = document.createElement("div");
  filterGrid.className = "grid grid-cols-1 md:grid-cols-3 gap-4";

  // Search
  const searchGroup = document.createElement("div");
  const searchLabel = document.createElement("label");
  searchLabel.className = "block text-sm font-medium text-gray-500 mb-2";
  searchLabel.textContent = "Search";
  searchGroup.appendChild(searchLabel);
  const search = document.createElement("input");
  search.type = "text";
  search.placeholder = "Search courses...";
  search.className = "w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
  search.id = "course-search";
  searchGroup.appendChild(search);
  filterGrid.appendChild(searchGroup);

  // Year filter
  const yearGroup = document.createElement("div");
  const yearLabel = document.createElement("label");
  yearLabel.className = "block text-sm font-medium text-gray-500 mb-2";
  yearLabel.textContent = "Year";
  yearGroup.appendChild(yearLabel);
  const yearFilter = document.createElement("select");
  yearFilter.className = "w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
  yearFilter.innerHTML = '<option value="">All Years</option><option value="1">Year 1</option><option value="2">Year 2</option><option value="3">Year 3</option><option value="4">Year 4</option>';
  yearFilter.id = "course-year-filter";
  yearGroup.appendChild(yearFilter);
  filterGrid.appendChild(yearGroup);

  // Category filter
  const catGroup = document.createElement("div");
  const catLabel = document.createElement("label");
  catLabel.className = "block text-sm font-medium text-gray-500 mb-2";
  catLabel.textContent = "Category";
  catGroup.appendChild(catLabel);
  const catFilter = document.createElement("select");
  catFilter.className = "w-full px-4 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
  catFilter.innerHTML = '<option value="">All Categories</option>' +
    Object.entries(CATEGORY_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  catFilter.id = "course-cat-filter";
  catGroup.appendChild(catFilter);
  filterGrid.appendChild(catGroup);

  filterCard.appendChild(filterGrid);
  container.appendChild(filterCard);

  // Results grid
  const grid = document.createElement("div");
  grid.id = "browse-grid";
  grid.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6";
  container.appendChild(grid);

  const applyFilters = () => {
    const q = search.value.toLowerCase().trim();
    const yr = yearFilter.value;
    const cat = catFilter.value;

    let filtered = _courses;
    if (q) filtered = filtered.filter((c) => c.name.toLowerCase().includes(q) || c.code.toLowerCase().includes(q));
    if (yr) filtered = filtered.filter((c) => c.year === parseInt(yr));
    if (cat) filtered = filtered.filter((c) => c.category === cat);

    grid.innerHTML = "";
    if (filtered.length === 0) {
      const empty = document.createElement("p");
      empty.className = "text-gray-400 text-center py-8 col-span-full";
      empty.textContent = "No courses match your filters.";
      grid.appendChild(empty);
    } else {
      filtered.forEach((c) => grid.appendChild(CourseCard(c, true)));
    }
    _refreshIcons();
  };

  search.addEventListener("input", applyFilters);
  yearFilter.addEventListener("change", applyFilters);
  catFilter.addEventListener("change", applyFilters);
  applyFilters();
}

function _renderPlan(container) {
  if (!isLoggedIn()) {
    const msg = document.createElement("div");
    msg.className = "text-center py-16";

    const iconWrap = document.createElement("div");
    iconWrap.className = "w-20 h-20 bg-gradient-to-br from-blue-100 to-green-100 rounded-2xl flex items-center justify-center mx-auto mb-6";
    iconWrap.appendChild(LucideIcon("lock", "w-10 h-10 text-blue-500"));
    msg.appendChild(iconWrap);

    const loginTitle = document.createElement("h3");
    loginTitle.className = "text-xl font-bold text-gray-800 mb-2";
    loginTitle.textContent = "Login Required";
    msg.appendChild(loginTitle);

    const loginMsg = document.createElement("p");
    loginMsg.className = "text-gray-500 mb-6";
    loginMsg.textContent = "Sign in to create your personalized study plan and track course progress.";
    msg.appendChild(loginMsg);

    const loginBtn = document.createElement("button");
    loginBtn.className = "bg-gradient-to-r from-blue-600 to-green-600 text-white px-8 py-3 rounded-xl hover:opacity-90 transition-opacity font-semibold flex items-center gap-2 mx-auto shadow-md";
    loginBtn.appendChild(LucideIcon("log-in", "w-5 h-5"));
    const loginBtnText = document.createElement("span");
    loginBtnText.textContent = "Sign In";
    loginBtn.appendChild(loginBtnText);
    loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
    msg.appendChild(loginBtn);

    container.appendChild(msg);
    return;
  }

  // Heading
  const heading = document.createElement("div");
  heading.className = "mb-6";
  const h1 = document.createElement("h1");
  h1.className = "text-3xl font-bold mb-2";
  h1.textContent = "Study Plan";
  heading.appendChild(h1);
  const subtitle = document.createElement("p");
  subtitle.className = "text-gray-500";
  subtitle.textContent = "Organize your courses by semester and plan your academic path.";
  heading.appendChild(subtitle);
  container.appendChild(heading);

  // Summary bar
  const totalCompleted = _progress.filter((p) => p.status === "completed").length;
  const totalInProgress = _progress.filter((p) => p.status === "in_progress").length;
  const summaryBar = document.createElement("div");
  summaryBar.className = "grid grid-cols-3 gap-4 mb-6";

  const sumDone = document.createElement("div");
  sumDone.className = "bg-white rounded-xl p-4 flex items-center gap-3 shadow-sm";
  const sumDoneIcon = document.createElement("div");
  sumDoneIcon.className = "w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center";
  sumDoneIcon.appendChild(LucideIcon("check-circle", "w-5 h-5 text-green-600"));
  sumDone.appendChild(sumDoneIcon);
  const sumDoneText = document.createElement("div");
  const sumDoneVal = document.createElement("div");
  sumDoneVal.className = "text-xl font-bold text-gray-800";
  sumDoneVal.textContent = totalCompleted;
  sumDoneText.appendChild(sumDoneVal);
  const sumDoneLbl = document.createElement("div");
  sumDoneLbl.className = "text-xs text-gray-500";
  sumDoneLbl.textContent = "Completed";
  sumDoneText.appendChild(sumDoneLbl);
  sumDone.appendChild(sumDoneText);
  summaryBar.appendChild(sumDone);

  const sumProg = document.createElement("div");
  sumProg.className = "bg-white rounded-xl p-4 flex items-center gap-3 shadow-sm";
  const sumProgIcon = document.createElement("div");
  sumProgIcon.className = "w-10 h-10 bg-amber-100 rounded-lg flex items-center justify-center";
  sumProgIcon.appendChild(LucideIcon("clock", "w-5 h-5 text-amber-600"));
  sumProg.appendChild(sumProgIcon);
  const sumProgText = document.createElement("div");
  const sumProgVal = document.createElement("div");
  sumProgVal.className = "text-xl font-bold text-gray-800";
  sumProgVal.textContent = totalInProgress;
  sumProgText.appendChild(sumProgVal);
  const sumProgLbl = document.createElement("div");
  sumProgLbl.className = "text-xs text-gray-500";
  sumProgLbl.textContent = "In Progress";
  sumProgText.appendChild(sumProgLbl);
  sumProg.appendChild(sumProgText);
  summaryBar.appendChild(sumProg);

  const sumLeft = document.createElement("div");
  sumLeft.className = "bg-white rounded-xl p-4 flex items-center gap-3 shadow-sm";
  const sumLeftIcon = document.createElement("div");
  sumLeftIcon.className = "w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center";
  sumLeftIcon.appendChild(LucideIcon("circle", "w-5 h-5 text-blue-600"));
  sumLeft.appendChild(sumLeftIcon);
  const sumLeftText = document.createElement("div");
  const sumLeftVal = document.createElement("div");
  sumLeftVal.className = "text-xl font-bold text-gray-800";
  sumLeftVal.textContent = Math.max(0, _courses.length - totalCompleted - totalInProgress);
  sumLeftText.appendChild(sumLeftVal);
  const sumLeftLbl = document.createElement("div");
  sumLeftLbl.className = "text-xs text-gray-500";
  sumLeftLbl.textContent = "Remaining";
  sumLeftText.appendChild(sumLeftLbl);
  sumLeft.appendChild(sumLeftText);
  summaryBar.appendChild(sumLeft);

  container.appendChild(summaryBar);

  // Semester tabs
  const semesters = [1, 2, 3, 4].flatMap((y) =>
    ["autumn", "spring"].map((s) => ({ year: y, semester: s }))
  );

  let _selectedSem = semesters[0];

  const tabsWrap = document.createElement("div");
  tabsWrap.className = "section-card mb-6";
  const tabsLabel = document.createElement("div");
  tabsLabel.className = "text-sm font-medium text-gray-500 mb-3 flex items-center gap-2";
  tabsLabel.appendChild(LucideIcon("calendar", "w-4 h-4"));
  const tabsLabelText = document.createElement("span");
  tabsLabelText.textContent = "Select Semester";
  tabsLabel.appendChild(tabsLabelText);
  tabsWrap.appendChild(tabsLabel);

  const tabs = document.createElement("div");
  tabs.className = "flex gap-2 flex-wrap planner-sem-tabs";

  semesters.forEach((sem) => {
    const isActive = _selectedSem.year === sem.year && _selectedSem.semester === sem.semester;
    const semCourses = _courses.filter((c) => c.year === sem.year && c.semester === sem.semester);
    const semDone = semCourses.filter((c) => _getProgress(c.id) === "completed").length;
    const hasProgress = semDone > 0;

    const tab = document.createElement("button");
    tab.className = `px-4 py-2.5 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
      isActive
        ? "bg-gradient-to-r from-blue-600 to-green-600 text-white shadow-md"
        : hasProgress
          ? "bg-green-50 text-green-700 hover:bg-green-100"
          : "bg-gray-50 text-gray-600 hover:bg-gray-100"
    }`;

    const tabIcon = document.createElement("i");
    tabIcon.setAttribute("data-lucide", hasProgress && semDone === semCourses.length ? "check-circle" : isActive ? "calendar-check" : "calendar");
    tabIcon.className = "w-4 h-4";
    tab.appendChild(tabIcon);

    const tabText = document.createElement("span");
    tabText.textContent = `Y${sem.year} ${sem.semester.charAt(0).toUpperCase() + sem.semester.slice(1)}`;
    tab.appendChild(tabText);

    if (hasProgress && !isActive) {
      const badge = document.createElement("span");
      badge.className = "text-xs bg-green-200 text-green-800 px-1.5 py-0.5 rounded-full";
      badge.textContent = semDone;
      tab.appendChild(badge);
    }

    tab.addEventListener("click", () => {
      _selectedSem = sem;
      // Re-render tabs
      tabs.querySelectorAll("button").forEach((b, i) => {
        const s = semesters[i];
        const active = s.year === _selectedSem.year && s.semester === _selectedSem.semester;
        const sCourses = _courses.filter((c) => c.year === s.year && c.semester === s.semester);
        const sDone = sCourses.filter((c) => _getProgress(c.id) === "completed").length;
        const sHasProgress = sDone > 0;
        b.className = `px-4 py-2.5 rounded-xl text-sm font-medium transition-all flex items-center gap-2 ${
          active
            ? "bg-gradient-to-r from-blue-600 to-green-600 text-white shadow-md"
            : sHasProgress
              ? "bg-green-50 text-green-700 hover:bg-green-100"
              : "bg-gray-50 text-gray-600 hover:bg-gray-100"
        }`;
      });
      renderSemesterCourses();
      _refreshIcons();
    });
    tabs.appendChild(tab);
  });
  tabsWrap.appendChild(tabs);
  container.appendChild(tabsWrap);

  // Semester header
  const semHeader = document.createElement("div");
  semHeader.id = "plan-sem-header";
  container.appendChild(semHeader);

  // Course grid
  const semGrid = document.createElement("div");
  semGrid.id = "plan-semester-grid";
  semGrid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4";
  container.appendChild(semGrid);

  function renderSemesterCourses() {
    const courses = _courses.filter(
      (c) => c.year === _selectedSem.year && c.semester === _selectedSem.semester
    );

    // Update semester header
    semHeader.innerHTML = "";
    const semDone = courses.filter((c) => _getProgress(c.id) === "completed").length;
    const semCredits = courses.reduce((s, c) => s + c.credits, 0);
    const doneCredits = courses.filter((c) => _getProgress(c.id) === "completed").reduce((s, c) => s + c.credits, 0);

    const semInfo = document.createElement("div");
    semInfo.className = "flex items-center justify-between mb-4";

    const semLabel = document.createElement("div");
    semLabel.className = "flex items-center gap-2";
    semLabel.appendChild(LucideIcon("layers", "w-5 h-5 text-blue-500"));
    const semTitle = document.createElement("span");
    semTitle.className = "font-semibold text-gray-800";
    semTitle.textContent = `Year ${_selectedSem.year} ${_selectedSem.semester.charAt(0).toUpperCase() + _selectedSem.semester.slice(1)}`;
    semLabel.appendChild(semTitle);
    const courseCount = document.createElement("span");
    courseCount.className = "text-sm text-gray-500";
    courseCount.textContent = `${courses.length} courses`;
    semLabel.appendChild(courseCount);
    semInfo.appendChild(semLabel);

    const creditBadge = document.createElement("span");
    creditBadge.className = "text-sm font-medium px-3 py-1 rounded-full bg-blue-50 text-blue-700";
    creditBadge.textContent = `${doneCredits}/${semCredits} credits`;
    semInfo.appendChild(creditBadge);
    semHeader.appendChild(semInfo);

    // Course grid
    semGrid.innerHTML = "";
    if (courses.length === 0) {
      const empty = document.createElement("div");
      empty.className = "col-span-full text-center py-16";

      const emptyIcon = document.createElement("div");
      emptyIcon.className = "w-20 h-20 bg-gradient-to-br from-gray-100 to-gray-50 rounded-2xl flex items-center justify-center mx-auto mb-6";
      emptyIcon.appendChild(LucideIcon("calendar-x", "w-10 h-10 text-gray-300"));
      empty.appendChild(emptyIcon);

      const emptyTitle = document.createElement("h3");
      emptyTitle.className = "text-lg font-semibold text-gray-700 mb-2";
      emptyTitle.textContent = "No courses this semester";
      empty.appendChild(emptyTitle);

      const emptyText = document.createElement("p");
      emptyText.className = "text-gray-400";
      emptyText.textContent = "This semester has no scheduled courses in the current plan.";
      empty.appendChild(emptyText);
      semGrid.appendChild(empty);
    } else {
      courses.forEach((c) => {
        const card = CourseCard(c, true);
        const status = _getProgress(c.id);
        const dd = StatusDropdown(c.id, status || "not_started");
        dd.addEventListener("click", (e) => e.stopPropagation());
        card.appendChild(dd);
        semGrid.appendChild(card);
      });
    }
    _refreshIcons();
  }

  renderSemesterCourses();
}

// ── Main Render ──────────────────────────────────────────────────────────────

export async function renderPlanner() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "planner");
  app.innerHTML = "";

  const container = document.createElement("div");
  container.className = "max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6";

  // View tabs — underline style
  const tabBar = document.createElement("div");
  tabBar.className = "flex border-b border-gray-200 mb-6 planner-tabs-wrap";
  tabBar.appendChild(ViewTab("Overview", "overview", "layout-dashboard"));
  tabBar.appendChild(ViewTab("My Progress", "progress", "bar-chart-2"));
  tabBar.appendChild(ViewTab("Browse", "browse", "book-open"));
  tabBar.appendChild(ViewTab("Plan", "plan", "git-branch"));
  container.appendChild(tabBar);

  // Content area
  const content = document.createElement("div");
  content.id = "planner-content";
  content.appendChild(LoadingSpinner());
  container.appendChild(content);

  app.appendChild(container);

  await _loadData();
  _render();
}

function _render() {
  const content = document.getElementById("planner-content");
  if (!content) return;
  content.innerHTML = "";

  switch (_view) {
    case "overview":
      _renderOverview(content);
      break;
    case "progress":
      _renderProgress(content);
      break;
    case "browse":
      _renderBrowse(content);
      break;
    case "plan":
      _renderPlan(content);
      break;
  }

  _refreshIcons();
}

// ── Data ──────────────────────────────────────────────────────────────────────

async function _loadData() {
  try {
    const data = await api.get("/courses?page_size=50");
    _courses = data.items;

    if (isLoggedIn()) {
      try {
        _progress = await api.get("/courses/progress/me");
      } catch {
        _progress = [];
      }
    } else {
      _progress = [];
    }
  } catch (err) {
    showToast("Failed to load courses: " + err.message, "error");
  }
}

async function _updateProgress(courseId, status) {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  try {
    await api.put("/courses/progress", { course_id: courseId, status });
    const existing = _progress.find((p) => p.course_id === courseId);
    if (existing) {
      existing.status = status;
    } else {
      _progress.push({ course_id: courseId, status, updated_at: new Date().toISOString() });
    }
    showToast("Progress updated!", "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Course Click ──────────────────────────────────────────────────────────────

function _onCourseClick(course) {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  const current = _getProgress(course.id);
  const next = current === "completed"
    ? "not_started"
    : current === "in_progress"
      ? "completed"
      : "in_progress";

  _updateProgress(course.id, next);
  _render();
}

// ── DSAI Template ─────────────────────────────────────────────────────────────

async function _loadDSAITemplate() {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  const items = Object.entries(DSAI_TEMPLATE).map(([course_id, status]) => ({
    course_id,
    status,
  }));

  try {
    _progress = await api.post("/courses/progress/batch", { items });
    showToast("DSAI template loaded! Track your progress now.", "success");
    _render();
  } catch (err) {
    showToast("Failed to load template: " + err.message, "error");
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _getProgress(courseId) {
  const p = _progress.find((p) => p.course_id === courseId);
  return p ? p.status : null;
}

function _parsePrereqs(prereqsStr) {
  try {
    return JSON.parse(prereqsStr || "[]");
  } catch {
    return [];
  }
}

function _prereqsMet(prereqIds) {
  return prereqIds.every((id) => _getProgress(id) === "completed");
}

function _getCourseName(courseId) {
  const c = _courses.find((c) => c.id === courseId);
  return c ? c.code : courseId;
}

function LoadingSpinner() {
  const el = document.createElement("div");
  el.className = "flex justify-center py-12";
  el.innerHTML = '<div class="spinner"></div>';
  return el;
}
