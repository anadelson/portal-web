#!/usr/bin/env bash
# =====================================================================================================================
#  Desinstalar ESTE nó da VPS, a pedido da GESTÃO (Console → Nós e licenças → Excluir nó) — 19/11/2026.
#  Quem roda: o ativador deste nó (root), pela tarefa "desinstalar_no". Também pode ser rodado à mão:
#      bash deploy/no/desinstalar.sh --backup /var/backups/portal-removidos/AAAAMMDD-HHMM-no-NOME
#
#  1. Recusa se este nó ainda hospeda algum órgão (exclua ou mude os órgãos antes).
#  2. BACKUP FINAL, fora da pasta do nó: todos os bancos, os arquivos e a configuração (.env, só root lê). Confere cada
#     arquivo (SHA-256). Se o backup falhar, NADA é apagado.
#  3. Agenda a remoção para daqui a 90 segundos (o ativador ainda avisa a gestão antes de tudo sumir) e a remoção apaga
#     SÓ o que é deste nó: ativador e backup automático, a rota dele no proxy, containers, volumes, imagens e a pasta.
#     O proxy (nginx/Traefik) e os outros sistemas e nós da VPS não são tocados.
# =====================================================================================================================
set -uo pipefail
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
DOCKER=${DOCKER:-docker}; SYSTEMD_RUN=${SYSTEMD_RUN:-systemd-run}; ESPERA_REMOCAO=${ESPERA_REMOCAO:-90}
BK=""; [ "${1:-}" = "--backup" ] && BK=${2:-}
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
para() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
[[ "$BK" =~ ^/var/backups/portal-removidos/[a-z0-9-]{1,100}$ ]] || para "informe --backup /var/backups/portal-removidos/<nome>"
[ "$(id -u)" = 0 ] || [ -n "${TESTE_DESINSTALAR:-}" ] || para "rode como root"
cd "$PROJ"
envv() { grep -E "^$1=" "$PROJ/.env" 2>/dev/null | tail -1 | cut -d= -f2-; }
[ "$(envv PAPEL)" = no ] || para "esta pasta não é de um nó: nada foi alterado"
INST=$(envv INSTANCIA); SUF=${INST:+-$INST}; NOME=$(envv NO_NOME)
PROJETO=$(basename "$PROJ" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9_-')
ok "nó $NOME · pasta $PROJ${INST:+ (instância $INST)}"

# 1. sem órgãos
ORG=$($DOCKER compose exec -T app python -m app.mover_orgao orgaos 2>/dev/null) || para "não consegui consultar o app deste nó"
[ "$ORG" = "[]" ] || para "este nó ainda hospeda órgão(s) $ORG: exclua ou mude cada um antes (nada foi apagado)"
ok "nenhum órgão neste nó"

# 2. backup final, conferido
mkdir -p "$BK" && chmod 700 "$(dirname "$BK")" "$BK" || para "não consegui criar a pasta do backup $BK"
bash "$PROJ/deploy/backup.sh" >> "$BK/backup.log" 2>&1 || para "o backup final falhou (veja $BK/backup.log): nada foi apagado"
D=$(date +%F)
cp -p "$PROJ"/backups/*-"$D".dump "$PROJ/backups/dados-$D.tgz" "$BK/" 2>/dev/null || para "backup final incompleto: nada foi apagado"
cp -p "$PROJ/.env" "$BK/env" && chmod 600 "$BK"/* || para "não consegui guardar a configuração: nada foi apagado"
(cd "$BK" && sha256sum -- *.dump *.tgz env > sha256.txt && sha256sum -c --quiet sha256.txt) || para "o backup final não confere: nada foi apagado"
ok "backup final conferido em $BK ($(du -sh "$BK" | cut -f1))"

# 3. remoção (depois que o ativador avisar a gestão)
R=/var/lib/portal-remocao$SUF.sh
MODO=$(envv PROXY_MODO); CONF=$(envv CONF_DIR); NGX=$(envv NGINX_C)
{ echo '#!/bin/bash'; echo "# remoção do nó $NOME (gerada por deploy/no/desinstalar.sh em $(date -Is))"
  echo "exec >> '$BK/remocao.log' 2>&1; echo \"\$(date -Is) início\""
  echo "systemctl disable --now portal-ativador$SUF.timer; rm -f /etc/systemd/system/portal-ativador$SUF.service /etc/systemd/system/portal-ativador$SUF.timer"
  echo "rm -rf /etc/systemd/system/portal-ativador$SUF.service.d; systemctl daemon-reload; rm -f /etc/cron.d/portal-backup$SUF"
  if [ "$MODO" = traefik ]; then echo "rm -f '$CONF/portal-orgaos$SUF.yml'"
  elif [ -n "$CONF" ]; then
    echo "rm -f '$CONF/portal-orgaos$SUF.conf'"
    [ -n "$INST" ] && echo "rm -f '$CONF/portal-comum$SUF.inc'"   # o trecho sem sufixo pode servir a outro nó: fica
    [ -n "$NGX" ] && echo "docker exec '$NGX' nginx -t && docker exec '$NGX' nginx -s reload"
  fi
  echo "cd '$PROJ' && docker compose down -v; docker image rm '$PROJETO-app' '$PROJETO-worker'"
  echo "cd / && rm -rf '$PROJ' /var/lib/portal-ativador$SUF; rm -f /root/portal-codigo*${INST:+@$INST}*.tar.gz /root/segredos-no${INST:+@$INST}*.enc"
  echo "echo \"\$(date -Is) fim\"; rm -f '$R'"
} > "$R"; chmod 700 "$R"
$SYSTEMD_RUN --unit="portal-remocao$SUF" --on-active="$ESPERA_REMOCAO" /bin/bash "$R" >/dev/null 2>&1 || para "não consegui agendar a remoção (o backup está guardado em $BK; nada foi apagado)"
ok "remoção agendada para daqui a $ESPERA_REMOCAO segundos (registro em $BK/remocao.log)"
echo "RESULTADO $(cd "$BK" && python3 -c "import json,os,sys; print(json.dumps({'pasta': os.getcwd(), 'arquivos': [{'nome': l.split()[1], 'sha256': l.split()[0], 'bytes': os.path.getsize(l.split()[1])} for l in open('sha256.txt')]}))")"
