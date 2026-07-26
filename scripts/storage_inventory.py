"""uploads bucket inventory + optional orphan GC (Plan B, downscoped).

Scale reality (2026-07-26 enum): the whole bucket holds ~8 legacy objects, all
originals (no @variant) + all no-cache, most orphaned. So instead of a heavy
CAS/ledger migration tool, this lightweight script:
  - lists every object (module / kind / size / cacheControl) — Storage only,
    no DB, runs anywhere the service key works;
  - with --gc, cross-refs the DB to find ORPHANS (objects no row references) and
    prints them (dry-run); --gc --apply deletes them.

Boundaries: read-only by default; deletion needs both --gc and --apply; never
touches DB rows or any referenced object. New uploads since #58 already have
variants + long cache, so this only deals with the legacy tail.

Env: SUPABASE_URL / SUPABASE_SERVICE_KEY from backend/.env (or env).
      PROD_DB_URL from env (or the commented pooler line in backend/.env) — only
      needed for --gc; it connects via the Supabase pooler (run in CI / non-VPN;
      local VPN often blocks the pooler port).

Usage:
  python3 scripts/storage_inventory.py              # inventory only (Storage)
  python3 scripts/storage_inventory.py --gc         # + find orphans (dry-run)
  python3 scripts/storage_inventory.py --gc --apply # + DELETE orphans
"""
import argparse
import asyncio
import os
import re
import ssl
from collections import Counter
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
BUCKET = "uploads"


def _load_env():
    env = dict(os.environ)
    p = REPO / "backend" / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    # PROD_DB_URL: env wins; else pull the commented pooler line from .env
    if not env.get("PROD_DB_URL"):
        for line in (p.read_text() if p.exists() else "").splitlines():
            m = re.search(r"(postgresql://[^\s\"']+pooler\.supabase\.com[^\s\"']+)", line)
            if m:
                env["PROD_DB_URL"] = m.group(1)
                break
    return env


def _classify(path: str) -> str:
    if "/v1/" in path and re.search(r"@[0-9a-f]{16}@", path):
        return "avatar-v1(new)"
    if re.search(r"@\d+\.(jpg|jpeg|png|webp)$", path):
        return "variant(@label)"
    return "ORIGINAL(no @label)"


async def enumerate_bucket(client, auth):
    """Recursively list all objects under the bucket. Returns [{path, size, cc}]."""
    out = []

    async def list_prefix(prefix):
        r = await client.post(
            f"/storage/v1/object/list/{BUCKET}", headers=auth, timeout=30,
            json={"prefix": prefix, "limit": 1000, "offset": 0},
        )
        return r.json() if r.status_code == 200 else []

    async def recurse(prefix):
        for it in await list_prefix(prefix):
            name = it.get("name", "")
            if not name:
                continue
            full = (prefix + name) if (not prefix or prefix.endswith("/")) else (prefix + "/" + name)
            meta = it.get("metadata")
            if meta:  # file
                out.append({"path": full, "size": meta.get("size"), "cc": meta.get("cacheControl")})
            else:  # subfolder
                sub = full if full.endswith("/") else full + "/"
                if sub != prefix:
                    await recurse(sub)

    await recurse("")
    return out


async def referenced_paths(client):
    """Set of bucket storage paths referenced by DB image columns."""
    import asyncpg
    env = _load_env()
    url = env.get("PROD_DB_URL")
    if not url:
        raise SystemExit("PROD_DB_URL not found (env or backend/.env pooler line)")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    conn = await asyncpg.connect(url, ssl=ctx, statement_cache_size=0, timeout=30, command_timeout=60)
    refs = set()
    try:
        for tbl, col in [("posts", "image_url"), ("lostfound", "image_url"), ("users", "avatar_url")]:
            rows = await conn.fetch(
                f"SELECT {col} AS u FROM {tbl} WHERE {col} LIKE '%/uploads/%'"
            )
            for r in rows:
                u = r["u"] or ""
                if "/object/public/uploads/" in u:
                    refs.add(u.split("/object/public/uploads/", 1)[1])
                elif "/uploads/" in u:
                    refs.add(u.split("/uploads/", 1)[1])
    finally:
        await conn.close()
    return refs


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gc", action="store_true", help="find orphan objects (dry-run)")
    ap.add_argument("--apply", action="store_true", help="with --gc, actually DELETE orphans")
    args = ap.parse_args()
    if args.apply and not args.gc:
        ap.error("--apply requires --gc")

    env = _load_env()
    supa = env.get("SUPABASE_URL", "").rstrip("/")
    key = env.get("SUPABASE_SERVICE_KEY", "")
    if not supa or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY missing")
    auth = {"Authorization": f"Bearer {key}", "apikey": key}

    async with httpx.AsyncClient(base_url=supa) as client:
        objs = await enumerate_bucket(client, auth)
        objs.sort(key=lambda o: o["path"])

        print(f"=== uploads bucket: {len(objs)} objects ===")
        by_mod = Counter(o["path"].split("/")[0] for o in objs)
        by_kind = Counter(_classify(o["path"]) for o in objs)
        by_cc = Counter(o["cc"] for o in objs)
        print("by module:", dict(by_mod))
        print("by kind  :", dict(by_kind))
        print("cacheCtrl:", dict(by_cc))
        for o in objs:
            print(f"  {_classify(o['path']):20} {str(o['size']):>9}B  cc={o['cc']!r:12} {o['path']}")

        if not args.gc:
            return

        print("\n=== orphan detection (DB cross-ref) ===")
        refs = await referenced_paths(client)
        orphans = [o for o in objs if o["path"] not in refs]
        print(f"DB-referenced bucket paths: {len(refs)}; orphans: {len(orphans)}")
        for o in orphans:
            print(f"  ORPHAN {o['path']}")
        if not orphans:
            print("  (none — bucket fully referenced)")
            return
        if not args.apply:
            print("\nDry-run only. Re-run with --gc --apply to delete the orphans.")
            return
        for o in orphans:
            r = await client.delete(f"/storage/v1/object/{BUCKET}/{o['path']}", headers=auth, timeout=30)
            print(f"  del {o['path']}: {r.status_code}")


if __name__ == "__main__":
    asyncio.run(main())
