"""
pages/inventory.py — vendor and processing-activity intake (S24, amended S25).

Two tabs, two deliberately different interaction models.

Systems use st.data_editor: every field is scalar, and the task is
*confirmation* rather than authoring — the client ticks catalogue vendors and
corrects the defaults. A grid is right for that, and it is the difference
between two minutes and twenty.

Processing activities use one form per row. Every interesting field is an
enumerated multi-select, and st.data_editor has no multiselect column type —
the alternative inside a grid is comma-separated free text, which would put
uncontrolled vocabulary into the exact columns the RoPA, the gap scoring and
the Art. 9 flag all depend on. Uglier, and correct.

── S25 amendments ────────────────────────────────────────────────────────
Two bugs fixed, both silent:

1. client_id was read only from st.session_state["selected_client"], which is
   populated in Advisory flows and absent everywhere else. So Starter and
   Professional clients wrote every system and activity with client_id NULL,
   while pages/documents.py resolved the same company through load_clients()
   and got a real id. The Cookie Policy read found nothing. Resolution is now
   shared: session first, then the user's sole client.

2. lang read _client["language"], a key that has never existed — so the page
   has been English-only since it shipped and the seeded French labels were
   unreachable. Document languages are a company property (plural); the UI
   language belongs to the user. Until a user language column exists, the
   first document language is the best available fallback.
"""

import pandas as pd
import streamlit as st

from auth import get_user_id
from database import load_clients
import inventory as INV
import inventory_store as STORE

st.title("Systems and processing activities")
st.caption(
    "This inventory is the source for your Record of Processing Activities, "
    "your Data Processing Agreements and your Cookie Policy. Filling it in "
    "once means those documents can be generated rather than written."
)

# app.py gates on is_logged_in() before navigation runs, so this page never
# renders unauthenticated. The guard stays as a cheap backstop against the
# page being reached some other way.
user_id = get_user_id()
if not user_id:
    st.warning("Please sign in to manage your inventory.")
    st.stop()


# ── Client resolution (S25) ───────────────────────────────────────────────
# One identity per company, resolved the same way on every page. Writing NULL
# here and a real id elsewhere is what broke the Cookie Policy read, and it
# would have broken the RoPA (S26) and the register (S27) in turn.

_client = st.session_state.get("selected_client") or {}
client_id = _client.get("id")

if not client_id:
    _owned = load_clients(user_id) or []
    if len(_owned) == 1:
        # Starter and Professional: the user is the company. There is exactly
        # one client row, so using it is unambiguous.
        _client = _owned[0]
        client_id = _client["id"]
    elif len(_owned) > 1:
        # Advisory, with nothing selected. Guessing would attach a vendor to
        # the wrong company — a silent, hard-to-notice error in a document that
        # later gets filed. Stop and ask instead.
        st.warning(
            "Select a client before editing the inventory. Systems and "
            "processing activities belong to a specific company."
        )
        st.stop()
    else:
        st.info("Create a client profile before filling in your inventory.")
        st.stop()

# Language for labels. See the module docstring: this is UI chrome, so it
# should follow the user once a user language column exists. Until then the
# first document language is the closest available signal.
lang = (
    st.session_state.get("ui_language")
    or (_client.get("document_languages") or ["en"])[0]
)
if lang not in INV.LANGUAGES:
    # label_for and note_for coerce internally, but options_for builds
    # label_{lang} by direct lookup — a bad code yields a dict of None labels
    # and every dropdown renders blank. Normalise once here.
    lang = "en"


# ── Data ──────────────────────────────────────────────────────────────────

systems = STORE.load_systems(user_id, client_id)
activities = STORE.load_activities(user_id, client_id)
links = STORE.load_links(user_id, client_id)

system_name = {s["id"]: s["name"] for s in systems}

ready = STORE.readiness(activities, systems, links)

