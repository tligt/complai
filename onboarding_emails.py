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
    reply_to: tuple[str, str] | None = None   # D-222: replies elsewhere than the sender


def _link(base_url: str, path: str, key: str, campaign: str = "onboarding") -> str:
    tags = f"utm_source=recosa&utm_medium=email&utm_campaign={campaign}&utm_content={key}"
    return f"{base_url}/{path}?{tags}" if path else f"{base_url}/?{tags}"


# Footers (the user, 27 Nov): "signed up", not "subscribed" (that means paying).
FOOT_WELCOME = ("You're receiving this onboarding email because you signed up for RECOSA and your "
                "free trial is under way. Over the next two weeks we'll send a few short tips to "
                "help you get the most out of it.")
FOOT_TRIAL = ("You're receiving this email because you signed up for RECOSA and your free trial "
              "is under way.")
FOOT_EXPIRED = "You're receiving this email because you tried RECOSA."

# The four things RECOSA does, in the welcome email.
FEATURES = [
    ("Your systems, mapped:", "scan your website and RECOSA lists the tools it finds; you tick the "
                              "ones you use."),
    ("A score per regulation:", "GDPR, NIS2 and the others that apply to you, with every gap "
                                "turned into a task on your action plan."),
    ("Your documents, written for you:", "privacy policy, record of processing activities and the "
                                         "rest your regulations require, in your language."),
    ("Alerts that concern you:", "regulatory changes as they are published, filtered for your "
                                 "company."),
]


def support_reply_to() -> tuple[str, str] | None:
    """Where replies to the lifecycle emails go (the user, 27 Nov: a support
    address, later turned into tickets). Set SUPPORT_REPLY_TO once the mailbox
    exists; until then replies go to the sending address, as before."""
    import os
    addr = (os.environ.get("SUPPORT_REPLY_TO") or "").strip()
    return ("RECOSA support", addr) if addr else None


def _footer(stop_url: str, lang: str, why: str = FOOT_TRIAL) -> tuple[str, str]:
    why = tr(why, lang)
    stop = tr("Stop these emails", lang)
    return (f'{_h.escape(why)} <a href="{stop_url}" style="color:#6b7280">{_h.escape(stop)}</a>',
            f"{why} {stop}: {stop_url}")


def _paragraphs(ps: list[str]) -> str:
    return "".join(p if p.startswith("<p") else f'<p style="margin:0 0 14px">{p}</p>' for p in ps)


def _button(label: str, url: str) -> str:
    """A button inside the text, where the email asks for the action."""
    return (f'<p data-btn="1" style="margin:6px 0 20px;text-align:center"><a href="{_h.escape(url)}" '
            f'style="display:inline-block;background:#003366;color:#fff;padding:12px 26px;'
            f'border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px">'
            f'{_h.escape(label)} &rarr;</a></p>')


