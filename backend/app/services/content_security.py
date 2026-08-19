"""WeChat content security (text) — msg_sec_check v2.

UGC text moderation for the mini program, **fail-closed** for WeChat users.

Non-WeChat users (web/email/Google) have no openid and are skipped (+ logged);
FR1c will cover them with a local sensitive-word layer. For WeChat users the
gate is default-deny: only an explicit ``suggest == "pass"`` allows the post.
Violation verdicts (``risky`` / ``review``) → HTTP 400. Any service anomaly —
transport failure, access-token failure, timeout, illegal JSON, any WeChat
errcode (incl. 61010 openid-expired), missing/non-dict result, or an unknown
suggest → HTTP 503 ("内容审核暂时不可用，请稍后重试"): the post is blocked, not
published. Rationale: a moderation gate that silently allows on service failure
is an open path to publish unmoderated UGC during a WeChat outage.
"""

import asyncio
import logging
import os
import time

import httpx
from fastapi import HTTPException

from ..config import ENABLE_CONTENT_MODERATION


logger = logging.getLogger("hkmu.security")

_WECHAT_BASE = "https://api.weixin.qq.com"
# ⚠️ 正确路径是 /cgi-bin/stable_token。FR1 起误写为 /cgi-bin/get_stable_access_token
# (该路径不存在,微信回 HTTP 404)→ fail-closed 503 挡了所有微信用户 UGC,
# 8-04 因此关审核,并被误诊为「IP 白名单架构堵死」——2026-08-16 生产日志铁证纠正。
_TOKEN_URL = _WECHAT_BASE + "/cgi-bin/stable_token"
_MSG_SEC_CHECK_URL = _WECHAT_BASE + "/wxa/msg_sec_check"
_IMG_SEC_CHECK_URL = _WECHAT_BASE + "/wxa/img_sec_check"

# scene enum (WeChat msg_sec_check v2)
SCENE_PROFILE = 1
SCENE_COMMENT = 2  # 评论
SCENE_FORUM = 3    # 论坛
SCENE_SOCIAL = 4

# verdicts we treat as violation (review is保守拦截 — 官方建议人工复核)
_SUGGEST_VIOLATION = ("risky", "review")

# errcode: openid not accessed the mini program in the last 2h
_ERRCODE_OPENID_EXPIRED = 61010

# errcode: img_sec_check verdict "content risky" (v1 has no suggest field)
_ERRCODE_IMG_RISKY = 87014

_PROVIDER_WECHAT = "wechat_miniprogram"


class WechatContentSecurityError(Exception):
    """Raised when the access_token cannot be obtained."""


# Module-level token cache. The access_token is app-wide unique, so a single
# cached value serves all requests; the lock prevents concurrent first-callers
# from each fetching a fresh token (WeChat invalidates the previous one).
_access_token: str | None = None
_token_expires_at: float = 0.0
_token_lock = asyncio.Lock()


async def _get_access_token() -> str:
    """Return a cached stable access_token, refreshing ~5 min before expiry."""
    global _access_token, _token_expires_at
    if _access_token and time.time() < _token_expires_at:
        return _access_token
    async with _token_lock:
        # double-check after acquiring the lock
        if _access_token and time.time() < _token_expires_at:
            return _access_token
        app_id = os.getenv("WECHAT_MINIPROGRAM_APPID", "").strip()
        secret = os.getenv("WECHAT_MINIPROGRAM_SECRET", "").strip()
        if not app_id or not secret:
            raise WechatContentSecurityError("WeChat appid/secret not configured")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    _TOKEN_URL,
                    json={
                        "grant_type": "client_credential",
                        "appid": app_id,
                        "secret": secret,
                    },
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise WechatContentSecurityError("Unable to reach WeChat token service") from exc
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise WechatContentSecurityError(f"get_stable_access_token failed: {data}")
        _access_token = token
        expires_in = int(data.get("expires_in") or 7200)
        # refresh 5 min early, but keep at least 60s of life
        _token_expires_at = time.time() + max(expires_in - 300, 60)
        return _access_token


