"""
ai_store.py — S61 (D-160). Reading and writing the AI inventory.

The I/O half of ai_rules.py. Through the user's own session (get_supabase),
so RLS applies: has_client_access to read, can_edit_client to write.
Systems themselves stay in the inventory (inventory_store); this module only
sets their ai_role.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Iterable

from database import get_supabase, log_audit_event
import ai_rules as AR


def _rows(table: str, client_id: str, order: str = "created_at") -> list[dict]:
    try:
        return (get_supabase().table(table).select("*").eq("client_id", client_id)
                .order(order).execute().data or [])
    except Exception as e:
        print(f"Could not load {table}: {e}")
        return []


def load_reference(value_type: str) -> list[dict]:
    try:
        return (get_supabase().table("reference_values").select("*")
                .eq("value_type", value_type).eq("active", True).is_("workspace_id", "null")
                .order("sort_order").execute().data or [])
    except Exception as e:
        print(f"Could not load {value_type}: {e}")
        return []


def load_all(client_id: str) -> dict[str, Any]:
    return {
        "systems": _rows("systems", client_id, "name"),
        "models": _rows("ai_models", client_id, "name"),
        "links": _rows("ai_system_models", client_id),
        "use_cases": _rows("ai_use_cases", client_id),
    }


def _clean(row: dict[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    out = {}
    for k in fields:
        if k not in row:
            continue
        v = row[k]
        if isinstance(v, str):
            v = v.strip() or None
        elif isinstance(v, (date, datetime)):
            v = v.isoformat()
        out[k] = v
    return out


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_policy_owner(user_id: str, client_id: str, owner: str) -> bool:
    """S62: who approves new AI tools, named in the AI policies."""
    try:
        get_supabase().table("clients").update({"ai_policy_owner": owner.strip() or None})             .eq("id", client_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="ai_inventory",
                        event_subtype="policy_owner", summary="AI policy owner set")
        return True
    except Exception as e:
        print(f"Could not set AI policy owner: {e}")
        return False


# ── Systems ───────────────────────────────────────────────────────────────

def set_ai_role(user_id: str, client_id: str, system_id: str, role: str) -> bool:
    """Mark an inventory system as AI (or not). The same field the Systems
    page edits."""
    try:
        get_supabase().table("systems").update({"ai_role": role, "updated_at": _now()}) \
            .eq("id", system_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="ai_inventory",
                        event_subtype="system_role", resource_id=system_id,
                        summary=f"AI role of a system set to {role}")
        return True
    except Exception as e:
        print(f"Could not set AI role: {e}")
        return False


def set_system_models(user_id: str, client_id: str, system_id: str, model_ids: list[str]) -> bool:
    try:
        sb = get_supabase()
        current = {r["model_id"] for r in (sb.table("ai_system_models").select("model_id")
                                           .eq("system_id", system_id).execute().data or [])}
        wanted = set(model_ids)
        if wanted - current:
            sb.table("ai_system_models").insert([
                {"client_id": client_id, "system_id": system_id, "model_id": m, "user_id": user_id}
                for m in sorted(wanted - current)]).execute()
        if current - wanted:
            sb.table("ai_system_models").delete().eq("system_id", system_id) \
                .in_("model_id", sorted(current - wanted)).execute()
        return True
    except Exception as e:
        print(f"Could not set system models: {e}")
        return False


# ── Models ────────────────────────────────────────────────────────────────

_MODEL_FIELDS = ("name", "supplier", "version", "general_purpose", "origin", "documentation_url", "notes")


def save_model(user_id: str, client_id: str, model: dict[str, Any], model_id: str | None = None) -> str | None:
    fields = _clean(model, _MODEL_FIELDS)
    try:
        sb = get_supabase()
        if model_id:
            sb.table("ai_models").update({**fields, "updated_at": _now()}).eq("id", model_id).execute()
            return model_id
        res = sb.table("ai_models").insert({**fields, "client_id": client_id, "user_id": user_id}).execute()
        return (res.data or [{}])[0].get("id")
    except Exception as e:
        print(f"Could not save model: {e}")
        return None


def delete_model(user_id: str, client_id: str, model_id: str) -> bool:
    try:
        get_supabase().table("ai_models").delete().eq("id", model_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="ai_inventory",
                        event_subtype="model_deleted", resource_id=model_id, summary="An AI model was deleted")
        return True
    except Exception as e:
        print(f"Could not delete model: {e}")
        return False


# ── Use cases ─────────────────────────────────────────────────────────────

_UC_FIELDS = ("system_id", "name", "description", "business_owner", "status", "role",
              "own_name_or_brand", "substantially_modified", "purpose_changed",
              "prohibited_practices", "annex_iii_area", "art6_3_condition", "art6_3_reason",
              "profiles_people", "interacts_with_people", "generates_content", "deep_fake",
              "public_interest_text", "emotion_or_biometric", "used_on_workers",
              "oversight_employee_id", "notes")


def save_use_case(user_id: str, client_id: str, uc: dict[str, Any], uc_id: str | None = None) -> str | None:
    fields = _clean(uc, _UC_FIELDS)
    risk = AR.classify(uc)["risk"]
    if risk != AR.UNKNOWN:
        fields["assessed_at"] = _now()
    try:
        sb = get_supabase()
        if uc_id:
            sb.table("ai_use_cases").update({**fields, "updated_at": _now()}).eq("id", uc_id).execute()
            sub = "use_case_updated"
        else:
            res = sb.table("ai_use_cases").insert({**fields, "client_id": client_id, "user_id": user_id}).execute()
            uc_id = (res.data or [{}])[0].get("id")
            sub = "use_case_added"
        if uc_id:
            log_audit_event(company_id=client_id, user_id=user_id, event_type="ai_inventory",
                            event_subtype=sub, resource_id=uc_id,
                            summary=f"AI use case: {(fields.get('name') or '')[:80]} — {AR.RISK_LABELS[risk]}",
                            metadata={"risk": risk})
        return uc_id
    except Exception as e:
        print(f"Could not save use case: {e}")
        return None


def delete_use_case(user_id: str, client_id: str, uc_id: str) -> bool:
    try:
        get_supabase().table("ai_use_cases").delete().eq("id", uc_id).execute()
        log_audit_event(company_id=client_id, user_id=user_id, event_type="ai_inventory",
                        event_subtype="use_case_deleted", resource_id=uc_id, summary="An AI use case was deleted")
        return True
    except Exception as e:
        print(f"Could not delete use case: {e}")
        return False


def open_findings(client: dict, data: dict[str, Any] | None = None) -> list[dict]:
    try:
        d = data or load_all(client["id"])
        return AR.findings(client, d["systems"], d["use_cases"])
    except Exception as e:
        print(f"AI inventory findings not loaded: {e}")
        return []
