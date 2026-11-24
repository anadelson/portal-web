"""Portal do processo legislativo (Fase 5): proposições, sessões, comissões, contas, transmissões e participação.
Só mostra o que foi publicado; dados pessoais de quem participa nunca aparecem."""
import re
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from . import config, db, legislativo as L
from .web import templates, ctx_orgao, ler_form, ir

r = APIRouter(prefix='/_p')
DOC_OK = re.compile(r'^[0-9a-f]{32}\.pdf$')

def leg(ctx):
    if ctx['orgao']['tipo'] != 'legislativo':
        raise HTTPException(404, 'Esta seção não está disponível neste portal.')
    return ctx['orgao']['banco']

def _proposicoes(b, q):
    w, p = [], []
    if q.get('tipo'): w.append('tipo=%s'); p.append(q['tipo'])
    if (q.get('ano') or '').isdigit(): w.append('ano=%s'); p.append(int(q['ano']))
    if q.get('situacao'): w.append('situacao ILIKE %s'); p.append(q['situacao'][:40] + '%')
    if q.get('autor'): w.append('autor ILIKE %s'); p.append('%' + q['autor'][:80] + '%')
    if q.get('q'): w.append("(tipo || ' ' || numero || '/' || ano || ' ' || ementa || ' ' || autor) ILIKE %s"); p.append('%' + q['q'][:120] + '%')
    return db.todos(b, 'SELECT * FROM proposicoes' + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY ano DESC, tipo, numero DESC LIMIT 500', p)

@r.get('/proposicoes')
def proposicoes(request: Request):
    ctx = ctx_orgao(request); b = leg(ctx)
    q = {k: request.query_params.get(k, '').strip() for k in ('tipo', 'ano', 'situacao', 'autor', 'q')}
    anos = [x['ano'] for x in db.todos(b, 'SELECT DISTINCT ano FROM proposicoes ORDER BY ano DESC')]
    return templates.TemplateResponse(request, 'portal/proposicoes.html', dict(ctx, props=_proposicoes(b, q), f=q, tipos=L.TIPOS, anos=anos,
        situacoes=[x['situacao'] for x in db.todos(b, 'SELECT DISTINCT situacao FROM proposicoes ORDER BY 1')], legal='proposicoes'))

@r.get('/proposicoes/{pid}')
def proposicao(request: Request, pid: int):
    ctx = ctx_orgao(request); b = leg(ctx)
    p = db.um(b, 'SELECT * FROM proposicoes WHERE id=%s', (pid,))
    if not p:
        raise HTTPException(404, 'Proposição não encontrada.')
    votacoes = db.todos(b, """SELECT i.*, s.nome sessao, s.data, s.id sessao_id FROM pauta_itens i JOIN sessoes s ON s.id=i.sessao_id
                              WHERE i.proposicao_id=%s AND s.votacao_publicada AND i.resultado IS NOT NULL ORDER BY s.data""", (pid,))
    for v in votacoes:
        v['votos'] = db.todos(b, 'SELECT vo.voto, ve.nome, ve.id FROM votos vo JOIN vereadores ve ON ve.id=vo.vereador_id WHERE item_id=%s ORDER BY ve.nome', (v['id'],))
        v['cont'] = L.contagem(b, v['id'])
    return templates.TemplateResponse(request, 'portal/proposicao.html', dict(ctx, p=p, rotulo=L.rotulo(p), votos_nome=L.VOTOS, doc_tipos=L.DOC_TIPOS,
        autores=db.todos(b, 'SELECT * FROM proposicao_autores WHERE proposicao_id=%s ORDER BY id', (pid,)),
        tram=db.todos(b, 'SELECT * FROM tramitacao WHERE proposicao_id=%s ORDER BY data, id', (pid,)),
        docs=db.todos(b, 'SELECT * FROM documentos WHERE proposicao_id=%s ORDER BY id', (pid,)),
        pareceres=db.todos(b, 'SELECT pa.*, c.nome comissao FROM pareceres pa JOIN comissoes c ON c.id=pa.comissao_id WHERE proposicao_id=%s AND publicado ORDER BY data', (pid,)),
        votacoes=votacoes, opinioes=db.todos(b, "SELECT posicao, texto, criado_em FROM opinioes WHERE proposicao_id=%s AND situacao='publicada' ORDER BY id DESC LIMIT 50", (pid,)),
        aberta=p['situacao'] in ('Em tramitação', 'Em comissão', 'Pronta para a pauta'), legal='proposicoes'))

@r.post('/proposicoes/{pid}/opiniao')
async def opiniao(request: Request, pid: int):
    ctx = ctx_orgao(request); b = leg(ctx); f = await ler_form(request)
    if f.get('site'):  # campo-armadilha para robôs
        return ir(f'/proposicoes/{pid}', 'Recebido.', request)
    if f.get('posicao') not in ('favor', 'contra', 'sugestao') or len(f.get('texto', '')) < 10:
        return ir(f'/proposicoes/{pid}#opinar', 'Escolha sua posição e escreva pelo menos 10 caracteres.', request)
    p = db.um(b, 'SELECT situacao FROM proposicoes WHERE id=%s', (pid,))
    if not p:
        raise HTTPException(404)
    if p['situacao'] not in ('Em tramitação', 'Em comissão', 'Pronta para a pauta'):
        return ir(f'/proposicoes/{pid}', 'Esta proposição já foi votada ou arquivada e não recebe mais opiniões.', request)
    db.exe(b, 'INSERT INTO opinioes (proposicao_id, posicao, texto) VALUES (%s,%s,%s)', (pid, f['posicao'], f['texto'][:1500]))
    return ir(f'/proposicoes/{pid}#opinar', 'Obrigado! Sua opinião será publicada depois da moderação, sem dados pessoais.', request)

@r.get('/sessoes')
def sessoes(request: Request):
    ctx = ctx_orgao(request); b = leg(ctx)
    return templates.TemplateResponse(request, 'portal/sessoes.html', dict(ctx, sessoes=db.todos(b, 'SELECT s.*, (SELECT count(*) FROM pauta_itens i WHERE i.sessao_id=s.id) n FROM sessoes s ORDER BY data DESC, id DESC'), legal='sessoes'))

@r.get('/sessoes/{sid}')
def sessao(request: Request, sid: int):
    ctx = ctx_orgao(request); b = leg(ctx)
    s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (sid,))
    if not s:
        raise HTTPException(404, 'Sessão não encontrada.')
    itens = db.todos(b, 'SELECT i.*, p.tipo, p.numero, p.ano FROM pauta_itens i LEFT JOIN proposicoes p ON p.id=i.proposicao_id WHERE sessao_id=%s ORDER BY ordem, id', (sid,)) if s['pauta_publicada'] or s['votacao_publicada'] else []
    for it in itens:
        it['cont'] = L.contagem(b, it['id'])
        it['docs'] = L.docs_item(b, it)
        it['votos'] = db.todos(b, 'SELECT vo.voto, ve.nome, ve.id FROM votos vo JOIN vereadores ve ON ve.id=vo.vereador_id WHERE item_id=%s ORDER BY ve.nome', (it['id'],)) if s['votacao_publicada'] else []
    pres = db.todos(b, 'SELECT p.situacao, v.nome, v.id FROM presencas p JOIN vereadores v ON v.id=p.vereador_id WHERE sessao_id=%s ORDER BY v.nome', (sid,)) if s['presenca_publicada'] else []
    t = db.um(b, "SELECT * FROM transmissoes WHERE sessao_id=%s AND video<>'' ORDER BY id DESC LIMIT 1", (sid,))
    return templates.TemplateResponse(request, 'portal/sessao.html', dict(ctx, s=s, itens=itens, pres=pres, transm=t, votos_nome=L.VOTOS, resultados=L.RESULTADOS_ITEM,
        eventos=L.eventos(b, sid) if s['linha_publicada'] else [], videos=L.videos(b, sid), plataformas=L.PLATAFORMAS, tipos_ev=L.EVENTOS, situacoes=L.SITUACOES_SESSAO,
        docs=db.todos(b, "SELECT * FROM documentos WHERE sessao_id=%s AND pauta_item_id IS NULL AND (tipo<>'ata' OR %s)", (sid, s['ata_publicada'])),
        tribuna=s['data'] >= config.hoje() and ctx['mods'].get('sess'), legal='sessoes'))

