"""
onboarding_emails.py — D-212. The six onboarding emails, in the reader's
language (the English text is the catalogue key, as everywhere: i18n.py).

compose(key, ...) → Email: subject, text, html (None for the personal one,
which is plain text), and the sender to use. Nothing here sends: see
monitor_lifecycle.py.
"""

from __future__ import annotations

import html as _h
from dataclasses import dataclass

from email_sender import email_layout
from i18n import translate as tr
import onboarding as OB

PERSONAL_SENDER = ("Fabrice from RECOSA", "fabrice@recosa.eu")

# What each step's email says. key: (subject, paragraph, button)
STEP_TEXT = {
    "profile": (
        "Step 1: your company profile",
        "Start with your company profile. Your company number or website fills most of it "
        "in — about five minutes. Documents need it most: your legal name, address and a "
        "contact email.",
        "Complete my profile"),
    "inventory": (
        "Step 2: the tools you use",
        "Next: your systems and activities — the tools you use and what you do with personal "
        "data. Scan your website and RECOSA lists the tools it finds; you tick the ones you use.",
        "Add my systems"),
    "gap": (
        "Step 3: your score per regulation",
        "Next: a gap assessment. You answer questions about how your company works and get a "
        "score for each regulation that applies to you, with every gap turned into a task on "
        "your action plan.",
        "Run my gap assessment"),
    "documents": (
        "Step 4: your documents",
        "Next: your documents. From your profile and your systems, RECOSA writes your privacy "
        "policy, your record of processing activities and the other documents your regulations "
        "require, in your language.",
        "Generate my documents"),
    "adopt": (
        "Step 5: put your documents in force",
        "Last step: adopt your documents. A document counts once your company works under it. "
        "Mark it in force and RECOSA keeps the record: which version, and since when.",
        "Adopt my documents"),
}

AFTER_SETUP = [
    "Regulatory alerts: the changes that concern your company, as they are published.",
    "Incidents: the NIS2 and GDPR deadlines counted for you, and the notifications drafted.",
    "Training: who was trained, when, and who is due.",
    "Nightly checks: documents to review, and records to keep or delete.",
]


@dataclass
class Email:
    subject: str
    text: str
    html: str | None
    sender: tuple[str, str] | None = None     # (name, address); None: the default


def _link(base_url: str, path: str, key: str, campaign: str = "onboarding") -> str:
    tags = f"utm_source=recosa&utm_medium=email&utm_campaign={campaign}&utm_content={key}"
    return f"{base_url}/{path}?{tags}" if path else f"{base_url}/?{tags}"


def _footer(stop_url: str, lang: str) -> tuple[str, str]:
    why = tr("You are receiving this because you started a RECOSA trial.", lang)
    stop = tr("Stop these emails", lang)
    return (f'{_h.escape(why)} <a href="{stop_url}" style="color:#6b7280">{_h.escape(stop)}</a>',
            f"{why} {stop}: {stop_url}")


def _paragraphs(ps: list[str]) -> str:
    return "".join(f'<p style="margin:0 0 14px">{p}</p>' for p in ps)


def compose(key: str, *, lang: str, base_url: str, stop_url: str,
            company: str | None, done: dict[str, bool]) -> Email:
    n_done = sum(1 for k in OB.STEP_ORDER if done.get(k))
    step = OB.first_pending(done)
    company_txt = company or tr("your company", lang)
    foot_html, foot_text = _footer(stop_url, lang)

    if key == "personal":
        text = (tr("Hello,", lang) + "\n\n"
                + tr("I'm Fabrice, I built RECOSA. You started a trial yesterday, and I would like "
                     "to know what you need it for: a customer asking about GDPR, NIS2 coming your "
                     "way, a policy to put in place, or something else?", lang) + "\n\n"
                + tr("Just reply to this email. I read every answer myself, and it helps me make "
                     "RECOSA useful for you.", lang) + "\n\n"
                + "Fabrice\n" + tr("Founder, RECOSA", lang) + "\nrecosa.eu\n\n--\n" + foot_text)
        return Email(tr("A quick question", lang), text, None, PERSONAL_SENDER)

    if key == "welcome":
        subject = tr("Welcome to RECOSA: your first step", lang)
        ps = [_h.escape(tr("Your 14-day trial of RECOSA has started. In the next two weeks you can "
                           "set up the compliance of {company}: your systems, a score per "
                           "regulation, and the documents your regulations require.",
                           lang).format(company=company_txt))]
        if company:
            ps.append(_h.escape(tr(STEP_TEXT["profile"][1], lang)))
            cta, path = tr(STEP_TEXT["profile"][2], lang), OB.STEPS["profile"][2]
        else:
            ps.append(_h.escape(tr("Start by adding your company. Your company number or website "
                                   "fills most of it in — about five minutes.", lang)))
            cta, path = tr("Add my company", lang), ""
        subtitle = tr("Your 14-day trial", lang)

    elif key in OB.STEP_EMAILS:
        step = step or "adopt"
        s_subject, s_text, s_cta = STEP_TEXT[step]
        subject = tr(s_subject, lang)
        progress = tr("{n} of 5 setup steps done.", lang).format(n=n_done)
        ps = [_h.escape(progress), _h.escape(tr(s_text, lang))]
        if not company and step == "profile":
            cta, path = tr("Add my company", lang), ""
        else:
            cta, path = tr(s_cta, lang), OB.STEPS[step][2]
        subtitle = tr("Setting up {company}", lang).format(company=company_txt)

    elif key == "wrapup":
        if step is None:
            subject = tr("You're set up: here is what RECOSA does now", lang)
            items = "".join(f'<li style="margin:0 0 6px">{_h.escape(tr(t, lang))}</li>'
                            for t in AFTER_SETUP)
            ps = [_h.escape(tr("All five setup steps are done. From now on, RECOSA keeps working "
                               "for {company}:", lang).format(company=company_txt)),
                  f'<ul style="margin:0;padding-left:18px">{items}</ul>']
            cta, path = tr("Open RECOSA", lang), ""
        else:
            subject = tr("{n} of 5 done, {left} to go", lang).format(n=n_done, left=5 - n_done)
            ps = [_h.escape(tr("You have done {n} of the five setup steps. Your trial has a few "
                               "days left: enough to finish.", lang).format(n=n_done)),
                  _h.escape(tr(STEP_TEXT[step][1], lang))]
            cta, path = tr(STEP_TEXT[step][2], lang), OB.STEPS[step][2]
        subtitle = tr("Setting up {company}", lang).format(company=company_txt)
    else:
        raise ValueError(f"Unknown onboarding email: {key}")

    url = _link(base_url, path, key)
    html = email_layout(subtitle, _paragraphs(ps), cta, url, footer_note=foot_html)
    text = "\n\n".join(_strip(p) for p in ps) + f"\n\n{cta}: {url}\n\n--\n{foot_text}"
    return Email(subject, text, html)


def _strip(p: str) -> str:
    import re
    p = re.sub(r"<li[^>]*>", "- ", p)
    p = re.sub(r"</li>", "\n", p)
    return _h.unescape(re.sub(r"<[^>]+>", "", p)).strip()
