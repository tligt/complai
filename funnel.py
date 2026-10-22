"""
funnel.py — S49. The free checks' content and scoring, shared by the public
app (quiz/quiz_app.py) and the client app (the result page after signup).

NO STREAMLIT. NO SUPABASE. NO I/O. The public app imports this, and it must
stay importable there with only the public app's own requirements.

The quiz questions, weights and advice are DRAFT MARKETING COPY, not reviewed
legal text (see quiz/quiz_app.py's header, and D-115: reviewed before launch).
"""

from __future__ import annotations

from urllib.parse import urlencode

# Version of the marketing-consent wording shown beside the email field.
# Stored with every lead that ticked it; change it whenever the wording does.
CONSENT_VERSION = "2026-10-22"
CONSENT_TEXT = (
    "Also send me occasional RECOSA updates on NIS2 and GDPR. "
    "I can unsubscribe at any time."
)

TOOL_QUIZ = "nis2_quiz"
TOOL_WEBSITE = "website_check"

# One question per NIS2 Art. 21(2) measure category, in order (a)-(j).
# Each option's index is its point value: 0 (not addressed) to 3 (documented
# and regularly reviewed). Max score 30.
OPTIONS = [
    "We haven't addressed this",
    "We do this informally, on an ad hoc basis",
    "We have a documented process, not regularly reviewed",
    "We have a documented process, reviewed and tested regularly",
]

# "obligations": the catalogue entries (obligations.py) a quiz answer is
# recorded against as a DECLARED answer after signup — the lowest precedence
# in the obligation register, so any real assessment or document overrides
# it. "Measuring effectiveness" maps to none: no catalogue entry is about it.
QUESTIONS = [
    {
        "category": "Risk analysis & security policy",
        "question": "Do you have a written information security policy, "
                    "informed by an assessment of your actual risks?",
        "advice": "Start with a short risk assessment of your main systems and "
                  "write the security policy from it — NIS2 expects the policy "
                  "to follow from the risks, not a template.",
        "obligations": ["nis2_01"],
    },
    {
        "category": "Incident handling",
        "question": "If you had a security incident tomorrow, is there a "
                    "written process for detecting, reporting and handling it?",
        "advice": "Write down who decides, who is called and what is reported "
                  "to the authority within 24 hours. NIS2's reporting clock "
                  "starts when you become aware, not when you are ready.",
        "obligations": ["nis2_02"],
    },
    {
        "category": "Business continuity",
        "question": "Do you have tested backups and a plan for keeping the "
                    "business running through a major disruption?",
        "advice": "Restore a backup for real at least once, and write down "
                  "how long each key system may be down.",
        "obligations": ["nis2_04", "nis2_10"],
    },
    {
        "category": "Supply chain security",
        "question": "Do you assess the security of the suppliers and "
                    "service providers your business depends on?",
        "advice": "List the suppliers your operations depend on and check "
                  "what security commitments their contracts actually contain.",
        "obligations": ["nis2_05"],
    },
    {
        "category": "Secure development & vulnerability handling",
        "question": "Do you have a process for finding and fixing security "
                    "vulnerabilities in the systems you build or buy?",
        "advice": "Decide who applies security updates and how fast, and keep "
                  "a record of what was patched.",
        "obligations": ["nis2_08"],
    },
    {
        "category": "Measuring effectiveness",
        "question": "Do you check, on some regular schedule, whether your "
                    "security measures are actually working?",
        "advice": "Pick a few measures (backups restored, patches applied, "
                  "accounts reviewed) and check them on a fixed schedule.",
        "obligations": [],
    },
    {
        "category": "Cyber hygiene & training",
        "question": "Do employees receive any regular training on security "
                    "basics — phishing, passwords, safe handling of data?",
        "advice": "A short yearly session plus a phishing reminder covers the "
                  "basics; keep a record of who attended.",
        "obligations": ["nis2_09"],
    },
    {
        "category": "Cryptography & encryption",
        "question": "Is sensitive data encrypted, both in transit and at rest?",
        "advice": "Check laptops, backups and file shares for encryption at "
                  "rest, and that every external connection uses TLS.",
        "obligations": ["nis2_07"],
    },
    {
        "category": "HR security & access control",
        "question": "Is system access tied to role, reviewed periodically, and "
                    "revoked promptly when someone leaves?",
        "advice": "Make account removal part of every departure, and review "
                  "who has admin rights twice a year.",
        "obligations": ["nis2_06"],
    },
    {
        "category": "Multi-factor authentication",
        "question": "Is multi-factor authentication required for access to "
                    "your important systems?",
        "advice": "Turn on MFA for email, admin accounts and remote access "
                  "first — it is the cheapest measure with the biggest effect.",
        "obligations": ["nis2_06"],
    },
]

MAX_SCORE = 3 * len(QUESTIONS)

BANDS = [
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

# How one answer reads per area, and the register status it is declared as.
LEVELS = ["Not addressed", "Informal", "Documented", "Documented and tested"]
_DECLARED_STATUS = ["missing", "partial", "partial", "compliant"]


def score(answers: list[int]) -> int:
    return sum(answers)


def band(total: int) -> tuple[str, str]:
    for ceiling, label, blurb in BANDS:
        if total <= ceiling:
            return label, blurb
    return BANDS[-1][1], BANDS[-1][2]


def breakdown(answers: list[int]) -> list[dict]:
    """One row per area, weakest first (ties keep question order)."""
    rows = [
        {"category": q["category"], "answer": a, "level": LEVELS[a],
         "advice": q["advice"]}
        for q, a in zip(QUESTIONS, answers)
    ]
    return sorted(rows, key=lambda r: r["answer"])


def weak_areas(answers: list[int]) -> int:
    """Areas not yet documented — the count shown on the locked teaser."""
    return sum(1 for a in answers if a < 2)


def encode_answers(answers: list[int]) -> str:
    return "".join(str(a) for a in answers)


def decode_answers(code: str | None) -> list[int] | None:
    """Ten digits 0-3, or None. Anything else is ignored, never trusted."""
    if (not code or len(code) != len(QUESTIONS)
            or any(c not in "0123" for c in code)):
        return None
    return [int(c) for c in code]


def declared_responses(answers: list[int]) -> dict[str, str]:
    """{obligation_id: status} to declare from the quiz. Where two answers map
    to one obligation (access control and MFA), the weaker one wins."""
    out: dict[str, str] = {}
    for q, a in zip(QUESTIONS, answers):
        for ob in q["obligations"]:
            status = _DECLARED_STATUS[a]
            prev = out.get(ob)
            if prev is None or _DECLARED_STATUS.index(status) < _DECLARED_STATUS.index(prev):
                out[ob] = status
    return out


def domains_match(email: str, site_domain: str) -> bool:
    """S43's rule for the public app, which has no database.py: the email is
    at the checked site's domain, or the two are subdomain-related. The same
    check runs again in submit_lead(), which is what actually enforces it."""
    e = email.strip().lower().rsplit("@", 1)[-1]
    s = site_domain.strip().lower()
    return bool(e and s) and (e == s or e.endswith("." + s) or s.endswith("." + e))


def signup_url(app_base_url: str, tool: str, *, answers: list[int] | None = None,
               site: str | None = None) -> str:
    """The CTA link into the client app's signup. Carries the answers or the
    checked site and the source — never the email or anything personal."""
    params = {"src": tool}
    if answers is not None:
        params["quiz"] = encode_answers(answers)
    if site:
        params["site"] = site
    return f"{app_base_url.rstrip('/')}/?{urlencode(params)}"
