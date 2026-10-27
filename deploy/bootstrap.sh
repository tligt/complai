#!/usr/bin/env bash
# deploy/bootstrap.sh — prepares a fresh Scaleway instance for RECOSA (S50).
#
# Run once, as root, on Ubuntu 24.04 LTS, AFTER the repository is cloned to
# /opt/recosa/app and deploy/.env is filled in (runbook steps 3–4):
#
#     sudo bash /opt/recosa/app/deploy/bootstrap.sh
#
# It installs Docker from Docker's own apt repository (Compose 2.24.4+ is
# needed for `!override` in supabase.override.yml), fetches the self-hosted
# Supabase stack at a pinned commit, generates its secrets, installs the jobs
# crontab DISABLED, and turns on automatic security updates. It starts
# nothing: the runbook brings the stacks up and checks them one at a time.
#
# Safe to run again: each step checks whether it is already done.

set -euo pipefail

ROOT=/opt/recosa
APP=$ROOT/app
SUPA=$ROOT/supabase
# The Supabase commit this deployment runs. Empty on the first install: the
# script then takes the current master and prints the commit to record here
# (and in docs/SPRINT_LOG.md). Upgrading Supabase = changing this, deliberately.
SUPABASE_REF="${SUPABASE_REF:-}"

[ "$(id -u)" = 0 ] || { echo "Run as root."; exit 1; }
[ -f "$APP/deploy/.env" ] || { echo "Fill in $APP/deploy/.env first (copy .env.example)."; exit 1; }

echo "== System updates and base packages"
apt-get update -q
DEBIAN_FRONTEND=noninteractive apt-get upgrade -yq
DEBIAN_FRONTEND=noninteractive apt-get install -yq ca-certificates curl git unattended-upgrades \
    postgresql-client rclone
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "== Docker (official repository)"
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -yq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
docker compose version

echo "== Self-hosted Supabase"
if [ ! -d "$SUPA/.git" ]; then
    git clone --filter=blob:none --no-checkout https://github.com/supabase/supabase "$SUPA"
    git -C "$SUPA" sparse-checkout set docker
fi
git -C "$SUPA" fetch -q origin
git -C "$SUPA" checkout -q "${SUPABASE_REF:-origin/master}"
echo "   Supabase commit: $(git -C "$SUPA" rev-parse HEAD)   <- record this as SUPABASE_REF"
cp "$APP/deploy/supabase.override.yml" "$SUPA/docker/docker-compose.override.yml"
# Edge Functions: the self-hosted runtime serves every folder in
# volumes/functions. RECOSA has one, the public Compliance Pulse feed.
mkdir -p "$SUPA/docker/volumes/functions"
cp -r "$APP/supabase/functions/compliance-pulse" "$SUPA/docker/volumes/functions/"
if [ ! -f "$SUPA/docker/.env" ]; then
    python3 "$APP/deploy/supabase_env.py" "$SUPA/docker"
    echo "   ^ copy SUPABASE_KEY and SUPABASE_SERVICE_KEY into $APP/deploy/.env"
fi

echo "== Jobs crontab (installed disabled — enabled at cutover)"
mkdir -p /var/log/recosa
install -m 0644 "$APP/deploy/crontab" /etc/cron.d/recosa.disabled
cat > /etc/logrotate.d/recosa <<'EOF'
/var/log/recosa/*.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
}
EOF
chmod 0755 "$APP/deploy/backup.sh"

echo
echo "Done. Next: runbook step 6 (start Supabase)."
