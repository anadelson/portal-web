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
    from . import integracao
    return integracao.orgao(slug=slug, id_=id_)   # desta instalação ou parceiro de outra (23/11/2026)

def par(origem, destino):
    from . import integracao
    return integracao.par(origem, destino)

def configurar_pares():
    """Cria o par Legislativo → Executivo do mesmo município (Prefeitura com Diário contratado) se ainda não existir.
    Desde 23/11/2026 a gestão cria os pares de todos os órgãos do município (integracao.garantir_pares) e os nós recebem os
    tokens no diretório: aqui só resta o caso do nó que ainda não recebeu diretório (gestão antiga)."""
    from . import orgaos, licenca, integracao
    if config.PAPEL != 'no':
        return integracao.garantir_pares()
    if integracao.tem_diretorio():
        return 0
    n = 0
    for c in orgaos.todos(tipo='legislativo'):
        for p in [x for x in orgaos.todos(tipo='executivo') if x['ibge'] == c['ibge'] and 'diario' in ((licenca.vigente(x) or {}).get('modulos') or [])]:
            if not db.um(db.LOCAL, 'SELECT 1 FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (c['id'], p['id'])):
                db.exe(db.LOCAL, 'INSERT INTO pares_orgaos (origem_id, destino_id, token) VALUES (%s,%s,%s)', (c['id'], p['id'], secrets.token_urlsafe(32)))
                n += 1
    return n

def destino_do(origem):
    """Diário de destino da Câmara: a Prefeitura do município que tem o módulo Diário (nesta instalação ou em outra)."""
    from . import integracao, licenca
    for o in integracao.parceiros(origem):
        if o['tipo'] == 'executivo' and integracao.par(origem, o):
            mods = o.get('modulos') if o.get('parceiro') else ((licenca.vigente(o) or {}).get('modulos') or [])
            if 'diario' in (mods or []):
                return o
    return None

def _assinatura(token, momento, metodo, caminho, corpo: bytes):
    from . import integracao
    return integracao.assinatura(token, momento, metodo, caminho, corpo)

def _log(origem, destino, acao, ok, detalhe=''):
    from . import integracao
    integracao.log(origem, destino, acao, ok, detalhe)

# ---------- cliente (órgão de origem) ----------
def chamar(origem, destino, metodo, caminho, dados=None):
    """Chamada ao Diário de destino: interna (mesma instalação) ou HTTPS (outra), sempre assinada (integracao.chamar)."""
    from . import integracao
    try:
        return integracao.chamar(origem, destino, metodo, caminho, dados)
    except ValueError as e:
        raise ValueError(str(e).replace('recusou', 'recusou a remessa', 1))

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
    from . import integracao
    return await integracao.autenticar(request)

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
                   f"Remessa de {origem['nome']}", origem['slug'], ext, D.data_alvo(b, config.agora())))
    _log(origem['slug'], destino['slug'], 'remessa recebida', True, f"ato {a['id']}")
    return _situacao(b, a)

@r.get('/api/diario/remessas/{aid}')
async def consultar(request: Request, aid: int):
    origem, destino, _ = await _autenticar(request)
    a = db.um(destino['banco'], 'SELECT * FROM diario_atos WHERE id=%s AND origem_orgao=%s', (aid, origem['slug']))
    if not a:
        return JSONResponse({'erro': 'remessa não encontrada'}, status_code=404)
    return _situacao(destino['banco'], a)

# ---------- teste de conversa entre os órgãos (23/11/2026) ----------
@r.get('/api/integracao/ping')
async def ping(request: Request):
    """Responde a uma chamada ASSINADA do parceiro: prova que tokens, horário e caminho (interno ou HTTPS) funcionam."""
    origem, destino, _ = await _autenticar(request)
    from . import licenca
    _log(origem['slug'], destino['slug'], 'ping', True)
    return JSONResponse({'ok': True, 'orgao': destino['nome'], 'slug': destino['slug'], 'versao': licenca.VERSAO_APP(), 'papel': config.PAPEL})
