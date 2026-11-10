# Ajustes da Fase 8 (portal × protótipo): casco único das páginas internas, início (Notícias + Paço, Conheça), /noticias só com notícias,
# página da notícia, Ouvidoria/e-SIC com pílulas e "Outros canais", /governo com secretarias e organograma, D1 e avisos de Transmissões.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_ajustes8.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

def cli(host='pmbora.localhost'):
    return TestClient(app, base_url=f'http://{host}')
erros = []
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text) or (sem and sem in r.text):
        erros.append(f'{nome}: {r.status_code} {r.text[:300]}')
    return r
def checa(cond, nome):
    if not cond:
        erros.append(nome)
PM = 'bd_pm_bora'
pub, adm = cli(), cli()

# ---------- D1: exemplos que não eram notícia viraram comunicados-exemplo ----------
checa(db.um(PM, "SELECT 1 FROM comunicados WHERE exemplo AND tipo='Aviso' AND titulo ILIKE 'Vacinação%%'"), 'vacinação virou comunicado-exemplo (Aviso)')
checa(db.um(PM, "SELECT 1 FROM comunicados WHERE exemplo AND tipo='Convocação' AND titulo ILIKE 'Edital de concurso%%'"), 'edital de concurso virou comunicado-exemplo (Convocação)')
checa(not db.um(PM, "SELECT 1 FROM conteudos WHERE situacao='publicado' AND exemplo AND tipo IN ('Aviso','Documento')"), 'conteúdos de origem arquivados')
from app import fase8 as F8
checa(F8.mover_exemplos_para_comunicados(PM) == 0, 'migração do D1 roda uma vez só')

# ---------- casco único das páginas internas ----------
def casco(u, nome, legal=True):
    r = ok(pub.get(u), nome=nome)
    m = r.text[r.text.find('<main'):r.text.find('</main>')]
    checa('class="migalha"' in m and 'aria-label="Você está em"' in m, f'{nome}: trilha "Você está em"')
    checa(m.count('<h1') == 1, f'{nome}: um H1')
    if legal:
        i_leg, i_h1 = m.find('legal-topo'), m.find('</h1>')
        checa(i_leg > i_h1 and m.find('Base legal:') == m.find('Base legal:', i_h1), f'{nome}: "Base legal:" logo abaixo do título/introdução')
        checa(m.count('Base legal:') == 1, f'{nome}: base legal uma vez só (não repete no fim)')
    checa('id="avaliar"' in m, f'{nome}: "Avalie esta página" no fim')
    cab = r.text[r.text.find('class="b-inst"'):r.text.find('</nav>', r.text.find('class="b-inst"'))]
    checa(cab.count('<li') >= 5 and r.text[r.text.find('id="menu"'):].split('</nav>')[0].count('<li') >= 3, f'{nome}: barras do cabeçalho com itens')
    return r
for u, nome, legal in [('/noticias', 'notícias', True), ('/ouvidoria', 'ouvidoria', True), ('/e-sic', 'e-sic', True), ('/governo', 'governo', True), ('/fotos', 'fotos', True),
                       ('/links-uteis', 'links úteis', False), ('/privacidade', 'privacidade', True), ('/acessibilidade', 'acessibilidade', True), ('/mapa-do-site', 'mapa', False),
                       ('/transparencia', 'transparência', True), ('/servicos', 'serviços', True), ('/legislacao', 'legislação', True), ('/diario', 'diário', True),
                       ('/comunicados', 'comunicados', True), ('/conheca', 'conheça', True), ('/fale-conosco', 'fale conosco', True)]:
    casco(u, nome, legal)
r = pub.get('/fale-conosco'); checa('class="intro"' in r.text, 'fale conosco com introdução')

# ---------- /noticias: só notícias, filtro por secretaria, cartões horizontais ----------
r = ok(pub.get('/noticias'), txt='<h1>Notícias</h1>', nome='/noticias título', sem='Notícias e avisos')
checa('Vacinação contra a gripe' not in r.text and 'Edital de concurso' not in r.text, '/noticias sem comunicados')
ok(entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123'), txt='Visão geral', nome='login')
S = '/admin/carta-secretarias'
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'secretaria', 'nome': 'Secretaria de Teste da Saúde', 'sigla': 'STS', 'resumo': 'Cuida das unidades de saúde (texto de teste).', 'icone': 'saude'})
sec = db.um(PM, "SELECT id FROM secretarias WHERE sigla='STS'")['id']
t = tok(adm, '/admin/conteudos/novo')
r = adm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': 'Notícia de teste da saúde', 'resumo': 'Resumo de teste.', 'texto': 'Texto de teste.',
                                              'classe': 'util', 'acao': 'revisao', 'secretaria_id': sec, 'publicado_em': '2026-11-05T10:15'}, follow_redirects=True)
