"""Páginas públicas da Fase 9: álbuns de fotos (/fotos)."""
from fastapi import APIRouter, Request, HTTPException
from . import db, eleicao
from .web import templates, ctx_orgao

r = APIRouter(prefix='/_p')
PORTAL_FOTOS_POR_PAGINA = 40  # álbum com centenas de fotos: o portal pagina (e a ampliação percorre só a página)

def _suspensas(b):
    """Categorias marcadas para sair do ar no período eleitoral (só valem durante o defeso)."""
    if not eleicao.em_defeso(b):
        return set()
    return {x['id'] for x in db.todos(b, 'SELECT id FROM foto_categorias WHERE suspender_defeso')}

def fotos_publicas(b, album):
    sus = _suspensas(b)
    if album['categoria_id'] in sus:
        return []
    return [f for f in db.todos(b, 'SELECT * FROM album_fotos WHERE album_id=%s ORDER BY principal DESC, ordem, id', (album['id'],))
            if (not f['tem_pessoas'] or f['autorizacao_imagem']) and f['categoria_id'] not in sus]

def com_alt(fotos, album):
    """Texto alternativo é opcional: sem ele, a galeria usa o título da foto ou "Foto N do álbum …"."""
    return [dict(f, alt_portal=f['alt'] or f['titulo'] or f"Foto {i} do álbum {album['titulo']}") for i, f in enumerate(fotos, 1)]

def albuns_publicos(b, limite=None):
    out = []
    for a in db.todos(b, 'SELECT * FROM albuns WHERE publicado ORDER BY ordem, id DESC'):
        if limite and len(out) >= limite:
            break
        fs = fotos_publicas(b, a)
        if fs:
            out.append(dict(a, capa=fs[0], n=len(fs)))
    return out

@r.get('/fotos')
def fotos(request: Request):
    ctx = ctx_orgao(request)
    return templates.TemplateResponse(request, 'portal/fotos.html', dict(ctx, albuns=albuns_publicos(ctx['orgao']['banco']), legal='conheca'))

@r.get('/fotos/{aid}')
def album(request: Request, aid: int):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    a = db.um(b, 'SELECT * FROM albuns WHERE id=%s AND publicado', (aid,))
    fs = com_alt(fotos_publicas(b, a), a) if a else []
    if not fs:
        raise HTTPException(404, 'Álbum não encontrado.')
    q = request.query_params.get('p', '')
    paginas = -(-len(fs) // PORTAL_FOTOS_POR_PAGINA)
    pg = min(max(1, int(q)), paginas) if q.isdigit() else 1
    ini = (pg - 1) * PORTAL_FOTOS_POR_PAGINA
    return templates.TemplateResponse(request, 'portal/album.html', dict(ctx, a=a, fotos=fs[ini:ini + PORTAL_FOTOS_POR_PAGINA], total=len(fs), inicio=ini,
                                                                         pg=pg, paginas=paginas, legal='conheca'))
