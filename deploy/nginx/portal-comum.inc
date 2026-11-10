# Trecho comum dos domínios publicados pelo console (incluído por portal-orgaos.conf, gerado pelo ativador).
# Extensão .inc: o nginx só carrega *.conf de conf.d, então este arquivo não é lido sozinho.
ssl_protocols TLSv1.2 TLSv1.3;

resolver 127.0.0.11 valid=10s ipv6=off;
client_max_body_size 25M;

gzip on;
gzip_types text/css application/javascript application/json image/svg+xml;

location / {
    set $portal_web_app portal-web-app:8000;
    proxy_pass http://$portal_web_app;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 15s;
    proxy_read_timeout 120s;
}

add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Strict-Transport-Security "max-age=31536000" always;
