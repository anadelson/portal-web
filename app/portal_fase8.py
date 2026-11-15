"""Páginas públicas da Fase 8."""
import csv, io, re
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, Response, JSONResponse
from . import config, db, fase8 as F
from .web import templates, ctx_orgao

r = APIRouter(prefix='/_p')
LEG_BASE = 'LAI (Lei 12.527/2011), art. 8º; Lei Orgânica do Município; Lei Complementar 95/1998 (elaboração e alteração de leis).'

# ---------- comunicados ----------
@r.get('/comunicados')
def comunicados(request: Request, tipo: str = '', ano: str = ''):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    anos = [x['a'] for x in db.todos(b, "SELECT DISTINCT extract(year FROM coalesce(publicado_em, criado_em))::int a FROM comunicados WHERE situacao='publicado' ORDER BY 1 DESC")]
    itens = F.comunicados(b, 200, tipo if tipo in F.tipos_comunicado(b) else '', int(ano) if ano.isdigit() else None, so_validos=False)
    from . import anexos as AX
    o = ctx['orgao']; nome_org = 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura'
    return templates.TemplateResponse(request, 'portal/comunicados.html', dict(ctx, itens=itens, tipos=F.tipos_comunicado(b), tipo=tipo, ano=ano, anos=anos, quando=F.quando, legal='comunicados',
                                      n_anexos=AX.contagem(b, [x['id'] for x in itens]), capas=AX.capas(b, [x['id'] for x in itens]),
                                      lat=dict(F.lateral(b, ctx['mods'], nome_org, ctx['tokens']['cor'], o.get('ibge')), comunicados=[])))

@r.get('/comunicados/{cid}')
def comunicado(request: Request, cid: int):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    c = next((x for x in F.comunicados(b, 1000, so_validos=False) if x['id'] == cid), None)
    if not c:
        raise HTTPException(404, 'Comunicado não encontrado.')
    from . import anexos as AX
    o = ctx['orgao']; nome_org = 'Câmara' if o['tipo'] == 'legislativo' else 'Prefeitura'
    return templates.TemplateResponse(request, 'portal/comunicado.html', dict(ctx, c=c, quando=F.quando, legal='comunicados', anexos=AX.listar(b, c['id']),
                                      lat=F.lateral(b, ctx['mods'], nome_org, ctx['tokens']['cor'], o.get('ibge'), excluir_comunicado=c['id'])))

