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
checa(re.search(r'<div class="b l65">\s*<section class="caixa" aria-labelledby="h-diario"', h) and re.search(r'<div class="b l35">\s*<section class="selos-b"', h), 'Atos oficiais e selos dividem a linha (65/35)')
checa('id="h-videos"' in h and 'exemplo-video.svg' in h and 'youtube-nocookie.com/embed' not in h, 'galeria de vídeos sem player antes do clique')
checa('id="h-cams"' not in h and 'Vídeos e câmeras ao vivo</h2>' in h and 'exemplo-camera.svg' in h and 'data-cam=' not in h, 'mesma seção: câmeras de exemplo, sem endereço')
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
UC = '/admin/cameras'
t = pm.get(UC).text
checa('Conversor de vídeo fora do ar' in t, 'aviso de conversor fora do ar')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste', 'local': 'Local de teste', 'rtsp': 'http://x'}, follow_redirects=True)
checa('Não salvo' in r.text and 'rtsp://' in r.text, 'endereço que não é RTSP recusado')
r = pm.post(UC, data={'csrf': tok(pm, UC), 'acao': 'adicionar', 'nome': 'Câmera de teste', 'local': 'Local de teste', 'rtsp': RTSP}, follow_redirects=True)
checa('Câmera cadastrada' in r.text and 'atualizado automaticamente' in r.text, 'cadastrar câmera (conversor fora do ar avisado)')
c = db.um(PM, "SELECT * FROM cameras WHERE nome='Câmera de teste'")
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
VT._api = o_api
CFG.CHAVE_CREDENCIAIS = o_chave
checa('Câmera de teste' in anon.get('/videos').text and anon.get('/cameras', follow_redirects=False).headers.get('location') == '/videos', 'página /videos com câmeras; /cameras leva para ela')

# ---------- 5) período eleitoral: selos e vídeos saem; câmeras ficam ----------
from app import eleicao
o_def = eleicao.em_defeso
eleicao.em_defeso = lambda b: True
try:
    h = anon.get('/').text
    checa('id="h-selos"' not in h and 'Câmeras ao vivo</h2>' in h and 'data-yt=' not in h and 'Câmera de teste' in h, 'no defeso: sem selos e vídeos, câmeras ficam na galeria')
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
