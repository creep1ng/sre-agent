# Digest verified against Docker Hub on 2026-09-08.
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10

ENV API_UPSTREAM=api:8000

COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html palette.css /usr/share/nginx/html/
COPY public /usr/share/nginx/html/public
COPY scripts/showcase.js /usr/share/nginx/html/scripts/showcase.js
COPY styles /usr/share/nginx/html/styles

EXPOSE 80
