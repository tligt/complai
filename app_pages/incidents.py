"""
app_pages/incidents.py — S53 (D-117). The breach procedure, while it happens.

The S29A procedure says what to do; this page does it with the client: log
the incident (the clock starts at discovery), walk the first hour, record the
assessment and the reasons for it, draft each notification for the
authority's own portal, record what was sent, and close with a review.

Rules — which regimes apply, the clocks, the draft texts — live in
incident_rules.py, shared with the action plan and the reminder job.
"""

from datetime import datetime, timezone

import streamlit as st

import incident_rules as R
import incident_store as S
from active_client import get_active_client
from auth import get_user_id
from inventory_store import load_systems

user_id = get_user_id()
client = get_active_client(user_id)
tz = R.DISPLAY_TZ

_langs = client.get("document_languages") or ["en"]
draft_langs = [l for l in _langs if l in ("en", "fr")] or ["en"]
jur = S.load_jurisdiction(client.get("country"))
systems = load_systems(user_id, client["id"])
sys_name = {s["id"]: s.get("name") or "?" for s in systems}

STATE_ICON = {R.OVERDUE: "🔴", R.DUE_SOON: "🟠", R.TO_DECIDE: "🟡", R.RUNNING: "⏱️",
              R.DONE: "✅", R.NOT_REQUIRED: "⚪"}
STATUS_LABEL = {"open": "Open", "contained": "Contained", "closed": "Closed"}

st.title("🚨 Incidents")
st.caption(
    "Log a security incident or data breach the moment you know about it — the "
    "reporting deadlines run from that moment. RECOSA tracks the deadlines, "
    "drafts each notification and keeps the record GDPR requires, whether or "
    "not you end up notifying anyone."
)


def _local_input(label: str, key: str, default: datetime | None = None) -> datetime:
    """Date + time in the app's display zone, returned as an aware datetime."""
    d0 = (default or datetime.now(tz)).astimezone(tz)
    c1, c2 = st.columns(2)
    d = c1.date_input(f"{label} — date", value=d0.date(), key=f"{key}_d", format="DD/MM/YYYY")
    t = c2.time_input(f"{label} — time ({R.TZ_LABEL})", value=d0.time().replace(second=0, microsecond=0),
                      key=f"{key}_t", step=300)
    return datetime.combine(d, t, tzinfo=tz)


def _fmt(ts) -> str:
    return R._ts(ts).astimezone(tz).strftime("%d/%m/%Y %H:%M")


incidents = S.load_incidents(client["id"])
events = S.load_events(client["id"])

# ── Report a new incident ─────────────────────────────────────────────────
with st.expander("➕ Report an incident", expanded=not incidents):
    st.caption("Report anything suspicious without first judging whether it is serious. "
               "You can complete the details later.")
    with st.form("new_incident", clear_on_submit=True):
        title = st.text_input("Short title", placeholder="e.g. Laptop stolen, phishing email answered, ransomware")
        desc = st.text_area("What happened", placeholder="What you saw, and what you know so far.")
        found = _local_input("When you found out", "new_found")
        reporter = st.text_input("Reported by", value=st.session_state.user.email)
        sys_ids = st.multiselect("Systems affected", options=list(sys_name),
                                 format_func=lambda i: sys_name[i])
        if st.form_submit_button("Log incident — start the clock", type="primary"):
            if not title.strip():
                st.error("Give the incident a short title.")
            elif found > datetime.now(tz):
                st.error("The time you found out can't be in the future.")
            else:
                row = S.create_incident(user_id, client["id"], title=title, description=desc,
                                        discovered_at=found, reported_by=reporter, system_ids=sys_ids)
                if row:
                    st.session_state.incident_sel = row["id"]
                    st.rerun()
                st.error("Could not log the incident. Please try again.")

if not incidents:
    st.info("No incidents recorded. That is the normal state — this page is ready when one happens.")
    st.stop()

# ── Pick an incident ──────────────────────────────────────────────────────
_proc_ctx = None


def _controllers(inc):
    global _proc_ctx
    if _proc_ctx is None:
        _proc_ctx = S.processor_context(user_id, client["id"])
    return R.affected_controllers(inc.get("system_ids") or [], **_proc_ctx)


def _deadlines(inc):
    return R.deadlines(inc, client, events.get(inc["id"], []), bool(_controllers(inc)))


