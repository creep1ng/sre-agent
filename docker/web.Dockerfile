FROM nginx:1.27-alpine

ENV API_UPSTREAM=api:8000

COPY docker/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html palette.css /usr/share/nginx/html/
COPY public /usr/share/nginx/html/public
COPY scripts/showcase.js /usr/share/nginx/html/scripts/showcase.js
COPY styles /usr/share/nginx/html/styles

EXPOSE 80
