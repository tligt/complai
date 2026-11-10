"""
pages/training.py — S60 (D-159). Skills matrix and training register.

RENDERING ONLY (D-61). Every state comes from training_rules, all I/O from
training_store, the PDFs from training_docs. This file decides what to show,
never what is true.

Evidence of a plan and of attendance, not of competence: said on the page and
in both documents, because a client who confuses the two is worse off than one
with no matrix.
"""
from i18n import tr  # S64 interface translation (D-164)

from datetime import date

import streamlit as st

import table_view as tv
import training_rules as TR
import training_store as TS
from active_client import can_edit_active, get_active_client
from auth import get_user_id
from display import plural
from guide import page_tip

st.title(tr("Training"))
page_tip("training")
st.caption(
    tr("Who needs which training, and who has a current session. Evidence of a "
    "plan and of attendance, not of competence. RECOSA does not give the training.")
)

user_id = get_user_id()
if not user_id:
    st.error(tr("Please log in."))
    st.stop()

client = get_active_client(user_id)
client_id = client["id"]
today = date.today()
editable = can_edit_active()

data = TS.load_all(client_id)
all_reqs = data["requirements"]
reqs = TR.applicable(all_reqs, client)
employees = data["employees"]
sessions = data["sessions"]
attendance = data["attendance"]
active = sorted([e for e in employees if TR.is_active(e, today)],
                key=lambda e: (e.get("name") or "").lower())
req_by_code = {r["code"]: r for r in reqs}

if not all_reqs:
    st.error(tr("The training requirements could not be loaded. Please try again later."))
    st.stop()
if not reqs:
    st.info(tr("None of this company's regulations asks for staff training that RECOSA tracks. "
            "Check the regulations on the Company profile."))
    st.stop()

mx = TR.matrix(active, reqs, sessions, attendance, today)
cov = TR.coverage(mx, reqs)

tab_matrix, tab_people, tab_sessions, tab_docs = st.tabs(
    [tr("Matrix"), f"People ({len(active)})", f"Sessions ({len(sessions)})", tr("Documents")])


def _fd(d) -> str:
    d = TR._d(d)
    return d.strftime("%d/%m/%Y") if d else ""


# ── Matrix ────────────────────────────────────────────────────────────────
with tab_matrix:
    # Three per row: five side by side broke the titles mid-word (10 Nov).
    _per_row = 3
    cols = [c for i in range(0, len(reqs), _per_row)
            for c in st.columns(_per_row)][:len(reqs)]
    for col, r in zip(cols, reqs):
        c = cov[r["code"]]
        ok = c[TR.CURRENT] + c[TR.EXPIRING]
        with col.container(border=True):
            st.markdown(f"**{r['label_en']}**")
            if r.get("applies_from") and r["applies_from"] > today:
                st.caption(f"Applies from {_fd(r['applies_from'])}")
            if c["required"]:
                st.metric(tr("Current"), f"{ok} / {c['required']}", label_visibility="collapsed")
                parts = []
                if c[TR.ABSENT]:
                    parts.append(f"{c[TR.ABSENT]} never trained")
                if c[TR.EXPIRED]:
                    parts.append(f"{c[TR.EXPIRED]} lapsed")
                if c[TR.EXPIRING]:
                    parts.append(f"{c[TR.EXPIRING]} lapsing soon")
                st.caption(" · ".join(parts) or "Everyone is current.")
            else:
                st.caption(tr("Nobody recorded needs it."))
            st.caption(f"{TR.AUDIENCES[r['audience']]} · {r['anchor']}", help=r["note_en"])

    if not active:
        st.info(tr("Record your people on the **People** tab to see who needs what."))
    else:
        rows = []
        for e in active:
            row = {"Person": e["name"], "Job title": e.get("job_title") or ""}
            for r in reqs:
                x = mx[e["id"]][r["code"]]
                txt = TR.STATE_ICON[x["state"]]
                if x.get("valid_until"):
                    txt += f" until {_fd(x['valid_until'])}"
                elif x["state"] == TR.ABSENT:
                    txt += " not trained"
                row[r["label_en"]] = txt
            rows.append(row)
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(f"🟢 current · 🟡 lapses within {TR.EXPIRING_DAYS} days · 🔴 lapsed · "
                   "⚪ never trained · – not required. A session counts for "
                   f"{reqs[0]['refresh_months']} months unless it says otherwise: RECOSA's "
                   "default, since the law asks for \"regular\" training without a number.")


