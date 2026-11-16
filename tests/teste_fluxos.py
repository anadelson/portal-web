# Teste de ponta a ponta: rode contra um banco de TESTE recém-provisionado (nunca no de produção).
# PYTHONPATH=. python tests/teste_fluxos.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste). Veja tests/README do PROGRESSO.')
from fastapi.testclient import TestClient
from app.main import app
from app import db, provision
from app.catalogo import LAYOUT_PADRAO_V1
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar
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
ok(pm.get('/conteudo/2'), nome='pm conteudo')
ok(cli('outro.localhost').get('/'), 404, nome='desconhecido')
# e-SIC
t = token(pm, '/acesso')
r = pm.post('/acesso', data={'csrf': t, 'tipo': 'pedido', 'assunto': 'Teste', 'texto': 'Quero a folha', 'nome': 'Fulano', 'email': 'f@x.com'}, follow_redirects=True)
ok(r, txt='Protocolo SIC-', nome='esic envio')
# admin
ok(pm.get('/admin/', follow_redirects=False), 303, nome='admin redireciona')
ok(entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123'), txt='Visão geral', nome='login com 2º fator e troca de senha')
for p in ['/admin/conteudos', '/admin/conteudos/novo', '/admin/conteudos/1', '/admin/pagina-inicial', '/admin/funcionalidades', '/admin/eleicao', '/admin/atendimento', '/admin/usuarios', '/admin/auditoria', '/admin/identidade', '/admin/diario']:
    ok(pm.get(p), nome=p)
# fluxo de conteúdo
t = token(pm, '/admin/conteudos/novo')
r = pm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': 'Teste fluxo', 'resumo': 'r', 'texto': 't', 'classe': 'util', 'acao': 'revisao'}, follow_redirects=True)
ok(r, txt='Enviou para aprovação', nome='conteudo revisao')
cid = int(re.search(r'/admin/conteudos/(\d+)">Teste fluxo', r.text).group(1))
t = token(pm, f'/admin/conteudos/{cid}')
ok(pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': cid, 'titulo': 'Teste fluxo', 'classe': 'util', 'acao': 'aprovar'}, follow_redirects=True), txt='Aprovou e publicou', nome='aprovar')
ok(pm.get(f'/conteudo/{cid}'), txt='Teste fluxo', nome='publicado no portal')
# diário
t = token(pm, '/admin/diario')
pm.post('/admin/diario/ato', data={'csrf': t, 'acao': 'novo', 'orgao_id': __import__('apoio').orgao_diario('bd_pm_bora', 'Gabinete (teste)'), 'tipo': 'Decreto', 'numero': '1/2026', 'ementa': 'Teste', 'texto': 'Art. 1º Teste.'})
r = pm.get('/admin/diario'); aid = re.search(r'name="id" value="(\d+)"><button class="btn sec" name="acao" value="aprovar"', r.text).group(1)
t = token(pm, '/admin/diario')
pm.post('/admin/diario/ato', data={'csrf': t, 'acao': 'aprovar', 'id': aid})
for a in ['abrir', 'fechar', 'assinar', 'assinar', 'publicar']:
    t = token(pm, '/admin/diario'); r = pm.post('/admin/diario/edicao', data={'csrf': t, 'acao': a}, follow_redirects=True)
ok(r, txt='MODO TESTE', nome='diario concluir (teste)')
cod = db.um('bd_pm_bora', "SELECT codigo FROM diario_edicoes WHERE situacao='publicada' ORDER BY id DESC LIMIT 1")['codigo']
ok(pm.get('/diario'), txt='Nenhuma edição oficial publicada', nome='edição de teste fora da lista oficial')
r = ok(pm.get(f'/diario/verificar?codigo={cod}'), txt='EDIÇÃO DE TESTE', nome='verificar teste')
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
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
for p in ['/admin/sessoes', '/admin/sessoes/1', '/admin/emendas', '/admin/']:
    ok(cm.get(p), nome='cm'+p)
# console
g = cli('gestao.localhost')
entrar(g, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
for p in ['/', '/orgao/1', '/orgao/2', '/catalogo', '/layout/2', '/log', '/orgaos/novo']:
    ok(g.get(p), nome='g'+p)
t = token(g, '/orgao/2'); ok(g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'integpref'}, follow_redirects=True), txt='desligado', nome='desliga integ')
ok(cm.get('/emendas'), 404, nome='emendas some sem modulo')
t = token(g, '/orgao/2'); g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'integpref'})
t = token(g, '/orgao/2'); g.post('/orgao/2', data={'csrf': t, 'acao': 'modulo', 'chave': 'emend'})
ok(cm.get('/emendas'), nome='emendas volta')
t = token(g, '/orgaos/novo')
# cadastro completo (etapa 1 do modelo multi-órgão): município fictício, e-mail do administrador obrigatório
ok(g.post('/orgaos/novo', data={'csrf': t, 'nome': 'Câmara Teste', 'tipo': 'legislativo', 'slug': 'cm-teste', 'dominio': 'cmteste.localhost', 'municipio': 'Município X', 'uf': 'SP', 'ibge': '3599911',
                                 'email_admin': 'admin@cmteste.localhost', 'sistema': 'nenhum'}, follow_redirects=True), txt='Órgão criado', nome='novo orgao')
