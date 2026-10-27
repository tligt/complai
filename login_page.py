"""
login_page.py — the page shown before login (D-127, 27 Oct 2026).

Redesigned after recosa.eu, which visitors arrive from: Public Sans, navy
#003366 for headings and the one main button, slate #31506D for text, the
turquoise #14C7D5 only for small labels, pale #E8EDF2 panels, white cards
with soft corners. A short pitch on the left, the form card (auth.login_ui)
on the right; on a phone Streamlit stacks the columns, card first.

Everything here is scoped to this page: the app's own styles (app.py) stay
as they are.
"""

import streamlit as st

from auth import login_ui, set_new_password_ui
from database import TRIAL_DAYS

WEBSITE_URL = "https://www.recosa.eu"

_CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;700;800&display=swap");
[data-testid="stSidebar"] { width: 0 !important; min-width: 0 !important; overflow: hidden !important; }
[data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"] { display: none !important; }
.stApp { background: #FFFFFF; }
/* Not on span/div: the password field's eye is an icon-font span. */
.stApp, .stApp p, .stApp label, .stApp input, .stApp button, .stApp a {
    font-family: 'Public Sans', -apple-system, BlinkMacSystemFont, sans-serif;
}
.main .block-container, [data-testid="stMainBlockContainer"] {
    max-width: 1040px !important; padding: 1.25rem 1.5rem 3rem !important;
}
.stApp p, .stApp li, .stApp label { color: #31506D; }
.stApp h1, .stApp h2, .stApp h3 { color: #003366 !important; font-weight: 800 !important; }

/* Top bar */
.lp-top { display: flex; align-items: center; gap: 10px; padding: 0 0 18px;
          border-bottom: 1px solid #EEF1F4; margin-bottom: 36px; }
.lp-mark { width: 32px; height: 32px; border-radius: 8px; background: #003366; color: #fff;
           display: flex; align-items: center; justify-content: center; font-weight: 800; }
.lp-name { color: #003366; font-weight: 800; font-size: 18px; letter-spacing: .5px; }
.lp-back { margin-left: auto; color: #31506D !important; font-size: 14px; font-weight: 700;
           text-decoration: none; }

/* Pitch */
.lp-pill, .auth-pill { display: inline-block; background: rgba(20,199,213,.14); color: #0B7F89;
           font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 999px; }
.lp-h { color: #003366; font-weight: 800; font-size: 40px; line-height: 1.12; margin: 16px 0 18px; }
.lp-li { display: flex; gap: 10px; color: #31506D; font-size: 16px; line-height: 1.5; margin: 12px 0; }
.lp-li span.tick { color: #14C7D5; font-weight: 800; }
.lp-note { background: #E8EDF2; border-radius: 14px; padding: 14px 16px; margin-top: 24px;
           color: #31506D; font-size: 14px; line-height: 1.5; }
.lp-note b { color: #003366; }

/* Form card */
.st-key-auth_card { background: #FFFFFF; border: 1px solid #E3E8EE !important;
                    border-radius: 18px !important; padding: 22px 22px 18px !important; }
.st-key-auth_card label p { color: #003366 !important; font-weight: 700 !important; font-size: 13px !important; }
.st-key-auth_card input { font-size: 15px !important; }
/* Streamlit 1.61 draws the field on stTextInputRootElement. */
.st-key-auth_card [data-testid="stTextInputRootElement"] { border-radius: 8px !important;
    border: 1px solid #D6DDE5 !important; background: #FFFFFF !important; }
.st-key-auth_card [data-testid="stTextInputRootElement"] * { background: transparent !important; }
.st-key-auth_card [data-testid="stTextInputRootElement"]:focus-within { border-color: #003366 !important; }

/* Log in / Sign up switch */
.st-key-auth_switch [data-testid="stButtonGroup"] > div { background: #E8EDF2; border-radius: 10px; padding: 3px; gap: 3px; }
.st-key-auth_switch button { border: none !important; background: transparent !important;
                             border-radius: 8px !important; min-height: 38px; }
.st-key-auth_switch button p { color: #31506D !important; font-weight: 700 !important; }
.st-key-auth_switch button[kind$="Active"], .st-key-auth_switch button[aria-checked="true"] {
    background: #FFFFFF !important; }
.st-key-auth_switch button[kind$="Active"] p, .st-key-auth_switch button[aria-checked="true"] p {
    color: #003366 !important; }

/* Plan cards */
[class*="st-key-plan_"] button { text-align: left !important; justify-content: flex-start !important;
    border: 1px solid #D6DDE5 !important; border-radius: 12px !important; background: #FFFFFF !important;
    padding: 10px 12px !important; min-height: 92px; align-items: flex-start !important; }
[class*="st-key-plan_"] button div, [class*="st-key-plan_"] button [data-testid="stMarkdownContainer"] {
    text-align: left !important; width: 100%; }
[class*="st-key-plan_"] button p { margin: 0 0 2px !important; font-size: 12px !important; line-height: 1.35 !important; color: #31506D !important; }
[class*="st-key-plan_"] button p:first-child { color: #003366 !important; font-size: 15px !important; }
[class*="st-key-plan_"] button p:nth-child(2) { font-weight: 700 !important; font-size: 13px !important; }
[class*="st-key-plan_"] button > div { justify-content: flex-start !important; text-align: left !important; }
[class*="st-key-plan_"][class*="_on"] button { border: 2px solid #003366 !important; background: #F5F8FB !important;
    padding: 9px 11px !important; }

/* Main button: navy, as on recosa.eu */
.st-key-auth_card .stButton > button[kind="primary"] { background: #003366 !important; border: none !important;
    border-radius: 8px !important; min-height: 44px; }
.st-key-auth_card .stButton > button[kind="primary"] p { color: #FFFFFF !important; font-weight: 700 !important; font-size: 15px !important; }
.st-key-auth_card .stButton > button[kind="primary"]:hover { background: #00264D !important; }
/* Text links (Forgot your password?, Back to log in) */
.st-key-auth_card .stButton > button[kind="tertiary"] { padding: 0 !important; min-height: 0 !important; }
.st-key-auth_card .stButton > button[kind="tertiary"] p { color: #003366 !important; font-weight: 700 !important;
    font-size: 13px !important; text-decoration: underline; }

@media (min-width: 640px) {
    .st-key-lp_cols [data-testid="stHorizontalBlock"] { flex-direction: row-reverse; }
    /* ...but not the plan cards inside the form. */
    .st-key-auth_card [data-testid="stHorizontalBlock"] { flex-direction: row; }
}

.auth-lbl { color: #003366; font-weight: 700; font-size: 13px; margin: 2px 0 6px; }
.auth-fine + div, div:has(> .auth-fine) { margin-bottom: 6px; }
.auth-fine { color: #31506D; font-size: 12.5px; line-height: 1.5; text-align: center; margin-top: 6px; }
.auth-fine a { color: #003366 !important; font-weight: 700; }
</style>
"""

_PITCH = f"""
<span class="lp-pill">{TRIAL_DAYS}-day free trial · no card</span>
<div class="lp-h">Your EU compliance co-pilot, ready in minutes.</div>
<div class="lp-li"><span class="tick">✓</span><span>GDPR, NIS2 and the EU AI Act in one place</span></div>
<div class="lp-li"><span class="tick">✓</span><span>Your obligations and an action plan, worked out from your company</span></div>
<div class="lp-li"><span class="tick">✓</span><span>Policies and registers generated from your own systems</span></div>
<div class="lp-li"><span class="tick">✓</span><span>Breach deadlines tracked, notifications drafted</span></div>
<div class="lp-note"><b>Built for SMEs in Belgium and France.</b> Your data is stored in the EU.</div>
"""


def _style() -> None:
    # st.html: a block holding only <style> is applied to the page without
    # taking any room. st.markdown showed the stylesheet as text.
    st.html(_CSS)


def render() -> None:
    """The whole page for a visitor who is not logged in."""
    _style()
    st.markdown(
        '<div class="lp-top"><div class="lp-mark">R</div><span class="lp-name">RECOSA</span>'
        f'<a class="lp-back" href="{WEBSITE_URL}" target="_self">Back to recosa.eu</a></div>',
        unsafe_allow_html=True)
    # The card comes first in the source so that on a phone, where the
    # columns stack, the form is what people see; on a wider screen the CSS
    # puts the pitch back on the left, as on the approved mockup.
    with st.container(key="lp_cols"):
        card, pitch = st.columns([1.05, 1], gap="large")
        with card, st.container(key="auth_card"):
            login_ui()
        with pitch:
            st.markdown(_PITCH, unsafe_allow_html=True)


def render_password_reset() -> None:
    """After a reset link: only the new-password form, same look."""
    _style()
    st.markdown(
        '<div class="lp-top"><div class="lp-mark">R</div><span class="lp-name">RECOSA</span></div>',
        unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid, st.container(key="auth_card"):
        set_new_password_ui()
