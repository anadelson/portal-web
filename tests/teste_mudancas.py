# Pedido de 19/11/2026: a GESTÃO conduz a mudança de um órgão entre dois nós da mesma VPS e a instalação de um nó novo,
# sem terminal (tarefas executadas pelo ativador do nó; os relatórios dos nós são SIMULADOS aqui). Órgão e domínio fictícios,
# IPs de documentação (RFC 5737). Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_mudancas.py
import json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, relatorio as RL, ativacao as AT, mudancas as MU, tarefas as TF, provision, credenciais as CR
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apoio
from apoio import entrar, tok
from app.security import totp

from cryptography.fernet import Fernet
config.CHAVE_CREDENCIAIS = Fernet.generate_key().decode()   # chave de TESTE (a mesma na gestão e no nó, como no .env)
erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
IP = '203.0.113.30'
DNS = {}
AT.resolver = lambda d: DNS.get(d, [])
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
L.criar_no('no-pm.exemplo.test'); L.criar_no('no-cm.exemplo.test', 'camara'); L.criar_no('no-longe.exemplo.test', 'longe')
A = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-pm.exemplo.test'")
B = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-cm.exemplo.test'")
X = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-longe.exemplo.test'")
r = con.post('/orgaos/novo', data={'csrf': tok(con, '/orgaos/novo'), 'tipo': 'legislativo', 'ibge': '3599952', 'municipio': 'Município Exemplo Mudança', 'uf': 'SP',
                                   'dominio': 'cmmud.exemplo.com', 'email_admin': 'admin@cmmud.exemplo.com', 'sistema': 'nenhum', 'no_id': str(A['id'])})
O = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='cmmud.exemplo.com'")
U = f"/orgao/{O['id']}"
DNS['cmmud.exemplo.com'] = [IP]
def rel(no, **k):
    """Relatório simulado do nó (a versão nova manda a chave "tarefas")."""
    base = {'v': 1, 'versao': 'teste', 'ip': IP, 'pasta': '/opt/portal_web', 'instancia': '', 'orgaos': {}, 'ativacoes': [], 'tarefas': []}
    base.update(k)
    return RL.receber(db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (no['id'],)), base)
def mud():
    return MU.ativa(O['id'])
def ativ(no_id=None):
    return db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (O['id'],))
def tarefa(tipo):
    return db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE mudanca_id=%s AND tipo=%s ORDER BY id DESC LIMIT 1', (mud()['id'], tipo))
def post(dados):
    return con.post(f'{U}/mudanca', data=dict({'csrf': tok(con, U)}, **dados), follow_redirects=True)

# 1. sem relatório (versão antiga) não dá; VPS diferente não dá
checa('precisam estar na mesma VPS' in post({'acao': 'iniciar', 'para_no': B['id'], 'confirmo': '1'}).text, 'sem relatório: mudança recusada')
rel(A, orgaos={O['slug']: {}}); rel(B, pasta='/opt/portal_web-camara', instancia='camara'); rel(X, ip='198.51.100.9')
checa([n['id'] for n in MU.destinos(O)] == [B['id']], 'destinos: só o nó da mesma VPS')
checa('precisam estar na mesma VPS' in post({'acao': 'iniciar', 'para_no': X['id'], 'confirmo': '1'}).text, 'nó de outra VPS: recusado')
checa('Marque a confirmação' in post({'acao': 'iniciar', 'para_no': B['id']}).text and not mud(), 'sem a confirmação: nada começa')
t = con.get(U).text
checa('Mudar de nó pela gestão' in t and 'Começar a mudança' in t and 'no-cm.exemplo.test (instância camara)' in t, 'tela: opção de mudar de nó')

# 2. domínio no ar: a mudança começa tirando do ar no nó de origem
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=TRUE WHERE id=%s', (O['id'],))
r = post({'acao': 'iniciar', 'para_no': B['id'], 'confirmo': '1'})
m = mud(); a = ativ()
checa(m and m['situacao'] == 'retirando' and m['publicar'] and a['acao'] == 'desativar' and a['situacao'] == 'pendente', 'início: pede ao nó de origem para tirar o domínio do ar')
checa(db.um(db.PLATAFORMA, "SELECT 1 x FROM ordens WHERE no_id=%s AND tipo='dominio' AND payload->>'acao'='desativar'", (A['id'],)), 'ordem de retirada vai para o nó de origem')
checa('já existe uma mudança' in post({'acao': 'iniciar', 'para_no': B['id'], 'confirmo': '1'}).text.lower(), 'segunda mudança ao mesmo tempo: recusada')
MU.avancar_todas()
checa(mud()['situacao'] == 'retirando' and db.um(db.PLATAFORMA, 'SELECT count(*) n FROM ativacoes WHERE orgao_id=%s', (O['id'],))['n'] == 1, 'esperando o nó: não repete o pedido')

