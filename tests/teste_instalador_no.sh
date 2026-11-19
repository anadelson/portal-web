#!/bin/bash
# Ensaio do deploy/no/instalar.sh num contêiner descartável: docker, apt, systemctl, ufw, timedatectl, ss e ip SIMULADOS
# (só registram a chamada). Respostas automáticas às perguntas. Valores de teste fictícios. Nada toca a VPS real.
# Uso (no host):  docker run --rm -v /opt/portal_web:/codigo:ro portal_web-app bash /codigo/tests/teste_instalador_no.sh
set -u
ERROS=0; checa() { if eval "$1"; then :; else echo "FALHOU: $2"; ERROS=$((ERROS + 1)); fi; }
P=/opt/portal_web; S=/tmp/stubs; mkdir -p "$S" /opt
# cópia SÓ do código (nunca o .env, segredos, backups, dados ou logs da VPS onde o teste roda)
mkdir -p "$P"
tar -C /codigo --exclude=./.env --exclude='./.env.*' --exclude=./segredos --exclude=./backups --exclude=./dados --exclude=./logs --exclude=./pacotes \
    --exclude=./deploy/no/proxy/conf.d --exclude='*/__pycache__' -cf - . | tar -C "$P" -xf -
checa '[ ! -e $P/.env ] && [ ! -e $P/segredos ] && [ ! -e $P/backups ]' 'cópia do teste sem .env, segredos nem backups'
mkdir -p /etc/systemd/system /etc/cron.d
# ---------- simulações ----------
for c in apt-get systemctl timedatectl; do printf '#!/bin/bash\necho "%s $*" >> /tmp/chamadas\n[ "$1" = show ] && echo America/Sao_Paulo\nexit 0\n' "$c" > "$S/$c"; done
printf '#!/bin/bash\necho "ufw $*" >> /tmp/chamadas\n[ "$1" = status ] && { [ -f /tmp/ufw-ativo ] && echo "Status: active" || echo "Status: inactive"; }\n[ "$1" = --force ] && touch /tmp/ufw-ativo\nexit 0\n' > "$S/ufw"
printf '#!/bin/bash\n[ -f /tmp/portas-ocupadas ] && echo "LISTEN 0 511 0.0.0.0:80 0.0.0.0:* users:((\\"outro-nginx\\",pid=1,fd=6))"\nexit 0\n' > "$S/ss"
printf '#!/bin/bash\necho "1.1.1.1 via 198.51.100.1 dev eth0 src 198.51.100.5 uid 0"\n' > "$S/ip"
# dpkg/apt-mark simulados: Docker "instalado" para conferir que ele fica segurado na atualização da VPS compartilhada
printf '#!/bin/bash\n[ "$1" = -s ] && case "$2" in docker-ce|containerd.io) exit 0 ;; esac\nexit 1\n' > "$S/dpkg"
printf '#!/bin/bash\necho "apt-mark $*" >> /tmp/chamadas\nexit 0\n' > "$S/apt-mark"
cat > "$S/docker" <<'EOF'
#!/bin/bash
echo "docker $*" >> /tmp/chamadas
if [ -f /tmp/traefik ]; then  # VPS com Dokploy: Traefik nas portas 80/443, rede overlay attachable
  case "$*" in
    "ps --filter"*|"ps --format"*) echo dokploy-traefik; exit 0 ;;
    *Config.Image*dokploy-traefik) echo traefik:v3.1.2; exit 0 ;;
    *Mounts*dokploy-traefik) printf '/etc/traefik/traefik.yml|/tmp/dk/traefik.yml\n/etc/dokploy/traefik/dynamic|/tmp/dk/dynamic\n/var/run/docker.sock|/var/run/docker.sock\n'; exit 0 ;;
    *Networks*dokploy-traefik) printf 'dokploy-network\n'; exit 0 ;;
    *Driver*) echo overlay; exit 0 ;;
    *Attachable*) echo true; exit 0 ;;
  esac
