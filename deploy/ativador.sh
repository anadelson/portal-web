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
#
# Dois modos de proxy (PROXY_MODO, gravado pelo instalador no drop-in do systemd):
#   nginx (padrão; também "proprio" e "existente"): certbot webroot + portal-orgaos.conf + nginx -t/reload, como acima.
#   traefik (VPS em que o Traefik — ex.: do Dokploy — ocupa 80/443): grava portal-orgaos.yml na pasta de rotas dinâmicas
#     do Traefik (CONF_DIR). O Traefik lê o arquivo sozinho e emite/renova o certificado pelo resolvedor dele; não há
#     certbot nem reload. Só esse arquivo é do portal: os de outros sistemas nunca são tocados.
set -uo pipefail

PROJ=${PROJ:-/opt/portal_web}
# Instância (mais de um nó na mesma VPS, 18/11/2026): vazio = a de sempre. Com instância "camara": arquivo de rotas
# portal-orgaos-camara.conf/.yml, trecho portal-comum-camara.inc (aponta para portal-web-app-camara) e estado próprio.
INSTANCIA=${INSTANCIA:-}
[[ -z "$INSTANCIA" || "$INSTANCIA" =~ ^[a-z0-9]{1,20}$ ]] || { echo "INSTANCIA inválida: $INSTANCIA"; exit 1; }
SUF=${INSTANCIA:+-$INSTANCIA}
APP_ALIAS=portal-web-app$SUF
CONF_DIR=${CONF_DIR:-/opt/hotspot/nginx/conf.d}
CERTS_DIR=${CERTS_DIR:-/var/lib/docker/volumes/hotspot_nginx-certs/_data}
ESTADO=${ESTADO:-/var/lib/portal-ativador$SUF}
LOG=${LOG:-$PROJ/logs/ativador.log}
NGINX_C=${NGINX_C:-nginx}
CERTBOT_C=${CERTBOT_C:-certbot}
DOCKER=${DOCKER:-docker}
CURL=${CURL:-curl}
PROXY_MODO=${PROXY_MODO:-existente}
TRAEFIK=0; [ "$PROXY_MODO" = traefik ] && TRAEFIK=1
TRAEFIK_ENTRADA_HTTP=${TRAEFIK_ENTRADA_HTTP:-web}
TRAEFIK_ENTRADA_HTTPS=${TRAEFIK_ENTRADA_HTTPS:-websecure}
TRAEFIK_RESOLVEDOR=${TRAEFIK_RESOLVEDOR:-letsencrypt}
if [ "$TRAEFIK" = 1 ]; then
  GERADO="$CONF_DIR/portal-orgaos$SUF.yml"; PROXY_NOME=Traefik
  # o Traefik só tira o certificado no primeiro acesso: espera até ~2 min antes de dar o HTTPS como falho
  TENTATIVAS=${TENTATIVAS:-24}; ESPERA=${ESPERA:-5}
else
  GERADO="$CONF_DIR/portal-orgaos$SUF.conf"; PROXY_NOME=nginx
fi
INC_DESTINO="$CONF_DIR/portal-comum$SUF.inc"
INC_ORIGEM="$PROJ/deploy/nginx/portal-comum.inc"

mkdir -p "$ESTADO" "$(dirname "$LOG")"
exec 9>"$ESTADO/trava"
flock -n 9 || exit 0

