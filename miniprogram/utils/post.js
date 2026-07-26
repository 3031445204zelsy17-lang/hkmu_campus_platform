const { API_ORIGIN } = require("./config");
const { formatDate, getInitial } = require("./format");

// Resolve a possibly-relative media URL to an absolute one.
// Absolute URLs (e.g. Supabase Storage) pass through; "/foo" gets the API origin prepended.
function resolveUrl(value) {
  if (!value) {
    return "";
  }

  return value.startsWith("/") ? `${API_ORIGIN}${value}` : value;
}

function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1000) {
    return `${(number / 1000).toFixed(1)}k`;
  }
  return String(number);
}

// Shared post normalizer for home + community feeds.
//   item       raw API post
//   text       i18n bundle (getTexts("home"|"community"))
//   opts.rawIndex   community passes the list index (home omits it)
//   opts.sectionKey community passes inferCommunityBoardKey(item) (home omits it)
function normalizePost(item, text, opts) {
  const options = opts || {};
  const rawIndex = options.rawIndex !== undefined ? options.rawIndex : -1;
  const sectionKey = options.sectionKey;
  const authorName = item.author_nickname || text.defaultAuthor;
  const content = String(item.content || "").trim();

  const out = {
    authorAvatar: resolveUrl(item.author_avatar),
    authorId: item.author_id,
    authorInitial: getInitial(authorName),
    authorName,
    category: item.category || text.defaultCategory,
    commentsLabel: compactNumber(item.comments_count),
    content,
    createdAtLabel: formatDate(item.created_at) || text.justNow,
    handle: `@campus${item.author_id || item.id}`,
    id: item.id,
    imageUrl: resolveUrl(item.image_url),
    isLiked: !!item.is_liked,
    likeClass: item.is_liked ? "post-action like-action is-liked" : "post-action like-action",
    likeIcon: item.is_liked ? "♥" : "♡",
    likeIconClass: item.is_liked ? "social-glyph like-glyph filled" : "social-glyph like-glyph",
    likeLabel: compactNumber(item.likes_count),
    title: item.title,
    topicClass: item.likes_count > 0 ? "topic-pill hot" : "topic-pill",
  };

  if (rawIndex !== -1) {
    out.rawIndex = rawIndex;
  }
  if (sectionKey !== undefined) {
    out.sectionKey = sectionKey;
  }
  return out;
}

// ── Feed revision(替代旧 postsNeedRefresh 布尔)──────────────────────────
// 单调递增计数器,任何写操作(发帖/删帖/点赞/评论)成功后 bump。
// 列表页(home/community)各自记 _lastFeedRevision,onShow 时与全局比较——
// 「比较不清零」→ 一个 tab 消费不会吞掉另一个 tab 的刷新信号(根因:旧布尔先到先清零)。
function getPostsRevision() {
  const app = getApp();
  return (app && app.globalData && app.globalData.postsRevision) || 0;
}

// payload 预留(未来 event bus 单条 surgical 更新用)。返回新 revision。
// 调用方:列表页(home/community)点赞 bump 后应把「自己」的 _lastFeedRevision
// 也置为返回值——自己已是新态,无需下次 onShow 无谓自刷;其他 tab 则会被触发。
function bumpPostsRevision(payload) {
  const app = getApp();
  if (!app || !app.globalData) return 0;
  const next = (app.globalData.postsRevision || 0) + 1;
  app.globalData.postsRevision = next;
  return next;
}

// 分页合并按 id 去重:已有则更新(新版本覆盖、保留原位置),没有则追加。
// 修 hot 排序位移 / 分页不稳 / 跨 tab 增量回写导致的重复帖。
function mergePostsById(existing, incoming) {
  const merged = (existing || []).slice();
  const indexById = new Map();
  for (let i = 0; i < merged.length; i++) {
    if (merged[i] && merged[i].id != null) indexById.set(merged[i].id, i);
  }
  (incoming || []).forEach((item) => {
    if (!item || item.id == null) return;
    const idx = indexById.get(item.id);
    if (idx !== undefined) {
      merged[idx] = item; // 更新已有(保留原位置)
    } else {
      indexById.set(item.id, merged.length);
      merged.push(item); // 追加新帖
    }
  });
  return merged;
}

module.exports = {
  normalizePost,
  compactNumber,
  resolveUrl,
  getPostsRevision,
  bumpPostsRevision,
  mergePostsById,
};
