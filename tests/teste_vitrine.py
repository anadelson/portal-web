# Pedido de 26/11/2026: selos e reconhecimentos (cadastro no admin, imagem e documento), galeria de vídeos do YouTube,
# câmeras ao vivo (RTSP cifrado, conversor do nó), cartões dos vereadores em 3 linhas e aviso de privacidade/cookies (LGPD).
# Dados FICTÍCIOS (selos, vídeos e câmeras de teste; nenhum endereço real). Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_vitrine.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config as CFG, vitrine as VT, catalogo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def secao(h, ident):  # trecho da seção (home) com aria-labelledby=ident, até o </section> que a fecha
    i = h.find(f'aria-labelledby="{ident}"')
    return h[i:h.index('</section>', i)] if i >= 0 else ''
def png(w=64, h=64):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), (14, 77, 100)).save(b, 'PNG'); return b.getvalue()
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
cm = TestClient(app, base_url='http://cmbora.localhost')
anon = TestClient(app, base_url='http://pmbora.localhost')
anon_cm = TestClient(app, base_url='http://cmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')

# ---------- 1) exemplos do piloto e posição dos blocos ----------
checa(db.um(PM, 'SELECT count(*) n FROM selos WHERE exemplo')['n'] == 3 and db.um(PM, 'SELECT count(*) n FROM videos WHERE exemplo')['n'] == 5, 'exemplos de selos e vídeos na Prefeitura')
checa(db.um(PM, 'SELECT count(*) n FROM cameras WHERE exemplo')['n'] == 2 and db.um(CM, 'SELECT count(*) n FROM cameras')['n'] == 0, 'câmeras de exemplo só na Prefeitura')
ordem = lambda b: [r['chave'] for r in db.todos(b, "SELECT chave FROM blocos WHERE pagina='home' AND regiao='principal' ORDER BY ordem")]
op, oc = ordem(PM), ordem(CM)
checa(op.index('selos') == op.index('diario') + 1 and op[-1] == 'videos' and 'cameras' not in op, f'Prefeitura: selos logo após Atos oficiais; galeria única de vídeos e câmeras no fim ({op})')
checa(oc.index('selos') == oc.index('emendas') + 1 and 'videos' in oc and 'cameras' not in oc, f'Câmara: selos em faixa após emendas ({oc})')
h = anon.get('/').text
checa('id="h-selos"' in h and h.count('class="exemplo">exemplo') >= 3, 'home da Prefeitura com selos marcados como exemplo')
hs = secao(h, 'h-selos')
checa(hs.count('href="/selos#selo-') == 2 and 'Veja mais (3 selos)' in hs and 'href="/selos"' in hs, 'home com 2 selos e "Veja mais" quando há mais de 2')
checa(re.search(r'<div class="b l65">\s*<section class="caixa" aria-labelledby="h-diario"', h) and re.search(r'<div class="b l35">\s*<section class="selos-b"', h), 'Atos oficiais e selos dividem a linha (65/35)')
checa('id="h-videos"' in h and 'exemplo-video.svg' in h and 'youtube-nocookie.com/embed' not in h, 'galeria de vídeos sem player antes do clique')
hv = secao(h, 'h-videos'); hk = secao(h, 'h-conheca')
checa('class="c-vivo"' in hk and 'exemplo-camera.svg' in hk and 'data-cam=' not in hk and 'href="/cameras-ao-vivo"' in hk and len(re.findall(r'<div class="cam(?: exemplo-cam)?"', hk)) == 2, 'Conheça com a faixa "ao vivo" (as 2 câmeras de exemplo, pequenas)')
checa('id="h-cams"' not in h and 'Vídeos e câmeras ao vivo</h2>' in hv and 'exemplo-camera.svg' in h and 'data-cam=' not in h, 'mesma seção: câmeras de exemplo, sem endereço')
g_ = h[h.index('id="h-videos"'):]
checa('<div class="vc dois">' in g_ and g_.index('class="vc-videos"') < g_.index('class="vc-cams"') and 'Vídeos do YouTube</h3>' in g_ and 'Câmeras ao vivo</h3>' in g_, 'vídeos e câmeras em colunas separadas, vídeos primeiro')
checa('id="aviso-cookies"' in h and 'Privacidade (LGPD)' in h and '/privacidade#cookies' in h, 'aviso de privacidade e cookies')
hc = anon_cm.get('/').text
checa('id="h-selos"' in hc and re.search(r'<div class="b ">\s*<section class="selos-b"', hc), 'Câmara: selos em faixa de largura total')
checa('id="aviso-cookies"' in hc and 'Galeria de vídeos</h2>' in hc and '<div class="vc">' in hc and 'vc-cams' not in hc, 'Câmara: aviso de cookies e só a coluna de vídeos, em largura total')
checa('Vídeos e câmeras:' in anon.get('/privacidade').text, 'política de privacidade cita vídeos e câmeras')

