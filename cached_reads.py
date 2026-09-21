"""Streamlit-cached wrappers around hot database.py reads.

Kept out of database.py deliberately: that module is imported by the
GitHub Actions cron scripts (monitor.py, monitor_marketing.py) and must
stay import-safe without pulling in Streamlit (see database.py's `_st()`
docstring). This module is only ever imported by Streamlit pages, which
already depend on Streamlit unconditionally, so importing it here is safe.

Every wrapper is a short-TTL cache, not a correctness boundary: RLS still
enforces per-user isolation at the database layer, and every cache key
below already includes user_id and/or client_id, so no wrapper can serve
one user's data to another regardless of TTL. The TTL exists to smooth
Streamlit's full-script-rerun-per-click model — every widget interaction
reruns the whole page top to bottom, so without caching, clicking
anything re-fetches everything — not to avoid ever refetching.

Deliberately short rather than paired with explicit .clear() calls on
every write path: those writes are spread across a dozen page files, and
a staleness window this short is not worth that surface area yet. A
client who adopts a document and immediately checks the dashboard sees
the update within one TTL window. Revisit with real invalidation if S32
wants tighter guarantees.
"""

import streamlit as st

import database as _db


@st.cache_data(ttl=20, show_spinner=False)
def load_clients(user_id: str):
    return _db.load_clients(user_id)


@st.cache_data(ttl=20, show_spinner=False)
def load_accessible_clients(user_id: str):
    # S38. Owned clients (same as load_clients) plus anything this account
    # has been granted access to as a workspace member. NOT what
    # tier_gates.client_limit_reached() should ever use — that stays on
    # load_clients, owned-only, on purpose.
    return _db.load_accessible_clients(user_id)


@st.cache_data(ttl=20, show_spinner=False)
def get_register_status(client_id: str, user_id: str):
    return _db.get_register_status(client_id, user_id)


@st.cache_data(ttl=20, show_spinner=False)
def get_current_client_documents(client_id: str, user_id: str, language: str | None = None):
    return _db.get_current_client_documents(client_id, user_id, language)


@st.cache_data(ttl=60, show_spinner=False)
def get_template_languages():
    # RECOSA's own template catalogue - changes only when a template ships,
    # not on client action. Longer TTL is safe.
    return _db.get_template_languages()


@st.cache_data(ttl=60, show_spinner=False)
def get_in_force_template_versions():
    # Same catalogue-not-client-data reasoning as get_template_languages: this
    # changes only when an admin bumps a template revision.
    import template_store as _ts
    return _ts.load_in_force_versions()


@st.cache_data(ttl=20, show_spinner=False)
def load_document_files(user_id: str, client_id: str | None):
    return _db.load_document_files(user_id, client_id)


@st.cache_data(ttl=15, show_spinner=False)
def count_unread_alerts(user_id: str):
    return _db.count_unread_alerts(user_id)


@st.cache_data(ttl=20, show_spinner=False)
def load_audit_files(email_domain: str | None = None, user_id: str | None = None):
    return _db.load_audit_files(email_domain=email_domain, user_id=user_id)
