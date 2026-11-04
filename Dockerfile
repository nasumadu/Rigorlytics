# syntax=docker/dockerfile:1
#
# Rigorlytics application image.
#
# Two stages. The builder compiles wheels and is thrown away, so the
# runtime image carries no compilers, headers or package caches. That is
# both a size win and a vulnerability-surface win: Trivy findings against
# gcc and friends never reach the shipped image.
#
#   docker build -t rigorlytics:dev .
#   docker run --rm -p 8000:8000 --env-file .env rigorlytics:dev
#
# Python 3.12 is chosen deliberately over the 3.9 in the VM's venv. If a
# dependency fails to build, drop both stages to python:3.9-slim-bookworm
# rather than loosening anything below.

# ---------------------------------------------------------------- builder
FROM python:3.12-slim-bookworm AS builder

# Build-only dependencies. psycopg needs libpq headers to compile; if the
# project moves to psycopg[binary] these can go entirely.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      build-essential \
      libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

# Build wheels once so the runtime stage installs without a toolchain.
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ---------------------------------------------------------------- runtime
FROM python:3.12-slim-bookworm AS runtime

# Runtime library only, not the -dev headers.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      libpq5 \
      curl \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get clean

# Non-root from the start. A fixed uid/gid matters once Kubernetes
# securityContext pins runAsUser, and it keeps volume ownership stable.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# Application code last, so dependency layers stay cached across code edits.
COPY --chown=app:app . .

USER app

EXPOSE 8000

# Plain HTTP check against the app's own route. Kubernetes ignores this and
# uses its own probes, but it makes `docker ps` and Compose honest.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# --timeout 120 is not arbitrary. A question that misses the database and
# falls through to live ESPN lookups took 34s in testing, and gunicorn's
# default 30s worker timeout would kill it mid-request. Two workers with
# four threads each suits an I/O-bound app that spends its time waiting on
# Postgres and the Anthropic API.
CMD ["sh", "-c", "exec gunicorn run:app \
     --bind 0.0.0.0:${PORT} \
     --workers 2 \
     --threads 4 \
     --timeout 120 \
     --graceful-timeout 30 \
     --access-logfile - \
     --error-logfile - \
     --log-level info"]
