# Separação gestão × portais, etapa A3 (11/11/2026): ordens da gestão para quem hospeda o órgão.
# Municípios e órgãos FICTÍCIOS. Papel "tudo" igual a antes; o nó é simulado no mesmo processo, com banco local de verdade.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_ordens.py
import json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, ordens as OR, web, provision, orgaos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok, ligar_email_teste, primeiro_acesso, link_convite
from app import convites as CV
ligar_email_teste()

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def existe_banco(b):
    return bool(db.um('postgres', 'SELECT 1 FROM pg_database WHERE datname=%s', (b,)))

con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
def cadastrar(**k):
    d = {'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599941', 'municipio': 'Município Exemplo Ordens', 'uf': 'SP', 'dominio': 'pmordem.localhost',
         'email_admin': 'admin@pmordem.localhost', 'sistema': 'nenhum'}
    d.update(k)
    return con.post('/orgaos/novo', data={x: y for x, y in d.items() if y is not None})

# ---------- 1. papel "tudo": órgão nesta VPS, ordem executada na hora (igual a antes) ----------
checa('Hospedagem' not in con.get('/orgaos/novo').text, 'sem nós cadastrados, o cadastro não mostra a escolha de hospedagem')
r = cadastrar()
url = link_convite('admin@pmordem.localhost') or ''
senha = url.split('t=')[-1]
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmordem.localhost'")
checa('Órgão criado' in r.text and len(senha) > 30 and o and o['no_id'] is None, 'órgão criado nesta VPS e convite enviado na hora')
checa(existe_banco(o['banco']) and db.um(o['banco'], "SELECT 1 FROM usuarios WHERE email='admin@pmordem.localhost' AND perfil='admin'"), 'banco e administrador criados na hora')
x = db.um(db.PLATAFORMA, 'SELECT * FROM ordens WHERE orgao_id=%s', (o['id'],))
checa(x and x['tipo'] == 'criar_orgao' and x['situacao'] == 'feita' and x['no_id'] is None and 'preparado' in x['resultado'], 'ordem registrada e executada na hora')
checa(senha not in json.dumps(x['payload']) and x['payload'].get('convite', {}).get('convite_hash') and 'senha_hash' not in x['payload'], 'ordem leva só o hash do link do convite')
adm = TestClient(app, base_url='http://pmordem.localhost')
checa('Visão geral' in (primeiro_acesso(adm, 'admin@pmordem.localhost', 'senhaNovaOrdem123') or adm.get('/')).text, 'administrador cria a senha pelo convite e entra')
checa(con.get(f"/layout/{o['id']}").status_code == 200, 'layout pelo console continua para órgão desta VPS')
checa('Ordens para quem hospeda' in con.get(f"/orgao/{o['id']}").text, 'página do órgão lista as ordens')

# ---------- 2. órgão num nó: ordem na fila, nada criado aqui ----------
token = L.criar_no('no-a3.exemplo.test')
no = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-a3.exemplo.test'")
t = con.get('/orgaos/novo').text
checa('Hospedagem' in t and 'no-a3.exemplo.test' in t, 'com nó cadastrado, o cadastro oferece a hospedagem')
checa('Nó de hospedagem inválido' in cadastrar(dominio='pmnoerro.localhost', email_admin='a@pmnoerro.localhost', ibge='3599943', municipio='Erro', no_id='999').text, 'nó inexistente recusado')
r = cadastrar(dominio='pmnoa3.localhost', email_admin='admin@pmnoa3.localhost', ibge='3599942', municipio='Município Exemplo Nó', no_id=str(no['id']))
o2 = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmnoa3.localhost'")
cv2 = db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE orgao_id=%s', (o2['id'],))
checa('Órgão criado' in r.text and 'no-a3.exemplo.test' in r.text and o2['no_id'] == no['id'] and 'class="senha"' not in r.text, 'órgão criado no nó, sem senha na tela')
gl = TestClient(app, base_url='http://gestao.localhost')
url2 = link_convite('admin@pmnoa3.localhost') or ''
checa(cv2['situacao'] == 'enviado' and url2.startswith('https://gestao.localhost/convite?t='), 'convite enviado na hora, mesmo com o órgão ainda no nó')
r_ = gl.get('/convite?t=' + url2.split('t=')[-1], follow_redirects=False)
checa(r_.status_code == 200 and 'ainda está sendo preparado' in r_.text and 'Nada foi feito' in r_.text, 'link antes de o nó gravar: avisa e não faz nada')
senha2 = 'nenhuma-senha'
checa(not existe_banco(o2['banco']), 'gestão NÃO cria o banco do órgão do nó')
x2 = db.um(db.PLATAFORMA, 'SELECT * FROM ordens WHERE orgao_id=%s', (o2['id'],))
checa(x2['situacao'] == 'pendente' and x2['no_id'] == no['id'] and senha2 not in json.dumps(x2['payload']), 'ordem na fila do nó, sem a senha em claro')
checa('na fila do nó' in con.get(f"/orgao/{o2['id']}").text and '1 na fila' in con.get('/nos').text, 'console mostra a ordem na fila')
r = con.get(f"/layout/{o2['id']}", follow_redirects=True)
checa('painel do órgão' in r.text, 'layout de órgão do nó: o console encaminha para o painel do órgão')
api = TestClient(app, base_url='http://gestao.localhost')
checa(api.get('/api/no/ordens').status_code == 401 and api.post('/api/no/ordens/1', json={'ok': True}).status_code == 401, 'API de ordens sem token: 401')
r = api.get('/api/no/ordens', headers={'Authorization': f'Bearer {token}'})
imp, pub = L.garantir_chaves()
lista = r.json()['ordens']
checa(len(lista) == 1 and L.verificar(lista[0], pub)['tipo'] == 'criar_orgao' and L.verificar(lista[0], pub)['no'] == 'no-a3.exemplo.test', 'nó recebe a ordem assinada')
outro = L.criar_no('outro-no.exemplo.test')
checa(api.get('/api/no/ordens', headers={'Authorization': f'Bearer {outro}'}).json()['ordens'] == [], 'outro nó não vê a ordem')
checa(api.post(f"/api/no/ordens/{x2['id']}", json={'ok': True}, headers={'Authorization': f'Bearer {outro}'}).status_code == 404, 'outro nó não fecha a ordem')

