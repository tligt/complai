import os
import base64
import requests

from i18n import LANGUAGES, translate as tr

# ── The recipient's language (S64, D-168) ─────────────────────────────────
# Every email is written in its reader's language: the person's own
# (profiles.ui_language, D-167). Someone RECOSA has no profile for — an
# incident team member who never logged in — gets the caller's fallback,
# else English. The English text is the catalogue key, as in the interface.


def _lang(lang: str | None) -> str:
    return lang if lang in LANGUAGES else "en"


def languages_of(emails, fallback: str | None = None) -> dict[str, str]:
    """{email: language} for these addresses, in one query."""
    wanted = [e for e in dict.fromkeys(emails) if e]
    found: dict[str, str] = {}
    if wanted:
        try:
            from database import get_supabase_admin
            rows = (get_supabase_admin().table("profiles").select("email, ui_language")
                    .in_("email", [e.strip().lower() for e in wanted]).execute().data or [])
            found = {(r.get("email") or "").lower(): r.get("ui_language") for r in rows}
        except Exception as e:
            print(f"Could not look up the recipients' language: {e}")
    return {e: _lang(found.get(e.strip().lower()) or fallback) for e in wanted}


def language_of(email: str, fallback: str | None = None) -> str:
    return languages_of([email], fallback).get(email, _lang(fallback))

# ── One layout for every RECOSA email (S49 part 2, D-119) ─────────────────
# The brand: dark blue #003366, teal #14C7D5 as the accent. The S6 audit
# email's navy/purple and the incident emails' own reds had drifted apart;
# everything now goes through email_layout(). Buttons are dark blue, not
# teal: white text on teal fails contrast.
BRAND_DARK = "#003366"
BRAND_ACCENT = "#14C7D5"


def email_layout(subtitle: str, body_html: str, cta_label: str | None = None,
                 cta_url: str | None = None, footer_note: str = "",
                 alert: bool = False) -> str:
    """The shared shell. alert=True adds a red rule under the header for the
    emails that mean "act now" (incident alerts and missed deadlines)."""
    import html as _h
    rule = "#993C1D" if alert else BRAND_ACCENT
    cta = (f'''<p style="margin:22px 0 4px;text-align:center">
      <a href="{cta_url}" style="display:inline-block;background:{BRAND_DARK};color:#fff;
         padding:12px 26px;border-radius:6px;text-decoration:none;font-weight:bold;
         font-size:15px">{_h.escape(cta_label)} &rarr;</a></p>''' if cta_label and cta_url else "")
    note = (f'<p style="color:#6b7280;font-size:11px;margin:0 0 6px">{footer_note}</p>'
            if footer_note else "")
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:20px;background:#ffffff">
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
  <div style="background:{BRAND_DARK};padding:20px 24px;border-radius:8px 8px 0 0;border-bottom:4px solid {rule}">
    <h1 style="color:#fff;margin:0;font-size:22px">RECOSA</h1>
    <p style="color:#c9d6e3;margin:6px 0 0;font-size:13px">{_h.escape(subtitle)}</p>
  </div>
  <div style="background:#f7f9fb;padding:24px;border:1px solid #e8edf2;line-height:1.55">
    {body_html}
    {cta}
  </div>
  <div style="background:#e8edf2;padding:14px;border-radius:0 0 8px 8px;text-align:center">
    {note}<p style="color:#6b7280;font-size:11px;margin:0">RECOSA &middot; recosa.eu</p>
  </div>
