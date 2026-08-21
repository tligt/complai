# ---------------------------------------------------------------------------
# ADD TO template_store.py — S26A, DPA loaders
# ---------------------------------------------------------------------------
# These reuse _load_inventory() rather than querying again: it already fetches
# activities, systems and links, and a DPA needs no table the registers do not.
#
# THE SCOPING RULE, WHICH IS THE WHOLE POINT
# ------------------------------------------
# Every function here filters to activities with controller_role == 'processor'
# FIRST, and only then walks to systems.
#
# The scope-lock said the sub-processor list comes from S24 `systems` filtered
# to role != 'internal'. That is wrong twice over. `role` is not on systems —
# it is on activity_systems, because a vendor can be processor for one activity
# and joint controller for another. And filtering the whole inventory would
# list every vendor the client uses, including those touching only the client's
# OWN controller-side data.
#
# That second error is the serious one. It would name, in a signed contract
# with a customer, vendors that never touch that customer's data — asserting a
# disclosure that never happened, and inviting an objection under Clause 7.7(a)
# to a sub-processor which is not one. Naming too many is not the safe
# direction here.


def _processor_activity_ids(inv: Mapping[str, Any]) -> set[str]:
    """Activities the client carries out on someone else's behalf."""
    return {
        a["id"] for a in inv["activities"]
        if a.get("controller_role") == "processor"
    }


def build_dpa_annex_ii_rows(
    inv: Mapping[str, Any], language: str
) -> list[dict[str, Any]]:
    """Annex II — one entry per processing carried out as processor.

    The OJ's Annex II is a single flat description, which assumes one
    processing. A client processing on a customer's behalf usually has several,
    so this emits one entry each and the renderer stacks them. That is adding
    information to an annex, which Clause 2(a) expressly permits.

    Duration (Clause 7.3, and 'Duration of the processing' in Annex II) is the
    retention period. It is left as None rather than defaulted when unset:
    Clause 7.3 confines processing to the duration Annex II specifies, so
    inventing one would shorten or extend the client's own contract by
    guesswork. The renderer surfaces the gap instead.
    """
    rows: list[dict[str, Any]] = []
    for a in sorted(inv["activities"], key=lambda r: (r.get("name") or "")):
        if a.get("controller_role") != "processor":
            continue

        specials = _labels("special_category", a.get("special_categories"), language)
        criminal = _labels("criminal_data", a.get("criminal_data"), language)

        rows.append({
            "name": a.get("name"),
            # Annex II asks for nature AND purpose as separate headings. The
            # inventory has one free-text purpose field, so nature is derived
            # from the activity name and purpose carries the client's text.
            "nature": a.get("name"),
            "purpose": a.get("purpose"),
            "data_subjects": _labels(
                "data_subject_category", a.get("data_subject_categories"), language),
            "data_categories": ", ".join(
                x for x in (
                    _labels("data_category", a.get("data_categories"), language),
                    criminal,
                ) if x
            ) or None,
            # Clause 7.5 obliges the processor to apply specific restrictions
            # or additional safeguards to sensitive data, and Annex II asks for
            # them explicitly. Carrying the special categories without the
            # safeguards would leave the annex asserting the trigger for an
            # obligation while saying nothing about how it is met.
            "special_categories": specials,
            "sensitive_safeguards": (
                _labels("security_measure", a.get("security_measures"), language)
                if specials else None
            ),
            "duration": a.get("retention_period"),
            "duration_basis": _clean_retention_basis(a.get("retention_basis")),
        })
    return rows


def build_dpa_security_measures(inv: Mapping[str, Any], language: str) -> str | None:
    """Annex III part 1 — Clause 7.4(a).

    Unioned across the processor activities rather than listed per activity.
    Clause 7.4(a) obliges the processor to implement at least the measures
    Annex III specifies, as a floor for the engagement as a whole; splitting
    them per activity would read as though a measure listed against one
    activity does not apply to another.
    """
    act_ids = _processor_activity_ids(inv)
    codes: set[str] = set()
    for a in inv["activities"]:
        if a["id"] in act_ids:
            for code in a.get("security_measures") or []:
                codes.add(code)
    return _labels("security_measure", sorted(codes), language)


