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
    2+ clients, st.session_state.selected_client already set (normally by
      Chat's own picker): returned as-is.
    2+ clients, nothing selected yet: renders "Select client" inline,
      right here on the page, and writes the choice into
      st.session_state.selected_client so it carries into every other
      page for the rest of the session — not just this one.

    S38: "clients" here means accessible clients — owned, or granted via
    workspace_members — not only owned ones. A workspace member with
    access to exactly one client gets the same silent auto-select an
    owner with one client always has; 2+ accessible clients (owner with
    several, or a member added to more than one) gets the same picker.
    """
    selected = st.session_state.get("selected_client")
    if selected and selected.get("id"):
        return selected

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

    # More than one client, nothing selected yet — the Advisory case.
    # Guessing would silently attach this page's work to the wrong
    # company (support.py and activity.py did exactly that before this
    # module existed); ask instead, with something to act on right here
    # rather than a warning pointing elsewhere.
    names = [c["company_name"] for c in clients]
    chosen = st.selectbox(
        "Select client", options=names, key="active_client_select",
    )
    picked = next((c for c in clients if c["company_name"] == chosen), None)
    if not picked:
        st.stop()
        return None

    st.session_state.selected_client = picked
    return picked
