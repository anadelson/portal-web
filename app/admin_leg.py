"""Painel do processo legislativo (Fase 5): legislaturas e Mesas, proposições e tramitação, comissões, sessões
com votação nominal, julgamento de contas, diárias, transmissões, participação, importação CSV e autoavaliação PNTP.
Mesmo código para qualquer órgão; as telas do Legislativo só aparecem para órgãos do tipo legislativo."""
import re
from datetime import date, datetime
from fastapi import APIRouter, Request, HTTPException
from psycopg.types.json import Jsonb
from . import config, db, legislativo as L, importar, aprovacao as AP
from .admin import T
from .catalogo import PODE
from .coletores.comum import chave
from .web import ler_form, ir, exige, auditar

r = APIRouter(prefix='/_a')

def leg_only(request):
    if request.state.orgao['tipo'] != 'legislativo':
        raise HTTPException(404, 'Disponível só para o Poder Legislativo.')
    return request.state.orgao['banco']

def _d(s):
    s = (s or '').strip()
    if not s:
        return None
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})$', s)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else date.fromisoformat(s)

def _arq(f, k):
    a = f.get(k)
    return a if a is not None and hasattr(a, 'read') and getattr(a, 'filename', '') else None

# ---------- legislaturas, vereadores e Mesas ----------
@r.get('/legislaturas')
def legislaturas(request: Request, leg: int | None = None):
    u = exige(request); b = leg_only(request)
    legs = db.todos(b, 'SELECT * FROM legislaturas ORDER BY numero DESC')
    leg = leg or (legs[0]['numero'] if legs else None)
    return T('legislaturas', request, u, legs=legs, leg=leg,
             ver=db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (leg,)) if leg else [],
             mesas=db.todos(b, 'SELECT * FROM mesas WHERE legislatura=%s ORDER BY bienio, id', (leg,)) if leg else [],
             bienios={x['bienio']: x for x in db.todos(b, 'SELECT * FROM mesa_bienios WHERE legislatura=%s', (leg,))} if leg else {},
             mesa_layout='abaixo' if db.cfg(b, 'mesa_layout') == 'abaixo' else 'lado')

@r.post('/legislaturas')
async def legislaturas_post(request: Request):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao'); leg = int(f.get('leg') or 0)
    try:
        if acao == 'nova':
            n = int(f['numero'])
            if not re.match(r'^\d{4}[–-]\d{4}$', f.get('anos', '')):
                raise ValueError('Anos no formato 2029–2032.')
            db.exe(b, 'INSERT INTO legislaturas (numero, anos, prefeito, vice) VALUES (%s,%s,%s,%s) ON CONFLICT (numero) DO UPDATE SET anos=EXCLUDED.anos, prefeito=EXCLUDED.prefeito, vice=EXCLUDED.vice',
                   (n, f['anos'].replace('-', '–'), f.get('prefeito', ''), f.get('vice', '')))
            a, z = [int(x) for x in f['anos'].replace('–', '-').split('-')]
            for bi in (f'{a}–{a + 1}', f'{a + 2}–{z}'):
                if not db.um(b, 'SELECT 1 FROM mesas WHERE legislatura=%s AND bienio=%s', (n, bi)):
                    for cargo in ('Presidente', 'Vice-presidente', '1º secretário', '2º secretário'):
                        db.exe(b, 'INSERT INTO mesas (legislatura, bienio, cargo, nome) VALUES (%s,%s,%s,NULL)', (n, bi, cargo))
            leg, msg = n, 'Legislatura salva (Mesas dos dois biênios criadas, a eleger).'
        elif acao == 'vereador':
            if not f.get('nome') or not f.get('partido'):
                raise ValueError('Informe nome e partido.')
            db.exe(b, 'INSERT INTO vereadores (nome, apelido, partido, legislatura, votos) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (nome, legislatura) DO UPDATE SET apelido=EXCLUDED.apelido, partido=EXCLUDED.partido, votos=EXCLUDED.votos',
                   (f['nome'][:120], f.get('apelido', '')[:60], f['partido'][:20], leg, int(f['votos']) if f.get('votos', '').isdigit() else None))
            msg = 'Vereador salvo.'
        elif acao == 'mesa':
            bi = f['bienio']
            nomes = {x['nome'] for x in db.todos(b, 'SELECT nome FROM vereadores WHERE legislatura=%s', (leg,))}
            for m in db.todos(b, 'SELECT * FROM mesas WHERE legislatura=%s AND bienio=%s', (leg, bi)):
                v = f.get(f"cargo_{m['id']}", '')
                if v and v not in nomes:
                    raise ValueError('Escolha vereadores da legislatura.')
                db.exe(b, 'UPDATE mesas SET nome=%s WHERE id=%s', (v or None, m['id']))
            db.exe(b, 'INSERT INTO mesa_bienios (legislatura, bienio, eleicao, posse, ato) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (legislatura, bienio) DO UPDATE SET eleicao=EXCLUDED.eleicao, posse=EXCLUDED.posse, ato=EXCLUDED.ato',
                   (leg, bi, _d(f.get('eleicao')), _d(f.get('posse')), f.get('ato', '')[:300]))
            msg = f'Mesa do biênio {bi} salva.'
        elif acao == 'mesa_layout':
            v = f.get('mesa_layout')
            if v not in ('lado', 'abaixo'):
                raise ValueError('Escolha lado a lado ou uma abaixo da outra.')
            db.set_cfg(b, 'mesa_layout', v)
            msg = 'Exibição das Mesas salva.'
        else:
            raise HTTPException(400)
    except (ValueError, KeyError) as e:
        return ir(f'/admin/legislaturas?leg={leg}', str(e) or 'Dados incompletos.', request)
    auditar(request, f'Legislaturas: {acao} ({leg})')
    return ir(f'/admin/legislaturas?leg={leg}', msg, request)

# ---------- proposições ----------
@r.get('/proposicoes')
def proposicoes(request: Request, tipo: str = '', ano: str = '', q: str = ''):
    u = exige(request); b = leg_only(request)
    w, p = [], []
    if tipo: w.append('tipo=%s'); p.append(tipo)
    if ano.isdigit(): w.append('ano=%s'); p.append(int(ano))
    if q: w.append("(ementa || ' ' || autor) ILIKE %s"); p.append(f'%{q}%')
    itens = db.todos(b, 'SELECT p.*, (SELECT count(*) FROM tramitacao t WHERE t.proposicao_id=p.id) n_tram, (SELECT count(*) FROM documentos d WHERE d.proposicao_id=p.id) n_doc FROM proposicoes p'
                     + (' WHERE ' + ' AND '.join(w) if w else '') + ' ORDER BY ano DESC, tipo, numero DESC LIMIT 300', p)
    return T('proposicoes', request, u, itens=itens, tipos=L.TIPOS, f={'tipo': tipo, 'ano': ano, 'q': q})

@r.get('/proposicoes/{pid}')
def proposicao(request: Request, pid: str):
    u = exige(request); b = leg_only(request)
    p = None if pid == 'nova' else db.um(b, 'SELECT * FROM proposicoes WHERE id=%s', (int(pid),))
    if pid != 'nova' and not p:
        raise HTTPException(404)
    pid_i = p['id'] if p else 0
    return T('proposicao', request, u, p=p, tipos=L.TIPOS, situacoes=L.SITUACOES_PROP, doc_tipos=L.DOC_TIPOS, ver=L.vereadores_atuais(b),
             autores=[a['nome'] for a in db.todos(b, 'SELECT nome FROM proposicao_autores WHERE proposicao_id=%s ORDER BY id', (pid_i,))],
             tram=db.todos(b, 'SELECT * FROM tramitacao WHERE proposicao_id=%s ORDER BY data, id', (pid_i,)),
             docs=db.todos(b, 'SELECT * FROM documentos WHERE proposicao_id=%s ORDER BY id', (pid_i,)),
             comissoes=db.todos(b, 'SELECT * FROM comissoes WHERE ativa ORDER BY nome'), hoje=config.hoje())

