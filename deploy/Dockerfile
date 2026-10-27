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

COPY --chown=recosa:recosa . .
USER recosa

# Streamlit settings that Streamlit Cloud used to set for us.
ENV STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port", "8501"]
