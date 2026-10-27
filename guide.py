"""
guide.py — user tips and the glossary (usability audit batch 3, 27 Oct 2026).

page_tip(key): a short "What is this page for, and what do I do here?" panel
at the top of a page, closed for good with "Got it" (profiles.dismissed_tips).
Account has "Show page tips again".

GLOSSARY: the terms used everywhere and defined nowhere, in plain language,
shown on the Glossary page. Definitions say what the term means for a small
company, not the full legal text; the legal reference follows.
"""

import streamlit as st

TIPS = {
    "dashboard": (
        "Home",
        "Where you stand, and what to do next. The box at the top lists the three most "
        "urgent tasks — **Fix it** takes you to the page where each is done. New here? "
        "Follow the getting-started steps first.",
    ),
    "action_plan": (
        "Action plan",
        "Everything outstanding for this company, most urgent first. RECOSA works the "
        "list out from your systems, documents and answers — it updates by itself when "
        "you fix something. If a task does not apply to you, dismiss it with a reason.",
    ),
    "obligations": (
        "Obligations",
        "Every requirement of the regulations that apply to you, with its status. Open "
        "one to see what it means and to record what you do about it — a date, a note, "
        "evidence. Statuses RECOSA works out itself are marked as such.",
    ),
    "gap": (
        "Gap Assessment",
        "A check of your documents and practices against the regulations, with a score "
        "per regulation. Run it once to get a baseline, and again after big changes. "
        "Its findings feed the action plan.",
    ),
    "risk": (
        "Risk assessments",
        "Which of your activities need a DPIA (a privacy risk assessment), and the "
        "register of security risks NIS2 asks for. RECOSA flags the activities from your "
        "Systems page; you assess and record the decision.",
    ),
    "inventory": (
        "Systems",
        "The tools you use (systems), what you do with personal data (activities) and "
        "who you share it with. Fill this in once: your register of processing, "
        "processing agreements and cookie policy are generated from it.",
    ),
    "documents": (
        "Documents",
        "**Your documents** lists what you have: review each one, download it, and "
        "mark it **in force** when you adopt it. **Generate a document** makes a new "
        "one from your company profile and systems. The Compliance record shows "
        "which version applies and since when.",
    ),
    "compliance_record": (
        "Compliance record",
        "The documents your company operates under, by version and date — the page to "
        "show an auditor. Read-only: documents are produced and adopted on Documents.",
    ),
    "incidents": (
        "Incidents",
        "Log a security incident or data breach as soon as you find out: the legal "
        "clocks start then. RECOSA alerts your team, works out which notifications are "
        "required and drafts them. Set up your incident team before you need it.",
    ),
    "wording": (
        "Incident wording",
        "Five short texts that go into your incident response and continuity plans. "
        "RECOSA drafts each one from your profile; correct it so it says what you "
        "really do.",
    ),
    "audit": (
        "Web Audit",
        "Checks a website for cookie banners, privacy pages, trackers and other visible "
        "compliance points. Subscribe to re-check it automatically.",
    ),
    "chat": (
        "Assistant",
        "Ask a compliance question in your own words. Answers are based on the "
        "regulations and on your company profile, with the sources listed. It is "
        "guidance, not legal advice.",
    ),
    "company": (
        "Company profile",
        "Who the company is and what applies to it. Documents, obligations and the "
        "assistant read from here, so keep it up to date.",
    ),
}