@r.post('/sessoes/{sid}/tribuna')
async def tribuna(request: Request, sid: int):
    ctx = ctx_orgao(request); b = leg(ctx); f = await ler_form(request)
    s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (sid,))
    if not s or s['data'] < config.hoje():
        return ir(f'/sessoes/{sid}', 'As inscrições para esta sessão estão encerradas.', request)
    if f.get('site'):
        return ir(f'/sessoes/{sid}', 'Recebido.', request)
    if not (f.get('nome') and f.get('contato') and len(f.get('tema', '')) >= 5 and f.get('aceite')):
        return ir(f'/sessoes/{sid}#tribuna', 'Preencha nome, contato e tema e aceite o uso dos dados.', request)
    db.exe(b, 'INSERT INTO tribuna_inscricoes (sessao_id, nome, contato, tema) VALUES (%s,%s,%s,%s)', (sid, f['nome'][:120], f['contato'][:120], f['tema'][:600]))
    return ir(f'/sessoes/{sid}#tribuna', 'Inscrição recebida. A Secretaria vai responder pelo contato informado.', request)

@r.get('/comissoes')
def comissoes(request: Request):
    ctx = ctx_orgao(request); b = leg(ctx)
    cs = db.todos(b, 'SELECT * FROM comissoes ORDER BY ativa DESC, nome')
    for c in cs:
        c['membros'] = db.todos(b, 'SELECT m.cargo, v.nome, v.id FROM comissao_membros m JOIN vereadores v ON v.id=m.vereador_id WHERE comissao_id=%s ORDER BY m.cargo, v.nome', (c['id'],))
        c['reunioes'] = db.todos(b, 'SELECT * FROM comissao_reunioes WHERE comissao_id=%s AND publicada ORDER BY data DESC LIMIT 10', (c['id'],))
        c['pareceres'] = db.todos(b, 'SELECT pa.*, p.id pid, p.tipo, p.numero, p.ano, d.arquivo FROM pareceres pa LEFT JOIN proposicoes p ON p.id=pa.proposicao_id LEFT JOIN documentos d ON d.id=pa.documento_id WHERE pa.comissao_id=%s AND pa.publicado ORDER BY pa.data DESC LIMIT 20', (c['id'],))
    return templates.TemplateResponse(request, 'portal/comissoes.html', dict(ctx, comissoes=cs, legal='comissoes'))

