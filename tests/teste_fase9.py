# Fase 9: mapa do layout, avaliação (cookie + limite por IP), consultas (teste sem gravar, parâmetros com histórico), lançamento manual,
# identidade (contraste AA, favicon, redes, IBGE, álbuns e defeso), editor (HTML limpo, versões) e login em duas etapas.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_fase9.py
import io, json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

def cli(host, ip='203.0.113.10'):
    return TestClient(app, base_url=f'http://{host}', headers={'x-forwarded-for': ip})
erros = []
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text) or (sem and sem in r.text):
        erros.append(f'{nome}: {r.status_code} {r.text[:300]}')
    return r
def checa(cond, nome):
    if not cond:
        erros.append(nome)
def png(w=64, h=64, cor=(14, 77, 100)):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), cor).save(b, 'PNG'); return b.getvalue()
PM = 'bd_pm_bora'
pm = cli('pmbora.localhost')

# ---------- 2) avaliação ----------
pub = cli('pmbora.localhost', '198.51.100.7')
r = pub.get('/transparencia'); t = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
r = pub.post('/avaliar', data={'csrf': t, 'pagina': '/transparencia', 'util': 'sim'}, headers={'Accept': 'application/json'})
checa(r.status_code == 200 and r.json()['ok'] and 'aval=' in r.headers.get('set-cookie', ''), f'avaliação por JS grava e devolve o cookie: {r.status_code} {r.text[:120]}')
checa('Obrigado' in r.json().get('msg', '') and 'a partir de' in r.json().get('msg', ''), 'mensagem de agradecimento com a data da próxima avaliação')
r = pub.post('/avaliar', data={'csrf': t, 'pagina': '/transparencia', 'util': 'nao'}, headers={'Accept': 'application/json'})
checa(not r.json()['ok'] and 'já avaliou' in r.json()['msg'], 'mesma página pelo mesmo navegador é recusada (cookie)')
checa(db.um(PM, "SELECT count(*) n FROM avaliacoes WHERE pagina='/transparencia'")['n'] == 1, 'só uma avaliação gravada')
checa('Você já avaliou esta página' in pub.get('/transparencia').text, 'página mostra que já foi avaliada (sem os botões)')
# sem JS: volta à página com a mensagem no próprio bloco do formulário
r = pub.post('/avaliar', data={'csrf': t, 'pagina': '/dados-abertos', 'util': 'sim'}, follow_redirects=True)
blk = r.text[r.text.find('id="avaliar"'):][:600]
checa('Obrigado! Sua avaliação' in blk, 'sem JS a mensagem aparece no bloco da avaliação (não no topo)')
checa(db.um(PM, "SELECT ip_hash FROM avaliacoes ORDER BY id DESC LIMIT 1")['ip_hash'] not in ('', '198.51.100.7') and '198.51.100.7' not in json.dumps(db.todos(PM, 'SELECT ip_hash FROM avaliacoes')), 'IP guardado só como hash')
# limite: 5 por hora por conexão (outros navegadores, mesmo IP)
for k in range(5):
    c = cli('pmbora.localhost', '192.0.2.50'); h = c.get('/'); tt = re.search(r'name="csrf" value="([^"]+)"', h.text).group(1)
    r = c.post('/avaliar', data={'csrf': tt, 'pagina': f'/pagina-{k}', 'util': 'sim'}, headers={'Accept': 'application/json'})
checa(r.status_code == 200, 'até 5 avaliações por hora passam')
c = cli('pmbora.localhost', '192.0.2.50'); h = c.get('/'); tt = re.search(r'name="csrf" value="([^"]+)"', h.text).group(1)
r = c.post('/avaliar', data={'csrf': tt, 'pagina': '/pagina-6', 'util': 'sim'}, headers={'Accept': 'application/json'})
checa(r.status_code == 429 and 'Muitas avaliações' in r.json()['msg'], f'6ª avaliação na hora pela mesma conexão é recusada: {r.status_code}')
ok(pm.get('/privacidade'), txt='“aval”', nome='privacidade descreve o cookie da avaliação')

