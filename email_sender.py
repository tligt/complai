import os
import base64
import requests


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
) -> bool:
    """
    Send the audit report PDF by email using the Brevo API.
    Returns True on success, False on failure.

    S49: cta_url, when given, is the signup link carrying the checked site
    (funnel.signup_url); otherwise the button opens the app's root.
    """
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

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;">

  <div style="background:#1B2A4A;padding:24px;border-radius:8px 8px 0 0;">
    <h1 style="color:white;margin:0;font-size:24px;">RECOSA ⚖️</h1>
    <p style="color:#ccc;margin:4px 0 0;">Your Website Compliance Audit Report</p>
  </div>

  <div style="background:#F4F3F0;padding:20px;border:1px solid #D3D1C7;">
    <h2 style="color:#1B2A4A;margin-top:0;">
      {risk_emoji} Compliance Score: {score}/100 — {risk_level} Risk
    </h2>
    <p>We completed the compliance audit for <strong>{website_url}</strong>.</p>

    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr>
        <td style="padding:10px;background:#0F6E56;color:white;text-align:center;border-radius:4px;width:30%;">
          <strong style="font-size:20px;">{ok_count}</strong><br>
          <span style="font-size:12px;">Compliant</span>
        </td>
        <td style="width:5%;"></td>
        <td style="padding:10px;background:#BA7517;color:white;text-align:center;border-radius:4px;width:30%;">
          <strong style="font-size:20px;">{warn_count}</strong><br>
          <span style="font-size:12px;">Needs attention</span>
        </td>
        <td style="width:5%;"></td>
        <td style="padding:10px;background:#993C1D;color:white;text-align:center;border-radius:4px;width:30%;">
          <strong style="font-size:20px;">{fail_count}</strong><br>
          <span style="font-size:12px;">Missing</span>
        </td>
      </tr>
    </table>

    <p>Your full audit report is attached to this email as a PDF.</p>
  </div>

  <div style="background:#4A3B8C;padding:20px;border-radius:0 0 8px 8px;text-align:center;">
    <h3 style="color:white;margin-top:0;">Ready to fix these gaps?</h3>
    <p style="color:#ccc;font-size:14px;">
      RECOSA shows you exactly how to remediate each issue, generates the required documents,
      and monitors your compliance continuously.
    </p>
    <a href="{cta_url}"
       style="display:inline-block;background:#0F6E56;color:white;
              padding:12px 28px;border-radius:6px;text-decoration:none;
              font-weight:bold;font-size:15px;margin-top:8px;">
      Start your free 14-day trial →
    </a>
    <p style="color:#aaa;font-size:12px;margin-top:12px;">No credit card required.</p>
  </div>

  <p style="color:#999;font-size:11px;text-align:center;margin-top:16px;">
    This audit was generated automatically by RECOSA based on publicly accessible website content.
    It does not constitute legal advice.<br>
    RECOSA · recosa.eu
  </p>

