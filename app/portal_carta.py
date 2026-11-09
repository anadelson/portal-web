"""Portal — Carta de Serviços (Fase 10): busca com sinônimos, filtros, ficha, avaliação (nota 1–5 + conseguiu?) e exportações."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from . import config, db, carta as CT
from .catalogo import BASE_LEGAL
from .web import templates, ctx_orgao, ler_form, ir

r = APIRouter(prefix='/_p')

def _modulo(ctx):
    if not ctx['mods'].get('carta'):
        raise HTTPException(404, 'A Carta de Serviços não está disponível neste portal.')

@r.get('/servicos')
def servicos(request: Request, q: str = '', categoria: str = '', publico: str = '', secretaria: str = '', letra: str = ''):
    ctx = ctx_orgao(request); _modulo(ctx); b = ctx['orgao']['banco']
    todos = CT.publicados(b)
    filtrando = any((q, categoria, publico, secretaria, letra))
    itens = CT.publicados(b, q.strip()[:80], categoria, publico if publico in CT.PUBLICOS else '', secretaria, letra[:1]) if filtrando else todos
    cats = {}
    for x in todos:
        cats[x['categoria']] = cats.get(x['categoria'], 0) + 1
    secs = sorted({(x.get('secretaria_id'), x['secretaria']) for x in todos if x.get('secretaria')}, key=lambda t: t[1])
    letras = sorted({CT.sem_acento(x['nome'])[:1].upper() for x in todos})
    return templates.TemplateResponse(request, 'portal/servicos.html', dict(ctx, itens=itens, todos=todos, filtrando=filtrando, f=dict(q=q, categoria=categoria, publico=publico, secretaria=secretaria, letra=letra),
        categorias=sorted(cats.items()), secretarias=secs, letras=letras, publicos=CT.PUBLICOS, formas=CT.FORMAS, top=CT.mais_acessados(b, 6) if not filtrando else [], legal='carta'))

@r.get('/servicos/{slug_}')
def servico(request: Request, slug_: str):
    ctx = ctx_orgao(request); _modulo(ctx); b = ctx['orgao']['banco']
    x = CT.no_ar(b, slug_)
    if not x:
        raise HTTPException(404, 'Serviço não encontrado na Carta.')
    CT.contar_acesso(b, x['id'])
    from . import avaliacao as AV
    ja = AV.avaliada_em(request, b, f'/servicos/{slug_}')
    secoes = [(sec, k, x.get(k)) for k, (rot, obr, sec) in CT.CAMPOS.items() if sec and x.get(k) and k != 'descricao']
    return templates.TemplateResponse(request, 'portal/servico.html', dict(ctx, x=x, secoes=secoes, publicos=CT.PUBLICOS, formas=CT.FORMAS, ja_avaliou=ja,
        msg_aval=request.session.pop('msg_aval_serv', ''), legal='carta'))

@r.post('/servicos/{slug_}/avaliar')
async def avaliar(request: Request, slug_: str):
    """Nota 1–5 + conseguiu? + comentário. Mesmo controle da Fase 9: cookie próprio por página e limite por hash de IP."""
    from . import avaliacao as AV
    from . import legislativo as L
    ctx = ctx_orgao(request); _modulo(ctx); b = ctx['orgao']['banco']; f = await ler_form(request)
    x = CT.no_ar(b, slug_)
    if not x:
        raise HTTPException(404)
    pagina = f'/servicos/{slug_}'
    js = 'application/json' in request.headers.get('accept', '')
    def resp(msg, ok, gravar=False, cod=200):
        rr = JSONResponse({'ok': ok, 'msg': msg}, status_code=cod) if js else ir(pagina + '#avaliar-servico', '', request)
        if not js:
            request.session['msg_aval_serv'] = msg
        if gravar:
            AV.gravar_cookie(rr, request, b, pagina)
        return rr
    nota = f.get('nota', '')
    if not nota.isdigit() or not 1 <= int(nota) <= 5 or f.get('site'):
        return resp('Escolha uma nota de 1 a 5.', False, cod=400)
    if AV.avaliada_em(request, b, pagina):
        return resp('Você já avaliou este serviço. Obrigado!', False)
    h = AV.ip_hash(request)
    db.exe(b, "UPDATE servico_avaliacoes SET ip_hash='' WHERE ip_hash<>'' AND criado_em < now() - interval '2 days'")
    n = db.um(b, "SELECT (SELECT count(*) FROM servico_avaliacoes WHERE ip_hash=%s AND criado_em > now() - interval '1 hour') + (SELECT count(*) FROM avaliacoes WHERE ip_hash=%s AND criado_em > now() - interval '1 hour') n", (h, h))['n']
    if n >= AV.LIMITE_HORA:
        return resp('Muitas avaliações a partir desta conexão na última hora. Tente de novo mais tarde.', False, cod=429)
    coment = (f.get('comentario') or '')[:600]
    if L.problemas_texto(coment) and 'dado pessoal' in ' '.join(L.problemas_texto(coment)):
        coment = '[comentário removido: continha dado pessoal]'
    cons = {'sim': True, 'nao': False}.get(f.get('conseguiu'))
    db.exe(b, 'INSERT INTO servico_avaliacoes (servico_id, nota, conseguiu, comentario, ip_hash) VALUES (%s,%s,%s,%s,%s)', (x['id'], int(nota), cons, coment, h))
    return resp('Obrigado! Sua avaliação deste serviço foi registrada e ajuda a melhorar o atendimento.', True, gravar=True)

def _orgao_nome(ctx):
    return (ctx['ident'].get('nome') or ctx['orgao']['nome'])

@r.get('/carta-de-servicos.json')
def exp_json(request: Request):
    ctx = ctx_orgao(request); _modulo(ctx)
    return JSONResponse({'orgao': _orgao_nome(ctx), 'gerado_em': config.hoje().isoformat(), 'base_legal': BASE_LEGAL['carta'], 'servicos': CT.registros(ctx['orgao']['banco'])},
                        headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=300'})

@r.get('/carta-de-servicos.csv')
def exp_csv(request: Request):
    ctx = ctx_orgao(request); _modulo(ctx)
    return Response(CT.csv_texto(ctx['orgao']['banco']), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{ctx["orgao"]["slug"]}-carta-de-servicos-{config.hoje().isoformat()}.csv"'})

@r.get('/carta-de-servicos.pdf')
def exp_pdf(request: Request):
    ctx = ctx_orgao(request); _modulo(ctx)
    return Response(CT.pdf(ctx['orgao']['banco'], _orgao_nome(ctx), BASE_LEGAL['carta']), media_type='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{ctx["orgao"]["slug"]}-carta-de-servicos-{config.hoje().isoformat()}.pdf"'})
