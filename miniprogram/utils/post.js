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

module.exports = { normalizePost, compactNumber, resolveUrl };
