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
git pull --ff-only
git log --oneline -1

cd deploy
docker compose build
docker compose up -d --no-deps app admin quiz
# Caddyfile changes: a bind-mounted file does not recreate the container.
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
docker compose ps
