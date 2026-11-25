"""Portal público de cada órgão (Prefeitura ou Câmara)."""
import re, secrets
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from . import config, db, eleicao
from . import avaliacao as AVAL
from .catalogo import BLOCOS, VEDADAS, LARGURA
from .web import templates, ctx_orgao, ler_form, ir

r = APIRouter(prefix='/_p')

def precisa(ctx, modulo):
    if not ctx['mods'].get(modulo):
        raise HTTPException(404, 'Esta seção não está disponível neste portal.')

def conteudos_publicos(banco, secao=None, limite=50):
    sql = "SELECT * FROM conteudos WHERE situacao='publicado' AND (publicar_em IS NULL OR publicar_em <= %s) AND (tirar_em IS NULL OR tirar_em > %s)"
    p = [config.hoje(), config.hoje()]
    if secao:
        sql += ' AND secao=%s'
        p.append(secao)
    sql += ' ORDER BY publicar_em DESC NULLS LAST, id DESC LIMIT %s'
    p.append(limite)
    itens = db.todos(banco, sql, p)
    if eleicao.em_defeso(banco):
        itens = [c for c in itens if c['classe'] not in VEDADAS or c['excecao_eleitoral']]
    return itens

def bienio_atual(bienio: str, ano: int) -> bool:
    try:
        a, b = [int(x) for x in bienio.replace('–', '-').split('-')[:2]]
        return a <= ano <= b
    except ValueError:
        return False

def dados_camara(b, hoje):
    leg = db.um(b, 'SELECT max(numero) n FROM legislaturas')['n']
    ver = db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (leg,))
    por_nome = {v['nome']: v for v in ver}
    mesas, atual, pres = [], None, None
    for g in db.todos(b, 'SELECT bienio, array_agg(cargo ORDER BY id) cargos, array_agg(nome ORDER BY id) nomes FROM mesas WHERE legislatura=%s GROUP BY bienio ORDER BY bienio', (leg,)):
        em = bienio_atual(g['bienio'], hoje.year)
        membros = [{'cargo': c, 'nome': n, 'vid': por_nome.get(n, {}).get('id'), 'foto': por_nome.get(n, {}).get('foto_url')} for c, n in zip(g['cargos'], g['nomes']) if n]
        mesas.append({'bienio': g['bienio'], 'atual': em, 'membros': membros})
        if em:
            atual = g['bienio']
            for m in membros:
                if m['vid']:
                    por_nome[m['nome']]['cargo'] = m['cargo']
                if m['cargo'] == 'Presidente':
                    pres = m['vid']
    # só os biênios que já começaram (o 2º aparece quando entra em vigor); antes da legislatura, o 1º
    ini = lambda g: int(re.match(r'\d{4}', g['bienio']).group()) if re.match(r'\d{4}', g['bienio']) else 0
    mesas = [g for g in mesas if ini(g) <= hoje.year] or mesas[:1]
    return dict(legislatura=leg, vereadores=ver, mesas=mesas, bienio_atual=atual, presidente_id=pres,
                mesa_layout='abaixo' if db.cfg(b, 'mesa_layout') == 'abaixo' else 'lado')

