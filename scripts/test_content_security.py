"""Unit tests for content_security.audit_user_text — mocks check_text, no network.

Run: python3 scripts/test_content_security.py
Covers 6 branches: pass / risky / review / errcode-61010 / API-failure / no-openid.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from backend.app.services import content_security as cs  # noqa: E402


async def _run(user, text, scene, fake_response=None, fake_raises=None):
    """Call audit_user_text with a mocked check_text. Returns (outcome, calls)."""
    calls = []

    async def fake_check_text(openid, content, scene_):
        calls.append((openid, content, scene_))
        if fake_raises:
            raise fake_raises
        return fake_response

    cs.check_text = fake_check_text  # monkeypatch module-level reference
    try:
        await cs.audit_user_text(user, text, scene)
        return ("allow", calls)
    except HTTPException as e:
        return (e.status_code, calls)


async def main():
    wechat_user = {"id": 1, "oauth_provider": "wechat_miniprogram", "oauth_id": "OPENID123"}
    web_user = {"id": 2, "oauth_provider": None, "oauth_id": None}

    cases = {}

    r, _ = await _run(wechat_user, "hello", cs.SCENE_FORUM,
                      fake_response={"errcode": 0, "result": {"suggest": "pass"}})
    cases["1. pass → allow"] = r == "allow"

    r, _ = await _run(wechat_user, "bad", cs.SCENE_FORUM,
                      fake_response={"errcode": 0, "result": {"suggest": "risky"}})
    cases["2. risky → 400"] = r == 400

    r, _ = await _run(wechat_user, "edge", cs.SCENE_FORUM,
                      fake_response={"errcode": 0, "result": {"suggest": "review"}})
    cases["3. review → 400"] = r == 400

    r, _ = await _run(wechat_user, "x", cs.SCENE_FORUM,
                      fake_response={"errcode": 61010, "errmsg": "openid expired"})
    cases["4. errcode 61010 (openid expired) → allow"] = r == "allow"

    r, _ = await _run(wechat_user, "x", cs.SCENE_FORUM,
                      fake_raises=cs.WechatContentSecurityError("timeout"))
    cases["5. API failure → allow (degrade)"] = r == "allow"

    # web user (no openid): even a risky verdict is never requested → skip
    r, calls = await _run(web_user, "x", cs.SCENE_FORUM,
                          fake_response={"errcode": 0, "result": {"suggest": "risky"}})
    cases["6. no openid (web user) → skip, check_text not called"] = (
        r == "allow" and len(calls) == 0
    )

    passed = sum(cases.values())
    for name, ok in cases.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n{passed}/{len(cases)} passed")
    sys.exit(0 if passed == len(cases) else 1)


if __name__ == "__main__":
    asyncio.run(main())