def _label(inc):
    nd = R.next_deadline(_deadlines(inc)) if inc["status"] != "closed" else None
    nxt = f" · {STATE_ICON[nd['state']]} {R.describe_left(nd)}" if nd else ""
    return f"{STATUS_LABEL[inc['status']]} · {_fmt(inc['discovered_at'])} · {inc['title']}{nxt}"


order = sorted(incidents, key=lambda i: (i["status"] == "closed", i["discovered_at"]), reverse=False)
order = [i for i in order if i["status"] != "closed"] + [i for i in order if i["status"] == "closed"]
ids = [i["id"] for i in order]
by_id = {i["id"]: i for i in incidents}
sel = st.session_state.get("incident_sel")
inc_id = st.selectbox("Incident", ids, index=ids.index(sel) if sel in ids else 0,
                      format_func=lambda i: _label(by_id[i]), key="incident_pick")
st.session_state.incident_sel = inc_id
inc = by_id[inc_id]
inc_events = events.get(inc_id, [])
dls = _deadlines(inc)
controllers = _controllers(inc)

# ── Clocks ────────────────────────────────────────────────────────────────
st.subheader(inc["title"])
st.caption(f"{STATUS_LABEL[inc['status']]} · found out {_fmt(inc['discovered_at'])} ({R.TZ_LABEL})"
           + (f" · reported by {inc['reported_by']}" if inc.get("reported_by") else "")
           + (f" · systems: {', '.join(sys_name.get(s, '?') for s in inc['system_ids'])}" if inc.get("system_ids") else ""))
if client.get("nis2_in_scope") is None and R.nis2_applies(client):
    st.caption("NIS2 deadlines are shown because NIS2 is among this company's regulations. "
               "Confirm the NIS2 scope on the Profile page.")

with st.container(border=True):
    st.markdown("**Deadlines**")
    for d in dls:
        if d["state"] == R.NOT_REQUIRED and d["required"] is False:
            continue
        due = f" — due {d['due'].astimezone(tz).strftime('%d/%m %H:%M')}" if d["due"] and d["state"] != R.DONE else ""
        extra = " (decide below)" if d["state"] == R.TO_DECIDE else ""
        st.markdown(f"{STATE_ICON[d['state']]} {R.LABELS['en'][d['kind']]} · **{R.describe_left(d)}**{due}{extra}")
    if all(d["state"] in (R.DONE, R.NOT_REQUIRED) for d in dls):
        st.caption("Nothing is due.")

tab_first, tab_assess, tab_notify, tab_close, tab_log = st.tabs(
    ["1 · First hour", "2 · Assess", "3 · Notify", "4 · Close", "Timeline"])

# ── 1. First hour (the S29A procedure, section 1) ─────────────────────────
with tab_first:
    st.markdown(
        "Do these in order. Don't wait for anyone to decide whether this is reportable.\n\n"
        "1. **Contain it.** Disconnect what needs disconnecting. Avoid powering systems off — it destroys evidence.\n"
        "2. **Write down the time** you found out and what you saw. *(Done — it's on this incident.)*\n"
        "3. **Tell the person who leads incidents.**\n"
        "4. **Do not delete anything**, including the thing that caused it.\n"
        "5. **Do not tell customers or the public yet.** That decision comes with the assessment."
    )
    if client.get("nis2_roles_text"):
        st.info(f"**Who leads incidents** (from your incident wording): {client['nis2_roles_text']}")
    if inc["status"] == "open" and st.button("Mark as contained", key="inc_contained"):
        if S.update_incident(inc_id, {"status": "contained"}):
            S.add_event(user_id, inc, "status", body="contained")
            st.rerun()

# ── 2. Assess ─────────────────────────────────────────────────────────────
_YN = {"Not sure yet": None, "Yes": True, "No": False}
_YN_REV = {v: k for k, v in _YN.items()}