@r.get('/')
def home(request: Request):
    ctx = ctx_orgao(request)
    o = ctx['orgao']; b = o['banco']; hoje = config.hoje()
    blocos = []
    for bl in db.todos(b, "SELECT * FROM blocos WHERE pagina='home' AND visivel ORDER BY ordem"):
        info = BLOCOS.get(bl['chave'])
        if not info:
            continue
        if info[2] and not ctx['mods'].get(info[2]):
            continue
        if bl['chave'] == 'defeso' and not ctx['defeso']:
            continue
        blocos.append(dict(bl, nome=info[0], largura=LARGURA.get(bl['chave'], '')))
    dados = {'noticias': conteudos_publicos(b, 'Notícias', 6), 'servicos': conteudos_publicos(b, 'Serviços', 8),
             'numeros': db.cfg(b, 'numeros')}  # "números do município": preenchido pelos coletores (Fase 4); vazio = bloco oculto
    if o['tipo'] == 'legislativo':
        dados.update(dados_camara(b, hoje))
        dados['sessoes'] = db.todos(b, 'SELECT * FROM sessoes WHERE data < %s ORDER BY data DESC LIMIT 4', (hoje,))
        dados['proxima'] = db.um(b, 'SELECT * FROM sessoes WHERE data >= %s ORDER BY data, id LIMIT 1', (hoje,))
        dados['projetos'] = db.todos(b, "SELECT * FROM proposicoes ORDER BY (tipo = 'Indicação'), ano DESC, numero DESC LIMIT 4")
        dados['emendas'] = db.um(b, "SELECT count(*) n, coalesce(sum(valor),0) total, coalesce(sum(pago_cadastro),0) pago, coalesce(sum(pago_empenho),0) pago_emp, count(*) FILTER (WHERE conferencia='divergente') divergentes FROM emendas")
        dados['financas'] = db.cfg(b, 'financas', {})
    if ctx['mods'].get('bi'):  # bloco "Acompanhe a gestão": até 4 indicadores em destaque, no cartão único com ⓘ
        from . import painel as P
        dados['indicadores'] = [P.cartao(m, o) for m in P.destaques(b)]
        dados['ind_atualizado'] = max((m['ult']['coletado_em'] for m in P.destaques(b)), default=None)
    from . import fase8 as F8, menus as MN
    dados['atalhos'] = MN.atalhos(b, ctx['externos'])
    dados['comunicados'] = F8.comunicados(b, 5)
    from . import carta as CT
    dados['servicos_top'] = CT.mais_acessados(b, 6) if ctx['mods'].get('carta') else []
    dados['noticias8'] = F8.noticias_home(b) if ctx['mods'].get('noticias') else None
    dados['perfis'] = F8.perfis(b, destaque=True)[:3]
    from . import portal_fase9 as P9  # galeria: últimos álbuns; sem o bloco "Galeria de fotos" visível, o Conheça mostra o botão
    dados['albuns'] = P9.albuns_publicos(b, limite=4)
    dados['bloco_fotos'] = any(x['chave'] == 'fotos' for x in blocos)
    eds = F8.editorias(b)
    nome_org = 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura'
    if dados.get('noticias8'):
        n8 = dados['noticias8']
        for c in [n8['destaque']] + n8['secundarias'] + n8['lista']:
            c['ed'] = F8.editoria_de(c, eds, nome_org, ctx['tokens']['cor'])
    # vitrine de notícias (15/11/2026); previsão do tempo pelo IBGE do município
    if dados.get('noticias8'):
        n8 = dados['noticias8']
        dados['vit_not'] = F8.vitrine([F8.item_noticia(c, c['ed']) for c in [n8['destaque']] + n8['secundarias'] + n8['lista']], 3, 5)
    from . import tempo as T
    dados['tempo'] = T.previsao(o.get('ibge'))
    vis = [x['chave'] for x in blocos]
    dados['tempo_hero'] = bool(dados['tempo']) and 'tempo' in vis and 'hero' in vis  # com foto principal, a previsão flutua sobre ela
    dados['sede_junto'] = bool(dados.get('noticias8')) and 'noticias' in vis and 'sede' in vis
    dados['redes_feed'] = (db.cfg(b, 'redes_feed', {}) or {}).get('itens', [])
    from . import municipio
    try:
        dados['mun_numeros'] = municipio.numeros(o, b)
    except Exception:
        dados['mun_numeros'] = []
    dados['quando'] = F8.quando
    if ctx['mods'].get('transm') or ctx['mods'].get('audiencias'):
        dados['gravacoes'] = db.todos(b, "SELECT * FROM transmissoes WHERE NOT ao_vivo AND video<>'' AND (encerrada_em IS NOT NULL OR previsto_para < now()) ORDER BY coalesce(encerrada_em, previsto_para) DESC NULLS LAST LIMIT 3")
        dados['proxima_tv'] = db.um(b, 'SELECT * FROM transmissoes WHERE NOT ao_vivo AND previsto_para > now() ORDER BY previsto_para LIMIT 1')
    if o['tipo'] == 'executivo':
        F8.sincronizar(b)
        dados['pub'] = {'ultima_edicao': db.um(b, "SELECT * FROM diario_edicoes WHERE situacao='publicada' AND (NOT modo_teste OR %s) ORDER BY data DESC, numero DESC LIMIT 1", (diario_teste(b),)) if ctx['mods'].get('diario') else None,
                        'licitacoes': db.um(b, "SELECT count(*) n FROM licitacoes WHERE ano=%s", (hoje.year,))['n'],
                        'modalidades': [r['m'] for r in db.todos(b, "SELECT DISTINCT modalidade m FROM licitacoes WHERE ano=%s AND modalidade<>'' ORDER BY 1", (hoje.year,))],
                        'legislacao': db.um(b, 'SELECT count(*) n FROM legislacao')['n']}
    if ctx['mods'].get('diario'):
        dados['edicoes'] = db.todos(b, "SELECT * FROM diario_edicoes WHERE situacao='publicada' AND (NOT modo_teste OR %s) ORDER BY data DESC, numero DESC, letra DESC LIMIT 4", (diario_teste(b),))
    destaque = [x for x in blocos if x['regiao'] == 'destaque']
    principal = [x for x in blocos if x['regiao'] == 'principal']
    lateral = [x for x in blocos if x['regiao'] == 'lateral']
    # 25/11/2026: a busca fica só no banner principal; o atalho de teclado [3] vai para ela (sem o banner, para /busca)
    ancora = '#q-home' if any(x['chave'] == 'hero' for x in destaque) else None
    return templates.TemplateResponse(request, 'portal/home.html', dict(ctx, destaque=destaque, principal=principal, lateral=lateral, d=dados, ancora_busca=ancora))

