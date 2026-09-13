FROM node:24.14.0-alpine3.23@sha256:7fddd9ddeae8196abf4a3ef2de34e11f7b1a722119f91f28ddf1e99dcafdf114 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.14.0-alpine3.23@sha256:7fddd9ddeae8196abf4a3ef2de34e11f7b1a722119f91f28ddf1e99dcafdf114 AS build
WORKDIR /app
ARG GLIO_API_URL=http://glio-proteogen:8000
ENV GLIO_API_URL=${GLIO_API_URL} \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24.14.0-alpine3.23@sha256:7fddd9ddeae8196abf4a3ef2de34e11f7b1a722119f91f28ddf1e99dcafdf114 AS runtime
WORKDIR /app
ENV HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    PORT=3000
RUN addgroup -S glio \
    && adduser -S -G glio glio \
    && mkdir -p /data/glio-auth \
    && chown glio:glio /data/glio-auth
COPY --from=build --chown=glio:glio /app/.next/standalone ./
COPY --from=build --chown=glio:glio /app/.next/static ./.next/static
USER glio
EXPOSE 3000
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:3000/healthz || exit 1
CMD ["node", "server.js"]