log() { echo "$(date -Is) $*" >> "$LOG"; }
app() { if [ -n "${APP_CMD:-}" ]; then $APP_CMD "$@"; else (cd "$PROJ" && $DOCKER compose exec -T app python -m app.ativacao "$@"); fi; }
dominio_ok() { [[ ${#1} -le 253 && "$1" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$ ]]; }

# domínio já atendido por outro site da VPS (hotspot e outros sistemas, ou o piloto)?
em_outro_site() {
  local f
  if [ "$TRAEFIK" = 1 ]; then
    # outras rotas do Traefik: arquivos da pasta dinâmica e rótulos de containers/serviços (regras Host(`dominio`))
    for f in "$CONF_DIR"/*; do
      [ -f "$f" ] && [ "$f" != "$GERADO" ] || continue
      grep -qF "\`$1\`" "$f" && return 0
    done
    { $DOCKER ps -q 2>/dev/null | xargs -r $DOCKER inspect -f '{{range $k, $v := .Config.Labels}}{{$v}}{{"\n"}}{{end}}' 2>/dev/null
      $DOCKER service ls -q 2>/dev/null | xargs -r $DOCKER service inspect -f '{{range $k, $v := .Spec.Labels}}{{$v}}{{"\n"}}{{end}}' 2>/dev/null
    } | grep -qF "\`$1\`" && return 0
    return 1
  fi
  for f in "$CONF_DIR"/*.conf; do
    [ "$f" = "$GERADO" ] && continue
    grep -E '^\s*server_name\s' "$f" | tr -s ' ;\t' '\n' | grep -qxF "$1" && return 0
  done
  return 1
}

nginx_testa_e_recarrega() {
  [ "$TRAEFIK" = 1 ] && return 0   # Traefik: o arquivo é JSON gerado e conferido pelo app; ele recarrega sozinho
  $DOCKER exec "$NGINX_C" nginx -t >>"$LOG" 2>&1 || return 1
  $DOCKER exec "$NGINX_C" nginx -s reload >>"$LOG" 2>&1
}

gerar() {  # conteúdo novo do arquivo do proxy (saída do app)
  if [ "$TRAEFIK" = 1 ]; then
    app vhost --formato traefik --entrada-http "$TRAEFIK_ENTRADA_HTTP" --entrada-https "$TRAEFIK_ENTRADA_HTTPS" --resolvedor "$TRAEFIK_RESOLVEDOR" "$@"
  else
    app vhost "$@"
  fi
}

# grava o portal-orgaos.conf novo (saída de "app vhost ...") de forma atômica; se o nginx -t recusar, volta o anterior
publicar() {
  local tmp="$ESTADO/portal-orgaos.novo" bak="$ESTADO/portal-orgaos.anterior"
  # (o temporário fica fora da pasta do proxy: o Traefik leria qualquer arquivo novo que aparecesse lá)
  [ "$TRAEFIK" = 1 ] || [ -f "$INC_DESTINO" ] || { sed "s/portal-web-app:8000/$APP_ALIAS:8000/" "$INC_ORIGEM" > "$INC_DESTINO" && chmod 0644 "$INC_DESTINO"; } || return 1
  gerar "$@" > "$tmp" || { rm -f "$tmp"; return 1; }
  grep -q '^# GERADO pelo ativador' "$tmp" || { rm -f "$tmp"; log "vhost gerado sem cabeçalho: recusado"; return 1; }
  if [ -f "$GERADO" ]; then cp -p "$GERADO" "$bak"; else rm -f "$bak"; fi
  chmod 0644 "$tmp" && cp -f "$tmp" "$CONF_DIR/.portal-orgaos$SUF.tmp" && mv -f "$CONF_DIR/.portal-orgaos$SUF.tmp" "$GERADO" && rm -f "$tmp"
  if ! nginx_testa_e_recarrega; then
    if [ -f "$bak" ]; then mv -f "$bak" "$GERADO"; else rm -f "$GERADO"; fi
    nginx_testa_e_recarrega || log "ATENÇÃO: nginx -t falhou também com a configuração anterior"
    return 1
  fi
}

certificado() {
  [ "$TRAEFIK" = 1 ] && return 0   # o Traefik emite o certificado sozinho quando a rota entra
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
    # confere em /admin/login: responde mesmo com o portal oculto (que dá 503 em /)
    if cod=$($CURL -sS -o /dev/null -w '%{http_code}' --max-time 20 --resolve "$1:443:127.0.0.1" "https://$1/admin/login" 2>>"$LOG") && [[ "$cod" =~ ^[234][0-9][0-9]$ ]]; then
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
  if [ "$TRAEFIK" = 0 ]; then
    app passo "$id" "Pedindo o certificado ao Let's Encrypt"
    certificado "$d" || { app concluir "$id" erro "O Let's Encrypt não emitiu o certificado (confira se o DNS aponta para a VPS e se a porta 80 responde). Nada foi publicado."; return; }
    app passo "$id" "Certificado emitido; gerando a configuração do nginx"
  else
    app passo "$id" "Gerando a rota no Traefik (ele pede o certificado ao Let's Encrypt)"
  fi
  publicar --incluir "$id" || { app concluir "$id" erro "O $PROXY_NOME recusou a configuração nova; a anterior foi mantida."; return; }
  app passo "$id" "$PROXY_NOME atualizado; conferindo o HTTPS"
  if no_ar "$d"; then
    app concluir "$id" no_ar "No ar em https://$d (certificado válido)."; log "pedido $id: $d no ar"
  else
    publicar --excluir "$id"
    app concluir "$id" erro "O $PROXY_NOME foi atualizado, mas https://$d não respondeu com certificado válido; o domínio foi retirado de novo."
  fi
}

desativar() {
  local id="$1" d="$2"
  app passo "$id" "Retirando o domínio do $PROXY_NOME"
  if publicar --excluir "$id"; then app concluir "$id" desativado "Retirado do ar (certificado guardado)."; log "pedido $id: $d retirado"
  else app concluir "$id" erro "O $PROXY_NOME recusou a configuração; nada mudou."; fi
}

# recarrega o nginx se algum certificado foi renovado desde a última verificação (no máximo uma vez por execução)
renovacao() {
  [ "$TRAEFIK" = 1 ] && return 0   # o Traefik renova e passa a usar o certificado novo sozinho
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
  [ "${DRY_RUN:-}" = 1 ] && { echo "ensaio do certificado ok (nada publicado)$([ "$TRAEFIK" = 1 ] && echo '; no Traefik o certificado só é pedido na publicação')"; return 0; }
  echo "2/4 publicar no $PROXY_NOME"; publicar --teste "$d" || { echo "FALHOU: o $PROXY_NOME recusou; configuração anterior mantida"; return 1; }
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

# ---------------------------------------------------------------------------------------------------------------------
# Tarefas pedidas pela GESTÃO (19/11/2026): mover órgão entre nós desta VPS e criar uma instância nova. Os passos e o
# resultado voltam à gestão pelo relatório do nó (enviado logo depois). Parâmetros conferidos de novo aqui.
# ---------------------------------------------------------------------------------------------------------------------
tarefa_app() { if [ -n "${TAREFAS_CMD:-}" ]; then $TAREFAS_CMD "$@"; else (cd "$PROJ" && $DOCKER compose exec -T app python -m app.tarefas "$@"); fi; }
campo() { python3 -c "import json,sys; print(json.loads(sys.argv[1]).get(sys.argv[2],''))" "$1" "$2" 2>/dev/null; }
PEND=$(tarefa_app pendentes 2>/dev/null || true)
while IFS=$'\t' read -r tid tipo params; do
  [[ "$tid" =~ ^[0-9]+$ ]] || continue
  log "tarefa $tid: $tipo"
  slug=$(campo "$params" slug); arq=$(campo "$params" arquivo)
  if [[ "$tipo" =~ ^(exportar|importar|limpar)$ ]] && ! { [[ "$slug" =~ ^[a-z0-9-]{2,40}$ ]] && [[ "$arq" =~ ^/var/lib/portal-transferencias/[a-z0-9-]{1,80}\.tgz$ ]]; }; then
    tarefa_app concluir "$tid" erro "parâmetros inválidos"; continue
  fi
  case "$tipo" in
    exportar) cmd=(bash "$PROJ/deploy/no/mover_orgao.sh" exportar "$slug" --saida "$arq") ;;
    importar) cmd=(bash "$PROJ/deploy/no/mover_orgao.sh" importar "$arq") ;;
    limpar) cmd=(bash "$PROJ/deploy/no/mover_orgao.sh" limpar "$arq" --auto) ;;
    instalar_instancia) cmd=(bash "$PROJ/deploy/no/criar_instancia.sh" "$tid") ;;
    *) tarefa_app concluir "$tid" erro "tipo de tarefa desconhecido"; continue ;;
  esac
  tarefa_app passo "$tid" "Começando no nó: $tipo"
  saida=$("${cmd[@]}" < /dev/null 2>&1); rc=$?
  limpa=$(printf '%s\n' "$saida" | sed 's/\x1b\[[0-9;]*m//g')
  while IFS= read -r l; do [ -n "$l" ] && tarefa_app passo "$tid" "$l"; done < <(printf '%s\n' "$limpa" | grep -E '✔|!' | sed -E 's/^ *(✔|!) *//')
  if [ "$rc" = 0 ]; then tarefa_app concluir "$tid" ok "$(printf '%s\n' "$limpa" | grep '✔' | tail -1 | sed -E 's/^ *✔ *//')"
  else tarefa_app concluir "$tid" erro "$(printf '%s\n' "$limpa" | grep '✘' | tail -1 | sed -E 's/^ *✘ *//')"; fi
  log "tarefa $tid: $tipo → código $rc"
done <<< "$PEND"
if [ -n "$PEND" ] && [ -z "${TAREFAS_CMD:-}" ]; then (cd "$PROJ" && $DOCKER compose exec -T app python -m app.relatorio enviar) >> "$LOG" 2>&1 || true; fi
