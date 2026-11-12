#!/usr/bin/env bash
# deploy/migrate/migrate_reference.sh — a CLEAN production database (D-172).
#
# Like migrate_db.sh, but copies the schema and only the reference data:
# what RECOSA needs to work, nothing a customer or a test user wrote. The
# dev project (Supabase Cloud) stays the dev environment; production starts
# with no accounts, companies or incidents.
#
#     OLD_DB_URL='postgresql://postgres.<ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:5432/postgres' \
#         bash migrate_reference.sh
#
# Read-only on the old side. Expects an EMPTY self-hosted stack.
# The schema comes from the Supabase CLI (roles and schema, as migrate_db.sh);
# the data from pg_dump 17 inside the supabase-db container, table by table.

set -euo pipefail
: "${OLD_DB_URL:?set OLD_DB_URL — see the header}"

# Reference tables: templates, the obligation and vendor catalogues, the
# reference values, countries, monitoring sources and the regulatory feed
# (so a new customer sees the alert history). Not copied: anything per
# account, company, user or session, logs, leads, marketing (stays in dev).
TABLES="public.reference_values public.catalogue_principles public.country_checklists
public.document_templates public.document_template_versions public.monitoring_sources
public.regulatory_updates public.alert_ref_counters public.vendor_catalogue
public.vendor_catalogue_activities public.vendor_domain_patterns storage.buckets"

SUPA=/opt/recosa/supabase/docker
OUT=/opt/recosa/migration
mkdir -p "$OUT"; chmod 700 "$OUT"
cd "$OUT"

echo "== Dumping roles and schema from Supabase Cloud"
supabase db dump --db-url "$OLD_DB_URL" -f roles.sql --role-only
supabase db dump --db-url "$OLD_DB_URL" -f schema.sql

echo "== Dumping the reference data"
args=""
for t in $TABLES; do args="$args --table=$t"; done
docker exec -e OLD_DB_URL="$OLD_DB_URL" supabase-db \
    pg_dump "$OLD_DB_URL" --data-only --no-owner --no-privileges $args > data.sql
ls -l roles.sql schema.sql data.sql

echo "== Restoring into the self-hosted database"
PGPASS=$(grep '^POSTGRES_PASSWORD=' "$SUPA/.env" | cut -d= -f2-)
{
    cat roles.sql schema.sql
    echo "SET session_replication_role = replica;"
    cat data.sql
} | docker exec -i -e PGPASSWORD="$PGPASS" supabase-db \
    psql -U postgres -d postgres --single-transaction -v ON_ERROR_STOP=1 -q

echo "== Comparing the reference tables"
for t in $TABLES; do
    old=$(docker exec supabase-db psql "$OLD_DB_URL" -Atc "select count(*) from $t")
    new=$(docker exec -e PGPASSWORD="$PGPASS" supabase-db psql -U postgres -d postgres -Atc "select count(*) from $t")
    printf '%-40s %6s %6s %s\n' "$t" "$old" "$new" "$([ "$old" = "$new" ] && echo ok || echo DIFFERENT)"
done
docker exec -e PGPASSWORD="$PGPASS" supabase-db psql -U postgres -d postgres -Atc \
    "select 'trigger on_auth_user_created: ' || count(*) from pg_trigger where tgname = 'on_auth_user_created'"
echo "   ^ must be 1: it creates the profile row of every new sign-up."
echo "Done. Keep $OUT until production is checked, then delete it (it holds the schema dump)."