</body>
</html>
"""

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "subject": f"Your RECOSA Compliance Audit — {website_url} ({risk_level} Risk, {score}/100)",
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


def send_quiz_result(to_email: str, answers: list[int], cta_url: str) -> bool:
    """S49. The full NIS2 Quick Check result, sent because the visitor asked
    for it on the public quiz. Weakest areas first, each with what to do.
    Returns True on success. Raises if BREVO_API_KEY is not set, like
    send_audit_report."""
    import html
    import funnel

    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")
    from_email = os.environ.get("BREVO_FROM_EMAIL", "audit@complai.be")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")

    total = funnel.score(answers)
    label, blurb = funnel.band(total)
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
        for r in funnel.breakdown(answers)
    )

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;">
  <div style="background:#1B2A4A;padding:24px;border-radius:8px 8px 0 0;">
    <h1 style="color:white;margin:0;font-size:24px;">RECOSA</h1>
    <p style="color:#ccc;margin:4px 0 0;">Your NIS2 Quick Check result</p>
  </div>
  <div style="background:#F4F3F0;padding:20px;border:1px solid #D3D1C7;">
    <h2 style="color:#1B2A4A;margin-top:0;">{total}/{funnel.MAX_SCORE} — {html.escape(label)}</h2>
    <p>{html.escape(blurb)}</p>
    <h3 style="color:#1B2A4A;">Your ten areas, weakest first</h3>
    <table style="width:100%;border-collapse:collapse;background:white;">{rows}
    </table>
  </div>
  <div style="background:#4A3B8C;padding:20px;border-radius:0 0 8px 8px;text-align:center;">
    <h3 style="color:white;margin-top:0;">Turn this into a plan</h3>
    <p style="color:#ccc;font-size:14px;">
      Create a free account to see this result in RECOSA, then start a 14-day trial
      to run the full assessment against every NIS2 obligation.
    </p>
    <a href="{cta_url}"
       style="display:inline-block;background:#0F6E56;color:white;padding:12px 28px;
              border-radius:6px;text-decoration:none;font-weight:bold;font-size:15px;">
      See my result in RECOSA →
    </a>
  </div>
  <p style="color:#999;font-size:11px;text-align:center;margin-top:16px;">
    A lightweight self-check based on your own answers — not a certified NIS2 audit,
    and not legal advice. You received this because you asked for your result on
    recosa.eu.<br>RECOSA · recosa.eu
  </p>
</body>
</html>
"""
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": to_email}],
            "subject": f"Your NIS2 Quick Check result: {total}/{funnel.MAX_SCORE} — {label}",
            "htmlContent": html_body,
        },
        timeout=20,
    )
    if response.status_code not in (200, 201):
        print(f"Brevo refused the quiz result: {response.status_code} {response.text[:300]}")
    return response.status_code in (200, 201)


