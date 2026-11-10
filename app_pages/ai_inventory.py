"""
pages/ai_inventory.py — S61 (D-160). The AI Act inventory: models, systems,
use cases.

RENDERING ONLY (D-61). Risk and role come from ai_rules, all I/O from
ai_store. AI systems are the inventory's own systems (ai_role != 'none'),
not a second list.

The intake asks what a deployer can answer. Technical attributes (training
data, accuracy, Annex IV) are the provider's documentation, not questions
for an SME using a vendor's chatbot.
"""
from i18n import tr  # S64 interface translation (D-164)

import streamlit as st

import ai_rules as AR
import ai_store as AIS
import table_view as tv
from active_client import can_edit_active, get_active_client
from auth import get_user_id
from guide import page_tip

st.title(tr("AI inventory"))
page_tip("ai_inventory")
st.caption(
    tr("Which AI systems you use, what they are built on, and what you use each one "
    "for. Role and risk attach to the use: the same tool can be minimal risk for "
    "one purpose and high risk for another.")
)

user_id = get_user_id()
if not user_id:
    st.error(tr("Please log in."))
    st.stop()

client = get_active_client(user_id)
client_id = client["id"]
editable = can_edit_active()
if "EU_AI_ACT" not in (client.get("regulations") or []):
    st.info(tr("The EU AI Act is not among this company's regulations, so nothing here feeds "
            "its obligations. Add it on the Company profile if you use AI."))

data = AIS.load_all(client_id)
systems = data["systems"]
models = data["models"]
links = data["links"]
use_cases = data["use_cases"]
ai_systems = [s for s in systems if AR.is_ai_system(s)]
sys_by_id = {s["id"]: s for s in systems}
model_by_id = {m["id"]: m for m in models}

annex = AIS.load_reference("ai_annex_iii_area")
practices = AIS.load_reference("ai_prohibited_practice")
annex_label = {r["code"]: r["label_en"] for r in annex}
practice_label = {r["code"]: r["label_en"] for r in practices}
try:
    import training_store as TS
    employees = [e for e in TS.load_employees(client_id) if not e.get("left_on")]
except Exception:
    employees = []
emp_label = {e["id"]: e["name"] for e in employees}

_TRI = [None, True, False]
_TRI_LABEL = {None: "Not answered", True: "Yes", False: "No"}


def _tri(col, label, value, key, help=None):
    return col.selectbox(label, _TRI, index=_TRI.index(value if value in _TRI else None),
                         format_func=lambda v: _TRI_LABEL[v], key=key, help=help)


# S62: the one name the AI policies need.
policy_owner = AIS.load_policy_owner(client_id)
with st.expander("Who approves new AI tools: " + (policy_owner or "not set yet"),
                 expanded=not policy_owner):
    st.caption(tr("Named in your AI acceptable use and human oversight policies (Documents): "
               "staff ask this person before using a new AI tool, and report problems to them. "
               "A role is better than a name if people change."))
    with st.form("ai_owner"):
        owner = st.text_input(tr("Role or name"), value=policy_owner or "",
                              placeholder=tr("The operations manager"))
        if st.form_submit_button(tr("Save"), disabled=not editable):
            if AIS.set_policy_owner(user_id, client_id, owner):
                st.rerun()
            st.error(tr("Could not save. If you have read-only access, an admin must do this."))

tab_uc, tab_sys, tab_models = st.tabs(
    [f"Use cases ({len([u for u in use_cases if AR.active(u)])})",
     f"AI systems ({len(ai_systems)})", f"Models ({len(models)})"])


