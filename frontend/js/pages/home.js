import { api, isLoggedIn } from "../api.js";
import { showToast } from "../components/toast.js";

const feedState = {
  loading: false,
  query: "",
  sort: "newest",
};

function el(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function icon(name, className = "w-4 h-4") {
  const node = document.createElement("i");
  node.setAttribute("data-lucide", name);
  node.className = className;
  return node;
}

function initials(name) {
  return String(name || "HKMU").trim().slice(0, 1).toUpperCase() || "H";
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000) return `${(number / 1000).toFixed(1)}k`;
  return String(number);
}

function postAuthor(post) {
  return post.author_nickname || "HKMU 同学";
}

function postTime(post) {
  if (!post.created_at) return "刚刚";
  const then = new Date(post.created_at).getTime();
  if (Number.isNaN(then)) return String(post.created_at).replace("T", " ").slice(0, 16);
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`;
  return new Date(post.created_at).toLocaleDateString("zh-CN");
}

function makeAvatar(name, avatarUrl = "") {
  const avatar = el("div", "home-avatar");
  if (avatarUrl) {
    const image = document.createElement("img");
    image.src = avatarUrl;
    image.alt = name;
    avatar.appendChild(image);
  } else {
    avatar.textContent = initials(name);
  }
  return avatar;
}

function makeFeedCard(post, onRefresh) {
  const card = el("article", "home-feed-card");
  const head = el("div", "home-feed-head");
  const author = postAuthor(post);

  head.appendChild(makeAvatar(author, post.author_avatar || ""));

  const main = el("div", "home-feed-main");
  const metaRow = el("div", "home-feed-meta-row");
  const authorBlock = el("div");
  authorBlock.appendChild(el("div", "home-feed-author", author));
  authorBlock.appendChild(el("div", "home-feed-meta", `@campus${post.author_id || post.id} · ${postTime(post)}`));
  metaRow.appendChild(authorBlock);
  metaRow.appendChild(el("span", "home-topic-pill", post.category || "校园"));
  main.appendChild(metaRow);

  main.appendChild(el("h3", "home-feed-title", post.title || "无标题动态"));
  main.appendChild(el("p", "home-feed-copy", post.content || ""));

  const actions = el("div", "home-feed-actions");
  const likeButton = el("button", post.is_liked ? "home-action active" : "home-action");
  likeButton.appendChild(icon("heart", "w-4 h-4"));
  likeButton.appendChild(el("span", "", `${compactNumber(post.likes_count)} 赞`));
  likeButton.addEventListener("click", async () => {
    if (!isLoggedIn()) {
      showToast("登录后可以点赞", "info");
      return;
    }
    try {
      await api.post(`/posts/${post.id}/like`);
      await onRefresh();
    } catch (err) {
      showToast(err.message || "点赞失败", "error");
    }
  });
  actions.appendChild(likeButton);

  const commentButton = el("button", "home-action");
  commentButton.appendChild(icon("message-circle", "w-4 h-4"));
  commentButton.appendChild(el("span", "", `${compactNumber(post.comments_count)} 评论`));
  commentButton.addEventListener("click", () => {
    location.hash = "#/community";
  });
  actions.appendChild(commentButton);

  const shareButton = el("button", "home-action");
  shareButton.appendChild(icon("repeat-2", "w-4 h-4"));
  shareButton.appendChild(el("span", "", "转发想法"));
  shareButton.addEventListener("click", () => {
    location.hash = "#/community";
  });
  actions.appendChild(shareButton);

  main.appendChild(actions);
  head.appendChild(main);
  card.appendChild(head);
  return card;
}

function makeEmptyState() {
  const empty = el("div", "home-empty");
  empty.appendChild(icon("sparkles", "w-7 h-7"));
  empty.appendChild(el("h3", "", "动态流还在等第一条内容"));
  empty.appendChild(el("p", "", "去社区发帖后，这里会像手机博客 App 一样实时展示。"));
  const button = el("button", "home-primary-btn", "去发布");
  button.addEventListener("click", () => {
    location.hash = "#/community";
  });
  empty.appendChild(button);
  return empty;
}

async function loadFeed(feedList, refreshButton) {
  if (feedState.loading) return;
  feedState.loading = true;
  feedList.replaceChildren(el("div", "home-loading", "正在同步校园动态..."));
  if (refreshButton) refreshButton.disabled = true;

  const query = [
    "page=1",
    "page_size=8",
    `sort=${feedState.sort}`,
  ];
  if (feedState.query) {
    query.push(`search=${encodeURIComponent(feedState.query)}`);
  }

  try {
    const data = await api.get(`/posts?${query.join("&")}`);
    feedList.replaceChildren();
    const posts = data.items || [];
    if (!posts.length) {
      feedList.appendChild(makeEmptyState());
      return;
    }
    posts.forEach((post) => {
      feedList.appendChild(makeFeedCard(post, () => loadFeed(feedList, refreshButton)));
    });
  } catch (err) {
    feedList.replaceChildren();
    const failed = makeEmptyState();
    failed.querySelector("h3").textContent = "动态加载失败";
    failed.querySelector("p").textContent = err.message || "稍后再试一次。";
    feedList.appendChild(failed);
    showToast(err.message || "动态加载失败", "error");
  } finally {
    feedState.loading = false;
    if (refreshButton) refreshButton.disabled = false;
    if (window.lucide) window.lucide.createIcons();
  }
}

function makeSegment(feedList, refreshButton) {
  const segment = el("div", "home-segment");
  [
    ["newest", "最新"],
    ["hot", "热门"],
  ].forEach(([value, label]) => {
    const button = el("button", value === feedState.sort ? "active" : "", label);
    button.addEventListener("click", () => {
      feedState.sort = value;
      [...segment.children].forEach((child) => child.classList.remove("active"));
      button.classList.add("active");
      loadFeed(feedList, refreshButton);
    });
    segment.appendChild(button);
  });
  return segment;
}

function makeSearch(feedList, refreshButton) {
  const search = el("div", "home-search");
  search.appendChild(icon("hash", "w-4 h-4"));
  const input = document.createElement("input");
  input.placeholder = "搜索动态、课程、活动";
  input.value = feedState.query;
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    feedState.query = input.value.trim();
    loadFeed(feedList, refreshButton);
  });
  search.appendChild(input);
  const button = el("button", "", "搜索");
  button.addEventListener("click", () => {
    feedState.query = input.value.trim();
    loadFeed(feedList, refreshButton);
  });
  search.appendChild(button);
  return search;
}

function makePhoneShell(feedList, refreshButton) {
  const phone = el("section", "home-phone");
  const screen = el("div", "home-phone-screen");

  const top = el("div", "home-phone-top");
  const titleWrap = el("div");
  titleWrap.appendChild(el("span", "home-kicker", "HKMU CAMPUS"));
  titleWrap.appendChild(el("h1", "", "动态"));
  top.appendChild(titleWrap);
  const profile = el("button", "home-profile-dot", "H");
  profile.addEventListener("click", () => {
    location.hash = "#/profile";
  });
  top.appendChild(profile);
  screen.appendChild(top);

  const compose = el("button", "home-compose");
  compose.appendChild(makeAvatar("H"));
  compose.appendChild(el("span", "", "分享校园里的新鲜事..."));
  compose.appendChild(el("strong", "", "发布"));
  compose.addEventListener("click", () => {
    location.hash = "#/community";
  });
  screen.appendChild(compose);

  screen.appendChild(makeSearch(feedList, refreshButton));
  screen.appendChild(makeSegment(feedList, refreshButton));
  screen.appendChild(feedList);
  phone.appendChild(screen);
  return phone;
}

function makeSidePanel(feedList, refreshButton) {
  const panel = el("aside", "home-side-panel");

  const intro = el("section", "home-hero-card");
  intro.appendChild(el("span", "home-kicker", "MOBILE FIRST REDESIGN"));
  intro.appendChild(el("h2", "", "像刷 X / 博客一样使用校园平台"));
  intro.appendChild(el("p", "", "首页不再是功能入口墙，而是直接显示校园动态、热门讨论和发布入口。"));
  const heroActions = el("div", "home-hero-actions");
  const community = el("button", "home-primary-btn", "进入社区");
  community.addEventListener("click", () => {
    location.hash = "#/community";
  });
  const planner = el("button", "home-secondary-btn", "课程规划");
  planner.addEventListener("click", () => {
    location.hash = "#/planner";
  });
  heroActions.appendChild(community);
  heroActions.appendChild(planner);
  intro.appendChild(heroActions);
  panel.appendChild(intro);

  const quick = el("section", "home-quick-card");
  quick.appendChild(el("h3", "", "快捷入口"));
  [
    ["message-circle", "社区动态", "发帖、点赞、评论", "#/community"],
    ["newspaper", "校园发现", "公告与新闻", "#/news"],
    ["search-check", "失物互助", "找物品、看招领", "#/lostfound"],
    ["book-open", "课程规划", "查看课程进度", "#/planner"],
  ].forEach(([iconName, title, desc, route]) => {
    const item = el("button", "home-quick-item");
    item.appendChild(icon(iconName, "w-5 h-5"));
    const copy = el("div");
    copy.appendChild(el("strong", "", title));
    copy.appendChild(el("span", "", desc));
    item.appendChild(copy);
    item.addEventListener("click", () => {
      location.hash = route;
    });
    quick.appendChild(item);
  });
  panel.appendChild(quick);

  const refresh = el("section", "home-refresh-card");
  refresh.appendChild(el("h3", "", "实时连接"));
  refresh.appendChild(el("p", "", "当前页面直接读取 `/api/v1/posts`，和社区、小程序共用同一个数据库。"));
  refreshButton.appendChild(icon("refresh-cw", "w-4 h-4"));
  refreshButton.appendChild(el("span", "", "刷新动态"));
  refreshButton.addEventListener("click", () => loadFeed(feedList, refreshButton));
  refresh.appendChild(refreshButton);
  panel.appendChild(refresh);

  return panel;
}

export async function renderHome() {
  const app = document.getElementById("app-content");
  app.setAttribute("data-page", "home");
  app.innerHTML = "";

  const stage = el("div", "home-app-stage");
  const feedList = el("div", "home-feed-list");
  const refreshButton = el("button", "home-refresh-btn");

  stage.appendChild(makePhoneShell(feedList, refreshButton));
  stage.appendChild(makeSidePanel(feedList, refreshButton));
  app.appendChild(stage);

  await loadFeed(feedList, refreshButton);
  if (window.lucide) window.lucide.createIcons();
}
