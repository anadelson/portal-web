"""Portal: e-SIC e Ouvidoria (23/11/2026). Formulários, protocolo + código de acesso, complemento, recurso, avaliação,
estatísticas do e-SIC, informações classificadas, relatório da Ouvidoria e a API assinada que recebe pedidos encaminhados
por órgão parceiro. Regras em app/atendimento.py."""
import csv, io, json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, Response
from . import db, atendimento as A
from .web import templates, ctx_orgao, ler_form, ir

r = APIRouter(prefix='/_p')


def _pagina(request, tipo, **kw):
    ctx = ctx_orgao(request)
    b = ctx['orgao']['banco']
    sc = []
    if tipo == 'manifestacao' and ctx['mods'].get('carta'):
        from . import carta as CT
        try:
            sc = CT.publicados(b)
        except Exception:
            sc = []
    return templates.TemplateResponse(request, 'portal/acesso.html', dict(ctx, legal='acesso', tipo_fixo=tipo, servicos_carta=sc, at=A.conf(b), A=A,
        titulo_pag='Ouvidoria' if tipo == 'manifestacao' else 'Acesso à informação (e-SIC)', protocolo='',
        intro_pag='Reclamações, sugestões, elogios, denúncias e solicitações sobre os serviços públicos.' if tipo == 'manifestacao' else 'Peça qualquer informação pública. Você não precisa explicar o motivo do pedido.',
        servico_sel=request.query_params.get('servico', ''), **kw))


@r.get('/ouvidoria')
def ouvidoria(request: Request):
    from . import sistemas as SIS
    return SIS.pagina(request, 'ouvidoria') or _pagina(request, 'manifestacao')


@r.get('/e-sic')
def esic(request: Request):
    from . import sistemas as SIS
    return SIS.pagina(request, 'esic') or _pagina(request, 'pedido')


@r.post('/acesso')
async def enviar(request: Request):
    o = request.state.orgao
    f = await ler_form(request)
    tipo = 'pedido' if f.get('tipo') == 'pedido' else 'manifestacao'
    sid = None
    if tipo == 'manifestacao' and str(f.get('servico_id', '')).isdigit():  # Fase 10: manifestação ligada a um serviço da Carta
        x = db.um(o['banco'], 'SELECT id FROM servicos WHERE id=%s AND publicado_dados IS NOT NULL', (int(f['servico_id']),))
        sid = x['id'] if x else None
    p, codigo, erro = A.registrar(o, dict(f, tipo=tipo, servico_id=sid, anonimo=f.get('anonimo') == '1'))
    if erro:
        return ir('/e-sic' if tipo == 'pedido' else '/ouvidoria', erro, request)
    return templates.TemplateResponse(request, 'portal/acesso_protocolo.html', dict(ctx_orgao(request), legal='acesso', modo='registrado', p=p, codigo=codigo, A=A,
                                      titulo_pag='Recebido'))


@r.get('/acesso')
def consulta(request: Request, protocolo: str = ''):
    if not protocolo:  # destinos próprios desde a Fase 8: /fale-conosco, /ouvidoria e /e-sic
        return RedirectResponse('/fale-conosco', status_code=301)
    p = A.por_protocolo(request.state.orgao['banco'], protocolo)
    return templates.TemplateResponse(request, 'portal/acesso_protocolo.html', dict(ctx_orgao(request), legal='acesso', modo='situacao', p=p, protocolo=protocolo[:40], A=A,
                                      titulo_pag='Acompanhar protocolo'))


def _completo(request, p, msg='', erro=False, codigo=''):
    b = request.state.orgao['banco']
    inst, lim = A.pode_recorrer(b, p)
    return templates.TemplateResponse(request, 'portal/acesso_protocolo.html', dict(ctx_orgao(request), legal='acesso', modo='completo', p=p, codigo=codigo, A=A,
        historico=A.historico(b, p['id']), recursos=A.recursos(b, p['id']), recurso_inst=inst, recurso_lim=lim, at=A.conf(b), aviso=msg, aviso_erro=erro,
        titulo_pag=f"Protocolo {p['protocolo']}"))


