"""Portal público de cada órgão (Prefeitura ou Câmara)."""
import secrets
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from . import config, db, eleicao
from .catalogo import BLOCOS, VEDADAS
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

@r.get('/')
def home(request: Request):
    ctx = ctx_orgao(request)
    o = ctx['orgao']; b = o['banco']
    blocos = []
    for bl in db.todos(b, "SELECT * FROM blocos WHERE pagina='home' AND visivel ORDER BY ordem"):
        info = BLOCOS.get(bl['chave'])
        if not info:
            continue
        if info[2] and not ctx['mods'].get(info[2]):
            continue
        if bl['chave'] == 'defeso' and not ctx['defeso']:
            continue
        blocos.append(dict(bl, nome=info[0]))
    dados = {'noticias': conteudos_publicos(b, 'Notícias', 6), 'servicos': conteudos_publicos(b, 'Serviços', 8)}
    if o['tipo'] == 'legislativo':
        leg = db.um(b, 'SELECT max(numero) n FROM legislaturas')['n']
        dados['vereadores'] = db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (leg,))
        dados['mesa'] = db.todos(b, 'SELECT * FROM mesas WHERE legislatura=%s ORDER BY id', (leg,))
        dados['sessoes'] = db.todos(b, 'SELECT * FROM sessoes ORDER BY data DESC LIMIT 5')
        dados['emendas'] = db.um(b, "SELECT count(*) n, coalesce(sum(valor),0) total, coalesce(sum(pago_cadastro),0) pago FROM emendas")
        dados['financas'] = db.cfg(b, 'financas', {})
        dados['legislatura'] = leg
    if ctx['mods'].get('diario'):
        dados['edicoes'] = db.todos(b, "SELECT * FROM diario_edicoes WHERE situacao='publicada' ORDER BY data DESC, numero DESC, letra DESC LIMIT 5")
    principal = [x for x in blocos if x['regiao'] in ('destaque', 'principal')]
    lateral = [x for x in blocos if x['regiao'] == 'lateral']
    return templates.TemplateResponse(request, 'portal/home.html', dict(ctx, principal=principal, lateral=lateral, d=dados))

@r.get('/noticias')
def noticias(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'noticias')
    return templates.TemplateResponse(request, 'portal/lista.html', dict(ctx, titulo='Notícias e avisos', itens=conteudos_publicos(ctx['orgao']['banco'], None), legal='noticias'))

@r.get('/servicos')
def servicos(request: Request, q: str = ''):
    ctx = ctx_orgao(request)
    itens = conteudos_publicos(ctx['orgao']['banco'], None if q else 'Serviços', 200)
    if q:
        t = q.lower()
        itens = [c for c in itens if t in (c['titulo'] + ' ' + c['resumo'] + ' ' + c['texto']).lower()]
    return templates.TemplateResponse(request, 'portal/lista.html', dict(ctx, titulo=f'Resultados para “{q}”' if q else 'Serviços ao cidadão', itens=itens, legal=None))

@r.get('/conteudo/{cid}')
def conteudo(request: Request, cid: int):
    ctx = ctx_orgao(request)
    c = db.um(ctx['orgao']['banco'], "SELECT * FROM conteudos WHERE id=%s AND situacao='publicado'", (cid,))
    if not c:
        raise HTTPException(404, 'Conteúdo não encontrado.')
    if eleicao.suspenso(c, ctx['orgao']['banco']):
        return templates.TemplateResponse(request, 'portal/suspenso.html', ctx, status_code=451)
    return templates.TemplateResponse(request, 'portal/conteudo.html', dict(ctx, c=c))

@r.get('/transparencia')
def transparencia(request: Request):
    ctx = ctx_orgao(request)
    return templates.TemplateResponse(request, 'portal/transparencia.html', dict(ctx, fin=db.cfg(ctx['orgao']['banco'], 'financas', {}), legal='transparencia'))

