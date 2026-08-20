"""
pages/inventory.py — vendor, activity and controller intake (S24, amended S25/S26).

Three tabs, three deliberately different interaction models.

Systems use st.data_editor: every field is scalar, and the task is
*confirmation* rather than authoring — the client ticks catalogue vendors and
corrects the defaults. A grid is right for that, and it is the difference
between two minutes and twenty.

Processing activities use list-plus-detail: a read-only summary of every row,
and one form for the row currently selected. Every interesting field is an
enumerated multi-select, and st.data_editor has no multiselect column type —
the alternative inside a grid is comma-separated free text, which would put
uncontrolled vocabulary into the exact columns the RoPA, the gap scoring and
the Art. 9 flag all depend on.

Controllers (Art. 30(2) counterparties) use the same list-plus-detail shape.

── S25 amendments ────────────────────────────────────────────────────────
Two silent bugs fixed: client_id was read only from session state and was NULL
for Starter/Professional clients; lang read _client["language"], a key that has
never existed, so the page was English-only since it shipped.

── S26 amendments ────────────────────────────────────────────────────────
1. LIST-PLUS-DETAIL. Every activity used to render a full st.form inside an
   expander — about a dozen widgets each. That is fine for the four or five
   activities a catalogue seed produces, which is what it was built against.
   A real Art. 30 record is 15-60 activities (CNIL's own guidance), and this
   is the sprint that pushes clients there. At 40 activities the old shape
   instantiated ~500 widgets per rerun. Now: one form, always.

2. PER-LINK ROLES. The form had no control for activity_systems.role, so
   _reconcile_links hardcoded 'processor' and every hand-linked vendor was
   asserted a processor with no evidence — a false statement in Art. 30(1)(d).
   The system multiselect sits OUTSIDE the form on purpose: a widget inside a
   form does not rerun on change, so the per-system role controls could never
   appear in response to a selection made in the same form.

3. CONTROLLERS TAB. Art. 30(2)(a) requires a processor to name each controller
   it acts for. Nowhere to record that existed before this sprint.

4. BLOCKING vs GAPS. readiness() now separates incomplete-but-truthful from
   would-be-wrong. Only the second stops a RoPA being generated.
"""

import pandas as pd
import streamlit as st

from auth import get_user_id
from database import load_clients
import inventory as INV
import inventory_store as STORE

st.title("Systems, activities and controllers")
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
            "Select a client before editing the inventory. Systems, processing "
            "activities and controllers belong to a specific company."
        )
        st.stop()
    else:
        st.info("Create a client profile before filling in your inventory.")
        st.stop()

# Language for labels. This is UI chrome, so it should follow the user once a
# user language column exists. Until then the first document language is the
# closest available signal.
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
counterparties = STORE.load_counterparties(user_id, client_id)
cp_links = STORE.load_counterparty_links(user_id, client_id)

system_name = {s["id"]: s["name"] for s in systems}
counterparty_name = {c["id"]: c["legal_name"] for c in counterparties}

ready = STORE.readiness(activities, systems, links, cp_links)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Systems", ready["systems"])
c2.metric("Activities", ready["activities"])
c3.metric("Ready for RoPA", f"{ready['complete_activities']}/{ready['activities']}")
c4.metric("Controllers", len(counterparties))

# The CNIL recommends two separate registers where an organisation is both
# controller and processor. Saying so here, where the split is visible, beats
# discovering it at generation time.
if ready["processor_activities"] and ready["controller_activities"]:
    st.info(
        f"You act as controller for {ready['controller_activities']} "
        f"{'activity' if ready['controller_activities'] == 1 else 'activities'} and as "
        f"processor for {ready['processor_activities']}. These produce two separate "
        "records — the supervisory authority expects them kept apart."
    )

# Blocking items are not gaps. A missing security measure leaves the record
# incomplete but truthful; an Art. 9 activity with no condition, or a transfer
# with no safeguard, would make it wrong. Only the second stops generation.
if ready["blocking"]:
    st.error(
        "**These would make your record inaccurate and must be resolved before "
        "it can be generated:**\n\n- " + "\n- ".join(ready["blocking"])
    )