@r.post('/acesso/consulta')
async def consulta_completa(request: Request):
    f = await ler_form(request)
    p = A.por_protocolo(request.state.orgao['banco'], f.get('protocolo', ''))
    if not A.confere(p, f.get('codigo', '')):
        return ir(f"/acesso?protocolo={(f.get('protocolo') or '')[:40]}", 'Protocolo ou código de acesso não confere.', request)
    return _completo(request, p, codigo=f['codigo'])


@r.post('/acesso/acao')
async def acao(request: Request):
    o = request.state.orgao
    f = await ler_form(request)
    p = A.por_protocolo(o['banco'], f.get('protocolo', ''))
    if not A.confere(p, f.get('codigo', '')):
        return ir(f"/acesso?protocolo={(f.get('protocolo') or '')[:40]}", 'Protocolo ou código de acesso não confere.', request)
    a = f.get('acao')
    if a == 'complementar':
        erro = A.complementar(o, p, f.get('texto', ''))
        ok = 'Complemento enviado. O prazo de resposta voltou a correr.'
    elif a == 'recorrer':
        erro = A.recorrer(o, p, f.get('texto', ''))
        ok = 'Recurso registrado.'
    elif a == 'avaliar':
        erro = A.avaliar(o, p, f.get('nota'), f.get('resolveu'), f.get('comentario', ''))
        ok = 'Obrigado pela avaliação.'
    else:
        erro = 'Ação desconhecida.'
    return _completo(request, A.por_protocolo(o['banco'], p['protocolo']), erro or ok, bool(erro), codigo=f['codigo'])


