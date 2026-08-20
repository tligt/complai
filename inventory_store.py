"""
inventory_store.py — reads and writes for the S24 inventory (amended S26).

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

── S26 amendments ─────────────────────────────────────────────────────────
1. Counterparty CRUD. Art. 30(2) requires a processor to name each controller
   it processes for. The table is new; so is the join.

2. Per-link roles. _reconcile_links used to hardcode role='processor' on every
   insert, so every manually linked system was asserted a processor with no
   evidence — a false statement in Art. 30(1)(d). It now takes a mapping and
   defaults to 'unknown', and it UPDATES a role that changed rather than only
   inserting and deleting.

3. readiness() covers the gaps the RoPA actually depends on. It is now a
   pre-generation gate, not just a progress metric: render_template blocks
   only on FieldSpec scalars, and per-activity gaps live inside a block
   renderer where the renderer structurally cannot see them.
"""

from __future__ import annotations

from typing import Any, Mapping

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
    "retention_period", "retention_basis", "security_measures",
    "counterparty_register_note", "notes",
)

COUNTERPARTY_EDITABLE = (
    "legal_name", "trading_name", "contact_name", "contact_email",
    "registered_address", "country",
    "dpa_status", "dpa_signed_on", "dpa_url", "notes",
)

# The role code meaning "we have not confirmed this", added to the system_role
# vocabulary in the S26 migration. Named here rather than inlined so the
# readiness check and the reconcile default cannot drift apart.
ROLE_UNKNOWN = "unknown"

# activity_systems.role values that do not describe a third party. A client's
# own server is not a recipient, so these are excluded from Art. 30(1)(d)
# rather than printed as a recipient category.
NON_RECIPIENT_ROLES = frozenset({"internal"})


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


def load_counterparties(user_id: str, client_id: str | None = None) -> list[dict]:
    """Controllers on whose behalf this client processes (Art. 30(2)(a))."""
    try:
        q = (
            get_supabase().table("processing_counterparties")
            .select("*").eq("user_id", user_id).order("legal_name")
        )
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []


def load_counterparty_links(user_id: str, client_id: str | None = None) -> list[dict]:
    try:
        q = (
            get_supabase().table("activity_counterparties")
            .select("*").eq("user_id", user_id)
        )
        if client_id:
            q = q.eq("client_id", client_id)
        return q.execute().data or []
    except Exception:
        return []


def systems_for_activity(links: list[dict], activity_id: str) -> list[str]:
    return [l["system_id"] for l in links if l["activity_id"] == activity_id]


def roles_for_activity(links: list[dict], activity_id: str) -> dict[str, str]:
    """system_id -> role, for one activity. Feeds the per-link role controls."""
    return {
        l["system_id"]: (l.get("role") or ROLE_UNKNOWN)
        for l in links if l["activity_id"] == activity_id
    }


def counterparties_for_activity(links: list[dict], activity_id: str) -> list[str]:
    return [l["counterparty_id"] for l in links if l["activity_id"] == activity_id]


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


# ── Writes: systems ───────────────────────────────────────────────────────

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


# ── Writes: activities ────────────────────────────────────────────────────

def save_activity(
    row: dict,
    system_roles: Mapping[str, str] | list[str],
    user_id: str,
    client_id: str | None,
    activity_id: str | None = None,
    counterparty_ids: list[str] | None = None,
) -> tuple[str | None, list[str]]:
    """Insert or update one activity and reconcile its links.

    `system_roles` maps system_id -> role code. A bare list of system ids is
    still accepted and every link defaults to 'unknown' — the old signature
    passed a list and silently meant 'processor', which is exactly the claim
    this sprint removes.
    """
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

    if not isinstance(system_roles, Mapping):
        system_roles = {sid: ROLE_UNKNOWN for sid in (system_roles or [])}

    link_errs = _reconcile_links(activity_id, system_roles, user_id, client_id)
    link_errs += _reconcile_counterparties(
        activity_id, counterparty_ids or [], user_id, client_id
    )
    return activity_id, link_errs


