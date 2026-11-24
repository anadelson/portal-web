# Busca no portal antigo (24/11/2026) — SEM internet: o "portal antigo" é um site FICTÍCIO servido por httpx.MockTransport.
# Só contra banco de TESTE recém-provisionado:  TESTE=1 PYTHONPATH=. python tests/teste_portal_antigo.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from pathlib import Path
import httpx
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app import config, db, orgaos, portal_antigo as PA
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)

# ---------- site fictício ----------
H = 'www.portal-antigo.test'
def foto(semente, w=640, h=420):
    import random
    rnd = random.Random(semente); im = Image.new('RGB', (w, h))
    im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(w * h)])
    b = io.BytesIO(); im.save(b, 'JPEG', quality=90); return b.getvalue()
PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
MOLDE = '''<!doctype html><html><head><meta charset="utf-8"><title>{t} | Portal antigo fictício</title>{meta}</head><body>
<header class="topo"><img src="/img/logo.png" alt="Brasão"><nav class="menu"><a href="/">Início</a> <a href="/noticias/">Notícias</a> <a href="/galeria/album1.html">Galeria</a>
<a href="/sessoes/">Sessões</a> <a href="/privado/segredo.html">Restrito</a> <a href="https://outro-site.test/fora.html">Outro site</a> <a href="/login.php">Entrar</a></nav></header>
<main>{c}</main><footer class="rodape">Rua Fictícia, 1 — telefone geral (00) 0000-0000 <a href="/protegida.html">Área protegida</a> <a href="/redir">Atalho</a></footer></body></html>'''
TXT = 'Texto de exemplo fictício para o teste da migração do portal antigo. ' * 6
PAGINAS = {
    '/': MOLDE.format(t='Início', meta='', c='<h1>Bem-vindo</h1><p>Página inicial fictícia.</p><a href="/noticias/festa.html">Festa</a>'),
    '/noticias/': MOLDE.format(t='Notícias', meta='', c='<ul><li><a href="/noticias/festa.html">Festa fictícia na praça</a></li><li><a href="/noticias/obra.html">Obra fictícia</a></li></ul>'),
    '/noticias/festa.html': MOLDE.format(t='Festa fictícia na praça', meta='', c=f'<article class="noticia"><h1>Festa fictícia na praça</h1><p class="data">Publicado em 12/03/2024</p>'
                            f'<p>{TXT}</p><p>Contato do participante fictício: fulano.teste@exemplo.test, CPF 123.456.789-09.</p><img src="/img/festa1.jpg" alt="Praça cheia na festa fictícia"><img src="/img/logo.png" alt=""></article>'),
    '/noticias/obra.html': MOLDE.format(t='Obra fictícia', meta='<meta property="article:published_time" content="2024-05-02T10:00:00">', c=f'<article><h1>Obra fictícia</h1><p>{TXT}</p></article>'),
    '/galeria/album1.html': MOLDE.format(t='Galeria: desfile fictício', meta='', c='<div class="conteudo"><h1>Galeria: desfile fictício</h1>' + ''.join(f'<img src="/img/desfile{i}.jpg" alt="Desfile fictício {i}">' for i in range(4)) + '</div>'),
    '/sessoes/': MOLDE.format(t='Sessões', meta='', c='<h1>Sessões</h1><ul><li><a href="/arquivos/ata-5-sessao.pdf">Ata da 5ª Sessão Ordinária de 10/03/2025</a></li>'
                 '<li><a href="/arquivos/pl-1-2025.pdf">Projeto de Lei nº 1/2025 — texto</a></li><li><a href="/arquivos/velho.doc">Documento antigo</a></li></ul>'),
    '/privado/segredo.html': MOLDE.format(t='Segredo', meta='', c='<p>NÃO DEVERIA SER LIDA</p>'),
}
ARQS = {'/img/festa1.jpg': foto(1), '/img/logo.png': foto(9, 300, 200), **{f'/img/desfile{i}.jpg': foto(10 + i) for i in range(4)},
        '/arquivos/ata-5-sessao.pdf': PDF + b'ata', '/arquivos/pl-1-2025.pdf': PDF + b'pl', '/arquivos/velho.doc': b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'x' * 100}