cid = int(re.search(r'/admin/conteudos/(\d+)">Notícia de teste da saúde', r.text).group(1))
adm.post('/admin/conteudos/salvar', data={'csrf': tok(adm, f'/admin/conteudos/{cid}'), 'id': cid, 'titulo': 'Notícia de teste da saúde', 'classe': 'util', 'acao': 'aprovar'})
checa(db.um(PM, 'SELECT secretaria_id FROM conteudos WHERE id=%s', (cid,))['secretaria_id'] == sec, 'editoria (secretaria) gravada na notícia')
r = ok(pub.get('/noticias'), txt='Notícia de teste da saúde', nome='/noticias lista a notícia')
checa('class="lista-not"' in r.text and 'Secretaria de Teste da Saúde' in r.text and 'id="f-nsec"' in r.text, 'cartões horizontais com editoria e filtro')
checa('class="cena"' in r.text, 'sem foto: imagem neutra da editoria')
checa(not re.search(r'<img[^>]+(unsplash|pexels|shutterstock)', r.text), 'nunca foto de banco de imagens')
ok(pub.get(f'/noticias?secretaria={sec}'), txt='Notícia de teste da saúde', nome='filtro por secretaria')
ok(pub.get(f'/noticias?secretaria={sec + 999}'), sem='Notícia de teste da saúde', nome='filtro por outra secretaria')
# ---------- página da notícia ----------
r = ok(pub.get(f'/conteudo/{cid}'), txt='Voltar para notícias', nome='página da notícia')
checa('href="/noticias">Notícias</a>' in r.text and 'Publicado em' in r.text and '05/11/2026, 10h15' in r.text and 'class="materia"' in r.text, 'trilha, "Publicado em data, hora · editoria" e cartão')
checa(re.search(r'class="btn sec" href="/noticias"', r.text), '"Voltar para notícias" no padrão de botão')
checa('aspect-ratio:21/9' in r.text, 'imagem 21:9 (neutra) no topo')
# ---------- início: fileira Notícias + Paço e Conheça ----------
h = pub.get('/').text
i = h.find('class="linha-not-paco"')
checa(i > 0 and h.find('class="noticias9"', i) > 0 and h.find('class="paco paco-lado"', i) > 0, 'fileira com Notícias e Paço')
checa(h.count('id="h-sede"') == 1, 'Paço aparece uma vez só')
blk = h[i:h.find('class="paco paco-lado"', i)]
checa('class="nd"' in blk and 'Todas as notícias' in blk, 'destaque e botão "Todas as notícias" no cartão')
checa('class="conheca9"' in h and 'class="c-mosaico' in h and 'Ver perfil' in h and 'Conheça mais' in h, 'Conheça em cartão com mosaico')

# ---------- Ouvidoria e e-SIC ----------
for u, atual in (('/ouvidoria', 'Ouvidoria'), ('/e-sic', 'Acesso à informação')):
    r = ok(pub.get(u), txt='Outros canais', nome=u)
    checa(re.search(rf'aria-current="page">{atual}</a>', r.text) and 'class="pilulas-atend"' in r.text, f'{u}: pílulas com a página atual marcada')
    checa('[telefone' not in r.text and '[número]' not in r.text, f'{u}: sem texto de exemplo do protótipo')

# ---------- Governo ----------
r = ok(pub.get('/governo'), txt='Secretaria de Teste da Saúde', nome='/governo')
checa('Cuida das unidades de saúde' in r.text and 'class="gov-card"' in r.text and 'Organograma' not in r.text, 'cartão com resumo; sem organograma, sem botão')
pdf = b'%PDF-1.4\n% teste\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'organograma'}, files={'arquivo': ('org.pdf', pdf, 'application/pdf')})
r = pub.get('/governo'); checa('Organograma (PDF)' in r.text, 'organograma publicado vira botão')
u = re.search(r'href="(/midia/[0-9a-f]{32}\.pdf)"', r.text)
checa(u and pub.get(u.group(1)).headers.get('content-type', '').startswith('application/pdf'), 'organograma servido como PDF')

# ---------- avisos de Transmissões ----------
r = ok(adm.get('/admin/'), txt='Transmissões: o que falta', nome='aviso na Visão geral')
checa('módulo de transmissões' in r.text and 'ID do canal' in r.text, 'aviso explica o que falta')
ok(adm.get('/admin/integracoes'), txt='Transmissões não aparecem no portal porque', nome='aviso em Integrações')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('ajustes 8: tudo ok')