# The rules behind the pre-filled values, readable where the values are.
# Without this a client sees a blank retention field and reads it as a bug
# rather than as a deliberate refusal to guess at their national law.
_principles = INV.principles_for_display(lang)
if _principles:
    with st.expander("How this inventory is filled in"):
        for p in _principles:
            st.markdown(f"**{p['title']}**")
            st.caption(p["body"])

tab_systems, tab_activities, tab_controllers = st.tabs(
    ["Systems", "Processing activities", "Controllers you process for"]
)


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
                    # S26: the seed deliberately inserts rows that fail
                    # validation so the client is not blocked at the tick.
                    # Previously the only trace was a note on the row.
                    for i in res.get("incomplete", []):
                        st.warning(f"Needs completing — {i}")
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
    sysrole_codes, sysrole_labels = INV.options_for("system_role", lang, client_id)
    subj_codes, subj_labels = INV.options_for("data_subject_category", lang, client_id)
    data_codes, data_labels = INV.options_for("data_category", lang, client_id)
    spec_codes, spec_labels = INV.options_for("special_category", lang, client_id)
    art9_codes, art9_labels = INV.options_for("art9_condition", lang, client_id)
    crim_codes, crim_labels = INV.options_for("criminal_data", lang, client_id)
    sec_codes, sec_labels = INV.options_for("security_measure", lang, client_id)

    blocking_names = {b.split(":")[0] for b in ready["blocking"]}
    gap_names = {g.split(":")[0] for g in ready["activity_gaps"]}

    # --- Summary -----------------------------------------------------------
    # Read-only, all rows, no widgets. This is what replaced the expander-per-
    # activity loop: the whole record is visible at a glance and only the
    # selected row costs anything to render.
    if activities:
        summary = pd.DataFrame([
            {
                "Activity": a["name"],
                "Your role": role_labels.get(a.get("controller_role"), a.get("controller_role") or "—"),
                "Legal basis": basis_labels.get(a.get("legal_basis"), a.get("legal_basis") or "—"),
                "Art. 9": "Yes" if a.get("special_categories") else "",
                "Systems": len(STORE.systems_for_activity(links, a["id"])),
                "Status": (
                    "Must fix" if a["name"] in blocking_names
                    else "Incomplete" if a["name"] in gap_names
                    else "Complete"
                ),
            }
            for a in activities
        ])
        st.dataframe(summary, hide_index=True, width="stretch")
    else:
        st.info("No processing activities yet. Add one below, or seed them from a catalogue tool.")

    st.divider()

    # --- Selection ---------------------------------------------------------
    NEW = "__new__"
    options = [NEW] + [a["id"] for a in activities]
    by_id = {a["id"]: a for a in activities}

    selected = st.selectbox(
        "Edit an activity",
        options=options,
        format_func=lambda i: "➕ Add a new activity" if i == NEW else by_id[i]["name"],
        key="inv_act_select",
    )

    existing = None if selected == NEW else by_id[selected]
    aid = None if existing is None else existing["id"]
    form_key = f"inv_act_form_{aid or 'new'}"

    # --- Systems and their roles ------------------------------------------
    # OUTSIDE the form on purpose. A widget inside st.form does not trigger a
    # rerun when changed, so role controls for the systems just selected could
    # never appear until after a submit. Selection outside, roles inside.
    st.markdown("**Systems used for this activity**")
    chosen_systems = st.multiselect(
        "Systems",
        options=list(system_name.keys()),
        default=STORE.systems_for_activity(links, aid) if aid else [],
        format_func=lambda i: system_name.get(i, i),
        key=f"inv_act_systems_{aid or 'new'}",
        label_visibility="collapsed",
    )
    if chosen_systems:
        st.caption(
            "The role each vendor plays for *this* activity. A vendor can be a "
            "processor for one activity and a joint controller for another, so "
            "the role belongs here rather than on the system."
        )

    with st.form(form_key):
        name = st.text_input("Activity name", value=(existing or {}).get("name") or "")
        purpose = st.text_area("Purpose", value=(existing or {}).get("purpose") or "", height=70)

        a = existing or {}

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

        # Per-system roles, driven by the selection made above.
        existing_roles = STORE.roles_for_activity(links, aid) if aid else {}
        system_roles: dict[str, str] = {}
        if chosen_systems:
            for sid in chosen_systems:
                current = existing_roles.get(sid, STORE.ROLE_UNKNOWN)
                idx = sysrole_codes.index(current) if current in sysrole_codes else 0
                system_roles[sid] = st.selectbox(
                    f"Role — {system_name.get(sid, sid)}",
                    options=sysrole_codes,
                    index=idx,
                    format_func=lambda c: sysrole_labels.get(c, c),
                    key=f"inv_act_role_{aid or 'new'}_{sid}",
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

        # --- Art. 30(2) ----------------------------------------------------
        # Always shown rather than revealed when the role is 'processor':
        # 'Your role' is a widget inside this same form, so changing it cannot
        # rerun the form to reveal these. The caption carries the condition.
        st.markdown("**Controllers you carry out this activity for**")
        st.caption(
            "Required when your role above is *Processor* (Art. 30(2)(a)). "
            "Name each controller, or say where the maintained list is kept — "
            "the record must be producible on request."
        )
        chosen_cps = st.multiselect(
            "Controllers",
            options=list(counterparty_name.keys()),
            default=STORE.counterparties_for_activity(cp_links, aid) if aid else [],
            format_func=lambda i: counterparty_name.get(i, i),
            label_visibility="collapsed",
            help="Add controllers in the 'Controllers you process for' tab.",
        )
        register_note = st.text_input(
            "Or: where the controller list is maintained",
            value=a.get("counterparty_register_note") or "",
            placeholder="e.g. Customer register in HubSpot, exportable on request",
            help="Use this instead of naming each controller when the list "
                 "changes constantly. It must point at a list you can actually "
                 "produce if an authority asks.",
        )

        notes = st.text_area("Notes", value=a.get("notes") or "", height=60)

        col_save, col_del = st.columns([3, 1])
        with col_save:
            saved = st.form_submit_button("Save activity", type="primary")
        with col_del:
            deleted = st.form_submit_button("Delete") if aid else False

    if saved:
        row = {
            "name": name, "purpose": purpose, "legal_basis": basis,
            "legitimate_interest_note": li_note, "controller_role": ctrl,
            "data_subject_categories": subjects, "data_categories": categories,
            "special_categories": specials, "art9_condition": art9,
            "criminal_data": criminal, "retention_period": retention,
            "retention_basis": retention_basis, "security_measures": measures,
            "counterparty_register_note": register_note, "notes": notes,
        }
        new_id, errs = STORE.save_activity(
            row, system_roles, user_id, client_id, aid,
            counterparty_ids=chosen_cps,
        )
        if errs:
            for e in errs:
                st.error(e)
        else:
            st.success("Saved.")
            st.session_state.pop("inv_act_select", None)
            st.rerun()

    if deleted and aid:
        errs = STORE.delete_activity(aid)
        for e in errs:
            st.error(e)
        if not errs:
            st.session_state.pop("inv_act_select", None)
            st.rerun()

    if ready["activity_gaps"]:
        st.warning("Incomplete for RoPA purposes:\n\n- " + "\n- ".join(ready["activity_gaps"]))


# ── Controllers you process for (Art. 30(2)) ──────────────────────────────

with tab_controllers:
    st.caption(
        "When you process personal data on someone else's instructions — "
        "hosting a client's data, running payroll for another company — you "
        "are a processor, and Art. 30(2) requires you to record who you act "
        "for. This is separate from your vendors."
    )

    cp_dpa_codes, cp_dpa_labels = INV.options_for("dpa_status", lang, client_id)

    activities_by_cp: dict[str, int] = {}
    for l in cp_links:
        activities_by_cp[l["counterparty_id"]] = activities_by_cp.get(l["counterparty_id"], 0) + 1

    if counterparties:
        st.dataframe(
            pd.DataFrame([
                {
                    "Controller": c["legal_name"],
                    "Country": c.get("country") or "—",
                    "Contact": c.get("contact_email") or "—",
                    "DPA": cp_dpa_labels.get(c.get("dpa_status"), c.get("dpa_status") or "—"),
                    "Activities": activities_by_cp.get(c["id"], 0),
                }
                for c in counterparties
            ]),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(
            "No controllers recorded. If you only ever decide the purposes of "
            "your own processing, you are a controller throughout and this tab "
            "stays empty."
        )

    st.divider()

    CP_NEW = "__new__"
    cp_options = [CP_NEW] + [c["id"] for c in counterparties]
    cp_by_id = {c["id"]: c for c in counterparties}

    cp_selected = st.selectbox(
        "Edit a controller",
        options=cp_options,
        format_func=lambda i: "➕ Add a controller" if i == CP_NEW else cp_by_id[i]["legal_name"],
        key="inv_cp_select",
    )

    cp_existing = None if cp_selected == CP_NEW else cp_by_id[cp_selected]
    cp_id = None if cp_existing is None else cp_existing["id"]
    c = cp_existing or {}

    with st.form(f"inv_cp_form_{cp_id or 'new'}"):
        cp_legal = st.text_input(
            "Legal name", value=c.get("legal_name") or "",
            help="The registered entity, not the trading name — this is what "
                 "appears in the record and in any processing agreement.",
        )
        cp_trading = st.text_input("Trading name", value=c.get("trading_name") or "")

        col_1, col_2 = st.columns(2)
        with col_1:
            cp_contact = st.text_input("Contact name", value=c.get("contact_name") or "")
        with col_2:
            cp_email = st.text_input("Contact email", value=c.get("contact_email") or "")

        cp_address = st.text_area(
            "Registered address", value=c.get("registered_address") or "", height=70
        )
        cp_country = st.text_input(
            "Country", value=c.get("country") or "", help="ISO code, e.g. BE, FR, DE."
        )

        col_3, col_4 = st.columns(2)
        with col_3:
            cp_status = st.selectbox(
                "Processing agreement",
                options=cp_dpa_codes,
                index=cp_dpa_codes.index(c["dpa_status"]) if c.get("dpa_status") in cp_dpa_codes else 0,
                format_func=lambda x: cp_dpa_labels.get(x, x),
            )
        with col_4:
            _signed = c.get("dpa_signed_on")
            cp_signed = st.date_input(
                "Signed on",
                value=pd.to_datetime(_signed).date() if _signed else None,
                format="YYYY-MM-DD",
            )

        cp_url = st.text_input("Agreement link", value=c.get("dpa_url") or "")
        cp_notes = st.text_area("Notes", value=c.get("notes") or "", height=60)

        col_s, col_d = st.columns([3, 1])
        with col_s:
            cp_saved = st.form_submit_button("Save controller", type="primary")
        with col_d:
            cp_deleted = st.form_submit_button("Delete") if cp_id else False

    if cp_saved:
        cp_row = {
            "legal_name": cp_legal, "trading_name": cp_trading,
            "contact_name": cp_contact, "contact_email": cp_email,
            "registered_address": cp_address,
            "country": (cp_country or "").strip().upper() or None,
            "dpa_status": cp_status,
            "dpa_signed_on": cp_signed.isoformat() if cp_signed else None,
            "dpa_url": cp_url, "notes": cp_notes,
        }
        new_cp, cp_errs = STORE.save_counterparty(cp_row, user_id, client_id, cp_id)
        if cp_errs:
            for e in cp_errs:
                st.error(e)
        else:
            st.success("Saved.")
            st.session_state.pop("inv_cp_select", None)
            st.rerun()

    if cp_deleted and cp_id:
        # activity_counterparties cascades; the activities survive. Losing a
        # customer should not erase the record of what was processed for them.
        cp_errs = STORE.delete_counterparty(cp_id)
        for e in cp_errs:
            st.error(e)
        if not cp_errs:
            st.session_state.pop("inv_cp_select", None)
            st.rerun()
