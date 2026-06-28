#!/usr/bin/env python3
"""HKMU News RSS → 生产 news 表 同步器（方案 C 精修版，Phase 6a）。

从 HKMU 官网 WordPress RSS 抓真实新闻入库。Phase 6a 只抓繁体；Phase 6b
（deferred，见 progress.json phase6b_news_trilingual）只需在 FEEDS 字典里
解开 en / zh-hans 两行 —— 表与后端 API 已一次到位，无需再改。

合规：robots.txt 全允许；只存摘要 + 精确原文链接，不存全文；UA 标识；低频。
复用：scripts/phase4_seed.py 的 asyncpg 连接模式（SSL + statement_cache_size=0）。

用法:
    PROD_DB_URL='postgresql://...' python scripts/sync_news.py                 # 增量(1页)
    PROD_DB_URL='postgresql://...' python scripts/sync_news.py --dry-run       # 只抓不写
    PROD_DB_URL='postgresql://...' python scripts/sync_news.py --pages 3       # 翻3页回填
    PROD_DB_URL='postgresql://...' python scripts/sync_news.py --purge --pages 3  # 首次:清旧+回填
"""
import argparse
import asyncio
import html
import os
import re
import ssl
import sys
from datetime import datetime, timezone

import asyncpg
import feedparser
import httpx

# Phase 6a：只抓繁体。Phase 6b 解开下面两行即支持三语（表/API 已就绪）。
FEEDS = {
    "zh-hant": "https://www.hkmu.edu.hk/news/tc/feed/",
    # "en": "https://www.hkmu.edu.hk/news/feed/",
    # "zh-hans": "https://www.hkmu.edu.hk/news/sc/feed/",
}
USER_AGENT = "HKMU-Campus-Platform/news-sync (student platform; contact: info@hkmu.edu.hk)"
SUMMARY_MAX = 200


# ── 解析辅助 ──────────────────────────────────────────────────────────────────

