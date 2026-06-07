import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 2  # 2 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7

DATABASE_URL = os.getenv("DATABASE_URL", "")
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

API_PREFIX = "/api/v1"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@hkmu-campus.example.com")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:8000")

# VAPID keys for Web Push
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS = {"sub": f"mailto:{os.getenv('VAPID_EMAIL', 'noreply@hkmu-campus.example.com')}"}

# Hot sort algorithm tuning
HOT_GRAVITY = float(os.getenv("HOT_GRAVITY", "48"))   # hours per 1-point decay
HOT_SEED = float(os.getenv("HOT_SEED", "1.0"))         # baseline score for new posts

# Admin setup: comma-separated usernames to auto-promote on startup
ADMIN_USERNAMES = [u.strip() for u in os.getenv("ADMIN_USERNAMES", "").split(",") if u.strip()]
