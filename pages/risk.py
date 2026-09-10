"""
pages/risk.py — S30. DPIAs and NIS2 risk assessments.

RENDERING ONLY (D-61). Every verdict comes from risk_assessment, all I/O from
risk_store. This file decides what to show, never what is true.

TWO REGULATIONS, ONE SCREEN, DIFFERENT MEANINGS
-----------------------------------------------
The register and the workflow are shared. What a risk IS, and what an
unacceptable one leads to, are not (D-85):

    GDPR   risk to the rights and freedoms of natural persons
           high residual risk -> Art. 36 prior consultation, BEFORE processing
    NIS2   risk to network and information systems
           high residual risk -> a named person accepts it, or nobody has

So the catalogue changes, the language changes, and the conclusion at the
bottom changes. The columns do not.

THE TRIGGER LIST IS THE FIRST THING ON THE PAGE
-----------------------------------------------
Most SMEs never ask whether they need a DPIA. Telling them which activities
trigger one is worth more than the document, because it is the part they get
wrong — usually by not realising the question applies to them.
"""

from datetime import date

import streamlit as st

import inventory as INV
import risk_assessment as RA
import risk_store as RS
from auth import get_user_id
from database import get_supabase

st.title("Risk assessments")
st.caption(
    "Data protection impact assessments, and the cybersecurity risk "
    "assessment NIS2 asks for."
)

user_id = get_user_id()
if not user_id:
    st.error("Please log in.")
    st.stop()

try:
    client = (get_supabase().table("clients").select("*")
              .eq("user_id", user_id).single().execute().data) or {}
except Exception as e:
    st.error(f"Could not load your profile: {e}")
    st.stop()
if not client:
    st.warning("Please complete your company profile first.")
    st.stop()

client_id = client["id"]
regulations = client.get("regulations") or ["GDPR"]
lang = st.session_state.get("ui_language") or client.get("ui_language") or "en"

try:
    import inventory_store as INVS
    activities = INVS.load_activities(user_id, client_id)
    systems = INVS.load_systems(user_id, client_id)
except Exception:
    activities, systems = [], []

# ── Which activities need a DPIA ──────────────────────────────────────────
if "GDPR" in regulations:
    flagged = RA.activities_needing_dpia(activities)
    st.subheader("Which of your activities need a DPIA")

    if not activities:
        st.info("No processing activities recorded yet.")
    elif flagged:
        st.warning(
            f"**{len(flagged)} of your {len(activities)} activities** meet at "
            "least one criterion."
        )
        for f in flagged:
            with st.expander(f"{f['activity_name']} — {len(f['triggers'])} criteria"):
                for t in f["triggers"]:
                    st.markdown(f"**{t['article']}** — {t['reason']}")
                st.caption(
                    "Two or more criteria usually means a DPIA is expected. "
                    "Where a criterion turns on scale, only you know the "
                    "numbers."
                )
    else:
        st.info("No activity meets a criterion RECOSA can check.")

    # NEVER "no DPIA needed". Art. 35(1) is a general standard and Art. 35(4)
    # lets each authority extend the list, so the absence of a visible trigger
    # is the absence of a check, not a negative result.
    st.caption(
        "This checks the criteria RECOSA can see in your inventory. Your "
        "supervisory authority publishes its own list under Art. 35(4), and "
        "Art. 35(1) applies generally — an activity with no criterion above "
        "may still need one."
    )
    st.divider()

# ── Existing assessments ──────────────────────────────────────────────────
assessments = RS.load_assessments(client_id, user_id)

