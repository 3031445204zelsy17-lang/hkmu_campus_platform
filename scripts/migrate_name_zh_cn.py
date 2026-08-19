"""One-off migration: populate course_catalogue.name_zh_cn from display_name.

Background
----------
``course_catalogue`` shipped without a Simplified-Chinese column; ``display_name``
holds the original (mixed: ~545 Traditional humanities courses + ~4100 English).
zh-CN viewers should see 简体, so we add ``name_zh_cn`` and back-fill it via
OpenCC t2s. English-only courses have no CJK → ``name_zh_cn`` stays NULL and the
front end falls back to ``display_name`` (which is the English name anyway).

This is separate from ``seed_catalogue.py`` because the seed uses
``ON CONFLICT DO NOTHING`` — re-running it would NOT populate the new column on
rows that already exist. Run this once after the column is added.

Idempotent: ``ADD COLUMN IF NOT EXISTS`` + re-UPDATE is safe to re-run.

Usage
-----
    # from repo root, against the DB pointed at by backend/.env (DATABASE_URL)
    pip install asyncpg opencc-python-reimplemented python-dotenv
    python scripts/migrate_name_zh_cn.py

    # --check: open OpenCC, scan the table, print how many rows would change,
    # but do NOT write. CI / dry-run gate.
    python scripts/migrate_name_zh_cn.py --check
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

try:
    from opencc import OpenCC
    _T2S = OpenCC("t2s")
except ImportError as exc:  # pragma: no cover
    print(f"ERROR: opencc not installed ({exc}). "
          "Run: pip install opencc-python-reimplemented")
    sys.exit(2)

_CJK_RE = re.compile(r"[一-鿿]")


async def migrate(check_only: bool) -> int:
    import asyncpg

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    conn = await asyncpg.connect(database_url)
    try:
        if not check_only:
            await conn.execute(
                "ALTER TABLE course_catalogue ADD COLUMN IF NOT EXISTS name_zh_cn TEXT"
            )

        rows = await conn.fetch("SELECT id, display_name FROM course_catalogue")
        updates = []  # (name_zh_cn, id)
        skipped_english = 0
        skipped_same = 0
        samples = []
        for r in rows:
            name = r["display_name"] or ""
            if not _CJK_RE.search(name):
                skipped_english += 1
                continue
            simplified = _T2S.convert(name)
            if simplified == name:
                skipped_same += 1  # already simplified / no diff
                continue
            updates.append((simplified, r["id"]))
            if len(samples) < 8:
                samples.append((r["id"], name, simplified))

        print(f"total rows:        {len(rows)}")
        print(f"english (skip):    {skipped_english}")
        print(f"unchanged (skip):  {skipped_same}")
        print(f"to update:         {len(updates)}")
        print("samples:")
        for cid, name, simp in samples:
            print(f"  [{cid}] {name}  →  {simp}")

        if check_only:
            print("--check: no writes performed.")
            return 0

        if not updates:
            print("nothing to update.")
            return 0

        BATCH = 500
        for i in range(0, len(updates), BATCH):
            await conn.executemany(
                "UPDATE course_catalogue SET name_zh_cn = $1 WHERE id = $2",
                updates[i:i + BATCH],
            )
        print(f"updated {len(updates)} rows. done.")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    sys.exit(asyncio.run(migrate(check_only)))
