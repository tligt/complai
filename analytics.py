"""
analytics.py — D-180, 16 Nov 2026: UTM tags and Umami events.

Two things the funnel lacked:

1. **UTM tags.** Links posted outside our own sites (LinkedIn, email,
   partners) carry the standard utm_* tags. Umami reads them from the
   address on its own; `utm_from_params` keeps them for our own
   funnel_events too (the `utm` column), next to `?src=`.

2. **Umami events.** The free check and the app are Streamlit: one page
   that redraws itself, so Umami sees a page load and nothing after it —
   not a check finished, an email given, a sign-up or a trial. `track`
   queues a named event; `flush`, called once per run, hands the queue to
   the visitor's browser, which calls `umami.track()`. From the browser,
   not our server: Umami ties events to a visitor by their browser and
   connection, so a server-side call would show up as a stranger and
   break the funnel.

   Events are content-free: the step, which check, and where the visitor
   came from. Never an email, a company name or an answer.

   Each event has an id; the browser remembers the ids it has sent
   (sessionStorage), so a rerun or a second mount never sends one twice.
   If Umami is blocked (an ad blocker) or not loaded, nothing happens.
"""

import uuid

import streamlit as st

UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term")

_QUEUE = "_umami_events"
_KEEP = 20


def utm_from_params(params) -> dict | None:
    """The utm_* values from a query string (st.query_params or a dict),
    trimmed. None when there are none."""
    out = {}
    for k in UTM_KEYS:
        v = (params.get(k) or "").strip()
        if v:
            out[k] = v[:80]
    return out or None


def track(name: str, **data) -> None:
    """Queue an Umami event for the visitor's browser. Empty values are
    dropped; keep `data` to short, non-personal strings."""
    clean = {k: str(v)[:80] for k, v in data.items() if v not in (None, "", [], {})}
    q = st.session_state.setdefault(_QUEUE, [])
    q.append({"id": uuid.uuid4().hex[:16], "name": name[:50], "data": clean})
    del q[:-_KEEP]


# A components-v2 element with no visible output. Values travel as data,
# never inlined into the script.
_JS = """
export default function(component) {
  const evs = ((component.data || {}).events) || [];
  if (!evs.length) return;
  const KEY = "recosa_umami_sent";
  const mem = (window.__recosaUmamiSent = window.__recosaUmamiSent || new Set());
  const load = () => {
    try { return new Set(JSON.parse(sessionStorage.getItem(KEY) || "[]")); }
    catch (e) { return new Set(); }
  };
  const fresh = () => { const s = load(); return evs.filter(e => !s.has(e.id) && !mem.has(e.id)); };
  if (!fresh().length) return;
  let tries = 0;
  const go = () => {
    const u = window.umami || (window.parent && window.parent.umami);
    if (!u || typeof u.track !== "function") {
      if (++tries < 40) setTimeout(go, 250);   // the script loads deferred: up to 10 s
      return;
    }
    const sent = load();
    for (const e of evs) {
      if (sent.has(e.id) || mem.has(e.id)) continue;
      mem.add(e.id); sent.add(e.id);
      try { u.track(e.name, e.data || {}); } catch (err) {}
    }
    try { sessionStorage.setItem(KEY, JSON.stringify([...sent].slice(-200))); } catch (err) {}
  };
  go();
}
"""
_component = None


def flush() -> None:
    """Hand the queued events to the browser. Call once per script run,
    early (before any st.stop), so events queued in the previous run go
    out even if this one stops short."""
    global _component
    q = st.session_state.get(_QUEUE)
    if not q:
        return
    import streamlit.components.v2 as components_v2

    def mount():
        _component(key="recosa_umami_events", data={"events": q})

    if _component is None:
        _component = components_v2.component("recosa_umami_events", js=_JS)
    try:
        mount()
    except ValueError:
        # A new runtime in the same process starts with an empty registry
        # (see sessions.bridge): register again.
        _component = components_v2.component("recosa_umami_events", js=_JS)
        mount()
    except Exception as e:
        # Analytics never breaks a page.
        print(f"Could not send Umami events: {e}")
