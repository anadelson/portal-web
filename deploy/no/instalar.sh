#!/usr/bin/env bash
# Instalador de um NÓ de portais (VPS que hospeda portais e painéis de órgãos; a gestão fica em outra VPS).
# Separação gestão × portais, fase 2. Roda como root na VPS NOVA, de dentro de /opt/portal_web (pacote de código extraído).
#
#   bash deploy/no/instalar.sh              # instalação guiada: pergunta o que falta e confirma cada etapa
#   bash deploy/no/instalar.sh --verificar  # só confere (não altera nada)
#
# Um nó hospeda QUANTOS órgãos (portais) a gestão atribuir a ele: não há nada por órgão aqui. Cada órgão chega pela
# licença assinada; o banco dele é criado por uma ordem da gestão; o domínio é publicado pelo ativador deste nó.
# Pode rodar de novo a qualquer momento: mantém o que já existe (senha do banco, segredos) e só refaz o que faltar.
# NUNCA mostra senhas, chaves ou tokens: segredos são lidos sem eco e gravados só no .env (permissão 600).
set -euo pipefail
umask 077
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
LOG="$PROJ/logs/instalar-no.log"
mkdir -p "$PROJ/logs"
VERIFICAR=0; [ "${1:-}" = "--verificar" ] && VERIFICAR=1

# ---------- apoio ----------
c_ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; echo "$(date -Is) ok $*" >> "$LOG"; }
c_av() { printf '  \033[33m!\033[0m %s\n' "$*"; echo "$(date -Is) aviso $*" >> "$LOG"; }
c_er() { printf '  \033[31m✘\033[0m %s\n' "$*"; echo "$(date -Is) ERRO $*" >> "$LOG"; }
etapa() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; echo "$(date -Is) etapa $1 $2" >> "$LOG"; }
confirma() { local r; read -r -p "  $1 [s/N] " r; [[ "$r" =~ ^[sS]$ ]]; }
pergunta() { local r; read -r -p "  $1${2:+ [$2]}: " r; echo "${r:-${2:-}}"; }
segredo() { local r; read -r -s -p "  $1 (não aparece na tela): " r; echo >&2; echo "$r"; }
env_val() { [ -f "$PROJ/.env" ] && grep -E "^$1=" "$PROJ/.env" | tail -1 | cut -d= -f2- || true; }
porta_ocupada() { ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }
para() { c_er "$*"; echo "  Nada foi desfeito. Corrija e rode de novo: bash deploy/no/instalar.sh"; exit 1; }

[ "$(id -u)" = 0 ] || { echo "Rode como root (sudo bash deploy/no/instalar.sh)."; exit 1; }
[ -f "$PROJ/docker-compose.yml" ] && [ -f "$PROJ/app/main.py" ] || { echo "Rode de dentro do código do portal (/opt/portal_web)."; exit 1; }
echo "Instalador do nó de portais — $(date '+%d/%m/%Y %H:%M') — registro em $LOG (sem segredos)"

