"""D-222: deleting an expired trial on day 60 (expired_trial.py has the
timeline; migration_d222_trial_deletion.sql the database side).

Order: the stored files first (the storage API, so the files themselves go,
not just their rows), then everything else in one database transaction
(delete_trial_account), which refuses anything that is not an expired trial
past its date, never paid, not an admin's, nothing under legal hold. A
failure after the files leaves the rest for the next run.
"""

from __future__ import annotations

BATCH = 100


def files_of(sb, account_id: str) -> list[tuple[str, str]]:
    rows = sb.rpc("account_deletion_files", {"p_account": account_id}).execute().data or []
    return [(r["bucket"], r["name"]) for r in rows]


def delete_account(sb, account_id: str, dry_run: bool = False) -> dict:
    """{"files": n, "deleted": {table: rows} | None}. Raises on refusal."""
    files = files_of(sb, account_id)
    if dry_run:
        return {"files": len(files), "deleted": None}
    by_bucket: dict[str, list[str]] = {}
    for bucket, name in files:
        by_bucket.setdefault(bucket, []).append(name)
    for bucket, names in by_bucket.items():
        for i in range(0, len(names), BATCH):
            sb.storage.from_(bucket).remove(names[i:i + BATCH])
    deleted = sb.rpc("delete_trial_account", {"p_account": account_id}).execute().data
    return {"files": len(files), "deleted": deleted}
