"""Páginas públicas de selos (/selos), vídeos (/videos) e câmeras ao vivo (/cameras), 26/11/2026.
O vídeo das câmeras passa pelo portal (/cameras/<id>/…) a partir do conversor do nó; o endereço da câmera nunca chega ao navegador."""
import re
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from starlette.background import BackgroundTask
from . import db, vitrine as VT
from .web import templates, ctx_orgao

r = APIRouter(prefix='/_p')
_RESTO = re.compile(r'^(?!.*\.\.)[A-Za-z0-9_\-.]+(/[A-Za-z0-9_\-.]+)*$')
_QS = re.compile(r'^[A-Za-z0-9_=&.\-]{0,200}$')
CSP_CAMERA = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
              "media-src 'self' blob:; worker-src 'self' blob:; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'")

@r.get('/selos')
def selos(request: Request):
    ctx = ctx_orgao(request)
    o = ctx['orgao']
    lista = [] if ctx['defeso'] else VT.selos(o['banco'])
    for s in lista:
        s['doc'] = VT.info_documento(o, s['documento'])
    return templates.TemplateResponse(request, 'portal/selos.html', dict(ctx, selos=lista))

@r.get('/videos')
def videos(request: Request):
    ctx = ctx_orgao(request)
    g = VT.galeria_unica(ctx['orgao']['banco'], ctx['mods'], ctx['defeso'], limite_videos=60)
    return templates.TemplateResponse(request, 'portal/videos.html', dict(ctx, galeria_d=g))

@r.get('/cameras')
def cameras(request: Request):
    """Galeria única desde 26/11/2026: as câmeras ficam junto dos vídeos."""
    return RedirectResponse('/videos', status_code=301)

@r.get('/cameras/{cid}/{resto:path}')
async def camera_video(request: Request, cid: int, resto: str = ''):
    """Repasse só de leitura (GET) do HLS do conversor para a câmera ativa deste órgão."""
    import httpx
    o = request.state.orgao
    c = db.um(o['banco'], 'SELECT caminho FROM cameras WHERE id=%s AND ativa AND NOT exemplo', (cid,))
    if not c or (resto and not _RESTO.match(resto)):
        raise HTTPException(404, 'Câmera não encontrada.')
    qs = request.url.query
    if not _QS.match(qs):
        raise HTTPException(400)
    cliente = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=3))
    try:
        resp = await cliente.send(cliente.build_request('GET', f"{VT.HLS}/{c['caminho']}/{resto}" + (f'?{qs}' if qs else '')), stream=True)
    except httpx.HTTPError:
        await cliente.aclose()
        raise HTTPException(503, 'Câmera fora do ar no momento. Tente de novo em alguns minutos.')
    async def fechar():
        await resp.aclose()
        await cliente.aclose()
    if resp.status_code >= 400:
        await fechar()
        raise HTTPException(503 if resp.status_code >= 500 else 404, 'Câmera fora do ar no momento. Tente de novo em alguns minutos.')
    h = {'Cache-Control': resp.headers.get('cache-control', 'no-cache'), 'X-Frame-Options': 'SAMEORIGIN', 'Content-Security-Policy': CSP_CAMERA}
    return StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, media_type=resp.headers.get('content-type', 'application/octet-stream'),
                             headers=h, background=BackgroundTask(fechar))
