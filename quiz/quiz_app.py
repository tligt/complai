"""
quiz/quiz_app.py — S45 stage 1. Standalone public NIS2 self-check.

Lives in its own directory, not the repo root, and that is load-bearing, not
tidiness. Streamlit's legacy multipage auto-discovery lists any `pages/`
directory sitting next to whichever script it runs as its own navigation —
confirmed live, running this file from the repo root put every gated page
(documents, gap, obligations, ...) in the public quiz's sidebar, each one
directly executable with no is_logged_in() check, since that gate lives only
in app.py's own script, not in the individual pages. Only accident (an
AttributeError on empty session_state) kept it from rendering real data.
Putting this script in a directory with no `pages/` sibling removes that
discovery path entirely, rather than relying on nothing being clicked.

Otherwise unchanged from the design: a SEPARATE entry point, not a page
inside app.py. app.py gates every page behind is_logged_in() before
st.navigation even builds (D-104) — routing a public lead magnet through that
gate means punching a hole in the app's real security boundary for a
marketing tool. This file has no import of auth.py, database.py, or app.py,
makes no Supabase call, and writes nothing anywhere. It is deployed
separately (its own Streamlit Cloud app, or embedded wherever the marketing
site needs it) pointing at this same repository, with `quiz/quiz_app.py` as
the entry point.

NOT A COMPLIANCE AUDIT. Acquisition, not accuracy (D-107) — ten questions,
one per NIS2 Art. 21(2) measure category, a hardcoded point rubric, no
document review, no site crawl. The real assessment lives behind signup, in
the product, reusing the existing gap-assessment engine (pages/gap.py). This
quiz's only job is converting a visitor into a signup.

VERIFY BEFORE TREATING AS LEGAL CONTENT. The ten categories below follow the
structure of NIS2 Art. 21(2)(a)-(j) as a recognisable shape, same instinct as
S27's EDPB-template match — but the question wording and point weights are
draft marketing copy, not reviewed legal text. Same standard this log already
holds itself to for compliance-adjacent copy (D-42, D-51): check before it is
treated as authoritative.
"""

import os
import streamlit as st

st.set_page_config(
    page_title="RECOSA — NIS2 Quick Check",
    page_icon="🛡️",
    layout="centered",
)

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "http://localhost:8501").rstrip("/")

# One question per NIS2 Art. 21(2) measure category, in order (a)-(j).
# Each option's index is its point value: 0 (not addressed) to 3 (documented
# and regularly reviewed). Max score 30.
_OPTIONS = [
    "We haven't addressed this",
    "We do this informally, on an ad hoc basis",
    "We have a documented process, not regularly reviewed",
    "We have a documented process, reviewed and tested regularly",
]

QUESTIONS = [
    {
        "category": "Risk analysis & security policy",
        "question": "Do you have a written information security policy, "
                     "informed by an assessment of your actual risks?",
    },
    {
        "category": "Incident handling",
        "question": "If you had a security incident tomorrow, is there a "
                     "written process for detecting, reporting and handling it?",
    },
    {
        "category": "Business continuity",
        "question": "Do you have tested backups and a plan for keeping the "
                     "business running through a major disruption?",
    },
    {
        "category": "Supply chain security",
        "question": "Do you assess the security of the suppliers and "
                     "service providers your business depends on?",
    },
    {
        "category": "Secure development & vulnerability handling",
        "question": "Do you have a process for finding and fixing security "
                     "vulnerabilities in the systems you build or buy?",
    },
    {
        "category": "Measuring effectiveness",
        "question": "Do you check, on some regular schedule, whether your "
                     "security measures are actually working?",
    },
    {
        "category": "Cyber hygiene & training",
        "question": "Do employees receive any regular training on security "
                     "basics — phishing, passwords, safe handling of data?",
    },
    {
        "category": "Cryptography & encryption",
        "question": "Is sensitive data encrypted, both in transit and at rest?",
    },
    {
        "category": "HR security & access control",
        "question": "Is system access tied to role, reviewed periodically, and "
                     "revoked promptly when someone leaves?",
    },
    {
        "category": "Multi-factor authentication",
        "question": "Is multi-factor authentication required for access to "
                     "your important systems?",
    },
]

_BANDS = [
    (10, "Early stage",
     "Several of the measures NIS2 expects aren't in place yet. That's "
     "normal at this stage — the important part is knowing where the gaps "
     "are before a regulator or an incident finds them for you."),
    (20, "Developing",
     "Some real foundations exist, but most aren't formalised or reviewed "
     "on a schedule yet — which is usually where NIS2 readiness actually "
     "gets tested."),
    (30, "Good foundation",
     "A solid starting point. The next step is usually less about adding "
     "new measures and more about documenting and testing the ones already "
     "in place."),
]


def _band_for(score: int) -> tuple[str, str]:
    for ceiling, label, blurb in _BANDS:
        if score <= ceiling:
            return label, blurb
    return _BANDS[-1][1], _BANDS[-1][2]


st.title("🛡️ NIS2 Quick Check")
st.caption(
    "10 questions, 2 minutes. A rough read on where your business stands "
    "against NIS2's core security expectations — not a compliance audit."
)
st.divider()

with st.form("nis2_quiz"):
    answers = []
    for i, q in enumerate(QUESTIONS):
        st.markdown(f"**{i + 1}. {q['category']}**")
        choice = st.radio(
            q["question"], options=range(4),
            format_func=lambda i: _OPTIONS[i],
            key=f"q_{i}", index=None, label_visibility="visible",
        )
        answers.append(choice)
        st.write("")
    submitted = st.form_submit_button("See my result", type="primary")

if submitted:
    if any(a is None for a in answers):
        st.warning("Answer all 10 questions to see your result.")
    else:
        score = sum(answers)
        label, blurb = _band_for(score)
        st.divider()
        st.subheader(f"Your result: {score}/30 — {label}")
        st.write(blurb)
        st.caption(
            "This is a lightweight self-check, not a certified NIS2 "
            "compliance audit — it doesn't examine your actual documents or "
            "systems. A full assessment, scored against every applicable "
            "obligation, is available free inside RECOSA."
        )
        st.link_button(
            "Get your full NIS2 maturity assessment — start free →",
            APP_BASE_URL, type="primary",
        )
