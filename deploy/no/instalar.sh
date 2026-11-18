#!/usr/bin/env bash
# =====================================================================================================================
#  Instalador de um NÓ de portais
# =====================================================================================================================
#  O que é um nó: uma VPS que hospeda os portais e painéis dos órgãos. A gestão (console, contratos, licenças) fica em
#  outra VPS. Um nó hospeda quantos órgãos a gestão atribuir a ele — não há nada por órgão neste script: cada órgão
#  chega depois, pela licença assinada; o banco dele é criado por uma ordem da gestão; o domínio é publicado pelo
#  ativador deste nó.
#
#  Como usar (como root, na VPS NOVA, de dentro de /opt/portal_web):
#      bash deploy/no/instalar.sh              # instalação guiada: descobre o que puder, pergunta o resto e
#                                              #   pede confirmação antes de cada etapa que altera a VPS
#      bash deploy/no/instalar.sh --verificar  # só confere (não altera nada)
#
#  Etapas:  1 conferência (só leitura)   2 atualizações/fuso/relógio   3 Docker   4 firewall   5 segredos da gestão
#           6 dados do nó   7 proxy (nginx ou Traefik) e certificados   8 banco/app/worker   9 ativador e backup
#           10 conferência final
#
#  VPS COMPARTILHADA (outros sistemas já usam as portas 80/443, ex.: Dokploy/Traefik ou outro nginx):
#    - a etapa 2 vem desligada por padrão e, se pedida, NÃO atualiza o Docker (reiniciaria todos os containers da VPS),
#      não reinicia serviços e não muda o fuso do servidor;
#    - a etapa 4 não liga o firewall por padrão (poderia bloquear serviços de fora do Docker);
#    - na etapa 7 o portal entra no proxy que já existe, acrescentando só os arquivos dele.
#
#  Pode rodar de novo a qualquer momento: mantém o que já existe (senha do banco, token, segredos) e refaz o que faltar.
#  NUNCA mostra senhas, chaves ou tokens: são lidos sem eco e gravados só no .env (permissão 600).
#  Tudo o que os comandos longos escrevem vai para o registro logs/instalar-no.log (sem segredos); na tela aparece
#  o andamento (tempo decorrido e a última linha do registro), para não parecer travado.
# =====================================================================================================================
set -euo pipefail
umask 077                                    # arquivos criados aqui nascem legíveis só pelo root

PROJ=$(cd "$(dirname "$0")/../.." && pwd)    # pasta do código (normalmente /opt/portal_web)
# Instância (mais de um nó na mesma VPS, 18/11/2026): sai do nome da pasta. /opt/portal_web = a de sempre;
# /opt/portal_web-camara = instância "camara", com containers, banco, apelido no proxy, rotas, ativador e backup próprios.
PASTA_BASE=$(basename "$PROJ"); INST=""
if [[ "$PASTA_BASE" =~ ^portal_web-([a-z0-9]{1,20})$ ]]; then INST=${BASH_REMATCH[1]}
elif [ "$PASTA_BASE" != portal_web ]; then echo "A pasta do código deve ser /opt/portal_web ou /opt/portal_web-<instância> (letras minúsculas e números)."; exit 1; fi
SUF=${INST:+-$INST}; APP_ALIAS=portal-web-app$SUF; ATIV=portal-ativador$SUF
LOG="$PROJ/logs/instalar-no.log"
mkdir -p "$PROJ/logs"
VERIFICAR=0; [ "${1:-}" = "--verificar" ] && VERIFICAR=1
TOTAL=10                                     # número de etapas (para mostrar "etapa 3/10")
INICIO=$SECONDS

# =====================================================================================================================
#  Funções de apoio (mensagens, perguntas e andamento)
# =====================================================================================================================
TELA=0; [ -t 1 ] && TELA=1                   # 1 = terminal de verdade (mostra o andamento animado); 0 = saída redirecionada

c_ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; echo "$(date -Is) ok $*" >> "$LOG"; }       # deu certo
c_av() { printf '  \033[33m!\033[0m %s\n' "$*"; echo "$(date -Is) aviso $*" >> "$LOG"; }    # atenção, mas segue
c_er() { printf '  \033[31m✘\033[0m %s\n' "$*"; echo "$(date -Is) ERRO $*" >> "$LOG"; }     # erro
etapa() { printf '\n\033[1m[%s/%s] %s\033[0m\n' "$1" "$TOTAL" "$2"; echo "$(date -Is) etapa $1 $2" >> "$LOG"; }
# para "motivo": encerra sem desfazer nada (rodar de novo continua de onde parou)
para() { c_er "$*"; echo "  Nada foi desfeito. Corrija e rode de novo: bash deploy/no/instalar.sh"; exit 1; }

# Perguntas. confirma = padrão NÃO (Enter recusa); confirma_s = padrão SIM (Enter aceita).
confirma()   { local r; read -r -p "  $1 [s/N] " r; [[ "$r" =~ ^[sS]$ ]]; }
confirma_s() { local r; read -r -p "  $1 [S/n] " r; ! [[ "$r" =~ ^[nN]$ ]]; }
pergunta()   { local r; read -r -p "  $1${2:+ [$2]}: " r; echo "${r:-${2:-}}"; }          # Enter = valor entre [ ]
segredo()    { local r; read -r -s -p "  $1 (não aparece na tela): " r; echo >&2; echo "$r"; }

env_val() { [ -f "$PROJ/.env" ] && grep -E "^$1=" "$PROJ/.env" | tail -1 | cut -d= -f2- || true; }  # valor já gravado
porta_ocupada() { ss -ltnH "( sport = :$1 )" 2>/dev/null | grep -q .; }
tempo() { printf '%dm%02ds' $(($1 / 60)) $(($1 % 60)); }

# rodar "descrição" comando [args...]
#   Roda um comando demorado com a saída indo para o registro. Enquanto roda, mostra na mesma linha:
#   indicador girando, tempo decorrido e a última linha do registro (ex.: o pacote que o apt está instalando).
#   Devolve o código de saída do comando (use:  rodar "..." cmd || para "...").
rodar() {
  local txt=$1 ini=$SECONDS rc=0; shift
  echo "$(date -Is) início: $txt" >> "$LOG"
  if [ "$TELA" = 1 ]; then
    "$@" >> "$LOG" 2>&1 &
    local pid=$! i=0 giro='|/-\' ult
    while kill -0 "$pid" 2>/dev/null; do
      ult=$(tail -n 1 "$LOG" 2>/dev/null | tr -d '\000-\037\177'); ult=${ult:0:70}   # última linha, sem caracteres de controle
      printf '\r\033[K  %s %s — %s %s' "${giro:i++%4:1}" "$txt" "$(tempo $((SECONDS - ini)))" "${ult:+· $ult}"
      sleep 1
    done
    wait "$pid" || rc=$?
    printf '\r\033[K'
  else
    echo "  … $txt"
    "$@" >> "$LOG" 2>&1 || rc=$?
  fi
  [ "$rc" = 0 ] && c_ok "$txt ($(tempo $((SECONDS - ini))))"
  return "$rc"
}

