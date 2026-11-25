"""
pages_admin/lifecycle.py — D-216. Where every account is in its lifecycle,
and which emails it got: the view agreed with the user on 25 Nov.

Top: how many accounts per stage. Then one lane per stage — its emails as
dots on the days they go out, and each account placed on the day it is on.
Then every account in a table; a click opens its history (sign-up, company,
status changes, each email sent, opt-out, last sign-in).

The lanes read the flows' own schedules (lifecycle_view.LANES), so what is
drawn is what monitor_lifecycle.py sends. Admin and test accounts are left
out unless asked for.
"""

import html as _h
from datetime import datetime, timezone

import streamlit as st

import lifecycle_view as LV
import table_view as tv
from database import get_supabase_admin

st.title("Lifecycle")
st.caption("Where each account is — trial, customer, drop-out, churned — and the lifecycle "
           "emails it got. The emails are sent by the hourly job (monitor_lifecycle.py).")

sb = get_supabase_admin()
include_internal = st.toggle("Include admin and test accounts", value=False, key="lc_internal")
rows = LV.load(sb, include_internal=include_internal)
pros = LV.prospects(sb)

# ── Counts ────────────────────────────────────────────────────────────────
by_stage = {s: [r for r in rows if r["stage"] == s] for s in LV.STAGES}
cols = st.columns(7)
cols[0].metric("Prospects (30 days)", pros.get("check_landing", 0),
               help="Visits to the free check in the last 30 days.")
for col, (stage, label) in zip(cols[1:], [("trial", "Trial"), ("customer", "Customers"),
                                          ("dropout", "Drop-outs"), ("churned", "Churned"),
                                          ("registered", "Trial not started"),
                                          ("blocked", "Blocked")]):
    col.metric(label, len(by_stage[stage]))

# ── Timeline ──────────────────────────────────────────────────────────────
FLOW_COLOR = {"onboarding": "#0F6E56", "trial_ending": "#854F0B", "expired_trial": "#993C1D",
              "churned": "#993556", "payments": "#185FA5"}
CHIP = {"trial": ("#E1F5EE", "#085041"), "customer": ("#E6F1FB", "#0C447C"),
        "dropout": ("#FAECE7", "#712B13"), "churned": ("#FBEAF0", "#72243E")}


def _lane(title: str, sub: str, length: int, emails: list, accounts: list, stage: str,
          end_label: str = "") -> str:
    ticks = "".join(
        f'<span title="{_h.escape(key)} — day {d}{"" if live else " (not sent yet)"}" '
        f'style="position:absolute;left:{min(d / length, 1) * 100:.1f}%;top:-19px;transform:translateX(-50%);'
        f'font-size:11px;color:{FLOW_COLOR.get(flow, "#555")};opacity:{1 if live else .45};white-space:nowrap">'
        f'{d}<span style="display:block;margin:2px auto 0;width:9px;height:9px;border-radius:50%;'
        f'background:#fff;border:1.5px {"solid" if live else "dashed"} currentColor"></span></span>'
        for d, key, flow, live in emails)
    bg, fg = CHIP.get(stage, ("#eee", "#333"))
    chips = "".join(
        f'<span title="{_h.escape(r["name"])} — day {r["day"]}" style="position:absolute;'
        f'left:{min((r["day"] or 0) / length, 1) * 100:.1f}%;top:{12 + 22 * (i % 3)}px;transform:translateX(-50%);'
        f'font-size:11px;padding:1px 7px;border-radius:6px;background:{bg};color:{fg};white-space:nowrap">'
        f'{_h.escape(r["name"][:22])}</span>'
        for i, r in enumerate(sorted(accounts, key=lambda r: r["day"] or 0)))
    end = (f'<span style="position:absolute;right:0;top:12px;font-size:11px;color:#A32D2D">'
           f'{_h.escape(end_label)}</span>' if end_label else "")
    height = 26 + 22 * min(max(len(accounts), 1), 3)
    return (f'<div style="display:grid;grid-template-columns:130px 1fr;gap:14px;padding:14px 0 4px;'
            f'border-top:1px solid #e8edf2"><div><div style="font-weight:600;font-size:14px">{title}</div>'
            f'<div style="font-size:12px;color:#6b7280">{sub}</div></div>'
            f'<div style="position:relative;height:6px;border-radius:3px;background:#eef1f4;'
            f'margin:24px 0 {height}px">{ticks}{chips}{end}</div></div>')