fi
case "$*" in
  *"app.tarefas env-instancia"*) cat /tmp/env-instancia; exit 0 ;;   # o app do nó entrega a configuração do nó novo (simulado)
  *Config.Env*) [ -f /tmp/gestao ] && printf 'PG_USER=portal\nPG_HOST=db\n'; exit 0 ;;   # container do portal na VPS da gestão (simulado; sem PAPEL = "tudo", como na gestão real)
  --version) echo "Docker version 27.0.0, build x" ;;
  "compose version"*) echo "2.29.0" ;;
  *"app.licenca puxar"*) echo "0 licença(s) aceitas" ;;
  *"app.relatorio enviar"*) echo "relatório entregue (0 ativação(ões) atualizada(s) na gestão)" ;;
  "ps --filter"*) if [ -f /tmp/no-proprio ]; then echo portal-nginx; else [ -f /tmp/portas-ocupadas ] && [ ! -f /tmp/sem-descoberta ] && echo outro-nginx; fi ;;
  "ps"*) if [ -f /tmp/no-proprio ]; then printf 'portal-nginx\nportal-certbot\nportal_web-app-1\n'; exit 0; fi; [ -f /tmp/portas-ocupadas ] && printf 'outro-nginx\noutro-certbot\n' ;;
  *Mounts*portal-nginx) printf '/etc/nginx/conf.d|/opt/portal_web/deploy/no/proxy/conf.d\n/etc/letsencrypt|/tmp/pc/certs\n/var/www/certbot|/tmp/pc/www\n' ;;
  *Mounts*portal-certbot) printf '/etc/letsencrypt|/tmp/pc/certs\n/var/www/certbot|/tmp/pc/www\n' ;;
  *Networks*portal-nginx) printf 'portal-proxy\n' ;;
  "ps"*) [ -f /tmp/portas-ocupadas ] && printf 'outro-nginx\noutro-certbot\n' ;;
  *Mounts*outro-nginx) printf '/etc/nginx/conf.d|/tmp/outro/conf.d\n/etc/letsencrypt|/tmp/outro/certs\n/var/www/certbot|/tmp/outro/www\n' ;;
  *Mounts*outro-certbot) printf '/etc/letsencrypt|/tmp/outro/certs\n/var/www/certbot|/tmp/outro/www\n' ;;
  *Networks*outro-nginx) printf 'outra-rede\n' ;;
  "inspect"*|"network inspect"*) [ -f /tmp/portas-ocupadas ] ;;
