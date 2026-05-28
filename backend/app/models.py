from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


# --- Auth ---

class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6)
    nickname: str = Field(min_length=1, max_length=30)
    student_id: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class GoogleLogin(BaseModel):
    id_token: str


class EmailRegister(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
    password: str = Field(min_length=6)
    nickname: str = Field(min_length=1, max_length=30)
    student_id: Optional[str] = None


class EmailLogin(BaseModel):
    email: str
    password: str


class ForgotPassword(BaseModel):
    email: str = Field(pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class ResetPassword(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


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


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=30)
    bio: Optional[str] = Field(None, max_length=300)
    avatar_url: Optional[str] = None


# --- Posts ---

class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)
    category: str = Field(min_length=1, max_length=30)


class PostUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = Field(None, max_length=10000)
    category: Optional[str] = Field(None, max_length=30)


class PostOut(BaseModel):
    id: int
    author_id: int
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


# --- Comments ---

class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentOut(BaseModel):
    id: int
    post_id: int
    author_id: int
    content: str
    likes_count: int = 0
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None
    author_avatar: Optional[str] = None


# --- Courses ---

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


class UserCourseUpdate(BaseModel):
    course_id: str
    status: str = Field(pattern=r"^(not_started|in_progress|completed)$")


class UserCourseOut(BaseModel):
    course_id: str
    status: str
    updated_at: Optional[str] = None


class CourseReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    content: str = Field(min_length=1, max_length=2000)


class CourseReviewOut(BaseModel):
    id: int
    course_id: str
    author_id: int
    rating: int
    content: str
    helpful_count: int = 0
    created_at: Optional[str] = None
    author_nickname: Optional[str] = None


# --- News ---

class NewsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    source_url: str


class NewsOut(BaseModel):
    id: int
    author_id: Optional[int] = None
    title: str
    summary: Optional[str] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    source_url: str
    published_at: Optional[str] = None


# --- Lost & Found ---

class LostFoundCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    item_type: str = Field(pattern=r"^(lost|found)$")
    category: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None


class LostFoundUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(active|resolved)$")


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
