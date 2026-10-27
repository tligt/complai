# S50 — Moving RECOSA to Scaleway: runbook

*Prepared 27 Oct 2026 (D-125). Decisions behind it: D-66 to D-69 — European
infrastructure before beta, self-hosted Supabase, Streamlit kept.*

Everything RECOSA runs moves to **one Scaleway instance in Paris**. What
changes, and what doesn't:

| Today | After S50 |
|---|---|
| Streamlit Community Cloud (Snowflake, US) — 3 apps | 3 containers on the instance |
| Supabase Cloud (Delaware; Frankfurt on AWS) | Self-hosted Supabase on the instance — same client library, same RLS, same SQL |
| Qdrant Cloud (AWS eu-central-1) | Qdrant container on the instance |
| GitHub Actions cron (Microsoft, US) | Host crontab on the instance |
| — (no backups of our own) | Nightly backup to Scaleway Object Storage, Paris |
| Mistral (FR), Brevo (FR) | Unchanged |

GitHub keeps hosting the **code** only; no client data passes through it.

What it moves today (measured 27 Oct): a 19 MB database, 148 files (6.3 MB),
1 user account, 4,890 knowledge-base points. Small — the work is in getting
the stack right, not in the copy.

The files referred to below are in `deploy/`.

---

## Part A — what you do (needs your accounts)

These need an account, a payment method or a DNS login, so they are yours.
Each says exactly what to note down for Part B.

**A1. Scaleway account.** Create the organisation, add the payment method,
turn on two-factor authentication. Note nothing.

**A2. SSH key.** Console → Project → Credentials → SSH keys → add your public
key (`~/.ssh/id_ed25519.pub`; create one with `ssh-keygen -t ed25519` if
needed).

**A3. Instance.** Console → Instances → Create:
- Zone: **Paris** (`fr-par-1` or `fr-par-2`).
- Type: **8 GB RAM, 2–4 vCPU** at least (the Supabase stack is about ten
  containers, plus three Streamlit apps and LibreOffice). A *Production
  Optimized* or *Cost Optimized* type in that range; check the current price
  list.
- Image: **Ubuntu 24.04 LTS**.
- Disk: **40 GB** or more (Block Storage).
- Public IPv4: yes (flexible IP).

→ Note the **public IP**.

**A4. Security group** (Instances → Security groups), attached to the
instance. Default policy *drop* inbound, and allow:
- TCP 22 from **your IP only**;
- TCP 80 and TCP 443 from anywhere;
- UDP 443 from anywhere (HTTP/3).

This is the real perimeter: Docker bypasses the instance's own firewall.

**A5. Object Storage bucket** for backups. Object Storage → Create bucket,
region **Paris**, *private*. Then Bucket settings → Lifecycle rules → expire
objects after **35 days**.

→ Note the **bucket name**.

**A6. API key for backups.** Project → Credentials → API keys → Generate,
scoped to **Object Storage** only.

→ Note the **access key** and **secret key**.

**A7. DNS.** Where recosa.eu's DNS is managed, add four **A records** to the
instance's IP: `app`, `admin`, `check`, `api` (the names can change in
`deploy/.env`). TTL 300 s, so a rollback is quick.

**A8. Brevo SMTP key.** Brevo → SMTP & API → SMTP → generate a key. It
sends Supabase's own emails (sign-up confirmation, password reset).

→ Note the **SMTP login** and **key**.

**A9. Read access to the repository.** GitHub → the repository → Settings →
Deploy keys → add a **read-only** key generated on the instance (step B2).

**A10. From the current setup, for the copy:**
- Streamlit Cloud → client app → Settings → **Secrets** (all values).
- Supabase dashboard → Connect → **Session pooler** connection string, and
  the **database password**.
- Supabase dashboard → Authentication → Sign In / Providers → Email:
  whether **Confirm email** is on.
- Qdrant Cloud console → the cluster's **version**.

---

## Part B — on the server

