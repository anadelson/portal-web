#!/bin/bash
# Ensaio do deploy/no/mover_orgao.sh com DOIS servidores PostgreSQL de teste (um por nó, como duas instâncias na mesma VPS):
# exportar a Câmara do nó A, importar no nó B (conferindo tabela por tabela), recusas e limpar o nó A. Dados de teste (seed),
# nada da VPS real: containers e rede descartáveis, apagados no fim.  Uso (no host): bash tests/teste_mover_orgao.sh
set -u
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
R=portal-mover; IMG=${IMG:-portal_web-app}
limpa() { docker rm -fv mover-db-a mover-db-b >/dev/null 2>&1; docker network rm $R >/dev/null 2>&1; }
limpa; trap limpa EXIT
docker network create $R >/dev/null
for x in a b; do docker run -d --name mover-db-$x --network $R --memory 256m -e POSTGRES_USER=portal -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=postgres postgres:16 >/dev/null; done
for x in a b; do until docker exec mover-db-$x pg_isready -U portal >/dev/null 2>&1; do sleep 2; done; done; sleep 3
docker run --rm -i -u 0 --network $R --memory 512m -v "$RAIZ/app:/srv/app:ro" -v "$RAIZ/deploy:/codigo/deploy:ro" \
  -e TESTE=1 -e PG_USER=portal -e PG_PASSWORD=teste -e DOMINIO_GESTAO=gestao.localhost -e DOMINIO_PM=pmbora.localhost -e DOMINIO_CM=cmbora.localhost \
  -e SENHA_INICIAL_GESTOR=gestor123 -e SENHA_INICIAL_ADMIN=admin123 -e SECRET_KEY=teste -e COOKIE_SEGURO=0 -e DADOS_DIR=/tmp/dados -e SEGREDOS_DIR=/tmp/segredos \
  "$IMG" bash -s <<'DENTRO'
set -u
ERROS=0; checa() { if eval "$1"; then :; else echo "FALHOU: $2"; ERROS=$((ERROS + 1)); fi; }
cd /srv
# ---- nó A com a gestão de teste (papel tudo) para semear Prefeitura e Câmara e assinar as licenças ----
G="env PG_HOST=mover-db-a"
$G python -m app.assinatura gerar-teste >/dev/null 2>&1; $G python -m app.provision init >/dev/null && $G python -m app.provision atualizar >/dev/null || { echo "provision falhou"; exit 1; }
$G python - <<'PY' > /tmp/prep.json
import json
from app import db, licenca as L, provision, no_local as NL
db.exe(db.PLATAFORMA, "INSERT INTO nos (nome, token_hash) VALUES ('no-a.exemplo.test','x') ON CONFLICT DO NOTHING")
n = db.um(db.PLATAFORMA, "SELECT id FROM nos WHERE nome='no-a.exemplo.test'")
db.exe(db.PLATAFORMA, "UPDATE orgaos SET no_id=%s WHERE slug IN ('pm-bora','cm-bora')", (n['id'],))
cm = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='cm-bora'"); pm = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
db.exe(db.PLATAFORMA, "INSERT INTO coletas (orgao_slug, fonte, ok, mensagem) VALUES ('cm-bora','teste',TRUE,'coleta de TESTE 1'),('cm-bora','teste',TRUE,'coleta de TESTE 2'),('pm-bora','teste',TRUE,'coleta de TESTE da PM')")
NL.exportar('no-a.exemplo.test', '/tmp/local-a.zip')
print(json.dumps({'pub': L.garantir_chaves()[1], 'lics': [L.emitir(pm), L.emitir(cm)], 'cm': cm['id'], 'pm': pm['id']}, default=str))
PY
PUB=$(python3 -c "import json; print(json.load(open('/tmp/prep.json'))['pub'])"); CM=$(python3 -c "import json; print(json.load(open('/tmp/prep.json'))['cm'])")
# os dois nós: banco local (no_local); o nó A recebe as licenças das duas e as linhas do banco local
for H in mover-db-a mover-db-b; do env PG_HOST=$H python -c "from app import provision; provision.criar_banco('no_local'); provision.aplicar('no_local', provision.MIG_LOCAL)" || exit 1; done
NA="env PAPEL=no PG_HOST=mover-db-a NO_BANCO=no_local LICENCA_CHAVE_PUBLICA=$PUB NO_NOME=no-a.exemplo.test"
NB="env PAPEL=no PG_HOST=mover-db-b NO_BANCO=no_local LICENCA_CHAVE_PUBLICA=$PUB NO_NOME=no-b.exemplo.test INSTANCIA=camara"
$NA python -c "
import json; from app import licenca as L, no_local as NL
d=json.load(open('/tmp/prep.json')); print(L.guardar(d['lics'], d['pub'])); print(NL.importar('/tmp/local-a.zip', True))" > /dev/null || exit 1
# o banco da Prefeitura NÃO fica no nó B; o da Câmara só no A (o nó B é a instância nova, vazia)
# ---- as duas pastas de instância e o docker simulado (encaminha "compose exec db/app" para o servidor de cada nó) ----
mkdir -p /tmp/inst /tmp/arq /tmp/stub /tmp/vol-a/cm-bora/midia /tmp/vol-a/pm-bora /tmp/vol-b
echo 'ARQUIVO DE TESTE da Câmara' > /tmp/vol-a/cm-bora/midia/teste.txt; echo 'ARQUIVO DE TESTE da Prefeitura' > /tmp/vol-a/pm-bora/x.txt; chown -R 1001:999 /tmp/vol-a
for i in portal_web portal_web-camara; do
  mkdir -p /tmp/inst/$i/deploy/no /tmp/inst/$i/app; cp /codigo/deploy/no/mover_orgao.sh /tmp/inst/$i/deploy/no/; echo 'versao-teste (abc1234)' > /tmp/inst/$i/app/VERSAO
  printf 'PAPEL=no\nPG_USER=portal\n' > /tmp/inst/$i/.env
