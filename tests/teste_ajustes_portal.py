# Ajustes pedidos pelo órgão (14/11/2026): data da notícia opcional (dois campos), texto alternativo opcional, ponto focal por clique,
# arquivados só na aba "Arquivados", tipos de comunicado e categorias de álbum em lista editável, comunicados com etiqueta à direita,
# Conheça sem fotos próprias (gentílico/fundação aparecem; botão "Galeria de fotos"), álbum paginado, bloco "Galeria de fotos" e portal oculto.
# Dados FICTÍCIOS. Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_ajustes_portal.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, web
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def png(cor=(14, 77, 100)):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (48, 36), cor).save(b, 'PNG'); return b.getvalue()
PM = 'bd_pm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')

# ---------- 1) notícia: data opcional (data + hora separadas), texto alternativo opcional, ponto focal ----------
t = tok(pm, '/admin/conteudos/novo')
html_novo = pm.get('/admin/conteudos/novo').text
checa('name="publicado_em_data"' in html_novo and 'name="publicado_em_hora"' in html_novo and 'type="datetime-local"' not in html_novo, 'notícia: data e hora em campos separados')
checa('data-foco' in html_novo and 'type="number" name="foco_x"' not in html_novo, 'notícia: ponto focal por clique, sem campos numéricos')
base = {'csrf': t, 'tipo': 'Notícia', 'secao': 'Notícias', 'resumo': 'r', 'texto': 'Texto de exemplo.', 'classe': 'util', 'acao': 'rascunho'}
r = pm.post('/admin/conteudos/salvar', data=dict(base, titulo='Exemplo sem data', publicado_em_data='', publicado_em_hora=''),
            files={'capa': ('c.png', png(), 'image/png')}, follow_redirects=True)
c = db.um(PM, "SELECT * FROM conteudos WHERE titulo='Exemplo sem data'")
checa(c and c['publicado_em'] is None and (c['imagem'] or '').startswith('/') and c['imagem_alt'] == '', f'notícia salva sem data e com capa sem texto alternativo ({r.status_code})')
pm.post('/admin/conteudos/salvar', data=dict(base, csrf=tok(pm, '/admin/conteudos/novo'), titulo='Exemplo com data', publicado_em_data='2026-11-03', publicado_em_hora=''))
c2 = db.um(PM, "SELECT publicado_em FROM conteudos WHERE titulo='Exemplo com data'")
checa(c2 and c2['publicado_em'].astimezone().strftime('%d/%m %H:%M') == '03/11 08:00', f"data sem hora = 08h00 ({c2 and c2['publicado_em']})")
pm.post('/admin/conteudos/salvar', data=dict(base, csrf=tok(pm, '/admin/conteudos/novo'), titulo='Exemplo com hora', publicado_em_data='2026-11-03', publicado_em_hora='15:30', foco_x='20', foco_y='80'))
c3 = db.um(PM, "SELECT publicado_em, foco_x, foco_y FROM conteudos WHERE titulo='Exemplo com hora'")
checa(c3 and c3['publicado_em'].astimezone().strftime('%H:%M') == '15:30' and (c3['foco_x'], c3['foco_y']) == (20, 80), 'data e hora digitadas; ponto focal gravado')

# ---------- 2) arquivados só na aba "Arquivado" ----------
db.exe(PM, "UPDATE conteudos SET situacao='arquivado' WHERE titulo='Exemplo com hora'")
todos = pm.get('/admin/conteudos').text
checa('Exemplo com hora' not in todos and 'Exemplo sem data' in todos, 'notícias: "Todos" não mostra arquivado')
checa('Exemplo com hora' in pm.get('/admin/conteudos?sit=arquivado').text, 'notícias: arquivado aparece na aba Arquivado')

# ---------- 3) comunicados: tipos em lista editável, data opcional, arquivados à parte ----------
UC = '/admin/comunicados?aba=config'
tipos = db.cfg(PM, 'comunicados_tipos') or __import__('app.fase8', fromlist=['x']).TIPOS_COMUNICADO
form = {'csrf': tok(pm, UC), 'acao': 'tipos', 'n': str(len(tipos))}
for i, x in enumerate(tipos):
    form[f'tipo_{i}'] = x; form[f'antigo_{i}'] = x