def send_incident_reminder(to_emails: list[str], company: str, incident_title: str,
                           items: list[tuple[str, str]], overdue: bool) -> bool:
    """S53. An incident deadline is close or missed. items: (deadline label,
    'in 4 h 10' / '3 h overdue'). Content-light on purpose — what happened
    stays in RECOSA; the email only says that a clock is running."""
    import html
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")
    colour = "#993C1D" if overdue else "#BA7517"
    lines = "".join(
        f'<li style="margin:6px 0;"><strong>{html.escape(l)}</strong> — '
        f'<span style="color:{colour};">{html.escape(w)}</span></li>' for l, w in items)
    html_body = f"""
<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;">
  <div style="background:{colour};padding:18px 22px;border-radius:8px 8px 0 0;">
    <h2 style="color:white;margin:0;">{'Incident deadline missed' if overdue else 'Incident deadline approaching'}</h2>
  </div>
  <div style="background:#F4F3F0;padding:20px;border:1px solid #D3D1C7;border-radius:0 0 8px 8px;">
    <p><strong>{html.escape(company)}</strong> — {html.escape(incident_title)}</p>
    <ul style="padding-left:18px;">{lines}</ul>
    <p>Send what you know now and follow up later: a late complete notification is worse than an
       early incomplete one. If a notification was already sent, record it in RECOSA to stop the clock.</p>
    <a href="{base_url}/incidents" style="display:inline-block;background:#003366;color:white;
       padding:10px 22px;border-radius:6px;text-decoration:none;font-weight:bold;">Open the incident</a>
  </div>
  <p style="color:#999;font-size:11px;text-align:center;margin-top:14px;">
    Sent because an incident is open in RECOSA for this company. RECOSA · recosa.eu</p>
</body></html>
"""
    response = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": api_key, "Content-Type": "application/json"},
        json={
            "sender": {"name": from_name, "email": from_email},
            "to": [{"email": e} for e in to_emails],
            "subject": ("Missed: " if overdue else "Due soon: ")
                       + f"incident deadline — {incident_title}"[:150],
            "htmlContent": html_body,
        },
        timeout=20,
    )
    if response.status_code not in (200, 201):
        print(f"Brevo refused the incident reminder: {response.status_code} {response.text[:300]}")
    return response.status_code in (200, 201)


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
            .select("id, email") \
            .in_("id", list(alert_ids_by_user)) \
            .execute().data or []
        email_by_user = {p["id"]: p.get("email") for p in profiles}

        severity_labels = {"urgent":"🔴 Urgent","important":"🟡 Important","info":"🔵 Info"}
        severity_label = severity_labels.get(update.get("severity","info"),"🔵 Info")

        # Assigned by a DB trigger on approval, so the caller's copy of the
        # row (loaded before approving) does not have it yet.
        ref_rows = admin.table("regulatory_updates") \
            .select("alert_ref") \
            .eq("id", update["id"]) \
            .execute().data or []
        alert_ref = (ref_rows[0].get("alert_ref") if ref_rows else None) or ""
        ref_prefix = f"{alert_ref} · " if alert_ref else ""

        action_html = (
            '<div style="background:#e8f5e9;border-left:4px solid #0F6E56;padding:12px;margin:16px 0"><strong>What to do:</strong> '
            + update.get("action_description", "") + "</div>"
        ) if update.get("action_description") else ""
        link_html = (
            '<p><a href="' + update.get("url", "")
            + '" style="color:#1B2A4A;font-weight:bold">Read full document →</a></p>'
        ) if update.get("url") else ""

        for user_id, alert_ids in alert_ids_by_user.items():
            email = email_by_user.get(user_id)
            if not email:
                result["failed"].append((f"user {user_id}", "no email on profile"))
                continue

            html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#1B2A4A;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="color:white;margin:0;font-size:24px">RECOSA</h1>
    <p style="color:#ccc;margin:8px 0 0">Regulatory Alert</p>
  </div>
  <div style="background:#f9f9f9;padding:24px;border:1px solid #eee">
    <p style="color:#666;font-size:12px;margin:0 0 12px">{ref_prefix}{severity_label} ·{update.get('source','')} · {(update.get('published_at') or '')[:10]}</p>
    <h2 style="color:#1B2A4A;font-size:18px;margin:0 0 12px">{update.get('title','')}</h2>
    <p style="color:#444;line-height:1.6">{update.get('summary','')}</p>
    {action_html}
    {link_html}
  </div>
  <div style="background:#eee;padding:16px;border-radius:0 0 8px 8px;text-align:center">
    <p style="color:#888;font-size:11px;margin:0">
      RECOSA · recosa.eu · EU-native compliance for SMEs<br>
      <a href="{base_url}/alerts" style="color:#0F6E56">View all alerts in RECOSA</a>
    </p>
  </div>
</div>"""

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


# ── S22: Support ticket reply notification ────────────────────────────────────

def send_ticket_reply_notification(
    to_email: str,
    ticket_id: str,
    ticket_ref: str | None = None,
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
    if os.environ.get("NOTIFY_ENABLED", "false").strip().lower() != "true":
        return False

    api_key    = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")

    if not (api_key and from_email and base_url and to_email):
        return False

    label = ticket_ref or str(ticket_id)[:8]
    link  = f"{base_url}/support?ticket={ticket_id}"

    text_body = (
        f"You have a new reply on your RECOSA support request {label}.\n\n"
        f"Open it here: {link}\n\n"
        "For confidentiality, replies are only readable inside RECOSA.\n"
        "RECOSA - recosa.eu"
    )

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
  <div style="background:#003366;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">RECOSA</h1>
    <p style="color:#c9d6e3;margin:6px 0 0;font-size:13px">Support</p>
  </div>
  <div style="background:#f7f9fb;padding:24px;border:1px solid #e8edf2">
    <p style="color:#333;line-height:1.6;margin:0 0 18px">
      You have a new reply on your support request
      <strong>{label}</strong>.
    </p>
    <p style="margin:0 0 18px">
      <a href="{link}"
         style="display:inline-block;background:#003366;color:#fff;
                padding:11px 24px;border-radius:6px;text-decoration:none;
                font-weight:bold;font-size:14px">Open the request &rarr;</a>
    </p>
    <p style="color:#6b7280;font-size:12px;margin:0">
      For confidentiality, replies are only readable inside RECOSA.
      Nothing about your request is included in this email.
    </p>
  </div>
  <div style="background:#e8edf2;padding:14px;border-radius:0 0 8px 8px;
              text-align:center">
    <p style="color:#6b7280;font-size:11px;margin:0">RECOSA &middot; recosa.eu</p>
  </div>
</div>
"""

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender":      {"name": from_name, "email": from_email},
                "to":          [{"email": to_email}],
                "subject":     f"RECOSA support - new reply on request {label}",
                "textContent": text_body,
                "htmlContent": html_body,
            },
            timeout=10,
        )
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"Ticket reply notification error: {e}")
        return False


