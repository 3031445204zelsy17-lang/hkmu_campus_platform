import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";
import { openModal, closeModal } from "../components/modal.js";
import { t } from "../utils/i18n.js";
import { skeletonCard, errorState } from "../components/skeleton.js";
import { track } from "../utils/analytics.js";
import { createImageUploader } from "../components/image_upload.js";
import { responsiveSrcset } from "../utils/image.js";

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
  highlightPostId: null,
  lfItemType: null,
  lfStatusFilter: null,
};

let _fabContainer = null;

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// Clean up FAB when navigating away from community
window.addEventListener("hashchange", () => {
  if (!location.hash.startsWith("#/community")) _cleanupFab();
});

const CATEGORIES = [
  { value: null, labelKey: "community.cat_all" },
  { value: "discussion", labelKey: "community.cat_discussion" },
  { value: "question", labelKey: "community.cat_question" },
  { value: "sharing", labelKey: "community.cat_sharing" },
  { value: "news", labelKey: "community.cat_news" },
  { value: "treehole", labelKey: "community.cat_treehole" },
  { value: "lostfound", labelKey: "community.cat_lostfound" },
  { value: "other", labelKey: "community.cat_other" },
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

function _shareIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "w-4 h-4");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("d", "M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z");
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
  name.textContent = post.author_nickname || t("community.anonymous");

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
      editBtn.textContent = t("community.edit");
      editBtn.addEventListener("click", () => _showPostEditor(post));

      const delBtn = document.createElement("button");
      delBtn.className = "text-gray-400 hover:text-red-500 text-xs px-2 py-1";
      delBtn.textContent = t("community.delete");
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
    treehole: "bg-gray-800 text-gray-100",
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
    more.textContent = t("community.read_more");
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

  if (post.image_url) {
    const img = document.createElement("img");
    img.src = post.image_url;
    img.srcset = responsiveSrcset(post.image_url);
    img.alt = post.title;
    img.className = "post-card-img";
    img.loading = "lazy";
    el.appendChild(img);
  }

  if (post.quoted_post) {
    const qCard = document.createElement("div");
    qCard.className = "quoted-post-card";
    qCard.addEventListener("click", () => {
      window.location.hash = `#/community?post=${post.quoted_post.id}`;
    });

    const qAuthor = document.createElement("div");
    qAuthor.className = "quoted-author";
    qAuthor.textContent = `@${post.quoted_post.author_nickname || "?"}`;

    const qTitle = document.createElement("div");
    qTitle.className = "quoted-title";
    qTitle.textContent = post.quoted_post.title;

    const qPreview = document.createElement("div");
    qPreview.className = "quoted-preview";
    qPreview.textContent = post.quoted_post.content_preview;

    qCard.appendChild(qAuthor);
    qCard.appendChild(qTitle);
    qCard.appendChild(qPreview);
    el.appendChild(qCard);
  }

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

  // Share button
  const shareWrapper = document.createElement("div");
  shareWrapper.style.position = "relative";

  const shareBtn = document.createElement("button");
  shareBtn.className = "action-btn";
  shareBtn.appendChild(_shareIcon());
  const shareLabel = document.createElement("span");
  shareLabel.textContent = t("community.share");
  shareBtn.appendChild(shareLabel);

  shareBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    _toggleShareMenu(shareWrapper, post);
  });

  shareWrapper.appendChild(shareBtn);
  el.appendChild(shareWrapper);

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
  p1.textContent = t("community.empty_title");

  const p2 = document.createElement("p");
  p2.className = "text-gray-300 text-sm mt-1";
  p2.textContent = t("community.empty_desc");

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
    btn.textContent = s === "newest" ? t("community.sort_newest") : t("community.sort_hot");
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
  searchInput.placeholder = t("community.search_placeholder");
  searchInput.setAttribute("aria-label", t("community.search"));
  if (_state.search) searchInput.value = _state.search;
  const searchBtn = document.createElement("button");
  searchBtn.textContent = t("community.search");

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
  el.setAttribute("role", "tablist");

  CATEGORIES.forEach((c) => {
    const btn = document.createElement("button");
    btn.className = "category-tab" + (_state.category === c.value ? " active" : "");
    btn.dataset.category = c.value || "";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", String(_state.category === c.value));
    btn.setAttribute("aria-label", t(c.labelKey));

    // Liquid animation requires nested spans
    const textContainer = document.createElement("span");
    textContainer.className = "text-container";
    const text = document.createElement("span");
    text.className = "text";
    text.textContent = t(c.labelKey);
    textContainer.appendChild(text);
    btn.appendChild(textContainer);

    btn.addEventListener("click", () => {
      const newHash = c.value ? `#/community?category=${c.value}` : "#/community";
      window.location.hash = newHash;
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
  _state.category = urlParams.get("category") || null;
  _state.search = urlParams.get("search") || null;
  _state.highlightPostId = urlParams.get("post") || null;
  _state.page = 1;

  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "community");

  const container = document.createElement("div");
  container.className = "max-w-2xl mx-auto px-4 py-6";

  // Page title
  const header = document.createElement("div");
  header.className = "mb-4";
  const title = document.createElement("h2");
  title.className = "text-2xl font-bold text-gray-800";
  title.textContent = t("community.title");
  header.appendChild(title);
  container.appendChild(header);

  // Filter bar depends on category
  if (_state.category === "lostfound") {
    container.appendChild(_LostFoundFilterBar());
  } else {
    container.appendChild(FilterBar());
  }

  // Category tabs
  container.appendChild(CategoryFilter());

  // Feed
  const feed = document.createElement("div");
  feed.id = "posts-feed";
  feed.className = "post-list";
  feed.innerHTML = skeletonCard(3);
  container.appendChild(feed);

  app.innerHTML = "";
  app.appendChild(container);

  // FAB (floating action button)
  if (isLoggedIn()) {
    _fabContainer = document.createElement("div");
    _fabContainer.className = "fab-container";
    const fabBtn = document.createElement("button");
    fabBtn.className = "fab-btn";
    if (_state.category === "lostfound") {
      fabBtn.textContent = t("lostfound.report_item");
      fabBtn.addEventListener("click", () => _showLostFoundModal());
    } else {
      fabBtn.textContent = t("community.new_post");
      fabBtn.addEventListener("click", () => _showPostEditor());
    }
    _fabContainer.appendChild(fabBtn);
    document.body.appendChild(_fabContainer);
  }

  if (_state.category === "lostfound") {
    _loadLostFound();
  } else {
    _loadPosts();
  }
}

// ── Data Loading ─────────────────────────────────────────────────────────────

async function _loadPosts() {
  const feed = document.getElementById("posts-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = skeletonCard(3);

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

    // Highlight shared post if ?post={id} is present
    if (_state.highlightPostId) {
      const targetCard = feed.querySelector(`[data-post-id="${_state.highlightPostId}"]`);
      if (targetCard) {
        setTimeout(() => {
          targetCard.scrollIntoView({ behavior: "smooth", block: "center" });
          targetCard.classList.add("post-highlight");
          setTimeout(() => targetCard.classList.remove("post-highlight"), 3000);
        }, 100);
      }
      _state.highlightPostId = null;
    }

    // Load more button
    if (data.has_next) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "w-full py-2 text-sm text-blue-500 hover:text-blue-700 transition-colors";
      moreBtn.textContent = t("community.load_more");
      moreBtn.addEventListener("click", () => {
        _state.page++;
        _loadPosts();
      });
      feed.appendChild(moreBtn);
    }
  } catch (err) {
    feed.innerHTML = errorState(t("error.load_failed"), err.message);
    showToast(err.message, "error");
  } finally {
    _state.loading = false;
  }
}

// ── Interactions ─────────────────────────────────────────────────────────────

let _activeShareMenu = null;

function _closeShareMenu() {
  if (_activeShareMenu) {
    _activeShareMenu.remove();
    _activeShareMenu = null;
  }
}

function _toggleShareMenu(wrapper, post) {
  _closeShareMenu();

  const menu = document.createElement("div");
  menu.className = "share-menu";

  // Copy link
  const copyItem = document.createElement("button");
  copyItem.className = "share-menu-item";
  copyItem.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>`;
  const copyText = document.createElement("span");
  copyText.textContent = t("community.share_copy_link");
  copyItem.appendChild(copyText);
  copyItem.addEventListener("click", (e) => { e.stopPropagation(); _shareExternal(post); });

  // DM forward
  const dmItem = document.createElement("button");
  dmItem.className = "share-menu-item";
  dmItem.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>`;
  const dmText = document.createElement("span");
  dmText.textContent = t("community.share_dm");
  dmItem.appendChild(dmText);
  dmItem.addEventListener("click", (e) => { e.stopPropagation(); _closeShareMenu(); _shareViaDM(post); });

  // Repost
  const repostItem = document.createElement("button");
  repostItem.className = "share-menu-item";
  repostItem.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4"/></svg>`;
  const repostText = document.createElement("span");
  repostText.textContent = t("community.share_repost");
  repostItem.appendChild(repostText);
  repostItem.addEventListener("click", (e) => { e.stopPropagation(); _closeShareMenu(); _shareAsRepost(post); });

  menu.appendChild(copyItem);
  menu.appendChild(dmItem);
  menu.appendChild(repostItem);
  wrapper.appendChild(menu);
  _activeShareMenu = menu;

  // Close on outside click
  setTimeout(() => {
    const closer = (evt) => {
      if (!menu.contains(evt.target)) {
        _closeShareMenu();
        document.removeEventListener("click", closer, true);
      }
    };
    document.addEventListener("click", closer, true);
  }, 0);
}

async function _shareExternal(post) {
  _closeShareMenu();
  const baseUrl = window.location.origin + window.location.pathname;
  const shareUrl = `${baseUrl}#/community?post=${post.id}`;
  const shareTitle = post.title || "HKMU Community Post";

  if (navigator.share) {
    try {
      await navigator.share({ title: shareTitle, text: post.content.slice(0, 100), url: shareUrl });
      track("post_shared", { method: "native" });
      return;
    } catch (err) {
      if (err.name === "AbortError") return;
    }
  }

  try {
    await navigator.clipboard.writeText(shareUrl);
    track("post_shared", { method: "copy_link" });
  } catch {
    const ta = document.createElement("textarea");
    ta.value = shareUrl;
    ta.style.cssText = "position:fixed;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  showToast(t("community.link_copied"), "success");
}

function _shareViaDM(post) {
  if (!isLoggedIn()) { showToast(t("community.share_login_required"), "warning"); return; }

  const wrapper = document.createElement("div");

  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.placeholder = t("community.share_search_user");
  searchInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 mb-3";

  const resultsDiv = document.createElement("div");
  resultsDiv.className = "max-h-60 overflow-y-auto";
  resultsDiv.textContent = "";

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    const q = searchInput.value.trim();
    if (!q) { resultsDiv.innerHTML = ""; return; }
    searchTimer = setTimeout(async () => {
      try {
        const users = await api.get(`/users/search?q=${encodeURIComponent(q)}`);
        resultsDiv.innerHTML = "";
        if (!users.length) {
          resultsDiv.textContent = t("messages.no_users");
          return;
        }
        users.forEach((u) => {
          const row = document.createElement("button");
          row.type = "button";
          row.className = "flex items-center gap-3 w-full p-3 rounded-lg hover:bg-gray-50 transition-colors text-left";
          row.innerHTML = `<span class="font-medium text-sm">${escapeHtml(u.nickname || u.username)}</span>`;
          row.addEventListener("click", async () => {
            try {
              const msgContent = `[${t("community.quoted_post")}] ${post.title}\n${post.content.slice(0, 100)}${post.content.length > 100 ? "..." : ""}\n${window.location.origin}${window.location.pathname}#/community?post=${post.id}`;
              await api.post(`/messages/${u.id}`, { content: msgContent });
              showToast(t("community.share_sent"), "success");
              track("post_shared", { method: "dm" });
              closeModal();
            } catch (err) {
              showToast(err.message, "error");
            }
          });
          resultsDiv.appendChild(row);
        });
      } catch {
        resultsDiv.textContent = t("messages.search_failed");
      }
    }, 300);
  });

  wrapper.appendChild(searchInput);
  wrapper.appendChild(resultsDiv);
  openModal(t("community.share_dm"), wrapper);
  setTimeout(() => searchInput.focus(), 100);
}