def _reconcile_links(
    activity_id: str,
    system_roles: Mapping[str, str],
    user_id: str,
    client_id: str | None,
) -> list[str]:
    """Make activity_systems match `system_roles` exactly, roles included.

    The role used to be hardcoded to 'processor' here, so a client who linked
    a vendor by hand got a confident processor claim with nothing behind it.
    For a Cookie Policy that was cosmetic; for Art. 30(1)(d) recipient
    categories it is a false statement in a document that gets filed.

    Roles now default to 'unknown', which renders as "Not recorded" — a
    visible gap the client can close, rather than an invisible assertion.
    """
    sb = get_supabase()
    errors: list[str] = []

    try:
        existing = (
            sb.table("activity_systems").select("id, system_id, role")
            .eq("activity_id", activity_id).execute().data or []
        )
    except Exception as e:
        return [str(e)]

    have = {r["system_id"]: r for r in existing}
    want = dict(system_roles)

    known_roles = INV.codes_for("system_role", client_id)

    for system_id, role in want.items():
        role = role or ROLE_UNKNOWN
        if known_roles and role not in known_roles:
            errors.append(f"Unknown role {role!r} — recorded as not confirmed.")
            role = ROLE_UNKNOWN

        current = have.get(system_id)
        if current is None:
            try:
                sb.table("activity_systems").insert({
                    "user_id": user_id,
                    "client_id": client_id,
                    "activity_id": activity_id,
                    "system_id": system_id,
                    "role": role,
                }).execute()
            except Exception as e:
                errors.append(str(e))
        elif (current.get("role") or ROLE_UNKNOWN) != role:
            # The branch the old implementation lacked entirely: a link that
            # already existed could never have its role corrected, because
            # reconcile only ever inserted and deleted.
            try:
                sb.table("activity_systems").update({"role": role}) \
                    .eq("id", current["id"]).execute()
            except Exception as e:
                errors.append(str(e))

    for system_id in set(have) - set(want):
        try:
            sb.table("activity_systems").delete().eq("id", have[system_id]["id"]).execute()
        except Exception as e:
            errors.append(str(e))

    return errors


def _reconcile_counterparties(
    activity_id: str,
    counterparty_ids: list[str],
    user_id: str,
    client_id: str | None,
) -> list[str]:
    """Make activity_counterparties match `counterparty_ids` exactly."""
    sb = get_supabase()
    errors: list[str] = []

    try:
        existing = (
            sb.table("activity_counterparties").select("id, counterparty_id")
            .eq("activity_id", activity_id).execute().data or []
        )
    except Exception as e:
        return [str(e)]

    have = {r["counterparty_id"]: r["id"] for r in existing}
    want = set(counterparty_ids)

    for cp_id in want - set(have):
        try:
            sb.table("activity_counterparties").insert({
                "user_id": user_id,
                "client_id": client_id,
                "activity_id": activity_id,
                "counterparty_id": cp_id,
            }).execute()
        except Exception as e:
            errors.append(str(e))

    for cp_id in set(have) - want:
        try:
            sb.table("activity_counterparties").delete().eq("id", have[cp_id]).execute()
        except Exception as e:
            errors.append(str(e))

    return errors


def delete_activity(activity_id: str) -> list[str]:
    try:
        get_supabase().table("processing_activities").delete().eq("id", activity_id).execute()
        return []
    except Exception as e:
        return [str(e)]


# ── Writes: counterparties ────────────────────────────────────────────────

def save_counterparty(
    row: dict,
    user_id: str,
    client_id: str | None,
    counterparty_id: str | None = None,
) -> tuple[str | None, list[str]]:
    """Insert or update one Art. 30(2) controller identity."""
    payload = {c: row.get(c) for c in COUNTERPARTY_EDITABLE}
    payload = {**payload, "user_id": user_id, "client_id": client_id}

    errs = INV.validate_counterparty(payload, scope=client_id)
    if errs:
        return None, errs

    sb = get_supabase()
    try:
        if counterparty_id:
            sb.table("processing_counterparties").update(payload) \
                .eq("id", counterparty_id).execute()
            return counterparty_id, []
        res = sb.table("processing_counterparties").insert(payload).execute()
        new_id = (res.data or [{}])[0].get("id")
        if not new_id:
            # The S21 lesson: an insert that succeeds but returns nothing
            # usually means a missing SELECT policy, not a failed write.
            return None, ["Saved, but could not read the row back — check RLS."]
        return new_id, []
    except Exception as e:
        return None, [str(e)]


