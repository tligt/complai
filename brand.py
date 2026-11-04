"""
brand.py — the look shared by the client app (app.py) and the back office
(admin_app.py), D-140.

The colour and font come from the theme, .streamlit/config.toml: navy
#003366 as the primary colour (main buttons, selected controls) and Public
Sans, as on recosa.eu and the free check. This adds what a theme cannot set:
the navy sidebar with readable text on it, the shape of the buttons, the
metric cards, the content width, and the logo at the top of the sidebar.

Before D-140 each app carried its own copy, and the back office's had drifted:
white on turquoise buttons (2.1:1), red form buttons, the sidebar contrast
fixes of the usability audit (C1-C3) never applied, and "Inter", a font
neither app loaded.
"""

import streamlit as st

SHELL_CSS = """
<style>
/* Hide Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #003366 !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] small {
    color: #CBD5E1 !important;
}
[data-testid="stSidebar"] a {
    color: #CBD5E1 !important;
    border-radius: 6px !important;
    padding: 0.4rem 0.75rem !important;
}
[data-testid="stSidebar"] a:hover {
    background: rgba(255,255,255,0.08) !important;
    color: white !important;
}
[data-testid="stSidebar"] [aria-current="page"],
[data-testid="stSidebar"] [aria-selected="true"] {
    background: rgba(20,199,213,0.18) !important;
    border-left: 3px solid #14C7D5 !important;
    color: white !important;
}
/* Nav section labels. stNavSectionHeader is the element Streamlit 1.61
   renders; the old stSidebarNavSeparator rule matched nothing, so the
   group titles came out dark grey on dark blue (usability audit C3). */
[data-testid="stNavSectionHeader"],
[data-testid="stNavSectionHeader"] * {
    color: #94A3B8 !important;
    visibility: visible !important;
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}
/* "View N more" — was dark grey on dark blue (audit C2). */
[data-testid="stSidebarNavViewButton"],
[data-testid="stSidebarNavViewButton"] * {
    color: #E2E8F0 !important;
    font-weight: 600 !important;
}
/* Sidebar buttons (Log out, New chat…): the text rule above made their
   label pale grey on Streamlit's near-white button, 1.4:1 (audit C1). */
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.45) !important;
}
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button * {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.10) !important;
}
/* Sidebar inputs */
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.15) !important;
    color: white !important;
}
/* Streamlit 1.61's select box is a text input inside; the company switcher's
   value was dark grey on dark blue. */
[data-testid="stSidebar"] [data-testid="stSelectbox"] input {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stSelectbox svg {
    fill: #94A3B8 !important;
}

/* ── Buttons ── */
/* Navy with white text, as on recosa.eu and the free check (D-140): the
   theme's primaryColor colours them; this keeps the shape the same on plain,
   form-submit and link buttons. (Turquoise with navy text, audit M12, was
   the earlier fix for white on turquoise at 2.1:1; navy and white is 12.6:1.) */
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"],
[data-testid="stBaseLinkButton-primary"] {
    border: none !important;
    font-weight: 600 !important;
    border-radius: 6px !important;
}
/* White label on every navy button. Needed where a page colours its text
   (the login pages set .stApp p, which beat the colour the button passes
   down: "Go to RECOSA" came out navy on navy, 4 Nov). */
.stButton > button[kind="primary"] p,
[data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] p,
[data-testid="stBaseLinkButton-primary"] p {
    color: #FFFFFF !important;
}

/* ── Content width ── */
.main .block-container {
    max-width: 1200px !important;
    padding: 2rem 3rem !important;
    margin: 0 auto !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: #F4F7FA;
    border-radius: 8px;
    padding: 1rem;
    border: 1px solid #E2E8F0;
}
</style>
"""

# The "R" mark of recosa.eu, white on the navy sidebar.
_MARK = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' "
         "height='28'><rect width='28' height='28' rx='7' fill='white'/><text x='14' "
         "y='19.5' font-family='Arial,sans-serif' font-weight='800' font-size='15' "
         "fill='%23003366' text-anchor='middle'>R</text></svg>")


def apply_shell() -> None:
    """The shared look, once per run, before anything is drawn."""
    st.markdown(SHELL_CSS, unsafe_allow_html=True)


def apply_logo(label: str, native_nav: bool = False) -> None:
    """The mark and the name at the top of the sidebar. native_nav: the menu
    is Streamlit's own (the back office), which needs pushing down; the
    client app draws its menu itself, as sidebar content."""
    room = ('[data-testid="stSidebarNav"] { margin-top: 70px !important; }' if native_nav else
            '[data-testid="stSidebarUserContent"] { padding-top: 1.25rem !important; }')
    st.markdown(f"""
<style>
{room}
[data-testid="stSidebar"]::before {{
    content: "{label}";
    display: block;
    position: absolute;
    top: 0; left: 0; right: 0;
    padding: 1rem 1rem 0.75rem 3.1rem;
    min-height: 1.6rem;
    line-height: 1.6rem;
    font-size: 1.05rem;
    font-weight: 800;
    letter-spacing: .5px;
    color: white !important;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    background: #003366 url("{_MARK}") no-repeat 1rem 0.95rem;
    z-index: 999;
}}
</style>
""", unsafe_allow_html=True)
