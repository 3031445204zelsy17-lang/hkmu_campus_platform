import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";

// ── State ────────────────────────────────────────────────────────────────────

let _state = {
  items: [],
  total: 0,
  page: 1,
  pageSize: 20,
  category: null,
  loading: false,
};

const CATEGORIES = [
  { value: null, label: "All" },
  { value: "announcement", label: "Announcements" },
  { value: "event", label: "Events" },
  { value: "academic", label: "Academic" },
  { value: "career", label: "Career" },
  { value: "other", label: "Other" },
];

let _fabContainer = null;

window.addEventListener("hashchange", () => {
  if (location.hash !== "#/news") _cleanupFab();
});

function _cleanupFab() {
  if (_fabContainer) {
    _fabContainer.remove();
    _fabContainer = null;
  }
}

// ── Main Render ──────────────────────────────────────────────────────────────

export function renderNews() {
  _cleanupFab();

  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "news");

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6";

  const header = document.createElement("div");
  header.className = "mb-4";
  const title = document.createElement("h2");
  title.className = "text-2xl font-bold text-gray-800";
  title.textContent = "Campus News";
  header.appendChild(title);
  container.appendChild(header);

  container.appendChild(_CategoryFilter());

  const feed = document.createElement("div");
  feed.id = "news-feed";
  feed.className = "news-list";
  feed.appendChild(_loadingSpinner());
  container.appendChild(feed);

  app.innerHTML = "";
  app.appendChild(container);

  if (isLoggedIn()) {
    _fabContainer = document.createElement("div");
    _fabContainer.className = "fab-container";
    const fabBtn = document.createElement("button");
    fabBtn.className = "fab-btn";
    fabBtn.textContent = "+ Add Link";
    fabBtn.addEventListener("click", _showCreateModal);
    _fabContainer.appendChild(fabBtn);
    document.body.appendChild(_fabContainer);
  }

  _loadNews();
}

// ── Components ───────────────────────────────────────────────────────────────

function _CategoryFilter() {
  const el = document.createElement("div");
  el.className = "news-category-tabs";

  CATEGORIES.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "news-tab" + (_state.category === c.value ? " active" : "");
    btn.textContent = c.label;
    btn.addEventListener("click", () => {
      _state.category = c.value;
      _state.page = 1;
      _loadNews();
      // update active state
      el.querySelectorAll(".news-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
    el.appendChild(btn);
  });

  return el;
}

function _NewsCard(item) {
  const card = document.createElement("a");
  card.className = "news-card card-hover";
  card.href = item.source_url;
  card.target = "_blank";
  card.rel = "noopener noreferrer";

  if (item.image_url) {
    const img = document.createElement("img");
    img.className = "news-card-image";
    img.src = item.image_url;
    img.alt = item.title;
    img.onerror = () => img.remove();
    card.appendChild(img);
  }

  const body = document.createElement("div");
  body.className = "news-card-body";

  const title = document.createElement("h3");
  title.className = "news-card-title";
  title.textContent = item.title;

  const meta = document.createElement("div");
  meta.className = "news-card-meta";

  if (item.category) {
    const cat = document.createElement("span");
    cat.className = "news-category-badge";
    cat.textContent = item.category;
    meta.appendChild(cat);
  }

  const time = document.createElement("span");
  time.textContent = _timeAgo(item.published_at);
  meta.appendChild(time);

  body.appendChild(title);

  if (item.summary) {
    const summary = document.createElement("p");
    summary.className = "news-card-summary";
    summary.textContent = item.summary;
    body.appendChild(summary);
  }

  body.appendChild(meta);
  card.appendChild(body);

  // Delete button — only for author
  const currentUserId = _getCurrentUserId();
  if (currentUserId && item.author_id === currentUserId) {
    const delBtn = document.createElement("button");
    delBtn.className = "news-delete-btn";
    delBtn.textContent = "×";
    delBtn.title = "Delete";
    delBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      _deleteNews(item.id);
    });
    card.appendChild(delBtn);
  }

  return card;
}

