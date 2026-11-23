"""
filed_figures_view.py — S76 (23 Nov 2026). On the Company profile: the size
a Belgian company filed with the National Bank, next to the size it declared.

Shown only for a company in Belgium with a company number, and only once the
NBB key is configured (nbb_accounts.configured). A fact with its source and
year, never a silent overwrite: when the filed size and the declared one
disagree, the person chooses.
"""

import streamlit as st

import nbb_accounts as NBB
from i18n import tr


def _eur(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"€{v / 1_000_000:,.2f} M"
    return f"€{v:,.0f}"


@st.fragment
def render(client: dict, user_id: str) -> None:
    if (client.get("country") or "").upper() != "BE" or not NBB.configured():
        return
    if not NBB.cbe_number(client.get("enterprise_number")):
        return
    from database import get_supabase, update_client_fields
    try:
        fig = (get_supabase().table("clients").select("filed_figures, company_size")
               .eq("id", client["id"]).single().execute().data) or {}
    except Exception:
        fig = {}
    declared = fig.get("company_size") or client.get("company_size")
    fig = fig.get("filed_figures") or None

    with st.container(border=True):
        st.markdown(tr("**Filed figures** — National Bank of Belgium"))
        if not fig:
            st.caption(tr("Your latest annual accounts filed with the National Bank give your "
                          "average number of employees and, where filed, your turnover. RECOSA "
                          "reads them for you, free."))
        else:
            year = (fig.get("year_end") or "")[:4] or "?"
            c1, c2, c3 = st.columns(3)
            c1.metric(tr("Employees (average FTE)"), "—" if fig.get("fte") is None else f"{fig['fte']:g}")
            c2.metric(tr("Turnover"), _eur(fig.get("turnover")))
            c3.metric(tr("Financial year"), year)
            st.caption(tr("From the accounts filed on {filed}, read {checked}. Accounts are filed "
                          "6 to 18 months after the year ends; RECOSA checks again every month.")
                       .format(filed=(fig.get("filed_on") or "?")[:10],
                               checked=(fig.get("checked_at") or "?")[:10]))
            band = NBB.size_band(fig.get("fte"))
            if band and declared and band != declared:
                st.warning(tr("Your profile says **{declared}** employees; your filed accounts say "
                              "**{fte:g}** (band {band}).").format(declared=declared, fte=fig["fte"], band=band))
                if st.button(tr("Use the filed size ({band})").format(band=band), key=f"ff_use_{client['id']}"):
                    if update_client_fields(client["id"], {"company_size": band}):
                        from cached_reads import load_clients, load_accessible_clients
                        load_clients.clear()
                        load_accessible_clients.clear()
                        st.session_state.selected_client = {**client, "company_size": band}
                        # The profile form's Employees box is keyed on the
                        # stored size (company.py), so it follows on this rerun.
                        st.rerun()
            nis2 = NBB.nis2_size(fig)
            if nis2 and "NIS2" in (client.get("regulations") or []):
                st.caption(tr("For NIS2, these figures make the company **{size}** (50 staff or "
                              "€10 M turnover is medium). The balance-sheet test is not read here.")
                           .format(size=tr(nis2)))
        if st.button(tr("Read from the National Bank") if not fig else tr("Check again"),
                     key=f"ff_go_{client['id']}"):
            with st.spinner(tr("Asking the National Bank…")):
                got = NBB.refresh_client(client, by=user_id)
            if got:
                st.rerun(scope="fragment")
            else:
                st.info(tr("No standardised annual accounts found for this company number — "
                           "sole traders and most non-profits file none, and some accounts exist "
                           "only as PDF."))