@r.post('/proposicoes/{pid}')
async def proposicao_post(request: Request, pid: str):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao'); hoje = config.hoje()
    try:
        if acao == 'salvar':
            if f.get('tipo') not in L.TIPO_SIGLA or not f.get('ementa'):
                raise ValueError('Escolha o tipo e escreva a ementa.')
            form = await request.form()
            autores = form.getlist('autor') + [x.strip() for x in f.get('autor_outro', '').split(';') if x.strip()]
            if not autores:
                raise ValueError('Informe ao menos um autor (vereador, Poder Executivo, Mesa Diretora ou Comissão).')
            ano = int(f.get('ano') or hoje.year)
            if pid == 'nova':
                num = L.proximo_numero(b, f['tipo'], ano)
                novo = db.exe(b, "INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao, relator, apresentada) VALUES (%s,%s,%s,'',%s,%s,%s,%s) RETURNING id",
                              (f['tipo'], num, ano, f['ementa'][:2000], f.get('situacao') or 'Em tramitação', f.get('relator', '')[:120], _d(f.get('apresentada')) or hoje))
                pid_i = novo['id']
                L.tramitar(b, pid_i, _d(f.get('apresentada')) or hoje, 'Apresentação', f'Protocolada como {f["tipo"]} nº {num}/{ano}.', quem=u['nome'])
            else:
                pid_i = int(pid)
                db.exe(b, 'UPDATE proposicoes SET ementa=%s, situacao=%s, relator=%s, apresentada=%s WHERE id=%s',
                       (f['ementa'][:2000], f.get('situacao') or 'Em tramitação', f.get('relator', '')[:120], _d(f.get('apresentada')), pid_i))
            L.definir_autores(b, pid_i, autores)
            msg = 'Proposição salva.'
        elif acao == 'tramitar':
            pid_i = int(pid)
            if not f.get('fase') or not f.get('data'):
                raise ValueError('Informe a data e a fase.')
            L.tramitar(b, pid_i, _d(f['data']), f['fase'], f.get('descricao', ''), quem=u['nome'], situacao=f.get('nova_situacao') or None)
            msg = 'Evento de tramitação registrado.'
        elif acao == 'documento':
            pid_i = int(pid)
            arq = _arq(f, 'arquivo')
            if not arq:
                raise ValueError('Escolha o arquivo PDF.')
            await L.salvar_pdf(request, arq, f.get('tipo_doc', ''), f.get('titulo', ''), f.get('descricao', ''), u['nome'], proposicao_id=pid_i)
            msg = 'Documento anexado.'
        elif acao == 'remover_doc':
            pid_i = int(pid)
            db.exe(b, 'DELETE FROM documentos WHERE id=%s AND proposicao_id=%s', (int(f['doc']), pid_i))
            msg = 'Documento removido.'
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir(f'/admin/proposicoes/{pid}', str(e), request)
    auditar(request, f'Proposição {pid_i}: {acao}')
    return ir(f'/admin/proposicoes/{pid_i}', msg, request)

# ---------- comissões ----------
@r.get('/comissoes')
def comissoes(request: Request):
    u = exige(request); b = leg_only(request)
    return T('comissoes', request, u, itens=db.todos(b, 'SELECT c.*, (SELECT count(*) FROM comissao_membros m WHERE m.comissao_id=c.id) n FROM comissoes c ORDER BY ativa DESC, nome'))

@r.get('/comissoes/{cid}')
def comissao(request: Request, cid: str):
    u = exige(request); b = leg_only(request)
    c = None if cid == 'nova' else db.um(b, 'SELECT * FROM comissoes WHERE id=%s', (int(cid),))
    if cid != 'nova' and not c:
        raise HTTPException(404)
    i = c['id'] if c else 0
    return T('comissao', request, u, c=c, ver=L.vereadores_atuais(b), props=db.todos(b, "SELECT id, tipo, numero, ano, ementa FROM proposicoes WHERE tipo = ANY(%s) ORDER BY ano DESC, numero DESC LIMIT 200", (list(L.PROJETOS) + ['Veto', 'Emenda'],)),
             membros=db.todos(b, 'SELECT m.*, v.nome FROM comissao_membros m JOIN vereadores v ON v.id=m.vereador_id WHERE comissao_id=%s ORDER BY cargo, v.nome', (i,)),
             reunioes=db.todos(b, 'SELECT * FROM comissao_reunioes WHERE comissao_id=%s ORDER BY data DESC', (i,)),
             pareceres=db.todos(b, 'SELECT pa.*, p.tipo, p.numero, p.ano FROM pareceres pa LEFT JOIN proposicoes p ON p.id=pa.proposicao_id WHERE comissao_id=%s ORDER BY data DESC', (i,)), doc_tipos=L.DOC_TIPOS)

