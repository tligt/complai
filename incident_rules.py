"""
incident_rules.py — S53. What an incident requires, and by when.

NO STREAMLIT. NO SUPABASE. NO I/O. (D-61) The page, the action plan and the
hourly reminder job all read the same answers from here.

TWO REGIMES (the S29A procedure, D-80/D-83)
-------------------------------------------
    GDPR Art. 33   personal data breach  → supervisory authority, 72 h
    GDPR Art. 34   high risk to people   → the people, without undue delay
    GDPR Art. 33(2) the client is a processor → each controller, without
                   undue delay
    NIS2 Art. 23   significant incident (client in scope)
                   → CSIRT: early warning 24 h, notification 72 h,
                     final report one month AFTER THE NOTIFICATION

The final report's clock runs from the 72-hour notification, not from
discovery — CCB's own wording, checked 22 Oct 2026. Until the notification
is recorded the final report has no date, and saying so is more honest than
inventing one.

An unanswered question (None) is not a "no". A clock whose regime is not yet
decided is shown as "to decide", and the deadline still counts from
discovery: deciding late does not move it.

DRAFTS, NOT SUBMISSIONS
-----------------------
The texts are what to paste into the authority's own portal. Templates, no
LLM (D-117): a notification is a legal statement the client makes. Placeholders
are left visible ([to complete]) rather than guessed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

# ── Deadlines ─────────────────────────────────────────────────────────────

GDPR_AUTHORITY   = "gdpr_authority"
DATA_SUBJECTS    = "data_subjects"
CONTROLLERS      = "controllers"
NIS2_EARLY       = "nis2_early_warning"
NIS2_NOTIFICATION = "nis2_notification"
NIS2_FINAL       = "nis2_final"

KINDS = [NIS2_EARLY, GDPR_AUTHORITY, NIS2_NOTIFICATION, CONTROLLERS,
         DATA_SUBJECTS, NIS2_FINAL]

LABELS = {
    "en": {
        GDPR_AUTHORITY: "Notify the data protection authority (GDPR Art. 33)",
        DATA_SUBJECTS: "Tell the people affected (GDPR Art. 34)",
        CONTROLLERS: "Notify your clients as controllers (GDPR Art. 33(2))",
        NIS2_EARLY: "NIS2 early warning to the CSIRT",
        NIS2_NOTIFICATION: "NIS2 incident notification to the CSIRT",
        NIS2_FINAL: "NIS2 final report to the CSIRT",
    },
    "fr": {
        GDPR_AUTHORITY: "Notifier l'autorité de protection des données (RGPD art. 33)",
        DATA_SUBJECTS: "Informer les personnes concernées (RGPD art. 34)",
        CONTROLLERS: "Notifier vos clients responsables du traitement (RGPD art. 33(2))",
        NIS2_EARLY: "Alerte précoce NIS2 au CSIRT",
        NIS2_NOTIFICATION: "Notification d'incident NIS2 au CSIRT",
        NIS2_FINAL: "Rapport final NIS2 au CSIRT",
    },
}

# Clock states, worst first.
OVERDUE  = "overdue"
DUE_SOON = "due_soon"     # under DUE_SOON_HOURS left
RUNNING  = "running"
TO_DECIDE = "to_decide"   # the regime is not decided yet; the clock still runs
DONE     = "done"
NOT_REQUIRED = "not_required"

DUE_SOON_HOURS = 6

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


def _ts(v: Any) -> datetime | None:
    if v is None or isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def _add_month(d: datetime) -> datetime:
    """Same day next month, clamped to the month's end (31 Jan → 28/29 Feb)."""
    import calendar
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


def deadlines(incident: Mapping[str, Any], client: Mapping[str, Any],
              events: Iterable[Mapping[str, Any]], is_processor: bool,
              now: datetime | None = None) -> list[dict[str, Any]]:
    """Every deadline this incident has, or may have, worst state first.

    Each: {kind, required (True/False/None = to decide), due (datetime or
    None for "without undue delay" / not yet dated), done_at, state,
    hours_left}.
    """
    now = now or datetime.now(timezone.utc)
    events = list(events)
    found = _ts(incident["discovered_at"])
    pd = incident.get("personal_data")
    sig = incident.get("significant")
    nis2 = nis2_applies(client)

    def req(answer: bool | None, applies: bool = True) -> bool | None:
        if not applies:
            return False
        return answer  # True / False / None (to decide)

    notif = sent(events, NIS2_NOTIFICATION)
    specs = [
        (GDPR_AUTHORITY, req(pd), found + timedelta(hours=72)),
        (DATA_SUBJECTS, None if pd is None else (pd and incident.get("high_risk")), None),
        (CONTROLLERS, req(pd, is_processor), None),
        (NIS2_EARLY, req(sig, nis2), found + timedelta(hours=24)),
        (NIS2_NOTIFICATION, req(sig, nis2), found + timedelta(hours=72)),
        (NIS2_FINAL, req(sig, nis2), _add_month(_ts(notif["occurred_at"])) if notif else None),
    ]

    out = []
    for kind, required, due in specs:
        done = sent(events, kind)
        done_at = _ts(done["occurred_at"]) if done else None
        hours_left = (due - now).total_seconds() / 3600 if due else None
        if done_at:
            state = DONE
        elif required is False:
            state = NOT_REQUIRED
        elif incident.get("status") == "closed" and required is None:
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
                    "done_at": done_at, "state": state, "hours_left": hours_left})
    return sorted(out, key=lambda d: (_ORDER[d["state"]], d["due"] or datetime.max.replace(tzinfo=timezone.utc)))


