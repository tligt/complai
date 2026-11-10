"""
work_items.py — S56 (D-145): who handles a piece of work, and the
conversation about it.

A piece of work is an action-plan task (its finding_key, tasks.py) or an
incident (its id). It can be given to one person of the company — by hand,
or by the company's routing rule for its area — discussed in a comment
thread, and it notifies people in their in-app inbox. migration_s56_
routing_messaging.sql has the tables.

D-05: none of it leaves RECOSA. The only email is a content-free nudge
("You have something new in RECOSA"), sent when a person's inbox goes from
empty to not empty, and only while NOTIFY_ENABLED is on.

Every plan with a team (asked for, 5 Nov): wherever more than one person
works on a company. Alone on a company, nothing of this is shown.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

AREAS = {
    "gdpr": "GDPR (and cookies)",
    "nis2": "NIS2",
    "ai_act": "EU AI Act",
    "documents": "Documents and records",
    "incidents": "Incidents",
}
_REG_AREA = {"GDPR": "gdpr", "EPRIVACY": "gdpr", "NIS2": "nis2", "EU_AI_ACT": "ai_act"}
_ROLE_RANK = {"owner": 0, "admin": 1, "contributor": 2, "read_only": 3}


def _db():
    from database import get_supabase
    return get_supabase()


def _admin():
    from database import get_supabase_admin
    return get_supabase_admin()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Areas ─────────────────────────────────────────────────────────────────

def area_of_task(task: dict) -> str:
    """The routing area of an action-plan task."""
    producer = task.get("producer") or ""
    if producer == "obligation":
        from obligations import OBLIGATION_BY_ID
        ob_id = (task.get("finding_key") or "").split(":")[1:2]
        reg = (OBLIGATION_BY_ID.get(ob_id[0]) or {}).get("regulation") if ob_id else None
        return _REG_AREA.get(reg, "gdpr")
    if producer == "incident":
        return "incidents"
    if producer == "ai":
        return "ai_act"
    if producer == "training":
        # S60: training:<requirement code>, routed with its regulation.
        code = (task.get("finding_key") or "").split(":", 1)[-1]
        return ("nis2" if code.startswith("nis2_") else
                "ai_act" if code.startswith("ai_") else "gdpr")
    return "documents"


# ── People ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60, show_spinner=False)
def people(client_id: str) -> list[dict]:
    """Everyone who can reach the company: the owner, its members and the
    members of its group, with their strongest role. [{id, name, email,
    role}], owner first."""
    admin = _admin()
    try:
        c = admin.table("clients").select("user_id").eq("id", client_id).limit(1).execute().data
        if not c:
            return []
        owner = c[0]["user_id"]
        roles: dict[str, str] = {owner: "owner"}
        for r in (admin.table("workspace_members").select("member_user_id, role")
                  .eq("client_id", client_id).eq("status", "active").execute().data or []):
            if r.get("member_user_id"):
                roles.setdefault(r["member_user_id"], r["role"])
                if _ROLE_RANK[r["role"]] < _ROLE_RANK[roles[r["member_user_id"]]]:
                    roles[r["member_user_id"]] = r["role"]
        g = (admin.table("client_groups").select("id").eq("owner_user_id", owner)
             .limit(1).execute().data)
        if g:
            for r in (admin.table("group_members").select("member_user_id, role")
                      .eq("group_id", g[0]["id"]).eq("status", "active").execute().data or []):
                uid = r.get("member_user_id")
                if uid and (uid not in roles or _ROLE_RANK[r["role"]] < _ROLE_RANK[roles[uid]]):
                    roles[uid] = r["role"]
        prof = {p["id"]: p for p in (admin.table("profiles").select("id, email, full_name")
                                     .in_("id", list(roles)).execute().data or [])}
    except Exception as e:
        print(f"Could not list the people of {client_id}: {e}")
        return []
    out = [{"id": uid, "role": role,
            "email": (prof.get(uid) or {}).get("email") or "",
            "name": (prof.get(uid) or {}).get("full_name") or (prof.get(uid) or {}).get("email") or "Someone"}
           for uid, role in roles.items()]
    return sorted(out, key=lambda p: (_ROLE_RANK[p["role"]], p["name"].lower()))


def has_team(client_id: str) -> bool:
    return len(people(client_id)) > 1


def name_of(client_id: str, user_id: str | None) -> str:
    if not user_id:
        return "nobody"
    for p in people(client_id):
        if p["id"] == user_id:
            return p["name"]
    return "a former member"


def assignable(client_id: str) -> list[dict]:
    """Who work can be given to: everyone who may change the company."""
    return [p for p in people(client_id) if p["role"] != "read_only"]


# ── Assignments ───────────────────────────────────────────────────────────

def current(client_id: str, item_type: str) -> dict[str, dict]:
    """{item_key: newest assignment row} for one company."""
    try:
        rows = (_db().table("assignments").select("*").eq("client_id", client_id)
                .eq("item_type", item_type).order("created_at", desc=True)
                .limit(5000).execute().data or [])
    except Exception as e:
        print(f"Could not read assignments: {e}")
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["item_key"], r)
    return out


def assign(client_id: str, item_type: str, item_key: str, title: str,
           assignee_id: str | None, by_user: str | None, source: str = "manual") -> bool:
    """Give an item to someone (None = nobody). By hand it is written as the
    user, under RLS; a routing rule writes with the service role."""
    row = {"client_id": client_id, "item_type": item_type, "item_key": item_key,
           "item_title": (title or "")[:300], "assignee_id": assignee_id,
           "assigned_by": by_user if source == "manual" else None, "source": source}
    try:
        (_db() if source == "manual" else _admin()).table("assignments").insert(row).execute()
    except Exception as e:
        print(f"Could not record the assignment: {e}")
        return False
    if assignee_id and assignee_id != by_user:
        notify([assignee_id], "assigned", client_id, item_type, item_key, title, by_user)
    from database import log_audit_event
    who = name_of(client_id, assignee_id)
    what = "task" if item_type == "task" else "incident"
    log_audit_event(client_id, "assignment",
                    (f"Gave a {what} to {who}" if assignee_id else f"Took a {what} back from its assignee")
                    + (" (routing rule)" if source == "rule" else ""),
                    user_id=by_user, event_subtype=source,
                    metadata={"item_type": item_type, "item_key": item_key, "title": title,
                              "assignee_id": assignee_id})
    return True


# ── Routing rules ─────────────────────────────────────────────────────────

def rules(client_id: str) -> dict[str, str]:
    """{area: assignee_id}."""
    try:
        rows = (_db().table("routing_rules").select("area, assignee_id")
                .eq("client_id", client_id).execute().data or [])
    except Exception as e:
        print(f"Could not read routing rules: {e}")
        return {}
    return {r["area"]: r["assignee_id"] for r in rows}


def set_rule(client_id: str, area: str, assignee_id: str | None, by_user: str) -> bool:
    try:
        t = _db().table("routing_rules")
        if assignee_id:
            t.upsert({"client_id": client_id, "area": area, "assignee_id": assignee_id,
                      "updated_by": by_user, "updated_at": _now()},
                     on_conflict="client_id,area").execute()
        else:
            t.delete().eq("client_id", client_id).eq("area", area).execute()
    except Exception as e:
        print(f"Could not save the routing rule: {e}")
        return False
    from database import log_audit_event
    log_audit_event(client_id, "routing",
                    f"{AREAS[area]} now goes to {name_of(client_id, assignee_id)}"
                    if assignee_id else f"{AREAS[area]}: no default person any more",
                    user_id=by_user, event_subtype="rule",
                    metadata={"area": area, "assignee_id": assignee_id})
    return True


def route_unassigned(client_id: str, tasks: list[dict], current_rows: dict[str, dict]) -> int:
    """Give every open task that was never assigned to its area's person.
    A task given back by hand (an assignment row to nobody) is left alone.
    Returns how many were routed."""
    rr = rules(client_id)
    if not rr:
        return 0
    valid = {p["id"] for p in assignable(client_id)}
    n = 0
    for t in tasks:
        if t["finding_key"] in current_rows:
            continue
        who = rr.get(area_of_task(t))
        if who and who in valid:
            if assign(client_id, "task", t["finding_key"], t["title"], who, None, "rule"):
                n += 1
    return n


def route_incident(client_id: str, incident: dict) -> bool:
    who = rules(client_id).get("incidents")
    if not who or who not in {p["id"] for p in assignable(client_id)}:
        return False
    return assign(client_id, "incident", incident["id"], incident.get("title") or "Incident",
                  who, None, "rule")


# ── Comments ──────────────────────────────────────────────────────────────

def comments(client_id: str, item_type: str, item_key: str) -> list[dict]:
    try:
        return (_db().table("item_comments").select("*").eq("client_id", client_id)
                .eq("item_type", item_type).eq("item_key", item_key)
                .order("created_at").execute().data or [])
    except Exception as e:
        print(f"Could not read comments: {e}")
        return []


def comment_counts(client_id: str, item_type: str) -> dict[str, int]:
    try:
        rows = (_db().table("item_comments").select("item_key").eq("client_id", client_id)
                .eq("item_type", item_type).limit(10000).execute().data or [])
    except Exception:
        return {}
    out: dict[str, int] = {}
    for r in rows:
        out[r["item_key"]] = out.get(r["item_key"], 0) + 1
    return out


def post_comment(client_id: str, item_type: str, item_key: str, title: str,
                 author_id: str, body: str, mention_ids: list[str] | None = None,
                 assignee_id: str | None = None) -> bool:
    body = (body or "").strip()
    if not body:
        return False
    earlier = comments(client_id, item_type, item_key)
    try:
        _db().table("item_comments").insert({
            "client_id": client_id, "item_type": item_type, "item_key": item_key,
            "author_id": author_id, "body": body[:4000],
        }).execute()
    except Exception as e:
        print(f"Could not post the comment: {e}")
        return False
    reachable = {p["id"] for p in people(client_id)}
    mentioned = {m for m in (mention_ids or []) if m in reachable} - {author_id}
    following = ({assignee_id} if assignee_id else set()) | {c["author_id"] for c in earlier if c.get("author_id")}
    following = (following & reachable) - {author_id} - mentioned
    notify(sorted(mentioned), "mention", client_id, item_type, item_key, title, author_id)
    notify(sorted(following), "comment", client_id, item_type, item_key, title, author_id)
    return True


# ── Notifications ─────────────────────────────────────────────────────────

def notify(user_ids: list[str], kind: str, client_id: str, item_type: str,
           item_key: str, title: str, actor_id: str | None) -> None:
    """In-app notifications, written with the service role. A person whose
    inbox was empty also gets the content-free email nudge."""
    if not user_ids:
        return
    admin = _admin()
    for uid in user_ids:
        was_empty = unread_count(uid, admin=True) == 0
        try:
            admin.table("notifications").insert({
                "user_id": uid, "client_id": client_id, "kind": kind,
                "item_type": item_type, "item_key": item_key,
                "item_title": (title or "")[:300], "actor_id": actor_id,
            }).execute()
        except Exception as e:
            print(f"Could not notify {uid}: {e}")
            continue
        if was_empty:
            _nudge(uid)


def _nudge(user_id: str) -> None:
    try:
        from email_sender import send_inbox_nudge
        p = (_admin().table("profiles").select("email").eq("id", user_id)
             .limit(1).execute().data)
        if p and p[0].get("email"):
            send_inbox_nudge(p[0]["email"])
    except Exception as e:
        print(f"Inbox nudge not sent: {e}")


def unread_count(user_id: str, admin: bool = False) -> int:
    try:
        res = ((_admin() if admin else _db()).table("notifications").select("id", count="exact")
               .eq("user_id", user_id).is_("read_at", "null").limit(1).execute())
        return res.count or 0
    except Exception:
        return 0


def inbox(user_id: str, limit: int = 100) -> list[dict]:
    try:
        return (_db().table("notifications").select("*").eq("user_id", user_id)
                .order("created_at", desc=True).limit(limit).execute().data or [])
    except Exception as e:
        print(f"Could not read the inbox: {e}")
        return []


def mark_read(user_id: str, *, ids: list[str] | None = None,
              item: tuple[str, str] | None = None) -> None:
    """Mark notifications read: given ids, every one about an item
    (item_type, item_key), or all of them."""
    try:
        q = (_db().table("notifications").update({"read_at": _now()})
             .eq("user_id", user_id).is_("read_at", "null"))
        if ids:
            q = q.in_("id", ids)
        elif item:
            q = q.eq("item_type", item[0]).eq("item_key", item[1])
        q.execute()
    except Exception as e:
        print(f"Could not mark notifications read: {e}")