# ── Use cases ─────────────────────────────────────────────────────────────
def _uc_form(key: str, u: dict | None = None):
    u = u or {}
    new = not u
    with st.form(key, clear_on_submit=new):
        st.markdown(tr("**The use**"))
        a, b = st.columns(2)
        sys_ids = [s["id"] for s in ai_systems]
        system_id = a.selectbox(tr("AI system"), sys_ids,
                                index=sys_ids.index(u["system_id"]) if u.get("system_id") in sys_ids else 0,
                                format_func=lambda i: sys_by_id[i].get("name") or "?")
        name = b.text_input(tr("Name of the use"), value=u.get("name") or "",
                            placeholder=tr("Answering customer questions on the website"))
        desc = st.text_area(tr("What it does, for whom"), value=u.get("description") or "", height=70)
        c, d, e_ = st.columns(3)
        owner = c.text_input(tr("Business owner"), value=u.get("business_owner") or "")
        stats = ["in_use", "planned", "retired"]
        status = d.selectbox(tr("Status"), stats, index=stats.index(u.get("status") or "in_use"),
                             format_func=lambda s: {"in_use": "In use", "planned": "Planned",
                                                    "retired": "No longer used"}[s])
        roles = [None] + list(AR.ROLES)
        role = e_.selectbox(tr("Your role for this use"), roles, index=roles.index(u.get("role")),
                            format_func=lambda r: "Same as the system" if r is None else AR.ROLES[r])

        st.markdown(tr("**Do you become the provider? (Art. 25)**"))
        a, b, c = st.columns(3)
        own = _tri(a, "Your name or trademark on it", u.get("own_name_or_brand"), f"{key}_own")
        mod = _tri(b, "Modified it substantially", u.get("substantially_modified"), f"{key}_mod",
                   help="Beyond configuration: retraining, changing what it does.")
        purp = _tri(c, "Changed its intended purpose", u.get("purpose_changed"), f"{key}_purp",
                    help="Using it for something the vendor did not intend, in a way that makes it high-risk.")

        st.markdown(tr("**Prohibited practices (Art. 5)**"))
        cur_pr = u.get("prohibited_practices")
        pr = st.multiselect(tr("Does this use do any of these?"), [r["code"] for r in practices],
                            default=[c_ for c_ in (cur_pr or []) if c_ in practice_label],
                            format_func=lambda c_: practice_label[c_],
                            help=tr("Leave empty and tick the box below if none applies."))
        screened = st.checkbox(tr("I checked: none of these applies"), value=cur_pr == [])

        st.markdown(tr("**High risk (Annex III)**"))
        areas = [None, "none"] + [r["code"] for r in annex]
        area = st.selectbox(tr("Is it used in one of these areas?"), areas,
                            index=areas.index(u.get("annex_iii_area")) if u.get("annex_iii_area") in areas else 0,
                            format_func=lambda c_: {None: "Not answered", "none": "None of these"}.get(
                                c_, annex_label.get(c_, c_)),
                            help="; ".join(f"{r['label_en']}: {r['note_en']}" for r in annex[:4]) + " …")
        a, b = st.columns(2)
        conds = [None] + list(AR.ART6_3)
        cond = a.selectbox(tr("Only if an area applies: is it one of the Art. 6(3) exceptions?"), conds,
                           index=conds.index(u.get("art6_3_condition")),
                           format_func=lambda c_: "No exception" if c_ is None else AR.ART6_3[c_])
        prof = _tri(b, "Does it profile people?", u.get("profiles_people"), f"{key}_prof",
                    help="Profiling always makes an Annex III use high-risk, whatever the exception.")
        reason = st.text_input(tr("Why the exception applies"), value=u.get("art6_3_reason") or "",
                               help=tr("Art. 6(4): a provider relying on it must document the assessment."))

        st.markdown(tr("**Transparency (Art. 50)**"))
        tcols = st.columns(len(AR.TRANSPARENCY))
        tvals = {k: _tri(col, label, u.get(k), f"{key}_{k}")
                 for col, (k, label, _ob) in zip(tcols, AR.TRANSPARENCY)}

        st.markdown(tr("**If high-risk (Art. 26, from 2 Dec 2027)**"))
        a, b = st.columns(2)
        workers = _tri(a, "Used on your workers", u.get("used_on_workers"), f"{key}_work",
                       help="Workers and their representatives must be told first (Art. 26(7)).")
        eids = [None] + list(emp_label)
        over = b.selectbox(tr("Human overseer"), eids,
                           index=eids.index(u.get("oversight_employee_id")) if u.get("oversight_employee_id") in eids else 0,
                           format_func=lambda i: "Nobody named" if i is None else emp_label[i],
                           help=tr("From the Training page's people. Mark them there as overseeing a "
                                "high-risk AI system so their training is tracked."))
        notes = st.text_input(tr("Notes"), value=u.get("notes") or "")
        if st.form_submit_button("Add use case" if new else "Save", type="primary", disabled=not editable):
            if not name.strip():
                st.error(tr("A name is needed."))
                return None
            if pr and screened:
                st.error(tr("You ticked practices and also 'none of these applies'."))
                return None
            return {"system_id": system_id, "name": name, "description": desc, "business_owner": owner,
                    "status": status, "role": role, "own_name_or_brand": own,
                    "substantially_modified": mod, "purpose_changed": purp,
                    "prohibited_practices": pr if pr else ([] if screened else None),
                    "annex_iii_area": area, "art6_3_condition": cond, "art6_3_reason": reason,
                    "profiles_people": prof, **tvals, "used_on_workers": workers,
                    "oversight_employee_id": over, "notes": notes}
    return None


