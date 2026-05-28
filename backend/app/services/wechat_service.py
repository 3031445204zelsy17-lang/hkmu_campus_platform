import os

import httpx


WECHAT_CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WechatMiniProgramError(Exception):
    """Base WeChat mini program login error."""


class WechatMiniProgramConfigError(WechatMiniProgramError):
    """Raised when the server is missing mini program credentials."""


class WechatMiniProgramAuthError(WechatMiniProgramError):
    """Raised when WeChat rejects or cannot complete the login exchange."""


class WechatMiniProgramSession:
    def __init__(self, openid: str, session_key: str, unionid: str | None = None):
        self.openid = openid
        self.session_key = session_key
        self.unionid = unionid


async def exchange_code_for_session(code: str) -> WechatMiniProgramSession:
    app_id = os.getenv("WECHAT_MINIPROGRAM_APPID", "").strip()
    secret = os.getenv("WECHAT_MINIPROGRAM_SECRET", "").strip()

    if not app_id or not secret:
        raise WechatMiniProgramConfigError("WeChat mini program login is not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                WECHAT_CODE2SESSION_URL,
                params={
                    "appid": app_id,
                    "secret": secret,
                    "js_code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise WechatMiniProgramAuthError("Unable to reach WeChat login service") from exc

    data = response.json()
    errcode = data.get("errcode")
    if errcode:
        errmsg = str(data.get("errmsg") or "unknown error")
        raise WechatMiniProgramAuthError(f"WeChat login failed: {errmsg} ({errcode})")

    openid = str(data.get("openid") or "").strip()
    session_key = str(data.get("session_key") or "").strip()
    unionid = str(data.get("unionid") or "").strip() or None

    if not openid or not session_key:
        raise WechatMiniProgramAuthError("WeChat login failed: missing openid or session_key")

    return WechatMiniProgramSession(openid=openid, session_key=session_key, unionid=unionid)
