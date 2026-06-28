#!/usr/bin/env python3
"""Phase 4 补丁 — 清掉 seed 的 7 条 lostfound 假数据，保留真实用户发的条目。

理由：失物招领是真实交互功能（真失主发布、真拾主认领、联系归还），
AI 编的假失物（U盘/学生证/雨伞…，作者还是 testuser1/评审测试/Zelsy）会
误导真实用户去联系认领根本不存在的东西。真实上线前应清空，让真实数据自然沉淀。
news 的 8 条校园新闻保留（单向资讯、有 HKMU 真实出处，不涉及认领误导）。

用法:
    PROD_DB_URL='postgresql://...' python scripts/phase4_cleanup_lostfound.py            # dry-run
    PROD_DB_URL='postgresql://...' python scripts/phase4_cleanup_lostfound.py --apply    # 执行
"""
import asyncio
import os
import ssl
import sys

import asyncpg

# phase4_seed.py 里加的 7 条 title（精确匹配；真实「黑色钱包」不在此列，保留）
SEED_TITLES = [
    "捡到银色 U 盘",
    "丢失学生证",
    "遗失黑色长柄雨伞",
    "捡到蓝色保温水杯",
    "遗失白色蓝牙耳机",
    "捡到课本《数据结构与算法》",
    "丢失钥匙串（三把钥匙 + 小熊挂件）",
]


async def main() -> None:
    apply = "--apply" in sys.argv
    url = os.environ.get("PROD_DB_URL")
    if not url:
        sys.exit("❌ PROD_DB_URL 未设置")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    print(f"⏳ 连接生产 …（模式: {'APPLY' if apply else 'DRY-RUN'}）")
    conn = await asyncpg.connect(
        url, ssl=ssl_ctx, statement_cache_size=0, timeout=30, command_timeout=60,
    )
    try:
        victims = await conn.fetch(
            "SELECT id, title, author_id FROM lostfound WHERE title = ANY($1::text[]) ORDER BY id",
            SEED_TITLES,
        )
        keepers = await conn.fetch(
            "SELECT id, title, author_id FROM lostfound WHERE title != ALL($1::text[]) ORDER BY id",
            SEED_TITLES,
        )

        print(f"\n=== 将删除 {len(victims)} 条 seed 假数据 ===")
        for r in victims:
            print(f"  id={r['id']:>2} author={r['author_id']} {r['title']!r}")
        print(f"\n=== 保留 {len(keepers)} 条（真实数据）===")
        for r in keepers:
            print(f"  id={r['id']:>2} author={r['author_id']} {r['title']!r}")

        if len(victims) != len(SEED_TITLES):
            print(f"\n⚠️ 命中 {len(victims)} 条 != 预期 {len(SEED_TITLES)} 条，可能有数据已被改过，请人工核对。")

        if not apply:
            print("\n🟡 DRY-RUN：未删除。确认后加 --apply 执行。")
            return

        async with conn.transaction():
            res = await conn.execute(
                "DELETE FROM lostfound WHERE title = ANY($1::text[])", SEED_TITLES
            )
        print(f"\n✅ {res}")
        after = await conn.fetchval("SELECT COUNT(*) FROM lostfound")
        print(f"lostfound 剩余 {after} 条")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
