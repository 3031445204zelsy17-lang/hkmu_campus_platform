import { api } from "../api.js";
import { t } from "../utils/i18n.js";
import { showToast } from "../components/toast.js";
import { skeletonCard, errorState } from "../components/skeleton.js";

// ── Reusable components ──────────────────────────────────────────────────────

function _homeCard(iconName, label, desc, fromColor, toColor, route) {
  const card = document.createElement("div");
  card.className = "bg-white rounded-2xl p-6 shadow-sm hover:shadow-lg transition-all hover:-translate-y-1 cursor-pointer";

  const iconWrap = document.createElement("div");
  iconWrap.className = `w-14 h-14 bg-gradient-to-br ${fromColor} ${toColor} rounded-xl flex items-center justify-center mb-5`;
  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", iconName);
  icon.className = "w-7 h-7 text-white";
  iconWrap.appendChild(icon);
  card.appendChild(iconWrap);

  const title = document.createElement("h3");
  title.className = "text-xl font-bold text-gray-800 mb-2";
  title.textContent = label;
  card.appendChild(title);

  const descEl = document.createElement("p");
  descEl.className = "text-sm text-gray-500";
  descEl.textContent = desc;
  card.appendChild(descEl);

  card.addEventListener("click", () => { location.hash = route; });
  return card;
}

