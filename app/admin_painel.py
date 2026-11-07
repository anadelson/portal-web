"""Painel administrativo: tela "Painel de indicadores" (módulo "bi").
Catálogo com a situação da última coleta, ativar/ocultar, ordem, meta, texto explicativo, destaque na página inicial,
lançamento manual (com motivo, histórico e auditoria) para indicadores sem fonte automática e botão "coletar agora"."""
import re
from datetime import date, datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from . import db, painel as P
from .web import ler_form, ir, exige, auditar
from .admin import T

r = APIRouter(prefix='/_a')

# Classe "transp" (transparência obrigatória): continua no ar no período eleitoral, por isso o texto precisa ser neutro.
TOM_PROPAGANDA = re.compile(r'prefeit[oa]|vice-prefeit|secret[áa]ri[oa]s? municipa|graças|recorde|melhor|conquist|orgulho|compromisso|!', re.I)
CPF = re.compile(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}')

def _mods(request, u):
    from .web import modulos_do_orgao
    if not modulos_do_orgao(request.state.orgao).get('bi'):
        raise HTTPException(404, 'O módulo "Painel de indicadores" não está contratado para este órgão.')

def _num(s):
    s = (s or '').strip().replace(' ', '')
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    return float(s)

@r.get('/indicadores')
def lista(request: Request):
    u = exige(request, 'config'); _mods(request, u)
    b = request.state.orgao['banco']
    itens = []
    for ind in P.catalogo(b, so_visiveis=False):
        ult = db.um(b, 'SELECT * FROM indicador_valores WHERE indicador_id=%s ORDER BY data_ref DESC, periodo DESC LIMIT 1', (ind['id'],))
        itens.append(dict(ind, ult=ult, valor=P.exibir(ind, ult) if ult else '', aviso=P.aviso_antigo(ind), tema_nome=P.TEMA_NOME[ind['tema']]))
    fontes = db.todos(db.PLATAFORMA, "SELECT fonte, ativo FROM fontes WHERE orgao_id=%s AND fonte IN ('ibge','cnes','mds','pni','painel') ORDER BY fonte", (request.state.orgao['id'],))
    coletas = db.todos(db.PLATAFORMA, "SELECT * FROM coletas WHERE orgao_slug=%s AND split_part(fonte, ':', 1) IN ('ibge','cnes','mds','pni','painel') ORDER BY id DESC LIMIT 15", (request.state.orgao['slug'],))
    hist = db.todos(b, 'SELECT h.*, i.nome FROM indicador_historico h LEFT JOIN indicadores i ON i.id=h.indicador_id ORDER BY h.id DESC LIMIT 40')
    return T('indicadores', request, u, itens=itens, fontes=fontes, coletas=coletas, hist=hist, max_dest=P.MAX_DESTAQUES)

def coletar_agora(o):
    """Roda as fontes ativas do painel deste órgão (mesma rotina do worker, com registro em `coletas`)."""
    from .worker import rodar
    res = []
    for f in db.todos(db.PLATAFORMA, "SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.ativo AND f.fonte IN ('ibge','cnes','mds','pni','painel') ORDER BY f.fonte", (o['id'],)):
        res += rodar(f, f['fonte'], f['params'])
    return res

@r.post('/indicadores')
async def lista_post(request: Request):
    u = exige(request, 'config'); _mods(request, u)
    f = await ler_form(request)
    o = request.state.orgao
    if f.get('acao') == 'coletar':
        res = await run_in_threadpool(coletar_agora, o)
        ok = sum(1 for x in res if x[1]); falhas = [x for x in res if not x[1]]
        auditar(request, f'Painel de indicadores: coleta manual ({ok} ok, {len(falhas)} com falha)')
        msg = f'Coleta concluída: {ok} etapa(s) sem erro' + (f"; {len(falhas)} com falha ({'; '.join(x[3][:80] for x in falhas)})" if falhas else '') + '.'
        return ir('/admin/indicadores', msg, request)
    return ir('/admin/indicadores', '', request)

@r.get('/indicadores/{iid}')
def editar(request: Request, iid: int):
    u = exige(request, 'config'); _mods(request, u)
    b = request.state.orgao['banco']
    ind = db.um(b, 'SELECT * FROM indicadores WHERE id=%s', (iid,))
    if not ind:
        raise HTTPException(404, 'Indicador não encontrado.')
    serie = list(reversed(P.serie(b, iid)))
    hist = db.todos(b, 'SELECT * FROM indicador_historico WHERE indicador_id=%s ORDER BY id DESC LIMIT 50', (iid,))
    return T('indicador', request, u, i=ind, serie=serie, hist=hist, exibir=P.exibir, faixas=P.FAIXAS_IEGM, tema_nome=P.TEMA_NOME[ind['tema']],
             link=P.link_fonte(ind, request.state.orgao), aviso=P.aviso_antigo(ind))