done
echo "$NA" > /tmp/inst/portal_web/.stub; echo "$NB" > /tmp/inst/portal_web-camara/.stub
cat > /tmp/stub/docker <<'EOF'
#!/bin/bash
[ "$1" = compose ] || exit 0
shift; [ "$1" = exec ] && shift; [ "$1" = -T ] && shift
svc=$1; shift; E=$(cat "$PWD/.stub"); H=$(echo "$E" | sed -n 's/.*PG_HOST=\([^ ]*\).*/\1/p')
export PGPASSWORD=teste
# o cliente desta imagem é mais novo que o servidor de teste (16): na VPS, pg_dump e pg_restore são os do próprio container db
# (mesma versão nas duas pontas). Aqui o pg_restore vira SQL sem o "SET transaction_timeout" (que o servidor 16 não conhece).
if [ "$svc" = db ] && [ "$1" = pg_restore ]; then
  shift; d=""; a=(); while [ $# -gt 0 ]; do case "$1" in -d) d=$2; shift 2 ;; -U) shift 2 ;; *) a+=("$1"); shift ;; esac; done
  pg_restore "${a[@]}" -f - | sed '/^SET transaction_timeout/d' | psql -h "$H" -U portal -d "$d" -v ON_ERROR_STOP=1 -q >/dev/null; exit ${PIPESTATUS[2]}
fi
if [ "$svc" = db ]; then c=$1; shift; exec "$c" -h "$H" "$@"; fi
if [ "$svc" = app ]; then cd /srv && exec $E "$@"; fi
exit 1
EOF
chmod +x /tmp/stub/docker
MA="env DOCKER=/tmp/stub/docker DESTINO_ARQ=/tmp/arq VOL_DADOS=/tmp/vol-a bash /tmp/inst/portal_web/deploy/no/mover_orgao.sh"
MB="env DOCKER=/tmp/stub/docker DESTINO_ARQ=/tmp/arq VOL_DADOS=/tmp/vol-b bash /tmp/inst/portal_web-camara/deploy/no/mover_orgao.sh"
cont() { PGPASSWORD=teste psql -h $1 -U portal -d $2 -Atc "SELECT count(*) FROM $3"; }
existe() { [ "$(PGPASSWORD=teste psql -h $1 -U portal -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='$2'")" = 1 ]; }
ANTES=$(cd /srv && $NA python -m app.mover_orgao contar bd_cm_bora)
PM_ANTES=$(cd /srv && $NA python -m app.mover_orgao contar bd_pm_bora)

# 1. domínio ainda publicado no nó A: exportar recusa
PGPASSWORD=teste psql -h mover-db-a -U portal -d no_local -qc "INSERT INTO dominios_publicados (orgao_id, dominio) VALUES ($CM, 'cmbora.localhost')"
S=$($MA exportar cm-bora 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "ainda está publicado" && [ -z "$(ls /tmp/arq)" ]' 'domínio publicado: exportar recusa sem gerar arquivo'
PGPASSWORD=teste psql -h mover-db-a -U portal -d no_local -qc "DELETE FROM dominios_publicados"
S=$($MA exportar nao-existe 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "não está neste nó"' 'órgão que não é do nó: recusa'

# 2. exportar a Câmara do nó A
S=$($MA exportar cm-bora 2>&1); RC=$?; ARQ=$(ls /tmp/arq/mover-cm-bora-*.tgz 2>/dev/null | head -1)
checa '[ $RC = 0 ] && [ -n "$ARQ" ] && [ "$(stat -c %a "$ARQ")" = 600 ]' "exportar: arquivo gerado com permissão 600 (rc=$RC): $(echo "$S" | grep ✘)"
checa 'tar -tzf "$ARQ" | sort | tr "\n" " " | grep -q "banco.dump contagens.json dados.tgz local.zip manifesto.json sha256.txt"' 'exportar: arquivo com banco, contagens, arquivos, banco local e manifesto'
checa 'existe mover-db-a bd_cm_bora && [ -d /tmp/vol-a/cm-bora ]' 'exportar não apaga nada da origem'

# 3. recusas na importação: arquivo adulterado; nó B sem o banco ainda
T=$(mktemp -d); tar -xzf "$ARQ" -C $T; echo x >> $T/contagens.json; tar -czf /tmp/arq/adulterado.tgz -C $T .; rm -rf $T
S=$($MB importar /tmp/arq/adulterado.tgz 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "não confere com o manifesto" && ! existe mover-db-b bd_cm_bora' 'arquivo adulterado: recusado, nada criado'

# 4. importar no nó B
S=$($MB importar "$ARQ" 2>&1); RC=$?
checa '[ $RC = 0 ] && existe mover-db-b bd_cm_bora' "importar: banco criado no nó B (rc=$RC): $(echo "$S" | grep ✘)"
DEPOIS=$(cd /srv && $NB python -m app.mover_orgao contar bd_cm_bora 2>/dev/null)
checa '[ -n "$DEPOIS" ] && [ "$DEPOIS" = "$ANTES" ]' 'importar: todas as tabelas com as mesmas contagens da origem'
checa 'echo "$S" | grep -q "todas iguais às da origem"' 'importar: informa a conferência'
checa '[ "$(cat /tmp/vol-b/cm-bora/midia/teste.txt)" = "ARQUIVO DE TESTE da Câmara" ] && [ "$(stat -c %u /tmp/vol-b/cm-bora/midia/teste.txt)" = 1001 ] && [ ! -e /tmp/vol-b/pm-bora ]' 'importar: arquivos da Câmara (e só eles), com o dono do app'
checa '[ "$(cont mover-db-b no_local "coletas WHERE orgao_slug='"'"'cm-bora'"'"'")" = 2 ] && [ "$(cont mover-db-b no_local "coletas WHERE orgao_slug='"'"'pm-bora'"'"'")" = 0 ] && [ "$(cont mover-db-b no_local "fontes WHERE orgao_id='$CM'")" = "$(cont mover-db-a no_local "fontes WHERE orgao_id='$CM'")" ]' 'importar: linhas do banco local só da Câmara'
checa '! existe mover-db-b bd_pm_bora' 'importar: a Prefeitura não vai para o nó B'
S=$($MB importar "$ARQ" 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "já existe neste nó"' 'importar de novo: recusado (banco já existe)'

# 5. limpar o nó A: recusa enquanto a Câmara ainda é do nó A; depois do inventário, apaga só a Câmara (com cópia)
S=$(echo cm-bora | $MA limpar "$ARQ" 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "ainda está neste nó" && existe mover-db-a bd_cm_bora' 'limpar antes de mudar a hospedagem: recusado'
env PG_HOST=mover-db-a python -c "
import json; from datetime import datetime, timezone; from app import licenca as L
d=json.load(open('/tmp/prep.json'))
json.dump(L.assinar({'tipo':'inventario','no':'no-a.exemplo.test','orgaos':[d['pm']],'emitido_em':datetime.now(timezone.utc).isoformat()}), open('/tmp/inv.json','w'))"
R=$(cd /srv && $NA python -c "
import json; from app import licenca as L
print(L.esquecer(json.load(open('/tmp/inv.json')), json.load(open('/tmp/prep.json'))['pub']))")
checa '[ "$R" = 1 ]' "inventário assinado: o nó A esquece a Câmara ($R)"
S=$(echo errado | $MA limpar "$ARQ" 2>&1); checa '[ $? != 0 ] && echo "$S" | grep -q "confirmação não confere" && existe mover-db-a bd_cm_bora' 'limpar sem a confirmação certa: nada apagado'
S=$(echo cm-bora | $MA limpar "$ARQ" 2>&1); RC=$?
checa '[ $RC = 0 ] && ! existe mover-db-a bd_cm_bora && [ ! -e /tmp/vol-a/cm-bora ]' "limpar: banco e arquivos da Câmara apagados do nó A (rc=$RC): $(echo "$S" | grep ✘)"
checa 'ls /tmp/inst/portal_web/backups/removido-bd_cm_bora-*.dump >/dev/null 2>&1 && [ "$(stat -c %a /tmp/inst/portal_web/backups/removido-bd_cm_bora-*.dump)" = 600 ]' 'limpar: cópia do banco guardada antes de apagar'
checa '[ "$(cont mover-db-a no_local "coletas WHERE orgao_slug='"'"'cm-bora'"'"'")" = 0 ] && [ "$(cont mover-db-a no_local "coletas WHERE orgao_slug='"'"'pm-bora'"'"'")" = 1 ]' 'limpar: linhas do banco local só da Câmara apagadas'
checa 'existe mover-db-a bd_pm_bora && [ "$(cd /srv && $NA python -m app.mover_orgao contar bd_pm_bora)" = "$PM_ANTES" ] && [ -f /tmp/vol-a/pm-bora/x.txt ]' 'a Prefeitura no nó A ficou intacta'
checa '[ "$(cd /srv && $NB python -m app.mover_orgao contar bd_cm_bora)" = "$ANTES" ]' 'a Câmara no nó B continua igual depois da limpeza do A'
grep -rqE "teste@|SECRET|senha" /tmp/inst/*/logs/mover-orgao.log && checa 'false' 'log sem segredos' || true

if [ "$ERROS" -gt 0 ]; then echo "ERROS: $ERROS"; exit 1; fi
echo 'mover órgão entre nós: tudo ok'
DENTRO
