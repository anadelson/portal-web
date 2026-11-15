# Pedido de 15/11/2026: Notícias e Comunicados no desenho "vitrine" (destaque + 3 cartões com "Continue lendo" + lista),
# miniatura do comunicado (1º anexo: imagem ou 1ª página do PDF), notícias e comunicados em largura total com coluna à direita
# (últimas notícias, últimos comunicados, previsão do tempo), previsão do tempo (Open-Meteo) e editor de texto ampliado.
# Dados FICTÍCIOS (previsão de teste gravada à mão; nenhuma consulta real). Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_vitrine_tempo.py
import io, os, re, sys
from datetime import date, timedelta
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app
from app import db, editor as ED, tempo as T, provision, catalogo
from app.coletores import tempo as CT, comum
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM = 'bd_pm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
anon = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
IBGE = db.um(db.PLATAFORMA, "SELECT ibge FROM orgaos WHERE slug='pm-bora'")['ibge']

# ---------- 1) editor: formatação nova, sempre por lista fechada ----------
h, _ = ED.limpar('<p style="color:red" class="al-centro intruso">a <u>b</u> <strike>c</strike> <mark>d</mark> <sup>2</sup> <sub>x</sub></p><hr>'
                 '<h4 class="al-dir">t</h4><h5>u</h5><p><a class="video" href="https://youtu.be/dQw4w9WgXcQ">Vídeo: sessão</a></p>'
                 '<p><a class="video outra" href="https://exemplo.org/v">v</a></p><script>alert(1)</script><iframe src="https://x"></iframe>')
checa('<p class="al-centro">' in h and 'style=' not in h and 'intruso' not in h, f'alinhamento vira classe da lista; style e classe estranha caem ({h[:80]})')
checa(all(x in h for x in ('<u>b</u>', '<s>c</s>', '<mark>d</mark>', '<sup>2</sup>', '<sub>x</sub>', '<hr>', '<h4 class="al-dir">', '<h4>u</h4>')), 'sublinhado, tachado, marca-texto, sobrescrito, subscrito, linha e título menor')
checa('<script' not in h and '<iframe' not in h, 'script e iframe nunca passam')
x = str(ED.exibir(h))
checa('youtube-nocookie.com/embed/dQw4w9WgXcQ' in x and 'title="Vídeo: sessão"' in x, 'link de vídeo do YouTube vira player youtube-nocookie com título')
checa('exemplo.org/v' in x and x.count('<iframe') == 1, 'link "vídeo" de fora do YouTube continua link (sem player)')
ed = pm.get('/admin/conteudos/novo').text
checa(all(f'data-cmd="{c}"' in ed for c in ('underline', 'strikeThrough', 'marca', 'al-centro', 'al-just', 'indent', 'unlink', 'video', 'hr', 'lin+', 'col+', 'codigo', 'cheio', 'undo', 'redo')),
      'barra do editor com os recursos novos')
checa('data-bloco' in ed and 'Título menor' in ed and 'ed-conta' in ed, 'estilo do parágrafo e contagem de palavras')
from pathlib import Path
css = (Path(__file__).resolve().parent.parent / 'app' / 'static' / 'admin.css').read_text()
checa('form.campos:has(.editor)' in css and 'max-width:none' in css.split('form.campos:has(.editor)', 1)[1][:200], 'telas com editor em largura total')

# ---------- 2) previsão do tempo: coleta (sem rede: resposta fictícia), exibição e validade ----------
FALSA = {'current': {'time': '2026-11-15T08:00', 'temperature_2m': 22.4, 'weather_code': 61, 'relative_humidity_2m': 81, 'wind_speed_10m': 9.6, 'is_day': 1},
         'daily': {'time': [(date.today() + timedelta(days=i)).isoformat() for i in range(4)], 'temperature_2m_max': [27.1, 28.3, 29.3, 30.0],
                   'temperature_2m_min': [20.8, 20.1, 19.5, 19.0], 'weather_code': [95, 3, 1, 0], 'precipitation_probability_max': [80, 20, 5, 0], 'precipitation_sum': [12.0, 0.4, 0, 0]}}
