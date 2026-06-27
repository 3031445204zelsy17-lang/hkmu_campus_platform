#!/usr/bin/env python3
"""Phase 4 — 补 news/lostfound seed + 清测试垃圾帖（连生产 Supabase）。

安全设计：
  · 默认 dry-run（只打印将要发生的事，零写入）；加 --apply 才真正执行。
  · 全程单事务，任何一步失败整体回滚。
  · 垃圾帖由 SQL 动态识别（asd/qwe + E2E Bot / WeChat User 作者），不硬编码 id。
  · 删帖按外键顺序：先 comments / post_likes，再 posts。
  · 只删帖，不删用户（删号超范围）。

用法:
    PROD_DB_URL='postgresql://...' python scripts/phase4_seed.py            # dry-run 预览
    PROD_DB_URL='postgresql://...' python scripts/phase4_seed.py --apply    # 实际执行
"""
import asyncio
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone

import asyncpg

HKMU_NEWS = "https://www.hkmu.edu.hk/latest-news-and-events/"
HKMU_HOME = "https://www.hkmu.edu.hk/"

# (title, summary, category, source_url, days_ago)  — author_id 固定 1(admin)
NEWS = [
    ("HKMU 公布最新发展蓝图 加大创新科技投入",
     "学校发布未来发展计划，重点投入人工智能、大数据与跨学科研究，提升教学与科研实力。",
     "academic", HKMU_NEWS, 2),
    ("数据科学及人工智能荣誉学士课程 2026/27 接受报名",
     "DSAI 课程新学年招生开启，培养人工智能与数据科学复合型人才，欢迎同学报读。",
     "academic", HKMU_NEWS, 6),
    ("HKMU 中乐团首演 粤剧专场反响热烈",
     "学校中乐团首次公开演出，以粤剧经典选段亮相，获师生与嘉宾一致好评。",
     "event", HKMU_NEWS, 10),
    ("AI 与低空经济峰会圆满举行",
     "HKMU 联合香港工程师学会主办峰会，探讨人工智能与低空经济的发展机遇与应用前景。",
     "event", HKMU_NEWS, 15),
    ("新医学科学实验室九月正式启用",
     "全新医学科学实验室将于新学期投入使用，大幅提升实验教学与科研能力。",
     "announcement", HKMU_NEWS, 21),
    ("2026/27 学年选课时间安排公布",
     "新学期选课系统开放时间及重要截止日期已公布，请同学及时登录系统查看。",
     "announcement", HKMU_NEWS, 27),
    ("校园秋季招聘会即将举办 多家企业到场",
     "学生事务处将举办秋季校园招聘会，多家企业到场设展，欢迎同学踊跃参加。",
     "career", HKMU_HOME, 33),
    ("粤语酒后语音检测系统研发取得突破",
     "HKMU 研究团队成功研发首个粤语酒后语音检测系统，相关成果获媒体广泛报道。",
     "other", HKMU_NEWS, 40),
]

# (title, description, item_type, category, location, status, author_id, days_ago)
LOSTFOUND = [
    ("捡到银色 U 盘",
     "在图书馆二楼自习区捡到一个银色 U 盘，失主请携带认领凭证联系。",
     "found", "电子产品", "图书馆二楼自习区", "active", 1, 1),
    ("丢失学生证",
     "不慎在食堂二楼遗失学生证，证上印有姓名，拾获者请联系，万分感谢。",
     "lost", "证件", "食堂二楼", "active", 10, 3),
    ("遗失黑色长柄雨伞",
     "在教学楼 A 座电梯口遗忘一把黑色长柄雨伞，已被好心同学代为保管。",
     "lost", "雨具", "教学楼 A 座电梯口", "resolved", 9, 7),
    ("捡到蓝色保温水杯",
     "图书馆一楼饮水机旁捡到一只蓝色保温水杯，已交至服务台。",
     "found", "生活用品", "图书馆一楼饮水机旁", "active", 1, 12),
    ("遗失白色蓝牙耳机",
     "在礼堂参加活动后遗失白色蓝牙耳机及充电盒，望拾获者联系酬谢。",
     "lost", "电子产品", "礼堂", "active", 10, 16),
    ("捡到课本《数据结构与算法》",
     "图书馆还书架发现一本《数据结构与算法》课本，已归还至借阅处。",
     "found", "书籍", "图书馆还书架", "resolved", 9, 22),
    ("丢失钥匙串（三把钥匙 + 小熊挂件）",
     "在篮球场遗失一串钥匙，共三把，挂着一个小熊挂件，拾获请联系。",
     "lost", "钥匙", "篮球场", "active", 1, 28),
]