# esperar "descrição" segundos_máximos comando [args...]
#   Repete o comando a cada 3 s até dar certo, mostrando o tempo de espera. Devolve 1 se passar do máximo.
esperar() {
  local txt=$1 max=$2 ini=$SECONDS; shift 2
  until "$@" >/dev/null 2>&1; do
    if [ $((SECONDS - ini)) -ge "$max" ]; then [ "$TELA" = 1 ] && printf '\r\033[K'; return 1; fi
    [ "$TELA" = 1 ] && printf '\r\033[K  … %s — %s' "$txt" "$(tempo $((SECONDS - ini)))"
    sleep 3
  done
  [ "$TELA" = 1 ] && printf '\r\033[K'
  c_ok "$txt ($(tempo $((SECONDS - ini))))"
}

# ---------------------------------------------------------------------------------------------------------------------
#  Descoberta do nginx que já existe na VPS (usado quando as portas 80/443 já estão ocupadas por outro sistema).
#  O ativador do nó precisa de 5 coisas desse nginx; aqui elas são lidas do próprio Docker, sem perguntar:
#    D_NGINX   container que publica a porta 443 (ou 80)
#    D_CONF    pasta do servidor montada em /etc/nginx/conf.d dentro dele  (onde o ativador grava portal-orgaos.conf)
#    D_CERTS   pasta do servidor montada em /etc/letsencrypt               (onde ficam os certificados)
#    D_REDE    rede docker do nginx                                        (o app do portal entra nela)
#    D_CERTBOT container que monta a MESMA pasta de certificados           (o ativador pede certificados nele)
#    D_WEBROOT pasta montada em /var/www/certbot (desafio do Let's Encrypt) — conferida no certbot também
#  O que não for encontrado fica vazio e é perguntado depois.
# ---------------------------------------------------------------------------------------------------------------------
montagem() {  # montagem CONTAINER /caminho/dentro → pasta correspondente no servidor
  { docker inspect -f '{{range .Mounts}}{{.Destination}}|{{.Source}}{{"\n"}}{{end}}' "$1" 2>/dev/null || true; } \
    | awk -F'|' -v d="$2" '$1 == d { print $2; exit }'
}
descobrir_nginx() {
  D_NGINX=""; D_CONF=""; D_CERTS=""; D_REDE=""; D_CERTBOT=""; D_WEBROOT=""
  command -v docker >/dev/null || return 1
  D_NGINX=$(docker ps --filter publish=443 --format '{{.Names}}' 2>/dev/null | head -1)
  [ -n "$D_NGINX" ] || D_NGINX=$(docker ps --filter publish=80 --format '{{.Names}}' 2>/dev/null | head -1)
  [ -n "$D_NGINX" ] || return 1                # as portas são de um programa fora do Docker
  D_CONF=$(montagem "$D_NGINX" /etc/nginx/conf.d)
  D_CERTS=$(montagem "$D_NGINX" /etc/letsencrypt)
  D_WEBROOT=$(montagem "$D_NGINX" /var/www/certbot)
  D_REDE=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$D_NGINX" 2>/dev/null \
             | grep -vxE 'bridge|host|none|' | head -1 || true)
  if [ -n "$D_CERTS" ]; then
    local c
    for c in $(docker ps --format '{{.Names}}' 2>/dev/null); do
      [ "$c" = "$D_NGINX" ] && continue
      if [ "$(montagem "$c" /etc/letsencrypt)" = "$D_CERTS" ]; then D_CERTBOT=$c; break; fi
    done
  fi
  return 0
}

# ---------------------------------------------------------------------------------------------------------------------
#  Descoberta do Traefik (ex.: o do Dokploy) quando é ele que ocupa as portas 80/443.
#    D_TRAEFIK   container do Traefik (publica 443/80, ou a imagem é traefik)
#    D_DIN       pasta do servidor com as rotas dinâmicas (provedor "file" do Traefik) — o ativador grava portal-orgaos.yml nela
#    D_REDE      rede docker do Traefik (o app do portal entra nela)
#    D_HTTP / D_HTTPS  nomes das entradas das portas 80 e 443 (no Dokploy: web e websecure)
#    D_RESOLV    resolvedor de certificados do Traefik (no Dokploy: letsencrypt)
#    D_WATCH     se o Traefik relê a pasta sozinho (watch: true)
#  Lê a configuração do próprio Traefik (arquivo traefik.yml montado no container e os argumentos de linha de comando).
# ---------------------------------------------------------------------------------------------------------------------
e_traefik() { docker inspect -f '{{.Config.Image}}' "$1" 2>/dev/null | grep -qi traefik; }
descobrir_traefik() {
  D_TRAEFIK=""; D_DIN=""; D_REDE=""; D_HTTP=""; D_HTTPS=""; D_RESOLV=""; D_WATCH=""
  command -v docker >/dev/null || return 1
  local c
  for c in $(docker ps --filter publish=443 --format '{{.Names}}' 2>/dev/null) $(docker ps --filter publish=80 --format '{{.Names}}' 2>/dev/null) \
           $(docker ps --format '{{.Names}}' 2>/dev/null); do
    if e_traefik "$c"; then D_TRAEFIK=$c; break; fi
  done
  [ -n "$D_TRAEFIK" ] || return 1
  local estatico="" d
  for d in /etc/traefik/traefik.yml /etc/traefik/traefik.yaml /etc/traefik/traefik.toml; do
    estatico=$(montagem "$D_TRAEFIK" "$d"); [ -n "$estatico" ] && break
  done
  [ -z "$estatico" ] && [ -d "$(montagem "$D_TRAEFIK" /etc/traefik)" ] && estatico="$(montagem "$D_TRAEFIK" /etc/traefik)/traefik.yml"
  local args; args=$(docker inspect -f '{{range .Args}}{{.}}{{"\n"}}{{end}}{{range .Config.Cmd}}{{.}}{{"\n"}}{{end}}' "$D_TRAEFIK" 2>/dev/null || true)
  local saida; saida=$(TRAEFIK_ARGS="$args" python3 - "${estatico:-}" <<'PY' 2>/dev/null || true
import os, re, sys
cfg = {}
def plano(d, pre=''):
    for k, v in (d or {}).items():
        if isinstance(v, dict): plano(v, pre + str(k).lower() + '.')
        else: cfg[pre + str(k).lower()] = str(v)
arq = sys.argv[1] if len(sys.argv) > 1 else ''
if arq and os.path.isfile(arq):
    txt = open(arq, encoding='utf-8', errors='replace').read()
    try:
        import yaml; plano(yaml.safe_load(txt))
    except Exception:  # sem PyYAML: leitor simples de mapas por indentação (basta para estas chaves)
        pilha = []
        for linha in txt.splitlines():
            if not linha.strip() or linha.lstrip().startswith(('#', '-')): continue
            m = re.match(r'^(\s*)([A-Za-z0-9_.-]+)\s*:\s*(.*?)\s*$', linha)
            if not m: continue
            ind = len(m.group(1)); pilha = [p for p in pilha if p[0] < ind]
            chave = '.'.join([p[1] for p in pilha] + [m.group(2).lower()])
            val = m.group(3).split(' #')[0].strip().strip('"\'')
            if val: cfg[chave] = val
            else: pilha.append((ind, m.group(2).lower()))
for a in os.environ.get('TRAEFIK_ARGS', '').split('\n'):  # --providers.file.directory=/x  --entrypoints.web.address=:80 ...
    m = re.match(r'^--([^=]+)=(.*)$', a.strip())
    if m: cfg[m.group(1).lower()] = m.group(2)
ent = {}
for k, v in cfg.items():
    m = re.match(r'^entrypoints\.([^.]+)\.address$', k)
    if m: ent[v.strip().rsplit(':', 1)[-1].split('/')[0]] = m.group(1)
res = sorted({k.split('.')[1] for k in cfg if k.startswith('certificatesresolvers.')})
print(cfg.get('providers.file.directory', ''))
print(ent.get('80', ''))
print(ent.get('443', ''))
print(res[0] if len(res) == 1 else ('letsencrypt' if 'letsencrypt' in res else ''))
print(cfg.get('providers.file.watch', ''))
PY
)
  local din_c; { read -r din_c; read -r D_HTTP; read -r D_HTTPS; read -r D_RESOLV; read -r D_WATCH; } <<< "$saida" || true
  [ -n "$din_c" ] && D_DIN=$(montagem "$D_TRAEFIK" "$din_c")
  D_REDE=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$D_TRAEFIK" 2>/dev/null \
             | grep -vxE 'bridge|host|none|ingress|' | head -1 || true)
  return 0
}

