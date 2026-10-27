import streamlit as st
from database import get_supabase_admin, load_regulatory_updates

st.title("⚙️ COMPLAI Admin")
st.caption(f"Logged in as admin · {st.session_state.user.email}")
st.divider()

# Quick stats
try:
    admin = get_supabase_admin()

    col1, col2, col3, col4 = st.columns(4)

    clients_res = admin.table("clients").select("id", count="exact").execute()
    col1.metric("Total clients", clients_res.count or 0)

    profiles_res = admin.table("profiles").select("id", count="exact").execute()
    col2.metric("Registered users", profiles_res.count or 0)

    pending = load_regulatory_updates(status="pending")
    col3.metric("Pending updates", len(pending),
                delta="needs review" if pending else None,
                delta_color="inverse" if pending else "off")

    docs_res = admin.table("documents").select("id", count="exact").execute()
    col4.metric("Documents generated", docs_res.count or 0)

except Exception as e:
    st.warning(f"Could not load stats: {e}")

st.divider()
st.subheader("Quick navigation")
st.caption("Use the sidebar to navigate between admin sections.")