pedidos = []
def buscar_falso(fonte, url, params=None, **k):
    pedidos.append(url)
    if 'ibge.gov.br' in url:
        return [{'id': IBGE, 'centroide': {'latitude': -22.2442, 'longitude': -50.5021}}]
    return FALSA
CT.buscar = buscar_falso
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
res = CT.coletar(o, {'ibge': IBGE})
checa(res and res[0][1] and res[0][2] == 4, f'coleta grava agora + 4 dias ({res})')
checa(any('ibge.gov.br' in u for u in pedidos) and any('open-meteo' in u for u in pedidos), 'centro do município pelo IBGE e previsão pelo Open-Meteo')
n = len(pedidos); CT.coletar(o, {'ibge': IBGE})
checa(len(pedidos) == n, 'segunda coleta na mesma hora (Câmara do mesmo município) não consulta de novo')
checa(db.um(db.LOCAL, "SELECT 1 FROM fontes WHERE orgao_id=%s AND fonte='tempo' AND ativo", (o['id'],)), 'fonte "tempo" cadastrada para o órgão')
p = T.previsao(IBGE)
checa(p and p['temp'] == 22 and p['texto'] == 'Chuva fraca' and p['dias'][0]['rotulo'] == 'Hoje' and p['dias'][0]['texto'] == 'Trovoadas', f'previsão interpretada ({p and p["texto"]})')
home = anon.get('/').text
checa('class="tempo"' in home and 'Tempo em' in home and '22 °C' in home and 'Open-Meteo' in home and 'Hoje' in home, 'faixa da previsão na página inicial, com a fonte')
blocos = [b['chave'] for b in db.todos(PM, "SELECT chave FROM blocos WHERE pagina='home' ORDER BY ordem, id")]
checa('tempo' in blocos and blocos.index('tempo') == blocos.index('comunicados') - 1, f'bloco "Previsão do tempo" entra logo antes de Comunicados ({blocos[:8]})')
db.exe(db.LOCAL, "UPDATE dados_publicos SET coletado_em = now() - interval '7 hours' WHERE ibge=%s AND fonte='tempo'", (IBGE,))
checa(T.previsao(IBGE) is None and 'class="tempo"' not in anon.get('/').text, 'previsão com mais de 6 h some (nunca mostra dado velho como atual)')
db.exe(db.LOCAL, "UPDATE dados_publicos SET coletado_em = now() WHERE ibge=%s AND fonte='tempo'", (IBGE,))
# bloco novo para órgão que já tinha layout: entra antes de Comunicados
db.exe(PM, "DELETE FROM blocos WHERE pagina='home' AND chave='tempo'")
provision.atualizar_layout(PM, 'executivo')
blocos = [b['chave'] for b in db.todos(PM, "SELECT chave FROM blocos WHERE pagina='home' ORDER BY ordem, id")]
checa(blocos.index('tempo') == blocos.index('comunicados') - 1, 'atualização acrescenta o bloco antes de Comunicados, sem mexer no resto')

# ---------- 3) comunicados: vitrine com miniatura do 1º anexo (PDF → 1ª página) ----------
def pdf():
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); c = canvas.Canvas(b); c.drawString(72, 760, 'EDITAL DE TESTE (exemplo fictício)'); c.save(); return b.getvalue()
U = '/admin/comunicados?novo=1'
for i in range(6):
    pm.post('/admin/comunicados', data={'csrf': tok(pm, U), 'acao': 'salvar', 'tipo': 'Aviso', 'classe': 'util', 'titulo': f'Exemplo de comunicado da vitrine {i}', 'texto': 'Texto fictício.',
                                        'publicado_em_data': f'2026-11-0{i + 1}', 'publicado_em_hora': '10:00', 'publicar': '1'})
db.exe(PM, "UPDATE comunicados SET situacao='publicado', exemplo=TRUE WHERE titulo LIKE 'Exemplo de comunicado da vitrine%%'")
cid = db.um(PM, "SELECT id FROM comunicados WHERE titulo='Exemplo de comunicado da vitrine 5'")['id']
db.exe(PM, "UPDATE comunicados SET publicado_em = (SELECT max(publicado_em) FROM comunicados) + interval '1 minute' WHERE id=%s", (cid,))  # o mais recente
r = pm.post('/admin/comunicados', data={'csrf': tok(pm, f'/admin/comunicados?id={cid}'), 'acao': 'anexo', 'id': cid, 'titulo_anexo': 'Edital completo'},
            files={'arquivo': ('edital.pdf', pdf(), 'application/pdf')}, follow_redirects=True)
