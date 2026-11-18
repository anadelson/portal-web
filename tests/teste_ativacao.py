# Etapa 2 (10/11/2026): ativação de domínio pelo console. O console só grava o pedido; o ativador da VPS executa.
# DNS simulado (nenhuma consulta real). Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_ativacao.py
import os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
import json
from app import db, ativacao as AT
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
VPS = '203.0.113.10'  # IP de documentação (RFC 5737)
DNS = {}
AT.vps_ip = lambda: VPS
AT.resolver = lambda d: DNS.get(d, [])

con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
r = con.post('/orgaos/novo', data={'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599921', 'municipio': 'Município da Ativação', 'uf': 'SP', 'dominio': 'pmativa.exemplo.com',
                                   'email_admin': 'admin@pmativa.exemplo.com', 'sistema': 'nenhum'})
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmativa.exemplo.com'")
checa(o and not o['vhost_ativo'], 'órgão novo nasce sem publicação')
U = f"/orgao/{o['id']}"

# ---------- DNS ainda não aponta ----------
DNS['pmativa.exemplo.com'] = ['198.51.100.7']
t = con.get(U).text
checa('Domínio e publicação' in t and 'ainda não aponta só para a VPS' in t and 'registro <strong>A</strong>' in t, 'console mostra o DNS e a instrução do registro A')
checa(re.search(r'<button class="btn"\s+disabled>Publicar domínio</button>', t), 'botão "Publicar domínio" desabilitado sem DNS')
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True)
checa('ainda não aponta' in r.text and not db.um(db.PLATAFORMA, 'SELECT 1 FROM ativacoes WHERE orgao_id=%s', (o['id'],)), 'pedido recusado sem DNS, nada na fila')
DNS['pmativa.exemplo.com'] = [VPS, '198.51.100.7']
checa(not AT.dns('pmativa.exemplo.com')['ok'], 'DNS com outro IP além da VPS não serve')

# ---------- DNS ok: pedido entra na fila ----------
DNS['pmativa.exemplo.com'] = [VPS]
t = con.get(U).text
checa('aponta para a VPS' in t and re.search(r'<button class="btn"\s*>Publicar domínio</button>', t), 'botão habilitado com DNS certo')
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True)
a = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
checa(a and a['situacao'] == 'pendente' and a['acao'] == 'ativar' and 'Pedido de ativação registrado' in r.text, 'pedido de ativação na fila')
checa('Já existe um pedido em andamento' in con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'ativar'}, follow_redirects=True).text, 'não duplica pedido em andamento')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM log_console WHERE acao LIKE %s", ('%pediu publicação do domínio pmativa.exemplo.com%',)), 'pedido no registro do console')

# ---------- comandos do ativador ----------
import io, contextlib
def roda(*args):
    b = io.StringIO()
    with contextlib.redirect_stdout(b):
        cod = AT.main(list(args))
    return cod, b.getvalue()
cod, out = roda('pendentes')
checa(f"{a['id']}\tativar\tpmativa.exemplo.com" in out, 'pendentes lista o pedido')
checa(roda('validar', str(a['id'])) == (0, 'ok\n'), 'validar aceita o pedido certo')
cod, v = roda('vhost', '--incluir', str(a['id']))
checa('# GERADO pelo ativador' in v and 'server_name pmativa.exemplo.com;' in v and '/etc/letsencrypt/live/pmativa.exemplo.com/fullchain.pem' in v and 'include /etc/nginx/conf.d/portal-comum.inc;' in v
      and 'acme-challenge' in v, 'vhost com os dois blocos (80 e 443)')
