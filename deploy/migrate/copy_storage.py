"""
deploy/migrate/copy_storage.py — copies the stored files from Supabase Cloud
to the self-hosted stack (S50).

migrate_db.sh brings over the buckets and the storage.objects rows, but not
the files themselves: those live in Supabase Cloud's object store. This walks
every bucket on the old side, downloads each file and uploads it to the same
path on the new side (upsert, so the restored row is simply rewritten).
Read-only on the old side. Safe to run again.

Run inside the app image, from deploy/:

    docker compose run --rm -T \
        -e OLD_SUPABASE_URL=https://<ref>.supabase.co \
        -e OLD_SUPABASE_SERVICE_KEY=... \
        -v ./migrate:/migrate jobs python /migrate/copy_storage.py

The new side comes from SUPABASE_URL / SUPABASE_SERVICE_KEY in deploy/.env.
Ends by comparing file counts and sizes per bucket; exits non-zero on any
difference.
"""

import os
import sys

from supabase import create_client

old = create_client(os.environ["OLD_SUPABASE_URL"], os.environ["OLD_SUPABASE_SERVICE_KEY"])
new = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def walk(client, bucket: str, prefix: str = ""):
    """Every file path in a bucket. Folders are listed with no id."""
    offset = 0
    while True:
        page = client.storage.from_(bucket).list(
            prefix, {"limit": 1000, "offset": offset, "sortBy": {"column": "name", "order": "asc"}})
        if not page:
            return
        for item in page:
            path = f"{prefix}/{item['name']}" if prefix else item["name"]
            if item.get("id") is None:
                yield from walk(client, bucket, path)
            else:
                yield path, (item.get("metadata") or {})
        offset += len(page)


def inventory(client, bucket: str) -> dict:
    """{path: metadata} for every file in the bucket."""
    return dict(walk(client, bucket))


def sizes(inv: dict) -> dict:
    return {p: m.get("size") or 0 for p, m in inv.items()}


failed = 0
for b in old.storage.list_buckets():
    name = b.name if hasattr(b, "name") else b["name"]
    files = inventory(old, name)
    print(f"== {name}: {len(files)} files")
    for path, meta in files.items():
        data = old.storage.from_(name).download(path)
        try:
            new.storage.from_(name).upload(
                path, data,
                {"content-type": meta.get("mimetype") or "application/octet-stream",
                 "upsert": "true"})
        except Exception as e:
            failed += 1
            print(f"   FAILED {path}: {e}")

    want, got = sizes(files), sizes(inventory(new, name))
    if want == got:
        print(f"   {name}: all {len(want)} files present, sizes match")
    else:
        failed += 1
        missing = sorted(set(want) - set(got))
        differ = sorted(p for p in want if p in got and got[p] != want[p])
        print(f"   {name}: {len(missing)} missing, {len(differ)} with a different size")
        for p in (missing + differ)[:20]:
            print(f"      {p}")

sys.exit(1 if failed else 0)