esac
exit 0
EOF
chmod +x "$S"/*; export PATH="$S:$PATH"
# ---------- pacote de segredos fictício (como o exportar_segredos.sh gera) ----------
T=$(mktemp -d); mkdir -p "$T/segredos/a1"
printf 'SECRET_KEY=segredo-teste-AAAA\nTOTP_CHAVE=totp-teste-BBBB\nCPF_HMAC_CHAVE=hmac-teste-CCCC\nCHAVE_CREDENCIAIS=cred-teste-DDDD\nPG_USER=portal\nPG_PASSWORD=senha-da-gestao-EEEE\nDOMINIO_GESTAO=gestao.exemplo.test\nDOMINIO_PM=pm.exemplo.test\nDIARIO_MODO=teste\n' > "$T/env-origem"
echo certificado-ficticio > "$T/segredos/a1/certificado.p12"
tar -czf /root/segredos-no-teste.tar.gz -C "$T" .
TOKEN=tokenFicticioDoNo-0123456789abcdefghijklmnop
PUB=$(python3 -c "import base64; print(base64.b64encode(bytes(range(32))).decode())")

# ---------- trava (18/11/2026): na VPS da GESTÃO o instalador para sem mexer em nada ----------
printf 'PAPEL=tudo\nPG_PASSWORD=senha-da-gestao-ZZZZ\nDOMINIO_PM=pm.exemplo.test\n' > "$P/.env"; chmod 600 "$P/.env"; H0=$(sha256sum "$P/.env"); : > /tmp/chamadas
SAIDA=$(printf 's\ns\n\n\nno1.exemplo.test\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "esta VPS já roda a GESTÃO" && [ "$(sha256sum $P/.env)" = "$H0" ] && [ ! -f $P/.env.origem ]' "gestão (.env com PAPEL=tudo): para sem alterar o .env (rc=$RC)"
checa '! grep -qE "compose (up|build)|apt-get|ufw --force" /tmp/chamadas && ! ls $P/.env.anterior-* >/dev/null 2>&1' 'gestão: nenhuma mudança (sem build, subida, atualização ou firewall)'
printf 'PAPEL=\n' > "$P/.env"; SAIDA=$(printf 's\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "esta VPS já roda a GESTÃO"' 'gestão (PAPEL vazio): para'
rm -f "$P/.env"; touch /tmp/gestao
SAIDA=$(printf 's\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "portal rodando como GESTÃO" && [ ! -f $P/.env ]' "gestão sem .env mas com o container do portal em papel tudo: para (rc=$RC)"
rm -f /tmp/gestao "$P/logs/instalar-no.log"; : > /tmp/chamadas

# ---------- 1ª instalação: portas livres, nginx próprio ----------
# respostas: atualizar(s) · firewall(s) · pacote(enter=padrão) · gestão(enter) · nome · token · chave pública · IP(enter) · validade(enter) · nginx(s) · portal(s) · ativador(s)
SAIDA=$(printf 's\ns\n\n\nno1.exemplo.test\n%s\n%s\n\n\ns\ns\ns\n' "$TOKEN" "$PUB" | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "instalação termina sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
E="$P/.env"
checa '[ "$(stat -c %a $E)" = 600 ] && [ "$(stat -c %a $P/.env.origem)" = 600 ]' '.env e .env.origem com permissão 600'
for l in PAPEL=no GESTAO_URL=https://gestao.exemplo.test NO_NOME=no1.exemplo.test "NO_TOKEN=$TOKEN" "LICENCA_CHAVE_PUBLICA=$PUB" LICENCA_VALIDADE_DIAS=15 \
         VPS_IP=198.51.100.5 PG_HOST=db COMPOSE_FILE=docker-compose.yml:deploy/no/docker-compose.no.yml REDE_PROXY=portal-proxy PROXY_MODO=proprio \
         SECRET_KEY=segredo-teste-AAAA TOTP_CHAVE=totp-teste-BBBB CPF_HMAC_CHAVE=hmac-teste-CCCC CHAVE_CREDENCIAIS=cred-teste-DDDD DIARIO_MODO=teste PG_USER=portal; do
  checa "grep -qxF '$l' $E" ".env tem $l"
done
checa '! grep -q "senha-da-gestao-EEEE" $E && grep -qE "^PG_PASSWORD=[0-9a-f]{48}$" $E' 'senha do banco do nó é nova (não é a da gestão)'
checa '! grep -qE "^(DOMINIO_PM|SENHA_INICIAL_ADMIN)=" $E' 'variáveis do piloto/gestão que não valem no nó ficam de fora'
checa '[ "$(grep -c "^PAPEL=" $E)" = 1 ] && [ "$(grep -c "^SECRET_KEY=" $E)" = 1 ]' 'sem chave repetida no .env'
for s in segredo-teste-AAAA totp-teste-BBBB hmac-teste-CCCC cred-teste-DDDD "$TOKEN" senha-da-gestao-EEEE "$(grep ^PG_PASSWORD= $E | cut -d= -f2)"; do
  checa "! echo \"\$SAIDA\" | grep -qF '$s' && ! grep -qF '$s' $P/logs/instalar-no.log" "segredo não aparece na tela nem no log (${s:0:6}…)"
done
checa '[ -f $P/segredos/a1/certificado.p12 ] && [ "$(stat -c %a $P/segredos)" = 700 ]' 'pasta segredos/ copiada, só root lê'
checa '[ -f $P/deploy/no/proxy/conf.d/00-acme.conf ] && cmp -s $P/deploy/nginx/portal-comum.inc $P/deploy/no/proxy/conf.d/portal-comum.inc' 'conf.d do nginx do nó com o desafio do Let'"'"'s Encrypt e o trecho comum'
checa 'grep -q "Environment=CONF_DIR=$P/deploy/no/proxy/conf.d" /etc/systemd/system/portal-ativador.service.d/no.conf && grep -q "NGINX_C=portal-nginx" /etc/systemd/system/portal-ativador.service.d/no.conf' 'ativador configurado para o nginx do nó'
checa 'grep -q "deploy/backup.sh" /etc/cron.d/portal-backup' 'backup diário agendado'
checa 'grep -q "systemctl enable --now portal-ativador.timer" /tmp/chamadas && grep -q "docker compose up -d worker" /tmp/chamadas && grep -q "app.provision atualizar" /tmp/chamadas' 'sobe portal, provision e ativador'
checa 'grep -q "ufw --force enable" /tmp/chamadas' 'firewall ligado'
checa 'echo "$SAIDA" | grep -q "licenças: 0 licença(s) aceitas" && echo "$SAIDA" | grep -q "relatório entregue"' 'conferência com a gestão no fim'
checa 'echo "$SAIDA" | grep -q "Pronto em .*No console da gestão"' 'mensagem final com os próximos passos'
PG1=$(grep ^PG_PASSWORD= $E)

# ---------- 2ª rodada: mantém senha do banco e segredos; não pede o token de novo ----------
: > /tmp/chamadas
# respostas: atualizar(n) · firewall já ativo · segredos já importados · gestão(enter) · nome(enter) · trocar token?(n) · chave(enter) · IP(enter) · validade(enter) · nginx(s) · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\n\nn\n\n\n\ns\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "segunda rodada sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
checa '[ "$(grep ^PG_PASSWORD= $E)" = "$PG1" ] && grep -qxF "NO_TOKEN=$TOKEN" $E' 'segunda rodada mantém a senha do banco e o token'
checa 'ls $P/.env.anterior-* >/dev/null 2>&1' '.env anterior guardado antes de regravar'
checa 'echo "$SAIDA" | grep -q "segredos da gestão já importados"' 'não pede o pacote de segredos de novo'

# ---------- VPS com outro sistema nas portas 80/443: usar o nginx existente ----------
touch /tmp/portas-ocupadas; rm -f "$E"; mkdir -p /tmp/outro/conf.d /tmp/outro/certs /tmp/outro/www
# o instalador DESCOBRE container, pastas, rede e certbot pelo Docker; basta confirmar (Enter)
# respostas: atualizar(n) · gestão · nome · token · chave · IP · validade · escolha(1) · usar estes dados?(Enter) · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\nno2.exemplo.test\n%s\n%s\n\n\n1\n\ns\ns\n' "$TOKEN" "$PUB" | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "VPS compartilhada: instalação sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
checa 'echo "$SAIDA" | grep -q "já são usadas por outro sistema"' 'detecta as portas ocupadas'
checa 'echo "$SAIDA" | grep -q "pasta conf.d no servidor: *.tmp.outro.conf.d" && echo "$SAIDA" | grep -q "container do certbot: *outro-certbot"' 'mostra o nginx descoberto (pastas e certbot)'
checa 'grep -qxF "PROXY_MODO=existente" $E && grep -qxF "REDE_PROXY=outra-rede" $E && grep -qxF "NGINX_C=outro-nginx" $E && grep -qxF "CERTBOT_C=outro-certbot" $E && grep -qxF "CONF_DIR=/tmp/outro/conf.d" $E && grep -qxF "PROXY_CERTS_DIR=/tmp/outro/certs" $E && ! grep -q "^CERTS_DIR=" $E' 'usa o nginx existente descoberto (container, certbot, pastas e rede)'
checa 'echo "$SAIDA" | grep -q "compartilham a pasta do desafio"' 'confere a pasta do desafio do Let'"'"'s Encrypt entre nginx e certbot'
checa '[ -f /tmp/outro/conf.d/portal-comum.inc ] && ! grep -q "up -d" <(grep "deploy/no/proxy" /tmp/chamadas)' 'instala só o trecho comum no nginx existente, sem subir outro nginx'
# nginx fora do Docker (nada descoberto): pergunta os dados um a um
rm -f "$E"; touch /tmp/sem-descoberta
# respostas: atualizar(n) · gestão · nome · token · chave · IP · validade · escolha(1) · container nginx · certbot · conf.d · certs · rede · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\nno2.exemplo.test\n%s\n%s\n\n\n1\noutro-nginx\noutro-certbot\n/tmp/outro/conf.d\n/tmp/outro/certs\noutra-rede\ns\ns\n' "$TOKEN" "$PUB" | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ] && echo "$SAIDA" | grep -q "não achei um nginx em contêiner" && grep -qxF "CONF_DIR=/tmp/outro/conf.d" $E' 'sem descoberta: pergunta e grava os dados digitados'
rm -f /tmp/sem-descoberta

# ---------- pacote gerado pelo console: cifrado (openssl), já com o token do nó, o endereço da gestão e a chave ----------
rm -f /tmp/portas-ocupadas "$E" "$P/.env.origem" /root/segredos-no-teste.tar.gz; rm -rf "$P/segredos"
T2=$(mktemp -d); mkdir -p "$T2/segredos/a1"; echo certificado-ficticio > "$T2/segredos/a1/certificado.p12"
printf 'SECRET_KEY=segredo-teste-AAAA\nTOTP_CHAVE=totp-teste-BBBB\nCPF_HMAC_CHAVE=hmac-teste-CCCC\nCHAVE_CREDENCIAIS=cred-teste-DDDD\nPG_USER=portal\nDOMINIO_GESTAO=gestao.exemplo.test\nGESTAO_URL=https://gestao.exemplo.test\nNO_NOME=no3.exemplo.test\nNO_TOKEN=%s\nLICENCA_CHAVE_PUBLICA=%s\n' "$TOKEN" "$PUB" > "$T2/env-origem"
tar -czf "$T2/p.tgz" -C "$T2" env-origem segredos
SP='senha-do-pacote-teste-123' openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt -in "$T2/p.tgz" -out /root/segredos-no.tar.gz.enc -pass env:SP
# senha do pacote errada: para sem gravar nada
SAIDA=$(printf 'n\n\nsenha-errada-qualquer\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "senha do pacote incorreta" && [ ! -f $P/.env.origem ] && [ ! -f $E ]' 'pacote do console com senha errada: para sem gravar'
# respostas: atualizar(n) · pacote(enter = o .enc mais novo) · senha do pacote · gestão(enter) · nome(enter) · [token não é perguntado] · chave(enter) · IP(enter) · validade(enter) · nginx(s) · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\nsenha-do-pacote-teste-123\n\n\n\n\n\ns\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "pacote do console: instalação sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
checa 'echo "$SAIDA" | grep -q "token do nó veio no pacote" && grep -qxF "NO_TOKEN=$TOKEN" $E && grep -qxF "NO_NOME=no3.exemplo.test" $E && grep -qxF "GESTAO_URL=https://gestao.exemplo.test" $E && grep -qxF "LICENCA_CHAVE_PUBLICA=$PUB" $E' 'instalador preenchido pelo pacote (token, nó, gestão e chave)'
checa '[ -f $P/segredos/a1/certificado.p12 ] && grep -qxF "SECRET_KEY=segredo-teste-AAAA" $E' 'segredos do pacote cifrado importados'
checa '! echo "$SAIDA" | grep -qF "senha-do-pacote-teste" && ! grep -qF "senha-do-pacote-teste" $P/logs/instalar-no.log && ! echo "$SAIDA" | grep -qF "$TOKEN"' 'senha do pacote e token fora da tela e do log'
rm -rf "$T2" /root/segredos-no.tar.gz.enc

# ---------- reinstalação com pacote NOVO do console (correção de 18/11/2026) ----------
# Antes, com o .env.origem da instalação anterior, o instalador ignorava o pacote novo e perdia o token e o nome novos.
pacote_novo() {  # $1 = nome do nó, $2 = token (vazio = pacote sem token novo); arquivo com data no futuro = mais novo que o já importado
  local T3; T3=$(mktemp -d); mkdir -p "$T3/segredos/a1"; echo certificado-ficticio > "$T3/segredos/a1/certificado.p12"
  { printf 'SECRET_KEY=segredo-teste-AAAA\nTOTP_CHAVE=totp-teste-BBBB\nCPF_HMAC_CHAVE=hmac-teste-CCCC\nCHAVE_CREDENCIAIS=cred-teste-DDDD\nPG_USER=portal\nDOMINIO_GESTAO=gestao.exemplo.test\n'
    printf 'GESTAO_URL=https://gestao.exemplo.test\nNO_NOME=%s\nLICENCA_CHAVE_PUBLICA=%s\n' "$1" "$PUB"; [ -n "$2" ] && printf 'NO_TOKEN=%s\n' "$2"; } > "$T3/env-origem"
  tar -czf "$T3/p.tgz" -C "$T3" env-origem segredos
  SP='senha-do-pacote-teste-123' openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt -in "$T3/p.tgz" -out /root/segredos-no.tar.gz.enc -pass env:SP
  touch -d "@$(( $(date +%s) + ${3:-60} ))" /root/segredos-no.tar.gz.enc; rm -rf "$T3"
}
TOKEN2=tokenNovoDoConsole-ZYXWVUTSRQPONMLKJIHGFEDCBA9876
pacote_novo no3.exemplo.test "$TOKEN2"
# respostas: atualizar(n) · usar o pacote novo?(Enter=S) · caminho(Enter) · senha · gestão · nome · [token vem do pacote] · chave · IP · validade · nginx(s) · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\n\nsenha-do-pacote-teste-123\n\n\n\n\n\ns\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ] && echo "$SAIDA" | grep -q "pacote de segredos mais novo que o já importado"' "reinstalação: oferece o pacote novo (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
checa 'grep -qxF "NO_TOKEN=$TOKEN2" $E && grep -qxF "NO_NOME=no3.exemplo.test" $E && [ "$(grep -c "^NO_TOKEN=" $E)" = 1 ]' 'reinstalação: token novo do pacote no .env (não o antigo)'
checa 'ls $P/.env.origem.anterior-* >/dev/null 2>&1' 'reinstalação: .env.origem anterior guardado'
# pacote novo SEM token novo: o nome vem do pacote e o token gravado no nó é mantido
pacote_novo no3.exemplo.test "" 120
# respostas: atualizar(n) · usar o pacote novo?(Enter) · caminho(Enter) · senha · gestão · nome · trocar o token?(Enter=não) · chave · IP · validade · nginx(s) · portal(s) · ativador(s)
SAIDA=$(printf 'n\n\n\nsenha-do-pacote-teste-123\n\n\n\n\n\n\ns\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ] && grep -qxF "NO_NOME=no3.exemplo.test" $E && grep -qxF "NO_TOKEN=$TOKEN2" $E' "pacote sem token novo: nome do pacote e token mantido (rc=$RC)"
# recusar o pacote novo: segue com o já importado
pacote_novo no3.exemplo.test "" 180
SAIDA=$(printf 'n\nn\n\n\n\n\n\n\ns\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ] && echo "$SAIDA" | grep -q "segredos da gestão já importados" && grep -qxF "NO_NOME=no3.exemplo.test" $E' "pacote novo recusado: mantém o importado (rc=$RC)"
# trava (19/11/2026): pacote de OUTRO nó na pasta deste nó — o caso real: o 2º nó instalado por cima do 1º. Para sem mexer em nada.
H2=$(sha256sum "$E" "$P/.env.origem" | sha256sum); : > /tmp/chamadas
pacote_novo outro-no.exemplo.test tokenDeOutroNo-0123456789abcdefghijklmnopq 240
SAIDA=$(printf 'n\n\n\nsenha-do-pacote-teste-123\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "já é do nó no3.exemplo.test, e o pacote é do nó outro-no.exemplo.test" && echo "$SAIDA" | grep -q "preencha a INSTÂNCIA"' "pacote de outro nó: para e explica o que fazer (rc=$RC)"
checa '[ "$(sha256sum "$E" "$P/.env.origem" | sha256sum)" = "$H2" ] && ! grep -qE "compose (up|build)" /tmp/chamadas' 'pacote de outro nó: .env e segredos intactos, nada subido'
checa 'echo "$SAIDA" | grep -q "TIPO: ATUALIZAÇÃO do nó no3.exemplo.test" && echo "$SAIDA" | grep -q "PASTA DESTE NÓ: /opt/portal_web"' 'resumo inicial: pasta e tipo (atualização) em linguagem simples'
checa 'grep -qxF "NO_PASTA=/opt/portal_web" $E' '.env registra a pasta do nó (vai para a gestão no relatório)'
rm -f /root/segredos-no.tar.gz.enc
# as recusas abaixo testam o token digitado: tira do pacote importado o que veio do console
grep -vE '^(NO_TOKEN|NO_NOME|GESTAO_URL|LICENCA_CHAVE_PUBLICA)=' "$P/.env.origem" > /tmp/origem && install -m 600 /tmp/origem "$P/.env.origem"

# ---------- recusas ----------
rm -f /tmp/portas-ocupadas "$E"
SAIDA=$(printf 'n\n\nno1.exemplo.test\ncurto\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "token do nó curto demais" && [ ! -f $E ]' 'token inválido: para sem gravar o .env'
SAIDA=$(printf 'n\n\nno1.exemplo.test\n%s\nnao-e-chave\n' "$TOKEN" | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "chave pública inválida"' 'chave pública inválida: para'

# ---------- VPS com Dokploy (Traefik nas portas 80/443): usa o Traefik, sem mexer no que já está no ar ----------
rm -f "$E" /tmp/ufw-ativo; touch /tmp/portas-ocupadas /tmp/traefik; : > /tmp/chamadas
mkdir -p /tmp/dk/dynamic; echo '# rota de outro sistema' > /tmp/dk/dynamic/app-de-outro.yml
cat > /tmp/dk/traefik.yml <<'YML'
providers:
  swarm:
    exposedByDefault: false
    watch: true
  docker:
    exposedByDefault: false
  file:
    directory: /etc/dokploy/traefik/dynamic
    watch: true
entryPoints:
  web:
    address: :80
  websecure:
    address: :443
    http3:
      advertisedPort: 443
    http:
      tls:
        certResolver: letsencrypt
api:
  insecure: true
certificatesResolvers:
  letsencrypt:
    acme:
      email: exemplo@exemplo.test
      storage: /etc/dokploy/traefik/dynamic/acme.json
      httpChallenge:
        entryPoint: web
YML
# respostas: atualizar(Enter=pula) · firewall(Enter=pula) · gestão(Enter) · nome · token · chave · IP · validade · escolha(Enter=Traefik) · usar estes dados?(Enter) · portal(s) · ativador(s)
SAIDA=$(printf '\n\n\nno4.exemplo.test\n%s\n%s\n\n\n\n\ns\ns\n' "$TOKEN" "$PUB" | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "Dokploy: instalação sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
checa 'echo "$SAIDA" | grep -q "VPS COMPARTILHADA" && echo "$SAIDA" | grep -q "Quem atende essas portas é o Traefik (container dokploy-traefik"' 'Dokploy: avisa VPS compartilhada e acha o Traefik'
checa '! grep -q "apt-get upgrade" /tmp/chamadas && ! grep -q "ufw --force enable" /tmp/chamadas && ! grep -q "set-timezone" /tmp/chamadas' 'Dokploy: Enter pula atualização e firewall; fuso não muda'
for l in PROXY_MODO=traefik CONF_DIR=/tmp/dk/dynamic REDE_PROXY=dokploy-network TRAEFIK_C=dokploy-traefik TRAEFIK_ENTRADA_HTTP=web TRAEFIK_ENTRADA_HTTPS=websecure TRAEFIK_RESOLVEDOR=letsencrypt; do
  checa "grep -qxF '$l' $E" "Dokploy: .env tem $l (descoberto)"
done
checa 'grep -q "Environment=PROXY_MODO=traefik" /etc/systemd/system/portal-ativador.service.d/no.conf && grep -q "Environment=TRAEFIK_RESOLVEDOR=letsencrypt" /etc/systemd/system/portal-ativador.service.d/no.conf' 'Dokploy: ativador configurado para o Traefik'
checa '! grep -q "^CERTS_DIR=" $E' 'Dokploy: .env sem CERTS_DIR (o app usa esse nome para os certificados do INEP)'
checa '[ "$(ls -A /tmp/dk/dynamic)" = app-de-outro.yml ] && ! grep -q "deploy/no/proxy" /tmp/chamadas' 'Dokploy: nada gravado na pasta do Traefik e nenhum nginx próprio subido'
checa '! grep -qE "docker (restart|stop|rm)|systemctl restart docker" /tmp/chamadas' 'Dokploy: nenhum container ou o Docker reiniciado'
# 2ª rodada pedindo a atualização: Docker segurado e solto no fim, fuso mantido
: > /tmp/chamadas
SAIDA=$(printf 's\n\n\n\nn\n\n\n\n\ns\ns\n' | bash "$P/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ] && grep -q "apt-mark hold  *docker-ce containerd.io" /tmp/chamadas && grep -q "apt-mark unhold  *docker-ce containerd.io" /tmp/chamadas' "Dokploy: atualização pedida segura e solta o Docker (rc=$RC)"
checa 'grep -q "apt-get upgrade" /tmp/chamadas && ! grep -q "set-timezone" /tmp/chamadas && echo "$SAIDA" | grep -q "fuso do servidor mantido"' 'Dokploy: atualização sem trocar o fuso do servidor'
rm -f /tmp/traefik /tmp/portas-ocupadas

# ---------- segundo nó na MESMA VPS: instância "camara" em /opt/portal_web-camara (18/11/2026) ----------
# O primeiro nó (/opt/portal_web) tem nginx próprio (portal-nginx); a instância usa esse nginx e não mexe em nada do primeiro.
PC=/opt/portal_web-camara; mkdir -p "$PC"
tar -C /codigo --exclude=./.env --exclude='./.env.*' --exclude=./segredos --exclude=./backups --exclude=./dados --exclude=./logs --exclude=./pacotes \
    --exclude=./deploy/no/proxy/conf.d --exclude='*/__pycache__' -cf - . | tar -C "$PC" -xf -
