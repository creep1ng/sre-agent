FROM node:22.14-alpine

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
