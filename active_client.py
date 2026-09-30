"""
active_client.py — S47: which client should this page operate on.

Streamlit-dependent (renders a selector, can call st.stop()), so this sits
alongside tier_gates.py rather than in cached_reads.py, which stays a pure
data-fetch layer by design.

Synthesizes two patterns that already existed in the codebase, separately,
neither complete alone: gap.py/documents.py's inline "Select client"
selector (works, but page-local — a choice made there had no effect
anywhere else) and inventory.py's refusal to guess when more than one
client exists and nothing is selected (safe, but the warning it showed had
nowhere on the page to act on it).

Before this, six pages queried `clients` filtered only by user_id with
`.single()` — correct only because no account had ever had more than one
client. The first one that did (18 Sept 2026) broke it immediately.
"""

import streamlit as st

from cached_reads import load_accessible_clients


def get_active_client(user_id: str) -> dict | None:
    """The client this page should operate on.

    Returns None only after already calling st.stop() — the caller does
    not need its own stop handling in that case.

    0 clients: tells the client to create one, stops.
    1 client: returned directly, no UI shown — the Starter/Professional
      case, where the user IS the company, and asking would be friction
      over a choice that does not exist.
    2+ clients: renders "Select client" at the top of the page, EVERY
      time, showing the current client and letting the user switch right
      there (30 Sept 2026: it used to show only until a first choice,
      then disappeared, leaving Chat's picker as the only way to switch).
      Nothing is preselected until a first choice is made; the page waits.
      The choice goes into st.session_state.selected_client, so it carries
      into every other page for the rest of the session.

    S38: "clients" here means accessible clients — owned, or granted via
    workspace_members — not only owned ones. A workspace member with
    access to exactly one client gets the same silent auto-select an
    owner with one client always has; 2+ accessible clients (owner with
    several, or a member added to more than one) gets the same picker.
    """
    clients = load_accessible_clients(user_id) or []

    if not clients:
        st.info(
            "You don't have a company profile yet. Open **➕ New client** in "
            "the sidebar (below the page list) to set one up."
        )
        st.stop()
        return None

    if len(clients) == 1:
        st.session_state.selected_client = clients[0]
        return clients[0]

    # More than one client — the Advisory case. Guessing would silently
    # attach this page's work to the wrong company (support.py and
    # activity.py did exactly that before this module existed), so nothing
    # is preselected until the user has chosen once. Found 30 Sept 2026:
    # preselecting the first client stored it on the very first run and
    # then ignored whatever the user picked next.
    by_id = {c["id"]: c for c in clients}
    current = st.session_state.get("selected_client") or {}
    # Re-read from the list: the stored dict may be stale (e.g. regulations
    # edited since), or no longer accessible (workspace access revoked).
    current = by_id.get(current.get("id"))
    names = [c["company_name"] for c in clients]

    # Keyed on the current client: when the client changes anywhere (here,
    # or Chat's own picker) the widget is recreated showing it, instead of
    # keeping a stale value in its own widget state.
    widget_key = f"active_client_select_{current['id'] if current else 'none'}"
    chosen = st.selectbox(
        "Select client", options=names, key=widget_key,
        index=names.index(current["company_name"]) if current else None,
        placeholder="Choose a client",
        on_change=_switch_client, args=(widget_key, clients),
    )
    picked = next((c for c in clients if c["company_name"] == chosen), None)
    if not picked:
        st.stop()
        return None

    st.session_state.selected_client = picked
    return picked


def _switch_client(widget_key: str, clients: list) -> None:
    """on_change for the picker: store the new client before the rerun, and
    start a fresh chat conversation, as Chat's own picker does when the
    client changes. Otherwise Chat would show the previous client's
    conversation under the new client."""
    name = st.session_state.get(widget_key)
    picked = next((c for c in clients if c["company_name"] == name), None)
    if not picked:
        return
    st.session_state.selected_client = picked
    st.session_state.history_loaded = False
    st.session_state.messages = []
    st.session_state.pop("session_id", None)
