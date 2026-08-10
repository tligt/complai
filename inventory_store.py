"""
inventory_store.py — reads and writes for the S24 inventory.

── Why the diff is done by ID, not by the editor's delta ──────────────────
st.data_editor exposes its changes through st.session_state[key] as
`edited_rows` (keyed by *position*), `added_rows` and `deleted_rows` (also
positions). Using that delta directly has three failure modes here:

  1. Positions are not identities. Add a sort control, a "show only vendors
     missing a DPA" filter, or a rerun that re-fetches in a different order,
     and position 7 is a different vendor than it was when the user clicked.

  2. The delta outlives the data. The session-state entry persists across
     reruns, so a stale delta can reapply against rows that have moved. This
     fails silently: no exception, just a vendor whose DPA status changed on
     its own.

  3. Deleting an added row leaves the position bookkeeping ambiguous.

None of that is necessary, because st.data_editor also *returns* the edited
frame — and if the frame carries the row id, the diff can be computed by
comparing the returned frame against the frame that was passed in. Rows
present in both with changed values are updates; ids missing from the return
are deletes; rows with no id are inserts. Positions never enter into it, so
sorting and filtering are free.

The id column is hidden from the client via column_config={"id": None},
which suppresses display while keeping the column in the returned data.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from database import get_supabase
import inventory as INV


# Columns the client may edit in the systems grid. Anything outside this set
# is ignored on write even if it somehow appears in the frame — the grid is
# not the only way rows are created, and an unexpected column arriving from a
# stale session should not reach the database.
SYSTEM_EDITABLE = (
    "name", "vendor_legal_name", "category", "purpose",
    "processing_country", "transfer_mechanism",
    "dpa_status", "dpa_signed_on", "dpa_url",
    "criticality", "ai_role", "sets_cookies",
    "privacy_policy_url", "notes",
)

ACTIVITY_EDITABLE = (
    "name", "purpose", "legal_basis", "legitimate_interest_note",
    "controller_role", "data_subject_categories", "data_categories",
    "special_categories", "art9_condition", "criminal_data",
    "retention_period", "retention_basis", "security_measures", "notes",
)


# ── Reads ─────────────────────────────────────────────────────────────────

def load_systems(user_id: str, client_id: str | None = None) -> list[dict]:
    try:
        q = (
            get_supabase().table("systems")
            .select("*").eq("user_id", user_id).order("name")
        )
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []


def load_activities(user_id: str, client_id: str | None = None) -> list[dict]:
    try:
        q = (
            get_supabase().table("processing_activities")
            .select("*").eq("user_id", user_id).order("name")
        )
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []


def load_links(user_id: str, client_id: str | None = None) -> list[dict]:
    try:
        q = (
            get_supabase().table("activity_systems")
            .select("*").eq("user_id", user_id)
        )
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []


def systems_for_activity(links: list[dict], activity_id: str) -> list[str]:
    return [l["system_id"] for l in links if l["activity_id"] == activity_id]


# ── Diff ──────────────────────────────────────────────────────────────────

def _normalise(value: Any) -> Any:
    """
    Make a value comparable across the pandas round trip.

    st.data_editor returns NaN for empty cells, numpy types for numbers, and
    pandas Timestamps for dates. Comparing those directly against what came
    out of PostgREST produces spurious diffs on every render, so every field
    gets flattened to a plain Python value first.
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


def diff_by_id(
    base_rows: list[dict],
    edited_df: pd.DataFrame,
    editable: tuple[str, ...],
    id_col: str = "id",
) -> tuple[list[dict], list[dict], list[str]]:
    """
    Compare the frame st.data_editor returned against the rows it was given.

    Returns (inserts, updates, delete_ids). Updates carry only the changed
    fields plus the id, so a concurrent change to a field this user did not
    touch is not clobbered.
    """
    base_by_id = {r["id"]: r for r in base_rows}

    inserts: list[dict] = []
    updates: list[dict] = []
    seen_ids: set[str] = set()

    for _, row in edited_df.iterrows():
        raw_id = row.get(id_col)
        row_id = _normalise(raw_id)

        if not row_id:
            # No id: a row the client added in the grid.
            payload = {c: _normalise(row.get(c)) for c in editable if c in edited_df.columns}
            # Streamlit appends a blank row the moment the client clicks the
            # "+" affordance, before anything is typed. Skipping empty rows
            # here is what stops every visit producing a nameless system.
            if any(v not in (None, "", [], False) for v in payload.values()):
                inserts.append(payload)
            continue

        seen_ids.add(row_id)
        original = base_by_id.get(row_id)
        if original is None:
            # An id in the frame that was not in the base rows means the
            # frame is stale — refuse rather than guess.
            continue

        changed = {}
        for col in editable:
            if col not in edited_df.columns:
                continue
            new = _normalise(row.get(col))
            old = _normalise(original.get(col))
            if new != old:
                changed[col] = new

        if changed:
            changed["id"] = row_id
            updates.append(changed)

    delete_ids = [rid for rid in base_by_id if rid not in seen_ids]
    return inserts, updates, delete_ids


