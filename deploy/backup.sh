#!/usr/bin/env bash
# Backup diário: um arquivo por banco do servidor PostgreSQL do projeto. Guarda 14 dias.
#   VPS da gestão/tudo: plataforma + um banco por órgão.  Nó (PAPEL=no): banco local do nó + um banco por órgão hospedado.
# Agendar no crontab da VPS:  0 2 * * * /opt/portal_web/deploy/backup.sh >> /opt/portal_web/backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
DEST=./backups; mkdir -p "$DEST"; DATA=$(date +%F)
# todos os bancos do servidor do projeto (o nó não tem o banco de controle; a lista não depende dele)
BANCOS=$(docker compose exec -T db psql -U "$PG_USER" -d postgres -Atc "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
[ -n "$BANCOS" ] || { echo "$(date -Is) ERRO: nenhum banco encontrado"; exit 1; }
for b in $BANCOS; do
  docker compose exec -T db pg_dump -U "$PG_USER" -Fc "$b" > "$DEST/$b-$DATA.dump"
  echo "$(date -Is) ok $b"
done
tar -czf "$DEST/dados-$DATA.tgz" -C /var/lib/docker/volumes/portal_web_dados _data
# .env (inclui CHAVE_CREDENCIAIS: sem ela as credenciais cifradas no banco não podem ser lidas). Só root lê (600).
install -m 600 .env "$DEST/env-$DATA"
find "$DEST" -name 'env-*' -mtime +14 -delete
find "$DEST" -name '*.dump' -mtime +14 -delete
find "$DEST" -name 'dados-*.tgz' -mtime +14 -delete