@r.get('/contas')
def contas(request: Request):
    ctx = ctx_orgao(request); b = leg(ctx)
    cs = db.todos(b, 'SELECT c.*, i.resultado item_resultado, i.id item_id, s.nome sessao, s.id sessao_id, s.votacao_publicada FROM contas_julgamento c LEFT JOIN pauta_itens i ON i.id=c.pauta_item_id LEFT JOIN sessoes s ON s.id=i.sessao_id WHERE c.publicado ORDER BY exercicio DESC')
    for c in cs:
        c['docs'] = db.todos(b, 'SELECT * FROM documentos WHERE contas_id=%s ORDER BY id', (c['id'],))
        c['cont'] = L.contagem(b, c['item_id']) if c['item_id'] and c['votacao_publicada'] else None
    return templates.TemplateResponse(request, 'portal/contas.html', dict(ctx, contas=cs, doc_tipos=L.DOC_TIPOS, legal='contas'))

@r.get('/transmissoes')
def transmissoes(request: Request):
    ctx = ctx_orgao(request); b = ctx['orgao']['banco']
    if not (ctx['mods'].get('transm') or ctx['mods'].get('audiencias')):
        raise HTTPException(404, 'Esta seção não está disponível neste portal.')
    vivo = db.um(b, 'SELECT * FROM transmissoes WHERE ao_vivo ORDER BY iniciada_em DESC LIMIT 1')
    agenda = db.todos(b, 'SELECT * FROM transmissoes WHERE NOT ao_vivo AND encerrada_em IS NULL AND previsto_para >= now() ORDER BY previsto_para LIMIT 10')
    grav = db.todos(b, "SELECT t.*, s.nome sessao FROM transmissoes t LEFT JOIN sessoes s ON s.id=t.sessao_id WHERE encerrada_em IS NOT NULL AND video<>'' ORDER BY encerrada_em DESC LIMIT 30")
    sem_transm = db.todos(b, "SELECT s.* FROM sessoes s WHERE video_url<>'' AND NOT EXISTS (SELECT 1 FROM transmissoes t WHERE t.sessao_id=s.id) ORDER BY data DESC LIMIT 30") if ctx['orgao']['tipo'] == 'legislativo' else []
    v = request.query_params.get('v')
    sel = db.um(b, 'SELECT t.*, s.nome sessao FROM transmissoes t LEFT JOIN sessoes s ON s.id=t.sessao_id WHERE t.id=%s', (int(v),)) if v and v.isdigit() else None
    return templates.TemplateResponse(request, 'portal/transmissoes.html', dict(ctx, vivo=vivo, agenda=agenda, grav=grav, sel=sel or vivo or (grav[0] if grav else None),
        sessoes_video=sem_transm, conf=db.cfg(b, 'transmissao', {}) or {}, legal='transmissoes'))

