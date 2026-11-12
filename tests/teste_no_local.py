# Separação gestão × portais, etapa A2 (11/11/2026): banco local do nó e cópia das tabelas operacionais.
# Papel "tudo" continua igual (banco local = banco de controle); o papel "no" é simulado no mesmo processo, com um banco local de verdade.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_no_local.py
import io, json, os, re, sys, tempfile, zipfile
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app
from app import db, config, licenca as L, web, worker, orgaos, remessa, provision, no_local as NL
from app.coletores import comum
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
checa(db.LOCAL == db.PLATAFORMA and config.PAPEL == 'tudo', 'papel "tudo": banco local é o próprio banco de controle')
PM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
CM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='cm-bora'")
LOCAL = 'no_local_teste'

# ---------- 1. esquema do banco local = esquema do controle ----------
provision.criar_banco(LOCAL)
provision.aplicar(LOCAL, provision.MIG_LOCAL)
provision.aplicar(LOCAL, provision.MIG_LOCAL)  # idempotente
def esquema(banco, t):
    return [(r['column_name'], r['data_type'], r['is_nullable'], re.sub(r"nextval\('[^']+'::regclass\)", 'nextval', r['column_default'] or ''))
            for r in db.todos(banco, "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (t,))]
for t in list(NL.TABELAS) + ['login_tentativas', 'licencas_cache']:
    checa(esquema(LOCAL, t) and esquema(LOCAL, t) == esquema(db.PLATAFORMA, t), f'{t}: mesmo esquema no banco local e no controle')
checa(not db.um(LOCAL, "SELECT 1 FROM information_schema.table_constraints WHERE constraint_type='FOREIGN KEY'"), 'banco local sem chave estrangeira para orgaos')

# ---------- 2. exportar só o que é dos órgãos do nó ----------
db.exe(db.PLATAFORMA, "INSERT INTO coletas (orgao_slug, fonte, ok, registros, mensagem) VALUES ('pm-bora','teste:a',TRUE,3,'exemplo'),('cm-bora','teste:b',TRUE,1,'exemplo'),('outro-orgao','teste:c',TRUE,1,'exemplo')")
db.exe(db.PLATAFORMA, "INSERT INTO dados_publicos (ibge, fonte, chave, payload) VALUES (%s,'teste','k1',%s),('9999999','teste','k2',%s) ON CONFLICT DO NOTHING", (PM['ibge'], Jsonb({'exemplo': 1}), Jsonb({'exemplo': 2})))
db.exe(db.PLATAFORMA, "INSERT INTO remessas_log (origem, destino, acao, ok, detalhe) VALUES ('cm-bora','pm-bora','teste',TRUE,'exemplo'),('x','y','teste',TRUE,'fora')")
db.exe(db.PLATAFORMA, "INSERT INTO config_console (chave, valor) VALUES ('teste_a2', %s) ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor", (Jsonb({'exemplo': True}),))
token = L.criar_no('no-a2.exemplo.test')
no = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-a2.exemplo.test'")
antes = [(f['slug'], f['fonte'], json.dumps(f['params'], sort_keys=True)) for f in worker.fontes_ativas()]  # antes de os órgãos irem para o nó
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id IN (%s,%s)', (no['id'], PM['id'], CM['id']))
checa(worker.fontes_ativas() == [] and orgaos.todos() == [], 'órgãos hospedados no nó saem desta VPS (worker e cadastro local)')
arq = os.path.join(tempfile.mkdtemp(), 'no.zip')
man = NL.exportar('no-a2.exemplo.test', arq)
T = man['tabelas']
checa(man['orgaos'] == ['pm-bora', 'cm-bora'] or sorted(man['orgaos']) == ['cm-bora', 'pm-bora'], 'manifesto com os órgãos do nó')
checa(T['coletas']['linhas'] == db.um(db.PLATAFORMA, "SELECT count(*) n FROM coletas WHERE orgao_slug IN ('pm-bora','cm-bora')")['n'], 'coletas: só as dos órgãos do nó')
checa(T['fontes']['linhas'] == db.um(db.PLATAFORMA, 'SELECT count(*) n FROM fontes WHERE orgao_id IN (%s,%s)', (PM['id'], CM['id']))['n'] and T['fontes']['linhas'] > 5, 'fontes dos dois órgãos')
checa(T['dados_publicos']['linhas'] == db.um(db.PLATAFORMA, 'SELECT count(*) n FROM dados_publicos WHERE ibge=%s', (PM['ibge'],))['n'], 'dados públicos só do município do nó')
checa(T['remessas_log']['linhas'] == db.um(db.PLATAFORMA, "SELECT count(*) n FROM remessas_log WHERE origem IN ('pm-bora','cm-bora') OR destino IN ('pm-bora','cm-bora')")['n'], 'remessas só dos órgãos do nó')
checa(T['pares_orgaos']['linhas'] >= 1 and 'login_tentativas' not in T and 'licencas_cache' not in T, 'pares incluídos; tentativas de login e cache de licenças fora')
checa(oct(os.stat(arq).st_mode)[-3:] in ('600', '644') and NL.ler(arq)[0]['no'] == 'no-a2.exemplo.test', 'arquivo legível e com manifesto')

# arquivo alterado: recusado antes de gravar qualquer coisa
ruim = arq.replace('no.zip', 'ruim.zip')
with zipfile.ZipFile(arq) as zi, zipfile.ZipFile(ruim, 'w') as zo:
    for n in zi.namelist():
        d = zi.read(n)
        zo.writestr(n, d + (b'1,2,3\n' if n == 'coletas.csv' else b''))
try:
    NL.ler(ruim); erros.append('arquivo alterado aceito')
except ValueError as e:
    checa('SHA-256' in str(e), 'arquivo alterado: recusado pela soma')

# ---------- 3. importar no banco local: tudo ou nada ----------
db.LOCAL = LOCAL
feitas = NL.importar(arq)
checa(feitas == {t: i['linhas'] for t, i in T.items()}, f'importação: contagens iguais às do manifesto ({feitas})')
try:
    NL.importar(arq); erros.append('importou por cima sem --substituir')
except ValueError as e:
    checa('--substituir' in str(e), 'segunda importação sem --substituir: recusada')
# manifesto mentindo a contagem: desfaz tudo (mesmo com --substituir, nada muda)
m2 = dict(man); m2['tabelas'] = json.loads(json.dumps(man['tabelas'])); m2['tabelas']['fontes']['linhas'] += 1
erra = arq.replace('no.zip', 'conta.zip')
with zipfile.ZipFile(arq) as zi, zipfile.ZipFile(erra, 'w') as zo:
    for n in zi.namelist():
        zo.writestr(n, json.dumps(m2) if n == 'manifesto.json' else zi.read(n))
db.exe(LOCAL, "INSERT INTO coletas (orgao_slug, fonte, ok) VALUES ('pm-bora','marca:antes',TRUE)")
try:
    NL.importar(erra, substituir=True); erros.append('contagem errada aceita')
except ValueError as e:
    checa('nada foi gravado' in str(e) and db.um(LOCAL, "SELECT 1 FROM coletas WHERE fonte='marca:antes'"), 'contagem diferente: transação desfeita (nada apagado nem gravado)')
db.exe(LOCAL, "DELETE FROM coletas WHERE fonte='marca:antes'")
checa(db.um(LOCAL, "SELECT nextval('coletas_id_seq') n")['n'] > db.um(LOCAL, 'SELECT max(id) m FROM coletas')['m'] - 1, 'sequência ajustada depois da cópia')

# ---------- 4. nó simulado lendo do banco local ----------
db.LOCAL = LOCAL
imp, pub = L.garantir_chaves()
pac = L.entregar(no)
config.PAPEL, config.LICENCA_CHAVE_PUBLICA = 'no', pub
web.limpar_cache(); L._memo.clear()
checa(L.guardar(pac['licencas'], pub) == (2, 0) and db.um(LOCAL, 'SELECT count(*) n FROM licencas_cache')['n'] == 2, 'licenças guardadas no banco local')
checa([o['slug'] for o in orgaos.todos()] == ['pm-bora', 'cm-bora'] and orgaos.executivo_do(CM['ibge'])['slug'] == 'pm-bora', 'órgãos do nó vêm das licenças')
depois = [(f['slug'], f['fonte'], json.dumps(f['params'], sort_keys=True)) for f in worker.fontes_ativas()]
checa(depois == antes and len(depois) > 5, 'worker do nó vê as mesmas fontes, lidas do banco local')
pt = TestClient(app, base_url='http://pmbora.localhost'); ct = TestClient(app, base_url='http://cmbora.localhost')
for c_, u in ((pt, '/'), (pt, '/transparencia'), (pt, '/diario'), (pt, '/dados-abertos'), (ct, '/'), (ct, '/transparencia')):
    r = c_.get(u)
    checa(r.status_code == 200, f'nó: {c_.base_url.host}{u} responde ({r.status_code})')
n_ctl = db.um(db.PLATAFORMA, 'SELECT count(*) n FROM coletas')['n']; n_loc = db.um(LOCAL, 'SELECT count(*) n FROM coletas')['n']
comum.registrar('pm-bora', 'teste:no', True, 1, 'exemplo')
checa(db.um(LOCAL, 'SELECT count(*) n FROM coletas')['n'] == n_loc + 1 and db.um(db.PLATAFORMA, 'SELECT count(*) n FROM coletas')['n'] == n_ctl, 'coleta registrada no banco local, não no controle')
checa((remessa.destino_do(CM) or {}).get('slug') == 'pm-bora' and remessa.configurar_pares() == 0, 'remessas Câmara → Prefeitura pelo banco local')
n_tent = db.um(db.PLATAFORMA, 'SELECT count(*) n FROM login_tentativas')['n']
adm = TestClient(app, base_url='http://pmbora.localhost')
r = entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
checa('Visão geral' in r.text, 'login no painel do nó')
checa(db.um(LOCAL, 'SELECT count(*) n FROM login_tentativas')['n'] >= 1 and db.um(db.PLATAFORMA, 'SELECT count(*) n FROM login_tentativas')['n'] == n_tent, 'tentativa de login gravada no banco local')
t = adm.get('/admin/integracoes?fonte=fiorilli').text
checa('Sistema contábil (Fiorilli)' in t and 'Agenda de execução' in t, 'integrações do painel lidas do banco local')
checa(TestClient(app, base_url='http://gestao.localhost').get('/login').status_code == 404, 'nó não serve o console')
import contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    provision.atualizar()
checa(f'{LOCAL} (banco local do nó)' in buf.getvalue() and 'plataforma: migrações' not in buf.getvalue() and 'pm-bora (bd_pm_bora)' in buf.getvalue(), 'provision no nó: banco local e bancos dos órgãos, sem o controle')

# ---------- 5. de volta ao papel "tudo" ----------
config.PAPEL = 'tudo'; db.LOCAL = db.PLATAFORMA; web.limpar_cache(); L._memo.clear()
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=NULL WHERE id IN (%s,%s)', (PM['id'], CM['id']))
checa([(f['slug'], f['fonte'], json.dumps(f['params'], sort_keys=True)) for f in worker.fontes_ativas()] == antes and pt.get('/').status_code == 200, 'papel "tudo" de volta: igual a antes')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('nó local: tudo ok')
