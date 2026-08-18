"""
template_seed.py — S25

Authors document template bodies and emits idempotent seed SQL.

NEVER IMPORTED AT RUNTIME. Same contract as inventory_seed.py: this file is the
authoring surface, the emitted SQL is the application mechanism, and
template_store.py reads the resulting tables. Two definitions of the same body
is the drift this separation exists to prevent.

Run:  python3 template_seed.py > seed_s25_cookie_policy.sql

The script self-checks before emitting. If a body references a field that
template_store.FIELD_SPECS does not declare, it exits non-zero and writes
nothing — because a typo'd merge field does not fail loudly at render time, it
renders "[[ TO COMPLETE: unknown field 'legal_nmae' ]]" into a legal document.

---------------------------------------------------------------------------
STATUS OF THIS TEXT
---------------------------------------------------------------------------
DRAFT FOR LEGAL REVIEW. Not reviewed by a lawyer as of authoring.

The structure follows the APD's stated mandatory sections for a cookie policy:
controller identity and contact details, DPO where one exists, the types of
cookies used, third-party access and the identity of those third parties, how
to delete cookies, the legal basis (legitimate interest for functional cookies,
consent for the rest), the retention period for collected data, data subject
rights, and a complaints route.

Two things counsel should be asked about specifically:

  1. The strictest-wins rule across markets (see seed_s25_jurisdictions.sql).
     It is a conservative reading, not settled law, and it shapes every
     document RECOSA emits.
  2. Section 4's vendor-level disclosure. Until the S42 scanner exists RECOSA
     records cookies at vendor level, not per cookie. The text is written to
     state that honestly rather than imply a completeness it does not have.
     Whether vendor-level disclosure satisfies the APD's "types of cookies and
     their expiration" expectation is a judgement call.
"""

from __future__ import annotations

import re
import sys
from datetime import date

from template_store import FIELD_SPECS

DOC_TYPE = "cookie_policy"
SOURCE_REVISION = 1
VERSION_NO = 1
EFFECTIVE_FROM = date.today().isoformat()


# ===========================================================================
# ENGLISH
# ===========================================================================