lanes = [
    _lane("Trial", "days 0–13", 14, LV.LANES["trial"][1], by_stage["trial"], "trial"),
    _lane("Customer", "paying or voucher", 30, LV.LANES["customer"][1],
          [{**r, "day": min(r["day"] or 0, 30)} for r in by_stage["customer"]], "customer",
          "payment emails: with Mollie"),
    _lane("Drop-out", "trial ended, no plan", 60, LV.LANES["dropout"][1], by_stage["dropout"],
          "dropout", "60: deletion (not built)"),
    _lane("Churned", "cancelled after paying", 120, LV.LANES["churned"][1], by_stage["churned"],
          "churned", "120: deletion (not built)"),
]
prospect_line = (
    f'<div style="display:grid;grid-template-columns:130px 1fr;gap:14px;padding:4px 0 10px">'
    f'<div><div style="font-weight:600;font-size:14px">Prospect</div>'
    f'<div style="font-size:12px;color:#6b7280">free check, 30 days</div></div>'
    f'<div style="font-size:13px;color:#333;padding-top:6px">'
    f'{pros.get("check_landing", 0)} visits → {pros.get("scope_completed", 0)} answered the scope → '
    f'{pros.get("results_viewed", 0)} saw their results → {pros.get("signup", 0)} signed up</div></div>')
legend = ('<div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:#6b7280;'
          'padding-top:10px;border-top:1px solid #e8edf2">'
          + "".join(f'<span style="color:{c}">● {n}</span>' for n, c in [
              ("Onboarding", FLOW_COLOR["onboarding"]), ("Trial ending", FLOW_COLOR["trial_ending"]),
              ("Drop-out", FLOW_COLOR["expired_trial"]), ("Churned (not built)", FLOW_COLOR["churned"])])
          + '<span>Dots: emails on the day they go out (dashed: not sent yet) · chips: accounts '
            'on their current day · hover for names</span></div>')
st.html(f'<div style="font-family:sans-serif">{prospect_line}{"".join(lanes)}{legend}</div>')

# ── Accounts ──────────────────────────────────────────────────────────────
st.subheader("Accounts")
if not rows:
    st.info("No account yet" + ("" if include_internal else " (admin and test accounts hidden)") + ".")
    st.stop()


def _last(r):
    if not r["emails"]:
        return None
    e = r["emails"][-1]
    return f"{e['email_key']} ({e['sent_at'][:10]})"


table_rows = [{
    "id": r["id"],
    "cells": {
        "name": r["name"], "owner": (r["owner"] or {}).get("email"),
        "stage": (LV.STAGES[r["stage"]], list(LV.STAGES).index(r["stage"])), "day": r["day"],
        "sent": len(r["emails"]), "last": _last(r),
        "next": ((f"now: {r['next'][1]}" if r["day"] is not None and r["next"][0] <= r["day"]
                  else f"day {r['next'][0]}: {r['next'][1]}") if r["next"] else None),
        "stop": "yes" if r["opted_out"] else None,
    },
    "actions": [{"id": "open", "label": "History", "icon": "📜"}],
} for r in rows]
hit = tv.table(table_rows, [
    {"key": "name", "label": "Company / account"}, {"key": "owner", "label": "Owner"},
    {"key": "stage", "label": "Stage"}, {"key": "day", "label": "Day"},
    {"key": "sent", "label": "Emails"}, {"key": "last", "label": "Last email"},
    {"key": "next", "label": "Next planned"}, {"key": "stop", "label": "Stopped emails"},
], key="lifecycle", sort=("stage", "asc"), current=st.session_state.get("lc_open"))
if hit:
    st.session_state["lc_open"] = hit["row"]

sel = next((r for r in rows if r["id"] == st.session_state.get("lc_open")), None)
if sel:
    st.divider()
    tv.focus("lifecycle")   # below a long table the history opened out of sight
    st.markdown(f"#### {sel['name']}")
    st.caption(f"{LV.STAGES[sel['stage']]}" + (f", day {sel['day']}" if sel["day"] is not None else "")
               + f" · owner {(sel['owner'] or {}).get('email', '—')}"
               + (f" · language {(sel['owner'] or {}).get('ui_language') or 'en'}"))
    events = LV.history(sb, sel)
    if events:
        tv.table([{"id": str(i), "cells": {"when": when, "what": what}}
                  for i, (when, what) in enumerate(events)],
                 [{"key": "when", "label": "When", "kind": "datetime"},
                  {"key": "what", "label": "What happened", "sortable": False}],
                 key=f"lc_hist_{sel['id']}", sort=("when", "asc"))
    else:
        st.caption("Nothing recorded yet.")