a = db.um(PM, 'SELECT * FROM comunicado_anexos WHERE comunicado_id=%s', (cid,))
checa(a, 'PDF anexado')
rc = anon.get(f"/anexo/{a['arquivo']}/capa")
checa(rc.status_code == 200 and rc.headers['content-type'] == 'image/webp' and rc.content[:4] == b'RIFF', f'miniatura da 1ª página do PDF ({rc.status_code})')
checa(anon.get('/anexo/00000000000000000000000000000000.pdf/capa').status_code == 404, 'miniatura de anexo inexistente: 404')
home = anon.get('/').text
blk = home[home.find('aria-labelledby="h-com"'):]
blk = blk[:blk.find('</section>')]
fx = home[home.find('<div class="faixa-com">'):]
checa(fx and fx.find('id="h-com"') < fx.find('id="h-serv"') and 'pilha' not in home, 'Comunicados volta ao lado de Serviços (mesma posição e tamanho de antes)')
checa('class="v-dest"' in blk and 'Exemplo de comunicado da vitrine 5' in blk[:blk.find('class="v-cartoes"')], 'comunicado mais recente em destaque')
checa(f"/anexo/{a['arquivo']}/capa" in blk and 'class="doc"' in blk, 'destaque usa a miniatura do PDF')
checa(blk.count('Continue lendo') == 4 and re.search(r'<ul class="v-cartoes">(.*?)</ul>', blk, re.S).group(1).count('<li>') == 3, 'destaque + 3 cartões com "Continue lendo"')
checa('class="v-lista"' in blk and 'Todos os comunicados' in blk and 'exemplo' in blk, 'lista de títulos, botão "Todos" e marca de exemplo')
checa('class="cena"' in blk, 'comunicado sem anexo usa o quadro neutro na cor do portal')
db.exe(PM, "UPDATE comunicados SET situacao='rascunho' WHERE id=%s", (cid,))
checa(anon.get(f"/anexo/{a['arquivo']}/capa").status_code == 404, 'comunicado fora do ar: miniatura não sai para o público')
db.exe(PM, "UPDATE comunicados SET situacao='publicado' WHERE id=%s", (cid,))

# ---------- 4) páginas de notícia e comunicado: largura total com coluna à direita ----------
pc = anon.get(f'/comunicados/{cid}').text
lado = pc[pc.find('<aside class="lateral"'):]
checa('class="com-lateral"' in pc and 'Comunicados e avisos' in lado and 'Tempo em' in lado, 'comunicado com coluna: comunicados e previsão do tempo')
checa('Exemplo de comunicado da vitrine 5' not in lado, 'a coluna não repete o comunicado aberto')
checa('Base legal' in pc, 'comunicado mantém "Base legal:"')
lc = anon.get('/comunicados').text
checa('class="lista-not lista-com"' in lc and f"/anexo/{a['arquivo']}/capa" in lc and '<aside class="lateral"' in lc, 'lista de comunicados com miniatura e coluna')
nid = db.um(PM, "SELECT id FROM conteudos WHERE tipo='Notícia' AND situacao='publicado' ORDER BY id LIMIT 1")
if nid:
    pn = anon.get(f"/conteudo/{nid['id']}").text
    lado_n = pn[pn.find('<aside'):]
    checa('class="com-lateral"' in pn and 'Comunicados e avisos' in lado_n and 'Tempo em' in lado_n, 'notícia com coluna à direita')
pcss = (Path(__file__).resolve().parent.parent / 'app' / 'static' / 'portal.css').read_text()
checa('.com-lateral .materia{max-width:none}' in pcss, 'matéria sem a largura máxima de 820 px quando há coluna')

if erros:
    print('ERROS:', len(erros)); [print(' -', e) for e in erros]; sys.exit(1)
print('vitrine e tempo: tudo ok')
