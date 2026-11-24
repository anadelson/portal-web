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
                 '<li><a href="/arquivos/pl-1-2025.pdf">Projeto de Lei nº 1/2025 — texto</a></li><li><a href="/arquivos/velho.doc">Documento antigo</a></li>'
                 '<li><a href="/arquivos/ata-2-sessao-2024.pdf">Ata da 2ª Sessão Ordinária de 20/02/2024, às 19h30</a></li>'
                 '<li><a href="/proposicoes/pl-7-2024.html">PL 7</a></li><li><a href="/proposicoes/req-3-2024.html">Requerimento 3</a></li></ul>'),
    # proposições FICTÍCIAS (só para o teste): uma com ementa, autor e data escritos; outra sem esses dados
    '/proposicoes/pl-7-2024.html': MOLDE.format(t='Projeto de Lei nº 7/2024 (fictício)', meta='', c='<article><h1>Projeto de Lei nº 7/2024 (fictício)</h1>'
                 '<p>Ementa: Dispõe sobre um assunto fictício usado só no teste da migração.</p><p>Autor: Vereador Fictício da Silva</p><p>Apresentado em 05/02/2024</p>'
                 f'<p>{TXT}</p><p><a href="/arquivos/projeto-de-lei-7-2024.pdf">Baixar</a></p></article>'),
    '/proposicoes/req-3-2024.html': MOLDE.format(t='Requerimento nº 3/2024 (fictício)', meta='', c=f'<article><h1>Requerimento nº 3/2024 (fictício)</h1><p>{TXT}</p></article>'),
    '/privado/segredo.html': MOLDE.format(t='Segredo', meta='', c='<p>NÃO DEVERIA SER LIDA</p>'),
}
ARQS = {'/img/festa1.jpg': foto(1), '/img/logo.png': foto(9, 300, 200), **{f'/img/desfile{i}.jpg': foto(10 + i) for i in range(4)},
        '/arquivos/ata-5-sessao.pdf': PDF + b'ata', '/arquivos/pl-1-2025.pdf': PDF + b'pl', '/arquivos/projeto-de-lei-7-2024.pdf': PDF + b'pl7', '/arquivos/ata-2-sessao-2024.pdf': PDF + b'ata2', '/arquivos/velho.doc': b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'x' * 100}
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

# ---------- 4b. Câmara: criar proposição e sessão a partir do portal antigo (dados conferidos; nada inventado) ----------
from datetime import date
itens = {i['url'].replace(f'https://{H}', ''): i for i in db.todos(CM, 'SELECT * FROM migracao_itens WHERE varredura_id=%s', (v['id'],))}
p7 = itens.get('/proposicoes/pl-7-2024.html'); p7pdf = itens.get('/arquivos/projeto-de-lei-7-2024.pdf')
r3 = itens.get('/proposicoes/req-3-2024.html'); a2 = itens.get('/arquivos/ata-2-sessao-2024.pdf')
checa(p7 and p7['sugestao'] == {'destino': 'nova_proposicao', 'rotulo': 'Projeto de Lei nº 7/2024'}, f"página da proposição: sugestão de criar ({p7 and p7['sugestao']})")
checa(p7pdf and p7pdf['sugestao'].get('destino') == 'nova_proposicao', f"PDF da proposição ainda inexistente: criar ({p7pdf and p7pdf['sugestao']})")
checa(a2 and a2['sugestao'].get('destino') == 'nova_sessao', f"ata de sessão inexistente: criar ({a2 and a2['sugestao']})")
c7 = PA.campos_leg(CM, p7)['proposicao']
checa(c7 == {'tipo': 'Projeto de Lei', 'numero': 7, 'ano': 2024, 'ementa': 'Dispõe sobre um assunto fictício usado só no teste da migração.', 'autor': 'Fictício da Silva',
             'apresentada': date(2024, 2, 5)}, f'campos lidos da página: {c7}')
c7pdf = PA.campos_leg(CM, p7pdf)['proposicao']
checa(c7pdf and c7pdf['ementa'].startswith('Dispõe sobre') and c7pdf['autor'] == 'Fictício da Silva', f'PDF usa a página de origem da mesma proposição: {c7pdf}')
c3 = PA.campos_leg(CM, r3)['proposicao']
checa(c3 and c3['tipo'] == 'Requerimento' and c3['ementa'] == '' and c3['autor'] == '' and PA.faltando('nova_proposicao', PA.campos_leg(CM, r3)) == ['ementa', 'autor'], f'sem dado escrito, fica em branco: {c3}')
s2 = PA.campos_leg(CM, a2)['sessao']
checa(s2 == {'tipo': 'Ordinária', 'numero': 2, 'data': date(2024, 2, 20), 'hora': '19h30'}, f'campos da sessão: {s2}')
checa(PA.campos_leg(CM, fe) == {'proposicao': None, 'sessao': None}, 'notícia comum não vira proposição nem sessão')
r = cm.get(uv)
checa('Criar a proposição (conferir os dados)' in r.text and 'abre um formulário para conferir' in r.text, 'destino de criar na revisão')
try:
    PA.migrar(ocm, p7['id'], 'nova_proposicao', None, 'teste'); checa(False, 'criar não passa pelo migrar direto')
except ValueError as e:
    checa('formulário' in str(e), 'criar só pelo formulário')
