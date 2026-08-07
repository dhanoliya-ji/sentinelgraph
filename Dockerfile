# SentinelGraph API.
#
# Builds the FastAPI backend only -- the React frontend is a static bundle and
# is deployed separately to Vercel (see README). Dependencies are installed in
# their own layer so a code change does not re-download the driver.

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY seed/ ./seed/

# Run as an unprivileged user.
RUN useradd --create-home --shell /usr/sbin/nologin sentinel \
    && chown -R sentinel:sentinel /app
USER sentinel

EXPOSE 8000

# Render (and most PaaS hosts) inject $PORT at runtime; default to 8000 locally.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