# trecho comum dos vhosts (portal-comum[-INST].inc) apontando para o app desta instância
instalar_inc() { sed "s/portal-web-app:8000/$APP_ALIAS:8000/" "$PROJ/deploy/nginx/portal-comum.inc" > "$1/portal-comum$SUF.inc" && chmod 644 "$1/portal-comum$SUF.inc"; }

# ---------------------------------------------------------------------------------------------------------------------
#  Começo
# ---------------------------------------------------------------------------------------------------------------------
[ "$(id -u)" = 0 ] || { echo "Rode como root (sudo bash deploy/no/instalar.sh)."; exit 1; }
[ -f "$PROJ/docker-compose.yml" ] && [ -f "$PROJ/app/main.py" ] || { echo "Rode de dentro do código do portal (/opt/portal_web ou /opt/portal_web-<instância>)."; exit 1; }
echo "Instalador do nó de portais — $(date '+%d/%m/%Y %H:%M')"
echo "Registro detalhado (sem segredos): $LOG   ·   para acompanhar em outro terminal: tail -f $LOG"

# =====================================================================================================================
#  1. Conferência do servidor — só lê, não altera nada
# =====================================================================================================================
etapa 1 "Conferência do servidor (só leitura)"
. /etc/os-release 2>/dev/null || true
echo "  Sistema: ${PRETTY_NAME:-?} · $(nproc) vCPU · $(free -m | awk '/Mem:/{print $2}') MB de RAM · disco livre em /: $(df -h / | awk 'NR==2{print $4}')"
[ "${ID:-}" = "ubuntu" ] || c_av "o instalador foi pensado para Ubuntu LTS"
[ "$(free -m | awk '/Mem:/{print $2}')" -ge 1800 ] || c_av "menos de 2 GB de RAM: apertado para banco, app, worker e nginx"
command -v docker >/dev/null && c_ok "Docker: $(docker --version | cut -d, -f1)" || c_av "Docker não instalado (etapa 3 instala)"
echo "  Fuso: $(timedatectl show -p Timezone --value 2>/dev/null || echo ?) · relógio sincronizado: $(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo ?)"
for p in 80 443; do
  if porta_ocupada $p; then c_av "porta $p já está em uso por: $(ss -ltnpH "( sport = :$p )" | sed -E 's/.*users:\(\("([^"]+)".*/\1/' | head -1)"; else c_ok "porta $p livre"; fi
done
# VPS compartilhada = 80/443 já usadas por outro sistema (não pelo nginx próprio do nó), ou instalação anterior assim
COMPARTILHADA=0
if (porta_ocupada 80 || porta_ocupada 443) && { [ -n "$INST" ] || ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx portal-nginx; }; then COMPARTILHADA=1; fi
[ -n "$INST" ] && c_ok "instância \"$INST\" (pasta $PROJ): containers, banco e rotas separados do outro nó desta VPS"
case "$(env_val PROXY_MODO)" in existente|traefik) COMPARTILHADA=1 ;; esac
if [ "$COMPARTILHADA" = 1 ]; then
  c_av "VPS COMPARTILHADA: outros sistemas já usam as portas 80/443. Para não derrubar nada do que já está no ar,"
  echo "    as etapas 2 (atualizações) e 4 (firewall) vêm desligadas por padrão — Enter pula."
fi
# Trava (18/11/2026): este instalador é SÓ para a VPS de um nó. Rodado na VPS da gestão (portal em papel "tudo"), ele trocava
# o .env da gestão pelo de um nó (outra senha do banco, sem os domínios) e derrubava gestão e portais. Agora para antes de mexer.
APP_ENV=$(docker inspect portal_web-app-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null || true)   # vazio = não há container do portal
PAPEL_APP=$(printf '%s\n' "$APP_ENV" | grep -E '^PAPEL=' | cut -d= -f2- || true); [ -n "$APP_ENV" ] && [ -z "$PAPEL_APP" ] && PAPEL_APP=tudo   # sem PAPEL = "tudo" (padrão)
if [ -f "$PROJ/.env" ] && [ "$(env_val PAPEL)" != "no" ]; then
  c_er "esta VPS já roda a GESTÃO/portais (o .env daqui não é de nó: PAPEL=$(env_val PAPEL))"
  echo "  Este instalador é só para a VPS do nó. Rode os comandos na VPS do nó, não nesta."
  echo "  Nada foi alterado."; exit 1
elif [ ! -f "$PROJ/.env" ] && [ -n "$PAPEL_APP" ] && [ "$PAPEL_APP" != "no" ]; then
  c_er "esta VPS já tem o portal rodando como GESTÃO (container portal_web-app-1, PAPEL=$PAPEL_APP)"
  echo "  Este instalador é só para a VPS do nó. Rode os comandos na VPS do nó, não nesta."
  echo "  Nada foi alterado."; exit 1
elif [ -f "$PROJ/.env" ]; then
  c_ok ".env do nó já existe (as respostas anteriores viram padrão)"
fi
if [ "$VERIFICAR" = 1 ]; then               # modo --verificar: mostra a situação e sai sem mexer em nada
  etapa V "Situação do nó"
  if [ -f "$PROJ/.env" ] && command -v docker >/dev/null; then
    (cd "$PROJ" && docker compose ps --format '  {{.Service}}: {{.Status}}' 2>/dev/null) || true
    if [ "$(env_val PROXY_MODO)" = traefik ]; then
      echo "  proxy: Traefik $(env_val TRAEFIK_C) · rotas em: $(env_val CONF_DIR)/portal-orgaos$SUF.yml · rede: $(env_val REDE_PROXY) · resolvedor: $(env_val TRAEFIK_RESOLVEDOR)"
    else
      echo "  proxy: nginx $(env_val NGINX_C) · conf.d: $(env_val CONF_DIR) · certificados: $(env_val PROXY_CERTS_DIR)$(env_val CERTS_DIR) · rede: $(env_val REDE_PROXY)"
    fi
    systemctl is-active --quiet "$ATIV.timer" && c_ok "ativador ligado" || c_av "ativador desligado"
    (cd "$PROJ" && docker compose exec -T app python -m app.licenca puxar 2>/dev/null | sed 's/^/  licenças: /') || c_av "app fora do ar"
  fi
  exit 0
fi

# =====================================================================================================================
#  2. Atualizações do sistema, fuso horário (America/Sao_Paulo) e relógio sincronizado (NTP)
#     O relógio certo importa: 2FA, validade das licenças e horário de publicação do Diário dependem dele.
# =====================================================================================================================
etapa 2 "Atualizações, fuso horário e relógio"
# Na VPS compartilhada: o Docker fica de fora da atualização (atualizá-lo reinicia TODOS os containers da VPS),
# o needrestart só lista (não reinicia serviços) e o fuso do servidor não muda (os containers do portal já usam
# America/Sao_Paulo por conta própria).
SEGURADOS=""
soltar_docker() { [ -n "$SEGURADOS" ] && apt-mark unhold $SEGURADOS >> "$LOG" 2>&1; SEGURADOS=""; }
if [ "$COMPARTILHADA" = 1 ]; then
  PERG="VPS compartilhada: atualizar os pacotes do sistema mesmo assim? (o Docker fica de fora e nenhum serviço é reiniciado)"
else
  PERG="Atualizar os pacotes do sistema e ajustar fuso (America/Sao_Paulo) e NTP?"
fi
if confirma "$PERG"; then
  export DEBIAN_FRONTEND=noninteractive      # o apt não para para fazer perguntas
  if [ "$COMPARTILHADA" = 1 ]; then
    export NEEDRESTART_MODE=l                # só lista os serviços que precisariam reiniciar
    for pk in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin docker.io containerd runc; do
      dpkg -s "$pk" >/dev/null 2>&1 && ! apt-mark showhold 2>/dev/null | grep -qx "$pk" && SEGURADOS="$SEGURADOS $pk"
    done
    [ -n "$SEGURADOS" ] && apt-mark hold $SEGURADOS >> "$LOG" 2>&1 && c_ok "Docker segurado durante a atualização:$SEGURADOS"
  fi
  rodar "Lendo a lista de pacotes (apt update)" apt-get update -q || { soltar_docker; para "falha ao ler a lista de pacotes (veja $LOG)"; }
  rodar "Atualizando os pacotes do sistema (pode levar alguns minutos)" apt-get upgrade -y -q || { soltar_docker; para "falha ao atualizar pacotes (veja $LOG)"; }
  rodar "Instalando ferramentas básicas (curl, openssl, ufw, python3)" apt-get install -y -q ca-certificates curl gnupg ufw openssl python3 \
    || { soltar_docker; para "falha ao instalar pacotes básicos (veja $LOG)"; }
  soltar_docker
  if [ "$COMPARTILHADA" = 1 ]; then
    timedatectl set-ntp true || c_av "não consegui ligar o NTP"
    c_ok "fuso do servidor mantido ($(timedatectl show -p Timezone --value 2>/dev/null || echo ?)); o portal usa America/Sao_Paulo nos containers"
  else
    timedatectl set-timezone America/Sao_Paulo && timedatectl set-ntp true || c_av "não consegui ajustar fuso/NTP"
    c_ok "fuso $(timedatectl show -p Timezone --value)"
  fi
else c_av "etapa pulada"; fi

# =====================================================================================================================
#  3. Docker (repositório oficial download.docker.com). Banco, app, worker e nginx rodam em contêineres.
# =====================================================================================================================
etapa 3 "Docker"
instalar_docker() {
  install -m 0755 -d /etc/apt/keyrings \
  && curl -fsSL "https://download.docker.com/linux/${ID:-ubuntu}/gpg" -o /etc/apt/keyrings/docker.asc && chmod a+r /etc/apt/keyrings/docker.asc \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID:-ubuntu} ${VERSION_CODENAME} stable" \
       > /etc/apt/sources.list.d/docker.list \
  && apt-get update -q \
  && apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
  && systemctl enable --now docker
}
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then
  c_ok "já instalado ($(docker compose version --short))"
