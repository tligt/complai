"""
incident_rules.py — S53. What an incident requires, and by when.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61) The page, the action plan, the
incident file and the hourly reminder job all read the same answers here.

THE REGIMES (S29A procedure, D-80/D-83; part 2 legal gaps, D-118)
-----------------------------------------------------------------
    GDPR Art. 33(1)  personal data breach, UNLESS unlikely to result in a
                     risk → supervisory authority, 72 h. Late: with the
                     reasons for the delay. Information may follow in
                     phases (33(4)). Every breach is documented (33(5)),
                     including the ones not notified, with the reason.
    GDPR Art. 34     HIGH risk → the people, without undue delay — unless
                     34(3): (a) data unintelligible (encryption),
                     (b) subsequent measures remove the high risk,
                     (c) disproportionate effort → a public communication
                     instead.
    GDPR Art. 33(2)  the client is a processor → each controller, without
                     undue delay — every breach, no risk test; the client's
                     DPAs may promise hours (clients.breach_notice_hours).
    NIS2 Art. 23     significant incident, entity in scope → CSIRT:
                     early warning 24 h; notification 72 h; intermediate
                     report when the CSIRT asks; final report one month
                     AFTER THE NOTIFICATION — or, if the incident is still
                     being handled then, a progress report at that date
                     and the final report one month after handling ends.
                     Recipients of the service likely to be affected are
                     informed without undue delay (23(1)).
    Contracts        a team member with deadline_hours (an insurer's 48 h)
                     gets a clock of their own, from discovery.

An unanswered question (None) is not a "no". A clock whose regime is not yet
decided is shown as "to decide", and the deadline still counts from
discovery: deciding late does not move it.

DRAFTS, NOT SUBMISSIONS
-----------------------
The texts are what to paste into the authority's own portal. Templates, no
LLM (D-117): a notification is a legal statement the client makes.
Placeholders are left visible ([to complete]) rather than guessed.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

# ── Kinds ─────────────────────────────────────────────────────────────────

GDPR_AUTHORITY    = "gdpr_authority"
DATA_SUBJECTS     = "data_subjects"
CONTROLLERS       = "controllers"
NIS2_EARLY        = "nis2_early_warning"
NIS2_NOTIFICATION = "nis2_notification"
NIS2_INTERMEDIATE = "nis2_intermediate"
NIS2_PROGRESS     = "nis2_progress"
NIS2_FINAL        = "nis2_final"
NIS2_RECIPIENTS   = "nis2_recipients"
CONTACT_PREFIX    = "contact:"   # + incident_contacts.id

KINDS = [NIS2_EARLY, GDPR_AUTHORITY, NIS2_NOTIFICATION, CONTROLLERS, DATA_SUBJECTS,
         NIS2_RECIPIENTS, NIS2_INTERMEDIATE, NIS2_PROGRESS, NIS2_FINAL]

# Which authority receives which kind (for the page and supplementary info).
AUTHORITY_OF = {GDPR_AUTHORITY: "gdpr", NIS2_EARLY: "nis2", NIS2_NOTIFICATION: "nis2",
                NIS2_INTERMEDIATE: "nis2", NIS2_PROGRESS: "nis2", NIS2_FINAL: "nis2"}

LABELS = {
    "en": {
        GDPR_AUTHORITY: "Notify the data protection authority (GDPR Art. 33)",
        DATA_SUBJECTS: "Tell the people affected (GDPR Art. 34)",
        CONTROLLERS: "Notify your clients as controllers (GDPR Art. 33(2))",
        NIS2_EARLY: "NIS2 early warning to the CSIRT",
        NIS2_NOTIFICATION: "NIS2 incident notification to the CSIRT",
        NIS2_INTERMEDIATE: "NIS2 intermediate report (requested by the CSIRT)",
        NIS2_PROGRESS: "NIS2 progress report (incident still being handled)",
        NIS2_FINAL: "NIS2 final report to the CSIRT",
        NIS2_RECIPIENTS: "Inform the users of your service (NIS2 Art. 23(1))",
    },
    "fr": {
        GDPR_AUTHORITY: "Notifier l'autorité de protection des données (RGPD art. 33)",
        DATA_SUBJECTS: "Informer les personnes concernées (RGPD art. 34)",
        CONTROLLERS: "Notifier vos clients responsables du traitement (RGPD art. 33(2))",
        NIS2_EARLY: "Alerte précoce NIS2 au CSIRT",
        NIS2_NOTIFICATION: "Notification d'incident NIS2 au CSIRT",
        NIS2_INTERMEDIATE: "Rapport intermédiaire NIS2 (demandé par le CSIRT)",
        NIS2_PROGRESS: "Rapport d'avancement NIS2 (incident toujours en cours)",
        NIS2_FINAL: "Rapport final NIS2 au CSIRT",
        NIS2_RECIPIENTS: "Informer les destinataires de vos services (NIS2 art. 23(1))",
    },
}

ROLES = {
    "lead": "Incident lead", "deputy": "Deputy incident lead", "it": "IT",
    "external_it": "External IT provider", "dpo": "DPO / privacy contact",
    "management": "Management", "legal": "Legal", "communications": "Communications",
    "insurer": "Cyber insurer", "other": "Other",
}
ALERT_ON = {
    "all": "Every incident", "personal_data": "When personal data is involved",
    "significant": "Significant (NIS2) incidents", "never": "Not alerted",
}
SUBJECTS_EXEMPTIONS = {
    "encrypted": "Art. 34(3)(a) — the data is unintelligible to anyone not authorised (e.g. encrypted)",
    "measures": "Art. 34(3)(b) — measures taken since ensure the high risk is no longer likely",
    "public": "Art. 34(3)(c) — contacting each person is disproportionate: a public communication instead",
}
GDPR_RISK = {
    "none": "Unlikely to result in a risk — not notified, reason recorded",
    "risk": "A risk to people's rights — notify the authority",
    "high": "A high risk — notify the authority and tell the people",
}


def label(kind: str, lang: str = "en", contacts: Mapping[str, Mapping] | None = None) -> str:
    if kind.startswith(CONTACT_PREFIX):
        c = (contacts or {}).get(kind[len(CONTACT_PREFIX):]) or {}
        name = c.get("name") or "team member"
        return (f"Prévenir {name} (contrat)" if lang == "fr" else
                f"Notify {name} ({ROLES.get(c.get('role'), '').lower() or 'contract'}) — contractual deadline")
    return LABELS.get(lang, LABELS["en"]).get(kind, kind)


# ── Clock states ──────────────────────────────────────────────────────────

OVERDUE      = "overdue"
DUE_SOON     = "due_soon"     # under DUE_SOON_HOURS left
RUNNING      = "running"
TO_DECIDE    = "to_decide"    # the regime is not decided yet; the clock still runs
DONE         = "done"
NOT_REQUIRED = "not_required"

DUE_SOON_HOURS = 6
OPEN_STATES = (OVERDUE, DUE_SOON, TO_DECIDE, RUNNING)

# Times are shown in Brussels time, as everywhere else in the app (the
# activity log's DISPLAY_TZ_NAME); the label says so, since a deadline read
# in the wrong zone is an hour wrong.
try:
    from zoneinfo import ZoneInfo
    DISPLAY_TZ = ZoneInfo("Europe/Brussels")
    TZ_LABEL = "Brussels time"
except Exception:  # no tz database (bare Windows without tzdata)
    DISPLAY_TZ = timezone.utc
    TZ_LABEL = "UTC"

_ORDER = {OVERDUE: 0, DUE_SOON: 1, TO_DECIDE: 2, RUNNING: 3, DONE: 4, NOT_REQUIRED: 5}
_FAR = datetime.max.replace(tzinfo=timezone.utc)


def _ts(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _add_month(d: datetime) -> datetime:
    """Same day next month, clamped to the month's end (31 Jan → 28/29 Feb)."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def sent(events: Iterable[Mapping[str, Any]], kind: str) -> Mapping[str, Any] | None:
    """The first recorded notification of this kind, if any."""
    notes = [e for e in events if e.get("event_type") == "notification" and e.get("kind") == kind]
    return min(notes, key=lambda e: _ts(e["occurred_at"])) if notes else None


