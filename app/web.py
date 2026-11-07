"""Peças comuns: resolução do órgão pelo domínio, templates, sessão e proteção de formulários."""
import time
from datetime import date, datetime
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from . import config, db, eleicao
from .catalogo import MOD, serve, CLASSES, SITUACOES, PERFIS, BASE_LEGAL, PODE
from .security import token, mascara_ip

templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

def br(d):
    if not d:
        return ''
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        return d.strftime('%d/%m/%Y %H:%M')
    return d.strftime('%d/%m/%Y')

def moeda(v):
    if v is None:
        return '—'
    s = f'{float(v):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')

templates.env.filters['br'] = br
templates.env.filters['moeda'] = moeda
templates.env.globals.update(CLASSES=CLASSES, SITUACOES=SITUACOES, PERFIS=PERFIS, BASE_LEGAL=BASE_LEGAL)

_cache = {'t': 0, 'orgaos': {}}

def orgao_por_dominio(host: str):
    host = (host or '').split(':')[0].lower()
    if time.time() - _cache['t'] > 30:
        _cache['orgaos'] = {o['dominio']: o for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE ativo')}
        _cache['t'] = time.time()
    return _cache['orgaos'].get(host)

def limpar_cache():
    _cache['t'] = 0

class RoteadorPorDominio:
    """Envia cada requisição para a área certa conforme o domínio:
    gestao → console (/_g); domínio de órgão → portal (/_p) ou painel (/admin → /_a)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        host = dict(scope['headers']).get(b'host', b'').decode().split(':')[0].lower()
        path = scope['path']
        if path.startswith('/static/') or path == '/saude':
            return await self.app(scope, receive, send)
        scope.setdefault('state', {})
        if host == config.DOMINIO_GESTAO.lower():
            novo = '/_g' + path
        else:
            o = orgao_por_dominio(host)
            if not o:
                novo = '/_desconhecido'
            else:
                scope['state']['orgao'] = o
                if path == '/admin' or path.startswith('/admin/'):
                    novo = '/_a' + (path[6:] or '/')
                else:
                    novo = '/_p' + path
        scope['path'] = novo
        scope['raw_path'] = novo.encode()
        return await self.app(scope, receive, send)

def situacao_contrato(c, hoje=None):
    hoje = hoje or config.hoje()
    if c['suspenso']:
        return ('Suspensa', 'susp')
    if hoje < c['inicio']:
        return ('Em implantação', 'impl')
    if hoje > c['fim']:
        dias = (hoje - c['fim']).days
        return ('Vencida · carência', 'carencia') if dias <= c['carencia_dias'] else ('Encerrada', 'fim')
    resto = (c['fim'] - hoje).days
    return (f'Ativa · vence em {resto} dias', 'alerta') if resto <= 90 else ('Ativa', 'ativa')

def modulos_do_orgao(o) -> dict:
    """Módulos efetivamente disponíveis: obrigatórios + plano + opcionais contratados, e ligados pelo órgão."""
    contratados = {r['chave'] for r in db.todos(db.PLATAFORMA, 'SELECT chave FROM orgao_modulos WHERE orgao_id=%s AND contratado', (o['id'],))}
    ligados = db.cfg(o['banco'], 'modulos_ligados', {}) or {}
    c = db.um(db.PLATAFORMA, 'SELECT * FROM contratos WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
    fase = situacao_contrato(c)[1] if c else 'impl'
    res = {}
    for k, m in MOD.items():
        if not serve(k, o['tipo']):
            continue
        if m[3] == 'obr':
            res[k] = True
        elif fase in ('carencia', 'fim', 'susp'):
            res[k] = False  # fora da vigência: só o obrigatório
        elif m[3] == 'plano':
            res[k] = ligados.get(k, True)
        else:
            res[k] = k in contratados and ligados.get(k, True)
    return res

def ctx_orgao(request: Request, **extra):
    o = request.state.orgao
    ident = db.cfg(o['banco'], 'identidade', {}) or {}
    mods = modulos_do_orgao(o)
    d = dict(request=request, orgao=o, ident=ident, mods=mods, cor=ident.get('cor', o['cor']),
             defeso=mods.get('eleicao') and eleicao.em_defeso(o['banco']), eleicao=eleicao.conf(o['banco']), hoje=config.hoje())
    d.update(extra)
    return d

# ---- sessão e formulários ----
def csrf(request: Request) -> str:
    t = request.session.get('csrf')
    if not t:
        t = token()
        request.session['csrf'] = t
    return t

templates.env.globals['csrf_token'] = csrf

async def ler_form(request: Request) -> dict:
    f = await request.form()
    if f.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in f.items()}

def ir(url: str, msg: str = '', request: Request | None = None):
    if msg and request is not None:
        request.session['msg'] = msg
    return RedirectResponse(url, status_code=303)

def pega_msg(request: Request):
    return request.session.pop('msg', '')

templates.env.globals['pega_msg'] = pega_msg

def usuario(request: Request):
    u = request.session.get('u')
    o = getattr(request.state, 'orgao', None)
    if not u or not o or u.get('orgao') != o['slug']:
        return None
    return u

def exige(request: Request, permissao: str | None = None):
    u = usuario(request)
    if not u:
        raise HTTPException(status_code=307, headers={'Location': '/admin/login'})
    if u.get('trocar') and request.url.path not in ('/_a/senha',):
        raise HTTPException(status_code=307, headers={'Location': '/admin/senha'})
    if permissao and u['perfil'] not in PODE[permissao]:
        raise HTTPException(403, 'Seu perfil não tem permissão para esta ação.')
    return u

def auditar(request: Request, acao: str, quem: str | None = None):
    o = request.state.orgao
    u = usuario(request)
    ip = request.headers.get('x-forwarded-for', request.client.host if request.client else '').split(',')[0].strip()
    db.exe(o['banco'], 'INSERT INTO auditoria (usuario, acao, ip) VALUES (%s,%s,%s)', (quem or (u['nome'] if u else 'anônimo'), acao, mascara_ip(ip)))