function _shareAsRepost(post) {
  if (!isLoggedIn()) { showToast(t("community.share_login_required"), "warning"); return; }

  const form = document.createElement("form");
  form.id = "post-editor-form";
  form.className = "space-y-3";

  // Quoted post preview
  const quotePreview = document.createElement("div");
  quotePreview.className = "repost-quote-preview";
  const qAuthor = document.createElement("div");
  qAuthor.className = "rq-author";
  qAuthor.textContent = `@${post.author_nickname || "?"}`;
  const qTitle = document.createElement("div");
  qTitle.className = "rq-title";
  qTitle.textContent = post.title;
  quotePreview.appendChild(qAuthor);
  quotePreview.appendChild(qTitle);

  const titleInput = document.createElement("input");
  titleInput.type = "hidden";
  titleInput.name = "title";
  titleInput.value = `${t("community.repost_label")}: ${post.title}`;

  const categoryInput = document.createElement("input");
  categoryInput.type = "hidden";
  categoryInput.name = "category";
  categoryInput.value = post.category;

  const textarea = document.createElement("textarea");
  textarea.name = "content";
  textarea.placeholder = t("community.field_content");
  textarea.maxLength = 10000;
  textarea.rows = 3;
  textarea.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";

  const errDiv = document.createElement("div");
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = t("community.publish");

  form.appendChild(quotePreview);
  form.appendChild(titleInput);
  form.appendChild(categoryInput);
  form.appendChild(textarea);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal(t("community.share_repost"), form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const userContent = fd.get("content") || "";
    const body = {
      title: fd.get("title"),
      content: userContent || fd.get("title"),
      category: fd.get("category"),
      parent_post_id: post.id,
    };

    try {
      await api.post("/posts", body);
      showToast(t("community.post_published"), "success");
      closeModal();
      _loadPosts();
    } catch (err) {
      errDiv.textContent = err.message;
      errDiv.classList.remove("hidden");
    }
  });
}

