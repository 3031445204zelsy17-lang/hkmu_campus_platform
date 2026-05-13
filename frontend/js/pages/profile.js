import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";
import { t } from "../utils/i18n.js";

// ── State ────────────────────────────────────────────────────────────────────

let _profileUser = null;
let _posts = [];
let _postsPage = 1;
let _postsHasMore = false;
let _activeTab = "posts";

// ── Main Render ──────────────────────────────────────────────────────────────

export async function renderProfile(userId) {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "profile");

  if (!isLoggedIn()) {
    app.innerHTML = "";
    const msg = document.createElement("p");
    msg.className = "text-gray-500 text-center py-8";
    msg.textContent = t("profile.login_required");
    app.appendChild(msg);
    return;
  }

  app.innerHTML = "";
  app.appendChild(_loadingSpinner());

  try {
    if (userId) {
      _profileUser = await api.get(`/users/${userId}`);
    } else {
      _profileUser = await api.get("/users/me");
    }
    _activeTab = "posts";
    _postsPage = 1;
    await _loadUserPosts();
    _renderPage(app);
  } catch (err) {
    app.innerHTML = "";
    const errorEl = document.createElement("p");
    errorEl.className = "text-red-400 text-center py-8";
    errorEl.textContent = t("error.load_failed") + ": " + err.message;
    app.appendChild(errorEl);
  }
}

// ── Page Structure ───────────────────────────────────────────────────────────

function _renderPage(app) {
  app.innerHTML = "";

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6";

  container.appendChild(_ProfileHeader(_profileUser));
  container.appendChild(_StatsBar(_profileUser));
  container.appendChild(_TabBar());
  container.appendChild(_TabContent());

  app.appendChild(container);
}

// ── Components ───────────────────────────────────────────────────────────────

function _ProfileHeader(user) {
  const el = document.createElement("div");
  el.className = "profile-header";

  // Avatar
  const avatarWrap = document.createElement("div");
  avatarWrap.className = "avatar-wrapper";
  if (user.avatar_url) {
    const img = document.createElement("img");
    img.className = "avatar";
    img.src = user.avatar_url;
    img.alt = (user.nickname || "U")[0].toUpperCase();
    img.onerror = () => img.replaceWith(_avatarFallback(user));
    avatarWrap.appendChild(img);
  } else {
    avatarWrap.appendChild(_avatarFallback(user));
  }
  el.appendChild(avatarWrap);

  const info = document.createElement("div");
  info.className = "profile-info";

  const name = document.createElement("h2");
  name.className = "profile-name";
  name.textContent = user.nickname || user.username;
  info.appendChild(name);

  if (user.student_id) {
    const sid = document.createElement("p");
    sid.className = "profile-subtitle";
    sid.textContent = t("profile.student_id", { id: user.student_id });
    info.appendChild(sid);
  }

  const identity = document.createElement("span");
  identity.className = "identity-badge";
  identity.textContent = user.identity || "student";
  info.appendChild(identity);

  if (user.bio) {
    const bio = document.createElement("p");
    bio.className = "profile-bio";
    bio.textContent = user.bio;
    info.appendChild(bio);
  }

  el.appendChild(info);

  // Edit button (only own profile)
  if (_isOwnProfile()) {
    const editBtn = document.createElement("button");
    editBtn.className = "edit-profile-btn";
    editBtn.textContent = t("profile.edit");
    editBtn.addEventListener("click", _showEditModal);
    el.appendChild(editBtn);
  }

  return el;
}

function _StatsBar(user) {
  const el = document.createElement("div");
  el.className = "stats-bar";

  const stats = [
    { label: t("profile.tab_posts"), value: _posts.length },
    { label: t("profile.tab_identity"), value: user.identity || "student" },
    { label: t("profile.tab_joined"), value: _formatDate(user.created_at) },
  ];

  stats.forEach((s) => {
    const card = document.createElement("div");
    card.className = "stat-card";
    const val = document.createElement("div");
    val.className = "stat-value";
    val.textContent = s.value;
    const lbl = document.createElement("div");
    lbl.className = "stat-label";
    lbl.textContent = s.label;
    card.appendChild(val);
    card.appendChild(lbl);
    el.appendChild(card);
  });

  return el;
}

function _TabBar() {
  const el = document.createElement("div");
  el.className = "profile-tabs";

  ["posts"].forEach((tab) => {
    const btn = document.createElement("button");
    btn.className = "profile-tab" + (_activeTab === tab ? " active" : "");
    btn.textContent = tab.charAt(0).toUpperCase() + tab.slice(1);
    btn.addEventListener("click", () => {
      _activeTab = tab;
      _renderPage(document.getElementById("app-content"));
    });
    el.appendChild(btn);
  });

  return el;
}

function _TabContent() {
  const el = document.createElement("div");
  el.id = "profile-tab-content";

  if (_activeTab === "posts") {
    if (_posts.length === 0) {
      el.appendChild(_emptyState(t("profile.no_posts")));
    } else {
      _posts.forEach((post) => el.appendChild(_PostCard(post)));
      if (_postsHasMore) {
        const moreBtn = document.createElement("button");
        moreBtn.className = "load-more-btn";
        moreBtn.textContent = t("profile.load_more");
        moreBtn.addEventListener("click", async () => {
          _postsPage++;
          await _loadUserPosts();
          _renderPage(document.getElementById("app-content"));
        });
        el.appendChild(moreBtn);
      }
    }
  }

  return el;
}

