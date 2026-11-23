"""Painel → Administração → Órgãos parceiros (23/11/2026): os outros órgãos do município, na mesma instalação ou em outra,
os serviços de cada um, se a integração está ativa, o teste de conversa e as últimas mensagens trocadas."""
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from . import db, integracao as IG, licenca
from .admin import T
from .web import ler_form, ir, exige, auditar

r = APIRouter(prefix='/_a')


def _servicos(p):
    if p.get('parceiro'):
        return p.get('modulos') or []
    return (licenca.vigente(p) or {}).get('modulos') or []


@r.get('/parceiros')
def parceiros(request: Request):
    u = exige(request, 'config')
    o = request.state.orgao
    ps = [dict(p, servicos=_servicos(p), ida=IG.par(o, p), volta=IG.par(p, o) if p.get('mesma_instalacao') else None) for p in IG.parceiros(o)]
    slugs = [p['slug'] for p in ps] or ['-']
    log = db.todos(db.LOCAL, 'SELECT * FROM remessas_log WHERE (origem=%s AND destino = ANY(%s)) OR (destino=%s AND origem = ANY(%s)) ORDER BY id DESC LIMIT 30',
                   (o['slug'], slugs, o['slug'], slugs))
    return T('parceiros', request, u, parceiros=ps, log=log, diretorio=IG.tem_diretorio())


@r.post('/parceiros')
async def parceiros_testar(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    o = request.state.orgao
    p = next((x for x in IG.parceiros(o) if str(x['id']) == f.get('id', '')), None)
    if not p:
        return ir('/admin/parceiros', 'Órgão parceiro não encontrado.', request)
    try:
        res = await run_in_threadpool(IG.chamar, o, p, 'GET', '/api/integracao/ping', None, 'teste de conversa')
        msg = f"Conversa ok com {res.get('orgao', p['nome'])} ({'mesma instalação' if p.get('mesma_instalacao') else 'outra instalação'}; versão {res.get('versao') or '?'})."
    except ValueError as e:
        msg = f'Falhou: {e}'
    auditar(request, f"Órgãos parceiros: teste de conversa com {p['slug']}")
    return ir('/admin/parceiros', msg, request)
