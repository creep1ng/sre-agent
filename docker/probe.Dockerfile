# E2E target of the deploy-executor (#720). compose.yaml builds it twice: demo/probe:1.1.0
# runs as the `probe` service and demo/probe:1.0.0 is the rollback target in the image store.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG PROBE_VERSION
ENV PROBE_VERSION=${PROBE_VERSION} PYTHONUNBUFFERED=1
COPY probe.py /probe.py
HEALTHCHECK --interval=2s --timeout=2s --retries=10 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/', timeout=1)"]
USER 65532:65532
EXPOSE 8080
CMD ["python", "/probe.py"]
