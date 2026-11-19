# Pedido de 19/11/2026: excluir órgão e nó PELA GESTÃO, com backup final no nó e só o registro na gestão. Relatórios dos nós
# SIMULADOS; órgão e domínio fictícios, IPs de documentação (RFC 5737). Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_remocoes.py
import os, re, sys, time
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, relatorio as RL, ativacao as AT, remocoes as RM, mudancas as MU
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apoio
from apoio import entrar, tok
from app.security import totp

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
IP = '203.0.113.40'
DNS = {}
AT.resolver = lambda d: DNS.get(d, [])
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
def codigo():
    time.sleep(31)  # um código do autenticador não vale duas vezes
    return totp(apoio.SEGREDOS['gestor@gestao.localhost'])
L.criar_no('no-rm.exemplo.test'); L.criar_no('no-nunca.exemplo.test', 'nunca')
A = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-rm.exemplo.test'")
N = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-nunca.exemplo.test'")
con.post('/orgaos/novo', data={'csrf': tok(con, '/orgaos/novo'), 'tipo': 'legislativo', 'ibge': '3599953', 'municipio': 'Município Exemplo Remoção', 'uf': 'SP',
                               'dominio': 'cmrm.exemplo.com', 'email_admin': 'admin@cmrm.exemplo.com', 'sistema': 'nenhum', 'no_id': str(A['id'])})
O = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='cmrm.exemplo.com'")
U = f"/orgao/{O['id']}"
DNS['cmrm.exemplo.com'] = [IP]
def rel(no, **k):
    base = {'v': 1, 'versao': 'teste', 'ip': IP, 'pasta': '/opt/portal_web', 'orgaos': {}, 'ativacoes': [], 'tarefas': []}
    base.update(k)
    return RL.receber(db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (no['id'],)), base)
def rem():
    return RM.ultima(orgao_id=O['id'])
def tar(r):
    return db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE remocao_id=%s ORDER BY id DESC LIMIT 1', (r['id'],))
def excluir(**k):
    d = dict({'csrf': tok(con, U), 'slug': O['slug'], 'minha_senha': 'gestorforte1234', 'codigo': '000000'}, **k)
    return con.post(f'{U}/excluir', data=d, follow_redirects=True)
rel(A, orgaos={O['slug']: {}})

# 1. recusas: identificador errado, senha errada, piloto desta VPS
checa('digite o identificador' in excluir(slug='errado').text and not rem(), 'identificador errado: nada começa')
checa('senha não confere' in excluir(minha_senha='errada').text and not rem(), 'senha errada: nada começa')
P = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
ok, msg = RM.iniciar_orgao(P, 'teste')
checa(not ok and 'nesta VPS' in msg, 'órgão desta VPS (piloto): não é excluído pelo console')
checa('Excluir este órgão (com backup final)' in con.get(U).text and 'não é excluído pelo console' in con.get(f"/orgao/{P['id']}").text, 'tela: opção só para órgão em nó')

# 2. domínio no ar: tira do ar; depois tarefa "excluir_orgao"; erro no nó: nada apagado; encerrar
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=TRUE WHERE id=%s', (O['id'],))
r = excluir(codigo=codigo())
a = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (O['id'],))
checa(rem()['situacao'] == 'retirando' and a['acao'] == 'desativar' and 'Exclusão iniciada' in r.text, 'domínio no ar: exclusão começa tirando do ar')
rel(A, orgaos={O['slug']: {}}, ativacoes=[{'id': a['id'], 'situacao': 'desativado', 'passos': []}])
t = tar(rem())
checa(rem()['situacao'] == 'backup' and t['tipo'] == 'excluir_orgao' and t['params']['slug'] == O['slug'] and t['params']['pasta'].startswith('/var/backups/portal-removidos/')
      and t['params']['pasta'].endswith(f"orgao-{O['slug']}"), 'fora do ar: tarefa de backup final e exclusão para o nó')
checa('aguardando o nó' in con.get(U).text or 'na fila' in con.get(U).text, 'tela do órgão mostra o andamento')
rel(A, orgaos={O['slug']: {}}, tarefas=[{'id': t['id'], 'situacao': 'erro', 'passos': [], 'mensagem': 'o backup final não foi feito: nada foi apagado'}])
checa(rem()['situacao'] == 'erro' and db.um(db.PLATAFORMA, 'SELECT 1 x FROM orgaos WHERE id=%s', (O['id'],)), 'erro no nó: o órgão continua na gestão')
r = con.post(f"/remocoes/{rem()['id']}", data={'csrf': tok(con, '/remocoes'), 'acao': 'encerrar'}, follow_redirects=True)
checa(rem()['situacao'] == 'cancelada' and 'nada foi apagado' in r.text.lower(), 'encerrar: registrado, nada apagado')