async def check_text(openid: str, content: str, scene: int) -> dict:
    """Call msg_sec_check v2. Returns the raw WeChat JSON response.

    Raises WechatContentSecurityError on transport failure (caller decides
    to degrade).
    """
    token = await _get_access_token()
    try:
        # 10s:Azure SEA → api.weixin.qq.com 跨境链路偶发高延迟,5s 会把慢响应
        # 误判为服务异常(fail-closed 503 挡正常发帖);等满 10s 再判死。
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _MSG_SEC_CHECK_URL,
                params={"access_token": token},
                json={
                    "openid": openid,
                    "content": content[:2500],
                    "scene": scene,
                    "version": 2,
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise WechatContentSecurityError("Unable to reach WeChat msg_sec_check") from exc
    return resp.json()


async def check_image(image_bytes: bytes) -> dict:
    """Call img_sec_check (v1, synchronous). Returns the raw WeChat JSON.

    ``image_bytes`` must already satisfy the API contract (PNG/JPEG/BMP,
    ≤1 MB, ≤750×1334) — build with storage_service.check_thumbnail.

    Raises WechatContentSecurityError on transport failure.
    """
    token = await _get_access_token()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _IMG_SEC_CHECK_URL,
                params={"access_token": token},
                files={"media": ("check.jpg", image_bytes, "image/jpeg")},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise WechatContentSecurityError("Unable to reach WeChat img_sec_check") from exc
    return resp.json()


async def audit_user_text(user: dict, text: str, scene: int) -> None:
    """Moderate UGC text for the current user — fail-closed for WeChat users.

    Decision table (WeChat user with openid):
      suggest == "pass"                  → allow (the ONLY allow path)
      suggest in ("risky", "review")     → HTTP 400 内容包含违规信息
      service anomaly *                  → HTTP 503 内容审核暂时不可用
    * service anomaly = transport / token / timeout failure, illegal JSON,
      any non-zero errcode (incl. 61010), missing/non-dict result, or unknown
      suggest. A moderation gate that silently allows on service failure is an
      open path to publish unmoderated UGC during a WeChat outage → block.

    Non-WeChat user (no openid): skip + log (FR1c local layer deferred).

    Kill switch: ENABLE_CONTENT_MODERATION=false bypasses moderation entirely
    (temporary degradation — see config.ENABLE_CONTENT_MODERATION).
    """
    if not ENABLE_CONTENT_MODERATION:
        logger.warning(
            "content moderation DISABLED via env — UGC from user=%s passes unfiltered",
            user.get("id"),
        )
        return

    provider = user.get("oauth_provider")
    openid = user.get("oauth_id")
    if provider != _PROVIDER_WECHAT or not openid:
        logger.info(
            "content_security skip (no openid): user=%s provider=%s",
            user.get("id"), provider,
        )
        return  # FR1c: non-WeChat users — local sensitive-word layer deferred

    # --- service / transport / parse failure → 503 (fail-closed) ---
    try:
        result = await check_text(openid, text, scene)
    except (WechatContentSecurityError, ValueError, httpx.HTTPError) as exc:
        logger.exception(
            "content_security check failed (fail-closed 503): user=%s err=%s",
            user.get("id"), exc,
        )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")

    if not isinstance(result, dict):
        logger.error(
            "content_security non-dict response (fail-closed 503): user=%s resp=%r",
            user.get("id"), result,
        )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")

    # --- any WeChat errcode (incl. 61010 openid-expired) → 503 ---
    errcode = result.get("errcode")
    if errcode:
        if errcode == _ERRCODE_OPENID_EXPIRED:
            logger.warning(
                "content_security openid expired (61010), fail-closed 503: user=%s",
                user.get("id"),
            )
        else:
            logger.error(
                "content_security errcode=%s errmsg=%s, fail-closed 503: user=%s",
                errcode, result.get("errmsg"), user.get("id"),
            )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")

    # --- verdict: only an explicit pass allows ---
    result_obj = result.get("result")
    if not isinstance(result_obj, dict):
        logger.error(
            "content_security missing/illegal result (fail-closed 503): user=%s resp=%r",
            user.get("id"), result,
        )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")
    suggest = result_obj.get("suggest")
    if suggest == "pass":
        return
    if suggest in _SUGGEST_VIOLATION:
        logger.info(
            "content_security rejected: user=%s scene=%s suggest=%s",
            user.get("id"), scene, suggest,
        )
        raise HTTPException(status_code=400, detail="内容包含违规信息，请修改后重试")
    # unknown suggest → fail-closed
    logger.error(
        "content_security unknown suggest (fail-closed 503): user=%s suggest=%r",
        user.get("id"), suggest,
    )
    raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")


async def audit_user_image(user: dict, raw: bytes) -> None:
    """Moderate a user-uploaded IMAGE (avatars, post/lostfound photos).

    Same policy skeleton as ``audit_user_text``, adapted to img_sec_check v1
    (no ``suggest`` field — the verdict IS errcode):

      errcode == 0                        → allow (the ONLY allow path)
      errcode == 87014 (risky)            → HTTP 400 内容包含违规信息
      service anomaly *                   → HTTP 503 内容审核暂时不可用
      undecodable image (thumb is None)   → HTTP 400 换格式 (a gate that
                                            can't inspect the bytes can't
                                            clear them for WeChat users)

    * transport / token / timeout failure, illegal JSON, any other non-zero
      errcode — fail-closed, identical rationale to the text gate.
    Non-WeChat users (no openid) skip + log; kill switch bypasses, same as text.
    """
    if not ENABLE_CONTENT_MODERATION:
        logger.warning(
            "content moderation DISABLED via env — image from user=%s passes unfiltered",
            user.get("id"),
        )
        return

    provider = user.get("oauth_provider")
    openid = user.get("oauth_id")
    if provider != _PROVIDER_WECHAT or not openid:
        logger.info(
            "content_security image skip (no openid): user=%s provider=%s",
            user.get("id"), provider,
        )
        return

    from .storage_service import check_thumbnail

    thumb = check_thumbnail(raw)
    if thumb is None:
        logger.warning(
            "content_security image undecodable (fail-closed 400): user=%s", user.get("id"),
        )
        raise HTTPException(status_code=400, detail="图片格式不支持，请更换后重试")

    # --- service / transport / parse failure → 503 (fail-closed) ---
    try:
        result = await check_image(thumb)
    except (WechatContentSecurityError, ValueError, httpx.HTTPError) as exc:
        logger.exception(
            "content_security image check failed (fail-closed 503): user=%s err=%s",
            user.get("id"), exc,
        )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")

    if not isinstance(result, dict):
        logger.error(
            "content_security image non-dict response (fail-closed 503): user=%s resp=%r",
            user.get("id"), result,
        )
        raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")

    errcode = result.get("errcode")
    if errcode == 0:
        return
    if errcode == _ERRCODE_IMG_RISKY:
        logger.info(
            "content_security image rejected: user=%s", user.get("id"),
        )
        raise HTTPException(status_code=400, detail="内容包含违规信息，请修改后重试")
    # any other errcode (incl. 61010-equivalent / token issues) → fail-closed
    logger.error(
        "content_security image errcode=%s errmsg=%s (fail-closed 503): user=%s",
        errcode, result.get("errmsg"), user.get("id"),
    )
    raise HTTPException(status_code=503, detail="内容审核暂时不可用，请稍后重试")
