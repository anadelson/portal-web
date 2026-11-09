"""Fase 9 — "Avalie esta página": controle de repetição por cookie próprio (sem dado pessoal) e limite por conexão.

- Cookie "aval": lista curta "código-da-página.dia" (código = 10 caracteres do SHA-256 do caminho; dia = dias desde 1970).
  Não identifica a pessoa; só diz que este navegador já avaliou aquela página. Validade = prazo configurado (padrão 30 dias).
- Limite por conexão: no máximo 5 avaliações por hora. Guardamos só o hash do IP com um sal que muda todo dia
  (SHA-256 de SECRET_KEY + data + IP); o hash é apagado depois de 2 dias. O IP puro nunca é gravado."""
import hashlib, time
from datetime import date, timedelta
from . import config, db

COOKIE = 'aval'
LIMITE_HORA = 5
MAX_PAGINAS = 40

def prazo(banco):
    try:
        d = int((db.cfg(banco, 'avaliacao', {}) or {}).get('dias', 30))
    except (TypeError, ValueError):
        d = 30
    return max(1, min(d, 365))

def codigo(pagina):
    return hashlib.sha256(pagina.encode()).hexdigest()[:10]

def hoje_n():
    return (config.hoje() - date(1970, 1, 1)).days

def ler(request):
    out = {}
    for p in (request.cookies.get(COOKIE) or '').split('-'):
        c, _, d = p.partition('.')
        if len(c) == 10 and d.isdigit():
            out[c] = int(d)
    return out

def avaliada_em(request, banco, pagina):
    """Data da avaliação anterior desta página por este navegador, se ainda dentro do prazo; senão None."""
    d = ler(request).get(codigo(pagina))
    if d is None or hoje_n() - d >= prazo(banco):
        return None
    return date(1970, 1, 1) + timedelta(days=d)

def proxima(banco, quando):
    return quando + timedelta(days=prazo(banco))

def gravar_cookie(resp, request, banco, pagina):
    lim = hoje_n() - prazo(banco)
    v = {c: d for c, d in ler(request).items() if d > lim}
    v[codigo(pagina)] = hoje_n()
    itens = sorted(v.items(), key=lambda x: -x[1])[:MAX_PAGINAS]
    resp.set_cookie(COOKIE, '-'.join(f'{c}.{d}' for c, d in itens), max_age=prazo(banco) * 86400, path='/',
                    httponly=True, samesite='lax', secure=config.COOKIE_SEGURO)

def ip_hash(request):
    ip = (request.headers.get('x-forwarded-for') or (request.client.host if request.client else '')).split(',')[0].strip()
    return hashlib.sha256(f'{config.SECRET_KEY}|{config.hoje().isoformat()}|{ip}'.encode()).hexdigest()

def excedeu(banco, h):
    db.exe(banco, "UPDATE avaliacoes SET ip_hash='' WHERE ip_hash<>'' AND criado_em < now() - interval '2 days'")
    n = db.um(banco, "SELECT count(*) n FROM avaliacoes WHERE ip_hash=%s AND criado_em > now() - interval '1 hour'", (h,))['n']
    return n >= LIMITE_HORA
