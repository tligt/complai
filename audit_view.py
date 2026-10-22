"""
audit_view.py — how a website check's result is shown.

Moved out of pages/audit.py in S49 so the public app (quiz/quiz_app.py) and
the client app's result page draw it the same way. Importing a page module
would run the page, so the renderer lives here.

locked=True is the free summary (D-115): score, risk and the count per
regulation, with the findings themselves held back for the email or an
account.
"""

import streamlit as st

from checklist import OK, WARN, FAIL

STATUS_EMOJI = {OK: "✅", WARN: "⚠️", FAIL: "❌"}


def render_results(audit_result, pdf_bytes=None, is_authenticated=False,
                   locked=False):
    col1, col2, col3 = st.columns(3)
    col1.metric("Score", f"{audit_result.score}/100")
    col2.metric("Risk level", audit_result.risk_level)
    col3.metric("Checks run", len(audit_result.checks))

    c1, c2, c3 = st.columns(3)
    c1.success(f"✅ {audit_result.ok_count} Compliant")
    c2.warning(f"⚠️ {audit_result.warn_count} Need attention")
    c3.error(f"❌ {audit_result.fail_count} Missing")

    st.divider()

    groups = {}
    for check in audit_result.checks:
        groups.setdefault(check.regulation, []).append(check)

    if locked:
        for regulation, items in groups.items():
            ok = sum(1 for i in items if i.status == OK)
            issues = len(items) - ok
            st.markdown(
                f"🔒 **{regulation}** — {ok}/{len(items)} compliant"
                + (f" · {issues} issue{'s' if issues != 1 else ''} to fix" if issues else "")
            )
        st.caption("The findings and how to fix them are in the full report.")
        return

    for regulation, items in groups.items():
        ok = sum(1 for i in items if i.status == OK)
        with st.expander(f"**{regulation}** — {ok}/{len(items)} compliant", expanded=True):
            for item in items:
                emoji = STATUS_EMOJI[item.status]
                st.markdown(f"{emoji} **{item.id} — {item.label}**")
                st.caption(item.detail)

    if is_authenticated and pdf_bytes:
        st.divider()
        st.download_button(
            label="📥 Download PDF Report",
            data=pdf_bytes,
            file_name=f"RECOSA_Audit_{audit_result.url.replace('https://','').replace('http://','')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