def delete_counterparty(counterparty_id: str) -> list[str]:
    """Delete a counterparty. activity_counterparties cascades.

    The activities survive, for the same reason deleting a system leaves them
    standing: losing a customer should not erase the record of what was
    processed for them.
    """
    try:
        get_supabase().table("processing_counterparties") \
            .delete().eq("id", counterparty_id).execute()
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

    created, errors, incomplete = 0, [], []
    for a in activity_rows:
        role = a.pop("_system_role", ROLE_UNKNOWN)
        statutory = a.pop("_retention_is_statutory", False)
        payload = {**a, "user_id": user_id, "client_id": client_id}

        # Catalogue defaults deliberately omit security measures, the
        # balancing test, and any retention period the vendor does not
        # determine — those are client facts, not vendor facts. The activity
        # is still created so the client can complete it; the gap belongs in
        # the readiness figures, not in a blocked seed.
        if not (payload.get("retention_period") or "").strip():
            # Guidance goes in NOTES, not retention_basis.
            #
            # retention_basis is an Art. 30(1)(f) column: it states WHY a
            # period is what it is. Writing an instruction there put
            # "3 years — To be set by your own retention policy." into a filed
            # register. A prompt addressed to the client is not a legal basis,
            # and the register is the one place it must never appear.
            guidance = (
                "Retention: set by national law — confirm the period that "
                "applies to you."
                if statutory else
                "Retention: to be set by your own retention policy."
            )
            existing_note = (payload.get("notes") or "").strip()
            payload["notes"] = (
                f"{existing_note} {guidance}".strip() if existing_note else guidance
            )

        # The seed path deliberately inserts rows that fail validation, so a
        # client is not blocked at the tick. S26 makes that visible: the
        # caller gets the list back and the page reports it, rather than the
        # only trace being a note buried on the row.
        verrs = INV.validate_activity(payload, scope=client_id)
        if verrs:
            payload.setdefault("notes", "Seeded from the RECOSA catalogue — please review.")
            incomplete.append(f"{payload.get('name')}: {'; '.join(verrs)}")

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
        "incomplete": incomplete,
    }


def already_seeded(systems: list[dict]) -> set[str]:
    return {s["catalogue_key"] for s in systems if s.get("catalogue_key")}


# ── Completeness ──────────────────────────────────────────────────────────
# A lightweight precursor to the S42 field-level score, promoted in S26 from
# a progress metric to a pre-generation gate.
#
# The gate has to live here rather than in the renderer. render_template
# blocks only on missing FieldSpec scalars; per-activity gaps live inside a
# block renderer, which is called after the decision to generate has already
# been made and has no way to stop it. So anything that should prevent a RoPA
# being emitted must be caught before generate() is called.

