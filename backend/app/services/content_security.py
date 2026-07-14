"""WeChat content security (text) — msg_sec_check v2.

UGC text moderation for the mini program. Non-WeChat users (web/email/Google)
have no openid and are skipped (+ logged); FR1c will cover them with a local
sensitive-word layer. On API failure / timeout / openid-expired we degrade to
allow-and-log so a WeChat outage never blocks posting — same philosophy as the
WS→polling fallback. Only a clear ``risky``/``review`` verdict rejects the post.
"""

import asyncio
import logging
import os
import time

import httpx
from fastapi import HTTPException


logger = logging.getLogger("hkmu.security")

_WECHAT_BASE = "https://api.weixin.qq.com"
_TOKEN_URL = _WECHAT_BASE + "/cgi-bin/get_stable_access_token"
_MSG_SEC_CHECK_URL = _WECHAT_BASE + "/wxa/msg_sec_check"

# scene enum (WeChat msg_sec_check v2)
SCENE_PROFILE = 1
SCENE_COMMENT = 2  # 评论
SCENE_FORUM = 3    # 论坛
SCENE_SOCIAL = 4

# verdicts we treat as violation (review is保守拦截 — 官方建议人工复核)
_SUGGEST_VIOLATION = ("risky", "review")

# errcode: openid not accessed the mini program in the last 2h
_ERRCODE_OPENID_EXPIRED = 61010

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
        async with httpx.AsyncClient(timeout=5.0) as client:
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


async def audit_user_text(user: dict, text: str, scene: int) -> None:
    """Moderate UGC text for the current user.

    - Non-WeChat user (no openid): skip + log
    - API failure / openid-expired (61010) / other errcode: degrade to allow + log
    - suggest in (risky, review): reject with HTTP 400
    - pass / unknown: allow
    """
    provider = user.get("oauth_provider")
    openid = user.get("oauth_id")
    if provider != _PROVIDER_WECHAT or not openid:
        logger.info(
            "content_security skip (no openid): user=%s provider=%s",
            user.get("id"), provider,
        )
        return

    try:
        result = await check_text(openid, text, scene)
    except WechatContentSecurityError as exc:
        logger.warning(
            "content_security API error, allow+log: user=%s err=%s",
            user.get("id"), exc,
        )
        return

    errcode = result.get("errcode")
    if errcode:
        if errcode == _ERRCODE_OPENID_EXPIRED:
            logger.info(
                "content_security openid expired (61010), allow: user=%s",
                user.get("id"),
            )
        else:
            logger.warning(
                "content_security errcode=%s errmsg=%s, allow+log: user=%s",
                errcode, result.get("errmsg"), user.get("id"),
            )
        return

    suggest = (result.get("result") or {}).get("suggest")
    if suggest in _SUGGEST_VIOLATION:
        logger.info(
            "content_security rejected: user=%s scene=%s suggest=%s",
            user.get("id"), scene, suggest,
        )
        raise HTTPException(status_code=400, detail="内容包含违规信息，请修改后重试")
    # pass / unknown → allow
