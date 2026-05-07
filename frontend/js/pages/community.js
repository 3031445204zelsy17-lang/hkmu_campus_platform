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
  search: null,
  loading: false,
};

let _fabContainer = null;

// Clean up FAB when navigating away from community
window.addEventListener("hashchange", () => {
  if (location.hash !== "#/community") _cleanupFab();
});

const CATEGORIES = [
  { value: null, label: "All" },
  { value: "discussion", label: "Discussion" },
  { value: "question", label: "Q&A" },
  { value: "sharing", label: "Sharing" },
  { value: "news", label: "Campus News" },
  { value: "other", label: "Other" },
];

// ── Helper: Avatar Fallbacks ────────────────────────────────────────────────

function _avatarFallback(post) {
  const el = document.createElement("div");
  el.className = "user-avatar-fallback";
  el.textContent = (post.author_nickname || "?")[0].toUpperCase();
  return el;
}

function _commentAvatarFallback(c) {
  const el = document.createElement("div");
  el.className = "comment-avatar-fallback";
  el.textContent = (c.author_nickname || "?")[0].toUpperCase();
  return el;
}

function _cleanupFab() {
  if (_fabContainer) {
    _fabContainer.remove();
    _fabContainer = null;
  }
}

// ── SVG Icon Helpers ─────────────────────────────────────────────────────────

function _heartIcon(filled) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "w-4 h-4");
  svg.setAttribute("fill", filled ? "currentColor" : "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("d", "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z");
  svg.appendChild(path);
  return svg;
}

function _commentIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "w-4 h-4");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("d", "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z");
  svg.appendChild(path);
  return svg;
}

// ── Functional UI Components ─────────────────────────────────────────────────

function PostHeader(post) {
  const el = document.createElement("div");
  el.className = "post-header";

  const userInfo = document.createElement("div");
  userInfo.className = "user-info";

  // Avatar: use API field if available, else gradient fallback
  if (post.author_avatar) {
    const img = document.createElement("img");
    img.className = "user-avatar";
    img.src = post.author_avatar;
    img.alt = (post.author_nickname || "User")[0].toUpperCase();
    img.onerror = () => { img.replaceWith(_avatarFallback(post)); };
    userInfo.appendChild(img);
  } else {
    userInfo.appendChild(_avatarFallback(post));
  }

  const nameTimeWrap = document.createElement("div");

  const name = document.createElement("div");
  name.className = "user-name";
  name.textContent = post.author_nickname || "Anonymous";

  const time = document.createElement("div");
  time.className = "user-time";
  time.textContent = _timeAgo(post.created_at);

  nameTimeWrap.appendChild(name);
  nameTimeWrap.appendChild(time);
  userInfo.appendChild(nameTimeWrap);
  el.appendChild(userInfo);

  // Author actions (edit/delete)
  if (isLoggedIn()) {
    const currentUserId = _getCurrentUserId();
    if (currentUserId && post.author_id === currentUserId) {
      const actions = document.createElement("div");
      actions.className = "flex gap-1 ml-auto";

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
  const colors = {
    discussion: "bg-blue-100 text-blue-700",
    question: "bg-amber-100 text-amber-700",
    sharing: "bg-green-100 text-green-700",
    news: "bg-purple-100 text-purple-700",
    other: "bg-gray-100 text-gray-600",
  };
  el.className = "category-badge " + (colors[category] || colors.other);
  el.textContent = category;
  return el;
}

function PostBody(post) {
  const el = document.createElement("div");
  el.className = "post-content";

  const headerRow = document.createElement("div");
  headerRow.className = "flex items-center gap-2 mb-2";
  headerRow.appendChild(CategoryBadge(post.category));

  const title = document.createElement("h3");
  title.textContent = post.title;
  headerRow.appendChild(title);

  const content = document.createElement("p");
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
  el.className = "post-actions";

  // Like button
  const likeBtn = document.createElement("button");
  likeBtn.className = "action-btn" + (post.is_liked ? " liked" : "");
  likeBtn.appendChild(_heartIcon(post.is_liked));
  const likeCount = document.createElement("span");
  likeCount.textContent = post.likes_count || 0;
  likeBtn.appendChild(likeCount);
  likeBtn.addEventListener("click", () => _toggleLike(post, likeBtn, likeCount));

  // Comment button
  const commentBtn = document.createElement("button");
  commentBtn.className = "action-btn";
  commentBtn.appendChild(_commentIcon());
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
  commentsContainer.className = "comments-section hidden";
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

function FilterBar() {
  const bar = document.createElement("div");
  bar.className = "filter-bar";

  // Sort buttons
  ["newest", "hot"].forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "filter-btn" + (_state.sort === s ? " active" : "");
    btn.dataset.sort = s;
    btn.textContent = s === "newest" ? "Newest" : "Hot";
    btn.addEventListener("click", () => {
      _state.sort = s;
      _state.page = 1;
      _loadPosts();
    });
    bar.appendChild(btn);
  });

  // Search box
  const searchBox = document.createElement("div");
  searchBox.className = "search-box";
  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.placeholder = "Search posts...";
  searchInput.setAttribute("aria-label", "Search posts");
  if (_state.search) searchInput.value = _state.search;
  const searchBtn = document.createElement("button");
  searchBtn.textContent = "Search";

  const doSearch = () => {
    _state.search = searchInput.value.trim() || null;
    _state.page = 1;
    _loadPosts();
  };
  searchBtn.addEventListener("click", doSearch);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
  });

  searchBox.appendChild(searchInput);
  searchBox.appendChild(searchBtn);
  bar.appendChild(searchBox);

  return bar;
}

