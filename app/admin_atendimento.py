"""Painel → e-SIC e Ouvidoria (23/11/2026): fila com filtros, ficha com histórico e notas internas, setor, prorrogação,
complemento, resposta com resultado e fundamento, decisão de recurso, encaminhamento ao órgão parceiro, registro
presencial, configuração (unidade, autoridades, norma local, e-mail da equipe e SMTP próprio), relatório e informações
classificadas. Regras em app/atendimento.py; perfis em catalogo.PODE (atendimento*, recurso_decidir)."""
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from . import db, atendimento as A, integracao as IG
from .admin import T
from .catalogo import PODE
from .web import ler_form, ir, exige, auditar

r = APIRouter(prefix='/_a')


def _prazo(b, p):
    s = p['situacao']
    if s in ('respondido', 'encerrado', 'encaminhado'):
        return 'Concluído', ''
    if s == 'complemento':
        return f"Aguardando o cidadão até {p['complemento_prazo']:%d/%m/%Y}", 'alerta'
    if s == 'recurso':
        rec = A.recurso_pendente(b, p)
        lim = rec['prazo'] if rec else A.hoje()
        falta = (lim - A.hoje()).days
        return f"Recurso: decidir até {lim:%d/%m/%Y}", 'erro' if falta <= 1 else 'alerta'
    falta = (p['prazo'] - A.hoje()).days
    txt = f"vencido há {-falta} dia(s)" if falta < 0 else 'vence hoje' if falta == 0 else f'faltam {falta} dia(s)'
    return f"{txt} ({p['prazo']:%d/%m/%Y})", 'erro' if falta <= 2 else ''


def _abas(atual):
    return [('/admin/atendimento', 'Pedidos e manifestações', atual == 'lista'), ('/admin/atendimento/novo', 'Registro presencial', atual == 'novo'),
            ('/admin/atendimento/relatorio', 'Relatório', atual == 'relatorio'), ('/admin/atendimento/classificadas', 'Informações classificadas', atual == 'classificadas'),
            ('/admin/atendimento/configuracao', 'Configuração', atual == 'config')]


@r.get('/atendimento')
def lista(request: Request, tipo: str = '', situacao: str = 'abertos', setor: str = '', q: str = ''):
    u = exige(request, 'atendimento')
    b = request.state.orgao['banco']
    w, par = ['TRUE'], []
    if tipo in ('pedido', 'manifestacao'):
        w.append('tipo=%s'); par.append(tipo)
    if situacao == 'abertos':
        w.append('situacao = ANY(%s)'); par.append(list(A.ABERTAS))
    elif situacao in A.SITUACOES:
        w.append('situacao=%s'); par.append(situacao)
    if setor:
        w.append('setor=%s'); par.append(setor)
    if q:
        w.append('(protocolo ILIKE %s OR assunto ILIKE %s)'); par += [f'%{q}%'] * 2
    itens = db.todos(b, f"SELECT * FROM esic WHERE {' AND '.join(w)} ORDER BY (situacao = ANY(%s)) DESC, prazo, id LIMIT 300", (*par, list(A.ABERTAS)))
    for p in itens:
        p['prazo_txt'], p['prazo_cls'] = _prazo(b, p)
    setores = [x['setor'] for x in db.todos(b, "SELECT DISTINCT setor FROM esic WHERE setor<>'' ORDER BY 1")]
    fila = db.um(b, 'SELECT count(*) n, max(erro) erro FROM email_fila WHERE enviado_em IS NULL')
    return T('atendimento', request, u, itens=itens, f=dict(tipo=tipo, situacao=situacao, setor=setor, q=q), setores=setores, A=A, abas=_abas('lista'), fila=fila)


# ---------- registro presencial ----------
@r.get('/atendimento/novo')
def novo(request: Request):
    u = exige(request, 'atendimento_responder')
    return T('atendimento_novo', request, u, A=A, abas=_abas('novo'), feito=None)


@r.post('/atendimento/novo')
async def novo_post(request: Request):
    u = exige(request, 'atendimento_responder'); f = await ler_form(request)
    o = request.state.orgao
    p, codigo, erro = A.registrar(o, dict(f, anonimo=f.get('anonimo') == '1'), canal='presencial', quem=u['nome'])
    if erro:
        return ir('/admin/atendimento/novo', erro, request)
    auditar(request, f"e-SIC/Ouvidoria: registro presencial {p['protocolo']}")
    return T('atendimento_novo', request, u, A=A, abas=_abas('novo'), feito=p, codigo=codigo)


# ---------- configuração ----------
def _autoridades(b):
    return db.todos(b, "SELECT id, nome, perfil FROM usuarios WHERE situacao='ativo' AND perfil = ANY(%s) ORDER BY nome", (list(PODE['recurso_decidir']),))


@r.get('/atendimento/configuracao')
def config_ver(request: Request):
    u = exige(request, 'atendimento_config')
    b = request.state.orgao['banco']
    from . import credenciais
    return T('atendimento_config', request, u, A=A, abas=_abas('config'), c=A.conf(b), smtp=A.smtp_atual(b), autoridades=_autoridades(b), chave_ok=credenciais.chave_ok())


