FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html palette.css /usr/share/nginx/html/
COPY public /usr/share/nginx/html/public
COPY scripts/showcase.js /usr/share/nginx/html/scripts/showcase.js
COPY styles /usr/share/nginx/html/styles

EXPOSE 80