def next_deadline(dls: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The most urgent deadline still open, for lists and the dashboard."""
    open_ = [d for d in dls if d["state"] in (OVERDUE, DUE_SOON, TO_DECIDE, RUNNING)]
    return open_[0] if open_ else None


def describe_left(d: Mapping[str, Any], lang: str = "en") -> str:
    """'in 5 h', '3 h overdue', 'without undue delay', 'sent 22 Oct 14:05'."""
    fr = lang == "fr"
    if d["state"] == DONE:
        return (("envoyé le " if fr else "sent ") + d["done_at"].astimezone(DISPLAY_TZ).strftime("%d/%m %H:%M"))
    if d["state"] == NOT_REQUIRED:
        return "non requis" if fr else "not required"
    if d["due"] is None:
        if d["kind"] == NIS2_FINAL:
            return ("un mois après la notification" if fr else "one month after the notification")
        return "sans retard injustifié" if fr else "without undue delay"
    h = d["hours_left"]
    if h < 0:
        h = -h
        span = f"{int(h)} h" if h < 72 else (f"{int(h // 24)} j" if fr else f"{int(h // 24)} days")
        return f"en retard de {span}" if fr else f"{span} overdue"
    span = f"{int(h)} h {int((h % 1) * 60):02d}" if h <= 72 else (f"{int(h // 24)} j" if fr else f"{int(h // 24)} days")
    return f"dans {span}" if fr else f"in {span}"


def reminder_stage(d: Mapping[str, Any]) -> str | None:
    """Which reminder this deadline is due, if any: 'soon' or 'overdue'.
    Only for deadlines with a date and a required-or-undecided regime."""
    if d["state"] == OVERDUE:
        return "overdue"
    if d["state"] == DUE_SOON:
        return "soon"
    return None


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


def _when(dt: Any) -> str:
    d = _ts(dt)
    return d.astimezone(DISPLAY_TZ).strftime("%d/%m/%Y %H:%M") + f" ({TZ_LABEL})" if d else ""


def draft(kind: str, incident: Mapping[str, Any], client: Mapping[str, Any],
          systems: list[str], lang: str = "en",
          events: Iterable[Mapping[str, Any]] = (), controller: str | None = None) -> str:
    """The text for one notification, in English or French."""
    lang = "fr" if lang == "fr" else "en"
    v = lambda x: _v(x, lang)  # noqa: E731
    org = client.get("legal_name") or client.get("company_name") or ""
    found = _when(incident["discovered_at"])
    sys_list = ", ".join(systems) if systems else v(None)
    dpo = (f"{client['dpo_name']} — {client.get('dpo_email') or ''}".strip(" —")
           if client.get("dpo_name") else client.get("contact_email"))
    subjects = incident.get("approx_subjects")
    records = incident.get("approx_records")
    early = sent(events, NIS2_EARLY)
    notif = sent(events, NIS2_NOTIFICATION)

    if lang == "fr":
        T = {
            GDPR_AUTHORITY: f"""Notification de violation de données à caractère personnel (RGPD, art. 33)

Responsable du traitement : {org}
Date et heure de la prise de connaissance : {found}
Systèmes concernés : {sys_list}

a) Nature de la violation
{v(incident.get('description'))}
Catégories de données concernées : {v(incident.get('data_categories'))}
Nombre approximatif de personnes concernées : {v(subjects)}
Nombre approximatif d'enregistrements concernés : {v(records)}

b) Point de contact
{v(dpo)}

c) Conséquences probables
{v(incident.get('likely_consequences'))}

d) Mesures prises ou envisagées
{v(incident.get('measures_taken'))}

Les informations encore inconnues seront communiquées dès que possible (art. 33(4)).""",
            DATA_SUBJECTS: f"""Objet : incident de sécurité concernant vos données

Madame, Monsieur,

Le {found}, {org} a constaté l'incident suivant : {v(incident.get('description'))}

Données concernées : {v(incident.get('data_categories'))}
Conséquences possibles pour vous : {v(incident.get('likely_consequences'))}
Mesures que nous avons prises : {v(incident.get('measures_taken'))}

Ce que nous vous recommandons : [à compléter — par exemple changer votre mot de passe, rester attentif aux messages suspects]

Pour toute question : {v(dpo)}""",
            CONTROLLERS: f"""Objet : notification d'une violation de données (RGPD, art. 33(2))