All commands as root (`sudo -i`). Each step ends with a check; stop at the
first one that fails.

**B1. Log in.** `ssh root@<ip>` (or `ubuntu@` then `sudo -i`).

**B2. Clone the code.**
```
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N ""
cat ~/.ssh/github_deploy.pub        # → GitHub deploy key (A9)
mkdir -p /opt/recosa
GIT_SSH_COMMAND="ssh -i ~/.ssh/github_deploy" git clone git@github.com:<owner>/complai.git /opt/recosa/app
git -C /opt/recosa/app config core.sshCommand "ssh -i ~/.ssh/github_deploy"
```

**B3. Settings.** `cp /opt/recosa/app/deploy/.env.example /opt/recosa/app/deploy/.env`,
then fill it in from Part A and the Streamlit secrets. Leave `SUPABASE_KEY`
and `SUPABASE_SERVICE_KEY` empty for now. `chmod 600` it.

**B4. Bootstrap.** `bash /opt/recosa/app/deploy/bootstrap.sh`
- Installs Docker, fetches Supabase, generates its secrets, installs the jobs
  crontab disabled.
- **Record** the printed Supabase commit as `SUPABASE_REF` (top of
  `bootstrap.sh`) and commit that change.
- **Copy** the two printed keys into `deploy/.env`.

**B5. Start Supabase.**
```
cd /opt/recosa/supabase/docker
docker compose pull && docker compose up -d
docker compose ps                     # all healthy (give it 2 minutes)
ss -tlnp | grep -v 127.0.0.1          # only :22 — nothing else public yet
```
If `ss` shows anything besides 22 (and later 80/443), a service name in
`supabase.override.yml` no longer matches the Supabase version: fix the
override before going further.

**B6. Start RECOSA.**
```
cd /opt/recosa/app/deploy
docker compose build && docker compose up -d
docker compose ps
```
Check: `https://app.<domain>` shows the login page with a valid certificate
(Caddy gets it on first request; DNS must already point here). `https://api.<domain>/`
answers *Not found* (Studio is not public — correct).

To open Supabase Studio: `ssh -L 8000:127.0.0.1:8000 root@<ip>`, then
http://localhost:8000 with `DASHBOARD_USERNAME` / `DASHBOARD_PASSWORD` from
`/opt/recosa/supabase/docker/.env`.

**B7. Supabase CLI** (for the database copy). Install the `.deb` from
github.com/supabase/cli/releases (`dpkg -i supabase_<version>_linux_amd64.deb`),
`supabase --version`.

### Rehearsal copy

**B8. Database.**
```
OLD_DB_URL='<session pooler string with the password>' bash /opt/recosa/app/deploy/migrate/migrate_db.sh
```
Ends with "All N tables match" and the trigger count 1.

**B9. Files.**
```
cd /opt/recosa/app/deploy
docker compose run --rm -T -e OLD_SUPABASE_URL=https://<ref>.supabase.co \
  -e OLD_SUPABASE_SERVICE_KEY=<old service key> -v ./migrate:/migrate jobs python /migrate/copy_storage.py
```
Expect: compliance-files 141, audit-reports 7, "sizes match".

**B10. Knowledge base.**
```
docker compose run --rm -T -e OLD_QDRANT_URL=<old url> -e OLD_QDRANT_API_KEY=<old key> \
  -v ./migrate:/migrate jobs python /migrate/copy_qdrant.py
```
Expect: "Old: 4890 points, new: 4890." (tested 27 Oct against the live
collection).

### Tests on the new server

