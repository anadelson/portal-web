"""Remessa de atos entre órgãos (ex.: Câmara → caderno Legislativo do Diário da Prefeitura) por API interna.

Segurança: um token por par de órgãos (tabela pares_orgaos, no banco de controle); cada chamada leva
X-Portal-Origem, X-Portal-Momento e X-Portal-Assinatura = HMAC-SHA256(token, momento\\nMÉTODO\\ncaminho\\nsha256(corpo)),
com janela de 5 minutos, e fica registrada em remessas_log. A Câmara nunca acessa o banco da Prefeitura."""
import hashlib, hmac, json, re, secrets, time
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from . import config, db

r = APIRouter(prefix='/_p')
JANELA = 300
TIPOS_REMESSA = ['Ato da Mesa', 'Resolução', 'Decreto Legislativo', 'Extrato de contrato', 'Portaria da Câmara', 'Aviso']

def _orgao(slug=None, id_=None):
    return db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE ' + ('slug=%s' if slug else 'id=%s'), (slug or id_,))

def par(origem, destino):
    return db.um(db.PLATAFORMA, 'SELECT * FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s AND ativo', (origem['id'], destino['id']))

def configurar_pares():
    """Cria o par Legislativo → Executivo do mesmo município (Prefeitura com Diário contratado) se ainda não existir."""
    n = 0
    for c in db.todos(db.PLATAFORMA, "SELECT * FROM orgaos WHERE tipo='legislativo' AND ativo"):
        for p in db.todos(db.PLATAFORMA, """SELECT o.* FROM orgaos o JOIN orgao_modulos m ON m.orgao_id=o.id AND m.chave='diario' AND m.contratado
                                           WHERE o.tipo='executivo' AND o.ativo AND o.ibge=%s""", (c['ibge'],)):
            if not db.um(db.PLATAFORMA, 'SELECT 1 FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (c['id'], p['id'])):
                db.exe(db.PLATAFORMA, 'INSERT INTO pares_orgaos (origem_id, destino_id, token) VALUES (%s,%s,%s)', (c['id'], p['id'], secrets.token_urlsafe(32)))
                n += 1
    return n

def destino_do(origem):
    return db.um(db.PLATAFORMA, 'SELECT o.* FROM pares_orgaos p JOIN orgaos o ON o.id=p.destino_id WHERE p.origem_id=%s AND p.ativo ORDER BY o.id LIMIT 1', (origem['id'],))

def _assinatura(token, momento, metodo, caminho, corpo: bytes):
    msg = f'{momento}\n{metodo}\n{caminho}\n{hashlib.sha256(corpo).hexdigest()}'.encode()
    return hmac.new(token.encode(), msg, hashlib.sha256).hexdigest()

def _log(origem, destino, acao, ok, detalhe=''):
    db.exe(db.PLATAFORMA, 'INSERT INTO remessas_log (origem, destino, acao, ok, detalhe) VALUES (%s,%s,%s,%s,%s)', (origem, destino, acao, ok, detalhe[:500]))

# ---------- cliente (órgão de origem) ----------
def _cliente():
    """Cliente HTTP da API interna (substituível nos testes). Chame sempre fora do laço de eventos (run_in_threadpool),
    porque o destino pode ser o próprio processo."""
    return httpx.Client(base_url=config.INTERNO_BASE, timeout=30)

def chamar(origem, destino, metodo, caminho, dados=None):
    p = par(origem, destino)
    if not p:
        raise ValueError('Não há integração ativa entre os órgãos (par sem token).')
    corpo = json.dumps(dados or {}, ensure_ascii=False).encode() if metodo == 'POST' else b''
    m = str(int(time.time()))
    h = {'Host': destino['dominio'], 'Content-Type': 'application/json', 'X-Portal-Origem': origem['slug'], 'X-Portal-Momento': m,
         'X-Portal-Assinatura': _assinatura(p['token'], m, metodo, caminho, corpo), 'X-Forwarded-Proto': 'https'}
    try:
        with _cliente() as c:
            resp = c.request(metodo, caminho, content=corpo or None, headers=h)
        ok = resp.status_code < 400
        _log(origem['slug'], destino['slug'], f'{metodo} {caminho}', ok, '' if ok else resp.text[:200])
        if not ok:
            raise ValueError(f'O Diário de destino recusou ({resp.status_code}): {resp.json().get("erro", "") if resp.headers.get("content-type", "").startswith("application/json") else ""}')
        return resp.json()
    except httpx.HTTPError as e:
        _log(origem['slug'], destino['slug'], f'{metodo} {caminho}', False, type(e).__name__)
        raise ValueError(f'Não foi possível falar com o Diário de destino ({type(e).__name__}).')

def enviar(origem, quem, tipo, numero, ementa, texto):
    destino = destino_do(origem)
    if not destino:
        raise ValueError('Este órgão não tem Diário de destino configurado.')
    if tipo not in TIPOS_REMESSA or len(ementa or '') < 5 or len(texto or '') < 10:
        raise ValueError('Escolha o tipo e preencha ementa e texto.')
    if re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', texto + ementa):
        raise ValueError('O texto tem CPF completo. Remova ou mascare antes de enviar (LGPD).')
    rid = db.exe(origem['banco'], 'INSERT INTO remessas (destino, tipo, numero, ementa, texto, enviado_por) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
                 (destino['slug'], tipo, numero[:40], ementa[:500], texto[:50000], quem))['id']
    try:
        res = chamar(origem, destino, 'POST', '/api/diario/remessas', {'tipo': tipo, 'numero': numero, 'ementa': ementa, 'texto': texto, 'orgao': origem['nome'], 'remessa': rid})
        db.exe(origem['banco'], 'UPDATE remessas SET remoto_id=%s, situacao=%s, atualizado_em=now(), erro=%s WHERE id=%s', (res['id'], res['situacao'], '', rid))
    except ValueError as e:
        db.exe(origem['banco'], "UPDATE remessas SET situacao='falha no envio', erro=%s, atualizado_em=now() WHERE id=%s", (str(e)[:300], rid))
        raise
    return rid

def atualizar(origem, rid):
    rm = db.um(origem['banco'], 'SELECT * FROM remessas WHERE id=%s', (rid,))
    if not rm or not rm['remoto_id']:
        raise ValueError('Remessa sem número no destino.')
    res = chamar(origem, _orgao(slug=rm['destino']), 'GET', f"/api/diario/remessas/{rm['remoto_id']}")
    db.exe(origem['banco'], 'UPDATE remessas SET situacao=%s, edicao=%s, pagina=%s, data_publicacao=%s, atualizado_em=now(), erro=%s WHERE id=%s',
           (res['situacao'], res.get('edicao') or '', res.get('pagina'), res.get('data'), res.get('comentario') or '', rid))
    return res

# ---------- servidor (Diário de destino) ----------
async def _autenticar(request: Request):
    destino = request.state.orgao
    origem = _orgao(slug=request.headers.get('x-portal-origem', ''))
    corpo = await request.body()
    m = request.headers.get('x-portal-momento', '')
    if not origem or not m.isdigit() or abs(time.time() - int(m)) > JANELA:
        _log(request.headers.get('x-portal-origem', '?')[:40], destino['slug'], request.url.path, False, 'origem ou momento inválido')
        raise HTTPException(401, 'Remessa recusada: origem ou horário inválido.')
    p = par(origem, destino)
    caminho = request.url.path.replace('/_p', '', 1)
    if not p or not hmac.compare_digest(_assinatura(p['token'], m, request.method, caminho, corpo), request.headers.get('x-portal-assinatura', '')):
        _log(origem['slug'], destino['slug'], caminho, False, 'assinatura inválida')
        raise HTTPException(401, 'Remessa recusada: assinatura inválida.')
    return origem, destino, corpo

def _situacao(b, a):
    if not a:
        return None
    e = db.um(b, 'SELECT * FROM diario_edicoes WHERE id=%s', (a['edicao_id'],)) if a['edicao_id'] else None
    sit = {'revisao': 'recebido', 'aprovado': 'aprovado', 'devolvido': 'devolvido', 'publicado': 'publicado', 'rascunho': 'recebido'}.get(a['situacao'], a['situacao'])
    if e and e['situacao'] == 'publicada' and e['modo_teste']:
        sit = 'publicado em edição de TESTE (sem valor oficial)'
    if e and e['situacao'] == 'invalidada':
        sit = 'edição invalidada'
    return {'id': a['id'], 'situacao': sit, 'comentario': a['comentario'] or '',
            'edicao': f"{e['numero']}{e['letra']}" if e and e['situacao'] in ('publicada', 'invalidada') else '',
            'data': e['data'].isoformat() if e and e['situacao'] in ('publicada', 'invalidada') else None,
            'pagina': a['pagina'] if e and e['situacao'] in ('publicada', 'invalidada') else None, 'data_prevista': a['data_alvo'].isoformat() if a['data_alvo'] else None}

@r.post('/api/diario/remessas')
async def receber(request: Request):
    from . import diario as D
    from datetime import datetime
    origem, destino, corpo = await _autenticar(request)
    try:
        d = json.loads(corpo)
        assert d.get('tipo') in TIPOS_REMESSA and len(d.get('ementa', '')) >= 5 and len(d.get('texto', '')) >= 10
    except Exception:
        return JSONResponse({'erro': 'dados da remessa incompletos'}, status_code=400)
    b = destino['banco']
    ext = f"{origem['slug']}:{int(d.get('remessa') or 0)}"
    a = db.um(b, 'SELECT * FROM diario_atos WHERE remessa_externa=%s', (ext,))
    if not a:
        a = db.exe(b, """INSERT INTO diario_atos (caderno, tipo, numero, orgao, ementa, texto, situacao, autor, origem_orgao, remessa_externa, data_alvo)
                         VALUES ('legislativo',%s,%s,%s,%s,%s,'revisao',%s,%s,%s,%s) RETURNING *""",
                  (d['tipo'], str(d.get('numero', ''))[:40], str(d.get('orgao') or origem['nome'])[:160], d['ementa'][:500], d['texto'][:50000],
                   f"Remessa de {origem['nome']}", origem['slug'], ext, D.data_alvo(b, datetime.now())))
    _log(origem['slug'], destino['slug'], 'remessa recebida', True, f"ato {a['id']}")
    return _situacao(b, a)

@r.get('/api/diario/remessas/{aid}')
async def consultar(request: Request, aid: int):
    origem, destino, _ = await _autenticar(request)
    a = db.um(destino['banco'], 'SELECT * FROM diario_atos WHERE id=%s AND origem_orgao=%s', (aid, origem['slug']))
    if not a:
        return JSONResponse({'erro': 'remessa não encontrada'}, status_code=404)
    return _situacao(destino['banco'], a)
