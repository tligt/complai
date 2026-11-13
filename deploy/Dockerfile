# RECOSA application image (S50) — one image for the client app, the admin
# back-office, the public free check and the scheduled jobs. Which one runs is
# chosen by the command in docker-compose.yml.
#
# Python 3.12: the version the pinned requirements were verified on locally
# (numpy==2.5.1 needs >= 3.12). Streamlit Cloud ran 3.14; nothing in the code
# depends on that.
#
# LibreOffice is an image layer now rather than an apt call on every Streamlit
# Cloud reboot (D-67): packages.txt stops being a failure mode. The -nogui
# Writer package is enough for document_generator.convert_docx_to_pdf/_odt,
# which call `soffice --headless`. fonts-liberation is metric-compatible with
# Arial, the font the generated .docx files use, so PDFs keep their layout.

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Brussels \
    HOME=/home/recosa

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui \
        fonts-liberation \
        fonts-dejavu-core \
        tzdata \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Not root: Streamlit and soffice need a writable home, nothing else.
RUN useradd --create-home --uid 10001 recosa
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# D-175, 13 Nov: Umami Cloud, same property as recosa.eu — into Streamlit's
# own static index.html, since st.html() strips a <script> tag (confirmed
# live: the element never reaches the DOM). All three apps share this one
# image, so all three would load it; data-domains is Umami's own hostname
# allowlist, and admin.recosa.eu is deliberately left off it — the script
# loads there too but self-disables, rather than needing a second image.
# app.recosa.eu this way covers the authenticated product, not just the
# login page, which is a wider scope than "prospects only" — flagged to
# the user, not a tested or final decision to track that too.
RUN python3 -c "import streamlit, os; p = os.path.join(os.path.dirname(streamlit.__file__), 'static', 'index.html'); s = open(p, encoding='utf-8').read(); tag = '<script defer src=\"https://cloud.umami.is/script.js\" data-website-id=\"de0d5db7-3b2c-4dae-b5e5-9522a7dbfde5\" data-domains=\"recosa.eu,www.recosa.eu,app.recosa.eu,check.recosa.eu\"></script>\n'; open(p, 'w', encoding='utf-8').write(s.replace('</head>', tag + '</head>')) if '</head>' in s and 'umami' not in s else None"

COPY --chown=recosa:recosa . .
USER recosa

# Streamlit settings that Streamlit Cloud used to set for us.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501"]
