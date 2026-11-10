"""
template_report.py — S63 (D-162). The annual compliance report ("bilan").

For management, not the auditor: S27's register lists documents; this says
what happened over a period and where the company stands, so the management
body can show it was informed (NIS2 Art. 20; GDPR Art. 5(2) accountability).

TWO KINDS OF CONTENT, SAID AS SUCH
----------------------------------
    as at the generation date   obligation statuses and the score, open
                                tasks, training coverage, the AI inventory
    during the period           documents adopted or replaced, incidents,
                                training sessions, tasks opened and closed,
                                regulatory changes notified

RECOSA keeps no history of obligation statuses, so a status "at the start of
the period" cannot be shown honestly; the report states the date its
statuses are from rather than implying a trend.

Tier 1. Everything is data; no prose is drafted. The obligation verdicts are
computed by the Obligations page's own code (obligation_view.load_state) and
passed in, so the report and the page cannot disagree.

NO STREAMLIT. Reads the database only in build_report_block_context.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Mapping

from template_renderer import Block, FieldSpec

REPORT_FIELDS = [
    FieldSpec("legal_name", "Legal name of the company", required=True),
    FieldSpec("legal_form", "Legal form"),
    FieldSpec("has_legal_form", "Legal form recorded", flag=True),
    FieldSpec("period_start", "Start of the period", required=True),
    FieldSpec("period_end", "End of the period", required=True),
    FieldSpec("generation_date", "Date generated", required=True),
    FieldSpec("tasks_opened", "Tasks opened in the period"),
    FieldSpec("tasks_closed", "Tasks closed in the period"),
    FieldSpec("tasks_open", "Tasks open now"),
    FieldSpec("tasks_urgent", "Tasks overdue or blocking now"),
    FieldSpec("has_verdicts", "Obligation statuses available", flag=True),
    FieldSpec("has_ai", "Subject to the AI Act", flag=True),
]
REPORT_BLOCKS = ("report_scores", "report_gaps", "report_documents", "report_incidents",
                 "report_training", "report_training_cov", "report_ai", "report_regulatory")

_REG = {"GDPR": "GDPR", "NIS2": "NIS2", "EU_AI_ACT": "AI Act", "EPRIVACY": "ePrivacy"}
_T = {
    "en": {
        "reg": "Regulation", "pct": "In place", "detail": "Detail",
        "detail_fmt": "{i} in place, {p} partly, of {a} — {d} on your own statement",
        "na": "No obligation in force",
        "ob": "Obligation", "status": "Status",
        "st": {"partial": "Partly in place", "missing": "Not in place", "unknown": "Nothing recorded"},
        "no_gaps": "Every obligation in force is in place or not applicable.",
        "no_verdicts": "Statuses were not available when this report was generated.",
        "doc": "Document", "lang": "Language", "event": "What happened", "date": "Date",
        "adopted": "Put in force", "superseded": "Replaced", "no_docs": "No document was put in force or replaced in the period.",
        "found": "Discovered", "incident": "Incident", "notif": "Notifications",
        "notif_fmt": "{n} sent", "late_fmt": "{n} sent, {l} late", "no_inc": "No incident was recorded in the period.",
        "inc_st": {"open": "Open", "contained": "Contained", "closed": "Closed"},
        "held": "Held on", "session": "Session", "covers": "Counts for", "att": "Attendees",
        "no_train": "No training session was recorded in the period.",
        "train": "Training", "current": "Current now", "cur_fmt": "{c} of {r}", "nobody": "Nobody recorded needs it", "no_req": "No training requirement applies.",
        "risk": "Risk class", "uses": "Uses", "no_ai": "No AI use is recorded.",
        "change": "Regulatory change", "regs": "Concerns", "no_reg": "No regulatory change was notified in the period.",
    },
    "fr": {
        "reg": "Réglementation", "pct": "En place", "detail": "Détail",
        "detail_fmt": "{i} en place, {p} en partie, sur {a} — dont {d} sur votre seule déclaration",
        "na": "Aucune obligation en vigueur",
        "ob": "Obligation", "status": "Statut",
        "st": {"partial": "En partie en place", "missing": "Pas en place", "unknown": "Rien d'enregistré"},
        "no_gaps": "Toutes les obligations en vigueur sont en place ou sans objet.",
        "no_verdicts": "Les statuts n'étaient pas disponibles lors de la génération de ce rapport.",
        "doc": "Document", "lang": "Langue", "event": "Événement", "date": "Date",
        "adopted": "Mis en vigueur", "superseded": "Remplacé", "no_docs": "Aucun document n'a été mis en vigueur ni remplacé sur la période.",
        "found": "Découvert le", "incident": "Incident", "notif": "Notifications",
        "notif_fmt": "{n} envoyée(s)", "late_fmt": "{n} envoyée(s), dont {l} en retard", "no_inc": "Aucun incident n'a été enregistré sur la période.",
        "inc_st": {"open": "Ouvert", "contained": "Maîtrisé", "closed": "Clos"},
        "held": "Date", "session": "Session", "covers": "Compte pour", "att": "Participants",
        "no_train": "Aucune session de formation n'a été enregistrée sur la période.",
        "train": "Formation", "current": "À jour à ce jour", "cur_fmt": "{c} sur {r}", "nobody": "Personne d'enregistré n'en a besoin", "no_req": "Aucune exigence de formation ne s'applique.",
        "risk": "Classe de risque", "uses": "Usages", "no_ai": "Aucun usage de l'IA n'est enregistré.",
        "change": "Évolution réglementaire", "regs": "Concerne", "no_reg": "Aucune évolution réglementaire n'a été notifiée sur la période.",
    },
}


_T["nl"] = {
    "reg": "Regelgeving", "pct": "Op orde", "detail": "Detail",
    "detail_fmt": "{i} op orde, {p} gedeeltelijk, van {a} — waarvan {d} alleen op eigen verklaring",
    "na": "Geen verplichting van kracht",
    "ob": "Verplichting", "status": "Status",
    "st": {"partial": "Gedeeltelijk op orde", "missing": "Niet op orde", "unknown": "Niets geregistreerd"},
    "no_gaps": "Elke verplichting die van kracht is, is op orde of niet van toepassing.",
    "no_verdicts": "De statussen waren niet beschikbaar toen dit verslag werd opgemaakt.",
    "doc": "Document", "lang": "Taal", "event": "Wat er gebeurde", "date": "Datum",
    "adopted": "In werking gesteld", "superseded": "Vervangen",
    "no_docs": "In de periode werd geen document in werking gesteld of vervangen.",
    "found": "Ontdekt op", "incident": "Incident", "notif": "Meldingen",
    "notif_fmt": "{n} verstuurd", "late_fmt": "{n} verstuurd, waarvan {l} te laat",
    "no_inc": "In de periode werd geen incident geregistreerd.",
    "inc_st": {"open": "Open", "contained": "Ingeperkt", "closed": "Afgesloten"},
    "held": "Datum", "session": "Sessie", "covers": "Telt voor", "att": "Deelnemers",
    "no_train": "In de periode werd geen opleidingssessie geregistreerd.",
    "train": "Opleiding", "current": "Nu geldig", "cur_fmt": "{c} van {r}",
    "nobody": "Niemand die is geregistreerd, heeft ze nodig", "no_req": "Er geldt geen opleidingsvereiste.",
    "risk": "Risicoklasse", "uses": "Toepassingen", "no_ai": "Er is geen gebruik van AI geregistreerd.",
    "change": "Wijziging in de regelgeving", "regs": "Betreft",
    "no_reg": "In de periode werd geen wijziging in de regelgeving gemeld.",
}


def _t(lang: str, key: str):
    return _T.get(lang, _T["en"]).get(key, _T["en"][key])


def _d(v: Any) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _fd(v: Any) -> str:
    d = _d(v)
    return d.strftime("%d/%m/%Y") if d else "—"


def in_period(v: Any, start: date, end: date) -> bool:
    d = _d(v)
    return d is not None and start <= d <= end


def default_period(today: date) -> tuple[date, date]:
    """The twelve months up to today."""
    try:
        start = today.replace(year=today.year - 1) + timedelta(days=1)
    except ValueError:   # 29 Feb
        start = today - timedelta(days=365)
    return start, today


# ── Pure section builders (tested) ────────────────────────────────────────

def document_events(docs: Iterable[Mapping[str, Any]], start: date, end: date) -> list[dict]:
    """One line per document, language, event and day. The register can hold
    several rows for one adoption (re-generations, re-uploads: 28 for one
    policy on one day in a real company, 10 Nov), and management needs the
    event, not the rows."""
    seen: set[tuple] = set()
    out = []
    for r in docs:
        if in_period(r.get("adopted_at"), start, end):
            out.append({"doc_type": r["document_type"], "language": r.get("language"),
                        "event": "adopted", "date": _d(r["adopted_at"])})
        if in_period(r.get("superseded_on"), start, end):
            out.append({"doc_type": r["document_type"], "language": r.get("language"),
                        "event": "superseded", "date": _d(r["superseded_on"])})
    unique = []
    for e in out:
        k = (e["doc_type"], e["language"], e["event"], e["date"])
        if k not in seen:
            seen.add(k)
            unique.append(e)
    return sorted(unique, key=lambda e: (e["date"], e["doc_type"], e["event"]))


def incident_rows(incidents, events_by_incident, start: date, end: date,
                  client: Mapping[str, Any] | None = None) -> list[dict]:
    """Incidents discovered in the period, with how many notifications were
    sent and how many of those after their deadline (the incident clock's own
    rules, incident_rules.deadlines)."""
    import incident_rules as R  # noqa: PLC0415
    out = []
    for inc in incidents:
        if not in_period(inc.get("discovered_at"), start, end):
            continue
        ev = events_by_incident.get(inc["id"], [])
        sent = sum(1 for e in ev if e.get("event_type") == "notification")
        try:
            dls = R.deadlines(inc, client or {}, ev, False)
            late = sum(1 for d in dls if d["state"] == R.DONE and R.is_late(d))
        except Exception:
            late = 0
        out.append({"discovered": _d(inc["discovered_at"]), "title": inc.get("title") or "",
                    "status": inc.get("status") or "open", "sent": sent, "late": late})
    return sorted(out, key=lambda r: r["discovered"])


def task_counts(events: Iterable[Mapping[str, Any]], open_tasks: Iterable[Mapping[str, Any]] | None,
                start: date, end: date) -> dict[str, Any]:
    ev = list(events)
    opened = sum(1 for e in ev if e.get("event") == "opened" and in_period(e.get("created_at"), start, end))
    closed = sum(1 for e in ev if e.get("event") == "closed" and in_period(e.get("created_at"), start, end))
    open_ = list(open_tasks) if open_tasks is not None else None
    return {"opened": opened, "closed": closed,
            "open": len(open_) if open_ is not None else None,
            "urgent": sum(1 for t in open_ if t.get("severity") in ("due", "blocking")) if open_ is not None else None}


# ── Block renderers ───────────────────────────────────────────────────────

def _rows_or(block: Block, rows: list[list[str]], empty: str) -> Block:
    block.rows.extend(rows or [[empty] + [""] * (len(block.headers) - 1)])
    return block


def render_report_scores(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_scores", headers=[_t(lang, "reg"), _t(lang, "pct"), _t(lang, "detail")])
    rows = []
    for reg, s in (ctx.get("scores") or {}).items():
        if s.get("percent") is None:
            rows.append([_REG.get(reg, reg), "—", _t(lang, "na")])
        else:
            rows.append([_REG.get(reg, reg), f"{s['percent']} %",
                         _t(lang, "detail_fmt").format(i=s["in_place"], p=s["partly"], a=s["applicable"],
                                                       d=s["declared"])])
    return _rows_or(b, rows, _t(lang, "no_verdicts"))


def render_report_gaps(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_gaps", headers=[_t(lang, "ob"), _t(lang, "reg"), _t(lang, "status")])
    if ctx.get("verdicts") is None:
        return _rows_or(b, [], _t(lang, "no_verdicts"))
    st = _t(lang, "st")
    rows = [[o["title"], _REG.get(o["regulation"], o["regulation"]), st[ctx["verdicts"][o["id"]]["status"]]]
            for o in ctx.get("gaps") or []]
    return _rows_or(b, rows, _t(lang, "no_gaps"))


def render_report_documents(ctx, language):
    lang = language if language in _T else "en"
    from obligations import document_label  # noqa: PLC0415
    b = Block(name="report_documents", headers=[_t(lang, "doc"), _t(lang, "lang"), _t(lang, "event"), _t(lang, "date")])
    rows = [[document_label(e["doc_type"]), (e.get("language") or "").upper(), _t(lang, e["event"]), _fd(e["date"])]
            for e in ctx.get("document_events") or []]
    return _rows_or(b, rows, _t(lang, "no_docs"))


def render_report_incidents(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_incidents", headers=[_t(lang, "found"), _t(lang, "incident"), _t(lang, "status"), _t(lang, "notif")])
    ist = _t(lang, "inc_st")
    rows = [[_fd(r["discovered"]), r["title"], ist.get(r["status"], r["status"]),
             (_t(lang, "late_fmt").format(n=r["sent"], l=r["late"]) if r["late"]
              else _t(lang, "notif_fmt").format(n=r["sent"]))]
            for r in ctx.get("incidents") or []]
    return _rows_or(b, rows, _t(lang, "no_inc"))


def render_report_training(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_training", headers=[_t(lang, "held"), _t(lang, "session"), _t(lang, "covers"), _t(lang, "att")])
    labels = ctx.get("training_labels") or {}
    rows = [[_fd(s["held_on"]), s.get("title") or "",
             ", ".join(labels.get(c, {}).get(lang) or labels.get(c, {}).get("en") or c
                       for c in s.get("requirement_codes") or []),
             str(s.get("attendees", 0))]
            for s in ctx.get("training_sessions") or []]
    return _rows_or(b, rows, _t(lang, "no_train"))


def render_report_training_cov(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_training_cov", headers=[_t(lang, "train"), _t(lang, "current")])
    rows = [[r["label"].get(lang) or r["label"]["en"],
             _t(lang, "cur_fmt").format(c=r["ok"], r=r["required"]) if r["required"] else _t(lang, "nobody")]
            for r in ctx.get("training_coverage") or []]
    return _rows_or(b, rows, _t(lang, "no_req"))


def render_report_ai(ctx, language):
    lang = language if language in _T else "en"
    from template_ai import _RISK  # noqa: PLC0415
    b = Block(name="report_ai", headers=[_t(lang, "risk"), _t(lang, "uses")])
    rows = [[_RISK.get(lang, _RISK["en"])[k], str(n)] for k, n in (ctx.get("ai_counts") or {}).items() if n]
    return _rows_or(b, rows, _t(lang, "no_ai"))


def render_report_regulatory(ctx, language):
    lang = language if language in _T else "en"
    b = Block(name="report_regulatory", headers=[_t(lang, "date"), _t(lang, "change"), _t(lang, "regs")])
    rows = [[_fd(u.get("notified_at")), u.get("title") or "",
             ", ".join(_REG.get(r, r) for r in (u.get("regulations") or []))]
            for u in ctx.get("regulatory") or []]
    return _rows_or(b, rows, _t(lang, "no_reg"))


REPORT_BLOCK_RENDERERS = {
    "report_scores": render_report_scores,
    "report_gaps": render_report_gaps,
    "report_documents": render_report_documents,
    "report_incidents": render_report_incidents,
    "report_training": render_report_training,
    "report_training_cov": render_report_training_cov,
    "report_ai": render_report_ai,
    "report_regulatory": render_report_regulatory,
}


# ── Context ───────────────────────────────────────────────────────────────

def build_report_context_from(*, client, start, end, verdicts=None, applicable=None, open_tasks=None,
                              docs=(), incidents=(), incident_events=None, task_events=(),
                              training=None, ai=None, regulatory=(), today=None) -> dict[str, Any]:
    """The pure half of build_report_block_context, for tests."""
    import ai_rules as AR  # noqa: PLC0415
    import training_rules as TR  # noqa: PLC0415
    import obligation_register as OR  # noqa: PLC0415
    from obligations import split_by_force  # noqa: PLC0415
    today = today or date.today()
    regs = client.get("regulations") or ["GDPR"]

    scores, gaps = {}, []
    if verdicts is not None and applicable is not None:
        live, _ = split_by_force(applicable)
        scores = {reg: OR.score(verdicts, [o for o in live if o.get("regulation") == reg]) for reg in regs}
        order = {"missing": 0, "unknown": 1, "partial": 2}
        gaps = sorted([o for o in live if verdicts.get(o["id"], {}).get("status") in order],
                      key=lambda o: (regs.index(o["regulation"]) if o["regulation"] in regs else 9,
                                     order[verdicts[o["id"]]["status"]]))

    tr = training or {"requirements": [], "employees": [], "sessions": [], "attendance": []}
    reqs = [r for r in TR.applicable(tr["requirements"], client) if TR.in_force(r, today)]
    att_n: dict[str, int] = {}
    for a in tr["attendance"]:
        att_n[a["session_id"]] = att_n.get(a["session_id"], 0) + 1
    sessions = sorted([{**s, "attendees": att_n.get(s["id"], 0)} for s in tr["sessions"]
                       if in_period(s.get("held_on"), start, end)], key=lambda s: s["held_on"])
    active = [e for e in tr["employees"] if TR.is_active(e, today)]
    cov = TR.coverage(TR.matrix(active, reqs, tr["sessions"], tr["attendance"], today), reqs) if reqs else {}
    coverage = [{"label": {"en": r["label_en"], "fr": r["label_fr"], "nl": r.get("label_nl") or r["label_en"]},
                 "required": cov[r["code"]]["required"],
                 "ok": cov[r["code"]][TR.CURRENT] + cov[r["code"]][TR.EXPIRING]} for r in reqs]
    labels = {r["code"]: {"en": r["label_en"], "fr": r["label_fr"], "nl": r.get("label_nl") or r["label_en"]}
              for r in tr["requirements"]}

    ai_counts = {k: 0 for k in (AR.PROHIBITED, AR.HIGH, AR.LIMITED, AR.MINIMAL, AR.UNKNOWN)}
    for u in (ai or {}).get("use_cases") or []:
        if AR.active(u):
            ai_counts[AR.classify(u)["risk"]] += 1

    tc = task_counts(task_events, open_tasks, start, end)
    return {
        "start": start, "end": end, "verdicts": verdicts, "scores": scores, "gaps": gaps,
        "document_events": document_events(docs, start, end),
        "incidents": incident_rows(incidents, incident_events or {}, start, end, client),
        "training_sessions": sessions, "training_coverage": coverage, "training_labels": labels,
        "ai_counts": ai_counts, "tasks": tc,
        "regulatory": sorted([u for u in regulatory if in_period(u.get("notified_at"), start, end)],
                             key=lambda u: u["notified_at"]),
    }


def build_report_block_context(client_id: str, language: str, **options: Any) -> tuple[dict[str, Any], str | None]:
    from template_store import _get_client, load_client  # noqa: PLC0415
    import training_rules as TR  # noqa: PLC0415
    sb = _get_client()
    client = load_client(client_id) or {}
    start, end = options.get("period_start"), options.get("period_end")
    if not (start and end):
        start, end = default_period(date.today())

    def rows(table, **eq):
        q = sb.table(table).select("*")
        for k, v in eq.items():
            q = q.eq(k, v)
        return q.execute().data or []

    try:
        incidents = rows("incidents", client_id=client_id)
        ev: dict[str, list] = {}
        for e in rows("incident_events", client_id=client_id):
            ev.setdefault(e["incident_id"], []).append(e)
        reqs = [TR.requirement(r) for r in (sb.table("reference_values").select("*")
                .eq("value_type", "training_requirement").is_("workspace_id", "null").execute().data or [])]
        alerts = rows("client_alerts", client_id=client_id)
        upd_ids = [a["update_id"] for a in alerts if a.get("update_id")]
        updates = {u["id"]: u for u in (sb.table("regulatory_updates").select("id, title, regulations")
                   .in_("id", upd_ids).execute().data or [])} if upd_ids else {}
        regulatory = [{**updates[a["update_id"]], "notified_at": a.get("notified_at")}
                      for a in alerts if a.get("update_id") in updates]
        ctx = build_report_context_from(
            client=client, start=start, end=end,
            verdicts=options.get("verdicts"), applicable=options.get("applicable"),
            open_tasks=options.get("open_tasks"),
            docs=rows("client_documents", client_id=client_id),
            incidents=incidents, incident_events=ev,
            task_events=rows("task_events", client_id=client_id),
            training={"requirements": reqs, "employees": rows("employees", client_id=client_id),
                      "sessions": rows("training_sessions", client_id=client_id),
                      "attendance": rows("training_attendance", client_id=client_id)},
            ai={"use_cases": rows("ai_use_cases", client_id=client_id)},
            regulatory=regulatory)
    except Exception as e:
        return {}, f"Could not read the company's records: {e}"
    return ctx, None


def apply_report_values(values: dict[str, Any], client: Mapping[str, Any],
                        block_context: Mapping[str, Any] | None, language: str) -> None:
    from template_store import format_date  # noqa: PLC0415
    ctx = block_context or {}
    regs = client.get("regulations") or ["GDPR"]
    values["has_legal_form"] = bool((client.get("legal_form") or "").strip())
    if ctx.get("start"):
        values["period_start"] = format_date(ctx["start"], language)
        values["period_end"] = format_date(ctx["end"], language)
    tc = ctx.get("tasks") or {}
    values["tasks_opened"] = str(tc.get("opened", 0))
    values["tasks_closed"] = str(tc.get("closed", 0))
    values["tasks_open"] = "—" if tc.get("open") is None else str(tc["open"])
    values["tasks_urgent"] = "—" if tc.get("urgent") is None else str(tc["urgent"])
    values["has_verdicts"] = ctx.get("verdicts") is not None
    values["has_ai"] = "EU_AI_ACT" in regs