# ── Writes ────────────────────────────────────────────────────────────────

def commit_systems(
    base_rows: list[dict],
    edited_df: pd.DataFrame,
    user_id: str,
    client_id: str | None,
) -> dict:
    """
    Apply a systems-grid edit. Returns a result summary; never raises.

    Validation runs per row before any write. Rows that fail are reported and
    skipped, and the valid rows still commit — an SME correcting ten vendors
    should not lose nine of them because the tenth has a contradictory
    transfer claim.
    """
    inserts, updates, delete_ids = diff_by_id(base_rows, edited_df, SYSTEM_EDITABLE)

    result = {"inserted": 0, "updated": 0, "deleted": 0, "errors": []}
    sb = get_supabase()

    for row in inserts:
        row = {**row, "user_id": user_id, "client_id": client_id}
        errs = INV.validate_system(row, scope=client_id)
        if errs:
            result["errors"].append(f"{row.get('name') or 'New system'}: {'; '.join(errs)}")
            continue
        try:
            sb.table("systems").insert(row).execute()
            result["inserted"] += 1
        except Exception as e:
            result["errors"].append(f"{row.get('name')}: {e}")

    base_by_id = {r["id"]: r for r in base_rows}
    for change in updates:
        row_id = change.pop("id")
        merged = {**base_by_id.get(row_id, {}), **change}
        errs = INV.validate_system(merged, scope=client_id)
        if errs:
            result["errors"].append(f"{merged.get('name') or row_id}: {'; '.join(errs)}")
            continue
        try:
            sb.table("systems").update(change).eq("id", row_id).execute()
            result["updated"] += 1
        except Exception as e:
            result["errors"].append(f"{merged.get('name')}: {e}")

    for row_id in delete_ids:
        try:
            # activity_systems cascades. The activities themselves survive:
            # dropping a vendor should not silently delete the RoPA rows that
            # named it, or a client removes a tool and loses their record of
            # the processing it supported.
            sb.table("systems").delete().eq("id", row_id).execute()
            result["deleted"] += 1
        except Exception as e:
            result["errors"].append(f"{base_by_id.get(row_id, {}).get('name', row_id)}: {e}")

    return result


def save_activity(
    row: dict,
    system_ids: list[str],
    user_id: str,
    client_id: str | None,
    activity_id: str | None = None,
) -> tuple[str | None, list[str]]:
    """Insert or update one activity and reconcile its system links."""
    payload = {c: row.get(c) for c in ACTIVITY_EDITABLE}
    payload = {**payload, "user_id": user_id, "client_id": client_id}

    errs = INV.validate_activity(payload, scope=client_id)
    if errs:
        return None, errs

    sb = get_supabase()
    try:
        if activity_id:
            sb.table("processing_activities").update(payload).eq("id", activity_id).execute()
        else:
            res = sb.table("processing_activities").insert(payload).execute()
            activity_id = (res.data or [{}])[0].get("id")
            if not activity_id:
                return None, ["Could not create the activity."]
    except Exception as e:
        return None, [str(e)]

    link_errs = _reconcile_links(activity_id, system_ids, user_id, client_id)
    return activity_id, link_errs


def _reconcile_links(
    activity_id: str,
    system_ids: list[str],
    user_id: str,
    client_id: str | None,
) -> list[str]:
    """Make activity_systems match `system_ids` exactly."""
    sb = get_supabase()
    errors: list[str] = []

    try:
        existing = (
            sb.table("activity_systems").select("id, system_id")
            .eq("activity_id", activity_id).execute().data or []
        )
    except Exception as e:
        return [str(e)]

    have = {r["system_id"]: r["id"] for r in existing}
    want = set(system_ids)

    for system_id in want - set(have):
        try:
            sb.table("activity_systems").insert({
                "user_id": user_id,
                "client_id": client_id,
                "activity_id": activity_id,
                "system_id": system_id,
                "role": "processor",
            }).execute()
        except Exception as e:
            errors.append(str(e))

    for system_id in set(have) - want:
        try:
            sb.table("activity_systems").delete().eq("id", have[system_id]).execute()
        except Exception as e:
            errors.append(str(e))

    return errors


