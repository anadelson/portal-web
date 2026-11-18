#!/usr/bin/env bash
# =====================================================================================================================
#  Mover um órgão de um nó para outro (por exemplo, separar a Câmara da Prefeitura em duas instâncias da mesma VPS).
#  Roda na VPS, como root, DE DENTRO da pasta do nó (/opt/portal_web ou /opt/portal_web-<instância>).
#
#    bash deploy/no/mover_orgao.sh exportar SLUG          # no nó de ORIGEM: gera /root/mover-SLUG-AAAAMMDD-HHMM.tgz (permissão 600)
#    bash deploy/no/mover_orgao.sh importar ARQUIVO.tgz   # no nó de DESTINO: cria o banco, restaura e confere tabela por tabela
#    bash deploy/no/mover_orgao.sh limpar ARQUIVO.tgz     # no nó de ORIGEM, depois de conferido o destino: apaga o que ficou
#
#  Ordem completa (o console mostra o mesmo roteiro em Órgão → Hospedagem):
#    1. Console: tirar o domínio do ar   2. exportar (origem)   3. importar (destino)   4. Console: mudar a hospedagem
#    5. Console: publicar o domínio (o nó novo emite o certificado)   6. conferido o portal: limpar (origem)
#  Até o passo 6, voltar atrás é só mudar a hospedagem de volta e publicar: os dados continuam na origem.
#
#  O arquivo leva: o banco do órgão (pg_dump), as contagens de cada tabela, a pasta de arquivos do órgão (mídia, PDFs)
#  e as linhas do banco local do nó que são do órgão. Tem dados pessoais (e-SIC, usuários): guarde com permissão 600 e
#  apague depois. Nada vai para a tela além de nomes e contagens.
# =====================================================================================================================
set -uo pipefail
PROJ=$(cd "$(dirname "$0")/../.." && pwd)
DOCKER=${DOCKER:-docker}
DESTINO_ARQ=${DESTINO_ARQ:-/root}
LOG="$PROJ/logs/mover-orgao.log"; mkdir -p "$PROJ/logs"
ok() { printf '  \033[32m✔\033[0m %s\n' "$*"; echo "$(date -Is) ok $*" >> "$LOG"; }
av() { printf '  \033[33m!\033[0m %s\n' "$*"; echo "$(date -Is) aviso $*" >> "$LOG"; }
para() { printf '  \033[31m✘\033[0m %s\n' "$*"; echo "$(date -Is) ERRO $*" >> "$LOG"; echo "  Nada mais foi feito."; exit 1; }
[ "$(id -u)" = 0 ] || [ -n "${TESTE_MOVER:-}" ] || { echo "Rode como root."; exit 1; }
[ -f "$PROJ/.env" ] && grep -qx 'PAPEL=no' "$PROJ/.env" || para "esta pasta não é de um nó ($PROJ/.env sem PAPEL=no)"
cd "$PROJ"
PG_USER=$(grep -E '^PG_USER=' .env | tail -1 | cut -d= -f2-); PG_USER=${PG_USER:-portal}
PROJETO=$(basename "$PROJ" | tr 'A-Z' 'a-z' | tr -cd 'a-z0-9_-')
VOL=${VOL_DADOS:-/var/lib/docker/volumes/${PROJETO}_dados/_data}
dc() { $DOCKER compose "$@"; }
app() { dc exec -T app python -m app.mover_orgao "$@"; }
psqlc() { dc exec -T db psql -U "$PG_USER" -d postgres -Atc "$1"; }
existe_banco() { [ "$(psqlc "SELECT 1 FROM pg_database WHERE datname='$1'")" = 1 ]; }
json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2]) if not isinstance(d.get(sys.argv[2]),bool) else ('sim' if d[sys.argv[2]] else 'nao'))" "$@"; }
abrir() {  # abre o .tgz numa pasta temporária e confere os SHA-256 do manifesto
  [ -f "$1" ] || para "arquivo $1 não encontrado"
  T=$(mktemp -d); chmod 700 "$T"
  tar -xzf "$1" -C "$T" || para "arquivo ilegível"
  [ -f "$T/manifesto.json" ] || para "arquivo sem manifesto (não foi gerado por este script)"
  (cd "$T" && sha256sum -c --quiet sha256.txt) || para "o arquivo não confere com o manifesto (corrompido ou alterado)"
  SLUG=$(json "$T/manifesto.json" slug); BANCO=$(json "$T/manifesto.json" banco); OID=$(json "$T/manifesto.json" id)
  [[ "$SLUG" =~ ^[a-z0-9-]{2,40}$ && "$BANCO" =~ ^[a-z0-9_]{2,60}$ && "$OID" =~ ^[0-9]+$ ]] || para "manifesto com dados inválidos"
}

