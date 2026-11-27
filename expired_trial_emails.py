"""
expired_trial_emails.py — D-214. The expired-trial emails, in the reader's
language. Built like trial_ending_emails.py; compose() sends nothing.

The win-back emails link to "Choose your plan" (/subscribe, which an
expired account reaches from any page). D-222: the notices (access closing,
access closed, last warning) quote the dates stored on the account; "deleted"
goes out after the deletion. The notices carry no stop link.
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
            ended_at: datetime, now: datetime, missed: tuple[int, int] = (0, 0),
            closes_at: datetime | None = None, delete_after: datetime | None = None,
            ask_feedback: bool = False) -> Email:
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
              _h.escape(tr("In the meantime, you can still open RECOSA to see and download everything, "
                           "read-only.", lang)),
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
    elif key in ("access_closing", "access_closed", "deleted"):
        import expired_trial as ET
        if not (closes_at and delete_after):
            closes_at, delete_after = ET.plan_dates(ended_at, now)
        closes, gone = _date(closes_at, lang, now), _date(delete_after, lang, now)
        kept = tr("What we keep, as the law requires or allows: the record that you accepted our "
                  "terms and, if you asked us to stop emailing you, your address on our "
                  "do-not-email list. Details in our privacy policy.", lang)
        if key == "access_closing":
            subject = tr("Your access to RECOSA closes on {date}", lang).format(date=closes)
            ps = [_h.escape(tr("Your trial ended on {ended}. Until {closes} you can still open "
                               "RECOSA and download everything you set up for {company}: your "
                               "documents, your records, your reports.", lang).format(
                                   ended=ended, closes=closes, company=company_txt)),
                  _h.escape(tr("On {closes} your access closes. Your data is kept for 15 more days, "
                               "then deleted on {gone}.", lang).format(closes=closes, gone=gone)),
                  _h.escape(tr("Choose a plan before then and everything stays as it is.", lang))]
            cta, path = tr("Download my documents", lang), "documents"
        elif key == "access_closed":
            subject = tr("Your RECOSA account will be deleted on {date}", lang).format(date=gone)
            ps = [_h.escape(tr("Your access to RECOSA closed on {closes}. Everything you set up for "
                               "{company} is still kept, until {gone}: on that day the account and "
                               "everything in it are deleted, for good.", lang).format(
                                   closes=closes, company=company_txt, gone=gone)),
                  _h.escape(tr("Choose a plan before then and you get it all back, as you left it.",
                               lang)),
                  _h.escape(kept)]
            cta, path = tr("Choose my plan", lang), "subscribe"
        else:
            subject = tr("Your RECOSA account has been deleted", lang)
            ps = [_h.escape(tr("As announced, the account of {company} and everything in it have "
                               "been deleted today.", lang).format(company=company_txt)),
                  _h.escape(kept)]
            if ask_feedback:
                # D-222 (the user, 27 Nov): the one place after the trial we
                # ask why; not to someone who stopped our emails.
                ps.append(_h.escape(tr("One last question, if you have a minute: what stopped you "
                                       "from continuing with RECOSA? Just reply to this email — "
                                       "Fabrice, who built RECOSA, reads every answer himself.",
                                       lang)))
            ps.append(_h.escape(tr("If you want to work with RECOSA again, you are welcome to sign "
                                   "up anew.", lang)))
            cta, path = tr("Visit recosa.eu", lang), None
        foot_html = foot_text = ""
        url = "https://www.recosa.eu" if path is None else _link(base_url, path, key, CAMPAIGN)
        html = email_layout(tr("Your RECOSA account", lang), _paragraphs(ps), cta, url,
                            footer_note=foot_html, alert=key != "deleted")
        text = "\n\n".join(_strip(p) for p in ps) + f"\n\n{cta}: {url}"
        return Email(subject, text, html,
                     reply_to=PERSONAL_SENDER if key == "deleted" and ask_feedback else None)
    else:
        raise ValueError(f"Unknown expired-trial email: {key}")

    cta = tr("Choose my plan", lang)
    url = _link(base_url, "subscribe", key, CAMPAIGN)
    html = email_layout(tr("Your RECOSA account", lang), _paragraphs(ps), cta, url,
                        footer_note=foot_html)
    text = "\n\n".join(_strip(p) for p in ps) + f"\n\n{cta}: {url}" + (
        f"\n\n--\n{foot_text}" if foot_text else "")
    return Email(subject, text, html)
