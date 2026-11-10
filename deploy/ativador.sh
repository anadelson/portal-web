#!/bin/bash
# Ativador dos Portais (etapa 2 do modelo multi-órgão, 10/11/2026). Roda como root a cada minuto (portal-ativador.timer).
# Lê a fila de pedidos do console (tabela `ativacoes`) e, com uma lista FECHADA de ações:
#   ativar:    revalida → certificado (certbot webroot) → gera portal-orgaos.conf → nginx -t → reload → confere HTTPS
#   desativar: gera portal-orgaos.conf sem o domínio → nginx -t → reload (o certificado fica guardado)
# Também recarrega o nginx quando algum certificado foi renovado pelo certbot (correção para todos os sites da VPS).
# Nunca edita outros arquivos do nginx, nunca apaga certificados, nunca aceita domínio que já esteja em outro site da VPS.
#
# Uso:  ativador.sh                 # processa a fila (é o que o timer roda)
#       ativador.sh --teste DOMINIO # ensaio de ponta a ponta com um domínio de teste (sem órgão): publica, confere e retira
#       DRY_RUN=1 ativador.sh --teste DOMINIO   # só pede o certificado em modo de ensaio do Let's Encrypt (não publica)
set -uo pipefail

PROJ=${PROJ:-/opt/portal_web}
CONF_DIR=${CONF_DIR:-/opt/hotspot/nginx/conf.d}
CERTS_DIR=${CERTS_DIR:-/var/lib/docker/volumes/hotspot_nginx-certs/_data}
ESTADO=${ESTADO:-/var/lib/portal-ativador}
LOG=${LOG:-$PROJ/logs/ativador.log}
NGINX_C=${NGINX_C:-nginx}
CERTBOT_C=${CERTBOT_C:-certbot}
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
GERADO="$CONF_DIR/portal-orgaos.conf"
INC_DESTINO="$CONF_DIR/portal-comum.inc"
INC_ORIGEM="$PROJ/deploy/nginx/portal-comum.inc"

mkdir -p "$ESTADO" "$(dirname "$LOG")"
exec 9>"$ESTADO/trava"
flock -n 9 || exit 0