# ---------- login em duas etapas (6) ----------
r = ok(pm.get('/admin/login'), txt='1 · E-mail e senha', nome='login etapa 1')
checa('Esqueci minha senha' in r.text and 'aria-current="step"' in r.text, 'login com etapas e "esqueci minha senha"')
ok(pm.get('/admin/esqueci'), txt='administrador', nome='esqueci minha senha')
r = pm.post('/admin/login', data={'csrf': tok(pm, '/admin/login'), 'email': 'ninguem@x.com', 'senha': 'errada123456'}, follow_redirects=True)
checa('E-mail ou senha incorretos' in r.text and '2 · Código' in r.text and 'name="codigo"' not in r.text, 'senha errada: mensagem genérica e sem a etapa do código')
r = entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
ok(r, txt='Visão geral', nome='login completo (senha + segundo fator)')
checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Tentativa de acesso recusada%%'"), 'tentativa recusada vai para a auditoria')
g = cli('gestao.localhost')
ok(g.get('/login'), txt='Console do gestor', nome='console login personalizado')
ok(g.get('/esqueci'), txt='outro gestor', nome='console esqueci')
entrar(g, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
ok(g.get('/aparencia'), txt='Aparência da tela de login', nome='console aparência')
ok(g.post('/aparencia', data={'csrf': tok(g, '/aparencia'), 'titulo': 'Plataforma de teste', 'credito': 'Foto de teste'}, files={'arquivo': ('f.png', png(400, 240), 'image/png')}, follow_redirects=True), txt='Aparência salva', nome='console fundo do login')
r = cli('gestao.localhost').get('/login'); checa('Plataforma de teste' in r.text and '/login-fundo/' in r.text, 'console login com título e fundo')
u = re.search(r"url\('(/login-fundo/[^']+)'\)", r.text).group(1); ok(cli('gestao.localhost').get(u), nome='imagem de fundo do console servida')

# ---------- 1) mapa do layout ----------
r = ok(pm.get('/admin/pagina-inicial'), txt='Onde fica no portal', nome='tela de blocos com mapa')
lista = re.findall(r'<li data-id="(\d+)"[^>]*data-regiao="(\w+)"', r.text)
mapa = re.findall(r'<div class="r [^"]*" data-id="(\d+)"', r.text)
checa([i for i, reg in lista if reg != 'topo'] == mapa, 'mapa na mesma ordem da lista')
princ = [i for i, reg in lista if reg == 'principal']
nova = [i for i, _ in lista]; a, b = nova.index(princ[0]), nova.index(princ[1]); nova[a], nova[b] = nova[b], nova[a]
vis = [i for i, _ in lista if i != princ[2]]
r = pm.post('/admin/pagina-inicial', data={'csrf': tok(pm, '/admin/pagina-inicial'), 'acao': 'salvar', 'ordem': nova, 'visivel': vis}, follow_redirects=True)
ok(r, txt='Página inicial salva', nome='salvar ordem e exibição de uma vez')
lista2 = [i for i, _ in re.findall(r'<li data-id="(\d+)"[^>]*data-regiao="(\w+)"', r.text)]
checa(lista2 == nova, 'ordem salva e o mapa acompanha')
checa(f'data-id="{princ[2]}"' in r.text and re.search(rf'class="r [^"]*off[^"]*" data-id="{princ[2]}"', r.text), 'bloco desligado aparece tracejado no mapa')
ruim = list(nova); ruim.insert(0, ruim.pop(ruim.index(princ[0])))
ok(pm.post('/admin/pagina-inicial', data={'csrf': tok(pm, '/admin/pagina-inicial'), 'acao': 'salvar', 'ordem': ruim, 'visivel': vis}, follow_redirects=True), txt='dentro da mesma região', nome='não move bloco para outra região')

# ---------- 2.3) painel da avaliação ----------
for aba in ('pagina', 'mes', 'comentarios', 'regras'):
    ok(pm.get(f'/admin/participacao?aba={aba}'), nome=f'avaliação aba {aba}')
ok(pm.post('/admin/participacao', data={'csrf': tok(pm, '/admin/participacao?aba=regras'), 'acao': 'aval_regras', 'dias': '7'}, follow_redirects=True), txt='Regra salva', nome='prazo configurável')
checa((db.cfg(PM, 'avaliacao') or {}).get('dias') == 7, 'prazo gravado')
db.exe(PM, "INSERT INTO avaliacoes (pagina, util, comentario) VALUES ('/x', false, 'comentário de teste')")
cid = db.um(PM, "SELECT id FROM avaliacoes WHERE comentario='comentário de teste'")['id']
pm.post('/admin/participacao', data={'csrf': tok(pm, '/admin/participacao?aba=regras'), 'acao': 'coment_remover', 'id': cid})
checa(db.um(PM, 'SELECT moderacao FROM avaliacoes WHERE id=%s', (cid,))['moderacao'] == 'removido', 'moderação remove o comentário')

# ---------- 3) consultas: teste sem gravar, parâmetros com confirmação e histórico ----------
import httpx
from app.coletores import comum
class _Resp:
    def __init__(s, url): s.status_code = 200; s.url = url
    def raise_for_status(s): pass
    def json(s):
        return {'items': [{'title': 'Edital de teste (fictício)', 'description': 'objeto', 'modalidade_licitacao_nome': 'Pregão', 'data_publicacao_pncp': '2026-11-01T10:00:00',
                           'valor_global': 1000, 'situacao_nome': 'Divulgada', 'item_url': '/editais/1', 'numero_controle_pncp': 'X-1', 'ano': 2026, 'numero_sequencial': 1}], 'total': 1}
class _Cli:
    def __init__(s, *a, **k): pass
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def get(s, url, params=None): return _Resp(url)
orig = comum.httpx.Client
comum.httpx.Client = _Cli
try:
    from app import consultas as CS
    o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
    antes = {t: db.um(PM, f'SELECT count(*) n FROM {t}')['n'] for t in ('licitacoes',)}
    rel = CS.ensaiar(o, 'pncp', {'ibge': '3507209', 'cnpj': '00.000.000/0001-00'})
    checa(rel.get('requisicoes') and 'pncp.gov.br' in rel['requisicoes'][0]['url'] and rel['requisicoes'][0]['status'] == 200, f'ensaio registra a requisição montada: {str(rel)[:200]}')
    checa({t: db.um(PM, f'SELECT count(*) n FROM {t}')['n'] for t in antes} == antes, 'ensaio NÃO grava nada')
    checa(db.ENSAIO.get() is None, 'modo ensaio desligado depois do teste')
    # escrita direta durante o ensaio é bloqueada
    tk = db.ENSAIO.set({}); db.exe(PM, "INSERT INTO foto_categorias (nome) VALUES ('nao-deveria')"); db.ENSAIO.reset(tk)
    checa(not db.um(PM, "SELECT 1 FROM foto_categorias WHERE nome='nao-deveria'"), 'escrita bloqueada no ensaio')
    ok(pm.get('/admin/integracoes?fonte=pncp'), txt='Como a consulta é montada', nome='tela de integrações')
    u = '/admin/integracoes?fonte=pncp'
    r = pm.post('/admin/integracoes/pncp', data={'csrf': tok(pm, u), 'volta': u, 'acao': 'salvar', 'p_ibge': '3507209', 'p_cnpj': '11.111.111/0001-11', 'confirmo': '1'}, follow_redirects=True)
    checa('teste a consulta' in r.text, 'salvar sem testar é recusado')
    r = pm.post('/admin/integracoes/pncp', data={'csrf': tok(pm, u), 'volta': u, 'acao': 'testar', 'p_ibge': '35072', 'p_cnpj': 'x'}, follow_redirects=True)
    checa('7 dígitos' in r.text, 'parâmetro inválido é recusado antes do teste')
    r = pm.post('/admin/integracoes/pncp', data={'csrf': tok(pm, u), 'volta': u, 'acao': 'testar', 'p_ibge': '3507209', 'p_cnpj': '11.111.111/0001-11'}, follow_redirects=True)
    ok(r, txt='nada foi gravado', nome='testar consulta pelo painel')
    checa('valores do último teste, ainda não salvos' in r.text and 'HTTP 200' in r.text, 'tela mostra o resultado do teste e os parâmetros em teste')
    r = pm.post('/admin/integracoes/pncp', data={'csrf': tok(pm, u), 'volta': u, 'acao': 'salvar', 'p_ibge': '3507209', 'p_cnpj': '11.111.111/0001-11'}, follow_redirects=True)
    checa('Marque a confirmação' in r.text, 'mudança de parâmetro exige confirmação')
    r = pm.post('/admin/integracoes/pncp', data={'csrf': tok(pm, u), 'volta': u, 'acao': 'salvar', 'p_ibge': '3507209', 'p_cnpj': '11.111.111/0001-11', 'confirmo': '1'}, follow_redirects=True)
    ok(r, txt='Parâmetros salvos', nome='salvar e coletar depois do teste')
    checa(db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='pncp'", (o['id'],))['params']['cnpj'] == '11.111.111/0001-11', 'parâmetro salvo')
    checa(db.um(db.PLATAFORMA, "SELECT 1 FROM fontes_historico WHERE orgao_id=%s AND fonte='pncp'", (o['id'],)), 'mudança no histórico')
    checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Integrações: parâmetros da fonte pncp alterados%%'"), 'mudança na auditoria')
    # Fiorilli: todos os endpoints aparecem com o GET montado
    r = ok(pm.get('/admin/integracoes?fonte=fiorilli'), nome='Fiorilli na tela de integrações')
    for lst in ('ReceitaOrcamentaria', 'DespesasPorUnidade', 'DespesasGerais', 'Diarias', 'Licitacoes', 'Contratos', 'Servidores'):
        checa(lst in r.text, f'Fiorilli mostra o endpoint {lst}')
finally:
    comum.httpx.Client = orig
# indicadores em abas e sub-abas (liga o módulo "bi" só neste banco de teste)
db.exe(db.PLATAFORMA, "INSERT INTO orgao_modulos (orgao_id, chave, contratado) VALUES (%s,'bi',TRUE) ON CONFLICT (orgao_id, chave) DO UPDATE SET contratado=TRUE", (o['id'],))
_m = db.cfg(PM, 'modulos_ligados', {}) or {}; _m['bi'] = True; db.set_cfg(PM, 'modulos_ligados', _m)
r = ok(pm.get('/admin/indicadores?area=edu'), nome='indicadores aba Educação')
checa('aria-current="page">Educação' in r.text and 'class="subabas"' in r.text and '>INEP<' in r.text, 'abas por área e sub-abas por fonte')
ok(pm.get('/admin/indicadores?area=edu&sub=inep'), txt='download.inep.gov.br', nome='sub-aba INEP mostra a consulta montada')
ok(pm.get('/admin/indicadores?area=geral'), txt='Coletar agora', nome='aba de coleta e agrupamento')
# lançamento manual quando a consulta falha
ind = db.um(PM, "SELECT * FROM indicadores WHERE chave='mun_populacao'")
db.exe(PM, "UPDATE indicadores SET ultima_tentativa=now(), ultima_ok=NULL WHERE id=%s", (ind['id'],))
url = f"/admin/indicadores/{ind['id']}"
ok(pm.get(url), txt='Fonte informada', nome='lançamento manual liberado quando a coleta falha')
ok(pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2026', 'data_ref': '2026-07-01', 'valor': '900', 'motivo': 'Valor FICTÍCIO de teste: consulta ao IBGE falhou'}, follow_redirects=True),
   txt='fonte do valor', nome='lançamento sem fonte informada é recusado')
pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2026', 'data_ref': '2026-07-01', 'valor': '900', 'fonte_informada': 'Documento de teste', 'motivo': 'Valor FICTÍCIO de teste: consulta ao IBGE falhou'})
checa(db.um(PM, "SELECT 1 FROM indicador_valores WHERE indicador_id=%s AND origem='manual' AND nota LIKE 'Fonte: Documento de teste%%'", (ind['id'],)), 'lançamento manual com a fonte informada')
checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao ILIKE '%%lan%%' ORDER BY id DESC LIMIT 1"), 'lançamento manual auditado')

# ---------- 4) identidade ----------
for aba in ('dados', 'tema', 'imagens', 'favicon', 'redes', 'municipio', 'fotos'):
    ok(pm.get(f'/admin/identidade?aba={aba}'), nome=f'identidade aba {aba}')
r = pm.post('/admin/identidade/cores', data={'csrf': tok(pm, '/admin/identidade?aba=tema'), 'cor': '#7FB7C9', 'cor_destaque': '#F0B429'}, follow_redirects=True)
checa('Recusado' in r.text and (db.cfg(PM, 'identidade') or {}).get('cor') != '#7FB7C9', 'cor sem contraste AA é recusada')
r = pm.post('/admin/identidade/cores', data={'csrf': tok(pm, '/admin/identidade?aba=tema'), 'cor': '#0e4d64', 'cor_destaque': '#F0B429'}, follow_redirects=True)
checa('Cores salvas' in r.text and db.cfg(PM, 'identidade')['cor'] == '#0E4D64', 'cor com contraste AA é aceita')
r = pm.post('/admin/identidade/favicon', data={'csrf': tok(pm, '/admin/identidade?aba=favicon'), 'acao': 'enviar'}, files={'png': ('f.png', png(512, 512), 'image/png')}, follow_redirects=True)
fav = (db.cfg(PM, 'identidade') or {}).get('favicon') or {}
checa(set(fav) >= {'16', '32', '180', '512'}, f'favicon gerado nos 4 tamanhos: {fav}')
if fav:
    rr = pm.get(fav['32']); checa(rr.status_code == 200 and rr.content[:4] == b'\x89PNG', 'favicon servido')
    from PIL import Image
    checa(Image.open(io.BytesIO(pm.get(fav['180']).content)).size == (180, 180), 'favicon 180×180')
    checa(f'href="{fav["32"]}"' in pm.get('/').text, 'portal declara o favicon')
svg_ruim = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
r = pm.post('/admin/identidade/favicon', data={'csrf': tok(pm, '/admin/identidade?aba=favicon'), 'acao': 'enviar'}, files={'png': ('f.png', png(512, 512), 'image/png'), 'svg': ('f.svg', svg_ruim, 'image/svg+xml')}, follow_redirects=True)
checa('SVG recusado' in r.text, 'SVG com script é recusado')
r = pm.post('/admin/identidade/favicon', data={'csrf': tok(pm, '/admin/identidade?aba=favicon'), 'acao': 'enviar'}, files={'png': ('f.png', png(300, 120), 'image/png')}, follow_redirects=True)
checa('quadrada' in r.text, 'favicon não quadrado é recusado')
# redes
r = pm.post('/admin/identidade/redes', data={'csrf': tok(pm, '/admin/identidade?aba=redes'), 'tipo': ['instagram'], 'url': ['https://exemplo.invalid/perfil'], 'ordem': ['10'], 'conta': ['']}, follow_redirects=True)
checa('Não salvo' in r.text, 'endereço de outra rede é recusado')
r = pm.post('/admin/identidade/redes', data={'csrf': tok(pm, '/admin/identidade?aba=redes'), 'tipo': ['youtube', 'instagram'], 'url': ['https://www.youtube.com/@canalteste', 'https://www.instagram.com/perfilteste'],
                                              'ordem': ['20', '10'], 'conta': ['UC' + 'a' * 22, '17841400000000000']}, follow_redirects=True)
ok(r, txt='Redes sociais salvas', nome='redes salvas')
h = pm.get('/').text
checa('aria-label="Instagram"' in h and h.find('aria-label="Instagram"') < h.find('aria-label="YouTube"'), 'rodapé com ícones na ordem')
# sincronizar (APIs simuladas, com credenciais simuladas)
from app.coletores import redes as RS
from app import credenciais as CR
o_cred = CR.obter
CR.obter = lambda f: ('chave', 'TESTE') if f in ('youtube', 'meta') else None
class _R2:
    def __init__(s, url, params): s.status_code = 200; s.url = url; s.p = params or {}
    @property
    def content(s): return png(320, 180)
    def json(s):
        if 'googleapis' in s.url:
            return {'items': [{'snippet': {'title': 'Vídeo de teste', 'publishedAt': '2026-11-05T12:00:00Z', 'resourceId': {'videoId': 'aqz-KE-bpKQ'}, 'thumbnails': {'medium': {'url': 'https://i.ytimg.com/vi/x/mq.jpg'}}}}]}
        return {'data': [{'caption': 'Publicação de teste', 'media_type': 'IMAGE', 'media_url': 'https://scontent.cdninstagram.com/x.jpg', 'permalink': 'https://www.instagram.com/p/teste/', 'timestamp': '2026-11-06T12:00:00+0000'}]}
class _C2:
    def __init__(s, *a, **k): pass
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def get(s, url, params=None): return _R2(url, params)
o_cli = RS.httpx.Client
RS.httpx.Client = _C2
try:
    res = RS.coletar(o, {})
finally:
    RS.httpx.Client = o_cli; CR.obter = o_cred
feed = (db.cfg(PM, 'redes_feed') or {}).get('itens', [])
checa(len(feed) == 2 and all(x['img'].startswith('/midia/') for x in feed), f'feed das redes com miniaturas servidas pelo portal: {res}')
h = pm.get('/').text
checa('Nas redes' in h and 'Publicação de teste' in h and 'cdninstagram' not in h and 'i.ytimg.com/vi/x' not in h, 'bloco "Nas redes" sem imagens de terceiros')
# dados do município (IBGE) — API simulada
from app.coletores import indicadores as IND
o_b = IND.buscar
IND.buscar = lambda f, url, params=None, **k: ([{'id': 29167, 'res': [{'localidade': '3507209', 'res': {'2024': '118.951', '2025': '118.951'}}]}] if '/33/' in url else [])
try:
    IND.coletar_ibge(o, {'ibge': '3507209'})
finally:
    IND.buscar = o_b
r = ok(pm.get('/admin/identidade?aba=municipio'), txt='Área territorial', nome='IBGE preenche a área territorial')
checa('118,9' in r.text or '119,0' in r.text, 'área com o valor do IBGE')
pm.post('/admin/identidade/municipio', data={'csrf': tok(pm, '/admin/identidade?aba=municipio'), 'distancia_capital': '~500 km', 'idhm': '0,746 (2010)'})
h = pm.get('/').text
checa('Área territorial' in h and 'Distância da capital*' in h and 'Fonte: IBGE' in h, 'bloco do município: automáticos + manuais marcados')
# álbuns: licença, autorização, categoria suspensa no defeso
U = '/admin/identidade?aba=fotos'
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, U), 'acao': 'categoria', 'nome': 'Eventos da gestão', 'suspender': '1'})
cat = db.um(PM, "SELECT id FROM foto_categorias WHERE nome='Eventos da gestão'")['id']
r = pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, U), 'acao': 'album', 'titulo': 'Álbum de teste', 'categoria_id': cat, 'publicado': '1'}, follow_redirects=True)
aid = db.um(PM, "SELECT id FROM albuns WHERE titulo='Álbum de teste'")['id']
UA = f'/admin/identidade?aba=fotos&album={aid}'
r = pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'foto', 'album_id': aid, 'alt': 'Praça de teste vista de cima', 'credito': 'Teste', 'licenca': 'Sem licença'}, files={'arquivo': ('a.png', png(), 'image/png')}, follow_redirects=True)
checa('licença' in r.text.lower() and not db.um(PM, 'SELECT 1 FROM album_fotos WHERE album_id=%s', (aid,)), 'licença obrigatória')
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'foto', 'album_id': aid, 'alt': 'Praça de teste vista de cima', 'credito': 'Teste', 'licenca': 'CC BY 4.0'}, files={'arquivo': ('a.png', png(), 'image/png')})
pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'foto', 'album_id': aid, 'alt': 'Pessoas em evento de teste', 'credito': 'Teste', 'licenca': 'CC BY 4.0', 'tem_pessoas': '1'}, files={'arquivo': ('b.png', png(cor=(200, 0, 0)), 'image/png')})
fotos = db.todos(PM, 'SELECT * FROM album_fotos WHERE album_id=%s ORDER BY id', (aid,))
r = ok(pm.get(f'/fotos/{aid}'), txt='Licença: CC BY 4.0', nome='álbum publicado')
checa(fotos[0]['url'] in r.text and fotos[1]['url'] not in r.text, 'foto com pessoas sem autorização não publica')
t = tok(pm, '/admin/eleicao')
pm.post('/admin/eleicao', data={'csrf': t, 'acao': 'salvar', 'nome': 'Teste', 'inicio': '2020-01-01', 'fim': '2099-01-01', 'aviso': 'on', 'bloquear': 'on'})
ok(pm.get(f'/fotos/{aid}'), 404, nome='categoria suspensa some no defeso')
checa('Álbum de teste' not in pm.get('/fotos').text, 'álbum da categoria suspensa fora da lista no defeso')
checa('Nas redes' not in pm.get('/').text, 'feed das redes suspenso no defeso')
pm.post('/admin/eleicao', data={'csrf': tok(pm, '/admin/eleicao'), 'acao': 'salvar', 'nome': 'Eleições municipais 2028', 'inicio': '2028-07-01', 'fim': '2028-10-01', 'aviso': 'on', 'bloquear': 'on'})
ok(pm.get(f'/fotos/{aid}'), nome='álbum volta depois do defeso')
r = pm.post('/admin/identidade/fotos', data={'csrf': tok(pm, UA), 'acao': 'destaque_portal', 'album_id': aid, 'foto_id': fotos[1]['id']}, follow_redirects=True)
checa('não pode ser o destaque' in r.text, 'foto com pessoas sem autorização não vira destaque')

