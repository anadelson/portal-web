"""Páginas públicas do painel de indicadores (/painel), downloads e API pública (/painel/api/...).
Tudo depende do módulo "bi": sem ele, as rotas respondem 404 e o bloco da página inicial volta ao conteúdo da Fase 4.
A Câmara, se precisar de algum número da Prefeitura, lê por /painel/api/... (nunca pelo banco)."""
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from . import db, painel as P
from .web import templates, ctx_orgao

r = APIRouter(prefix='/_p')
ABAS = [('tudo', 'Tudo')] + P.TEMAS

def _ctx(request):
    ctx = ctx_orgao(request)
    if not ctx['mods'].get('bi'):
        raise HTTPException(404, 'O painel de indicadores não está disponível neste portal.')
    return ctx

def _indicador(o, chave):
    ind = db.um(o['banco'], 'SELECT * FROM indicadores WHERE chave=%s AND visivel', (chave,))
    if not ind or not db.um(o['banco'], 'SELECT 1 FROM indicador_valores WHERE indicador_id=%s LIMIT 1', (ind['id'],)):
        raise HTTPException(404, 'Indicador não encontrado.')
    return ind

def _com_dados(o):
    return [i for i in P.catalogo(o['banco']) if db.um(o['banco'], 'SELECT 1 FROM indicador_valores WHERE indicador_id=%s LIMIT 1', (i['id'],))]

@r.get('/painel')
def painel(request: Request, tema: str = '', aba: str = ''):
    ctx = _ctx(request); o = ctx['orgao']
    if aba and not tema:  # endereço antigo (?aba=) → ?tema=
        from fastapi.responses import RedirectResponse
        return RedirectResponse('/painel' + (f'?tema={aba}' if aba in dict(ABAS) and aba != 'tudo' else ''), status_code=301)
    tema = tema if tema in dict(ABAS) else 'tudo'
    from . import painel_blocos as PB
    d = PB.montar(o, tema)
    return templates.TemplateResponse(request, 'portal/painel.html', dict(ctx, abas=ABAS, aba=tema, d=d, legal_txt=P.BASE_LEGAL))

def _resposta(o, inds, nome, formato, titulo):
    linhas = P.linhas_export(o, inds)
    arq = f"{o['slug']}-{nome}"
    cab = {'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*'}
    if formato == 'csv':
        return Response(P.csv_bytes(linhas), media_type='text/csv; charset=utf-8', headers={**cab, 'Content-Disposition': f'attachment; filename="{arq}.csv"'})
    if formato == 'json':
        return JSONResponse(P.json_obj(o, linhas, titulo), headers=cab)
    if formato == 'ods':
        return Response(P.ods_bytes(linhas, 'Indicadores'), media_type='application/vnd.oasis.opendocument.spreadsheet', headers={**cab, 'Content-Disposition': f'attachment; filename="{arq}.ods"'})
    raise HTTPException(404)

@r.get('/painel/baixar/painel.{formato}')
def baixar_tudo(request: Request, formato: str):
    ctx = _ctx(request); o = ctx['orgao']
    return _resposta(o, _com_dados(o), 'painel-de-indicadores', formato, 'Painel de indicadores (todos)')

@r.get('/painel/baixar/{chave}.{formato}')
def baixar(request: Request, chave: str, formato: str):
    ctx = _ctx(request); o = ctx['orgao']
    ind = _indicador(o, chave)
    return _resposta(o, [ind], f'indicador-{chave}', formato, ind['nome'])

# ---------- API pública (também para a Câmara e outros sistemas) ----------
def _resumo(o, m):
    return {'chave': m['chave'], 'tema': m['tema_nome'], 'nome': m['nome'], 'unidade': m['unidade'], 'fonte': m['fonte'], 'link_fonte': P.link_fonte(m, o, m['ult']),
            'periodicidade': m['periodicidade'], 'periodo': m['ult']['periodo'], 'data_referencia': m['ult']['data_ref'].isoformat(),
            'valor': None if P.suprimido(m, m['ult']) or m['ult']['valor'] is None else float(m['ult']['valor']), 'valor_exibido': m['valor_txt'],
            'parcial': m['ult']['parcial'], 'nota': m['ult']['nota'], 'variacao': m['variacao'], 'meta': None if m['meta'] is None else float(m['meta']),
            'situacao_meta': m['meta_txt'], 'atualizado_em': m['ult']['coletado_em'].astimezone().isoformat(timespec='minutes'), 'aviso': m['aviso'],
            'base_legal': m['base_legal'], 'serie': f"/painel/api/{m['chave']}.json"}

@r.get('/painel/api/indicadores.json')
def api_lista(request: Request):
    ctx = _ctx(request); o = ctx['orgao']
    corpo = {'orgao': o['nome'], 'base_legal': P.BASE_LEGAL, 'lgpd': 'Só dados agregados; contagens de pessoas abaixo de 5 vêm sem o número.',
             'indicadores': [_resumo(o, m) for m in P.painel(o['banco'])]}
    return JSONResponse(corpo, headers={'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*'})

@r.get('/painel/api/financas.json')
def api_financas(request: Request):
    """Resumo das finanças da Prefeitura (só totais), lido pela Câmara do mesmo município (23/11/2026). Só no Executivo."""
    ctx = _ctx(request); o = ctx['orgao']
    from . import config, painel_blocos as PB
    r = PB.resumo_local(o, config.hoje()) if o['tipo'] == 'executivo' else None
    if not r:
        raise HTTPException(404, 'Sem finanças do ano corrente neste portal.')
    return JSONResponse(dict(r, base_legal=P.BASE_LEGAL), headers={'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*'})

@r.get('/painel/api/{chave}.json')
def api_indicador(request: Request, chave: str):
    ctx = _ctx(request); o = ctx['orgao']
    ind = _indicador(o, chave)
    m = P.montar(o['banco'], ind)
    corpo = dict(_resumo(o, m), descricao=m['descricao'], registros=P.linhas_export(o, [ind]))
    return JSONResponse(corpo, headers={'Cache-Control': 'public, max-age=300', 'Access-Control-Allow-Origin': '*'})

@r.get('/painel/{chave}')
def indicador(request: Request, chave: str):
    ctx = _ctx(request); o = ctx['orgao']
    ind = _indicador(o, chave)
    m = P.montar(o['banco'], ind)
    serie = P.com_lacunas(ind, m['serie'])
    return templates.TemplateResponse(request, 'portal/painel_indicador.html', dict(ctx, i=m, serie=list(reversed(serie)), grafico=P.grafico(ind, serie, 'g-' + chave),
        link=P.link_fonte(ind, o, m['ult']), exibir=P.exibir, suprimido=P.suprimido, legal_txt=P.BASE_LEGAL, detalhe=m['ult']['detalhe'],
        extras=any(isinstance(x['detalhe'], dict) and ('rendimento' in x['detalhe'] or 'projecao' in x['detalhe']) for x in serie), num_br=P._br))

def blocos_dados_abertos(o):
    """Linhas do painel para a página /dados-abertos."""
    return [{'chave': i['chave'], 'nome': i['nome'], 'tema': P.TEMA_NOME[i['tema']], 'fonte': i['fonte'],
             'n': db.um(o['banco'], 'SELECT count(*) n FROM indicador_valores WHERE indicador_id=%s', (i['id'],))['n'],
             'atualizado': db.um(o['banco'], 'SELECT max(coletado_em) t FROM indicador_valores WHERE indicador_id=%s', (i['id'],))['t']} for i in _com_dados(o)]
