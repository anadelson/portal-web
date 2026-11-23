"""Painel — e-SIC e Ouvidoria (23/11/2026): fila com prazos, atendimento com histórico, prorrogação, complemento,
resposta com resultado e fundamento, recurso decidido por outra pessoa, encaminhamento a órgão parceiro (mesma instalação
ou outra), registro de atendimento presencial/telefone, configuração (autoridades, normas, e-mail), relatório anual da
Ouvidoria, rol de informações classificadas e a tela de integrações entre órgãos. Regras em atendimento.py."""
from datetime import date
from fastapi import APIRouter, Request, HTTPException
from starlette.concurrency import run_in_threadpool
from . import config, db, atendimento as A, notificacoes as N
from .catalogo import PODE
from .web import ler_form, ir, exige, auditar
from .admin import T

r = APIRouter(prefix='/_a')
FILTROS = [('abertos', 'Em aberto'), ('vencendo', 'Vencendo ou vencidos'), ('recurso', 'Recursos'), ('concluidos', 'Concluídos'), ('todos', 'Todos')]

def _pode(u, p):
    return u['perfil'] in PODE[p]

def _cx(request, u, **kw):
    return dict(SIT_AT=A.SITUACOES, DECISOES=A.DECISOES, DECISOES_RECURSO=A.DECISOES_RECURSO, CATEGORIAS=A.CATEGORIAS, CANAIS=A.CANAIS, conf_at=A.conf(request.state.orgao['banco']), **kw)

@r.get('/atendimento')
def lista(request: Request, f: str = 'abertos', tipo: str = '', q: str = ''):
    u = exige(request, 'atendimento'); b = request.state.orgao['banco']
    hoje = config.hoje()
    cond = {'abertos': "situacao IN ('recebido','analise','prorrogado','complementacao','recurso')",
            'vencendo': "situacao IN ('recebido','analise','prorrogado') AND prazo <= %(lim)s",
            'recurso': "situacao='recurso'", 'concluidos': "situacao IN ('respondido','encaminhado','encerrado')", 'todos': 'TRUE'}.get(f, 'TRUE')
    sql = f'SELECT * FROM esic WHERE {cond}' + (' AND tipo=%(tipo)s' if tipo in ('pedido', 'manifestacao') else '') + (' AND (protocolo ILIKE %(q)s OR assunto ILIKE %(q)s)' if q else '')
    sql += " ORDER BY (situacao IN ('respondido','encaminhado','encerrado')), prazo NULLS LAST, id DESC LIMIT 300"
    from datetime import timedelta
    itens = db.todos(b, sql, {'lim': hoje + timedelta(days=5), 'tipo': tipo, 'q': f'%{q.strip()[:60]}%'})
    for p in itens:
        p['prazo_txt'], p['prazo_cls'] = A.prazo_info(p, b)
    cont = db.um(b, """SELECT count(*) FILTER (WHERE situacao IN ('recebido','analise','prorrogado','complementacao','recurso')) abertos,
                              count(*) FILTER (WHERE situacao IN ('recebido','analise','prorrogado') AND prazo < %s) vencidos,
                              count(*) FILTER (WHERE situacao='recurso') recursos FROM esic""", (hoje,))
    fila = N.situacao_fila(b)
    return T('atendimento', request, u, **_cx(request, u, itens=itens, filtro=f if f in dict(FILTROS) else 'abertos', filtros=FILTROS, tipo=tipo, q=q, cont=cont,
             fila=fila, via_email=N.caminho(b)))

# ---------- registro no balcão, por telefone ou carta ----------
@r.get('/atendimento/novo')
def novo(request: Request):
    u = exige(request, 'atendimento')
    return T('atendimento_novo', request, u, **_cx(request, u))