# ---------- páginas públicas de números (sem dado pessoal) ----------
def _csv(linhas, cab, nome):
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(cab)
    for l in linhas:
        w.writerow(l)
    return Response('﻿' + buf.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{nome}.csv"'})


def _ano(request, b):
    anos = A.anos(b)
    a = request.query_params.get('ano', '')
    return (int(a) if a.isdigit() and 2000 <= int(a) <= 2100 else anos[0]), anos


@r.get('/e-sic/estatisticas')
def estatisticas(request: Request, formato: str = ''):
    o = request.state.orgao; b = o['banco']
    ano, anos = _ano(request, b)
    e = A.estatisticas(b, ano)
    if formato == 'json':
        return JSONResponse({'orgao': o['nome'], 'ano': ano, 'base_legal': 'LAI, art. 30, III', 'indicadores': {k: e[k] for k, _ in A.ROTULOS_EST},
                             'rotulos': dict(A.ROTULOS_EST)}, headers={'Access-Control-Allow-Origin': '*'})
    if formato == 'csv':
        return _csv([[ano, k, n, e[k]] for k, n in A.ROTULOS_EST], ['ano', 'indicador', 'descricao', 'valor'], f"{o['slug']}-esic-estatisticas-{ano}")
    return templates.TemplateResponse(request, 'portal/atendimento_numeros.html', dict(ctx_orgao(request), legal='esic_estatisticas', pagina='estatisticas', ano=ano, anos=anos, e=e, A=A,
                                      titulo_pag='Estatísticas do e-SIC'))


@r.get('/e-sic/informacoes-classificadas')
def classificadas(request: Request, formato: str = ''):
    o = request.state.orgao; b = o['banco']
    ativas, descl = A.classificadas(b)
    if formato == 'csv':
        cab = ['situacao', 'referencia', 'grau', 'assunto', 'categoria', 'fundamento', 'classificada_em', 'prazo_ate', 'autoridade', 'desclassificada_em']
        linhas = [['classificada' if x['desclassificada_em'] is None else 'desclassificada'] + [str(x[c] or '') for c in cab[1:]] for x in ativas + descl]
        return _csv(linhas, cab, f"{o['slug']}-informacoes-classificadas")
    return templates.TemplateResponse(request, 'portal/atendimento_numeros.html', dict(ctx_orgao(request), legal='esic_classificadas', pagina='classificadas', ativas=ativas, descl=descl,
                                      at=A.conf(b), A=A, titulo_pag='Informações classificadas'))


@r.get('/ouvidoria/relatorio')
def relatorio(request: Request, formato: str = ''):
    o = request.state.orgao; b = o['banco']
    ano, anos = _ano(request, b)
    rel = A.relatorio_ouvidoria(b, ano)
    if formato == 'json':
        return JSONResponse(json.loads(json.dumps(dict(rel, orgao=o['nome']), default=str)), headers={'Access-Control-Allow-Origin': '*'})
    if formato == 'csv':
        linhas = [[ano, 'total', k, v] for k, v in rel['totais'].items()] + [[ano, 'categoria', c['categoria'], c['n']] for c in rel['categorias']] + [[ano, 'servico', s['nome'], s['n']] for s in rel['servicos']]
        return _csv(linhas, ['ano', 'grupo', 'item', 'valor'], f"{o['slug']}-ouvidoria-relatorio-{ano}")
    return templates.TemplateResponse(request, 'portal/atendimento_numeros.html', dict(ctx_orgao(request), legal='ouvidoria_relatorio', pagina='ouvidoria', ano=ano, anos=anos, rel=rel, A=A,
                                      titulo_pag='Relatório da Ouvidoria'))


# ---------- API assinada: pedido encaminhado por órgão parceiro (sem identidade) ----------
@r.post('/api/integracao/esic')
async def receber_encaminhado(request: Request):
    from . import integracao as IG
    origem, destino, corpo = await IG.autenticar(request)
    try:
        d = json.loads(corpo or b'{}')
    except ValueError:
        raise HTTPException(400, 'JSON inválido')
    if not (d.get('assunto') and d.get('texto') and d.get('protocolo')):
        return JSONResponse({'erro': 'faltam assunto, texto ou protocolo de origem'}, status_code=400)
    ja = db.um(destino['banco'], 'SELECT * FROM esic WHERE origem_orgao=%s AND origem_protocolo=%s', (origem['slug'], d['protocolo'][:40]))
    if ja:
        return JSONResponse({'erro': f"já recebido (protocolo {ja['protocolo']})"}, status_code=409)
    p, codigo, erro = A.registrar(destino, {'tipo': d.get('tipo'), 'categoria': d.get('categoria', ''), 'assunto': str(d['assunto']), 'texto': str(d['texto'])},
                                  canal='encaminhado', quem=origem['nome'], origem={'slug': origem['slug'], 'nome': origem['nome'], 'protocolo': str(d['protocolo'])})
    if erro:
        return JSONResponse({'erro': erro}, status_code=400)
    IG.log(origem['slug'], destino['slug'], f"recebido encaminhamento {d['protocolo']} → {p['protocolo']}", True)
    return {'ok': True, 'protocolo': p['protocolo'], 'codigo': codigo, 'situacao': p['situacao'], 'prazo': p['prazo'].isoformat()}


@r.get('/api/integracao/esic/{protocolo}')
async def situacao_encaminhado(request: Request, protocolo: str):
    from . import integracao as IG
    origem, destino, _ = await IG.autenticar(request)
    p = db.um(destino['banco'], 'SELECT protocolo, situacao, prazo, respondido FROM esic WHERE protocolo=%s AND origem_orgao=%s', (protocolo.upper()[:40], origem['slug']))
    if not p:
        return JSONResponse({'erro': 'protocolo não encontrado (ou não veio deste órgão)'}, status_code=404)
    return {'protocolo': p['protocolo'], 'situacao': p['situacao'], 'prazo': p['prazo'].isoformat() if p['prazo'] else None,
            'respondido': p['respondido'].isoformat() if p['respondido'] else None}
