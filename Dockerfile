FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GLIO_PROTEOGEN_DATABASE_PATH=/data/glio-proteogen/events.sqlite3 \
    GLIO_PROTEOGEN_HOST=0.0.0.0 \
    GLIO_PROTEOGEN_PORT=8000
RUN groupadd --system glio && useradd --system --gid glio --home-dir /nonexistent --shell /usr/sbin/nologin glio
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0555 /usr/local/bin/docker-entrypoint.sh
RUN mkdir -p /data/glio-proteogen && chown -R glio:glio /data/glio-proteogen
USER glio
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD-SHELL python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('GLIO_PROTEOGEN_PORT', '8000') + '/readyz', timeout=3)"
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