printf 'PAPEL=no\nPROXY_MODO=proprio\nNGINX_C=portal-nginx\nCONF_DIR=%s/deploy/no/proxy/conf.d\nAPP_ALIAS=portal-web-app\n' "$P" > "$E"; chmod 600 "$E"
mkdir -p "$P/deploy/no/proxy/conf.d" /tmp/pc/certs /tmp/pc/www /etc/systemd/system/portal-ativador.service.d
echo '# do primeiro nó' > "$P/deploy/no/proxy/conf.d/portal-comum.inc"; echo '# primeiro nó' > /etc/systemd/system/portal-ativador.service.d/no.conf
echo '0 2 * * * root /opt/portal_web/deploy/backup.sh' > /etc/cron.d/portal-backup
H1=$(cat "$E" "$P/deploy/no/proxy/conf.d/portal-comum.inc" /etc/systemd/system/portal-ativador.service.d/no.conf /etc/cron.d/portal-backup | sha256sum)
touch /tmp/portas-ocupadas /tmp/no-proprio; rm -f /tmp/ufw-ativo; : > /tmp/chamadas
TOKEN3=tokenDoNoDaCamara-abcdefghijklmnopqrstuvwxyz0123
pac_inst() {  # $1 = INSTANCIA gravada no pacote
  local T4; T4=$(mktemp -d); mkdir -p "$T4/segredos"
  printf 'SECRET_KEY=segredo-teste-AAAA\nTOTP_CHAVE=totp-teste-BBBB\nCPF_HMAC_CHAVE=hmac-teste-CCCC\nCHAVE_CREDENCIAIS=cred-teste-DDDD\nPG_USER=portal\nDOMINIO_GESTAO=gestao.exemplo.test\nGESTAO_URL=https://gestao.exemplo.test\nNO_NOME=no-cm.exemplo.test\nNO_TOKEN=%s\nLICENCA_CHAVE_PUBLICA=%s\nINSTANCIA=%s\n' "$TOKEN3" "$PUB" "$1" > "$T4/env-origem"
  tar -czf "$T4/p.tgz" -C "$T4" env-origem segredos
  SP='senha-do-pacote-teste-123' openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt -in "$T4/p.tgz" -out /root/segredos-no@camara.tar.gz.enc -pass env:SP; rm -rf "$T4"
}
# pacote de OUTRA instância na pasta da camara: para sem gravar
pac_inst outra
SAIDA=$(printf '\n\n\nsenha-do-pacote-teste-123\n' | bash "$PC/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "este pacote é do nó da instância" && [ ! -f $PC/.env ]' "instância: pacote de outra instância recusado (rc=$RC)"
rm -f "$PC/.env.origem"; rm -rf "$PC/segredos"
pac_inst camara
# respostas: atualizar(Enter=pula) · firewall(Enter=pula) · pacote(Enter) · senha · gestão · nome · [token do pacote] · chave · IP · validade · nginx existente(1) · usar estes dados?(Enter) · portal(s) · ativador(s)
SAIDA=$(printf '\n\n\nsenha-do-pacote-teste-123\n\n\n\n\n\n1\n\ns\ns\n' | bash "$PC/deploy/no/instalar.sh" 2>&1); RC=$?
checa '[ $RC = 0 ]' "instância: instalação sem erro (rc=$RC): $(echo "$SAIDA" | grep -E '✘|ERRO' | head -3)"
EC="$PC/.env"
for l in PAPEL=no INSTANCIA=camara APP_ALIAS=portal-web-app-camara NO_NOME=no-cm.exemplo.test "NO_TOKEN=$TOKEN3" PROXY_MODO=existente NGINX_C=portal-nginx CERTBOT_C=portal-certbot \
         "CONF_DIR=$P/deploy/no/proxy/conf.d" REDE_PROXY=portal-proxy; do
  checa "grep -qxF '$l' $EC" "instância: .env tem $l"
done
checa 'grep -q "portal-web-app-camara:8000" $P/deploy/no/proxy/conf.d/portal-comum-camara.inc && ! grep -q "portal-web-app:8000" $P/deploy/no/proxy/conf.d/portal-comum-camara.inc' 'instância: trecho do nginx aponta para o app da instância'
checa 'grep -q "ExecStart=/opt/portal_web-camara/deploy/ativador.sh" /etc/systemd/system/portal-ativador-camara.service && [ -f /etc/systemd/system/portal-ativador-camara.timer ] && grep -q "Environment=INSTANCIA=camara" /etc/systemd/system/portal-ativador-camara.service.d/no.conf && grep -q "Environment=PROJ=/opt/portal_web-camara" /etc/systemd/system/portal-ativador-camara.service.d/no.conf' 'instância: ativador próprio (portal-ativador-camara)'
checa 'grep -q "systemctl enable --now portal-ativador-camara.timer" /tmp/chamadas' 'instância: liga o ativador da instância'
checa 'grep -q "/opt/portal_web-camara/deploy/backup.sh" /etc/cron.d/portal-backup-camara && grep -q "^20 " /etc/cron.d/portal-backup-camara' 'instância: backup próprio, 20 min depois do primeiro'
checa '[ "$(cat $E $P/deploy/no/proxy/conf.d/portal-comum.inc /etc/systemd/system/portal-ativador.service.d/no.conf /etc/cron.d/portal-backup | sha256sum)" = "$H1" ]' 'instância: nada do primeiro nó foi alterado (.env, trecho do nginx, ativador, backup)'
checa '! grep -qE "deploy/no/proxy.*up -d|compose -f .*proxy" /tmp/chamadas && echo "$SAIDA" | grep -q "instância \"camara\""' 'instância: não sobe outro nginx e avisa a instância'
rm -rf "$PC" /root/segredos-no@camara.tar.gz.enc /tmp/no-proprio /tmp/portas-ocupadas /tmp/pc

# ---------- instância criada SEM TERMINAL, a pedido da gestão (19/11/2026): criar_instancia.sh + instalador automático ----------
PC=/opt/portal_web-camara; rm -rf "$PC"
printf 'PAPEL=no\nNO_NOME=no1.exemplo.test\nPROXY_MODO=proprio\nNGINX_C=portal-nginx\nCERTBOT_C=portal-certbot\nCONF_DIR=%s/deploy/no/proxy/conf.d\nPROXY_CERTS_DIR=/tmp/pc/certs\nREDE_PROXY=portal-proxy\nVPS_IP=198.51.100.5\n' "$P" > "$E"; chmod 600 "$E"
mkdir -p /tmp/pc/certs /tmp/pc/www; H1=$(sha256sum "$E" | cut -c1-16); touch /tmp/portas-ocupadas /tmp/no-proprio; : > /tmp/chamadas
printf 'SECRET_KEY=segredo-teste-AAAA\nTOTP_CHAVE=totp-teste-BBBB\nCPF_HMAC_CHAVE=hmac-teste-CCCC\nCHAVE_CREDENCIAIS=cred-teste-DDDD\nPG_USER=portal\nGESTAO_URL=https://gestao.exemplo.test\nNO_NOME=no-cm.exemplo.test\nNO_TOKEN=%s\nLICENCA_CHAVE_PUBLICA=%s\nINSTANCIA=camara\n' "$TOKEN3" "$PUB" > /tmp/env-instancia
SAIDA=$(bash "$P/deploy/no/criar_instancia.sh" 77 2>&1); RC=$?
checa '[ $RC = 0 ] && echo "$SAIDA" | grep -q "nó no-cm.exemplo.test instalado em /opt/portal_web-camara"' "sem terminal: instância criada (rc=$RC): $(echo "$SAIDA" | grep -E '✘' | head -3)"
for l in PAPEL=no INSTANCIA=camara APP_ALIAS=portal-web-app-camara NO_NOME=no-cm.exemplo.test "NO_TOKEN=$TOKEN3" PROXY_MODO=existente NGINX_C=portal-nginx REDE_PROXY=portal-proxy NO_PASTA=/opt/portal_web-camara SECRET_KEY=segredo-teste-AAAA; do
  checa "grep -qxF '$l' $PC/.env" "sem terminal: .env do nó novo tem $l"
done
checa '[ -f $PC/app/main.py ] && [ -z "$(ls -A $PC/backups 2>/dev/null)" ] && [ "$(stat -c %a $PC/.env)" = 600 ]' 'sem terminal: código copiado, sem backups do outro nó, .env protegido'
checa 'grep -q "ExecStart=/opt/portal_web-camara/deploy/ativador.sh" /etc/systemd/system/portal-ativador-camara.service && grep -q "/opt/portal_web-camara/deploy/backup.sh" /etc/cron.d/portal-backup-camara' 'sem terminal: ativador e backup do nó novo'
checa '[ "$(sha256sum "$E" | cut -c1-16)" = "$H1" ] && ! grep -qE "apt-get upgrade|ufw --force" /tmp/chamadas' 'sem terminal: nada do primeiro nó mudou; sem atualização nem firewall'
checa '! echo "$SAIDA" | grep -qF "$TOKEN3" && ! echo "$SAIDA" | grep -qF "segredo-teste-AAAA"' 'sem terminal: token e chaves fora da saída (que vai para a gestão)'
# pasta da instância já é de outro nó: para sem mexer
sed -i 's/^NO_NOME=.*/NO_NOME=outro-no.exemplo.test/' "$PC/.env"; H3=$(sha256sum "$PC/.env")
SAIDA=$(bash "$P/deploy/no/criar_instancia.sh" 78 2>&1); RC=$?
checa '[ $RC != 0 ] && echo "$SAIDA" | grep -q "já é de outro nó" && [ "$(sha256sum "$PC/.env")" = "$H3" ]' 'sem terminal: pasta de outro nó recusada'
rm -rf "$PC" /tmp/env-instancia /tmp/no-proprio /tmp/portas-ocupadas /tmp/pc

if [ "$ERROS" -gt 0 ]; then echo "ERROS: $ERROS"; exit 1; fi
echo 'instalador do nó (simulado): tudo ok'