@r.get('/noticias')
def noticias(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'noticias')
    b = ctx['orgao']['banco']; o = ctx['orgao']
    from . import fase8 as F8
    sel = request.query_params.get('secretaria', '')
    agora = config.agora()
    def ja_publicada(c):
        t = c.get('publicado_em')
        if not t:
            return True
        return (t.astimezone().replace(tzinfo=None) if agora.tzinfo is None else t) <= agora
    itens = [c for c in conteudos_publicos(b, 'Notícias', 200) if c['tipo'] == 'Notícia' and ja_publicada(c)]
    if ctx['defeso']:
        itens = []  # notícias são publicidade institucional: fora do ar no defeso (como na página inicial)
    eds = F8.editorias(b)
    nome_org = 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura'
    for c in itens:
        c['ed'] = F8.editoria_de(c, eds, nome_org, ctx['tokens']['cor'])
    if sel.isdigit():
        itens = [c for c in itens if c.get('secretaria_id') == int(sel)]
    return templates.TemplateResponse(request, 'portal/noticias.html', dict(ctx, itens=itens, editorias=list(eds.values()), sel=sel, quando=F8.quando, legal='noticias',
                                      lat=dict(F8.lateral(b, ctx['mods'], nome_org, ctx['tokens']['cor'], o.get('ibge')), noticias=[])))

# /servicos (Carta de Serviços) fica em portal_carta.py (Fase 10)