case "${1:-}" in
# ---------------------------------------------------------------------------------------------------------------------
exportar)
  SLUG=${2:-}; [[ "$SLUG" =~ ^[a-z0-9-]{2,40}$ ]] || para "informe o slug do órgão (ex.: cmb-bora)"
  echo "Exportar o órgão $SLUG deste nó ($PROJ)"
  T=$(mktemp -d); chmod 700 "$T"; trap 'rm -rf "$T"' EXIT
  app info "$SLUG" > "$T/info.json" || para "não consegui ler o órgão no app (o app está no ar?)"
  [ "$(json "$T/info.json" hospedado_aqui)" = sim ] || para "o órgão $SLUG não está neste nó"
  [ "$(json "$T/info.json" publicado)" = nao ] || para "o domínio do órgão ainda está publicado aqui: tire do ar no console (Publicação → Tirar do ar) e espere o ativador (1 a 3 min)"
  BANCO=$(json "$T/info.json" banco); OID=$(json "$T/info.json" id)
  existe_banco "$BANCO" || para "o banco $BANCO não existe neste nó"
  dc exec -T db pg_dump -U "$PG_USER" -Fc "$BANCO" > "$T/banco.dump" && [ -s "$T/banco.dump" ] || para "pg_dump do banco $BANCO falhou"
  ok "banco $BANCO copiado ($(du -h "$T/banco.dump" | cut -f1))"
  app contar "$BANCO" > "$T/contagens.json" || para "não consegui contar as tabelas do banco $BANCO"
  ok "contagens de $(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$T/contagens.json") tabelas registradas"
  app exportar-local "$SLUG" - > "$T/local.zip" 2>> "$LOG" || para "não consegui copiar as linhas do banco local do órgão"
  ok "linhas do banco local do órgão copiadas"
  if [ -d "$VOL/$SLUG" ]; then tar --numeric-owner -czf "$T/dados.tgz" -C "$VOL" "$SLUG" || para "falha ao copiar a pasta de arquivos"; ok "pasta de arquivos $SLUG copiada ($(du -sh "$VOL/$SLUG" | cut -f1))"
  else tar -czf "$T/dados.tgz" -T /dev/null; av "o órgão não tem pasta de arquivos neste nó"; fi
  python3 - "$T/info.json" "$T/manifesto.json" <<'PY'
import json, sys, datetime
i = json.load(open(sys.argv[1]))
json.dump({'slug': i['slug'], 'id': i['id'], 'banco': i['banco'], 'dominio': i['dominio'], 'origem_instancia': i['instancia'], 'versao': i['versao'],
           'gerado_em': datetime.datetime.now(datetime.timezone.utc).isoformat()}, open(sys.argv[2], 'w'), ensure_ascii=False, indent=1)
PY
  (cd "$T" && sha256sum banco.dump contagens.json local.zip dados.tgz manifesto.json > sha256.txt)
  ARQ="$DESTINO_ARQ/mover-$SLUG-$(date +%Y%m%d-%H%M).tgz"
  (umask 077 && tar -czf "$ARQ" -C "$T" banco.dump contagens.json local.zip dados.tgz manifesto.json sha256.txt) || para "não consegui gravar $ARQ"
  chmod 600 "$ARQ"
  ok "arquivo gerado: $ARQ (permissão 600)"
  echo "  Próximo passo, na pasta do nó de DESTINO:  bash deploy/no/mover_orgao.sh importar $ARQ"
  ;;