r = acao({'acao': 'migrar', 'item': p7['id'], f"destino_{p7['id']}": 'nova_proposicao'})
checa('Dispõe sobre um assunto fictício' in r.text and 'Fictício da Silva' in r.text and '2024-02-05' in r.text and 'lido no portal antigo' in r.text, 'formulário pré-preenchido')
checa('escolha conforme o original' in r.text, 'situação sem valor padrão')
uc = f"{uv}/criar/{p7['id']}"
dados7 = {'destino': 'nova_proposicao', 'tipo': 'Projeto de Lei', 'numero': '7', 'ano': '2024', 'ementa': c7['ementa'], 'autor': 'Fictício da Silva', 'apresentada': '2024-02-05', 'volta': uv}
r = cm.post(uc, data=dict(dados7, csrf=tok(cm, uv)))
checa('Escolha a situação' in r.text and 'Fictício da Silva' in r.text, 'sem situação: recusa e mantém o que foi digitado')
checa(not db.um(CM, "SELECT 1 FROM proposicoes WHERE tipo='Projeto de Lei' AND numero=7 AND ano=2024"), 'nada gravado sem a situação')
r = cm.post(uc, data=dict(dados7, situacao='Em tramitação', volta='https://fora.test/', csrf=tok(cm, uv)), follow_redirects=False)
checa(r.status_code == 303 and r.headers['location'].startswith(uv), f"volta só para a própria busca ({r.headers.get('location')})")
np7 = db.um(CM, "SELECT * FROM proposicoes WHERE tipo='Projeto de Lei' AND numero=7 AND ano=2024")
checa(np7 and np7['origem'] == 'portal_antigo' and np7['autor'] == 'Fictício da Silva' and np7['situacao'] == 'Em tramitação' and np7['apresentada'] == date(2024, 2, 5), f'proposição criada: {np7}')
tr = db.todos(CM, 'SELECT * FROM tramitacao WHERE proposicao_id=%s', (np7['id'],)) if np7 else []
checa(len(tr) == 1 and tr[0]['fase'] == 'Apresentação' and tr[0]['origem'] == 'portal_antigo', 'só a apresentação na tramitação')
checa(db.um(CM, 'SELECT situacao, destino, destino_id FROM migracao_itens WHERE id=%s', (p7['id'],)) == {'situacao': 'migrado', 'destino': 'nova_proposicao', 'destino_id': np7['id']}, 'item marcado como migrado')
cm.get(uv)   # a revisão recalcula: o PDF passa a ir para a proposição criada
s7 = db.um(CM, 'SELECT sugestao FROM migracao_itens WHERE id=%s', (p7pdf['id'],))['sugestao']
checa(s7 == {'destino': 'proposicao', 'alvo': np7['id'], 'rotulo': 'Projeto de Lei nº 7/2024'}, f'PDF encadeado à proposição criada: {s7}')
try:
    PA.criar_proposicao(ocm, p7pdf['id'], dict(dados7, situacao='Em tramitação'), 'teste'); checa(False, 'duplicata deveria ser recusada')
except ValueError as e:
    checa('já existe' in str(e), 'proposição duplicada recusada')
# lote: a ata (completa) e o requerimento (incompleto)
r = acao({'acao': 'migrar_sugeridos'}, sel=[str(a2['id']), str(r3['id'])])
checa('Conferir antes de criar' in r.text and '2ª Sessão Ordinária' in r.text and 'Falta: ementa, autor' in r.text and '19h30' in r.text, 'tabela de conferência do lote')
checa(not db.um(CM, "SELECT 1 FROM sessoes WHERE data='2024-02-20'"), 'nada criado antes de confirmar')
r = acao({'acao': 'migrar_sugeridos', 'confirmado': '1', f"realizada_{a2['id']}": '1'}, sel=[str(a2['id']), str(r3['id'])])
checa('1 item(ns) migrado(s)' in r.text and 'faltam ementa, autor' in r.text, f'lote confirmado: {re.findall(r"class=.msg.[^>]*>([^<]+)", r.text)}')
ns = db.um(CM, "SELECT * FROM sessoes WHERE data='2024-02-20'")
checa(ns and ns['origem'] == 'portal_antigo' and ns['situacao'] == 'realizada' and ns['hora'] == '19h30' and ns['nome'] == '2ª Sessão Ordinária de 2024' and ns['numero'] == 2, f'sessão criada: {ns}')
checa(ns and not (ns['pauta_publicada'] or ns['ata_publicada'] or ns['presenca_publicada'] or ns['votacao_publicada']), 'sessão sem nada publicado')
checa(ns and not db.um(CM, 'SELECT 1 FROM presencas WHERE sessao_id=%s', (ns['id'],)) and not db.um(CM, 'SELECT 1 FROM pauta_itens WHERE sessao_id=%s', (ns['id'],)), 'nenhuma presença nem pauta inventada')
dn = db.um(CM, 'SELECT * FROM documentos WHERE sessao_id=%s', (ns['id'],)) if ns else None
checa(dn and dn['tipo'] == 'ata' and anon.get(f"/documento/{dn['arquivo']}").status_code == 404, 'ata anexada, fora do ar até ser publicada')
checa(db.um(CM, 'SELECT situacao FROM migracao_itens WHERE id=%s', (r3['id'],))['situacao'] == 'novo', 'incompleto continua para revisar')
checa(not db.um(CM, "SELECT 1 FROM proposicoes WHERE tipo='Requerimento' AND numero=3 AND ano=2024"), 'requerimento sem ementa/autor não foi criado')

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
checa('Criar a proposição' not in pm.get(f"/admin/importar/portal/{vp['id']}").text, 'Prefeitura: sem criar proposição/sessão')
checa(pm.get(f"/admin/importar/portal/{vp['id']}/criar/{ip[0]['id']}?destino=nova_sessao").status_code == 404, 'Prefeitura: formulário de criar não existe')
try:
    PA.criar_sessao(opm, ip[0]['id'], {'tipo': 'Ordinária', 'data': '2024-01-01', 'hora': '19h', 'numero': '1'}, 'teste'); checa(False, 'Prefeitura não cria sessão')
except ValueError:
    pass

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