# ── People ────────────────────────────────────────────────────────────────
_FLAGS = [
    ("handles_personal_data", "Handles personal data", "GDPR awareness."),
    ("uses_ai", "Uses or operates AI systems", "AI literacy (AI Act Art. 4)."),
    ("management_body", "Member of the management body", "NIS2 Art. 20(2) training."),
    ("ai_overseer", "Oversees a high-risk AI system", "AI Act Art. 26(2), from Dec 2027."),
]


def _person_form(key: str, e: dict | None = None) -> dict | None:
    e = e or {}
    with st.form(key, clear_on_submit=not e):
        a, b = st.columns(2)
        name = a.text_input(tr("Name"), value=e.get("name") or "")
        email = b.text_input(tr("Email (optional)"), value=e.get("email") or "")
        job = a.text_input(tr("Job title"), value=e.get("job_title") or "")
        dept = b.text_input(tr("Department"), value=e.get("department") or "")
        flags = {}
        fc = st.columns(len(_FLAGS))
        for col, (k, lbl, hlp) in zip(fc, _FLAGS):
            flags[k] = col.checkbox(lbl, value=bool(e.get(k, k == "handles_personal_data")),
                                    help=f"Decides: {hlp}")
        c, d = st.columns(2)
        started = c.date_input(tr("Started on (optional)"), value=TR._d(e.get("started_on")),
                               format="DD/MM/YYYY")
        left = d.date_input(tr("Left on (keeps their record)"), value=TR._d(e.get("left_on")),
                            format="DD/MM/YYYY")
        notes = st.text_input(tr("Notes"), value=e.get("notes") or "")
        if st.form_submit_button("Save" if e else "Add person", type="primary",
                                 disabled=not editable):
            if not name.strip():
                st.error(tr("A name is needed."))
                return None
            if started and left and left < started:
                st.error(tr("They cannot leave before they started."))
                return None
            return {"name": name, "email": email, "job_title": job, "department": dept,
                    **flags, "started_on": started, "left_on": left, "notes": notes}
    return None


with tab_people:
    if not employees:
        st.info(tr("No one recorded yet. Add people one by one, or paste a list below."))
    else:
        show_left = st.toggle(tr("Show people who have left"), value=False)
        listed = [e for e in employees if show_left or TR.is_active(e, today)]
        hit = tv.table(
            [{"id": e["id"], "cells": {
                "name": e["name"], "job": e.get("job_title"), "dept": e.get("department"),
                "needs": ", ".join(r["label_en"] for r in reqs if TR.needs(e, r)) or "—",
                "left": TR._d(e.get("left_on")),
            }, "actions": [{"id": "open", "label": "Edit", "icon": "✏️"}]} for e in listed],
            [{"key": "name", "label": "Name"}, {"key": "job", "label": "Job title"},
             {"key": "dept", "label": "Department"}, {"key": "needs", "label": "Needs"},
             {"key": "left", "label": "Left on", "kind": "date"}],
            key="training_people", current=st.session_state.get("tr_person"),
            empty="Nobody to show.")
        if hit:
            st.session_state["tr_person"] = hit["row"]

        sel = next((e for e in employees if e["id"] == st.session_state.get("tr_person")), None)
        if sel:
            tv.focus("training_people")
            with st.container(border=True):
                st.markdown(f"**{sel['name']}**")
                upd = _person_form(f"tr_edit_{sel['id']}", sel)
                if upd:
                    if TS.save_employee(user_id, client_id, upd, sel["id"]):
                        st.success(tr("Saved."))
                        st.rerun()
                    st.error(tr("Could not save. If you have read-only access, an admin must do this."))
                with st.expander(tr("Delete this person")):
                    st.caption(tr("Deleting removes their training history too. If they left, "
                               "set **Left on** instead: the record stays as evidence."))
                    if st.button(tr("Delete permanently"), key=f"tr_del_{sel['id']}",
                                 disabled=not editable):
                        if TS.delete_employee(user_id, client_id, sel["id"]):
                            st.session_state.pop("tr_person", None)
                            st.rerun()
                        st.error(tr("Could not delete."))

    st.subheader(tr("Add a person"))
    new = _person_form("tr_add")
    if new:
        if TS.save_employee(user_id, client_id, new):
            st.success(f"{new['name']} added.")
            st.rerun()
        st.error(tr("Could not add. If you have read-only access, an admin must do this."))

    with st.expander(tr("Paste a list")):
        st.caption(tr("One person per line: **name; job title; email**. Job title and email are "
                   "optional. Everyone is marked as handling personal data; adjust the rest "
                   "per person afterwards."))
        with st.form("tr_bulk", clear_on_submit=True):
            text = st.text_area(tr("People"), height=140,
                                placeholder=tr("Marie Dupont; Office manager; marie@example.be"))
            ai_all = st.checkbox(tr("They all use AI tools"))
            if st.form_submit_button(tr("Add all"), disabled=not editable):
                rows = []
                for line in text.splitlines():
                    parts = [p.strip() for p in line.split(";")]
                    if parts and parts[0]:
                        rows.append({"name": parts[0][:200],
                                     "job_title": parts[1] if len(parts) > 1 else None,
                                     "email": parts[2] if len(parts) > 2 else None,
                                     "handles_personal_data": True, "uses_ai": ai_all})
                n = TS.save_employees(user_id, client_id, rows)
                if n:
                    st.success(f"{plural(n, 'person', 'people')} added.")
                    st.rerun()
                st.error(tr("Nothing added."))


