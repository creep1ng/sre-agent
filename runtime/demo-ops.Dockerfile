# Evidence-only operator: candidate Python/locked dependencies plus Docker CLI.
# The CLI image is version-tagged tooling, not a claimed immutable audit digest.
ARG CHECKS_IMAGE=audit-runtime370-checks
FROM docker:27.5.1-cli AS docker-cli
FROM ${CHECKS_IMAGE}
USER 0
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
ENTRYPOINT []
CMD ["python", "/evidence/demo-audit.py", "verify"]
