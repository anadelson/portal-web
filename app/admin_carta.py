"""Painel — Carta de Serviços (Fase 10): fichas, validação por secretaria, publicação pelo DTIC, secretarias e designações,
monitoramento e importação do inventário. As regras de publicação estão em carta.py."""
import re
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from . import config, db, carta as CT
from .catalogo import PODE
from .web import ler_form, ir, exige, auditar
from .admin import T

r = APIRouter(prefix='/_a')
ABAS = [('minhas', 'Rascunhos e devolvidas'), ('validacao', 'Em validação'), ('autorizadas', 'Autorizadas'), ('publicadas', 'Publicadas'), ('revisar', 'A revisar'), ('todas', 'Todas')]

def _escopo(u):
    """Redator e validador veem só a própria secretaria."""
    return u.get('secretaria_id') if u['perfil'] in ('redator', 'validador') else None

def _usuario(request):
    u = exige(request, 'carta_ver')
    x = db.um(request.state.orgao['banco'], 'SELECT secretaria_id FROM usuarios WHERE id=%s', (u['id'],))
    return dict(u, secretaria_id=x['secretaria_id'] if x else None)

@r.get('/carta')
def lista(request: Request, aba: str = 'minhas'):
    u = _usuario(request); b = request.state.orgao['banco']
    esc = _escopo(u)
    cond = {'minhas': "s.situacao IN ('rascunho','devolvido')", 'validacao': "s.situacao='em_validacao'", 'autorizadas': "s.situacao='autorizado'",
            'publicadas': "s.publicado_dados IS NOT NULL AND s.situacao<>'arquivado'", 'revisar': 's.revisar_em < %(hoje)s', 'todas': 'TRUE'}.get(aba, 'TRUE')
    sql = f"SELECT s.*, sec.nome secretaria FROM servicos s LEFT JOIN secretarias sec ON sec.id=s.secretaria_id WHERE {cond}" + (' AND s.secretaria_id=%(esc)s' if esc else '') + ' ORDER BY s.atualizado_em DESC'
    itens = db.todos(b, sql, {'hoje': config.hoje(), 'esc': esc})
    cont = {k: db.um(b, f"SELECT count(*) n FROM servicos s WHERE {c}" + (' AND s.secretaria_id=%(esc)s' if esc else ''), {'hoje': config.hoje(), 'esc': esc})['n']
            for k, c in [('validacao', "s.situacao='em_validacao'"), ('autorizadas', "s.situacao='autorizado'"), ('revisar', 's.revisar_em < %(hoje)s')]}
    sem_sec = u['perfil'] in ('redator', 'validador') and not u.get('secretaria_id')
    return T('carta', request, u, itens=itens, aba=aba if aba in dict(ABAS) else 'minhas', abas=ABAS, cont=cont, situacoes=CT.SITUACOES, sem_sec=sem_sec,
             vencidas=CT.vencidas(b, esc), tem_secretarias=bool(db.um(b, 'SELECT 1 FROM secretarias LIMIT 1')))

def _secretarias(b):
    return db.todos(b, 'SELECT * FROM secretarias WHERE ativa ORDER BY nome')

def _categorias(b):
    return (db.cfg(b, 'carta', {}) or {}).get('categorias') or CT.CATEGORIAS_PADRAO

@r.get('/carta/novo')
def novo(request: Request):
    u = exige(request, 'carta_redigir'); u = _usuario(request); b = request.state.orgao['banco']
    return T('carta_ficha', request, u, s=None, campos=CT.CAMPOS, secretarias=_secretarias(b), categorias=_categorias(b), publicos=CT.PUBLICOS, formas=CT.FORMAS,
             faltam=[], avisos=[], versoes=[], validar=(False, ''), situacoes=CT.SITUACOES, aval=None)

