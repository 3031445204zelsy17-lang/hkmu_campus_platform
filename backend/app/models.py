import re
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional


# --- Auth ---

class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=30)
    student_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserLogin(BaseModel):
    # max_length bounds the lockout-dict key (Codex [17][18]) — a giant
    # username would otherwise inflate the in-memory failure tracker.
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class GoogleLogin(BaseModel):
    id_token: str


class EmailRegister(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', max_length=254)
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=30)
    student_id: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        return v


class EmailLogin(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class ForgotPassword(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$', max_length=254)


class ResetPassword(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r'[a-z]', v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r'\d', v):
            raise ValueError("Password must contain at least one digit")
        return v


class VerifyEmail(BaseModel):
    token: str = Field(min_length=1)


class Token(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


# --- Users ---

class UserOut(BaseModel):
    id: int
    username: str
    nickname: str
    student_id: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: str = ""
    identity: str = "student"
    created_at: Optional[str] = None
    email: Optional[str] = None
    oauth_provider: Optional[str] = None
    programme_code: Optional[str] = None
    entry_term: Optional[str] = None
    # 批次 5 入学点系列轴:1/2/3 = Year N Entry(advice sheet 页眉口径);
    # None = 未采集。drives graduation-status 的系列化 placements。
    entry_level: Optional[int] = None
    hkmu_verified: bool = False
    # invite_code intentionally absent — only exposed via /users/me/invite-code (self).
    # Returning another user's invite_code enabled a force-friend vector.


class UserPublicOut(BaseModel):
    """Public-safe view of ANOTHER user (no email / oauth / student_id /
    programme_code / hkmu_verified / invite_code). Used for /users/{user_id}."""
    id: int
    username: str
    nickname: str
    avatar_url: Optional[str] = None
    bio: str = ""
    identity: str = "student"
    created_at: Optional[str] = None


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=30)
    bio: Optional[str] = Field(None, max_length=300)
    avatar_url: Optional[str] = None
    programme_code: Optional[str] = None
    entry_term: Optional[str] = None
    # 批次 5:入学点 1/2/3(Year N Entry);合法值校验在 router(不在 pydantic
    # 层做,保证 4xx 带上业务说明文案)。
    entry_level: Optional[int] = None


# --- Posts ---

class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    category: str = Field(min_length=1, max_length=30)
    parent_post_id: Optional[int] = None
    is_anonymous: bool = False
    image_url: Optional[str] = None


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    category: Optional[str] = Field(None, min_length=1, max_length=30)


class QuotedPostOut(BaseModel):
    id: int
    author_nickname: Optional[str] = None
    title: str
    content_preview: str
    created_at: Optional[str] = None


class PostOut(BaseModel):
    id: int
    author_id: Optional[int]
    title: str
    content: str
    category: str
    likes_count: int = 0
    comments_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author_nickname: Optional[str] = None
    author_avatar: Optional[str] = None
    is_liked: bool = False
    parent_post_id: Optional[int] = None
    quoted_post: Optional[QuotedPostOut] = None
    is_anonymous: bool = False
    image_url: Optional[str] = None


# --- Comments ---

class CommentCreate(BaseModel):
    # content becomes optional when an image is attached (image-only comment);
    # the posts router enforces "content or image_url, at least one"
    content: Optional[str] = Field(None, max_length=2000)
    parent_id: Optional[int] = None  # reply target; always hoisted to a top-level comment
    image_url: Optional[str] = None  # must reference our own uploads bucket (moderation path)


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_id: int
    content: str = ""
    likes_count: int = 0
    parent_id: Optional[int] = None
    reply_to_nickname: Optional[str] = None  # "回复 @xxx" display hint for replies
    image_url: Optional[str] = None
    # two-layer tree: top-level comments carry their replies, replies carry []
    replies: Optional[List["CommentOut"]] = None
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None
    author_avatar: Optional[str] = None


CommentOut.model_rebuild()  # resolve the self-referential `replies` forward ref


# --- Courses ---

class GECourseInfoOut(BaseModel):
    """官方 GE 目录信息(GE_catalog_3cru.pdf 富化),挂在 CourseOut.ge 上。

    school 是池内缩写(A&SS 等),前端 i18n 映射双语全称;school_name 是目录
    逐课打印的学院名原文——官方文件内课码字母与学院栏偶有出入,展示以目录为准。"""
    field: str
    level: int = 0            # 官方「程度」:1000 | 2000
    moi: str = ""             # english | chinese | bilingual
    terms: list[str] = []
    excluded: list[str] = []
    description: str = ""
    school: str = ""
    school_name: str = ""


class CourseOut(BaseModel):
    id: str
    code: str
    name: str
    credits: int
    category: str
    year: int
    semester: str
    prerequisites: str = "[]"
    description: Optional[str] = None
    ge: Optional[GECourseInfoOut] = None


class UserCourseUpdate(BaseModel):
    course_id: str
    status: str = Field(pattern=r"^(not_started|in_progress|completed)$")


class UserCourseOut(BaseModel):
    course_id: str
    status: str
    updated_at: Optional[str] = None


# 避坑标签白名单 — course_review_tags.tag 只存这些 key，前端 i18n 映射三语展示。
REVIEW_TAGS = (
    "generous_grading",   # 给分好
    "tough_grading",      # 给分严
    "heavy_workload",     # 作业多
    "light_workload",     # 作业少
    "high_gain",          # 收获大
    "open_book",          # 开卷考
    "group_project",      # 小组项目多
    "attendance_strict",  # 点名严
)


class CourseReviewCreate(BaseModel):
    # 老 5 星兼容保留(T17);三维时代至少传一维,rating 可空
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    rating_teaching: Optional[int] = Field(default=None, ge=1, le=5)
    rating_workload: Optional[int] = Field(default=None, ge=1, le=5)
    rating_gain: Optional[int] = Field(default=None, ge=1, le=5)
    content: str = Field(min_length=1, max_length=2000)
    tags: List[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def tags_whitelist(cls, v):
        unknown = [t for t in v if t not in REVIEW_TAGS]
        if unknown:
            raise ValueError(f"unknown review tags: {unknown}")
        return list(dict.fromkeys(v))  # 去重保序

    @model_validator(mode="after")
    def at_least_one_rating(self):
        # 三维与老 5 星至少传一项,全空直接 422
        if not any(
            (self.rating, self.rating_teaching, self.rating_workload, self.rating_gain)
        ):
            raise ValueError("at least one rating is required")
        return self


class CourseReviewOut(BaseModel):
    id: int
    course_id: str
    author_id: int
    rating: Optional[int] = None
    rating_teaching: Optional[int] = None
    rating_workload: Optional[int] = None
    rating_gain: Optional[int] = None
    content: str
    helpful_count: int = 0
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class CourseTagAggregate(BaseModel):
    tag: str
    count: int
    voted: bool = False  # 当前查看者是否已投(未登录恒 False)


class CourseReviewTagsOut(BaseModel):
    course_id: str
    total_votes: int = 0
    tags: List[CourseTagAggregate] = Field(default_factory=list)


class CourseReviewStatsOut(BaseModel):
    """三维均分(T15 course-detail 头部);无评分的维度为 None。"""
    course_id: str
    review_count: int = 0
    rating_avg: Optional[float] = None  # 老 5 星均分(兼容展示)
    teaching_avg: Optional[float] = None
    workload_avg: Optional[float] = None
    gain_avg: Optional[float] = None


# --- News ---

class NewsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    source_url: str
    lang: Optional[str] = None  # defaults to zh-hant server-side; trilingual hook


class NewsOut(BaseModel):
    id: int
    author_id: Optional[int] = None
    title: str
    summary: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    source_url: str
    published_at: Optional[str] = None
    comments_count: int = 0
    lang: Optional[str] = None


class NewsCommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class NewsCommentOut(BaseModel):
    id: int
    news_id: int
    author_id: int
    content: str
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None
    author_avatar: Optional[str] = None


# --- Lost & Found ---

class LostFoundCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    item_type: str = Field(pattern=r"^(lost|found)$")
    category: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None


class LostFoundUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Optional[str] = Field(None, pattern=r"^(active|resolved)$")
    item_type: Optional[str] = Field(None, pattern=r"^(lost|found)$")
    category: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None


class LostFoundOut(BaseModel):
    id: int
    author_id: int
    title: str
    description: str
    item_type: str
    category: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    status: str = "active"
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None


# --- Messages ---

class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class MessageOut(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    is_read: bool = False
    created_at: Optional[str] = None


class ConversationOut(BaseModel):
    partner_id: int
    partner_nickname: str
    partner_avatar: Optional[str] = None
    last_message: Optional[str] = None
    last_time: Optional[str] = None
    unread_count: int = 0


# --- Pagination ---

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    has_next: bool


# --- Push Notifications ---

class PushSubscriptionIn(BaseModel):
    subscription: dict


# --- Social ---

class BindEmail(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class InviteCodeOut(BaseModel):
    invite_code: str
    share_path: str


class FriendshipOut(BaseModel):
    id: int
    friend: UserPublicOut  # public-safe — no email/student_id/programme (leak fix [12])
    source: str
    created_at: Optional[str] = None


class SuggestOut(UserPublicOut):
    reason: Optional[str] = None


class InviteAccept(BaseModel):
    invite_code: str = Field(min_length=1, max_length=64)


# --- Feedback ---

class FeedbackCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=2000)
    contact: str | None = Field(default=None, max_length=200)


class FeedbackOut(BaseModel):
    id: int
    rating: int
    content: str
    contact: Optional[str] = None
    created_at: Optional[str] = None


# --- Reports (举报) ---
# UGC report of illegal/abusive content for admin review. target_type is an
# extensible enum (MVP frontend wires 'post' only); reason_code is a fixed set
# mirrored in miniprogram i18n. Report detail is admin-eyes-only (never shown to
# other users), so it is NOT routed through WeChat msg_sec_check — see
# routers/reports.py for the rationale.

class ReportCreate(BaseModel):
    target_type: str = Field(pattern=r"^(post|comment|lostfound|news_comment|user)$")
    target_id: int = Field(ge=1)
    reason_code: str = Field(pattern=r"^(spam|abuse|porn|illegal|other)$")
    detail: Optional[str] = Field(default=None, max_length=500)


class ReportOut(BaseModel):
    id: int
    target_type: str
    target_id: int
    reason_code: str
    detail: Optional[str] = None
    status: str = "open"
    created_at: Optional[str] = None
    # admin-view convenience fields (reporter nickname + a short label of the
    # reported target, e.g. a post title). Only populated by the admin list view.
    reporter_nickname: Optional[str] = None
    target_label: Optional[str] = None


class ReportStatusUpdate(BaseModel):
    status: str = Field(pattern=r"^(resolved|dismissed)$")