# ---------------------------------------------------------------------------------------------------------------------
importar)
  abrir "${2:-}"; trap 'rm -rf "$T"' EXIT
  echo "Importar o órgão $SLUG (banco $BANCO) neste nó ($PROJ)"
  ORIG_V=$(json "$T/manifesto.json" versao); AQUI_V=$(cat app/VERSAO 2>/dev/null || true)
  [ "$ORIG_V" = "$AQUI_V" ] || av "versões diferentes (origem: $ORIG_V · aqui: $AQUI_V): depois da hospedagem, rode 'docker compose exec -T app python -m app.provision atualizar'"
  existe_banco "$BANCO" && para "o banco $BANCO já existe neste nó: nada foi alterado (se for sobra de uma tentativa, confira e apague à mão)"
  [ -e "$VOL/$SLUG" ] && para "a pasta de arquivos $SLUG já existe neste nó ($VOL/$SLUG)"
  dc exec -T db createdb -U "$PG_USER" "$BANCO" || para "não consegui criar o banco $BANCO"
  desfaz() { dc exec -T db dropdb -U "$PG_USER" --if-exists "$BANCO" >/dev/null 2>&1; rm -rf "${VOL:?}/$SLUG"; }
  if ! dc exec -T db pg_restore -U "$PG_USER" --no-owner --exit-on-error -d "$BANCO" < "$T/banco.dump" >> "$LOG" 2>&1; then desfaz; para "pg_restore falhou (veja $LOG): banco apagado de novo"; fi
  app contar "$BANCO" > "$T/aqui.json" || { desfaz; para "não consegui contar as tabelas restauradas"; }
  DIF=$(python3 -c "
import json,sys
a,b=json.load(open(sys.argv[1])),json.load(open(sys.argv[2]))
print('; '.join(f'{t}: origem {a.get(t)} × aqui {b.get(t)}' for t in sorted(set(a)|set(b)) if a.get(t)!=b.get(t)))" "$T/contagens.json" "$T/aqui.json")
  [ -z "$DIF" ] || { desfaz; para "as contagens não conferem ($DIF): banco apagado de novo"; }
  ok "banco $BANCO restaurado: $(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(f'{len(d)} tabelas, {sum(d.values())} linhas, todas iguais às da origem')" "$T/aqui.json")"
  mkdir -p "$VOL"; tar --numeric-owner --same-owner -xzf "$T/dados.tgz" -C "$VOL" || { desfaz; para "falha ao copiar a pasta de arquivos"; }
  [ -d "$VOL/$SLUG" ] && ok "pasta de arquivos $SLUG copiada"
  app importar-local - < "$T/local.zip" >> "$LOG" 2>&1 || { desfaz; para "as linhas do banco local não foram importadas (veja $LOG): banco e pasta apagados de novo"; }
  ok "linhas do banco local do órgão importadas"
  echo "  Próximo passo, no console da gestão: Órgão → Hospedagem → este nó; depois Publicação → Publicar."
  echo "  O nó começa a servir o órgão em até 5 minutos (quando receber a licença)."
  ;;
# ---------------------------------------------------------------------------------------------------------------------
limpar)
  abrir "${2:-}"; trap 'rm -rf "$T"' EXIT
  echo "Apagar deste nó ($PROJ) o que ficou do órgão $SLUG (banco $BANCO), já levado para outro nó"
  app info "$SLUG" > "$T/info.json" || para "não consegui consultar o app"
  [ "$(json "$T/info.json" hospedado_aqui)" = nao ] || para "o órgão $SLUG ainda está neste nó (licença): mude a hospedagem no console e espere até 5 minutos"
  existe_banco "$BANCO" || av "o banco $BANCO já não existe aqui"
  read -r -p "  Confira o portal no nó novo antes. Para apagar, digite o slug do órgão ($SLUG): " R
  [ "$R" = "$SLUG" ] || para "confirmação não confere"
  mkdir -p "$PROJ/backups"
  if existe_banco "$BANCO"; then
    dc exec -T db pg_dump -U "$PG_USER" -Fc "$BANCO" > "$PROJ/backups/removido-$BANCO-$(date +%Y%m%d-%H%M).dump" || para "não consegui guardar a cópia do banco antes de apagar"
    chmod 600 "$PROJ"/backups/removido-"$BANCO"-*.dump; ok "cópia guardada em backups/removido-$BANCO-….dump"
    dc exec -T db dropdb -U "$PG_USER" "$BANCO" || para "não consegui apagar o banco $BANCO"; ok "banco $BANCO apagado deste nó"
  fi
  [ -d "$VOL/$SLUG" ] && { rm -rf "${VOL:?}/$SLUG"; ok "pasta de arquivos $SLUG apagada deste nó"; }
  app limpar-local "$SLUG" "$OID" >> "$LOG" 2>&1 || para "não consegui apagar as linhas do banco local (veja $LOG)"
  ok "linhas do banco local do órgão apagadas"
  echo "  Pronto. Apague também o arquivo de transferência quando não precisar mais: rm ${2}"
  ;;
*) sed -n '2,20p' "$0"; exit 2 ;;
esac
