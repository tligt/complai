"""
funnel.py — S49. The free checks' content and scoring, shared by the public
app (quiz/quiz_app.py) and the client app (the result page after signup).

NO STREAMLIT. NO SUPABASE. NO I/O. The public app imports this, and it must
stay importable there with only the public app's own requirements.

The quiz questions, weights and advice are DRAFT MARKETING COPY, not reviewed
legal text (see quiz/quiz_app.py's header, and D-115: reviewed before launch).
"""

from __future__ import annotations

import re
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


_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$")


# ── Which rules apply (28 Oct 2026, D-129) ────────────────────────────────
# Four questions before any check, so a visitor is sent to the checks that
# matter for them, not to two tabs that each end the visit. A FIRST
# INDICATION, said so on the page: NIS2 scope in particular depends on the
# national law and on facts four questions cannot ask.

SIZES = {
    "small":  "Fewer than 50 people, and under €10 million turnover",
    "medium": "50 to 249 people, or €10 to 50 million turnover",
    "large":  "250 people or more, or over €50 million turnover",
}

# NIS2 Annexes I and II, grouped as a visitor would name their business.
# "named": the few kinds of entity NIS2 covers whatever their size (Art. 2(2)).
NIS2_SECTORS = {
    "energy":        ("Energy (electricity, oil, gas, heating, hydrogen)", "I"),
    "transport":     ("Transport (air, rail, water, road)", "I"),
    "finance":       ("Banking or financial market infrastructure", "I"),
    "health":        ("Health care, medical labs, pharmaceuticals", "I"),
    "water":         ("Drinking water or waste water", "I"),
    "digital_infra": ("Digital infrastructure (data centres, cloud, hosting, CDN)", "I"),
    "named":         ("DNS, domain registry, trust services or public telecom networks", "I"),
    "ict_services":  ("Managed IT or security services for other businesses", "I"),
    "public":        ("Public administration", "I"),
    "space":         ("Space", "I"),
    "postal":        ("Postal or courier services", "II"),
    "waste":         ("Waste management", "II"),
    "chemicals":     ("Chemicals", "II"),
    "food":          ("Food production, processing or distribution", "II"),
    "manufacturing": ("Manufacturing (medical devices, electronics, machinery, vehicles)", "II"),
    "digital_prov":  ("Online marketplace, search engine or social network", "II"),
    "research":      ("Research organisation", "II"),
}
SECTOR_NONE = "none"
SECTOR_UNSURE = "unsure"
SECTOR_OPTIONS = {**{k: v[0] for k, v in NIS2_SECTORS.items()},
                  SECTOR_NONE: "None of these",
                  SECTOR_UNSURE: "Not sure"}

YES, NO, UNSURE = "yes", "no", "unsure"

# Verdicts per regulation, as shown on the page.
APPLIES, LIKELY, POSSIBLE, UNLIKELY = "applies", "likely", "possible", "unlikely"


def applicable_rules(scope: dict) -> dict[str, tuple[str, str]]:
    """{regulation: (verdict, why)} from the four answers. Pure; the page
    words it, this decides it."""
    size, sector = scope.get("size"), scope.get("sector")
    website, ai = scope.get("website"), scope.get("ai")
    out: dict[str, tuple[str, str]] = {
        "GDPR": (APPLIES, "Every company that handles personal data — customers, staff, "
                          "suppliers' contacts — which is practically every company."),
    }
    if website == YES:
        out["ePrivacy"] = (APPLIES, "Your website: cookies, trackers and what it must tell "
                                    "visitors. The website check reads it for you.")
    if sector == "named":
        out["NIS2"] = (LIKELY, "NIS2 covers these services whatever the company's size.")
    elif sector in NIS2_SECTORS:
        if size in ("medium", "large"):
            kind = "essential" if (size == "large" and NIS2_SECTORS[sector][1] == "I") else "important"
            out["NIS2"] = (LIKELY, f"Your sector is listed in NIS2 and your size is over the "
                                   f"threshold — probably as an {kind} entity.")
        else:
            out["NIS2"] = (POSSIBLE, "Your sector is listed in NIS2. Companies under 50 people "
                                     "are usually out, unless your country names them or you "
                                     "supply a company that is in scope.")
    elif sector == SECTOR_UNSURE:
        out["NIS2"] = (POSSIBLE, "Depends on your sector. The quick check shows where you would "
                                 "stand if it applies.")
    else:
        out["NIS2"] = (UNLIKELY, "Your sector is not one NIS2 lists. Your clients may still ask "
                                 "for its security measures in their contracts.")
    if ai == YES:
        out["EU AI Act"] = (APPLIES, "Companies that use AI tools have duties too: AI literacy "
                                     "for the staff who use them, and telling people when they "
                                     "deal with AI.")
    elif ai == UNSURE:
        out["EU AI Act"] = (POSSIBLE, "If anyone uses AI tools at work — chatbots, writing or "
                                      "recruitment tools — some duties apply.")
    return out