c1, c2, c3 = st.columns(3)
c1.metric("Systems", ready["systems"])
c2.metric("Processing activities", ready["activities"])
c3.metric("Ready for RoPA", f"{ready['complete_activities']}/{ready['activities']}")

# The rules behind the pre-filled values, readable where the values are.
# Without this a client sees a blank retention field and reads it as a bug
# rather than as a deliberate refusal to guess at their national law.
_principles = INV.principles_for_display(lang)
if _principles:
    with st.expander("How this inventory is filled in"):
        for p in _principles:
            st.markdown(f"**{p['title']}**")
            st.caption(p["body"])

tab_systems, tab_activities = st.tabs(["Systems", "Processing activities"])


# ── Systems ───────────────────────────────────────────────────────────────

with tab_systems:
    catalogue = INV.get_catalogue()
    seeded = STORE.already_seeded(systems)
    available = [v for v in catalogue if v["key"] not in seeded]

    if available:
        with st.expander("Add a common tool", expanded=not systems):
            st.caption(
                "Adding a tool from this list pre-fills its vendor details and "
                "creates the processing activities it usually supports. Every "
                "value is a starting point — review and correct them."
            )
            choice = st.selectbox(
                "Tool",
                options=[v["key"] for v in available],
                format_func=lambda k: next(v["name"] for v in available if v["key"] == k),
                key="inv_catalogue_choice",
            )
            entry = next(v for v in available if v["key"] == choice)

            n_acts = len(entry.get("activities", []))
            st.caption(
                f"Creates 1 system and {n_acts} processing "
                f"{'activity' if n_acts == 1 else 'activities'}."
            )
            # Surfacing the caveats before the click, not after — a client who
            # accepts a joint-controller default without seeing the argument
            # has been given a conclusion, not a tool.
            for note_field in ("role_note", "ai_note"):
                note = entry.get(f"{note_field}_{lang}") or entry.get(f"{note_field}_en")
                if note:
                    st.info(note)

            if st.button("Add to my inventory", type="primary", key="inv_seed_btn"):
                res = STORE.seed_from_catalogue(choice, user_id, client_id, lang)
                if res.get("error"):
                    st.error(res["error"])
                else:
                    st.success(
                        f"Added {res['system_name']} and "
                        f"{res['activities_created']} processing activities."
                    )
                    for e in res.get("errors", []):
                        st.warning(e)
                    st.rerun()

    st.divider()

    if not systems:
        st.info("No systems yet. Add one from the list above, or type directly into the table.")

    cat_codes, cat_labels = INV.options_for("system_category", lang, client_id)
    tm_codes, tm_labels = INV.options_for("transfer_mechanism", lang, client_id)
    dpa_codes, dpa_labels = INV.options_for("dpa_status", lang, client_id)
    crit_codes, crit_labels = INV.options_for("criticality", lang, client_id)
    ai_codes, ai_labels = INV.options_for("ai_role", lang, client_id)

    grid_cols = ["id"] + list(STORE.SYSTEM_EDITABLE)
    base_df = pd.DataFrame(
        [{c: s.get(c) for c in grid_cols} for s in systems],
        columns=grid_cols,
    )

    edited = st.data_editor(
        base_df,
        key="inv_systems_editor",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            # None hides the column while keeping it in the returned frame.
            # The id is what makes the diff immune to sorting and filtering.
            "id": None,
            "name": st.column_config.TextColumn("System", required=True, width="medium"),
            "vendor_legal_name": st.column_config.TextColumn("Vendor legal entity", width="medium"),
            "category": st.column_config.SelectboxColumn("Category", options=cat_codes),
            "purpose": st.column_config.TextColumn("What you use it for", width="large"),
            "processing_country": st.column_config.TextColumn("Country", width="small",
                                                              help="ISO code, or EU for multi-state EEA processing."),
            "transfer_mechanism": st.column_config.SelectboxColumn("Transfer basis", options=tm_codes),
            "dpa_status": st.column_config.SelectboxColumn("DPA", options=dpa_codes),
            "dpa_signed_on": st.column_config.DateColumn("DPA signed"),
            "dpa_url": st.column_config.LinkColumn("DPA link"),
            "criticality": st.column_config.SelectboxColumn("Criticality", options=crit_codes),
            "ai_role": st.column_config.SelectboxColumn("AI role", options=ai_codes),
            "sets_cookies": st.column_config.CheckboxColumn("Sets cookies"),
            "privacy_policy_url": st.column_config.LinkColumn("Privacy policy"),
            "notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )

    st.caption(
        "Codes such as `scc` or `not_required` are shown raw in this table; "
        "their full meaning appears wherever they are used in a document. "
        "Scroll the table sideways to reach *Sets cookies*, *AI role* and *Notes*."
    )

    if st.button("Save changes", type="primary", key="inv_systems_save"):
        result = STORE.commit_systems(systems, edited, user_id, client_id)

        parts = []
        if result["inserted"]:
            parts.append(f"{result['inserted']} added")
        if result["updated"]:
            parts.append(f"{result['updated']} updated")
        if result["deleted"]:
            parts.append(f"{result['deleted']} removed")

        if parts:
            st.success(", ".join(parts).capitalize() + ".")
        elif not result["errors"]:
            st.info("Nothing to save.")

        for e in result["errors"]:
            st.error(e)

        if not result["errors"]:
            # Dropping the widget state stops a delta from an earlier render
            # replaying against the freshly-loaded rows on the next rerun.
            st.session_state.pop("inv_systems_editor", None)
            st.rerun()

    if ready["dpa_gaps"]:
        st.warning(
            "No signed processing agreement recorded for: "
            + ", ".join(ready["dpa_gaps"])
        )


# ── Processing activities ─────────────────────────────────────────────────

with tab_activities:
    st.caption(
        "One row per purpose you process personal data for. These become the "
        "rows of your Art. 30 record."
    )

    basis_codes, basis_labels = INV.options_for("legal_basis", lang, client_id)
    role_codes, role_labels = INV.options_for("controller_role", lang, client_id)
    subj_codes, subj_labels = INV.options_for("data_subject_category", lang, client_id)
    data_codes, data_labels = INV.options_for("data_category", lang, client_id)
    spec_codes, spec_labels = INV.options_for("special_category", lang, client_id)
    art9_codes, art9_labels = INV.options_for("art9_condition", lang, client_id)
    crim_codes, crim_labels = INV.options_for("criminal_data", lang, client_id)
    sec_codes, sec_labels = INV.options_for("security_measure", lang, client_id)


    def activity_form(existing: dict | None, form_key: str):
        a = existing or {}
        aid = a.get("id")

        with st.form(form_key):
            name = st.text_input("Activity name", value=a.get("name") or "")
            purpose = st.text_area("Purpose", value=a.get("purpose") or "", height=70)

            col_a, col_b = st.columns(2)
            with col_a:
                basis = st.selectbox(
                    "Legal basis (Art. 6)",
                    options=basis_codes,
                    index=basis_codes.index(a["legal_basis"]) if a.get("legal_basis") in basis_codes else 0,
                    format_func=lambda c: basis_labels.get(c, c),
                )
                note = INV.note_for("legal_basis", basis, lang, client_id)
                if note:
                    st.caption(note)
            with col_b:
                ctrl = st.selectbox(
                    "Your role",
                    options=role_codes,
                    index=role_codes.index(a["controller_role"]) if a.get("controller_role") in role_codes else 0,
                    format_func=lambda c: role_labels.get(c, c),
                )

            li_note = st.text_area(
                "Balancing test",
                value=a.get("legitimate_interest_note") or "",
                height=70,
                help="Required for legitimate interests: your interest, why the "
                     "processing is necessary, and why it does not override the "
                     "individual's rights.",
            )

            subjects = st.multiselect(
                "Categories of data subject", options=subj_codes,
                default=[c for c in (a.get("data_subject_categories") or []) if c in subj_codes],
                format_func=lambda c: subj_labels.get(c, c),
            )
            categories = st.multiselect(
                "Categories of personal data", options=data_codes,
                default=[c for c in (a.get("data_categories") or []) if c in data_codes],
                format_func=lambda c: data_labels.get(c, c),
            )

            specials = st.multiselect(
                "Special categories (Art. 9)", options=spec_codes,
                default=[c for c in (a.get("special_categories") or []) if c in spec_codes],
                format_func=lambda c: spec_labels.get(c, c),
                help="Sick leave and workplace accident records count as health data.",
            )
            art9 = st.selectbox(
                "Art. 9(2) condition",
                options=[None] + art9_codes,
                index=(art9_codes.index(a["art9_condition"]) + 1) if a.get("art9_condition") in art9_codes else 0,
                format_func=lambda c: "—" if c is None else art9_labels.get(c, c),
                help="Required whenever special category data is selected.",
            )
            criminal = st.multiselect(
                "Criminal convictions (Art. 10)", options=crim_codes,
                default=[c for c in (a.get("criminal_data") or []) if c in crim_codes],
                format_func=lambda c: crim_labels.get(c, c),
            )

            col_c, col_d = st.columns(2)
            with col_c:
                retention = st.text_input("Retention period", value=a.get("retention_period") or "")
            with col_d:
                retention_basis = st.text_input(
                    "Why that period", value=a.get("retention_basis") or "",
                    help="The rule or reason — a statutory limitation period, a contract term.",
                )
            if not (a.get("retention_period") or "").strip():
                _rp = INV.principle("retention", lang)
                if _rp:
                    st.caption(_rp["body"])

            measures = st.multiselect(
                "Security measures", options=sec_codes,
                default=[c for c in (a.get("security_measures") or []) if c in sec_codes],
                format_func=lambda c: sec_labels.get(c, c),
            )

            chosen_systems = st.multiselect(
                "Systems used for this activity",
                options=list(system_name.keys()),
                default=STORE.systems_for_activity(links, aid) if aid else [],
                format_func=lambda i: system_name.get(i, i),
            )

            notes = st.text_area("Notes", value=a.get("notes") or "", height=60)

            saved = st.form_submit_button("Save activity", type="primary")

        if saved:
            row = {
                "name": name, "purpose": purpose, "legal_basis": basis,
                "legitimate_interest_note": li_note, "controller_role": ctrl,
                "data_subject_categories": subjects, "data_categories": categories,
                "special_categories": specials, "art9_condition": art9,
                "criminal_data": criminal, "retention_period": retention,
                "retention_basis": retention_basis, "security_measures": measures,
                "notes": notes,
            }
            new_id, errs = STORE.save_activity(row, chosen_systems, user_id, client_id, aid)
            if errs:
                for e in errs:
                    st.error(e)
            else:
                st.success("Saved.")
                st.rerun()


    for a in activities:
        flags = []
        if a.get("special_categories"):
            flags.append("Art. 9")
        if a["id"] not in {l["activity_id"] for l in links}:
            flags.append("no system linked")
        title = a["name"] + (f"  ·  {' · '.join(flags)}" if flags else "")

        with st.expander(title):
            activity_form(a, f"inv_act_{a['id']}")
            if st.button("Delete this activity", key=f"inv_del_{a['id']}"):
                errs = STORE.delete_activity(a["id"])
                for e in errs:
                    st.error(e)
                if not errs:
                    st.rerun()

    st.divider()
    with st.expander("Add a processing activity", expanded=not activities):
        activity_form(None, "inv_act_new")

    if ready["activity_gaps"]:
        st.warning("Incomplete for RoPA purposes:\n\n- " + "\n- ".join(ready["activity_gaps"]))