function _EmptyState() {
  const el = document.createElement("div");
  el.className = "text-center py-16";
  const icon = document.createElement("div");
  icon.className = "text-5xl mb-3 opacity-30";
  icon.textContent = "\u{1F4F0}";
  const p = document.createElement("p");
  p.className = "text-gray-400 text-lg";
  p.textContent = "No news yet";
  el.appendChild(icon);
  el.appendChild(p);
  return el;
}

function _loadingSpinner() {
  const el = document.createElement("div");
  el.className = "flex justify-center py-8";
  el.innerHTML = '<div class="spinner"></div>';
  return el;
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadNews() {
  const feed = document.getElementById("news-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = "";
  feed.appendChild(_loadingSpinner());

  try {
    const params = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
    });
    if (_state.category) params.set("category", _state.category);

    const data = await api.get(`/news?${params}`);
    _state.items = data.items;
    _state.total = data.total;

    feed.innerHTML = "";

    if (_state.items.length === 0) {
      feed.appendChild(_EmptyState());
    } else {
      _state.items.forEach((item) => feed.appendChild(_NewsCard(item)));
    }

    if (data.has_next) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "w-full py-2 text-sm text-blue-500 hover:text-blue-700 transition-colors";
      moreBtn.textContent = "Load more...";
      moreBtn.addEventListener("click", () => {
        _state.page++;
        _loadNews();
      });
      feed.appendChild(moreBtn);
    }
  } catch (err) {
    feed.innerHTML = "";
    const errorEl = document.createElement("p");
    errorEl.className = "text-red-400 text-center py-8";
    errorEl.textContent = "Failed to load news: " + err.message;
    feed.appendChild(errorEl);
  } finally {
    _state.loading = false;
  }
}

// ── Create News Modal ────────────────────────────────────────────────────────

function _showCreateModal() {
  const form = document.createElement("form");
  form.id = "news-create-form";
  form.className = "space-y-3";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.name = "title";
  titleInput.placeholder = "Title";
  titleInput.required = true;
  titleInput.maxLength = 200;
  titleInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const urlInput = document.createElement("input");
  urlInput.type = "url";
  urlInput.name = "source_url";
  urlInput.placeholder = "Link URL (https://...)";
  urlInput.required = true;
  urlInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const summaryInput = document.createElement("textarea");
  summaryInput.name = "summary";
  summaryInput.placeholder = "Brief summary (optional)";
  summaryInput.rows = 2;
  summaryInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";

  const categorySelect = document.createElement("select");
  categorySelect.name = "category";
  categorySelect.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  const placeholderOpt = document.createElement("option");
  placeholderOpt.value = "";
  placeholderOpt.textContent = "Category (optional)";
  categorySelect.appendChild(placeholderOpt);
  CATEGORIES.filter((c) => c.value).forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.value;
    opt.textContent = c.label;
    categorySelect.appendChild(opt);
  });

  const errDiv = document.createElement("div");
  errDiv.id = "news-create-error";
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = "Add Link";

  form.appendChild(titleInput);
  form.appendChild(urlInput);
  form.appendChild(summaryInput);
  form.appendChild(categorySelect);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal("Add News Link", form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const errEl = document.getElementById("news-create-error");

    try {
      errEl.classList.add("hidden");
      await api.post("/news", {
        title: fd.get("title"),
        source_url: fd.get("source_url"),
        summary: fd.get("summary") || null,
        category: fd.get("category") || null,
      });
      showToast("Link added!", "success");
      closeModal();
      _loadNews();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}

// ── Delete ───────────────────────────────────────────────────────────────────

async function _deleteNews(newsId) {
  if (!confirm("Delete this news item?")) return;
  try {
    await api.del(`/news/${newsId}`);
    showToast("News deleted", "info");
    _loadNews();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Utilities ────────────────────────────────────────────────────────────────

function _getCurrentUserId() {
  try {
    const token = localStorage.getItem("token");
    if (!token) return null;
    const payload = JSON.parse(atob(token.split(".")[1]));
    return parseInt(payload.sub);
  } catch {
    return null;
  }
}

function _timeAgo(isoStr) {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(isoStr).toLocaleDateString();
}