# ---------- Câmara ----------
@r.get('/vereadores')
def vereadores(request: Request, leg: int | None = None):
    ctx = ctx_orgao(request); precisa(ctx, 'ver')
    b = ctx['orgao']['banco']
    legs = db.todos(b, 'SELECT * FROM legislaturas ORDER BY numero DESC')
    if not legs:
        raise HTTPException(404, 'Composição ainda não cadastrada.')
    leg = leg or legs[0]['numero']
    return templates.TemplateResponse(request, 'portal/vereadores.html', dict(ctx, legs=legs, leg=db.um(b, 'SELECT * FROM legislaturas WHERE numero=%s', (leg,)),
        ver=db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (leg,)),
        mesas=db.todos(b, 'SELECT * FROM mesas WHERE legislatura=%s ORDER BY bienio, id', (leg,)), legal='vereadores'))

@r.get('/vereador/{vid}')
def vereador(request: Request, vid: int):
    ctx = ctx_orgao(request); precisa(ctx, 'ver')
    b = ctx['orgao']['banco']
    v = db.um(b, 'SELECT * FROM vereadores WHERE id=%s', (vid,))
    if not v:
        raise HTTPException(404, 'Vereador não encontrado.')
    primeiro = v['nome'].split()[0]
    norm = lambda s: s.lower().replace('í', 'i').replace('é', 'e').replace('ã', 'a').replace('ç', 'c').replace('luiz', 'luis')
    props = [p for p in db.todos(b, 'SELECT * FROM proposicoes ORDER BY ano DESC, numero DESC') if norm(v['nome']) in norm(p['autor'])]
    emendas = [e for e in db.todos(b, 'SELECT * FROM emendas ORDER BY numero') if norm(e['autor']) == norm(v['nome'])] if v['legislatura'] == db.um(b, 'SELECT max(numero) n FROM legislaturas')['n'] else []
    mandatos = db.todos(b, 'SELECT v.*, l.anos FROM vereadores v JOIN legislaturas l ON l.numero=v.legislatura WHERE v.nome=%s ORDER BY v.legislatura DESC', (v['nome'],))
    cargos = db.todos(b, 'SELECT * FROM mesas WHERE nome=%s ORDER BY legislatura DESC, bienio', (v['nome'],))
    pres = db.um(b, "SELECT count(*) FILTER (WHERE p.situacao='presente') presente, count(*) FILTER (WHERE p.situacao='ausente') ausente, count(*) FILTER (WHERE p.situacao='justificada') justificada FROM presencas p JOIN sessoes s ON s.id=p.sessao_id WHERE s.presenca_publicada AND p.vereador_id=%s", (vid,))
    return templates.TemplateResponse(request, 'portal/vereador.html', dict(ctx, v=v, props=props, emendas=emendas, mandatos=mandatos, cargos=cargos, pres=pres, legal='vereadores'))

@r.get('/sessoes')
def sessoes(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'sess')
    return templates.TemplateResponse(request, 'portal/sessoes.html', dict(ctx, sessoes=db.todos(ctx['orgao']['banco'], 'SELECT * FROM sessoes ORDER BY data DESC'), legal='sessoes'))

@r.get('/proposicoes')
def proposicoes(request: Request, q: str = ''):
    ctx = ctx_orgao(request); precisa(ctx, 'prop')
    props = db.todos(ctx['orgao']['banco'], "SELECT * FROM proposicoes WHERE %s = '' OR (tipo || ' ' || ementa || ' ' || autor) ILIKE %s ORDER BY ano DESC, numero DESC", (q, f'%{q}%'))
    return templates.TemplateResponse(request, 'portal/proposicoes.html', dict(ctx, props=props, q=q, legal='proposicoes'))