checa('pmbora' not in v and 'cmbora' not in v and 'gestao' not in v, 'vhost não inclui o piloto nem o console')
checa('pmativa' not in roda('vhost')[1], 'sem --incluir, o domínio ainda não publicado fica fora')
roda('passo', str(a['id']), 'Pedindo o certificado ao Let\'s Encrypt')
checa(db.um(db.PLATAFORMA, 'SELECT situacao FROM ativacoes WHERE id=%s', (a['id'],))['situacao'] == 'processando', 'primeiro passo marca "em andamento"')
checa('Pedindo o certificado' in con.get(U).text, 'console mostra os passos')
roda('concluir', str(a['id']), 'no_ar', 'No ar em https://pmativa.exemplo.com')
checa(db.um(db.PLATAFORMA, 'SELECT vhost_ativo FROM orgaos WHERE id=%s', (o['id'],))['vhost_ativo'], 'concluir no_ar marca o órgão como publicado')
checa('server_name pmativa.exemplo.com;' in roda('vhost')[1], 'domínio publicado entra no vhost')
t = con.get(U).text
checa('no ar pelo console' in t and 'Tirar do ar' in t, 'console mostra "no ar" e "Tirar do ar"')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM log_console WHERE quem='ativador da VPS' AND acao LIKE %s", ('%pmativa.exemplo.com%no_ar%',)), 'conclusão no registro do console')
checa(roda('validar', str(a['id']))[0] == 1, 'pedido concluído não é processado de novo')

# ---------- tirar do ar ----------
r = con.post(f'{U}/dominio', data={'csrf': tok(con, U), 'acao': 'desativar'}, follow_redirects=True)
d = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
checa(d['acao'] == 'desativar' and 'Pedido para tirar do ar registrado' in r.text, 'pedido de retirada na fila')
checa('pmativa' not in roda('vhost', '--excluir', str(d['id']))[1], 'vhost sem o domínio retirado')
roda('concluir', str(d['id']), 'desativado', 'Retirado do ar')
checa(not db.um(db.PLATAFORMA, 'SELECT vhost_ativo FROM orgaos WHERE id=%s', (o['id'],))['vhost_ativo'], 'órgão volta a "não publicado"')

# ---------- recusas e segurança ----------
db.exe(db.PLATAFORMA, 'INSERT INTO ativacoes (orgao_id, dominio, acao, pedido_por) VALUES (%s,%s,%s,%s)', (o['id'], 'outro.exemplo.com', 'ativar', 'teste'))
x = db.um(db.PLATAFORMA, 'SELECT id FROM ativacoes ORDER BY id DESC LIMIT 1')['id']
checa(roda('validar', str(x)) == (1, 'domínio do pedido não confere com o cadastro do órgão\n'), 'recusa domínio que não é o do órgão')
roda('concluir', str(x), 'erro', 'teste')
DNS['pmativa.exemplo.com'] = []
db.exe(db.PLATAFORMA, 'INSERT INTO ativacoes (orgao_id, dominio, acao, pedido_por) VALUES (%s,%s,%s,%s)', (o['id'], 'pmativa.exemplo.com', 'ativar', 'teste'))
y = db.um(db.PLATAFORMA, 'SELECT id FROM ativacoes ORDER BY id DESC LIMIT 1')['id']
checa(roda('validar', str(y)) == (1, 'o DNS não aponta para a VPS\n'), 'ativador revalida o DNS na hora')
roda('concluir', str(y), 'erro', 'teste')
for ruim in ('a.com;\n include /etc/passwd', 'exemplo.com/x', 'EXEMPLO.COM', 'sem-ponto'):
    try:
        AT.bloco(ruim); erros.append(f'bloco aceitou {ruim!r}')
    except ValueError:
        pass
checa(roda('vhost', '--teste', 'x;y')[0] == 2, 'domínio de teste inválido recusado')
checa('server_name teste-ativacao.exemplo.com;' in roda('vhost', '--teste', 'teste-ativacao.exemplo.com')[1], 'modo de teste do ativador inclui o domínio de teste')
# Traefik (VPS com Dokploy): JSON válido (também YAML), rotas http→https e https com o resolvedor pedido, nomes com prefixo
rc, y = roda('vhost', '--formato', 'traefik', '--resolvedor', 'meu-le', '--teste', 'teste-ativacao.exemplo.com')
corpo = json.loads(''.join(l for l in y.splitlines(True) if not l.startswith('#'))) if rc == 0 else {}
rt = corpo.get('http', {}).get('routers', {})
checa(rc == 0 and y.startswith('# GERADO pelo ativador') and rt.get('portal-orgaos-teste-ativacao-exemplo-com', {}).get('tls') == {'certResolver': 'meu-le'}
      and rt.get('portal-orgaos-teste-ativacao-exemplo-com-http', {}).get('entryPoints') == ['web'], 'traefik: rotas do domínio de teste com o resolvedor pedido')
