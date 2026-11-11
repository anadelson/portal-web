# Separação gestão × portais, etapa A4 (11/11/2026): relatório do nó e publicação de domínio de órgão hospedado em nó.
# Órgãos e domínios FICTÍCIOS; DNS e IPs simulados (faixas de documentação RFC 5737). Nada toca nginx ou certificados.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_relatorio.py
import io, contextlib, json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, ordens as OR, relatorio as RL, ativacao as AT, web, provision
from app.coletores import comum
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
GESTAO_IP, NO_IP = '203.0.113.10', '203.0.113.20'
DNS = {}
AT.resolver = lambda d: DNS.get(d, [])
AT.vps_ip = lambda: os.environ.get('VPS_IP') or GESTAO_IP  # no nó, o IP do .env do nó

con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
token = L.criar_no('no-a4.exemplo.test')
no = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-a4.exemplo.test'")
outro_tok = L.criar_no('outro-a4.exemplo.test')
outro = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='outro-a4.exemplo.test'")
r = con.post('/orgaos/novo', data={'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599951', 'municipio': 'Município Exemplo A4', 'uf': 'SP',
                                   'dominio': 'pma4.exemplo.com', 'email_admin': 'admin@pma4.exemplo.com', 'sistema': 'nenhum', 'no_id': str(no['id'])})
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pma4.exemplo.com'")
checa(o and o['no_id'] == no['id'], 'órgão do nó cadastrado')
U = f"/orgao/{o['id']}"
imp, pub = L.garantir_chaves()

# ---------- 1. sem relatório, o console não sabe o IP do nó ----------
DNS['pma4.exemplo.com'] = [NO_IP]
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True)
checa('ainda não informou o IP' in r.text and not db.um(db.PLATAFORMA, 'SELECT 1 FROM ativacoes WHERE orgao_id=%s', (o['id'],)), 'sem relatório do nó: pedido recusado')

# ---------- 2. nó simulado: banco local, licenças, ordens e relatório ----------
LOCAL = 'no_local_a4'
provision.criar_banco(LOCAL); provision.aplicar(LOCAL, provision.MIG_LOCAL)
def como_gestao(f, *a):
    papel, loc = config.PAPEL, db.LOCAL
    config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA
    try:
        return f(*a)
    finally:
        config.PAPEL, db.LOCAL = papel, loc
def no_mode():
    config.PAPEL, db.LOCAL = 'no', LOCAL; web.limpar_cache(); L._memo.clear()
def gestao_mode():
    config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA; web.limpar_cache(); L._memo.clear()
L.buscar_na_gestao = lambda: como_gestao(L.entregar, no)
OR.buscar_na_gestao = lambda: {'ordens': como_gestao(OR.para_no, no)}
OR.devolver_na_gestao = lambda oid, ok, res: como_gestao(OR.informar, no, oid, ok, res)
RL.enviar_na_gestao = lambda rel: {'ativacoes': como_gestao(RL.receber, no, json.loads(json.dumps(rel, default=str)))}
config.GESTAO_URL, config.NO_TOKEN, config.LICENCA_CHAVE_PUBLICA = 'https://gestao.exemplo.test', token, pub
os.environ['VPS_IP'] = NO_IP
no_mode()
checa(L.puxar() == '1 licença(s) aceitas' and OR.puxar() == '1 ordem(ns) executada(s)', 'nó cria o órgão (licença e ordem)')
comum.registrar(o['slug'], 'siconfi:extrato', False, 0, 'HTTP 502 (exemplo)')
rel = RL.montar()
checa(rel['ip'] == NO_IP and rel['orgaos'][o['slug']]['licenca_valida'] and rel['orgaos'][o['slug']]['falhas_24h'] == 1 and rel['disco'], 'relatório: IP, licença, falhas e disco')
txt = json.dumps(rel, default=str)
checa('admin@pma4' not in txt and 'senha' not in txt.lower() and not re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', txt), 'relatório sem dados pessoais nem senha')
checa(RL.enviar().startswith('relatório entregue'), 'relatório entregue à gestão')
gestao_mode()
n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (no['id'],))
checa(n['relatorio_em'] and n['relatorio']['ip'] == NO_IP and AT.ip_do_no(no['id']) == NO_IP, 'gestão guarda o relatório e o IP do nó')
t = con.get('/nos').text
checa(NO_IP in t and 'GB livres' in t and '1 falha(s) de coleta em 24 h' in t, 'console mostra o relatório do nó')
t = con.get(U).text
checa('No nó (relatório de' in t and 'siconfi:extrato' in t and 'HTTP 502 (exemplo)' in t, 'página do órgão mostra as coletas no nó')