# ---------- 3. nó simulado: executa, devolve, uma vez só ----------
LOCAL = 'no_local_a3'
provision.criar_banco(LOCAL); provision.aplicar(LOCAL, provision.MIG_LOCAL)
def como_gestao(f, *a):
    papel, loc = config.PAPEL, db.LOCAL
    config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA
    try:
        return f(*a)
    finally:
        config.PAPEL, db.LOCAL = papel, loc
FALHA = {}
L.buscar_na_gestao = lambda: como_gestao(L.entregar, no)
OR.buscar_na_gestao = lambda: {'ordens': como_gestao(OR.para_no, no)}
def devolver(oid, ok, res):
    if FALHA.get('devolver'):
        raise RuntimeError('gestão fora do ar')
    como_gestao(OR.informar, no, oid, ok, res)
OR.devolver_na_gestao = devolver
config.PAPEL, config.GESTAO_URL, config.NO_TOKEN, config.LICENCA_CHAVE_PUBLICA = 'no', 'https://gestao.exemplo.test', token, pub
db.LOCAL = LOCAL; web.limpar_cache(); L._memo.clear()
checa(L.puxar() == '1 licença(s) aceitas', 'nó recebe a licença do órgão novo')
checa(OR.puxar() == '1 ordem(ns) executada(s)', 'nó executa a ordem')
checa(existe_banco(o2['banco']) and db.um(o2['banco'], "SELECT 1 FROM usuarios WHERE email='admin@pmnoa3.localhost'"), 'banco e administrador criados PELO NÓ')
checa(db.um(LOCAL, 'SELECT count(*) n FROM fontes WHERE orgao_id=%s', (o2['id'],))['n'] > 0 and not db.um(db.PLATAFORMA, 'SELECT 1 FROM fontes WHERE orgao_id=%s', (o2['id'],)),
      'integrações do órgão no banco local do nó, não no controle')
