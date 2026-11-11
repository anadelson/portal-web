"""Painel do processo legislativo (Fase 5): legislaturas e Mesas, proposições e tramitação, comissões, sessões
com votação nominal, julgamento de contas, diárias, transmissões, participação, importação CSV e autoavaliação PNTP.
Mesmo código para qualquer órgão; as telas do Legislativo só aparecem para órgãos do tipo legislativo."""
import re
from datetime import date, datetime
from fastapi import APIRouter, Request, HTTPException
from psycopg.types.json import Jsonb
from . import config, db, legislativo as L, importar
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
             bienios={x['bienio']: x for x in db.todos(b, 'SELECT * FROM mesa_bienios WHERE legislatura=%s', (leg,))} if leg else {})

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
    acao = f.get('acao'); pub = u['perfil'] in PODE['publicar']
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
    return T('sessoes', request, u, itens=db.todos(b, 'SELECT s.*, (SELECT count(*) FROM pauta_itens i WHERE i.sessao_id=s.id) n_itens FROM sessoes s ORDER BY data DESC, id DESC'))

def _dados_sessao(b, s):
    membros = L.vereadores_atuais(b)
    pres = {p['vereador_id']: p['situacao'] for p in db.todos(b, 'SELECT * FROM presencas WHERE sessao_id=%s', (s['id'],))}
    itens = db.todos(b, 'SELECT i.*, p.tipo, p.numero, p.ano, p.ementa FROM pauta_itens i LEFT JOIN proposicoes p ON p.id=i.proposicao_id WHERE sessao_id=%s ORDER BY ordem, id', (s['id'],))
    for it in itens:
        it['votos'] = {v['vereador_id']: v['voto'] for v in db.todos(b, 'SELECT * FROM votos WHERE item_id=%s', (it['id'],))}
        it['cont'] = L.contagem(b, it['id'])
    return membros, pres, itens

@r.get('/sessoes/{sid}')
def sessao(request: Request, sid: str):
    u = exige(request); b = leg_only(request)
    if sid == 'nova':
        return T('sessao', request, u, s=None, membros=[], pres={}, itens=[], props=[], docs=[], pres_id=None, quoruns=L.QUORUNS, votos=L.VOTOS)
    s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (int(sid),))
    if not s:
        raise HTTPException(404)
    membros, pres, itens = _dados_sessao(b, s)
    p = L.presidente_em(b, s['data'])
    return T('sessao', request, u, s=s, membros=membros, pres=pres, itens=itens, quoruns=L.QUORUNS, votos=L.VOTOS, pres_id=p['id'] if p else None,
             props=db.todos(b, "SELECT id, tipo, numero, ano, ementa FROM proposicoes WHERE situacao NOT IN ('Aprovada','Aprovado','Rejeitada','Rejeitado','Arquivada','Retirada') ORDER BY ano DESC, tipo, numero DESC LIMIT 300"),
             docs=db.todos(b, 'SELECT * FROM documentos WHERE sessao_id=%s ORDER BY id', (s['id'],)))

