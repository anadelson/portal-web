# Pedido de 27/11/2026: Diário Oficial em plataforma de terceiros (DOSP). O portal só lista as edições, em "Diário Oficial"
# e em "Atos oficiais e oportunidades"; o clique abre a edição na plataforma. Adaptador por fixtures (tests/fixtures/dosp),
# SEM acesso à rede: toda requisição passa por um HTTP falso. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_diario_fontes.py
import os, re, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
import httpx
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app
from app import db, diario_externo as DX, diario_fontes as DF
from app.diario_fontes import dosp as DO
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def secao(h, ident):
    i = h.find(f'aria-labelledby="{ident}"')
    return h[i:h.index('</section>', i)] if i >= 0 else ''
FX = Path(__file__).parent / 'fixtures' / 'dosp'
ler = lambda n: (FX / n).read_text(encoding='utf-8')
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
PAG = 'https://www.imprensaoficialmunicipal.com.br/bora'
API = 'https://dosp.com.br/api/index.php/dioe.js/4730'


class HttpFalso:
    """Responde pelas fixtures e anota cada endereço pedido; nunca sai da máquina."""
    def __init__(self, mapa):
        self.mapa, self.pedidos = dict(mapa), []
    def get(self, url, bloqueio=None):
        self.pedidos.append(url)
        if url not in self.mapa:
            raise DF.ErroFonte('a plataforma respondeu HTTP 404')
        st, txt = self.mapa[url]
        if bloqueio and bloqueio(st, txt):
            raise DF.Bloqueio('a plataforma pediu verificação de navegador (Cloudflare); a sincronização parou sem contornar o bloqueio')
        if st != 200:
            raise DF.ErroFonte(f'a plataforma respondeu HTTP {st}')
        return txt

class SemRede:
    def get(self, url, bloqueio=None):
        raise AssertionError(f'tentou acessar a rede: {url}')
HttpReal = DF.Http
DF.Http = SemRede  # qualquer adaptador criado sem HTTP explícito (painel, worker) falha em vez de acessar a rede
NORMAL = {PAG: (200, ler('pagina.html')), API: (200, ler('dioe.txt'))}

# ---------- 1) adaptador DOSP por fixtures ----------
checa('dosp' in DF.ADAPTADORES and DF.criar('dosp', {'slug': 'bora'}, HttpFalso({})).tipo == 'dosp', 'registro: tipo dosp')
try:
    DF.criar('outra', {})
    checa(False, 'tipo desconhecido recusado')
except DF.ErroFonte:
    pass
checa(not DO.eh_bloqueio(200, ler('pagina.html')), 'página normal (com o script passivo do Cloudflare) não é bloqueio')
checa(DO.eh_bloqueio(403, ler('cloudflare.html')) and DO.eh_bloqueio(200, ler('cloudflare.html')), 'página de verificação do Cloudflare é bloqueio')
checa(not DO.eh_bloqueio(200, ler('dioe.txt')), 'JSONP não é bloqueio')
j1, j2 = DO.ler_jsonp(ler('dioe.txt')), DO.ler_jsonp(ler('dioe_p.txt'))
checa(len(j1['data']) == 3 and j1 == j2, 'JSONP puro e dentro de <p> dão o mesmo resultado')
checa(DO.link_edicao({'iddo': 895189}) == 'https://dosp.com.br/exibe_do.php?i=ODk1MTg5', 'link por base64(iddo): 895189 → ODk1MTg5')
checa(DO.link_edicao({'iddo': 1, 'link': 'javascript:alert(1)'}).startswith('https://dosp.com.br/exibe_do.php?i=')
      and DO.link_edicao({'iddo': 1, 'link': 'https://outro.exemplo/x.pdf'}).startswith('https://dosp.com.br/exibe_do.php'), 'link de fora da DOSP é ignorado')