@r.post('/atendimento/novo')
async def novo_post(request: Request):
    u = exige(request, 'atendimento'); f = await ler_form(request)
    o = request.state.orgao
    canal = f.get('canal') if f.get('canal') in ('presencial', 'telefone', 'carta', 'email') else 'presencial'
    try:
        p, codigo = A.registrar(o, dict(f, preservar=f.get('preservar') == '1', anonimo=f.get('anonimo') == '1'), canal=canal, quem=u['nome'])
    except A.Erro as e:
        return ir('/admin/atendimento/novo', str(e), request)
    auditar(request, f"Atendimento {p['protocolo']}: registrado no canal {canal}")
    request.session['codigo_balcao'] = {'id': p['id'], 'c': codigo}
    return ir(f"/admin/atendimento/{p['id']}", f"Registrado: protocolo {p['protocolo']}. Entregue ao cidadão o protocolo e o código de acesso mostrados abaixo.", request)

# ---------- um atendimento ----------
@r.get('/atendimento/{pid}')
def ver(request: Request, pid: int):
    u = exige(request, 'atendimento'); o = request.state.orgao; b = o['banco']
    p = A.pega(b, pid)
    if not p:
        raise HTTPException(404)
    p['prazo_txt'], p['prazo_cls'] = A.prazo_info(p, b)
    rev = pid in (request.session.get('id_rev') or [])
    ver_id = _pode(u, 'atendimento_identidade') and (not A.identidade_restrita(p) or rev)
    cb = request.session.pop('codigo_balcao', None)
    rec = A.recursos(b, pid)
    aberto = next((x for x in rec if not x['decisao']), None)
    return T('atendimento_item', request, u, **_cx(request, u, p=p, hist=A.historico(b, pid), recursos=rec, recurso_aberto=aberto, ver_id=ver_id,
             restrita=A.identidade_restrita(p), pode_ver_id=_pode(u, 'atendimento_identidade'), pode_recurso=_pode(u, 'atendimento_recurso'),
             destinos=A.destinos_possiveis(o, p) if p['situacao'] in A.ABERTAS and p['situacao'] != 'recurso' else [],
             codigo_balcao=cb['c'] if cb and cb.get('id') == pid else None, notif=db.todos(b, 'SELECT * FROM notificacoes WHERE ref=%s ORDER BY id DESC LIMIT 10', (p['protocolo'],))))

