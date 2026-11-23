"""Portal — e-SIC e Ouvidoria (23/11/2026): registro, acompanhamento com código de acesso, complemento, recurso,
avaliação, relatório estatístico (LAI, art. 30, III), relatório da Ouvidoria (Lei 13.460, art. 15), rol de informações
classificadas (LAI, art. 30, I e II) e a API de encaminhamento entre órgãos (mesma instalação ou outra).
Regras em atendimento.py. Nome e e-mail do cidadão nunca aparecem no portal."""
import csv, io, json
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, Response, JSONResponse
from . import config, db, atendimento as A
from .web import templates, ctx_orgao, ler_form, ir

r = APIRouter(prefix='/_p')

def _mods(request):
    from .web import modulos_do_orgao
    return modulos_do_orgao(request.state.orgao)

def _liberados(request):
    return request.session.get('protocolos') or []

def _liberar(request, prot):
    lst = [x for x in _liberados(request) if x != prot][-9:]  # guarda até 10 protocolos na sessão deste navegador
    request.session['protocolos'] = lst + [prot]

def _ctx(request, **kw):
    ctx = ctx_orgao(request)
    b = ctx['orgao']['banco']
    ctx.update(conf_at=A.conf(b), CATEGORIAS=A.CATEGORIAS, SIT_AT=A.SITUACOES, DECISOES=A.DECISOES, DECISOES_RECURSO=A.DECISOES_RECURSO,
               PRAZO=A.PRAZO, PRORROGA=A.PRORROGA, RECURSO_INTERPOR=A.RECURSO_INTERPOR, RECURSO_DECIDIR=A.RECURSO_DECIDIR)
    ctx.update(kw)
    return ctx

# ---------- formulários ----------
def _form(request, tipo):
    ctx = _ctx(request)
    from . import carta as CT
    try:
        sc = CT.publicados(ctx['orgao']['banco']) if tipo == 'manifestacao' and ctx['mods'].get('carta') else []
    except Exception:
        sc = []
    return templates.TemplateResponse(request, 'portal/acesso.html', dict(ctx, legal='ouvidoria' if tipo == 'manifestacao' else 'esic', tipo_fixo=tipo, servicos_carta=sc,
        titulo_pag='Ouvidoria' if tipo == 'manifestacao' else 'Acesso à informação (e-SIC)', protocolo='',
        intro_pag='Reclamações, sugestões, elogios, denúncias e solicitações sobre os serviços públicos.' if tipo == 'manifestacao' else 'Peça qualquer informação pública. Você não precisa explicar o motivo do pedido.',
        servico_sel=request.query_params.get('servico', '')))

@r.get('/ouvidoria')
def ouvidoria(request: Request):
    return _form(request, 'manifestacao')

@r.get('/e-sic')
def esic(request: Request):
    return _form(request, 'pedido')

@r.post('/acesso')
async def registrar(request: Request):
    o = request.state.orgao
    f = await ler_form(request)
    tipo = 'pedido' if f.get('tipo') == 'pedido' else 'manifestacao'
    sid = None
    if tipo == 'manifestacao' and str(f.get('servico_id', '')).isdigit():  # Fase 10: manifestação ligada a um serviço da Carta
        x = db.um(o['banco'], 'SELECT id FROM servicos WHERE id=%s AND publicado_dados IS NOT NULL', (int(f['servico_id']),))
        sid = x['id'] if x else None
    try:
        p, codigo = A.registrar(o, dict(f, tipo=tipo, servico_id=sid, anonimo=f.get('anonimo') == '1', preservar=f.get('preservar') == '1'))
    except A.Erro as e:
        return ir('/e-sic' if tipo == 'pedido' else '/ouvidoria', str(e), request)
    _liberar(request, p['protocolo'])
    request.session['codigo_novo'] = {'p': p['protocolo'], 'c': codigo}
    return ir(f"/acesso?protocolo={p['protocolo']}", f"Recebido. Guarde o protocolo {p['protocolo']} e o código de acesso.", request)