function _statCard(iconName, value, label, colorClass) {
  const card = document.createElement("div");
  card.className = "bg-white rounded-2xl p-6 shadow-md text-center";

  const icon = document.createElement("i");
  icon.setAttribute("data-lucide", iconName);
  icon.className = `w-8 h-8 ${colorClass} mx-auto mb-2`;
  card.appendChild(icon);

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

function _quickLinkItem(iconName, label, rightText, route) {
  const btn = document.createElement("button");
  btn.className = "w-full flex items-center justify-between p-4 bg-gray-50 rounded-xl hover:bg-blue-50 transition-colors text-left";
  btn.addEventListener("click", () => { location.hash = route; });

  const left = document.createElement("div");
  left.className = "flex items-center gap-3";

  if (typeof iconName === "number") {
    // Year number badge
    const badge = document.createElement("span");
    badge.className = "w-8 h-8 bg-gradient-to-br from-blue-600 to-green-600 text-white rounded-lg flex items-center justify-center font-bold text-sm";
    badge.textContent = iconName;
    left.appendChild(badge);
  } else {
    const dot = document.createElement("span");
    dot.className = `w-3 h-3 ${iconName} rounded-full`;
    left.appendChild(dot);
  }

  const text = document.createElement("span");
  text.className = "font-medium text-gray-700";
  text.textContent = label;
  left.appendChild(text);
  btn.appendChild(left);

  const right = document.createElement("div");
  right.className = "flex items-center gap-2";
  if (rightText) {
    const rt = document.createElement("span");
    rt.className = "text-sm text-gray-400";
    rt.textContent = rightText;
    right.appendChild(rt);
  }
  const chevron = document.createElement("i");
  chevron.setAttribute("data-lucide", "chevron-right");
  chevron.className = "w-5 h-5 text-gray-400";
  right.appendChild(chevron);
  btn.appendChild(right);

  return btn;
}

// ── Main render ──────────────────────────────────────────────────────────────

export async function renderHome() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "home");
  app.innerHTML = "";

  const wrap = document.createElement("div");
  wrap.className = "space-y-10";

  // ── 1. Hero section ──────────────────────────────────────────────────────
  const hero = document.createElement("section");
  hero.className = "relative overflow-hidden rounded-2xl";
  hero.style.background = "linear-gradient(135deg, #0066CC, #2E7D52, #0066CC)";
  hero.style.backgroundSize = "200% 200%";
  hero.style.animation = "planner-gradientShift 8s ease infinite";

  // Floating shapes
  const deco1 = document.createElement("div");
  deco1.className = "absolute top-8 right-10 w-32 h-32 bg-white/10 rounded-full";
  deco1.style.animation = "planner-float 6s ease-in-out infinite";
  hero.appendChild(deco1);

  const deco2 = document.createElement("div");
  deco2.className = "absolute bottom-8 left-10 w-20 h-20 bg-white/10 rounded-full";
  deco2.style.animation = "planner-float 6s ease-in-out infinite";
  deco2.style.animationDelay = "2s";
  hero.appendChild(deco2);

  const deco3 = document.createElement("div");
  deco3.className = "absolute top-20 right-48 w-12 h-12 bg-white/5 rounded-full";
  deco3.style.animation = "planner-float 6s ease-in-out infinite";
  deco3.style.animationDelay = "4s";
  hero.appendChild(deco3);

  const inner = document.createElement("div");
  inner.className = "max-w-3xl mx-auto text-center py-16 px-4 relative z-10";

  // Pill label
  const pill = document.createElement("span");
  pill.className = "inline-flex items-center gap-2 px-4 py-2 bg-white/20 rounded-full text-white text-sm font-medium mb-6";
  const pillIcon = document.createElement("i");
  pillIcon.setAttribute("data-lucide", "sparkles");
  pillIcon.className = "w-4 h-4";
  pill.appendChild(pillIcon);
  const pillText = document.createElement("span");
  pillText.textContent = t("home.hero_title");
  pill.appendChild(pillText);
  inner.appendChild(pill);

  const h1 = document.createElement("h1");
  h1.className = "text-4xl sm:text-5xl font-bold text-white mb-4";
  h1.textContent = t("home.hero_subtitle");
  inner.appendChild(h1);

  const desc = document.createElement("p");
  desc.className = "text-lg text-white/80 mb-8 max-w-2xl mx-auto";
  desc.textContent = t("home.hero_desc");
  inner.appendChild(desc);

  // CTA buttons
  const ctaRow = document.createElement("div");
  ctaRow.className = "flex flex-col sm:flex-row gap-4 justify-center";

  const btn1 = document.createElement("button");
  btn1.className = "bg-white px-8 py-4 rounded-xl font-semibold flex items-center justify-center gap-2 hover:opacity-90 transition-opacity";
  btn1.style.color = "#0066CC";
  btn1.appendChild(_lucide("message-circle", "w-5 h-5"));
  btn1.appendChild(_text(t("home.join_community")));
  btn1.addEventListener("click", () => { location.hash = "#/community"; });
  ctaRow.appendChild(btn1);

  const btn2 = document.createElement("button");
  btn2.className = "bg-white/20 text-white border-2 border-white/50 px-8 py-4 rounded-xl font-semibold flex items-center justify-center gap-2 hover:bg-white/30 transition-colors";
  btn2.appendChild(_lucide("book-open", "w-5 h-5"));
  btn2.appendChild(_text(t("home.plan_courses")));
  btn2.addEventListener("click", () => { location.hash = "#/planner"; });
  ctaRow.appendChild(btn2);

  inner.appendChild(ctaRow);
  hero.appendChild(inner);

  // SVG wave
  const waveDiv = document.createElement("div");
  waveDiv.className = "absolute bottom-0 left-0 right-0";
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 1440 120");
  svg.setAttribute("fill", "none");
  svg.style.display = "block";
  const wavePath = document.createElementNS(svgNS, "path");
  wavePath.setAttribute("d", "M0 120L60 110C120 100 240 80 360 70C480 60 600 60 720 65C840 70 960 80 1080 85C1200 90 1320 90 1380 90L1440 90V120H0Z");
  wavePath.setAttribute("fill", "#F5F7FA");
  svg.appendChild(wavePath);
  waveDiv.appendChild(svg);
  hero.appendChild(waveDiv);

  wrap.appendChild(hero);

  // ── 2. Stats section ─────────────────────────────────────────────────────
  const statsSection = document.createElement("section");
  statsSection.className = "py-2";
  const statsGrid = document.createElement("div");
  statsGrid.className = "grid grid-cols-2 lg:grid-cols-4 gap-6";

  // Show skeleton while loading
  const main = document.getElementById("app-content");
  main.appendChild(wrap);
  statsSection.innerHTML = skeletonCard(4);

  // Fetch course stats
  let courseCount = 43;
  try {
    const data = await api.get("/courses?page_size=1");
    if (data.total !== undefined) courseCount = data.total;
    else if (data.items) courseCount = data.items.length;
  } catch (err) {
    statsSection.innerHTML = errorState(t("error.load_failed"), err.message);
    showToast(err.message, "error");
  }

  if (!statsSection.querySelector(".flex.flex-col")) {
    statsSection.innerHTML = "";
    const totalCredits = courseCount * 3; // approximate
    statsGrid.appendChild(_statCard("book-open", courseCount, t("home.stat_courses"), "text-blue-600"));
    statsGrid.appendChild(_statCard("award", totalCredits, t("home.stat_credits"), "text-green-600"));
    statsGrid.appendChild(_statCard("layers", "6", t("home.stat_categories"), "text-purple-600"));
    statsGrid.appendChild(_statCard("calendar", "4", t("home.stat_years"), "text-orange-500"));
    statsSection.appendChild(statsGrid);
  }
  wrap.appendChild(statsSection);

  // ── 3. Feature cards ─────────────────────────────────────────────────────
  const featureSection = document.createElement("section");
  const featureTitle = document.createElement("h2");
  featureTitle.className = "text-2xl font-bold mb-6";
  featureTitle.textContent = t("home.explore");
  featureSection.appendChild(featureTitle);

  const featureGrid = document.createElement("div");
  featureGrid.className = "grid grid-cols-1 md:grid-cols-3 gap-6";
  featureGrid.appendChild(_homeCard("message-circle", t("home.feat_community"), t("home.feat_community_desc"), "from-blue-500", "to-blue-600", "#/community"));
  featureGrid.appendChild(_homeCard("book-open", t("home.feat_planner"), t("home.feat_planner_desc"), "from-green-500", "to-green-600", "#/planner"));
  featureGrid.appendChild(_homeCard("newspaper", t("home.feat_news"), t("home.feat_news_desc"), "from-orange-500", "to-orange-600", "#/news"));
  featureSection.appendChild(featureGrid);
  wrap.appendChild(featureSection);

  // ── 4. Quick Links ───────────────────────────────────────────────────────
  const linksSection = document.createElement("section");
  const linksTitle = document.createElement("h2");
  linksTitle.className = "text-2xl font-bold mb-6";
  linksTitle.textContent = t("home.quick_links");
  linksSection.appendChild(linksTitle);

  const linksGrid = document.createElement("div");
  linksGrid.className = "grid grid-cols-1 lg:grid-cols-2 gap-6";

  // Browse by Year
  const yearCard = document.createElement("div");
  yearCard.className = "bg-white rounded-2xl p-6 shadow-md";
  const yearHeader = document.createElement("div");
  yearHeader.className = "flex items-center gap-2 mb-5";
  yearHeader.appendChild(_lucide("graduation-cap", "w-5 h-5 text-blue-600"));
  const yearTitle = document.createElement("h3");
  yearTitle.className = "text-lg font-bold";
  yearTitle.textContent = t("home.browse_year");
  yearHeader.appendChild(yearTitle);
  yearCard.appendChild(yearHeader);

  const yearList = document.createElement("div");
  yearList.className = "space-y-2";
  [1, 2, 3, 4].forEach((y) => {
    yearList.appendChild(_quickLinkItem(y, `Year ${y} Courses`, `${y === 1 ? '13' : y === 2 ? '9' : y === 3 ? '11' : '10'} courses`, `#/planner`));
  });
  yearCard.appendChild(yearList);
  linksGrid.appendChild(yearCard);

  // Browse by Category
  const catCard = document.createElement("div");
  catCard.className = "bg-white rounded-2xl p-6 shadow-md";
  const catHeader = document.createElement("div");
  catHeader.className = "flex items-center gap-2 mb-5";
  catHeader.appendChild(_lucide("layers", "w-5 h-5 text-green-600"));
  const catTitle = document.createElement("h3");
  catTitle.className = "text-lg font-bold";
  catTitle.textContent = t("home.browse_category");
  catHeader.appendChild(catTitle);
  catCard.appendChild(catHeader);

  const catList = document.createElement("div");
  catList.className = "space-y-2";
  const categories = [
    { color: "bg-blue-500", name: t("home.cat_core"), credits: "84 cr" },
    { color: "bg-purple-500", name: t("home.cat_elective"), credits: "12 cr" },
    { color: "bg-amber-500", name: t("home.cat_project"), credits: "6 cr" },
    { color: "bg-emerald-500", name: t("home.cat_english"), credits: "6 cr" },
    { color: "bg-pink-500", name: t("home.cat_general"), credits: "6 cr" },
    { color: "bg-indigo-500", name: t("home.cat_university"), credits: "9 cr" },
  ];
  categories.forEach((cat) => {
    catList.appendChild(_quickLinkItem(cat.color, cat.name, cat.credits, "#/planner"));
  });
  catCard.appendChild(catList);
  linksGrid.appendChild(catCard);

  linksSection.appendChild(linksGrid);
  wrap.appendChild(linksSection);

  if (window.lucide) window.lucide.createIcons();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function _lucide(name, className = "w-5 h-5") {
  const i = document.createElement("i");
  i.setAttribute("data-lucide", name);
  i.className = className;
  return i;
}

function _text(content) {
  const span = document.createElement("span");
  span.textContent = content;
  return span;
}