BODY_EN = """\
# Cookie Policy

**{{legal_name}}** {{legal_form}}  
{{registered_address}}  
Company registration number: {{enterprise_number}}

Last updated: {{generation_date}}

## 1. About this policy

This policy explains how {{legal_name}} uses cookies and similar technologies
on {{website_url}}, what they are used for, and how you can control them.

It should be read together with our privacy policy, which explains more
generally how we handle personal data.

## 2. What cookies are

A cookie is a small text file placed on your device when you visit a website.
Similar technologies — local storage, pixels, tracking scripts — work
differently but serve comparable purposes, and this policy covers them all.

Cookies allow a website to remember your actions and preferences over time,
and can also be used to build a picture of how you and others use a site.

## 3. Cookies we use and why

**Strictly necessary cookies** are required for the website to function — they
keep you signed in, remember what is in a form, and protect against fraud.
These are placed on the basis of our legitimate interest in operating a working
and secure website, and they cannot be switched off.

**All other cookies** — including analytics, functionality and advertising
cookies — are placed only if you consent to them. You are free to refuse, and
refusing does not restrict your access to this website.

{{#if:cookie_walls_prohibited}}
We do not make access to this website conditional on your accepting cookies.
{{/if:cookie_walls_prohibited}}

## 4. Third parties

{{#if:has_vendors}}
Some cookies are placed by third-party services we use. Those services receive
data about your visit and process it under their own terms. The services
currently in use are:

{{#block:cookie_table}}

Where a service is described as a joint controller, that means we and the
service jointly determine why and how the data collected through it is
processed, and we are jointly responsible for it.
{{/if:has_vendors}}

{{#ifnot:has_vendors}}
We do not currently use any third-party services that place cookies on this
website. Should that change, this policy will be updated before the service is
introduced.
{{/ifnot:has_vendors}}

This list is maintained at the level of the service rather than the individual
cookie. If you need the specific cookie names, durations and values set by a
particular service, contact us using the details in section 8 and we will
provide them.

## 5. How long cookies last

{{#if:has_cookie_lifetime_cap}}
Cookies placed with your consent expire no later than {{cookie_max_lifetime_months}}
months after they are set. They are not renewed automatically when you return
to the site.
{{/if:has_cookie_lifetime_cap}}

{{#ifnot:has_cookie_lifetime_cap}}
Cookies placed with your consent are kept no longer than is necessary for the
purpose they were set for, and are never given an unlimited lifetime. The
period differs by cookie; we can tell you the duration for any particular
cookie on request.
{{/ifnot:has_cookie_lifetime_cap}}

{{#if:has_data_retention_cap}}
Data collected through those cookies is retained for no more than
{{cookie_data_retention_months}} months, after which it is deleted or
anonymised.
{{/if:has_data_retention_cap}}

{{#if:has_consent_renewal_period}}
We will ask you again about your cookie preferences after
{{consent_renewal_months}} months, or sooner if what we use cookies for
changes.
{{/if:has_consent_renewal_period}}

## 6. Your choices

You gave or refused consent when you first visited this website, and you can
change that decision at any time using the cookie settings link available on
every page.

{{#if:reject_parity_required}}
Refusing is as easy as accepting: both options are presented together, with
equal prominence, before any non-essential cookie is placed.
{{/if:reject_parity_required}}

Withdrawing consent stops further collection. It does not undo processing that
already took place while your consent was valid.

You can also delete cookies already stored, and block future ones, through your
browser settings. Every major browser offers this under its privacy or security
settings. Blocking strictly necessary cookies may stop parts of the website
working.

## 7. Your rights

You have the right to access the personal data we hold about you, to have it
corrected or erased, to restrict or object to how we process it, and to receive
it in a portable form. Where processing rests on consent, you may withdraw that
consent at any time.

{{#if:is_multi_market}}
This website serves visitors in more than one country. Where national rules on
cookies differ, we apply the stricter requirement to all visitors rather than
varying the protection by location.
{{/if:is_multi_market}}

## 8. Contact and complaints

For any question about this policy, or to exercise any of the rights above,
contact us at {{contact_email}}.

{{#if:has_dpo}}
Our Data Protection Officer is {{dpo_name}}, reachable at {{dpo_email}}.
{{/if:has_dpo}}

If you are not satisfied with our response, you may lodge a complaint with the
{{authority_name}} ({{authority_url}}). You may also complain to the
supervisory authority in the country where you live or work.
"""


# ===========================================================================
# FRENCH
# ===========================================================================