def clean_text(raw: str) -> str:
    """Strip HTML tags, decode entities, collapse whitespace."""
    if not raw:
        return ""
    out = re.sub(r"<[^>]+>", " ", raw)
    out = html.unescape(out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def map_category(wp_categories: list[str]) -> str:
    """Map WordPress categories (>=1 per post) → frontend 5-way enum, by priority.

    HKMU News is WPML multilingual: the zh-hant feed carries Chinese category
    labels (新聞稿 / 都大學者撰文…), the en feed carries English (Press Releases…).
    We match BOTH so the script maps correctly regardless of which language feed
    is active in FEEDS. Frontend enum (frontend/js/pages/news.js CATEGORIES):
    announcement / event / academic / career / other.
    """
    joined = " ".join(c.lower().strip() for c in wp_categories if c)
    if any(k in joined for k in (
        "press release", "announcement", "新聞稿", "新聞發佈", "公告", "佈告",
    )):
        return "announcement"
    if any(k in joined for k in (
        "major event", "重要活動", "大型活動", "主要活動", "活動日誌", "活動",
    )):
        return "event"
    if any(k in joined for k in (
        "academic", "research", "applied science", "knowledge transfer",
        "學術", "研究", "應用科學", "知識轉移", "學者", "撰文",
    )):
        return "academic"
    if any(k in joined for k in (
        "industry", "employer", "career", "employment", "internship",
        "就業", "招聘", "實習", "職涯",
    )):
        return "career"
    return "other"


def parse_entry(entry, lang: str, fallback_now: datetime) -> dict | None:
    title = clean_text(entry.get("title", ""))
    source_url = (entry.get("link") or "").strip()
    if not title or not source_url:
        return None
    summary = clean_text(entry.get("summary", "") or entry.get("description", ""))[:SUMMARY_MAX]
    pt = entry.get("published_parsed")
    published_at = datetime(*pt[:6], tzinfo=timezone.utc) if pt else fallback_now
    wp_cats = [t.get("term", "") for t in entry.get("tags", []) if isinstance(t, dict)]
    if not wp_cats and entry.get("category"):
        wp_cats = [entry["category"]]
    return {
        "lang": lang,
        "title": title,
        "summary": summary,
        "category": map_category(wp_cats),
        "source_url": source_url,
        "published_at": published_at,
    }


async def fetch_entries(client: httpx.AsyncClient, feed_url: str, pages: int) -> list:
    entries = []
    for page in range(1, pages + 1):
        url = feed_url if page == 1 else f"{feed_url}?paged={page}"
        try:
            resp = await client.get(url)
        except httpx.HTTPError as exc:
            print(f"  ⚠️  page {page} 请求失败: {exc}")
            break
        if resp.status_code != 200:
            print(f"  page {page}: HTTP {resp.status_code}, 停止翻页")
            break
        feed = feedparser.parse(resp.text)
        if not feed.entries:
            print(f"  page {page}: 无条目，停止翻页")
            break
        entries.extend(feed.entries)
    return entries


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def main() -> None:
    ap = argparse.ArgumentParser(description="Sync HKMU news RSS → production news table")
    ap.add_argument("--dry-run", action="store_true", help="只抓取+解析+打印，不写库")
    ap.add_argument("--pages", type=int, default=1, help="回填页数（每页 ~10 条）")
    ap.add_argument("--purge", action="store_true", help="写库前清空 news（首次清假 seed）")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    all_items: list[dict] = []
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for lang, feed_url in FEEDS.items():
            print(f"📡 [{lang}] {feed_url} (pages={args.pages})")
            raw = await fetch_entries(client, feed_url, args.pages)
            print(f"   解析到 {len(raw)} 条原始条目")
            for e in raw:
                item = parse_entry(e, lang, now)
                if item:
                    all_items.append(item)

    # 去重（同语言同链接，feed 翻页偶发重复）
    seen = set()
    deduped = []
    for it in all_items:
        key = (it["lang"], it["source_url"])
        if key not in seen:
            seen.add(key)
            deduped.append(it)
    all_items = deduped

    print(f"\n=== 共 {len(all_items)} 条待写 ===")
    for it in all_items[:25]:
        print(f"  [{it['lang']}/{it['category']:11}] {it['published_at']:%Y-%m-%d}  "
              f"{it['title'][:46]}")
        print(f"      → {it['source_url']}")
    if len(all_items) > 25:
        print(f"  … 余 {len(all_items) - 25} 条")

    if args.dry_run:
        print(f"\n🟡 DRY-RUN：未写库（{len(all_items)} 条预览）。确认无误去掉 --dry-run 执行。")
        return

    # ── 写库 ──
    db_url = os.environ.get("PROD_DB_URL")
    if not db_url:
        sys.exit("❌ PROD_DB_URL 未设置")
    # 归一到 transaction-mode pooler（6543），与 phase4 脚本一致，使 db-backup 的
    # 5432 secret 也能直接复用。session mode (5432) 与 transaction mode (6543) 同密码。
    db_url = db_url.replace(":5432/", ":6543/")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    print(f"\n⏳ 连接生产 Supabase pooler …（purge={'是' if args.purge else '否'}）")
    conn = await asyncpg.connect(
        db_url, ssl=ssl_ctx, statement_cache_size=0, timeout=30, command_timeout=120,
    )
    try:
        new = updated = 0
        # 单事务：purge → 建唯一索引 → upsert。任一步失败整体回滚（含 purge），
        # 绝不会出现"清空了却没回填"的中间态。
        async with conn.transaction():
            # Ensure lang column exists (idempotent — database.py DDL also adds it
            # on app restart; whichever runs first is fine). Lets the sync work
            # even before the backend is redeployed.
            await conn.execute(
                "ALTER TABLE news ADD COLUMN IF NOT EXISTS lang "
                "TEXT NOT NULL DEFAULT 'zh-hant'"
            )
            if args.purge:
                old = await conn.fetchval("SELECT COUNT(*) FROM news")
                await conn.execute("DELETE FROM news")
                print(f"🗑  purge：删除 {old} 条旧数据（含 Phase 4 假 seed）")

            # 唯一索引（upsert 依赖；首次需数据已 purge 干净，否则重复 source_url 会报错）
            try:
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_news_lang_source "
                    "ON news(lang, source_url)"
                )
            except Exception as exc:
                print(f"❌ 建唯一索引失败（可能有重复 source_url）：{exc}")
                print("   → 请用 --purge 先清掉旧数据再同步。")
                raise

            for it in all_items:
                row = await conn.fetchrow(
                    """
                    INSERT INTO news (lang, title, summary, category, source_url, published_at, author_id)
                    VALUES ($1, $2, $3, $4, $5, $6, NULL)
                    ON CONFLICT (lang, source_url) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        category = EXCLUDED.category,
                        published_at = EXCLUDED.published_at
                    RETURNING (xmax = 0) AS inserted
                    """,
                    it["lang"], it["title"], it["summary"], it["category"],
                    it["source_url"], it["published_at"],
                )
                if row["inserted"]:
                    new += 1
                else:
                    updated += 1
        print(f"\n✅ 同步完成：新增 {new}，更新 {updated}（共 {new + updated}）")
        total = await conn.fetchval("SELECT COUNT(*) FROM news")
        print(f"   news 表当前 {total} 条")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
