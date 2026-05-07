import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";

// ── State ────────────────────────────────────────────────────────────────────

let _state = {
  posts: [],
  total: 0,
  page: 1,
  pageSize: 20,
  sort: "newest",
  category: null,
  loading: false,
};

const CATEGORIES = [
  { value: null, label: "All" },
  { value: "discussion", label: "Discussion" },
  { value: "question", label: "Q&A" },
  { value: "sharing", label: "Sharing" },
  { value: "news", label: "Campus News" },
  { value: "other", label: "Other" },
];

// ── Functional UI Components ─────────────────────────────────────────────────

function PostHeader(post) {
  const el = document.createElement("div");
  el.className = "flex items-center gap-3 mb-3";

  const avatar = document.createElement("div");
  avatar.className = "w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-green-500 flex items-center justify-center text-white font-semibold text-sm";
  avatar.textContent = (post.author_nickname || "?")[0].toUpperCase();

  const info = document.createElement("div");
  info.className = "flex-1 min-w-0";

  const name = document.createElement("div");
  name.className = "font-medium text-gray-800 text-sm truncate";
  name.textContent = post.author_nickname || "Anonymous";

  const meta = document.createElement("div");
  meta.className = "text-xs text-gray-400";
  meta.textContent = _timeAgo(post.created_at);

  info.appendChild(name);
  info.appendChild(meta);
  el.appendChild(avatar);
  el.appendChild(info);

  // Author actions
  if (isLoggedIn()) {
    const currentUserId = _getCurrentUserId();
    if (currentUserId && post.author_id === currentUserId) {
      const actions = document.createElement("div");
      actions.className = "flex gap-1";

      const editBtn = document.createElement("button");
      editBtn.className = "text-gray-400 hover:text-blue-500 text-xs px-2 py-1";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => _showPostEditor(post));

      const delBtn = document.createElement("button");
      delBtn.className = "text-gray-400 hover:text-red-500 text-xs px-2 py-1";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => _deletePost(post.id));

      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      el.appendChild(actions);
    }
  }

  return el;
}

function CategoryBadge(category) {
  const el = document.createElement("span");
  el.className = "category-badge";
  const colors = {
    discussion: "bg-blue-100 text-blue-700",
    question: "bg-amber-100 text-amber-700",
    sharing: "bg-green-100 text-green-700",
    news: "bg-purple-100 text-purple-700",
    other: "bg-gray-100 text-gray-600",
  };
  el.className += " " + (colors[category] || colors.other);
  el.textContent = category;
  return el;
}

function PostBody(post) {
  const el = document.createElement("div");

  const title = document.createElement("h3");
  title.className = "text-lg font-semibold text-gray-800 mb-2";
  title.textContent = post.title;

  const badge = CategoryBadge(post.category);

  const headerRow = document.createElement("div");
  headerRow.className = "flex items-center gap-2 mb-2";
  headerRow.appendChild(badge);
  headerRow.appendChild(title);

  const content = document.createElement("p");
  content.className = "text-gray-600 text-sm leading-relaxed mb-3";
  const maxLen = 300;
  if (post.content.length > maxLen) {
    content.textContent = post.content.slice(0, maxLen) + "...";

    const more = document.createElement("button");
    more.className = "text-blue-500 text-xs hover:underline ml-1";
    more.textContent = "Read more";
    more.addEventListener("click", () => {
      content.textContent = post.content;
      more.remove();
    });
    content.appendChild(more);
  } else {
    content.textContent = post.content;
  }

  el.appendChild(headerRow);
  el.appendChild(content);
  return el;
}