# ---------- 2) selos: cadastro com imagem e documento ----------
checa('/admin/selos' in pm.get('/admin/').text and '/admin/cameras' in pm.get('/admin/').text, 'menu com selos, vídeos e câmeras')
U = '/admin/selos?novo=1'
r = pm.post('/admin/selos', data={'csrf': tok(pm, U), 'acao': 'salvar', 'nome': 'x', 'instituicao': 'Inst'}, follow_redirects=True)
checa('Não salvo' in r.text, 'selo sem nome recusado')
r = pm.post('/admin/selos', data={'csrf': tok(pm, U), 'acao': 'salvar', 'nome': 'Selo de teste', 'instituicao': 'Instituição de teste', 'link': 'http://inseguro'}, follow_redirects=True)
checa('https://' in r.text and 'Não salvo' in r.text, 'link sem https recusado')
r = pm.post('/admin/selos', data={'csrf': tok(pm, U), 'acao': 'salvar', 'nome': 'Selo de teste', 'instituicao': 'Instituição de teste', 'como': 'Avaliação de teste.', 'nota': '91 de 100',
                                  'concedido_em': '2026-10-01', 'valido_ate': '2027-10-01', 'link': 'https://exemplo.test/selo', 'documento_titulo': 'Certificado de teste', 'visivel': '1', 'ordem': '1'},
            files={'imagem': ('selo.png', png(), 'image/png'), 'documento': ('cert.pdf', b'%PDF-1.4\n% teste\n%%EOF\n', 'application/pdf')}, follow_redirects=True)
checa('Selo cadastrado' in r.text, 'cadastrar selo com imagem e documento')
s = db.um(PM, "SELECT * FROM selos WHERE nome='Selo de teste'")
checa(s and re.match(r'^/midia/[0-9a-f]{32}\.webp$', s['imagem']) and re.match(r'^/midia/[0-9a-f]{32}\.pdf$', s['documento']) and not s['exemplo'], 'imagem em WEBP e documento PDF guardados')
checa(anon.get(s['imagem']).status_code == 200 and anon.get(s['documento']).headers['content-type'] == 'application/pdf', 'imagem e documento servidos pelo portal')
r = pm.post('/admin/selos', data={'csrf': tok(pm, U), 'acao': 'salvar', 'nome': 'Selo ruim', 'instituicao': 'Inst'}, files={'documento': ('x.zip', b'PK\x03\x04lixo', 'application/zip')}, follow_redirects=True)
checa('Não salvo' in r.text and not db.um(PM, "SELECT 1 FROM selos WHERE nome='Selo ruim'"), 'documento que não é PDF/imagem recusado')
p = anon.get('/selos').text
checa('Selo de teste' in p and '91 de 100' in p and 'Avaliação de teste.' in p and 'Certificado de teste (PDF' in p and 'https://exemplo.test/selo' in p, 'página /selos com instituição, nota, como e documento')
checa(p.index('Selo de teste') < p.index('Selo de exemplo'), 'selos reais antes dos exemplos')
ex = db.um(PM, 'SELECT id FROM selos WHERE exemplo ORDER BY id LIMIT 1')['id']
r = pm.post('/admin/selos', data={'csrf': tok(pm, f'/admin/selos?ed={ex}'), 'acao': 'salvar', 'id': ex, 'nome': 'Selo editado', 'instituicao': 'Instituição real de teste', 'visivel': '1'}, follow_redirects=True)
checa('Selo salvo' in r.text and not db.um(PM, 'SELECT exemplo FROM selos WHERE id=%s', (ex,))['exemplo'], 'editar exemplo tira a marca de exemplo')
arq = s['documento'].split('/')[-1]
r = pm.post('/admin/selos', data={'csrf': tok(pm, f"/admin/selos?ed={s['id']}"), 'acao': 'apagar', 'id': s['id']}, follow_redirects=True)
checa('Selo apagado' in r.text and anon.get('/midia/' + arq).status_code == 404, 'apagar selo apaga os arquivos')
checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Selo cadastrado:%%'") and db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Selo apagado:%%'"), 'auditoria dos selos')

