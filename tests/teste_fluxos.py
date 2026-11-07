# Teste de ponta a ponta: rode contra um banco de TESTE recém-provisionado (nunca no de produção).
# PYTHONPATH=. python tests/teste_fluxos.py
import re, sys
from fastapi.testclient import TestClient
from app.main import app
def cli(host):
    return TestClient(app, base_url=f'http://{host}')
def token(c, url):
    r = c.get(url); m = re.search(r'name="csrf" value="([^"]+)"', r.text); return m.group(1) if m else None
erros = []
def ok(r, cod=200, txt=None, nome=''):
    if r.status_code != cod or (txt and txt not in r.text):
        erros.append(f'{nome}: {r.status_code} {r.text[:300]}')
    return r
# portais públicos
for host in ['pmbora.localhost', 'cmbora.localhost']:
    c = cli(host)
    ok(c.get('/'), nome=host+' home')
    for p in ['/transparencia', '/acesso', '/noticias']:
        ok(c.get(p), nome=host+p)
cm = cli('cmbora.localhost')
for p in ['/vereadores', '/vereadores?leg=13', '/sessoes', '/proposicoes', '/emendas', '/emendas/2026/22', '/vereador/1']:
    ok(cm.get(p), nome='cm'+p)
pm = cli('pmbora.localhost')
ok(pm.get('/diario'), nome='pm diario'); ok(pm.get('/vereadores'), 404, nome='pm sem vereadores')
ok(pm.get('/conteudo/1'), nome='pm conteudo')
ok(cli('outro.localhost').get('/'), 404, nome='desconhecido')
# e-SIC
t = token(pm, '/acesso')
r = pm.post('/acesso', data={'csrf': t, 'tipo': 'pedido', 'assunto': 'Teste', 'texto': 'Quero a folha', 'nome': 'Fulano', 'email': 'f@x.com'}, follow_redirects=True)
ok(r, txt='Protocolo SIC-', nome='esic envio')
# admin
ok(pm.get('/admin/', follow_redirects=False), 303, nome='admin redireciona')
t = token(pm, '/admin/login')
r = pm.post('/admin/login', data={'csrf': t, 'email': 'admin@pmbora.localhost', 'senha': 'admin123'}, follow_redirects=True)
ok(r, txt='Primeiro acesso', nome='login admin')
t = token(pm, '/admin/senha')
ok(pm.post('/admin/senha', data={'csrf': t, 'atual': 'admin123', 'nova': 'senhaforte123', 'conf': 'senhaforte123'}, follow_redirects=True), txt='Visão geral', nome='troca senha')
for p in ['/admin/conteudos', '/admin/conteudos/novo', '/admin/conteudos/1', '/admin/pagina-inicial', '/admin/funcionalidades', '/admin/eleicao', '/admin/atendimento', '/admin/usuarios', '/admin/auditoria', '/admin/identidade', '/admin/diario']:
    ok(pm.get(p), nome=p)
