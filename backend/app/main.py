from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from .database import init_db, close_db
from .config import API_PREFIX, SECRET_KEY
from .routers import auth, posts, courses, users, news, lostfound


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SECRET_KEY == "change-me-in-production":
        import warnings
        warnings.warn("WARNING: Using default SECRET_KEY. Set SECRET_KEY in .env for production!")
    await init_db()
    yield
    await close_db()


app = FastAPI(title="HKMU Campus Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8000,http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(posts.router, prefix=API_PREFIX)
app.include_router(courses.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(news.router, prefix=API_PREFIX)
app.include_router(lostfound.router, prefix=API_PREFIX)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