with tab_assess:
    st.caption("The deadlines keep running while you assess. If you are unsure, treat it as "
               "reportable — an unnecessary notification costs an email, a missed one does not.")
    with st.form("assess"):
        # Also here, not only at logging: Enter in the logging form submits
        # it, so the systems are often still empty when the incident is made.
        sys_sel = st.multiselect("Systems affected", options=list(sys_name),
                                 default=[s for s in inc.get("system_ids") or [] if s in sys_name],
                                 format_func=lambda i: sys_name[i])
        pd = st.radio("Is personal data involved? (lost, exposed, altered or unavailable, even briefly)",
                      list(_YN), index=list(_YN).index(_YN_REV[inc.get("personal_data")]), horizontal=True)
        cats = st.text_input("Which categories of personal data?", value=inc.get("data_categories") or "",
                             placeholder="e.g. names, email addresses, payment data")
        c1, c2 = st.columns(2)
        subj = c1.number_input("Approx. people affected", min_value=0, step=1,
                               value=inc.get("approx_subjects") or 0)
        recs = c2.number_input("Approx. records affected", min_value=0, step=1,
                               value=inc.get("approx_records") or 0)
        hr = st.radio("Is it likely to result in a HIGH risk to the people affected? "
                      "(if yes, they must be told — GDPR Art. 34)",
                      list(_YN), index=list(_YN).index(_YN_REV[inc.get("high_risk")]), horizontal=True)
        if R.nis2_applies(client):
            sig = st.radio("Is it a significant incident under NIS2? (serious disruption of your "
                           "services, or considerable financial, material or other damage)",
                           list(_YN), index=list(_YN).index(_YN_REV[inc.get("significant")]), horizontal=True)
        else:
            sig = "No"
            st.caption("NIS2 does not apply to this company, so there is no NIS2 deadline.")
        cons = st.text_area("Likely consequences", value=inc.get("likely_consequences") or "")
        meas = st.text_area("Measures taken or planned", value=inc.get("measures_taken") or "")
        why = st.text_area("Why — the reasoning behind these answers (recorded with the decision)",
                           placeholder="e.g. the laptop was encrypted, so the data is not accessible")
        if st.form_submit_button("Save the assessment", type="primary"):
            changes = {
                "system_ids": sys_sel,
                "personal_data": _YN[pd], "data_categories": cats.strip() or None,
                "approx_subjects": int(subj) or None, "approx_records": int(recs) or None,
                "high_risk": _YN[hr], "significant": _YN[sig],
                "likely_consequences": cons.strip() or None, "measures_taken": meas.strip() or None,
            }
            summary = (f"Personal data: {pd}. High risk to people: {hr}. "
                       f"Significant (NIS2): {sig}." + (f" Reason: {why.strip()}" if why.strip() else ""))
            if S.update_incident(inc_id, changes):
                S.add_event(user_id, inc, "decision", body=summary)
                st.rerun()
            st.error("Could not save the assessment.")

# ── 3. Notify ─────────────────────────────────────────────────────────────
with tab_notify:
    lang = st.radio("Draft language", draft_langs, horizontal=True, key="inc_lang",
                    format_func=lambda l: {"en": "English", "fr": "Français"}[l]) if len(draft_langs) > 1 else draft_langs[0]
    auth = R.authorities(jur, lang)
    st.caption("RECOSA drafts; you submit on the authority's own portal, then record it here — "
               "that stops the clock. Send what you know within the deadline and follow up: "
               "a late complete notification is worse than an early incomplete one.")
    sys_names = [sys_name.get(s, "?") for s in inc.get("system_ids") or []]
    shown = 0
    for d in sorted(dls, key=lambda d: R.KINDS.index(d["kind"])):
        if d["required"] is False and d["state"] != R.DONE:
            continue
        shown += 1
        kind = d["kind"]
        with st.expander(f"{STATE_ICON[d['state']]} {R.LABELS['en'][kind]} — {R.describe_left(d)}",
                         expanded=d["state"] in (R.OVERDUE, R.DUE_SOON)):
            if kind in (R.GDPR_AUTHORITY,):
                a = auth["gdpr"]
                st.markdown(f"**To:** {a['name']}" + (f" ({a['short']})" if a["short"] else ""))
                if a["submit"]:
                    st.markdown(f"**Submit here:** {a['submit']}")
                elif a["site"]:
                    st.warning(f"RECOSA has not confirmed this authority's notification channel yet. "
                               f"Start from its website: {a['site']}")
                if a["note"]:
                    st.caption(a["note"])
            elif kind in (R.NIS2_EARLY, R.NIS2_NOTIFICATION, R.NIS2_FINAL):
                a = auth["nis2"]
                st.markdown(f"**To:** {a['name']}" + (f" ({a['short']})" if a["short"] else ""))
                if a["submit"]:
                    st.markdown(f"**Submit here:** {a['submit']}")
                if a["note"]:
                    st.caption(a["note"])
                if a.get("phone") or a.get("email"):
                    st.caption(" · ".join(x for x in (
                        f"Emergency line: {a['phone']}" if a.get("phone") else "",
                        f"Email: {a['email']}" if a.get("email") else "") if x))
                if a.get("guide"):
                    st.caption(f"What each report must contain: {a['guide']}")
            elif kind == R.CONTROLLERS:
                st.markdown("**To:** each company you process this data for:")
                for c in controllers:
                    st.markdown(f"- {c.get('legal_name')}" + (f" — {c['contact_email']}" if c.get("contact_email") else
                                                             " — *no contact email on record (Systems → counterparties)*"))
            elif kind == R.DATA_SUBJECTS:
                st.markdown("**To:** the people whose data is affected, directly where possible.")

            if kind == R.CONTROLLERS:
                for c in controllers:
                    st.text_area(f"Draft for {c.get('legal_name')}",
                                 R.draft(kind, inc, client, sys_names, lang, inc_events, controller=c.get("legal_name")),
                                 height=280, key=f"draft_{kind}_{c['id']}_{lang}")
            else:
                st.text_area("Draft — copy, complete the [to complete] parts, and paste into the portal",
                             R.draft(kind, inc, client, sys_names, lang, inc_events),
                             height=320, key=f"draft_{kind}_{lang}")

            if d["state"] == R.DONE:
                e = R.sent(inc_events, kind)
                st.success(f"Recorded as sent {_fmt(e['occurred_at'])}"
                           + (f" — reference {e['reference']}" if e.get("reference") else ""))
            else:
                with st.form(f"sent_{kind}"):
                    st.markdown("**Record it as sent**")
                    when = _local_input("Sent", f"sent_{kind}")
                    ref = st.text_input("Reference number from the authority (if any)", key=f"ref_{kind}")
                    if st.form_submit_button("Record as sent"):
                        if when < R._ts(inc["discovered_at"]):
                            st.error("It can't have been sent before the incident was found.")
                        elif when > datetime.now(tz):
                            st.error("The time sent can't be in the future.")
                        elif S.add_event(user_id, inc, "notification", kind=kind, occurred_at=when, reference=ref):
                            st.rerun()
                        else:
                            st.error("Could not record it.")
    if not shown:
        st.info("Nothing to notify on the answers recorded so far.")