ok(cli('cmteste.localhost').get('/'), nome='novo orgao portal')

# ---------- Fase 3: identidade visual ----------
def png(w=40, h=30):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), (14, 77, 100)).save(b, 'PNG'); return b.getvalue()
def imgs_sem_alt(html):
    return [t for t in re.findall(r'<img\b[^>]*>', html) if not re.search(r'\salt="', t)]
for txt in ['Serviços mais acessados', 'Conheça Borá', 'Paço Municipal', 'Radar da Transparência Pública', 'Avalie este portal', 'Voltar ao topo', 'Acesso direto', 'Câmara Municipal', 'brasao.webp', 'Public+Sans', 'Alto contraste']:
    ok(pm.get('/'), txt=txt, nome='pm home: ' + txt)
assert 'Prefeitura em números' not in pm.get('/').text and 'Borá em números</h2>' not in pm.get('/').text, 'bloco de números deveria estar oculto sem dados'
for txt in ['Próxima sessão', 'Presidente da Câmara', 'Mesa Diretora da 15ª Legislatura', 'Quanto custa a Câmara', 'Emendas impositivas dos vereadores', 'Últimas sessões', 'Projetos e proposições', 'Prefeitura Municipal']:
    ok(cm.get('/'), txt=txt, nome='cm home: ' + txt)
for c, paginas in [(pm, ['/', '/servicos', '/transparencia', '/acesso', '/diario', '/privacidade', '/acessibilidade', '/mapa-do-site', '/conteudo/2']),
                   (cm, ['/', '/vereadores', '/vereadores?leg=14', '/vereadores?leg=acervo', '/vereador/1', '/emendas', '/emendas/2026/22', '/sessoes', '/proposicoes'])]:
    for pg in paginas:
        r = ok(c.get(pg), nome='a11y ' + pg)
        if imgs_sem_alt(r.text):
            erros.append(f'imagem sem alt em {pg}: {imgs_sem_alt(r.text)[:2]}')
        if 'lang="pt-BR"' not in r.text or 'id="conteudo"' not in r.text:
            erros.append(f'{pg}: falta lang ou âncora de conteúdo')
ok(cm.get('/emendas/2026/22'), txt='Caminho da emenda na Prefeitura', nome='caminho da emenda')
ok(cm.get('/vereadores?leg=acervo'), txt='Legislaturas anteriores', nome='acervo')
ok(cm.get('/vereador/1'), txt='Mandatos na Câmara', nome='perfil')
ok(cm.get('/midia/../../etc/passwd'), 404, nome='midia path traversal')
ok(cm.get('/midia/abc.png'), 404, nome='midia nome invalido')
# admin: blocos novos, identidade com upload, vereadores (pm/cm já logados acima)
ok(pm.get('/admin/pagina-inicial'), txt='Conheça a cidade', nome='admin blocos novos pm')
ok(cm.get('/admin/pagina-inicial'), txt='Projetos em tramitação', nome='admin blocos novos cm')
ok(pm.get('/admin/identidade?aba=imagens'), txt='aba=imagens&amp;uso=brasao', nome='admin identidade: grade de imagens'); ok(pm.get('/admin/identidade?aba=imagens&uso=brasao'), txt='Texto alternativo (opcional)', nome='admin identidade: edição do brasão')
t = token(pm, '/admin/identidade')
r = pm.post('/admin/identidade/midia', data={'csrf': t, 'uso': 'hero', 'alt': '', 'credito': 'teste'}, files={'arquivo': ('a.png', png(), 'image/png')}, follow_redirects=True)
ok(r, txt='texto alternativo', nome='upload sem alt recusado')
t = token(pm, '/admin/identidade')
r = pm.post('/admin/identidade/midia', data={'csrf': t, 'uso': 'hero', 'alt': 'Foto de teste do destaque', 'credito': 'Teste CC0'}, files={'arquivo': ('a.txt', b'nao e imagem', 'image/png')}, follow_redirects=True)
ok(r, txt='não é uma imagem', nome='upload falso recusado')
t = token(pm, '/admin/identidade')
r = pm.post('/admin/identidade/midia', data={'csrf': t, 'uso': 'hero', 'alt': 'Foto de teste do destaque', 'credito': 'Teste CC0'}, files={'arquivo': ('a.png', png(), 'image/png')}, follow_redirects=True)
ok(r, txt='atualizada', nome='upload hero')
m = re.search(r'/midia/([0-9a-f]{32}\.png)', pm.get('/').text)
if not m:
    erros.append('hero enviado não aparece na home')
