"""Painel → Diário Oficial → Plataformas externas (27/11/2026): fontes do Diário em plataforma de terceiros (ex.: DOSP).

Cadastrar, ativar/desativar, ver a última sincronização e o erro, e sincronizar na hora. A fonte não é apagada: desativar
só para a sincronização, e as edições já listadas continuam no portal (o histórico é permanente)."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from psycopg.types.json import Jsonb
from . import db, diario_externo as DX, diario_fontes as DF
from .web import ir, exige, auditar, ler_form, modulos_do_orgao
from .admin import T

r = APIRouter(prefix='/_a')
VOLTA = '/admin/diario/fontes'


def _modulo(request):
    if not modulos_do_orgao(request.state.orgao).get('diario'):
        raise HTTPException(404)


@r.get('/diario/fontes')
def fontes(request: Request):
    u = exige(request); _modulo(request); b = request.state.orgao['banco']
    lista = DX.fontes(b)
    for f in lista:
        f['plataforma'] = DX.plataforma(f['tipo'])
        f['n'] = db.um(b, 'SELECT count(*) n, max(data) ult FROM diario_externo_edicoes WHERE fonte_id=%s', (f['id'],))
        f['syncs'] = db.todos(b, 'SELECT * FROM diario_sincronizacoes WHERE fonte_id=%s ORDER BY id DESC LIMIT 5', (f['id'],))
    tipos = [(k, c.plataforma, c.campos) for k, c in sorted(DF.ADAPTADORES.items())]
    return T('diario_fontes', request, u, fontes=lista, tipos=tipos)


def _validar(f, tipo):
    cls = DF.ADAPTADORES.get(tipo)
    if not cls:
        raise ValueError('Escolha a plataforma.')
    nome = (f.get('nome') or '').strip()[:120]
    if len(nome) < 3:
        raise ValueError('Informe o nome da fonte como deve aparecer em "Fonte oficial:" (ex.: Imprensa Oficial Municipal — DOSP).')
    try:
        intervalo = int(f.get('intervalo_min') or 60)
    except ValueError:
        intervalo = 0
    if not 15 <= intervalo <= 1440:
        raise ValueError('O intervalo da sincronização vai de 15 a 1440 minutos.')
    return nome, cls.validar_config({k: f.get(k, '') for k, _, _ in cls.campos}), intervalo, f.get('nova_aba') == '1'


@r.post('/diario/fontes')
async def fontes_post(request: Request):
    u = exige(request, 'config'); _modulo(request); b = request.state.orgao['banco']
    f = await ler_form(request)
    acao = f.get('acao', '')
    fid = int(f['id']) if str(f.get('id') or '').isdigit() else 0
    atual = db.um(b, 'SELECT * FROM diario_fontes WHERE id=%s', (fid,)) if fid else None
    if fid and not atual:
        return ir(VOLTA, 'Fonte não encontrada.', request)
    try:
        if acao == 'criar':
            nome, cfg, intervalo, nova_aba = _validar(f, f.get('tipo', ''))
            db.exe(b, 'INSERT INTO diario_fontes (tipo, nome, config, intervalo_min, nova_aba) VALUES (%s,%s,%s,%s,%s)',
                   (f['tipo'], nome, Jsonb(cfg), intervalo, nova_aba))
            auditar(request, f'Diário: fonte externa cadastrada ({nome})')
            return ir(VOLTA, 'Fonte cadastrada. A primeira sincronização roda em até 1 minuto, ou clique em "Sincronizar agora".', request)
        if not atual:
            return ir(VOLTA, '', request)
        if acao == 'salvar':
            nome, cfg, intervalo, nova_aba = _validar(f, atual['tipo'])
            if cfg.get('slug') == (atual['config'] or {}).get('slug'):
                cfg = dict(atual['config'], **cfg)  # mesmo endereço: mantém o código já descoberto
            db.exe(b, 'UPDATE diario_fontes SET nome=%s, config=%s, intervalo_min=%s, nova_aba=%s, atualizado_em=now() WHERE id=%s',
                   (nome, Jsonb(cfg), intervalo, nova_aba, fid))
            auditar(request, f'Diário: fonte externa alterada ({nome})')
            return ir(VOLTA, 'Fonte salva.', request)
        if acao in ('ativar', 'desativar'):
            db.exe(b, 'UPDATE diario_fontes SET ativa=%s, falhas_seguidas=0, atualizado_em=now() WHERE id=%s', (acao == 'ativar', fid))
            auditar(request, f"Diário: fonte externa {'ativada' if acao == 'ativar' else 'desativada'} ({atual['nome']})")
            return ir(VOLTA, 'Fonte ativada.' if acao == 'ativar' else 'Fonte desativada: a sincronização parou e as edições já listadas continuam no portal.', request)
        if acao == 'sincronizar':
            res = await run_in_threadpool(DX.sincronizar, b, atual)
            auditar(request, f"Diário: sincronização manual ({atual['nome']})")
            if res['erro']:
                return ir(VOLTA, f"A sincronização falhou: {res['erro']}", request)
            return ir(VOLTA, f"Sincronizado: {res['novas']} edição(ões) nova(s), {res['atualizadas']} atualizada(s).", request)
    except ValueError as e:
        return ir(VOLTA, str(e), request)
    return ir(VOLTA, '', request)