def _small(text: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:13px;color:#6b7280">{_h.escape(text)}</p>'


def days_left(ends_at, now) -> int | None:
    """Whole days left in the trial, rounded up (13.5 days: 14)."""
    if not (ends_at and now):
        return None
    d = ends_at - now
    return max(0, d.days + (1 if d.seconds else 0))


def compose(key: str, *, lang: str, base_url: str, stop_url: str,
            company: str | None, done: dict[str, bool], ends_at=None, now=None) -> Email:
    n_done = sum(1 for k in OB.STEP_ORDER if done.get(k))
    step = OB.first_pending(done)
    company_txt = company or tr("your company", lang)
    foot_html, foot_text = _footer(stop_url, lang, FOOT_WELCOME if key == "welcome" else FOOT_TRIAL)
    reply_to = support_reply_to()

    if key == "personal":
        # Plain text from Fabrice, no footer (the user, 27 Nov: a service
        # email, and a disclaimer would make it read as automatic). The stop
        # link still stops it.
        text = (tr("Hello,", lang) + "\n\n"
                + tr("I'm Fabrice, I built RECOSA. You started a trial yesterday, and I would like "
                     "to know what you need it for: a customer asking about GDPR, NIS2 coming your "
                     "way, a policy to put in place, or something else?", lang) + "\n\n"
                + tr("Just reply to this email. I read every answer myself, and it helps me make "
                     "RECOSA useful for you.", lang) + "\n\n"
                + "Fabrice\n" + tr("Founder, RECOSA", lang) + "\nrecosa.eu")
        return Email(tr("A quick question", lang), text, None, PERSONAL_SENDER)

    if key == "welcome":
        from trial_ending_emails import long_date
        subject = tr("Welcome to RECOSA: your 14-day trial has started", lang)
        subtitle = (tr("Welcome, {company}", lang).format(company=company) if company
                    else tr("Welcome to RECOSA", lang))
        until = (tr("It runs for 14 days, until {date}, with every feature open to you:", lang)
                 .format(date=long_date(ends_at, lang)) if ends_at else
                 tr("It runs for 14 days, with every feature open to you:", lang))
        items = "".join(f'<li style="margin:0 0 6px"><strong>{_h.escape(tr(a, lang))}</strong> '
                        f'{_h.escape(tr(b, lang))}</li>' for a, b in FEATURES)
        ps = [_h.escape(tr("Thank you for choosing RECOSA. We're glad to have you with us, and "
                           "we're here to help you put the compliance of {company} in order "
                           "without it taking over your week.", lang).format(company=company_txt)),
              _h.escape(tr("Your free trial has started.", lang)) + " " + _h.escape(until),
              f'<ul style="margin:0 0 14px;padding-left:18px">{items}</ul>',
              _h.escape(tr("You don't need to be a compliance expert. Our AI does the heavy "
                           "lifting: it fills in what it can, writes your documents, and answers "
                           "your questions along the way.", lang))]
        how = _h.escape(tr("Your company number or website fills most of it in, which takes about "
                           "five minutes, and everything else builds on it.", lang))
        if company:
            ps.append("<strong>" + _h.escape(tr("Begin with your company profile.", lang))
                      + "</strong> " + how)
            cta, path = tr(STEP_TEXT["profile"][2], lang), OB.STEPS["profile"][2]
        else:
            ps.append("<strong>" + _h.escape(tr("Begin by adding your company.", lang))
                      + "</strong> " + how)
            cta, path = tr("Add my company", lang), ""
        ps.append(_button(cta, _link(base_url, path, key)))
        ps += ["<strong>" + _h.escape(tr("Nothing you do now is lost.", lang)) + "</strong> "
               + _h.escape(tr("If you subscribe, everything you set up during the trial stays "
                              "exactly as it is, so every minute you spend now counts.", lang)),
               _h.escape(tr("Questions, or stuck somewhere? Just reply to this email: a real "
                            "person reads every answer.", lang)),
               _h.escape(tr("The RECOSA team", lang))]
        return _finish(subject, subtitle, ps, foot_html, foot_text, lang, reply_to)

    if key in OB.STEP_EMAILS:
        step = step or "adopt"
        s_subject, s_text, s_cta = STEP_TEXT[step]
        left = days_left(ends_at, now)
        subject = (tr("{days} days left in your trial — {step}", lang).format(
                       days=left, step=tr(s_subject, lang)) if left else tr(s_subject, lang))
        ps = []
        if left:
            ps.append(_h.escape(tr("Don't forget: your 14-day RECOSA trial is running, with {days} "
                                   "days left. Make the most of it.", lang).format(days=left)))
        ps.append(_h.escape(tr(s_text, lang)))
        if not company and step == "profile":
            cta, path = tr("Add my company", lang), ""
        else:
            cta, path = tr(s_cta, lang), OB.STEPS[step][2]
        ps.append(_button(cta, _link(base_url, path, key)))
        ps.append(_small(tr("{n} of 5 setup steps done.", lang).format(n=n_done)))
        subtitle = tr("Setting up {company}", lang).format(company=company_txt)
        return _finish(subject, subtitle, ps, foot_html, foot_text, lang, reply_to)

    if key == "wrapup":
        if step is None:
            subject = tr("You're set up: here is what RECOSA does now", lang)
            items = "".join(f'<li style="margin:0 0 6px">{_h.escape(tr(t, lang))}</li>'
                            for t in AFTER_SETUP)
            ps = [_h.escape(tr("All five setup steps are done. From now on, RECOSA keeps working "
                               "for {company}:", lang).format(company=company_txt)),
                  f'<ul style="margin:0 0 14px;padding-left:18px">{items}</ul>']
            cta, path = tr("Open RECOSA", lang), ""
        else:
            subject = tr("{n} of 5 done, {left} to go", lang).format(n=n_done, left=5 - n_done)
            ps = [_h.escape(tr("You have done {n} of the five setup steps. Your trial has a few "
                               "days left: enough to finish.", lang).format(n=n_done)),
                  _h.escape(tr(STEP_TEXT[step][1], lang))]
            cta, path = tr(STEP_TEXT[step][2], lang), OB.STEPS[step][2]
        ps.append(_button(cta, _link(base_url, path, key)))
        subtitle = tr("Setting up {company}", lang).format(company=company_txt)
        return _finish(subject, subtitle, ps, foot_html, foot_text, lang, reply_to)

    raise ValueError(f"Unknown onboarding email: {key}")


def _finish(subject, subtitle, ps, foot_html, foot_text, lang, reply_to=None) -> Email:
    html = email_layout(subtitle, _paragraphs(ps), footer_note=foot_html, lang=lang)
    text = "\n\n".join(_strip(p) for p in ps) + f"\n\n--\n{foot_text}"
    return Email(subject, text, html, reply_to=reply_to)


def _strip(p: str) -> str:
    import re
    m = re.search(r'data-btn="1".*?href="([^"]+)"[^>]*>(.*?) &rarr;</a>', p, re.S)
    if m:   # a button: "Label: url" in the text version
        return f"{_h.unescape(m.group(2))}: {_h.unescape(m.group(1))}"
    p = re.sub(r"<li[^>]*>", "- ", p)
    p = re.sub(r"</li>", "\n", p)
    return _h.unescape(re.sub(r"<[^>]+>", "", p)).strip()