# ---------- 1. verificação (só leitura) ----------
etapa 1 "Conferência do servidor (só leitura)"
. /etc/os-release 2>/dev/null || true
echo "  Sistema: ${PRETTY_NAME:-?} · $(nproc) vCPU · $(free -m | awk '/Mem:/{print $2}') MB de RAM · disco livre em /: $(df -h / | awk 'NR==2{print $4}')"
[ "${ID:-}" = "ubuntu" ] || c_av "o instalador foi pensado para Ubuntu LTS"
[ "$(free -m | awk '/Mem:/{print $2}')" -ge 1800 ] || c_av "menos de 2 GB de RAM: apertado para banco, app, worker e nginx"
command -v docker >/dev/null && c_ok "Docker: $(docker --version | cut -d, -f1)" || c_av "Docker não instalado (etapa 3)"
echo "  Fuso: $(timedatectl show -p Timezone --value 2>/dev/null || echo ?) · relógio sincronizado: $(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo ?)"
for p in 80 443; do
  if porta_ocupada $p; then c_av "porta $p já está em uso por: $(ss -ltnpH "( sport = :$p )" | sed -E 's/.*users:\(\("([^"]+)".*/\1/' | head -1)"; else c_ok "porta $p livre"; fi
done
if [ -f "$PROJ/.env" ]; then
  [ "$(env_val PAPEL)" = "no" ] && c_ok ".env do nó já existe (as respostas anteriores viram padrão)" || c_av ".env existe, mas não é de nó (PAPEL=$(env_val PAPEL))"
fi
if [ "$VERIFICAR" = 1 ]; then
  etapa V "Situação do nó"
  if [ -f "$PROJ/.env" ] && command -v docker >/dev/null; then
    (cd "$PROJ" && docker compose ps --format '  {{.Service}}: {{.Status}}' 2>/dev/null) || true
    systemctl is-active --quiet portal-ativador.timer && c_ok "ativador ligado" || c_av "ativador desligado"
    (cd "$PROJ" && docker compose exec -T app python -m app.licenca puxar 2>/dev/null | sed 's/^/  licenças: /') || c_av "app fora do ar"
  fi
  exit 0
fi

# ---------- 2. base do sistema ----------
etapa 2 "Atualizações, fuso horário e relógio"
if confirma "Atualizar os pacotes do sistema e ajustar fuso (America/Sao_Paulo) e NTP?"; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q >> "$LOG" 2>&1 && apt-get upgrade -y -q >> "$LOG" 2>&1 || para "falha ao atualizar pacotes (veja $LOG)"
  apt-get install -y -q ca-certificates curl gnupg ufw openssl python3 >> "$LOG" 2>&1 || para "falha ao instalar pacotes básicos"
  timedatectl set-timezone America/Sao_Paulo && timedatectl set-ntp true || c_av "não consegui ajustar fuso/NTP"
  c_ok "sistema atualizado; fuso $(timedatectl show -p Timezone --value)"
else c_av "etapa pulada"; fi

# ---------- 3. Docker ----------
etapa 3 "Docker"
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  c_ok "já instalado ($(docker compose version --short))"
elif confirma "Instalar o Docker pelo repositório oficial (download.docker.com)?"; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID:-ubuntu}/gpg" -o /etc/apt/keyrings/docker.asc && chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID:-ubuntu} ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q >> "$LOG" 2>&1 && apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >> "$LOG" 2>&1 || para "falha ao instalar o Docker"
  systemctl enable --now docker >> "$LOG" 2>&1
  c_ok "Docker instalado ($(docker compose version --short))"
else para "o nó precisa do Docker"; fi

# ---------- 4. firewall ----------
etapa 4 "Firewall"
if ufw status 2>/dev/null | grep -q "Status: active"; then
  c_ok "firewall já ativo"; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
elif confirma "Ligar o firewall (ufw) liberando só SSH, 80 e 443? (a conexão SSH atual continua)"; then
  ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && ufw --force enable >/dev/null
  c_ok "firewall ativo (SSH, 80, 443)"
else c_av "firewall não ligado: faça isso pelo painel do provedor"; fi

# ---------- 5. segredos vindos da gestão ----------
etapa 5 "Segredos (iguais aos da VPS da gestão)"
echo "  As chaves abaixo PRECISAM ser as mesmas da VPS atual, senão o 2FA dos administradores, o login por CPF,"
echo "  as credenciais das fontes e os códigos do Diário param de funcionar depois da mudança."
echo "  Jeito recomendado: na VPS da gestão rode  bash deploy/no/exportar_segredos.sh  e copie o arquivo gerado para cá (scp)."
ORIGEM=""
if [ -f "$PROJ/.env.origem" ]; then
  c_ok "segredos da gestão já importados antes (.env.origem)"; ORIGEM="$PROJ/.env.origem"
else
  ARQ=$(pergunta "Caminho do pacote de segredos (segredos-no*.tar.gz.enc ou .tar.gz) — vazio para digitar as chaves" "$(ls -1t /root/segredos-no*.enc /root/segredos-no-*.tar.gz 2>/dev/null | head -1)")
  if [ -n "$ARQ" ]; then
    [ -f "$ARQ" ] || para "arquivo $ARQ não encontrado"
    T=$(mktemp -d)
    if [[ "$ARQ" == *.enc ]]; then  # gerado pelo console (Nós e licenças → Preparar instalação): cifrado com a senha do pacote
      command -v openssl >/dev/null || para "falta o openssl para abrir o pacote cifrado (apt-get install -y openssl)"
      SENHA_PACOTE=$(segredo "Senha do pacote (a que você escolheu no console)"); export SENHA_PACOTE
      openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -in "$ARQ" -out "$T/pacote.tar.gz" -pass env:SENHA_PACOTE 2>/dev/null || { unset SENHA_PACOTE; rm -rf "$T"; para "senha do pacote incorreta ou arquivo corrompido"; }
      unset SENHA_PACOTE
      tar -xzf "$T/pacote.tar.gz" -C "$T" || para "pacote de segredos ilegível"; rm -f "$T/pacote.tar.gz"
    else
      tar -xzf "$ARQ" -C "$T" || para "pacote de segredos ilegível"
    fi
    [ -f "$T/env-origem" ] || para "pacote sem env-origem (gere de novo com exportar_segredos.sh)"
    install -m 600 "$T/env-origem" "$PROJ/.env.origem"; ORIGEM="$PROJ/.env.origem"
    if [ -d "$T/segredos" ]; then mkdir -p "$PROJ/segredos"; cp -a "$T/segredos/." "$PROJ/segredos/"; chmod -R go-rwx "$PROJ/segredos"; c_ok "pasta segredos/ (certificado do Diário etc.) copiada"; fi
    rm -rf "$T"
    c_ok "segredos importados de $(basename "$ARQ") — apague o arquivo quando terminar: rm $ARQ"
  else
    c_av "sem pacote: digite as chaves da VPS da gestão"
    { for k in SECRET_KEY TOTP_CHAVE CPF_HMAC_CHAVE CHAVE_CREDENCIAIS; do v=$(segredo "$k"); [ -n "$v" ] && echo "$k=$v"; done; } > "$PROJ/.env.origem"
    chmod 600 "$PROJ/.env.origem"; ORIGEM="$PROJ/.env.origem"
  fi
fi
for k in SECRET_KEY TOTP_CHAVE CPF_HMAC_CHAVE CHAVE_CREDENCIAIS; do
  grep -qE "^$k=.+" "$ORIGEM" && c_ok "$k presente" || c_av "$k ausente (sem ela: $( [ $k = SECRET_KEY ] && echo 'NÃO prossiga' || echo 'a função correspondente fica desligada'))"
done
grep -qE "^SECRET_KEY=.+" "$ORIGEM" || para "SECRET_KEY é obrigatória (a mesma da gestão)"

# ---------- 6. configuração do nó ----------
etapa 6 "Configuração do nó"
echo "  Os dados abaixo estão no console da gestão, em Nós e licenças (cadastre o nó lá para receber o token)."
org_val() { grep -E "^$1=" "$ORIGEM" 2>/dev/null | tail -1 | cut -d= -f2- || true; }  # valor vindo do pacote de segredos
DG=$(org_val DOMINIO_GESTAO)
PADRAO=$(org_val GESTAO_URL); [ -n "$PADRAO" ] || PADRAO=$(env_val GESTAO_URL); [ -n "$PADRAO" ] || { [ -n "$DG" ] && PADRAO="https://$DG"; } || true
GESTAO_URL=$(pergunta "Endereço da gestão" "$PADRAO")
[[ "$GESTAO_URL" =~ ^https://[a-z0-9.-]+$ ]] || para "endereço da gestão inválido (ex.: https://gestao.dominio.tld)"
PADRAO=$(org_val NO_NOME); [ -n "$PADRAO" ] || PADRAO=$(env_val NO_NOME)
NO_NOME=$(pergunta "Nome do nó (o mesmo cadastrado no console)" "$PADRAO")
[[ "$NO_NOME" =~ ^[a-z0-9][a-z0-9.-]{1,60}$ ]] || para "nome do nó inválido"
NO_TOKEN=$(org_val NO_TOKEN)
if [ -n "$NO_TOKEN" ]; then
  c_ok "token do nó veio no pacote gerado pelo console (não é exibido)"
else
  NO_TOKEN=$(env_val NO_TOKEN)
  if [ -n "$NO_TOKEN" ] && ! confirma "Já existe um token do nó gravado. Trocar?"; then :; else NO_TOKEN=$(segredo "Token do nó (mostrado uma vez no console)"); fi
fi
[ ${#NO_TOKEN} -ge 30 ] || para "token do nó curto demais (copie de novo do console)"
PADRAO=$(org_val LICENCA_CHAVE_PUBLICA); [ -n "$PADRAO" ] || PADRAO=$(env_val LICENCA_CHAVE_PUBLICA)
PUB=$(pergunta "Chave pública da licença (LICENCA_CHAVE_PUBLICA, mostrada em Nós e licenças)" "$PADRAO")
python3 -c "import base64,sys; sys.exit(0 if len(base64.b64decode(sys.argv[1], validate=True)) == 32 else 1)" "$PUB" 2>/dev/null || para "chave pública inválida (copie de novo do console)"
IP_DET=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -nE 's/.* src ([0-9.]+).*/\1/p')
PADRAO=$(env_val VPS_IP); [ -n "$PADRAO" ] || PADRAO="$IP_DET"
VPS_IP=$(pergunta "IP público deste nó (o DNS dos órgãos vai apontar para ele; confira no painel do provedor)" "$PADRAO")
[[ "$VPS_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || para "IP inválido"
PADRAO=$(env_val LICENCA_VALIDADE_DIAS); [ -n "$PADRAO" ] || PADRAO=15
VALID=$(pergunta "Dias de validade da licença sem contato com a gestão" "$PADRAO")
[[ "$VALID" =~ ^[0-9]{1,3}$ ]] || para "validade inválida"

# ---------- 7. nginx e certificados ----------
etapa 7 "nginx e certificados (Let's Encrypt)"
MODO=$(env_val PROXY_MODO)
if [ -z "$MODO" ]; then
  if (porta_ocupada 80 || porta_ocupada 443) && ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx portal-nginx; then
    echo "  As portas 80/443 já são usadas por outro sistema nesta VPS."
    echo "  [1] usar o nginx que já existe (como na VPS da gestão, que usa o nginx de outro projeto)   [2] parar aqui"
    [ "$(pergunta "Escolha" "1")" = "1" ] && MODO=existente || para "libere as portas 80/443 ou escolha usar o nginx existente"
  else MODO=proprio; fi
fi
if [ "$MODO" = proprio ]; then
  NGINX_C=portal-nginx; CERTBOT_C=portal-certbot; REDE=portal-proxy
  CONF_DIR="$PROJ/deploy/no/proxy/conf.d"; CERTS_DIR=/var/lib/docker/volumes/portal-proxy_certs/_data
  mkdir -p "$CONF_DIR"; install -m 644 "$PROJ/deploy/no/proxy/00-acme.conf" "$CONF_DIR/00-acme.conf"; install -m 644 "$PROJ/deploy/nginx/portal-comum.inc" "$CONF_DIR/portal-comum.inc"
  chmod 755 "$CONF_DIR"
  if confirma "Subir o nginx e o certbot próprios do nó (portas 80 e 443)?"; then
    (cd "$PROJ/deploy/no/proxy" && docker compose up -d >> "$LOG" 2>&1) || para "nginx/certbot não subiram (veja $LOG)"
    docker exec "$NGINX_C" nginx -t >> "$LOG" 2>&1 && c_ok "nginx no ar e configuração válida" || para "nginx -t falhou (veja $LOG)"
  else para "o nó precisa do nginx"; fi
else
  echo "  Dados do nginx existente (nome do container, pasta conf.d no servidor, pasta dos certificados e rede docker):"
  NGINX_C=$(pergunta "Container do nginx" "$(env_val NGINX_C || true)"); CERTBOT_C=$(pergunta "Container do certbot" "$(env_val CERTBOT_C || true)")
  CONF_DIR=$(pergunta "Pasta conf.d do nginx (no servidor)" "$(env_val CONF_DIR || true)"); CERTS_DIR=$(pergunta "Pasta dos certificados (letsencrypt, no servidor)" "$(env_val CERTS_DIR || true)")
  REDE=$(pergunta "Rede docker do nginx" "$(env_val REDE_PROXY || true)")
  docker inspect "$NGINX_C" >/dev/null 2>&1 || para "container $NGINX_C não existe"; docker inspect "$CERTBOT_C" >/dev/null 2>&1 || para "container $CERTBOT_C não existe"
  [ -d "$CONF_DIR" ] && [ -d "$CERTS_DIR" ] || para "pasta conf.d ou de certificados não existe"; docker network inspect "$REDE" >/dev/null 2>&1 || para "rede $REDE não existe"
  install -m 644 "$PROJ/deploy/nginx/portal-comum.inc" "$CONF_DIR/portal-comum.inc"
  c_av "o nginx existente precisa responder /.well-known/acme-challenge/ na porta 80 a partir de /var/www/certbot (veja deploy/no/proxy/00-acme.conf)"
fi

# ---------- .env do nó ----------
PGP=$(env_val PG_PASSWORD); [ -n "$PGP" ] && [ "$(env_val PAPEL)" = no ] || PGP=$(openssl rand -hex 24)
NOVO=$(mktemp)
grep -vE '^(PAPEL|NO_BANCO|GESTAO_URL|NO_TOKEN|NO_NOME|LICENCA_CHAVE_PUBLICA|LICENCA_VALIDADE_DIAS|VPS_IP|PG_PASSWORD|PG_HOST|COMPOSE_FILE|REDE_PROXY|PROXY_MODO|NGINX_C|CERTBOT_C|CONF_DIR|CERTS_DIR|DOMINIO_PM|DOMINIO_CM|SENHA_INICIAL_ADMIN|SENHA_INICIAL_GESTOR)=' "$ORIGEM" > "$NOVO" || true
{ echo; echo "# ---- nó de portais (gerado por deploy/no/instalar.sh em $(date -Is)) ----"
  echo "PAPEL=no"; echo "GESTAO_URL=$GESTAO_URL"; echo "NO_NOME=$NO_NOME"; echo "NO_TOKEN=$NO_TOKEN"; echo "LICENCA_CHAVE_PUBLICA=$PUB"
  echo "LICENCA_VALIDADE_DIAS=$VALID"; echo "VPS_IP=$VPS_IP"; echo "PG_PASSWORD=$PGP"; echo "PG_HOST=db"
  echo "COMPOSE_FILE=docker-compose.yml:deploy/no/docker-compose.no.yml"; echo "REDE_PROXY=$REDE"; echo "PROXY_MODO=$MODO"
  echo "NGINX_C=$NGINX_C"; echo "CERTBOT_C=$CERTBOT_C"; echo "CONF_DIR=$CONF_DIR"; echo "CERTS_DIR=$CERTS_DIR"; } >> "$NOVO"
grep -qE '^PG_USER=.+' "$NOVO" || echo "PG_USER=portal" >> "$NOVO"
[ -f "$PROJ/.env" ] && cp -p "$PROJ/.env" "$PROJ/.env.anterior-$(date +%Y%m%d%H%M%S)"
install -m 600 "$NOVO" "$PROJ/.env"; rm -f "$NOVO"
unset NO_TOKEN PGP
c_ok ".env do nó gravado (permissão 600; valores não exibidos)"

# ---------- 8. portal ----------
etapa 8 "Portal: banco, app e worker"
if confirma "Gerar a imagem e subir banco, app e worker (com os limites de memória do projeto)?"; then
  cd "$PROJ"
  docker compose build app worker >> "$LOG" 2>&1 || para "falha ao gerar a imagem (veja $LOG)"
  docker compose up -d db >> "$LOG" 2>&1
  for i in $(seq 1 40); do docker compose exec -T db pg_isready -q >/dev/null 2>&1 && break; sleep 3; done
  docker compose up -d app >> "$LOG" 2>&1
  for i in $(seq 1 40); do docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=5)" >/dev/null 2>&1 && break; sleep 3; done
  docker compose exec -T app python -m app.provision atualizar >> "$LOG" 2>&1 || para "provision falhou (veja $LOG)"
  docker compose up -d worker >> "$LOG" 2>&1
  c_ok "banco, app e worker no ar; banco local do nó preparado"
else para "o nó precisa do portal no ar"; fi

# ---------- 9. ativador e backup ----------
etapa 9 "Ativador de domínios e backup diário"
if confirma "Instalar o ativador (a cada minuto) e o backup diário (02h00, guarda 14 dias)?"; then
  install -m 644 "$PROJ/deploy/systemd/portal-ativador.service" "$PROJ/deploy/systemd/portal-ativador.timer" /etc/systemd/system/
  mkdir -p /etc/systemd/system/portal-ativador.service.d
  printf '[Service]\nEnvironment=PROJ=%s\nEnvironment=CONF_DIR=%s\nEnvironment=CERTS_DIR=%s\nEnvironment=NGINX_C=%s\nEnvironment=CERTBOT_C=%s\n' \
    "$PROJ" "$CONF_DIR" "$CERTS_DIR" "$NGINX_C" "$CERTBOT_C" > /etc/systemd/system/portal-ativador.service.d/no.conf
  chmod 644 /etc/systemd/system/portal-ativador.service.d/no.conf
  systemctl daemon-reload && systemctl enable --now portal-ativador.timer >> "$LOG" 2>&1 && c_ok "ativador ligado"
  echo "0 2 * * * root $PROJ/deploy/backup.sh >> $PROJ/backups/backup.log 2>&1" > /etc/cron.d/portal-backup; chmod 644 /etc/cron.d/portal-backup
  mkdir -p "$PROJ/backups"; c_ok "backup diário agendado (copie $PROJ/backups para fora da VPS — combine o destino)"
else c_av "etapa pulada: sem ativador, nenhum domínio é publicado"; fi

# ---------- 10. conferência ----------
etapa 10 "Conferência com a gestão"
cd "$PROJ"
R=$(docker compose exec -T app python -m app.licenca puxar 2>&1 | tail -1) || true
[[ "$R" == *"aceitas"* ]] && c_ok "licenças: $R" || c_er "licenças: $R"
R=$(docker compose exec -T app python -m app.relatorio enviar 2>&1 | tail -1) || true
[[ "$R" == relatório\ entregue* ]] && c_ok "$R" || c_er "relatório: $R"
echo
echo "Pronto. No console da gestão, em Nós e licenças, o nó $NO_NOME deve aparecer com IP $VPS_IP e o relatório de agora."
echo "Próximos passos (no console da gestão): hospedar órgãos neste nó; o nó cria cada banco em até 1 minuto e publica"
echo "o domínio de cada órgão quando você pedir (DNS do órgão apontando para $VPS_IP)."
echo "Para conferir depois sem mudar nada: bash deploy/no/instalar.sh --verificar"