@r.get('/conteudo/{cid}')
def conteudo(request: Request, cid: int):
    ctx = ctx_orgao(request)
    c = db.um(ctx['orgao']['banco'], "SELECT * FROM conteudos WHERE id=%s AND situacao='publicado'", (cid,))
    if not c:
        raise HTTPException(404, 'Conteúdo não encontrado.')
    if eleicao.suspenso(c, ctx['orgao']['banco']):
        return templates.TemplateResponse(request, 'portal/suspenso.html', ctx, status_code=451)
    if c['secao'] == 'Serviços':
        from . import fase8
        fase8.contar_acesso(ctx['orgao']['banco'], c['id'])
    from . import fase8 as F8
    o = ctx['orgao']
    c['ed'] = F8.editoria_de(c, F8.editorias(o['banco']), 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura', ctx['tokens']['cor'])
    noticia = c['tipo'] == 'Notícia'
    pai = ('Notícias', '/noticias') if noticia else {'Serviços': ('Carta de Serviços', '/servicos'), 'Transparência': ('Transparência', '/transparencia'), 'Governo': ('Governo', '/governo')}.get(c['secao'])
    lat = F8.lateral(o['banco'], ctx['mods'], 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura', ctx['tokens']['cor'], o.get('ibge'), excluir_noticia=c['id']) if noticia else None
    return templates.TemplateResponse(request, 'portal/conteudo.html', dict(ctx, c=c, pai=pai, noticia=noticia, quando=F8.quando, legal='noticias' if noticia else None, lat=lat))

# ---------- Câmara ----------
def _norm(s):
    return (s or '').lower().replace('í', 'i').replace('é', 'e').replace('ã', 'a').replace('ç', 'c').replace('á', 'a').replace('ó', 'o').replace('luiz', 'luis')

def proposicoes_de(b, nome):
    n = _norm(nome)
    return [p for p in db.todos(b, 'SELECT * FROM proposicoes ORDER BY ano DESC, numero DESC') if n in _norm(p['autor'])]

@r.get('/vereadores')
def vereadores(request: Request, leg: str = ''):
    ctx = ctx_orgao(request); precisa(ctx, 'ver')
    b = ctx['orgao']['banco']
    if ctx['orgao']['tipo'] != 'legislativo':
        raise HTTPException(404, 'Página da Câmara.')
    legs = db.todos(b, 'SELECT * FROM legislaturas ORDER BY numero DESC')
    notas = db.cfg(b, 'notas_fonte', {}) or {}
    if not legs or leg == 'acervo':   # sem legislatura cadastrada: a página existe e diz isso (o link está no menu)
        return templates.TemplateResponse(request, 'portal/vereadores.html', dict(ctx, legs=legs, leg=None, ver=[], mesas=[], legal='vereadores', notas=notas))
    num = int(leg) if leg.isdigit() else legs[0]['numero']
    lg = db.um(b, 'SELECT * FROM legislaturas WHERE numero=%s', (num,))
    if not lg:
        raise HTTPException(404, 'Legislatura não encontrada.')
    ver = db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (num,))
    atual = num == legs[0]['numero']
    from . import legislativo as L
    props = {v['id']: len(L.proposicoes_do_vereador(b, v)) for v in ver} if atual else {}
    return templates.TemplateResponse(request, 'portal/vereadores.html', dict(ctx, legs=legs, leg=lg, ver=ver, loop_atual=atual, props=props,
        mesas=db.todos(b, 'SELECT * FROM mesas WHERE legislatura=%s ORDER BY bienio, id', (num,)), legal='vereadores', notas=notas))

@r.get('/vereador/{vid}')
def vereador(request: Request, vid: int):
    ctx = ctx_orgao(request); precisa(ctx, 'ver')
    b = ctx['orgao']['banco']
    v = db.um(b, 'SELECT * FROM vereadores WHERE id=%s', (vid,))
    if not v:
        raise HTTPException(404, 'Vereador não encontrado.')
    from . import legislativo as L
    props = L.proposicoes_do_vereador(b, v)
    atual = v['legislatura'] == db.um(b, 'SELECT max(numero) n FROM legislaturas')['n']
    emendas = [e for e in db.todos(b, "SELECT * FROM emendas ORDER BY split_part(numero, '/', 1)::int") if _norm(e['autor']) == _norm(v['nome'])] if atual and ctx['mods'].get('emend') else []
    mandatos = db.todos(b, 'SELECT v.*, l.anos FROM vereadores v JOIN legislaturas l ON l.numero=v.legislatura WHERE v.nome=%s ORDER BY v.legislatura DESC', (v['nome'],))
    cargos = db.todos(b, 'SELECT * FROM mesas WHERE nome=%s ORDER BY legislatura DESC, bienio', (v['nome'],))
    pres, votos, resumo_votos = L.estatisticas_vereador(b, vid)
    grupos = [('Indicações', 'Pedidos ao Poder Executivo', [p for p in props if p['tipo'] == 'Indicação']),
              ('Requerimentos e moções', 'Pedidos de informação, homenagens e manifestações', [p for p in props if p['tipo'] in ('Requerimento', 'Moção')]),
              ('Projetos, emendas e vetos', 'Proposições normativas com autoria ou coautoria', [p for p in props if p['tipo'] not in ('Indicação', 'Requerimento', 'Moção')])]
    return templates.TemplateResponse(request, 'portal/vereador.html', dict(ctx, notas=db.cfg(b, 'notas_fonte', {}) or {}, v=v, props=props, emendas=emendas, mandatos=mandatos, cargos=cargos, pres=pres, grupos=grupos, votos=votos, resumo_votos=resumo_votos, votos_nome=L.VOTOS,
        participacao=L.participacao_vereador(b, vid), tipos_ev=L.EVENTOS,
        leg=db.um(b, 'SELECT * FROM legislaturas WHERE numero=%s', (v['legislatura'],)), legal='vereadores'))

@r.get('/emendas')
def emendas(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'emend')
    b = ctx['orgao']['banco']
    return templates.TemplateResponse(request, 'portal/emendas.html', dict(ctx, emendas=db.todos(b, 'SELECT * FROM emendas ORDER BY split_part(numero, %s, 1)::int', ('/',)),
        tot=db.um(b, 'SELECT count(*) n, coalesce(sum(valor),0) total, coalesce(sum(pago_cadastro),0) pago, coalesce(sum(pago_empenho),0) pago_emp FROM emendas'), legal='emendas'))

def caminho_emenda(e):
    """Passos da emenda na Prefeitura (cadastro → empenho → anulação → liquidação → pagamento) e totais."""
    d = e['detalhe'] or {}
    passos = [{'n': 1, 't': 'Emenda cadastrada', 'd': d.get('vinculo') or e['objeto'], 'data': '', 'v': e['valor'], 'tipo': ''}]
    emp = anul = liq = pag = 0
    for em in d.get('empenhos', []):
        emp += em.get('valor') or 0
        passos.append({'t': f"Empenho {em['num']} ({em.get('tipo', '')})", 'd': d.get('credor', ''), 'data': em.get('data', ''), 'v': em.get('valor'), 'tipo': ''})
        for dt, v in em.get('anul', []):
            anul += v; passos.append({'t': 'Anulação de empenho', 'd': f"Empenho {em['num']}", 'data': dt, 'v': -v, 'tipo': 'anul'})
        for dt, v in em.get('liq', []):
            liq += v; passos.append({'t': 'Liquidação', 'd': 'Serviço ou material entregue e conferido', 'data': dt, 'v': v, 'tipo': ''})
        for dt, v in em.get('pag', []):
            pag += v; passos.append({'t': 'Pagamento', 'd': f"Empenho {em['num']}", 'data': dt, 'v': v, 'tipo': 'pago'})
    for i, x in enumerate(passos, 1):
        x['n'] = i
    tot = {'indicado': e['valor'], 'empenhado': emp - anul, 'liquidado': liq, 'pago': pag, 'pago_cadastro': e['pago_cadastro']}
    tot['pct'] = float(pag) / float(e['valor']) * 100 if e['valor'] else 0
    return passos, tot

@r.get('/emendas/{ano}/{num}')
def emenda(request: Request, ano: int, num: int):
    ctx = ctx_orgao(request); precisa(ctx, 'emend')
    e = db.um(ctx['orgao']['banco'], 'SELECT * FROM emendas WHERE numero=%s', (f'{num}/{ano}',))
    if not e:
        raise HTTPException(404, 'Emenda não encontrada.')
    passos, tot = caminho_emenda(e)
    return templates.TemplateResponse(request, 'portal/emenda.html', dict(ctx, e=e, passos=passos, tot=tot, legal='emendas'))

# ---------- Diário Oficial ----------
def diario_teste(b):
    from .diario import mostrar_teste
    return mostrar_teste(b)

@r.get('/diario')
def diario(request: Request):
    from . import sistemas as SIS  # 25/11/2026: Diário em sistema de terceiros (na Câmara, pode ser o da Prefeitura)
    ext = SIS.pagina(request, 'diario')
    if ext:
        return ext
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    b = ctx['orgao']['banco']
    eds = db.todos(b, "SELECT * FROM diario_edicoes WHERE situacao IN ('publicada','invalidada') AND (NOT modo_teste OR %s) ORDER BY data DESC, numero DESC, letra DESC LIMIT 100", (diario_teste(b),))
    return templates.TemplateResponse(request, 'portal/diario.html', dict(ctx, edicoes=eds, invalidadas=[e for e in eds if e['situacao'] == 'invalidada'], legal='diario'))

@r.get('/diario/{eid}.pdf')
def diario_pdf(request: Request, eid: int):
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    e = db.um(ctx['orgao']['banco'], "SELECT * FROM diario_edicoes WHERE id=%s AND situacao IN ('publicada','invalidada') AND (NOT modo_teste OR %s)", (eid, diario_teste(ctx['orgao']['banco'])))
    if not e or not e['pdf_arquivo'] or not Path(e['pdf_arquivo']).exists():
        raise HTTPException(404, 'Edição não encontrada.')
    # abre no navegador (inline) e sempre confere com o servidor (no-cache + ETag): edição de teste refeita ou PDF trocado aparece na hora.
    # O link leva a versão (?v=início do sha256), então uma cópia antiga em cache nunca é reaproveitada.
    return FileResponse(e['pdf_arquivo'], media_type='application/pdf', content_disposition_type='inline', headers={'Cache-Control': 'no-cache'},
                        filename=f"diario-oficial-{e['numero']}{e['letra']}{'-TESTE' if e['modo_teste'] else ''}.pdf")

@r.get('/diario/verificar')
def diario_verificar(request: Request, codigo: str = '', c: str = ''):
    codigo = codigo or c  # QR Code da capa: /diario/verificar?c=CÓDIGO (já mostra o resultado)
    from . import assinatura as A
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    e = db.um(ctx['orgao']['banco'], "SELECT * FROM diario_edicoes WHERE codigo=%s AND situacao IN ('publicada','invalidada') AND (NOT modo_teste OR %s)", (codigo.strip().upper()[:20], diario_teste(ctx['orgao']['banco']))) if codigo else None
    sigs = []
    if e and e['pdf_arquivo'] and Path(e['pdf_arquivo']).is_file():
        try:
            sigs = A.validar(Path(e['pdf_arquivo']).read_bytes())
        except Exception:
            sigs = [{'campo': f"Assinatura_{x['etapa']}", 'signatario': x.get('signatario', ''), 'integra': True, 'valida': True, 'confiavel': not e['modo_teste'], 'carimbo': x.get('carimbo'), 'carimbo_valido': False} for x in e['assinaturas'] if x.get('feita')]
    return templates.TemplateResponse(request, 'portal/diario_verificar.html', dict(ctx, e=e, codigo=codigo, sigs=sigs, etapas=A.ETAPAS, legal='diario'))

# ---------- Páginas institucionais e mídia ----------
MIDIA_OK = re.compile(r'^([0-9a-f]{32}|favicon-[0-9a-f]{16}(-\d{2,3})?)\.(png|jpg|webp|svg|pdf)$')
TIPOS = {'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp', 'svg': 'image/svg+xml', 'pdf': 'application/pdf'}

@r.get('/midia/{arquivo}')
def midia(request: Request, arquivo: str):
    """Fotos enviadas pelo painel (brasão, destaque, Conheça, vereadores), guardadas em DADOS_DIR/<órgão>/midia."""
    if not MIDIA_OK.match(arquivo):
        raise HTTPException(404)
    f = Path(config.DADOS_DIR) / request.state.orgao['slug'] / 'midia' / arquivo
    if not f.is_file():
        raise HTTPException(404)
    h = {'Cache-Control': 'public, max-age=86400', 'X-Content-Type-Options': 'nosniff'}
    if arquivo.endswith('.svg'):  # SVG (favicon) já filtrado no envio; aqui nunca executa script
        h['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'"
    return FileResponse(f, media_type=TIPOS[arquivo.rsplit('.', 1)[1]], headers=h)

@r.get('/tempo')
def tempo(request: Request):
    """Previsão completa (15/11/2026): a página inicial mostra só hoje e amanhã."""
    from . import tempo as T
    ctx = ctx_orgao(request); o = ctx['orgao']
    return templates.TemplateResponse(request, 'portal/tempo.html', dict(ctx, t=T.previsao(o.get('ibge')), cidade=ctx['ident'].get('nome_curto') or (o.get('municipio') or '').split(' (')[0] or 'o município'))

@r.get('/busca')
def busca(request: Request, q: str = ''):
    """Busca geral do portal (25/11/2026): tudo o que o órgão publica (app/busca.py)."""
    from . import busca as BU
    ctx = ctx_orgao(request)
    q = (q or '').strip()[:120]
    grupos, total = BU.buscar(ctx, q) if q else ([], 0)
    return templates.TemplateResponse(request, 'portal/busca.html', dict(ctx, q=q, grupos=grupos, total=total, curta=bool(q) and len(BU.norm(q).replace(' ', '')) < BU.MIN_CARACTERES))

@r.get('/privacidade')
def privacidade(request: Request):
    return templates.TemplateResponse(request, 'portal/pagina.html', dict(ctx_orgao(request), pagina='privacidade', titulo='Política de privacidade', legal='acesso', prazo_aval=AVAL.prazo(request.state.orgao['banco'])))

@r.get('/acessibilidade')
def acessibilidade(request: Request):
    return templates.TemplateResponse(request, 'portal/pagina.html', dict(ctx_orgao(request), pagina='acessibilidade', titulo='Acessibilidade', legal='acessibilidade'))

@r.get('/mapa-do-site')
def mapa(request: Request):
    return templates.TemplateResponse(request, 'portal/pagina.html', dict(ctx_orgao(request), pagina='mapa', titulo='Mapa do site'))

# ---------- Acesso à informação: e-SIC e Ouvidoria em app/portal_atendimento.py (23/11/2026) ----------


# Portal oculto enquanto é configurado: o filtro (web.PortalOculto) manda para cá quem não entrou no painel deste órgão
@r.api_route('/_em_preparacao', methods=['GET', 'POST', 'HEAD'])
def em_preparacao(request: Request):
    o = request.state.orgao
    ident = db.cfg(o['banco'], 'identidade', {}) or {}
    return templates.TemplateResponse(request, 'portal/em_preparacao.html', dict(request=request, orgao=o, ident=ident, cor=ident.get('cor') or o['cor']),
                                      status_code=503, headers={'Retry-After': '86400', 'Cache-Control': 'no-store'})