def checks_for(rules: dict[str, tuple[str, str]]) -> list[str]:
    """The free checks worth taking, in the order they are run: the website
    first (30 seconds, no typing), then the NIS2 questions."""
    out = []
    if "ePrivacy" in rules:
        out.append(TOOL_WEBSITE)
    if rules.get("NIS2", (UNLIKELY,))[0] in (LIKELY, POSSIBLE):
        out.append(TOOL_QUIZ)
    return out


def encode_scope(scope: dict) -> str:
    """size.sector.website.ai — short enough for a link, nothing personal."""
    return ".".join(str(scope.get(k) or "") for k in ("size", "sector", "website", "ai"))


def decode_scope(code: str | None) -> dict | None:
    """The four answers, or None. Visitor-controlled: validated, never trusted."""
    parts = (code or "").split(".")
    if len(parts) != 4:
        return None
    size, sector, website, ai = parts
    if (size not in SIZES or sector not in SECTOR_OPTIONS
            or website not in (YES, NO) or ai not in (YES, NO, UNSURE)):
        return None
    return {"size": size, "sector": sector, "website": website, "ai": ai}


# ── The result an account carries ─────────────────────────────────────────
# Since D-129 one free account can carry both checks: the quiz answers, the
# checked site, or both, and the four scope answers when given. "tool" stays
# as the label of the first check (events, the lead's source); code asks
# has_quiz / has_site, never tool, what the result contains.

def pending_from_params(quiz: str | None, site: str | None,
                        scope: str | None = None) -> dict | None:
    """What the signup link carried, as stored on the profile
    (profiles.pending_result). Validated: the link is visitor-controlled."""
    out: dict = {}
    answers = decode_answers(quiz)
    if answers is not None:
        out["answers"] = encode_answers(answers)
    if site:
        site = site.strip().lower()
        if _DOMAIN_RE.match(site):
            out["site"] = site
    if not out:
        return None
    out["tool"] = TOOL_WEBSITE if "site" in out else TOOL_QUIZ
    if decode_scope(scope):
        out["scope"] = scope
    return out


def has_quiz(pending: dict | None) -> bool:
    return bool((pending or {}).get("answers"))


def has_site(pending: dict | None) -> bool:
    return bool((pending or {}).get("site"))


def domains_match(email: str, site_domain: str) -> bool:
    """S43's rule for the public app, which has no database.py: the email is
    at the checked site's domain, or the two are subdomain-related. The same
    check runs again in submit_lead(), which is what actually enforces it."""
    e = email.strip().lower().rsplit("@", 1)[-1]
    s = site_domain.strip().lower()
    return bool(e and s) and (e == s or e.endswith("." + s) or s.endswith("." + e))


def merge_pending(old: dict | None, new: dict) -> dict:
    """A new free check brought to an account that already has one: the new
    checks replace the old, a check not retaken is kept, and the site's proof
    survives when the site is the same."""
    old = old or {}
    out = {k: v for k, v in old.items()
           if k in ("answers", "site", "scope", "site_verified", "verified_by", "site_token")}
    if "site" in new and new["site"] != old.get("site"):
        for k in ("site_verified", "verified_by", "site_token"):
            out.pop(k, None)
    out.update(new)
    out["tool"] = new.get("tool") or old.get("tool")
    return out


def signup_url(app_base_url: str, tool: str, *, answers: list[int] | None = None,
               site: str | None = None, scope: str | None = None,
               login: bool = False) -> str:
    """The CTA link into the client app's signup. Carries the answers, the
    checked site, the scope answers and the source — never the email or
    anything personal. login=True opens the log-in form instead."""
    params = {"src": tool}
    if login:
        params["login"] = "1"
    if answers is not None:
        params["quiz"] = encode_answers(answers)
    if site:
        params["site"] = site
    if scope:
        params["scope"] = scope
    return f"{app_base_url.rstrip('/')}/?{urlencode(params)}"