@r.get('/carta/{sid}')
def ver(request: Request, sid: int):
    u = _usuario(request); b = request.state.orgao['banco']
    s = db.um(b, 'SELECT * FROM servicos WHERE id=%s', (sid,))
    if not s or (_escopo(u) and s['secretaria_id'] != _escopo(u)):
        raise HTTPException(404)
    textos = ' '.join(str(s.get(k) or '') for k in ('descricao', 'requisitos', 'documentos', 'etapas', 'prioridades', 'comunicacao', 'manifestacoes', 'acompanhamento'))
    return T('carta_ficha', request, u, s=s, campos=CT.CAMPOS, secretarias=_secretarias(b), categorias=_categorias(b), publicos=CT.PUBLICOS, formas=CT.FORMAS,
             faltam=CT.faltando(s), avisos=CT.avisos_linguagem(textos), situacoes=CT.SITUACOES,
             versoes=db.todos(b, 'SELECT id, situacao, quem, comentario, quando FROM servico_versoes WHERE servico_id=%s ORDER BY id DESC LIMIT 30', (sid,)),
             validar=CT.pode_validar(b, u, s) if u['perfil'] in ('validador', 'admin') else (False, ''), aval=CT.avaliacao_resumo(b, sid),
             mudou_desde_autorizacao=bool(s['autorizado_hash']) and CT.resumo_conteudo(s) != s['autorizado_hash'])

def _ler_ficha(form):
    d = {}
    for k in CT.CAMPOS:
        if k in ('publicos', 'formas'):
            d[k] = [x for x in form.getlist(k) if x in (CT.PUBLICOS if k == 'publicos' else CT.FORMAS)]
        elif k == 'secretaria_id':
            v = form.get(k, ''); d[k] = int(v) if str(v).isdigit() else None
        else:
            d[k] = (form.get(k) or '').strip()[:8000]
    return d