GLOSSARY = [
    ("Activity (processing activity)",
     "Something you do with personal data for a purpose — running payroll, sending a "
     "newsletter. Each one goes in your register of processing.", "GDPR Art. 30"),
    ("AI Act (EU AI Act)",
     "The EU law on artificial intelligence. Most obligations depend on whether you build "
     "or only use an AI system, and on how risky its use is.", "Regulation (EU) 2024/1689"),
    ("Controller",
     "The organisation that decides why and how personal data is used. For your own staff "
     "and customers, that is you.", "GDPR Art. 4(7)"),
    ("CSIRT",
     "The national team that receives NIS2 incident reports and helps with cyber "
     "incidents — CCB in Belgium, ANSSI's CERT-FR in France.", "NIS2 Art. 10"),
    ("DPA (data processing agreement)",
     "The contract you must have with every supplier that handles personal data for you "
     "— your payroll provider, your email host.", "GDPR Art. 28"),
    ("Data protection authority",
     "The regulator for personal data — the APD/GBA in Belgium, the CNIL in France. "
     "Breaches are reported to it.", "GDPR Art. 51"),
    ("Digital Omnibus",
     "A 2026 EU package that simplified parts of the AI Act and other digital laws — for "
     "example, AI literacy became a duty to make an effort rather than a guaranteed "
     "result.", "Regulation (EU) 2026/1744"),
    ("DPIA (data protection impact assessment)",
     "A written risk assessment required before high-risk processing, such as monitoring "
     "staff or large-scale sensitive data.", "GDPR Art. 35"),
    ("DPO (data protection officer)",
     "A person who advises on and checks GDPR compliance. Mandatory only in some cases "
     "(public bodies, large-scale monitoring or sensitive data).", "GDPR Art. 37"),
    ("Essential / important entity",
     "The two NIS2 categories. Essential: large companies in the most critical sectors, "
     "checked proactively. Important: the rest of NIS2's scope, checked after an incident "
     "or complaint. Both owe the same measures.", "NIS2 Art. 3, Annexes I and II"),
    ("In force",
     "A document your company has adopted and operates under, from a given date. A "
     "generated document is a draft until you mark it in force.", ""),
    ("NIS2",
     "The EU cybersecurity law for medium and large companies in listed sectors: security "
     "measures, incident reporting, management accountability.", "Directive (EU) 2022/2555"),
    ("Personal data breach",
     "Personal data lost, stolen, disclosed or made unavailable by accident or attack. "
     "Reportable to the authority within 72 hours unless unlikely to cause harm.",
     "GDPR Art. 4(12), 33"),
    ("Processor",
     "A supplier that handles personal data on your behalf and on your instructions — "
     "cloud software, an accountant. You need a DPA with each.", "GDPR Art. 4(8)"),
    ("RoPA (register of processing activities)",
     "The list of everything you do with personal data: what, why, whose, how long, who "
     "receives it. Mandatory for almost every company.", "GDPR Art. 30"),
    ("RTO / RPO",
     "Recovery time objective: how long a system may be down. Recovery point objective: "
     "how much recent data you can afford to lose — a nightly backup means up to a day.",
     "NIS2 Art. 21(2)(c)"),
    ("SCC (standard contractual clauses)",
     "EU-approved contract terms that make it lawful to send personal data to a supplier "
     "outside the EU, for example in the US.", "GDPR Art. 46"),
    ("Significant incident",
     "A NIS2 incident serious enough to report: it causes severe disruption or financial "
     "loss, or considerable damage to others.", "NIS2 Art. 23(3)"),
]


def _dismissed() -> set:
    if "dismissed_tips" not in st.session_state:
        from database import get_user_profile
        from auth import get_user_id
        st.session_state.dismissed_tips = set(
            get_user_profile(get_user_id()).get("dismissed_tips") or [])
    return st.session_state.dismissed_tips


def page_tip(key: str) -> None:
    """The page's tip, or — once closed — a small line that shows it on
    hover, so a closed tip can still be read."""
    if key not in TIPS:
        return
    title, text = TIPS[key]
    if key in _dismissed():
        # Streamlit draws the small (?) icon; hovering it shows the tip.
        st.caption("What is this page for?", help=text)
        return
    with st.container(border=True):
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"💡 **What is this page for?** {text}")
        if c2.button("Got it", key=f"tip_ok_{key}", use_container_width=True):
            from database import set_dismissed_tips
            from auth import get_user_id
            st.session_state.dismissed_tips = _dismissed() | {key}
            set_dismissed_tips(get_user_id(), list(st.session_state.dismissed_tips))
            st.rerun()


def reset_tips() -> None:
    from database import set_dismissed_tips
    from auth import get_user_id
    st.session_state.dismissed_tips = set()
    set_dismissed_tips(get_user_id(), [])


def notice(key: str, text: str) -> None:
    """A one-time note about a change, closed for good with "Got it" — same
    storage as the page tips, so "Show page tips again" brings it back too."""
    if key in _dismissed():
        return
    with st.container(border=True):
        c1, c2 = st.columns([6, 1])
        c1.markdown(f"ℹ️ {text}")
        if c2.button("Got it", key=f"tip_ok_{key}", use_container_width=True):
            from database import set_dismissed_tips
            from auth import get_user_id
            st.session_state.dismissed_tips = _dismissed() | {key}
            set_dismissed_tips(get_user_id(), list(st.session_state.dismissed_tips))
            st.rerun()
