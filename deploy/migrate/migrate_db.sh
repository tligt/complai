#!/usr/bin/env bash
# deploy/migrate/migrate_db.sh — copies the database from Supabase Cloud to the
# self-hosted stack (S50). Follows Supabase's documented CLI method: roles,
# then schema, then data with triggers off, in one transaction.
#
#     OLD_DB_URL='postgresql://postgres.<ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres' \
#         bash migrate_db.sh
#
# OLD_DB_URL: Supabase dashboard → Connect → Session pooler (port 5432), with
# the database password. Quote it: it contains characters the shell eats.
#
# Needs the Supabase CLI on the host (runbook step 7). Read-only on the old
# side; on the new side it expects an EMPTY stack (first start, nothing
# written) — run it again only after resetting the stack (runbook).
#
# Ends by comparing row counts, table by table, old against new, and exits
# non-zero on any difference.

set -euo pipefail
: "${OLD_DB_URL:?set OLD_DB_URL — see the header}"

SUPA=/opt/recosa/supabase/docker
OUT=/opt/recosa/migration
mkdir -p "$OUT"; chmod 700 "$OUT"
cd "$OUT"

echo "== Dumping from Supabase Cloud"
supabase db dump --db-url "$OLD_DB_URL" -f roles.sql --role-only
supabase db dump --db-url "$OLD_DB_URL" -f schema.sql
supabase db dump --db-url "$OLD_DB_URL" -f data.sql --use-copy --data-only
ls -l roles.sql schema.sql data.sql

echo "== Restoring into the self-hosted database"
PGPASS=$(grep '^POSTGRES_PASSWORD=' "$SUPA/.env" | cut -d= -f2-)
{
    cat roles.sql schema.sql
    echo "SET session_replication_role = replica;"
    cat data.sql
} | docker exec -i -e PGPASSWORD="$PGPASS" supabase-db \
    psql -U postgres -d postgres --single-transaction -v ON_ERROR_STOP=1 -q

echo "== Comparing row counts"
COUNT_SQL="select format('%s.%s', schemaname, relname) from pg_stat_user_tables
           where schemaname in ('public','auth','storage') order by 1"
count_all() {  # $1 = psql command prefix
    for t in $($1 -Atc "$COUNT_SQL"); do
        printf '%s %s\n' "$t" "$($1 -Atc "select count(*) from $t")"
    done
}
count_all "psql $OLD_DB_URL" > counts_old.txt
count_all "docker exec -e PGPASSWORD=$PGPASS supabase-db psql -U postgres -d postgres" > counts_new.txt
if diff counts_old.txt counts_new.txt; then
    echo "All $(wc -l < counts_old.txt) tables match."
else
    echo "Row counts differ (old < > new) — do not cut over."; exit 1
fi

echo "== Checks the counts cannot make"
docker exec -e PGPASSWORD="$PGPASS" supabase-db psql -U postgres -d postgres -Atc \
    "select 'trigger on_auth_user_created: ' || count(*) from pg_trigger where tgname = 'on_auth_user_created'"
echo "   ^ must be 1: it creates the profile row of every new sign-up."
