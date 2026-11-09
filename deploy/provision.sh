#!/usr/bin/env bash
# deploy/provision.sh — S50: create RECOSA's production resources on
# Scaleway (runbook steps A3–A5) with the scw CLI, in the Recosa project only.
#
#   bash deploy/provision.sh            # shows what it would create
#   bash deploy/provision.sh --apply    # creates it (this costs money)
#
# Creates, in fr-par (Paris), each tagged "recosa" and named "recosa-prod*":
#   - a security group: inbound dropped except SSH from ADMIN_IP, HTTP(S) and
#     HTTP/3 from anywhere (runbook A4 — Docker bypasses the host firewall,
#     so this is the real perimeter);
#   - a flexible public IPv4;
#   - the instance: Ubuntu 24.04, TYPE (default BASIC3-X2C-8G, 2 vCPU / 8 GB),
#     a 40 GB block volume; the project's SSH key is installed by Scaleway;
#   - a private Object Storage bucket for the nightly backups.
#
# Safe to run again: anything that already exists (by name, in the project)
# is reused, not duplicated. Nothing outside PROJECT_ID is read or touched —
# the CLI's key (IAM application RECOSA) cannot reach other projects anyway.
#
# Not done here (Scaleway's CLI has no command for it, or it is yours):
#   - the bucket's 35-day expiry rule (console: bucket → Lifecycle rules);
#   - the API key for backups (A6), DNS (A7), Brevo SMTP key (A8), the deploy
#     key (A9) — see docs/S50_RUNBOOK.md.

set -euo pipefail

APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true

ZONE="${ZONE:-fr-par-1}"
REGION="${REGION:-fr-par}"
TYPE="${TYPE:-BASIC3-X2C-8G}"
DISK_GB="${DISK_GB:-40}"
NAME="${NAME:-recosa-prod}"
BUCKET="${BUCKET:-recosa-prod-backups}"

# scw prints a permissions warning on stdout on some machines; keep it out of
# the values read below.
scwq() { scw "$@" 2>/dev/null | { grep -v -e '^WARNING:' -e '^You can fix it' || true; }; }

PROJECT_ID="${PROJECT_ID:-$(scwq config get default-project-id)}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "No PROJECT_ID (and no default project in the scw config)." >&2; exit 1
fi
PROJECT_NAME="$(scwq account project get project-id="$PROJECT_ID" -o template='{{ .Name }}' || true)"
if [[ "$PROJECT_NAME" != "Recosa" ]]; then
  echo "PROJECT_ID $PROJECT_ID is \"$PROJECT_NAME\", not the Recosa project. Stopping." >&2
  exit 1
fi

ADMIN_IP="${ADMIN_IP:-$(curl -fsS https://api.ipify.org || true)}"
if [[ ! "$ADMIN_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Could not work out your public IP; set ADMIN_IP=a.b.c.d (SSH will only be open to it)." >&2
  exit 1
fi

run() {
  if $APPLY; then "$@"; else echo "  would run: $*"; fi
}

find_id() {   # find_id <scw list args…> name=<n> : the first match's ID, or nothing
  scwq "$@" project-id="$PROJECT_ID" -o template='{{ .ID }}' | head -n1
}

PRICE="$(scwq instance server-type get zone="$ZONE" name="$TYPE" -o template='{{ .HourlyPrice }}' || true)"

echo "Project:   Recosa ($PROJECT_ID), zone $ZONE"
echo "Instance:  $NAME — $TYPE, Ubuntu 24.04, ${DISK_GB} GB disk${PRICE:+ — $PRICE per hour}"
echo "SSH from:  $ADMIN_IP only"
echo "Backups:   bucket $BUCKET ($REGION, private)"
echo
$APPLY || echo "Dry run. Nothing is created; run again with --apply to create it."
echo

# ── Security group ──────────────────────────────────────────────────────────
SG_ID="$(find_id instance security-group list zone="$ZONE" name="$NAME")"
if [[ -n "$SG_ID" ]]; then
  echo "Security group: exists ($SG_ID)"
else
  echo "Security group: create $NAME"
  if $APPLY; then
    SG_ID="$(scwq instance security-group create zone="$ZONE" project-id="$PROJECT_ID" \
      name="$NAME" stateful=true inbound-default-policy=drop outbound-default-policy=accept \
      tags.0=recosa -o template='{{ .SecurityGroup.ID }}')"
    rule() { scwq instance security-group create-rule zone="$ZONE" security-group-id="$SG_ID" \
      direction=inbound action=accept "$@" >/dev/null; }
    rule protocol=TCP ip-range="$ADMIN_IP/32" dest-port-from=22
    rule protocol=TCP ip-range=0.0.0.0/0 dest-port-from=80
    rule protocol=TCP ip-range=0.0.0.0/0 dest-port-from=443
    rule protocol=UDP ip-range=0.0.0.0/0 dest-port-from=443
    echo "  created $SG_ID: SSH from $ADMIN_IP, 80/443 TCP and 443 UDP from anywhere"
  else
    echo "  would allow: TCP 22 from $ADMIN_IP/32; TCP 80, TCP 443, UDP 443 from anywhere; drop the rest"
  fi
fi

# ── Public IP ───────────────────────────────────────────────────────────────
SERVER_ID="$(find_id instance server list zone="$ZONE" name="$NAME")"
if [[ -n "$SERVER_ID" ]]; then
  echo "Instance: exists ($SERVER_ID)"
  IP="$(scwq instance server get zone="$ZONE" server-id="$SERVER_ID" -o template='{{ range .PublicIPs }}{{ .Address }} {{ end }}')"
else
  echo "Public IP: reserve a flexible IPv4"
  IP_ID=""
  if $APPLY; then
    IP_ID="$(scwq instance ip create zone="$ZONE" project-id="$PROJECT_ID" type=routed_ipv4 \
      tags.0=recosa -o template='{{ .IP.ID }}')"
  fi
  # ── Instance ──────────────────────────────────────────────────────────────
  echo "Instance: create $NAME ($TYPE, ubuntu_noble, ${DISK_GB} GB)"
  if $APPLY; then
    SERVER_ID="$(scwq instance server create zone="$ZONE" project-id="$PROJECT_ID" \
      name="$NAME" type="$TYPE" image=ubuntu_noble root-volume="sbs:${DISK_GB}GB" \
      ip="$IP_ID" security-group-id="$SG_ID" tags.0=recosa tags.1=production \
      -o template='{{ .ID }}')"
    IP="$(scwq instance server get zone="$ZONE" server-id="$SERVER_ID" -o template='{{ range .PublicIPs }}{{ .Address }} {{ end }}')"
    echo "  created $SERVER_ID"
  fi
fi

# ── Backup bucket ───────────────────────────────────────────────────────────
if scwq object bucket get name="$BUCKET" region="$REGION" >/dev/null 2>&1 \
   && [[ -n "$(scwq object bucket get name="$BUCKET" region="$REGION" -o template='{{ .Name }}')" ]]; then
  echo "Bucket: exists ($BUCKET)"
else
  echo "Bucket: create $BUCKET (private)"
  run scwq object bucket create name="$BUCKET" region="$REGION" project-id="$PROJECT_ID" acl=private tags.0=recosa
fi

echo
if $APPLY; then
  echo "Done. Public IP: ${IP:-?}"
  echo "Next (docs/S50_RUNBOOK.md): A5 expiry rule on the bucket, A6–A9, then Part B: ssh root@${IP:-<ip>}"
fi