BODY_FR = """\
# Politique relative aux cookies

**{{legal_name}}** {{legal_form}}  
{{registered_address}}  
Numéro d'entreprise : {{enterprise_number}}

Dernière mise à jour : {{generation_date}}

## 1. Objet de la présente politique

La présente politique explique comment {{legal_name}} utilise des cookies et
technologies similaires sur {{website_url}}, à quelles fins, et comment vous
pouvez les contrôler.

Elle se lit conjointement avec notre politique de confidentialité, qui décrit
plus largement notre traitement des données à caractère personnel.

## 2. Qu'est-ce qu'un cookie

Un cookie est un petit fichier texte déposé sur votre appareil lorsque vous
visitez un site web. Des technologies similaires — stockage local, pixels,
scripts de mesure — fonctionnent différemment mais poursuivent des finalités
comparables ; la présente politique les couvre également.

Les cookies permettent à un site de mémoriser vos actions et préférences dans
le temps, et peuvent aussi servir à reconstituer la manière dont vous et
d'autres utilisez le site.

## 3. Les cookies que nous utilisons et pourquoi

**Les cookies strictement nécessaires** permettent au site de fonctionner : ils
vous maintiennent connecté, conservent le contenu d'un formulaire et protègent
contre la fraude. Ils reposent sur notre intérêt légitime à exploiter un site
fonctionnel et sécurisé, et ne peuvent pas être désactivés.

**Tous les autres cookies** — mesure d'audience, fonctionnalités, publicité —
ne sont déposés qu'avec votre consentement. Vous pouvez refuser librement, et
ce refus ne restreint en rien votre accès au site.

{{#if:cookie_walls_prohibited}}
Nous ne conditionnons pas l'accès à ce site à l'acceptation des cookies.
{{/if:cookie_walls_prohibited}}

## 4. Les tiers

{{#if:has_vendors}}
Certains cookies sont déposés par des services tiers auxquels nous recourons.
Ces services reçoivent des données relatives à votre visite et les traitent
selon leurs propres conditions. Les services actuellement utilisés sont les
suivants :

{{#block:cookie_table}}

Lorsqu'un service est qualifié de responsable conjoint du traitement, cela
signifie que nous déterminons conjointement avec lui les finalités et les
moyens du traitement des données collectées, et que nous en sommes
conjointement responsables.
{{/if:has_vendors}}

{{#ifnot:has_vendors}}
Nous n'utilisons actuellement aucun service tiers déposant des cookies sur ce
site. Si cela devait changer, la présente politique serait mise à jour avant
l'introduction du service.
{{/ifnot:has_vendors}}

Cette liste est tenue au niveau du service et non du cookie individuel. Si vous
souhaitez connaître les noms, durées et valeurs des cookies déposés par un
service déterminé, contactez-nous aux coordonnées de la section 8 et nous vous
les communiquerons.

## 5. Durée de conservation

{{#if:has_cookie_lifetime_cap}}
Les cookies déposés avec votre consentement expirent au plus tard
{{cookie_max_lifetime_months}} mois après leur dépôt. Leur durée n'est pas
prolongée automatiquement lors de vos visites ultérieures.
{{/if:has_cookie_lifetime_cap}}

{{#ifnot:has_cookie_lifetime_cap}}
Les cookies déposés avec votre consentement ne sont conservés que le temps
nécessaire à la finalité pour laquelle ils ont été déposés, et ne se voient
jamais attribuer une durée illimitée. Cette durée varie selon le cookie ; nous
pouvons vous l'indiquer sur demande.
{{/ifnot:has_cookie_lifetime_cap}}

{{#if:has_data_retention_cap}}
Les données collectées au moyen de ces cookies sont conservées
{{cookie_data_retention_months}} mois au maximum, puis supprimées ou
anonymisées.
{{/if:has_data_retention_cap}}

{{#if:has_consent_renewal_period}}
Nous vous interrogerons à nouveau sur vos préférences après
{{consent_renewal_months}} mois, ou plus tôt si les finalités de nos cookies
évoluent.
{{/if:has_consent_renewal_period}}

## 6. Vos choix

Vous avez donné ou refusé votre consentement lors de votre première visite.
Vous pouvez modifier ce choix à tout moment via le lien de paramétrage des
cookies présent sur chaque page.

{{#if:reject_parity_required}}
Refuser est aussi simple qu'accepter : les deux options sont présentées
ensemble, avec la même visibilité, avant le dépôt de tout cookie non essentiel.
{{/if:reject_parity_required}}

Le retrait du consentement met fin à toute collecte ultérieure. Il ne remet pas
en cause les traitements déjà effectués pendant la période où votre
consentement était valable.

Vous pouvez également supprimer les cookies déjà enregistrés et bloquer les
suivants depuis les paramètres de votre navigateur. Tous les principaux
navigateurs proposent cette fonction dans leurs réglages de confidentialité ou
de sécurité. Le blocage des cookies strictement nécessaires peut empêcher
certaines parties du site de fonctionner.

## 7. Vos droits

Vous disposez du droit d'accéder aux données à caractère personnel vous
concernant, d'en demander la rectification ou l'effacement, d'en limiter le
traitement ou de vous y opposer, et d'en recevoir une copie dans un format
portable. Lorsque le traitement repose sur le consentement, vous pouvez le
retirer à tout moment.

{{#if:is_multi_market}}
Ce site s'adresse à des visiteurs de plusieurs pays. Lorsque les règles
nationales en matière de cookies diffèrent, nous appliquons l'exigence la plus
stricte à l'ensemble des visiteurs plutôt que de faire varier la protection
selon le lieu.
{{/if:is_multi_market}}

## 8. Contact et réclamations

Pour toute question relative à la présente politique, ou pour exercer l'un des
droits ci-dessus, écrivez-nous à {{contact_email}}.

{{#if:has_dpo}}
Notre délégué à la protection des données est {{dpo_name}}, joignable à
l'adresse {{dpo_email}}.
{{/if:has_dpo}}

Si notre réponse ne vous satisfait pas, vous pouvez introduire une réclamation
auprès de {{authority_name}} ({{authority_url}}). Vous pouvez également saisir
l'autorité de contrôle du pays dans lequel vous résidez ou travaillez.
"""


