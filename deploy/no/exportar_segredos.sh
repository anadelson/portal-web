#!/usr/bin/env bash
# Roda na VPS da GESTÃO (a atual). Gera o pacote de segredos que o instalador do nó precisa: o .env daqui (com as chaves que
# têm de ser IGUAIS no nó: SECRET_KEY, TOTP_CHAVE, CPF_HMAC_CHAVE, CHAVE_CREDENCIAIS...) e a pasta segredos/ (certificado do Diário).
# Nada é exibido. O arquivo fica com permissão 600; copie para a VPS nova (scp) e APAGUE nas duas pontas depois da instalação.
#   bash deploy/no/exportar_segredos.sh
set -euo pipefail
umask 077
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
[ "$(id -u)" = 0 ] || { echo "Rode como root."; exit 1; }
[ -f "$PROJ/.env" ] || { echo "Sem .env em $PROJ."; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
install -m 600 "$PROJ/.env" "$T/env-origem"
[ -d "$PROJ/segredos" ] && cp -a "$PROJ/segredos" "$T/segredos"
ARQ="/root/segredos-no-$(date +%Y%m%d-%H%M).tar.gz"
tar -czf "$ARQ" -C "$T" .
chmod 600 "$ARQ"
echo "Pacote de segredos: $ARQ (permissão 600; conteúdo não exibido)"
echo "SHA-256: $(sha256sum "$ARQ" | cut -d' ' -f1)  (confira na VPS nova com: sha256sum $(basename "$ARQ"))"
echo "Copie para a VPS nova:  scp $ARQ root@IP_DO_NO:/root/"
echo "Depois da instalação, apague nas duas VPS:  rm $ARQ"
