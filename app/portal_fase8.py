"""Páginas públicas da Fase 8."""
import csv, io
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
    return templates.TemplateResponse(request, 'portal/comunicados.html', dict(ctx, itens=itens, tipos=F.tipos_comunicado(b), tipo=tipo, ano=ano, anos=anos, quando=F.quando, legal='comunicados'))

@r.get('/comunicados/{cid}')
def comunicado(request: Request, cid: int):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    c = next((x for x in F.comunicados(b, 1000, so_validos=False) if x['id'] == cid), None)
    if not c:
        raise HTTPException(404, 'Comunicado não encontrado.')
    return templates.TemplateResponse(request, 'portal/comunicado.html', dict(ctx, c=c, quando=F.quando, legal='comunicados'))

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
    pm = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE tipo='executivo' AND ativo AND ibge=%s ORDER BY id LIMIT 1", (o['ibge'],))
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
    return templates.TemplateResponse(request, 'portal/acesso.html', dict(ctx, consulta=None, protocolo='', legal='acesso', tipo_fixo=tipo, servicos_carta=sc, servico_sel=request.query_params.get('servico', '')))

@r.get('/ouvidoria')
def ouvidoria(request: Request):
    return _acesso(request, 'manifestacao')

@r.get('/e-sic')
def esic(request: Request):
    return _acesso(request, 'pedido')

# ---------- governo e links úteis (rodapé) ----------
@r.get('/governo')
def governo(request: Request):
    from .portal import conteudos_publicos
    ctx = ctx_orgao(request)
    return templates.TemplateResponse(request, 'portal/lista.html', dict(ctx, titulo='Governo', itens=conteudos_publicos(ctx['orgao']['banco'], 'Governo', 100), legal='acesso',
        vazio='A estrutura do governo (secretarias, responsáveis e competências) ainda não foi publicada.'))

@r.get('/links-uteis')
def links_uteis(request: Request):
    ctx = ctx_orgao(request)
    return templates.TemplateResponse(request, 'portal/links_uteis.html', dict(ctx, links=F.links_uteis(ctx['orgao']['banco'])))
