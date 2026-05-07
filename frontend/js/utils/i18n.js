import * as storage from "./storage.js";

const STORAGE_KEY = "lang";

const SUPPORTED = ["en", "zh-CN", "zh-TW"];
const DEFAULT_LANG = "en";

let _currentLang = DEFAULT_LANG;

// ── Translations ─────────────────────────────────────────────────────────────

const translations = {
  en: {
    // Nav
    "nav.home": "Home",
    "nav.community": "Community",
    "nav.planner": "Planner",
    "nav.news": "News",
    "nav.lostfound": "Lost & Found",
    "nav.profile": "Profile",
    "nav.messages": "Messages",
    "nav.login": "Login",
    "nav.logout": "Logout",

    // Community
    "community.title": "Community",
    "community.new_post": "+ New Post",
    "community.sort_newest": "Newest",
    "community.sort_hot": "Hot",
    "community.cat_all": "All",
    "community.cat_discussion": "Discussion",
    "community.cat_question": "Q&A",
    "community.cat_sharing": "Sharing",
    "community.cat_news": "Campus News",
    "community.cat_other": "Other",
    "community.empty_title": "No posts yet",
    "community.empty_desc": "Be the first to share something!",
    "community.load_more": "Load more...",
    "community.read_more": "Read more",
    "community.edit": "Edit",
    "community.delete": "Delete",
    "community.like": "Like",
    "community.comment": "Comment",
    "community.write_comment": "Write a comment...",
    "community.send": "Send",
    "community.no_comments": "No comments yet",
    "community.modal_new": "New Post",
    "community.modal_edit": "Edit Post",
    "community.publish": "Publish Post",
    "community.update": "Update Post",
    "community.field_title": "Title",
    "community.field_category": "Select category",
    "community.field_content": "What's on your mind?",
    "community.confirm_delete": "Delete this post?",
    "community.post_published": "Post published!",
    "community.post_updated": "Post updated!",
    "community.post_deleted": "Post deleted",
    "community.comment_posted": "Comment posted!",

    // Auth
    "auth.welcome": "Welcome Back",
    "auth.create": "Create Account",
    "auth.login": "Login",
    "auth.register": "Register",
    "auth.username": "Username",
    "auth.password": "Password (min 6 chars)",
    "auth.nickname": "Nickname",
    "auth.student_id": "Student ID (optional)",
    "auth.logged_in": "Logged in!",
    "auth.registered": "Account created! Please login.",
    "auth.logged_out": "Logged out",

    // Misc
    "time.just_now": "just now",
    "time.minutes_ago": "{n}m ago",
    "time.hours_ago": "{n}h ago",
    "time.days_ago": "{n}d ago",
  },

  "zh-CN": {
    "nav.home": "首页",
    "nav.community": "社区",
    "nav.planner": "选课规划",
    "nav.news": "新闻",
    "nav.lostfound": "失物招领",
    "nav.profile": "个人中心",
    "nav.messages": "私信",
    "nav.login": "登录",
    "nav.logout": "退出",

    "community.title": "社区",
    "community.new_post": "+ 发帖",
    "community.sort_newest": "最新",
    "community.sort_hot": "热门",
    "community.cat_all": "全部",
    "community.cat_discussion": "讨论",
    "community.cat_question": "问答",
    "community.cat_sharing": "分享",
    "community.cat_news": "校园新闻",
    "community.cat_other": "其他",
    "community.empty_title": "暂无帖子",
    "community.empty_desc": "成为第一个分享的人吧！",
    "community.load_more": "加载更多...",
    "community.read_more": "展开",
    "community.edit": "编辑",
    "community.delete": "删除",
    "community.like": "点赞",
    "community.comment": "评论",
    "community.write_comment": "写评论...",
    "community.send": "发送",
    "community.no_comments": "暂无评论",
    "community.modal_new": "发帖",
    "community.modal_edit": "编辑帖子",
    "community.publish": "发布",
    "community.update": "更新",
    "community.field_title": "标题",
    "community.field_category": "选择分类",
    "community.field_content": "你在想什么？",
    "community.confirm_delete": "确定删除这篇帖子？",
    "community.post_published": "发布成功！",
    "community.post_updated": "更新成功！",
    "community.post_deleted": "已删除",
    "community.comment_posted": "评论成功！",

    "auth.welcome": "欢迎回来",
    "auth.create": "创建账号",
    "auth.login": "登录",
    "auth.register": "注册",
    "auth.username": "用户名",
    "auth.password": "密码（至少6位）",
    "auth.nickname": "昵称",
    "auth.student_id": "学号（选填）",
    "auth.logged_in": "登录成功！",
    "auth.registered": "注册成功！请登录。",
    "auth.logged_out": "已退出",

    "time.just_now": "刚刚",
    "time.minutes_ago": "{n}分钟前",
    "time.hours_ago": "{n}小时前",
    "time.days_ago": "{n}天前",
  },

  "zh-TW": {
    "nav.home": "首頁",
    "nav.community": "社群",
    "nav.planner": "選課規劃",
    "nav.news": "新聞",
    "nav.lostfound": "失物招領",
    "nav.profile": "個人中心",
    "nav.messages": "私訊",
    "nav.login": "登入",
    "nav.logout": "登出",

    "community.title": "社群",
    "community.new_post": "+ 發文",
    "community.sort_newest": "最新",
    "community.sort_hot": "熱門",
    "community.cat_all": "全部",
    "community.cat_discussion": "討論",
    "community.cat_question": "問答",
    "community.cat_sharing": "分享",
    "community.cat_news": "校園新聞",
    "community.cat_other": "其他",
    "community.empty_title": "暫無貼文",
    "community.empty_desc": "成為第一個分享的人吧！",
    "community.load_more": "載入更多...",
    "community.read_more": "展開",
    "community.edit": "編輯",
    "community.delete": "刪除",
    "community.like": "按讚",
    "community.comment": "留言",
    "community.write_comment": "寫留言...",
    "community.send": "傳送",
    "community.no_comments": "暫無留言",
    "community.modal_new": "發文",
    "community.modal_edit": "編輯貼文",
    "community.publish": "發佈",
    "community.update": "更新",
    "community.field_title": "標題",
    "community.field_category": "選擇分類",
    "community.field_content": "你在想什麼？",
    "community.confirm_delete": "確定刪除這篇貼文？",
    "community.post_published": "發佈成功！",
    "community.post_updated": "更新成功！",
    "community.post_deleted": "已刪除",
    "community.comment_posted": "留言成功！",

    "auth.welcome": "歡迎回來",
    "auth.create": "建立帳號",
    "auth.login": "登入",
    "auth.register": "註冊",
    "auth.username": "使用者名稱",
    "auth.password": "密碼（至少6位）",
    "auth.nickname": "暱稱",
    "auth.student_id": "學號（選填）",
    "auth.logged_in": "登入成功！",
    "auth.registered": "註冊成功！請登入。",
    "auth.logged_out": "已登出",

    "time.just_now": "剛剛",
    "time.minutes_ago": "{n}分鐘前",
    "time.hours_ago": "{n}小時前",
    "time.days_ago": "{n}天前",
  },
};

