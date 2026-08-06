"""
TEMPORARY — reports installed package versions so requirements.txt can be
pinned from a deploy that is known to work. Delete once pinned.

Reads the live interpreter rather than the installer's output: Streamlit
Cloud pre-installs Streamlit before touching requirements.txt, so what was
resolved and what is running are not guaranteed to agree.
"""

import sys
import streamlit as st
from importlib.metadata import version, PackageNotFoundError

PKGS = [
    "streamlit", "starlette", "supabase", "qdrant-client", "pypdf",
    "python-docx", "reportlab", "beautifulsoup4", "numpy",
    "requests", "python-dotenv",
]

st.markdown("## Installed versions")
st.caption(f"Python {sys.version.split()[0]}")

lines = []
for p in PKGS:
    try:
        lines.append(f"{p}=={version(p)}")
    except PackageNotFoundError:
        lines.append(f"# {p} NOT INSTALLED")

st.code("\n".join(lines), language="text")
st.caption("Copy into requirements.txt, then delete this page and its "
           "st.Page entry in admin_app.py.")
