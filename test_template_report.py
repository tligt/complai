"""
test_template_report.py — S63 (D-162)

Run: python test_template_report.py [--show]

What would fail silently: an event outside the period counted in it, a
superseded document missed, a late notification not counted, statuses shown
when none were passed, and an unfilled field in either language.
"""

import sys
from datetime import date, datetime, timezone

import template_report as TR
import template_seed_report as SEED
import template_store as TS
from template_renderer import render_template

failures = []


def check(name, cond, detail=""):
    if not cond:
        failures.append(f"{name} {detail}")


START, END, TODAY = date(2025, 11, 11), date(2026, 11, 10), date(2026, 11, 10)
check("default period", TR.default_period(TODAY) == (START, END), str(TR.default_period(TODAY)))

docs = [
    {"document_type": "privacy_policy", "language": "fr", "adopted_at": "2026-03-01T10:00:00Z",
     "superseded_on": "2026-09-01"},
    {"document_type": "dpa", "language": "en", "adopted_at": "2024-01-01T10:00:00Z"},   # before
    {"document_type": "ropa_controller", "language": "fr", "adopted_at": None},
]
ev = TR.document_events(docs + [dict(docs[0]), dict(docs[0])], START, END)
check("document events", [(e["doc_type"], e["event"]) for e in ev] ==
      [("privacy_policy", "adopted"), ("privacy_policy", "superseded")], str(ev))

found = datetime(2026, 5, 1, 9, tzinfo=timezone.utc)
inc = {"id": "i1", "title": "Phishing", "discovered_at": found.isoformat(), "status": "closed",
       "personal_data": True, "gdpr_risk": "risk", "significant": None}
old = {**inc, "id": "i0", "discovered_at": "2024-02-01T00:00:00+00:00"}
events = {"i1": [{"event_type": "notification", "kind": "gdpr_authority",
                  "occurred_at": datetime(2026, 5, 5, 9, tzinfo=timezone.utc).isoformat()}]}
rows = TR.incident_rows([inc, old], events, START, END, {"regulations": ["GDPR"]})
check("incident in period only", [r["title"] for r in rows] == ["Phishing"])
check("late notification counted", rows and rows[0]["sent"] == 1 and rows[0]["late"] == 1, str(rows))

tev = [{"event": "opened", "created_at": "2026-01-02T00:00:00Z"},
       {"event": "closed", "created_at": "2026-02-02T00:00:00Z"},
       {"event": "opened", "created_at": "2024-02-02T00:00:00Z"}]
tc = TR.task_counts(tev, [{"severity": "due"}, {"severity": "open"}], START, END)
check("tasks", tc == {"opened": 1, "closed": 1, "open": 2, "urgent": 1}, str(tc))

client = {"legal_name": "Test SA", "legal_form": "SA", "regulations": ["GDPR", "EU_AI_ACT"]}
from obligations import OBLIGATIONS
applicable = [o for o in OBLIGATIONS if o["regulation"] in client["regulations"]]
verdicts = {o["id"]: {"status": "compliant", "source": "derived"} for o in applicable}
verdicts[applicable[0]["id"]] = {"status": "missing", "source": "none"}

for with_verdicts in (True, False):
    ctx = TR.build_report_context_from(
        client=client, start=START, end=END, today=TODAY,
        verdicts=verdicts if with_verdicts else None, applicable=applicable if with_verdicts else None,
        open_tasks=[{"severity": "due"}], docs=docs, incidents=[inc], incident_events=events,
        task_events=tev, regulatory=[{"title": "EDPB guidelines", "regulations": ["GDPR"],
                                      "notified_at": "2026-06-01T00:00:00Z"}])
    doc, _ = SEED.DOCS["report"]
    for lang, body in doc.bodies.items():
        values = {"legal_name": "Test SA", "legal_form": "SA",
                  "generation_date": TS.format_date(TODAY, lang)}
        TR.apply_report_values(values, client, ctx, lang)
        res = render_template(body, values=values, specs=TS.FIELD_SPECS["annual_report"], language=lang,
                              block_renderers=TS.DEFAULT_BLOCK_RENDERERS, block_context=ctx)
        tag = f"[{lang}/{'verdicts' if with_verdicts else 'none'}]"
        md = res.body or ""
        check(f"{tag} not blocked", not res.blocked and not res.unknown_tags, f"{res.missing_required}")
        check(f"{tag} no placeholder", "{{" not in md and "TO COMPLETE" not in md and "COMPLÉTER" not in md)
        check(f"{tag} incident listed", "Phishing" in md)
        check(f"{tag} regulatory listed", "EDPB guidelines" in md)
        check(f"{tag} gap listed or not available",
              (__import__("i18n").translate(dict(applicable[0])["title"], lang) in md) if with_verdicts else
              ("not available" in md or "pas disponibles" in md))
        if with_verdicts and lang == "en" and "--show" in sys.argv:
            print(md)

if failures:
    print("FAILED:")
    for f in failures:
        print("  " + f[:300])
    sys.exit(1)
print("All annual report tests passed.")