function _PostCard(post) {
  const card = document.createElement("div");
  card.className = "profile-post-card";

  const title = document.createElement("h4");
  title.className = "profile-post-title";
  title.textContent = post.title;

  const meta = document.createElement("div");
  meta.className = "profile-post-meta";

  const cat = document.createElement("span");
  cat.className = "category-badge " + _categoryColor(post.category);
  cat.textContent = post.category;

  const time = document.createElement("span");
  time.textContent = _timeAgo(post.created_at);

  meta.appendChild(cat);
  meta.appendChild(time);

  const content = document.createElement("p");
  content.className = "profile-post-content";
  content.textContent = post.content.length > 150 ? post.content.slice(0, 150) + "..." : post.content;

  card.appendChild(title);
  card.appendChild(meta);
  card.appendChild(content);
  return card;
}

// ── Edit Profile Modal ───────────────────────────────────────────────────────

function _showEditModal() {
  const form = document.createElement("form");
  form.id = "edit-profile-form";
  form.className = "space-y-3";

  const nicknameInput = document.createElement("input");
  nicknameInput.type = "text";
  nicknameInput.name = "nickname";
  nicknameInput.placeholder = t("profile.field_nickname");
  nicknameInput.maxLength = 30;
  nicknameInput.required = true;
  nicknameInput.value = _profileUser.nickname || "";
  nicknameInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const bioInput = document.createElement("textarea");
  bioInput.name = "bio";
  bioInput.placeholder = t("profile.field_bio");
  bioInput.maxLength = 300;
  bioInput.rows = 3;
  bioInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";
  bioInput.value = _profileUser.bio || "";

  const avatarSection = document.createElement("div");
  avatarSection.className = "space-y-2";

  const avatarLabel = document.createElement("label");
  avatarLabel.className = "block text-sm font-medium text-gray-700";
  avatarLabel.textContent = t("profile.field_avatar");

  const avatarInput = document.createElement("input");
  avatarInput.type = "file";
  avatarInput.name = "avatar";
  avatarInput.accept = "image/*";
  avatarInput.className = "block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100";

  avatarSection.appendChild(avatarLabel);
  avatarSection.appendChild(avatarInput);

  const errDiv = document.createElement("div");
  errDiv.id = "edit-profile-error";
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = t("profile.save_changes");

  form.appendChild(nicknameInput);
  form.appendChild(bioInput);
  form.appendChild(avatarSection);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal(t("profile.edit_modal"), form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = document.getElementById("edit-profile-error");
    errEl.classList.add("hidden");

    try {
      const fd = new FormData(e.target);

      // Update text fields
      await api.put("/users/me", {
        nickname: fd.get("nickname"),
        bio: fd.get("bio"),
      });

      // Upload avatar if selected
      const avatarFile = avatarInput.files[0];
      if (avatarFile) {
        const avatarForm = new FormData();
        avatarForm.append("file", avatarFile);
        const token = localStorage.getItem("token");
        const res = await fetch("/api/v1/users/me/avatar", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: avatarForm,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || "Avatar upload failed");
        }
      }

      _profileUser = await api.get("/users/me");
      showToast(t("profile.updated"), "success");
      closeModal();
      _renderPage(document.getElementById("app-content"));
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadUserPosts() {
  try {
    const data = await api.get(`/posts?page=${_postsPage}&page_size=10`);
    if (_postsPage === 1) {
      _posts = data.items.filter((p) => p.author_id === _profileUser.id);
    } else {
      _posts = _posts.concat(data.items.filter((p) => p.author_id === _profileUser.id));
    }
    _postsHasMore = data.has_next;
  } catch (err) {
    _posts = [];
    _postsHasMore = false;
    showToast(t("error.load_failed"), "error");
  }
}

// ── Utilities ────────────────────────────────────────────────────────────────

function _isOwnProfile() {
  try {
    const token = localStorage.getItem("token");
    if (!token) return false;
    const payload = JSON.parse(atob(token.split(".")[1]));
    return parseInt(payload.sub) === _profileUser.id;
  } catch {
    return false;
  }
}

function _avatarFallback(user) {
  const el = document.createElement("div");
  el.className = "avatar-fallback";
  el.textContent = (user.nickname || user.username || "?")[0].toUpperCase();
  return el;
}

function _loadingSpinner() {
  const el = document.createElement("div");
  el.className = "flex justify-center py-8";
  el.innerHTML = '<div class="spinner"></div>';
  return el;
}

function _emptyState(text) {
  const el = document.createElement("div");
  el.className = "text-center py-12";
  const p = document.createElement("p");
  p.className = "text-gray-400";
  p.textContent = text;
  el.appendChild(p);
  return el;
}

function _timeAgo(isoStr) {
  if (!isoStr) return "";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return t("time.just_now");
  if (mins < 60) return t("time.minutes_ago", {n: mins});
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("time.hours_ago", {n: hours});
  const days = Math.floor(hours / 24);
  if (days < 30) return t("time.days_ago", {n: days});
  return new Date(isoStr).toLocaleDateString();
}

function _formatDate(isoStr) {
  if (!isoStr) return t("profile.not_available");
  return new Date(isoStr).toLocaleDateString();
}

function _categoryColor(cat) {
  const colors = {
    discussion: "bg-blue-100 text-blue-700",
    question: "bg-amber-100 text-amber-700",
    sharing: "bg-green-100 text-green-700",
    news: "bg-purple-100 text-purple-700",
    other: "bg-gray-100 text-gray-600",
  };
  return colors[cat] || colors.other;
}
