#!/usr/bin/env bash
# Roda na VPS da GESTÃO. Gera o pacote de CÓDIGO para a VPS nova a partir de uma tag do git (sem .env, sem segredos,
# sem backups, sem dados: só o que está versionado).
#   bash deploy/no/empacotar.sh [TAG]      # padrão: a tag mais recente
set -euo pipefail
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
cd "$PROJ"
TAG=${1:-$(git describe --tags --abbrev=0)}
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null || { echo "Tag $TAG não existe."; exit 1; }
mkdir -p "$PROJ/pacotes"
ARQ="$PROJ/pacotes/portal-codigo-$TAG.tar.gz"
git archive --format=tar.gz --prefix=portal_web/ -o "$ARQ" "$TAG"
echo "Pacote de código: $ARQ ($(du -h "$ARQ" | cut -f1)) · tag $TAG"
echo "SHA-256: $(sha256sum "$ARQ" | cut -d' ' -f1)"
echo "Na VPS nova:  scp $ARQ root@IP_DO_NO:/root/  e depois:"
echo "  mkdir -p /opt && tar -xzf /root/$(basename "$ARQ") -C /opt && cd /opt/portal_web && bash deploy/no/instalar.sh"