# ── 4. Close ──────────────────────────────────────────────────────────────
with tab_close:
    if inc["status"] == "closed":
        st.success(f"Closed {_fmt(inc['closed_at'])}." if inc.get("closed_at") else "Closed.")
    open_required = [d for d in dls if d["state"] in (R.OVERDUE, R.DUE_SOON, R.RUNNING, R.TO_DECIDE)
                     and d["kind"] != R.NIS2_FINAL]
    if open_required and inc["status"] != "closed":
        st.warning("Some notifications are still open: " +
                   "; ".join(R.LABELS["en"][d["kind"]] for d in open_required) + ".")
    st.caption("Reviewing an incident is the only part of the procedure that makes the next one less likely.")
    with st.form("close"):
        rc = st.text_area("Root cause", value=inc.get("root_cause") or "")
        ls = st.text_area("What changed as a result", value=inc.get("lessons") or "")
        c1, c2 = st.columns(2)
        save = c1.form_submit_button("Save the review")
        close = c2.form_submit_button("Save and close the incident", type="primary",
                                      disabled=inc["status"] == "closed")
        if save or close:
            changes = {"root_cause": rc.strip() or None, "lessons": ls.strip() or None}
            if close:
                changes.update(status="closed", closed_at=datetime.now(timezone.utc).isoformat())
            if S.update_incident(inc_id, changes):
                if close:
                    S.add_event(user_id, inc, "status", body="closed")
                st.rerun()
            st.error("Could not save.")

# ── Timeline ──────────────────────────────────────────────────────────────
with tab_log:
    st.markdown(f"- **{_fmt(inc['discovered_at'])}** — found out"
                + (f" ({inc['reported_by']})" if inc.get("reported_by") else ""))
    for e in inc_events:
        what = {
            "decision": "Assessment recorded",
            "notification": f"Sent: {R.LABELS['en'].get(e.get('kind'), e.get('kind'))}",
            "status": f"Marked {e.get('body')}",
            "reminder": f"Reminder emailed ({e.get('body')})",
            "note": "Note",
        }.get(e["event_type"], e["event_type"])
        detail = e.get("reference") and f" — ref. {e['reference']}" or ""
        body = f"  \n  {e['body']}" if e.get("body") and e["event_type"] in ("decision", "note") else ""
        st.markdown(f"- **{_fmt(e['occurred_at'])}** — {what}{detail}{body}")
    st.caption(f"Times in {R.TZ_LABEL}. The timeline cannot be edited: it is the record GDPR Art. 33(5) asks for.")
