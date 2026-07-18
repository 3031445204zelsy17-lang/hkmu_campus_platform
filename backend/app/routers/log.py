"""Client-side error reporting endpoint (FR2).

Web frontend captures window.onerror / unhandledrejection and POSTs here;
we log via the shared hkmu.security logger so it lands in App Insights
AppTraces (same channel as backend errors). Best-effort + IP rate-limited.
"""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..services.rate_limiter import check_rate_limit


router = APIRouter(prefix="/log", tags=["log"])
logger = logging.getLogger("hkmu.security")


class ClientError(BaseModel):
    type: str = Field(default="error", max_length=64)  # "error" / "unhandledrejection" (Codex [21])
    message: str = Field(default="", max_length=1000)
    source: str | None = Field(default=None, max_length=500)  # filename
    lineno: int | None = None
    colno: int | None = None
    stack: str | None = Field(default=None, max_length=1000)
    url: str | None = Field(default=None, max_length=500)


@router.post("/client-error", status_code=204)
async def report_client_error(body: ClientError, request: Request):
    # 宽松 IP 限流,防日志被刷(前端正常错误远低于此)
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"client-error:{ip}", max_requests=30, window_seconds=60)

    logger.warning(
        "client_error type=%s: %s @ %s:%s:%s | url=%s | stack=%s",
        body.type,
        (body.message or "")[:300],
        body.source,
        body.lineno,
        body.colno,
        body.url,
        (body.stack or "")[:500],
    )
    # 204 No Content — 前端 best-effort,不关心响应
    return None
