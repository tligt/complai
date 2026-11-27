"""
readonly.py — D-215. An expired trial keeps read-only access: it sees and
downloads everything it built, and changes nothing.

app.py sets st.session_state["read_only"] for such an account. Then:

- every Supabase client the session gets (database.get_supabase and
  get_supabase_admin) comes wrapped: insert / update / upsert / delete on a
  table, and upload / remove / move / update in storage, are not sent and
  raise ReadOnlyError. The page's own "could not save" path then runs (a
  silent empty result let pages say "Saved." for a change that was not);
  a notice says nothing was saved, also after the page reloads, and app.py
  turns an uncaught ReadOnlyError into a plain message. Reads, downloads and
  signed URLs go through;
- the AI calls (Mistral) are refused before they are made (check()), so a
  read-only session neither generates anything nor costs anything.

What stays writable (WRITABLE): what an expired account still needs — its
sign-in, its language and email preferences, support and the plan request,
its billing company details, alerts marked as read, the funnel's counts,
its acceptance of the terms (D-221).

Scheduled jobs have no Streamlit session: never read-only.
"""

from __future__ import annotations

WRITABLE = {
    "profiles", "app_sessions", "audit_log", "funnel_events",
    "support_tickets", "message_threads", "messages", "notifications",
    "accounts", "client_alerts", "workspace_members", "answer_feedback",
    "terms_acceptances",   # D-221: the login prompt for an account with none
}
# Bookkeeping a page writes while it draws (the action plan records task
# history on load): refused like the rest, but without the "nothing was
# saved" notice — the person did not try to save anything.
QUIET = {"task_events"}
_TABLE_WRITES = ("insert", "update", "upsert", "delete")
_STORAGE_WRITES = ("upload", "update", "remove", "move", "copy", "create_signed_upload_url",
                   "upload_to_signed_url")


class ReadOnlyError(Exception):
    """Shown as is by pages ("Could not save …: <this>"): plain language, in the
    reader's language. What was refused goes to the server log."""

    def __init__(self, detail: str = ""):
        self.detail = detail
        try:
            from i18n import tr
            msg = tr("your trial has ended and RECOSA is read-only. Choose a plan to make changes.")
        except Exception:
            msg = "your trial has ended and RECOSA is read-only. Choose a plan to make changes."
        super().__init__(msg)


def active() -> bool:
    try:
        import streamlit as st
        return bool(st.session_state.get("read_only"))
    except Exception:
        return False


def _notice() -> None:
    """Once per run, wherever the refused write happened; kept for the next
    run too (pending_notice), since pages often reload right after saving."""
    try:
        import streamlit as st
        if not st.session_state.get("_ro_noticed_run"):
            st.session_state["_ro_noticed_run"] = True
            st.session_state["_ro_notice_pending"] = True
            show_pending_notice(keep=True)
    except Exception:
        pass


def show_pending_notice(keep: bool = False) -> None:
    import streamlit as st
    from i18n import tr
    if st.session_state.get("_ro_notice_pending"):
        if not keep:
            st.session_state["_ro_notice_pending"] = False
        st.toast(tr("Your trial has ended: RECOSA is read-only. Nothing was saved."), icon="🔒")


def check(what: str = "") -> None:
    """Before an AI call or anything else that only makes sense with a plan."""
    if active():
        _notice()
        raise ReadOnlyError(f"Read-only (trial ended){': ' + what if what else ''}")


class _Table:
    def __init__(self, builder, name: str):
        self._b, self._name = builder, name

    def __getattr__(self, attr):
        if attr in _TABLE_WRITES:
            def _refused(*_a, **_k):
                print(f"read-only: {attr} on {self._name} not sent", flush=True)
                if self._name not in QUIET:
                    _notice()
                raise ReadOnlyError(f"Read-only (trial ended): {attr} on {self._name}")
            return _refused
        return getattr(self._b, attr)


class _Bucket:
    def __init__(self, bucket):
        self._b = bucket

    def __getattr__(self, attr):
        if attr in _STORAGE_WRITES:
            def _refused(*_a, **_k):
                _notice()
                raise ReadOnlyError("Read-only (trial ended): storage write")
            return _refused
        return getattr(self._b, attr)


class _Storage:
    def __init__(self, storage):
        self._s = storage

    def from_(self, bucket_id):
        return _Bucket(self._s.from_(bucket_id))

    def __getattr__(self, attr):
        return getattr(self._s, attr)


class _Client:
    def __init__(self, client):
        self._c = client

    def table(self, name):
        real = self._c.table(name)
        return real if name in WRITABLE else _Table(real, name)

    from_ = table

    @property
    def storage(self):
        return _Storage(self._c.storage)

    def __getattr__(self, attr):            # auth, rpc, postgrest, functions…
        return getattr(self._c, attr)


def wrap(client):
    """The client as this session may use it."""
    return _Client(client) if active() else client
