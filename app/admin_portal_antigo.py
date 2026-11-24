"""Painel › Dados antigos › Portal antigo (24/11/2026): cadastro da busca, acompanhamento e revisão do que foi encontrado.
O endereço do portal antigo é informado só aqui, no painel do órgão; a varredura roda no worker (ver app/portal_antigo.py)."""
import re
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from . import config, db, orgaos, portal_antigo as PA
from .admin import T
from .catalogo import PODE
from .web import ler_form, ir, exige, auditar

r = APIRouter(prefix='/_a')
POR_PAGINA = 40
SIT = {'aguardando': 'Aguardando o início', 'rodando': 'Em andamento', 'pausada': 'Pausada', 'concluida': 'Concluída', 'erro': 'Parou com erro'}
ARQ_TIPOS = {'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp', 'gif': 'image/gif', 'pdf': 'application/pdf',
             'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
             'odt': 'application/vnd.oasis.opendocument.text', 'ods': 'application/vnd.oasis.opendocument.spreadsheet', 'csv': 'text/csv'}

def _d(s):
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        raise ValueError('Data inválida no período.')

def _proprios(o):
    return [o['dominio'], config.DOMINIO_GESTAO] + [x.get('dominio') for x in orgaos.todos(ativos=False)]

@r.get('/importar/portal')
def lista(request: Request):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    buscas = db.todos(b, """SELECT v.*, (SELECT count(*) FROM migracao_itens i WHERE i.varredura_id=v.id AND i.situacao='novo') a_revisar,
                                 (SELECT count(*) FROM migracao_itens i WHERE i.varredura_id=v.id AND i.situacao='migrado') migrados
                            FROM migracao_varreduras v ORDER BY id DESC""")
    cfg = dict(PA.PADRAO, **(db.cfg(b, 'portal_antigo', {}) or {}))
    return T('portal_antigo', request, u, buscas=buscas, assuntos=PA.ASSUNTOS, sit=SIT, cfg=cfg, pode_criar=u['perfil'] in PODE['config'])