else:
    rr = pm.get('/midia/' + m.group(1)); ok(rr, nome='servir midia')
    if rr.headers.get('content-type') != 'image/png': erros.append('midia com content-type errado')
    ok(pm.get('/'), txt='alt="Foto de teste do destaque"', nome='alt do hero')
t = token(pm, '/admin/identidade')
ok(pm.post('/admin/identidade/cores', data={'csrf': t, 'cor': 'vermelho', 'cor_destaque': '#F0B429'}, follow_redirects=True), txt='formato #RRGGBB', nome='cor invalida')
ok(cm.get('/admin/vereadores'), txt='Iniciais', nome='admin vereadores')
t = token(cm, '/admin/vereadores/1')
ok(cm.post('/admin/vereadores/1', data={'csrf': t, 'partido': 'PSD', 'apelido': 'Du', 'bio': 'Biografia de teste.', 'contato': 'gabinete@teste', 'foto_alt': 'Retrato oficial de teste'}, files={'foto': ('f.png', png(80, 100), 'image/png')}, follow_redirects=True), txt='Perfil salvo', nome='vereador foto')
r = cm.get('/vereador/1'); ok(r, txt='alt="Retrato oficial de teste"', nome='foto do vereador no perfil')
ok(r, txt='Biografia de teste.', nome='bio no perfil')
ok(pm.get('/admin/vereadores'), 404, nome='prefeitura sem vereadores no admin')
t = token(pm, '/admin/conteudos/1')
ok(pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': 1, 'tipo': 'Aviso', 'secao': 'Serviços', 'titulo': 'Vacinação contra a gripe nas unidades de saúde', 'resumo': 'r', 'texto': 't', 'classe': 'util', 'imagem': 'saude', 'acao': 'rascunho'}, follow_redirects=True), txt='Salvou rascunho', nome='conteudo imagem')
t = token(pm, '/admin/conteudos/1'); pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': 1, 'titulo': 'Vacinação contra a gripe nas unidades de saúde', 'classe': 'util', 'acao': 'aprovar'})
ok(pm.get('/'), txt='Nenhum serviço publicado na Carta de Serviços ainda.', nome='mais acessados vem só das fichas da Carta (conteúdo-exemplo fora)')
ok(g.get('/layout/1'), txt='Conheça a cidade', nome='console editor de regiões')
ok(g.get('/'), txt='Órgãos e licenças', nome='console menu')
# provision atualizar: idempotente e migra layout padrão antigo
db.exe('bd_cm_bora', "DELETE FROM blocos WHERE pagina='home'")
for i, (k, reg) in enumerate(LAYOUT_PADRAO_V1['legislativo']):
    db.exe('bd_cm_bora', "INSERT INTO blocos (pagina, chave, regiao, ordem) VALUES ('home',%s,%s,%s)", (k, reg, i))
provision.atualizar(); provision.atualizar()
bl = {b['chave']: b['regiao'] for b in db.todos('bd_cm_bora', "SELECT chave, regiao FROM blocos WHERE pagina='home'")}
if bl.get('emendas') != 'principal' or 'projetos' not in bl: erros.append(f'atualizar não migrou layout V1: {bl}')
db.exe('bd_pm_bora', "DELETE FROM blocos WHERE chave='conheca'")
provision.atualizar()
if not db.um('bd_pm_bora', "SELECT 1 FROM blocos WHERE chave='conheca'"): erros.append('atualizar não acrescentou bloco faltante')
ok(cm.get('/'), txt='Projetos e proposições', nome='cm home depois de atualizar')
# contraste AA dos pares de cor do tema
def lum(h):
    c = [int(h[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= .03928 else ((x + .055) / 1.055) ** 2.4 for x in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def contraste(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + .05) / (lb + .05)
from app.web import mistura
for fg, bg, nome in [('#FFFFFF', '#0E4D64', 'branco/primária PM'), ('#FFFFFF', '#2F5233', 'branco/primária CM'), ('#0E4D64', '#FFFFFF', 'link PM'), ('#2F5233', '#FFFFFF', 'link CM'),
                     ('#4B5563', '#FFFFFF', 'texto secundário'), ('#4B5563', '#F5F7F9', 'secundário/fundo'), ('#17212B', '#F0B429', 'texto/destaque PM'), ('#17212B', '#F7C948', 'texto/destaque CM'),
                     ('#7A4A00', '#FCEFD9', 'alerta'), ('#9B1C1C', '#FBE4D8', 'erro'), ('#146C43', '#E3F2E9', 'sucesso'), ('#C9D1D9', '#17212B', 'rodapé'), ('#AEB8C2', '#121A22', 'rodapé faixa 4'),
                     ('#FFFFFF', mistura('#0E4D64', '#000000', .3), 'chip partido'), (mistura('#0E4D64', '#000000', .3), mistura('#0E4D64', '#FFFFFF', .88), 'tag'), ('#AEB8C2', '#17212B', 'menu painel')]:
    if contraste(fg, bg) < 4.5: erros.append(f'contraste {nome}: {contraste(fg, bg):.2f}')
print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