# 3. nó A tira do ar → exportar; nó A exporta → importar no B
rel(A, orgaos={O['slug']: {}}, ativacoes=[{'id': a['id'], 'situacao': 'desativado', 'passos': []}])
MU.avancar_todas()
te = tarefa('exportar')
checa(mud()['situacao'] == 'exportando' and te and te['no_id'] == A['id'] and te['params'] == {'slug': O['slug'], 'arquivo': f"/var/lib/portal-transferencias/mover-{O['slug']}-{mud()['id']}.tgz"},
      'domínio fora do ar: tarefa "exportar" para o nó de origem')
o_ = db.um(db.PLATAFORMA, "SELECT payload FROM ordens WHERE no_id=%s AND tipo='tarefa' ORDER BY id DESC LIMIT 1", (A['id'],))
checa(o_ and o_['payload']['tipo'] == 'exportar' and o_['payload']['tarefa_id'] == te['id'], 'ordem "tarefa" assinada para o nó de origem')
rel(A, orgaos={O['slug']: {}}, tarefas=[{'id': te['id'], 'situacao': 'processando', 'passos': [{'em': '2026-11-19T07:00:00-03:00', 'texto': 'banco copiado'}]}])
checa(mud()['situacao'] == 'exportando' and 'banco copiado' in con.get(U).text, 'passos da tarefa aparecem na tela do órgão')
rel(A, orgaos={O['slug']: {}}, tarefas=[{'id': te['id'], 'situacao': 'ok', 'passos': [], 'mensagem': 'arquivo gerado'}])
ti = tarefa('importar')
checa(mud()['situacao'] == 'importando' and ti and ti['no_id'] == B['id'], 'exportado: tarefa "importar" para o nó de destino')
checa(rel(X, ip='198.51.100.9', tarefas=[{'id': ti['id'], 'situacao': 'ok', 'passos': []}]) == 0 and tarefa('importar')['situacao'] == 'pendente', 'relatório de OUTRO nó não mexe na tarefa')

# 4. importado → hospedagem → espera a licença no destino → publica no destino → concluída
rel(B, tarefas=[{'id': ti['id'], 'situacao': 'ok', 'passos': [], 'mensagem': 'todas as tabelas conferem'}])
checa(mud()['situacao'] == 'publicando' and db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (O['id'],))['no_id'] == B['id'], 'importado: hospedagem passa para o nó de destino')
checa(ativ()['acao'] == 'desativar', 'sem a licença no destino: ainda não publica')
rel(B, orgaos={O['slug']: {}}, tarefas=[])
MU.avancar_todas(); a2 = ativ()
checa(a2['acao'] == 'ativar' and db.um(db.PLATAFORMA, "SELECT 1 x FROM ordens WHERE no_id=%s AND tipo='dominio' AND payload->>'acao'='ativar'", (B['id'],)), 'licença no destino: publicação pedida ao nó de destino')
rel(B, orgaos={O['slug']: {}}, ativacoes=[{'id': a2['id'], 'situacao': 'no_ar', 'passos': []}])
MU.avancar_todas()
t = con.get(U).text
checa(mud()['situacao'] == 'concluida' and db.um(db.PLATAFORMA, 'SELECT vhost_ativo FROM orgaos WHERE id=%s', (O['id'],))['vhost_ativo'], 'domínio no ar no destino: mudança concluída')
checa('Confira o portal e o painel' in t and 'Apagar da origem' in t and 'Desfazer' in t, 'tela: conferir, limpar ou desfazer')

# 5. limpar: exige o identificador; tarefa "limpar" no nó de origem; depois, finalizada
checa('digite o identificador' in post({'acao': 'limpar', 'slug': 'errado'}).text and mud()['situacao'] == 'concluida', 'limpar sem o identificador certo: recusado')
post({'acao': 'limpar', 'slug': O['slug']})
tl = tarefa('limpar')
checa(mud()['situacao'] == 'limpando' and tl and tl['no_id'] == A['id'], 'limpar: tarefa para o nó de origem')
rel(A, tarefas=[{'id': tl['id'], 'situacao': 'ok', 'passos': [], 'mensagem': 'linhas do banco local do órgão apagadas'}])
checa(mud()['situacao'] == 'finalizada' and 'Finalizada' in con.get(U).text, 'limpeza feita: mudança finalizada')
checa('Tarefa' in ' '.join(x['acao'] for x in db.todos(db.PLATAFORMA, "SELECT acao FROM log_console WHERE acao LIKE 'Tarefa %%'")), 'tarefas concluídas ficam no registro do console')