@r.get('/emendas')
def emendas(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'emend')
    b = ctx['orgao']['banco']
    return templates.TemplateResponse(request, 'portal/emendas.html', dict(ctx, emendas=db.todos(b, 'SELECT * FROM emendas ORDER BY split_part(numero, %s, 1)::int', ('/',)),
        tot=db.um(b, 'SELECT count(*) n, sum(valor) total, sum(pago_cadastro) pago FROM emendas'), legal='emendas'))

@r.get('/emendas/{ano}/{num}')
def emenda(request: Request, ano: int, num: int):
    ctx = ctx_orgao(request); precisa(ctx, 'emend')
    e = db.um(ctx['orgao']['banco'], 'SELECT * FROM emendas WHERE numero=%s', (f'{num}/{ano}',))
    if not e:
        raise HTTPException(404, 'Emenda não encontrada.')
    return templates.TemplateResponse(request, 'portal/emenda.html', dict(ctx, e=e, legal='emendas'))

# ---------- Diário Oficial ----------
@r.get('/diario')
def diario(request: Request):
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    eds = db.todos(ctx['orgao']['banco'], "SELECT * FROM diario_edicoes WHERE situacao='publicada' ORDER BY data DESC, numero DESC, letra DESC LIMIT 100")
    return templates.TemplateResponse(request, 'portal/diario.html', dict(ctx, edicoes=eds, legal='diario'))

@r.get('/diario/{eid}.pdf')
def diario_pdf(request: Request, eid: int):
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    e = db.um(ctx['orgao']['banco'], "SELECT * FROM diario_edicoes WHERE id=%s AND situacao='publicada'", (eid,))
    if not e or not e['pdf_arquivo'] or not Path(e['pdf_arquivo']).exists():
        raise HTTPException(404, 'Edição não encontrada.')
    return FileResponse(e['pdf_arquivo'], media_type='application/pdf', filename=f"diario-oficial-{e['numero']}{e['letra']}.pdf")

@r.get('/diario/verificar')
def diario_verificar(request: Request, codigo: str = ''):
    ctx = ctx_orgao(request); precisa(ctx, 'diario')
    e = db.um(ctx['orgao']['banco'], "SELECT * FROM diario_edicoes WHERE codigo=%s AND situacao='publicada'", (codigo.strip().upper(),)) if codigo else None
    return templates.TemplateResponse(request, 'portal/diario_verificar.html', dict(ctx, e=e, codigo=codigo, legal='diario'))

# ---------- Acesso à informação ----------
@r.get('/acesso')
def acesso(request: Request, protocolo: str = ''):
    ctx = ctx_orgao(request)
    p = db.um(ctx['orgao']['banco'], 'SELECT protocolo, tipo, categoria, assunto, recebido, situacao, resposta, respondido FROM esic WHERE protocolo=%s', (protocolo.strip().upper(),)) if protocolo else None
    return templates.TemplateResponse(request, 'portal/acesso.html', dict(ctx, consulta=p, protocolo=protocolo, legal='acesso'))

@r.post('/acesso')
async def acesso_enviar(request: Request):
    ctx = ctx_orgao(request)
    f = await ler_form(request)
    tipo = 'pedido' if f.get('tipo') == 'pedido' else 'manifestacao'
    if not (f.get('assunto') and f.get('texto') and f.get('nome') and '@' in f.get('email', '')):
        return ir('/acesso', 'Preencha assunto, texto, nome e e-mail.', request)
    prefixo = 'SIC' if tipo == 'pedido' else 'OUV'
    prot = f"{prefixo}-{config.hoje().year}-{secrets.token_hex(3).upper()}"
    db.exe(ctx['orgao']['banco'], 'INSERT INTO esic (protocolo, tipo, categoria, assunto, texto, nome, email) VALUES (%s,%s,%s,%s,%s,%s,%s)',
           (prot, tipo, f.get('categoria', ''), f['assunto'][:200], f['texto'][:5000], f['nome'][:120], f['email'][:120]))
    return ir(f'/acesso?protocolo={prot}', f'Recebido. Guarde o protocolo {prot}.', request)
