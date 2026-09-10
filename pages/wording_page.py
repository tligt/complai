"""
pages/wording.py — S29A. The prose RECOSA cannot derive.

Five sections that go into the incident response plan and the business
continuity plan. RECOSA drafts each one; the client edits it; it is then merged
like any other field.

WHY THIS IS A PAGE AND NOT PART OF GENERATION
---------------------------------------------
Tier 2 means a template with client-authored prose in it, not a template a
model fills in at render time.

Generating the prose during generation would mean every regeneration produced
different text, nothing was reviewable before it landed in a document, and a
lawyer reviewing a template reviewed a shape rather than a document. That is
the whole of template-first (D-01).

So the LLM runs here, at authoring time, where a person sees the output and
owns it before it reaches anything. Same category as the S26C translation
drafts: assistance, under review, stored.

The draft is a STARTING POINT and the page says so. D-43/D-44: RECOSA supplies
something defensible, the client owns the answer, and it is not scored.
"""

import streamlit as st

import draft_inserts
from auth import get_user_id
from database import get_supabase, log_audit_event
from template_nis2 import INSERTS

st.title("Incident and continuity wording")
st.caption(
    "Five short sections that go into your incident response plan and your "
    "business continuity plan. RECOSA drafts each one; you correct it. What "
    "you save here is what appears in the documents."
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

_filled = sum(1 for k in INSERTS if (client.get(k) or "").strip())
st.progress(_filled / len(INSERTS), text=f"{_filled} of {len(INSERTS)} written")

if _filled < len(INSERTS):
    st.info(
        "Documents that use a section you have not written yet will refuse to "
        "generate rather than produce a placeholder. A continuity plan with "
        "**[to complete]** where the testing section should be is worse than "
        "no continuity plan, because it looks finished."
    )

st.divider()

for key, spec in INSERTS.items():
    current = client.get(key) or ""
    done = bool(current.strip())

    with st.expander(
        f"{'✅' if done else '⚪'}  {spec['label']}",
        expanded=not done,
    ):
        st.caption(spec["prompt"])

        draft_key = f"draft_{key}"
        # A drafted suggestion lives in session state until saved. Writing it
        # straight to the client record would make a machine's first attempt
        # the client's own statement without anyone reading it — which is what
        # the review step exists to prevent.
        pending = st.session_state.get(draft_key)

        if pending:
            st.markdown("**Suggested draft**")
            st.info(pending)
            d1, d2 = st.columns(2)
            if d1.button("Use this", key=f"use_{key}", type="primary"):
                st.session_state[f"text_{key}"] = pending
                # Drop the WIDGET key so the text area re-initialises.
                #
                # Streamlit ignores value= once a widget key exists in session
                # state. Setting text_{key} and rerunning changed nothing: the
                # box kept its old empty value and the save wrote that.
                #
                # Fourth instance of this in one week — the inventory
                # translation boxes, the activity selector, the adoption
                # control, and now this. Anything whose value= must change
                # after a rerun needs its key cleared, or it will not.
                st.session_state.pop(f"ta_{key}", None)
                st.session_state.pop(draft_key, None)
                st.rerun()
            if d2.button("Discard", key=f"drop_{key}"):
                st.session_state.pop(draft_key, None)
                st.session_state.pop(f"text_{key}", None)
                st.rerun()
            st.caption(
                "Read it before using it. It is a starting point written from "
                "the regulation and what RECOSA knows about you — it may "
                "describe something you do not actually do, and it becomes "
                "your statement once you save it."
            )

        text = st.text_area(
            "What you do",
            value=st.session_state.get(f"text_{key}", current),
            key=f"ta_{key}",
            height=140,
            label_visibility="collapsed",
        )

        c1, c2, c3 = st.columns([1, 1, 3])

        if c1.button("Draft it for me", key=f"gen_{key}",
                     use_container_width=True,
                     disabled=bool(pending)):
            with st.spinner("Reading the regulation and drafting…"):
                out = draft_inserts.draft(
                    key, client, language="en",
                    user_id=user_id, client_id=client_id,
                )
            if out:
                st.session_state[draft_key] = out
                st.rerun()
            else:
                st.warning(
                    "Could not draft this one. Write it in your own words — "
                    "two or three sentences is enough."
                )

        if c2.button("Save", key=f"save_{key}", type="primary",
                     use_container_width=True):
            try:
                get_supabase().table("clients").update(
                    {key: text.strip() or None}
                ).eq("id", client_id).execute()

                # Audited: this text ends up in a document that may be shown to
                # an authority, and who wrote it and when is part of the
                # record. Only on change — a trail that logs every page save is
                # one nobody reads.
                if text.strip() != current.strip():
                    log_audit_event(
                        company_id=client_id, user_id=user_id,
                        event_type="document", event_subtype="wording_changed",
                        resource_id=key,
                        summary=f"{spec['label']} updated",
                        metadata={"insert": key,
                                  "was_empty": not current.strip()},
                    )
                st.session_state.pop(f"text_{key}", None)
                st.session_state.pop(f"ta_{key}", None)
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")

        if done and not pending:
            c3.caption("Appears in your incident and continuity documents.")

st.divider()
st.caption(
    "These are your words, not RECOSA's. Nothing here is scored — the "
    "documents reproduce what you have written, and a section describing "
    "something you do not do is worse than one admitting it is not yet in "
    "place."
)