h = HttpFalso(NORMAL)
ad = DF.criar('dosp', {'slug': 'bora'}, h)
eds = ad.listar_edicoes()
checa(ad.config.get('codigo') == '4730' and h.pedidos == [PAG, API], f'código descoberto na página ({ad.config}, {h.pedidos})')
por = {e.id_externo: e for e in eds}
checa(set(por) == {'912656', '895189', '795464'}, f'3 edições ({sorted(por)})')
e1, e2, e3 = por['912656'], por['895189'], por['795464']
checa(e1.numero == '122' and e1.data == date(2026, 11, 26) and not e1.extra and e1.paginas == 11 and e1.url.endswith('/ed-122-912656-33b0dc80c293.pdf'), 'edição recente: link direto da DOSP')
checa(e2.url == 'https://dosp.com.br/exibe_do.php?i=ODk1MTg5' and e3.numero == '1', 'sem link: exibe_do.php; número "01" vira "1"')
checa([e.id_externo for e in ad.listar_edicoes(desde=date(2026, 10, 1), ate=date(2026, 10, 31))] == ['895189'], 'filtro por data no adaptador')
h2 = HttpFalso(NORMAL); DF.criar('dosp', {'slug': 'bora', 'codigo': '4730'}, h2).listar_edicoes()
checa(h2.pedidos == [API], 'código guardado: não busca a página de novo')
h3 = HttpFalso(NORMAL); a3 = DF.criar('dosp', {'slug': 'bora', 'codigo': '9999'}, h3); a3.listar_edicoes()
checa(a3.config['codigo'] == '4730' and h3.pedidos[-2:] == [PAG, API], 'código que falha é descoberto de novo')
x = dict(j1); x['data'] = [dict(j1['data'][0], flag_extra=1)]
checa(DF.criar('dosp', {'slug': 'bora', 'codigo': '4730'}, HttpFalso({API: (200, 'parseResponse(' + __import__('json').dumps(x) + ');')})).listar_edicoes()[0].extra, 'flag_extra > 0 = extra')
for nome, mapa in (('API', {PAG: NORMAL[PAG], API: (200, ler('cloudflare.html'))}), ('página', {PAG: (403, ler('cloudflare.html'))})):
    try:
        DF.criar('dosp', {'slug': 'bora'}, HttpFalso(mapa)).listar_edicoes()
        checa(False, f'Cloudflare na {nome}: aborta')
    except DF.Bloqueio:
        pass
try:
    DO.Dosp.validar_config({'slug': '../x?y'})
    checa(False, 'slug inválido recusado')
except ValueError:
    pass
checa(DO.Dosp.validar_config({'slug': 'https://www.imprensaoficialmunicipal.com.br/Bora/'}) == {'slug': 'bora'}, 'endereço colado vira slug')

# HTTP real com transporte simulado: identificação, 1 req/s, novas tentativas; bloqueio não é repetido
chamadas, esperas = [], []
class Cliente(httpx.Client):
    def __init__(self, **kw):
        resp = Cliente.resp
        super().__init__(transport=httpx.MockTransport(lambda req: (chamadas.append(req.headers.get('user-agent')), resp.pop(0))[1]), **kw)
DF.httpx.Client, _sleep = Cliente, DF.time.sleep
DF.time.sleep = lambda s: esperas.append(s)
Cliente.resp = [httpx.Response(503, text='x'), httpx.Response(200, text='ok')]
checa(HttpReal().get('https://dosp.com.br/x') == 'ok' and len(chamadas) == 2 and chamadas[0], f'nova tentativa após HTTP 503, com User-Agent ({chamadas})')
chamadas.clear(); Cliente.resp = [httpx.Response(403, text=ler('cloudflare.html')), httpx.Response(200, text='ok')]
try:
    HttpReal().get('https://dosp.com.br/x', bloqueio=DO.eh_bloqueio)
    checa(False, 'bloqueio levanta')
except DF.Bloqueio:
    checa(len(chamadas) == 1, 'bloqueio do Cloudflare não é repetido')
DF.httpx.Client, DF.time.sleep = httpx.Client, _sleep

# ---------- 2) sincronização idempotente, falhas e alerta ----------
fid = db.exe(PM, "INSERT INTO diario_fontes (tipo, nome, config) VALUES ('dosp', 'Imprensa Oficial Municipal — DOSP (teste)', %s) RETURNING id", (Jsonb({'slug': 'bora'}),))['id']
fonte = lambda: db.um(PM, 'SELECT * FROM diario_fontes WHERE id=%s', (fid,))
checa([f['id'] for f in DX.pendentes(PM)] == [fid], 'fonte nova está pendente')
r1 = DX.sincronizar(PM, fonte(), http=HttpFalso(NORMAL))
r2 = DX.sincronizar(PM, fonte(), http=HttpFalso(NORMAL))
n = lambda: db.um(PM, 'SELECT count(*) n FROM diario_externo_edicoes WHERE fonte_id=%s', (fid,))['n']
checa(r1 == {'novas': 3, 'atualizadas': 0, 'erro': ''} and r2 == {'novas': 0, 'atualizadas': 0, 'erro': ''} and n() == 3, f'2ª execução não cria nada ({r1}, {r2})')
checa(fonte()['config'].get('codigo') == '4730' and not DX.pendentes(PM), 'código guardado na fonte; sincronizada não fica pendente')
alt = dict(NORMAL); alt[API] = (200, ler('dioe.txt').replace('"pgtotal": 11', '"pgtotal": 12'))
r3 = DX.sincronizar(PM, fonte(), http=HttpFalso(alt))
checa(r3['atualizadas'] == 1 and r3['novas'] == 0 and db.um(PM, "SELECT paginas FROM diario_externo_edicoes WHERE id_externo='912656'")['paginas'] == 12, f'edição alterada conta como atualizada ({r3})')
checa(db.um(PM, 'SELECT count(*) n FROM diario_sincronizacoes WHERE fonte_id=%s AND erros=0', (fid,))['n'] == 3, 'log das sincronizações')
alertas = lambda: db.um(PM, "SELECT count(*) n FROM diario_alertas WHERE tipo='fonte_externa'")['n']
cf = {API: (200, ler('cloudflare.html'))}
for i in range(4):
    rf = DX.sincronizar(PM, fonte(), http=HttpFalso(cf))