# ── S38: workspace invite notification ─────────────────────────────────────

def send_workspace_invite(
    to_email: str, client_name: str, inviter_email: str,
) -> bool:
    """Tells someone they now have access to a client on RECOSA.

    Same shape as send_ticket_reply_notification: NOTIFY_ENABLED gate,
    soft-fail, a deep link and nothing else sensitive. There is no
    per-invite page to land on — logging in is what claims the invite
    (database.claim_pending_invites, called from app.py) — so the link is
    just the app root, not a token URL. Less confidentiality-sensitive
    than a ticket reply, but kept just as short on the same principle:
    say what happened, not what it is about.
    """
    if os.environ.get("NOTIFY_ENABLED", "false").strip().lower() != "true":
        return False

    api_key    = os.environ.get("BREVO_API_KEY")
    from_email = os.environ.get("BREVO_FROM_EMAIL")
    from_name  = os.environ.get("BREVO_FROM_NAME", "RECOSA")
    base_url   = (os.environ.get("APP_BASE_URL") or "").rstrip("/")

    if not (api_key and from_email and base_url and to_email):
        return False

    text_body = (
        f"{inviter_email} has given you access to {client_name} on RECOSA.\n\n"
        f"Log in here: {base_url}/\n\n"
        "If you don't have an account yet, sign up with this email address "
        "and access is granted automatically.\n\n"
        "RECOSA - recosa.eu"
    )

    html_body = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto">
  <div style="background:#003366;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">RECOSA</h1>
  </div>
  <div style="background:#f7f9fb;padding:24px;border:1px solid #e8edf2">
    <p style="color:#333;line-height:1.6;margin:0 0 18px">
      <strong>{inviter_email}</strong> has given you access to
      <strong>{client_name}</strong> on RECOSA.
    </p>
    <p style="margin:0 0 18px">
      <a href="{base_url}/"
         style="display:inline-block;background:#003366;color:#fff;
                padding:11px 24px;border-radius:6px;text-decoration:none;
                font-weight:bold;font-size:14px">Log in &rarr;</a>
    </p>
    <p style="color:#6b7280;font-size:12px;margin:0">
      No account yet? Sign up with this email address and access is
      granted automatically.
    </p>
  </div>
  <div style="background:#e8edf2;padding:14px;border-radius:0 0 8px 8px;
              text-align:center">
    <p style="color:#6b7280;font-size:11px;margin:0">RECOSA &middot; recosa.eu</p>
  </div>
</div>
"""

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "sender":      {"name": from_name, "email": from_email},
                "to":          [{"email": to_email}],
                "subject":     f"You've been given access to {client_name} on RECOSA",
                "textContent": text_body,
                "htmlContent": html_body,
            },
            timeout=10,
        )
        return response.status_code in (200, 201, 202)
    except Exception as e:
        print(f"Workspace invite notification error: {e}")
        return False
