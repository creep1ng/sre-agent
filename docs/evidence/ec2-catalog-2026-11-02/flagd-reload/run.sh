#!/bin/sh
# The flagd reload probe of #724: run from the repository root (docker only). See ../README.md.
set -e
P=docs/evidence/ec2-catalog-2026-11-02/flagd-reload
FLAGD=ghcr.io/open-feature/flagd:v0.16.0@sha256:32234e63c1d0634883aabd31cbd46802934aaaef0153dfd653b5d1017940bb4e
PY=python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
W=$(mktemp -d) && mkdir -m 777 "$W/flagd"
docker run --rm --user "$(id -u):$(id -g)" -v "$W/flagd:/out" curlimages/curl:8.10.1 -fsSL -o /out/demo.flagd.json \
  https://raw.githubusercontent.com/open-telemetry/opentelemetry-demo/1755859a9de82c2e5e225be68abc401a5ebf2b4f/src/flagd/demo.flagd.json
chmod 666 "$W/flagd/demo.flagd.json"
docker network create flagd-reload >/dev/null
# Upstream's flagd service: its image, command and directory mount (compose.yaml at 1755859a).
docker run -d --name flagd --network flagd-reload -v "$W/flagd:/etc/flagd" "$FLAGD" start --uri file:./etc/flagd/demo.flagd.json >/dev/null
docker run --rm --network flagd-reload "$PY" python -c "import time,urllib.request as u
for _ in range(60):
    try: u.urlopen(u.Request('http://flagd:8016/ofrep/v1/evaluate/flags/paymentUnreachable',b'{}',{'Content-Type':'application/json'})); break
    except Exception: time.sleep(1)"
echo "--- writes"; docker run --rm --user "$(id -u):$(id -g)" --network flagd-reload -v "$W:/probe" -v "$PWD/$P:/p:ro" "$PY" python /p/probe.py
echo "flagd: $(docker inspect -f 'started {{.State.StartedAt}}, restarts {{.RestartCount}}' flagd)"
echo "--- an atomic replace while a stream is open"
docker run -d --name stream1 --network flagd-reload -v "$PWD/$P:/p:ro" "$PY" python /p/stream.py 10 >/dev/null
sleep 3
docker run --rm --user "$(id -u):$(id -g)" -v "$W:/probe" "$PY" python -c "import json,os
F='/probe/flagd/demo.flagd.json'; d=json.load(open(F)); d['flags']['paymentUnreachable']['defaultVariant']='on'
open(F[:-5]+'.tmp','w').write(json.dumps(d,indent=2)); os.replace(F[:-5]+'.tmp',F)"
docker wait stream1 >/dev/null; docker logs stream1; docker rm stream1 >/dev/null
echo "--- docker restart flagd while a stream is open"
docker run -d --name stream2 --network flagd-reload -v "$PWD/$P:/p:ro" "$PY" python /p/stream.py 10 >/dev/null
sleep 3; docker restart flagd >/dev/null
docker wait stream2 >/dev/null; docker logs stream2; docker rm stream2 >/dev/null
echo "--- flagd log"; docker logs flagd 2>&1 | grep -e "filepath event" -e "Starting filepath" | cut -c1-120
docker rm -f flagd >/dev/null; docker network rm flagd-reload >/dev/null; rm -rf "$W"