_open = st.session_state.get("risk_open")
if _open:
    a = next((x for x in assessments if x["id"] == _open), None)
    if not a:
        st.session_state.pop("risk_open", None)
        st.rerun()

    items = RS.load_items(a["id"], user_id)
    is_dpia = a["regulation"] == "GDPR"
    vocab = "dpia_risk" if is_dpia else "nis2_risk"
    codes, labels = INV.options_for(vocab, lang, client_id)

    if st.button("← All assessments"):
        st.session_state.pop("risk_open", None)
        st.rerun()

    st.subheader(a["title"])
    st.caption(
        ("Risks to the rights and freedoms of the people whose data this "
         "processing involves — not risks to the business."
         if is_dpia else
         "Risks to the systems and services you depend on.")
    )

    counts = RA.summarise(items)
    c1, c2, c3 = st.columns(3)
    c1.metric("Risks recorded", counts["total"])
    c2.metric("Assessed after mitigation", counts["assessed"])
    c3.metric("Still to assess", counts["unassessed"])

    # ── Add a risk ────────────────────────────────────────────────────────
    with st.expander("Add a risk", expanded=not items):
        with st.form(f"add_{a['id']}"):
            code = st.selectbox(
                "What could happen", options=codes,
                format_func=lambda c: labels.get(c, c),
            )
            note = INV.note_for(vocab, code, lang, client_id) if code else ""
            if note:
                st.caption(note)
            desc = st.text_input(
                "In your case", placeholder="How this applies to you",
                help="What makes this real for your organisation, in a line.",
            )
            l1, l2 = st.columns(2)
            lik = l1.select_slider(
                "How likely", options=[1, 2, 3, 4], value=2,
                format_func=lambda v: RA.level_label(v, lang),
            )
            sev = l2.select_slider(
                "How bad" if not is_dpia else "How bad for the person",
                options=[1, 2, 3, 4], value=2,
                format_func=lambda v: RA.level_label(v, lang),
            )
            if st.form_submit_button("Add", type="primary"):
                RS.save_item(user_id, client_id, a["id"],
                             catalogue_code=code, description=desc,
                             likelihood=lik, severity=sev)
                st.rerun()

    # ── The register ──────────────────────────────────────────────────────
    for it in items:
        label = labels.get(it["catalogue_code"], it["catalogue_code"])
        head = f"**{label}**"
        if it.get("residual_severity"):
            head += (f"  ·  after measures: "
                     f"{RA.level_label(it['residual_severity'], lang)}")
        else:
            head += "  ·  :orange[not assessed after measures]"

        with st.expander(head):
            if it.get("description"):
                st.caption(it["description"])
            st.markdown(
                f"Before measures — likelihood "
                f"**{RA.level_label(it.get('likelihood'), lang)}**, "
                f"severity **{RA.level_label(it.get('severity'), lang)}**"
            )

            with st.form(f"it_{it['id']}"):
                controls = st.text_area(
                    "What already reduces this",
                    value=it.get("existing_controls") or "", height=70)
                measures = st.text_area(
                    "What you will do about it",
                    value=it.get("additional_measures") or "", height=70)

                r1, r2 = st.columns(2)
                rlik = r1.select_slider(
                    "Likelihood after measures", options=[1, 2, 3, 4],
                    value=it.get("residual_likelihood") or it.get("likelihood") or 2,
                    format_func=lambda v: RA.level_label(v, lang),
                )
                rsev = r2.select_slider(
                    "Severity after measures", options=[1, 2, 3, 4],
                    value=it.get("residual_severity") or it.get("severity") or 2,
                    format_func=lambda v: RA.level_label(v, lang),
                )

                # NIS2 only. There is no Art. 36 there — Art. 20(1) puts
                # approval of the measures on the management body, so what a
                # high residual risk needs is a named person accepting it.
                accepted = None
                if not is_dpia:
                    accepted = st.text_input(
                        "Accepted by (name and role)",
                        value=it.get("accepted_by") or "",
                        help="Required for a high residual risk. An "
                             "unattributed acceptance is a decision nobody made.",
                    )

                s1, s2 = st.columns([3, 1])
                if s1.form_submit_button("Save", type="primary"):
                    fields = {
                        "existing_controls": controls,
                        "additional_measures": measures,
                        "residual_likelihood": rlik,
                        "residual_severity": rsev,
                    }
                    if accepted is not None:
                        fields["accepted_by"] = accepted
                    RS.save_item(user_id, client_id, a["id"],
                                 item_id=it["id"], **fields)
                    st.rerun()
                if s2.form_submit_button("Remove"):
                    RS.delete_item(it["id"], user_id)
                    st.rerun()

    # ── The conclusion ────────────────────────────────────────────────────
    st.divider()
    if is_dpia:
        verdict = RA.consultation_needed(items)
        # required is None for an empty assessment — neither required nor not.
        if verdict["required"] is None:
            st.info(verdict["detail"])
        elif verdict["required"]:
            # The point of the whole document. Most templates bury it.
            st.error(
                "**Prior consultation is required.** "
                + verdict["detail"]
                + "\n\nThis does not stop you producing the DPIA — it is "
                "exactly the document Art. 36 expects to exist. It stops you "
                "starting the processing."
            )
        elif verdict["unresolved"]:
            st.warning(verdict["detail"])
        else:
            st.success(verdict["detail"])

        # Art. 35(2): "where a data protection officer has been designated,
        # the controller shall seek his or her advice". No DPO, no obligation —
        # and asking a client without one to answer it invites a meaningless
        # answer in a document an authority may read.
        _has_dpo = bool((client.get("dpo_name") or "").strip()
                        or (client.get("dpo_email") or "").strip())

    if is_dpia and _has_dpo:
        st.markdown("**Art. 35(2) — the DPO's advice**")
        with st.form(f"dpo_{a['id']}"):
            _opts = [None, True, False]
            consulted = st.selectbox(
                "Was the DPO's advice sought?", options=_opts,
                index=_opts.index(a.get("dpo_consulted"))
                if a.get("dpo_consulted") in _opts else 0,
                format_func=lambda v: {None: "Not answered", True: "Yes",
                                       False: "No"}[v],
            )
            advice = st.text_area(
                "Their advice", value=a.get("dpo_advice") or "", height=80,
                help="What they said about THIS assessment — whether the "
                     "measures are adequate, and whether they disagreed. A "
                     "recorded disagreement that was overruled is exactly what "
                     "an authority looks for.",
            )
            if st.form_submit_button("Save"):
                # The result was ignored, so a failed save looked identical to
                # a successful one: the page just reloaded.
                if RS.set_dpo_advice(a["id"], user_id, consulted, advice):
                    st.success("Saved.")
                    st.rerun()
                else:
                    st.error("Could not save.")

    if not is_dpia:
        verdict = RA.nis2_unaccepted(items)
        (st.warning if verdict["unaccepted"] else st.success)(verdict["detail"])

    if a["status"] == "draft":
        _unassessed = [it for it in items if it.get("residual_severity") is None]
        st.markdown("---")
        if _unassessed:
            # Warned, not blocked — same reasoning as Art. 36. An incomplete
            # assessment is still a document someone may need to produce, and
            # refusing to finish it is the wrong instinct. Completing it
            # silently is worse than the empty-assessment problem, because it
            # looks finished.
            st.warning(
                f"**{len(_unassessed)} risk(s) have not been assessed after "
                "measures.** Marking this complete records a conclusion the "
                "register cannot support — whether the residual risk is "
                "acceptable is the question this document exists to answer."
            )
        if st.button("Mark complete", type="primary"):
            RS.complete_assessment(
                a["id"], user_id, client_id,
                consultation_required=bool(
                    RA.consultation_needed(items)["required"]
                ) if is_dpia else False,
            )
            st.rerun()

