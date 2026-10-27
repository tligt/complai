# _unused — files no part of RECOSA uses any more

Moved here on 27 Oct 2026 to be reviewed and deleted later. Nothing imports
them: checked by following every import and page path from `app.py`,
`admin_app.py`, `quiz/quiz_app.py` and the GitHub workflows.

| File | What it was | Why it is here |
|---|---|---|
| `pages_admin/admin_monitoring.py` | Old monitoring page | Replaced by `pages_admin/monitoring.py` |
| `pages_admin/monitoring_admin.py` | Older copy of the same | Replaced by `pages_admin/monitoring.py` |
| `pages_admin/admin_dashboard.py` | Old "Client Dashboard" | Replaced by `pages_admin/dashboard.py` |
| `pages_admin/admin_home.py` | Old admin home | Replaced by `pages_admin/home.py` |
| `pages_admin/templates.py` | Read-only template viewer (S25) | Not in the admin menu. Re-register it in `admin_app.py` if it is still wanted |
| `colab_rebuild_v2.py` | Colab notebook for the June knowledge-base rebuild (Sprint 7) | One-off |
| `ingest.py` | First knowledge-base load into Qdrant | One-off, June; the KB page in the admin app ingests now |
| `fix_log_strip.py` | Repair script for an accidental find-and-replace (3 Aug) | One-off, done |
| `SPRINT_LOG.md`, `scope/SPRINT_LOG.md` | Copies of the sprint log frozen in September | The live one is `docs/SPRINT_LOG.md` |
| `s29a_scope.md` | An earlier draft of `scope/s29a_scope.md` | Duplicate |
| `scope/scope` | Empty 2-byte file | Stray |

Kept on purpose (not run by the app, but still used by hand): the
`template_seed*.py` and `inventory_seed.py` authoring scripts, the
`migration_*.sql` and `seed_*.sql` files, and `test_template_renderer.py`.