**B11.** Log in on `https://app.<domain>` with your usual password (password
hashes move with the database; sessions don't, so everyone logs in once).
Then:
- Home figures match the old app (GDPR 68%, NIS2 40%, AI Act 6% on 27 Oct).
- Documents → download a document in force (signed URL through `api.`).
- Generate a document and download its **PDF** (LibreOffice in the image).
- Assistant answers with sources (Qdrant + Mistral).
- Sign up with a second address → the confirmation email arrives (Brevo
  SMTP), the link works, the free check starts.
- Account → "forgot password" email, if enabled in S51.
- `https://admin.<domain>` loads; `https://check.<domain>` runs a free check.
- Jobs, one at a time (they write to the new database only; until cutover
  its data is a copy, so the only person they can email is you):
  `docker compose run --rm -T jobs python monitor_incidents.py`, then
  `monitor_funnel.py`, `monitor_audits.py`, `monitor.py`, `monitor_marketing.py`.

**B12. Backup, and restore once.**
`bash /opt/recosa/app/deploy/backup.sh` → three files in the bucket. Then
follow *Restoring from a backup* below into a scratch database
(`createdb restore_test`) and compare a few counts. Drop it afterwards.

---

## Part C — cutover (about one hour, announced in advance)

**C1. Freeze**, so nothing more is written to the old project:
- Take the three Streamlit Cloud apps offline. Either restrict who can view
  them (app → Settings → Sharing), or delete them; they redeploy from the
  repository in minutes if you roll back.
- In GitHub → Actions, disable the four scheduled workflows (audit, funnel,
  incident reminders, regulatory).

**C2. Reset the new stack** so the final copy starts clean (keeps
`.env`, so keys and secrets stay valid):
```
cd /opt/recosa/supabase/docker && docker compose down
rm -rf volumes/db/data volumes/storage
docker compose up -d
```
Qdrant stays as it is, unless documents were added to the knowledge base
since B10.

**C3. Final copy.** B8 and B9 again (B10 only if documents were added to the
knowledge base since).

**C4. Switch the jobs on.** `mv /etc/cron.d/recosa.disabled /etc/cron.d/recosa`

**C5. Links.** On the Framer site, point the app, sign-up and free-check
links to the new names. Brevo templates and `APP_BASE_URL` already use the
new app name.

**C6. Check.** B11's list, briefly. Then announce.

**C7. Afterwards** (code changes, done in the repo with Claude):
- Remove the `schedule:` triggers from the GitHub workflows.
- Update `LOCAL_DEV.md`, the `requirements.txt` header and the Streamlit
  Cloud references.
- D-66: the marketing claim can become "hosted in France, no US cloud
  provider" once the old projects are deleted.

**C8. After 30 days without a rollback:** delete the Supabase Cloud project,
the Qdrant Cloud cluster and the three Streamlit Cloud apps.

### Rollback

Until C8 the old setup is intact. To go back: un-pause the Streamlit apps,
re-enable the GitHub workflows, rename the cron file back to
`recosa.disabled`, and restore the Framer links. Anything written on the new
server since cutover stays there — copy it back by hand if needed.

---

## Running it

- **Deploying a change:** push to main, then on the server
  `bash /opt/recosa/app/deploy/update.sh`.
- **Logs:** `docker compose logs -f app` (or `admin`, `quiz`, `caddy`) in
  `deploy/`; jobs in `/var/log/recosa/`.
- **Supabase upgrade:** change `SUPABASE_REF` in `bootstrap.sh` to a newer
  commit, run it, `docker compose pull && up -d` in the Supabase directory,
  re-run B5's `ss` check. One upgrade at a time, after a backup.
- **Security updates** install themselves (unattended-upgrades); reboot
  when `/var/run/reboot-required` exists.

## Restoring from a backup

```
rclone ls scw:<bucket>/db                       # rclone env from backup.sh
rclone copyto scw:<bucket>/db/recosa-<stamp>.dump /tmp/r.dump
docker cp /tmp/r.dump supabase-db:/tmp/r.dump
docker exec supabase-db pg_restore -U postgres -d postgres --clean --if-exists /tmp/r.dump
```
Storage: stop Supabase, replace `volumes/storage` with the archive's
`storage/` folder, start. Qdrant: upload the snapshot through the Qdrant API
(`PUT /collections/<name>/snapshots/upload`).