@r.post('/atendimento/{pid}')
async def acao(request: Request, pid: int):
    u = exige(request, 'atendimento'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']
    p = A.pega(b, pid)
    if not p:
        raise HTTPException(404)
    a = f.get('acao', '')
    volta = f'/admin/atendimento/{pid}'
    try:
        if a == 'setor':
            A.andamento(o, p, f.get('setor', ''), u['nome']); msg = 'Andamento registrado.'
        elif a == 'nota':
            A.nota(o, p, f.get('nota', ''), u['nome']); msg = 'Nota interna registrada.'
        elif a == 'prorrogar':
            A.prorrogar(o, p, f.get('justificativa', ''), u['nome']); msg = 'Prazo prorrogado; o cidadão foi avisado.'
        elif a == 'complemento':
            A.pedir_complemento(o, p, f.get('complemento', ''), u['nome']); msg = 'Complemento pedido; o prazo ficou suspenso.'
        elif a == 'responder':
            A.responder(o, p, f.get('resposta', ''), f.get('decisao', ''), f.get('fundamento', ''), u['nome']); msg = 'Resposta enviada ao cidadão.'
        elif a == 'recurso':
            if not _pode(u, 'atendimento_recurso'):
                raise HTTPException(403, 'Só a autoridade de recurso decide recursos.')
            A.decidir_recurso(o, p, f.get('decisao', ''), f.get('resposta', ''), u['nome']); msg = 'Decisão do recurso enviada ao cidadão.'
        elif a == 'encaminhar_orgao':
            res = await run_in_threadpool(A.encaminhar_orgao, o, p, f.get('destino_id'), u['nome'], f.get('com_identificacao') == '1')
            msg = f"Encaminhado. Protocolo no órgão de destino: {res.get('protocolo')}."
        elif a == 'atualizar_encaminhamento':
            res = await run_in_threadpool(A.atualizar_encaminhamento, o, p, u['nome'])
            msg = f"Situação no destino: {res.get('situacao_txt')}" + (' · resposta registrada no andamento.' if res.get('resposta') else '.')
        elif a == 'identidade':
            if not _pode(u, 'atendimento_identidade'):
                raise HTTPException(403, 'Seu perfil não vê a identificação do solicitante.')
            A.revelar_identidade(o, p, u['nome'])
            request.session['id_rev'] = ((request.session.get('id_rev') or []) + [pid])[-20:]
            msg = 'Identificação mostrada. O acesso ficou registrado.'
        else:
            raise HTTPException(400)
    except (A.Erro, ValueError) as e:
        return ir(volta, str(e), request)
    auditar(request, f"Atendimento {p['protocolo']}: {a}")
    return ir(volta, msg, request)

# ---------- configuração ----------
@r.get('/atendimento-config')
def conf_tela(request: Request):
    u = exige(request, 'atendimento_config'); b = request.state.orgao['banco']
    from . import email_saida as EM, credenciais
    return T('atendimento_config', request, u, **_cx(request, u, smtp=N.smtp_publico(b), seguras=EM.SEGURANCAS, via_email=N.caminho(b), fila=N.situacao_fila(b),
             chave_ok=credenciais.chave_ok(), papel=config.PAPEL))

@r.post('/atendimento-config')
async def conf_post(request: Request):
    u = exige(request, 'atendimento_config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    a = f.get('acao')
    if a == 'regras':
        c = A.conf(b)
        for k in ('unidade', 'unidade_ouvidoria', 'autoridade_1', 'autoridade_2', 'norma_lai', 'norma_ouvidoria', 'email_equipe'):
            c[k] = (f.get(k) or '').strip()[:300]
        for k in ('norma_lai_url', 'norma_ouvidoria_url'):
            v = (f.get(k) or '').strip()[:500]
            c[k] = v if v.startswith(('https://', 'http://', '/')) else ''
        c['instancias'] = 2 if f.get('instancias') == '2' else 1
        db.set_cfg(b, 'atendimento', c)
        msg = 'Regras do atendimento salvas.'
    elif a == 'smtp':
        from . import email_saida as EM
        d, erros = EM.validar(f)
        if erros:
            return ir('/admin/atendimento-config', ' '.join(erros), request)
        try:
            N.salvar_smtp(b, d)
        except ValueError as e:
            return ir('/admin/atendimento-config', str(e), request)
        msg = 'E-mail de saída do órgão salvo. Use "Enviar teste" para conferir.'
    elif a == 'smtp_apagar':
        N.apagar_smtp(b); msg = 'E-mail de saída do órgão removido.'
    elif a == 'smtp_testar':
        para = (f.get('para') or '').strip()
        msg = 'Teste: ' + await run_in_threadpool(N.testar, b, para, u['nome'])
    elif a == 'reenviar':
        db.exe(b, "UPDATE notificacoes SET tentativas=0, erro='' WHERE enviado_em IS NULL")
        msg = 'Mensagens pendentes voltam para a fila agora.'
    else:
        raise HTTPException(400)
    auditar(request, f'e-SIC/Ouvidoria (configuração): {a}')
    return ir('/admin/atendimento-config', msg, request)

# ---------- relatório anual da Ouvidoria ----------
@r.get('/atendimento-relatorio')
def relatorio(request: Request, ano: str = ''):
    u = exige(request, 'atendimento_config'); b = request.state.orgao['banco']
    try:
        a = int(ano)
    except ValueError:
        a = config.hoje().year - 1 if config.hoje().month <= 3 else config.hoje().year
    return T('atendimento_relatorio', request, u, **_cx(request, u, rel=A.relatorio_ouvidoria(b, a), ano=a, anos=sorted(set(A.anos(b)) | {a, config.hoje().year}, reverse=True)))

@r.post('/atendimento-relatorio')
async def relatorio_post(request: Request):
    u = exige(request, 'atendimento_config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    a = int(f.get('ano') or config.hoje().year)
    pub = f.get('acao') == 'publicar'
    db.exe(b, """INSERT INTO ouvidoria_relatorios (ano, analise, providencias, atualizado_por) VALUES (%s,%s,%s,%s)
                 ON CONFLICT (ano) DO UPDATE SET analise=EXCLUDED.analise, providencias=EXCLUDED.providencias, atualizado_por=EXCLUDED.atualizado_por""",
           (a, f.get('analise', '')[:20000], f.get('providencias', '')[:20000], u['nome']))
    if pub:
        db.exe(b, 'UPDATE ouvidoria_relatorios SET publicado_em=now() WHERE ano=%s', (a,))
    auditar(request, f'Relatório da Ouvidoria {a}: {"publicado" if pub else "salvo"}')
    return ir(f'/admin/atendimento-relatorio?ano={a}', 'Relatório publicado no portal.' if pub else 'Rascunho salvo.', request)

# ---------- informações classificadas ----------
@r.get('/atendimento-classificadas')
def classificadas(request: Request):
    u = exige(request, 'atendimento_config')
    return T('atendimento_classificadas', request, u, **_cx(request, u, itens=db.todos(request.state.orgao['banco'], 'SELECT * FROM informacoes_classificadas ORDER BY classificada_em DESC, id DESC')))

@r.post('/atendimento-classificadas')
async def classificadas_post(request: Request):
    u = exige(request, 'atendimento_config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    if f.get('acao') == 'nova':
        try:
            cl, ate = date.fromisoformat(f['classificada_em']), date.fromisoformat(f['prazo_ate'])
        except (KeyError, ValueError):
            return ir('/admin/atendimento-classificadas', 'Informe as datas de classificação e do fim do sigilo.', request)
        maximo = {'reservado': 5, 'secreto': 15, 'ultrassecreto': 25}.get(f.get('grau'))
        if not maximo or not f.get('assunto') or not f.get('fundamento'):
            return ir('/admin/atendimento-classificadas', 'Preencha assunto, grau e fundamento legal.', request)
        if ate > cl.replace(year=cl.year + maximo) or ate <= cl:
            return ir('/admin/atendimento-classificadas', f"O sigilo {f['grau']} vale no máximo {maximo} anos (LAI, art. 24, § 1º).", request)
        db.exe(b, 'INSERT INTO informacoes_classificadas (assunto, grau, categoria, fundamento, classificada_em, prazo_ate, autoridade) VALUES (%s,%s,%s,%s,%s,%s,%s)',
               (f['assunto'][:500], f['grau'], f.get('categoria', '')[:200], f['fundamento'][:500], cl, ate, f.get('autoridade', '')[:200]))
        msg = 'Informação classificada registrada no rol público.'
    elif f.get('acao') == 'desclassificar' and str(f.get('id', '')).isdigit():
        db.exe(b, 'UPDATE informacoes_classificadas SET desclassificada_em=%s WHERE id=%s AND desclassificada_em IS NULL', (config.hoje(), int(f['id'])))
        msg = 'Informação desclassificada (fica 12 meses na lista de desclassificadas).'
    else:
        raise HTTPException(400)
    auditar(request, f"Informações classificadas: {f.get('acao')}")
    return ir('/admin/atendimento-classificadas', msg, request)

# ---------- integrações entre órgãos ----------
@r.get('/orgaos-parceiros')
def parceiros_tela(request: Request):
    u = exige(request, 'config'); o = request.state.orgao
    from . import integracao as I
    pars = I.parceiros(o, ativos=False)
    for x in pars:
        x['par'] = bool(I.par(o, x))
        x['onde'] = 'mesma instalação' if I.e_local(x) else f"outra instalação{(' (' + x['hospedagem'] + ')') if x.get('hospedagem') else ''}"
    return T('orgaos_parceiros', request, u, parceiros=pars, log=I.historico(o, 40), teste=request.session.pop('teste_integ', None), papel=config.PAPEL)

@r.post('/orgaos-parceiros')
async def parceiros_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    o = request.state.orgao
    from . import integracao as I
    p = I.parceiro(id_=int(f.get('id') or 0))
    if not p or p['ibge'] != o['ibge'] or p['id'] == o['id']:
        raise HTTPException(400)
    ok, txt = await run_in_threadpool(I.testar, o, p)
    request.session['teste_integ'] = {'ok': ok, 'txt': txt, 'nome': p['nome']}
    auditar(request, f"Integração: teste com {p['slug']} ({'ok' if ok else 'falhou'})")
    return ir('/admin/orgaos-parceiros', '', request)
