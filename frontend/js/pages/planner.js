import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";

// ── State ────────────────────────────────────────────────────────────────────

let _courses = [];
let _progress = []; // [{course_id, status, updated_at}]
let _view = "overview"; // overview | progress | browse | plan
let _loading = false;

// DSAI standard template: maps course_id -> expected status for Year 1
const DSAI_TEMPLATE = {
  // Year 1 completed (assuming returning student)
  COMP1080SEF: "completed",
  IT1020SEF: "completed",
  MATH1410SEF: "completed",
  ENGL1101AEF: "completed",
  GEN001: "completed",
  UNI1002ABW: "completed",
  UNI1012ABW: "completed",
  // Year 1 Spring — in progress
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
  not_started: "bg-gray-200 text-gray-600",
  in_progress: "bg-amber-100 text-amber-700",
  completed: "bg-green-100 text-green-700",
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
  core: "bg-blue-100 text-blue-700 border-blue-200",
  elective: "bg-purple-100 text-purple-700 border-purple-200",
  "general-ed": "bg-teal-100 text-teal-700 border-teal-200",
  english: "bg-orange-100 text-orange-700 border-orange-200",
  "university-core": "bg-gray-100 text-gray-700 border-gray-200",
  project: "bg-red-100 text-red-700 border-red-200",
};

// ── Functional UI Components ─────────────────────────────────────────────────

function ViewTab(label, viewId) {
  const btn = document.createElement("button");
  btn.className = `px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
    _view === viewId
      ? "bg-blue-600 text-white shadow-sm"
      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
  }`;
  btn.textContent = label;
  btn.addEventListener("click", () => {
    _view = viewId;
    _render();
  });
  return btn;
}

function ProgressBar(pct, label) {
  const wrap = document.createElement("div");
  wrap.className = "mb-1";

  if (label) {
    const lbl = document.createElement("div");
    lbl.className = "flex justify-between text-xs text-gray-500 mb-1";
    const left = document.createElement("span");
    left.textContent = label;
    const right = document.createElement("span");
    right.textContent = `${Math.round(pct)}%`;
    lbl.appendChild(left);
    lbl.appendChild(right);
    wrap.appendChild(lbl);
  }

  const bar = document.createElement("div");
  bar.className = "progress-bar";
  const fill = document.createElement("div");
  fill.className = "progress-bar-fill";
  fill.style.width = `${pct}%`;
  bar.appendChild(fill);
  wrap.appendChild(bar);
  return wrap;
}

function CourseCard(course, showStatus = false) {
  const card = document.createElement("div");
  card.className = "course-card cursor-pointer";
  card.dataset.courseId = course.id;

  const status = _getProgress(course.id);

  // Header row
  const header = document.createElement("div");
  header.className = "flex items-start justify-between gap-2 mb-2";

  const code = document.createElement("span");
  code.className = "text-xs font-mono text-gray-400";
  code.textContent = course.code;

  const credits = document.createElement("span");
  credits.className = "text-xs font-semibold text-gray-500";
  credits.textContent = `${course.credits} credits`;

  header.appendChild(code);
  header.appendChild(credits);
  card.appendChild(header);

  // Name
  const name = document.createElement("div");
  name.className = "font-medium text-gray-800 text-sm mb-2";
  name.textContent = course.name;
  card.appendChild(name);

  // Category badge
  const badges = document.createElement("div");
  badges.className = "flex items-center gap-2 mb-2 flex-wrap";

  const catBadge = document.createElement("span");
  catBadge.className = `text-xs px-2 py-0.5 rounded-full border ${CATEGORY_COLORS[course.category] || "bg-gray-100 text-gray-600 border-gray-200"}`;
  catBadge.textContent = CATEGORY_LABELS[course.category] || course.category;
  badges.appendChild(catBadge);

  const semBadge = document.createElement("span");
  semBadge.className = "text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500 border border-gray-100";
  semBadge.textContent = `Y${course.year} ${course.semester}`;
  badges.appendChild(semBadge);

  card.appendChild(badges);

  // Status indicator
  if (showStatus && status) {
    const statusEl = document.createElement("div");
    statusEl.className = `text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[status]}`;
    statusEl.textContent = STATUS_LABELS[status];
    card.appendChild(statusEl);
  }

  // Prerequisites check
  const prereqs = _parsePrereqs(course.prerequisites);
  if (prereqs.length > 0) {
    const met = _prereqsMet(prereqs);
    const prereqRow = document.createElement("div");
    prereqRow.className = `text-xs mt-2 ${met ? "text-green-600" : "text-red-500"}`;
    prereqRow.textContent = met
      ? "Prerequisites met"
      : `Prerequisites: ${prereqs.map((id) => _getCourseName(id)).join(", ")}`;
    card.appendChild(prereqRow);
  }

  // Click to toggle status
  card.addEventListener("click", () => _onCourseClick(course));

  return card;
}

