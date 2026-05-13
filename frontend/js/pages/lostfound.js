import { api, isLoggedIn } from "../api.js";
import { t } from "../utils/i18n.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";
import { skeletonCard, errorState } from "../components/skeleton.js";

// ── State ────────────────────────────────────────────────────────────────────

let _state = {
  items: [],
  total: 0,
  page: 1,
  pageSize: 20,
  itemType: null,
  statusFilter: null,
  loading: false,
};

const ITEM_TYPES = [
  { value: null, labelKey: "lostfound.type_all" },
  { value: "lost", labelKey: "lostfound.type_lost" },
  { value: "found", labelKey: "lostfound.type_found" },
];

const STATUS_OPTIONS = [
  { value: null, labelKey: "lostfound.status_all" },
  { value: "active", labelKey: "lostfound.status_active" },
  { value: "resolved", labelKey: "lostfound.status_resolved" },
];

let _fabContainer = null;

window.addEventListener("hashchange", () => {
  if (location.hash !== "#/lostfound") _cleanupFab();
});

function _cleanupFab() {
  if (_fabContainer) {
    _fabContainer.remove();
    _fabContainer = null;
  }
}

// ── Main Render ──────────────────────────────────────────────────────────────

export function renderLostFound() {
  _cleanupFab();

  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "lostfound");

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6";

  const header = document.createElement("div");
  header.className = "mb-4";
  const title = document.createElement("h2");
  title.className = "text-2xl font-bold text-gray-800";
  title.textContent = t("lostfound.title");
  header.appendChild(title);
  container.appendChild(header);

  container.appendChild(_FilterBar());

  const feed = document.createElement("div");
  feed.id = "lf-feed";
  feed.className = "lf-list";
  feed.innerHTML = skeletonCard(3);
  container.appendChild(feed);

  app.innerHTML = "";
  app.appendChild(container);

  if (isLoggedIn()) {
    _fabContainer = document.createElement("div");
    _fabContainer.className = "fab-container";
    const fabBtn = document.createElement("button");
    fabBtn.className = "fab-btn";
    fabBtn.textContent = t("lostfound.report_item");
    fabBtn.addEventListener("click", _showCreateModal);
    _fabContainer.appendChild(fabBtn);
    document.body.appendChild(_fabContainer);
  }

  _loadItems();
}

// ── Components ───────────────────────────────────────────────────────────────

function _FilterBar() {
  const bar = document.createElement("div");
  bar.className = "lf-filter-bar";

  // Type tabs
  const typeWrap = document.createElement("div");
  typeWrap.className = "lf-type-tabs";

  ITEM_TYPES.forEach((itemType) => {
    const btn = document.createElement("button");
    btn.className = "lf-type-tab" + (_state.itemType === itemType.value ? " active" : "");
    btn.textContent = t(itemType.labelKey);
    if (itemType.value === "lost") btn.classList.add("lost");
    if (itemType.value === "found") btn.classList.add("found");
    btn.addEventListener("click", () => {
      _state.itemType = itemType.value;
      _state.page = 1;
      _loadItems();
      typeWrap.querySelectorAll(".lf-type-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
    typeWrap.appendChild(btn);
  });

  bar.appendChild(typeWrap);

  // Status filter
  const statusSelect = document.createElement("select");
  statusSelect.className = "lf-status-select";
  STATUS_OPTIONS.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.value || "";
    opt.textContent = t(s.labelKey);
    if (_state.statusFilter === s.value) opt.selected = true;
    statusSelect.appendChild(opt);
  });
  statusSelect.addEventListener("change", () => {
    _state.statusFilter = statusSelect.value || null;
    _state.page = 1;
    _loadItems();
  });
  bar.appendChild(statusSelect);

  return bar;
}

function _ItemCard(item) {
  const card = document.createElement("div");
  card.className = "lf-card card-hover";

  // Type badge
  const typeBadge = document.createElement("span");
  typeBadge.className = "lf-type-badge " + item.item_type;
  typeBadge.textContent = item.item_type === "lost" ? t("lostfound.lost_label") : t("lostfound.found_label");
  card.appendChild(typeBadge);

  // Status badge
  if (item.status === "resolved") {
    const statusBadge = document.createElement("span");
    statusBadge.className = "lf-status-badge resolved";
    statusBadge.textContent = t("lostfound.resolved_label");
    card.appendChild(statusBadge);
  }

  const body = document.createElement("div");
  body.className = "lf-card-body";

  const title = document.createElement("h3");
  title.className = "lf-card-title";
  title.textContent = item.title;

  body.appendChild(title);

  if (item.location) {
    const loc = document.createElement("p");
    loc.className = "lf-card-location";
    loc.textContent = "\u{1F4CD} " + item.location;
    body.appendChild(loc);
  }

  const desc = document.createElement("p");
  desc.className = "lf-card-desc";
  desc.textContent = item.description.length > 150 ? item.description.slice(0, 150) + "..." : item.description;
  body.appendChild(desc);

  const meta = document.createElement("div");
  meta.className = "lf-card-meta";

  const author = document.createElement("span");
  author.textContent = item.author_nickname || t("community.anonymous");

  const time = document.createElement("span");
  time.textContent = _timeAgo(item.created_at);

  meta.appendChild(author);
  meta.appendChild(time);
  body.appendChild(meta);

  card.appendChild(body);

  // Author actions
  if (isLoggedIn() && _isItemOwner(item.author_id)) {
    const actions = document.createElement("div");
    actions.className = "lf-card-actions";

    if (item.status === "active") {
      const resolveBtn = document.createElement("button");
      resolveBtn.className = "lf-action-btn resolve";
      resolveBtn.textContent = t("lostfound.resolved_label");
      resolveBtn.addEventListener("click", () => _resolveItem(item.id));
      actions.appendChild(resolveBtn);
    }

    const delBtn = document.createElement("button");
    delBtn.className = "lf-action-btn delete";
    delBtn.textContent = t("community.delete");
    delBtn.addEventListener("click", () => _deleteItem(item.id));
    actions.appendChild(delBtn);

    card.appendChild(actions);
  }

  return card;
}

function _EmptyState() {
  const el = document.createElement("div");
  el.className = "text-center py-16";
  const icon = document.createElement("div");
  icon.className = "text-5xl mb-3 opacity-30";
  icon.textContent = "\u{1F50D}";
  const p = document.createElement("p");
  p.className = "text-gray-400 text-lg";
  p.textContent = t("lostfound.empty_title");
  el.appendChild(icon);
  el.appendChild(p);
  return el;
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadItems() {
  const feed = document.getElementById("lf-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = skeletonCard(3);

  try {
    const params = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
    });
    if (_state.itemType) params.set("item_type", _state.itemType);
    if (_state.statusFilter) params.set("status", _state.statusFilter);

    const data = await api.get(`/lostfound?${params}`);
    _state.items = data.items;
    _state.total = data.total;

    feed.innerHTML = "";

    if (_state.items.length === 0) {
      feed.appendChild(_EmptyState());
    } else {
      _state.items.forEach((item) => feed.appendChild(_ItemCard(item)));
    }

    if (data.has_next) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "w-full py-2 text-sm text-blue-500 hover:text-blue-700 transition-colors";
      moreBtn.textContent = t("lostfound.load_more");
      moreBtn.addEventListener("click", () => {
        _state.page++;
        _loadItems();
      });
      feed.appendChild(moreBtn);
    }
  } catch (err) {
    feed.innerHTML = "";
    feed.appendChild(errorState(t("lostfound.load_failed")));
    showToast(t("lostfound.load_failed"), "error");
  } finally {
    _state.loading = false;
  }
}