@r.post('/importar/portal')
async def lista_post(request: Request):
    u = exige(request, 'config'); o = request.state.orgao; b = o['banco']; f = await ler_form(request)
    acao = f.get('acao')
    try:
        if acao == 'nova':
            if f.get('declaro') != '1':
                raise ValueError('Confirme que o portal antigo é deste órgão e que o conteúdo pode ser migrado.')
            url, host = PA.validar_endereco(f.get('url', ''), _proprios(o))
            assunto = f.get('assunto') if f.get('assunto') in PA.ASSUNTOS else 'tudo'
            if assunto in ('sessoes', 'proposicoes') and o['tipo'] != 'legislativo':
                assunto = 'documentos' if assunto == 'proposicoes' else 'tudo'
            cfg = dict(PA.PADRAO, **(db.cfg(b, 'portal_antigo', {}) or {}))
            lim = int(f['limite']) if (f.get('limite') or '').isdigit() else 300
            lim = max(10, min(lim, int(cfg['paginas_max'])))
            desde, ate = _d(f.get('desde')), _d(f.get('ate'))
            if desde and ate and desde > ate:
                raise ValueError('No período, a data inicial vem antes da final.')
            if db.um(b, "SELECT 1 FROM migracao_varreduras WHERE situacao IN ('aguardando','rodando')"):
                raise ValueError('Já existe uma busca em andamento. Espere terminar ou pause a busca atual.')
            palavras = re.sub(r'\s+', ' ', f.get('palavras', '')).strip()[:300]
            vid = db.exe(b, 'INSERT INTO migracao_varreduras (url_inicial, dominio, assunto, palavras, desde, ate, limite_paginas, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                         (url, host, assunto, palavras, desde, ate, lim, u['nome']))['id']
            auditar(request, f'Portal antigo: nova busca nº {vid} ({PA.ASSUNTOS[assunto]}, até {lim} páginas)')
            return ir(f'/admin/importar/portal/{vid}', 'Busca cadastrada. Ela começa em até 1 minuto e anda devagar (1 página por segundo) para não sobrecarregar o portal antigo.', request)
        vid = int(f.get('busca') or 0)
        v = db.um(b, 'SELECT * FROM migracao_varreduras WHERE id=%s', (vid,))
        if not v:
            raise ValueError('Busca não encontrada.')
        if acao == 'pausar' and v['situacao'] in ('aguardando', 'rodando'):
            db.exe(b, "UPDATE migracao_varreduras SET situacao='pausada', msg='Pausada por ' || %s WHERE id=%s", (u['nome'], vid)); msg = 'Busca pausada.'
        elif acao == 'retomar' and v['situacao'] in ('pausada', 'erro'):
            if db.um(b, "SELECT 1 FROM migracao_varreduras WHERE situacao IN ('aguardando','rodando') AND id<>%s", (vid,)):
                raise ValueError('Já existe outra busca em andamento.')
            db.exe(b, "UPDATE migracao_varreduras SET situacao=CASE WHEN robots IS NULL THEN 'aguardando' ELSE 'rodando' END, msg='' WHERE id=%s", (vid,)); msg = 'Busca retomada.'
        elif acao == 'apagar':
            PA.apagar(o, vid); auditar(request, f'Portal antigo: busca nº {vid} apagada')
            return ir('/admin/importar/portal', 'Busca apagada, com os arquivos da área de revisão. O que já foi migrado continua nas seções.', request)
        else:
            raise ValueError('Ação inválida para a situação da busca.')
        auditar(request, f'Portal antigo: busca nº {vid}: {acao}')
        return ir(f'/admin/importar/portal/{vid}', msg, request)
    except ValueError as e:
        return ir('/admin/importar/portal' + (f"/{f.get('busca')}" if f.get('busca', '').isdigit() else ''), str(e), request)

@r.get('/importar/portal/{vid}')
def busca(request: Request, vid: int, sit: str = 'novo', tipo: str = '', p: int = 1):
    u = exige(request, 'editar'); o = request.state.orgao; b = o['banco']
    v = db.um(b, 'SELECT * FROM migracao_varreduras WHERE id=%s', (vid,))
    if not v:
        raise HTTPException(404)
    sit = sit if sit in ('novo', 'migrado', 'descartado') else 'novo'
    filtro, par = 'varredura_id=%s AND situacao=%s', [vid, sit]
    if tipo in ('pagina', 'arquivo'):
        filtro += ' AND tipo=%s'; par.append(tipo)
    n = db.um(b, f'SELECT count(*) n FROM migracao_itens WHERE {filtro}', par)['n']
    p = max(1, min(p, (n + POR_PAGINA - 1) // POR_PAGINA or 1))
    itens = db.todos(b, f'SELECT * FROM migracao_itens WHERE {filtro} ORDER BY data_original DESC NULLS LAST, id LIMIT %s OFFSET %s', par + [POR_PAGINA, (p - 1) * POR_PAGINA])
    for it in itens:
        it['fotos'] = [a for a, _ in PA._fotos_validas(b, it)]
        it['arq'] = db.um(b, 'SELECT * FROM migracao_arquivos WHERE id=%s', (it['arquivo_id'],)) if it['arquivo_id'] else None
        it['trecho'] = (it['texto'] or '')[:420]
    contas = db.um(b, """SELECT count(*) FILTER (WHERE situacao='novo') novo, count(*) FILTER (WHERE situacao='migrado') migrado, count(*) FILTER (WHERE situacao='descartado') descartado,
                                count(*) FILTER (WHERE situacao='novo' AND tipo='pagina') paginas, count(*) FILTER (WHERE situacao='novo' AND tipo='arquivo') arquivos
                         FROM migracao_itens WHERE varredura_id=%s""", (vid,))
    fila = db.um(b, """SELECT count(*) FILTER (WHERE situacao='pendente') pendente, count(*) FILTER (WHERE situacao='lida') lida, count(*) FILTER (WHERE situacao='ignorada') ignorada,
                              count(*) FILTER (WHERE situacao='erro') erro FROM migracao_fila WHERE varredura_id=%s""", (vid,))
    motivos = db.todos(b, "SELECT motivo, count(*) n FROM migracao_fila WHERE varredura_id=%s AND situacao IN ('ignorada','erro') GROUP BY motivo ORDER BY n DESC LIMIT 8", (vid,))
    leg = o['tipo'] == 'legislativo'
    return T('portal_antigo_busca', request, u, v=v, itens=itens, n=n, p=p, paginas=(n + POR_PAGINA - 1) // POR_PAGINA, sit_f=sit, tipo_f=tipo, contas=contas, fila=fila, motivos=motivos,
             sit=SIT, assuntos=PA.ASSUNTOS, destinos={k: t for k, t in PA.DESTINOS.items() if leg or k not in PA.SO_LEGISLATIVO},
             dest_pagina=PA.DESTINOS_PAGINA, dest_arquivo=[d for d in PA.DESTINOS_ARQUIVO if leg or d not in PA.SO_LEGISLATIVO],
             sessoes=db.todos(b, 'SELECT id, nome, data FROM sessoes ORDER BY data DESC LIMIT 400') if leg else [],
             props=db.todos(b, 'SELECT id, tipo, numero, ano, ementa FROM proposicoes ORDER BY ano DESC, tipo, numero DESC LIMIT 600') if leg else [],
             pode_config=u['perfil'] in PODE['config'])

@r.post('/importar/portal/{vid}')
async def busca_post(request: Request, vid: int):
    u = exige(request, 'editar'); o = request.state.orgao; b = o['banco']; f = await ler_form(request)
    acao = f.get('acao'); volta = f"/admin/importar/portal/{vid}?sit={f.get('sit_f') or 'novo'}&tipo={f.get('tipo_f') or ''}&p={f.get('p') or 1}"
    if not db.um(b, 'SELECT 1 FROM migracao_varreduras WHERE id=%s', (vid,)):
        raise HTTPException(404)
    def do_item(i):
        it = db.um(b, 'SELECT * FROM migracao_itens WHERE id=%s AND varredura_id=%s', (i, vid))
        if not it:
            raise ValueError('Item não encontrado.')
        return it
    try:
        if acao == 'migrar':
            it = do_item(int(f['item']))
            destino = f.get(f"destino_{it['id']}") or f.get('destino')
            alvo_txt = f.get(f"alvo_{destino}_{it['id']}") or ''
            msg = PA.migrar(o, it['id'], destino, int(alvo_txt) if alvo_txt.isdigit() else None, u['nome'])
            auditar(request, f"Portal antigo: item {it['id']} migrado para {PA.DESTINOS[destino]}")
        elif acao == 'descartar':
            it = do_item(int(f['item']))
            db.exe(b, "UPDATE migracao_itens SET situacao='descartado', migrado_por=%s, migrado_em=now() WHERE id=%s AND situacao='novo'", (u['nome'], it['id'])); msg = 'Item descartado.'
        elif acao == 'restaurar':
            it = do_item(int(f['item']))
            db.exe(b, "UPDATE migracao_itens SET situacao='novo' WHERE id=%s AND situacao='descartado'", (it['id'],)); msg = 'Item voltou para a revisão.'
        elif acao in ('migrar_sugeridos', 'descartar_marcados'):
            ids = [int(x) for x in (await request.form()).getlist('sel') if str(x).isdigit()]
            if not ids:
                raise ValueError('Marque pelo menos um item.')
            ok, falhas = 0, []
            for i in ids[:POR_PAGINA]:
                it = do_item(i)
                if it['situacao'] != 'novo':
                    continue
                if acao == 'descartar_marcados':
                    db.exe(b, "UPDATE migracao_itens SET situacao='descartado', migrado_por=%s, migrado_em=now() WHERE id=%s", (u['nome'], i)); ok += 1; continue
                s = it['sugestao'] or {}
                try:
                    PA.migrar(o, i, s.get('destino'), s.get('alvo'), u['nome']); ok += 1
                except ValueError as e:
                    falhas.append(f"“{it['titulo'][:50]}”: {e}")
            auditar(request, f"Portal antigo: {ok} item(ns) {'descartado(s)' if acao == 'descartar_marcados' else 'migrado(s) com o destino sugerido'}")
            msg = f"{ok} item(ns) {'descartado(s)' if acao == 'descartar_marcados' else 'migrado(s) para o destino sugerido, como rascunho'}." + (' Não migrados: ' + '; '.join(falhas)[:400] if falhas else '')
        else:
            raise ValueError('Ação inválida.')
    except ValueError as e:
        return ir(volta, str(e), request)
    return ir(volta, msg, request)

@r.get('/importar/portal/{vid}/arquivo/{aid}')
def arquivo(request: Request, vid: int, aid: int):
    """Prévia do arquivo da área de revisão: só para quem está no painel; nunca como página (HTML) do portal antigo."""
    exige(request, 'editar'); o = request.state.orgao
    a = db.um(o['banco'], 'SELECT * FROM migracao_arquivos WHERE id=%s AND varredura_id=%s AND arquivo IS NOT NULL', (aid, vid))
    if not a or a['ext'] not in ARQ_TIPOS or not re.fullmatch(r'[0-9a-f]{32}\.[a-z]{3,4}', a['arquivo']):
        raise HTTPException(404)
    f = PA.pasta(o, vid) / a['arquivo']
    if not f.is_file():
        raise HTTPException(404)
    img = a['ext'] in ('png', 'jpg', 'webp', 'gif')
    return FileResponse(f, media_type=ARQ_TIPOS[a['ext']], filename=None if img else f"documento-{aid}.{a['ext']}",
                        content_disposition_type='inline' if img or a['ext'] == 'pdf' else 'attachment',
                        headers={'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox", 'Cache-Control': 'private, max-age=3600'})