# 3. de novo, até o fim: o cadastro some e fica só o registro com o backup
r = excluir(codigo=codigo())
t = tar(rem())
res = {'pasta': rem()['pasta'], 'arquivos': [{'nome': f"orgao-{O['slug']}.tgz", 'bytes': 2_500_000, 'sha256': 'a' * 64}]}
rel(A, orgaos={O['slug']: {}}, tarefas=[{'id': t['id'], 'situacao': 'ok', 'passos': [{'em': '2026-11-19T10:00:00-03:00', 'texto': 'backup final conferido'}], 'mensagem': 'órgão excluído deste nó', 'resultado': res}])
R = db.um(db.PLATAFORMA, 'SELECT * FROM remocoes WHERE id=%s', (rem()['id'],)) if rem() else None
checa(R and R['situacao'] == 'concluida' and R['backup'] == res and R['detalhes']['dominio'] == 'cmrm.exemplo.com', 'concluída: registro com o backup e os dados do órgão')
for t_, col in (('orgaos', 'id'), ('orgao_modulos', 'orgao_id'), ('contratos', 'orgao_id'), ('ordens', 'orgao_id'), ('ativacoes', 'orgao_id'), ('fontes', 'orgao_id')):
    checa(db.um(db.PLATAFORMA, f'SELECT count(*) n FROM {t_} WHERE {col}=%s', (O['id'],))['n'] == 0, f'cadastro apagado: {t_}')
t = con.get('/remocoes').text
checa('cmrm.exemplo.com' in t and 'orgao-' + O['slug'] + '.tgz' in t and '2.4 MB' in t and 'Concluída' in t and 'rm -rf ' + R['pasta'] in t, 'Remoções: o quê, onde está o backup e como apagá-lo')
con.post(f"/remocoes/{R['id']}", data={'csrf': tok(con, '/remocoes'), 'acao': 'backup_apagado'}, follow_redirects=True)
checa(db.um(db.PLATAFORMA, 'SELECT backup_apagado_em FROM remocoes WHERE id=%s', (R['id'],))['backup_apagado_em'] and 'backup apagado em' in con.get('/remocoes').text, 'registrar que o backup foi apagado')

# 4. nós: com órgão recusa; nunca instalado sai direto; instalado faz backup e se desinstala
L.criar_no('no-ocupado.exemplo.test'); B = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-ocupado.exemplo.test'")
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (B['id'], P['id']))
ok, msg = RM.iniciar_no(B, 'teste')
checa(not ok and 'ainda hospeda' in msg, 'nó com órgão: recusado')
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=NULL WHERE id=%s', (P['id'],))
def excluir_no(no, **k):
    d = dict({'csrf': tok(con, '/nos'), 'nome': no['nome'], 'minha_senha': 'gestorforte1234', 'codigo': '000000'}, **k)
    return con.post(f"/nos/{no['id']}/excluir", data=d, follow_redirects=True)
checa('digite o nome dele' in excluir_no(N, nome='outro').text and db.um(db.PLATAFORMA, 'SELECT 1 x FROM nos WHERE id=%s', (N['id'],)), 'excluir nó: nome errado recusa')
r = excluir_no(N, codigo=codigo())
checa('nunca tinha sido instalado' in r.text and not db.um(db.PLATAFORMA, 'SELECT 1 x FROM nos WHERE id=%s', (N['id'],))
      and RM.ultima(no_id=N['id'])['situacao'] == 'concluida', 'nó nunca instalado: sai direto, com registro')
rel(A)  # A sem órgãos agora
r = excluir_no(A, codigo=codigo())
ra = RM.ultima(no_id=A['id']); t = tar(ra)
checa(ra['situacao'] == 'backup' and t['tipo'] == 'desinstalar_no' and t['params']['pasta'].startswith('/var/backups/portal-removidos/'), 'nó instalado: tarefa de backup final e desinstalação')
rel(A, tarefas=[{'id': t['id'], 'situacao': 'ok', 'passos': [], 'mensagem': 'remoção agendada', 'resultado': {'pasta': ra['pasta'], 'arquivos': [{'nome': 'env', 'bytes': 900, 'sha256': 'b' * 64}]}}])
checa(RM.ultima(no_id=A['id'])['situacao'] == 'concluida' and not db.um(db.PLATAFORMA, 'SELECT 1 x FROM nos WHERE id=%s', (A['id'],)), 'nó desinstalado: cadastro apagado, registro fica')
checa('no-rm.exemplo.test' in con.get('/remocoes').text and 'href="/remocoes"' in con.get('/nos').text, 'Remoções no menu e com o nó')
checa(sum(1 for x in db.todos(db.PLATAFORMA, "SELECT acao FROM log_console WHERE acao LIKE '%%exclusão%%'")) >= 3, 'exclusões no registro do console')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
