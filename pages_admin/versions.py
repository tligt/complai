"""
pages_admin/versions.py — what runs here against what requirements.txt pins.

Reads, on every load, the requirements.txt deployed with this app and the
packages the running interpreter actually has (Streamlit Cloud pre-installs
Streamlit before it reads the file, so the two can differ). Any difference
is flagged. Also lists packages the code imports directly but gets only
through another package — those should be pinned too (9 Nov: cryptography
and Pillow were, and the August Starlette outage came from exactly such an
unpinned version moving).
"""

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import streamlit as st

# Imported directly by RECOSA's code. Keep in step with the imports.
DIRECT_IMPORTS = {
    "cryptography": "sessions.py (session encryption)",
    "pillow": "doc_theme.py, linkedin_post.py (logos, the LinkedIn card)",
}

st.title("Versions")
st.caption(f"Python {sys.version.split()[0]} · read live on every load")


def _installed(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


req = Path(__file__).resolve().parent.parent / "requirements.txt"
pins: dict[str, str] = {}
try:
    for line in req.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#;]+)", line)
        if m:
            pins[m.group(1).lower()] = m.group(2)
except OSError as e:
    st.error(f"Could not read requirements.txt: {e}")

rows, off = [], 0
for name, pinned in sorted(pins.items()):
    got = _installed(name)
    ok = got == pinned
    off += not ok
    rows.append({"Package": name, "Pinned": pinned, "Running": got or "not installed",
                 "": "✅" if ok else "⚠️"})
for name, why in DIRECT_IMPORTS.items():
    if name not in pins:
        off += 1
        rows.append({"Package": name, "Pinned": "— not pinned", "Running": _installed(name) or
                     "not installed", "": "⚠️"})

if off:
    st.warning(f"{off} package{'s' if off != 1 else ''} differ from requirements.txt or "
               "are not pinned. Pin the running version to keep a reboot from changing it.")
else:
    st.success("Everything running matches requirements.txt.")

st.dataframe(rows, hide_index=True, width="stretch",
             column_config={"": st.column_config.TextColumn(width=40)})
unpinned = [r for r in rows if r["Pinned"] == "— not pinned"]
if unpinned:
    st.caption("To pin what runs today, add to requirements.txt:")
    st.code("\n".join(f"{r['Package']}=={r['Running']}" for r in unpinned), language="text")
for name, why in DIRECT_IMPORTS.items():
    st.caption(f"`{name}` is imported by {why}.")