function SemesterGroup(year, semester, courses) {
  const group = document.createElement("div");
  group.className = "mb-6";

  const title = document.createElement("h3");
  title.className = "text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 pb-1 border-b border-gray-100";
  title.textContent = `Year ${year} — ${semester}`;
  group.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3";
  courses.forEach((c) => grid.appendChild(CourseCard(c, true)));
  group.appendChild(grid);

  return group;
}

function StatCard(label, value, color) {
  const card = document.createElement("div");
  card.className = "bg-white rounded-xl border border-gray-100 p-4 text-center";

  const val = document.createElement("div");
  val.className = `text-2xl font-bold ${color}`;
  val.textContent = value;
  card.appendChild(val);

  const lbl = document.createElement("div");
  lbl.className = "text-xs text-gray-400 mt-1";
  lbl.textContent = label;
  card.appendChild(lbl);

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

  // Welcome section
  const welcome = document.createElement("div");
  welcome.className = "bg-gradient-to-r from-blue-600 to-green-600 rounded-xl p-6 text-white mb-6";

  const welcomeTitle = document.createElement("h2");
  welcomeTitle.className = "text-xl font-bold mb-2";
  welcomeTitle.textContent = "DSAI Course Planner";

  const welcomeDesc = document.createElement("p");
  welcomeDesc.className = "text-sm opacity-80 mb-4";
  welcomeDesc.textContent = "Track your progress through the Data Science & AI programme at HKMU.";

  welcome.appendChild(welcomeTitle);
  welcome.appendChild(welcomeDesc);
  welcome.appendChild(ProgressBar(pct, "Overall Progress"));
  container.appendChild(welcome);

  // Stats row
  const stats = document.createElement("div");
  stats.className = "grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6";
  stats.appendChild(StatCard("Total Courses", total, "text-gray-800"));
  stats.appendChild(StatCard("Completed", completed, "text-green-600"));
  stats.appendChild(StatCard("In Progress", inProgress, "text-amber-600"));
  stats.appendChild(StatCard("Credits Earned", `${completedCredits}/${totalCredits}`, "text-blue-600"));
  container.appendChild(stats);

  // Year-by-year breakdown
  const years = [1, 2, 3, 4];
  years.forEach((y) => {
    const yearCourses = _courses.filter((c) => c.year === y);
    if (yearCourses.length === 0) return;

    const yearCompleted = yearCourses.filter((c) => _getProgress(c.id) === "completed").length;
    const yearPct = yearCourses.length > 0 ? (yearCompleted / yearCourses.length) * 100 : 0;

    container.appendChild(ProgressBar(yearPct, `Year ${y} (${yearCompleted}/${yearCourses.length})`));
  });

  // Quick actions
  if (isLoggedIn() && _progress.length === 0) {
    const tip = document.createElement("div");
    tip.className = "bg-blue-50 border border-blue-100 rounded-lg p-4 text-sm text-blue-700 mt-4";

    const tipText = document.createElement("p");
    tipText.className = "mb-3";
    tipText.textContent = "New here? Load the DSAI standard template to get started with course tracking.";
    tip.appendChild(tipText);

    const loadBtn = document.createElement("button");
    loadBtn.className = "bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
    loadBtn.textContent = "Load DSAI Template";
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

  const grid = document.createElement("div");
  grid.className = "space-y-6";

  // Group courses by year then semester
  const years = [1, 2, 3, 4];
  years.forEach((y) => {
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
  // Search & filter bar
  const toolbar = document.createElement("div");
  toolbar.className = "flex flex-wrap gap-2 mb-4";

  const search = document.createElement("input");
  search.type = "text";
  search.placeholder = "Search courses...";
  search.className = "flex-1 min-w-[200px] px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  search.id = "course-search";

  const yearFilter = document.createElement("select");
  yearFilter.className = "px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  yearFilter.innerHTML = '<option value="">All Years</option><option value="1">Year 1</option><option value="2">Year 2</option><option value="3">Year 3</option><option value="4">Year 4</option>';
  yearFilter.id = "course-year-filter";

  const catFilter = document.createElement("select");
  catFilter.className = "px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  catFilter.innerHTML = '<option value="">All Categories</option>' +
    Object.entries(CATEGORY_LABELS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  catFilter.id = "course-cat-filter";

  toolbar.appendChild(search);
  toolbar.appendChild(yearFilter);
  toolbar.appendChild(catFilter);
  container.appendChild(toolbar);

  // Results grid
  const grid = document.createElement("div");
  grid.id = "browse-grid";
  grid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3";
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
  };

  search.addEventListener("input", applyFilters);
  yearFilter.addEventListener("change", applyFilters);
  catFilter.addEventListener("change", applyFilters);

  // Initial render
  applyFilters();
}

function _renderPlan(container) {
  if (!isLoggedIn()) {
    const msg = document.createElement("div");
    msg.className = "text-center py-12";
    const loginMsg = document.createElement("p");
    loginMsg.className = "text-gray-400 mb-2";
    loginMsg.textContent = "Login to create your course plan";
    msg.appendChild(loginMsg);
    const loginBtn = document.createElement("button");
    loginBtn.className = "bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm";
    loginBtn.textContent = "Login";
    loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
    msg.appendChild(loginBtn);
    container.appendChild(msg);
    return;
  }

  // Semester tabs for planning
  const semesters = [1, 2, 3, 4].flatMap((y) =>
    ["autumn", "spring"].map((s) => ({ year: y, semester: s }))
  );

  const tabs = document.createElement("div");
  tabs.className = "flex gap-1 flex-wrap mb-4 bg-gray-50 rounded-lg p-1";

  let _selectedSem = semesters[0];

  semesters.forEach((sem) => {
    const tab = document.createElement("button");
    tab.className = `px-3 py-1.5 rounded text-xs font-medium transition-colors ${
      _selectedSem.year === sem.year && _selectedSem.semester === sem.semester
        ? "bg-white text-gray-800 shadow-sm"
        : "text-gray-500 hover:text-gray-700"
    }`;
    tab.textContent = `Y${sem.year} ${sem.semester.slice(0, 1).toUpperCase() + sem.semester.slice(1)}`;
    tab.addEventListener("click", () => {
      _selectedSem = sem;
      // Re-render tabs
      tabs.querySelectorAll("button").forEach((b, i) => {
        const s = semesters[i];
        const isActive = s.year === _selectedSem.year && s.semester === _selectedSem.semester;
        b.className = `px-3 py-1.5 rounded text-xs font-medium transition-colors ${
          isActive ? "bg-white text-gray-800 shadow-sm" : "text-gray-500 hover:text-gray-700"
        }`;
      });
      renderSemesterCourses();
    });
    tabs.appendChild(tab);
  });
  container.appendChild(tabs);

  const semGrid = document.createElement("div");
  semGrid.id = "plan-semester-grid";
  semGrid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3";
  container.appendChild(semGrid);

  function renderSemesterCourses() {
    const courses = _courses.filter(
      (c) => c.year === _selectedSem.year && c.semester === _selectedSem.semester
    );

    semGrid.innerHTML = "";
    if (courses.length === 0) {
      const empty = document.createElement("p");
      empty.className = "text-gray-400 text-center py-8 col-span-full";
      empty.textContent = "No courses scheduled for this semester.";
      semGrid.appendChild(empty);
    } else {
      courses.forEach((c) => {
        const card = CourseCard(c, true);
        // Add inline status dropdown
        const status = _getProgress(c.id);
        const dd = StatusDropdown(c.id, status || "not_started");
        dd.addEventListener("click", (e) => e.stopPropagation());
        card.appendChild(dd);
        semGrid.appendChild(card);
      });
    }
  }

  renderSemesterCourses();
}

// ── Main Render ──────────────────────────────────────────────────────────────

export async function renderPlanner() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "planner");
  app.innerHTML = "";

  const container = document.createElement("div");
  container.className = "max-w-4xl mx-auto px-4 py-6";

  // View tabs
  const tabs = document.createElement("div");
  tabs.className = "flex gap-2 mb-6 flex-wrap";
  tabs.appendChild(ViewTab("Overview", "overview"));
  tabs.appendChild(ViewTab("My Progress", "progress"));
  tabs.appendChild(ViewTab("Browse", "browse"));
  tabs.appendChild(ViewTab("Plan", "plan"));
  container.appendChild(tabs);

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
}

// ── Data ──────────────────────────────────────────────────────────────────────

async function _loadData() {
  _loading = true;
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
  } finally {
    _loading = false;
  }
}

async function _updateProgress(courseId, status) {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  try {
    await api.put("/courses/progress", { course_id: courseId, status });
    // Update local state
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
  el.className = "flex justify-center py-8";
  el.innerHTML = '<div class="spinner"></div>';
  return el;
}
