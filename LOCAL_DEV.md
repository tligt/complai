# Local development

Runs the Streamlit apps on your machine instead of Streamlit Cloud, while
Supabase, GitHub, Qdrant, and Mistral stay exactly where they already are
(in the cloud). Nothing about the deployed apps changes.

## Prerequisites

- Python 3.12+ (tested locally on 3.13; production runs 3.14 per the note
  at the top of `requirements.txt`). **Not 3.11** — `numpy==2.5.1` in
  `requirements.txt` requires Python ≥3.12, so `pip install` fails on
  3.11 with no matching numpy version.
- LibreOffice (system package — needed for the docx→pdf/odt conversion in
  `document_generator.py`)
  - macOS: `brew install --cask libreoffice`
  - Debian/Ubuntu: `sudo apt install libreoffice`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Fill in `.env` with real values, copied from the Streamlit Cloud app's
**Secrets** panel (Manage app → Settings → Secrets) — same key/value
pairs, just `.env` format instead of TOML. `.env` is gitignored; it is
never committed.

## Running

```bash
streamlit run app.py          # client app  — http://localhost:8501
streamlit run admin_app.py    # admin BO    — http://localhost:8502
```

Run on different ports (`--server.port 8502`) if you want both up at
once.

Both apps read `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_SERVICE_KEY`
straight from the environment (no `st.secrets` dependency), so they work
identically locally and on Streamlit Cloud.

## Monitoring scripts

`monitor.py` and `monitor_marketing.py` (normally run by the GitHub
Actions cron jobs) can also be run locally against the same `.env`:

```bash
python monitor.py
python monitor_marketing.py
```

## Database

There is currently **no separate dev/test Supabase project** — local
runs point at the same Supabase project as production. That's fine for
now (no live clients), but worth revisiting once there are:

- Move to a Supabase branch (or a second project) once client data exists
  that local testing shouldn't touch.
- Branching requires a paid Supabase plan, the Supabase CLI, and —
  importantly — an actual migrations history, which this repo doesn't
  have yet (schema changes so far have been applied ad hoc). Migrations
  would need to be written down first for branching to be useful.
