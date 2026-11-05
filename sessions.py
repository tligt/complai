"""
sessions.py — S51 (D-143): a login that survives a page refresh, a reopened
tab or a link opened later, in the client app and the back office.

Before: the login lived only in st.session_state, which a refresh or a new
tab replaces with an empty one — so every reload meant logging in again.

Now:
- The browser keeps one cookie with a random, opaque value (32 bytes). It is
  not a token: on its own it opens nothing outside this app.
- `app_sessions` (migration_s51_app_sessions.sql) keeps what it stands for:
  the Supabase access and refresh tokens, encrypted with SESSION_SECRET,
  under the SHA-256 of the cookie value. Service role only.
- All tabs of a browser share one login, so the single-use refresh token is
  rotated in one place: a refresh writes the new tokens only if the row
  still holds the ones it started from (compare and swap); a tab that loses
  the race takes the winner's tokens instead of reusing a spent one, which
  Supabase would answer by revoking the whole login.
- Limits: the client app keeps a login 7 days at most and ends it after 24 h
  without use; the back office 12 h and 4 h. Logging out deletes the row, so
  the cookie is dead at once, even if the browser keeps it.

Switched on by two secrets, SESSION_SECRET and SUPABASE_SERVICE_KEY. Without
them (tests, a fresh environment) everything works as before: no cookie, a
refresh logs out.

The cookie is written by a few lines of JavaScript (st.html), so it cannot be
HttpOnly; that is why it holds an opaque id and not a token. On the S50
server it can move to an HttpOnly cookie set by the server (st.App routes).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import streamlit as st

COOKIE = {"client": "recosa_sid", "admin": "recosa_bo_sid"}
# (absolute lifetime, idle timeout), seconds.
LIMITS = {
    "client": (7 * 24 * 3600, 24 * 3600),
    "admin": (12 * 3600, 4 * 3600),
}
# last_seen_at is written at most this often (one write per click is waste).
TOUCH_EVERY = 300


# ── Switch and crypto ─────────────────────────────────────────────────────

def _fernet():
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        return None
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def enabled() -> bool:
    return bool(os.environ.get("SESSION_SECRET") and os.environ.get("SUPABASE_SERVICE_KEY"))


def _hash(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _seal(access: str, refresh: str) -> str:
    return _fernet().encrypt(json.dumps({"a": access, "r": refresh}).encode()).decode()


def _open(sealed: str) -> tuple[str, str] | None:
    try:
        d = json.loads(_fernet().decrypt(sealed.encode()))
        return d["a"], d["r"]
    except Exception:
        # Another SESSION_SECRET, or a damaged row: the login is over.
        return None


def _db():
    from database import get_supabase_admin
    return get_supabase_admin().table("app_sessions")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── The store ─────────────────────────────────────────────────────────────

def create(app: str, user_id: str, access: str, refresh: str) -> str | None:
    """A new login: its row, and the cookie value to give the browser."""
    if not enabled():
        return None
    sid = secrets.token_urlsafe(32)
    absolute, _ = LIMITS[app]
    try:
        ua = (st.context.headers.get("User-Agent") or "")[:300]
    except Exception:
        ua = ""
    try:
        _db().insert({
            "id": _hash(sid), "app": app, "user_id": user_id,
            "tokens": _seal(access, refresh),
            "expires_at": (_now() + timedelta(seconds=absolute)).isoformat(),
            "user_agent": ua or None,
        }).execute()
    except Exception as e:
        print(f"Could not store the login: {e}")
        return None
    return sid


def load(app: str, sid: str) -> dict | None:
    """The login behind a cookie, or None when there is none or it is over
    (past its absolute end, idle too long, or unreadable — those rows go)."""
    if not (enabled() and sid):
        return None
    try:
        rows = _db().select("*").eq("id", _hash(sid)).eq("app", app).limit(1).execute().data
    except Exception as e:
        print(f"Could not read the login: {e}")
        return None
    if not rows:
        return None
    row = rows[0]
    _, idle = LIMITS[app]
    now = _now()
    tokens = _open(row["tokens"])
    if (tokens is None or _ts(row["expires_at"]) <= now
            or _ts(row["last_seen_at"]) + timedelta(seconds=idle) <= now):
        delete(sid)
        return None
    return {"sealed": row["tokens"], "access": tokens[0], "refresh": tokens[1],
            "user_id": row["user_id"], "last_seen_at": row["last_seen_at"]}


def swap_tokens(sid: str, sealed_before: str, access: str, refresh: str) -> bool:
    """Store refreshed tokens if the row still holds `sealed_before`. False
    when another tab refreshed first (its tokens are then the ones to use)."""
    try:
        res = (_db().update({"tokens": _seal(access, refresh), "last_seen_at": _now().isoformat()})
               .eq("id", _hash(sid)).eq("tokens", sealed_before).execute())
        return bool(res.data)
    except Exception as e:
        print(f"Could not store the refreshed login: {e}")
        return False


def touch(sid: str) -> None:
    try:
        _db().update({"last_seen_at": _now().isoformat()}).eq("id", _hash(sid)).execute()
    except Exception as e:
        print(f"Could not record activity on the login: {e}")


def delete(sid: str) -> None:
    if not (enabled() and sid):
        return
    try:
        _db().delete().eq("id", _hash(sid)).execute()
    except Exception as e:
        print(f"Could not end the login: {e}")


def delete_others(user_id: str, keep_sid: str | None) -> None:
    """After a password change: every other browser's login ends."""
    if not enabled():
        return
    try:
        q = _db().delete().eq("user_id", user_id)
        if keep_sid:
            q = q.neq("id", _hash(keep_sid))
        q.execute()
    except Exception as e:
        print(f"Could not end the other logins: {e}")


# ── The cookie ────────────────────────────────────────────────────────────

def read_cookie(app: str) -> str | None:
    """The cookie as the browser sent it when this tab connected."""
    try:
        value = st.context.cookies.get(COOKIE[app])
    except Exception:
        return None
    # token_urlsafe(32) is 43 characters of [A-Za-z0-9_-]; anything else is
    # not ours.
    if value and 20 <= len(value) <= 100 and all(c.isalnum() or c in "-_" for c in value):
        return value
    return None


def write_cookie(app: str, sid: str | None) -> None:
    """Sets (sid) or clears (None) the cookie in the browser. Rendered inside
    a hidden container; the value is only [A-Za-z0-9_-], safe to inline."""
    name = COOKIE[app]
    absolute, _ = LIMITS[app]
    value, max_age = (sid, absolute) if sid else ("", 0)
    st.html(
        f"""<script>(function(){{
          var s = location.protocol === "https:" ? "; Secure" : "";
          document.cookie = "{name}={value}; Max-Age={max_age}; Path=/; SameSite=Lax" + s;
        }})();</script>""",
        unsafe_allow_javascript=True,
    )


def seconds_since(iso: str) -> float:
    try:
        return time.time() - _ts(iso).timestamp()
    except Exception:
        return 0.0