with tab_uc:
    if not ai_systems:
        st.info(tr("No AI system yet. Mark one on the **AI systems** tab first."))
    else:
        shown = sorted(use_cases, key=lambda u: (not AR.active(u), u.get("name") or ""))
        if shown:
            rows = []
            for u in shown:
                c = AR.classify(u)
                role, _ = AR.effective_role(u, sys_by_id.get(u["system_id"]))
                rows.append({"id": u["id"], "cells": {
                    "risk": f"{AR.RISK_ICON[c['risk']]} {AR.RISK_LABELS[c['risk']]}",
                    "name": u["name"] + ("" if AR.active(u) else " (no longer used)"),
                    "system": (sys_by_id.get(u["system_id"]) or {}).get("name"),
                    "role": AR.ROLES.get(role, "—").split(" —")[0] if role else "—",
                }, "actions": [{"id": "open", "label": "Open", "icon": "📂"}]})
            hit = tv.table(rows, [{"key": "risk", "label": "Risk"}, {"key": "name", "label": "Use"},
                                  {"key": "system", "label": "AI system"}, {"key": "role", "label": "Role"}],
                           key="ai_use_cases", current=st.session_state.get("ai_uc"))
            if hit:
                st.session_state["ai_uc"] = hit["row"]
        sel = next((u for u in use_cases if u["id"] == st.session_state.get("ai_uc")), None)
        if sel:
            tv.focus("ai_use_cases")
            c = AR.classify(sel, annex_label)
            role, why = AR.effective_role(sel, sys_by_id.get(sel["system_id"]))
            with st.container(border=True):
                st.markdown(f"**{AR.RISK_ICON[c['risk']]} {sel['name']}** — {AR.RISK_LABELS[c['risk']]}")
                for r in c["reasons"]:
                    st.caption(r)
                if c["open"]:
                    st.caption("Still to answer: " + "; ".join(c["open"]))
                st.caption(f"Role: **{AR.ROLES.get(role, 'not recorded')}**. {why}")
                from obligations import OBLIGATION_BY_ID
                duties = [OBLIGATION_BY_ID[o] for o in AR.duties(sel, sys_by_id.get(sel["system_id"]))
                          if o in OBLIGATION_BY_ID]
                with st.expander(f"What this use brings into play ({len(duties)} obligations)"):
                    for o in duties:
                        st.markdown(f"- {o['title']} ({o['article']})")
                upd = _uc_form(f"ai_uc_{sel['id']}", sel)
                if upd:
                    if AIS.save_use_case(user_id, client_id, upd, sel["id"]):
                        st.success(tr("Saved."))
                        st.rerun()
                    st.error(tr("Could not save. If you have read-only access, an admin must do this."))
                with st.expander(tr("Delete this use case")):
                    st.caption(tr("If it stopped, set its status to **No longer used** instead: the "
                               "record of what you assessed stays."))
                    if st.button(tr("Delete permanently"), key=f"ai_ucdel_{sel['id']}", disabled=not editable):
                        if AIS.delete_use_case(user_id, client_id, sel["id"]):
                            st.session_state.pop("ai_uc", None)
                            st.rerun()

        st.subheader(tr("Add a use case"))
        new = _uc_form("ai_uc_new")
        if new:
            if AIS.save_use_case(user_id, client_id, new):
                st.success(tr("Added."))
                st.rerun()
            st.error(tr("Could not add. If you have read-only access, an admin must do this."))
        st.caption(tr("Not asked here: whether the AI is a safety component of a product covered by "
                   "EU product law (Art. 6(1), Annex I). That is a provider question; if it may "
                   "apply to you, ask your provider."))