function CategoryFilter() {
  const el = document.createElement("div");
  el.className = "category-tabs";

  CATEGORIES.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "category-tab" + (_state.category === c.value ? " active" : "");
    btn.dataset.category = c.value || "";
    btn.setAttribute("aria-label", c.label);

    // Liquid animation requires nested spans
    const textContainer = document.createElement("span");
    textContainer.className = "text-container";
    const text = document.createElement("span");
    text.className = "text";
    text.textContent = c.label;
    textContainer.appendChild(text);
    btn.appendChild(textContainer);

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
  _cleanupFab();

  // Read category/search from URL hash query params
  const hashQuery = window.location.hash.split("?")[1] || "";
  const urlParams = new URLSearchParams(hashQuery);
  const urlCategory = urlParams.get("category");
  const urlSearch = urlParams.get("search");
  if (urlCategory !== null || urlSearch !== null) {
    _state.category = urlCategory || null;
    _state.search = urlSearch || null;
    _state.page = 1;
  }

  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "community");

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6";

  // Page title
  const header = document.createElement("div");
  header.className = "mb-4";
  const title = document.createElement("h2");
  title.className = "text-2xl font-bold text-gray-800";
  title.textContent = "Community";
  header.appendChild(title);
  container.appendChild(header);

  // Filter bar (sort + search)
  container.appendChild(FilterBar());

  // Category tabs
  container.appendChild(CategoryFilter());

  // Posts feed
  const feed = document.createElement("div");
  feed.id = "posts-feed";
  feed.className = "post-list";
  feed.appendChild(LoadingSpinner());
  container.appendChild(feed);

  app.innerHTML = "";
  app.appendChild(container);

  // FAB (floating action button)
  if (isLoggedIn()) {
    _fabContainer = document.createElement("div");
    _fabContainer.className = "fab-container";
    const fabBtn = document.createElement("button");
    fabBtn.className = "fab-btn";
    fabBtn.textContent = "+ New Post";
    fabBtn.addEventListener("click", () => _showPostEditor());
    _fabContainer.appendChild(fabBtn);
    document.body.appendChild(_fabContainer);
  }

  _loadPosts();
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadPosts() {
  const feed = document.getElementById("posts-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = "";
  feed.appendChild(LoadingSpinner());

  // Update filter-btn active states
  document.querySelectorAll("[data-page='community'] .filter-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sort === _state.sort);
  });

  // Update category-tab active states
  document.querySelectorAll("[data-page='community'] .category-tab").forEach((btn) => {
    const v = btn.dataset.category || null;
    btn.classList.toggle("active", _state.category === v);
  });

  try {
    const params = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
      sort: _state.sort,
    });
    if (_state.category) params.set("category", _state.category);
    if (_state.search) params.set("search", _state.search);

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

    // Update SVG fill
    const svg = btnEl.querySelector("svg");
    svg.setAttribute("fill", post.is_liked ? "currentColor" : "none");
    btnEl.className = "action-btn" + (post.is_liked ? " liked" : "");
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

    data.items.forEach((c) => {
      const row = document.createElement("div");
      row.className = "comment";

      // Avatar
      if (c.author_avatar) {
        const img = document.createElement("img");
        img.className = "comment-avatar";
        img.src = c.author_avatar;
        img.alt = (c.author_nickname || "?")[0].toUpperCase();
        img.onerror = () => img.replaceWith(_commentAvatarFallback(c));
        row.appendChild(img);
      } else {
        row.appendChild(_commentAvatarFallback(c));
      }

      const body = document.createElement("div");
      body.className = "comment-content";

      const meta = document.createElement("div");
      const nameSpan = document.createElement("span");
      nameSpan.className = "comment-author";
      nameSpan.textContent = c.author_nickname;
      meta.appendChild(nameSpan);

      const timeSpan = document.createElement("span");
      timeSpan.className = "comment-time";
      timeSpan.textContent = _timeAgo(c.created_at);
      meta.appendChild(timeSpan);
      body.appendChild(meta);

      const text = document.createElement("p");
      text.textContent = c.content;
      body.appendChild(text);

      row.appendChild(body);
      section.appendChild(row);
    });

    if (data.items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "text-xs text-gray-400 text-center py-2";
      empty.textContent = "No comments yet";
      section.appendChild(empty);
    }

    if (isLoggedIn()) {
      _renderCommentInput(section, postId);
    }
  } catch (err) {
    section.innerHTML = "";
    const errorEl = document.createElement("p");
    errorEl.className = "text-xs text-red-400 text-center";
    errorEl.textContent = "Failed to load comments";
    section.appendChild(errorEl);
  }
}

function _renderCommentInput(section, postId) {
  const form = document.createElement("div");
  form.className = "comment-input";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = "Write a comment...";

  const btn = document.createElement("button");
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
      const post = _state.posts.find((p) => p.id === postId);
      if (post) post.comments_count++;
      const card = document.querySelector(`[data-post-id="${postId}"]`);
      if (card) {
        const commentBtn = card.querySelectorAll(".action-btn")[1];
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
