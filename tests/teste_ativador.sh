#!/bin/bash
# Ensaio do deploy/ativador.sh com docker, certbot, nginx e curl SIMULADOS, em pastas temporárias (nada toca a VPS real).
# Uso: bash tests/teste_ativador.sh
set -u
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
ERROS=0; checa() { if eval "$1"; then :; else echo "FALHOU: $2"; ERROS=$((ERROS + 1)); fi; }
mkdir -p "$T/conf.d" "$T/certs/live" "$T/certs/archive" "$T/estado" "$T/bin" "$T/fila"
printf 'server {\n    listen 443 ssl;\n    server_name ocupado.exemplo.com outro.exemplo.com;\n}\n' > "$T/conf.d/outro-sistema.conf"

# --- docker simulado: certbot cria o certificado; nginx -t falha se existir $T/nginx-quebrado ---
cat > "$T/bin/docker" <<EOF
#!/bin/bash
echo "docker \$*" >> "$T/chamadas"
if [ "\$1 \$2" = "exec certbot" ]; then
  d=\$(echo "\$*" | sed -n 's/.* -d \([^ ]*\) .*/\1/p')
  [ -f "$T/certbot-falha" ] && exit 1
  case " \$* " in *" --dry-run "*) exit 0 ;; esac
  mkdir -p "$T/certs/live/\$d" && echo cert > "$T/certs/live/\$d/fullchain.pem"; exit 0
