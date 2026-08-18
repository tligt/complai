"""
docgen_templates.py — S25

Bridges template_store.generate() to the existing persistence and file-building
in document_generator.py.

A separate module rather than surgery on document_generator.py: that file is
935 lines of LLM-prompt machinery for Tier 2/3 documents, and Tier 1 templated
generation shares almost none of it. What it DOES share — build_docx, the
storage upload, the audit event — is reused rather than reimplemented.

The one change needed in document_generator.py is optional stamping kwargs on
save_document_with_files. See docgen_stamping_patch.md.

---------------------------------------------------------------------------
WHY NOT A SECOND INSERT PATH
---------------------------------------------------------------------------
It would be easy to write an insert into `documents` here and leave
document_generator.py untouched. That is the mistake the "rop"/"ropa" incident
was made of: two writers to one table drift, and the drift is invisible until
a dashboard stops matching a document. One insert path, extended.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import template_store as TS


@dataclass
class GenerationOutcome:
    ok: bool
    document_group_id: str | None
    saved: list[dict[str, Any]]          # one per persisted language
    skipped: list[dict[str, str]]        # languages with no in-force template
    missing_required: list[str]
    outstanding_total: int
    outstanding_by_language: dict[str, int]
    revision_split: bool
    message: str


def generate_templated_document(
    user_id: str,
    client_id: str,
    doc_type: str,
    *,
    company_name: str,
    languages: list[str] | None = None,
    theme: str | None = None,
    make_pdf: bool = True,
) -> GenerationOutcome:
    """Render, build and persist one document in every language the client
    issues documents in. All siblings share a document_group_id.

    ------------------------------------------------------------------
    BLOCKING SEMANTICS — two different failures, handled differently
    ------------------------------------------------------------------
    A MISSING REQUIRED FIELD blocks the whole group and saves nothing. Required
    fields are client-wide (legal name, registered address), so if one language
    blocks, every language blocks on the same value. Saving a partial group
    would put an EN policy in the register while its FR sibling silently never
    existed — and S27 adoption applies to the group, so the client would adopt
    a document that is missing a language.

    A MISSING TEMPLATE for one language does NOT block the others. That is the
    normal mid-translation state: FR is authored, NL is not yet. The available
    languages are saved and the gap is REPORTED rather than swallowed, because
    a client expecting a Dutch policy needs to be told it is unavailable, not
    left to notice a third file missing.
    """
    from document_generator import build_docx, convert_docx_to_pdf  # noqa: PLC0415
    from document_generator import save_document_with_files  # noqa: PLC0415

    docs = TS.generate(
        client_id,
        doc_type,
        generation_date=date.today().strftime("%d %B %Y"),
        languages=languages,
        theme=theme,
    )
    if not docs:
        return GenerationOutcome(
            False, None, [], [], [], 0, {}, False,
            "No document languages configured for this client.",
        )

    summary = TS.group_summary(docs)
    group_id = summary["document_group_id"]

    # Case 1: a required field is missing. Nothing is saved.
    if summary["missing_required"]:
        specs = {s.name: s.label for s in TS.FIELD_SPECS[doc_type]}
        labels = [specs.get(f, f) for f in summary["missing_required"]]
        return GenerationOutcome(
            False, group_id, [], [], summary["missing_required"], 0, {}, False,
            "Cannot generate yet — these are required and not filled in: "
            + ", ".join(labels),
        )

    # Case 2: some languages have no template. Save the rest, report the gap.
    skipped = [
        {"language": d.language, "reason": d.skipped_reason or "unavailable"}
        for d in docs if d.skipped_reason
    ]
    renderable = [d for d in docs if not d.result.blocked and d.result.body]

    if not renderable:
        return GenerationOutcome(
            False, group_id, [], skipped, [], 0, {}, False,
            f"No in-force {doc_type} template exists in any of this client's "
            "document languages.",
        )

    saved: list[dict[str, Any]] = []
    for d in renderable:
        docx_bytes = build_docx(d.result.body, doc_type, company_name, d.language)

        pdf_bytes = None
        if make_pdf:
            try:
                pdf_bytes = convert_docx_to_pdf(docx_bytes)
            except Exception:
                # PDF conversion shells out to LibreOffice and is the most
                # fragile step here. A missing PDF is a degraded result, not a
                # lost document — the DOCX is the artefact of record.
                pdf_bytes = None

        doc_id = save_document_with_files(
            user_id=user_id,
            client_id=client_id,
            document_type=doc_type,
            language=d.language,
            company_name=company_name,
            docx_bytes=docx_bytes,
            pdf_bytes=pdf_bytes,
            # S25 stamping
            template_version_id=d.template_version_id,
            document_group_id=d.document_group_id,
            outstanding_fields=d.result.outstanding_fields,
            jurisdictions_applied=d.jurisdictions_applied,
        )

        saved.append({
            "document_id": doc_id,
            "language": d.language,
            "template_version_id": d.template_version_id,
            "source_revision": d.source_revision,
            "outstanding": len(d.result.outstanding_fields),
            "body": d.result.body,
        })

    parts = [f"Generated in {', '.join(s['language'].upper() for s in saved)}."]
    if skipped:
        parts.append(
            "No template available in "
            + ", ".join(s["language"].upper() for s in skipped)
            + "."
        )
    if summary["outstanding_total"]:
        parts.append(
            f"{summary['outstanding_total']} field(s) left to complete — "
            "they appear as marked placeholders in the document."
        )
    if summary["revision_split"]:
        # Honest rather than hidden: the languages are tracking different
        # editorial revisions, which is legitimate mid-translation but means
        # the siblings are not word-for-word equivalent.
        parts.append(
            "Note: the language versions are based on different template "
            "revisions, so their wording may differ."
        )

    return GenerationOutcome(
        ok=True,
        document_group_id=group_id,
        saved=saved,
        skipped=skipped,
        missing_required=[],
        outstanding_total=summary["outstanding_total"],
        outstanding_by_language=summary["outstanding_by_language"],
        revision_split=summary["revision_split"],
        message=" ".join(parts),
    )


def preview_templated_document(
    client_id: str,
    doc_type: str,
    language: str,
    *,
    theme: str | None = None,
) -> tuple[str | None, list[str], list[dict[str, str]]]:
    """Render one language without building files or writing anything.

    Returns (body_markdown, missing_required_labels, outstanding_fields).

    Used by the admin BO viewer and by any "see it before you commit" flow.
    Writes nothing, so it is safe to call on every rerun.
    """
    docs = TS.generate(
        client_id, doc_type,
        generation_date=date.today().strftime("%d %B %Y"),
        languages=[language], theme=theme,
    )
    if not docs:
        return None, [], []

    d = docs[0]
    specs = {s.name: s.label for s in TS.FIELD_SPECS[doc_type]}
    labels = [specs.get(f, f) for f in d.result.missing_required]
    return d.result.body, labels, d.result.outstanding_fields