BODIES = {"en": BODY_EN, "fr": BODY_FR}


# ===========================================================================
# SELF-CHECKS
# ===========================================================================
# S24's lesson: encode the rule as an executable check, not as prose. The
# retention principle written as a self_check caught three violations minutes
# after it was authored. These do the same for merge fields.

_FIELD_RE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_IF_RE = re.compile(r"\{\{#(if|ifnot):([a-z0-9_]+)\}\}")
_CLOSE_RE = re.compile(r"\{\{/(if|ifnot):([a-z0-9_]+)\}\}")
_BLOCK_RE = re.compile(r"\{\{#block:([a-z0-9_]+)\}\}")

KNOWN_BLOCKS = {"cookie_table"}


def check_bodies() -> list[str]:
    errors: list[str] = []
    specs = {s.name: s for s in FIELD_SPECS[DOC_TYPE]}

    for lang, body in BODIES.items():
        # 1. Every substituted field is declared.
        for name in sorted(set(_FIELD_RE.findall(body))):
            if name not in specs:
                errors.append(f"[{lang}] undeclared field: {name}")
            elif specs[name].flag:
                errors.append(
                    f"[{lang}] {name} is a flag and must be used in a "
                    f"conditional, not substituted as text"
                )

        # 2. Every conditional tests a declared flag.
        for kind, name in _IF_RE.findall(body):
            if name not in specs:
                errors.append(f"[{lang}] #{kind} on undeclared field: {name}")
            elif not specs[name].flag:
                errors.append(
                    f"[{lang}] #{kind}:{name} tests a value field. Conditionals "
                    f"take flags — otherwise the branch silently depends on "
                    f"whether the client filled a text box."
                )

        # 3. Conditionals balance. An unclosed one strips silently at render.
        opens = sorted(_IF_RE.findall(body))
        closes = sorted(_CLOSE_RE.findall(body))
        if opens != closes:
            errors.append(f"[{lang}] unbalanced conditionals: {opens} vs {closes}")

        # 4. Blocks exist.
        for name in _BLOCK_RE.findall(body):
            if name not in KNOWN_BLOCKS:
                errors.append(f"[{lang}] unknown block: {name}")

    # 5. Languages agree on which fields they use. A field present in one body
    #    and absent from another means the translation drifted from the source
    #    — a French reader silently loses a paragraph the English reader gets.
    used = {
        lang: set(_FIELD_RE.findall(b)) | {n for _, n in _IF_RE.findall(b)}
        for lang, b in BODIES.items()
    }
    baseline_lang = "en"
    for lang, names in used.items():
        if lang == baseline_lang:
            continue
        missing = used[baseline_lang] - names
        extra = names - used[baseline_lang]
        if missing:
            errors.append(f"[{lang}] fields present in en but missing: {sorted(missing)}")
        if extra:
            errors.append(f"[{lang}] fields not present in en: {sorted(extra)}")

    # 6. Every required field is actually referenced. A required field no body
    #    uses blocks generation for nothing.
    referenced = set().union(*used.values())
    for name, spec in specs.items():
        if spec.required and name not in referenced:
            errors.append(
                f"required field '{name}' is declared but referenced by no "
                f"body — it would block generation and change nothing"
            )

    return errors