# ---------- 3. publicar domínio do órgão do nó ----------
DNS['pma4.exemplo.com'] = [GESTAO_IP]
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True)
checa('ainda não aponta só para o nó' in r.text, 'DNS apontando para a gestão (e não para o nó): recusado')
DNS['pma4.exemplo.com'] = [NO_IP]
checa('aponta para a VPS' in con.get(U).text, 'console confere o DNS contra o IP do nó')
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True)
a = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
checa('Pedido enviado ao nó' in r.text and a and a['situacao'] == 'pendente', 'pedido registrado no console e enviado ao nó')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM ordens WHERE tipo='dominio' AND no_id=%s AND situacao='pendente'", (no['id'],)), 'ordem "dominio" na fila do nó')
def roda(*args):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        cod = AT.main(list(args))
    return cod, b.getvalue()
checa(str(a['id']) not in roda('pendentes')[1], 'ativador desta VPS ignora o pedido do órgão do nó')
checa('pma4.exemplo.com' not in roda('vhost')[1], 'vhost desta VPS não leva o órgão do nó')
# o nó recebe, o ativador do nó publica, os passos voltam
no_mode()
checa(OR.puxar() == '1 ordem(ns) executada(s)', 'nó recebe o pedido')
checa(f"{a['id']}\tativar\tpma4.exemplo.com" in roda('pendentes')[1], 'pedido na fila do ativador do nó (mesmo id)')
checa(roda('validar', str(a['id'])) == (0, 'ok\n'), 'nó valida o pedido (domínio da licença, DNS no IP do nó)')
checa('server_name pma4.exemplo.com;' in roda('vhost', '--incluir', str(a['id']))[1], 'vhost do nó com o domínio novo')
roda('passo', str(a['id']), "Pedindo o certificado ao Let's Encrypt")
checa(RL.com_pressa(), 'com pedido em andamento, o relatório vai a cada minuto')
RL.enviar()
gestao_mode()
checa(db.um(db.PLATAFORMA, 'SELECT situacao FROM ativacoes WHERE id=%s', (a['id'],))['situacao'] == 'processando' and 'Pedindo o certificado' in con.get(U).text, 'passo do nó aparece no console')
no_mode()
roda('concluir', str(a['id']), 'no_ar', 'No ar em https://pma4.exemplo.com')
checa('server_name pma4.exemplo.com;' in roda('vhost')[1] and db.um(LOCAL, "SELECT 1 FROM dominios_publicados WHERE dominio='pma4.exemplo.com'"), 'nó publica o domínio')
RL.enviar()
gestao_mode()
checa(db.um(db.PLATAFORMA, 'SELECT vhost_ativo FROM orgaos WHERE id=%s', (o['id'],))['vhost_ativo'], 'console marca o domínio como no ar')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM log_console WHERE quem='ativador do nó no-a4.exemplo.test' AND acao LIKE %s", ('%pma4.exemplo.com%no_ar%',)), 'registro do console com o ativador do nó')
checa('no ar pelo console' in con.get(U).text and 'Tirar do ar' in con.get(U).text, 'console mostra "no ar" e "Tirar do ar"')
checa('pma4.exemplo.com' not in roda('vhost')[1], 'vhost desta VPS continua sem o órgão do nó')
# outro nó não mexe no pedido deste nó
falso = {'ativacoes': [{'id': a['id'], 'situacao': 'erro', 'passos': [], 'mensagem': 'tentativa de outro nó'}]}
checa(RL.receber(outro, falso) == 0 and db.um(db.PLATAFORMA, 'SELECT situacao FROM ativacoes WHERE id=%s', (a['id'],))['situacao'] == 'no_ar', 'relatório de outro nó não mexe no pedido')
api = TestClient(app, base_url='http://gestao.localhost')
checa(api.post('/api/no/relatorio', json={}).status_code == 401, 'relatório sem token: 401')
checa(api.post('/api/no/relatorio', content=b'x' * (RL.MAX_BYTES + 10), headers={'Authorization': f'Bearer {token}'}).status_code == 413, 'relatório grande demais: recusado')
checa(api.post('/api/no/relatorio', content=b'[1,2]', headers={'Authorization': f'Bearer {token}'}).status_code == 400, 'relatório inválido: recusado')
# tirar do ar
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'desativar'}, follow_redirects=True)
d = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
checa(d['acao'] == 'desativar' and 'enviado ao nó' in r.text, 'pedido de retirada enviado ao nó')
no_mode()
OR.puxar()
checa('pma4.exemplo.com' not in roda('vhost', '--excluir', str(d['id']))[1], 'vhost do nó sem o domínio retirado')
roda('concluir', str(d['id']), 'desativado', 'Retirado do ar')
RL.enviar()
gestao_mode()
checa(not db.um(db.PLATAFORMA, 'SELECT vhost_ativo FROM orgaos WHERE id=%s', (o['id'],))['vhost_ativo'], 'console marca como fora do ar')

# ---------- 4. papel "tudo": ativação desta VPS igual a antes ----------
del os.environ['VPS_IP']
checa(TestClient(app, base_url='http://pmbora.localhost').get('/').status_code == 200, 'papel "tudo" de volta')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('relatório do nó: tudo ok')
