"""
invitations.py — D-200. Invitation codes for beta testers.

A personal code (BETA-PRABIN-7K3Q), sent with a personal invitation, makes the
account that signs up with it ACTIVE on Professional, free during the beta,
with no trial clock — D-173's rule for beta testers ("granted access
directly"), done at sign-up instead of by hand in the back office.

Where a code comes in:
  - the free check:  check.recosa.eu/?code=… — kept through the visit, shown as
                     an invitation, and carried on the new account as user
                     metadata (recosa_invite); claimed at first login (app.py).
  - the app:         app.recosa.eu/?code=…, or typed into the sign-up form;
                     claimed right after sign-up (auth.py).

The database decides (migration_d200_invitation_codes.sql): validity is a
public yes/no (invitation_code_valid), the claim is atomic and service-role
only (claim_invitation_code), and claiming twice for the same person is
harmless. "Free during the beta" carries no end date on purpose (the user,
20 Nov): an end date promised to someone is a commitment to keep the service
running until then.
"""

from __future__ import annotations

import re
import secrets
import unicodedata

# No 0/O, 1/I/L: a code read aloud or copied by hand must not be ambiguous.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,39}$")

INVITE_NOTE = "Beta invitation {code}: full access, free during the beta"


def normalise(code: str | None) -> str | None:
    """The code as stored (upper case, trimmed), or None if it cannot be one.

    The address is visitor-controlled: anything that is not letters, digits
    and dashes, or is too short or too long, is not looked up at all."""
    c = (code or "").strip().upper()
    return c if _CODE_RE.match(c) else None


def new_code(name: str, prefix: str = "BETA") -> str:
    """BETA-<NAME>-<4 random>: readable, personal, and not guessable from the name.

    The name part is the person's or company's name, reduced to plain letters
    and digits (accents dropped), at most 12 characters."""
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Z0-9]+", "", plain.upper())[:12] or "INVITE"
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    return f"{prefix}-{slug}-{suffix}"


def invite_link(code: str, base: str = "https://check.recosa.eu",
                source: str = "linkedin", medium: str = "dm", campaign: str = "beta") -> str:
    """The link to send: the free check, the code, and D-180's UTM tags."""
    return (f"{base.rstrip('/')}/?code={code}&utm_source={source}"
            f"&utm_medium={medium}&utm_campaign={campaign}")


# ── With the database ─────────────────────────────────────────────────────

def is_valid(code: str | None) -> bool:
    """Whether the code can still be used. Anyone may ask (anon key)."""
    c = normalise(code)
    if not c:
        return False
    try:
        from database import get_supabase
        return bool(get_supabase().rpc("invitation_code_valid", {"p_code": c}).execute().data)
    except Exception as e:
        print(f"Invitation check failed: {e}")
        return False


def redeem(user_id: str, code: str | None) -> bool:
    """Use the code for this person: their account becomes active on the code's
    plan, with a dated note. True if the code applied (now or before).

    Only while the account is registered or on trial — an account already
    active, or one an admin has expired, is never changed by a code."""
    c = normalise(code)
    if not c or not user_id:
        return False
    try:
        from database import get_supabase_admin, ensure_account, change_account
        plan = get_supabase_admin().rpc("claim_invitation_code",
                                        {"p_code": c, "p_user": user_id}).execute().data
    except Exception as e:
        print(f"Invitation claim failed: {e}")
        return False
    if not plan:
        return False
    acc = ensure_account(user_id, plan=plan)
    if not acc:
        return False
    if acc.get("status") == "active" and acc.get("plan") == plan:
        return True                                     # already done (a second login)
    if acc.get("status") not in ("registered", "trial"):
        return False
    ok, err = change_account(acc["id"], plan=plan, status="active",
                             note=INVITE_NOTE.format(code=c), by=user_id)
    if not ok:
        print(f"Invitation {c}: account not updated: {err}")
    return ok


def create(name: str, by: str | None, note: str | None = None,
           max_uses: int = 1, plan: str = "professional") -> str | None:
    """A new code for `name` (back office). Retries once on the (unlikely) clash."""
    from database import get_supabase_admin
    for _ in range(2):
        code = new_code(name)
        try:
            get_supabase_admin().table("invitation_codes").insert({
                "code": code, "plan": plan, "note": note or name,
                "max_uses": max(1, int(max_uses)), "created_by": by,
            }).execute()
            return code
        except Exception as e:
            print(f"Invitation code not created ({code}): {e}")
    return None


def list_codes() -> list[dict]:
    """Every code, newest first, with who used it (email) and when."""
    from database import get_supabase_admin
    admin = get_supabase_admin()
    try:
        codes = (admin.table("invitation_codes").select("*")
                 .order("created_at", desc=True).execute().data or [])
        used = admin.table("invitation_redemptions").select("code, user_id, redeemed_at") \
            .execute().data or []
        ids = list({u["user_id"] for u in used})
        emails = {p["id"]: p.get("email") for p in
                  (admin.table("profiles").select("id, email").in_("id", ids).execute().data
                   if ids else [])}
    except Exception as e:
        print(f"Invitation codes not read: {e}")
        return []
    by_code: dict[str, list] = {}
    for u in used:
        by_code.setdefault(u["code"], []).append(
            {"email": emails.get(u["user_id"]) or u["user_id"], "at": u["redeemed_at"]})
    for c in codes:
        c["redeemed"] = sorted(by_code.get(c["code"], []), key=lambda r: r["at"])
    return codes


def set_active(code: str, active: bool) -> bool:
    from database import get_supabase_admin
    try:
        get_supabase_admin().table("invitation_codes").update({"active": active}) \
            .eq("code", code).execute()
        return True
    except Exception as e:
        print(f"Invitation code {code} not updated: {e}")
        return False
