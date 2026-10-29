# The demo's second enrolled service (#721), built by compose.demo.yaml for one release:
# demo/checkout:1.4.0 runs, `demo_env.py fail --service sre-checkout` builds and deploys 1.5.0,
# and the deploy-executor rolls back to a tag the local image store holds.
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ARG CHECKOUT_VERSION
ENV CHECKOUT_VERSION=${CHECKOUT_VERSION} PYTHONUNBUFFERED=1
COPY checkout.py /checkout.py
HEALTHCHECK --interval=2s --timeout=2s --retries=10 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=1)"]
USER 65532:65532
EXPOSE 8080
CMD ["python", "/checkout.py"]