elif confirma "Instalar o Docker pelo repositório oficial (download.docker.com)?"; then
  rodar "Instalando o Docker" instalar_docker || para "falha ao instalar o Docker (veja $LOG)"
  c_ok "Docker $(docker compose version --short)"
else para "o nó precisa do Docker"; fi

# =====================================================================================================================
#  4. Firewall (ufw): deixa entrar só SSH, 80 (http) e 443 (https). A conexão SSH atual não cai.
# =====================================================================================================================
etapa 4 "Firewall"
if ufw status 2>/dev/null | grep -q "Status: active"; then
  c_ok "firewall já ativo"; ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
elif [ "$COMPARTILHADA" = 1 ] && ! confirma "VPS compartilhada: ligar o firewall pode BLOQUEAR serviços desta VPS que não estão em Docker. Ligar mesmo assim (só SSH, 80 e 443)?"; then
  c_av "firewall não mexido (VPS compartilhada): confira as regras no painel do provedor"
elif [ "$COMPARTILHADA" = 1 ] || confirma "Ligar o firewall (ufw) liberando só SSH, 80 e 443? (a conexão SSH atual continua)"; then
  ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null && ufw --force enable >/dev/null
  c_ok "firewall ativo (SSH, 80, 443)"
else c_av "firewall não ligado: faça isso pelo painel do provedor"; fi

# =====================================================================================================================
#  5. Segredos vindos da gestão
#     SECRET_KEY, TOTP_CHAVE, CPF_HMAC_CHAVE e CHAVE_CREDENCIAIS PRECISAM ser iguais às da VPS da gestão.
#     Origem (nesta ordem): .env.origem já importado → pacote em /root (o mais novo é sugerido) → digitar as chaves.
#     O pacote .enc vem do console (Nós e licenças → Preparar instalação) e é aberto com a senha do pacote.
# =====================================================================================================================
etapa 5 "Segredos (iguais aos da VPS da gestão)"
echo "  As chaves abaixo PRECISAM ser as mesmas da gestão, senão o 2FA dos administradores, o login por CPF,"
echo "  as credenciais das fontes e os códigos do Diário param de funcionar."
ORIGEM=""
if [ -n "$INST" ]; then ACHADO=$(ls -1t "/root/segredos-no@$INST.tar.gz.enc" 2>/dev/null | head -1 || true)   # pacote da instância
else ACHADO=$(ls -1t /root/segredos-no*.enc /root/segredos-no-*.tar.gz 2>/dev/null | grep -v '@' | head -1 || true); fi  # "@" = pacote de outra instância
# Pacote NOVO (mais recente que o .env.origem já importado) = reinstalação com dados novos do console (token, nome do nó):
# usa o pacote. Antes (até 18/11/2026) o .env.origem antigo tinha prioridade e o pacote novo era ignorado.
USAR_PACOTE_NOVO=""
if [ -f "$PROJ/.env.origem" ] && [ -n "$ACHADO" ] && [ "$ACHADO" -nt "$PROJ/.env.origem" ]; then
  c_av "há um pacote de segredos mais novo que o já importado: $ACHADO"
  confirma_s "Usar o pacote novo (traz o token e o nome do nó gerados agora no console)?" && USAR_PACOTE_NOVO=1
