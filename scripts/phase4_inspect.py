#!/usr/bin/env python3
"""Phase 4 — 生产数据只读探查（不改任何数据）。

用途：连生产 Supabase，统计 news/lostfound/posts/users 现状，定位测试垃圾帖，
为「补 seed + 清垃圾帖」提供决策依据。全部 SELECT，零写入。

用法:
    PROD_DB_URL='postgresql://postgres.xxx:pass@aws-1-...pooler.supabase.com:6543/postgres' \
        python scripts/phase4_inspect.py
"""
import asyncio
import os
import ssl
import sys

import asyncpg

TABLES = [
    "users", "posts", "comments", "post_likes",
    "news", "news_comments", "lostfound", "messages",
]


async def main() -> None:
    url = os.environ.get("PROD_DB_URL")
    if not url:
        sys.exit("❌ PROD_DB_URL 未设置（生产 pooler 连接串）")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE  # 与 database.py 一致

    print("⏳ 连接生产 Supabase pooler …")
    conn = await asyncpg.connect(
        url, ssl=ssl_ctx, statement_cache_size=0,
        timeout=30, command_timeout=30,
    )
    try:
        ver = await conn.fetchval("SELECT version()")
        print(f"✅ 已连接：{ver[:60]} …\n")

        print("=== 各表行数 ===")
        for t in TABLES:
            cnt = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
            print(f"  {t:15} {cnt}")

        print("\n=== users（lostfound seed 候选作者）===")
        rows = await conn.fetch(
            "SELECT id, username, nickname, identity, email, created_at "
            "FROM users ORDER BY id"
        )
        for r in rows:
            print(f"  id={r['id']:>3} username={r['username']!r:<28} "
                  f"nick={r['nickname']!r:<20} identity={r['identity']!r:<10} "
                  f"email={r['email']!r}")

        print("\n=== news（现有）===")
        rows = await conn.fetch(
            "SELECT id, title, category, source_url, published_at FROM news ORDER BY id"
        )
        for r in rows:
            print(f"  id={r['id']:>3} cat={r['category']!r:<12} {r['title']!r}")
        print(f"  共 {len(rows)} 条")

        print("\n=== lostfound（现有）===")
        rows = await conn.fetch(
            "SELECT id, title, item_type, status, category, author_id FROM lostfound ORDER BY id"
        )
        for r in rows:
            print(f"  id={r['id']:>3} type={r['item_type']!r:<6} status={r['status']!r:<9} "
                  f"cat={r['category']!r:<12} author={r['author_id']} {r['title']!r}")
        print(f"  共 {len(rows)} 条")

        print("\n=== 疑似垃圾帖（asd/qwe 标题正文 / E2E Bot / WeChat User 作者）===")
        rows = await conn.fetch(
            """
            SELECT p.id, p.title, p.content, p.category, p.created_at,
                   p.author_id, u.username, u.nickname
            FROM posts p JOIN users u ON u.id = p.author_id
            WHERE p.title ILIKE '%asd%' OR p.title ILIKE '%qwe%'
               OR p.content ILIKE '%asd%' OR p.content ILIKE '%qwe%'
               OR u.nickname ILIKE '%E2E Bot%'
               OR u.username ILIKE '%E2E Bot%'
               OR u.nickname ILIKE '%WeChat User%'
               OR u.username ILIKE '%WeChat User%'
            ORDER BY p.id
            """
        )
        for r in rows:
            content_preview = (r["content"] or "")[:40].replace("\n", " ")
            print(f"  id={r['id']:>3} cat={r['category']!r:<14} "
                  f"author={r['author_id']}({r['nickname']!r}) "
                  f"title={r['title']!r} content={content_preview!r}")
        print(f"  垃圾帖候选共 {len(rows)} 条")

        # 这些垃圾帖是否有关联数据（影响删除顺序）
        if rows:
            ids = [r["id"] for r in rows]
            c_cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM comments WHERE post_id = ANY($1::int[])", ids
            )
            l_cnt = await conn.fetchval(
                "SELECT COUNT(*) FROM post_likes WHERE post_id = ANY($1::int[])", ids
            )
            print(f"  关联：comments={c_cnt}  post_likes={l_cnt}（删帖前需先清）")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
