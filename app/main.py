"""Aplicação única: console do gestor, portais dos órgãos e painéis /admin, separados pelo domínio."""
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import config, portal, admin, console, transparencia, admin_leg, portal_leg, remessa, portal_painel, admin_painel, portal_fase8, admin_fase8, admin_fase9, portal_fase9, admin_carta, portal_carta, admin_pntp, admin_integracao, portal_atendimento, admin_atendimento, admin_portal_antigo, portal_vitrine, admin_vitrine
from .web import RoteadorPorDominio, PortalOculto, templates

app = FastAPI(title=config.NOME_PLATAFORMA, docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')
app.include_router(transparencia.r)
app.include_router(portal_atendimento.r)
app.include_router(portal.r)
app.include_router(portal_painel.r)
app.include_router(portal_fase8.r)
app.include_router(admin_atendimento.r)
app.include_router(admin.r)
app.include_router(admin_painel.r)
app.include_router(admin_fase8.r)
app.include_router(admin_fase9.r)
app.include_router(portal_fase9.r)
app.include_router(portal_vitrine.r)
app.include_router(admin_vitrine.r)
app.include_router(admin_carta.r)
app.include_router(portal_carta.r)
app.include_router(admin_leg.r)
app.include_router(admin_portal_antigo.r)
app.include_router(admin_pntp.r)
app.include_router(admin_integracao.r)
app.include_router(portal_leg.r)
app.include_router(remessa.r)
app.include_router(console.r)

@app.get('/saude')
def saude():
    return {'ok': True}

@app.get('/_desconhecido')
def desconhecido():
    return PlainTextResponse('Domínio não cadastrado nesta plataforma.', status_code=404)

@app.exception_handler(HTTPException)
async def erros(request: Request, exc: HTTPException):
    if exc.status_code == 307 and exc.headers and 'Location' in exc.headers:
        return RedirectResponse(exc.headers['Location'], status_code=303)
    msg = exc.detail if isinstance(exc.detail, str) else 'Erro.'
    html = f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>{exc.status_code}</title><body style="font-family:system-ui;max-width:640px;margin:10vh auto;padding:0 20px"><h1>{exc.status_code}</h1><p>{msg}</p><p><a href="/">Voltar ao início</a></p></body></html>'
    return HTMLResponse(html, status_code=exc.status_code)

# Mapa das câmeras (26/11/2026): imagens do mapa do OpenStreetMap (tile.openstreetmap.org), só nas páginas com mapa.
# VLibras (Governo Federal, aprovado em 09/11/2026): o widget carrega script, estilos, imagens e o avatar (WebGL/WebAssembly) de vlibras.gov.br.
VLIBRAS = 'https://vlibras.gov.br https://*.vlibras.gov.br https://cdn.jsdelivr.net/gh/spbgovbr-vlibras/'  # vlibras.gov.br/app redireciona para a pasta oficial no jsDelivr
CSP = (f"default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' {VLIBRAS}; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com {VLIBRAS}; "
       f"font-src 'self' https://fonts.gstatic.com {VLIBRAS}; img-src 'self' data: blob: https://i.ytimg.com https://tile.openstreetmap.org {VLIBRAS}; media-src 'self' blob: {VLIBRAS}; worker-src 'self' blob:; "
       f"frame-src https://www.youtube-nocookie.com https:; connect-src 'self' {VLIBRAS}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

class Cabecalhos:
    """Cabeçalhos de segurança em todas as respostas (o HSTS vem do nginx)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        caminho = scope['path']  # o roteador por domínio reescreve scope['path'] (/admin → /_a): guarda o original
        async def enviar(msg):
            if msg['type'] == 'http.response.start':
                h = [(k, v) for k, v in msg.get('headers', []) if k.lower() not in (b'server',)]
                nomes = {k.lower() for k, _ in h}
                for k, v in ((b'content-security-policy', CSP.encode()), (b'x-frame-options', b'DENY'), (b'x-content-type-options', b'nosniff'),
                             (b'referrer-policy', b'strict-origin-when-cross-origin'), (b'permissions-policy', b'camera=(), microphone=(), geolocation=(), payment=()')):
                    if k not in nomes:
                        h.append((k, v))
                host = dict(scope.get('headers') or []).get(b'host', b'').decode().split(':')[0].lower()
                if (caminho.startswith('/admin') or host == config.DOMINIO_GESTAO.lower()) and b'cache-control' not in nomes:
                    h.append((b'cache-control', b'no-store'))
                msg = dict(msg, headers=h)
            await send(msg)
        return await self.app(scope, receive, enviar)

# Ordem: a sessão precisa existir antes do roteamento (middlewares rodam de fora para dentro: último adicionado = mais externo)
app.add_middleware(PortalOculto)  # mais interno: já tem a sessão e o caminho /_p/…
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie='sessao', same_site='lax', https_only=config.COOKIE_SEGURO, max_age=8 * 3600)
app.add_middleware(RoteadorPorDominio)
app.add_middleware(Cabecalhos)
