FROM ghcr.io/astral-sh/uv:0.11.14@sha256:1025398289b62de8269e70c45b91ffa37c373f38118d7da036fb8bb8efc85d97 AS uv-bin

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ARG SOURCE_DATE_EPOCH=315532800
COPY --from=uv-bin /uv /usr/local/bin/uv
ENV SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY THIRD_PARTY_NOTICES.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ARG VCS_REF=unknown
ARG SOURCE_DATE_EPOCH=315532800
LABEL org.opencontainers.image.title="GLIO-PROTEOGEN API" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.source="https://github.com/AURORA-NEURO/glio-proteogen"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/glio-proteogen/bin:$PATH \
    SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH} \
    GLIO_PROTEOGEN_DATABASE_PATH=/data/glio-proteogen/events.sqlite3 \
    GLIO_PROTEOGEN_HOST=0.0.0.0 \
    GLIO_PROTEOGEN_PORT=8000
RUN groupadd --system --gid 10001 glio \
    && useradd --system --uid 10001 --gid glio --home-dir /nonexistent --shell /usr/sbin/nologin glio \
    && mkdir -p /data/glio-proteogen \
    && chown glio:glio /data/glio-proteogen
COPY --from=builder /build/.venv /opt/glio-proteogen
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0555 /usr/local/bin/docker-entrypoint.sh
USER glio
WORKDIR /app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('GLIO_PROTEOGEN_PORT', '8000') + '/readyz', timeout=3)"
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
