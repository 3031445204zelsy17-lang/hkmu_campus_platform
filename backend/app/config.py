import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

DB_PATH = os.getenv("DATABASE_URL", "campus.db")

API_PREFIX = "/api/v1"
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
