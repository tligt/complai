# S49 — Monitoring source management (admin BO)

**Priority: low.** Nothing here blocks the beta gate at S33. It is admin-only,
and the immediate incident has been corrected by hand. Scheduled so it does not
get rediscovered as an emergency.

**Sequencing note:** overlaps S34 (regulatory update → impact re-scoring) and
the carried Compliance Pulse content fixes, which touch the same subsystem and
the same admin pages. If S34 is picked up first, fold this in rather than
running them separately — two sprints editing the same page in sequence is how
one of them silently reverts the other.

---

## What happened

The monitoring page at `complai-bo.streamlit.app` shows "Active" beside each
source. It reads as a status badge. It is a control: clicking it deactivates
the source, which then disappears from the list with no confirmation, no undo,
and no indication of where it went.

A source was deactivated by accident and had to be restored by hand in
Postgres.

The row was never lost — the codebase retires rather than deletes, consistent
with the append-only vocabulary rule. But a row that is real in Postgres and
invisible in the UI is indistinguishable from a deleted one to the person
looking at the screen, which is the actual defect.

## The second, quieter problem

Several marketing sources carry no URL. The monitor presumably skips them.

They are not sources the monitor "skips" — they are rows that should not have
been insertable. They sit in the list looking configured, contribute nothing,
and nothing on the page says so. Same failure shape as the toggle: state that
is real in the database and not legible in the interface.

This one is worse than the toggle, because it fails silently and permanently
rather than loudly and once.

---

## Scope

**1. Toggle safety**
- Confirmation before deactivating. Naming the source in the prompt, not a
  generic "are you sure".
- Deactivated sources stay visible, greyed, with a Reactivate control — rather
  than vanishing. Retiring is not deleting and the UI should not imply it is.
- Distinguish the control from a status badge visually. If it shows state and
  changes state, it must look like a switch.
- Write deactivation to the S21 audit trail. `log_audit_event()` already exists
  and this is exactly the class of change it was built for.

**2. Editable sources**
- Edit name, URL, cadence, language, and type in place. Currently impossible.
- Add a source through the UI, not only through SQL.

**3. Incomplete sources cannot hide**
- A source with no URL is either invalid or is a kind that does not need one.
  Decide which — this is a schema question, not a UI one.
  - If every source needs a URL: `NOT NULL`, plus a migration deciding what
    happens to the existing marketing rows. They are RECOSA's own data, so a
    migration may edit them; that is not the S24 client-data situation.
  - If some kinds legitimately have none: a `source_kind` vocabulary and a
    CHECK that URL is present for the kinds that require it. Structural
    constraint in the database, not a validation rule in the page — the S24
    lesson about Art. 9 conditions.
- Surface what the last monitoring run skipped and why. A source that produced
  nothing should say whether it was inactive, malformed, unreachable, or simply
  had no new items. `url_validation.py` and the `url_flagged` status from S20
  already carry some of this; it is not shown.

**4. Untangle `pages_admin/`**
- Three monitoring modules with duplicate page names, one wired into
  `admin_app.py`. Edits can land in a file Streamlit never loads.
- Resolve before doing any of the above, or the above may not take effect.

---

## Principle this belongs to

An unanswered question is a gap, not an error (S24). A source with no URL is a
gap in the configuration — it should be recorded, surfaced, and fixable, not
silently ignored at run time.

And its counterpart, which this incident adds: **a state change the interface
does not show is indistinguishable from data loss.** Retiring rather than
deleting only protects the data. It does not protect the person looking at the
screen, and it was never meant to.

---

## To scope properly

- `pages_admin/` — the monitoring module actually wired into `admin_app.py`
- The monitoring source table schema
- Whether the marketing sources without URLs are a distinct kind or simply
  incomplete rows. This decides section 3 and is the only genuinely open
  question here.