form.update(novo='Comunicado de obras', adicionar='1')
pm.post('/admin/comunicados', data=form)
t1 = db.cfg(PM, 'comunicados_tipos')
checa(t1 and t1[-1] == 'Comunicado de obras' and len(t1) == len(tipos) + 1, f'tipo de comunicado adicionado pela lista ({t1})')
t = tok(pm, '/admin/comunicados?novo=1')
pm.post('/admin/comunicados', data={'csrf': t, 'acao': 'salvar', 'tipo': 'Comunicado de obras', 'classe': 'util', 'titulo': 'Exemplo de comunicado de obras', 'texto': 'x', 'publicado_em_data': '', 'publicado_em_hora': ''})
cm = db.um(PM, "SELECT * FROM comunicados WHERE titulo='Exemplo de comunicado de obras'")
checa(cm and cm['publicado_em'] is None, 'comunicado salvo com data em branco')
form = {'csrf': tok(pm, UC), 'acao': 'tipos', 'n': str(len(t1))}
for i, x in enumerate(t1):
    form[f'tipo_{i}'] = 'Aviso de obras' if x == 'Comunicado de obras' else x; form[f'antigo_{i}'] = x
pm.post('/admin/comunicados', data=form)
checa(db.um(PM, 'SELECT tipo FROM comunicados WHERE id=%s', (cm['id'],))['tipo'] == 'Aviso de obras' and 'Aviso de obras' in db.cfg(PM, 'comunicados_tipos'), 'renomear o tipo atualiza os comunicados')
t2 = db.cfg(PM, 'comunicados_tipos')
form = {'csrf': tok(pm, UC), 'acao': 'tipos', 'n': str(len(t2)), 'remover': str(t2.index('Aviso de obras'))}
for i, x in enumerate(t2):
    form[f'tipo_{i}'] = x; form[f'antigo_{i}'] = x
pm.post('/admin/comunicados', data=form)
checa('Aviso de obras' not in db.cfg(PM, 'comunicados_tipos'), 'tipo removido da lista')
checa('Aviso de obras' in pm.get(f"/admin/comunicados?id={cm['id']}").text, 'comunicado antigo mantém o tipo removido ao ser editado')
pm.post('/admin/comunicados', data={'csrf': tok(pm, '/admin/comunicados'), 'acao': 'situacao', 'id': cm['id'], 'situacao': 'arquivado'})
checa('Exemplo de comunicado de obras' not in pm.get('/admin/comunicados').text and 'Exemplo de comunicado de obras' in pm.get('/admin/comunicados?aba=arquivados').text,
      'comunicado arquivado só na aba Arquivados')

# ---------- 4) álbuns: categorias em lista, envio de várias fotos sem texto alternativo, grade paginada ----------
UF = '/admin/identidade?aba=fotos&sub=categorias'
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UF), 'acao': 'categorias', 'n': '0', 'novo': 'Exemplo turismo', 'adicionar': '1'})
cat = db.um(PM, "SELECT * FROM foto_categorias WHERE nome='Exemplo turismo'")
checa(cat is not None, 'categoria adicionada pela lista')
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UF), 'acao': 'categorias', 'n': '1', 'cat_id_0': cat['id'], 'cat_nome_0': 'Exemplo de turismo', 'cat_susp_0': '1'})
cat = db.um(PM, 'SELECT * FROM foto_categorias WHERE id=%s', (cat['id'],))
checa(cat['nome'] == 'Exemplo de turismo' and cat['suspender_defeso'], 'categoria renomeada e marcada para o defeso')
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, '/admin/identidade?aba=fotos'), 'acao': 'album', 'titulo': 'Álbum de exemplo', 'categoria_id': cat['id'], 'publicado': '1'})
aid = db.um(PM, "SELECT id FROM albuns WHERE titulo='Álbum de exemplo'")['id']
UA = f'/admin/identidade?aba=fotos&album={aid}'
for lote in range(3):  # 3 envios de 20 = 60 fotos (mais de uma página no painel e no portal)
    arqs = [('arquivo', (f'f{lote}_{i}.png', png((lote * 40, i * 10, 90)), 'image/png')) for i in range(20)]
    r = pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'foto', 'album_id': aid, 'credito': 'Exemplo', 'licenca': 'CC BY 4.0'}, files=arqs, follow_redirects=True)