fi
if [ -f "$PROJ/.env.origem" ] && [ -z "$USAR_PACOTE_NOVO" ]; then
  c_ok "segredos da gestão já importados antes (.env.origem)"; ORIGEM="$PROJ/.env.origem"
else
  [ -n "$ACHADO" ] && c_ok "pacote de segredos encontrado: $ACHADO (Enter para usar)"
  ARQ=$(pergunta "Caminho do pacote de segredos — vazio para digitar as chaves" "$ACHADO")
  if [ -n "$ARQ" ]; then
    [ -f "$ARQ" ] || para "arquivo $ARQ não encontrado"
    T=$(mktemp -d)                            # pasta temporária só do root; apagada no fim desta etapa
    if [[ "$ARQ" == *.enc ]]; then
      command -v openssl >/dev/null || para "falta o openssl para abrir o pacote cifrado (apt-get install -y openssl)"
      SENHA_PACOTE=$(segredo "Senha do pacote (a que você escolheu no console)"); export SENHA_PACOTE
      openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -in "$ARQ" -out "$T/pacote.tar.gz" -pass env:SENHA_PACOTE 2>/dev/null \
        || { unset SENHA_PACOTE; rm -rf "$T"; para "senha do pacote incorreta ou arquivo corrompido"; }
      unset SENHA_PACOTE
      tar -xzf "$T/pacote.tar.gz" -C "$T" || para "pacote de segredos ilegível"; rm -f "$T/pacote.tar.gz"
    else
      tar -xzf "$ARQ" -C "$T" || para "pacote de segredos ilegível"
    fi
    [ -f "$T/env-origem" ] || para "pacote sem env-origem (gere de novo no console)"
    [ -f "$PROJ/.env.origem" ] && cp -p "$PROJ/.env.origem" "$PROJ/.env.origem.anterior-$(date +%Y%m%d%H%M%S)"
    install -m 600 "$T/env-origem" "$PROJ/.env.origem"; ORIGEM="$PROJ/.env.origem"
    if [ -d "$T/segredos" ]; then                # certificado do Diário e afins
      mkdir -p "$PROJ/segredos"; cp -a "$T/segredos/." "$PROJ/segredos/"; chmod -R go-rwx "$PROJ/segredos"
      c_ok "pasta segredos/ (certificado do Diário etc.) copiada"
    fi
    rm -rf "$T"
    c_ok "segredos importados de $(basename "$ARQ") — apague o arquivo quando terminar: rm $ARQ"
  else
    c_av "sem pacote: digite as chaves da VPS da gestão"
    { for k in SECRET_KEY TOTP_CHAVE CPF_HMAC_CHAVE CHAVE_CREDENCIAIS; do v=$(segredo "$k"); [ -n "$v" ] && echo "$k=$v"; done; } > "$PROJ/.env.origem"
    chmod 600 "$PROJ/.env.origem"; ORIGEM="$PROJ/.env.origem"
  fi
fi
for k in SECRET_KEY TOTP_CHAVE CPF_HMAC_CHAVE CHAVE_CREDENCIAIS; do   # confere só se existem; valores nunca aparecem
  grep -qE "^$k=.+" "$ORIGEM" && c_ok "$k presente" || c_av "$k ausente (sem ela: $( [ $k = SECRET_KEY ] && echo 'NÃO prossiga' || echo 'a função correspondente fica desligada'))"
done
grep -qE "^SECRET_KEY=.+" "$ORIGEM" || para "SECRET_KEY é obrigatória (a mesma da gestão)"
# o pacote é do nó desta instância? (o console grava a instância do nó no pacote)
P_INST=$(grep -E "^INSTANCIA=" "$ORIGEM" 2>/dev/null | tail -1 | cut -d= -f2- || true)
if grep -qE "^INSTANCIA=" "$ORIGEM" 2>/dev/null && [ "$P_INST" != "$INST" ]; then
  para "este pacote é do nó da instância \"${P_INST:-padrão}\" (pasta /opt/portal_web${P_INST:+-$P_INST}), não desta pasta ($PROJ)"
fi