# ── AI systems ────────────────────────────────────────────────────────────
with tab_sys:
    st.caption(tr("These are your Systems-page systems, marked as AI. Changing the role here "
               "changes it there."))
    if not systems:
        st.info(tr("No systems in your inventory yet. Add them on the **Systems** page."))
    for s in ai_systems:
        with st.container(border=True):
            ucs = [u for u in use_cases if u["system_id"] == s["id"] and AR.active(u)]
            st.markdown(f"**{s.get('name')}** · {s.get('vendor_legal_name') or ''}")
            st.caption(f"Default role: {AR.ROLES.get(s.get('ai_role'), s.get('ai_role'))} · "
                       f"{len(ucs)} use{'s' if len(ucs) != 1 else ''}")
            current = [l_["model_id"] for l_ in links if l_["system_id"] == s["id"]]
            with st.form(f"ai_sys_{s['id']}"):
                a, b = st.columns([2, 1])
                pick = a.multiselect(tr("Built on"), list(model_by_id), default=current,
                                     format_func=lambda i: model_by_id[i]["name"],
                                     help=tr("Add models on the Models tab."))
                roles = ["none"] + list(AR.ROLES)
                role = b.selectbox(tr("Default role"), roles, index=roles.index(s.get("ai_role") or "none"),
                                   format_func=lambda r: "Not an AI system" if r == "none" else AR.ROLES[r])
                if st.form_submit_button(tr("Save"), disabled=not editable):
                    ok = AIS.set_system_models(user_id, client_id, s["id"], pick)
                    if role != s.get("ai_role"):
                        ok = AIS.set_ai_role(user_id, client_id, s["id"], role) and ok
                    if ok:
                        st.rerun()
                    st.error(tr("Could not save."))
    others = [s for s in systems if not AR.is_ai_system(s)]
    if others:
        st.subheader(tr("Mark a system as AI"))
        with st.form("ai_mark"):
            a, b = st.columns([2, 1])
            sid = a.selectbox(tr("System"), [s["id"] for s in others],
                              format_func=lambda i: sys_by_id[i].get("name") or "?")
            role = b.selectbox(tr("Your role"), list(AR.ROLES), format_func=lambda r: AR.ROLES[r])
            if st.form_submit_button(tr("Mark as AI"), disabled=not editable):
                if AIS.set_ai_role(user_id, client_id, sid, role):
                    st.rerun()
                st.error(tr("Could not save."))


# ── Models ────────────────────────────────────────────────────────────────
_ORIG = {"third_party": "From a supplier", "open_weights": "Open weights", "in_house": "Built in-house"}


def _model_form(key: str, m: dict | None = None):
    m = m or {}
    with st.form(key, clear_on_submit=not m):
        a, b, c = st.columns(3)
        name = a.text_input(tr("Model"), value=m.get("name") or "", placeholder=tr("GPT-4o"))
        supplier = b.text_input(tr("Supplier"), value=m.get("supplier") or "", placeholder=tr("OpenAI"))
        version = c.text_input(tr("Version"), value=m.get("version") or "")
        a, b = st.columns(2)
        origins = list(_ORIG)
        origin = a.selectbox(tr("Origin"), origins, index=origins.index(m.get("origin") or "third_party"),
                             format_func=lambda o: _ORIG[o])
        gp = _tri(b, "General-purpose model", m.get("general_purpose"), f"{key}_gp",
                  help="A model that can do many distinct tasks (Art. 3(63)), such as a large language model.")
        doc = st.text_input(tr("Supplier's documentation (URL)"), value=m.get("documentation_url") or "")
        notes = st.text_input(tr("Notes"), value=m.get("notes") or "")
        if st.form_submit_button("Save" if m else "Add model", type="primary", disabled=not editable):
            if not name.strip():
                st.error(tr("A name is needed."))
                return None
            return {"name": name, "supplier": supplier, "version": version, "origin": origin,
                    "general_purpose": gp, "documentation_url": doc, "notes": notes}
    return None


with tab_models:
    st.caption(tr("What your AI systems are built on. One model can sit under several systems."))
    for m in models:
        used = [sys_by_id[l_["system_id"]].get("name") for l_ in links
                if l_["model_id"] == m["id"] and l_["system_id"] in sys_by_id]
        with st.expander(f"{m['name']} · {m.get('supplier') or ''} — used by "
                         f"{', '.join(used) if used else 'no system yet'}"):
            upd = _model_form(f"ai_m_{m['id']}", m)
            if upd:
                if AIS.save_model(user_id, client_id, upd, m["id"]):
                    st.rerun()
                st.error(tr("Could not save."))
            if st.button(tr("Delete this model"), key=f"ai_mdel_{m['id']}", disabled=not editable):
                if AIS.delete_model(user_id, client_id, m["id"]):
                    st.rerun()
    st.subheader(tr("Add a model"))
    new = _model_form("ai_m_new")
    if new:
        if AIS.save_model(user_id, client_id, new):
            st.success(tr("Added."))
            st.rerun()
        st.error(tr("Could not add."))