# ── Sessions ──────────────────────────────────────────────────────────────
_FMT_KEYS = list(TR.FORMATS)


def _session_form(key: str, s: dict | None = None, attendee_ids: set[str] | None = None):
    s = s or {}
    with st.form(key, clear_on_submit=not s):
        title = st.text_input(tr("Title"), value=s.get("title") or "",
                              placeholder=tr("GDPR and phishing awareness, spring session"))
        codes = st.multiselect(
            tr("Which training it counts for"), [r["code"] for r in reqs],
            default=[c for c in (s.get("requirement_codes") or []) if c in req_by_code],
            format_func=lambda c: req_by_code[c]["label_en"])
        a, b, c = st.columns(3)
        held = a.date_input(tr("Held on"), value=TR._d(s.get("held_on")) or today, format="DD/MM/YYYY")
        dur = b.number_input(tr("Duration (minutes)"), min_value=0, step=15,
                             value=int(s.get("duration_minutes") or 0))
        fmt = c.selectbox(tr("Format"), _FMT_KEYS,
                          index=_FMT_KEYS.index(s.get("format") or "in_person"),
                          format_func=lambda k: TR.FORMATS[k])
        d, e_ = st.columns(2)
        provider = d.text_input(tr("Provider"), value=s.get("provider") or "",
                                help=tr("Internal, or the training company."))
        trainer = e_.text_input(tr("Trainer"), value=s.get("trainer") or "")
        content = st.text_area(tr("What it covered"), value=s.get("content") or "", height=80,
                               help=tr("A few lines: an auditor's first question is what was taught."))
        until = st.date_input(tr("Counts until (optional)"), value=TR._d(s.get("valid_until")),
                              format="DD/MM/YYYY",
                              help=tr("Leave blank to use the default refresh interval."))
        people_ids = [p["id"] for p in active]
        names = {p["id"]: p["name"] for p in active}
        attendees = st.multiselect(tr("Who attended"), people_ids,
                                   default=[i for i in (attendee_ids or set()) if i in names],
                                   format_func=lambda i: names[i])
        add_needed = st.checkbox(tr("Also add everyone who needs the training selected above"))
        if st.form_submit_button("Save" if s else "Record session", type="primary",
                                 disabled=not editable):
            if not title.strip() or not codes:
                st.error(tr("A title and at least one training it counts for are needed."))
                return None
            if until and until < held:
                st.error(tr("It cannot stop counting before it was held."))
                return None
            ids = set(attendees)
            if add_needed:
                ids |= {p["id"] for p in active if any(TR.needs(p, req_by_code[x]) for x in codes)}
            return ({"title": title, "requirement_codes": codes, "held_on": held,
                     "duration_minutes": int(dur) or None, "format": fmt, "provider": provider,
                     "trainer": trainer, "content": content, "valid_until": until}, sorted(ids))
    return None