pedidos = []
def site(req: httpx.Request):
    pedidos.append(str(req.url))
    if req.url.host != H:
        return httpx.Response(200, text='<html>outro site</html>', headers={'content-type': 'text/html'})
    p = req.url.path
    if p == '/robots.txt':
        return httpx.Response(200, text=f'User-agent: *\nDisallow: /privado/\nSitemap: https://{H}/sitemap.xml\n')
    if p == '/sitemap.xml':
        return httpx.Response(200, text=f'<urlset><url><loc>https://{H}/noticias/obra.html</loc></url></urlset>', headers={'content-type': 'application/xml'})
    if p == '/protegida.html':
        return httpx.Response(403, text='proibido')
    if p == '/redir':
        return httpx.Response(302, headers={'location': 'https://outro-site.test/'})
    if p in PAGINAS:
        return httpx.Response(200, text=PAGINAS[p], headers={'content-type': 'text/html; charset=utf-8'})
    if p in ARQS:
        return httpx.Response(200, content=ARQS[p], headers={'content-type': 'application/pdf' if p.endswith('.pdf') else 'application/octet-stream' if p.endswith('.doc') else 'image/jpeg'})
    return httpx.Response(404, text='não achei')
PA.TRANSPORTE = httpx.MockTransport(site)
PA.dormir = lambda s: None
_publico_real = PA.publico
PA.publico = lambda host: host.endswith('.test')
Path(config.DADOS_DIR).mkdir(parents=True, exist_ok=True)

# ---------- 1. endereço: só domínio público e que não seja o próprio portal ----------
for ruim, txt in (('http://10.0.0.5/', 'IP'), ('https://192.168.0.1', 'IP'), ('ftp://www.portal-antigo.test', 'inválido'), ('https://www.portal-antigo.test:8080/', 'porta'),
                  ('https://cmbora.localhost/', 'próprio portal'), ('https://naoexiste.invalid/', 'internet pública'), ('https://usuario:senha@www.portal-antigo.test/', 'inválido')):
    try:
        PA.validar_endereco(ruim, ['cmbora.localhost'])
        checa(False, f'endereço {ruim} deveria ser recusado')
    except ValueError as e:
        checa(txt.lower() in str(e).lower(), f'{ruim}: mensagem "{e}"')
checa(PA.validar_endereco('www.portal-antigo.test', ['cmbora.localhost']) == (f'https://{H}/', H), 'endereço sem https ganha https://')
checa(_publico_real('localhost') is False, 'localhost não é endereço público')
checa(PA.no_dominio('fotos.portal-antigo.test', H) and not PA.no_dominio('portal-antigo.test.mal.com', H), 'subdomínio aceito, domínio parecido recusado')
checa(PA.achar_data('Publicado em 12 de março de 2024') == __import__('datetime').date(2024, 3, 12), 'data por extenso')

# ---------- 2. Câmara: cadastro pelo painel ----------
cm = TestClient(app, base_url='http://cmbora.localhost'); entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
CM = 'bd_cm_bora'; ocm = next(o for o in orgaos.todos() if o['banco'] == CM)
sess = db.exe(CM, "INSERT INTO sessoes (nome, data, hora, tipo) VALUES ('5ª Sessão Ordinária de 2025 (fictícia)', '2025-03-10', '19h', 'Ordinária') RETURNING id")['id']
prop = db.exe(CM, "INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao, apresentada) VALUES ('Projeto de Lei', 1, 2025, '', 'Projeto fictício de teste.', 'Em tramitação', '2025-02-01') RETURNING id")['id']
r = cm.get('/admin/importar/portal')
checa(r.status_code == 200 and 'Nova busca' in r.text and 'Portal antigo (buscar e migrar)' in r.text and 'Base legal:' in r.text, 'tela do portal antigo')
checa('Dados antigos (importar)' in cm.get('/admin/').text, 'item do menu')
def nova(c, dados):
    return c.post('/admin/importar/portal', data=dict(dados, csrf=tok(c, '/admin/importar/portal')), follow_redirects=True)