@r.get('/documento/{arquivo}')
def documento(request: Request, arquivo: str):
    if not DOC_OK.match(arquivo):
        raise HTTPException(404)
    o = request.state.orgao
    d = db.um(o['banco'], 'SELECT * FROM documentos WHERE arquivo=%s', (arquivo,))
    f = Path(config.DADOS_DIR) / o['slug'] / 'docs' / arquivo
    if not d or not f.is_file():
        raise HTTPException(404)
    if d['sessao_id'] and d['tipo'] == 'ata' and not db.um(o['banco'], 'SELECT ata_publicada FROM sessoes WHERE id=%s', (d['sessao_id'],))['ata_publicada'] and not request.session.get('u'):
        raise HTTPException(404)
    if d.get('pauta_item_id') and not d['proposicao_id'] and not request.session.get('u'):  # PDF só do item: aparece com a pauta publicada
        s = db.um(o['banco'], 'SELECT s.pauta_publicada, s.votacao_publicada FROM pauta_itens i JOIN sessoes s ON s.id=i.sessao_id WHERE i.id=%s', (d['pauta_item_id'],))
        if not s or not (s['pauta_publicada'] or s['votacao_publicada']):
            raise HTTPException(404)
    nome = re.sub(r'[^\w.-]+', '-', d['titulo'])[:80] + '.pdf'
    return FileResponse(f, media_type='application/pdf', filename=nome, headers={'X-Content-Type-Options': 'nosniff'})

@r.post('/avaliar')
async def avaliar(request: Request):
    """Grava a avaliação e responde perto do formulário (JSON para o envio por JS; senão volta à página com a mensagem no formulário)."""
    from fastapi.responses import JSONResponse
    from . import avaliacao as AV
    ctx = ctx_orgao(request); f = await ler_form(request); b = ctx['orgao']['banco']
    pagina = (f.get('pagina') or '/')[:200]
    js = 'application/json' in request.headers.get('accept', '')
    def resp(msg, ok, gravar=False, cod=200):
        r = JSONResponse({'ok': ok, 'msg': msg}, status_code=cod) if js else ir(pagina + '#avaliar', '', request)
        if not js:
            request.session['msg_aval'] = msg
        if gravar:
            AV.gravar_cookie(r, request, b, pagina)
        return r
    if not pagina.startswith('/') or pagina.startswith('//') or '\\' in pagina or f.get('util') not in ('sim', 'nao') or f.get('site'):
        return resp('Não foi possível registrar a avaliação.', False, cod=400)
    antes = AV.avaliada_em(request, b, pagina)
    if antes:
        return resp(f"Você já avaliou esta página em {antes.strftime('%d/%m/%Y')}. Poderá avaliar de novo a partir de {AV.proxima(b, antes).strftime('%d/%m/%Y')}.", False)
    h = AV.ip_hash(request)
    if AV.excedeu(b, h):
        return resp('Muitas avaliações a partir desta conexão na última hora. Tente de novo mais tarde.', False, cod=429)
    coment = f.get('comentario', '')[:600]
    if L.problemas_texto(coment) and 'dado pessoal' in ' '.join(L.problemas_texto(coment)):
        coment = '[comentário removido: continha dado pessoal]'
    db.exe(b, 'INSERT INTO avaliacoes (pagina, util, comentario, ip_hash) VALUES (%s,%s,%s,%s)', (pagina, f['util'] == 'sim', coment, h))
    prox = AV.proxima(b, AV.config.hoje()).strftime('%d/%m/%Y')
    return resp(f'Obrigado! Sua avaliação desta página foi registrada. Você poderá avaliar esta página de novo a partir de {prox}.', True, gravar=True)
