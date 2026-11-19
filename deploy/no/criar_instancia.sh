#!/usr/bin/env bash
# =====================================================================================================================
#  Cria um NÓ NOVO nesta mesma VPS (instância), a pedido da GESTÃO — 19/11/2026.
#  Quem roda: o ativador deste nó (root), quando chega a tarefa "instalar_instancia" do console (Nós e licenças →
#  "Instalar pela VPS do nó …"). Ninguém precisa entrar no terminal.
#
#    bash deploy/no/criar_instancia.sh ID_DA_TAREFA
#
#  O que faz:
#    1. lê da tarefa a instância e o nome do nó novo; o token do nó novo chega cifrado e só é aberto aqui dentro;
#    2. copia o código DESTE nó (mesma versão) para /opt/portal_web-<instância> (sem .env, backups, logs nem dados);
#    3. escreve a configuração do nó novo: as mesmas chaves da gestão, a identidade do nó novo e o MESMO proxy deste nó
#       (o nó novo entra no nginx/Traefik que já está no ar, sem mexer em nada dele);
#    4. roda o instalador em modo automático (sem perguntas): sobe banco, app e worker do nó novo, liga o ativador e o
#       backup dele e avisa a gestão. Se algo falhar, para e explica; este nó continua no ar como estava.
# =====================================================================================================================
set -uo pipefail
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
DOCKER=${DOCKER:-docker}
TID=${1:-}
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; }
para() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
[[ "$TID" =~ ^[0-9]+$ ]] || para "informe o número da tarefa"
[ "$(id -u)" = 0 ] || [ -n "${TESTE_INSTANCIA:-}" ] || para "rode como root"
cd "$PROJ"
envv() { grep -E "^$1=" "$PROJ/.env" | tail -1 | cut -d= -f2-; }
[ "$(envv PAPEL)" = no ] || para "esta pasta não é de um nó"
app() { $DOCKER compose exec -T app python -m app.tarefas "$@"; }

T=$(mktemp -d); chmod 700 "$T"; trap 'rm -rf "$T"' EXIT
( umask 077; app env-instancia "$TID" > "$T/env-origem" ) || para "não consegui ler a tarefa no app deste nó"
INST=$(grep -E '^INSTANCIA=' "$T/env-origem" | cut -d= -f2-); NOME=$(grep -E '^NO_NOME=' "$T/env-origem" | cut -d= -f2-)
[[ "$INST" =~ ^[a-z0-9]{1,20}$ ]] || para "instância inválida na tarefa"
NOVO="$(dirname "$PROJ")/portal_web-$INST"
[ "$NOVO" != "$PROJ" ] || para "a instância pedida é a deste próprio nó"
if [ -f "$NOVO/.env" ] && [ "$(grep -E '^NO_NOME=' "$NOVO/.env" | cut -d= -f2-)" != "$NOME" ]; then
  para "a pasta $NOVO já é de outro nó ($(grep -E '^NO_NOME=' "$NOVO/.env" | cut -d= -f2-)): nada foi alterado"
fi
ok "nó novo: $NOME · pasta $NOVO (instância $INST)"

# 2. código: o mesmo deste nó (a versão que está no ar aqui)
mkdir -p "$NOVO"
tar -C "$PROJ" --exclude=./.env --exclude='./.env.*' --exclude=./backups --exclude=./logs --exclude=./dados --exclude=./pacotes --exclude=./.git \
    --exclude=./deploy/no/proxy/conf.d --exclude='*/__pycache__' -cf - . | tar -C "$NOVO" -xf - || para "não consegui copiar o código para $NOVO"
chmod -R go-rwx "$NOVO/segredos" 2>/dev/null || true
ok "código copiado ($(cat "$PROJ/app/VERSAO" 2>/dev/null || echo 'versão deste nó'))"

# 3. configuração: segredos e identidade (.env.origem) + o proxy DESTE nó (o novo entra no mesmo proxy)
install -m 600 "$T/env-origem" "$NOVO/.env.origem"
MODO=$(envv PROXY_MODO); [ "$MODO" = proprio ] && MODO=existente   # o nginx "próprio" deste nó é o "existente" para o novo
{ echo "PAPEL=no"; echo "NO_NOME=$NOME"; echo "PROXY_MODO=$MODO"
  for k in NGINX_C CERTBOT_C CONF_DIR PROXY_CERTS_DIR REDE_PROXY TRAEFIK_C TRAEFIK_ENTRADA_HTTP TRAEFIK_ENTRADA_HTTPS TRAEFIK_RESOLVEDOR VPS_IP LICENCA_VALIDADE_DIAS; do
    v=$(envv $k); [ -n "$v" ] && echo "$k=$v"
  done; } > "$T/env-inicial"
[ -f "$NOVO/.env" ] || install -m 600 "$T/env-inicial" "$NOVO/.env"
ok "configuração do nó novo preparada (mesmo proxy deste nó: $MODO)"

# 4. instalador em modo automático
ok "instalando o nó novo (banco, app, worker, ativador e backup); a primeira vez leva alguns minutos"
if INSTALAR_AUTO=1 bash "$NOVO/deploy/no/instalar.sh" < /dev/null > "$T/saida" 2>&1; then
  grep -E '✔|!' "$T/saida" | sed 's/\x1b\[[0-9;]*m//g' | tail -12
  ok "nó $NOME instalado em $NOVO; ele aparece em Nós e licenças com o relatório de agora"
else
  grep -E '✔|!|✘' "$T/saida" | sed 's/\x1b\[[0-9;]*m//g' | tail -12
  para "o instalador do nó novo parou (registro completo: $NOVO/logs/instalar-no.log). Este nó continua no ar como estava."
fi
