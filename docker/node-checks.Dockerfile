# Digest verified against Docker Hub on 2026-09-08.
FROM node:22.14-alpine@sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944

WORKDIR /workspace
COPY package.json package-lock.json ./
RUN npm ci

COPY schemas/tooling/package.json schemas/tooling/package-lock.json ./schemas/tooling/
RUN npm --prefix schemas/tooling ci

USER node
