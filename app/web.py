"""Peças comuns: resolução do órgão pelo domínio, templates, sessão e proteção de formulários."""
import time
from datetime import date, datetime
from pathlib import Path
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from . import config, db, eleicao
from .catalogo import MOD, serve, CLASSES, SITUACOES, PERFIS, BASE_LEGAL, PODE, TEMAS
from .security import token, mascara_ip

templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

def br(d):
    if not d:
        return ''
    if isinstance(d, str):
        d = date.fromisoformat(d[:10])
    if isinstance(d, datetime):
        if d.tzinfo:  # horário de Brasília (TZ do container), qualquer que seja o fuso da sessão do banco
            d = d.astimezone()
        return d.strftime('%d/%m/%Y %H:%M')
    return d.strftime('%d/%m/%Y')

def moeda(v):
    if v is None:
        return '—'
    s = f'{float(v):,.2f}'
    return 'R$ ' + s.replace(',', 'X').replace('.', ',').replace('X', '.')

def _rgb(h):
    h = (h or '#1D4E89').lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (29, 78, 137)

def mistura(cor, outra, t):
    """Mistura duas cores #RRGGBB (t = peso da segunda)."""
    a, b = _rgb(cor), _rgb(outra)
    return '#%02X%02X%02X' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))

def iniciais(nome):
    p = [x for x in (nome or '').split() if x[:1].isalpha() and x.lower() not in ('de', 'da', 'do', 'dos', 'das', 'e')]
    return ((p[0][:1] + p[-1][:1]) if len(p) > 1 else (p[0][:2] if p else '?')).upper()

# Ícones de traço 24×24 (caminhos do protótipo do painel + ícones do portal)
ICONES = {
    'painel': 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
    'lista': 'M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6',
    'home': 'M3 4h18v6H3zM3 14h8v6H3zM15 14h6v6h-6z',
    'midia': 'M3 5h18v14H3zM3 16l5-5 4 4 3-3 6 6M14 9.5a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0',
    'ident': 'M3 5h18v14H3zM6 16c.8-2 5.2-2 6 0M7 10.5a2 2 0 1 0 4 0a2 2 0 1 0-4 0M15 9h3M15 12h3M15 15h2',
    'vereadores': 'M5 7.5a4 4 0 1 0 8 0a4 4 0 1 0-8 0M2 21c0-4 3-6 7-6s7 2 7 6M16 3.5a4 4 0 0 1 0 7.5M18 15c2.5.5 4 2.5 4 6',
    'sessoes': 'M4 5h16v16H4zM4 9h16M8 3v4M16 3v4M9 15l2 2 4-4',
    'proposicoes': 'M6 3h9l4 4v14H6zM15 3v4h4M9 11h6M9 14h6M9 17h4',
    'emendas': 'M4 6a8 3 0 1 0 16 0a8 3 0 1 0-16 0M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6',
    'diario': 'M4 5h13v14a2 2 0 0 0 2 2H6a2 2 0 0 1-2-2zM17 9h3v10a2 2 0 0 1-2 2M7 9h7M7 13h7M7 17h4',
    'transm': 'M3 6h13v12H3zM16 10l5-3v10l-5-3',
    'bases': 'M4 6a8 3 0 1 0 16 0a8 3 0 1 0-16 0M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3',
    'integ': 'M4 12a8 8 0 0 1 14-5.3L20 5v6h-6l2.3-2.3A5 5 0 0 0 7 12M20 12a8 8 0 0 1-14 5.3L4 19v-6h6l-2.3 2.3A5 5 0 0 0 17 12',
    'indicadores': 'M4 4v16h16M8 16v-5M12 16V8M16 16v-3',
    'esic': 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 11v6M12 7.5v.01',
    'ouvidoria': 'M4 5h16v11H9l-5 4zM8 9h8M8 12h5',
    'participacao': 'M3 10v4h4l6 5V5l-6 5zM16.5 9a4 4 0 0 1 0 6M19 6.5a7.5 7.5 0 0 1 0 11',
    'mods': 'M4 7h9M17 7h3M4 17h3M11 17h9M15 4v6M9 14v6',
    'eleicao': 'M4 11h16v9H4zM8 11V4h8v7M10 7h4M4 15h16',
    'lgpd': 'M5 11h14v10H5zM8 11V8a4 4 0 0 1 8 0v3M12 15v2',
    'users': 'M5 7.5a4 4 0 1 0 8 0a4 4 0 1 0-8 0M2 21c0-4 3-6 7-6 1.6 0 3 .3 4.1.9M18 14v7M14.5 17.5h7',
    'perfil': 'M8 8a4 4 0 1 0 8 0a4 4 0 1 0-8 0M4 21c0-4 3.5-6 8-6s8 2 8 6',
    'orgaos': 'M4 21V9l8-5 8 5v12M9 21v-6h6v6M8 11h.01M12 11h.01M16 11h.01M2 21h20',
    'operacao': 'M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0',
    'aud': 'M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 7v5l3 2',
    # portal
    'busca': 'M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0M20 20l-4-4',
    'grafico': 'M4 4v16h16M8 16v-5M12 16V8M16 16v-3',
    'atendimento': 'M4 13a8 8 0 0 1 16 0M4 13v4h3v-5H4M20 13v4h-3v-5h3M17 17c0 2-2 3-5 3',
    'predio': 'M3 21h18M5 21V10M19 21V10M9 21v-7h6v7M2 10l10-6 10 6',
    'saude': 'M12 21s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 6-8 11-8 11zM9 11h6M12 8v6',
    'educacao': 'M2 9l10-5 10 5-10 5zM6 11v5c3 2.5 9 2.5 12 0v-5M22 9v6',
    'tributos': 'M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3',
    'empresas': 'M3 8h18v12H3zM8 8V5h8v3M3 13h18',
    'cidade': 'M3 21h18M5 21V8l5-3v16M10 21V10h9v11M13 13h3M13 17h3',
    'social': 'M8 7a3 3 0 1 0 6 0a3 3 0 1 0-6 0M3 21c0-3.5 3-6 8-6s8 2.5 8 6M17 4a3 3 0 0 1 0 6',
    'local': 'M12 21s-7-6.1-7-11.5A7 7 0 0 1 19 9.5C19 14.9 12 21 12 21zM9.5 9.5a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0',
    'relogio': 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M12 7v5l3 2',
    'telefone': 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z',
    'whatsapp': 'M4 20l1.5-4A8 8 0 1 1 9 19.5z',
    'radar': 'M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0M8 12a4 4 0 1 0 8 0a4 4 0 1 0-8 0M12 12l6-6',
    'estrela': 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z',
    'topo': 'M12 19V5M5 12l7-7 7 7',
    'cadeado': 'M5 11h14v10H5zM8 11V8a4 4 0 0 1 8 0v3',
    'seta': 'M5 12h14M13 6l6 6-6 6',
    'acess': 'M12 4a1.5 1.5 0 1 0 0 .01M6 8l6 1.2L18 8M12 9.2V14m0 0l-3 6m3-6l3 6',
}