@r.post('/comissoes/{cid}')
async def comissao_post(request: Request, cid: str):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao'); pub = AP.pode_publicar(b, 'legislativo', u)
    try:
        if acao == 'salvar':
            if not f.get('nome'):
                raise ValueError('Informe o nome da comissão.')
            vals = (f['nome'][:160], f.get('tipo') if f.get('tipo') in ('permanente', 'temporaria') else 'permanente', f.get('finalidade', '')[:1000], _d(f.get('inicio')), _d(f.get('fim')), bool(f.get('ativa', 'on')))
            if cid == 'nova':
                i = db.exe(b, 'INSERT INTO comissoes (nome, tipo, finalidade, inicio, fim, ativa) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id', vals)['id']
            else:
                i = int(cid); db.exe(b, 'UPDATE comissoes SET nome=%s, tipo=%s, finalidade=%s, inicio=%s, fim=%s, ativa=%s WHERE id=%s', vals + (i,))
            msg = 'Comissão salva.'
        else:
            i = int(cid)
            if acao == 'membro':
                db.exe(b, 'INSERT INTO comissao_membros (comissao_id, vereador_id, cargo) VALUES (%s,%s,%s) ON CONFLICT (comissao_id, vereador_id) DO UPDATE SET cargo=EXCLUDED.cargo',
                       (i, int(f['vereador']), f.get('cargo') if f.get('cargo') in ('Presidente', 'Relator', 'Membro') else 'Membro'))
                msg = 'Membro salvo.'
            elif acao == 'tirar_membro':
                db.exe(b, 'DELETE FROM comissao_membros WHERE comissao_id=%s AND vereador_id=%s', (i, int(f['vereador']))); msg = 'Membro retirado.'
            elif acao == 'reuniao':
                if not f.get('data') or not f.get('pauta'):
                    raise ValueError('Informe data e pauta da reunião.')
                db.exe(b, 'INSERT INTO comissao_reunioes (comissao_id, data, hora, pauta) VALUES (%s,%s,%s,%s)', (i, _d(f['data']), f.get('hora', '')[:10], f['pauta'][:5000])); msg = 'Reunião cadastrada.'
            elif acao == 'pub_reuniao' and pub:
                db.exe(b, 'UPDATE comissao_reunioes SET publicada=TRUE WHERE id=%s AND comissao_id=%s', (int(f['reuniao']), i)); msg = 'Pauta publicada.'
            elif acao == 'parecer':
                if not f.get('conclusao') or not f.get('data'):
                    raise ValueError('Informe a data e a conclusão do parecer.')
                doc = None
                if _arq(f, 'arquivo'):
                    doc = await L.salvar_pdf(request, _arq(f, 'arquivo'), 'parecer', f'Parecer da comissão', f.get('descricao', ''), u['nome'], comissao_id=i, proposicao_id=int(f['proposicao']) if f.get('proposicao') else None)
                pid = int(f['proposicao']) if f.get('proposicao') else None
                db.exe(b, 'INSERT INTO pareceres (comissao_id, proposicao_id, relator, conclusao, texto, data, documento_id) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                       (i, pid, f.get('relator', '')[:120], f['conclusao'][:200], f.get('texto', '')[:10000], _d(f['data']), doc))
                if pid:
                    c = db.um(b, 'SELECT nome FROM comissoes WHERE id=%s', (i,))['nome']
                    L.tramitar(b, pid, _d(f['data']), f'Parecer — {c}', f"{f['conclusao']}" + (f" · relator: {f['relator']}" if f.get('relator') else ''), quem=u['nome'])
                msg = 'Parecer registrado.'
            elif acao == 'pub_parecer' and pub:
                db.exe(b, 'UPDATE pareceres SET publicado=TRUE WHERE id=%s AND comissao_id=%s', (int(f['parecer']), i)); msg = 'Parecer publicado.'
            else:
                raise HTTPException(403)
    except ValueError as e:
        return ir(f'/admin/comissoes/{cid}', str(e), request)
    auditar(request, f'Comissão {i}: {acao}')
    return ir(f'/admin/comissoes/{i}', msg, request)

# ---------- sessões: pauta, presença, votação nominal, ata, vídeo ----------
@r.get('/sessoes')
def sessoes(request: Request):
    u = exige(request); b = leg_only(request)
    return T('sessoes', request, u, tipos_sessao=L.TIPOS_SESSAO, situacoes=L.SITUACOES_SESSAO, hoje=config.hoje(),
             itens=db.todos(b, 'SELECT s.*, (SELECT count(*) FROM pauta_itens i WHERE i.sessao_id=s.id) n_itens FROM sessoes s ORDER BY data DESC, id DESC'))

def _dados_sessao(b, s):
    membros = L.vereadores_atuais(b)
    pres = {p['vereador_id']: p['situacao'] for p in db.todos(b, 'SELECT * FROM presencas WHERE sessao_id=%s', (s['id'],))}
    itens = db.todos(b, 'SELECT i.*, p.tipo, p.numero, p.ano, p.ementa FROM pauta_itens i LEFT JOIN proposicoes p ON p.id=i.proposicao_id WHERE sessao_id=%s ORDER BY ordem, id', (s['id'],))
    for it in itens:
        it['votos'] = {v['vereador_id']: v['voto'] for v in db.todos(b, 'SELECT * FROM votos WHERE item_id=%s', (it['id'],))}
        it['cont'] = L.contagem(b, it['id'])
        it['docs'] = L.docs_item(b, it)
    return membros, pres, itens

@r.get('/sessoes/{sid}')
def sessao(request: Request, sid: str):
    u = exige(request); b = leg_only(request)
    if sid == 'nova':
        return ir('/admin/sessoes?novo=1', '', request)
    s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (int(sid),))
    if not s:
        raise HTTPException(404)
    membros, pres, itens = _dados_sessao(b, s)
    p = L.presidente_em(b, s['data'])
    return T('sessao', request, u, s=s, membros=membros, pres=pres, itens=itens, quoruns=L.QUORUNS, votos=L.VOTOS, pres_id=p['id'] if p else None,
             props=db.todos(b, "SELECT id, tipo, numero, ano, ementa FROM proposicoes WHERE situacao NOT IN ('Aprovada','Aprovado','Rejeitada','Rejeitado','Arquivada','Retirada') ORDER BY ano DESC, tipo, numero DESC LIMIT 300"),
             docs=db.todos(b, 'SELECT * FROM documentos WHERE sessao_id=%s AND pauta_item_id IS NULL ORDER BY id', (s['id'],)), passos=(ps := L.passos(b, s)), passos_d={p['chave']: p for p in ps}, eventos=L.eventos(b, s['id']), videos=L.videos(b, s['id']),
             tipos_ev=L.EVENTOS, tipos_sessao=L.TIPOS_SESSAO, situacoes=L.SITUACOES_SESSAO, plataformas=L.PLATAFORMAS, resultados=L.RESULTADOS_ITEM,
             tipos_prop=[t for t, _ in L.TIPOS], hoje=config.hoje(), pdf_tipos={k: L.DOC_TIPOS[k] for k in PDF_ITEM})

def _https(url):
    import re as _re
    url = (url or '').strip()
    if not _re.fullmatch(r'https://[\w.-]+\.[a-z]{2,}(:\d+)?(/\S*)?', url, _re.I):
        raise ValueError('Informe o endereço completo do vídeo, começando com https:// (YouTube, Facebook ou outro).')
    return url[:400]