@r.post('/atendimento/configuracao')
async def config_post(request: Request):
    u = exige(request, 'atendimento_config'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']
    acao = f.get('acao', 'salvar')
    volta = '/admin/atendimento/configuracao'
    if acao == 'salvar':
        c = A.conf(b)
        for k in ('unidade', 'unidade_ouvidoria', 'autoridade1_cargo', 'autoridade2_cargo', 'norma_nome', 'norma_url', 'email_equipe'):
            c[k] = (f.get(k) or '').strip()[:300]
        if c['norma_url'] and not c['norma_url'].startswith(('https://', 'http://', '/')):
            return ir(volta, 'O endereço da norma precisa começar com https:// (ou /).', request)
        if c['email_equipe'] and not A.EMAIL.match(c['email_equipe']):
            return ir(volta, 'E-mail da equipe inválido.', request)
        ids = {x['id'] for x in _autoridades(b)}
        for k in ('autoridade1_id', 'autoridade2_id'):
            v = f.get(k, '')
            c[k] = int(v) if v.isdigit() and int(v) in ids else None
        if c['autoridade1_id'] and c['autoridade1_id'] == c['autoridade2_id']:
            return ir(volta, 'A autoridade da 2ª instância precisa ser outra pessoa.', request)
        if f.get('sem_classificadas') == '1':
            c['sem_classificadas'] = c['sem_classificadas'] or A.hoje().isoformat()
        else:
            c['sem_classificadas'] = ''
        db.set_cfg(b, 'atendimento', c)
        auditar(request, 'e-SIC/Ouvidoria: configuração salva')
        return ir(volta, 'Configuração salva.', request)
    if acao == 'smtp':
        erro = A.smtp_salvar(b, f, u['nome'])
        auditar(request, 'e-SIC/Ouvidoria: SMTP próprio ' + ('recusado' if erro else 'gravado'))
        return ir(volta, erro or 'SMTP do órgão gravado (a senha fica cifrada). Faça o teste.', request)
    if acao == 'smtp_remover':
        A.smtp_remover(b)
        auditar(request, 'e-SIC/Ouvidoria: SMTP próprio removido')
        return ir(volta, 'SMTP do órgão removido.', request)
    if acao == 'smtp_testar':
        res = await run_in_threadpool(A.smtp_testar, o, f.get('para', ''), u['nome'])
        return ir(volta, f'Teste: {res}', request)
    raise HTTPException(400)


# ---------- relatório ----------
@r.get('/atendimento/relatorio')
def relatorio(request: Request, ano: int = 0):
    u = exige(request, 'atendimento')
    b = request.state.orgao['banco']
    anos = A.anos(b)
    ano = ano if ano in anos else anos[0]
    fila = db.todos(b, 'SELECT id, tipo, assunto, criado_em, tentativas, enviado_em, erro FROM email_fila ORDER BY id DESC LIMIT 20')
    return T('atendimento_relatorio', request, u, A=A, abas=_abas('relatorio'), ano=ano, anos=anos, e=A.estatisticas(b, ano), rel=A.relatorio_ouvidoria(b, ano),
             vencendo=A.vencendo(b, 7), fila=fila)


# ---------- informações classificadas (LAI arts. 24, 30 e 31) ----------
@r.get('/atendimento/classificadas')
def classificadas(request: Request, id: int = 0):
    u = exige(request, 'atendimento')
    b = request.state.orgao['banco']
    ativas, descl = A.classificadas(b)
    todas = db.todos(b, 'SELECT * FROM info_classificadas ORDER BY desclassificada_em NULLS FIRST, classificada_em DESC')
    x = db.um(b, 'SELECT * FROM info_classificadas WHERE id=%s', (id,)) if id else None
    return T('atendimento_classificadas', request, u, A=A, abas=_abas('classificadas'), todas=todas, x=x, c=A.conf(b))


def _data(s):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


@r.post('/atendimento/classificadas')
async def classificadas_post(request: Request):
    u = exige(request, 'atendimento_config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    volta = '/admin/atendimento/classificadas'
    xid = int(f['id']) if f.get('id', '').isdigit() else None
    if f.get('acao') == 'desclassificar' and xid:
        if not f.get('motivo'):
            return ir(f'{volta}?id={xid}', 'Informe o motivo da desclassificação.', request)
        db.exe(b, 'UPDATE info_classificadas SET desclassificada_em=%s, motivo_desclassificacao=%s, atualizado_por=%s WHERE id=%s AND desclassificada_em IS NULL',
               (_data(f.get('desclassificada_em')) or A.hoje(), f['motivo'][:500], u['nome'], xid))
        auditar(request, f'Informações classificadas: desclassificou o item {xid}')
        return ir(volta, 'Informação desclassificada (aparece por 12 meses na lista pública de desclassificadas).', request)
    grau = f.get('grau')
    em = _data(f.get('classificada_em'))
    if grau not in A.GRAUS or not f.get('assunto') or not f.get('fundamento') or not em:
        return ir(volta + (f'?id={xid}' if xid else ''), 'Preencha grau, assunto, fundamento legal e data da classificação.', request)
    ate = _data(f.get('prazo_ate')) or em + timedelta(days=365 * A.GRAUS[grau][1])
    if ate > em + timedelta(days=365 * A.GRAUS[grau][1] + 7):
        return ir(volta + (f'?id={xid}' if xid else ''), f'O sigilo {A.GRAUS[grau][0].lower()} vale no máximo {A.GRAUS[grau][1]} anos (LAI, art. 24, § 1º).', request)
    if A.tem_cpf(f.get('assunto'), f.get('categoria'), f.get('fundamento')):
        return ir(volta, 'O texto tem um CPF: retire o dado pessoal.', request)
    v = (f.get('referencia', '')[:120], f['assunto'][:500], f.get('categoria', '')[:200], grau, f['fundamento'][:500], em, ate, f.get('autoridade', '')[:200], u['nome'])
    if xid:
        db.exe(b, """UPDATE info_classificadas SET referencia=%s, assunto=%s, categoria=%s, grau=%s, fundamento=%s, classificada_em=%s, prazo_ate=%s, autoridade=%s, atualizado_por=%s
                     WHERE id=%s""", v + (xid,))
    else:
        db.exe(b, 'INSERT INTO info_classificadas (referencia, assunto, categoria, grau, fundamento, classificada_em, prazo_ate, autoridade, atualizado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)', v)
    auditar(request, 'Informações classificadas: ' + ('alterou' if xid else 'cadastrou') + f' ({A.GRAUS[grau][0]})')
    return ir(volta, 'Informação classificada gravada.', request)


# ---------- ficha ----------
def _p(b, pid):
    p = db.um(b, 'SELECT * FROM esic WHERE id=%s', (pid,))
    if not p:
        raise HTTPException(404)
    return p


@r.get('/atendimento/{pid}')
def ficha(request: Request, pid: int):
    u = exige(request, 'atendimento')
    o = request.state.orgao; b = o['banco']
    p = _p(b, pid)
    p['prazo_txt'], p['prazo_cls'] = _prazo(b, p)
    rec = A.recurso_pendente(b, p) if p['situacao'] == 'recurso' else None
    decide = A.pode_decidir(o, p, u, rec) if rec else (False, '')
    parceiros = [x for x in IG.parceiros(o) if IG.par(o, x)]
    return T('atendimento_item', request, u, p=p, A=A, historico=A.historico(b, pid, internos=True), recursos=A.recursos(b, pid), rec=rec, decide=decide,
             ve_identidade=u['perfil'] in PODE['atendimento_identidade'], responde=u['perfil'] in PODE['atendimento_responder'], parceiros=parceiros,
             setores=[x['setor'] for x in db.todos(b, "SELECT DISTINCT setor FROM esic WHERE setor<>'' ORDER BY 1")], abas=_abas('lista'))


@r.post('/atendimento/{pid}')
async def ficha_post(request: Request, pid: int):
    u = exige(request, 'atendimento'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']
    p = _p(b, pid)
    acao = f.get('acao', '')
    volta = f'/admin/atendimento/{pid}'
    if acao != 'decidir' and u['perfil'] not in PODE['atendimento_responder']:
        raise HTTPException(403, 'Ação não permitida para o seu perfil.')
    if acao == 'nota':
        erro, ok = A.nota(o, p, u, f.get('texto', '')), 'Nota registrada (só a equipe vê).'
    elif acao == 'setor':
        erro, ok = A.setor(o, p, u, f.get('setor', '')), 'Setor atualizado.'
    elif acao == 'prorrogar':
        erro, ok = A.prorrogar(o, p, u, f.get('justificativa', '')), 'Prazo prorrogado; o cidadão será avisado.'
    elif acao == 'complemento':
        erro, ok = A.pedir_complemento(o, p, u, f.get('texto', '')), 'Complemento pedido; o prazo fica suspenso até o cidadão responder.'
    elif acao == 'responder':
        erro, ok = A.responder(o, p, u, f.get('resposta', ''), f.get('resultado', ''), f.get('fundamento', '')), 'Resposta registrada; o cidadão será avisado.'
    elif acao == 'decidir':
        erro, ok = A.decidir(o, p, u, f.get('decisao', ''), f.get('resultado', '')), 'Recurso decidido; o cidadão será avisado.'
    elif acao == 'encaminhar':
        destino = next((x for x in IG.parceiros(o) if str(x['id']) == f.get('destino', '')), None)
        erro = await run_in_threadpool(A.encaminhar, o, p, u, destino) if destino else 'Escolha o órgão de destino.'
        ok = 'Encaminhado; o cidadão recebe o novo protocolo e o código.'
    elif acao == 'consultar':
        erro = await run_in_threadpool(A.consultar_encaminhado, o, p) if p['situacao'] == 'encaminhado' else 'Não foi encaminhado.'
        ok = 'Situação no órgão de destino atualizada.'
    else:
        raise HTTPException(400)
    if not erro:
        auditar(request, f"e-SIC/Ouvidoria {p['protocolo']}: {acao}")
    return ir(volta, erro or ok, request)
