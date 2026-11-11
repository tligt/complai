"""
app_pages/incidents.py — S53 (D-117, D-118). The breach procedure, while it
happens, as a documented flow.

  Incident team   who is alerted, for which incidents, contractual deadlines
  Each incident   1 alert the team → 2 first hour → 3 assess (with reasons)
                  → 4 notify (draft, send on the authority's portal, record
                  the text actually sent) → 5 follow up (supplementary
                  information, the CSIRT's requests, authority questions)
                  → 6 close with a review → the record and the incident file

Rules — which regimes apply, the clocks, the draft texts, who to alert —
live in incident_rules.py, shared with the action plan, the incident file
and the reminder job.
"""
from i18n import tr, current_language  # S64 interface translation (D-164)

from datetime import datetime, timezone

import streamlit as st

import table_view as tv

from display import fmt_datetime

import incident_rules as R
import incident_store as S
from active_client import get_active_client
from auth import get_user_id
from database import get_supabase
from inventory_store import load_systems

user_id = get_user_id()
client = get_active_client(user_id)
tz = R.DISPLAY_TZ
_L = current_language()   # deadline labels and countdowns in the reader's language (D-169)

_langs = client.get("document_languages") or ["en"]
draft_langs = [l for l in _langs if l in ("en", "fr")] or ["en"]
jur = S.load_jurisdiction(client.get("country"))
systems = load_systems(user_id, client["id"])
sys_name = {s["id"]: s.get("name") or "?" for s in systems}
contacts = S.load_contacts(client["id"])
contacts_all = S.load_contacts(client["id"], include_inactive=True)
contact_by_id = {c["id"]: c for c in contacts_all}
nis2 = R.nis2_applies(client)

STATE_ICON = {R.OVERDUE: "🔴", R.DUE_SOON: "🟠", R.TO_DECIDE: "🟡", R.RUNNING: "⏱️",
              R.DONE: "✅", R.NOT_REQUIRED: "⚪"}
STATUS_LABEL = {"open": tr("Open"), "contained": tr("Contained"), "closed": tr("Closed")}

st.title(tr("Incidents"))
from guide import page_tip
page_tip("incidents")
st.caption(
    tr("Log a security incident or data breach the moment you know about it — the "
    "reporting deadlines run from that moment. RECOSA alerts your incident team, tracks "
    "the deadlines, drafts each notification and keeps the record GDPR requires, "
    "whether or not you end up notifying anyone.")
)


def _local_input(label: str, key: str, default: datetime | None = None) -> datetime:
    """Date + time in the app's display zone, returned as an aware datetime."""
    d0 = (default or datetime.now(tz)).astimezone(tz)
    c1, c2 = st.columns(2)
    d = c1.date_input(tr("{label} — date").format(label=label), value=d0.date(), key=f"{key}_d", format="DD/MM/YYYY")
    t = c2.time_input(tr("{label} — time ({r_tz_label})").format(label=label, r_tz_label=R.TZ_LABEL), value=d0.time().replace(second=0, microsecond=0),
                      key=f"{key}_t", step=300)
    return datetime.combine(d, t, tzinfo=tz)


def _fmt(ts) -> str:
    return fmt_datetime(R._ts(ts).astimezone(tz)) if ts else "—"


def _contact_line(c) -> str:
    bits = [f"**{c['name']}** — {tr(R.ROLES.get(c.get('role'), c.get('role') or ''))}"]
    if c.get("phone"):
        bits.append(f"📞 {c['phone']}")
    if c.get("email"):
        bits.append(c["email"])
    return " · ".join(bits)


tab_inc, tab_team, tab_wording = st.tabs([tr("Incidents"), tr("Incident team"), tr("Incident wording")])

# ══ Incident wording (usability audit batch 2, H4) ═══════════════════════
# Its own page, no longer in the menu: five text sections that only feed the
# incident and continuity documents belong with the incident team.
with tab_wording:
    st.caption(
        tr("Five short sections that go into your incident response plan and your "
        "business continuity plan: how you detect and contain an incident, who "
        "does what, how you keep running, and how you test it. RECOSA drafts "
        "each one; you correct it.")
    )
    if st.button(tr("Edit the incident wording"), key="inc_to_wording", type="primary"):
        st.switch_page("app_pages/wording.py")