// ── Create Item Modal ────────────────────────────────────────────────────────

function _showCreateModal() {
  const form = document.createElement("form");
  form.id = "lf-create-form";
  form.className = "space-y-3";

  const typeGroup = document.createElement("div");
  typeGroup.className = "flex gap-3";

  const lostLabel = document.createElement("label");
  lostLabel.className = "lf-radio-label";
  const lostRadio = document.createElement("input");
  lostRadio.type = "radio";
  lostRadio.name = "item_type";
  lostRadio.value = "lost";
  lostRadio.required = true;
  lostRadio.checked = true;
  lostLabel.appendChild(lostRadio);
  lostLabel.appendChild(document.createTextNode(" " + t("lostfound.i_lost")));

  const foundLabel = document.createElement("label");
  foundLabel.className = "lf-radio-label";
  const foundRadio = document.createElement("input");
  foundRadio.type = "radio";
  foundRadio.name = "item_type";
  foundRadio.value = "found";
  foundRadio.checked = false;
  foundLabel.appendChild(foundRadio);
  foundLabel.appendChild(document.createTextNode(" " + t("lostfound.i_found")));

  typeGroup.appendChild(lostLabel);
  typeGroup.appendChild(foundLabel);

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.name = "title";
  titleInput.placeholder = t("lostfound.field_title");
  titleInput.required = true;
  titleInput.maxLength = 200;
  titleInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const locationInput = document.createElement("input");
  locationInput.type = "text";
  locationInput.name = "location";
  locationInput.placeholder = t("lostfound.field_location");
  locationInput.maxLength = 200;
  locationInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const descInput = document.createElement("textarea");
  descInput.name = "description";
  descInput.placeholder = t("lostfound.field_desc");
  descInput.required = true;
  descInput.maxLength = 2000;
  descInput.rows = 4;
  descInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";

  const errDiv = document.createElement("div");
  errDiv.id = "lf-create-error";
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = t("lostfound.submit_report");

  form.appendChild(typeGroup);
  form.appendChild(titleInput);
  form.appendChild(locationInput);
  form.appendChild(descInput);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal(t("lostfound.report_modal"), form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const errEl = document.getElementById("lf-create-error");

    try {
      errEl.classList.add("hidden");
      await api.post("/lostfound", {
        title: fd.get("title"),
        description: fd.get("description"),
        item_type: fd.get("item_type"),
        location: fd.get("location") || null,
      });
      showToast(t("lostfound.report_submitted"), "success");
      closeModal();
      _loadItems();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}

// ── Actions ──────────────────────────────────────────────────────────────────

async function _resolveItem(itemId) {
  if (!confirm(t("lostfound.confirm_resolve"))) return;
  try {
    await api.put(`/lostfound/${itemId}`, { status: "resolved" });
    showToast(t("lostfound.marked_resolved"), "success");
    _loadItems();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function _deleteItem(itemId) {
  if (!confirm(t("lostfound.confirm_delete"))) return;
  try {
    await api.del(`/lostfound/${itemId}`);
    showToast(t("lostfound.report_deleted"), "info");
    _loadItems();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Utilities ────────────────────────────────────────────────────────────────

function _isItemOwner(authorId) {
  try {
    const token = localStorage.getItem("token");
    if (!token) return false;
    const payload = JSON.parse(atob(token.split(".")[1]));
    return parseInt(payload.sub) === authorId;
  } catch {
    return false;
  }
}

function _timeAgo(isoStr) {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return t("time.just_now");
  if (mins < 60) return t("time.minutes_ago", { n: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("time.hours_ago", { n: hours });
  const days = Math.floor(hours / 24);
  if (days < 30) return t("time.days_ago", { n: days });
  return new Date(isoStr).toLocaleDateString();
}
