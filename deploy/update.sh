#!/usr/bin/env bash
# deploy/update.sh — deploys the latest main on the server (S50). Replaces
# Streamlit Cloud's deploy-on-push: after a push, run on the server
#
#     sudo bash /opt/recosa/app/deploy/update.sh
#
# Pulls, rebuilds the image (the pip layer is cached unless requirements.txt
# changed), and restarts the apps one after the other. Each Streamlit app is
# down for the few seconds its container takes to start — users see the
# "connecting" banner and carry on.

set -euo pipefail
cd /opt/recosa/app
# D-212: the pull can change this very script, and bash goes on reading the
# old one from where it was. So pull, then start again on the new copy.
if [ "${RECOSA_UPDATE_PULLED:-}" != "1" ]; then
  git pull --ff-only
  RECOSA_UPDATE_PULLED=1 exec bash /opt/recosa/app/deploy/update.sh "$@"
fi
git log --oneline -1

cd deploy
# D-209: journal limits for the apps' logs (they go to journald).
if ! cmp -s journald-recosa.conf /etc/systemd/journald.conf.d/recosa.conf; then
  install -D -m 644 journald-recosa.conf /etc/systemd/journald.conf.d/recosa.conf
  systemctl restart systemd-journald
fi
# D-212: the jobs' crontab, so a new job goes live with its code.
if ! cmp -s crontab /etc/cron.d/recosa; then
  install -m 0644 crontab /etc/cron.d/recosa
fi
docker compose build
docker compose up -d --no-deps app admin quiz
# Caddyfile changes: a bind-mounted file does not recreate the container.
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
docker compose ps
