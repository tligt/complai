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


def render_company_switcher(user_id: str) -> None:
    """The one company switcher, at the top of the sidebar (usability audit
    batch 2, H1). Shown only to accounts with several companies; a
    one-company account never sees a choice that does not exist.

    Replaces the "Select client" box that sat at the top of every page
    (30 Sept 2026 – 26 Oct 2026) and Chat's own two pickers. The choice goes
    into st.session_state.selected_client, read by get_active_client().
    """
    clients = load_accessible_clients(user_id) or []
    if len(clients) < 2:
        return
    current = _current(clients)
    ids = [c["id"] for c in clients]
    by_id = {c["id"]: c for c in clients}
    # Keyed on the current client, so a change made elsewhere (a new client
    # just created) recreates the widget showing it.
    widget_key = f"company_switcher_{current['id']}"
    st.selectbox(
        "Company", options=ids, index=ids.index(current["id"]),
        format_func=lambda i: by_id[i]["company_name"],
        key=widget_key, on_change=_switch_client, args=(widget_key, clients),
    )


def _current(clients: list) -> dict:
    """The selected client, re-read from the list (the stored dict may be
    stale, or no longer accessible); the first one when nothing is selected.

    Picking the first used to be refused (30 Sept 2026): with the picker at
    the top of each page, a silent default attached work to a company the
    user had not looked at. The switcher now sits in the sidebar on every
    page and each page names the company it works on, so the default is
    visible wherever work is done."""
    by_id = {c["id"]: c for c in clients}
    current = by_id.get((st.session_state.get("selected_client") or {}).get("id"))
    current = current or clients[0]
    st.session_state.selected_client = current
    return current


def get_active_client(user_id: str) -> dict | None:
    """The client this page should operate on.

    Returns None only after already calling st.stop() — the caller does
    not need its own stop handling in that case.

    0 clients: points to the Company profile page, stops.
    1 client: returned directly, no UI shown.
    2+ clients: the one chosen in the sidebar switcher (render_company_switcher),
      the first until a choice is made; the page shows its name.

    S38: "clients" here means accessible clients — owned, or granted via
    workspace_members — not only owned ones.
    """
    clients = load_accessible_clients(user_id) or []

    if not clients:
        st.info(
            "You don't have a company profile yet. Set one up on the "
            "**Company profile** page (Account, in the menu)."
        )
        st.stop()
        return None

    if len(clients) == 1:
        st.session_state.selected_client = clients[0]
        _read_only_notice(clients[0])
        return clients[0]

    current = _current(clients)
    st.caption(f"🏢 {current['company_name']} · change company in the menu")
    _read_only_notice(current)
    return current


def can_edit_active() -> bool:
    """S54: may this session change the active company's data? The
    database decides (can_edit_client); pages use this only to say so
    before a click, never as the guard itself."""
    from database import can_edit
    return can_edit((st.session_state.get("selected_client") or {}).get("role"))


def require_edit(action: str) -> bool:
    """S54: stop an action a read-only person cannot complete before any
    work is done — an AI call, a conversion, a file upload — instead of
    letting the database refuse the result at the end."""
    if can_edit_active():
        return True
    st.warning(f"You have read-only access to this company, so you cannot {action}. "
               "Ask an admin of the company if you need to.")
    return False


def _read_only_notice(client: dict) -> None:
    """S54: a read-only person sees everything; the database refuses their
    changes. Said once, at the top of every page, so a refused save is not a
    surprise."""
    if client.get("role") == "read_only":
        st.info(f"👁️ You have **read-only** access to {client['company_name']}: "
                "you can see everything, but changes will not be saved. "
                "Ask an admin of the company if you need to edit.")


def _switch_client(widget_key: str, clients: list) -> None:
    """on_change for the switcher: store the new client before the rerun, and
    start a fresh chat conversation. Otherwise the Assistant would show the
    previous client's conversation under the new client."""
    chosen = st.session_state.get(widget_key)
    picked = next((c for c in clients if c["id"] == chosen), None)
    if not picked:
        return
    st.session_state.selected_client = picked
    st.session_state.history_loaded = False
    st.session_state.messages = []
    st.session_state.pop("session_id", None)