f = fonte()
checa('Cloudflare' in rf['erro'] and 'Cloudflare' in f['ultimo_erro'] and f['falhas_seguidas'] == 4, f'erro registrado na fonte ({f["ultimo_erro"]}, {f["falhas_seguidas"]})')
checa(alertas() == 1, 'alerta único depois de 3 falhas seguidas')
checa(n() == 3, 'falha não apaga edições')
DX.sincronizar(PM, fonte(), http=HttpFalso(NORMAL))
checa(fonte()['falhas_seguidas'] == 0 and fonte()['ultimo_erro'] == '', 'sucesso zera as falhas')
db.exe(PM, "UPDATE diario_fontes SET ultima_sincronizacao_em = now() - interval '61 minutes' WHERE id=%s", (fid,))
checa([f['id'] for f in DX.pendentes(PM)] == [fid], 'vence depois do intervalo (60 min)')
db.exe(PM, 'UPDATE diario_fontes SET ultima_sincronizacao_em = now() WHERE id=%s', (fid,))
checa(DX.tick(PM) == [], 'worker: nada vencido, nada roda (sem rede)')

# ---------- 3) portal: lista e link para a plataforma ----------
anon = TestClient(app, base_url='http://pmbora.localhost')
URL1 = 'https://dosp.com.br/diario/sp/bora/2026-11-26/ed-122-912656-33b0dc80c293.pdf'
hd = secao(anon.get('/').text, 'h-diario')
checa(f'href="{URL1}"' in hd and 'Edição nº 122' in hd and 'rel="noopener external"' in hd, 'home: edição da DOSP com link para a plataforma')
checa('Imprensa Oficial Municipal — DOSP (teste)' in hd, 'home: fonte da edição')
dg = anon.get('/diario')
t = dg.text
checa(dg.status_code == 200 and 'Base legal:' in t, '/diario com "Base legal:"')
checa(t.count('Abrir edição') == 3 and f'href="{URL1}"' in t and 'href="https://dosp.com.br/exibe_do.php?i=ODk1MTg5"' in t, '/diario: as 3 edições com link para a plataforma')
checa('Fonte oficial: Imprensa Oficial Municipal — DOSP (teste)' in t, '/diario: "Fonte oficial:"')
checa('target="_blank"' not in t, 'mesma aba por padrão')
db.exe(PM, 'UPDATE diario_fontes SET nova_aba=TRUE WHERE id=%s', (fid,))
checa('target="_blank"' in anon.get('/diario').text and '(abre em nova aba)' in anon.get('/diario').text, 'nova aba quando marcada, avisada no rótulo')