@r.post('/carta/salvar')
async def salvar(request: Request):
    u = _usuario(request); b = request.state.orgao['banco']
    form = await request.form()
    if form.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    acao = form.get('acao', ''); sid = int(form['id']) if str(form.get('id', '')).isdigit() else None
    s = db.um(b, 'SELECT * FROM servicos WHERE id=%s', (sid,)) if sid else None
    esc = _escopo(u)
    if s and esc and s['secretaria_id'] != esc:
        raise HTTPException(403)
    volta = f'/admin/carta/{sid}' if sid else '/admin/carta/novo'

    if acao in ('rascunho', 'enviar'):
        if u['perfil'] not in PODE['carta_redigir']:
            raise HTTPException(403)
        d = _ler_ficha(form)
        if esc:
            d['secretaria_id'] = esc  # redator/validador só cadastram na própria secretaria
        if not d['nome']:
            return ir(volta, 'Informe o nome do serviço.', request)
        if d['link_online'] and not d['link_online'].startswith('https://'):
            return ir(volta, 'O link “Solicitar online” precisa começar com https://.', request)
        if re.search(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', ' '.join(str(v) for v in d.values())):
            return ir(volta, 'A ficha tem um número com formato de CPF. Retire (LGPD).', request)
        if s and s['situacao'] in ('em_validacao',) and u['perfil'] not in ('validador', 'admin'):
            return ir(volta, 'A ficha está em validação: aguarde a decisão do responsável.', request)
        cols = list(CT.CAMPOS)
        if s:
            db.exe(b, f"UPDATE servicos SET {', '.join(c + '=%s' for c in cols)}, atualizado_em=now() WHERE id=%s", tuple(d[c] for c in cols) + (sid,))
        else:
            sl, k = CT.slug(d['nome']), 2
            while db.um(b, 'SELECT 1 FROM servicos WHERE slug=%s', (sl,)):
                sl = f"{CT.slug(d['nome'])}-{k}"; k += 1
            sid = db.exe(b, f"INSERT INTO servicos (slug, criado_por, {', '.join(cols)}) VALUES (%s,%s,{', '.join(['%s'] * len(cols))}) RETURNING id", (sl, u['nome']) + tuple(d[c] for c in cols))['id']
        s = db.um(b, 'SELECT * FROM servicos WHERE id=%s', (sid,))
        # mudou o conteúdo de uma ficha autorizada ou no ar: a versão de trabalho volta a rascunho (o que está no ar não muda)
        if s['situacao'] in ('autorizado', 'publicado') and CT.resumo_conteudo(s) != s['autorizado_hash']:
            db.exe(b, "UPDATE servicos SET situacao='rascunho' WHERE id=%s", (sid,)); s['situacao'] = 'rascunho'
        if acao == 'enviar':
            falta = CT.faltando(s)
            if falta:
                CT.versao(b, sid, s['situacao'], u['nome'], 'Salvou')
                return ir(f'/admin/carta/{sid}', 'Salvo, mas não enviado: faltam campos obrigatórios (art. 7º): ' + '; '.join(falta) + '.', request)
            if s['situacao'] not in ('rascunho', 'devolvido'):
                return ir(f'/admin/carta/{sid}', 'Esta ficha não está em rascunho.', request)
            db.exe(b, "UPDATE servicos SET situacao='em_validacao', comentario='' WHERE id=%s", (sid,))
            CT.versao(b, sid, 'em_validacao', u['nome'], 'Enviou para validação')
            auditar(request, f"Carta: “{s['nome']}” enviada para validação")
            return ir('/admin/carta?aba=minhas', 'Ficha enviada para validação do responsável da secretaria.', request)
        CT.versao(b, sid, s['situacao'], u['nome'], 'Salvou')
        auditar(request, f"Carta: “{s['nome']}” salva ({s['situacao']})")
        return ir(f'/admin/carta/{sid}', 'Ficha salva.', request)

    if not s:
        raise HTTPException(400)
    if acao in ('autorizar', 'devolver'):
        if s['situacao'] != 'em_validacao':
            return ir(volta, 'Só fichas em validação podem ser autorizadas ou devolvidas.', request)
        ok, ato = CT.pode_validar(b, u, s)
        if not ok:
            return ir(volta, 'Só o responsável pela secretaria ou o servidor designado por ato vigente pode validar esta ficha.', request)
        if acao == 'devolver':
            com = (form.get('comentario') or '').strip()[:1000]
            if len(com) < 5:
                return ir(volta, 'Para devolver, escreva o comentário para o redator.', request)
            db.exe(b, "UPDATE servicos SET situacao='devolvido', comentario=%s WHERE id=%s", (com, sid))
            CT.versao(b, sid, 'devolvido', u['nome'], com)
            auditar(request, f"Carta: “{s['nome']}” devolvida ao redator")
            return ir('/admin/carta?aba=validacao', 'Ficha devolvida com o comentário.', request)
        if CT.faltando(s):
            return ir(volta, 'A ficha tem campo obrigatório vazio; devolva ao redator.', request)
        db.exe(b, "UPDATE servicos SET situacao='autorizado', autorizado_por=%s, autorizado_em=now(), autorizado_ato=%s, autorizado_hash=%s, comentario='' WHERE id=%s",
               (u['nome'], ato, CT.resumo_conteudo(s), sid))
        CT.versao(b, sid, 'autorizado', u['nome'], f'Autorizou ({ato})')
        auditar(request, f"Carta: “{s['nome']}” AUTORIZADA por {u['nome']} ({ato})")
        return ir('/admin/carta?aba=validacao', 'Ficha autorizada. O DTIC pode organizar e publicar.', request)

    if acao in ('publicar', 'organizar', 'arquivar'):
        exige(request, 'carta_publicar')
        if acao == 'organizar':  # DTIC: só categoria, sinônimos e ordem (não muda o que foi autorizado)
            cat = (form.get('categoria') or '').strip()[:80]
            if cat not in _categorias(b):
                return ir(volta, 'Escolha uma categoria da lista.', request)
            db.exe(b, 'UPDATE servicos SET categoria=%s, sinonimos=%s, ordem=%s WHERE id=%s',
                   (cat, (form.get('sinonimos') or '').strip()[:600], int(form.get('ordem') or 100) if str(form.get('ordem') or '').isdigit() else 100, sid))
            if s['publicado_dados']:
                db.exe(b, "UPDATE servicos SET publicado_dados = publicado_dados || jsonb_build_object('categoria', %s::text, 'sinonimos', %s::text) WHERE id=%s",
                       (cat, (form.get('sinonimos') or '').strip()[:600], sid))
            auditar(request, f"Carta: “{s['nome']}” organizada (categoria/sinônimos)")
            return ir(volta, 'Categoria e sinônimos salvos.', request)
        if acao == 'arquivar':
            db.exe(b, "UPDATE servicos SET situacao='arquivado' WHERE id=%s", (sid,))
            CT.versao(b, sid, 'arquivado', u['nome'], (form.get('comentario') or 'Arquivou')[:500])
            auditar(request, f"Carta: “{s['nome']}” arquivada (saiu do portal)")
            return ir('/admin/carta?aba=todas', 'Ficha arquivada: saiu do portal.', request)
        try:
            CT.publicar(b, s, u['nome'])
        except ValueError as e:
            auditar(request, f"Carta: publicação RECUSADA de “{s['nome']}”: {e}")
            return ir(volta, f'Não publicado: {e}', request)
        CT.versao(b, sid, 'publicado', u['nome'], f"Publicou (autorizado por {s['autorizado_por']})")
        auditar(request, f"Carta: “{s['nome']}” publicada (autorizada por {s['autorizado_por']})")
        return ir('/admin/carta?aba=publicadas', 'Ficha publicada na Carta de Serviços.', request)
    raise HTTPException(400)

# ---------- secretarias, responsáveis, designações e redatores ----------
@r.get('/carta-secretarias')
def secretarias(request: Request):
    u = exige(request, 'carta_ver'); b = request.state.orgao['banco']
    secs = db.todos(b, 'SELECT s.*, u.nome responsavel FROM secretarias s LEFT JOIN usuarios u ON u.id=s.responsavel_id ORDER BY s.nome')
    for x in secs:
        x['designacoes'] = db.todos(b, 'SELECT d.*, u.nome FROM designacoes_carta d JOIN usuarios u ON u.id=d.usuario_id WHERE d.secretaria_id=%s ORDER BY d.id DESC', (x['id'],))
        x['membros'] = db.todos(b, "SELECT id, nome, perfil FROM usuarios WHERE secretaria_id=%s ORDER BY nome", (x['id'],))
    from . import fase8 as F8
    return T('carta_secretarias', request, u, secs=secs, icones=F8.ICONES_EDITORIA, usuarios=db.todos(b, "SELECT id, nome, perfil FROM usuarios WHERE situacao='ativo' ORDER BY nome"),
             unidades=db.todos(b, 'SELECT codigo, unidade FROM areas_unidades ORDER BY codigo') if db.um(b, "SELECT 1 FROM information_schema.tables WHERE table_name='areas_unidades'") else [])

@r.post('/carta-secretarias')
async def secretarias_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    acao = f.get('acao')
    if acao == 'secretaria':
        nome = re.sub(r'\s+', ' ', f.get('nome', '')).strip()[:120]
        if not nome:
            return ir('/admin/carta-secretarias', 'Informe o nome oficial da secretaria.', request)
        resp = int(f['responsavel_id']) if str(f.get('responsavel_id', '')).isdigit() else None
        sid = int(f['id']) if str(f.get('id', '')).isdigit() else None
        from . import fase8 as F8
        icone = f.get('icone') if f.get('icone') in F8.ICONES_EDITORIA else 'predio'
        vals = (nome, f.get('sigla', '').strip()[:20], resp, f.get('unidades', '').strip()[:300], f.get('resumo', '').strip()[:400], icone)
        try:
            if sid:
                db.exe(b, 'UPDATE secretarias SET nome=%s, sigla=%s, responsavel_id=%s, unidades=%s, resumo=%s, icone=%s WHERE id=%s', vals + (sid,))
            else:
                sid = db.exe(b, 'INSERT INTO secretarias (nome, sigla, responsavel_id, unidades, resumo, icone) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id', vals)['id']
        except Exception:
            return ir('/admin/carta-secretarias', 'Já existe uma secretaria com esse nome.', request)
        if resp:  # o responsável passa a ser validador desta secretaria
            db.exe(b, "UPDATE usuarios SET secretaria_id=%s, perfil=CASE WHEN perfil IN ('admin','publicador') THEN perfil ELSE 'validador' END WHERE id=%s", (sid, resp))
        auditar(request, f'Carta: secretaria “{nome}” salva' + (' com responsável' if resp else ''))
        return ir('/admin/carta-secretarias', 'Secretaria salva.', request)
    if acao == 'organograma':  # PDF ou imagem; o botão "Organograma" do /governo só aparece com o arquivo
        import secrets as _s
        from pathlib import Path
        from .imagens import validar_upload
        ident = db.cfg(b, 'identidade', {}) or {}
        if f.get('remover') == '1':
            ident.pop('organograma', None); db.set_cfg(b, 'identidade', ident); auditar(request, 'Governo: organograma removido')
            return ir('/admin/carta-secretarias#organograma', 'Organograma removido.', request)
        arq = f.get('arquivo')
        if arq is None or not getattr(arq, 'filename', ''):
            return ir('/admin/carta-secretarias#organograma', 'Escolha o arquivo do organograma (PDF, PNG, JPG ou WEBP).', request)
        dados = await arq.read(10 * 1024 * 1024 + 1)
        if dados[:5] == b'%PDF-' and len(dados) <= 10 * 1024 * 1024:
            ext = 'pdf'
        else:
            try:
                ext = validar_upload(dados)
            except ValueError as e:
                return ir('/admin/carta-secretarias#organograma', f'Organograma: {e} (ou envie um PDF de até 10 MB).', request)
        o = request.state.orgao
        pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'; pasta.mkdir(parents=True, exist_ok=True)
        nome = f'{_s.token_hex(16)}.{ext}'
        (pasta / nome).write_bytes(dados)
        ident['organograma'] = {'url': f'/midia/{nome}', 'tipo': ext}
        db.set_cfg(b, 'identidade', ident); auditar(request, 'Governo: organograma publicado')
        return ir('/admin/carta-secretarias#organograma', 'Organograma publicado: o botão aparece na página Governo.', request)
    sec = db.um(b, 'SELECT * FROM secretarias WHERE id=%s', (int(f.get('secretaria_id') or 0),))
    if not sec:
        raise HTTPException(400)
    if acao == 'designar':
        uid = int(f.get('usuario_id') or 0)
        try:
            dt = date.fromisoformat(f.get('ato_data', ''))
            ate = date.fromisoformat(f['ate']) if f.get('ate') else None
        except ValueError:
            return ir('/admin/carta-secretarias', 'Data do ato inválida.', request)
        if not (f.get('ato_tipo') and f.get('ato_numero') and uid):
            return ir('/admin/carta-secretarias', 'Informe o servidor e o ato de designação (tipo, número e data).', request)
        db.exe(b, 'INSERT INTO designacoes_carta (secretaria_id, usuario_id, ato_tipo, ato_numero, ato_data, ate, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)',
               (sec['id'], uid, f['ato_tipo'][:40], f['ato_numero'][:40], dt, ate, u['nome']))
        db.exe(b, "UPDATE usuarios SET secretaria_id=%s, perfil=CASE WHEN perfil IN ('admin','publicador') THEN perfil ELSE 'validador' END WHERE id=%s", (sec['id'], uid))
        auditar(request, f"Carta: designação para validar na secretaria “{sec['nome']}” ({f['ato_tipo']} nº {f['ato_numero']})")
        return ir('/admin/carta-secretarias', 'Designação registrada.', request)
    if acao == 'redator':
        uid = int(f.get('usuario_id') or 0)
        db.exe(b, "UPDATE usuarios SET secretaria_id=%s, perfil=CASE WHEN perfil IN ('admin','publicador','validador') THEN perfil ELSE 'redator' END WHERE id=%s", (sec['id'], uid))
        auditar(request, f"Carta: redator vinculado à secretaria “{sec['nome']}”")
        return ir('/admin/carta-secretarias', 'Redator vinculado.', request)
    if acao == 'encerrar':
        db.exe(b, 'UPDATE designacoes_carta SET ate=%s WHERE id=%s AND secretaria_id=%s', (config.hoje(), int(f.get('designacao_id') or 0), sec['id']))
        auditar(request, f"Carta: designação encerrada na secretaria “{sec['nome']}”")
        return ir('/admin/carta-secretarias', 'Designação encerrada.', request)
    raise HTTPException(400)

# ---------- monitoramento ----------
@r.get('/carta-monitoramento')
def monitoramento(request: Request):
    u = exige(request, 'carta_ver'); b = request.state.orgao['banco']
    tot = {x['situacao']: x['n'] for x in db.todos(b, 'SELECT situacao, count(*) n FROM servicos GROUP BY 1')}
    no_ar = db.um(b, "SELECT count(*) n FROM servicos WHERE publicado_dados IS NOT NULL AND situacao<>'arquivado'")['n']
    por_sec = db.todos(b, """SELECT sec.id, sec.nome, count(s.id) FILTER (WHERE s.publicado_dados IS NOT NULL AND s.situacao<>'arquivado') no_ar,
                             count(s.id) FILTER (WHERE s.situacao='em_validacao') validacao, count(s.id) FILTER (WHERE s.situacao IN ('rascunho','devolvido')) rascunhos,
                             count(s.id) FILTER (WHERE s.publicado_dados IS NOT NULL AND s.revisar_em < %s) vencidas
                             FROM secretarias sec LEFT JOIN servicos s ON s.secretaria_id=sec.id GROUP BY sec.id, sec.nome ORDER BY sec.nome""", (config.hoje(),))
    aval = db.todos(b, """SELECT s.id, s.nome, count(a.id) n, round(avg(a.nota)::numeric, 1) media, count(a.id) FILTER (WHERE a.conseguiu) sim
                          FROM servicos s JOIN servico_avaliacoes a ON a.servico_id=s.id GROUP BY s.id, s.nome ORDER BY avg(a.nota) NULLS LAST""")
    manif = db.todos(b, """SELECT s.nome, count(e.id) n FROM esic e JOIN servicos s ON s.id=e.servico_id
                           WHERE e.recebido > %s GROUP BY s.nome ORDER BY count(e.id) DESC""", (config.hoje() - timedelta(days=90),))
    coment = db.todos(b, "SELECT a.*, s.nome FROM servico_avaliacoes a JOIN servicos s ON s.id=a.servico_id WHERE a.comentario<>'' AND a.moderacao='pendente' ORDER BY a.id DESC LIMIT 50")
    return T('carta_monitor', request, u, tot=tot, no_ar=no_ar, por_sec=por_sec, aval=aval, manif=manif, coment=coment, vencidas=CT.vencidas(b),
             revisao=CT.prazo_revisao(b), categorias=_categorias(b), situacoes=CT.SITUACOES)

@r.post('/carta-monitoramento')
async def monitoramento_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    cfg = db.cfg(b, 'carta', {}) or {}
    if f.get('acao') == 'config':
        m = f.get('revisao_meses', '')
        cats = [c.strip()[:80] for c in (f.get('categorias') or '').splitlines() if c.strip()]
        if not m.isdigit() or not 1 <= int(m) <= 36 or not cats:
            return ir('/admin/carta-monitoramento', 'Revisão entre 1 e 36 meses e pelo menos uma categoria.', request)
        cfg.update(revisao_meses=int(m), categorias=cats); db.set_cfg(b, 'carta', cfg)
        auditar(request, f'Carta: revisão a cada {m} meses; {len(cats)} categorias')
        return ir('/admin/carta-monitoramento', 'Configuração salva.', request)
    if f.get('acao') in ('coment_lido', 'coment_remover'):
        i = int(f.get('id') or 0)
        if f['acao'] == 'coment_lido':
            db.exe(b, "UPDATE servico_avaliacoes SET moderacao='lido' WHERE id=%s", (i,))
        else:
            db.exe(b, "UPDATE servico_avaliacoes SET moderacao='removido', comentario='[removido pela moderação]' WHERE id=%s", (i,))
        auditar(request, f"Carta: comentário de avaliação {i} {f['acao']}")
        return ir('/admin/carta-monitoramento#comentarios', 'Comentário atualizado.', request)
    raise HTTPException(400)

# ---------- importação do inventário ----------
@r.get('/carta-importar')
def importar_ver(request: Request):
    u = _usuario(request)
    return T('carta_importar', request, u, colunas=CT.COLUNAS_IMPORT, rel=None)

@r.post('/carta-importar')
async def importar_post(request: Request):
    u = _usuario(request); exige(request, 'carta_redigir'); f = await ler_form(request); b = request.state.orgao['banco']
    arq = f.get('arquivo')
    if arq is None or not getattr(arq, 'filename', ''):
        return ir('/admin/carta-importar', 'Escolha o arquivo CSV.', request)
    dados = await arq.read(2 * 1024 * 1024 + 1)
    if len(dados) > 2 * 1024 * 1024:
        return ir('/admin/carta-importar', 'Arquivo maior que 2 MB.', request)
    rel = CT.importar(b, dados, u['nome'], simular=f.get('acao') != 'gravar', secretaria_unica=_escopo(u) if u['perfil'] in ('redator', 'validador') else None)
    auditar(request, f"Carta: importação do inventário — {rel['gravadas']} de {rel['linhas']} ({'simulação' if rel['simulacao'] else 'gravado'})")
    return T('carta_importar', request, u, colunas=CT.COLUNAS_IMPORT, rel=rel)