# ══ Incident team ═════════════════════════════════════════════════════════
with tab_team:
    st.caption(
        tr("The people to alert when an incident happens, and when. RECOSA emails them as "
        "soon as an incident is logged, or once the assessment shows personal data or a "
        "significant NIS2 incident. This list also appears in your incident and breach "
        "notification procedure — regenerate it under Documents after changes.")
    )
    # The shared table (table_view.py): click a person to edit them below.
    # It replaced an st.dataframe plus an "Add or edit" box.
    if contacts_all:
        _t_hit = tv.table(
            [{"id": c["id"], "cells": {
                "name": c["name"], "role": tr(R.ROLES.get(c.get("role"), c.get("role") or "")),
                "email": c.get("email"), "phone": c.get("phone"),
                "alerted": tr(R.ALERT_ON.get(c.get("alert_on"), c.get("alert_on") or "")),
                "deadline": f"{c['deadline_hours']} h" if c.get("deadline_hours") else None,
                "active": tr("Yes") if c.get("active") else tr("No"),
            }, "actions": [{"id": "open", "label": tr("Edit"), "icon": "✏️"}]} for c in contacts_all],
            [{"key": "name", "label": tr("Name")}, {"key": "role", "label": tr("Role")},
             {"key": "email", "label": tr("Email")}, {"key": "phone", "label": tr("Phone")},
             {"key": "alerted", "label": tr("Alerted")}, {"key": "deadline", "label": tr("Contract deadline")},
             {"key": "active", "label": tr("Active")}],
            key="incident_team", current=st.session_state.get("team_edit"))
        if _t_hit:
            st.session_state.team_edit = _t_hit["row"]
    else:
        st.info(tr("No incident team yet. Start with whoever leads incidents and a deputy, then IT, "
                "your DPO or privacy contact, and management."))
    if not any(c.get("role") == "lead" for c in contacts):
        st.warning(tr("No incident lead on the list. The procedure says to tell them first."))

    if st.session_state.get("team_edit") not in contact_by_id:
        st.session_state.team_edit = "new"
    if st.session_state.team_edit != "new" and st.button(tr("➕ Add a team member"), key="team_add"):
        st.session_state.team_edit = "new"
        st.rerun()
    edit_id = st.session_state.team_edit
    tv.focus("incident_team")
    st.markdown(tr("**Add a team member**") if edit_id == "new"
                else tr("**Edit {name}**").format(name=contact_by_id[edit_id]['name']))
    cur = contact_by_id.get(edit_id, {})
    roles, alerts = list(R.ROLES), list(R.ALERT_ON)
    with st.form(f"team_form_{edit_id}"):
        name = st.text_input(tr("Name"), value=cur.get("name", ""))
        c1, c2 = st.columns(2)
        role = c1.selectbox(tr("Role"), roles, index=roles.index(cur.get("role", "other")),
                            format_func=lambda r: tr(R.ROLES[r]))
        alert_on = c2.selectbox(tr("Alerted for"), alerts, index=alerts.index(cur.get("alert_on", "all")),
                                format_func=lambda a: tr(R.ALERT_ON[a]))
        email = c1.text_input(tr("Email"), value=cur.get("email") or "")
        phone = c2.text_input(tr("Phone (for the first hour)"), value=cur.get("phone") or "")
        hours = st.number_input(
            tr("Contractual deadline to notify them, in hours (e.g. your cyber insurer) — 0 for none"),
            min_value=0, step=1, value=cur.get("deadline_hours") or 0)
        notes = st.text_input(tr("Notes"), value=cur.get("notes") or "",
                              placeholder=tr("e.g. policy number, out-of-hours line"))
        active = st.checkbox(tr("Active"), value=cur.get("active", True))
        if st.form_submit_button(tr("Save"), type="primary"):
            if not name.strip():
                st.error(tr("A name is needed."))
            elif email.strip() and ("@" not in email or "." not in email.split("@")[-1]):
                st.error(tr("That email address doesn't look right."))
            else:
                ok = S.save_contact(user_id, client["id"], {
                    "name": name.strip(), "role": role, "alert_on": alert_on,
                    "email": email.strip() or None, "phone": phone.strip() or None,
                    "deadline_hours": int(hours) or None, "notes": notes.strip() or None,
                    "sort_order": roles.index(role), "active": active,
                }, None if edit_id == "new" else edit_id)
                if ok:
                    st.rerun()
                st.error(tr("Could not save."))

    st.divider()
    st.markdown(tr("**Your contracts with your own clients**"))
    with st.form("notice_hours"):
        nh = st.number_input(
            tr("If you process data for clients: within how many hours do your contracts (DPAs) "
            "promise to tell them about a breach? 0 = \"without undue delay\", as the GDPR says."),
            min_value=0, step=1, value=client.get("breach_notice_hours") or 0)
        if st.form_submit_button(tr("Save")):
            try:
                get_supabase().table("clients").update(
                    {"breach_notice_hours": int(nh) or None}).eq("id", client["id"]).execute()
                st.session_state.selected_client = {**client, "breach_notice_hours": int(nh) or None}
                st.rerun()
            except Exception as e:
                st.error(tr("Could not save: {e}").format(e=e))