# ===========================================================================
# SQL EMISSION
# ===========================================================================

def _dollar_quote(text: str, tag: str) -> str:
    """Dollar-quote rather than escape.

    These bodies contain apostrophes throughout ("l'autorité", "d'entreprise").
    Doubling them is a correctness hazard for exactly the language most likely
    to need it, so the quoting mechanism sidesteps escaping entirely.
    """
    marker = f"${tag}$"
    if marker in text:
        raise ValueError(f"body contains the dollar-quote tag {marker}")
    return f"{marker}{text}{marker}"


def emit_sql() -> str:
    parts: list[str] = []
    parts.append(f"""\
-- ============================================================================
-- seed_s25_cookie_policy.sql
-- GENERATED BY template_seed.py — DO NOT EDIT THIS FILE.
--
-- Edit template_seed.py and regenerate. Editing here means the next
-- regeneration silently discards the change.
--
-- Idempotent. Re-running updates the bodies in place.
--
-- DRAFT FOR LEGAL REVIEW — not yet reviewed by counsel.
-- ============================================================================

INSERT INTO document_templates (doc_type, title, tier, active, sort_order)
VALUES ('{DOC_TYPE}', 'Cookie Policy', 1, TRUE, 10)
ON CONFLICT (doc_type) DO UPDATE
SET title = EXCLUDED.title,
    tier = EXCLUDED.tier,
    active = EXCLUDED.active,
    sort_order = EXCLUDED.sort_order;
""")

    for lang, body in BODIES.items():
        quoted = _dollar_quote(body, f"body_{lang}")
        parts.append(f"""
INSERT INTO document_template_versions
    (template_id, language, version_no, source_revision, body_md,
     materiality, status, change_note, effective_from)
SELECT id, '{lang}', {VERSION_NO}, {SOURCE_REVISION},
       {quoted},
       'required', 'in_force', 'Initial version (S25).', DATE '{EFFECTIVE_FROM}'
FROM document_templates WHERE doc_type = '{DOC_TYPE}'
ON CONFLICT (template_id, language, version_no) DO UPDATE
SET source_revision = EXCLUDED.source_revision,
    body_md         = EXCLUDED.body_md,
    materiality     = EXCLUDED.materiality,
    status          = EXCLUDED.status,
    change_note     = EXCLUDED.change_note,
    effective_from  = EXCLUDED.effective_from;
""")

    parts.append("""
-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
-- SELECT t.doc_type, v.language, v.version_no, v.source_revision, v.status,
--        v.effective_from, length(v.body_md) AS body_chars
-- FROM document_template_versions v
-- JOIN document_templates t ON t.id = v.template_id
-- WHERE t.doc_type = 'cookie_policy'
-- ORDER BY v.language;
--
-- Expect two rows, both in_force, both at source_revision 1.
--
-- NOTE ON RE-RUNNING: the ON CONFLICT arbiter is the real UNIQUE constraint
-- (template_id, language, version_no). It is NOT the partial index
-- dtv_one_in_force_per_language, which cannot arbitrate — a partial index
-- raises 42P10 if named as a conflict target.
""")
    return "".join(parts)


if __name__ == "__main__":
    problems = check_bodies()
    if problems:
        print("SELF-CHECK FAILED — nothing emitted:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        sys.exit(1)
    print(emit_sql())
