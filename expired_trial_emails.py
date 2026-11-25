"""
expired_trial_emails.py — D-214. The expired-trial emails, in the reader's
language. Built like trial_ending_emails.py; compose() sends nothing.

The win-back emails link to "Choose your plan" (/subscribe, which an
expired account reaches from any page). The deletion warnings exist but are
not sent yet (expired_trial.DELETION_ACTIVE).
"""

from __future__ import annotations

import html as _h
from datetime import datetime

from email_sender import email_layout
from i18n import translate as tr
from onboarding_emails import PERSONAL_SENDER, Email, _footer, _link, _paragraphs, _strip
from trial_ending_emails import _plans_line, long_date

CAMPAIGN = "expired_trial"


def _date(d: datetime, lang: str, now: datetime) -> str:
    """'8 December', with the year when it is not this year's."""
    s = long_date(d, lang)
    return s if d.year == now.year else f"{s} {d.year}"


def compose(key: str, *, lang: str, base_url: str, stop_url: str, company: str | None,
            ended_at: datetime, now: datetime, missed: tuple[int, int] = (0, 0)) -> Email:
    company_txt = company or tr("your company", lang)
    ended = _date(ended_at, lang, now)
    foot_html, foot_text = _footer(stop_url, lang)

    if key == "why":
        text = (tr("Hello,", lang) + "\n\n"
                + tr("Your RECOSA trial ended three weeks ago and you did not continue. That is "
                     "fine, but I would really like to know why. Was something missing, too "
                     "complicated, too expensive, or just not the right moment?", lang) + "\n\n"
                + tr("One line in reply is enough. I read every answer myself.", lang) + "\n\n"
                + "Fabrice\n" + tr("Founder, RECOSA", lang) + "\nrecosa.eu\n\n--\n" + foot_text)
        return Email(tr("What stopped you?", lang), text, None, PERSONAL_SENDER)

    if key == "ended":
        subject = tr("Your RECOSA trial has ended", lang)
        ps = [_h.escape(tr("Your 14-day trial of RECOSA ended on {date}.", lang).format(date=ended)),
              _h.escape(tr("Everything you set up for {company} is kept. Choose a plan and you pick "
                           "up where you left off: your systems, documents and score are there, and "
                           "the alerts and reminders start again.", lang).format(company=company_txt)),
              _h.escape(_plans_line(lang))]
    elif key == "missing":
        total, mine = missed
        if total:
            subject = tr("{n} regulatory updates since your trial ended", lang).format(n=total)
            ps = [_h.escape(tr("Since your trial ended on {date}, RECOSA has published {n} "
                               "regulatory updates.", lang).format(date=ended, n=total))]
            ps.append(_h.escape(
                tr("{mine} of them concern {company}. They are waiting in your account.", lang)
                .format(mine=mine, company=company_txt) if mine else
                tr("With a plan, RECOSA tells you which ones concern {company}, as they come out.",
                   lang).format(company=company_txt)))
        else:
            subject = tr("Your RECOSA account is still here", lang)
            ps = [_h.escape(tr("Your trial ended on {date}, and everything you set up for {company} "
                               "is kept.", lang).format(date=ended, company=company_txt))]
        ps.append(_h.escape(tr("Choose a plan and RECOSA keeps watch again: the regulatory alerts, "
                               "the deadlines and the checks.", lang)))
    elif key in ("deletion_warning", "last_warning"):
        import expired_trial as ET
        on = _date(ET.deletion_date(ended_at), lang, now)
        subject = (tr("Your RECOSA account will be deleted on {date}", lang).format(date=on)
                   if key == "deletion_warning" else
                   tr("5 days before your RECOSA account is deleted", lang))
        ps = [_h.escape(tr("Your trial ended on {ended}. An account without a plan is deleted 60 "
                           "days after its trial ends: the account of {company} and everything in "
                           "it will be deleted on {date}.", lang).format(
                               ended=ended, company=company_txt, date=on)),
              _h.escape(tr("Download what you want to keep before then, or choose a plan: "
                           "everything stays and keeps working.", lang))]
        foot_html = foot_text = ""
    else:
        raise ValueError(f"Unknown expired-trial email: {key}")

    cta = tr("Choose my plan", lang)
    url = _link(base_url, "subscribe", key, CAMPAIGN)
    html = email_layout(tr("Your RECOSA account", lang), _paragraphs(ps), cta, url,
                        footer_note=foot_html, alert=key in ("deletion_warning", "last_warning"))
    text = "\n\n".join(_strip(p) for p in ps) + f"\n\n{cta}: {url}" + (
        f"\n\n--\n{foot_text}" if foot_text else "")
    return Email(subject, text, html)