# 6. volta para A (agora a origem é B) e erro na exportação: para e explica; "encerrar" deixa o órgão onde está
rel(B, orgaos={O['slug']: {}}); db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=FALSE WHERE id=%s', (O['id'],))
O = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (O['id'],))
post({'acao': 'iniciar', 'para_no': A['id'], 'confirmo': '1'})
te = tarefa('exportar')
checa(mud()['situacao'] == 'exportando' and te['no_id'] == B['id'], 'sem domínio no ar: começa direto pela exportação')
rel(B, tarefas=[{'id': te['id'], 'situacao': 'erro', 'passos': [], 'mensagem': 'pg_dump do banco falhou'}])
m = mud()
checa(m['situacao'] == 'erro' and 'pg_dump do banco falhou' in m['mensagem'] and 'Nada foi apagado' in m['mensagem'], 'erro numa tarefa: para e explica')
checa('Encerrar / voltar para a origem' in con.get(U).text, 'tela: opção de encerrar')
post({'acao': 'desfazer'})
checa(mud()['situacao'] == 'cancelada' and db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (O['id'],))['no_id'] == B['id'], 'encerrar depois de erro: órgão continua na origem')

# 7. desfazer depois de concluída: volta para a origem (domínio retirado do destino e publicado de novo na origem)
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=TRUE WHERE id=%s', (O['id'],))
post({'acao': 'iniciar', 'para_no': A['id'], 'confirmo': '1'})
rel(B, orgaos={O['slug']: {}}, ativacoes=[{'id': ativ()['id'], 'situacao': 'desativado', 'passos': []}])
rel(B, tarefas=[{'id': tarefa('exportar')['id'], 'situacao': 'ok', 'passos': []}])
rel(A, orgaos={O['slug']: {}}, tarefas=[{'id': tarefa('importar')['id'], 'situacao': 'ok', 'passos': []}])
rel(A, orgaos={O['slug']: {}}, ativacoes=[{'id': ativ()['id'], 'situacao': 'no_ar', 'passos': []}])
checa(mud()['situacao'] == 'concluida' and db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (O['id'],))['no_id'] == A['id'], 'mudança de volta concluída')
post({'acao': 'desfazer'})
checa(mud()['situacao'] == 'desfazendo' and ativ()['acao'] == 'desativar', 'desfazer: tira do ar no destino')
rel(A, orgaos={O['slug']: {}}, ativacoes=[{'id': ativ()['id'], 'situacao': 'desativado', 'passos': []}])
MU.avancar_todas()
checa(db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (O['id'],))['no_id'] == B['id'], 'desfazer: hospedagem de volta à origem')
rel(B, orgaos={O['slug']: {}}); MU.avancar_todas()
checa(ativ()['acao'] == 'ativar', 'desfazer: publica de novo na origem')
rel(B, orgaos={O['slug']: {}}, ativacoes=[{'id': ativ()['id'], 'situacao': 'no_ar', 'passos': []}])
checa(mud()['situacao'] == 'desfeita', 'desfeita: o órgão voltou e está no ar')

# 8. fila de tarefas no NÓ (banco local de teste): enfileirar, pendentes, passos, conclusão, relatório; recusas
LOC = 'no_local_tarefas'
provision.criar_banco(LOC); provision.aplicar(LOC, provision.MIG_LOCAL)
db_local, db.LOCAL = db.LOCAL, LOC
checa(TF.enfileirar({'tarefa_id': 901, 'tipo': 'exportar', 'params': {'slug': 'cm-x', 'arquivo': '/var/lib/portal-transferencias/mover-cm-x-1.tgz'}}).startswith('tarefa 901'), 'nó: tarefa na fila')
checa(TF.enfileirar({'tarefa_id': 901, 'tipo': 'exportar', 'params': {'slug': 'cm-x', 'arquivo': '/var/lib/portal-transferencias/mover-cm-x-1.tgz'}}) == 'tarefa já estava na fila', 'nó: ordem repetida não duplica')
for ruim in ({'tipo': 'apagar_tudo', 'params': {}}, {'tipo': 'exportar', 'params': {'slug': 'x; rm', 'arquivo': '/etc/passwd'}},
             {'tipo': 'importar', 'params': {'slug': 'cm-x', 'arquivo': '/var/lib/portal-transferencias/../../etc/x.tgz'}}):
    try:
        TF.enfileirar(dict(ruim, tarefa_id=902)); checa(False, f'nó: recusa {ruim}')
    except ValueError:
        pass
