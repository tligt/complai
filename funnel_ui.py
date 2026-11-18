"""
funnel_ui.py — S49. The quick checks' screens (NIS2, and the AI Act since
S55: pass kind=funnel.AI_ACT), drawn the same way in the public app
(quiz/quiz_app.py) and on the client app's result page.

Streamlit only. No Supabase: the callers decide what to store.
"""
from i18n import tr  # S64 interface translation (D-164)

import os

import streamlit as st

import funnel

# As in funnel.py: the public app reloads this module when the file is newer.
_LOADED_MTIME = os.path.getmtime(__file__)


def render_quiz_form(key: str = "nis2_quiz", kind: dict = funnel.NIS2,
                     previous: list[int] | None = None,
                     submit_label: str = "See my result") -> list[int] | None:
    """The questions. Returns the answers once all are submitted, else None
    (with a warning if the form was submitted incomplete). previous: the
    answers given before, pre-selected when they are changed."""
    questions = kind["questions"]
    with st.form(key):
        answers = []
        for i, q in enumerate(questions):
            st.markdown(f"**{i + 1}. {q['category']}**")
            opts = funnel.options_for(q)
            choice = st.radio(
                q["question"], options=range(len(opts)),
                format_func=lambda i, opts=opts: opts[i],
                key=f"{key}_q_{i}",
                index=previous[i] if previous and i < len(previous) else None,
            )
            answers.append(choice)
            st.write("")
        submitted = st.form_submit_button(submit_label, type="primary",
                                          use_container_width=True)

    if not submitted:
        return None
    if any(a is None for a in answers):
        st.warning(tr("Answer all {len_questions} questions to see your result.").format(len_questions=len(questions)))
        return None
    return answers


def render_quiz_score(answers: list[int], kind: dict = funnel.NIS2) -> None:
    total = funnel.score(answers)
    label, blurb = funnel.band(total, kind, len(answers))
    st.subheader(tr("Your result: {total}/{funnel_max_score_kind_an} — {label}").format(total=total, funnel_max_score_kind_an=funnel.max_score(kind, answers), label=label))
    st.write(blurb)


def render_quiz_breakdown(answers: list[int], locked: bool, kind: dict = funnel.NIS2) -> None:
    """Locked: each area's state in the open, and only the advice locked
    (D-191, D-192). Unlocked: every area's level and what to do, weakest
    first.

    D-191 showed the verdict instead of ten padlocks. D-192 made it four
    states instead of two: answer 2 reads "documented, not regularly
    reviewed" (NIS2) or "partly in place" (GDPR, AI Act) and the register
    records it as partial (funnel._DECLARED_STATUS) — showing it green told a
    prospect who answered well that there was nothing left to do. Even the
    best answer is the company's own declaration, so its green carries
    "declared — to confirm". D-193 removed the locked line under each area:
    one line per area, and one sentence at the end on what the full report
    holds — no mention of an account, which read as "you have to pay"."""
    rows = funnel.breakdown(answers, kind)
    if locked:
        need = funnel.weak_areas(answers)
        declared = len(rows) - need
        st.markdown(tr("**Your breakdown by area** — {need} of {n} need work, {declared} declared "
                       "in place").format(need=need, n=len(rows), declared=declared))
        # D-193: one line per area, nothing under it — the state says it.
        for r in rows:                                    # weakest first
            icon, state = _STATE[r["answer"]]
            st.markdown(f"{icon} **{r['category']}** — {tr(state)}")
        if need and declared:
            cta = tr("**Fix the {need} that need work, and confirm the {declared} you declared**").format(
                need=_areas(need), declared=_areas(declared))
        elif need:
            cta = tr("**See how to fix {these}**").format(
                these=tr("this area") if need == 1 else tr("these {n} areas").format(n=need))
        else:
            cta = tr("**Confirm the {declared} you declared**").format(declared=_areas(declared))
        # D-193: no mention of an account here — it read as "you have to pay".
        # The flow brings them to the report; this only says what it holds.
        st.info(cta + tr(" — your full report will detail the actions to take."))
        return

    st.markdown(tr("**Your {words_get_len_rows_len_r} areas, weakest first**").format(words_get_len_rows_len_r=_WORDS.get(len(rows), len(rows))))
    icon = ["🔴", "🟠", "🟡", "🟢"]
    for r in rows:
        with st.container(border=True):
            st.markdown(f"{icon[r['answer']]} **{r['category']}** — {r['level']}")
            st.caption(r["advice"])


_WORDS = {8: "eight", 9: "nine", 10: "ten", 13: "thirteen"}

# D-192. The state of an area on the locked teaser, by answer (0-3).
_STATE = {
    0: ("🔴", "not in place"),
    1: ("🟠", "started"),
    2: ("🟡", "partly in place"),
    3: ("✅", "declared in place — to confirm"),
}


def _areas(n: int) -> str:
    return tr("1 area") if n == 1 else tr("{n} areas").format(n=n)


# D-129. How each verdict reads, beside the regulation's name.
_VERDICT = {
    funnel.APPLIES:  ("✅", "Applies"),
    funnel.LIKELY:   ("✅", "Likely applies"),
    funnel.POSSIBLE: ("🟡", "May apply"),
    funnel.UNLIKELY: ("⚪", "Unlikely"),
}


def render_rules(rules: dict) -> None:
    """The regulations from funnel.applicable_rules(), one line each."""
    for reg, (verdict, why) in rules.items():
        icon, label = _VERDICT[verdict]
        st.markdown(tr("{icon} **{reg}** — {label}  \n:gray[{why}]").format(icon=icon, reg=reg, label=label, why=why))