r = nova(cm, {'acao': 'nova', 'url': H, 'assunto': 'tudo', 'limite': '100'})
checa('Confirme que o portal antigo' in r.text, 'cadastro exige a declaração')
r = nova(cm, {'acao': 'nova', 'url': 'https://cmbora.localhost/', 'assunto': 'tudo', 'declaro': '1'})
checa('próprio portal' in r.text, 'cadastro recusa o próprio portal')
r = nova(cm, {'acao': 'nova', 'url': H, 'assunto': 'tudo', 'limite': '100', 'declaro': '1'})
checa('Busca cadastrada' in r.text, 'busca cadastrada')
v = db.um(CM, 'SELECT * FROM migracao_varreduras ORDER BY id DESC LIMIT 1')
checa(v and v['situacao'] == 'aguardando' and v['dominio'] == H, 'busca aguardando o worker')
r = nova(cm, {'acao': 'nova', 'url': H, 'assunto': 'noticias', 'declaro': '1'})
checa('em andamento' in r.text, 'uma busca por vez')

# ---------- 3. varredura (o que o worker faz) ----------
for _ in range(20):
    PA.processar(ocm, v['id'], segundos=20)
    if db.um(CM, 'SELECT situacao FROM migracao_varreduras WHERE id=%s', (v['id'],))['situacao'] != 'rodando':
        break
v = db.um(CM, 'SELECT * FROM migracao_varreduras WHERE id=%s', (v['id'],))
checa(v['situacao'] == 'concluida', f"busca concluída ({v['situacao']}: {v['msg']})")
checa(not any('/privado/' in p for p in pedidos), 'robots.txt respeitado (área proibida não lida)')
checa(not any('outro-site.test' in p for p in pedidos), 'nada fora do domínio (nem por link nem por redirecionamento)')
checa(not any('/login.php' in p for p in pedidos), 'link de login não seguido')
checa(any(p.endswith('/noticias/obra.html') for p in pedidos), 'endereço do sitemap lido')
fila = {f['url'].replace(f'https://{H}', ''): f for f in db.todos(CM, 'SELECT * FROM migracao_fila WHERE varredura_id=%s', (v['id'],))}
checa('pede login' in fila.get('/protegida.html', {}).get('motivo', ''), 'página 403 fica de fora, sem contornar')
checa('robots' in fila.get('/privado/segredo.html', {}).get('motivo', ''), 'motivo do robots registrado')
checa('Office' in fila.get('/arquivos/velho.doc', {}).get('motivo', ''), '.doc antigo recusado')
itens = {i['url'].replace(f'https://{H}', ''): i for i in db.todos(CM, 'SELECT * FROM migracao_itens WHERE varredura_id=%s', (v['id'],))}
fe = itens.get('/noticias/festa.html')
checa(fe and fe['data_original'] == __import__('datetime').date(2024, 3, 12) and fe['titulo'] == 'Festa fictícia na praça', 'notícia: título e data')
checa(fe and '123.456.789-09' not in fe['texto'] and '***.***.***-**' in fe['texto'], 'CPF mascarado no texto guardado')
checa(fe and any('e-mail' in a for a in fe['avisos']) and any('CPF' in a for a in fe['avisos']), 'avisos de LGPD')
checa(fe and 'Bem-vindo' not in fe['texto'] and 'Rua Fictícia' not in fe['texto'], 'menu e rodapé fora do texto')
checa(fe and fe['sugestao'].get('destino') == 'noticia', f"sugestão da notícia: {fe and fe['sugestao']}")
checa(itens.get('/noticias/obra.html', {}).get('data_original') == __import__('datetime').date(2024, 5, 2), 'data da meta article:published_time')
al = itens.get('/galeria/album1.html')
checa(al and al['sugestao'].get('destino') == 'album' and len(al['imagens']) == 4, f"galeria: sugestão de álbum com 4 fotos ({al and al['sugestao']}, {al and len(al['imagens'])})")
ata = itens.get('/arquivos/ata-5-sessao.pdf'); pl = itens.get('/arquivos/pl-1-2025.pdf')
checa(ata and ata['sugestao'] == {'destino': 'sessao', 'alvo': sess, 'rotulo': '5ª Sessão Ordinária de 2025 (fictícia)'}, f"ata: sugestão da sessão pela data ({ata and ata['sugestao']})")
checa(pl and pl['sugestao'].get('destino') == 'proposicao' and pl['sugestao'].get('alvo') == prop, f"PL: sugestão da proposição ({pl and pl['sugestao']})")
logo = db.um(CM, "SELECT * FROM migracao_arquivos WHERE varredura_id=%s AND url LIKE '%%logo%%'", (v['id'],))
checa(not logo, 'logo (nome de layout) não é baixado')