# ---------- 3) vídeos ----------
UV = '/admin/videos'
r = pm.post(UV, data={'csrf': tok(pm, UV), 'acao': 'adicionar', 'link': 'https://exemplo.test/v', 'titulo': 'Vídeo de teste'}, follow_redirects=True)
checa('cole o link do vídeo no YouTube' in r.text, 'link fora do YouTube recusado')
checa(VT.youtube_id('https://youtu.be/aqz-KE-bpKQ?t=3') == VT.youtube_id('https://www.youtube.com/watch?v=aqz-KE-bpKQ&x=1') == VT.youtube_id('https://www.youtube.com/shorts/aqz-KE-bpKQ') == 'aqz-KE-bpKQ', 'formatos de link do YouTube')
r = pm.post(UV, data={'csrf': tok(pm, UV), 'acao': 'adicionar', 'link': 'https://www.youtube.com/watch?v=aqz-KE-bpKQ', 'titulo': 'Vídeo de teste da galeria', 'publicado_em': '2026-11-20'}, follow_redirects=True)
checa('acrescentado' in r.text, 'acrescentar vídeo')
r = pm.post(UV, data={'csrf': tok(pm, UV), 'acao': 'adicionar', 'link': 'https://youtu.be/aqz-KE-bpKQ', 'titulo': 'Repetido'}, follow_redirects=True)
checa('já está na galeria' in r.text, 'vídeo repetido recusado')
h = anon.get('/').text
checa('data-yt="aqz-KE-bpKQ"' in h and 'i.ytimg.com/vi/aqz-KE-bpKQ/hqdefault.jpg' in h and h.index('Vídeo de teste da galeria') < h.index('Vídeo de exemplo'), 'vídeo real em destaque, antes dos exemplos')
checa('Vídeo de teste da galeria' in anon.get('/videos').text, 'página /videos')