À l'attention de {v(controller)},

En tant que sous-traitant, {org} vous notifie une violation de données à caractère personnel susceptible de concerner les traitements que nous effectuons pour votre compte.

Prise de connaissance : {found}
Systèmes concernés : {sys_list}
Nature : {v(incident.get('description'))}
Catégories de données : {v(incident.get('data_categories'))}
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
Alerte précoce envoyée : {_when(early['occurred_at']) + (' — réf. ' + early['reference'] if early.get('reference') else '') if early else '[à compléter]'}

Mise à jour de l'alerte précoce : {v(incident.get('description'))}
Évaluation initiale — gravité et impact : {v(incident.get('likely_consequences'))}
Indicateurs de compromission : [à compléter]
Mesures prises : {v(incident.get('measures_taken'))}""",
            NIS2_FINAL: f"""Rapport final (NIS2, art. 23(4)(d))

Entité : {org}
Notification d'incident envoyée : {_when(notif['occurred_at']) + (' — réf. ' + notif['reference'] if notif.get('reference') else '') if notif else '[à compléter]'}

Description détaillée de l'incident, de sa gravité et de son impact :
{v(incident.get('description'))}
{v(incident.get('likely_consequences'))}

Cause racine ou type de menace : {v(incident.get('root_cause'))}
Mesures d'atténuation appliquées et en cours : {v(incident.get('measures_taken'))}
Enseignements et changements : {v(incident.get('lessons'))}
Impact transfrontière : [à compléter]""",
        }
    else:
        T = {
            GDPR_AUTHORITY: f"""Personal data breach notification (GDPR Art. 33)

Controller: {org}
Date and time the breach became known: {found}
Systems affected: {sys_list}

(a) Nature of the breach
{v(incident.get('description'))}
Categories of data concerned: {v(incident.get('data_categories'))}
Approximate number of data subjects: {v(subjects)}
Approximate number of records: {v(records)}

(b) Contact point
{v(dpo)}

(c) Likely consequences
{v(incident.get('likely_consequences'))}

(d) Measures taken or proposed
{v(incident.get('measures_taken'))}

Information not yet known will be provided in phases as it becomes available (Art. 33(4)).""",
            DATA_SUBJECTS: f"""Subject: a security incident affecting your data

Dear Sir or Madam,

On {found}, {org} discovered the following incident: {v(incident.get('description'))}

Data concerned: {v(incident.get('data_categories'))}
What this may mean for you: {v(incident.get('likely_consequences'))}
What we have done: {v(incident.get('measures_taken'))}

What we recommend you do: [to complete — for example change your password, watch for suspicious messages]

If you have questions: {v(dpo)}""",
            CONTROLLERS: f"""Subject: notification of a personal data breach (GDPR Art. 33(2))

For the attention of {v(controller)},

As your processor, {org} is notifying you of a personal data breach that may affect the processing we carry out on your behalf.

Became known: {found}
Systems affected: {sys_list}
Nature: {v(incident.get('description'))}
Categories of data: {v(incident.get('data_categories'))}
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
Early warning sent: {_when(early['occurred_at']) + (' — ref. ' + early['reference'] if early.get('reference') else '') if early else '[to complete]'}

Update to the early warning: {v(incident.get('description'))}
Initial assessment — severity and impact: {v(incident.get('likely_consequences'))}
Indicators of compromise: [to complete]
Measures taken: {v(incident.get('measures_taken'))}""",
            NIS2_FINAL: f"""Final report (NIS2 Art. 23(4)(d))

Entity: {org}
Incident notification sent: {_when(notif['occurred_at']) + (' — ref. ' + notif['reference'] if notif.get('reference') else '') if notif else '[to complete]'}

Detailed description of the incident, its severity and impact:
{v(incident.get('description'))}
{v(incident.get('likely_consequences'))}

Root cause or type of threat: {v(incident.get('root_cause'))}
Mitigation measures applied and ongoing: {v(incident.get('measures_taken'))}
Lessons learned and changes made: {v(incident.get('lessons'))}
Cross-border impact: [to complete]""",
        }
    return T[kind]


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
             now: datetime | None = None) -> list[dict[str, Any]]:
    """One task per open deadline of every incident not yet closed."""
    from tasks import _finding, DUE, OPEN
    out = []
    for inc in incidents:
        if inc.get("status") == "closed":
            continue
        dls = deadlines(inc, client, events_by_incident.get(inc["id"], []),
                        processor_by_incident.get(inc["id"], False), now)
        for d in dls:
            if d["state"] not in (OVERDUE, DUE_SOON, TO_DECIDE, RUNNING):
                continue
            out.append(_finding(
                "incident", f"{inc['id']}:{d['kind']}",
                f"{LABELS['en'][d['kind']]} — {inc['title']}",
                DUE if d["state"] in (OVERDUE, DUE_SOON) else OPEN,
                describe_left(d), d["due"].date() if d["due"] else None,
                link="incidents",
            ))
    return out