# ---------- 4. revisão e migração ----------
uv = f"/admin/importar/portal/{v['id']}"
r = cm.get(uv)
checa(r.status_code == 200 and 'Festa fictícia na praça' in r.text and 'Sugestão:' in r.text and 'Migrar marcados' in r.text, 'tela de revisão')
checa('123.456.789-09' not in r.text, 'CPF completo nunca aparece na revisão')
anon = TestClient(app, base_url='http://cmbora.localhost')
fid = fe['imagens'][0]['arquivo_id']
checa(anon.get(f'{uv}/arquivo/{fid}', follow_redirects=False).status_code in (303, 307), 'prévia da foto só para quem está no painel')
ra = cm.get(f'{uv}/arquivo/{fid}')
checa(ra.status_code == 200 and ra.headers['content-type'] == 'image/jpeg' and 'sandbox' in ra.headers.get('content-security-policy', ''), 'prévia da foto com tipo certo e sandbox')
def acao(dados, sel=None):
    d = dict(dados, csrf=tok(cm, uv))
    if sel:
        d['sel'] = sel
    return cm.post(uv, data=d, follow_redirects=True)
r = acao({'acao': 'migrar', 'item': fe['id'], f"destino_{fe['id']}": 'noticia'})
checa('Notícia criada como rascunho' in r.text, 'migrar notícia')
c = db.um(CM, "SELECT * FROM conteudos WHERE titulo='Festa fictícia na praça'")
checa(c and c['situacao'] == 'rascunho' and c['tipo'] == 'Notícia' and c['imagem'].startswith('/midia/') and c['imagem'].endswith('.webp'), 'rascunho com capa em WEBP')
checa(c and 'Publicado originalmente em 12/03/2024' in c['html'] and '123.456.789-09' not in c['html'] and 'Migrado do portal anterior' in c['comentario'], 'texto, nota de origem e aviso')
checa('Festa fictícia na praça' not in anon.get('/noticias').text, 'rascunho não aparece no portal')
r = acao({'acao': 'migrar', 'item': fe['id'], f"destino_{fe['id']}": 'noticia'})
checa('já tratado' in r.text, 'item não migra duas vezes')
r = acao({'acao': 'migrar', 'item': al['id'], f"destino_{al['id']}": 'album'})
alb = db.um(CM, "SELECT * FROM albuns WHERE titulo='Galeria: desfile fictício'")
fotos = db.todos(CM, 'SELECT * FROM album_fotos WHERE album_id=%s', (alb['id'],)) if alb else []
checa(alb and not alb['publicado'] and len(fotos) == 4 and all(f['tem_pessoas'] and not f['autorizacao_imagem'] for f in fotos), 'álbum fora do ar, fotos sem autorização de imagem')
r = acao({'acao': 'migrar_sugeridos'}, sel=[str(ata['id']), str(pl['id'])])
checa('2 item(ns) migrado(s)' in r.text, f'migrar marcados com a sugestão: {re.findall(r"class=.msg.[^>]*>([^<]+)", r.text)}')
da = db.um(CM, 'SELECT * FROM documentos WHERE sessao_id=%s', (sess,)); dp = db.um(CM, 'SELECT * FROM documentos WHERE proposicao_id=%s', (prop,))
checa(da and da['tipo'] == 'ata' and dp and dp['tipo'] == 'texto', 'PDFs vinculados à sessão (ata) e à proposição (texto)')
checa(da and anon.get(f"/documento/{da['arquivo']}").status_code == 404, 'ata migrada só aparece com a ata publicada')
ob = itens['/noticias/obra.html']
acao({'acao': 'descartar', 'item': ob['id']})
checa(db.um(CM, 'SELECT situacao FROM migracao_itens WHERE id=%s', (ob['id'],))['situacao'] == 'descartado', 'descartar')
acao({'acao': 'restaurar', 'item': ob['id']})
checa(db.um(CM, 'SELECT situacao FROM migracao_itens WHERE id=%s', (ob['id'],))['situacao'] == 'novo', 'voltar para a revisão')
r = acao({'acao': 'migrar', 'item': ob['id'], f"destino_{ob['id']}": 'sessao'})
checa('não serve' in r.text, 'destino de arquivo recusado para página')

