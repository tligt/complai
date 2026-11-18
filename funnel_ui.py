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
    """Locked: each area's verdict in the open — in place, or needs attention
    — and only the advice locked (D-191). Unlocked: every area's level and
    what to do, weakest first.

    D-191 changed the teaser. It showed the area names behind a lock each and
    "2 of 10 need attention" without saying which: ten identical padlocks read
    as bullet points, and the one thing the person had just earned was
    withheld. What brings someone to sign up is not whether an area is weak —
    they half know — but what to do about it, so that is what stays locked."""
    rows = funnel.breakdown(answers, kind)
    if locked:
        weak_rows = [r for r in rows if r["answer"] < 2]     # funnel.weak_areas's rule
        ok_rows = [r for r in rows if r["answer"] >= 2]
        weak = len(weak_rows)
        st.markdown(
            tr("**Your breakdown by area** — {weak} of {len_rows} areas {need_if_weak_1_else_need} attention").format(weak=weak, len_rows=len(rows), need_if_weak_1_else_need='need' if weak != 1 else 'needs')
        )
        for r in weak_rows:
            with st.container(border=True):
                st.markdown(tr("🟠 **{category}** — needs attention").format(category=r["category"]))
                st.caption(tr("🔒 What to do, and the document that covers it: in your full report."))
        for r in ok_rows:
            st.markdown(tr("✅ {category} — in place").format(category=r["category"]))
        if weak:
            st.info(tr("**See how to fix {these}** — your full report, with what to do for each "
                       "area, comes free with an account.").format(
                these=tr("this area") if weak == 1 else tr("these {n} areas").format(n=weak)))
        return

    st.markdown(tr("**Your {words_get_len_rows_len_r} areas, weakest first**").format(words_get_len_rows_len_r=_WORDS.get(len(rows), len(rows))))
    icon = ["🔴", "🟠", "🟡", "🟢"]
    for r in rows:
        with st.container(border=True):
            st.markdown(f"{icon[r['answer']]} **{r['category']}** — {r['level']}")
            st.caption(r["advice"])


_WORDS = {8: "eight", 9: "nine", 10: "ten", 13: "thirteen"}


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