async function _toggleLike(post, btnEl, countEl) {
  if (!isLoggedIn()) {
    window.dispatchEvent(new CustomEvent("auth:show-login"));
    return;
  }

  try {
    const updated = await api.post(`/posts/${post.id}/like`);
    post.is_liked = updated.is_liked;
    post.likes_count = updated.likes_count;
    track("post_liked", { post_id: post.id, liked: post.is_liked });

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
      empty.textContent = t("community.no_comments");
      section.appendChild(empty);
    }

    if (isLoggedIn()) {
      _renderCommentInput(section, postId);
    } else {
      const loginPrompt = document.createElement("div");
      loginPrompt.className = "text-center py-2";
      const loginBtn = document.createElement("button");
      loginBtn.className = "text-sm text-blue-500 hover:underline";
      loginBtn.textContent = t("community.login_to_comment");
      loginBtn.addEventListener("click", () => window.dispatchEvent(new CustomEvent("auth:show-login")));
      loginPrompt.appendChild(loginBtn);
      section.appendChild(loginPrompt);
    }
  } catch (err) {
    section.innerHTML = "";
    const errorEl = document.createElement("p");
    errorEl.className = "text-xs text-red-400 text-center";
    errorEl.textContent = t("error.load_failed");
    section.appendChild(errorEl);
    showToast(err.message, "error");
  }
}