checa(db.um(PM, 'SELECT count(*) n FROM album_fotos WHERE album_id=%s', (aid,))['n'] == 60, 'várias fotos por envio, sem texto alternativo')
checa('20 foto(s) enviada(s)' in r.text, 'mensagem com o número de fotos enviadas')
arqs = [('arquivo', (f'x{i}.png', png(), 'image/png')) for i in range(21)]
r = pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'foto', 'album_id': aid, 'licenca': 'CC BY 4.0'}, files=arqs, follow_redirects=True)
checa('no máximo 20' in r.text, 'limite de 20 fotos por envio')
a1 = pm.get(UA).text
checa('class="grade-fotos"' in a1 and a1.count('<li><a href="/admin/identidade?aba=fotos&amp;album=') == 48 and 'página 1 de 2' in a1, 'painel: grade de miniaturas com 48 por página')
f1 = db.um(PM, 'SELECT id FROM album_fotos WHERE album_id=%s ORDER BY id DESC LIMIT 1', (aid,))['id']
checa('name="foto_id"' in pm.get(f'{UA}&foto={f1}').text, 'painel: cada foto é editada na própria tela')
r = pm.get(f'/fotos/{aid}')
checa(r.status_code == 200 and r.text.count('data-galeria=') == 40 and '60 foto(s)' in r.text and '?p=2' in r.text, 'portal: álbum paginado (40 por página)')
checa('alt="Foto 41 do álbum Álbum de exemplo"' in pm.get(f'/fotos/{aid}?p=2').text, 'portal: sem texto alternativo, usa "Foto N do álbum …"')

# ---------- 5) página inicial: Galeria de fotos (oculta por padrão) e botão no Conheça; gentílico e fundação ----------
bl = db.um(PM, "SELECT * FROM blocos WHERE pagina='home' AND chave='fotos'")
checa(bl is not None and not bl['visivel'], 'bloco "Galeria de fotos" acrescentado oculto')
pm.post('/admin/identidade/municipio', data={'csrf': tok(pm, '/admin/identidade?aba=municipio'), 'distancia_capital': '~500 km', 'idhm': '0,7 (exemplo)', 'fundacao': '1900 (exemplo)', 'gentilico': 'exemplense'})
db.exe(PM, "UPDATE blocos SET visivel=TRUE WHERE pagina='home' AND chave='conheca'")
h = pm.get('/').text
checa('href="/fotos">Galeria de fotos</a>' in h and 'id="h-fotos"' not in h, 'Conheça mostra o botão Galeria de fotos quando o bloco está desligado')
checa('Gentílico' in h and 'exemplense' in h and 'Fundação / emancipação' in h, 'gentílico e fundação aparecem no Conheça')
db.exe(PM, "UPDATE blocos SET visivel=TRUE WHERE pagina='home' AND chave='fotos'")
h = pm.get('/').text
checa('id="h-fotos"' in h and 'href="/fotos">Galeria de fotos</a>' not in h, 'com o bloco ligado: galeria na página inicial e sem o botão no Conheça')
checa('Fotos do bloco' not in pm.get('/admin/identidade?aba=conheca').text, 'painel: Conheça sem a seção de fotos do bloco')

# ---------- 6) portal oculto enquanto é configurado ----------
fun = '/admin/funcionalidades'
r = pm.post(fun, data={'csrf': tok(pm, fun), 'chave': '_visibilidade', 'oculto': '1'}, follow_redirects=True)
checa('Portal oculto' in r.text and db.cfg(PM, 'portal_oculto') is True, 'chave "Ocultar o portal" grava')
anon = TestClient(app, base_url='http://pmbora.localhost')
r = anon.get('/')
checa(r.status_code == 503 and 'em preparação' in r.text and 'noindex' in r.headers.get('x-robots-tag', '') and 'Notícias' not in r.text, f'público vê "em preparação" (503, fora dos buscadores): {r.status_code}')
checa(anon.get('/transparencia').status_code == 503 and anon.get(f'/fotos/{aid}').status_code == 503, 'todas as páginas do portal ficam ocultas')
checa(anon.get('/admin/login').status_code == 200, 'login do painel continua acessível')
checa(anon.get('/api/diario/remessas/1').status_code != 503, 'API pública continua respondendo')
r = pm.get('/')
checa(r.status_code == 200 and 'Portal oculto:' in r.text and 'noindex' in r.headers.get('x-robots-tag', ''), 'equipe logada vê o portal, com a faixa de aviso')
cm_ = TestClient(app, base_url='http://cmbora.localhost')
checa(cm_.get('/').status_code == 200, 'portal de outro órgão não é afetado')
pm.post(fun, data={'csrf': tok(pm, fun), 'chave': '_visibilidade', 'oculto': ''})
web.limpar_cache_oculto()
r = anon.get('/')
checa(r.status_code == 200 and 'x-robots-tag' not in r.headers, 'publicado de novo: aberto ao público')

if erros:
    print('ERROS:', len(erros)); [print(' -', e) for e in erros]; sys.exit(1)
print('ajustes do portal: tudo ok')
