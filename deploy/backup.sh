#!/usr/bin/env bash
# Backup diário: um arquivo por banco (plataforma + um por órgão). Guarda 14 dias.
# Agendar no crontab da VPS:  0 2 * * * /opt/portal_web/deploy/backup.sh >> /opt/portal_web/backups/backup.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
DEST=./backups; mkdir -p "$DEST"; DATA=$(date +%F)
BANCOS=$(docker compose exec -T db psql -U "$PG_USER" -d plataforma -Atc "SELECT 'plataforma' UNION ALL SELECT banco FROM orgaos")
for b in $BANCOS; do
  docker compose exec -T db pg_dump -U "$PG_USER" -Fc "$b" > "$DEST/$b-$DATA.dump"
  echo "$(date -Is) ok $b"
done
tar -czf "$DEST/dados-$DATA.tgz" -C /var/lib/docker/volumes/portal_web_dados _data
find "$DEST" -name '*.dump' -mtime +14 -delete
find "$DEST" -name 'dados-*.tgz' -mtime +14 -delete