# ---------- acompanhamento ----------
@r.get('/acesso')
def acompanhar(request: Request, protocolo: str = ''):
    if not protocolo:  # destinos próprios desde a Fase 8: /fale-conosco, /ouvidoria e /e-sic
        return RedirectResponse('/fale-conosco', status_code=301)
    o = request.state.orgao
    b = o['banco']
    p = A.por_protocolo(b, protocolo)
    novo = request.session.pop('codigo_novo', None)
    codigo_novo = novo['c'] if novo and p and novo.get('p') == p['protocolo'] else None
    completo = bool(p and (p['protocolo'] in _liberados(request) or not p['codigo_hash']))  # registros antigos (sem código) seguem como antes
    hist = A.historico(b, p['id'], so_publico=True) if p and completo else []
    rec = A.recursos(b, p['id']) if p and completo else []
    pr = A.pode_recorrer(b, p) if p and completo else None
    prazo = A.prazo_info(p, b) if p else None
    return templates.TemplateResponse(request, 'portal/protocolo.html', _ctx(request, p=p, protocolo=protocolo.strip().upper()[:40], completo=completo, hist=hist, recursos=rec,
        pode_recorrer=pr, prazo=prazo, codigo_novo=codigo_novo, legal='esic' if p and p['tipo'] == 'pedido' else 'ouvidoria' if p else 'acesso',
        titulo_pag=f"Protocolo {p['protocolo']}" if p else 'Acompanhar protocolo'),
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

@r.post('/acesso/consultar')
async def consultar(request: Request):
    f = await ler_form(request)
    o = request.state.orgao
    p = A.por_protocolo(o['banco'], f.get('protocolo'))
    if not p or not A.confere_codigo(o['banco'], p, f.get('codigo', '')):
        return ir(f"/acesso?protocolo={(f.get('protocolo') or '').strip().upper()[:40]}", 'Protocolo ou código de acesso não confere.', request)
    _liberar(request, p['protocolo'])
    return ir(f"/acesso?protocolo={p['protocolo']}", '', request)

async def _acao(request, fn, ok_msg):
    f = await ler_form(request)
    o = request.state.orgao
    p = A.por_protocolo(o['banco'], f.get('protocolo'))
    if not p or p['protocolo'] not in _liberados(request):
        return ir(f"/acesso?protocolo={(f.get('protocolo') or '')[:40]}", 'Informe o código de acesso para continuar.', request)
    try:
        fn(o, p, f)
    except A.Erro as e:
        return ir(f"/acesso?protocolo={p['protocolo']}", str(e), request)
    return ir(f"/acesso?protocolo={p['protocolo']}", ok_msg, request)

@r.post('/acesso/recurso')
async def recurso(request: Request):
    return await _acao(request, lambda o, p, f: A.recorrer(o, p, f.get('texto', '')), 'Recurso recebido. Você será avisado por e-mail da decisão.')

@r.post('/acesso/complemento')
async def complemento(request: Request):
    return await _acao(request, lambda o, p, f: A.complementar(o, p, f.get('texto', '')), 'Complemento recebido. O prazo voltou a correr.')

@r.post('/acesso/avaliar')
async def avaliar(request: Request):
    return await _acao(request, lambda o, p, f: A.avaliar(o, p, f.get('nota'), f.get('resolveu')), 'Obrigado pela avaliação!')

# ---------- relatório estatístico do e-SIC (LAI, art. 30, III; PNTP 12.7) ----------
def _ano(b, ano):
    anos = A.anos(b)
    try:
        a = int(ano)
    except (TypeError, ValueError):
        a = anos[0]
    return a, sorted(set(anos) | {a, config.hoje().year}, reverse=True)

def _linhas_estat(e):
    p, rc = e['pedidos'], e['recursos']
    return [('Pedidos recebidos', p['recebidos']), ('Pedidos concluídos', p['concluidos']), ('Acesso concedido', p['concedidos']), ('Acesso parcialmente concedido', p['parciais']),
            ('Acesso negado (indeferidos)', p['negados']), ('Informação inexistente ou de outro órgão', p['nao_possui']), ('Encaminhados ao órgão competente', p['encaminhados']),
            ('Encerrados sem complemento', p['encerrados']), ('Em andamento', p['andamento']), ('Com prazo prorrogado', p['prorrogados']),
            ('Respondidos no prazo', p['no_prazo']), ('Tempo médio de resposta (dias)', p['media_dias'] if p['media_dias'] is not None else '—'),
            ('Solicitantes pessoa física', p['pf']), ('Solicitantes pessoa jurídica', p['pj']), ('Solicitantes sem informação de tipo', p['pn']),
            ('Recursos apresentados', rc['n']), ('Recursos providos (total ou parcial)', rc['providos']), ('Recursos não providos', rc['desprovidos']),
            ('Recursos de 2ª instância', rc['segunda']), ('Recursos aguardando decisão', rc['pendentes'])]

@r.get('/e-sic/estatisticas')
def estatisticas(request: Request, ano: str = ''):
    b = request.state.orgao['banco']
    a, anos = _ano(b, ano)
    e = A.estatisticas(b, a)
    return templates.TemplateResponse(request, 'portal/esic_estatisticas.html', _ctx(request, e=e, linhas=_linhas_estat(e), ano=a, anos=anos, legal='esic_estatisticas',
        titulo_pag='Relatório estatístico do e-SIC'))

@r.get('/e-sic/estatisticas.{fmt}')
def estatisticas_arquivo(request: Request, fmt: str, ano: str = ''):
    o = request.state.orgao
    a, _ = _ano(o['banco'], ano)
    e = A.estatisticas(o['banco'], a)
    linhas = _linhas_estat(e)
    if fmt == 'json':
        return JSONResponse({'orgao': o['nome'], 'ano': a, 'gerado_em': config.agora().isoformat(timespec='minutes'), 'base_legal': 'LAI, art. 30, III',
                             'indicadores': [{'indicador': k, 'valor': float(v) if isinstance(v, Decimal) else v} for k, v in linhas],
                             'por_mes': [dict(m) for m in e['meses']], 'por_canal': [{'canal': c['nome'], 'pedidos': c['n']} for c in e['canais']]},
                            headers={'Access-Control-Allow-Origin': '*'})
    if fmt != 'csv':
        raise HTTPException(404)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['ano', 'indicador', 'valor'])
    for k, v in linhas:
        w.writerow([a, k, str(v).replace('.', ',')])
    for m in e['meses']:
        w.writerow([a, f"Pedidos em {m['mes']:02d}/{a}", m['pedidos']])
        w.writerow([a, f"Manifestações de ouvidoria em {m['mes']:02d}/{a}", m['manifestacoes']])
    return Response('﻿' + buf.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="esic-estatisticas-{a}.csv"'})

# ---------- relatório anual da Ouvidoria (Lei 13.460, arts. 14 e 15) ----------
@r.get('/ouvidoria/relatorio')
def relatorio_ouvidoria(request: Request, ano: str = ''):
    b = request.state.orgao['banco']
    a, anos = _ano(b, ano)
    rel = A.relatorio_ouvidoria(b, a)
    return templates.TemplateResponse(request, 'portal/ouvidoria_relatorio.html', _ctx(request, rel=rel, ano=a, anos=anos, legal='ouvidoria_relatorio',
        titulo_pag='Relatório de gestão da Ouvidoria'))

# ---------- rol de informações classificadas (LAI, art. 30, I e II; PNTP 12.8 e 12.9) ----------
def _classificadas(b):
    from datetime import timedelta
    hoje = config.hoje()
    ativas = db.todos(b, 'SELECT * FROM informacoes_classificadas WHERE desclassificada_em IS NULL AND prazo_ate >= %s ORDER BY classificada_em DESC', (hoje,))
    descl = db.todos(b, """SELECT *, coalesce(desclassificada_em, prazo_ate) saiu FROM informacoes_classificadas
                           WHERE coalesce(desclassificada_em, CASE WHEN prazo_ate < %s THEN prazo_ate END) >= %s ORDER BY 1 DESC""", (hoje, hoje - timedelta(days=365)))
    return ativas, descl

@r.get('/e-sic/informacoes-classificadas')
def classificadas(request: Request):
    ativas, descl = _classificadas(request.state.orgao['banco'])
    return templates.TemplateResponse(request, 'portal/classificadas.html', _ctx(request, ativas=ativas, descl=descl, legal='classificadas',
        titulo_pag='Informações classificadas e desclassificadas'))

@r.get('/e-sic/informacoes-classificadas.csv')
def classificadas_csv(request: Request):
    ativas, descl = _classificadas(request.state.orgao['banco'])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['situacao', 'assunto', 'grau', 'categoria', 'fundamento', 'classificada_em', 'prazo_ate', 'desclassificada_em', 'autoridade'])
    for lst, sit in ((ativas, 'classificada'), (descl, 'desclassificada')):
        for x in lst:
            w.writerow([sit, x['assunto'], x['grau'], x['categoria'], x['fundamento'], x['classificada_em'].isoformat(), x['prazo_ate'].isoformat(),
                        x['desclassificada_em'].isoformat() if x['desclassificada_em'] else '', x['autoridade']])
    return Response('﻿' + buf.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="informacoes-classificadas.csv"'})

# ---------- API entre órgãos: encaminhamento (mesma instalação ou outra) ----------
@r.post('/api/atendimento/encaminhamentos')
async def api_receber(request: Request):
    from . import integracao as I
    origem, destino, corpo = await I.autenticar(request)
    try:
        d = json.loads(corpo)
    except Exception:
        return JSONResponse({'erro': 'corpo inválido'}, status_code=400)
    from .web import modulos_do_orgao
    srv = 'sic' if d.get('tipo') == 'pedido' else 'ouv'
    if not modulos_do_orgao(destino).get(srv):
        return JSONResponse({'erro': 'serviço desligado neste órgão'}, status_code=409)
    try:
        p = A.receber_encaminhamento(destino, origem, d)
    except A.Erro as e:
        return JSONResponse({'erro': str(e)}, status_code=400)
    I.log(origem['slug'], destino['slug'], 'encaminhamento recebido', True, p['protocolo'])
    return {'protocolo': p['protocolo'], 'situacao': p['situacao'], 'prazo': p['prazo'].isoformat() if p['prazo'] else None}

@r.get('/api/atendimento/encaminhamentos/{protocolo}')
async def api_situacao(request: Request, protocolo: str):
    from . import integracao as I
    origem, destino, _ = await I.autenticar(request)
    s = A.situacao_publica(destino, origem, protocolo)
    if not s:
        return JSONResponse({'erro': 'protocolo não encontrado'}, status_code=404)
    return s