</div>
</body></html>'''


def more_checks_html(more: list[tuple[str, str]] | None, lang: str = "en") -> str:
    """D-133. The last line of a result email: the free checks not taken yet,
    each a link straight to it. Empty when every check is taken."""
    import html as _h
    if not more:
        return ""
    links = " &middot; ".join(
        f'<a href="{_h.escape(url)}" style="color:{BRAND_DARK};font-weight:bold">{_h.escape(label)}</a>'
        for label, url in more)
    return (f'<p style="margin:18px 0 0;font-size:13px;color:#555">'
            + tr("Also free, and added to the same account: {links}", lang).format(links=links) + "</p>")


def send_audit_report(
    to_email: str,
    website_url: str,
    pdf_bytes: bytes,
    score: int,
    risk_level: str,
    ok_count: int,
    warn_count: int,
    fail_count: int,
    cta_url: str | None = None,
    more: list[tuple[str, str]] | None = None,
    lang: str | None = None,
) -> bool:
    """
    Send the audit report PDF by email using the Brevo API.
    Returns True on success, False on failure.

    S49: cta_url, when given, is the signup link carrying the checked site
    (funnel.signup_url); otherwise the button opens the app's root.
    D-168: the email in the recipient's language; the PDF stays English.
    """
    lang = _lang(lang) if lang else language_of(to_email)
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")

    from_email = os.environ.get("BREVO_FROM_EMAIL", "audit@complai.be")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA Audit")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    cta_url    = cta_url or f"{base_url}/"

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    risk_emoji = {"Green": "🟢", "Amber": "🟡", "Red": "🔴"}.get(risk_level, "⚪")

    filename = (
        "RECOSA_Audit_"
        + website_url.replace("https://", "").replace("http://", "").replace("/", "_")
        + ".pdf"
    )

    import html as _h
    counts = f'''
    <table style="width:100%;border-collapse:collapse;margin:16px 0;text-align:center">
      <tr>
        <td style="padding:10px;background:#0F6E56;color:white;border-radius:4px;width:31%">
          <strong style="font-size:20px">{ok_count}</strong><br><span style="font-size:12px">{tr("Compliant", lang)}</span></td>
        <td style="width:3%"></td>
        <td style="padding:10px;background:#BA7517;color:white;border-radius:4px;width:31%">
          <strong style="font-size:20px">{warn_count}</strong><br><span style="font-size:12px">{tr("Needs attention", lang)}</span></td>
        <td style="width:3%"></td>
        <td style="padding:10px;background:#993C1D;color:white;border-radius:4px;width:31%">
          <strong style="font-size:20px">{fail_count}</strong><br><span style="font-size:12px">{tr("Missing", lang)}</span></td>
      </tr>
    </table>'''
    risk = {"Green": tr("low risk", lang), "Amber": tr("medium risk", lang),
            "Red": tr("high risk", lang)}.get(risk_level, risk_level)
    site = f"<strong>{_h.escape(website_url)}</strong>"
    html_body = email_layout(
        tr("Your website compliance report", lang),
        f'''<h2 style="color:{BRAND_DARK};margin-top:0">{risk_emoji} {_h.escape(tr("Compliance score: {score}/100 — {risk}", lang).format(score=score, risk=risk))}</h2>
    <p>{tr("We checked {site}. Your full report is attached as a PDF, and it is in your RECOSA account.", lang).format(site=site)}</p>
    {counts}
    <p>{_h.escape(tr("RECOSA shows you how to fix each issue, generates the documents you are missing and keeps checking your site.", lang))}</p>{more_checks_html(more, lang)}''',
        tr("Open RECOSA", lang), cta_url,
        footer_note=_h.escape(tr("Generated automatically from your website's public pages. Not legal advice.", lang)),
    )

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "subject": tr("Your RECOSA compliance audit — {site} ({risk}, {score}/100)", lang).format(
            site=website_url, risk=risk, score=score),
        "htmlContent": html_body,
        "attachment": [
            {
                "name": filename,
                "content": pdf_b64,
            }
        ],
    }

    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code not in (200, 201):
        # S49: Brevo's reason (unknown IP, unverified sender, ...) in the
        # app's logs. Without it a failed send looked like nothing at all.
        print(f"Brevo refused the audit report: {response.status_code} {response.text[:300]}")
    return response.status_code in (200, 201)


def send_quiz_result(to_email: str, answers: list[int], cta_url: str,
                     kind: dict | None = None,
                     more: list[tuple[str, str]] | None = None) -> bool:
    """S49. The full NIS2 Quick Check result — or the AI Act Quick Check's
    (S55, kind=funnel.AI_ACT) — sent because the visitor asked for it on the
    public app. Weakest areas first, each with what to do. Returns True on
    success. Raises if BREVO_API_KEY is not set, like send_audit_report.
    D-168: stays in English, like the free checks it reports on, until those
    are translated — a French frame round English results reads worse."""
    import html
    import funnel
    kind = kind or funnel.NIS2
    name = kind["name"]
    reg = kind.get("reg", "NIS2")

    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")
    from_email = os.environ.get("BREVO_FROM_EMAIL", "audit@complai.be")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")

    total = funnel.score(answers)
    label, blurb = funnel.band(total, kind, len(answers))
    top = funnel.max_score(kind, answers)
    level_colour = ["#993C1D", "#BA7517", "#BA7517", "#0F6E56"]
    rows = "".join(
        f"""
      <tr>
        <td style="padding:10px;border-bottom:1px solid #E2E8F0;vertical-align:top;">
          <strong>{html.escape(r["category"])}</strong><br>
          <span style="color:#555;font-size:13px;">{html.escape(r["advice"])}</span>
        </td>
        <td style="padding:10px;border-bottom:1px solid #E2E8F0;vertical-align:top;
                   white-space:nowrap;color:{level_colour[r["answer"]]};font-weight:bold;">
          {html.escape(r["level"])}
        </td>
      </tr>"""
        for r in funnel.breakdown(answers, kind)
    )
    n_areas = {8: "eight", 9: "nine", 10: "ten", 13: "thirteen"}.get(len(answers), str(len(answers)))

    html_body = email_layout(
        f"Your {name} result",
        f'''<h2 style="color:{BRAND_DARK};margin-top:0">{total}/{top} — {html.escape(label)}</h2>
    <p>{html.escape(blurb)}</p>
    <h3 style="color:{BRAND_DARK}">Your {n_areas} areas, weakest first</h3>
    <table style="width:100%;border-collapse:collapse;background:white">{rows}
    </table>
    <p>The full assessment in RECOSA scores you against every {reg} obligation and turns the
       gaps into an action plan — included in the 14-day free trial.</p>{more_checks_html(more)}''',
        "Open RECOSA", cta_url,
        footer_note=f"A lightweight self-check based on your own answers — not a certified {reg} "
                    "audit, and not legal advice.",
    )
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": to_email}],
            "subject": f"Your {name} result: {total}/{top} — {label}",
            "htmlContent": html_body,
        },
        timeout=20,
    )
    if response.status_code not in (200, 201):
        print(f"Brevo refused the quiz result: {response.status_code} {response.text[:300]}")
    return response.status_code in (200, 201)


def _by_language(to_emails: list[str], fallback: str | None) -> dict[str, list[str]]:
    """The recipients grouped by language: one email per language, so each
    reads it in theirs and they still see who else was told."""
    groups: dict[str, list[str]] = {}
    for e, lg in languages_of(to_emails, fallback).items():
        groups.setdefault(lg, []).append(e)
    return groups


def send_incident_alert(to_emails: list[str], company: str, incident_title: str,
                        discovered_at, reason: str, fallback_lang: str | None = None) -> bool:
    """S53 part 2. Tell the incident team an incident is open. Content-light
    on purpose, like the reminder: what happened stays in RECOSA. reason:
    'logged', 'personal_data', 'significant' or 'manual'.
    D-168: each member in their language; fallback_lang for members with no
    RECOSA profile (the company's document language). True when every
    language group was accepted."""
    import html
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    try:
        import incident_rules as R
        found = R.when(discovered_at)
    except Exception:
        found = str(discovered_at or "")
    ok = True
    for lang, group in _by_language(to_emails, fallback_lang).items():
        why = {
            "logged": tr("An incident has been logged and you are on the incident team.", lang),
            "personal_data": tr("The incident involves personal data, and you are on the team for those.", lang),
            "significant": tr("The incident has been assessed as significant under NIS2.", lang),
            "manual": tr("You have been alerted by the person handling the incident.", lang),
        }.get(reason, tr("You are on the incident team.", lang))
        html_body = email_layout(
            tr("Incident open — {company}", lang).format(company=company),
            f'''<p><strong>{html.escape(incident_title)}</strong><br>{html.escape(tr("Found out: {when}", lang).format(when=found))}</p>
    <p>{html.escape(why)}</p>
    <p>{html.escape(tr("Reporting deadlines may already be running. Open the incident for the steps, the deadlines and who does what. Do not forward this email outside the team.", lang))}</p>''',
            tr("Open the incident", lang), f"{base_url}/incidents",
            footer_note=html.escape(tr("Sent because you are on this company's incident team.", lang)),
            alert=True,
        )
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": e} for e in group],
                "subject": tr("Incident open — {company}: {title}", lang).format(
                    company=company, title=incident_title)[:150],
                "htmlContent": html_body,
            },
            timeout=20,
        )
        if response.status_code not in (200, 201):
            print(f"Brevo refused the incident alert: {response.status_code} {response.text[:300]}")
            ok = False
    return ok


def send_incident_reminder(to_emails: list[str], company: str, incident_title: str,
                           items, overdue: bool, fallback_lang: str | None = None) -> bool:
    """S53. An incident deadline is close or missed. items: (deadline label,
    'in 4 h 10' / '3 h overdue'), or — D-168 — a function of the language
    giving them, so each recipient reads the deadlines in theirs.
    Content-light on purpose — what happened stays in RECOSA; the email only
    says that a clock is running."""
    import html
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    colour = "#993C1D" if overdue else "#BA7517"
    ok = True
    for lang, group in _by_language(to_emails, fallback_lang).items():
        rows = items(lang) if callable(items) else items
        lines = "".join(
            f'<li style="margin:6px 0;"><strong>{html.escape(l)}</strong> — '
            f'<span style="color:{colour};">{html.escape(w)}</span></li>' for l, w in rows)
        html_body = email_layout(
            tr("Incident deadline missed", lang) if overdue else tr("Incident deadline approaching", lang),
            f'''<p><strong>{html.escape(company)}</strong> — {html.escape(incident_title)}</p>
    <ul style="padding-left:18px">{lines}</ul>
    <p>{html.escape(tr("Send what you know now and follow up later: a late complete notification is worse than an early incomplete one. If a notification was already sent, record it in RECOSA to stop the clock.", lang))}</p>''',
            tr("Open the incident", lang), f"{base_url}/incidents",
            footer_note=html.escape(tr("Sent because an incident is open in RECOSA for this company.", lang)),
            alert=overdue,
        )
        subject = (tr("Missed: incident deadline — {title}", lang) if overdue
                   else tr("Due soon: incident deadline — {title}", lang))
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender": {"name": from_name, "email": from_email},
                "to": [{"email": e} for e in group],
                "subject": subject.format(title=incident_title)[:150],
                "htmlContent": html_body,
            },
            timeout=20,
        )
        if response.status_code not in (200, 201):
            print(f"Brevo refused the incident reminder: {response.status_code} {response.text[:300]}")
            ok = False
    return ok


def is_free_email(email: str) -> bool:
    """Return True if the email uses a free/consumer provider."""
    free_domains = {
        "gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "yahoo.co.uk",
        "yahoo.be", "yahoo.nl", "hotmail.com", "hotmail.fr", "hotmail.be",
        "hotmail.nl", "outlook.com", "outlook.fr", "outlook.be", "outlook.nl",
        "live.com", "live.fr", "live.be", "msn.com", "icloud.com", "me.com",
        "mac.com", "protonmail.com", "proton.me", "tutanota.com", "gmx.com",
        "gmx.net", "gmx.fr", "aol.com", "wanadoo.fr", "orange.fr", "free.fr",
        "laposte.net", "sfr.fr", "skynet.be", "telenet.be", "proximus.be",
    }
    domain = email.strip().lower().split("@")[-1]
    return domain in free_domains


def extract_email_domain(email: str) -> str:
    """Extract the domain part of an email address."""
    return email.strip().lower().split("@")[-1]


def send_regulatory_alert(update: dict) -> dict:
    """Send the regulatory alert email to every user with an unsent alert.

    One email per user, however many of their clients match: an account
    with four clients gets one email, not four. Only the alerts of users
    Brevo accepted are marked email_sent, so a failed send can be retried.

    Returns {"sent": [email, ...], "failed": [(email, reason), ...],
    "error": str | None}.
    """
    import os, requests
    from database import get_supabase_admin

    result = {"sent": [], "failed": [], "error": None}
    api_key = os.environ.get("BREVO_API_KEY","")
    from_email = os.environ.get("BREVO_FROM_EMAIL","audit@complai.be")
    from_name = os.environ.get("BREVO_FROM_NAME","RECOSA")
    base_url = (os.environ.get("APP_BASE_URL") or "").rstrip("/")

    if not api_key:
        result["error"] = "BREVO_API_KEY is not set."
        return result

    try:
        admin = get_supabase_admin()
        alerts = admin.table("client_alerts") \
            .select("id, user_id") \
            .eq("update_id", update["id"]) \
            .eq("email_sent", False) \
            .execute().data or []
        if not alerts:
            return result

        # client_alerts has no foreign key to profiles, so an embedded
        # profiles(email) select fails (PGRST200). Look the emails up directly.
        alert_ids_by_user: dict[str, list[str]] = {}
        for a in alerts:
            alert_ids_by_user.setdefault(a["user_id"], []).append(a["id"])
        profiles = admin.table("profiles") \
            .select("id, email, ui_language") \
            .in_("id", list(alert_ids_by_user)) \
            .execute().data or []
        email_by_user = {p["id"]: p.get("email") for p in profiles}
        lang_by_user = {p["id"]: _lang(p.get("ui_language")) for p in profiles}

        # Assigned by a DB trigger on approval, so the caller's copy of the
        # row (loaded before approving) does not have it yet.
        ref_rows = admin.table("regulatory_updates") \
            .select("alert_ref") \
            .eq("id", update["id"]) \
            .execute().data or []
        alert_ref = (ref_rows[0].get("alert_ref") if ref_rows else None) or ""
        ref_prefix = f"{alert_ref} · " if alert_ref else ""

        for user_id, alert_ids in alert_ids_by_user.items():
            email = email_by_user.get(user_id)
            if not email:
                result["failed"].append((f"user {user_id}", "no email on profile"))
                continue
            # D-168: the frame in the reader's language. The alert itself
            # (title, summary, what to do) is written once, by us, in English.
            lang = lang_by_user.get(user_id, "en")
            severity_label = {"urgent": "🔴 " + tr("Urgent", lang),
                              "important": "🟡 " + tr("Important", lang),
                              }.get(update.get("severity", "info"), "🔵 " + tr("Info", lang))
            action_html = (
                '<div style="background:#e8f5e9;border-left:4px solid #0F6E56;padding:12px;margin:16px 0"><strong>'
                + tr("What to do:", lang) + '</strong> '
                + update.get("action_description", "") + "</div>"
            ) if update.get("action_description") else ""
            link_html = (
                '<p><a href="' + update.get("url", "")
                + '" style="color:#003366;font-weight:bold">' + tr("Read the full document", lang) + ' →</a></p>'
            ) if update.get("url") else ""

            html = email_layout(
                tr("Regulatory alert", lang),
                f'''<p style="color:#666;font-size:12px;margin:0 0 12px">{ref_prefix}{severity_label} · {update.get('source','')} · {(update.get('published_at') or '')[:10]}</p>
    <h2 style="color:{BRAND_DARK};font-size:18px;margin:0 0 12px">{update.get('title','')}</h2>
    <p style="color:#444">{update.get('summary','')}</p>
    {action_html}
    {link_html}''',
                tr("View all alerts in RECOSA", lang), f"{base_url}/alerts",
                footer_note=tr("EU-native compliance for SMEs.", lang),
            )

            try:
                r = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": api_key, "Content-Type":"application/json"},
                    json={
                        "sender": {"name": from_name, "email": from_email},
                        "to": [{"email": email}],
                        "subject": f"[RECOSA] {ref_prefix}{severity_label} — {update.get('title','')}",
                        "htmlContent": html,
                    },
                    timeout=15,
                )
            except Exception as e:
                result["failed"].append((email, f"request failed: {e}"))
                continue
            if r.status_code not in (200, 201):
                result["failed"].append((email, f"Brevo {r.status_code}: {r.text[:200]}"))
                continue

            admin.table("client_alerts") \
                .update({"email_sent": True}) \
                .in_("id", alert_ids) \
                .execute()
            result["sent"].append(email)

        return result
    except Exception as e:
        print(f"Alert email error: {e}")
        result["error"] = str(e)
        return result


# ── The short notifications (S22, S38, S56, S60) ─────────────────────────────
# Same shape for all four: NOTIFY_ENABLED gate, soft-fail (False, never an
# exception), a deep link and nothing sensitive (D-05). D-168: each in the
# recipient's language, looked up from their address unless the caller knows.

def _notify_config() -> tuple[str, str, str, str] | None:
    if os.environ.get("NOTIFY_ENABLED", "false").strip().lower() != "true":
        return None
    api_key    = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    if not (api_key and from_email and base_url):
        return None
    return api_key, from_email, from_name, base_url


def _short_html(paragraphs: list[str], action: str, link: str, note: str = "") -> str:
    """paragraphs are HTML (escape what you put in them); action and note are text."""
    import html as _h
    body = "".join(f'''
    <p style="color:#333;line-height:1.6;margin:0 0 18px">{p}</p>''' for p in paragraphs)
    note_html = (f'''
    <p style="color:#6b7280;font-size:12px;margin:0">{_h.escape(note)}</p>''' if note else "")
    return f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
  <div style="background:#003366;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">RECOSA</h1>
  </div>
  <div style="background:#f7f9fb;padding:24px;border:1px solid #e8edf2">{body}
    <p style="margin:0 0 18px">
      <a href="{link}"
         style="display:inline-block;background:#003366;color:#fff;
                padding:11px 24px;border-radius:6px;text-decoration:none;
                font-weight:bold;font-size:14px">{_h.escape(action)} &rarr;</a>
    </p>{note_html}
  </div>
  <div style="background:#e8edf2;padding:14px;border-radius:0 0 8px 8px;
              text-align:center">
    <p style="color:#6b7280;font-size:11px;margin:0">RECOSA &middot; recosa.eu</p>
  </div>
</div>
"""


def _post_short(cfg, to_email: str, subject: str, text_body: str, html_body: str, what: str) -> bool:
    api_key, from_email, from_name, _base = cfg
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender":      {"name": from_name, "email": from_email},
                "to":          [{"email": to_email}],
                "subject":     subject,
                "textContent": text_body,
                "htmlContent": html_body,
            },
            timeout=10,
        )
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"{what} error: {e}")
        return False


def send_ticket_reply_notification(
    to_email: str,
    ticket_id: str,
    ticket_ref: str | None = None,
    lang: str | None = None,
) -> bool:
    """Content-free nudge telling a client a reply is waiting.

    Deliberately excludes the message body AND the ticket subject, category
    and severity. All of those are client-authored and routinely contain
    compliance content ("do we have to notify the APD about the 3 August
    breach?"), which must never transit Brevo. The email carries a reference
    and a link, nothing else.

    Returns False (without raising) on any failure so a Brevo outage can
    never break the reply that triggered it.
    """
    cfg = _notify_config()
    if not (cfg and to_email):
        return False
    lang = _lang(lang) if lang else language_of(to_email)
    label = ticket_ref or str(ticket_id)[:8]
    link  = f"{cfg[3]}/support?ticket={ticket_id}"
    intro = tr("You have a new reply on your RECOSA support request {ref}.", lang)
    note = tr("For confidentiality, replies are only readable inside RECOSA. "
              "Nothing about your request is included in this email.", lang)
    action = tr("Open the request", lang)
    text_body = f"{intro.format(ref=label)}\n\n{action}: {link}\n\n{note}\nRECOSA - recosa.eu"
    html_body = _short_html([intro.format(ref=f"<strong>{label}</strong>")], action, link, note)
    subject = tr("RECOSA support - new reply on request {ref}", lang).format(ref=label)
    return _post_short(cfg, to_email, subject, text_body, html_body, "Ticket reply notification")


def send_workspace_invite(
    to_email: str, client_name: str, inviter_email: str,
    set_password_url: str | None = None, lang: str | None = None,
) -> bool:
    """Tells someone they now have access to a client on RECOSA.

    There is no per-invite page to land on — logging in is what claims the
    invite (database.claim_pending_invites, called from app.py) — so the
    link is just the app root, not a token URL. Kept short on the same
    principle as the others: say what happened, not what it is about.
    lang: the new member has no settings yet, so the caller passes the
    language of the account inviting them; otherwise their profile's.
    """
    import html as _h
    cfg = _notify_config()
    if not (cfg and to_email):
        return False
    lang = _lang(lang) if lang else language_of(to_email)

    # D-146: a new colleague gets a one-time link to choose their password.
    link = set_password_url or f"{cfg[3]}/"
    action = tr("Choose my password", lang) if set_password_url else tr("Log in", lang)
    how = (tr("Your account is ready. Choose your password with the button below. "
              "The link works once; if it has expired, ask for a new invite.", lang)
           if set_password_url else tr("Log in with this email address to start.", lang))
    what = tr("{inviter} has given you access to {company} on RECOSA.", lang)
    text_body = (f"{what.format(inviter=inviter_email, company=client_name)}\n\n"
                 f"{how}\n\n{action}: {link}\n\nRECOSA - recosa.eu")
    html_body = _short_html(
        [what.format(inviter=f"<strong>{_h.escape(inviter_email or '')}</strong>",
                     company=f"<strong>{_h.escape(client_name or '')}</strong>"), _h.escape(how)],
        action, link)
    subject = tr("You've been given access to {company} on RECOSA", lang).format(company=client_name)
    return _post_short(cfg, to_email, subject, text_body, html_body, "Workspace invite notification")


# ── S56: inbox nudge ───────────────────────────────────────────────────────

def send_inbox_nudge(to_email: str, lang: str | None = None) -> bool:
    """Content-free: someone has something new in their RECOSA inbox.

    D-05: no title, no company, no comment text, no name — those are
    compliance content written by the client. Sent only when the person's
    inbox goes from empty to not empty (work_items.notify), so a busy day is
    one email, not twenty.
    """
    import html as _h
    cfg = _notify_config()
    if not (cfg and to_email):
        return False
    lang = _lang(lang) if lang else language_of(to_email)
    link = f"{cfg[3]}/inbox"
    intro = tr("You have something new in your RECOSA inbox: a task given to you, or a comment.", lang)
    note = tr("For confidentiality, nothing about the task or the comment is included in this email.", lang)
    action = tr("Open my inbox", lang)
    text_body = f"{intro}\n\n{action}: {link}\n\n{note}\nRECOSA - recosa.eu"
    html_body = _short_html([_h.escape(intro)], action, link, note)
    return _post_short(cfg, to_email, tr("Something new for you in RECOSA", lang),
                       text_body, html_body, "Inbox nudge")


# ── S60: training nudge ────────────────────────────────────────────────────

def send_training_nudge(to_email: str, lang: str | None = None) -> bool:
    """Content-free: someone's training is due or has lapsed in RECOSA.

    D-05: no names, no company, no training titles — those stay in RECOSA.
    At most monthly per company (clients.training_nudged_at, set by
    monitor_training.py).
    """
    import html as _h
    cfg = _notify_config()
    if not (cfg and to_email):
        return False
    lang = _lang(lang) if lang else language_of(to_email)
    link = f"{cfg[3]}/training"
    intro = tr("Some of your staff training is due, or has lapsed.", lang)
    note = tr("For confidentiality, nothing about your staff is included in this email.", lang)
    action = tr("Open Training", lang)
    text_body = f"{intro}\n\n{action}: {link}\n\n{note}\nRECOSA - recosa.eu"
    html_body = _short_html([_h.escape(intro)], action, link, note)
    return _post_short(cfg, to_email, tr("Staff training due in RECOSA", lang),
                       text_body, html_body, "Training nudge")