def build_dpa_subprocessor_rows(
    inv: Mapping[str, Any], language: str
) -> list[dict[str, Any]]:
    """Schedule 1 — the agreed list for Clause 7.7(a) Option 2.

    Scoped to systems supporting processor-role activities, with internal
    systems excluded: a client's own server is not a sub-processor, the same
    reason _NON_RECIPIENT_ROLES exists for the controller register.

    Location and transfer mechanism are included because Clause 7.8(a) confines
    third-country transfers to documented instructions, and a controller cannot
    give an informed instruction about a sub-processor whose location the
    schedule does not state.
    """
    from inventory import label_for  # noqa: PLC0415

    act_ids = _processor_activity_ids(inv)
    systems_by_id = {s["id"]: s for s in inv["systems"]}

    roles_by_system: dict[str, list[str]] = {}
    for l in inv["links"]:
        if l["activity_id"] not in act_ids:
            continue
        role = l.get("role")
        if (role or "") in _NON_RECIPIENT_ROLES:
            continue
        bucket = roles_by_system.setdefault(l["system_id"], [])
        if role and role not in bucket:
            bucket.append(role)
        elif not role:
            roles_by_system.setdefault(l["system_id"], [])

    rows: list[dict[str, Any]] = []
    for system_id, roles in roles_by_system.items():
        s = systems_by_id.get(system_id)
        if not s:
            continue
        country = (s.get("processing_country") or "").upper() or None
        rows.append({
            "name": s.get("vendor_legal_name") or s.get("name"),
            "category_label": (
                label_for("system_category", s["category"], language)
                if s.get("category") else None
            ),
            "role_label": "; ".join(
                label_for("system_role", r, language) for r in roles
            ) or None,
            "country": country,
            "transfer_mechanism": (
                label_for("transfer_mechanism", s.get("transfer_mechanism") or "unknown", language)
                if country and _is_third_country(country) else None
            ),
        })
    return sorted(rows, key=lambda r: (r["name"] or "").lower())


def _is_third_country(code: str) -> bool:
    from inventory import is_third_country  # noqa: PLC0415
    return is_third_country(code)


# ---------------------------------------------------------------------------
# D-44 — Annex III parts 2 and 3 have no inventory source
# ---------------------------------------------------------------------------
# Clause 8(d) requires Annex III to set out the measures by which the processor
# assists the controller AND the scope and extent of that assistance. The
# closing paragraph of Clause 9.2 requires it to set out the further elements
# provided when assisting with breach notification. Neither has anything in
# S24 to draw on: security_measures are controls, and assistance is a service
# commitment.
#
# Leaving them blank emits a DPA that fails its own clauses. Deriving them from
# security_measures answers a different question. So: a RECOSA-authored default
# the client edits, on the D-43 reasoning — a commercial term on the client's
# contract with their customer, where RECOSA supplies a defensible starting
# point and does not score the answer.
#
# Part 3 is the more determinate of the two, since Clause 9.2(a)-(c) already
# fixes the minimum content; the default adds only the routing.
#
# NOT scored by readiness(). A client who narrows the assistance has made a
# commercial choice their customer may push back on, not a compliance failure.

_DPA_ASSISTANCE_DEFAULT = {
    "en": (
        "The processor assists the controller by: forwarding any data subject "
        "request received to the controller's stated contact without responding "
        "to it directly; providing, on request, the information held about the "
        "processing that the controller needs for a data protection impact "
        "assessment or a prior consultation; informing the controller without "
        "delay on becoming aware that personal data it processes is inaccurate "
        "or out of date; and making available the information necessary to "
        "demonstrate compliance with these Clauses, including permitting and "
        "contributing to audits under Clause 7.6.\n\n"
        "Assistance is provided within the timeframes the controller specifies "
        "as necessary to meet its own statutory deadlines, and at no additional "
        "charge where the request arises from the processing described in "
        "Annex II."
    ),
    "fr": (
        "Le sous-traitant prête assistance au responsable du traitement en : "
        "transmettant au contact désigné par le responsable du traitement toute "
        "demande reçue d'une personne concernée, sans y répondre directement ; "
        "fournissant, sur demande, les informations dont il dispose sur le "
        "traitement et qui sont nécessaires au responsable du traitement pour "
        "réaliser une analyse d'impact relative à la protection des données ou "
        "une consultation préalable ; informant sans délai le responsable du "
        "traitement lorsqu'il apprend que les données à caractère personnel "
        "qu'il traite sont inexactes ou obsolètes ; et mettant à disposition "
        "les informations nécessaires pour démontrer le respect des présentes "
        "clauses, y compris en permettant les audits prévus à la clause 7.6 et "
        "en y contribuant.\n\n"
        "L'assistance est fournie dans les délais indiqués par le responsable "
        "du traitement comme nécessaires au respect de ses propres délais "
        "légaux, et sans frais supplémentaires lorsque la demande découle du "
        "traitement décrit à l'annexe II."
    ),
}

