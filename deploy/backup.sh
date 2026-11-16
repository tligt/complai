#!/usr/bin/env bash
# deploy/backup.sh — nightly backup to Scaleway Object Storage (S50).
#
# Three things, each a single file named by date:
#   db/       pg_dump of the whole database (custom format: restore with
#             pg_restore, one table at a time if needed)
#   storage/  the Supabase storage volume — the uploaded and generated files
#   qdrant/   a snapshot of the knowledge-base collection
#
# Runs from /etc/cron.d/recosa at 02:30 UTC. Old backups are removed by a
# lifecycle rule on the bucket (runbook: expire after 35 days), not here, so a
# broken script can never delete backups.
#
# Restore is described in docs/S50_RUNBOOK.md, "Restoring from a backup" —
# test it once before go-live, a backup never restored is a hope.

set -euo pipefail

APP=/opt/recosa/app
SUPA=/opt/recosa/supabase/docker
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

set -a; . "$APP/deploy/.env"; set +a
PGPASS=$(grep '^POSTGRES_PASSWORD=' "$SUPA/.env" | cut -d= -f2-)

# rclone reads its remote from the environment — no config file holding keys.
export RCLONE_CONFIG_SCW_TYPE=s3
export RCLONE_CONFIG_SCW_PROVIDER=Scaleway
export RCLONE_CONFIG_SCW_ACCESS_KEY_ID="$SCW_ACCESS_KEY"
export RCLONE_CONFIG_SCW_SECRET_ACCESS_KEY="$SCW_SECRET_KEY"
export RCLONE_CONFIG_SCW_REGION="$SCW_REGION"
export RCLONE_CONFIG_SCW_ENDPOINT="s3.$SCW_REGION.scw.cloud"

echo "== $STAMP database"
docker exec -e PGPASSWORD="$PGPASS" supabase-db \
    pg_dump -U postgres -d postgres -Fc > "$WORK/recosa-$STAMP.dump"
rclone copyto "$WORK/recosa-$STAMP.dump" "scw:$BACKUP_BUCKET/db/recosa-$STAMP.dump"

echo "== $STAMP storage files"
tar -C "$SUPA/volumes" -czf "$WORK/storage-$STAMP.tar.gz" storage
rclone copyto "$WORK/storage-$STAMP.tar.gz" "scw:$BACKUP_BUCKET/storage/storage-$STAMP.tar.gz"

echo "== $STAMP qdrant snapshot"
# Through the app image (it has curl; the Qdrant image may not), on the
# internal network where Qdrant listens.
cd "$APP/deploy"
QAPI="$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots"
q() { docker compose run --rm -T jobs curl -fsS -H "api-key: $QDRANT_API_KEY" "$@"; }
SNAP=$(q -X POST "$QAPI" | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["name"])')
q "$QAPI/$SNAP" > "$WORK/$SNAP"
rclone copyto "$WORK/$SNAP" "scw:$BACKUP_BUCKET/qdrant/$SNAP"
q -X DELETE "$QAPI/$SNAP" >/dev/null

echo "== $STAMP done"