tok_cif = CR.cifrar('no', 'token-ficticio-do-no-novo-0123456789abcdef')
TF.enfileirar({'tarefa_id': 903, 'tipo': 'instalar_instancia', 'params': {'instancia': 'camara', 'nome': 'no-cm.exemplo.test', 'token': tok_cif}})
papel, config.PAPEL = config.PAPEL, 'no'
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    TF.main(['pendentes'])
linhas = [l.split('\t') for l in buf.getvalue().splitlines()]
checa([l[0] for l in linhas] == ['901', '903'] and 'token' not in linhas[1][2], f'nó: pendentes para o ativador (sem o token) {linhas}')
TF.main(['passo', '901', 'banco copiado']); TF.main(['concluir', '901', 'ok', 'arquivo gerado'])
rr = {t['id']: t for t in TF.para_relatorio()}
checa(rr[901]['situacao'] == 'ok' and rr[901]['passos'][0]['texto'] == 'banco copiado' and rr[903]['situacao'] == 'processando', 'nó: passos e resultado no relatório')
config.GESTAO_URL, config.LICENCA_CHAVE_PUBLICA = 'https://gestao.exemplo.test', 'chave-publica-teste'
env = TF.env_instancia(903)
checa('NO_NOME=no-cm.exemplo.test' in env and 'NO_TOKEN=token-ficticio-do-no-novo-0123456789abcdef' in env and 'INSTANCIA=camara' in env
      and f"SECRET_KEY={config.env('SECRET_KEY')}" in env, 'nó: configuração da instância nova (chaves iguais + identidade nova)')
checa(TF.em_andamento(), 'nó: tarefa em andamento acelera o relatório')
config.PAPEL, db.LOCAL = papel, db_local

# 9. instalar sem terminal: pede senha e 2FA; manda a tarefa ao nó escolhido com o token novo CIFRADO
UI = f"/nos/{B['id']}/instalar"
t = con.get(UI).text
checa('Instalar sem terminal' in t and 'no-pm.exemplo.test' in t, 'tela: instalar pela VPS de outro nó')
d = {'csrf': tok(con, UI), 'host': str(A['id']), 'minha_senha': 'errada', 'codigo': '000000'}
checa('Sua senha não confere' in con.post(f"/nos/{B['id']}/instalar-auto", data=d, follow_redirects=True).text, 'instalar sem terminal: senha errada recusa')
hash_antes = db.um(db.PLATAFORMA, 'SELECT token_hash FROM nos WHERE id=%s', (B['id'],))['token_hash']
d.update(csrf=tok(con, UI), minha_senha='gestorforte1234', codigo=totp(apoio.SEGREDOS['gestor@gestao.localhost']))
r = con.post(f"/nos/{B['id']}/instalar-auto", data=d, follow_redirects=True)
ti = db.um(db.PLATAFORMA, "SELECT * FROM tarefas WHERE tipo='instalar_instancia' ORDER BY id DESC LIMIT 1")
oi = db.um(db.PLATAFORMA, "SELECT payload FROM ordens WHERE tipo='tarefa' AND payload->>'tipo'='instalar_instancia' ORDER BY id DESC LIMIT 1")
checa('Pedido enviado ao nó no-pm.exemplo.test' in r.text and ti and ti['no_id'] == A['id'] and 'token' not in ti['params'] and ti['params']['instancia'] == 'camara', 'instalar sem terminal: tarefa para o nó escolhido (sem o token na tarefa)')
checa(oi and CR.decifrar(oi['payload']['params']['token']) and L.no_do_token(CR.decifrar(oi['payload']['params']['token'])[1])['id'] == B['id']
      and db.um(db.PLATAFORMA, 'SELECT token_hash FROM nos WHERE id=%s', (B['id'],))['token_hash'] != hash_antes, 'instalar sem terminal: token NOVO do nó vai cifrado na ordem')
checa('Pedido ' in con.get(UI).text, 'tela: acompanha o pedido de instalação')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