def icone(nome, tam=24, classe=''):
    from markupsafe import Markup
    d = ICONES.get(nome, ICONES['lista'])
    return Markup(f'<svg class="ic {classe}" width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="{d}"/></svg>')

templates.env.filters['br'] = br
templates.env.filters['moeda'] = moeda
templates.env.filters['iniciais'] = iniciais
templates.env.globals.update(CLASSES=CLASSES, SITUACOES=SITUACOES, PERFIS=PERFIS, BASE_LEGAL=BASE_LEGAL, icone=icone, TEMAS=TEMAS)

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

def vizinhos(o):
    """Outros órgãos ativos do mesmo município (ex.: a Câmara, vista pela Prefeitura)."""
    orgao_por_dominio(o['dominio'])
    return [x for x in _cache['orgaos'].values() if x['ibge'] == o['ibge'] and x['id'] != o['id']]

def ctx_orgao(request: Request, **extra):
    o = request.state.orgao
    ident = db.cfg(o['banco'], 'identidade', {}) or {}
    mods = modulos_do_orgao(o)
    cor = ident.get('cor') or o['cor']
    tokens = {'cor': cor, 'cor_escura': mistura(cor, '#000000', .3), 'cor_clara': mistura(cor, '#FFFFFF', .88),
              'destaque': ident.get('cor_destaque') or '#F0B429'}
    ao_vivo = db.um(o['banco'], 'SELECT id, titulo, tipo, iniciada_em FROM transmissoes WHERE ao_vivo ORDER BY iniciada_em DESC LIMIT 1') if (mods.get('transm') or mods.get('audiencias')) else None
    d = dict(request=request, orgao=o, ident=ident, mods=mods, cor=cor, tokens=tokens, vizinhos=vizinhos(o), leg=o['tipo'] == 'legislativo', atual=request.url.path[3:] or '/', ao_vivo=ao_vivo,
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
    from .acesso import sessao_expirada
    if request.session.get('u') and sessao_expirada(request):
        request.session['msg'] = 'Sessão encerrada por inatividade. Entre de novo.'
        raise HTTPException(status_code=307, headers={'Location': '/admin/login'})
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
