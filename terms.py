"""D-221: the record that a user accepted the Terms of Service and the
Privacy Policy (table terms_acceptances).

Written at both sign-ups (auth.py, quiz_app._signup) and by the prompt at
login for an account with no record (app.py). Kept after an account is
deleted: it is the proof of what was agreed.

Change TERMS_VERSION / PRIVACY_VERSION to the "Last updated" date whenever a
new text is published on recosa.eu (sources: docs/legal/).
"""

from __future__ import annotations

TERMS_URL = "https://www.recosa.eu/terms-of-service"
PRIVACY_URL = "https://www.recosa.eu/privacy-policy"
TERMS_VERSION = "2026-11-27"
PRIVACY_VERSION = "2026-11-27"

SRC_APP = "app_signup"
SRC_CHECK = "check_signup"
SRC_LOGIN = "login_prompt"


def record(user_id: str, email: str, source: str) -> bool:
    """Save one acceptance. Never raises: a failure is logged, and the login
    prompt asks again next time."""
    try:
        from database import get_supabase_admin
        get_supabase_admin().table("terms_acceptances").insert({
            "user_id": user_id, "email": email, "source": source,
            "terms_version": TERMS_VERSION, "privacy_version": PRIVACY_VERSION,
        }).execute()
        return True
    except Exception as e:
        print(f"terms acceptance not recorded for {user_id}: {e}")
        return False


def has_accepted(user_id: str) -> bool:
    """Any acceptance on record. Fails open (True) if it cannot be read, so a
    database hiccup never locks someone out."""
    try:
        from database import get_supabase_admin
        rows = get_supabase_admin().table("terms_acceptances").select("id") \
            .eq("user_id", user_id).limit(1).execute().data
        return bool(rows)
    except Exception as e:
        print(f"terms acceptance not readable for {user_id}: {e}")
        return True
