#!/bin/sh
set -eu

container="${BROWSER_API_NGINX_CONTAINER:-sre-agent-browser-api-nginx}"
image="${BROWSER_API_NGINX_IMAGE:-sre-agent-browser-api-web}"

cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

cleanup
docker build --quiet --file docker/web.Dockerfile --tag "$image" . >/dev/null
docker run --rm \
  --name "$container" \
  --add-host host.docker.internal:host-gateway \
  --mount "type=bind,source=$(pwd)/tests/browser/fixtures,target=/usr/share/nginx/html/tests/browser/fixtures,readonly" \
  --publish 127.0.0.1:4173:80 \
  --env API_UPSTREAM=host.docker.internal:4174 \
  "$image" &
wait "$!"
