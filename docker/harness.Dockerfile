# Digest verified against Docker Hub on 2026-09-08.
FROM node:22.14-alpine@sha256:9bef0ef1e268f60627da9ba7d7605e8831d5b56ad07487d24d1aa386336d1944

WORKDIR /opt/tooling
COPY schemas/tooling/package.json schemas/tooling/package-lock.json ./
RUN npm ci

COPY docker/harness-entrypoint.sh /usr/local/bin/harness-entrypoint
RUN chmod 755 /usr/local/bin/harness-entrypoint \
    && mkdir -p /workspace/node_modules

WORKDIR /workspace
USER node
ENTRYPOINT ["harness-entrypoint"]
CMD ["npm", "--prefix", "schemas/tooling", "run", "conformance", "--", "--consumer", "issue-10"]