# fluxo de conteúdo
t = token(pm, '/admin/conteudos/novo')
r = pm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': 'Teste fluxo', 'resumo': 'r', 'texto': 't', 'classe': 'util', 'acao': 'revisao'}, follow_redirects=True)
ok(r, txt='Enviou para revisão', nome='conteudo revisao')
cid = int(re.search(r'/admin/conteudos/(\d+)">Teste fluxo', r.text).group(1))
t = token(pm, f'/admin/conteudos/{cid}')
ok(pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': cid, 'titulo': 'Teste fluxo', 'classe': 'util', 'acao': 'aprovar'}, follow_redirects=True), txt='Aprovou e publicou', nome='aprovar')
ok(pm.get(f'/conteudo/{cid}'), txt='Teste fluxo', nome='publicado no portal')
# diário
t = token(pm, '/admin/diario')
pm.post('/admin/diario/ato', data={'csrf': t, 'acao': 'novo', 'caderno': 'executivo', 'tipo': 'Decreto', 'numero': '1/2026', 'orgao': 'Gabinete', 'ementa': 'Teste', 'texto': 'Art. 1º Teste.'})
r = pm.get('/admin/diario'); aid = re.search(r'name="id" value="(\d+)"><button class="btn sec" name="acao" value="aprovar"', r.text).group(1)
t = token(pm, '/admin/diario')
pm.post('/admin/diario/ato', data={'csrf': t, 'acao': 'aprovar', 'id': aid})
for a in ['abrir', 'fechar', 'publicar']:
    t = token(pm, '/admin/diario'); r = pm.post('/admin/diario/edicao', data={'csrf': t, 'acao': a}, follow_redirects=True)
ok(r, txt='publicada', nome='diario publicar')
r = pm.get('/diario'); cod = re.search(r'<code>([0-9A-F-]{14})</code>', r.text).group(1)
ok(pm.get(f'/diario/verificar?codigo={cod}'), txt='Edição autêntica', nome='verificar')
eid = re.search(r'/diario/(\d+)\.pdf', r.text).group(1)
rp = pm.get(f'/diario/{eid}.pdf'); ok(rp, nome='pdf'); assert rp.content[:4] == b'%PDF'
# eleição: simular defeso
t = token(pm, '/admin/eleicao')
pm.post('/admin/eleicao', data={'csrf': t, 'acao': 'salvar', 'nome': 'Teste', 'inicio': '2020-01-01', 'fim': '2099-01-01', 'aviso': 'on', 'bloquear': 'on'})
r = pm.get('/'); ok(r, txt='Lei 9.504', nome='aviso defeso')
assert '[Prefeito] entrega' not in pm.get('/noticias').text, 'vedado aparece no defeso'
ok(pm.get('/conteudo/2'), 451, nome='conteudo suspenso')
t = token(pm, '/admin/eleicao')
pm.post('/admin/eleicao', data={'csrf': t, 'acao': 'salvar', 'nome': 'Eleições municipais 2028', 'inicio': '2028-07-01', 'fim': '2028-10-01', 'aviso': 'on', 'bloquear': 'on'})
# câmara admin
t = token(cm, '/admin/login')
cm.post('/admin/login', data={'csrf': t, 'email': 'admin@cmbora.localhost', 'senha': 'admin123'})
t = token(cm, '/admin/senha'); cm.post('/admin/senha', data={'csrf': t, 'atual': 'admin123', 'nova': 'senhaforte123', 'conf': 'senhaforte123'})
for p in ['/admin/sessoes', '/admin/sessoes/1', '/admin/emendas', '/admin/']:
    ok(cm.get(p), nome='cm'+p)
# console
g = cli('gestao.localhost')
t = token(g, '/login')
r = g.post('/login', data={'csrf': t, 'email': 'gestor@gestao.localhost', 'senha': 'gestor123'}, follow_redirects=True)
t = token(g, '/senha'); g.post('/senha', data={'csrf': t, 'atual': 'gestor123', 'nova': 'gestorforte1234', 'conf': 'gestorforte1234'})
for p in ['/', '/orgao/1', '/orgao/2', '/catalogo', '/layout/2', '/log', '/orgaos/novo']:
    ok(g.get(p), nome='g'+p)
t = token(g, '/orgao/2'); ok(g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'integpref'}, follow_redirects=True), txt='desligado', nome='desliga integ')
ok(cm.get('/emendas'), 404, nome='emendas some sem modulo')
t = token(g, '/orgao/2'); g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'integpref'})
t = token(g, '/orgao/2'); g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'emend'})
ok(cm.get('/emendas'), nome='emendas volta')
t = token(g, '/orgaos/novo')
ok(g.post('/orgaos/novo', data={'csrf': t, 'nome': 'Câmara Teste', 'tipo': 'legislativo', 'slug': 'cm-teste', 'dominio': 'cmteste.localhost', 'municipio': 'X', 'ibge': '1'}, follow_redirects=True), txt='Órgão criado', nome='novo orgao')
ok(cli('cmteste.localhost').get('/'), nome='novo orgao portal')
print('ERROS:', len(erros)); print('\n'.join(erros))
