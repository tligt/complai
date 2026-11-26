"""
deploy/streamlit_head.py — RECOSA's title and link-preview tags in Streamlit's
own static index.html (D-219, 26 Nov 2026). Run once at image build.

Why: a link to check.recosa.eu showed on LinkedIn as "Streamlit". Link
previews read the raw HTML, which is Streamlit's index.html with
<title>Streamlit</title> and no Open Graph tags; st.set_page_config sets the
title later, in JavaScript, which preview crawlers do not run.

All three apps share this image, so all three get the same tags. They are
written for the free check (check.recosa.eu), the only one linked publicly;
each app still sets its own tab title through st.set_page_config. No og:url
for the same reason, and no og:image until there is a logo file to serve.

Idempotent: running it twice changes nothing.
"""

import html
import os

import streamlit

TITLE = "RECOSA — Free compliance check"
DESCRIPTION = ("See which GDPR, NIS2 and EU AI Act requirements may apply to your "
               "business, and where to start. About two minutes, no sign-up.")

path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
s = open(path, encoding="utf-8").read()

if 'property="og:title"' not in s:
    t, d = html.escape(TITLE), html.escape(DESCRIPTION)
    s = s.replace("<title>Streamlit</title>", "<title>RECOSA</title>")
    tags = (
        f'<meta name="description" content="{d}" />\n'
        '<meta property="og:type" content="website" />\n'
        '<meta property="og:site_name" content="RECOSA" />\n'
        f'<meta property="og:title" content="{t}" />\n'
        f'<meta property="og:description" content="{d}" />\n'
        '<meta name="twitter:card" content="summary" />\n'
        f'<meta name="twitter:title" content="{t}" />\n'
        f'<meta name="twitter:description" content="{d}" />\n'
    )
    s = s.replace("</head>", tags + "</head>", 1)
    open(path, "w", encoding="utf-8").write(s)

assert "<title>Streamlit</title>" not in s, "Streamlit's title was not replaced"
print("index.html: RECOSA title and preview tags in place")