def nis2_applies(client: Mapping[str, Any]) -> bool:
    """The client's own NIS2 scope answer (Profile) when given; otherwise
    whether NIS2 is among its regulations. Unset is common — no client had
    answered it on 22 Oct 2026 — and must not silently mean 'out of scope'."""
    if client.get("nis2_in_scope") is not None:
        return bool(client["nis2_in_scope"])
    return "NIS2" in (client.get("regulations") or [])


def final_report_due(incident: Mapping[str, Any], events: Iterable[Mapping[str, Any]],
                     now: datetime) -> tuple[datetime | None, datetime | None]:
    """(final report due, progress report due). Art. 23(4)(d)/(e): one month
    after the notification; if still being handled then, a progress report
    at that date and the final report one month after handling ends."""
    notif = sent(events, NIS2_NOTIFICATION)
    if not notif:
        return None, None
    first = _add_month(_ts(notif["occurred_at"]))
    closed = _ts(incident.get("closed_at"))
    if closed and closed <= first:
        return first, None
    if closed:
        return _add_month(closed), first
    if now <= first:
        return first, None          # may still close in time
    return None, first              # still handling: final report undated


def deadlines(incident: Mapping[str, Any], client: Mapping[str, Any],
              events: Iterable[Mapping[str, Any]], is_processor: bool,
              now: datetime | None = None,
              contacts: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Every deadline this incident has, or may have, worst state first.

    Each: {kind, required (True/False/None = to decide), due (datetime or
    None for "without undue delay" / not yet dated), done_at, state,
    hours_left}.
    """
    now = now or datetime.now(timezone.utc)
    events = list(events)
    found = _ts(incident["discovered_at"])
    pd = incident.get("personal_data")
    risk = incident.get("gdpr_risk")
    sig = incident.get("significant") if nis2_applies(client) else False

    # GDPR Art. 33(1): the risk test decides, not the mere presence of data.
    if pd is False:
        gdpr, subjects = False, False
    elif pd is None or risk is None:
        gdpr = None
        subjects = False if risk in ("none", "risk") else None
    else:
        gdpr = risk in ("risk", "high")
        subjects = risk == "high" and incident.get("subjects_exemption") not in ("encrypted", "measures")

    # Art. 33(2): every breach, no risk test.
    controllers = False if not is_processor else pd
    hours = client.get("breach_notice_hours")
    controllers_due = found + timedelta(hours=int(hours)) if hours else None

    recipients = False if sig is False else (None if sig is None else incident.get("affects_recipients"))
    final_due, progress_due = final_report_due(incident, events, now)
    progress_req: bool | None
    if not sig or not sent(events, NIS2_NOTIFICATION):
        progress_req = False if sig is False else None
    elif progress_due:
        progress_req = True
    else:
        progress_req = False if _ts(incident.get("closed_at")) else None

    specs = [
        (GDPR_AUTHORITY, gdpr, found + timedelta(hours=72)),
        (DATA_SUBJECTS, subjects, None),
        (CONTROLLERS, controllers, controllers_due),
        (NIS2_EARLY, sig, found + timedelta(hours=24)),
        (NIS2_NOTIFICATION, sig, found + timedelta(hours=72)),
        (NIS2_RECIPIENTS, recipients, None),
        (NIS2_INTERMEDIATE, True if sig and incident.get("intermediate_due") else False,
         _ts(incident.get("intermediate_due"))),
        (NIS2_PROGRESS, progress_req, progress_due),
        (NIS2_FINAL, sig, final_due),
    ]
    for c in contacts:
        if not c.get("active", True) or not c.get("deadline_hours"):
            continue
        when = c.get("alert_on") or "all"
        req = {"all": True, "personal_data": pd, "significant": sig, "never": False}.get(when, True)
        specs.append((CONTACT_PREFIX + c["id"], req, found + timedelta(hours=int(c["deadline_hours"]))))

    closed = incident.get("status") == "closed"
    out = []
    for kind, required, due in specs:
        done = sent(events, kind)
        done_at = _ts(done["occurred_at"]) if done else None
        hours_left = (due - now).total_seconds() / 3600 if due else None
        if done_at:
            state = DONE
        elif required is False:
            state = NOT_REQUIRED
        elif closed and required is None:
            state = NOT_REQUIRED
        elif due and hours_left < 0:
            state = OVERDUE
        elif due and hours_left < DUE_SOON_HOURS:
            state = DUE_SOON
        elif required is None:
            state = TO_DECIDE
        else:
            state = RUNNING
        out.append({"kind": kind, "required": required, "due": due,
                    "done_at": done_at, "state": state, "hours_left": hours_left,
                    # Final report undated because the incident is still
                    # being handled past its first date (Art. 23(4)(e)).
                    "after_handling": kind == NIS2_FINAL and due is None
                                      and sent(events, NIS2_NOTIFICATION) is not None})
    return sorted(out, key=lambda d: (_ORDER[d["state"]], d["due"] or _FAR))


def next_deadline(dls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most urgent deadline still open, for lists and the dashboard."""
    open_ = [d for d in dls if d["state"] in OPEN_STATES]
    return open_[0] if open_ else None


def is_late(d: Mapping[str, Any], at: datetime | None = None) -> bool:
    """Sent (or about to be sent, at `at`) after its due date — GDPR then
    wants the reasons for the delay with the notification."""
    at = at or d.get("done_at") or datetime.now(timezone.utc)
    return bool(d.get("due") and at > d["due"])


def describe_left(d: Mapping[str, Any], lang: str = "en") -> str:
    """'in 5 h', '3 h overdue', 'without undue delay', 'sent 22/10 14:05'."""
    fr = lang == "fr"
    if d["state"] == DONE:
        _at = d["done_at"].astimezone(DISPLAY_TZ)
        return (f"envoyé le {_at:%d/%m %H:%M}" if fr
                else f"sent {_at.day} {_at:%b %H:%M}")
    if d["state"] == NOT_REQUIRED:
        return "non requis" if fr else "not required"
    if d["due"] is None:
        if d["kind"] == NIS2_FINAL:
            if d.get("after_handling"):
                return "un mois après la fin du traitement" if fr else "one month after handling ends"
            return "un mois après la notification" if fr else "one month after the notification"
        if d["kind"] == NIS2_PROGRESS:
            return ("si l'incident est encore en cours à la date du rapport final" if fr
                    else "if still being handled when the final report is due")
        return "sans retard injustifié" if fr else "without undue delay"
    h = d["hours_left"]
    if h < 0:
        h = -h
        span = f"{int(h)} h" if h < 72 else (f"{int(h // 24)} j" if fr else f"{int(h // 24)} days")
        return f"en retard de {span}" if fr else f"{span} overdue"
    span = f"{int(h)} h {int((h % 1) * 60):02d}" if h <= 72 else (f"{int(h // 24)} j" if fr else f"{int(h // 24)} days")
    return f"dans {span}" if fr else f"in {span}"


def reminder_stage(d: Mapping[str, Any]) -> str | None:
    """Which reminder this deadline is due, if any: 'soon' or 'overdue'."""
    if d["state"] == OVERDUE:
        return "overdue"
    if d["state"] == DUE_SOON:
        return "soon"
    return None


# ── The team ──────────────────────────────────────────────────────────────

def alert_targets(contacts: Iterable[Mapping[str, Any]], incident: Mapping[str, Any],
                  events: Iterable[Mapping[str, Any]], is_nis2: bool) -> list[Mapping[str, Any]]:
    """Team members who should be alerted now and have not been yet: those
    marked 'every incident' from the start, and those marked 'personal data'
    / 'significant' once the assessment says so."""
    already = set()
    for e in events:
        if e.get("event_type") == "alert":
            already.update((e.get("reference") or "").split(","))
    pd = incident.get("personal_data") is True
    sig = is_nis2 and incident.get("significant") is True
    out = []
    for c in contacts:
        if not c.get("active", True) or not c.get("email") or c["id"] in already:
            continue
        when = c.get("alert_on") or "all"
        if when == "all" or (when == "personal_data" and pd) or (when == "significant" and sig):
            out.append(c)
    return out


# ── Authorities ───────────────────────────────────────────────────────────

def authorities(jurisdiction: Mapping[str, Any], lang: str = "en") -> dict[str, dict[str, Any]]:
    """Who to send each notification to, from the jurisdiction metadata
    (D-83, channels checked 22 Oct 2026). `verified` is False where the
    submission channel was not confirmed on the authority's own site."""
    j = jurisdiction or {}
    l = lang if lang in ("en", "fr", "nl", "de") else "en"
    return {
        "gdpr": {
            "name": j.get(f"supervisory_authority_{l}") or j.get("supervisory_authority_en") or "[to complete]",
            "short": j.get("supervisory_authority_short") or "",
            "site": j.get("supervisory_authority_url"),
            "submit": j.get("breach_portal_url"),
            "note": j.get(f"breach_portal_note_{l}") or j.get("breach_portal_note_en"),
            "verified": bool(j.get("breach_portal_verified_on")),
        },
        "nis2": {
            "name": j.get(f"csirt_{l}") or j.get("csirt_en") or "[to complete]",
            "short": j.get("csirt_short") or "",
            "site": j.get("csirt_url"),
            "submit": j.get("csirt_report_url"),
            "note": j.get(f"csirt_report_note_{l}") or j.get("csirt_report_note_en"),
            "email": j.get("csirt_email"),
            "phone": j.get("csirt_phone"),
            "guide": j.get("csirt_guide_url"),
            "verified": bool(j.get("csirt_report_verified_on")),
        },
    }


# ── Drafts ────────────────────────────────────────────────────────────────

_TBC = {"en": "[to complete]", "fr": "[à compléter]"}


def _v(value: Any, lang: str) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return _TBC[lang]
    return str(value).strip()


def when(dt: Any) -> str:
    d = _ts(dt)
    return d.astimezone(DISPLAY_TZ).strftime("%d/%m/%Y %H:%M") + f" ({TZ_LABEL})" if d else ""


def _sent_line(e: Mapping[str, Any] | None, lang: str) -> str:
    if not e:
        return _TBC[lang]
    ref = e.get("reference")
    return when(e["occurred_at"]) + ((" — réf. " if lang == "fr" else " — ref. ") + ref if ref else "")


def draft(kind: str, incident: Mapping[str, Any], client: Mapping[str, Any],
          systems: list[str], lang: str = "en",
          events: Iterable[Mapping[str, Any]] = (), controller: str | None = None,
          late: bool = False, followup: bool = False) -> str:
    """The text for one notification, in English or French.

    late: GDPR wants the reasons for the delay with a late notification.
    followup: supplementary information to a notification already sent
    (Art. 33(4); a CSIRT update) — headed as such, with its reference."""
    lang = "fr" if lang == "fr" else "en"
    fr = lang == "fr"
    events = list(events)
    v = lambda x: _v(x, lang)  # noqa: E731
    org = client.get("legal_name") or client.get("company_name") or ""
    found = when(incident["discovered_at"])
    sys_list = ", ".join(systems) if systems else v(None)
    dpo = (f"{client['dpo_name']} — {client.get('dpo_email') or ''}".strip(" —")
           if client.get("dpo_name") else client.get("contact_email"))
    subjects = incident.get("approx_subjects")
    records = incident.get("approx_records")
    early = sent(events, NIS2_EARLY)
    notif = sent(events, NIS2_NOTIFICATION)
    public = incident.get("subjects_exemption") == "public"

    if fr:
        T = {
            GDPR_AUTHORITY: f"""Notification de violation de données à caractère personnel (RGPD, art. 33)

Responsable du traitement : {org}
Date et heure de la prise de connaissance : {found}
Systèmes concernés : {sys_list}

a) Nature de la violation
{v(incident.get('description'))}
Catégories de personnes concernées : {v(incident.get('subject_categories'))}
Nombre approximatif de personnes concernées : {v(subjects)}
Catégories d'enregistrements concernés : {v(incident.get('data_categories'))}
Nombre approximatif d'enregistrements concernés : {v(records)}

b) Point de contact
{v(dpo)}

c) Conséquences probables
{v(incident.get('likely_consequences'))}

d) Mesures prises ou envisagées
{v(incident.get('measures_taken'))}

Les informations encore inconnues seront communiquées dès que possible (art. 33(4)).""",
            DATA_SUBJECTS: (f"""Communication publique — incident de sécurité (RGPD, art. 34(3)(c))

Le {found}, {org} a constaté un incident de sécurité : {v(incident.get('description'))}

Données concernées : {v(incident.get('data_categories'))}
Conséquences possibles : {v(incident.get('likely_consequences'))}
Mesures prises : {v(incident.get('measures_taken'))}
Ce que nous recommandons aux personnes concernées : [à compléter]

Contact : {v(dpo)}""" if public else f"""Objet : incident de sécurité concernant vos données

Madame, Monsieur,

Le {found}, {org} a constaté l'incident suivant : {v(incident.get('description'))}

Données concernées : {v(incident.get('data_categories'))}
Conséquences possibles pour vous : {v(incident.get('likely_consequences'))}
Mesures que nous avons prises : {v(incident.get('measures_taken'))}

Ce que nous vous recommandons : [à compléter — par exemple changer votre mot de passe, rester attentif aux messages suspects]

Pour toute question : {v(dpo)}"""),
            CONTROLLERS: f"""Objet : notification d'une violation de données (RGPD, art. 33(2))

À l'attention de {v(controller)},

En tant que sous-traitant, {org} vous notifie une violation de données à caractère personnel susceptible de concerner les traitements que nous effectuons pour votre compte.

Prise de connaissance : {found}
Systèmes concernés : {sys_list}
Nature : {v(incident.get('description'))}
Catégories de personnes / de données : {v(incident.get('subject_categories'))} / {v(incident.get('data_categories'))}
Personnes / enregistrements concernés (approx.) : {v(subjects)} / {v(records)}
Conséquences probables : {v(incident.get('likely_consequences'))}
Mesures prises : {v(incident.get('measures_taken'))}
Contact : {v(dpo)}

Nous vous transmettrons toute information complémentaire dès qu'elle sera disponible.""",
            NIS2_EARLY: f"""Alerte précoce — incident important (NIS2, art. 23(4)(a))

Entité : {org}
Prise de connaissance : {found}
Systèmes concernés : {sys_list}
Description : {v(incident.get('description'))}

L'incident est-il soupçonné d'être causé par des actes illicites ou malveillants ? [à compléter]
Impact transfrontière possible ? [à compléter]
Demande d'assistance : [à compléter]""",
            NIS2_NOTIFICATION: f"""Notification d'incident (NIS2, art. 23(4)(b))

Entité : {org}
Prise de connaissance : {found}
Alerte précoce envoyée : {_sent_line(early, lang)}

Mise à jour de l'alerte précoce : {v(incident.get('description'))}
Évaluation initiale — gravité et impact : {v(incident.get('likely_consequences'))}
Indicateurs de compromission : [à compléter]
Mesures prises : {v(incident.get('measures_taken'))}""",
            NIS2_INTERMEDIATE: f"""Rapport intermédiaire (NIS2, art. 23(4)(c)) — à la demande du CSIRT

Entité : {org}
Notification d'incident envoyée : {_sent_line(notif, lang)}

Mises à jour pertinentes de la situation : {v(incident.get('description'))}
Gravité et impact à ce jour : {v(incident.get('likely_consequences'))}
Mesures prises depuis la notification : {v(incident.get('measures_taken'))}""",
            NIS2_PROGRESS: f"""Rapport d'avancement (NIS2, art. 23(4)(e)) — incident toujours en cours de traitement

Entité : {org}
Notification d'incident envoyée : {_sent_line(notif, lang)}

État du traitement de l'incident : {v(incident.get('description'))}
Gravité et impact à ce jour : {v(incident.get('likely_consequences'))}
Mesures d'atténuation appliquées et en cours : {v(incident.get('measures_taken'))}
Le rapport final suivra dans un délai d'un mois après la fin du traitement de l'incident.""",
            NIS2_FINAL: f"""Rapport final (NIS2, art. 23(4)(d))

Entité : {org}
Notification d'incident envoyée : {_sent_line(notif, lang)}

Description détaillée de l'incident, de sa gravité et de son impact :
{v(incident.get('description'))}
{v(incident.get('likely_consequences'))}

Cause racine ou type de menace : {v(incident.get('root_cause'))}
Mesures d'atténuation appliquées et en cours : {v(incident.get('measures_taken'))}
Enseignements et changements : {v(incident.get('lessons'))}
Impact transfrontière : [à compléter]""",
            NIS2_RECIPIENTS: f"""Objet : incident affectant nos services

Madame, Monsieur,

{org} a constaté le {found} un incident important susceptible d'affecter la fourniture de nos services : {v(incident.get('description'))}

Impact possible pour vous : {v(incident.get('likely_consequences'))}
Mesures que nous avons prises : {v(incident.get('measures_taken'))}
Mesures que vous pouvez prendre : [à compléter]

Pour toute question : {v(client.get('contact_email'))}""",
        }
        late_txt = "\n\nMotifs du retard (art. 33(1)) : [à compléter]"
        fu_head = "Informations complémentaires — suite à notre notification du {d}\n\n"
    else:
        T = {
            GDPR_AUTHORITY: f"""Personal data breach notification (GDPR Art. 33)

Controller: {org}
Date and time the breach became known: {found}
Systems affected: {sys_list}

(a) Nature of the breach
{v(incident.get('description'))}
Categories of data subjects: {v(incident.get('subject_categories'))}
Approximate number of data subjects: {v(subjects)}
Categories of records concerned: {v(incident.get('data_categories'))}
Approximate number of records: {v(records)}

(b) Contact point
{v(dpo)}

(c) Likely consequences
{v(incident.get('likely_consequences'))}

(d) Measures taken or proposed
{v(incident.get('measures_taken'))}

Information not yet known will be provided in phases as it becomes available (Art. 33(4)).""",
            DATA_SUBJECTS: (f"""Public communication — security incident (GDPR Art. 34(3)(c))

On {found}, {org} discovered a security incident: {v(incident.get('description'))}

Data concerned: {v(incident.get('data_categories'))}
Possible consequences: {v(incident.get('likely_consequences'))}
What we have done: {v(incident.get('measures_taken'))}
What we recommend people affected do: [to complete]

Contact: {v(dpo)}""" if public else f"""Subject: a security incident affecting your data

Dear Sir or Madam,

On {found}, {org} discovered the following incident: {v(incident.get('description'))}

Data concerned: {v(incident.get('data_categories'))}
What this may mean for you: {v(incident.get('likely_consequences'))}
What we have done: {v(incident.get('measures_taken'))}

What we recommend you do: [to complete — for example change your password, watch for suspicious messages]

If you have questions: {v(dpo)}"""),
            CONTROLLERS: f"""Subject: notification of a personal data breach (GDPR Art. 33(2))

For the attention of {v(controller)},

As your processor, {org} is notifying you of a personal data breach that may affect the processing we carry out on your behalf.

Became known: {found}
Systems affected: {sys_list}
Nature: {v(incident.get('description'))}
Categories of data subjects / data: {v(incident.get('subject_categories'))} / {v(incident.get('data_categories'))}
Data subjects / records affected (approx.): {v(subjects)} / {v(records)}
Likely consequences: {v(incident.get('likely_consequences'))}
Measures taken: {v(incident.get('measures_taken'))}
Contact: {v(dpo)}

We will send further information as soon as it is available.""",
            NIS2_EARLY: f"""Early warning — significant incident (NIS2 Art. 23(4)(a))

Entity: {org}
Became aware: {found}
Systems affected: {sys_list}
Description: {v(incident.get('description'))}

Suspected to be caused by unlawful or malicious acts? [to complete]
Possible cross-border impact? [to complete]
Assistance requested: [to complete]""",
            NIS2_NOTIFICATION: f"""Incident notification (NIS2 Art. 23(4)(b))

Entity: {org}
Became aware: {found}
Early warning sent: {_sent_line(early, lang)}

Update to the early warning: {v(incident.get('description'))}
Initial assessment — severity and impact: {v(incident.get('likely_consequences'))}
Indicators of compromise: [to complete]
Measures taken: {v(incident.get('measures_taken'))}""",
            NIS2_INTERMEDIATE: f"""Intermediate report (NIS2 Art. 23(4)(c)) — at the CSIRT's request

Entity: {org}
Incident notification sent: {_sent_line(notif, lang)}

Relevant status updates: {v(incident.get('description'))}
Severity and impact so far: {v(incident.get('likely_consequences'))}
Measures taken since the notification: {v(incident.get('measures_taken'))}""",
            NIS2_PROGRESS: f"""Progress report (NIS2 Art. 23(4)(e)) — incident still being handled

Entity: {org}
Incident notification sent: {_sent_line(notif, lang)}

Where the handling stands: {v(incident.get('description'))}
Severity and impact so far: {v(incident.get('likely_consequences'))}
Mitigation measures applied and ongoing: {v(incident.get('measures_taken'))}
The final report will follow within one month of the incident being handled.""",
            NIS2_FINAL: f"""Final report (NIS2 Art. 23(4)(d))

Entity: {org}
Incident notification sent: {_sent_line(notif, lang)}

Detailed description of the incident, its severity and impact:
{v(incident.get('description'))}
{v(incident.get('likely_consequences'))}

Root cause or type of threat: {v(incident.get('root_cause'))}
Mitigation measures applied and ongoing: {v(incident.get('measures_taken'))}
Lessons learned and changes made: {v(incident.get('lessons'))}
Cross-border impact: [to complete]""",
            NIS2_RECIPIENTS: f"""Subject: an incident affecting our services

Dear Sir or Madam,

On {found}, {org} discovered a significant incident that may affect the services we provide to you: {v(incident.get('description'))}

Possible impact for you: {v(incident.get('likely_consequences'))}
What we have done: {v(incident.get('measures_taken'))}
What you can do: [to complete]

If you have questions: {v(client.get('contact_email'))}""",
        }
        late_txt = "\n\nReasons for the delay (Art. 33(1)): [to complete]"
        fu_head = "Supplementary information — further to our notification of {d}\n\n"

    if kind.startswith(CONTACT_PREFIX):
        text = (f"Incident chez {org}, constaté le {found} : {v(incident.get('description'))}\n"
                f"Systèmes concernés : {sys_list}\nMesures prises : {v(incident.get('measures_taken'))}"
                if fr else
                f"Incident at {org}, discovered {found}: {v(incident.get('description'))}\n"
                f"Systems affected: {sys_list}\nMeasures taken: {v(incident.get('measures_taken'))}")
    else:
        text = T[kind]
    if late and kind == GDPR_AUTHORITY:
        text += late_txt
    if followup:
        text = fu_head.format(d=_sent_line(sent(events, kind), lang)) + text
    return text


# ── Processor chain (Art. 33(2)) ─────────────────────────────────────────

def affected_controllers(system_ids: Iterable[str], activities: Iterable[Mapping[str, Any]],
                         activity_systems: Iterable[Mapping[str, Any]],
                         activity_counterparties: Iterable[Mapping[str, Any]],
                         counterparties: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Controllers to notify: the counterparties of every processing activity
    the client performs AS A PROCESSOR on one of the affected systems."""
    sys_ids = set(system_ids)
    proc_acts = {a["id"] for a in activities if a.get("controller_role") == "processor"}
    acts = {l["activity_id"] for l in activity_systems
            if l.get("system_id") in sys_ids and l.get("activity_id") in proc_acts}
    cp_ids = {l["counterparty_id"] for l in activity_counterparties if l.get("activity_id") in acts}
    return sorted((c for c in counterparties if c["id"] in cp_ids),
                  key=lambda c: (c.get("legal_name") or "").lower())


# ── Action plan (tasks.py producer) ──────────────────────────────────────

def findings(incidents: Iterable[Mapping[str, Any]], client: Mapping[str, Any],
             events_by_incident: Mapping[str, list], processor_by_incident: Mapping[str, bool],
             now: datetime | None = None, contacts: Iterable[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """One task per open deadline of every incident not yet closed."""
    from tasks import _finding, DUE, OPEN
    contacts = list(contacts)
    by_id = {c["id"]: c for c in contacts}
    out = []
    for inc in incidents:
        if inc.get("status") == "closed":
            continue
        dls = deadlines(inc, client, events_by_incident.get(inc["id"], []),
                        processor_by_incident.get(inc["id"], False), now, contacts)
        for d in dls:
            if d["state"] not in OPEN_STATES:
                continue
            f = _finding(
                "incident", f"{inc['id']}:{d['kind']}",
                f"{label(d['kind'], 'en', by_id)} — {inc['title']}",
                DUE if d["state"] in (OVERDUE, DUE_SOON) else OPEN,
                describe_left(d), d["due"].date() if d["due"] else None,
                link="incidents",
            )
            # For Home (usability audit H10): a deadline whose regime is not
            # decided yet reads as "assess first", not as one more emergency.
            f.update(incident_title=inc["title"], incident_id=inc["id"],
                     deadline_state=d["state"], deadline_label=label(d["kind"], "en", by_id),
                     due_at=d["due"])
            out.append(f)
    return out
