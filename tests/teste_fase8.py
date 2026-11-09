# Fase 8: cabeçalho em barras sem destino repetido, comunicados ≠ notícias, Conheça (autorização de imagem), bloco de notícias,
# defeso, legislação montada do Diário + importação CSV + leitura pela Câmara via API pública, transmissões (YouTube) e VLibras.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_fase8.py
import io, json, os, re, sys
from datetime import datetime, timedelta, timezone
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, menus as MN, fase8 as F
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

def cli(host):
    return TestClient(app, base_url=f'http://{host}')
erros = []
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text) or (sem and sem in r.text):
        erros.append(f'{nome}: {r.status_code} {r.text[:300]}')
    return r
def checa(cond, nome):
    if not cond:
        erros.append(nome)
def png(w=64, h=36):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), (14, 77, 100)).save(b, 'PNG'); return b.getvalue()
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
pm, cm = cli('pmbora.localhost'), cli('cmbora.localhost')

# ---------- A) cabeçalho: cada destino em uma única barra ----------
def destinos(html):
    inst = re.search(r'<nav class="b-inst"[^>]*>(.*?)</nav>', html, re.S)
    port = re.search(r'<nav class="menu" id="menu"[^>]*>(.*?)</nav>', html, re.S)
    hrefs = lambda m: re.findall(r'href="([^"#?]+)', m.group(1)) if m else []
    return hrefs(inst), hrefs(port)
for nome, c in (('pm', pm), ('cm', cm)):
    html = ok(c.get('/'), nome=f'{nome} home').text
    i, p = destinos(html)
    checa(i and p, f'{nome}: barras institucional e do portal presentes ({len(i)}/{len(p)})')
    checa(not (set(i) & set(p)), f'{nome}: destino repetido entre as barras: {set(i) & set(p)}')
    checa(len(i) == len(set(i)) and len(p) == len(set(p)), f'{nome}: destino repetido dentro da mesma barra')
    checa('class="btn-menu"' in html and 'id="menu-cel"' in html and 'aria-controls="menu-cel"' in html, f'{nome}: botão e painel do menu do celular')
    checa('Área restrita' in html, f'{nome}: Área restrita na barra de acessibilidade')
i, p = destinos(pm.get('/').text)
for d in ['/transparencia', '/painel', '/diario', '/legislacao', '/ouvidoria', '/e-sic']:
    checa(d in i or d in p or d == '/painel', f'pm: destino {d} no cabeçalho')
checa('/fale-conosco' in p and '/comunicados' in p and '/conheca' in p, 'pm: barra do portal com Fale conosco, Comunicados e Conheça')
checa('/servicos' in i and '/servicos' not in p, 'pm: Serviços só na barra institucional')
# o normalizador e a recusa no banco
checa(MN.normalizar('/Legislacao/') == '/legislacao', 'normalizar destino')
checa(MN.conflito(PM, '/transparencia', 'portal', None), 'conflito detecta destino já usado em outra barra')

# ---------- páginas de atendimento separadas; /acesso redireciona ----------
ok(pm.get('/acesso', follow_redirects=False), 301, nome='/acesso → /fale-conosco')
checa(pm.get('/acesso', follow_redirects=False).headers.get('location', '').endswith('/fale-conosco'), 'destino do redirecionamento')
ok(pm.get('/acesso?protocolo=SIC-0'), nome='/acesso com protocolo continua (consulta)')
ok(pm.get('/fale-conosco'), txt='Base legal:', nome='fale conosco')
ok(pm.get('/ouvidoria'), txt='name="tipo" value="manifestacao"', nome='ouvidoria')
ok(pm.get('/e-sic'), txt='name="tipo" value="pedido"', nome='e-sic')
ok(pm.get('/links-uteis'), nome='links úteis'); ok(pm.get('/governo'), nome='governo')