fi
if [ "\$1 \$2 \$3 \$4" = "exec nginx nginx -t" ]; then [ -f "$T/nginx-quebrado" ] && exit 1; exit 0; fi
if [ "\$1 \$2 \$3" = "exec nginx nginx" ]; then echo reload >> "$T/recargas"; exit 0; fi
# Traefik: um container de outro sistema com rótulo de rota (Host(\`rotulo.exemplo.com\`))
if [ "\$1 \$2" = "ps -q" ]; then echo abc123; exit 0; fi
if [ "\$1" = inspect ] && [ "\$4" = abc123 ]; then echo 'Host(\`rotulo.exemplo.com\`)'; exit 0; fi
exit 0
EOF
# --- curl simulado: 200, ou falha se existir $T/https-falha ---
cat > "$T/bin/curl" <<EOF
#!/bin/bash
[ -f "$T/https-falha" ] && { echo 000; exit 7; }
# "https-lento": falha nas primeiras N chamadas (o nginx ainda com os processos antigos logo depois da recarga)
if [ -f "$T/https-lento" ]; then n=\$(cat "$T/https-lento"); if [ "\$n" -gt 0 ]; then echo \$((n - 1)) > "$T/https-lento"; echo 000; exit 60; fi; fi
echo 200
EOF
# --- app simulado: fila em arquivos (id acao dominio situacao) e geração do vhost como o app.ativacao ---
cat > "$T/bin/app" <<'EOF'
#!/bin/bash
F="$FILA"
case "$1" in
  pendentes) for f in "$F"/*.ped; do [ -e "$f" ] || continue; read -r id ac d sit < "$f"; [ "$sit" = pendente ] && printf '%s\t%s\t%s\n' "$id" "$ac" "$d"; done ;;
  validar) read -r id ac d sit < "$F/$2.ped"; [ -f "$F/dns-ruim" ] && { echo 'o DNS não aponta para a VPS'; exit 1; }; echo ok ;;
  passo) echo "$3" >> "$F/$2.passos" ;;
  concluir) read -r id ac d sit < "$F/$2.ped"; echo "$id $ac $d $3" > "$F/$2.ped"; echo "$4" > "$F/$2.msg"
            [ "$3" = no_ar ] && echo "$d" >> "$F/ativos"; [ "$3" = desativado ] && { grep -vxF "$d" "$F/ativos" > "$F/a.tmp"; mv "$F/a.tmp" "$F/ativos"; }; true ;;
  vhost) touch "$F/ativos"; doms=$(cat "$F/ativos")
         [ "${2:-}" = --incluir ] && { read -r id ac d sit < "$F/$3.ped"; doms="$doms $d"; }
         [ "${2:-}" = --excluir ] && { read -r id ac d sit < "$F/$3.ped"; doms=$(echo "$doms" | tr ' ' '\n' | grep -vxF "$d"); }
         [ "${2:-}" = --teste ] && doms="$doms $3"
         echo '# GERADO pelo ativador dos Portais (teste)'
         if [ "${2:-}" = --formato ]; then  # traefik: como o app, recebe entradas e resolvedor e devolve uma rota por domínio
           echo "# $*"; shift 9; [ "${1:-}" = --incluir ] && { read -r id ac d sit < "$F/$2.ped"; doms="$(cat "$F/ativos") $d"; }
           [ "${1:-}" = --excluir ] && { read -r id ac d sit < "$F/$2.ped"; doms=$(cat "$F/ativos" | grep -vxF "$d"); }
           [ "${1:-}" = --teste ] && doms="$(cat "$F/ativos") $2"
           for d in $doms; do printf '"rule": "Host(`%s`)"\n' "$d"; done; exit 0
         fi
         for d in $doms; do printf 'server {\n    listen 443 ssl http2;\n    server_name %s;\n    include /etc/nginx/conf.d/portal-comum.inc;\n}\n' "$d"; done ;;
esac
EOF
chmod +x "$T/bin/"*
pedido() { echo "$1 $2 $3 pendente" > "$T/fila/$1.ped"; }
rodar() { TENTATIVAS=${TENTATIVAS:-5} ESPERA=0 PROJ="$RAIZ" CONF_DIR="$T/conf.d" CERTS_DIR="$T/certs" ESTADO="$T/estado" LOG="$T/ativador.log" DOCKER="$T/bin/docker" CURL="$T/bin/curl" \
          APP_CMD="$T/bin/app" FILA="$T/fila" bash "$RAIZ/deploy/ativador.sh" "$@"; }
sit() { cut -d' ' -f4 < "$T/fila/$1.ped"; }

# 1. ativar com sucesso
pedido 1 ativar novo.exemplo.com; rodar
checa '[ "$(sit 1)" = no_ar ]' 'pedido 1 no ar'
checa 'grep -q "server_name novo.exemplo.com;" "$T/conf.d/portal-orgaos.conf"' 'vhost gerado com o domínio'
checa 'cmp -s "$RAIZ/deploy/nginx/portal-comum.inc" "$T/conf.d/portal-comum.inc"' 'trecho comum instalado'
checa '[ -s "$T/certs/live/novo.exemplo.com/fullchain.pem" ]' 'certificado emitido'
checa 'grep -q -- "--webroot -w /var/www/certbot -d novo.exemplo.com --cert-name novo.exemplo.com --non-interactive --agree-tos --keep-until-expiring" "$T/chamadas"' 'certbot em modo webroot, sem sobrescrever'
checa 'grep -q "Certificado emitido" "$T/fila/1.passos"' 'passos registrados'
checa 'cmp -s "$T/conf.d/outro-sistema.conf" <(printf "server {\n    listen 443 ssl;\n    server_name ocupado.exemplo.com outro.exemplo.com;\n}\n")' 'arquivo de outro sistema intacto'
# 2. domínio de outro sistema da VPS: recusa sem tocar em nada
cp "$T/conf.d/portal-orgaos.conf" "$T/antes.conf"; : > "$T/chamadas"
pedido 2 ativar ocupado.exemplo.com; rodar
checa '[ "$(sit 2)" = erro ] && grep -q "outro site da VPS" "$T/fila/2.msg"' 'domínio de outro sistema recusado'
checa '! grep -q "exec certbot" "$T/chamadas" && cmp -s "$T/antes.conf" "$T/conf.d/portal-orgaos.conf"' 'nada emitido nem alterado'
# 3. nginx -t recusa: volta o arquivo anterior e não recarrega
touch "$T/nginx-quebrado"; : > "$T/recargas"
pedido 3 ativar quebra.exemplo.com; rodar
checa '[ "$(sit 3)" = erro ] && grep -q "nginx recusou" "$T/fila/3.msg"' 'nginx -t recusou: erro informado'
checa 'cmp -s "$T/antes.conf" "$T/conf.d/portal-orgaos.conf"' 'configuração anterior restaurada'
checa '[ ! -s "$T/recargas" ]' 'nginx não recarregado com configuração quebrada'
rm -f "$T/nginx-quebrado"
# 4. certificado não sai: nada publicado
touch "$T/certbot-falha"; pedido 4 ativar semcert.exemplo.com; rodar; rm -f "$T/certbot-falha"
checa '[ "$(sit 4)" = erro ] && ! grep -q semcert "$T/conf.d/portal-orgaos.conf"' 'sem certificado: nada publicado'
# 5. HTTPS não responde: retira de novo
touch "$T/https-falha"; pedido 5 ativar mudo.exemplo.com; rodar; rm -f "$T/https-falha"
checa '[ "$(sit 5)" = erro ] && ! grep -q mudo "$T/conf.d/portal-orgaos.conf"' 'HTTPS mudo: domínio retirado de novo'
# 5b. HTTPS só responde depois de alguns instantes (recarga gradual do nginx): o ativador tenta de novo e publica
echo 2 > "$T/https-lento"; pedido 51 ativar lento.exemplo.com; rodar
checa '[ "$(sit 51)" = no_ar ] && grep -q "server_name lento.exemplo.com;" "$T/conf.d/portal-orgaos.conf"' 'HTTPS lento após a recarga: publicado na 3ª tentativa'
checa '[ "$(grep -c "conferência do HTTPS de lento.exemplo.com: tentativa" "$T/ativador.log")" = 2 ]' 'tentativas registradas no log'
echo 9 > "$T/https-lento"; pedido 52 ativar lento2.exemplo.com; TENTATIVAS=3 rodar; rm -f "$T/https-lento"
checa '[ "$(sit 52)" = erro ] && ! grep -q lento2 "$T/conf.d/portal-orgaos.conf"' 'HTTPS que não responde em nenhuma tentativa: retirado'
pedido 53 desativar lento.exemplo.com; rodar
# 6. DNS deixou de apontar (revalidação)
touch "$T/fila/dns-ruim"; pedido 6 ativar dns.exemplo.com; rodar; rm -f "$T/fila/dns-ruim"
checa '[ "$(sit 6)" = erro ] && grep -q "Recusado" "$T/fila/6.msg"' 'DNS revalidado na hora'
# 7. tirar do ar
pedido 7 desativar novo.exemplo.com; rodar
checa '[ "$(sit 7)" = desativado ] && ! grep -q novo.exemplo.com "$T/conf.d/portal-orgaos.conf"' 'retirada do ar'
checa '[ -s "$T/certs/live/novo.exemplo.com/fullchain.pem" ]' 'certificado guardado na retirada'
# 8. renovação: recarrega só quando um certificado mudou
: > "$T/recargas"; rodar; checa '[ ! -s "$T/recargas" ]' 'sem renovação: nenhuma recarga'
sleep 1; mkdir -p "$T/certs/archive/x"; echo novo > "$T/certs/archive/x/fullchain2.pem"; rodar
checa '[ "$(wc -l < "$T/recargas")" = 1 ] && grep -q "certificado renovado: nginx recarregado" "$T/ativador.log"' 'renovação: recarga do nginx'
: > "$T/recargas"; rodar; checa '[ ! -s "$T/recargas" ]' 'renovação: não recarrega de novo à toa'
# 9. modo de teste: publica, confere e retira
saida=$(rodar --teste teste-ativacao.exemplo.com)
checa 'echo "$saida" | grep -q "responde com certificado válido"' "teste de ponta a ponta ($saida)"
checa '! grep -q teste-ativacao "$T/conf.d/portal-orgaos.conf"' 'domínio de teste retirado no fim'
saida=$(DRY_RUN=1 rodar --teste ensaio.exemplo.com); checa 'echo "$saida" | grep -q "ensaio do certificado ok" && grep -q -- "--dry-run" "$T/chamadas"' 'ensaio (--dry-run) não publica'
checa '[ "$(rodar --teste "x;y" ; echo $?)" != 0 ]' 'domínio de teste inválido recusado'
# 10. trava: duas execuções ao mesmo tempo não se atropelam
exec 8>"$T/estado/trava"; flock -n 8; pedido 8 ativar trava.exemplo.com; rodar; checa '[ "$(sit 8)" = pendente ]' 'segunda execução sai sem fazer nada (trava)'; flock -u 8

# 11. modo Traefik (VPS com Dokploy): grava portal-orgaos.yml na pasta dinâmica, sem certbot nem nginx
mkdir -p "$T/dyn"; printf 'http:\n  routers:\n    app-dokploy:\n      rule: Host(`ocupado2.exemplo.com`)\n' > "$T/dyn/app-dokploy.yml"; cp "$T/dyn/app-dokploy.yml" "$T/dokploy-antes.yml"
rm -rf "$T/fila"/*; mkdir -p "$T/fila"; : > "$T/chamadas"; : > "$T/recargas"
rodar_t() { PROXY_MODO=traefik TRAEFIK_RESOLVEDOR=le CONF_DIR="$T/dyn" TENTATIVAS=${TENTATIVAS:-3} ESPERA=0 PROJ="$RAIZ" CERTS_DIR="$T/certs" ESTADO="$T/estado" LOG="$T/ativador.log" \
            DOCKER="$T/bin/docker" CURL="$T/bin/curl" APP_CMD="$T/bin/app" FILA="$T/fila" bash "$RAIZ/deploy/ativador.sh" "$@"; }
pedido 21 ativar orgao.exemplo.com; rodar_t
checa '[ "$(sit 21)" = no_ar ] && grep -q "Host(\`orgao.exemplo.com\`)" "$T/dyn/portal-orgaos.yml"' 'traefik: rota do órgão publicada em portal-orgaos.yml'
checa 'grep -q -- "--formato traefik --entrada-http web --entrada-https websecure --resolvedor le" "$T/dyn/portal-orgaos.yml"' 'traefik: entradas e resolvedor configurados passam para o app'
checa '! grep -q "exec certbot\|nginx -t" "$T/chamadas" && [ ! -s "$T/recargas" ] && [ ! -e "$T/dyn/portal-comum.inc" ]' 'traefik: sem certbot, sem nginx e sem trecho do nginx'
checa 'cmp -s "$T/dyn/app-dokploy.yml" "$T/dokploy-antes.yml" && [ "$(ls -A "$T/dyn" | sort | tr "\n" " ")" = "app-dokploy.yml portal-orgaos.yml " ]' 'traefik: arquivo do Dokploy intacto e nenhum arquivo extra na pasta'
grep -q "Gerando a rota no Traefik" "$T/fila/21.passos"; checa '[ $? = 0 ]' 'traefik: passos falam do Traefik'
pedido 22 ativar ocupado2.exemplo.com; pedido 23 ativar rotulo.exemplo.com; cp "$T/dyn/portal-orgaos.yml" "$T/antes.yml"; rodar_t
checa '[ "$(sit 22)" = erro ] && [ "$(sit 23)" = erro ] && cmp -s "$T/antes.yml" "$T/dyn/portal-orgaos.yml"' 'traefik: domínio de rota de outro sistema (arquivo ou rótulo) recusado sem mudar nada'
touch "$T/https-falha"; pedido 24 ativar mudo.exemplo.com; rodar_t; rm -f "$T/https-falha"
checa '[ "$(sit 24)" = erro ] && ! grep -q mudo "$T/dyn/portal-orgaos.yml" && grep -q "Traefik foi atualizado" "$T/fila/24.msg"' 'traefik: HTTPS sem certificado válido: retirado de novo'
pedido 25 desativar orgao.exemplo.com; rodar_t
checa '[ "$(sit 25)" = desativado ] && ! grep -q "orgao.exemplo.com" "$T/dyn/portal-orgaos.yml"' 'traefik: retirada do ar'
saida=$(rodar_t --teste teste-traefik.exemplo.com); checa 'echo "$saida" | grep -q "publicar no Traefik" && ! grep -q teste-traefik "$T/dyn/portal-orgaos.yml"' "traefik: modo de teste publica e retira ($saida)"

if [ "$ERROS" -gt 0 ]; then echo "ERROS: $ERROS"; exit 1; fi
echo 'ativador (simulado): tudo ok'