# ---------- 4) câmeras: endereço cifrado, só gravação; conversor ----------
CFG.CHAVE_CREDENCIAIS, o_chave = 'Wt1PlqXUjmWtBbBQW3uI0SeS7ksW2yXlxkX7KzQd9mM=', CFG.CHAVE_CREDENCIAIS
RTSP = 'rtsp://usuario-teste:senha-teste-123@192.0.2.10:554/stream1'
VT._api, o_api = (lambda *a, **k: (_ for _ in ()).throw(ConnectionError('sem conversor no teste'))), VT._api
def quadro_falso(url, espera=10):  # quadro fictício no lugar da câmera (nenhuma câmera real no teste)
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (1280, 720), (40, 90, 120)).save(b, 'PNG'); return b.getvalue()
VT.quadro_rtsp, o_quadro = quadro_falso, VT.quadro_rtsp
UC = '/admin/cameras'
t = pm.get(UC).text
checa('Conversor de vídeo fora do ar' in t, 'aviso de conversor fora do ar')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste', 'local': 'Local de teste', 'rtsp': 'http://x'}, follow_redirects=True)
checa('Não salvo' in r.text and 'rtsp://' in r.text, 'endereço que não é RTSP recusado')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste', 'local': 'Local de teste', 'rtsp': RTSP}, follow_redirects=True)
checa('Câmera cadastrada' in r.text and 'atualizado automaticamente' in r.text, 'cadastrar câmera (conversor fora do ar avisado)')
c = db.um(PM, "SELECT * FROM cameras WHERE nome='Câmera de teste'")
checa('Miniatura tirada da câmera' in r.text and re.match(r'^/midia/[0-9a-f]{32}\.webp$', c['miniatura'] or ''), 'miniatura tirada do RTSP no cadastro')
checa(c and 'senha-teste' not in c['rtsp'] and VT.decifrar_rtsp(c['rtsp']) == RTSP and 'pm' in c['caminho'] and '192.0.2' not in c['caminho'], 'endereço cifrado; caminho público não revela a câmera')
checa('senha-teste' not in pm.get(UC).text and '192.0.2.10' not in pm.get(UC).text, 'tela não devolve o endereço')
checa(not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE '%%senha-teste%%' OR acao LIKE '%%192.0.2%%'"), 'auditoria sem o endereço')
chamadas = []
def api_falsa(metodo, caminho, corpo=None, timeout=5):
    chamadas.append((metodo, caminho, corpo))
    if caminho.startswith('/v3/config/paths/list'):
        return {'items': [{'name': 'antiga-1234', 'source': 'rtsp://x'}]}
    return {}
VT._api = api_falsa
res = VT.sincronizar()
add = [x for x in chamadas if x[0] == 'POST']
checa(len(add) == 1 and add[0][1] == f"/v3/config/paths/add/{c['caminho']}" and add[0][2]['source'] == RTSP and add[0][2]['sourceOnDemand'], 'conversor recebe a câmera ativa, sob demanda')
checa(('DELETE', '/v3/config/paths/delete/antiga-1234', None) in chamadas and 'senha' not in res, f'conversor perde câmera que saiu; resumo sem endereço ({res})')
pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'ativa', 'id': c['id']})
checa(c['caminho'] not in VT.desejadas(), 'câmera desligada sai do conversor')
pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'ativa', 'id': c['id']})
h = anon.get('/').text
checa(f'data-cam="/cameras/{c["id"]}/"' in h and 'Assistir ao vivo' in h and 'senha-teste' not in h and c['caminho'] not in h, 'home: câmera real só com o endereço do portal')
checa(anon.get(f"/cameras/{c['id']}/").status_code == 503, 'sem conversor: 503 com aviso')
ex_c = db.um(PM, 'SELECT id FROM cameras WHERE exemplo LIMIT 1')['id']
checa(anon.get(f'/cameras/{ex_c}/').status_code == 404 and anon.get(f"/cameras/{c['id']}/..%2F..%2Fetc").status_code in (400, 404), 'câmera de exemplo e caminho estranho: 404')
checa(db.um(CM, 'SELECT count(*) n FROM cameras')['n'] == 0 and anon_cm.get(f"/cameras/{c['id']}/").status_code == 404, 'câmera de um órgão não aparece no outro')
# conversor falso que responde como o MediaMTX 1.21: o 1º pedido da playlist recebe 302 (checagem de cookie, "?cookieCheck=1")
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
PL = f"/{c['caminho']}/index.m3u8"
class ConversorFalso(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def responder(self, cod, corpo=b'', tipo='text/plain', loc=None):
        self.send_response(cod)
        if loc: self.send_header('Location', loc)
        self.send_header('Content-Type', tipo); self.send_header('Content-Length', str(len(corpo))); self.end_headers(); self.wfile.write(corpo)
    def do_GET(self):
        if self.path == PL: return self.responder(302, loc=PL + '?cookieCheck=1')
        if self.path == PL + '?cookieCheck=1': return self.responder(200, b'#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-STREAM-INF:BANDWIDTH=1\nmain_stream.m3u8\n', 'application/vnd.apple.mpegurl')
        self.responder(404)
srv = ThreadingHTTPServer(('127.0.0.1', 0), ConversorFalso); threading.Thread(target=srv.serve_forever, daemon=True).start()
VT.HLS, o_hls = f'http://127.0.0.1:{srv.server_port}', VT.HLS
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'testar', 'id': c['id']}, follow_redirects=True)
checa('ok, vídeo recebido' in r.text and 'código 302' not in r.text, 'Testar segue o 302 de checagem de cookie do conversor')
r = anon.get(f"/cameras/{c['id']}/index.m3u8", follow_redirects=False)
checa(r.status_code == 200 and r.text.startswith('#EXTM3U') and 'location' not in r.headers and c['caminho'] not in r.text, 'vídeo do portal: 302 do conversor seguido no servidor, sem expor o caminho interno')
checa(anon.get(f"/cameras/{c['id']}/nada.ts", follow_redirects=False).status_code == 404, 'arquivo inexistente no conversor: 404')
srv.shutdown(); VT.HLS = o_hls