# =====================================================================================================================
#  6. Dados do nó. Se o pacote veio do console, endereço da gestão, nome, token e chave pública já vêm preenchidos
#     (basta Enter). O IP público é descoberto pela rota de saída; confira no painel do provedor.
# =====================================================================================================================
etapa 6 "Configuração do nó"
org_val() { grep -E "^$1=" "$ORIGEM" 2>/dev/null | tail -1 | cut -d= -f2- || true; }  # valor vindo do pacote
# Endereço da gestão: pacote → .env anterior → https:// + domínio da gestão
DG=$(org_val DOMINIO_GESTAO)
PADRAO=$(org_val GESTAO_URL); [ -n "$PADRAO" ] || PADRAO=$(env_val GESTAO_URL); [ -n "$PADRAO" ] || { [ -n "$DG" ] && PADRAO="https://$DG"; } || true
GESTAO_URL=$(pergunta "Endereço da gestão" "$PADRAO")
[[ "$GESTAO_URL" =~ ^https://[a-z0-9.-]+$ ]] || para "endereço da gestão inválido (ex.: https://gestao.dominio.tld)"
# Nome do nó: o mesmo cadastrado no console
PADRAO=$(org_val NO_NOME); [ -n "$PADRAO" ] || PADRAO=$(env_val NO_NOME)
NO_NOME=$(pergunta "Nome do nó (o mesmo cadastrado no console)" "$PADRAO")
[[ "$NO_NOME" =~ ^[a-z0-9][a-z0-9.-]{1,60}$ ]] || para "nome do nó inválido"
# Token do nó: pacote → .env anterior (pergunta se troca) → digitar
NO_TOKEN=$(org_val NO_TOKEN)
if [ -n "$NO_TOKEN" ]; then
  c_ok "token do nó veio no pacote gerado pelo console (não é exibido)"
else
  NO_TOKEN=$(env_val NO_TOKEN)
  if [ -n "$NO_TOKEN" ] && ! confirma "Já existe um token do nó gravado. Trocar?"; then :; else NO_TOKEN=$(segredo "Token do nó (mostrado uma vez no console)"); fi
fi
[ ${#NO_TOKEN} -ge 30 ] || para "token do nó curto demais (copie de novo do console)"
# Chave pública da licença (Ed25519, 32 bytes em base64): confere a assinatura das licenças
PADRAO=$(org_val LICENCA_CHAVE_PUBLICA); [ -n "$PADRAO" ] || PADRAO=$(env_val LICENCA_CHAVE_PUBLICA)
PUB=$(pergunta "Chave pública da licença (LICENCA_CHAVE_PUBLICA, mostrada em Nós e licenças)" "$PADRAO")
python3 -c "import base64,sys; sys.exit(0 if len(base64.b64decode(sys.argv[1], validate=True)) == 32 else 1)" "$PUB" 2>/dev/null || para "chave pública inválida (copie de novo do console)"
# IP público: descoberto pela rota de saída
IP_DET=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -nE 's/.* src ([0-9.]+).*/\1/p')
PADRAO=$(env_val VPS_IP); [ -n "$PADRAO" ] || PADRAO="$IP_DET"
VPS_IP=$(pergunta "IP público deste nó (o DNS dos órgãos vai apontar para ele)" "$PADRAO")
[[ "$VPS_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || para "IP inválido"
# Validade da licença sem contato com a gestão
PADRAO=$(env_val LICENCA_VALIDADE_DIAS); [ -n "$PADRAO" ] || PADRAO=15
VALID=$(pergunta "Dias de validade da licença sem contato com a gestão" "$PADRAO")
[[ "$VALID" =~ ^[0-9]{1,3}$ ]] || para "validade inválida"

# =====================================================================================================================
#  7. nginx e certificados (Let's Encrypt). Dois modos:
#     proprio    portas 80/443 livres → sobe nginx + certbot do próprio nó (deploy/no/proxy/docker-compose.yml)
#     existente  portas ocupadas por outro sistema (VPS compartilhada) → usa o nginx que já está lá. Container,
#                pastas, rede e certbot são DESCOBERTOS pelo Docker (descobrir_nginx, acima); só o que não for
#                encontrado é perguntado.
# =====================================================================================================================
etapa 7 "Proxy (nginx ou Traefik) e certificados (Let's Encrypt)"
MODO=$(env_val PROXY_MODO)
if [ -z "$MODO" ]; then
  if [ "$COMPARTILHADA" = 1 ]; then
    echo "  As portas 80/443 já são usadas por outro sistema nesta VPS."
    if descobrir_traefik; then
      echo "  Quem atende essas portas é o Traefik (container $D_TRAEFIK — por exemplo, o do Dokploy)."
      echo "  [1] usar esse Traefik (recomendado: o portal só acrescenta as rotas dele)   [2] usar um nginx em contêiner   [3] parar aqui"
      case "$(pergunta "Escolha" "1")" in 1) MODO=traefik ;; 2) MODO=existente ;; *) para "nada foi alterado no proxy" ;; esac
    else
      echo "  [1] usar o nginx que já existe (como na VPS da gestão, que usa o nginx de outro projeto)   [2] parar aqui"
      [ "$(pergunta "Escolha" "1")" = "1" ] && MODO=existente || para "libere as portas 80/443 ou escolha usar o nginx existente"
    fi
  else MODO=proprio; fi
fi
TRAEFIK_C=""; T_HTTP=""; T_HTTPS=""; T_RESOLV=""
if [ "$MODO" = proprio ]; then
  NGINX_C=portal-nginx; CERTBOT_C=portal-certbot; REDE=portal-proxy
  CONF_DIR="$PROJ/deploy/no/proxy/conf.d"; CERTS_DIR=/var/lib/docker/volumes/portal-proxy_certs/_data
  mkdir -p "$CONF_DIR"
  install -m 644 "$PROJ/deploy/no/proxy/00-acme.conf" "$CONF_DIR/00-acme.conf"          # responde o desafio do Let's Encrypt
  instalar_inc "$CONF_DIR"      # trecho comum dos vhosts dos órgãos
  chmod 755 "$CONF_DIR"
  if confirma "Subir o nginx e o certbot próprios do nó (portas 80 e 443)?"; then
    rodar "Baixando e subindo nginx e certbot" bash -c "cd '$PROJ/deploy/no/proxy' && docker compose up -d" || para "nginx/certbot não subiram (veja $LOG)"
    docker exec "$NGINX_C" nginx -t >> "$LOG" 2>&1 && c_ok "configuração do nginx válida" || para "nginx -t falhou (veja $LOG)"
  else para "o nó precisa do nginx"; fi
elif [ "$MODO" = traefik ]; then
  # Traefik: o ativador grava SÓ o arquivo portal-orgaos.yml na pasta de rotas dinâmicas; o Traefik emite os certificados.
  # Nada do Traefik nem dos outros sistemas é alterado; para desfazer, basta apagar esse arquivo.
  TRAEFIK_C=$(env_val TRAEFIK_C); CONF_DIR=$(env_val CONF_DIR); REDE=$(env_val REDE_PROXY)
  T_HTTP=$(env_val TRAEFIK_ENTRADA_HTTP); T_HTTPS=$(env_val TRAEFIK_ENTRADA_HTTPS); T_RESOLV=$(env_val TRAEFIK_RESOLVEDOR)
  if [ -n "${D_TRAEFIK:-}" ] || descobrir_traefik; then
    TRAEFIK_C=${TRAEFIK_C:-$D_TRAEFIK}; CONF_DIR=${CONF_DIR:-$D_DIN}; REDE=${REDE:-$D_REDE}
    T_HTTP=${T_HTTP:-$D_HTTP}; T_HTTPS=${T_HTTPS:-$D_HTTPS}; T_RESOLV=${T_RESOLV:-$D_RESOLV}
  else c_av "não achei um container do Traefik; informe os dados abaixo"; fi
  echo "  Traefik encontrado nesta VPS:"
  printf '    %-34s %s\n' "container do Traefik:" "${TRAEFIK_C:-(não encontrado)}" "pasta de rotas dinâmicas (servidor):" "${CONF_DIR:-(não encontrada)}" \
    "rede docker:" "${REDE:-(não encontrada)}" "entrada da porta 80:" "${T_HTTP:-(não encontrada)}" "entrada da porta 443:" "${T_HTTPS:-(não encontrada)}" \
    "resolvedor de certificados:" "${T_RESOLV:-(não encontrado)}"
  if [ -n "$TRAEFIK_C" ] && [ -n "$CONF_DIR" ] && [ -n "$REDE" ] && [ -n "$T_HTTP" ] && [ -n "$T_HTTPS" ] && [ -n "$T_RESOLV" ] && confirma_s "Usar estes dados?"; then
    :
  else
    TRAEFIK_C=$(pergunta "Container do Traefik" "$TRAEFIK_C"); CONF_DIR=$(pergunta "Pasta de rotas dinâmicas do Traefik (no servidor)" "${CONF_DIR:-/etc/dokploy/traefik/dynamic}")
    REDE=$(pergunta "Rede docker do Traefik" "${REDE:-dokploy-network}"); T_HTTP=$(pergunta "Entrada da porta 80" "${T_HTTP:-web}")
    T_HTTPS=$(pergunta "Entrada da porta 443" "${T_HTTPS:-websecure}"); T_RESOLV=$(pergunta "Resolvedor de certificados" "${T_RESOLV:-letsencrypt}")
  fi
  for v in "$T_HTTP" "$T_HTTPS" "$T_RESOLV"; do [[ "$v" =~ ^[A-Za-z0-9_-]{1,40}$ ]] || para "nome inválido para o Traefik: $v"; done
  docker inspect "$TRAEFIK_C" >/dev/null 2>&1 || para "container $TRAEFIK_C não existe"
  [ -d "$CONF_DIR" ] || para "pasta $CONF_DIR não existe"
  docker network inspect "$REDE" >/dev/null 2>&1 || para "rede $REDE não existe"
  # rede overlay (Docker Swarm, como a do Dokploy) só aceita containers comuns se for "attachable"
  if [ "$(docker network inspect -f '{{.Driver}}' "$REDE" 2>/dev/null)" = overlay ] && [ "$(docker network inspect -f '{{.Attachable}}' "$REDE" 2>/dev/null)" != true ]; then
    para "a rede $REDE é overlay e não aceita containers de fora do Swarm (attachable=false)"
  fi
  [ "${D_WATCH:-}" = false ] && c_av "o Traefik está com watch: false — ele só lê rotas novas quando reinicia; ligue watch: true no provedor file"
  [ -e "$CONF_DIR/portal-orgaos$SUF.yml" ] && c_ok "portal-orgaos$SUF.yml já existe (instalação anterior): o ativador continua cuidando dele"
  NGINX_C=""; CERTBOT_C=""; CERTS_DIR=""
  c_ok "o portal vai usar o Traefik $TRAEFIK_C (rotas em $CONF_DIR/portal-orgaos$SUF.yml, criado só quando um domínio for publicado)"
else
  # Valores já gravados numa instalação anterior têm prioridade; o que faltar vem da descoberta.
  NGINX_C=$(env_val NGINX_C); CERTBOT_C=$(env_val CERTBOT_C); CONF_DIR=$(env_val CONF_DIR); CERTS_DIR=$(env_val PROXY_CERTS_DIR); CERTS_DIR=${CERTS_DIR:-$(env_val CERTS_DIR)}; REDE=$(env_val REDE_PROXY)  # CERTS_DIR: nome antigo
  if descobrir_nginx; then
    NGINX_C=${NGINX_C:-$D_NGINX}; CONF_DIR=${CONF_DIR:-$D_CONF}; CERTS_DIR=${CERTS_DIR:-$D_CERTS}; REDE=${REDE:-$D_REDE}; CERTBOT_C=${CERTBOT_C:-$D_CERTBOT}
  else
    c_av "não achei um nginx em contêiner publicando 80/443 (pode ser um nginx instalado direto no sistema)."
    c_av "o ativador precisa de um nginx e de um certbot em contêiner; informe-os abaixo."
  fi
  echo "  nginx encontrado nesta VPS:"
  printf '    %-26s %s\n' "container do nginx:" "${NGINX_C:-(não encontrado)}" "pasta conf.d no servidor:" "${CONF_DIR:-(não encontrada)}" \
    "pasta dos certificados:" "${CERTS_DIR:-(não encontrada)}" "rede docker:" "${REDE:-(não encontrada)}" "container do certbot:" "${CERTBOT_C:-(não encontrado)}"
  if [ -n "$NGINX_C" ] && [ -n "$CONF_DIR" ] && [ -n "$CERTS_DIR" ] && [ -n "$REDE" ] && [ -n "$CERTBOT_C" ] && confirma_s "Usar estes dados?"; then
    :
  else                                         # pergunta só o que falta (ou tudo, se recusou), com o encontrado como padrão
    NGINX_C=$(pergunta "Container do nginx" "$NGINX_C");      CERTBOT_C=$(pergunta "Container do certbot" "$CERTBOT_C")
    CONF_DIR=$(pergunta "Pasta conf.d do nginx (no servidor)" "$CONF_DIR"); CERTS_DIR=$(pergunta "Pasta dos certificados (letsencrypt, no servidor)" "$CERTS_DIR")
    REDE=$(pergunta "Rede docker do nginx" "$REDE")
  fi
  docker inspect "$NGINX_C" >/dev/null 2>&1 || para "container $NGINX_C não existe"
  docker inspect "$CERTBOT_C" >/dev/null 2>&1 || para "container $CERTBOT_C não existe"
  [ -d "$CONF_DIR" ] && [ -d "$CERTS_DIR" ] || para "pasta conf.d ou de certificados não existe"
  docker network inspect "$REDE" >/dev/null 2>&1 || para "rede $REDE não existe"
  instalar_inc "$CONF_DIR"
  c_ok "trecho comum dos portais copiado para $CONF_DIR (portal-comum$SUF.inc → $APP_ALIAS)"
  # O certbot grava o desafio em /var/www/certbot; o nginx precisa ler a MESMA pasta.
  W_CB=$(montagem "$CERTBOT_C" /var/www/certbot)
  if [ -n "$W_CB" ] && [ "$W_CB" = "$(montagem "$NGINX_C" /var/www/certbot)" ]; then
    c_ok "nginx e certbot compartilham a pasta do desafio do Let's Encrypt"
  else
    c_av "confira: o nginx existente precisa responder /.well-known/acme-challenge/ na porta 80 a partir da mesma pasta /var/www/certbot do certbot (modelo: deploy/no/proxy/00-acme.conf)"
  fi
fi

# =====================================================================================================================
#  .env do nó: segredos da gestão (menos o que não vale no nó) + dados das etapas 6 e 7.
#  A senha do banco do nó é gerada aqui na 1ª vez e mantida nas próximas. O .env anterior é guardado com data.
# =====================================================================================================================
PGP=$(env_val PG_PASSWORD); [ -n "$PGP" ] && [ "$(env_val PAPEL)" = no ] || PGP=$(openssl rand -hex 24)
NOVO=$(mktemp)
grep -vE '^(PAPEL|INSTANCIA|APP_ALIAS|NO_BANCO|GESTAO_URL|NO_TOKEN|NO_NOME|LICENCA_CHAVE_PUBLICA|LICENCA_VALIDADE_DIAS|VPS_IP|PG_PASSWORD|PG_HOST|COMPOSE_FILE|REDE_PROXY|PROXY_MODO|NGINX_C|CERTBOT_C|CONF_DIR|CERTS_DIR|PROXY_CERTS_DIR|TRAEFIK_C|TRAEFIK_ENTRADA_HTTP|TRAEFIK_ENTRADA_HTTPS|TRAEFIK_RESOLVEDOR|DOMINIO_PM|DOMINIO_CM|SENHA_INICIAL_ADMIN|SENHA_INICIAL_GESTOR)=' "$ORIGEM" > "$NOVO" || true
{ echo; echo "# ---- nó de portais (gerado por deploy/no/instalar.sh em $(date -Is)) ----"
  echo "PAPEL=no"; echo "INSTANCIA=$INST"; echo "APP_ALIAS=$APP_ALIAS"; echo "GESTAO_URL=$GESTAO_URL"; echo "NO_NOME=$NO_NOME"; echo "NO_TOKEN=$NO_TOKEN"; echo "LICENCA_CHAVE_PUBLICA=$PUB"
  echo "LICENCA_VALIDADE_DIAS=$VALID"; echo "VPS_IP=$VPS_IP"; echo "PG_PASSWORD=$PGP"; echo "PG_HOST=db"
  echo "COMPOSE_FILE=docker-compose.yml:deploy/no/docker-compose.no.yml"; echo "REDE_PROXY=$REDE"; echo "PROXY_MODO=$MODO"
  echo "NGINX_C=$NGINX_C"; echo "CERTBOT_C=$CERTBOT_C"; echo "CONF_DIR=$CONF_DIR"; echo "PROXY_CERTS_DIR=$CERTS_DIR"  # não "CERTS_DIR": o app lê o .env e esse nome era o dos certificados do INEP
  if [ "$MODO" = traefik ]; then echo "TRAEFIK_C=$TRAEFIK_C"; echo "TRAEFIK_ENTRADA_HTTP=$T_HTTP"; echo "TRAEFIK_ENTRADA_HTTPS=$T_HTTPS"; echo "TRAEFIK_RESOLVEDOR=$T_RESOLV"; fi
} >> "$NOVO"
grep -qE '^PG_USER=.+' "$NOVO" || echo "PG_USER=portal" >> "$NOVO"
[ -f "$PROJ/.env" ] && cp -p "$PROJ/.env" "$PROJ/.env.anterior-$(date +%Y%m%d%H%M%S)"
install -m 600 "$NOVO" "$PROJ/.env"; rm -f "$NOVO"
unset NO_TOKEN PGP
c_ok ".env do nó gravado (permissão 600; valores não exibidos)"

# =====================================================================================================================
#  8. Portal: gera a imagem, sobe o banco, espera ficar pronto, sobe o app, prepara o banco local e sobe o worker.
# =====================================================================================================================
etapa 8 "Portal: banco, app e worker"
app_responde() { docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=5)"; }
if confirma "Gerar a imagem e subir banco, app e worker (com os limites de memória do projeto)?"; then
  cd "$PROJ"
  rodar "Gerando a imagem do portal (a primeira vez leva de 3 a 10 minutos)" docker compose build app worker || para "falha ao gerar a imagem (veja $LOG)"
  rodar "Subindo o banco" docker compose up -d db || para "o banco não subiu (veja $LOG)"
  esperar "Banco pronto" 120 docker compose exec -T db pg_isready -q || para "o banco não ficou pronto em 2 minutos (veja: docker compose logs db)"
  rodar "Subindo o app" docker compose up -d app || para "o app não subiu (veja $LOG)"
  esperar "App respondendo" 120 app_responde || para "o app não respondeu em 2 minutos (veja: docker compose logs app)"
  rodar "Preparando o banco local do nó" docker compose exec -T app python -m app.provision atualizar || para "provision falhou (veja $LOG)"
  rodar "Subindo o worker" docker compose up -d worker || para "o worker não subiu (veja $LOG)"
else para "o nó precisa do portal no ar"; fi

# =====================================================================================================================
#  9. Ativador (systemd, a cada minuto: cria bancos e publica domínios pedidos pela gestão) e backup diário (cron 02h00).
#     O ativador recebe por um "drop-in" do systemd as pastas e containers do nginx escolhidos na etapa 7.
# =====================================================================================================================
etapa 9 "Ativador de domínios e backup diário"
if confirma "Instalar o ativador (a cada minuto) e o backup diário (02h00, guarda 14 dias)?"; then
  for u in service timer; do   # unidades da instância: portal-ativador[-INST].service/.timer, apontando para o ativador desta pasta
    sed -e "s#/opt/portal_web/deploy/ativador.sh#$PROJ/deploy/ativador.sh#" -e "s#Ativador dos Portais#Ativador dos Portais${INST:+ (instância $INST)}#;s#o ativador dos Portais#o ativador dos Portais${INST:+ (instância $INST)}#" \
        -e "s#^Unit=.*#Unit=$ATIV.service#" "$PROJ/deploy/systemd/portal-ativador.$u" > "/etc/systemd/system/$ATIV.$u"; chmod 644 "/etc/systemd/system/$ATIV.$u"
  done
  mkdir -p "/etc/systemd/system/$ATIV.service.d"
  { printf '[Service]\nEnvironment=PROJ=%s\nEnvironment=CONF_DIR=%s\nEnvironment=CERTS_DIR=%s\nEnvironment=NGINX_C=%s\nEnvironment=CERTBOT_C=%s\nEnvironment=PROXY_MODO=%s\nEnvironment=INSTANCIA=%s\n' \
      "$PROJ" "$CONF_DIR" "$CERTS_DIR" "$NGINX_C" "$CERTBOT_C" "$MODO" "$INST"
    [ "$MODO" = traefik ] && printf 'Environment=TRAEFIK_ENTRADA_HTTP=%s\nEnvironment=TRAEFIK_ENTRADA_HTTPS=%s\nEnvironment=TRAEFIK_RESOLVEDOR=%s\n' "$T_HTTP" "$T_HTTPS" "$T_RESOLV"
  } > "/etc/systemd/system/$ATIV.service.d/no.conf"
  chmod 644 "/etc/systemd/system/$ATIV.service.d/no.conf"
  systemctl daemon-reload && systemctl enable --now "$ATIV.timer" >> "$LOG" 2>&1 && c_ok "ativador ligado ($ATIV)"
  # 02h00 de Brasília: se o servidor estiver em UTC (comum em VPS compartilhada, cujo fuso não mudamos), 05h00 UTC
  HORA=2; case "$(timedatectl show -p Timezone --value 2>/dev/null)" in UTC|Etc/UTC|Etc/UCT|UCT|Universal|Zulu) HORA=5 ;; esac
  [ -n "$INST" ] && MIN=20 || MIN=0   # instância: 20 min depois, para os backups não rodarem juntos
  echo "$MIN $HORA * * * root $PROJ/deploy/backup.sh >> $PROJ/backups/backup.log 2>&1" > "/etc/cron.d/portal-backup$SUF"; chmod 644 "/etc/cron.d/portal-backup$SUF"
  mkdir -p "$PROJ/backups"; c_ok "backup diário agendado às 02h00 de Brasília (copie $PROJ/backups para fora da VPS — combine o destino)"
else c_av "etapa pulada: sem ativador, nenhum domínio é publicado"; fi

# =====================================================================================================================
#  10. Conferência com a gestão: busca as licenças e envia o primeiro relatório (o nó aparece no console).
# =====================================================================================================================
etapa 10 "Conferência com a gestão"
cd "$PROJ"
R=$(docker compose exec -T app python -m app.licenca puxar 2>&1 | tail -1) || true
[[ "$R" == *"aceitas"* ]] && c_ok "licenças: $R" || c_er "licenças: $R"
R=$(docker compose exec -T app python -m app.relatorio enviar 2>&1 | tail -1) || true
[[ "$R" == relatório\ entregue* ]] && c_ok "$R" || c_er "relatório: $R"
echo
echo "Pronto em $(tempo $((SECONDS - INICIO))). No console da gestão, em Nós e licenças, o nó $NO_NOME deve aparecer com IP $VPS_IP e o relatório de agora."
echo "Próximos passos (no console da gestão): hospedar órgãos neste nó; o nó cria cada banco em até 1 minuto e publica"
echo "o domínio de cada órgão quando você pedir (DNS do órgão apontando para $VPS_IP)."
echo "Para conferir depois sem mudar nada: bash deploy/no/instalar.sh --verificar"