# ══ Incidents ═════════════════════════════════════════════════════════════
with tab_inc:
    incidents = S.load_incidents(client["id"])
    events = S.load_events(client["id"])

    with st.expander(tr("➕ Report an incident"), expanded=not incidents):
        st.caption(tr("Report anything suspicious without first judging whether it is serious. "
                   "You can complete the details later."))
        if not contacts:
            st.warning(tr("No incident team recorded, so nobody will be alerted. Add it in the "
                       "Incident team tab."))
        with st.form("new_incident", clear_on_submit=True):
            title = st.text_input(tr("Short title"), placeholder=tr("e.g. Laptop stolen, phishing email answered, ransomware"))
            desc = st.text_area(tr("What happened"), placeholder=tr("What you saw, and what you know so far."))
            found = _local_input(tr("When you found out"), "new_found")
            reporter = st.text_input(tr("Reported by"), value=st.session_state.user.email)
            sys_ids = st.multiselect(tr("Systems affected"), options=list(sys_name),
                                     format_func=lambda i: sys_name[i])
            do_alert = st.checkbox(tr("Alert the incident team now"), value=bool(contacts))
            if st.form_submit_button(tr("Log incident — start the clock"), type="primary"):
                if not title.strip():
                    st.error(tr("Give the incident a short title."))
                elif found > datetime.now(tz):
                    st.error(tr("The time you found out can't be in the future."))
                else:
                    row = S.create_incident(user_id, client["id"], title=title, description=desc,
                                            discovered_at=found, reported_by=reporter, system_ids=sys_ids)
                    if row:
                        # S56: the company's incidents person handles it.
                        try:
                            import work_items as _W
                            _W.route_incident(client["id"], row)
                        except Exception as _e:
                            print(f"Incident not routed: {_e}")
                        if do_alert:
                            S.alert_team(user_id, row, client, R.alert_targets(contacts, row, [], nis2), "logged")
                        st.session_state.incident_sel = row["id"]
                        st.rerun()
                    st.error(tr("Could not log the incident. Please try again."))

    if not incidents:
        st.info(tr("No incidents recorded. That is the normal state — this page is ready when one happens."))
        st.stop()

    _proc_ctx = None

    def _controllers(inc):
        global _proc_ctx
        if _proc_ctx is None:
            _proc_ctx = S.processor_context(user_id, client["id"])
        return R.affected_controllers(inc.get("system_ids") or [], **_proc_ctx)

    def _deadlines(inc):
        return R.deadlines(inc, client, events.get(inc["id"], []), bool(_controllers(inc)),
                           contacts=contacts)

    def _label(inc):
        nd = R.next_deadline(_deadlines(inc)) if inc["status"] != "closed" else None
        nxt = f" · {STATE_ICON[nd['state']]} {R.describe_left(nd, _L)}" if nd else ""
        return f"{STATUS_LABEL[inc['status']]} · {_fmt(inc['discovered_at'])} · {inc['title']}{nxt}"

    order = ([i for i in incidents if i["status"] != "closed"]
             + [i for i in incidents if i["status"] == "closed"])
    ids = [i["id"] for i in order]
    by_id = {i["id"]: i for i in incidents}
    # The shared table (table_view.py): open incidents first; click one to
    # open it below. It replaced an "Incident" picker.
    def _next(inc):
        nd = R.next_deadline(_deadlines(inc)) if inc["status"] != "closed" else None
        return f"{STATE_ICON[nd['state']]} {R.describe_left(nd, _L)}" if nd else None

    _i_hit = tv.table(
        [{"id": i["id"], "cells": {
            "status": STATUS_LABEL[i["status"]], "found": R._ts(i["discovered_at"]).astimezone(tz) if i.get("discovered_at") else None,
            "title": i["title"], "next": _next(i),
        }, "actions": [{"id": "open", "label": tr("Open"), "icon": "📂"}]} for i in order],
        [{"key": "status", "label": tr("Status")},
         {"key": "found", "label": tr("Found out ({tz})").format(tz=R.TZ_LABEL), "kind": "datetime"},
         {"key": "title", "label": tr("Incident")}, {"key": "next", "label": tr("Next deadline")}],
        key="incidents", current=st.session_state.get("incident_sel"))
    if _i_hit:
        st.session_state.incident_sel = _i_hit["row"]
    if st.session_state.get("incident_sel") not in ids:
        st.session_state.incident_sel = ids[0]
    inc_id = st.session_state.incident_sel
    inc = by_id[inc_id]
    inc_events = events.get(inc_id, [])
    dls = _deadlines(inc)
    controllers = _controllers(inc)
    sys_names = [sys_name.get(s, "?") for s in inc.get("system_ids") or []]

    # ── Deadlines ──────────────────────────────────────────────────────────
    tv.focus("incidents")
    st.subheader(inc["title"])
    st.caption(f"{STATUS_LABEL[inc['status']]} · "
               + tr("found out {when} ({tz})").format(when=_fmt(inc['discovered_at']), tz=R.TZ_LABEL)
               + (" · " + tr("reported by {who}").format(who=inc['reported_by']) if inc.get("reported_by") else "")
               + (" · " + tr("systems: {names}").format(names=', '.join(sys_names)) if sys_names else ""))
    if client.get("nis2_in_scope") is None and nis2:
        st.caption(tr("NIS2 deadlines are shown because NIS2 is among this company's regulations. "
                   "Confirm whether NIS2 applies at the top of the Obligations page "
                   "(\"NIS2 — are you in scope, and as what?\")."))
        if st.button(tr("Go to Obligations"), icon="✅", key="nis2_scope_link"):
            st.switch_page("app_pages/obligations.py")
    # S56: who handles this incident, and the team's comments on it.
    import work_items as _W
    if _W.has_team(client["id"]) or _W.comments(client["id"], "incident", inc_id):
        from work_items_view import render_panel as _panel
        _arow = _W.current(client["id"], "incident").get(inc_id)
        _n = len(_W.comments(client["id"], "incident", inc_id))
        _who = (_arow or {}).get("assignee_id")
        with st.expander("👤 " + tr("Handled by {who}").format(
                             who=_W.name_of(client['id'], _who) if _who else tr("nobody yet"))
                         + (f" · 💬 {_n}" if _n else ""),
                         expanded=st.session_state.pop("incident_open_panel", False)):
            _panel(client, "incident", inc_id, inc["title"], user_id, _arow)

    with st.container(border=True):
        st.markdown(tr("**Deadlines**"))

        def _dl_line(d):
            due = (" — " + tr("due {when}").format(when=fmt_datetime(d['due'].astimezone(tz)))
                   if d["due"] and d["state"] != R.DONE else "")
            st.markdown(f"{STATE_ICON[d['state']]} {R.label(d['kind'], _L, contact_by_id)} · "
                        f"**{R.describe_left(d, _L)}**{due}")

        shown_dls = [d for d in dls if not (d["state"] == R.NOT_REQUIRED and d["required"] is False)]
        undecided = [d for d in shown_dls if d["state"] == R.TO_DECIDE]
        decided = [d for d in shown_dls if d["state"] != R.TO_DECIDE]
        # Usability audit H10: the deadlines that depend on the assessment are
        # one clock and one instruction, not a list of apparent emergencies.
        if undecided:
            first = min(undecided, key=lambda d: d["due"] or datetime.max.replace(tzinfo=timezone.utc))
            _which = (tr("Until you do, RECOSA cannot tell which other notifications apply.") if decided
                      else tr("Until you do, RECOSA cannot tell which notifications apply."))
            st.warning(
                "⏱️ " + tr("**Assess this incident in step 3.**") + " " + _which + " "
                + tr("The earliest of them — {label} — is due **{left}**").format(
                    label=R.label(first['kind'], _L, contact_by_id), left=R.describe_left(first, _L))
                + (f" ({fmt_datetime(first['due'].astimezone(tz))})." if first["due"] else ".")
            )
        for d in decided:
            _dl_line(d)
        if undecided:
            with st.expander(tr("1 possible deadline depends on the assessment") if len(undecided) == 1 else
                             tr("{n} possible deadlines depend on the assessment").format(n=len(undecided))):
                for d in undecided:
                    _dl_line(d)
        if all(d["state"] in (R.DONE, R.NOT_REQUIRED) for d in dls):
            st.caption(tr("Nothing is due."))

    s_team, s_first, s_assess, s_notify, s_follow, s_close, s_record = st.tabs(
        [tr("1 · Team"), tr("2 · First hour"), tr("3 · Assess"), tr("4 · Notify"), tr("5 · Follow up"),
         tr("6 · Close"), tr("Record & file")])

    # ── 1. Team ────────────────────────────────────────────────────────────
    with s_team:
        alerts = [e for e in inc_events if e["event_type"] == "alert"]
        for e in alerts:
            st.markdown(tr("✅ Alerted {fmt_e_occurred_at}: {e_get_body}").format(fmt_e_occurred_at=_fmt(e['occurred_at']), e_get_body=e.get('body')))
        pending = R.alert_targets(contacts, inc, inc_events, nis2)
        if pending:
            st.warning(tr("Not alerted yet: {names}").format(names=", ".join(c["name"] for c in pending)))
            if st.button(tr("Alert them now"), type="primary", key="alert_pending"):
                sent_to = S.alert_team(user_id, inc, client, pending, "manual")
                if sent_to:
                    st.rerun()
                st.error(tr("Could not send the alert. Call them — the numbers are below."))
        elif not alerts:
            st.info(tr("Nobody to alert: add your team in the Incident team tab."))
        if contacts:
            st.markdown(tr("**The team**"))
            for c in contacts:
                st.markdown("- " + _contact_line(c))

    # ── 2. First hour (the S29A procedure, section 1) ──────────────────────
    with s_first:
        lead = [c for c in contacts if c.get("role") in ("lead", "deputy")]
        st.markdown(
            tr("Do these in order. Don't wait for anyone to decide whether this is reportable.") + "\n\n"
            "1. " + tr("**Contain it.** Disconnect what needs disconnecting. Avoid powering systems off — it destroys evidence.") + "\n"
            "2. " + tr("**Write down the time** you found out and what you saw. *(Done — it's on this incident.)*") + "\n"
            "3. " + tr("**Tell the person who leads incidents.**")
            + (" " + "; ".join(f"{c['name']} ({c.get('phone') or c.get('email') or tr('no contact details')})"
                                for c in lead) if lead else "") + "\n"
            "4. " + tr("**Do not delete anything**, including the thing that caused it.") + "\n"
            "5. " + tr("**Do not tell customers or the public yet.** That decision comes with the assessment.")
        )
        if client.get("nis2_roles_text"):
            st.info(tr("**Who does what** (from your incident wording): {client_nis2_roles_text}").format(client_nis2_roles_text=client['nis2_roles_text']))
        if inc["status"] == "open" and st.button(tr("Mark as contained"), key="inc_contained"):
            if S.update_incident(inc_id, {"status": "contained"}):
                S.add_event(user_id, inc, "status", body="contained")
                st.rerun()

    # ── 3. Assess ──────────────────────────────────────────────────────────
    _YN = {"Not sure yet": None, "Yes": True, "No": False}
    _YN_REV = {v: k for k, v in _YN.items()}
    _RISK = {"Not decided yet": None, **{R.GDPR_RISK[k]: k for k in R.GDPR_RISK}}
    _RISK_REV = {v: k for k, v in _RISK.items()}
    _EXEMPT = {"None — tell them directly": None, **{R.SUBJECTS_EXEMPTIONS[k]: k for k in R.SUBJECTS_EXEMPTIONS}}
    _EXEMPT_REV = {v: k for k, v in _EXEMPT.items()}

    with s_assess:
        st.caption(tr("The deadlines keep running while you assess. Every answer is recorded with "
                   "your reasoning — including a decision not to notify, which GDPR requires you "
                   "to document."))
        with st.form("assess"):
            sys_sel = st.multiselect(tr("Systems affected"), options=list(sys_name),
                                     default=[s for s in inc.get("system_ids") or [] if s in sys_name],
                                     format_func=lambda i: sys_name[i])
            st.markdown(tr("**Personal data (GDPR)**"))
            pd = st.radio(tr("Is personal data involved? (lost, exposed, altered or unavailable, even briefly)"),
                          list(_YN), index=list(_YN).index(_YN_REV[inc.get("personal_data")]), horizontal=True,
                          format_func=tr)
            risk = st.radio(
                tr("What is the risk to the people concerned? (GDPR Art. 33(1): notify the authority unless "
                "the breach is unlikely to result in a risk)"),
                list(_RISK), index=list(_RISK).index(_RISK_REV[inc.get("gdpr_risk")]), format_func=tr)
            exempt = st.selectbox(
                tr("If high risk: does an Art. 34(3) exemption apply to telling the people?"),
                list(_EXEMPT), index=list(_EXEMPT).index(_EXEMPT_REV[inc.get("subjects_exemption")]),
                format_func=tr)
            c1, c2 = st.columns(2)
            scats = c1.text_input(tr("Categories of people"), value=inc.get("subject_categories") or "",
                                  placeholder=tr("e.g. customers, employees, patients"))
            cats = c2.text_input(tr("Categories of data"), value=inc.get("data_categories") or "",
                                 placeholder=tr("e.g. names, emails, payment data"))
            subj = c1.number_input(tr("Approx. people affected"), min_value=0, step=1,
                                   value=inc.get("approx_subjects") or 0)
            recs = c2.number_input(tr("Approx. records affected"), min_value=0, step=1,
                                   value=inc.get("approx_records") or 0)
            if nis2:
                st.markdown(tr("**Security incident (NIS2)**"))
                sig = st.radio(tr("Is it a significant incident? (serious disruption of your services, or "
                               "considerable financial, material or other damage)"),
                               list(_YN), index=list(_YN).index(_YN_REV[inc.get("significant")]), horizontal=True,
                               format_func=tr)
                rcp = st.radio(tr("Is it likely to affect the users of your services? (they must then be "
                               "informed — NIS2 Art. 23(1))"),
                               list(_YN), index=list(_YN).index(_YN_REV[inc.get("affects_recipients")]),
                               horizontal=True, format_func=tr)
            else:
                sig, rcp = "No", "No"
                st.caption(tr("NIS2 does not apply to this company, so there is no NIS2 deadline."))
            cons = st.text_area(tr("Likely consequences"), value=inc.get("likely_consequences") or "")
            meas = st.text_area(tr("Measures taken or planned"), value=inc.get("measures_taken") or "")
            why = st.text_area(tr("Why — the reasoning behind these answers (recorded with the decision)"),
                               placeholder=tr("e.g. the laptop was encrypted, so the data is not accessible"))
            if st.form_submit_button(tr("Save the assessment"), type="primary"):
                if _RISK[risk] == "none" and not why.strip():
                    st.error(tr("A decision that the breach is unlikely to result in a risk must say why — "
                             "it is what the authority will ask for if it ever looks at this."))
                else:
                    changes = {
                        "system_ids": sys_sel,
                        "personal_data": _YN[pd], "gdpr_risk": _RISK[risk] if _YN[pd] is not False else None,
                        "subjects_exemption": _EXEMPT[exempt] if _RISK[risk] == "high" else None,
                        "subject_categories": scats.strip() or None, "data_categories": cats.strip() or None,
                        "approx_subjects": int(subj) or None, "approx_records": int(recs) or None,
                        "significant": _YN[sig], "affects_recipients": _YN[rcp] if _YN[sig] else None,
                        "likely_consequences": cons.strip() or None, "measures_taken": meas.strip() or None,
                    }
                    summary = (f"Personal data: {pd}. GDPR risk: {risk}."
                               + (f" Exemption: {exempt}." if changes["subjects_exemption"] else "")
                               + (f" Significant (NIS2): {sig}. Users affected: {rcp}." if nis2 else "")
                               + (f" Reason: {why.strip()}" if why.strip() else ""))
                    if S.update_incident(inc_id, changes):
                        S.add_event(user_id, inc, "decision", body=summary)
                        newer = {**inc, **changes}
                        targets = R.alert_targets(contacts, newer, inc_events, nis2)
                        if targets:
                            S.alert_team(user_id, newer, client, targets,
                                         "significant" if newer.get("significant") else "personal_data")
                        st.rerun()
                    st.error(tr("Could not save the assessment."))

    # ── 4. Notify ──────────────────────────────────────────────────────────
    with s_notify:
        lang = (st.radio(tr("Draft language"), draft_langs, horizontal=True, key="inc_lang",
                         format_func=lambda l: {"en": "English", "fr": "Français"}[l])
                if len(draft_langs) > 1 else draft_langs[0])
        auth = R.authorities(jur, lang)
        st.caption(tr("RECOSA drafts; the person on your team who sends it submits it on the authority's "
                   "own portal (or emails it, for your clients, users and team contacts), then records "
                   "it here — which stops the clock and keeps the text sent in the incident file. "
                   "Send what you know within the deadline and follow up in step 5."))
        shown = 0
        order_k = {k: i for i, k in enumerate(R.KINDS)}
        for d in sorted(dls, key=lambda d: order_k.get(d["kind"], 99)):
            kind = d["kind"]
            if d["required"] is False and d["state"] != R.DONE:
                continue
            if kind in (R.NIS2_PROGRESS,) and d["required"] is None:
                continue
            shown += 1
            late = kind == R.GDPR_AUTHORITY and R.is_late(d)
            with st.expander(f"{STATE_ICON[d['state']]} {R.label(kind, _L, contact_by_id)} — {R.describe_left(d, _L)}",
                             expanded=d["state"] in (R.OVERDUE, R.DUE_SOON)):
                who = R.AUTHORITY_OF.get(kind)
                if who == "gdpr":
                    a = auth["gdpr"]
                    st.markdown(tr("**To:** {name}").format(name=a['name']) + (f" ({a['short']})" if a["short"] else ""))
                    if a["submit"]:
                        st.markdown(tr("**Submit here:** {url}").format(url=a['submit']))
                    elif a["site"]:
                        st.warning(tr("RECOSA has not confirmed this authority's notification channel yet. "
                                      "Start from its website: {url}").format(url=a['site']))
                    if a["note"]:
                        st.caption(a["note"])
                    if a.get("guide"):
                        st.caption(tr("How to notify, on the authority's site: {url}").format(url=a['guide']))
                elif who == "nis2":
                    a = auth["nis2"]
                    st.markdown(tr("**To:** {name}").format(name=a['name']) + (f" ({a['short']})" if a["short"] else ""))
                    if a["submit"]:
                        st.markdown(tr("**Submit here:** {url}").format(url=a['submit']))
                    if a["note"]:
                        st.caption(a["note"])
                    if a.get("phone") or a.get("email"):
                        st.caption(" · ".join(x for x in (
                            tr("Emergency line: {phone}").format(phone=a['phone']) if a.get("phone") else "",
                            tr("Email: {email}").format(email=a['email']) if a.get("email") else "") if x))
                    if a.get("guide"):
                        st.caption(tr("What each report must contain: {url}").format(url=a['guide']))
                elif kind == R.CONTROLLERS:
                    st.markdown(tr("**To:** each company you process this data for, from your own mailbox:"))
                    for c in controllers:
                        st.markdown(f"- {c.get('legal_name')}" + (
                            f" — {c['contact_email']}" if c.get("contact_email")
                            else " — " + tr("*no contact email on record (Systems → counterparties)*")))
                    if client.get("breach_notice_hours"):
                        st.caption(tr("Your contracts promise notice within {h} h.").format(h=client['breach_notice_hours']))
                elif kind == R.DATA_SUBJECTS:
                    st.markdown(tr("**To:** the public — a communication instead of contacting each person "
                                   "(Art. 34(3)(c)).") if inc.get("subjects_exemption") == "public"
                                else tr("**To:** the people whose data is affected, directly, from your own channels."))
                elif kind == R.NIS2_RECIPIENTS:
                    st.markdown(tr("**To:** the users of your services likely to be affected, from your own channels."))
                elif kind.startswith(R.CONTACT_PREFIX):
                    c = contact_by_id.get(kind[len(R.CONTACT_PREFIX):], {})
                    st.markdown(tr("**To:** {who}").format(who=_contact_line(c)) if c else tr("**To:** [removed contact]"))
                    if c.get("notes"):
                        st.caption(c["notes"])

                if late:
                    st.warning(tr("This is past the 72 hours: the notification must give the reasons for "
                               "the delay. The draft has a line for them."))
                text_keys = []
                if kind == R.CONTROLLERS:
                    for c in controllers:
                        k = f"draft_{kind}_{c['id']}_{lang}"
                        text_keys.append((c.get("legal_name"), k))
                        st.text_area(tr("Draft for {c_get_legal_name}").format(c_get_legal_name=c.get('legal_name')),
                                     R.draft(kind, inc, client, sys_names, lang, inc_events,
                                             controller=c.get("legal_name")),
                                     height=280, key=k)
                else:
                    k = f"draft_{kind}_{lang}_{int(late)}"
                    text_keys.append((None, k))
                    st.text_area(tr("Draft — edit it until it is what you send; complete the [to complete] parts"),
                                 R.draft(kind, inc, client, sys_names, lang, inc_events, late=late),
                                 height=320, key=k)

                if d["state"] == R.DONE:
                    e = R.sent(inc_events, kind)
                    st.success(tr("Recorded as sent {when}").format(when=_fmt(e['occurred_at']))
                               + (" — " + tr("reference {ref}").format(ref=e['reference']) if e.get("reference") else ""))
                else:
                    with st.form(f"sent_{kind}"):
                        st.markdown(tr("**Record it as sent** — the text above is kept as what was sent"))
                        when = _local_input(tr("Sent"), f"sent_{kind}")
                        ref = st.text_input(tr("Reference number from the authority (if any)"), key=f"ref_{kind}")
                        if st.form_submit_button(tr("Record as sent")):
                            texts = [(n, st.session_state.get(k, "")) for n, k in text_keys]
                            body = "\n\n".join((f"— To {n} —\n" if n else "") + t for n, t in texts)
                            if when < R._ts(inc["discovered_at"]):
                                st.error(tr("It can't have been sent before the incident was found."))
                            elif when > datetime.now(tz):
                                st.error(tr("The time sent can't be in the future."))
                            elif kind == R.GDPR_AUTHORITY and R.is_late(d, when) and (
                                    "Reasons for the delay (Art. 33(1)): [to complete]" in body
                                    or "Motifs du retard (art. 33(1)) : [à compléter]" in body
                                    or not ("Reasons for the delay" in body or "Motifs du retard" in body)):
                                st.error(tr("Sent after 72 hours: complete the reasons for the delay in the "
                                         "text before recording it."))
                            elif S.add_event(user_id, inc, "notification", kind=kind, occurred_at=when,
                                             reference=ref, body=body):
                                st.rerun()
                            else:
                                st.error(tr("Could not record it."))
        if not shown:
            st.info(tr("Nothing to notify on the answers recorded so far."))

    # ── 5. Follow up ───────────────────────────────────────────────────────
    with s_follow:
        st.caption(tr("After the first notification: send what you learn as you learn it, answer the "
                   "authority's questions, and keep it all on the record."))
        sent_kinds = [k for k in R.AUTHORITY_OF if R.sent(inc_events, k)]
        st.markdown(tr("**Supplementary information** (GDPR Art. 33(4), or an update to the CSIRT)"))
        if not sent_kinds:
            st.caption(tr("Available once a notification to an authority has been recorded as sent."))
        else:
            fk = st.selectbox(tr("Further to"), sent_kinds, format_func=lambda k: R.label(k, _L), key="fu_kind")
            fl = draft_langs[0] if len(draft_langs) == 1 else st.session_state.get("inc_lang", draft_langs[0])
            st.text_area(tr("Draft"), R.draft(fk, inc, client, sys_names, fl, inc_events, followup=True),
                         height=260, key=f"fu_text_{fk}_{fl}")
            with st.form("followup"):
                when = _local_input(tr("Sent"), "fu_sent")
                ref = st.text_input(tr("Reference (if any)"))
                if st.form_submit_button(tr("Record as sent")):
                    if S.add_event(user_id, inc, "followup", kind=fk, occurred_at=when, reference=ref,
                                   body=st.session_state.get(f"fu_text_{fk}_{fl}", "")):
                        st.rerun()
                    st.error(tr("Could not record it."))

        if nis2 and inc.get("significant"):
            st.divider()
            st.markdown(tr("**The CSIRT asked for an intermediate report** (NIS2 Art. 23(4)(c))"))
            if inc.get("intermediate_due"):
                st.caption(tr("Requested — due {fmt_inc_intermediate_due}. It is in step 4.").format(fmt_inc_intermediate_due=_fmt(inc['intermediate_due'])))
            with st.form("intermediate"):
                due = _local_input(tr("Due by"), "int_due")
                note = st.text_input(tr("What they asked (optional)"))
                if st.form_submit_button(tr("Record the request")):
                    if S.update_incident(inc_id, {"intermediate_due": due.astimezone(timezone.utc).isoformat()}):
                        S.add_event(user_id, inc, "request", kind=R.NIS2_INTERMEDIATE,
                                    body=note or "Intermediate report requested")
                        st.rerun()
                    st.error(tr("Could not record it."))

        st.divider()
        st.markdown(tr("**A question, acknowledgement or answer from an authority, or anything else to keep**"))
        with st.form("note"):
            note = st.text_area(tr("Note"))
            ref = st.text_input(tr("Reference (if any)"))
            if st.form_submit_button(tr("Add to the record")):
                if note.strip() and S.add_event(user_id, inc, "note", reference=ref, body=note):
                    st.rerun()
                st.error(tr("Write the note first.") if not note.strip() else tr("Could not save it."))

    # ── 6. Close ───────────────────────────────────────────────────────────
    with s_close:
        if inc["status"] == "closed":
            st.success(tr("Closed {fmt_inc_get_closed_at}.").format(fmt_inc_get_closed_at=_fmt(inc.get('closed_at'))))
        open_required = [d for d in dls if d["state"] in R.OPEN_STATES
                         and d["kind"] not in (R.NIS2_FINAL, R.NIS2_PROGRESS)]
        if open_required and inc["status"] != "closed":
            st.warning(tr("Still open: {labels}.").format(
                labels="; ".join(R.label(d["kind"], _L, contact_by_id) for d in open_required)))
        if nis2 and inc.get("significant"):
            st.caption(tr("Closing marks the end of handling: if the NIS2 notification was sent, the final "
                       "report is due one month after it — or one month after closing, if later."))
        st.caption(tr("Reviewing an incident is the only part of the procedure that makes the next one less likely."))
        with st.form("close"):
            rc = st.text_area(tr("Root cause"), value=inc.get("root_cause") or "")
            ls = st.text_area(tr("What changed as a result"), value=inc.get("lessons") or "")
            c1, c2 = st.columns(2)
            save = c1.form_submit_button(tr("Save the review"))
            close = c2.form_submit_button(tr("Save and close the incident"), type="primary",
                                          disabled=inc["status"] == "closed")
            if save or close:
                changes = {"root_cause": rc.strip() or None, "lessons": ls.strip() or None}
                if close:
                    changes.update(status="closed", closed_at=datetime.now(timezone.utc).isoformat())
                if S.update_incident(inc_id, changes):
                    if close:
                        S.add_event(user_id, inc, "status", body="closed")
                    st.rerun()
                st.error(tr("Could not save."))

    # ── Record & file ──────────────────────────────────────────────────────
    with s_record:
        from incident_file import build_pdf
        st.download_button(
            tr("📄 Download the incident file (PDF)"),
            build_pdf(inc, client, inc_events, dls, sys_names, contact_by_id),
            file_name=f"incident_{R._ts(inc['discovered_at']).astimezone(tz):%Y-%m-%d}_{inc_id[:8]}.pdf",
            mime="application/pdf", type="primary",
        )
        st.caption(tr("The facts, the decisions and their reasons, every text sent with its reference, the "
                   "team alerts and the timeline — what an authority or auditor asks for."))
        st.markdown(f"- **{_fmt(inc['discovered_at'])}** — " + tr("found out")
                    + (f" ({inc['reported_by']})" if inc.get("reported_by") else ""))
        for e in inc_events:
            what = {
                "decision": tr("Assessment recorded"),
                "notification": tr("Sent: {label}").format(label=R.label(e.get('kind') or '', _L, contact_by_id)),
                "followup": tr("Supplementary information: {label}").format(
                    label=R.label(e.get('kind') or '', _L, contact_by_id)),
                "status": tr("Marked {status}").format(
                    status=STATUS_LABEL.get(e.get('body'), e.get('body') or '').lower()),
                "reminder": tr("Reminder emailed ({stage})").format(stage=e.get('body')),
                "alert": tr("Team alerted: {who}").format(who=e.get('body')),
                "request": tr("Request from an authority"),
                "note": tr("Note"),
            }.get(e["event_type"], e["event_type"])
            detail = " — " + tr("ref. {ref}").format(ref=e['reference']) if e.get("reference") and e["event_type"] != "alert" else ""
            body = (f"  \n  {e['body']}" if e.get("body") and e["event_type"] in ("decision", "note", "request")
                    else "")
            st.markdown(f"- **{_fmt(e['occurred_at'])}** — {what}{detail}{body}")
        st.caption(tr("Times in {r_tz_label}. The record cannot be edited: it is the documentation GDPR Art. 33(5) asks for.").format(r_tz_label=R.TZ_LABEL))