// ── Public API ───────────────────────────────────────────────────────────────

export function initLang() {
  const saved = storage.get(STORAGE_KEY);
  if (saved && SUPPORTED.includes(saved)) {
    _currentLang = saved;
  } else {
    // Auto-detect from browser
    const browser = navigator.language;
    if (browser.startsWith("zh")) {
      _currentLang = browser.includes("TW") || browser.includes("HK") || browser.includes("Hant")
        ? "zh-TW"
        : "zh-CN";
    }
  }
  _applyToDOM();
}

export function t(key, params = {}) {
  const dict = translations[_currentLang] || translations[DEFAULT_LANG];
  let text = dict[key] || translations[DEFAULT_LANG][key] || key;
  for (const [k, v] of Object.entries(params)) {
    text = text.replace(`{${k}}`, v);
  }
  return text;
}

export function currentLang() {
  return _currentLang;
}

export function setLang(lang) {
  if (!SUPPORTED.includes(lang)) return;
  _currentLang = lang;
  storage.set(STORAGE_KEY, lang);
  _applyToDOM();
}

export function supportedLangs() {
  return SUPPORTED.map((code) => ({
    code,
    label: { en: "English", "zh-CN": "简体中文", "zh-TW": "繁體中文" }[code],
  }));
}

// ── DOM auto-translate via data-i18n ─────────────────────────────────────────

function _applyToDOM() {
  document.documentElement.lang = _currentLang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const text = t(key);
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      el.placeholder = text;
    } else {
      el.textContent = text;
    }
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
}