# ---------- 5) editor ----------
sujo = ('<h1 style="color:red">Título colado</h1><p class="MsoNormal" style="font-family:Calibri">Texto <b>forte</b> <span style="x">e</span> '
        '<a href="javascript:alert(1)">link ruim</a> <a href="https://www.gov.br">link bom</a></p><script>alert(1)</script><table><tr><td>a</td></tr></table>')
t = tok(pm, '/admin/conteudos/novo')
r = pm.post('/admin/conteudos/salvar', data={'csrf': t, 'tipo': 'Página', 'secao': 'Serviços', 'titulo': 'Teste do editor', 'resumo': 'r', 'texto': '', 'html': sujo, 'classe': 'serv', 'acao': 'rascunho'}, follow_redirects=True)
c = db.um(PM, "SELECT * FROM conteudos WHERE titulo='Teste do editor'")
checa(c and '<script' not in c['html'] and 'style=' not in c['html'] and 'class=' not in c['html'] and 'javascript:' not in c['html'] and 'https://www.gov.br' in c['html'] and '<strong>forte</strong>' in c['html'],
      f"HTML limpo: {c and c['html'][:300]}")
checa(c and 'Texto forte' in c['texto'], 'texto puro derivado do HTML')
t = tok(pm, f"/admin/conteudos/{c['id']}")
r = pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': c['id'], 'tipo': 'Página', 'secao': 'Serviços', 'titulo': 'Teste do editor', 'texto': '', 'html': '<p>x</p><figure><img src="/midia/' + 'a' * 32 + '.png" alt=""></figure>', 'classe': 'serv', 'acao': 'rascunho'}, follow_redirects=True)
checa('sem texto alternativo' in r.text, 'imagem sem texto alternativo é recusada')
r = pm.post('/admin/editor/imagem', data={'csrf': tok(pm, '/admin/conteudos/novo'), 'alt': 'Imagem de teste do editor', 'credito': 'Teste'}, files={'arquivo': ('i.png', png(), 'image/png')})
img = r.json().get('url', '')
checa(img.startswith('/midia/'), 'envio de imagem do editor')
t = tok(pm, f"/admin/conteudos/{c['id']}")
pm.post('/admin/conteudos/salvar', data={'csrf': t, 'id': c['id'], 'tipo': 'Página', 'secao': 'Serviços', 'titulo': 'Teste do editor (v2)', 'texto': '', 'html': f'<p>Versão dois.</p><figure><img src="{img}" alt="Imagem de teste do editor"><figcaption>Legenda · Teste</figcaption></figure>', 'classe': 'serv', 'acao': 'rascunho'})
vs = db.todos(PM, 'SELECT * FROM conteudo_versoes WHERE conteudo_id=%s ORDER BY id', (c['id'],))
checa(len(vs) >= 2 and vs[0]['dados'], 'versões guardam o texto')
r = ok(pm.get(f"/admin/conteudos/{c['id']}/versao/{vs[0]['id']}"), txt='Removido:', nome='comparar versões')
pm.post(f"/admin/conteudos/{c['id']}/versao/{vs[0]['id']}", data={'csrf': tok(pm, f"/admin/conteudos/{c['id']}")})
checa(db.um(PM, 'SELECT titulo FROM conteudos WHERE id=%s', (c['id'],))['titulo'] == 'Teste do editor', 'versão restaurada')

# ---------- usuários: senha provisória ----------
ok(pm.get('/admin/usuarios'), txt='Senha provisória', nome='admin pode definir senha provisória')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('fase 9: tudo ok')