@r.post('/indicadores/{iid}')
async def editar_post(request: Request, iid: int):
    u = exige(request, 'config'); _mods(request, u)
    f = await ler_form(request)
    b = request.state.orgao['banco']
    ind = db.um(b, 'SELECT * FROM indicadores WHERE id=%s', (iid,))
    if not ind:
        raise HTTPException(404, 'Indicador não encontrado.')
    volta = f'/admin/indicadores/{iid}'
    acao = f.get('acao')
    if acao == 'config':
        desc = f.get('descricao', '')[:1200]
        if TOM_PROPAGANDA.search(desc) and desc != ind['descricao']:
            return ir(volta, 'Texto explicativo recusado: use linguagem neutra, sem nomes de agentes políticos, adjetivos de promoção ou exclamações (o painel continua no ar no período eleitoral como transparência; Constituição, art. 37, § 1º).', request)
        try:
            meta = _num(f.get('meta'))
            ordem = int(f.get('ordem') or ind['ordem'])
        except ValueError:
            return ir(volta, 'Meta e ordem precisam ser números.', request)
        destaque = f.get('destaque') == '1'
        if destaque and not ind['destaque'] and db.um(b, 'SELECT count(*) n FROM indicadores WHERE destaque AND id<>%s', (iid,))['n'] >= P.MAX_DESTAQUES:
            return ir(volta, f'Já há {P.MAX_DESTAQUES} indicadores em destaque na página inicial. Tire um deles antes.', request)
        meta_bl = f.get('meta_base_legal', '')[:400]
        if meta is not None and not meta_bl:
            return ir(volta, 'Informe a base legal (ou o documento) que define a meta.', request)
        antes = {k: ind[k] for k in ('descricao', 'meta', 'meta_base_legal', 'visivel', 'destaque', 'ordem')}
        depois = {'descricao': desc, 'meta': meta, 'meta_base_legal': meta_bl, 'visivel': f.get('visivel') == '1', 'destaque': destaque, 'ordem': ordem}
        db.exe(b, 'UPDATE indicadores SET descricao=%s, meta=%s, meta_base_legal=%s, visivel=%s, destaque=%s, ordem=%s WHERE id=%s',
               (desc, meta, meta_bl, depois['visivel'], destaque, ordem, iid))
        mud = [k for k in antes if (float(antes[k]) if k == 'meta' and antes[k] is not None else antes[k]) != depois[k]]
        if mud:
            P.historico(b, iid, u['nome'], 'Configuração alterada: ' + ', '.join(mud), {k: antes[k] for k in mud}, {k: depois[k] for k in mud})
            auditar(request, f"Painel de indicadores: {ind['nome']} — alterado ({', '.join(mud)})")
        return ir(volta, 'Indicador atualizado.' if mud else 'Nada mudou.', request)
    if acao == 'lancar':
        if ind['modo'] != 'manual':
            return ir(volta, 'Este indicador tem fonte automática: o valor vem do coletor.', request)
        periodo = f.get('periodo', '').strip()[:40]
        motivo = f.get('motivo', '').strip()
        nota = f.get('nota', '').strip()[:300]
        try:
            data_ref = date.fromisoformat(f.get('data_ref', ''))
        except ValueError:
            return ir(volta, 'Informe a data de referência (fim do período).', request)
        if not periodo or len(motivo) < 10:
            return ir(volta, 'Informe o período e o motivo do lançamento (pelo menos 10 caracteres, com o documento de origem).', request)
        if CPF.search(nota + motivo):
            return ir(volta, 'Não inclua CPF (LGPD).', request)
        if ind['formato'] == 'faixa':
            texto, valor = f.get('texto', ''), None
            if texto not in P.FAIXAS_IEGM:
                return ir(volta, 'Escolha a faixa publicada pelo Tribunal de Contas.', request)
        else:
            texto = ''
            try:
                valor = _num(f.get('valor'))
            except ValueError:
                valor = None
            if valor is None:
                return ir(volta, 'Informe o valor como número (ex.: 215,4).', request)
        antes = db.um(b, 'SELECT periodo, valor, texto, nota, origem, motivo FROM indicador_valores WHERE indicador_id=%s AND periodo=%s', (iid, periodo))
        P.gravar(b, ind['chave'], periodo, data_ref, valor, texto=texto, nota=nota, origem='manual', usuario=u['nome'], motivo=motivo)
        db.exe(b, 'UPDATE indicadores SET ultima_ok=now(), ultima_tentativa=now(), ultima_msg=%s WHERE id=%s', (f"lançamento manual por {u['nome']}", iid))
        P.historico(b, iid, u['nome'], f'Lançamento manual: {periodo} — motivo: {motivo[:200]}', antes, {'periodo': periodo, 'valor': valor, 'texto': texto, 'nota': nota})
        auditar(request, f"Painel de indicadores: lançamento manual em {ind['nome']} ({periodo}) — motivo: {motivo[:150]}")
        return ir(volta, 'Valor lançado e registrado no histórico e na auditoria.', request)
    if acao == 'excluir':
        vid = int(f.get('valor_id') or 0)
        motivo = f.get('motivo', '').strip()
        v = db.um(b, "SELECT * FROM indicador_valores WHERE id=%s AND indicador_id=%s AND origem='manual'", (vid, iid))
        if not v or len(motivo) < 10:
            return ir(volta, 'Para excluir um lançamento manual, informe o motivo (pelo menos 10 caracteres).', request)
        db.exe(b, 'DELETE FROM indicador_valores WHERE id=%s', (vid,))
        P.historico(b, iid, u['nome'], f"Lançamento manual excluído: {v['periodo']} — motivo: {motivo[:200]}", {'periodo': v['periodo'], 'valor': v['valor'], 'texto': v['texto'], 'motivo': v['motivo']}, None)
        auditar(request, f"Painel de indicadores: lançamento de {ind['nome']} ({v['periodo']}) excluído — motivo: {motivo[:150]}")
        return ir(volta, 'Lançamento excluído e registrado.', request)
    return ir(volta, '', request)
