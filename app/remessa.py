"""Remessa de atos entre órgãos (ex.: Câmara → caderno Legislativo do Diário da Prefeitura) por API interna.

Funciona com os dois órgãos na mesma instalação ou em instalações separadas (ver app/integracao.py).
Segurança: um token por par de órgãos (tabela pares_orgaos, criado e distribuído pela gestão); cada chamada leva
X-Portal-Origem, X-Portal-Momento e X-Portal-Assinatura = HMAC-SHA256(token, momento\\nMÉTODO\\ncaminho\\nsha256(corpo)),
com janela de 5 minutos, e fica registrada em remessas_log. A Câmara nunca acessa o banco da Prefeitura."""
import json, re
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from . import config, db
from . import integracao as I

r = APIRouter(prefix='/_p')
JANELA = I.JANELA
TIPOS_REMESSA = ['Ato da Mesa', 'Resolução', 'Decreto Legislativo', 'Extrato de contrato', 'Portaria da Câmara', 'Aviso']

def _orgao(slug=None, id_=None):
    return I.parceiro(slug=slug, id_=id_)

def par(origem, destino):
    return I.par(origem, destino)

def configurar_pares():
    """Pares entre os órgãos do mesmo município (um token por sentido). Desde 23/11/2026 a gestão cria e distribui os
    pares para todos os nós (integracao.garantir_pares); aqui fica o nome antigo, usado pelo provision e pelas ordens."""
    return I.garantir_pares()

def destino_do(origem):
    """O Diário de destino da remessa: Prefeitura do mesmo município com o Diário contratado e par ativo, esteja ela
    nesta instalação ou em outra."""
    for p in sorted(I.parceiros(origem), key=lambda x: x['id']):
        if p['tipo'] == 'executivo' and 'diario' in (p.get('servicos') or []) and par(origem, p):
            return p
    return None

def _assinatura(token, momento, metodo, caminho, corpo: bytes):
    return I.assinatura(token, momento, metodo, caminho, corpo)

def _log(origem, destino, acao, ok, detalhe=''):
    I.log(origem, destino, acao, ok, detalhe)

# ---------- cliente (órgão de origem) ----------
def _cliente():
    """Cliente HTTP da API interna para Diário NESTA instalação (substituível nos testes). Chame sempre fora do laço de
    eventos (run_in_threadpool), porque o destino pode ser o próprio processo. Diário em outra instalação: HTTPS público."""
    return I.cliente_local()

def chamar(origem, destino, metodo, caminho, dados=None):
    return I.chamar(origem, destino, metodo, caminho, dados, cliente=lambda: _cliente(), rotulo='Diário de destino')

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
    return await I.autenticar(request)

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