# ---------- 4b) posição no mapa, no máximo 2 câmeras sorteadas na galeria, página /cameras-ao-vivo com o mapa ----------
checa(VT.ler_posicao('-22.2442, -50.5021') == (-22.2442, -50.5021) and VT.ler_posicao('-22,2442; -50,5021') == (-22.2442, -50.5021)
      and VT.ler_posicao('-22.2442,-50.5021') == (-22.2442, -50.5021) and VT.ler_posicao('  ') == (None, None), 'posição lida nos formatos copiados dos mapas')
for ruim in ('-22.2442', 'abc, def', '-122.5, -50.5', '-22.5, 200'):
    try:
        VT.ler_posicao(ruim); checa(False, f'posição inválida aceita: {ruim}')
    except ValueError:
        pass
h = secao(anon.get('/').text, 'h-videos')
checa(h.count('data-cam="/cameras/') == 1 and len(re.findall(r'<div class="cam(?: exemplo-cam)?"', h)) == 2 and 'Mais câmeras (3)' in h, 'com 1 real e 2 exemplos: 2 na galeria (a real sempre) e "Mais câmeras (3)"')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste 2', 'local': '', 'rtsp': RTSP.replace('stream1', 'stream2'), 'posicao': '-22,5; -50'}, follow_redirects=True)
checa('Câmera cadastrada' in r.text, 'cadastrar câmera com posição')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera ruim', 'local': '', 'rtsp': RTSP, 'posicao': '-50, 200'}, follow_redirects=True)
checa('Não salvo' in r.text and 'fora do mapa' in r.text and not db.um(PM, "SELECT 1 FROM cameras WHERE nome='Câmera ruim'"), 'posição fora do mapa recusada')
pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste 3', 'local': 'Sem posição', 'rtsp': RTSP.replace('stream1', 'stream3')})
c2 = db.um(PM, "SELECT id, lat::float lat, lon::float lon FROM cameras WHERE nome='Câmera de teste 2'")
c3 = db.um(PM, "SELECT id FROM cameras WHERE nome='Câmera de teste 3'")
checa(c2 and (c2['lat'], c2['lon']) == (-22.5, -50.0), 'posição gravada em graus decimais')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'posicao', 'id': c['id'], 'posicao': '-22.2400, -50.5000'}, follow_redirects=True)
checa('Posição no mapa gravada' in r.text and 'no mapa: -22.240000, -50.500000' in r.text and 'data-mapa-escolher="pos-' in r.text, 'trocar a posição pelo painel (com o mapa para marcar)')
vistos, ex_na_galeria = set(), False
for _ in range(25):
    hh = anon.get('/').text; h, hk = secao(hh, 'h-videos'), secao(hh, 'h-conheca')
    ik = re.findall(r'data-cam="/cameras/(\d+)/"', hk)
    checa(len(ik) == 3 and len(set(ik)) == 3 and 'exemplo-camera.svg' not in hk and 'Todas as câmeras (5)' in hk and 'sorteadas' not in hk, f'Conheça com 3 câmeras reais diferentes ({ik})')
    ids = tuple(re.findall(r'data-cam="/cameras/(\d+)/"', h))
    checa(len(ids) == 2 and len(re.findall(r'<div class="cam(?: exemplo-cam)?"', h)) == 2, f'galeria com exatamente 2 câmeras ({ids})')
    ex_na_galeria |= 'exemplo-camera.svg' in h
    vistos.add(ids)