# 动态识别垃圾帖的条件（与 phase4_inspect.py 保持一致）
GARBAGE_WHERE = """
    p.title ILIKE '%asd%' OR p.title ILIKE '%qwe%'
 OR p.content ILIKE '%asd%' OR p.content ILIKE '%qwe%'
 OR u.nickname ILIKE '%E2E Bot%'  OR u.username ILIKE '%E2E Bot%'
 OR u.nickname ILIKE '%WeChat User%' OR u.username ILIKE '%WeChat User%'
"""


async def main() -> None:
    apply = "--apply" in sys.argv
    url = os.environ.get("PROD_DB_URL")
    if not url:
        sys.exit("❌ PROD_DB_URL 未设置")

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    print(f"⏳ 连接生产 Supabase pooler …（模式: {'APPLY 写入' if apply else 'DRY-RUN 只读预览'}）")
    conn = await asyncpg.connect(
        url, ssl=ssl_ctx, statement_cache_size=0, timeout=30, command_timeout=60,
    )
    try:
        # ── 预览：垃圾帖 ──
        garbage = await conn.fetch(
            f"""SELECT p.id, p.title, p.author_id, u.nickname
                FROM posts p JOIN users u ON u.id = p.author_id
                WHERE {GARBAGE_WHERE} ORDER BY p.id"""
        )
        g_ids = [r["id"] for r in garbage]
        g_comments = await conn.fetchval(
            "SELECT COUNT(*) FROM comments WHERE post_id = ANY($1::int[])", g_ids
        ) if g_ids else 0
        g_likes = await conn.fetchval(
            "SELECT COUNT(*) FROM post_likes WHERE post_id = ANY($1::int[])", g_ids
        ) if g_ids else 0

        print(f"\n=== 将插入 news {len(NEWS)} 条 ===")
        for t, s, c, src, d in NEWS:
            print(f"  [{c:12}] (-{d:>2}d) {t}")
        print(f"\n=== 将插入 lostfound {len(LOSTFOUND)} 条 ===")
        for t, desc, it, cat, loc, st, au, d in LOSTFOUND:
            print(f"  [{it:5}/{st:8}] (-{d:>2}d) author={au} {t}  @ {loc}")
        print(f"\n=== 将删除垃圾帖 {len(garbage)} 条（关联 comments={g_comments} post_likes={g_likes}，先清后删）===")
        for r in garbage:
            print(f"  id={r['id']:>3} author={r['author_id']}({r['nickname']!r}) {r['title']!r}")

        if not apply:
            print("\n🟡 DRY-RUN：未写入任何数据。确认无误后加 --apply 执行。")
            return

        # ── APPLY：单事务执行 ──
        print("\n🟢 APPLY：开始事务写入 …")
        async with conn.transaction():
            now = datetime.now(timezone.utc)
            n_news = n_lf = 0
            for t, s, c, src, d in NEWS:
                await conn.execute(
                    """INSERT INTO news (author_id, title, summary, category, source_url, published_at)
                       VALUES ($1,$2,$3,$4,$5,$6)""",
                    1, t, s, c, src, now - timedelta(days=d),
                )
                n_news += 1
            for t, desc, it, cat, loc, st, au, d in LOSTFOUND:
                await conn.execute(
                    """INSERT INTO lostfound
                         (author_id, title, description, item_type, category, location, status, created_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    au, t, desc, it, cat, loc, st, now - timedelta(days=d),
                )
                n_lf += 1
            if g_ids:
                dc = await conn.execute(
                    "DELETE FROM comments WHERE post_id = ANY($1::int[])", g_ids)
                dl = await conn.execute(
                    "DELETE FROM post_likes WHERE post_id = ANY($1::int[])", g_ids)
                dp = await conn.execute(
                    "DELETE FROM posts WHERE id = ANY($1::int[])", g_ids)
            else:
                dc = dl = dp = "DELETE 0"
            print(f"  ✅ INSERT news={n_news}  lostfound={n_lf}")
            print(f"  ✅ {dc}  {dl}  {dp}（comments / post_likes / posts）")
        print("\n🎉 事务已提交。")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
