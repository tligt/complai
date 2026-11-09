"""
table_view.py — the shared table: sortable columns and a ⋮ menu at the end
of every row (BO review, 9 Nov, points 4–6; used in the back office first,
then the client app).

    res = table_view.table(
        rows=[{"id": "a1", "cells": {"name": "Acme", "since": dt}, "actions": [...]}, ...],
        columns=[{"key": "name", "label": "Account"}, {"key": "since", "label": "Since", "kind": "date"}],
        key="accounts",
    )
    if res: row_id, action = res["row"], res["action"]

An action is {"id", "label"} plus optional "icon" (an emoji), "danger" (red),
and "disabled": a reason string — the item stays in the menu, greyed, with a
lock and the reason (point 5: what can't be changed is shown, with why).
Clicking a row (anywhere but the menu) chooses its "open" action, if it has
one; otherwise a click does nothing. The click comes back once, on the run it caused; the page
acts on it (opens a panel, a dialog, …).

Cells are formatted here, in Python, and sorted on their raw value, so a
date sorts as a date and an empty cell sorts last. Values travel as data and
are inserted as text, never as HTML.

A components-v2 element (like the cookie bridge in sessions.py), in a shadow
root so its styles stay its own.
"""

from __future__ import annotations

from datetime import date, datetime

import streamlit as st

_CSS = """
:host { display: block; font-family: inherit; }
.wrap { position: relative; border: 1px solid #e3e6ea; border-radius: 10px; background: #fff; }
.scroll { overflow-x: auto; border-radius: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; color: #1f2937; }
th { text-align: left; font-weight: 600; font-size: 13px; color: #4b5563; background: #f6f7f9;
     padding: 10px 12px; border-bottom: 1px solid #e3e6ea; white-space: nowrap; user-select: none; }
th.sortable { cursor: pointer; }
th.sortable:hover { color: #003366; }
th .arrow { display: inline-block; width: 14px; color: #003366; font-size: 12px; }
td { padding: 10px 12px; border-bottom: 1px solid #eef0f3; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tbody tr { cursor: pointer; }
tbody tr:hover td { background: #f3f6fa; }
tbody tr.current td { background: #e8eef6; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.muted { color: #9aa1ab; }
td.menu-cell { width: 44px; text-align: right; padding: 6px 8px; }
button.dots { border: 1px solid #d9dde3; background: #fff; border-radius: 8px; width: 32px; height: 30px;
              font-size: 18px; line-height: 1; color: #374151; cursor: pointer; }
button.dots:hover, button.dots[aria-expanded="true"] { border-color: #003366; color: #003366; }
.menu { position: absolute; z-index: 50; min-width: 220px; background: #fff;
        border: 1px solid #d9dde3; border-radius: 10px; box-shadow: 0 8px 24px rgba(16,24,40,.14);
        padding: 6px; text-align: left; }
.item { display: flex; gap: 8px; align-items: flex-start; width: 100%; border: 0; background: none;
        text-align: left; padding: 8px 10px; border-radius: 7px; font: inherit; font-size: 14px;
        color: #1f2937; cursor: pointer; }
.item:hover:not([disabled]) { background: #f0f4f9; color: #003366; }
.item.danger { color: #b42318; }
.item[disabled] { color: #9aa1ab; cursor: not-allowed; }
.item .why { display: block; font-size: 12px; color: #9aa1ab; margin-top: 2px; }
.empty { padding: 18px; color: #6b7280; font-size: 14px; }
"""