@r.post('/sessoes/{sid}')
async def sessao_post(request: Request, sid: str):
    u = exige(request, 'editar'); b = leg_only(request); f = await ler_form(request)
    acao = f.get('acao'); pub = u['perfil'] in PODE['publicar']
    try:
        if acao == 'criar':
            if not f.get('nome') or not f.get('data'):
                raise ValueError('Informe o nome e a data da sessão.')
            i = db.exe(b, 'INSERT INTO sessoes (nome, data, hora, tipo) VALUES (%s,%s,%s,%s) RETURNING id', (f['nome'][:160], _d(f['data']), f.get('hora') or '19h', f.get('tipo') or 'Ordinária'))['id']
            auditar(request, f"Criou a sessão {f['nome']}")
            return ir(f'/admin/sessoes/{i}', 'Sessão criada. Monte a pauta.', request)
        i = int(sid); s = db.um(b, 'SELECT * FROM sessoes WHERE id=%s', (i,))
        if not s:
            raise HTTPException(404)
        if acao == 'dados':
            db.exe(b, 'UPDATE sessoes SET nome=%s, data=%s, hora=%s, tipo=%s, video_url=%s WHERE id=%s', (f.get('nome', s['nome'])[:160], _d(f.get('data')) or s['data'], f.get('hora', s['hora'])[:10], f.get('tipo', s['tipo'])[:40], f.get('video_url', '')[:300], i))
            msg = 'Dados da sessão salvos.'
        elif acao == 'item':
            if s['votacao_publicada']:
                raise ValueError('A votação já foi publicada: a pauta não pode mais mudar.')
            pid = int(f['proposicao']) if f.get('proposicao') else None
            if not pid and not f.get('descricao'):
                raise ValueError('Escolha uma proposição ou descreva o item.')
            desc = f.get('descricao') or ''
            if pid and not desc:
                p = db.um(b, 'SELECT * FROM proposicoes WHERE id=%s', (pid,)); desc = f"{L.rotulo(p)} — {p['ementa'][:200]}"
            ordem = db.um(b, 'SELECT coalesce(max(ordem),0)+1 n FROM pauta_itens WHERE sessao_id=%s', (i,))['n']
            db.exe(b, 'INSERT INTO pauta_itens (sessao_id, ordem, proposicao_id, descricao, fase, quorum) VALUES (%s,%s,%s,%s,%s,%s)',
                   (i, ordem, pid, desc[:600], f.get('fase') or 'Discussão e votação única', f.get('quorum') if f.get('quorum') in L.QUORUNS else 'simples'))
            if pid:
                L.tramitar(b, pid, s['data'], 'Incluída na pauta', f"{s['nome']}, {s['data'].strftime('%d/%m/%Y')}", sessao_id=i, quem=u['nome'], situacao='Pronta para a pauta')
            msg = 'Item incluído na pauta.'
        elif acao == 'tirar_item':
            it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i))
            if it and it['resultado'] in ('aprovado', 'rejeitado'):
                raise ValueError('Item já votado não pode sair da pauta.')
            db.exe(b, 'DELETE FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i)); msg = 'Item retirado da pauta.'
        elif acao == 'presenca':
            if s['data'] > config.hoje():
                raise ValueError('A presença só pode ser registrada no dia da sessão ou depois.')
            membros = L.vereadores_atuais(b)
            for m in membros:
                v = f.get(f"pres_{m['id']}")
                if v in ('presente', 'ausente', 'justificada'):
                    db.exe(b, 'INSERT INTO presencas (sessao_id, vereador_id, situacao) VALUES (%s,%s,%s) ON CONFLICT (sessao_id, vereador_id) DO UPDATE SET situacao=EXCLUDED.situacao', (i, m['id'], v))
            msg = 'Presença registrada.'
        elif acao == 'votar':
            if s['data'] > config.hoje():
                raise ValueError('A votação só pode ser registrada no dia da sessão ou depois.')
            if s['votacao_publicada']:
                raise ValueError('Votação já publicada.')
            it = db.um(b, 'SELECT * FROM pauta_itens WHERE id=%s AND sessao_id=%s', (int(f['item']), i))
            membros = L.vereadores_atuais(b)
            pres = {p['vereador_id']: p['situacao'] for p in db.todos(b, 'SELECT * FROM presencas WHERE sessao_id=%s', (i,))}
            if len(pres) < len(membros):
                raise ValueError('Registre a presença de todos os vereadores antes da votação.')
            votos = {}
            for m in membros:
                v = f.get(f"voto_{m['id']}")
                if v and pres.get(m['id']) != 'presente' and v != 'ausente':
                    raise ValueError(f"{m['nome']} não está presente: o voto só pode ser \"Ausente\".")
                if v:
                    votos[m['id']] = v
            p = L.presidente_em(b, s['data'])
            resultado, cont, aviso = L.apurar(b, it, votos, membros, p['id'] if p else None)
            for vid, v in votos.items():
                db.exe(b, 'INSERT INTO votos (item_id, vereador_id, voto) VALUES (%s,%s,%s) ON CONFLICT (item_id, vereador_id) DO UPDATE SET voto=EXCLUDED.voto', (it['id'], vid, v))
            db.exe(b, 'UPDATE pauta_itens SET resultado=%s, votado_em=now() WHERE id=%s', (resultado, it['id']))
            if it['proposicao_id']:
                pr = db.um(b, 'SELECT tipo FROM proposicoes WHERE id=%s', (it['proposicao_id'],))
                fem = pr['tipo'] in ('Indicação', 'Moção', 'Emenda') or pr['tipo'].startswith('Proposta')
                sit = ('Aprovada' if fem else 'Aprovado') if resultado == 'aprovado' else ('Rejeitada' if fem else 'Rejeitado')
                if pr['tipo'] in L.PROJETOS:
                    sit = 'Aprovada' if resultado == 'aprovado' else 'Rejeitada'
                L.tramitar(b, it['proposicao_id'], s['data'], f"Votação em Plenário — {it['fase']}",
                           f"{'Aprovado' if resultado == 'aprovado' else 'Rejeitado'} na {s['nome']}: {cont['sim']} sim, {cont['nao']} não, {cont['abstencao']} abstenções, {cont['ausente']} ausentes. {aviso}".strip(),
                           sessao_id=i, quem=u['nome'], situacao=sit)
            if it['contas_id']:
                db.exe(b, 'UPDATE contas_julgamento SET resultado=%s WHERE id=%s', ('Contas aprovadas (parecer prévio mantido)' if resultado == 'aprovado' else 'Parecer prévio rejeitado', it['contas_id']))
            msg = f"Votação registrada: {'APROVADO' if resultado == 'aprovado' else 'REJEITADO'} ({cont['sim']} sim × {cont['nao']} não). {aviso}"
        elif acao == 'ata':
            db.exe(b, 'UPDATE sessoes SET ata=%s WHERE id=%s', (f.get('ata', '')[:100000], i))
            if _arq(f, 'arquivo'):
                await L.salvar_pdf(request, _arq(f, 'arquivo'), 'ata', f"Ata — {s['nome']}", f.get('descricao', '') or f"Ata da {s['nome']} de {s['data'].strftime('%d/%m/%Y')}.", u['nome'], sessao_id=i)
            msg = 'Ata salva.'
        elif acao in ('pub_pauta', 'pub_presenca', 'pub_votacao', 'pub_ata'):
            if not pub:
                raise HTTPException(403)
            if acao == 'pub_presenca' and not db.um(b, 'SELECT 1 FROM presencas WHERE sessao_id=%s', (i,)):
                raise ValueError('Não há presença registrada.')
            if acao == 'pub_votacao' and not db.um(b, "SELECT 1 FROM pauta_itens WHERE sessao_id=%s AND resultado IS NOT NULL", (i,)):
                raise ValueError('Não há votação registrada.')
            if acao == 'pub_ata' and len(s['ata'] or '') < 20 and not db.um(b, "SELECT 1 FROM documentos WHERE sessao_id=%s AND tipo='ata'", (i,)):
                raise ValueError('Escreva a ata ou anexe o PDF antes de publicar.')
            col = {'pub_pauta': 'pauta_publicada', 'pub_presenca': 'presenca_publicada', 'pub_votacao': 'votacao_publicada', 'pub_ata': 'ata_publicada'}[acao]
            db.exe(b, f'UPDATE sessoes SET {col}=TRUE WHERE id=%s', (i,)); msg = 'Publicado no portal.'
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir(f'/admin/sessoes/{sid}', str(e), request)
    auditar(request, f'Sessão {i}: {acao}')
    return ir(f'/admin/sessoes/{i}', msg, request)

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
        elif acao == 'publicar' and u['perfil'] in PODE['publicar']:
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

# ---------- autoavaliação PNTP ----------
@r.get('/pntp')
def pntp(request: Request):
    u = exige(request); b = leg_only(request)
    return T('pntp', request, u, itens=L.pntp(b))
