"""
app_pages/glossary.py — usability audit batch 3: the terms RECOSA uses, in
plain language. Content in guide.GLOSSARY.
"""

import streamlit as st

from guide import GLOSSARY

st.title("Glossary")
st.caption("The terms used across RECOSA, in plain words. The legal reference "
           "is there if you want the exact text.")

q = st.text_input("Search", placeholder="e.g. DPIA, processor, RTO")
for term, meaning, ref in GLOSSARY:
    if q and q.lower() not in f"{term} {meaning}".lower():
        continue
    st.markdown(f"**{term}**  \n{meaning}" + (f"  \n:gray[{ref}]" if ref else ""))
