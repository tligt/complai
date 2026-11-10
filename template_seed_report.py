"""
template_seed_report.py — S63 (D-162)

Authors the annual compliance report ("bilan") for management.

Run:  python template_seed_report.py > seed_s63_report.sql
      or: python load_template_docs.py template_seed_report report

NEVER IMPORTED AT RUNTIME.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

---------------------------------------------------------------------------
FOR COUNSEL
---------------------------------------------------------------------------
1. Section 7 asks the management body to sign that it has read the report.
   That is the NIS2 Art. 20 point — management must oversee the measures — and
   a signature is the usual evidence. It does not approve the measures.
2. Statuses are stated as at the generation date, never as a trend: RECOSA
   keeps no history of them, and implying one would be wrong.
3. Late notifications are counted from the incident clock's own deadlines and
   the dates recorded; a notification recorded late but sent on time counts
   as late.
"""

from __future__ import annotations

from template_seed_lib import TemplateDoc, run

BODY_EN = """\
# Annual compliance report

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

**Period: {{period_start}} to {{period_end}}.** Generated on {{generation_date}}.

For the management body. It says what happened in compliance during the period
and where the company stands on the date it was generated. Statuses are as at
that date; events are those dated within the period.

## 1. Where we stand

The share of the obligations in force that are in place, partly in place
counting half, by regulation.

{{#block:report_scores}}

{{#if:has_verdicts}}
"On your own statement" counts the obligations whose status rests only on what
we recorded ourselves, without a document, a derivation from our records or an
assessment behind it.
{{/if:has_verdicts}}

## 2. What is not yet in place

{{#block:report_gaps}}

## 3. Documents

Documents put in force or replaced during the period.

{{#block:report_documents}}

## 4. Incidents

Incidents discovered during the period, and the notifications made for them.

{{#block:report_incidents}}

## 5. Training

Sessions held during the period:

{{#block:report_training}}

Where each training stands today:

{{#block:report_training_cov}}

## 6. Artificial intelligence

{{#if:has_ai}}Our recorded uses of AI by risk class (AI Act):{{/if:has_ai}}

{{#block:report_ai}}

## 7. Actions

- Actions opened during the period: **{{tasks_opened}}**
- Actions closed during the period: **{{tasks_closed}}**
- Open on {{generation_date}}: **{{tasks_open}}**, of which overdue or blocking: **{{tasks_urgent}}**

## 8. Regulatory changes

Changes notified to us during the period:

{{#block:report_regulatory}}

## Read by the management body

The undersigned members of the management body have read this report.

| Name | Function | Date | Signature |
|---|---|---|---|
| | | | |
| | | | |
"""

BODY_FR = """\
# Rapport annuel de conformité

**{{legal_name}}**{{#if:has_legal_form}}, {{legal_form}}{{/if:has_legal_form}}

**Période : du {{period_start}} au {{period_end}}.** Généré le {{generation_date}}.

À l'attention de l'organe de direction. Il indique ce qui s'est passé en
matière de conformité sur la période et où en est l'entreprise à la date de sa
génération. Les statuts sont ceux de cette date ; les événements sont ceux
datés dans la période.

## 1. Où nous en sommes

La part des obligations en vigueur qui sont en place, celles en partie en
place comptant pour moitié, par réglementation.

{{#block:report_scores}}

{{#if:has_verdicts}}
« Sur votre seule déclaration » compte les obligations dont le statut repose
uniquement sur ce que nous avons nous-mêmes enregistré, sans document,
déduction de nos registres ou évaluation à l'appui.
{{/if:has_verdicts}}

## 2. Ce qui n'est pas encore en place

{{#block:report_gaps}}

## 3. Documents

Documents mis en vigueur ou remplacés au cours de la période.

{{#block:report_documents}}

## 4. Incidents

Incidents découverts au cours de la période, et notifications effectuées.

{{#block:report_incidents}}

## 5. Formation

Sessions tenues au cours de la période :

{{#block:report_training}}

Situation de chaque formation à ce jour :

{{#block:report_training_cov}}

## 6. Intelligence artificielle

{{#if:has_ai}}Nos usages enregistrés de l'IA par classe de risque (AI Act) :{{/if:has_ai}}

{{#block:report_ai}}

## 7. Actions

- Actions ouvertes au cours de la période : **{{tasks_opened}}**
- Actions clôturées au cours de la période : **{{tasks_closed}}**
- Ouvertes au {{generation_date}} : **{{tasks_open}}**, dont en retard ou bloquantes : **{{tasks_urgent}}**

## 8. Évolutions réglementaires

Évolutions qui nous ont été notifiées au cours de la période :

{{#block:report_regulatory}}

## Lu par l'organe de direction

Les membres soussignés de l'organe de direction ont pris connaissance du
présent rapport.

| Nom | Fonction | Date | Signature |
|---|---|---|---|
| | | | |
| | | | |
"""

DOCS = {
    "report": (TemplateDoc(
        doc_type="annual_report", title="Annual compliance report", tier=1, sort_order=70,
        sprint="S63", bodies={"en": BODY_EN, "fr": BODY_FR},
        blocks={"report_scores", "report_gaps", "report_documents", "report_incidents",
                "report_training", "report_training_cov", "report_ai", "report_regulatory"},
        change_note="Initial version (S63). Statuses as at the generation date, events within "
                    "the period. DRAFT — not yet reviewed by counsel.",
    ), "seed_s63_report.sql"),
}

if __name__ == "__main__":
    run(*DOCS["report"])