checa(len(vistos) >= 3 and not ex_na_galeria, f'2 câmeras sorteadas a cada carregamento, reais antes dos exemplos ({len(vistos)} combinações)')
checa('Mais câmeras (5)' in h and 'href="/cameras-ao-vivo"' in h and 'a cada visita' not in h and 'só carrega quando' not in h and 'Canal oficial no YouTube' not in h, 'botão "Mais câmeras" com o total')
checa(anon.get('/videos').text.count('data-cam="/cameras/') == 2, '/videos também com 2 câmeras')
# com as câmeras no Conheça e um álbum publicado, a 2ª coluna da galeria da home vira a galeria de fotos (fictícia)
ids_alb = []  # 7 álbuns fictícios, um por dia: a home mostra só os 6 mais recentes, do mais novo ao mais antigo
for i in range(7):
    a_ = db.exe(PM, "INSERT INTO albuns (titulo, publicado, ordem, criado_em) VALUES (%s, TRUE, %s, now() - %s * interval '1 day') RETURNING id", (f'Álbum de teste {i}', 100 - i, i))['id']
    db.exe(PM, "INSERT INTO album_fotos (album_id, url, alt) VALUES (%s, '/static/img/exemplo-video.svg', 'Foto de teste')", (a_,))
    ids_alb.append(a_)
aid = ids_alb[0]
hf = secao(anon.get('/').text, 'h-videos')
vistos_alb = [int(x) for x in re.findall(r'href="/fotos/(\d+)"', hf)]
checa(vistos_alb == ids_alb[:6], f'galeria de fotos da home: 6 álbuns, os mais recentes primeiro ({vistos_alb})')
hh = anon.get('/').text; h = secao(hh, 'h-videos')
checa('Vídeos e fotos</h2>' in h and '<div class="vc dois">' in h and 'class="vc-fotos"' in h and f'href="/fotos/{aid}"' in h and 'vc-cams' not in h and 'data-cam=' not in h
      and len(re.findall(r'data-cam="/cameras/', secao(hh, 'h-conheca'))) == 3, 'com álbum: vídeos + galeria de fotos; câmeras só no Conheça')
checa(anon.get('/videos').text.count('data-cam="/cameras/') == 2, '/videos continua com as câmeras mesmo com álbum')
db.exe(PM, "UPDATE blocos SET visivel=FALSE WHERE pagina='home' AND chave='conheca'")
h = anon.get('/').text
checa('class="c-vivo"' not in h and 'vc-cams' in secao(h, 'h-videos') and 'vc-fotos' not in h, 'sem a seção Conheça as câmeras voltam para a galeria de vídeos')
db.exe(PM, "UPDATE blocos SET visivel=TRUE WHERE pagina='home' AND chave='conheca'")
db.exe(PM, 'DELETE FROM albuns WHERE id = ANY(%s)', (ids_alb,))
o_centro, VT.centro = VT.centro, (lambda ibge: {'lat': -22.25, 'lon': -50.50})
try:
    t = anon.get('/cameras-ao-vivo').text
finally:
    VT.centro = o_centro
m = re.search(r'<script type="application/json" id="dados-mapa">(.*?)</script>', t, re.S)
import json as _json
mp = _json.loads(m.group(1)) if m else {}
pts = {p['id']: p for p in mp.get('pontos', [])}
checa(t.count('data-cam="/cameras/') == 3 and 'exemplo-camera.svg' in t and f'id="cam-{c3["id"]}"' in t and 'Sem posição no mapa' in t, '/cameras-ao-vivo: todas as câmeras na lista, a sem posição avisada')
checa('data-mapa-cameras' in t and '/static/vendor/leaflet-1.9.4/leaflet.js' in t and 'tile.openstreetmap.org' in t and 'OpenStreetMap' in t, 'mapa do OpenStreetMap com atribuição e aviso de privacidade')
checa(pts.get(c['id'], {}).get('lat') == -22.24 and pts.get(c2['id'], {}).get('lon') == -50.0 and c3['id'] not in pts
      and sum(1 for p in pts.values() if p['exemplo'] and p['ilustrativa']) == 2, 'pontos do mapa: posições cadastradas; exemplos em posição ilustrativa marcada')
