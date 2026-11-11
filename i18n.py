"""
i18n.py — S64 interface slice (D-164). The interface in the user's language.

    from i18n import tr
    st.title(tr("Training"))
    st.caption(tr("{n} people").format(n=3))

The English text is its own key, gettext-style: code stays readable, a string
with no translation shows in English (never blank, never a key), and a new
string needs nothing but the wrapper to appear in the catalogue.

The language is the USER's (profiles.ui_language, set on Account), kept apart
from the language a COMPANY's documents are produced in (D-75, D-163). app.py
puts it in st.session_state["ui_language"] after login.

Catalogues: i18n/<lang>.json, {"English text": "translation"}. Reloaded when
the file changes, so a corrected translation shows without a restart.

Format placeholders ({n}, {name}) must survive translation unchanged;
test_i18n.py checks every entry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DIR = Path(__file__).resolve().parent / "i18n"
LANGUAGES = ("en", "fr", "nl")    # interface languages with a catalogue
_cache: dict[str, tuple[float, dict[str, str]]] = {}


def catalogue(lang: str) -> dict[str, str]:
    path = DIR / f"{lang}.json"
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    cached = _cache.get(lang)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # a broken catalogue must not take the app down
        print(f"i18n: could not read {path.name}: {e}")
        data = {}
    _cache[lang] = (mtime, data)
    return data


def current_language() -> str:
    try:
        import streamlit as st
        lang = st.session_state.get("ui_language") or "en"
    except Exception:
        lang = "en"
    return lang if lang in LANGUAGES else "en"


def translate(text: str, lang: str | None = None) -> str:
    lang = lang or current_language()
    if lang == "en" or not text:
        return text
    return catalogue(lang).get(text) or text


tr = translate
_ = translate   # outside pages only: pages reuse "_" as a throwaway name


# ── The language we write to someone in (D-167) ──────────────────────────
LANGUAGE_NAMES = {"en": "English", "fr": "Français", "nl": "Nederlands", "de": "Deutsch"}


def person_language(profile: dict | None) -> str:
    """A person's language: their interface, and what we write to them in."""
    return ((profile or {}).get("ui_language") or "en")


def account_language(account: dict | None, owner_profile: dict | None) -> tuple[str, bool]:
    """(language, set_on_the_account). An account without its own language
    is written to in its owner's."""
    own = (account or {}).get("language")
    return (own, True) if own else (person_language(owner_profile), False)