def delete_activity(activity_id: str) -> list[str]:
    try:
        get_supabase().table("processing_activities").delete().eq("id", activity_id).execute()
        return []
    except Exception as e:
        return [str(e)]


# ── Seeding from the catalogue ────────────────────────────────────────────

def seed_from_catalogue(
    catalogue_key: str,
    user_id: str,
    client_id: str | None,
    lang: str = "en",
) -> dict:
    """
    Create a system and its suggested activities from a catalogue entry.

    This is the path that makes the join table earn its keep: Microsoft 365
    seeds four activities and four links from a single tick.

    Not transactional — PostgREST has no multi-statement transaction, so a
    failure partway leaves the system created and some activities missing.
    That is recoverable by hand and by re-running (the unique index on
    (client_id, catalogue_key) makes the system insert idempotent), which is
    a better trade than moving the whole thing into an RPC for a path that
    runs a handful of times per client.
    """
    seeded = INV.seed_rows_for(catalogue_key, lang=lang)
    if seeded is None:
        return {"error": f"Unknown catalogue entry: {catalogue_key}"}

    system_row, activity_rows = seeded
    system_row = {**system_row, "user_id": user_id, "client_id": client_id}

    errs = INV.validate_system(system_row, scope=client_id)
    if errs:
        return {"error": "; ".join(errs)}

    sb = get_supabase()
    try:
        res = sb.table("systems").insert(system_row).execute()
        system_id = (res.data or [{}])[0].get("id")
    except Exception as e:
        # The unique index fires here when the vendor is already present,
        # which is the common case on a second visit rather than an error.
        return {"error": f"{system_row['name']} may already be in your inventory ({e})"}

    created, errors = 0, []
    for a in activity_rows:
        role = a.pop("_system_role", "processor")
        payload = {**a, "user_id": user_id, "client_id": client_id}
        verrs = INV.validate_activity(payload, scope=client_id)
        if verrs:
            # Catalogue defaults omit security measures and the balancing
            # test on purpose — those are client facts, not vendor facts.
            # The activity is still created so the client can complete it;
            # the completeness score is where the gap belongs.
            payload.setdefault("notes", "Seeded from the RECOSA catalogue — please review.")
        try:
            ares = sb.table("processing_activities").insert(payload).execute()
            activity_id = (ares.data or [{}])[0].get("id")
            if activity_id and system_id:
                sb.table("activity_systems").insert({
                    "user_id": user_id,
                    "client_id": client_id,
                    "activity_id": activity_id,
                    "system_id": system_id,
                    "role": role,
                }).execute()
            created += 1
        except Exception as e:
            errors.append(f"{a.get('name')}: {e}")

    return {
        "system_id": system_id,
        "system_name": system_row["name"],
        "activities_created": created,
        "errors": errors,
    }


def already_seeded(systems: list[dict]) -> set[str]:
    return {s["catalogue_key"] for s in systems if s.get("catalogue_key")}


# ── Completeness ──────────────────────────────────────────────────────────
# A lightweight precursor to the S41 field-level score. Reported, not scored:
# the point at this stage is to tell a client what is missing before they
# generate a RoPA that quietly omits it.

def readiness(activities: list[dict], systems: list[dict], links: list[dict]) -> dict:
    linked_activity_ids = {l["activity_id"] for l in links}

    gaps: list[str] = []
    for a in activities:
        missing = []
        if not a.get("legal_basis"):
            missing.append("legal basis")
        if not (a.get("retention_period") or "").strip():
            missing.append("retention period")
        if not a.get("data_categories"):
            missing.append("data categories")
        if not a.get("security_measures"):
            missing.append("security measures")
        if a["id"] not in linked_activity_ids:
            missing.append("no system linked")
        if missing:
            gaps.append(f"{a['name']}: {', '.join(missing)}")

    vendor_gaps = [
        s["name"] for s in systems
        if s.get("dpa_status") in ("none", "unknown", "requested")
    ]

    total = len(activities)
    complete = total - len([g for g in gaps])
    return {
        "activities": total,
        "systems": len(systems),
        "complete_activities": max(complete, 0),
        "activity_gaps": gaps,
        "dpa_gaps": vendor_gaps,
    }