def readiness(
    activities: list[dict],
    systems: list[dict],
    links: list[dict],
    counterparty_links: list[dict] | None = None,
    client_id_scope: str | None = None,
) -> dict:
    """Report what is missing before a RoPA can be honestly generated.

    counterparty_links is optional so existing call sites keep working, but a
    caller that omits it will see every processor-side activity reported as
    missing its controllers. Pass it.
    """
    counterparty_links = counterparty_links or []

    linked_activity_ids = {l["activity_id"] for l in links}
    systems_by_id = {s["id"]: s for s in systems}
    cp_activity_ids = {l["activity_id"] for l in counterparty_links}

    links_by_activity: dict[str, list[dict]] = {}
    for l in links:
        links_by_activity.setdefault(l["activity_id"], []).append(l)

    gaps: list[str] = []
    blocking: list[str] = []
    gap_ids: set[str] = set()
    blocking_ids: set[str] = set()

    for a in activities:
        missing: list[str] = []
        blocks: list[str] = []

        if not a.get("legal_basis"):
            blocks.append("no Art. 6 legal basis")

        # Art. 30(1)(f). Blocking rather than a gap: a record that states a
        # purpose and no erasure period is not an incomplete record, it is one
        # that omits a mandatory field.
        if not (a.get("retention_period") or "").strip():
            blocks.append("no retention period (Art. 30(1)(f))")

        # Art. 6(1)(f). The balancing test is a condition of the basis being
        # available at all, so a record claiming legitimate interests without
        # one documents a probable breach — the same reasoning as Art. 9(2).
        if INV.needs_balancing_test(a.get("legal_basis"), client_id_scope):
            if not (a.get("legitimate_interest_note") or "").strip():
                blocks.append("legitimate interests with no recorded balancing test")
        if not a.get("data_categories"):
            missing.append("data categories")
        if not a.get("security_measures"):
            missing.append("security measures")
        if a["id"] not in linked_activity_ids:
            missing.append("no system linked")

        # Art. 9(1) without an Art. 9(2) condition is unlawful processing. The
        # database CHECK enforces this on write, but rows predating it — or
        # written by a path that bypassed validation — would otherwise reach
        # a generated record. This blocks.
        if a.get("special_categories") and not a.get("art9_condition"):
            blocks.append("special category data with no Art. 9(2) condition")

        # Art. 30(2)(a): a processor must name each controller it acts for, or
        # say where the maintained list is kept. Categories of PROCESSING may
        # be described in the record; the controllers themselves are named.
        if a.get("controller_role") == "processor":
            has_named = a["id"] in cp_activity_ids
            has_register = bool((a.get("counterparty_register_note") or "").strip())
            if not (has_named or has_register):
                blocks.append("processor activity with no controller recorded")

        # Art. 30(1)(e): a transfer out of the EEA must state its safeguard.
        # Derived from the systems the activity actually uses, so a client
        # never restates a fact already recorded against the vendor.
        for link in links_by_activity.get(a["id"], []):
            sysrow = systems_by_id.get(link["system_id"])
            if not sysrow:
                continue
            if INV.is_third_country(sysrow.get("processing_country")):
                if (sysrow.get("transfer_mechanism") or "unknown") == "unknown":
                    blocks.append(
                        f"transfer to {sysrow.get('processing_country')} via "
                        f"{sysrow.get('name')} with no safeguard recorded"
                    )
            if (link.get("role") or ROLE_UNKNOWN) == ROLE_UNKNOWN:
                missing.append(f"role not confirmed for {sysrow.get('name')}")

        if blocks:
            blocking.append(f"{a['name']}: {', '.join(blocks)}")
            blocking_ids.add(a["id"])
        if missing:
            gaps.append(f"{a['name']}: {', '.join(missing)}")
            gap_ids.add(a["id"])

    vendor_gaps = [
        s["name"] for s in systems
        if s.get("dpa_status") in ("none", "unknown", "requested")
    ]

    total = len(activities)
    complete = total - len(gap_ids | blocking_ids)

    controller_count = sum(1 for a in activities if a.get("controller_role") != "processor")
    processor_count = total - controller_count

    return {
        "activities": total,
        "systems": len(systems),
        "complete_activities": max(complete, 0),
        "activity_gaps": gaps,
        "blocking": blocking,
        # Ids, not names. Two activities can legitimately share a name — a
        # catalogue seed from two vendors produces exactly that — and matching
        # on the name marked both rows broken when only one was, with no way
        # for the client to tell which they had already fixed. Names are for
        # reading; ids are for deciding.
        "gap_ids": sorted(gap_ids),
        "blocking_ids": sorted(blocking_ids),
        "can_generate": not blocking,
        "dpa_gaps": vendor_gaps,
        # The CNIL recommends two separate registers where an organisation is
        # both controller and processor, so the counts drive which documents
        # are offered rather than being decoration.
        "controller_activities": controller_count,
        "processor_activities": processor_count,
    }
