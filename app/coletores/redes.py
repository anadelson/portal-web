"""Redes sociais (Fase 9): últimas publicações das contas oficiais, só por API oficial e com credencial no console.

- YouTube: chave "youtube" (a mesma das transmissões); conta = ID do canal (UC…).
- Instagram / Facebook: token "meta" (Graph API da Meta, conta comercial/página do órgão); conta = ID da conta ou página.
- Outras redes (X, TikTok, LinkedIn, WhatsApp): só o link com ícone — sem API gratuita/oficial adequada.
- As miniaturas são baixadas e servidas pelo próprio portal (/midia): o navegador do cidadão não fala com servidores das redes (LGPD).
- Sem credencial ou sem conta informada: nada a fazer (lista vazia). Erros registram só o código HTTP (as URLs levam o token)."""
import secrets
from datetime import datetime, timezone
from pathlib import Path
import httpx
from .. import config, db, credenciais as CR
from .comum import anotar

GRAPH = 'https://graph.facebook.com/v21.0'
MAX = 6

def _get(fonte, url, params):
    import time
    t0 = time.monotonic()
    try:
        with httpx.Client(timeout=30, headers={'User-Agent': 'PortaisBora-coletor/1.0', 'Accept': 'application/json'}) as c:
            r = c.get(url, params=params)
    except Exception as e:
        anotar(fonte, url, params, 0, int((time.monotonic() - t0) * 1000), erro=type(e).__name__)
        raise RuntimeError(f'falha de conexão ({type(e).__name__})') from None
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        anotar(fonte, url, params, r.status_code, ms, erro=f'HTTP {r.status_code}')
        raise RuntimeError(f'HTTP {r.status_code}')
    d = r.json()
    anotar(fonte, url, params, 200, ms, d)
    return d

def _miniatura(o, url):
    """Baixa a imagem (até 3 MB, formato conferido) para a pasta de mídia do órgão. Devolve a URL local ou ''."""
    if not url or not url.startswith('https://'):
        return ''
    if db.ENSAIO.get() is not None:
        return ''
    from ..imagens import validar_upload, LIMITE_UPLOAD
    try:
        with httpx.Client(timeout=30, follow_redirects=True, headers={'User-Agent': 'PortaisBora-coletor/1.0'}) as c:
            r = c.get(url)
        dados = r.content[:LIMITE_UPLOAD + 1]
        ext = validar_upload(dados)
    except Exception:
        return ''
    pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.{ext}'
    (pasta / nome).write_bytes(dados)
    return f'/midia/{nome}'

def youtube(o, conta, key):
    if not conta.startswith('UC') or len(conta) != 24:
        raise RuntimeError('ID do canal deve começar com UC e ter 24 caracteres')
    pl = _get('redes', 'https://www.googleapis.com/youtube/v3/playlistItems', {'part': 'snippet', 'playlistId': 'UU' + conta[2:], 'maxResults': MAX, 'key': key})
    out = []
    for x in pl.get('items', []):
        sn = x.get('snippet') or {}
        vid = (sn.get('resourceId') or {}).get('videoId')
        if not vid:
            continue
        th = ((sn.get('thumbnails') or {}).get('medium') or {}).get('url', '')
        out.append({'rede': 'youtube', 'texto': (sn.get('title') or '')[:200], 'link': f'https://www.youtube.com/watch?v={vid}',
                    'quando': sn.get('publishedAt', ''), 'img_origem': th})
    return out

def instagram(o, conta, token):
    d = _get('redes', f'{GRAPH}/{conta}/media', {'fields': 'caption,media_type,media_url,thumbnail_url,permalink,timestamp', 'limit': MAX, 'access_token': token})
    return [{'rede': 'instagram', 'texto': (x.get('caption') or '')[:200], 'link': x.get('permalink', ''), 'quando': x.get('timestamp', ''),
             'img_origem': x.get('thumbnail_url') if x.get('media_type') == 'VIDEO' else x.get('media_url', '')} for x in d.get('data', []) if x.get('permalink')]

def facebook(o, conta, token):
    d = _get('redes', f'{GRAPH}/{conta}/posts', {'fields': 'message,permalink_url,created_time,full_picture', 'limit': MAX, 'access_token': token})
    return [{'rede': 'facebook', 'texto': (x.get('message') or '')[:200], 'link': x.get('permalink_url', ''), 'quando': x.get('created_time', ''),
             'img_origem': x.get('full_picture', '')} for x in d.get('data', []) if x.get('permalink_url')]

def coletar(o, p, hoje=None):
    ident = db.cfg(o['banco'], 'identidade', {}) or {}
    redes = [r for r in ident.get('redes_v2', []) if r.get('conta') and r['tipo'] in ('youtube', 'instagram', 'facebook')]
    if not redes:
        return []
    yt, meta = CR.obter('youtube'), CR.obter('meta')
    res, feed = [], []
    for r in redes:
        cred = yt if r['tipo'] == 'youtube' else meta
        if not cred:
            continue  # sem credencial: só o link com ícone
        try:
            itens = {'youtube': youtube, 'instagram': instagram, 'facebook': facebook}[r['tipo']](o, r['conta'], cred[1])
            for x in itens:
                x['img'] = _miniatura(o, x.pop('img_origem', ''))
            feed += itens
            res.append((r['tipo'], True, len(itens), f"{len(itens)} publicação(ões)"))
        except (RuntimeError, ValueError, KeyError) as e:
            res.append((r['tipo'], False, 0, str(e)[:120]))
    if feed and db.ENSAIO.get() is None:
        feed.sort(key=lambda x: x.get('quando') or '', reverse=True)
        antigo = (db.cfg(o['banco'], 'redes_feed', {}) or {}).get('itens', [])
        db.set_cfg(o['banco'], 'redes_feed', {'itens': feed[:MAX * 2], 'atualizado': datetime.now(timezone.utc).isoformat()})
        for x in antigo:  # miniaturas que saíram do feed são apagadas
            if x.get('img', '').startswith('/midia/'):
                f = Path(config.DADOS_DIR) / o['slug'] / 'midia' / x['img'].rsplit('/', 1)[1]
                f.unlink(missing_ok=True)
    return res