log() { echo "$(date -Is) $*" >> "$LOG"; }
app() { if [ -n "${APP_CMD:-}" ]; then $APP_CMD "$@"; else (cd "$PROJ" && $DOCKER compose exec -T app python -m app.ativacao "$@"); fi; }
dominio_ok() { [[ ${#1} -le 253 && "$1" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$ ]]; }

# domínio já atendido por outro arquivo do nginx (hotspot e outros sistemas, ou o piloto)?
em_outro_site() {
  local f
  for f in "$CONF_DIR"/*.conf; do
    [ "$f" = "$GERADO" ] && continue
    grep -E '^\s*server_name\s' "$f" | tr -s ' ;\t' '\n' | grep -qxF "$1" && return 0
  done
  return 1
}

nginx_testa_e_recarrega() {
  $DOCKER exec "$NGINX_C" nginx -t >>"$LOG" 2>&1 || return 1
  $DOCKER exec "$NGINX_C" nginx -s reload >>"$LOG" 2>&1
}

# grava o portal-orgaos.conf novo (saída de "app vhost ...") de forma atômica; se o nginx -t recusar, volta o anterior
publicar() {
  local tmp="$CONF_DIR/.portal-orgaos.conf.novo" bak="$ESTADO/portal-orgaos.conf.anterior"
  [ -f "$INC_DESTINO" ] || install -m 0644 "$INC_ORIGEM" "$INC_DESTINO" || return 1
  app vhost "$@" > "$tmp" || { rm -f "$tmp"; return 1; }
  grep -q '^# GERADO pelo ativador' "$tmp" || { rm -f "$tmp"; log "vhost gerado sem cabeçalho: recusado"; return 1; }
  if [ -f "$GERADO" ]; then cp -p "$GERADO" "$bak"; else rm -f "$bak"; fi
  chmod 0644 "$tmp" && mv -f "$tmp" "$GERADO"
  if ! nginx_testa_e_recarrega; then
    if [ -f "$bak" ]; then mv -f "$bak" "$GERADO"; else rm -f "$GERADO"; fi
    nginx_testa_e_recarrega || log "ATENÇÃO: nginx -t falhou também com a configuração anterior"
    return 1
  fi
}

certificado() {
  local d="$1" extra=()
  [ "${DRY_RUN:-}" = 1 ] && extra+=(--dry-run)
  $DOCKER exec "$CERTBOT_C" certbot certonly --webroot -w /var/www/certbot -d "$d" --cert-name "$d" \
      --non-interactive --agree-tos --keep-until-expiring "${extra[@]}" >>"$LOG" 2>&1 || return 1
  [ "${DRY_RUN:-}" = 1 ] || [ -s "$CERTS_DIR/live/$d/fullchain.pem" ]
}

no_ar() {  # HTTPS responde pelo nginx local com certificado válido para o domínio (o curl confere a cadeia e o nome).
  # A recarga do nginx é gradual (processos antigos terminam o que atendem): tenta algumas vezes antes de dar como falha.
  local cod i
  for ((i = 1; i <= ${TENTATIVAS:-5}; i++)); do
    if cod=$($CURL -sS -o /dev/null -w '%{http_code}' --max-time 20 --resolve "$1:443:127.0.0.1" "https://$1/" 2>>"$LOG") && [[ "$cod" =~ ^[234][0-9][0-9]$ ]]; then
      return 0
    fi
    log "conferência do HTTPS de $1: tentativa $i sem sucesso"
    [ "$i" -lt "${TENTATIVAS:-5}" ] && sleep "${ESPERA:-2}"
  done
  return 1
}

ativar() {
  local id="$1" d="$2" erro
  erro=$(app validar "$id") || { app concluir "$id" erro "Recusado: $erro"; log "pedido $id ($d) recusado: $erro"; return; }
  dominio_ok "$d" || { app concluir "$id" erro "Domínio em formato inválido."; return; }
  if em_outro_site "$d"; then app concluir "$id" erro "Este domínio já é atendido por outro site da VPS; nada foi alterado."; return; fi
  app passo "$id" "Pedindo o certificado ao Let's Encrypt"
  certificado "$d" || { app concluir "$id" erro "O Let's Encrypt não emitiu o certificado (confira se o DNS aponta para a VPS e se a porta 80 responde). Nada foi publicado."; return; }
  app passo "$id" "Certificado emitido; gerando a configuração do nginx"
  publicar --incluir "$id" || { app concluir "$id" erro "O nginx recusou a configuração nova (nginx -t); a anterior foi mantida."; return; }
  app passo "$id" "nginx recarregado; conferindo o HTTPS"
  if no_ar "$d"; then
    app concluir "$id" no_ar "No ar em https://$d (certificado válido)."; log "pedido $id: $d no ar"
  else
    publicar --excluir "$id"
    app concluir "$id" erro "O nginx foi recarregado, mas https://$d não respondeu; o domínio foi retirado de novo."
  fi
}

desativar() {
  local id="$1" d="$2"
  app passo "$id" "Retirando o domínio do nginx"
  if publicar --excluir "$id"; then app concluir "$id" desativado "Retirado do ar (certificado guardado)."; log "pedido $id: $d retirado"
  else app concluir "$id" erro "O nginx recusou a configuração; nada mudou."; fi
}

# recarrega o nginx se algum certificado foi renovado desde a última verificação (no máximo uma vez por execução)
renovacao() {
  local marca="$ESTADO/ultima-renovacao"
  [ -f "$marca" ] || { touch "$marca"; return; }
  if find "$CERTS_DIR/archive" -name '*.pem' -newer "$marca" 2>/dev/null | grep -q .; then
    touch "$marca"
    if nginx_testa_e_recarrega; then log "certificado renovado: nginx recarregado"; else log "certificado renovado, mas nginx -t falhou: NÃO recarregado"; fi
  fi
}

teste() {
  local d="$1"
  dominio_ok "$d" || { echo "domínio de teste inválido"; return 2; }
  if em_outro_site "$d"; then echo "domínio já está em outro site da VPS"; return 2; fi
  echo "1/4 certificado$([ "${DRY_RUN:-}" = 1 ] && echo ' (ensaio, --dry-run)')"; certificado "$d" || { echo "FALHOU: certificado (veja $LOG)"; return 1; }
  [ "${DRY_RUN:-}" = 1 ] && { echo "ensaio do certificado ok (nada publicado)"; return 0; }
  echo "2/4 publicar no nginx"; publicar --teste "$d" || { echo "FALHOU: nginx -t recusou; configuração anterior mantida"; return 1; }
  echo "3/4 conferir HTTPS"; if no_ar "$d"; then echo "   https://$d responde com certificado válido"; ok=1; else echo "   FALHOU: https://$d não respondeu"; ok=0; fi
  echo "4/4 retirar o domínio de teste"; publicar || echo "ATENÇÃO: não consegui retirar o domínio de teste (veja $LOG)"
  [ "$ok" = 1 ]
}

if [ "${1:-}" = "--teste" ]; then teste "${2:-}"; exit $?; fi
renovacao
app pendentes | while IFS=$'\t' read -r id acao dom; do
  [[ "$id" =~ ^[0-9]+$ ]] || continue
  log "pedido $id: $acao $dom"
  case "$acao" in ativar) ativar "$id" "$dom" ;; desativar) desativar "$id" "$dom" ;; esac
done