checa(all(k.startswith('portal-orgaos-') for sec in corpo.get('http', {}).values() for k in sec), 'traefik: tudo com prefixo portal-orgaos- (não colide com outros sistemas)')
checa(corpo.get('http', {}).get('services', {}).get('portal-orgaos-app', {}).get('loadBalancer', {}).get('servers') == [{'url': 'http://portal-web-app:8000'}]
      and corpo['http']['middlewares']['portal-orgaos-limite']['buffering']['maxRequestBodyBytes'] == 25 * 1024 * 1024, 'traefik: aponta para o app e limita envios a 25 MB')
checa(roda('vhost', '--formato', 'traefik', '--resolvedor', 'x`y')[0] == 2, 'traefik: nome de resolvedor inválido recusado')
# instância (segundo nó na mesma VPS, 18/11/2026): nomes, apelido do app e trecho do nginx próprios; sem instância, como sempre
import subprocess as _sp
def roda_inst(inst, *a):
    p = _sp.run([sys.executable, '-m', 'app.ativacao', *a], env=dict(os.environ, INSTANCIA=inst), capture_output=True, text=True)
    return p.returncode, p.stdout
rc, y = roda_inst('camara', 'vhost', '--formato', 'traefik', '--teste', 'cm.exemplo.com')
ci = json.loads(''.join(l for l in y.splitlines(True) if not l.startswith('#'))) if rc == 0 else {}
checa(rc == 0 and all(k.startswith('portal-orgaos-camara-') for sec in ci.get('http', {}).values() for k in sec)
      and ci['http']['services']['portal-orgaos-camara-app']['loadBalancer']['servers'] == [{'url': 'http://portal-web-app-camara:8000'}],
      'instância: rotas do Traefik com prefixo e app da instância (não colidem com o outro nó)')
rc, v = roda_inst('camara', 'vhost', '--teste', 'cm.exemplo.com')
checa(rc == 0 and 'include /etc/nginx/conf.d/portal-comum-camara.inc;' in v, 'instância: vhost do nginx inclui o trecho da instância')
checa('include /etc/nginx/conf.d/portal-comum.inc;' in roda('vhost', '--teste', 'teste-ativacao.exemplo.com')[1], 'sem instância: trecho de sempre')
checa(roda_inst('Camara!', 'vhost', '--teste', 'cm.exemplo.com')[1].count('portal-comum.inc') == 1, 'instância inválida: ignorada (trecho de sempre)')
# IP do visitante: X-Real-IP do proxy vence; sem ele, o último do X-Forwarded-For (o primeiro pode ser inventado)
from types import SimpleNamespace as NS
from app import config as CFG
req = lambda h, c='10.0.0.9': NS(headers={k.lower(): v for k, v in h.items()}, client=NS(host=c))
checa(CFG.ip_cliente(req({'X-Real-IP': '203.0.113.7', 'X-Forwarded-For': '1.2.3.4, 203.0.113.7'})) == '203.0.113.7', 'IP: X-Real-IP do proxy')
checa(CFG.ip_cliente(req({'X-Forwarded-For': '1.2.3.4, 203.0.113.8'})) == '203.0.113.8', 'IP: sem X-Real-IP, o último do X-Forwarded-For (não o inventado)')
checa(CFG.ip_cliente(req({})) == '10.0.0.9', 'IP: sem cabeçalhos, o da conexão')
r = con.post('/orgao/1/dominio', data={'csrf': tok(con, '/orgao/1'), 'acao': 'ativar'}, follow_redirects=True)
checa('publicados pelo portal-bora.conf' in r.text and 'portal-bora.conf' in con.get('/orgao/1').text, 'domínios do piloto ficam fora do ativador')
anon = TestClient(app, base_url='http://gestao.localhost')
checa(anon.post(f'{U}/dominio', data={'acao': 'ativar'}, follow_redirects=False).status_code in (302, 303, 400, 401, 403), 'sem login não pede ativação')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('ativação: tudo ok')