# ---------- 4) painel ----------
pm = TestClient(app, base_url='http://pmbora.localhost')
cm = TestClient(app, base_url='http://cmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
pg = pm.get('/admin/diario/fontes')
checa(pg.status_code == 200 and 'Plataformas externas' in pg.text and 'Imprensa Oficial Municipal — DOSP (teste)' in pg.text and 'Código do município na plataforma: 4730' in pg.text, 'painel: fonte, código e contagem')
checa('Plataformas externas' in pm.get('/admin/diario').text, 'aba no Diário')
checa(cm.get('/admin/diario/fontes').status_code == 404, 'Câmara sem o módulo Diário: 404')
post = lambda d: pm.post('/admin/diario/fontes', data=dict(d, csrf=tok(pm, '/admin/diario/fontes')), follow_redirects=True)
checa('só letras minúsculas' in post({'acao': 'criar', 'tipo': 'dosp', 'nome': 'Outra fonte', 'slug': '../x'}).text, 'painel: slug inválido recusado')
checa(db.um(PM, 'SELECT count(*) n FROM diario_fontes')['n'] == 1, 'nada gravado com erro')
rs = post({'acao': 'sincronizar', 'id': fid})  # HTTP padrão = SemRede: falha registrada, sem sair da máquina
checa('A sincronização falhou' in rs.text and 'erro inesperado (AssertionError)' in fonte()['ultimo_erro'], 'painel: sincronizar agora (sem rede no teste) mostra a falha')
post({'acao': 'salvar', 'id': fid, 'nome': 'DOSP (teste)', 'slug': 'bora', 'intervalo_min': '120'})
checa(fonte()['nome'] == 'DOSP (teste)' and fonte()['intervalo_min'] == 120 and fonte()['config'].get('codigo') == '4730', 'painel: salvar mantém o código do mesmo endereço')
post({'acao': 'desativar', 'id': fid})
checa(not fonte()['ativa'] and DX.pendentes(PM) == [], 'desativada: sai da sincronização')
t = anon.get('/diario').text
checa(t.count('Abrir edição') == 3 and f'href="{URL1}"' in secao(anon.get('/').text, 'h-diario'), 'desativada: o histórico continua no portal')
post({'acao': 'ativar', 'id': fid})
checa(fonte()['ativa'], 'reativada')
checa(db.um(PM, "SELECT count(*) n FROM auditoria WHERE acao LIKE 'Diário: fonte externa%%'")['n'] >= 3, 'auditoria das ações')

# ---------- 5) Diário no painel: um item no menu e tudo em abas ----------
ABAS = ['Visão geral', 'Atos', 'Edições', 'Plataformas externas', 'Órgãos', 'Signatários', 'Calendário', 'Lei, horários e teste']
def abas(t):
    m = re.search(r'<nav class="abas" aria-label="Diário Oficial">(.*?)</nav>', t, re.S)
    return (re.findall(r'>([^<]+)</a>', m.group(1)), re.findall(r'aria-current="page">([^<]+)<', m.group(1))) if m else ([], [])
for url, atual in (('/admin/diario', 'Visão geral'), ('/admin/diario?aba=atos', 'Atos'), ('/admin/diario?aba=edicoes', 'Edições'), ('/admin/diario/fontes', 'Plataformas externas'),
                   ('/admin/diario/orgaos', 'Órgãos'), ('/admin/diario/config', 'Signatários'), ('/admin/diario/config?aba=calendario', 'Calendário'), ('/admin/diario/config?aba=regras', 'Lei, horários e teste')):
    todas, cur = abas(pm.get(url).text)
    checa(todas == ABAS and cur == [atual], f'abas do Diário em {url} ({todas}, {cur})')
menu = pm.get('/admin/').text
nav = menu.split('<main')[0]
checa(nav.count('href="/admin/diario"') == 1 and not re.search(r'href="/admin/diario[/?]', nav), 'um único item "Diário Oficial" no menu do painel')
g, at, ed = pm.get('/admin/diario').text, pm.get('/admin/diario?aba=atos').text, pm.get('/admin/diario?aba=edicoes').text
checa('Edição em andamento' in g and 'Atos aguardando publicação' not in g and 'Últimas edições' not in g and 'id="h-ext"' in g, 'Visão geral: edição em andamento e plataformas externas')
checa('Atos aguardando publicação' in at and 'Edição em andamento' not in at, 'aba Atos')
checa('Últimas edições' in ed and 'Edições em plataformas externas' in ed and f'href="{URL1}"' in ed, 'aba Edições com as da plataforma')
cs, cc, cr = pm.get('/admin/diario/config').text, pm.get('/admin/diario/config?aba=calendario').text, pm.get('/admin/diario/config?aba=regras').text
checa('Signatários designados' in cs and 'Calendário: feriados' not in cs and 'Lei, decreto e horários' not in cs, 'aba Signatários sozinha')
checa('Calendário: feriados' in cc and 'Signatários designados' not in cc, 'aba Calendário sozinha')
checa('Lei, decreto e horários' in cr and 'Edições de teste no portal' in cr and 'Signatários designados' not in cr, 'aba Lei, horários e teste')
rf = pm.post('/admin/diario/config', data={'csrf': tok(pm, '/admin/diario/config?aba=calendario'), 'acao': 'feriado', 'data': '2026-12-25', 'descricao': 'Natal (teste)', 'tipo': 'feriado'}, follow_redirects=False)
checa(rf.status_code == 303 and rf.headers['location'] == '/admin/diario/config?aba=calendario', f"feriado volta para a aba Calendário ({rf.headers.get('location')})")
ra = pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario?aba=atos'), 'acao': 'novo', 'ementa': ''}, follow_redirects=False)
checa(ra.status_code == 303 and ra.headers['location'].startswith('/admin/diario?'), f"ato volta para o Diário ({ra.headers.get('location')})")

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
print('diário em plataformas externas: tudo ok' if not erros else 'FALHOU')
sys.exit(1 if erros else 0)