@r.post('/sessoes/{sid}')
async def sessao_post(request: Request, sid: str):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao'); pub = AP.pode_publicar(b, 'legislativo', u); hoje = config.hoje()
    try:
        if acao == 'criar':
            if not f.get('data'):
                raise ValueError('Informe a data da sessão.')
            d = _d(f['data']); tipo = f.get('tipo') if f.get('tipo') in L.TIPOS_SESSAO else 'Ordinária'
            num = int(f['numero']) if (f.get('numero') or '').isdigit() else L.proximo_numero_sessao(b, tipo, d.year)
            nome = (f.get('nome') or '').strip()[:160] or L.nome_sessao(num, tipo, d.year)
            i = db.exe(b, 'INSERT INTO sessoes (nome, data, hora, tipo, numero) VALUES (%s,%s,%s,%s,%s) RETURNING id', (nome, d, L.hora(f.get('hora')) or '19h', tipo, num))['id']
            auditar(request, f'Criou a sessão {nome}')
            return ir(f'/admin/sessoes/{i}', f'Sessão criada: {nome}. Os próximos passos são opcionais e podem ser registrados depois da sessão.', request)
        i = int(sid); s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (i,))
        if not s:
            raise HTTPException(404)
        depois = s['data'] <= hoje
        if acao == 'dados':
            tipo = f.get('tipo') if f.get('tipo') in L.TIPOS_SESSAO else s['tipo']
            num = int(f['numero']) if (f.get('numero') or '').isdigit() else s['numero']
            db.exe(b, 'UPDATE sessoes SET nome=%s, data=%s, hora=%s, tipo=%s, numero=%s WHERE id=%s',
                   ((f.get('nome') or s['nome'])[:160], _d(f.get('data')) or s['data'], L.hora(f.get('hora')) or s['hora'], tipo, num, i))
            msg = 'Dados da sessão salvos.'
        elif acao == 'situacao':
            sit = f.get('situacao')
            if sit not in L.SITUACOES_SESSAO:
                raise ValueError('Situação inválida.')
            if sit == 'cancelada' and len((f.get('motivo') or '').strip()) < 5:
                raise ValueError('Informe o motivo do cancelamento (aparece no portal).')
            db.exe(b, 'UPDATE sessoes SET situacao=%s, motivo_cancelamento=%s WHERE id=%s', (sit, (f.get('motivo') or '').strip()[:300] if sit == 'cancelada' else '', i))
            msg = f'Sessão marcada como {L.SITUACOES_SESSAO[sit].lower()}.'
        elif acao in ('abertura', 'encerramento'):
            col = 'aberta_as' if acao == 'abertura' else 'encerrada_as'
            h = L.hora(f.get('hora'))
            if h and not depois:
                raise ValueError('O horário só pode ser registrado no dia da sessão ou depois.')
            db.exe(b, f'UPDATE sessoes SET {col}=%s WHERE id=%s', (h, i))
            if h:
                L.marcar_realizada(b, i)
            msg = (f"{'Abertura' if acao == 'abertura' else 'Encerramento'} registrado às {h}." if h else 'Horário apagado.')
        elif acao == 'item':
            if s['votacao_publicada']:
                raise ValueError('A votação já foi publicada: a pauta não pode mais mudar.')
            pid = int(f['proposicao']) if f.get('proposicao') else None
            if not pid and not (f.get('descricao') or '').strip():
                raise ValueError('Escolha uma proposição ou descreva o item.')
            it_id = _incluir_item(b, s, pid, (f.get('descricao') or '').strip(), f.get('quorum'), u)
            msg = 'Item incluído na pauta.'
            if _arq(f, 'arquivo'):
                try:
                    await _pdf_item(request, b, it_id, f, u)
                    msg = 'Item incluído na pauta, com o PDF.'
                except ValueError as e:
                    msg = f'Item incluído na pauta, mas o PDF não foi salvo: {e} Anexe de novo no item.'
        elif acao == 'pdf_item':
            if not _arq(f, 'arquivo'):
                raise ValueError('Escolha o arquivo PDF.')
            await _pdf_item(request, b, int(f['item']), f, u, sessao_id=i)
            msg = 'PDF vinculado ao item da pauta.'
        elif acao == 'tirar_pdf':
            d = db.um(b, 'SELECT * FROM documentos WHERE id=%s AND sessao_id=%s AND pauta_item_id IS NOT NULL', (int(f['doc']), i))
            if not d:
                raise ValueError('PDF não encontrado.')
            _apagar_doc(request, b, d)
            msg = 'PDF removido do item.'
        elif acao in ('subir_item', 'descer_item'):
            if s['votacao_publicada']:
                raise ValueError('A votação já foi publicada: a pauta não pode mais mudar.')
            _mover(b, 'pauta_itens', i, int(f['item']), acao == 'subir_item')
            msg = 'Ordem da pauta atualizada.'
        elif acao == 'materia':
            msg = await _materia_nova(request, b, s, f, u, (await request.form()).getlist('autor'))
        elif acao == 'tirar_item':
            it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i))
            if it and it['resultado'] in ('aprovado', 'rejeitado'):
                raise ValueError('Item já votado não pode sair da pauta.')
            for d in db.todos(b, 'SELECT * FROM documentos WHERE pauta_item_id=%s AND proposicao_id IS NULL', (int(f['item']),)):
                _apagar_doc(request, b, d)  # PDF só do item sai junto; o da proposição fica na proposição
            db.exe(b, 'DELETE FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i)); msg = 'Item retirado da pauta.'
        elif acao == 'presenca':
            if not depois:
                raise ValueError('A presença só pode ser registrada no dia da sessão ou depois.')
            n = 0
            for m in L.vereadores_atuais(b):
                v = f.get(f"pres_{m['id']}")
                if v in ('presente', 'ausente', 'justificada'):
                    db.exe(b, 'INSERT INTO presencas (sessao_id, vereador_id, situacao) VALUES (%s,%s,%s) ON CONFLICT (sessao_id, vereador_id) DO UPDATE SET situacao=EXCLUDED.situacao', (i, m['id'], v))
                    n += 1
            if n:
                L.marcar_realizada(b, i)
            msg = f'Presença registrada ({n} vereador(es)).' if n else 'Nenhuma presença marcada.'
        elif acao == 'votar':
            if not depois:
                raise ValueError('A votação só pode ser registrada no dia da sessão ou depois.')
            if s['votacao_publicada']:
                raise ValueError('Votação já publicada.')
            it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i))
            membros = L.vereadores_atuais(b)
            pres = {p['vereador_id']: p['situacao'] for p in db.todos(b, 'SELECT * FROM presencas WHERE sessao_id=%s', (i,))}
            votos = {}
            for m in membros:  # a presença não é obrigatória; quem está registrado como ausente ou justificado não vota
                v = f.get(f"voto_{m['id']}")
                if v and pres.get(m['id']) in ('ausente', 'justificada') and v != 'ausente':
                    raise ValueError(f"{m['nome']} não está presente: o voto só pode ser \"Ausente\".")
                if v:
                    votos[m['id']] = v
            p = L.presidente_em(b, s['data'])
            resultado, cont, aviso = L.apurar(b, it, votos, membros, p['id'] if p else None)
            db.exe(b, 'DELETE FROM votos WHERE item_id=%s', (it['id'],))
            for vid, v in votos.items():
                db.exe(b, 'INSERT INTO votos (item_id, vereador_id, voto) VALUES (%s,%s,%s)', (it['id'], vid, v))
            db.exe(b, "UPDATE pauta_itens SET resultado=%s, votado_em=now(), modo_votacao='nominal', observacao='' WHERE id=%s", (resultado, it['id']))
            L.situacao_apos_votacao(b, it, resultado, s, u['nome'], f"{cont['sim']} sim, {cont['nao']} não, {cont['abstencao']} abstenções, {cont['ausente']} ausentes. {aviso}".strip())
            if it['contas_id']:
                db.exe(b, 'UPDATE contas_julgamento SET resultado=%s WHERE id=%s', ('Contas aprovadas (parecer prévio mantido)' if resultado == 'aprovado' else 'Parecer prévio rejeitado', it['contas_id']))
            L.marcar_realizada(b, i)
            sem_pres = [m['nome'] for m in membros if m['id'] not in pres]
            msg = f"Votação registrada: {'APROVADO' if resultado == 'aprovado' else 'REJEITADO'} ({cont['sim']} sim × {cont['nao']} não). {aviso}" + \
                  (f" Presença ainda não registrada para {len(sem_pres)} vereador(es) — pode ser feita depois." if sem_pres else '')
        elif acao == 'simbolica':
            if not depois:
                raise ValueError('O resultado só pode ser registrado no dia da sessão ou depois.')
            if s['votacao_publicada']:
                raise ValueError('Votação já publicada.')
            it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i))
            res = f.get('resultado')
            if not it or res not in L.RESULTADOS_ITEM:
                raise ValueError('Escolha o resultado do item.')
            obs = (f.get('observacao') or '').strip()[:300]
            if L.problemas_texto(obs) and 'contém dado pessoal (CPF, e-mail, telefone ou RG)' in L.problemas_texto(obs):
                raise ValueError('A observação não pode ter dado pessoal (CPF, e-mail, telefone ou RG).')
            db.exe(b, 'DELETE FROM votos WHERE item_id=%s', (it['id'],))
            db.exe(b, "UPDATE pauta_itens SET resultado=%s, votado_em=now(), modo_votacao='simbolica', observacao=%s WHERE id=%s", (res, obs, it['id']))
            L.situacao_apos_votacao(b, it, res, s, u['nome'], ('votação simbólica' if res in ('aprovado', 'rejeitado') else '') + (f' ({obs})' if obs else ''))
            if it['contas_id'] and res in ('aprovado', 'rejeitado'):
                db.exe(b, 'UPDATE contas_julgamento SET resultado=%s WHERE id=%s', ('Contas aprovadas (parecer prévio mantido)' if res == 'aprovado' else 'Parecer prévio rejeitado', it['contas_id']))
            L.marcar_realizada(b, i)
            msg = f'Resultado registrado: {L.RESULTADOS_ITEM[res]}.'
        elif acao == 'evento':
            tipo = f.get('tipo')
            if tipo not in L.EVENTOS:
                raise ValueError('Escolha o tipo do acontecimento.')
            desc = (f.get('descricao') or '').strip()[:2000]
            vid = int(f['vereador']) if (f.get('vereador') or '').isdigit() else None
            pid = int(f['proposicao']) if (f.get('proposicao') or '').isdigit() else None
            if not (desc or vid or pid):
                raise ValueError('Descreva o acontecimento ou escolha o(a) vereador(a) ou a matéria.')
            if 'contém dado pessoal (CPF, e-mail, telefone ou RG)' in L.problemas_texto(desc):
                raise ValueError('O texto não pode ter dado pessoal (CPF, e-mail, telefone ou RG). Na tribuna livre, basta o tema da fala.')
            ordem = db.um(b, 'SELECT coalesce(max(ordem), 0) + 1 n FROM sessao_eventos WHERE sessao_id=%s', (i,))['n']
            db.exe(b, 'INSERT INTO sessao_eventos (sessao_id, ordem, hora, tipo, descricao, vereador_id, proposicao_id, registrado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                   (i, ordem, L.hora(f.get('hora')), tipo, desc, vid, pid, u['nome']))
            if depois:
                L.marcar_realizada(b, i)
            msg = 'Acontecimento registrado na linha do tempo.'
        elif acao in ('tirar_evento', 'subir_evento', 'descer_evento'):
            e = db.um(b, 'SELECT * FROM sessao_eventos WHERE id=%s AND sessao_id=%s', (int(f['evento']), i))
            if not e:
                raise ValueError('Registro não encontrado.')
            if acao == 'tirar_evento':
                db.exe(b, 'DELETE FROM sessao_eventos WHERE id=%s', (e['id'],)); msg = 'Registro apagado.'
            else:
                lst = db.todos(b, 'SELECT id FROM sessao_eventos WHERE sessao_id=%s ORDER BY ordem, id', (i,))
                ids = [x['id'] for x in lst]; k = ids.index(e['id']); j = k - 1 if acao == 'subir_evento' else k + 1
                if 0 <= j < len(ids):
                    ids[k], ids[j] = ids[j], ids[k]
                for n, x in enumerate(ids, 1):
                    db.exe(b, 'UPDATE sessao_eventos SET ordem=%s WHERE id=%s', (n, x))
                msg = 'Ordem ajustada.'
        elif acao == 'video':
            url = _https(f.get('url'))
            db.exe(b, 'INSERT INTO sessao_videos (sessao_id, plataforma, url, rotulo) VALUES (%s,%s,%s,%s) ON CONFLICT (sessao_id, url) DO UPDATE SET rotulo=EXCLUDED.rotulo',
                   (i, L.plataforma(url), url, (f.get('rotulo') or '').strip()[:120]))
            L.sincronizar_video(b, i)
            msg = f"Vídeo do {L.PLATAFORMAS[L.plataforma(url)]} vinculado à sessão." if L.plataforma(url) != 'outro' else 'Vídeo vinculado à sessão.'
        elif acao == 'tirar_video':
            db.exe(b, 'DELETE FROM sessao_videos WHERE id=%s AND sessao_id=%s', (int(f['video']), i))
            L.sincronizar_video(b, i)
            msg = 'Vídeo desvinculado.'
        elif acao == 'ata':
            db.exe(b, 'UPDATE sessoes SET ata=%s WHERE id=%s', (f.get('ata', '')[:100000], i))
            if _arq(f, 'arquivo'):
                await L.salvar_pdf(request, _arq(f, 'arquivo'), 'ata', f"Ata — {s['nome']}", f.get('descricao', '') or f"Ata da {s['nome']} de {s['data'].strftime('%d/%m/%Y')}.", u['nome'], sessao_id=i)
            if len(f.get('ata', '')) >= 20 or _arq(f, 'arquivo'):
                L.marcar_realizada(b, i)
            msg = 'Ata salva.'
        elif acao in ('pub_pauta', 'pub_presenca', 'pub_votacao', 'pub_ata', 'pub_linha'):
            if not pub:
                raise HTTPException(403)
            ok_, motivo = _publicavel(b, s, acao)
            if not ok_:
                raise ValueError(motivo)
            db.exe(b, f'UPDATE sessoes SET {PUB[acao][0]}=TRUE WHERE id=%s', (i,)); msg = 'Publicado no portal.'
        elif acao == 'pub_tudo':
            if not pub:
                raise HTTPException(403)
            feitos, faltam = [], []
            for a, (col, nome) in PUB.items():
                if s[col]:
                    continue
                ok_, _ = _publicavel(b, s, a)
                if ok_:
                    db.exe(b, f'UPDATE sessoes SET {col}=TRUE WHERE id=%s', (i,)); feitos.append(nome)
                else:
                    faltam.append(nome)
            msg = (f"Publicado: {', '.join(feitos)}." if feitos else 'Nada novo para publicar.') + (f" Sem registro (fica para depois, se houver): {', '.join(faltam)}." if faltam else '')
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir(f'/admin/sessoes/{sid}', str(e), request)
    auditar(request, f'Sessão {i}: {acao}')
    return ir(f'/admin/sessoes/{i}', msg, request)

PUB = {'pub_pauta': ('pauta_publicada', 'pauta'), 'pub_presenca': ('presenca_publicada', 'presença'), 'pub_linha': ('linha_publicada', 'linha do tempo'),
       'pub_votacao': ('votacao_publicada', 'votações'), 'pub_ata': ('ata_publicada', 'ata')}

def _publicavel(b, s, acao):
    """Cada parte é publicada só com o que existe; a falta de uma não impede as outras."""
    i = s['id']
    if acao == 'pub_pauta' and not (s['pauta'] or db.um(b, 'SELECT 1 FROM pauta_itens WHERE sessao_id=%s', (i,))):
        return False, 'A pauta está vazia.'
    if acao == 'pub_presenca' and not db.um(b, 'SELECT 1 FROM presencas WHERE sessao_id=%s', (i,)):
        return False, 'Não há presença registrada.'
    if acao == 'pub_votacao' and not db.um(b, "SELECT 1 FROM pauta_itens WHERE sessao_id=%s AND resultado IS NOT NULL", (i,)):
        return False, 'Não há votação registrada.'
    if acao == 'pub_ata' and len(s['ata'] or '') < 20 and not db.um(b, "SELECT 1 FROM documentos WHERE sessao_id=%s AND tipo='ata'", (i,)):
        return False, 'Escreva a ata ou anexe o PDF antes de publicar.'
    if acao == 'pub_linha' and not (s['aberta_as'] or s['encerrada_as'] or db.um(b, 'SELECT 1 FROM sessao_eventos WHERE sessao_id=%s', (i,))):
        return False, 'Não há horário nem acontecimento registrado.'
    return True, ''

def _incluir_item(b, s, pid, desc, quorum, u):
    """Item da Ordem do Dia: proposição (ou item avulso) e quórum. A fase da votação saiu do cadastro em 24/11/2026."""
    if pid and not desc:
        p = db.um(b, 'SELECT * FROM proposicoes WHERE id=%s', (pid,)); desc = f"{L.rotulo(p)} — {p['ementa'][:200]}"
    ordem = db.um(b, 'SELECT coalesce(max(ordem),0)+1 n FROM pauta_itens WHERE sessao_id=%s', (s['id'],))['n']
    it = db.exe(b, "INSERT INTO pauta_itens (sessao_id, ordem, proposicao_id, descricao, fase, quorum) VALUES (%s,%s,%s,%s,'',%s) RETURNING id",
                (s['id'], ordem, pid, desc[:600], quorum if quorum in L.QUORUNS else 'simples'))['id']
    if pid:
        L.tramitar(b, pid, s['data'], 'Incluída na pauta', f"{s['nome']}, {s['data'].strftime('%d/%m/%Y')}", sessao_id=s['id'], quem=u['nome'], situacao='Pronta para a pauta')
    return it

PDF_ITEM = ('texto', 'parecer', 'outro')  # tipos oferecidos no item da pauta

async def _pdf_item(request, b, item_id, f, u, sessao_id=None):
    """PDF vinculado ao item da pauta; se o item é uma proposição, o PDF também aparece na página dela."""
    it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s' + (' AND sessao_id=%s' if sessao_id else ''), (item_id, sessao_id) if sessao_id else (item_id,))
    if not it:
        raise ValueError('Item da pauta não encontrado.')
    tipo = f.get('tipo_doc') if f.get('tipo_doc') in PDF_ITEM else 'texto'
    titulo = (f.get('titulo') or '').strip() or L.DOC_TIPOS[tipo]
    desc = (f.get('descricao_doc') or '').strip() or f"{L.DOC_TIPOS[tipo]} do item da pauta: {it['descricao']}"
    await L.salvar_pdf(request, _arq(f, 'arquivo'), tipo, titulo, desc, u['nome'], sessao_id=it['sessao_id'], pauta_item_id=it['id'], proposicao_id=it['proposicao_id'])

def _apagar_doc(request, b, d):
    from pathlib import Path
    db.exe(b, 'DELETE FROM documentos WHERE id=%s', (d['id'],))
    arq = Path(config.DADOS_DIR) / request.state.orgao['slug'] / 'docs' / d['arquivo']
    if arq.is_file():
        arq.unlink()

def _mover(b, tabela, sid, item, subir):
    """Troca a posição do item com o vizinho (acima ou abaixo), renumerando a ordem da sessão."""
    ids = [r['id'] for r in db.todos(b, f'SELECT id FROM {tabela} WHERE sessao_id=%s ORDER BY ordem, id', (sid,))]
    if item not in ids:
        return
    k = ids.index(item); j = k - 1 if subir else k + 1
    if 0 <= j < len(ids):
        ids[k], ids[j] = ids[j], ids[k]
    for n, x in enumerate(ids, 1):
        db.exe(b, f'UPDATE {tabela} SET ordem=%s WHERE id=%s', (n, x))

async def _materia_nova(request, b, s, f, u, marcados):
    """Moção, requerimento, indicação, projeto… criado dentro da sessão, com o(s) autor(es); entra em Proposições e no perfil do autor."""
    tipo = f.get('tipo_materia')
    if tipo not in L.TIPO_SIGLA or not (f.get('ementa') or '').strip():
        raise ValueError('Escolha o tipo da matéria e escreva a ementa.')
    autores = list(marcados) + [x.strip() for x in (f.get('autor_outro') or '').split(';') if x.strip()]
    if not autores:
        raise ValueError('Escolha o(a) vereador(a) autor(a) (ou informe Mesa Diretora, Comissão ou Poder Executivo).')
    ano = s['data'].year
    num = L.proximo_numero(b, tipo, ano)
    pid = db.exe(b, "INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao, apresentada) VALUES (%s,%s,%s,'',%s,'Em tramitação',%s) RETURNING id",
                 (tipo, num, ano, f['ementa'].strip()[:2000], s['data']))['id']
    L.definir_autores(b, pid, autores)
    L.tramitar(b, pid, s['data'], 'Apresentação', f'Protocolada como {tipo} nº {num}/{ano} na {s["nome"]}.', sessao_id=s['id'], quem=u['nome'])
    partes = [f'{tipo} nº {num}/{ano} criada']
    if f.get('lida') == '1':
        ordem = db.um(b, 'SELECT coalesce(max(ordem), 0) + 1 n FROM sessao_eventos WHERE sessao_id=%s', (s['id'],))['n']
        vid = next((r['vereador_id'] for r in db.todos(b, 'SELECT vereador_id FROM proposicao_autores WHERE proposicao_id=%s AND vereador_id IS NOT NULL ORDER BY id', (pid,))), None)
        db.exe(b, "INSERT INTO sessao_eventos (sessao_id, ordem, hora, tipo, descricao, vereador_id, proposicao_id, registrado_por) VALUES (%s,%s,'','leitura','',%s,%s,%s)",
               (s['id'], ordem, vid, pid, u['nome']))
        L.tramitar(b, pid, s['data'], 'Leitura em Plenário', f"Lida no expediente da {s['nome']}.", sessao_id=s['id'], quem=u['nome'])
        partes.append('lida no expediente')
    if f.get('na_pauta') == '1':
        if s['votacao_publicada']:
            raise ValueError('A votação desta sessão já foi publicada: a matéria foi criada, mas não entra mais na pauta.')
        it_id = _incluir_item(b, s, pid, '', f.get('quorum'), u)
        partes.append('incluída na pauta para votação')
    else:
        it_id = None
    if _arq(f, 'arquivo'):
        try:
            await L.salvar_pdf(request, _arq(f, 'arquivo'), 'texto', f"Texto — {tipo} nº {num}/{ano}", f"Texto da {tipo} nº {num}/{ano}: {f['ementa'].strip()[:300]}",
                               u['nome'], proposicao_id=pid, sessao_id=s['id'] if it_id else None, pauta_item_id=it_id)
            partes.append('com o PDF')
        except ValueError as e:
            partes.append(f'mas o PDF não foi salvo ({e})')
    m = ', '.join(partes); return m[:1].upper() + m[1:] + '. Ela aparece em Proposições e no perfil do autor.'

# ---------- julgamento das contas do Prefeito ----------
@r.get('/contas')
def contas(request: Request):
    u = exige(request); b = leg_only(request)
    itens = db.todos(b, 'SELECT c.*, i.resultado item_resultado, s.nome sessao, s.id sessao_id FROM contas_julgamento c LEFT JOIN pauta_itens i ON i.id=c.pauta_item_id LEFT JOIN sessoes s ON s.id=i.sessao_id ORDER BY exercicio DESC')
    for c in itens:
        c['docs'] = db.todos(b, 'SELECT * FROM documentos WHERE contas_id=%s ORDER BY id', (c['id'],))
    return T('contas', request, u, itens=itens, sessoes=db.todos(b, 'SELECT id, nome, data FROM sessoes ORDER BY data DESC LIMIT 60'))

@r.post('/contas')
async def contas_post(request: Request):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao')
    try:
        if acao == 'salvar':
            if not f.get('exercicio', '').isdigit() or not f.get('responsavel'):
                raise ValueError('Informe o exercício e o responsável pelas contas.')
            db.exe(b, """INSERT INTO contas_julgamento (exercicio, responsavel, tce_processo, tce_parecer, comissao_parecer, decreto) VALUES (%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (exercicio) DO UPDATE SET responsavel=EXCLUDED.responsavel, tce_processo=EXCLUDED.tce_processo, tce_parecer=EXCLUDED.tce_parecer, comissao_parecer=EXCLUDED.comissao_parecer, decreto=EXCLUDED.decreto""",
                   (int(f['exercicio']), f['responsavel'][:120], f.get('tce_processo', '')[:60], f.get('tce_parecer', '')[:40], f.get('comissao_parecer', '')[:200], f.get('decreto', '')[:120]))
            msg = 'Processo de contas salvo.'
        elif acao == 'documento':
            c = db.um(b, 'SELECT * FROM contas_julgamento WHERE id=%s', (int(f['contas']),))
            if not _arq(f, 'arquivo'):
                raise ValueError('Escolha o arquivo PDF.')
            await L.salvar_pdf(request, _arq(f, 'arquivo'), f.get('tipo_doc', ''), f.get('titulo', '') or L.DOC_TIPOS.get(f.get('tipo_doc'), 'Documento'), f.get('descricao', ''), u['nome'], contas_id=c['id'])
            msg = 'Documento anexado.'
        elif acao == 'pauta':
            c = db.um(b, 'SELECT * FROM contas_julgamento WHERE id=%s', (int(f['contas']),))
            sid = int(f['sessao'])
            ordem = db.um(b, 'SELECT coalesce(max(ordem),0)+1 n FROM pauta_itens WHERE sessao_id=%s', (sid,))['n']
            it = db.exe(b, "INSERT INTO pauta_itens (sessao_id, ordem, descricao, fase, quorum, contas_id) VALUES (%s,%s,%s,'Votação do parecer prévio do TCESP','dois_tercos',%s) RETURNING id",
                        (sid, ordem, f"Julgamento das contas do Prefeito, exercício {c['exercicio']} ({c['responsavel']}) — parecer prévio do TCESP: {c['tce_parecer'] or 'a informar'}", c['id']))['id']
            db.exe(b, 'UPDATE contas_julgamento SET pauta_item_id=%s WHERE id=%s', (it, c['id']))
            msg = 'Incluído na pauta (o parecer do TCESP só deixa de prevalecer por 2/3 dos membros — Constituição, art. 31, § 2º).'
        elif acao == 'publicar' and AP.pode_publicar(b, 'legislativo', u):
            db.exe(b, 'UPDATE contas_julgamento SET publicado=TRUE WHERE id=%s', (int(f['contas']),)); msg = 'Publicado no portal.'
        else:
            raise HTTPException(403)
    except ValueError as e:
        return ir('/admin/contas', str(e), request)
    auditar(request, f'Contas: {acao}')
    return ir('/admin/contas', msg, request)

# ---------- diárias e verbas (PNTP 20.10) ----------
@r.get('/diarias')
def diarias(request: Request):
    u = exige(request); b = leg_only(request)
    return T('diarias', request, u, itens=db.todos(b, 'SELECT * FROM diarias_legislativo ORDER BY inicio DESC NULLS LAST, id DESC LIMIT 300'), decl=db.cfg(b, 'diarias_declaracao', {}) or {}, ano=config.hoje().year)

@r.post('/diarias')
async def diarias_post(request: Request):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao')
    try:
        if acao == 'nova':
            ini, fim = _d(f.get('inicio')), _d(f.get('fim'))
            valor = float(f.get('valor', '').replace('.', '').replace(',', '.'))
            if not f.get('beneficiario') or not ini or valor <= 0:
                raise ValueError('Informe beneficiário, início e valor.')
            db.exe(b, 'INSERT INTO diarias_legislativo (chave, fonte, ano, beneficiario, cargo, destino, motivo, inicio, fim, valor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (chave) DO NOTHING',
                   (chave('dl', f['beneficiario'], ini, fim, valor, f.get('destino')), 'cadastro', ini.year, f['beneficiario'][:160], f.get('cargo', '')[:80], f.get('destino', '')[:160], f.get('motivo', '')[:600], ini, fim, valor))
            msg = 'Diária lançada.'
        elif acao == 'declarar':
            d = db.cfg(b, 'diarias_declaracao', {}) or {}
            d[str(config.hoje().year)] = f'Não houve pagamento de diárias ou verbas até {config.hoje().strftime("%d/%m/%Y")} (declarado por {u["nome"]}).'
            db.set_cfg(b, 'diarias_declaracao', d); msg = 'Declaração registrada.'
        elif acao == 'remover':
            db.exe(b, 'DELETE FROM diarias_legislativo WHERE id=%s', (int(f['id']),)); msg = 'Lançamento removido.'
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir('/admin/diarias', str(e) if 'Informe' in str(e) else 'Valor inválido.', request)
    auditar(request, f'Diárias: {acao}')
    return ir('/admin/diarias', msg, request)

# ---------- transmissões (Câmara; Prefeitura quando o módulo de audiências estiver contratado) ----------
def _transm_ok(ctx_mods, o):
    if not (ctx_mods.get('transm') or ctx_mods.get('audiencias')):
        raise HTTPException(404, 'Módulo de transmissões não disponível para este órgão.')

def video_valido(v: str) -> str:
    """Aceita ID do YouTube (11 caracteres), endereço do YouTube ou URL https de um player. Devolve o valor normalizado."""
    v = (v or '').strip()
    if not v:
        return ''
    m = re.search(r'(?:youtu\.be/|v=|/embed/|/live/)([\w-]{11})', v)
    if m:
        return m.group(1)
    if re.fullmatch(r'[\w-]{11}', v):
        return v
    if v.startswith('https://') and ' ' not in v and '"' not in v and '<' not in v:
        return v
    raise ValueError('Use o ID do vídeo do YouTube, o endereço do vídeo ou uma URL https do player.')

@r.get('/transmissoes')
def transmissoes(request: Request):
    from .web import modulos_do_orgao
    u = exige(request); o = request.state.orgao; _transm_ok(modulos_do_orgao(o), o)
    return T('transmissoes', request, u, itens=db.todos(o['banco'], 'SELECT t.*, s.nome sessao FROM transmissoes t LEFT JOIN sessoes s ON s.id=t.sessao_id ORDER BY ao_vivo DESC, coalesce(previsto_para, iniciada_em) DESC NULLS LAST LIMIT 100'),
             conf=db.cfg(o['banco'], 'transmissao', {}) or {}, sessoes=db.todos(o['banco'], 'SELECT id, nome, data FROM sessoes ORDER BY data DESC LIMIT 60'), yt=_yt_situacao(o))

def _yt_situacao(o):
    """Texto curto sobre a integração com o YouTube (sem expor a chave)."""
    from . import credenciais as CR
    if not CR.situacao('youtube'):
        return 'chave da YouTube Data API ainda não cadastrada no console (Credenciais de fontes): só o botão manual funciona.'
    c = db.um(db.LOCAL, "SELECT inicio, ok, mensagem FROM coletas WHERE orgao_slug=%s AND fonte='youtube:canal' ORDER BY id DESC LIMIT 1", (o['slug'],))
    if not c:
        return 'chave cadastrada; nenhuma consulta ainda.'
    return f"última consulta em {c['inicio'].astimezone().strftime('%d/%m/%Y, %Hh%M')}: {'ok' if c['ok'] else 'falhou'} — {c['mensagem']}"

@r.post('/transmissoes')
async def transmissoes_post(request: Request):
    from .web import modulos_do_orgao
    u = exige(request, 'editar'); o = request.state.orgao; _transm_ok(modulos_do_orgao(o), o); f = await ler_form(request)
    b = o['banco']; acao = f.get('acao')
    try:
        if acao == 'config':
            if f.get('canal') and not re.fullmatch(r'UC[\w-]{22}', f['canal']):
                raise ValueError('O ID do canal começa com UC e tem 24 caracteres (YouTube Studio → Configurações → Canal → Configurações avançadas).')
            db.set_cfg(b, 'transmissao', {'canal': f.get('canal', '')[:60], 'canal_url': f.get('canal_url', '')[:200] if f.get('canal_url', '').startswith('https://') else ''}); msg = 'Canal salvo.'
        elif acao == 'nova':
            if not f.get('titulo'):
                raise ValueError('Informe o título.')
            prev = datetime.fromisoformat(f['previsto_para']) if f.get('previsto_para') else None
            db.exe(b, 'INSERT INTO transmissoes (titulo, tipo, previsto_para, video, sessao_id, legendas, libras) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   (f['titulo'][:200], f.get('tipo') or 'Sessão', prev, video_valido(f.get('video')), int(f['sessao']) if f.get('sessao') else None, bool(f.get('legendas')), bool(f.get('libras'))))
            msg = 'Transmissão agendada.'
        elif acao in ('iniciar', 'encerrar'):
            t = db.um(b, 'SELECT * FROM transmissoes WHERE id=%s', (int(f['id']),))
            if acao == 'iniciar':
                if not t['video']:
                    raise ValueError('Informe o vídeo/player antes de iniciar.')
                db.exe(b, 'UPDATE transmissoes SET ao_vivo=FALSE WHERE ao_vivo AND id<>%s', (t['id'],))
                db.exe(b, 'UPDATE transmissoes SET ao_vivo=TRUE, iniciada_em=coalesce(iniciada_em, now()), encerrada_em=NULL WHERE id=%s', (t['id'],))
                msg = 'Transmissão AO VIVO: a faixa já aparece no portal.'
            else:
                db.exe(b, 'UPDATE transmissoes SET ao_vivo=FALSE, encerrada_em=now() WHERE id=%s', (t['id'],))
                if t['sessao_id'] and t['video'] and len(t['video']) == 11:
                    db.exe(b, "UPDATE sessoes SET video_url=%s WHERE id=%s AND video_url=''", (f"https://www.youtube.com/watch?v={t['video']}", t['sessao_id']))
                msg = 'Transmissão encerrada: a faixa saiu do portal e a gravação ficou vinculada.'
        elif acao == 'editar':
            caps = []
            for l in f.get('capitulos', '').splitlines():
                m = re.match(r'^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$', l)
                if m:
                    caps.append([m.group(1), m.group(2)[:120]])
            db.exe(b, 'UPDATE transmissoes SET video=%s, capitulos=%s, legendas=%s, libras=%s, sessao_id=%s WHERE id=%s',
                   (video_valido(f.get('video')), Jsonb(caps), bool(f.get('legendas')), bool(f.get('libras')), int(f['sessao']) if f.get('sessao') else None, int(f['id'])))
            msg = 'Transmissão atualizada.'
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir('/admin/transmissoes', str(e), request)
    auditar(request, f'Transmissões: {acao}')
    return ir('/admin/transmissoes', msg, request)

# ---------- participação: Tribuna Livre, opiniões e avaliação ----------
@r.get('/participacao')
def participacao(request: Request, aba: str = 'pagina'):
    u = exige(request); o = request.state.orgao; b = o['banco']
    op = db.todos(b, "SELECT op.*, p.tipo, p.numero, p.ano FROM opinioes op JOIN proposicoes p ON p.id=op.proposicao_id ORDER BY (op.situacao='pendente') DESC, op.id DESC LIMIT 200")
    for x in op:
        x['avisos'] = L.problemas_texto(x['texto'])
    trib = db.todos(b, 'SELECT t.*, s.nome sessao, s.data FROM tribuna_inscricoes t JOIN sessoes s ON s.id=t.sessao_id ORDER BY (t.situacao=%s) DESC, s.data DESC, t.id', ('pendente',)) if o['tipo'] == 'legislativo' else []
    aval = db.todos(b, "SELECT pagina, count(*) n, count(*) FILTER (WHERE util) sim, count(*) FILTER (WHERE NOT util) nao, max(criado_em) ultima FROM avaliacoes GROUP BY pagina ORDER BY count(*) DESC LIMIT 100")
    coment = db.todos(b, "SELECT id, pagina, util, comentario, moderacao, criado_em FROM avaliacoes WHERE comentario<>'' AND moderacao<>'removido' ORDER BY (moderacao='pendente') DESC, id DESC LIMIT 100")
    mensal = db.todos(b, "SELECT to_char(criado_em AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM') mes, count(*) n, count(*) FILTER (WHERE util) sim FROM avaliacoes GROUP BY 1 ORDER BY 1 DESC LIMIT 24")
    from . import avaliacao as AV
    return T('participacao', request, u, op=op, trib=trib, aval=aval, coment=coment, mensal=mensal, aba=aba if aba in ('pagina', 'mes', 'comentarios', 'regras') else 'pagina',
             pend_coment=sum(1 for c in coment if c['moderacao'] == 'pendente'), prazo=AV.prazo(b))

@r.post('/participacao')
async def participacao_post(request: Request):
    u = exige(request, 'publicar'); b = request.state.orgao['banco']; f = await ler_form(request)
    acao, i = f.get('acao'), int(f.get('id') or 0)
    if acao == 'aval_regras':
        exige(request, 'config')
        d = f.get('dias', '')
        if not d.isdigit() or not 1 <= int(d) <= 365:
            return ir('/admin/participacao?aba=regras', 'Informe um prazo entre 1 e 365 dias.', request)
        db.set_cfg(b, 'avaliacao', {'dias': int(d)}); auditar(request, f'Avaliação do portal: prazo para nova avaliação = {d} dias')
        return ir('/admin/participacao?aba=regras', 'Regra salva.', request)
    if acao in ('coment_lido', 'coment_remover'):
        if acao == 'coment_lido':
            db.exe(b, "UPDATE avaliacoes SET moderacao='lido' WHERE id=%s", (i,))
        else:
            db.exe(b, "UPDATE avaliacoes SET moderacao='removido', comentario='[comentário removido pela moderação]' WHERE id=%s", (i,))
        auditar(request, f'Avaliação do portal: comentário {i} ' + ('marcado como lido' if acao == 'coment_lido' else 'removido'))
        return ir('/admin/participacao?aba=comentarios', 'Comentário ' + ('marcado como lido.' if acao == 'coment_lido' else 'removido.'), request)
    if acao == 'publicar':
        op = db.um(b, 'SELECT * FROM opinioes WHERE id=%s', (i,))
        if L.problemas_texto(op['texto']):
            return ir('/admin/participacao', 'Não publicado: o texto tem dado pessoal ou possível ofensa. Rejeite com o motivo.', request)
        db.exe(b, "UPDATE opinioes SET situacao='publicada', moderado_em=now() WHERE id=%s", (i,)); msg = 'Opinião publicada (sem dados pessoais).'
    elif acao == 'rejeitar':
        db.exe(b, "UPDATE opinioes SET situacao='rejeitada', motivo=%s, moderado_em=now() WHERE id=%s", (f.get('motivo', 'Fora das regras de participação')[:200], i)); msg = 'Opinião rejeitada.'
    elif acao in ('deferir', 'indeferir'):
        db.exe(b, 'UPDATE tribuna_inscricoes SET situacao=%s, motivo=%s WHERE id=%s', ('deferida' if acao == 'deferir' else 'indeferida', f.get('motivo', '')[:300], i)); msg = 'Inscrição ' + ('deferida.' if acao == 'deferir' else 'indeferida.')
    else:
        raise HTTPException(400)
    auditar(request, f'Participação: {acao} {i}')
    return ir('/admin/participacao', msg, request)

# ---------- importação de dados antigos (CSV) ----------
@r.get('/importar')
def importar_ver(request: Request):
    u = exige(request); b = request.state.orgao['banco']
    return T('importar', request, u, modelos=importar.modelos_do(request.state.orgao['tipo']), hist=db.todos(b, 'SELECT * FROM importacoes ORDER BY id DESC LIMIT 30'))

@r.post('/importar')
async def importar_post(request: Request):
    u = exige(request, 'config'); b = request.state.orgao['banco']; f = await ler_form(request)
    modelos = importar.modelos_do(request.state.orgao['tipo'])
    arq = _arq(f, 'arquivo')
    if not arq or f.get('modelo') not in modelos:
        return ir('/admin/importar', 'Escolha o modelo e o arquivo CSV.', request)
    dados = await arq.read(5 * 1024 * 1024 + 1)
    if len(dados) > 5 * 1024 * 1024:
        return ir('/admin/importar', 'Arquivo maior que 5 MB.', request)
    rel = importar.importar(b, f['modelo'], dados, simular=f.get('acao') != 'gravar', quem=u['nome'], arquivo=arq.filename)
    if f['modelo'] == 'votos' and rel['gravadas']:
        importar.votacoes_importadas_tramitar(b)
    auditar(request, f"Importação {f['modelo']}: {rel['gravadas']} de {rel['linhas']} ({'simulação' if rel['simulacao'] else 'gravado'})")
    return T('importar', request, u, modelos=modelos, hist=db.todos(b, 'SELECT * FROM importacoes ORDER BY id DESC LIMIT 30'), rel=rel)

# A autoavaliação PNTP (matriz inteira, Prefeitura e Câmara) fica em admin_pntp.py; a dimensão 20 continua calculada em legislativo.pntp.