@r.get('/anexo/{arquivo}')
def anexo(request: Request, arquivo: str):
    """Arquivo anexo de comunicado. Só sai se o comunicado estiver publicado e visível (fora do defeso, se vedado),
    ou para quem está no painel do próprio órgão (pré-visualização)."""
    from fastapi.responses import FileResponse
    from . import anexos as AX
    if not AX.ARQ_OK.match(arquivo):
        raise HTTPException(404)
    o = request.state.orgao; b = o['banco']
    a = db.um(b, 'SELECT * FROM comunicado_anexos WHERE arquivo=%s', (arquivo,))
    f = AX.pasta(o) / arquivo
    if not a or not f.is_file():
        raise HTTPException(404)
    u = request.session.get('u') or {}
    visivel = any(x['id'] == a['comunicado_id'] for x in F.comunicados(b, 1000, so_validos=False))
    if not visivel and u.get('orgao') != o['slug']:
        raise HTTPException(404)
    mime, _, inline = AX.TIPOS[a['ext']]
    nome = re.sub(r'[^\w.-]+', '-', a['titulo']).strip('-')[:80] or 'anexo'
    disp = 'inline' if inline else 'attachment'
    return FileResponse(f, media_type=mime, filename=f'{nome}.{a["ext"]}', content_disposition_type=disp,
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=300'})

@r.get('/anexo/{arquivo}/capa')
def anexo_capa(request: Request, arquivo: str):
    """Miniatura do anexo (imagem reduzida ou 1ª página do PDF), com a mesma regra de visibilidade do arquivo."""
    from fastapi.responses import FileResponse
    from . import anexos as AX
    if not AX.ARQ_OK.match(arquivo):
        raise HTTPException(404)
    o = request.state.orgao; b = o['banco']
    a = db.um(b, 'SELECT * FROM comunicado_anexos WHERE arquivo=%s', (arquivo,))
    if not a:
        raise HTTPException(404)
    u = request.session.get('u') or {}
    visivel = any(x['id'] == a['comunicado_id'] for x in F.comunicados(b, 1000, so_validos=False))
    if not visivel and u.get('orgao') != o['slug']:
        raise HTTPException(404)
    f = AX.capa(o, a)
    if not f:
        raise HTTPException(404)
    return FileResponse(f, media_type='image/webp', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': ('public, max-age=3600' if visivel else 'private, max-age=60')})

# ---------- Conheça ----------
@r.get('/conheca')
def conheca(request: Request, categoria: str = '', q: str = ''):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    cat = categoria if categoria in F.CATEGORIAS else ''
    return templates.TemplateResponse(request, 'portal/conheca.html', dict(ctx, perfis=F.perfis(b, cat, q.strip()[:80]), categorias=F.CATEGORIAS, categoria=cat, q=q, legal='conheca'))

@r.get('/conheca/{slug}')
def perfil(request: Request, slug: str):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    p = next((x for x in F.perfis(b) if x['slug'] == slug), None)
    if not p:
        raise HTTPException(404, 'Perfil não encontrado.')
    outros = [x for x in F.perfis(b) if x['id'] != p['id']][:3]
    return templates.TemplateResponse(request, 'portal/perfil.html', dict(ctx, p=p, fotos=F.fotos(b, p['id']), outros=outros,
        videos=db.todos(b, 'SELECT * FROM perfil_videos WHERE perfil_id=%s ORDER BY ordem, id', (p['id'],)), legal='conheca'))

# ---------- Legislação ----------
def _leg_prefeitura(o):
    """Na Câmara, a legislação municipal vem da API pública da Prefeitura do mesmo município (nunca do banco)."""
    from . import orgaos
    pm = orgaos.executivo_do(o['ibge'])
    if not pm:
        return [], None
    import httpx
    try:
        with httpx.Client(base_url=config.INTERNO_BASE, timeout=20) as c:
            d = c.get('/legislacao.json', headers={'Host': pm['dominio'], 'X-Forwarded-Proto': 'https'}).json()
        return d.get('registros', []), pm
    except Exception:
        return None, pm

@r.get('/legislacao')
def legislacao(request: Request, tipo: str = '', situacao: str = '', ano: str = '', q: str = ''):
    ctx = ctx_orgao(request); o = ctx['orgao']
    if o['tipo'] == 'legislativo':
        regs, pm = _leg_prefeitura(o)
        itens = [x for x in (regs or []) if (not tipo or x['tipo'] == tipo) and (not situacao or x['situacao'] == situacao) and (not ano or str(x['ano']) == ano)
                 and (not q or q.lower() in (x['ementa'] + ' ' + x['numero']).lower())]
        return templates.TemplateResponse(request, 'portal/legislacao.html', dict(ctx, itens=itens, externo=pm, falhou=regs is None, tipos=F.TIPOS_LEGISLACAO,
            f=dict(tipo=tipo, situacao=situacao, ano=ano, q=q), anos=sorted({x['ano'] for x in (regs or []) if x.get('ano')}, reverse=True), legal_txt=LEG_BASE, acervo=None, rotulo=lambda x: f"{x['tipo']} nº {x['numero']}/{x['ano']}"))
    b = o['banco']
    F.sincronizar(b)
    itens = F.lista_legislacao(b, tipo if tipo in F.TIPOS_LEGISLACAO else '', situacao if situacao in ('vigente', 'alterada', 'revogada') else '', ano, q.strip()[:80])
    anos = [x['ano'] for x in db.todos(b, 'SELECT DISTINCT ano FROM legislacao WHERE ano IS NOT NULL ORDER BY ano DESC')]
    return templates.TemplateResponse(request, 'portal/legislacao.html', dict(ctx, itens=itens, externo=None, falhou=False, tipos=F.TIPOS_LEGISLACAO, f=dict(tipo=tipo, situacao=situacao, ano=ano, q=q),
        anos=anos, legal_txt=LEG_BASE, acervo=(db.cfg(b, 'legislacao_acervo') or {}).get('url'), rotulo=F.rotulo))

def _registros(b):
    F.sincronizar(b)
    return [{'id': x['id'], 'tipo': x['tipo'], 'numero': x['numero'], 'ano': x['ano'], 'data': x['data'].isoformat() if x['data'] else None, 'ementa': x['ementa'],
             'situacao': x['situacao'], 'origem': x['origem'], 'edicao': x['edicao'], 'pagina': x['pagina'], 'pdf': x['pdf_url']} for x in F.lista_legislacao(b)]

@r.get('/legislacao.json')
def legislacao_json(request: Request):
    o = request.state.orgao
    if o['tipo'] != 'executivo':
        raise HTTPException(404)
    return JSONResponse({'orgao': o['nome'], 'base_legal': LEG_BASE, 'registros': _registros(o['banco'])}, headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=300'})

@r.get('/legislacao.csv')
def legislacao_csv(request: Request):
    o = request.state.orgao
    if o['tipo'] != 'executivo':
        raise HTTPException(404)
    regs = _registros(o['banco'])
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=['tipo', 'numero', 'ano', 'data', 'ementa', 'situacao', 'origem', 'edicao', 'pagina', 'pdf'], extrasaction='ignore')
    w.writeheader(); [w.writerow(x) for x in regs]
    return Response('﻿' + buf.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{o["slug"]}-legislacao.csv"'})

@r.get('/legislacao/{lid}')
def ato(request: Request, lid: int):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    if ctx['orgao']['tipo'] != 'executivo':
        raise HTTPException(404)
    x = db.um(b, 'SELECT * FROM legislacao WHERE id=%s', (lid,))
    if not x:
        raise HTTPException(404, 'Ato não encontrado.')
    x['situacao'] = F.situacao(b, lid)
    return templates.TemplateResponse(request, 'portal/legislacao_ato.html', dict(ctx, x=x, relacoes=F.relacoes_do(b, lid), rotulo=F.rotulo, legal_txt=LEG_BASE))

# ---------- atendimento: destinos próprios (cada um em uma única barra) ----------
@r.get('/fale-conosco')
def fale_conosco(request: Request):
    return templates.TemplateResponse(request, 'portal/fale_conosco.html', dict(ctx_orgao(request), legal='acesso'))

def _acesso(request, tipo):
    from .portal import acesso
    ctx = ctx_orgao(request)
    from . import carta as CT
    try:
        sc = CT.publicados(ctx['orgao']['banco']) if tipo == 'manifestacao' and ctx['mods'].get('carta') else []
    except Exception:
        sc = []
    return templates.TemplateResponse(request, 'portal/acesso.html', dict(ctx, consulta=None, protocolo='', legal='acesso', tipo_fixo=tipo, servicos_carta=sc, titulo_pag='Ouvidoria' if tipo == 'manifestacao' else 'Acesso à informação (e-SIC)',
        intro_pag='Reclamações, sugestões, elogios, denúncias e solicitações sobre os serviços públicos.' if tipo == 'manifestacao' else 'Peça qualquer informação pública. Você não precisa explicar o motivo do pedido.', servico_sel=request.query_params.get('servico', '')))

@r.get('/ouvidoria')
def ouvidoria(request: Request):
    return _acesso(request, 'manifestacao')

@r.get('/e-sic')
def esic(request: Request):
    return _acesso(request, 'pedido')

# ---------- governo e links úteis (rodapé) ----------
@r.get('/governo')
def governo(request: Request):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    eds = F.editorias(b)
    secs = []
    try:
        rows = db.todos(b, "SELECT s.*, (SELECT count(*) FROM servicos v WHERE v.secretaria_id=s.id AND v.publicado_dados IS NOT NULL AND v.situacao<>'arquivado') servicos FROM secretarias s WHERE ativa ORDER BY nome")
    except Exception:
        rows = []
    for x in rows:
        secs.append(dict(x, ed=eds.get(x['id']) or {'cor': ctx['tokens']['cor'], 'icone': 'predio'}))
    return templates.TemplateResponse(request, 'portal/governo.html', dict(ctx, secretarias=secs, legal='acesso'))

@r.get('/links-uteis')
def links_uteis(request: Request):
    ctx = ctx_orgao(request)
    return templates.TemplateResponse(request, 'portal/links_uteis.html', dict(ctx, links=F.links_uteis(ctx['orgao']['banco'])))
