"""Aplicação única: console do gestor, portais dos órgãos e painéis /admin, separados pelo domínio."""
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import config, portal, admin, console, transparencia, admin_leg, portal_leg, remessa
from .web import RoteadorPorDominio, templates

app = FastAPI(title='Portais de Borá — piloto', docs_url=None, redoc_url=None, openapi_url=None)
app.mount('/static', StaticFiles(directory=str(Path(__file__).parent / 'static')), name='static')
app.include_router(transparencia.r)
app.include_router(portal.r)
app.include_router(admin.r)
app.include_router(admin_leg.r)
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

# Ordem: a sessão precisa existir antes do roteamento (middlewares rodam de fora para dentro: último adicionado = mais externo)
app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY, session_cookie='sessao', same_site='lax', https_only=config.COOKIE_SEGURO, max_age=8 * 3600)
app.add_middleware(RoteadorPorDominio)
