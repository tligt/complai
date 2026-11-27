"""
trial_ending_emails.py — D-213. The two trial-ending emails, in the reader's
language. Built like onboarding_emails.py: the English text is the
catalogue key, compose() sends nothing.

Both link to "Choose your plan" (/subscribe). Neither says "read-only": an
ended trial keeps its data, but read-only access to it is not built yet.
"""

from __future__ import annotations

import html as _h
from datetime import datetime

import pricing
from email_sender import email_layout
from i18n import translate as tr
from onboarding_emails import Email, _footer, _link, _paragraphs, _strip

CAMPAIGN = "trial_ending"
SUBSCRIBE_PATH = "subscribe"

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"],
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
           "september", "oktober", "november", "december"],
}


def long_date(d: datetime, lang: str) -> str:
    """'8 December' / '8 décembre' / '8 december'."""
    return f"{d.day} {_MONTHS.get(lang, _MONTHS['en'])[d.month - 1]}"


def _plans_line(lang: str) -> str:
    """One line, from pricing.py (the user, 27 Nov: the plans themselves are on
    the "Choose your plan" page, so the emails don't need changing with them)."""
    return tr("Plans start at {month} a month, or {year} a year (one month free), excl. VAT.",
              lang).format(month=pricing.eur(pricing.price("starter", "monthly")),
                           year=pricing.eur(pricing.price("starter", "yearly")))


def compose(key: str, *, lang: str, base_url: str, stop_url: str, company: str | None,
            ends_at: datetime, figures: dict) -> Email:
    company_txt = company or tr("your company", lang)
    when = long_date(ends_at, lang)
    foot_html, foot_text = _footer(stop_url, lang)

    if key == "four_days":
        subject = tr("4 days left in your RECOSA trial", lang)
        lines = []
        f = figures or {}
        if f.get("systems") or f.get("activities"):
            lines.append(tr("{systems} systems and {activities} processing activities recorded",
                            lang).format(systems=f.get("systems", 0),
                                         activities=f.get("activities", 0)))
        if f.get("documents") and f.get("docs_total"):
            # The user, 27 Nov: "out of" shows what is still there to do.
            lines.append(tr("{n} of the {total} documents for your regulations generated, "
                            "{in_force} of them in force", lang).format(
                n=f["documents"], total=max(f["docs_total"], f["documents"]),
                in_force=f.get("in_force", 0)))
        elif f.get("documents"):
            lines.append(tr("{n} documents generated", lang).format(n=f["documents"]))
        if f.get("score") is not None:
            lines.append(tr("A compliance score of {score}%, with an action plan", lang).format(
                score=f["score"]))
        if f.get("alerts"):
            lines.append(tr("{n} regulatory alerts that concern you", lang).format(n=f["alerts"]))
        ps = [_h.escape(tr("Your trial ends on {date}.", lang).format(date=when))]
        if lines:
            ps.append(_h.escape(tr("Here is what {company} has in RECOSA so far:", lang).format(
                company=company_txt)))
            ps.append('<ul style="margin:0 0 14px;padding-left:18px">' + "".join(
                f'<li style="margin:0 0 6px">{_h.escape(x)}</li>' for x in lines) + "</ul>")
            if f.get("docs_total") and f.get("documents", 0) < f["docs_total"]:
                ps.append(_h.escape(tr("{left} more documents are waiting to be written for "
                                       "{company}: RECOSA does it in minutes.", lang).format(
                    left=f["docs_total"] - f["documents"], company=company_txt)))
        elif f.get("docs_total"):
            ps.append(_h.escape(tr("Your regulations call for {total} documents, and RECOSA can "
                                   "write them for {company} in minutes: four days are enough to "
                                   "set up the essentials.", lang).format(
                total=f["docs_total"], company=company_txt)))
        else:
            ps.append(_h.escape(tr("There is still time to see what RECOSA does for {company}: "
                                   "four days are enough to set up the essentials.",
                                   lang).format(company=company_txt)))
        ps.append(_h.escape(_plans_line(lang)))
        ps.append(_h.escape(tr("When you subscribe, everything you set up stays as it is.", lang)))
    elif key == "last_day":
        subject = tr("Your RECOSA trial ends tomorrow", lang)
        ps = [_h.escape(tr("Your free trial of RECOSA ends tomorrow, {date}.", lang).format(date=when)),
              _h.escape(tr("Everything you set up is kept: your systems, your documents, your "
                           "score. Choose a plan and it all keeps working, with the alerts, "
                           "reminders and checks.", lang)),
              _h.escape(_plans_line(lang))]
    else:
        raise ValueError(f"Unknown trial-ending email: {key}")

    cta = tr("Choose my plan", lang)
    url = _link(base_url, SUBSCRIBE_PATH, key, CAMPAIGN)
    html = email_layout(tr("Your 14-day trial", lang), _paragraphs(ps), cta, url,
                        footer_note=foot_html, lang=lang)
    text = "\n\n".join(_strip(p) for p in ps) + f"\n\n{cta}: {url}\n\n--\n{foot_text}"
    from onboarding_emails import support_reply_to
    return Email(subject, text, html, reply_to=support_reply_to())