checa('senha-teste' not in t and '192.0.2' not in t and c['caminho'] not in t and 'rtsp' not in m.group(1), 'mapa sem endereço nem caminho interno da câmera')
checa(anon.get('/cameras', follow_redirects=False).headers.get('location') == '/cameras-ao-vivo' and anon.get('/cameras', follow_redirects=False).status_code == 302, '/cameras leva (302) para /cameras-ao-vivo')
checa('tile.openstreetmap.org' in anon.get('/').headers.get('content-security-policy', ''), 'política de segurança libera só as imagens do mapa do OpenStreetMap')
checa('/static/vendor/leaflet' not in anon.get('/').text, 'início não carrega a biblioteca do mapa')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'posicao', 'id': c2['id'], 'posicao': ''}, follow_redirects=True)
checa('Posição no mapa apagada' in r.text and db.um(PM, 'SELECT lat FROM cameras WHERE id=%s', (c2['id'],))['lat'] is None, 'apagar a posição (campo em branco)')
checa(not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE '%%senha-teste%%' OR acao LIKE '%%-22.24%%'"), 'auditoria sem endereço nem coordenadas')
# visão fixa do mapa (centro + zoom) escolhida no painel, com zoom travado opcional
def dados_mapa():
    t = anon.get('/cameras-ao-vivo').text
    m = re.search(r'<script type="application/json" id="dados-mapa">(.*?)</script>', t, re.S)
    return _json.loads(m.group(1)) if m else {}
checa(dados_mapa().get('visao') is None and 'automático' in pm.get(UC).text and 'data-mapa-visao' in pm.get(UC).text, 'mapa começa no automático; painel com o mapa da visão')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'visao', 'lat': '-22.2450', 'lon': '-50.5030', 'zoom': '16', 'travar': '1'}, follow_redirects=True)
checa('Visão do mapa gravada' in r.text and 'zoom travado' in r.text and 'Voltar ao automático' in r.text, 'gravar visão fixa com zoom travado')
checa(dados_mapa().get('visao') == {'lat': -22.245, 'lon': -50.503, 'zoom': 16, 'travar': True}, 'página das câmeras abre na visão gravada, travada')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'visao', 'lat': '-22.2450', 'lon': '-50.5030', 'zoom': '25'}, follow_redirects=True)
checa('Não salvo' in r.text and dados_mapa()['visao']['zoom'] == 16, 'zoom fora da faixa recusado (visão anterior mantida)')
pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'visao', 'lat': '-22.2450', 'lon': '-50.5030', 'zoom': '14'})
checa(dados_mapa().get('visao', {}).get('travar') is False and dados_mapa()['visao']['zoom'] == 14, 'visão sem travar o zoom')
checa(db.cfg(CM, 'cameras_mapa') is None, 'visão do mapa é de cada órgão')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'visao_auto'}, follow_redirects=True)
checa('Mapa no automático' in r.text and dados_mapa().get('visao') is None, 'voltar ao automático')
# miniatura: foto fixa de fundo do cartão (tirada no cadastro/troca do endereço ou enviada pelo admin)
c = db.um(PM, "SELECT id, miniatura FROM cameras WHERE nome='Câmera de teste'")
t = anon.get('/cameras-ao-vivo').text
checa(f'<img class="cam-mini" src="{c["miniatura"]}"' in t and 'foto de cada cartão é fixa' in t, 'cartão da câmera com a miniatura de fundo')
checa(f'class="cam-mini-adm" src="{c["miniatura"]}"' in pm.get(UC).text and 'Tirar da câmera agora' in pm.get(UC).text, 'admin mostra a miniatura e as opções')
VT.quadro_rtsp = lambda url, espera=10: (_ for _ in ()).throw(ValueError('a câmera não entregou imagem'))
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'miniatura_gerar', 'id': c['id']}, follow_redirects=True)
checa('Sem miniatura (a câmera não entregou imagem)' in r.text and db.um(PM, 'SELECT miniatura FROM cameras WHERE id=%s', (c['id'],))['miniatura'] == c['miniatura'], 'falha ao tirar da câmera mantém a miniatura anterior')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'miniatura', 'id': c['id']}, files={'imagem': ('x.txt', b'nada aqui', 'text/plain')}, follow_redirects=True)
checa('Não salvo' in r.text, 'miniatura que não é imagem recusada')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'miniatura', 'id': c['id']}, files={'imagem': ('m.png', png(1600, 900), 'image/png')}, follow_redirects=True)
m2 = db.um(PM, 'SELECT miniatura FROM cameras WHERE id=%s', (c['id'],))['miniatura']
checa('Miniatura trocada' in r.text and m2 != c['miniatura'] and re.match(r'^/midia/[0-9a-f]{32}\.webp$', m2) and anon.get(c['miniatura']).status_code == 404 and anon.get(m2).status_code == 200, 'enviar imagem troca a miniatura e apaga a antiga')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'miniatura_tirar', 'id': c['id']}, follow_redirects=True)
checa('Miniatura removida' in r.text and db.um(PM, 'SELECT miniatura FROM cameras WHERE id=%s', (c['id'],))['miniatura'] == '' and anon.get(m2).status_code == 404, 'remover a miniatura')
VT.quadro_rtsp = quadro_falso
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'trocar', 'id': c['id'], 'rtsp': RTSP}, follow_redirects=True)
checa('Endereço trocado. Miniatura tirada da câmera' in r.text and db.um(PM, 'SELECT miniatura FROM cameras WHERE id=%s', (c['id'],))['miniatura'], 'trocar o endereço tira a miniatura de novo')
checa(not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE '%%senha-teste%%' OR acao LIKE '%%192.0.2%%'"), 'auditoria da miniatura sem o endereço')
# leitor de vídeo de verdade (PyAV): um vídeo fictício gerado aqui; e câmera inexistente sem vazar a senha
VT.quadro_rtsp = o_quadro
import av, tempfile
from PIL import Image
arq = os.path.join(tempfile.mkdtemp(), 'teste.mkv')
with av.open(arq, 'w') as sai:
    st = sai.add_stream('mpeg4', rate=10); st.width, st.height, st.pix_fmt = 320, 180, 'yuv420p'
    for i in range(10):
        for pk in st.encode(av.VideoFrame.from_image(Image.new('RGB', (320, 180), (200, 20 * i, 40)))):
            sai.mux(pk)
    for pk in st.encode():
        sai.mux(pk)
q = VT.quadro_rtsp(arq, espera=5)
checa(q[:8] == b'\x89PNG\r\n\x1a\n' and Image.open(io.BytesIO(q)).size == (320, 180), 'PyAV lê um quadro do vídeo')
try:
    VT.quadro_rtsp('rtsp://usuario-teste:senha-teste-123@127.0.0.1:9/stream1', espera=2); checa(False, 'câmera inexistente deveria falhar')
except ValueError as e:
    checa('senha' not in str(e) and '127.0.0.1' not in str(e), 'erro do leitor sem endereço nem senha')
VT._api = o_api
CFG.CHAVE_CREDENCIAIS = o_chave
checa('Câmeras ao vivo' in anon.get('/videos').text, 'página /videos com câmeras')

# ---------- 5) período eleitoral: selos e vídeos saem; câmeras ficam ----------
from app import eleicao
o_def = eleicao.em_defeso
eleicao.em_defeso = lambda b: True
try:
    h = anon.get('/').text
    checa('id="h-selos"' not in h and 'Câmeras ao vivo</h2>' in h and 'data-yt=' not in h and 'data-cam="/cameras/' in h, 'no defeso: sem selos e vídeos, câmeras ficam na galeria')
    checa('suspenso durante o período eleitoral' in anon.get('/selos').text, '/selos suspenso no defeso')
finally:
    eleicao.em_defeso = o_def

# ---------- 6) vereadores em 3 linhas ----------
hc = anon_cm.get('/').text
lis = re.findall(r'<a class="vmini".*?</a>', hc, re.S)
checa(lis and all(x.count('<small') == 2 and 'class="vl2' in x and 'class="vl3"' in x for x in lis), 'cartões dos vereadores com 3 linhas')
v = db.um(CM, "SELECT * FROM vereadores WHERE apelido<>'' AND votos IS NOT NULL AND legislatura=(SELECT max(numero) FROM legislaturas) ORDER BY nome LIMIT 1")
if v:
    checa(f"{v['nome']} – {v['apelido']}" in hc and f"{v['partido']} · {v['votos']} votos" in hc, 'linha 1 nome – apelido; linha 3 partido e votos')
checa('Sem cargo na Mesa ou em comissão' in hc or ' da Mesa' in hc, 'linha 2: Mesa ou comissão')

print('ERROS:', len(erros), ' | '.join(erros) if erros else '')