function PostActions(post) {
  const el = document.createElement("div");
  el.className = "flex items-center gap-4 pt-2 border-t border-gray-100";

  // Like button
  const likeBtn = document.createElement("button");
  likeBtn.className = `flex items-center gap-1 text-sm transition-colors ${
    post.is_liked ? "text-red-500" : "text-gray-400 hover:text-red-400"
  }`;
  likeBtn.innerHTML = `<svg class="w-4 h-4" fill="${post.is_liked ? "currentColor" : "none"}" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>`;
  const likeCount = document.createElement("span");
  likeCount.textContent = post.likes_count || 0;
  likeBtn.appendChild(likeCount);
  likeBtn.addEventListener("click", () => _toggleLike(post, likeBtn, likeCount));

  // Comment button
  const commentBtn = document.createElement("button");
  commentBtn.className = "flex items-center gap-1 text-sm text-gray-400 hover:text-blue-400 transition-colors";
  commentBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>`;
  const commentCount = document.createElement("span");
  commentCount.textContent = post.comments_count || 0;
  commentBtn.appendChild(commentCount);
  commentBtn.addEventListener("click", () => _toggleComments(post.id));

  el.appendChild(likeBtn);
  el.appendChild(commentBtn);
  return el;
}

function PostCard(post) {
  const card = document.createElement("div");
  card.className = "post-card";
  card.dataset.postId = post.id;
  card.appendChild(PostHeader(post));
  card.appendChild(PostBody(post));
  card.appendChild(PostActions(post));

  // Comments container (hidden)
  const commentsContainer = document.createElement("div");
  commentsContainer.className = "comments-section hidden mt-3 pt-3 border-t border-gray-100";
  commentsContainer.id = `comments-${post.id}`;
  card.appendChild(commentsContainer);

  return card;
}

function EmptyState() {
  const el = document.createElement("div");
  el.className = "text-center py-16";

  const icon = document.createElement("div");
  icon.className = "text-5xl mb-3 opacity-30";
  icon.textContent = "\u{1F4AC}";

  const p1 = document.createElement("p");
  p1.className = "text-gray-400 text-lg";
  p1.textContent = "No posts yet";

  const p2 = document.createElement("p");
  p2.className = "text-gray-300 text-sm mt-1";
  p2.textContent = "Be the first to share something!";

  el.appendChild(icon);
  el.appendChild(p1);
  el.appendChild(p2);
  return el;
}

function LoadingSpinner() {
  const el = document.createElement("div");
  el.className = "flex justify-center py-8";
  el.innerHTML = '<div class="spinner"></div>';
  return el;
}

// ── Toolbar Components ───────────────────────────────────────────────────────

function SortTabs() {
  const el = document.createElement("div");
  el.className = "flex gap-1 bg-gray-100 rounded-lg p-1";

  ["newest", "hot"].forEach((s) => {
    const btn = document.createElement("button");
    btn.className = `sort-tab px-3 py-1 rounded-md text-sm transition-colors ${
      _state.sort === s ? "bg-white text-gray-800 shadow-sm" : "text-gray-500 hover:text-gray-700"
    }`;
    btn.dataset.sort = s;
    btn.textContent = s === "newest" ? "Newest" : "Hot";
    btn.addEventListener("click", () => {
      _state.sort = s;
      _state.page = 1;
      _loadPosts();
    });
    el.appendChild(btn);
  });
  return el;
}

function CategoryFilter() {
  const el = document.createElement("div");
  el.className = "flex gap-2 flex-wrap";

  CATEGORIES.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = `cat-filter text-xs px-3 py-1 rounded-full border transition-colors ${
      _state.category === c.value
        ? "bg-blue-600 text-white border-blue-600"
        : "bg-white text-gray-500 border-gray-200 hover:border-blue-300"
    }`;
    btn.dataset.category = c.value || "";
    btn.textContent = c.label;
    btn.addEventListener("click", () => {
      _state.category = c.value;
      _state.page = 1;
      _loadPosts();
    });
    el.appendChild(btn);
  });
  return el;
}

// ── Main Render ──────────────────────────────────────────────────────────────

export function renderCommunity() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "community");

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6 space-y-4";

  // Header row
  const header = document.createElement("div");
  header.className = "flex items-center justify-between";

  const title = document.createElement("h2");
  title.className = "text-2xl font-bold text-gray-800";
  title.textContent = "Community";

  header.appendChild(title);

  if (isLoggedIn()) {
    const newBtn = document.createElement("button");
    newBtn.id = "new-post-btn";
    newBtn.className = "bg-green-600 text-white px-4 py-2 rounded-lg hover:bg-green-700 transition-colors text-sm font-medium";
    newBtn.textContent = "+ New Post";
    newBtn.addEventListener("click", () => _showPostEditor());
    header.appendChild(newBtn);
  }

  container.appendChild(header);

  // Toolbar
  const toolbar = document.createElement("div");
  toolbar.className = "flex items-center justify-between gap-3";
  toolbar.appendChild(SortTabs());
  toolbar.appendChild(CategoryFilter());
  container.appendChild(toolbar);

  // Posts feed
  const feed = document.createElement("div");
  feed.id = "posts-feed";
  feed.className = "space-y-4";
  feed.appendChild(LoadingSpinner());
  container.appendChild(feed);

  app.innerHTML = "";
  app.appendChild(container);

  _loadPosts();
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadPosts() {
  const feed = document.getElementById("posts-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = "";
  feed.appendChild(LoadingSpinner());

  // Update toolbar active states
  document.querySelectorAll(".sort-tab").forEach((btn) => {
    btn.className = btn.className.replace(/bg-white text-gray-800 shadow-sm/g, "").replace(/text-gray-500 hover:text-gray-700/g, "");
    if (btn.dataset.sort === _state.sort) {
      btn.className += " bg-white text-gray-800 shadow-sm";
    } else {
      btn.className += " text-gray-500 hover:text-gray-700";
    }
  });

  document.querySelectorAll(".cat-filter").forEach((btn) => {
    const v = btn.dataset.category || null;
    const isActive = _state.category === v;
    btn.className = `cat-filter text-xs px-3 py-1 rounded-full border transition-colors ${
      isActive ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-500 border-gray-200 hover:border-blue-300"
    }`;
  });

  try {
    const params = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
      sort: _state.sort,
    });
    if (_state.category) params.set("category", _state.category);

    const data = await api.get(`/posts?${params}`);
    _state.posts = data.items;
    _state.total = data.total;

    feed.innerHTML = "";

    if (_state.posts.length === 0) {
      feed.appendChild(EmptyState());
    } else {
      _state.posts.forEach((post) => feed.appendChild(PostCard(post)));
    }

    // Load more button
    if (data.has_next) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "w-full py-2 text-sm text-blue-500 hover:text-blue-700 transition-colors";
      moreBtn.textContent = "Load more...";
      moreBtn.addEventListener("click", () => {
        _state.page++;
        _loadPosts();
      });
      feed.appendChild(moreBtn);
    }
  } catch (err) {
    feed.innerHTML = "";
    const errorEl = document.createElement("p");
    errorEl.className = "text-red-400 text-center py-8";
    errorEl.textContent = "Failed to load posts. " + err.message;
    feed.appendChild(errorEl);
  } finally {
    _state.loading = false;
  }
}

// ── Interactions ─────────────────────────────────────────────────────────────

async function _toggleLike(post, btnEl, countEl) {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  try {
    const updated = await api.post(`/posts/${post.id}/like`);
    post.is_liked = updated.is_liked;
    post.likes_count = updated.likes_count;

    // Update UI in-place
    const svg = btnEl.querySelector("svg");
    svg.setAttribute("fill", post.is_liked ? "currentColor" : "none");
    btnEl.className = `flex items-center gap-1 text-sm transition-colors ${
      post.is_liked ? "text-red-500" : "text-gray-400 hover:text-red-400"
    }`;
    countEl.textContent = post.likes_count;
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function _toggleComments(postId) {
  const section = document.getElementById(`comments-${postId}`);
  if (!section) return;

  if (section.classList.contains("hidden")) {
    section.classList.remove("hidden");
    await _loadComments(postId);
  } else {
    section.classList.add("hidden");
  }
}

async function _loadComments(postId) {
  const section = document.getElementById(`comments-${postId}`);
  if (!section) return;
  section.innerHTML = '<div class="flex justify-center py-2"><div class="spinner"></div></div>';

  try {
    const data = await api.get(`/posts/${postId}/comments?page=1&page_size=50`);

    section.innerHTML = "";

    // Comment list
    data.items.forEach((c) => {
      const row = document.createElement("div");
      row.className = "flex gap-2 mb-3";

      const avatar = document.createElement("div");
      avatar.className = "w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500 flex-shrink-0";
      avatar.textContent = (c.author_nickname || "?")[0].toUpperCase();

      const body = document.createElement("div");
      body.className = "flex-1";

      const meta = document.createElement("div");
      meta.className = "text-xs text-gray-500 mb-0.5";
      const nameSpan = document.createElement("span");
      nameSpan.className = "font-medium text-gray-700";
      nameSpan.textContent = c.author_nickname;
      meta.appendChild(nameSpan);
      meta.appendChild(document.createTextNode(" · " + _timeAgo(c.created_at)));

      const text = document.createElement("p");
      text.className = "text-sm text-gray-600";
      text.textContent = c.content;

      body.appendChild(meta);
      body.appendChild(text);
      row.appendChild(avatar);
      row.appendChild(body);
      section.appendChild(row);
    });

    if (data.items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "text-xs text-gray-400 text-center py-2";
      empty.textContent = "No comments yet";
      section.appendChild(empty);
    }

    // Comment input
    if (isLoggedIn()) {
      _renderCommentInput(section, postId);
    }
  } catch (err) {
    section.innerHTML = `<p class="text-xs text-red-400 text-center">Failed to load comments</p>`;
  }
}

function _renderCommentInput(section, postId) {
  const form = document.createElement("div");
  form.className = "flex gap-2 mt-2";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Write a comment...";
  input.className = "flex-1 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400";

  const btn = document.createElement("button");
  btn.className = "bg-blue-500 text-white px-3 py-1.5 rounded-lg text-sm hover:bg-blue-600 transition-colors disabled:opacity-50";
  btn.textContent = "Send";
  btn.disabled = true;

  input.addEventListener("input", () => {
    btn.disabled = !input.value.trim();
  });

  btn.addEventListener("click", async () => {
    const content = input.value.trim();
    if (!content) return;
    btn.disabled = true;
    btn.textContent = "...";

    try {
      await api.post(`/posts/${postId}/comments`, { content });
      input.value = "";
      showToast("Comment posted!", "success");
      // Update state count
      const post = _state.posts.find((p) => p.id === postId);
      if (post) post.comments_count++;
      // Update DOM count on the post card
      const card = document.querySelector(`[data-post-id="${postId}"]`);
      if (card) {
        const commentBtn = card.querySelectorAll("button")[1];
        const countSpan = commentBtn?.querySelector("span");
        if (countSpan) countSpan.textContent = post.comments_count;
      }
      await _loadComments(postId);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Send";
    }
  });

  form.appendChild(input);
  form.appendChild(btn);
  section.appendChild(form);
}

// ── Post Editor Modal ────────────────────────────────────────────────────────

function _showPostEditor(post = null) {
  const isEdit = !!post;

  const form = document.createElement("form");
  form.id = "post-editor-form";
  form.className = "space-y-3";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.name = "title";
  titleInput.placeholder = "Title";
  titleInput.required = true;
  titleInput.maxLength = 200;
  titleInput.value = isEdit ? post.title : "";
  titleInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const select = document.createElement("select");
  select.name = "category";
  select.required = true;
  select.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";

  const placeholderOpt = document.createElement("option");
  placeholderOpt.value = "";
  placeholderOpt.disabled = true;
  placeholderOpt.selected = !isEdit;
  placeholderOpt.textContent = "Select category";
  select.appendChild(placeholderOpt);

  CATEGORIES.filter((c) => c.value).forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.value;
    opt.textContent = c.label;
    if (isEdit && post.category === c.value) opt.selected = true;
    select.appendChild(opt);
  });

  const textarea = document.createElement("textarea");
  textarea.name = "content";
  textarea.placeholder = "What's on your mind?";
  textarea.required = true;
  textarea.maxLength = 10000;
  textarea.rows = 5;
  textarea.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";
  textarea.value = isEdit ? post.content : "";

  const errDiv = document.createElement("div");
  errDiv.id = "post-editor-error";
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = isEdit ? "Update Post" : "Publish Post";

  form.appendChild(titleInput);
  form.appendChild(select);
  form.appendChild(textarea);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal(isEdit ? "Edit Post" : "New Post", form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      title: fd.get("title"),
      content: fd.get("content"),
      category: fd.get("category"),
    };

    const errEl = document.getElementById("post-editor-error");
    try {
      errEl.classList.add("hidden");
      if (isEdit) {
        await api.put(`/posts/${post.id}`, body);
        showToast("Post updated!", "success");
      } else {
        await api.post("/posts", body);
        showToast("Post published!", "success");
      }
      closeModal();
      _loadPosts();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}

async function _deletePost(postId) {
  if (!confirm("Delete this post?")) return;

  try {
    await api.del(`/posts/${postId}`);
    showToast("Post deleted", "info");
    _loadPosts();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Utilities ────────────────────────────────────────────────────────────────

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

function _escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function _escapeAttr(s) {
  return s.replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

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