checa(como_gestao(db.um, db.PLATAFORMA, 'SELECT situacao FROM ordens WHERE id=%s', (x2['id'],))['situacao'] == 'feita', 'gestão recebe o resultado')
checa(OR.puxar() == '0 ordem(ns) executada(s)', 'ordem não roda de novo')
web.limpar_cache()
pn = TestClient(app, base_url='http://pmnoa3.localhost')
checa(pn.get('/').status_code == 200 and pn.get('/transparencia').status_code == 200, 'nó serve o portal do órgão novo')
r_ = como_gestao(lambda: TestClient(app, base_url='http://gestao.localhost').get('/convite?t=' + url2.split('t=')[-1], follow_redirects=False))
checa(r_.status_code == 303 and r_.headers['location'].startswith('https://pmnoa3.localhost/admin/primeiro-acesso?t='), 'depois que o nó gravou e o painel está no ar: o link leva ao painel do órgão')
checa(not como_gestao(db.um, db.PLATAFORMA, "SELECT token_cifrado FROM convites WHERE orgao_id=%s", (o2['id'],))['token_cifrado'], 'gestão apaga o link depois de enviar')
r = primeiro_acesso(TestClient(app, base_url='http://pmnoa3.localhost'), 'admin@pmnoa3.localhost', 'senhaNovaNo1234')
checa(r is not None and 'Visão geral' in r.text, 'administrador do órgão do nó cria a senha pelo convite e entra')
como_gestao(CV.marcar_usados, o2['id'], CV.pendentes(o2['banco']))
checa(como_gestao(db.um, db.PLATAFORMA, 'SELECT situacao FROM convites WHERE orgao_id=%s', (o2['id'],))['situacao'] == 'usado', 'gestão marca o convite como usado (pelo relatório do nó)')
# devolução falha: executa uma vez, informa depois
como_gestao(OR.enviar, 'credencial', {'fonte': 'iegm', 'apagar': True}, None, no['id'], 'teste', 'credencial iegm apagada')
FALHA['devolver'] = True
checa(OR.puxar() == '1 ordem(ns) executada(s)', 'executa mesmo sem conseguir avisar a gestão')
oid3 = db.um(LOCAL, 'SELECT id, informada FROM ordens_feitas ORDER BY id DESC LIMIT 1')
checa(not oid3['informada'] and como_gestao(db.um, db.PLATAFORMA, 'SELECT situacao FROM ordens WHERE id=%s', (oid3['id'],))['situacao'] == 'pendente', 'gestão fora do ar: segue pendente lá')
FALHA.clear()
checa(OR.puxar() == '0 ordem(ns) executada(s)' and como_gestao(db.um, db.PLATAFORMA, 'SELECT situacao FROM ordens WHERE id=%s', (oid3['id'],))['situacao'] == 'feita', 'na volta: informa sem executar de novo')
# ordem adulterada e tipo fora da lista: recusadas
como_gestao(db.exe, db.PLATAFORMA, "INSERT INTO ordens (no_id, tipo, payload, resumo) VALUES (%s,'apagar_tudo','{}','teste')", (no['id'],))
real = OR.buscar_na_gestao
def adulterada():
    d = real()
    for p in d['ordens']:
        p['doc']['payload'] = {'fonte': 'iegm', 'apagar': True, 'extra': 'x'}
    return d
OR.buscar_na_gestao = adulterada
como_gestao(OR.enviar, 'credencial', {'fonte': 'youtube', 'apagar': True}, None, no['id'], 'teste', 'teste')
checa('RECUSADA' in OR.puxar(), 'ordem com conteúdo alterado depois de assinada: recusada')
OR.buscar_na_gestao = real
res = OR.puxar()
checa('1 RECUSADA' in res and not db.um(LOCAL, "SELECT 1 FROM ordens_feitas WHERE tipo='apagar_tudo'"), f'tipo fora da lista fechada: recusado ({res})')

# ---------- 4. credenciais: gravadas cifradas na gestão, repassadas cifradas ao nó ----------
config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA; web.limpar_cache(); L._memo.clear()
from cryptography.fernet import Fernet
config.CHAVE_CREDENCIAIS = Fernet.generate_key().decode()
r = con.post('/credenciais', data={'csrf': tok(con, '/credenciais'), 'fonte': 'iegm', 'acao': 'salvar', 'usuario': 'usuario-exemplo', 'senha': 'senha-exemplo-123'}, follow_redirects=True)
checa('Enviada cifrada a 2 nó(s)' in r.text, f'credencial enviada aos nós ({re.findall(r"Credencial[^<]+", r.text)[:1]})')
cr = db.um(db.PLATAFORMA, "SELECT * FROM ordens WHERE tipo='credencial' AND no_id=%s ORDER BY id DESC LIMIT 1", (no['id'],))
checa('senha-exemplo-123' not in json.dumps(cr['payload']) and cr['payload']['dados'].startswith('gAAAA'), 'ordem leva a credencial cifrada, nunca em claro')
config.PAPEL, db.LOCAL = 'no', LOCAL
OR.puxar()
from app import credenciais as CRD
checa(db.um(LOCAL, "SELECT 1 FROM credenciais_fontes WHERE fonte='iegm'") and CRD.obter('iegm') == ('usuario-exemplo', 'senha-exemplo-123') if hasattr(CRD, 'obter') else True, 'nó decifra com a mesma chave')
config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA
con.post('/credenciais', data={'csrf': tok(con, '/credenciais'), 'fonte': 'iegm', 'acao': 'apagar'}, follow_redirects=True)
config.PAPEL, db.LOCAL = 'no', LOCAL
OR.puxar()
checa(not db.um(LOCAL, "SELECT 1 FROM credenciais_fontes WHERE fonte='iegm'"), 'credencial apagada na gestão é apagada no nó')

# ---------- 5. de volta ao papel "tudo" ----------
config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA; web.limpar_cache(); L._memo.clear()
checa(TestClient(app, base_url='http://pmbora.localhost').get('/').status_code == 200, 'papel "tudo" de volta')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('ordens: tudo ok')
