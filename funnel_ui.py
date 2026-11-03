"""
funnel_ui.py — S49. The quick checks' screens (NIS2, and the AI Act since
S55: pass kind=funnel.AI_ACT), drawn the same way in the public app
(quiz/quiz_app.py) and on the client app's result page.

Streamlit only. No Supabase: the callers decide what to store.
"""

import streamlit as st

import funnel


def render_quiz_form(key: str = "nis2_quiz", kind: dict = funnel.NIS2) -> list[int] | None:
    """The questions. Returns the answers once all are submitted, else None
    (with a warning if the form was submitted incomplete)."""
    questions = kind["questions"]
    with st.form(key):
        answers = []
        for i, q in enumerate(questions):
            st.markdown(f"**{i + 1}. {q['category']}**")
            opts = funnel.options_for(q)
            choice = st.radio(
                q["question"], options=range(len(opts)),
                format_func=lambda i, opts=opts: opts[i],
                key=f"{key}_q_{i}", index=None,
            )
            answers.append(choice)
            st.write("")
        submitted = st.form_submit_button("See my result", type="primary")

    if not submitted:
        return None
    if any(a is None for a in answers):
        st.warning(f"Answer all {len(questions)} questions to see your result.")
        return None
    return answers


def render_quiz_score(answers: list[int], kind: dict = funnel.NIS2) -> None:
    total = funnel.score(answers)
    label, blurb = funnel.band(total, kind)
    st.subheader(f"Your result: {total}/{funnel.max_score(kind)} — {label}")
    st.write(blurb)


def render_quiz_breakdown(answers: list[int], locked: bool, kind: dict = funnel.NIS2) -> None:
    """Locked: the area names only, and how many need attention (the free
    teaser, D-115). Unlocked: every area's level and what to do, weakest
    first."""
    rows = funnel.breakdown(answers, kind)
    if locked:
        weak = funnel.weak_areas(answers)
        st.markdown(
            f"**Your breakdown by area** — {weak} of {len(rows)} areas "
            f"{'need' if weak != 1 else 'needs'} attention"
        )
        for r in rows:
            st.markdown(f"🔒 {r['category']}")
        return

    st.markdown(f"**Your {_WORDS.get(len(rows), len(rows))} areas, weakest first**")
    icon = ["🔴", "🟠", "🟡", "🟢"]
    for r in rows:
        with st.container(border=True):
            st.markdown(f"{icon[r['answer']]} **{r['category']}** — {r['level']}")
            st.caption(r["advice"])


_WORDS = {8: "eight", 10: "ten"}


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
        st.markdown(f"{icon} **{reg}** — {label}  \n:gray[{why}]")