# ---------- admin ----------
ok(entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123'), txt='Visão geral', nome='login pm')
for u in ['/admin/menus', '/admin/comunicados', '/admin/conheca', '/admin/importar', '/admin/transmissoes' if False else '/admin/menus']:
    ok(pm.get(u), nome=u)
# Menus: recusa destino repetido
t = tok(pm, '/admin/menus')
ok(pm.post('/admin/menus', data={'csrf': t, 'acao': 'novo', 'barra': 'portal', 'rotulo': 'Transparência 2', 'destino': '/transparencia/', 'ordem': 5, 'ativo': '1'}, follow_redirects=True),
   txt='Recusado', nome='menus recusa destino repetido')
checa(not db.um(PM, "SELECT 1 FROM menus WHERE rotulo='Transparência 2'"), 'item repetido não gravado')
t = tok(pm, '/admin/menus')
ok(pm.post('/admin/menus', data={'csrf': t, 'acao': 'novo', 'barra': 'portal', 'rotulo': 'Agenda cultural', 'destino': '/agenda', 'ordem': 90, 'ativo': '1'}, follow_redirects=True), txt='Item salvo', nome='menus novo item')
checa('href="/agenda"' in pm.get('/').text, 'novo item aparece na barra do portal')
# acesso direto personalizável
t = tok(pm, '/admin/menus')
ok(pm.post('/admin/menus', data={'csrf': t, 'acao': 'atalho', 'titulo': 'Botão de teste', 'descricao': 'Descrição curta', 'destino': '/servicos', 'ativo': '1'}, follow_redirects=True), txt='Botão salvo', nome='atalho novo')
checa('Botão de teste' in pm.get('/').text, 'atalho personalizado na página inicial')
# acervo da legislação: só https, botão só com endereço
t = tok(pm, '/admin/menus')
ok(pm.post('/admin/menus', data={'csrf': t, 'acao': 'acervo', 'url': 'http://inseguro'}, follow_redirects=True), txt='https://', nome='acervo recusa http')
checa('Acervo anterior' not in pm.get('/legislacao').text, 'sem endereço, sem botão do acervo')
# VLibras ligado por padrão; desliga pelo painel
checa('vlibras-plugin.js' in pm.get('/').text and 'vw-access-button' in pm.get('/').text, 'VLibras presente por padrão')
t = tok(pm, '/admin/menus'); pm.post('/admin/menus', data={'csrf': t, 'acao': 'vlibras'})
checa('vlibras-plugin.js' not in pm.get('/').text, 'VLibras desligado pelo painel')
t = tok(pm, '/admin/menus'); pm.post('/admin/menus', data={'csrf': t, 'acao': 'vlibras', 'vlibras': '1'})
csp = pm.get('/').headers.get('content-security-policy', '')
checa('https://vlibras.gov.br' in csp and 'https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/' in csp and "frame-ancestors" in csp, 'CSP libera só o VLibras oficial')

# ---------- E) comunicados ≠ notícias ----------
t = tok(pm, '/admin/comunicados')
ok(pm.post('/admin/comunicados', data={'csrf': t, 'acao': 'salvar', 'tipo': 'Notícia', 'titulo': 'Não pode', 'classe': 'util'}, follow_redirects=True), txt='Tipo inválido', nome='comunicado recusa tipo notícia')
t = tok(pm, '/admin/comunicados')
ok(pm.post('/admin/comunicados', data={'csrf': t, 'acao': 'tipos', 'tipos': 'Aviso, Notícia'}, follow_redirects=True), txt='Notícia não é tipo de comunicado', nome='lista de tipos recusa notícia')
t = tok(pm, '/admin/conteudos/novo')
ok(pm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Convocação', 'secao': 'Notícias', 'titulo': 'X', 'classe': 'util', 'acao': 'rascunho'}, follow_redirects=True), txt='Comunicados', nome='conteúdo recusa tipo de comunicado')
ids = []
for n, (tipo, tit, val) in enumerate([('Aviso', 'Aviso de teste vigente', ''), ('Convocação', 'Convocação de teste vencida', '2026-11-01'), ('Nota oficial', 'Nota oficial de teste', '')]):
    t = tok(pm, '/admin/comunicados')
    r = pm.post('/admin/comunicados', data={'csrf': t, 'acao': 'salvar', 'tipo': tipo, 'titulo': tit, 'texto': 'Texto de teste.', 'classe': 'util', 'valido_ate': val,
                                            'publicado_em': f'2026-11-0{n + 2}T09:4{n}'}, follow_redirects=True)
    cid = int(re.search(r'/admin/comunicados\?id=(\d+)', str(r.url)).group(1)); ids.append(cid)
    t = tok(pm, '/admin/comunicados'); pm.post('/admin/comunicados', data={'csrf': t, 'acao': 'situacao', 'id': cid, 'situacao': 'publicado'})
home = pm.get('/').text
checa('Aviso de teste vigente' in home and 'Convocação de teste vencida' not in home, 'home: comunicado vencido sai da página inicial')
ok(pm.get('/comunicados'), txt='Convocação de teste vencida', nome='/comunicados mantém o vencido')
ok(pm.get('/comunicados?tipo=Aviso'), txt='Aviso de teste vigente', sem='Nota oficial de teste', nome='filtro por tipo')
ok(pm.get('/comunicados?ano=2026'), txt='Nota oficial de teste', nome='filtro por ano')
ok(pm.get(f'/comunicados/{ids[0]}'), txt='Base legal:', nome='página do comunicado')

# ---------- D) Conheça: foto com pessoas só com autorização ----------
t = tok(pm, '/admin/conheca')
r = pm.post('/admin/conheca', data={'csrf': t, 'acao': 'perfil', 'titulo': 'Praça de teste', 'categoria': 'Lugares', 'classe': 'util', 'publicado': '1'}, follow_redirects=True)
pid = int(re.search(r'/admin/conheca\?id=(\d+)', str(r.url)).group(1))
t = tok(pm, f'/admin/conheca?id={pid}')
ok(pm.post('/admin/conheca', data={'csrf': t, 'acao': 'foto', 'id': pid, 'alt': ''}, files={'arquivo': ('a.png', png(), 'image/png')}, follow_redirects=True), txt='texto alternativo', nome='foto sem alt recusada')
t = tok(pm, f'/admin/conheca?id={pid}')
ok(pm.post('/admin/conheca', data={'csrf': t, 'acao': 'foto', 'id': pid, 'alt': 'Pessoas reunidas na praça de teste', 'tem_pessoas': '1'}, files={'arquivo': ('a.png', png(), 'image/png')}, follow_redirects=True),
   txt='não aparece no portal', nome='foto com pessoas sem autorização avisada')
foto = db.um(PM, 'SELECT * FROM perfil_fotos WHERE perfil_id=%s', (pid,))
slug = db.um(PM, 'SELECT slug FROM perfis WHERE id=%s', (pid,))['slug']
checa(foto['url'] not in pm.get(f'/conheca/{slug}').text, 'foto com pessoas sem autorização NÃO publica')
t = tok(pm, f'/admin/conheca?id={pid}')
pm.post('/admin/conheca', data={'csrf': t, 'acao': 'foto_editar', 'id': pid, 'foto_id': foto['id'], 'alt': foto['alt'], 'tem_pessoas': '1', 'autorizacao': '1'})
checa(foto['url'] in pm.get(f'/conheca/{slug}').text, 'com autorização registrada, a foto publica')
t = tok(pm, f'/admin/conheca?id={pid}')
pm.post('/admin/conheca', data={'csrf': t, 'acao': 'foto', 'id': pid, 'alt': 'Coreto da praça de teste', 'credito': 'Teste CC0'}, files={'arquivo': ('b.png', png(), 'image/png')})
ok(pm.get(f'/conheca/{slug}'), txt='data-galeria="1"', nome='galeria com ampliação (2 fotos)')
t = tok(pm, f'/admin/conheca?id={pid}')
ok(pm.post('/admin/conheca', data={'csrf': t, 'acao': 'video', 'id': pid, 'youtube': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ'}, follow_redirects=True), txt='Vídeo incluído', nome='vídeo do YouTube')
ok(pm.get(f'/conheca/{slug}'), txt='youtube-nocookie.com/embed/aqz-KE-bpKQ', nome='vídeo sem cookies')
ok(pm.get('/conheca?categoria=Lugares&q=praça'), txt='Praça de teste', nome='busca e filtro do Conheça')
# no máximo 3 em destaque
for k in range(4):
    t = tok(pm, '/admin/conheca')
    r = pm.post('/admin/conheca', data={'csrf': t, 'acao': 'perfil', 'titulo': f'Destaque {k}', 'categoria': 'Lugares', 'publicado': '1', 'destaque': '1'}, follow_redirects=True)
checa(db.um(PM, 'SELECT count(*) n FROM perfis WHERE destaque')['n'] <= 3, 'no máximo 3 perfis em destaque')
checa('Já há 3 perfis' in r.text, 'aviso do limite de destaques')
# evento é publicidade: sai no defeso
t = tok(pm, '/admin/conheca')
pm.post('/admin/conheca', data={'csrf': t, 'acao': 'perfil', 'titulo': 'Festa de teste da gestão', 'categoria': 'Eventos', 'classe': 'util', 'publicado': '1'})
checa(db.um(PM, "SELECT classe FROM perfis WHERE titulo='Festa de teste da gestão'")['classe'] == 'pub', 'evento classificado como publicidade')

# ---------- F) notícias: destaque, 3 secundárias, lista de 5 ----------
def noticia(titulo, quando, destaque=False, capa=False):
    t = tok(pm, '/admin/conteudos/novo')
    data = {'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': titulo, 'resumo': 'Resumo de teste.', 'texto': 'Texto.', 'classe': 'pub', 'acao': 'revisao', 'publicado_em': quando}
    if destaque:
        data['destaque'] = '1'
    files = None
    if capa:
        data.update(imagem_alt='Foto de teste da capa', foco_x='30', foco_y='40'); files = {'capa': ('c.png', png(160, 90), 'image/png')}
    r = pm.post('/admin/conteudos/salvar', data=data, files=files, follow_redirects=True)
    cid = int(re.search(rf'/admin/conteudos/(\d+)">{re.escape(titulo)}', r.text).group(1))
    t = tok(pm, f'/admin/conteudos/{cid}')
    pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': cid, 'titulo': titulo, 'classe': 'pub', 'acao': 'aprovar'})
    return cid
t = tok(pm, '/admin/conteudos/novo')
ok(pm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': 'Sem alt', 'classe': 'pub', 'acao': 'rascunho'},
           files={'capa': ('c.png', png(160, 90), 'image/png')}, follow_redirects=True), txt='texto alternativo', nome='capa sem alt recusada')
for k in range(9):
    noticia(f'Notícia de teste {k}', f'2026-11-0{k % 5 + 1}T0{k}:1{k}')
dest = noticia('Notícia em destaque de teste', '2026-10-20T09:44', destaque=True, capa=True)
h = pm.get('/').text
blk = h[h.find('class="noticias8'):] if 'class="noticias8' in h else ''
checa(blk and blk.find('Notícia em destaque de teste') < blk.find('not-sec'), 'notícia marcada como destaque vem primeiro (mesmo mais antiga)')
checa('20/10/2026, 09h44' in blk, 'data e hora da notícia no formato 08/11/2026, 09h44')
checa('object-position:30% 40%' in blk and 'alt="Foto de teste da capa"' in blk, 'capa 16:9 com ponto focal e texto alternativo')
sec = re.findall(r'<ul class="not-sec">(.*?)</ul>', blk, re.S)
checa(sec and sec[0].count('<li>') == 3, 'três notícias secundárias')
tit = re.findall(r'<ul class="not-tit">(.*?)</ul>', blk, re.S)
checa(tit and tit[0].count('<li>') == 5, 'lista com cinco títulos')
checa('Todas as notícias' in blk and 'class="btn' in blk, 'botão "Todas as notícias"')
checa(db.um(PM, 'SELECT count(*) n FROM conteudos WHERE destaque')['n'] == 1, 'só uma notícia em destaque')

# ---------- defeso: notícias e eventos somem sem deixar espaço ----------
t = tok(pm, '/admin/eleicao')
pm.post('/admin/eleicao', data={'csrf': t, 'acao': 'salvar', 'nome': 'Teste', 'inicio': '2020-01-01', 'fim': '2099-01-01', 'aviso': 'on', 'bloquear': 'on'})
h = pm.get('/').text
checa('class="noticias8' not in h and 'h-not' not in h, 'defeso: bloco de notícias some')
checa('Festa de teste da gestão' not in pm.get('/conheca').text, 'defeso: evento (publicidade) some do Conheça')
checa('Praça de teste' in pm.get('/conheca').text, 'defeso: lugar (utilidade) continua')
t = tok(pm, '/admin/eleicao')
pm.post('/admin/eleicao', data={'csrf': t, 'acao': 'salvar', 'nome': 'Eleições municipais 2028', 'inicio': '2028-07-01', 'fim': '2028-10-01', 'aviso': 'on', 'bloquear': 'on'})

# ---------- I) legislação ----------
csv_ok = ('tipo;numero;ano;data;ementa;link;relacoes\n'
          'Lei;12;2020;10/03/2020;Lei de teste importada (dado fictício de teste);https://exemplo.invalid/l12;\n'
          'Lei;15;2021;;Altera a lei de teste (dado fictício de teste);;altera:Lei 12/2020\n').encode()
csv_ruim = 'tipo;numero;ano;data;ementa;link;relacoes\nNotícia;1;2020;;x;;\nLei;2;2020;;y;;revoga:Lei 99/1999\n'.encode()
t = tok(pm, '/admin/importar')
r = ok(pm.post('/admin/importar', data={'csrf': t, 'modelo': 'legislacao', 'acao': 'simular'}, files={'arquivo': ('l.csv', csv_ruim, 'text/csv')}), txt='nada gravado', nome='importação com erros')
checa('tipo deve ser um de' in r.text and 'não está na lista' in r.text, 'relatório aponta tipo inválido e relação sem ato')
t = tok(pm, '/admin/importar')
ok(pm.post('/admin/importar', data={'csrf': t, 'modelo': 'legislacao', 'acao': 'simular'}, files={'arquivo': ('l.csv', csv_ok, 'text/csv')}), txt='(simulação: nada gravado)', nome='simulação ok')
checa(not db.um(PM, "SELECT 1 FROM legislacao WHERE origem='importado'"), 'simulação não grava')
t = tok(pm, '/admin/importar')
ok(pm.post('/admin/importar', data={'csrf': t, 'modelo': 'legislacao', 'acao': 'gravar'}, files={'arquivo': ('l.csv', csv_ok, 'text/csv')}), txt='2 gravadas', nome='importação gravada')
ok(pm.post('/admin/importar', data={'csrf': tok(pm, '/admin/importar'), 'modelo': 'vereadores', 'acao': 'simular'}, files={'arquivo': ('l.csv', csv_ok, 'text/csv')}, follow_redirects=True),
   txt='Escolha o modelo', nome='prefeitura não importa modelos da Câmara')
# ato no Diário que revoga a Lei 12/2020
t = tok(pm, '/admin/diario')
pm.post('/admin/diario/ato', data={'csrf': t, 'acao': 'novo', 'caderno': 'executivo', 'tipo': 'Lei', 'numero': '20/2026', 'orgao': 'Gabinete', 'ementa': 'Lei de teste publicada no Diário (dado fictício de teste)',
                                   'texto': 'Art. 1º Teste. Art. 2º Revoga-se a Lei 12/2020.', 'rel_tipo_0': 'revoga', 'rel_alvo_0': 'Lei 12/2020'})
checa(db.um(PM, "SELECT relacoes FROM diario_atos WHERE numero='20/2026'")['relacoes'] == [{'tipo': 'revoga', 'alvo': 'Lei 12/2020'}], 'relação gravada no ato do Diário')
r = pm.get('/admin/diario'); aid = re.search(r'name="id" value="(\d+)"><button class="btn sec" name="acao" value="aprovar"', r.text).group(1)
pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario'), 'acao': 'aprovar', 'id': aid})
for a in ['abrir', 'fechar', 'assinar', 'assinar', 'publicar']:
    pm.post('/admin/diario/edicao', data={'csrf': tok(pm, '/admin/diario'), 'acao': a})
checa(not db.um(PM, "SELECT 1 FROM legislacao WHERE numero='20'"), 'edição de TESTE (sem valor oficial) não entra na legislação')
# simula, só no banco de teste, uma edição oficial assinada (o certificado de teste não tem valor oficial)
db.exe(PM, "UPDATE diario_edicoes SET modo_teste=FALSE WHERE id=(SELECT edicao_id FROM diario_atos WHERE numero='20/2026')")
r = ok(pm.get('/legislacao'), txt='Base legal:', nome='/legislacao')
checa('Lei nº 20/2026' in r.text, 'ato publicado no Diário entra sozinho na lista')
ok(pm.get('/legislacao?situacao=revogada'), txt='Lei de teste importada', sem='Lei de teste publicada', nome='filtro situação revogada')
ok(pm.get('/legislacao?situacao=vigente&ano=2026'), txt='Lei de teste publicada', nome='filtro vigente e ano')
ok(pm.get('/legislacao?q=altera'), txt='Altera a lei de teste', nome='busca na legislação')
l12 = db.um(PM, "SELECT id FROM legislacao WHERE numero='12' AND ano=2020")['id']
r = ok(pm.get(f'/legislacao/{l12}'), txt='revogad', nome='página do ato mostra relações')
checa('Lei nº 20/2026' in r.text and 'Lei nº 15/2021' in r.text, 'relações: revogada pela 20/2026 e alterada pela 15/2021')
j = pm.get('/legislacao.json').json()
checa(j.get('base_legal') and any(x['numero'] == '20' and x['situacao'] == 'vigente' for x in j['registros']), 'JSON com base legal e situação')
rc = pm.get('/legislacao.csv'); checa(rc.status_code == 200 and rc.text.lstrip('﻿').startswith('tipo,numero,ano'), 'CSV da legislação')
# Câmara: lê pela API pública da Prefeitura (aqui o "servidor interno" é o próprio app de teste)
import httpx
_Client = httpx.Client
class _Interno(TestClient):
    def __init__(self, *a, **k):
        super().__init__(app, base_url='http://interno')
httpx.Client = _Interno
try:
    r = ok(cm.get('/legislacao'), txt='Lei nº 20/2026', nome='Câmara lê a legislação pela API da Prefeitura')
    checa('Lei de teste importada' in cm.get('/legislacao?situacao=revogada').text, 'Câmara: filtro por situação')
finally:
    httpx.Client = _Client
checa(not db.todos(CM, "SELECT 1 FROM information_schema.tables WHERE table_name='legislacao'") or not db.um(CM, 'SELECT 1 FROM legislacao LIMIT 1'), 'Câmara não guarda a legislação no próprio banco')
ok(cm.get('/legislacao.json'), 404, nome='Câmara não publica legislação própria pela API da Prefeitura')

# ---------- G) transmissões: detecção pelo YouTube (dados simulados, sem rede) ----------
from app.coletores import youtube as YT
agora = datetime(2026, 11, 6, 13, 0, tzinfo=timezone.utc)
db.exe(PM, "DELETE FROM transmissoes")
db.exe(PM, "INSERT INTO transmissoes (titulo, tipo, previsto_para) VALUES ('Audiência pública de teste', 'Audiência pública', %s)", (agora + timedelta(minutes=10),))
checa(YT.em_janela(PM, agora), 'janela da agenda: 15 min antes do início')
checa(not YT.em_janela(PM, agora - timedelta(hours=2)), 'fora da janela não consulta')
vid = {'id': 'aqz-KE-bpKQ', 'titulo': 'Ao vivo de teste', 'estado': 'live', 'foi_ao_vivo': True, 'inicio': agora, 'fim': None, 'publicado': agora, 'legendas': True}
YT.aplicar(PM, [vid], agora, False)
t = db.um(PM, "SELECT * FROM transmissoes WHERE titulo='Audiência pública de teste'")
checa(t['ao_vivo'] and t['video'] == 'aqz-KE-bpKQ', 'ao vivo vinculado à transmissão agendada')
YT.aplicar(PM, [dict(vid, estado='none', fim=agora + timedelta(hours=1))], agora + timedelta(hours=1), False)
checa(not db.um(PM, 'SELECT ao_vivo FROM transmissoes WHERE id=%s', (t['id'],))['ao_vivo'], 'fim da transmissão detectado')
comum = {'id': 'Ks-_Mh1QhMc', 'titulo': 'Vídeo comum do canal', 'estado': 'none', 'foi_ao_vivo': False, 'inicio': None, 'fim': None, 'publicado': agora, 'legendas': False}
grav = {'id': 'M7lc1UVf-VE', 'titulo': 'Gravação de transmissão', 'estado': 'none', 'foi_ao_vivo': True, 'inicio': agora - timedelta(days=1), 'fim': agora - timedelta(days=1) + timedelta(hours=2), 'publicado': agora, 'legendas': False}
YT.aplicar(PM, [comum, grav], agora, True)
checa(db.um(PM, "SELECT 1 FROM transmissoes WHERE video='M7lc1UVf-VE' AND origem='youtube'") and not db.um(PM, "SELECT 1 FROM transmissoes WHERE video='Ks-_Mh1QhMc'"),
      'varredura diária registra só transmissões encerradas (vídeo comum não entra)')
YT.aplicar(PM, [grav], agora, True)
checa(db.um(PM, "SELECT count(*) n FROM transmissoes WHERE video='M7lc1UVf-VE'")['n'] == 1, 'gravação não duplica')
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
checa(YT.coletar(o, {}, agora) == [], 'sem módulo/canal/chave: coletor não faz nada')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.slug='cm-bora' AND f.fonte='youtube'"), 'fonte youtube cadastrada pelo provision')
try:
    YT.videos_recentes('canal-ruim', 'x')
    checa(False, 'canal inválido deveria falhar')
except RuntimeError as e:
    checa('UC' in str(e) and 'x' not in str(e).replace('caracteres', ''), 'erro do canal não expõe a chave')
# Câmara: canal precisa ter formato UC…
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
ok(cm.get('/admin/transmissoes'), txt='Configure o canal', nome='aviso de canal não configurado')
ok(cm.post('/admin/transmissoes', data={'csrf': tok(cm, '/admin/transmissoes'), 'acao': 'config', 'canal': 'meu-canal'}, follow_redirects=True), txt='começa com UC', nome='canal inválido recusado')
ok(cm.post('/admin/transmissoes', data={'csrf': tok(cm, '/admin/transmissoes'), 'acao': 'config', 'canal': 'UC' + 'a' * 22}, follow_redirects=True), sem='Configure o canal', nome='canal válido salvo')

# ---------- H) Acessibilidade ----------
r = ok(pm.get('/acessibilidade'), txt='NVDA', nome='página de acessibilidade')
for t_ in ['DOSVOX', 'MOTRIX', 'VLibras', 'intervox.nce.ufrj.br', 'emag.governoeletronico.gov.br']:
    checa(t_ in r.text, f'acessibilidade: {t_}')

# ---------- B) título curto do indicador ----------
try:
    db.exe(PM, "UPDATE indicadores SET titulo_curto=%s WHERE id=(SELECT min(id) FROM indicadores)", ('x' * 33,))
    checa(False, 'título curto com 33 caracteres deveria ser recusado pelo banco')
except Exception:
    pass
checa(not db.um(PM, "SELECT 1 FROM indicadores WHERE titulo_curto=''"), 'todo indicador do catálogo tem título curto')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('fase 8: tudo ok')