_JS = r"""
const SORT = new Map();   // key -> {col, dir}: the sort survives reruns in the tab
const CLOSERS = new Set(); // one document listener closes every open menu
let bound = false;

function text(el, s) { el.textContent = s == null ? "" : String(s); return el; }

function cmp(a, b) {
  const ea = a === null || a === undefined || a === "", eb = b === null || b === undefined || b === "";
  if (ea && eb) return 0; if (ea) return 1; if (eb) return -1;      // empty last
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, {numeric: true, sensitivity: "base"});
}

export default function(component) {
  const { data, parentElement, setTriggerValue } = component;
  const d = data || {};
  const cols = d.columns || [], rows = d.rows || [];
  const key = d.key || "t";
  let root = parentElement.querySelector(".wrap");
  if (root) root.remove();
  root = document.createElement("div"); root.className = "wrap";
  parentElement.appendChild(root);

  const scroll = document.createElement("div"); scroll.className = "scroll"; root.appendChild(scroll);
  const table = document.createElement("table"); scroll.appendChild(table);
  const thead = table.createTHead(), hr = thead.insertRow();
  const sort = SORT.get(key) || d.sort || null;

  cols.forEach((c, i) => {
    const th = document.createElement("th");
    if (c.width) th.style.width = c.width;
    if (c.sortable !== false) {
      th.className = "sortable";
      th.title = "Sort by " + c.label;
      th.onclick = () => {
        const cur = SORT.get(key) || d.sort;
        const dir = cur && cur.col === i && cur.dir === "asc" ? "desc" : "asc";
        SORT.set(key, {col: i, dir}); draw();
      };
    }
    text(th, c.label);
    const arrow = document.createElement("span"); arrow.className = "arrow";
    if (sort && sort.col === i) arrow.textContent = sort.dir === "asc" ? " ↑" : " ↓";
    th.appendChild(arrow);
    hr.appendChild(th);
  });
  const anyActions = rows.some(r => (r.actions || []).length);
  if (anyActions) { const th = document.createElement("th"); th.style.width = "44px"; hr.appendChild(th); }

  const tbody = table.createTBody();
  let openMenu = null;
  function closeMenu() { if (openMenu) { openMenu.menu.remove(); openMenu.btn.setAttribute("aria-expanded", "false"); openMenu = null; } }
  CLOSERS.add(closeMenu);
  if (!bound) { bound = true; document.addEventListener("click", () => CLOSERS.forEach(f => f())); }

  function draw() {
    closeMenu();
    const s = SORT.get(key) || d.sort;
    hr.querySelectorAll(".arrow").forEach((a, i) => { a.textContent = s && s.col === i ? (s.dir === "asc" ? " ↑" : " ↓") : ""; });
    const order = rows.slice();
    if (s) order.sort((a, b) => { const r = cmp(a.sort[s.col], b.sort[s.col]); return s.dir === "asc" ? r : -r; });
    tbody.textContent = "";
    if (!order.length) {
      const tr = tbody.insertRow(), td = tr.insertCell();
      td.colSpan = cols.length + (anyActions ? 1 : 0); td.className = "muted"; text(td, d.empty || "Nothing to show.");
      return;
    }
    order.forEach(r => {
      const tr = tbody.insertRow();
      if (r.id === d.current) tr.className = "current";
      cols.forEach((c, i) => {
        const td = tr.insertCell();
        const v = r.cells[i];
        if (c.kind === "number") td.className = "num";
        if (v === "" || v === null || v === undefined) { td.classList.add("muted"); text(td, "—"); }
        else text(td, v);
      });
      const acts = r.actions || [];
      const first = acts.find(a => a.id === "open" && !a.disabled);
      if (first) tr.onclick = () => setTriggerValue("action", {row: r.id, action: first.id, n: Date.now()});
      if (anyActions) {
        const td = tr.insertCell(); td.className = "menu-cell";
        if (acts.length) {
          const btn = document.createElement("button");
          btn.className = "dots"; btn.textContent = "⋮"; btn.title = "Actions";
          btn.setAttribute("aria-haspopup", "menu"); btn.setAttribute("aria-expanded", "false");
          btn.onclick = (e) => {
            e.stopPropagation();
            if (openMenu && openMenu.btn === btn) { closeMenu(); return; }
            closeMenu();
            const menu = document.createElement("div"); menu.className = "menu"; menu.setAttribute("role", "menu");
            acts.forEach(a => {
              const it = document.createElement("button");
              it.className = "item" + (a.danger ? " danger" : ""); it.setAttribute("role", "menuitem");
              const label = document.createElement("span");
              text(label, (a.disabled ? "🔒 " : (a.icon ? a.icon + " " : "")) + a.label);
              if (a.disabled) {
                it.disabled = true; it.title = a.disabled;
                const why = document.createElement("span"); why.className = "why"; text(why, a.disabled);
                label.appendChild(why);
              } else {
                it.onclick = (ev) => { ev.stopPropagation(); closeMenu(); setTriggerValue("action", {row: r.id, action: a.id, n: Date.now()}); };
              }
              it.appendChild(label); menu.appendChild(it);
            });
            // On the table's frame, not in the cell: the scrolling area would
            // cut it off. Opens upwards when the window has no room below.
            root.appendChild(menu);
            const b = btn.getBoundingClientRect(), w = root.getBoundingClientRect();
            menu.style.right = (w.right - b.right) + "px";
            if (window.innerHeight - b.bottom < menu.offsetHeight + 12 && b.top > menu.offsetHeight + 12)
              menu.style.top = (b.top - w.top - menu.offsetHeight - 4) + "px";
            else menu.style.top = (b.bottom - w.top + 4) + "px";
            btn.setAttribute("aria-expanded", "true");
            openMenu = {menu, btn};
          };
          td.onclick = (e) => e.stopPropagation();
          td.appendChild(btn);
        }
      }
    });
  }
  draw();
  root.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
}
"""