# ---------- 5. Prefeitura: mesmo código, destinos próprios ----------
pm = TestClient(app, base_url='http://pmbora.localhost'); entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
PM = 'bd_pm_bora'; opm = next(o for o in orgaos.todos() if o['banco'] == PM)
r = pm.get('/admin/importar/portal')
checa(r.status_code == 200 and 'Sessões, pautas e atas' not in r.text, 'Prefeitura: sem assuntos do Legislativo')
pedidos.clear()
r = nova(pm, {'acao': 'nova', 'url': H, 'assunto': 'noticias', 'limite': '50', 'declaro': '1'})
vp = db.um(PM, 'SELECT * FROM migracao_varreduras ORDER BY id DESC LIMIT 1')
for _ in range(20):
    PA.processar(opm, vp['id'], segundos=20)
    if db.um(PM, 'SELECT situacao FROM migracao_varreduras WHERE id=%s', (vp['id'],))['situacao'] != 'rodando':
        break
ip = db.todos(PM, 'SELECT * FROM migracao_itens WHERE varredura_id=%s', (vp['id'],))
checa(ip and all('/noticias/' in i['url'] for i in ip), f"Prefeitura: só notícias ({[i['url'] for i in ip]})")
try:
    PA.migrar(opm, ip[0]['id'], 'sessao', 1, 'teste'); checa(False, 'Prefeitura não tem destino sessão')
except ValueError:
    pass
checa('Migrar para' in pm.get(f"/admin/importar/portal/{vp['id']}").text, 'Prefeitura: tela de revisão')

# ---------- 6. pausar, retomar, apagar ----------
def post_lista(c, dados):
    return c.post('/admin/importar/portal', data=dict(dados, csrf=tok(c, '/admin/importar/portal')), follow_redirects=True)
pasta = Path(config.DADOS_DIR) / ocm['slug'] / 'portal-antigo' / str(v['id'])
checa(pasta.is_dir() and any(pasta.iterdir()), 'arquivos na área de revisão')
r = post_lista(cm, {'acao': 'apagar', 'busca': v['id']})
checa('Busca apagada' in r.text and not pasta.exists() and not db.um(CM, 'SELECT 1 FROM migracao_itens WHERE varredura_id=%s', (v['id'],)), 'apagar a busca e os arquivos')
checa(db.um(CM, "SELECT 1 FROM conteudos WHERE titulo='Festa fictícia na praça'") is not None, 'o que foi migrado continua')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('portal antigo: tudo ok')