_DPA_BREACH_ELEMENTS_DEFAULT = {
    "en": (
        "In addition to the information required by Clause 9.2(a) to (c), the "
        "processor provides: the date and time the breach was detected and, "
        "where known, when it began; which of the systems listed in Schedule 1 "
        "were involved; whether any sub-processor was affected; the containment "
        "steps already taken; and whether the data was encrypted or otherwise "
        "rendered unintelligible.\n\n"
        "Notification is sent to the controller's stated contact and is not "
        "withheld pending a complete picture — an initial notification carries "
        "what is known at the time, and further information follows as it "
        "becomes available."
    ),
    "fr": (
        "Outre les informations exigées par la clause 9.2, points a) à c), le "
        "sous-traitant communique : la date et l'heure de la détection de la "
        "violation et, si elle est connue, celle de son début ; ceux des "
        "systèmes énumérés à l'annexe technique 1 qui sont concernés ; si un "
        "sous-traitant ultérieur est touché ; les mesures de confinement déjà "
        "prises ; et si les données étaient chiffrées ou rendues incompréhen"
        "sibles par un autre moyen.\n\n"
        "La notification est adressée au contact désigné par le responsable du "
        "traitement et n'est pas différée dans l'attente d'un tableau complet : "
        "la notification initiale contient les informations disponibles à ce "
        "moment-là, les informations complémentaires suivant à mesure qu'elles "
        "deviennent disponibles."
    ),
}


def dpa_assistance_text(language: str) -> str:
    return _DPA_ASSISTANCE_DEFAULT.get(language, _DPA_ASSISTANCE_DEFAULT["en"])


def dpa_breach_elements_text(language: str) -> str:
    return _DPA_BREACH_ELEMENTS_DEFAULT.get(language, _DPA_BREACH_ELEMENTS_DEFAULT["en"])


# ---------------------------------------------------------------------------
# Wiring — add a 'dpa' branch to build_block_context()
# ---------------------------------------------------------------------------
#     if doc_type == "dpa":
#         inv = _load_inventory(client_id)
#         stamps = [
#             r.get("updated_at")
#             for key in ("activities", "systems")
#             for r in inv[key] if r.get("updated_at")
#         ]
#         return {
#             "dpa_annex_ii_rows": build_dpa_annex_ii_rows(inv, language),
#             "dpa_security_measures": build_dpa_security_measures(inv, language),
#             "dpa_assistance": dpa_assistance_text(language),
#             "dpa_breach_elements": dpa_breach_elements_text(language),
#             "dpa_subprocessor_rows": build_dpa_subprocessor_rows(inv, language),
#         }, (max(stamps)[:10] if stamps else None)
#
# ---------------------------------------------------------------------------
# Wiring — add a 'dpa' branch to build_values()
# ---------------------------------------------------------------------------
#     if doc_type == "dpa":
#         ctx = block_context or {}
#         values["has_enterprise_number"] = bool(
#             (client.get("enterprise_number") or "").strip())
#         values["has_subprocessors"] = bool(ctx.get("dpa_subprocessor_rows"))
#         values["sub_processor_notice_period"] = format_notice_period(
#             client.get("sub_processor_notice_days"), language)
#
# has_dpo is already set above for every doc_type, so the DPA gets it free.