_component = None


def _fmt(v, kind: str | None) -> tuple[str, object]:
    """(what the cell shows, what it sorts on)."""
    if v is None or v == "":
        return "", None
    if kind in ("date", "datetime") and isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v, v
    if isinstance(v, datetime):
        shown = v.strftime("%d %b %Y, %H:%M") if kind == "datetime" else v.strftime("%d %b %Y")
        return shown, v.isoformat()
    if isinstance(v, date):
        return v.strftime("%d %b %Y"), v.isoformat()
    if isinstance(v, bool):
        return ("Yes" if v else "No"), int(v)
    if isinstance(v, (int, float)):
        return f"{v:,}".replace(",", " ") if isinstance(v, int) else f"{v:,.2f}", v
    return str(v), str(v).lower()


def table(rows: list[dict], columns: list[dict], *, key: str,
          sort: tuple[str, str] | None = None, current: str | None = None,
          empty: str = "Nothing to show.") -> dict | None:
    """Draw the table. Returns {"row": id, "action": id} on the run caused by
    a click, else None. `sort`: the initial (column key, "asc"|"desc");
    `current`: the id of the row to highlight (the one open below)."""
    global _component
    import streamlit.components.v2 as components_v2

    keys = [c["key"] for c in columns]
    payload = []
    for r in rows:
        cells, sorts = [], []
        for c in columns:
            shown, s = _fmt(r["cells"].get(c["key"]), c.get("kind"))
            cells.append(shown)
            sorts.append(s)
        payload.append({"id": str(r["id"]), "cells": cells, "sort": sorts,
                        "actions": [{k: a[k] for k in ("id", "label", "icon", "disabled", "danger") if a.get(k)}
                                    for a in r.get("actions") or []]})
    data = {
        "key": key, "empty": empty, "current": current,
        "columns": [{"label": c["label"], "kind": c.get("kind"), "width": c.get("width"),
                     "sortable": c.get("sortable", True)} for c in columns],
        "rows": payload,
        "sort": ({"col": keys.index(sort[0]), "dir": sort[1]} if sort and sort[0] in keys else None),
    }

    def mount():
        return _component(key=f"tv_{key}", data=data,
                          on_action_change=lambda: None)

    if _component is None:
        _component = components_v2.component("recosa_table_view", css=_CSS, js=_JS)
    try:
        res = mount()
    except ValueError:          # a new runtime in the same process: register again
        _component = components_v2.component("recosa_table_view", css=_CSS, js=_JS)
        res = mount()
    hit = getattr(res, "action", None)
    if not (isinstance(hit, dict) and hit.get("row") and hit.get("action")):
        return None
    # A click is reported once. The component can hand the same click back
    # on a later run (seen 9 Nov: after "Cancel" the task reopened), so each
    # click carries its time and one already acted on is ignored.
    seen_key = f"_tv_seen_{key}"
    if hit.get("n") is not None and st.session_state.get(seen_key) == hit["n"]:
        return None
    st.session_state[seen_key] = hit.get("n")
    return {"row": hit["row"], "action": hit["action"]}


def locked(label: str, value, reason: str, key: str | None = None) -> None:
    """A field shown but not editable, with why (BO review, point 5)."""
    st.text_input(f"🔒 {label}", value="" if value is None else str(value), disabled=True,
                  help=reason, key=key)