function _renderCommentInput(section, postId) {
  const form = document.createElement("div");
  form.className = "comment-input";

  const input = document.createElement("input");
  input.type = "text";
  input.placeholder = t("community.write_comment");
  input.setAttribute("aria-label", t("community.write_comment"));

  const btn = document.createElement("button");
  btn.textContent = t("community.send");
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
      showToast(t("community.comment_posted"), "success");
      track("comment_created", { post_id: postId, page_context: "community" });
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
      btn.textContent = t("community.send");
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
  titleInput.placeholder = t("community.field_title");
  titleInput.required = true;
  titleInput.maxLength = 200;
  titleInput.value = isEdit ? post.title : "";
  titleInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  titleInput.setAttribute("aria-label", t("community.field_title"));

  const select = document.createElement("select");
  select.name = "category";
  select.required = true;
  select.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  select.setAttribute("aria-label", t("community.field_category"));

  const placeholderOpt = document.createElement("option");
  placeholderOpt.value = "";
  placeholderOpt.disabled = true;
  placeholderOpt.selected = !isEdit;
  placeholderOpt.textContent = t("community.field_category");
  select.appendChild(placeholderOpt);

  CATEGORIES.filter((c) => c.value).forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.value;
    opt.textContent = t(c.labelKey);
    if (isEdit && post.category === c.value) opt.selected = true;
    select.appendChild(opt);
  });

  const anonWrapper = document.createElement("div");
  anonWrapper.className = "flex items-center gap-2 text-sm text-gray-600";
  const anonCheckbox = document.createElement("input");
  anonCheckbox.type = "checkbox";
  anonCheckbox.name = "is_anonymous";
  anonCheckbox.id = "anon-toggle";
  anonCheckbox.className = "w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500";
  const anonLabel = document.createElement("label");
  anonLabel.htmlFor = "anon-toggle";
  anonLabel.className = "select-none cursor-pointer";
  anonLabel.textContent = t("community.post_anonymously");
  anonWrapper.appendChild(anonCheckbox);
  anonWrapper.appendChild(anonLabel);

  if (isEdit && post.is_anonymous) anonCheckbox.checked = true;

  select.addEventListener("change", () => {
    const isTreehole = select.value === "treehole";
    anonCheckbox.checked = isTreehole;
    anonCheckbox.disabled = isTreehole;
  });

  const textarea = document.createElement("textarea");
  textarea.name = "content";
  textarea.placeholder = t("community.field_content");
  textarea.required = true;
  textarea.maxLength = 10000;
  textarea.rows = 5;
  textarea.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";
  textarea.setAttribute("aria-label", t("community.field_content"));
  textarea.value = isEdit ? post.content : "";

  const errDiv = document.createElement("div");
  errDiv.id = "post-editor-error";
  errDiv.className = "text-red-500 text-xs hidden";

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.className = "w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium";
  submitBtn.textContent = isEdit ? t("community.update") : t("community.publish");

  // Image upload is only available when creating a new post (editing the image
  // of an existing post is not supported yet — PostUpdate has no image_url).
  const imageUploader = isEdit ? null : createImageUploader({ module: "posts" });

  form.appendChild(titleInput);
  form.appendChild(select);
  form.appendChild(anonWrapper);
  form.appendChild(textarea);
  if (imageUploader) form.appendChild(imageUploader.el);
  form.appendChild(errDiv);
  form.appendChild(submitBtn);

  openModal(isEdit ? t("community.modal_edit") : t("community.modal_new"), form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      title: fd.get("title"),
      content: fd.get("content"),
      category: fd.get("category"),
      is_anonymous: fd.get("is_anonymous") === "on",
      image_url: imageUploader ? imageUploader.getUrl() : null,
    };

    const errEl = document.getElementById("post-editor-error");
    try {
      errEl.classList.add("hidden");
      if (isEdit) {
        await api.put(`/posts/${post.id}`, body);
        showToast(t("community.post_updated"), "success");
      } else {
        await api.post("/posts", body);
        showToast(t("community.post_published"), "success");
        track("post_created", { category: body.category, is_anonymous: body.is_anonymous });
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
  if (!confirm(t("community.confirm_delete"))) return;

  try {
    await api.del(`/posts/${postId}`);
    showToast(t("community.post_deleted"), "info");
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
  if (mins < 1) return t("time.just_now");
  if (mins < 60) return t("time.minutes_ago", { n: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("time.hours_ago", { n: hours });
  const days = Math.floor(hours / 24);
  if (days < 30) return t("time.days_ago", { n: days });
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

// ── Lost & Found Integration ─────────────────────────────────────────────────

const LF_ITEM_TYPES = [
  { value: null, labelKey: "lostfound.type_all" },
  { value: "lost", labelKey: "lostfound.type_lost" },
  { value: "found", labelKey: "lostfound.type_found" },
];

const LF_STATUS_OPTIONS = [
  { value: null, labelKey: "lostfound.status_all" },
  { value: "active", labelKey: "lostfound.status_active" },
  { value: "resolved", labelKey: "lostfound.status_resolved" },
];

function _LostFoundFilterBar() {
  const bar = document.createElement("div");
  bar.className = "lf-filter-bar";

  const typeWrap = document.createElement("div");
  typeWrap.className = "lf-type-tabs";

  LF_ITEM_TYPES.forEach((itemType) => {
    const btn = document.createElement("button");
    btn.className = "lf-type-tab" + (_state.lfItemType === itemType.value ? " active" : "");
    btn.textContent = t(itemType.labelKey);
    if (itemType.value === "lost") btn.classList.add("lost");
    if (itemType.value === "found") btn.classList.add("found");
    btn.addEventListener("click", () => {
      _state.lfItemType = itemType.value;
      _state.page = 1;
      _loadLostFound();
      typeWrap.querySelectorAll(".lf-type-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
    typeWrap.appendChild(btn);
  });

  bar.appendChild(typeWrap);

  const statusSelect = document.createElement("select");
  statusSelect.className = "lf-status-select";
  LF_STATUS_OPTIONS.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.value || "";
    opt.textContent = t(s.labelKey);
    if (_state.lfStatusFilter === s.value) opt.selected = true;
    statusSelect.appendChild(opt);
  });
  statusSelect.addEventListener("change", () => {
    _state.lfStatusFilter = statusSelect.value || null;
    _state.page = 1;
    _loadLostFound();
  });
  bar.appendChild(statusSelect);

  return bar;
}

async function _loadLostFound() {
  const feed = document.getElementById("posts-feed");
  if (!feed) return;

  _state.loading = true;
  feed.innerHTML = skeletonCard(3);

  try {
    const params = new URLSearchParams({
      page: _state.page,
      page_size: _state.pageSize,
    });
    if (_state.lfItemType) params.set("item_type", _state.lfItemType);
    if (_state.lfStatusFilter) params.set("status", _state.lfStatusFilter);

    const data = await api.get(`/lostfound?${params}`);
    feed.innerHTML = "";

    if (data.items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "text-center py-16";
      const icon = document.createElement("div");
      icon.className = "text-5xl mb-3 opacity-30";
      icon.textContent = "\u{1F50D}";
      const p = document.createElement("p");
      p.className = "text-gray-400 text-lg";
      p.textContent = t("lostfound.empty_title");
      empty.appendChild(icon);
      empty.appendChild(p);
      feed.appendChild(empty);
    } else {
      data.items.forEach((item) => feed.appendChild(_LostFoundCard(item)));
    }

    if (data.has_next) {
      const moreBtn = document.createElement("button");
      moreBtn.className = "w-full py-2 text-sm text-blue-500 hover:text-blue-700 transition-colors";
      moreBtn.textContent = t("lostfound.load_more");
      moreBtn.addEventListener("click", () => {
        _state.page++;
        _loadLostFound();
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

function _LostFoundCard(item) {
  const card = document.createElement("div");
  card.className = "lf-card card-hover";

  // Image (if present)
  if (item.image_url) {
    const img = document.createElement("img");
    img.src = item.image_url;
    img.srcset = responsiveSrcset(item.image_url);
    img.alt = item.title;
    img.className = "lf-card-img";
    img.loading = "lazy";
    card.appendChild(img);
  }

  const typeBadge = document.createElement("span");
  typeBadge.className = "lf-type-badge " + item.item_type;
  typeBadge.textContent = item.item_type === "lost" ? t("lostfound.lost_label") : t("lostfound.found_label");
  card.appendChild(typeBadge);

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

  if (isLoggedIn() && _isLfItemOwner(item.author_id)) {
    const actions = document.createElement("div");
    actions.className = "lf-card-actions";

    if (item.status === "active") {
      const resolveBtn = document.createElement("button");
      resolveBtn.className = "lf-action-btn resolve";
      resolveBtn.textContent = t("lostfound.resolved_label");
      resolveBtn.addEventListener("click", () => _resolveLfItem(item.id));
      actions.appendChild(resolveBtn);
    }

    const delBtn = document.createElement("button");
    delBtn.className = "lf-action-btn delete";
    delBtn.textContent = t("community.delete");
    delBtn.addEventListener("click", () => _deleteLfItem(item.id));
    actions.appendChild(delBtn);

    card.appendChild(actions);
  }

  return card;
}

function _isLfItemOwner(authorId) {
  try {
    const token = localStorage.getItem("token");
    if (!token) return false;
    const payload = JSON.parse(atob(token.split(".")[1]));
    return parseInt(payload.sub) === authorId;
  } catch {
    return false;
  }
}

async function _resolveLfItem(itemId) {
  if (!confirm(t("lostfound.confirm_resolve"))) return;
  try {
    await api.put(`/lostfound/${itemId}`, { status: "resolved" });
    showToast(t("lostfound.marked_resolved"), "success");
    _loadLostFound();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function _deleteLfItem(itemId) {
  if (!confirm(t("lostfound.confirm_delete"))) return;
  try {
    await api.del(`/lostfound/${itemId}`);
    showToast(t("lostfound.report_deleted"), "info");
    _loadLostFound();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function _showLostFoundModal() {
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
  titleInput.setAttribute("aria-label", t("lostfound.field_title"));

  const locationInput = document.createElement("input");
  locationInput.type = "text";
  locationInput.name = "location";
  locationInput.placeholder = t("lostfound.field_location");
  locationInput.maxLength = 200;
  locationInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400";
  locationInput.setAttribute("aria-label", t("lostfound.field_location"));

  const descInput = document.createElement("textarea");
  descInput.name = "description";
  descInput.placeholder = t("lostfound.field_desc");
  descInput.required = true;
  descInput.maxLength = 2000;
  descInput.rows = 4;
  descInput.className = "w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-blue-400 resize-none";
  descInput.setAttribute("aria-label", t("lostfound.field_desc"));

  // Image upload component
  const imageUploader = createImageUploader({ module: "lostfound" });

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
  form.appendChild(imageUploader.el);
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
        image_url: imageUploader.getUrl(),
      });
      showToast(t("lostfound.report_submitted"), "success");
      track("lost_found_reported", { item_type: fd.get("item_type") });
      closeModal();
      _loadLostFound();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}