else:
    # ── The list ──────────────────────────────────────────────────────────
    if assessments:
        for a in assessments:
            cols = st.columns([5, 1])
            cols[0].markdown(
                f"**{a['title']}**  ·  {a['regulation']}  ·  "
                + ("draft" if a["status"] == "draft" else a["status"])
            )
            if cols[1].button("Open", key=f"open_{a['id']}",
                              use_container_width=True):
                st.session_state["risk_open"] = a["id"]
                st.rerun()
    else:
        st.info("No assessments yet.")

    st.divider()
    st.subheader("Start one")
    with st.form("new_assessment"):
        reg = st.selectbox(
            "What kind", options=[r for r in ("GDPR", "NIS2")
                                  if r in regulations],
            format_func=lambda r: (
                "Data protection impact assessment (GDPR)" if r == "GDPR"
                else "Cybersecurity risk assessment (NIS2)"),
        )
        title = st.text_input(
            "What is it about",
            placeholder="e.g. Recruitment and candidate screening",
            help="A DPIA is about a type of processing, not about the whole "
                 "company. One per thing you are assessing.",
        )
        picked = st.multiselect(
            "Which activities does it cover",
            options=[a["id"] for a in activities],
            format_func=lambda i: next(
                (x.get("name") or i for x in activities if x["id"] == i), i),
        )
        # Validated on SUBMIT, not through disabled=.
        #
        # Widgets inside st.form do not trigger a rerun, so `disabled` is
        # evaluated when the form first renders — when `title` is empty — and
        # never re-evaluated. The button stayed dead however much was typed.
        # Same constraint as the note in pages/inventory.py about the system
        # multiselect sitting outside its form.
        if st.form_submit_button("Start", type="primary"):
            if not title.strip():
                st.error("Give it a name — what is this assessment about?")
            else:
                new_id = RS.create_assessment(
                    user_id, client_id, reg, title.strip(), activity_ids=picked)
                if new_id:
                    st.session_state["risk_open"] = new_id
                    st.rerun()
                else:
                    st.error("Could not start the assessment.")