lang_opts = [l for l in (client.get("document_languages") or ["en"]) if l in ("en", "fr")] or ["en"]

with tab_sessions:
    att_by_session: dict[str, set[str]] = {}
    for a_ in attendance:
        att_by_session.setdefault(a_["session_id"], set()).add(a_["employee_id"])
    if not sessions:
        st.info(tr("No training recorded yet."))
    else:
        hit = tv.table(
            [{"id": s["id"], "cells": {
                "date": TR._d(s["held_on"]), "title": s["title"],
                "covers": ", ".join(req_by_code[c]["label_en"] for c in s.get("requirement_codes") or []
                                    if c in req_by_code),
                "n": len(att_by_session.get(s["id"], ())),
            }, "actions": [{"id": "open", "label": "Open", "icon": "📂"}]} for s in sessions],
            [{"key": "date", "label": "Held on", "kind": "date"}, {"key": "title", "label": "Title"},
             {"key": "covers", "label": "Counts for"}, {"key": "n", "label": "Attendees", "kind": "number"}],
            key="training_sessions", sort=("date", "desc"),
            current=st.session_state.get("tr_session"), empty="No sessions.")
        if hit:
            st.session_state["tr_session"] = hit["row"]

        sel = next((s for s in sessions if s["id"] == st.session_state.get("tr_session")), None)
        if sel:
            tv.focus("training_sessions")
            with st.container(border=True):
                st.markdown(f"**{sel['title']}** — {_fd(sel['held_on'])}")
                who = [e for e in employees if e["id"] in att_by_session.get(sel["id"], set())]
                from training_docs import build_attestation_pdf
                dl = st.columns(len(lang_opts))
                for col, lg in zip(dl, lang_opts):
                    col.download_button(
                        f"Attendance attestation ({lg.upper()})",
                        data=build_attestation_pdf(client, sel, who, reqs, lg),
                        file_name=f"attestation_{_fd(sel['held_on']).replace('/', '-')}_{lg}.pdf",
                        mime="application/pdf", key=f"tr_att_{sel['id']}_{lg}")
                res = _session_form(f"tr_ses_{sel['id']}", sel, att_by_session.get(sel["id"], set()))
                if res:
                    if TS.save_session(user_id, client_id, res[0], res[1], sel["id"]):
                        st.success(tr("Saved."))
                        st.rerun()
                    st.error(tr("Could not save. If you have read-only access, an admin must do this."))
                with st.expander(tr("Delete this session")):
                    st.caption(tr("Its attendance goes with it, and the people who attended may no "
                               "longer count as trained."))
                    if st.button(tr("Delete permanently"), key=f"tr_sdel_{sel['id']}",
                                 disabled=not editable):
                        if TS.delete_session(user_id, client_id, sel["id"]):
                            st.session_state.pop("tr_session", None)
                            st.rerun()
                        st.error(tr("Could not delete."))

    st.subheader(tr("Record a session"))
    if not active:
        st.caption(tr("Add people first, so you can say who attended."))
    res = _session_form("tr_ses_new")
    if res:
        if TS.save_session(user_id, client_id, res[0], res[1]):
            st.success(f"Recorded, with {plural(len(res[1]), 'attendee', 'attendees')}.")
            st.rerun()
        st.error(tr("Could not record. If you have read-only access, an admin must do this."))


# ── Documents ─────────────────────────────────────────────────────────────
with tab_docs:
    st.markdown(tr("**Training plan**"))
    st.caption(tr("What the law asks of whom, where each person stands, who is due in the next "
               "twelve months, and what was given in the last twelve. Built from this page, "
               "so it can be regenerated at any time."))
    from training_docs import build_plan_pdf
    dl = st.columns(len(lang_opts) + 1)
    for col, lg in zip(dl, lang_opts):
        col.download_button(
            f"Training plan ({lg.upper()})",
            data=build_plan_pdf(client, all_reqs, employees, sessions, attendance, today, lg),
            file_name=f"training_plan_{today:%Y-%m-%d}_{lg}.pdf", mime="application/pdf",
            key=f"tr_plan_{lg}")
    st.markdown(tr("**Attendance attestations**"))
    st.caption(tr("One per session: open it on the **Sessions** tab."))
