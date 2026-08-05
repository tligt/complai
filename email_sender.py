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
) -> bool:
    """
    Send the audit report PDF by email using the Brevo API.
    Returns True on success, False on failure.
    """
    api_key = os.environ.get("BREVO_API_KEY")
    if not api_key:
        raise ValueError("BREVO_API_KEY not set in secrets.")

    from_email = os.environ.get("BREVO_FROM_EMAIL", "audit@complai.be")
    from_name  = os.environ.get("BREVO_FROM_NAME", "COMPLAI Audit")

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    risk_emoji = {"Green": "🟢", "Amber": "🟡", "Red": "🔴"}.get(risk_level, "⚪")

    filename = (
        "COMPLAI_Audit_"
        + website_url.replace("https://", "").replace("http://", "").replace("/", "_")
        + ".pdf"
    )

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#333;">

  <div style="background:#1B2A4A;padding:24px;border-radius:8px 8px 0 0;">
    <h1 style="color:white;margin:0;font-size:24px;">COMPLAI ⚖️</h1>
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
      COMPLAI shows you exactly how to remediate each issue, generates the required documents,
      and monitors your compliance continuously.
    </p>
    <a href="https://complai.be/register"
       style="display:inline-block;background:#0F6E56;color:white;
              padding:12px 28px;border-radius:6px;text-decoration:none;
              font-weight:bold;font-size:15px;margin-top:8px;">
      Start your free 15-day trial →
    </a>
    <p style="color:#aaa;font-size:12px;margin-top:12px;">No credit card required.</p>
  </div>

  <p style="color:#999;font-size:11px;text-align:center;margin-top:16px;">
    This audit was generated automatically by COMPLAI based on publicly accessible website content.
    It does not constitute legal advice.<br>
    COMPLAI · complai.be
  </p>

</body>
</html>
"""

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "subject": f"Your COMPLAI Compliance Audit — {website_url} ({risk_level} Risk, {score}/100)",
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
    )

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


def send_regulatory_alert(update: dict) -> bool:
    """Send regulatory alert email to all affected clients."""
    import os, requests, json
    from database import get_supabase_admin

    api_key = os.environ.get("BREVO_API_KEY","")
    from_email = os.environ.get("BREVO_FROM_EMAIL","audit@complai.be")
    from_name = os.environ.get("BREVO_FROM_NAME","COMPLAI")

    if not api_key:
        return False

    try:
        admin = get_supabase_admin()
        # Get all client alert records for this update that haven't been emailed
        alerts_res = admin.table("client_alerts")             .select("user_id, clients(company_name), profiles(email)")             .eq("update_id", update["id"])             .eq("email_sent", False)             .execute()

        alerts = alerts_res.data or []
        if not alerts:
            return True

        severity_labels = {"urgent":"🔴 Urgent","important":"🟡 Important","info":"🔵 Info"}
        severity_label = severity_labels.get(update.get("severity","info"),"🔵 Info")

        for alert in alerts:
            email = (alert.get("profiles") or {}).get("email")
            if not email:
                continue

            html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <div style="background:#1B2A4A;padding:20px;border-radius:8px 8px 0 0">
    <h1 style="color:white;margin:0;font-size:24px">COMPL<span style="color:#0F6E56">AI</span></h1>
    <p style="color:#ccc;margin:8px 0 0">Regulatory Alert</p>
  </div>
  <div style="background:#f9f9f9;padding:24px;border:1px solid #eee">
    <p style="color:#666;font-size:12px;margin:0 0 12px">{severity_label} · {update.get('source','')} · {(update.get('published_at') or '')[:10]}</p>
    <h2 style="color:#1B2A4A;font-size:18px;margin:0 0 12px">{update.get('title','')}</h2>
    <p style="color:#444;line-height:1.6">{update.get('summary','')}</p>
    {"<div style=\"background:#e8f5e9;border-left:4px solid #0F6E56;padding:12px;margin:16px 0\"><strong>What to do:</strong> " + update.get("action_description","") + "</div>" if update.get("action_description") else ""}
    {"<p><a href=\"" + update.get("url","") + "\" style=\"color:#1B2A4A;font-weight:bold\">Read full document →</a></p>" if update.get("url") else ""}
  </div>
  <div style="background:#eee;padding:16px;border-radius:0 0 8px 8px;text-align:center">
    <p style="color:#888;font-size:11px;margin:0">
      COMPLAI · complai.be · EU-native compliance for SMEs<br>
      <a href="https://app.complai.be/alerts" style="color:#0F6E56">View all alerts in COMPLAI</a>
    </p>
  </div>
</div>"""

            requests.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={"api-key": api_key, "Content-Type":"application/json"},
                json={
                    "sender": {"name": from_name, "email": from_email},
                    "to": [{"email": email}],
                    "subject": f"[COMPLAI] {severity_label} — {update.get('title','')}",
                    "htmlContent": html,
                },
                timeout=15,
            )

        # Mark as email_sent
        admin.table("client_alerts")             .update({"email_sent": True})             .eq("update_id", update["id"])             .execute()

        return True
    except Exception as e:
        print(f"Alert email error: {e}")
        return False


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
