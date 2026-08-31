FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS dependencies
WORKDIR /app
RUN apt-get update \
    && apt-get install --yes --no-install-recommends g++ make python3 \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci --omit=dev \
    && npm cache clean --force

FROM node:24.15.0-bookworm-slim@sha256:4e6b70dd6cbfc88c8157ba19aa3d9f9cce6ba4703576d55459e45efcbc9c5f5d AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    T3_CODE_BASE_DIR=/data/t3 \
    T3_CODE_PORT=3773 \
    T3_PAIRING_BROKER_PORT=3774 \
    T3_WORKSPACE_PATH=/workspace
RUN groupadd --system --gid 10001 t3 \
    && useradd --system --uid 10001 --gid t3 --home-dir /data/t3 --shell /bin/sh t3 \
    && mkdir -p /data/t3 /workspace \
    && chown -R t3:t3 /data/t3 /workspace
COPY --from=dependencies --chown=t3:t3 /app/node_modules ./node_modules
COPY --chown=t3:t3 server.mjs ./server.mjs
USER t3
EXPOSE 3773 3774
HEALTHCHECK --interval=20s --timeout=3s --start-period=20s --retries=5 CMD ["node", "-e", "fetch('http://127.0.0.1:3774/healthz').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"]
CMD ["node", "server.mjs"]
