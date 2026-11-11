"""Console do gestor da plataforma (servido no domínio de gestão)."""
import re
from datetime import date
from fastapi import APIRouter, Request, HTTPException
from . import config, db
from .catalogo import MOD, MODULOS, serve, BLOCOS, REGIOES
from .security import hash_senha, confere_senha
from .web import templates, ler_form, ir, situacao_contrato, limpar_cache
from . import provision

r = APIRouter(prefix='/_g')

def gestor(request: Request):
    from .acesso import sessao_expirada
    if request.session.get('gestor') and sessao_expirada(request):
        request.session['msg'] = 'Sessão encerrada por inatividade. Entre de novo.'
        raise HTTPException(status_code=307, headers={'Location': '/login'})
    g = request.session.get('gestor')
    if not g:
        raise HTTPException(status_code=307, headers={'Location': '/login'})
    if g.get('trocar') and request.url.path != '/_g/senha':
        raise HTTPException(status_code=307, headers={'Location': '/senha'})
    return g

def log(g, acao):
    db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)', (g['nome'], acao))

def T(nome, request, **kw):
    return templates.TemplateResponse(request, f'console/{nome}.html', dict(request=request, g=request.session.get('gestor'), hoje=config.hoje(), **kw))

def contrato(oid):
    return db.um(db.PLATAFORMA, 'SELECT * FROM contratos WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (oid,))

@r.get('/login')
def login(request: Request):
    from . import acesso as AC
    from .web import tela_acesso
    return T('login', request, govbr=AC.govbr_ativo(), tela=tela_acesso(request, 1, console=True))

@r.get('/esqueci')
def esqueci(request: Request):
    from .web import tela_acesso
    t = tela_acesso(request, console=True); t['titulo'] = 'Esqueci minha senha'
    return templates.TemplateResponse(request, 'acesso/esqueci.html', dict(request=request, tela=t))

def _log_anonimo(acao):
    db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)', ('anônimo', acao[:300]))

@r.post('/login')
async def login_post(request: Request):
    from . import acesso as AC
    f = await ler_form(request)
    c = AC.Conta(request, 'gestor')
    conta, erro = AC.verificar_senha(request, c, f.get('email', ''), f.get('senha', ''))
    if erro:
        _log_anonimo(f"Tentativa de acesso recusada: {f.get('email','')[:60]}")
        return ir('/login', erro, request)
    AC.iniciar_segundo_fator(request, c, conta)
    return ir('/2fa', '', request)

@r.get('/2fa')
def segundo_fator(request: Request):
    from . import acesso as AC
    c = AC.Conta(request, 'gestor'); conta = AC.pre_conta(request, c)
    if not conta:
        return ir('/login', 'Entre com e-mail e senha.', request)
    cad = None if conta['totp_ativo'] else AC.preparar_cadastro(request, c, conta)
    from .web import tela_acesso
    return templates.TemplateResponse(request, 'acesso/2fa.html', dict(request=request, acao='/2fa', cadastro=cad, titulo='Console do gestor', codigos=None, sair='/login', cor='#1B1E30', tela=tela_acesso(request, 2, console=True)))

@r.post('/2fa')
async def segundo_fator_post(request: Request):
    from . import acesso as AC
    f = await ler_form(request)
    c = AC.Conta(request, 'gestor'); conta = AC.pre_conta(request, c)
    if not conta:
        return ir('/login', 'Tempo esgotado. Entre de novo.', request)
    if not conta['totp_ativo']:
        cods = AC.confirmar_cadastro(request, c, conta, f.get('codigo', ''))
        if not cods:
            return ir('/2fa', 'Código não confere. Digite o código atual do aplicativo.', request)
        AC.concluir_login(request, c, c.por_id(conta['id']), 'senha+totp')
        log(request.session['gestor'], 'Cadastrou o segundo fator e entrou no console')
        from .web import tela_acesso
        return templates.TemplateResponse(request, 'acesso/2fa.html', dict(request=request, acao='', cadastro=None, titulo='Console do gestor', codigos=cods, continuar='/senha' if conta['trocar_senha'] else '/', cor='#1B1E30', tela=tela_acesso(request, 2, console=True)))
    ok, msg = AC.conferir_segundo_fator(request, c, conta, f.get('codigo', ''), f.get('recuperacao', ''))
    if not ok:
        ate = AC.registrar_tentativa(request, c, conta, False)
        _log_anonimo(f"Segundo fator incorreto: {conta['email']}")
        if ate:
            request.session.pop('pre', None)
            return ir('/login', AC.msg_bloqueio(ate), request)
        return ir('/2fa', msg, request)
    AC.concluir_login(request, c, conta, 'senha+totp')
    log(request.session['gestor'], 'Entrou no console (senha + segundo fator)')
    return ir('/senha' if conta['trocar_senha'] else '/', msg, request)

@r.get('/govbr')
def govbr(request: Request):
    from . import acesso as AC
    from fastapi.responses import RedirectResponse
    if not AC.govbr_ativo():
        raise HTTPException(404, 'Login gov.br ainda não configurado.')
    return RedirectResponse(AC.govbr_redirecionar(request, AC.Conta(request, 'gestor')), status_code=303)

@r.get('/govbr/retorno')
def govbr_retorno(request: Request, code: str = '', state: str = ''):
    from . import acesso as AC
    c = AC.Conta(request, 'gestor')
    conta, erro = AC.govbr_concluir(request, c, code, state)
    if erro:
        _log_anonimo(f'Login gov.br recusado: {erro[:80]}')
        return ir('/login', erro, request)
    AC.concluir_login(request, c, conta, 'gov.br')
    log(request.session['gestor'], 'Entrou no console (gov.br)')
    return ir('/', '', request)

@r.get('/sair')
def sair(request: Request):
    request.session.pop('gestor', None); request.session.pop('ultimo', None)
    return ir('/login', 'Sessão encerrada.', request)

@r.get('/senha')
def senha(request: Request):
    gestor(request)
    return T('senha', request)

@r.post('/senha')
async def senha_post(request: Request):
    g = gestor(request); f = await ler_form(request)
    atual = db.um(db.PLATAFORMA, 'SELECT senha_hash FROM gestores WHERE id=%s', (g['id'],))
    if not confere_senha(f.get('atual', ''), atual['senha_hash']) or len(f.get('nova', '')) < 12 or f.get('nova') != f.get('conf'):
        return ir('/senha', 'Confira a senha atual; a nova precisa ter 12+ caracteres e ser igual nos dois campos.', request)
    db.exe(db.PLATAFORMA, 'UPDATE gestores SET senha_hash=%s, trocar_senha=FALSE WHERE id=%s', (hash_senha(f['nova']), g['id']))
    g['trocar'] = False; request.session['gestor'] = g
    log(g, 'Trocou a senha')
    return ir('/', 'Senha alterada.', request)

@r.get('/')
def inicio(request: Request):
    gestor(request)
    orgaos = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos ORDER BY id')
    for o in orgaos:
        c = contrato(o['id'])
        o['contrato'] = c
        o['sit'], o['fase'] = situacao_contrato(c) if c else ('Sem contrato', 'impl')
        o['opc'] = db.um(db.PLATAFORMA, 'SELECT count(*) n FROM orgao_modulos WHERE orgao_id=%s AND contratado', (o['id'],))['n']
    return T('inicio', request, orgaos=orgaos, alertas=[o for o in orgaos if o['fase'] in ('alerta', 'carencia', 'fim', 'susp')])

@r.get('/orgao/{oid}')
def orgao(request: Request, oid: int):
    gestor(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    c = contrato(oid)
    sit, fase = situacao_contrato(c)
    adit = db.todos(db.PLATAFORMA, 'SELECT * FROM aditivos WHERE contrato_id=%s ORDER BY id', (c['id'],))
    contratados = {x['chave']: x['contratado'] for x in db.todos(db.PLATAFORMA, 'SELECT * FROM orgao_modulos WHERE orgao_id=%s', (oid,))}
    opc = [dict(chave=m[0], nome=m[1], desc=m[2], depende=m[5], on=contratados.get(m[0], False)) for m in MODULOS if m[3] == 'opc' and serve(m[0], o['tipo'])]
    anos = (c['fim'] - c['inicio']).days / 365.25
    from . import ativacao as AT
    pub = {'dns': AT.dns(o['dominio']), 'ultima': AT.ultima(oid), 'pilotos': {x['slug'] for x in provision.PILOTO}}
    from . import licenca
    lic = licenca.situacao(o)
    lic['doc'] = licenca.documento(o)
    nos_ = db.todos(db.PLATAFORMA, 'SELECT id, nome, ultimo_contato FROM nos WHERE ativo ORDER BY nome')
    lic['ordens'] = db.todos(db.PLATAFORMA, 'SELECT * FROM ordens WHERE orgao_id=%s ORDER BY id DESC LIMIT 8', (oid,))
    return T('orgao', request, o=o, c=c, sit=sit, fase=fase, adit=adit, opc=opc, anos=anos, MOD=MOD, pub=pub, lic=lic, nos=nos_, validade=config.LICENCA_VALIDADE_DIAS)

@r.post('/orgao/{oid}/dominio')
async def orgao_dominio(request: Request, oid: int):
    """Pede ao ativador da VPS para publicar (ou tirar do ar) o domínio do órgão. O console só grava o pedido."""
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    if o['slug'] in {x['slug'] for x in provision.PILOTO}:
        return ir(f'/orgao/{oid}#publicacao', 'Os domínios do piloto são publicados pelo portal-bora.conf, fora do ativador.', request)
    from . import ativacao as AT
    ok, msg = AT.pedir(o, f.get('acao', ''), g['nome'])
    if ok:
        log(g, f"{o['nome']}: pediu {'publicação' if f.get('acao') == 'ativar' else 'retirada'} do domínio {o['dominio']}")
    return ir(f'/orgao/{oid}#publicacao', msg, request)

def _add_meses(d: date, n: int) -> date:
    m = d.month - 1 + n
    a = d.year + m // 12
    m = m % 12 + 1
    import calendar
    return date(a, m, min(d.day, calendar.monthrange(a, m)[1]))

@r.post('/orgao/{oid}')
async def orgao_post(request: Request, oid: int):
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    c = contrato(oid); acao = f.get('acao')
    if acao == 'dados':
        db.exe(db.PLATAFORMA, 'UPDATE contratos SET numero=%s, processo=%s, inicio=%s, fim=%s, carencia_dias=%s WHERE id=%s',
               (f['numero'], f['processo'], f['inicio'], f['fim'], int(f.get('carencia_dias') or 60), c['id']))
        msg = 'Contrato atualizado.'
    elif acao == 'prorrogar':
        _, fase = situacao_contrato(c)
        novo = _add_meses(c['fim'], 12)
        if fase in ('carencia', 'fim'):
            return ir(f'/orgao/{oid}', 'Contrato vencido: a prorrogação precisa ser feita durante a vigência; exige nova contratação.', request)
        if (novo - c['inicio']).days / 365.25 > 10:
            return ir(f'/orgao/{oid}', 'Passaria de 10 anos de vigência (Lei 14.133/2021, art. 107).', request)
        db.exe(db.PLATAFORMA, 'UPDATE contratos SET fim=%s WHERE id=%s', (novo, c['id']))
        db.exe(db.PLATAFORMA, 'INSERT INTO aditivos (contrato_id, descricao, novo_fim) VALUES (%s,%s,%s)', (c['id'], f"Prorrogação até {novo.strftime('%d/%m/%Y')}", novo))
        msg = f"Vigência prorrogada até {novo.strftime('%d/%m/%Y')}."
    elif acao in ('suspender', 'reativar'):
        db.exe(db.PLATAFORMA, 'UPDATE contratos SET suspenso=%s WHERE id=%s', (acao == 'suspender', c['id']))
        msg = 'Licença suspensa.' if acao == 'suspender' else 'Licença reativada.'
    elif acao == 'modulo':
        k = f['chave']
        atual = db.um(db.PLATAFORMA, 'SELECT contratado FROM orgao_modulos WHERE orgao_id=%s AND chave=%s', (oid, k))
        novo = not (atual and atual['contratado'])
        dep = MOD[k][5]
        if novo and dep and not (db.um(db.PLATAFORMA, 'SELECT contratado FROM orgao_modulos WHERE orgao_id=%s AND chave=%s', (oid, dep)) or {}).get('contratado'):
            return ir(f'/orgao/{oid}', f'{MOD[k][1]} depende de {MOD[dep][1]}. Contrate primeiro.', request)
        db.exe(db.PLATAFORMA, 'INSERT INTO orgao_modulos (orgao_id, chave, contratado) VALUES (%s,%s,%s) ON CONFLICT (orgao_id, chave) DO UPDATE SET contratado=EXCLUDED.contratado', (oid, k, novo))
        if not novo:
            for m in MODULOS:
                if m[5] == k:
                    db.exe(db.PLATAFORMA, 'UPDATE orgao_modulos SET contratado=FALSE WHERE orgao_id=%s AND chave=%s', (oid, m[0]))
        msg = f"{MOD[k][1]} {'contratado' if novo else 'desligado do contrato'}."
    else:
        raise HTTPException(400)
    log(g, f"{o['nome']}: {msg}")
    return ir(f'/orgao/{oid}', msg, request)

# ---------- nós (VPS de portais) e licenças — separação gestão × portais, etapa A1 ----------
def _nos_ativos():
    return db.todos(db.PLATAFORMA, 'SELECT id, nome FROM nos WHERE ativo ORDER BY nome')

def _no_da_api(request):
    from . import licenca
    if config.PAPEL == 'no':
        raise HTTPException(404)
    a = request.headers.get('authorization', '')
    return licenca.no_do_token(a[7:].strip() if a[:7].lower() == 'bearer ' else '')

@r.get('/api/no/ordens')
def api_ordens(request: Request):
    """Ordens pendentes do nó do token, assinadas pela gestão."""
    from fastapi.responses import JSONResponse
    from . import ordens
    no = _no_da_api(request)
    if not no:
        return JSONResponse({'erro': 'não autorizado'}, status_code=401, headers={'Cache-Control': 'no-store'})
    db.exe(db.PLATAFORMA, 'UPDATE nos SET ultimo_contato=now() WHERE id=%s', (no['id'],))
    return JSONResponse({'ordens': ordens.para_no(no)}, headers={'Cache-Control': 'no-store'})

@r.post('/api/no/ordens/{oid}')
async def api_ordem_resultado(request: Request, oid: int):
    """O nó devolve o resultado de uma ordem que executou."""
    from fastapi.responses import JSONResponse
    from . import ordens
    no = _no_da_api(request)
    if not no:
        return JSONResponse({'erro': 'não autorizado'}, status_code=401)
    try:
        d = await request.json()
    except Exception:
        return JSONResponse({'erro': 'corpo inválido'}, status_code=400)
    if not ordens.informar(no, oid, bool(d.get('ok')), str(d.get('resultado', ''))[:500]):
        return JSONResponse({'erro': 'ordem não é deste nó'}, status_code=404)
    return JSONResponse({'ok': True})
@r.get('/api/no/licencas')
def api_licencas(request: Request):
    """API para os nós: licenças assinadas dos órgãos hospedados no nó do token. Sem sessão; só o token do nó."""
    from fastapi.responses import JSONResponse
    from . import licenca
    if config.PAPEL == 'no':
        raise HTTPException(404)
    a = request.headers.get('authorization', '')
    no = licenca.no_do_token(a[7:].strip() if a[:7].lower() == 'bearer ' else '')
    if not no:
        return JSONResponse({'erro': 'não autorizado'}, status_code=401, headers={'Cache-Control': 'no-store'})
    d = licenca.entregar(no, ip=(request.headers.get('x-forwarded-for') or (request.client.host if request.client else '')).split(',')[0].strip(),
                         versao=request.headers.get('x-versao', ''))
    return JSONResponse(d, headers={'Cache-Control': 'no-store'})

@r.get('/nos')
def nos(request: Request):
    gestor(request)
    from . import licenca
    imp, pub = licenca.garantir_chaves()
    lista = db.todos(db.PLATAFORMA, """SELECT n.*, (SELECT count(*) FROM orgaos o WHERE o.no_id=n.id) orgaos,
                                     (SELECT count(*) FROM ordens x WHERE x.no_id=n.id AND x.situacao='pendente') pendentes,
                                     (SELECT count(*) FROM ordens x WHERE x.no_id=n.id AND x.situacao='erro') com_erro FROM nos n ORDER BY n.id""")
    return T('nos', request, nos=lista, impressao=imp, publica=pub, validade=config.LICENCA_VALIDADE_DIAS)

@r.post('/nos')
async def nos_post(request: Request):
    g = gestor(request); f = await ler_form(request)
    from . import licenca
    acao = f.get('acao')
    if acao == 'criar':
        nome = (f.get('nome') or '').strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,60}', nome):
            return ir('/nos', 'Nome do nó: letras minúsculas, números, ponto e hífen (ex.: no1.conectatech.tech).', request)
        if db.um(db.PLATAFORMA, 'SELECT 1 FROM nos WHERE nome=%s', (nome,)):
            return ir('/nos', 'Já existe um nó com este nome.', request)
        token = licenca.criar_no(nome)
        log(g, f'Nó {nome} criado (token mostrado uma vez)')
        n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE nome=%s', (nome,))
    elif acao == 'token':
        n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (int(f.get('id') or 0),))
        if not n:
            raise HTTPException(404)
        if f.get('confirmo') != '1':
            return ir('/nos', 'Marque a confirmação: o token antigo deixa de valer na hora e o nó para de receber licenças até o .env ser atualizado.', request)
        token = licenca.novo_token(n['id'])
        log(g, f"Nó {n['nome']}: token trocado (o anterior deixou de valer)")
    else:
        raise HTTPException(400)
    imp, pub = licenca.garantir_chaves()
    r = T('no_token', request, n=n, token=token, gestao=f'https://{config.DOMINIO_GESTAO}', publica=pub, impressao=imp)
    r.headers['Cache-Control'] = 'no-store'
    return r

@r.post('/orgao/{oid}/hospedagem')
async def orgao_hospedagem(request: Request, oid: int):
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    novo = int(f['no_id']) if (f.get('no_id') or '').isdigit() else None
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (novo,)) if novo else None
    if novo and not n:
        raise HTTPException(400)
    if f.get('confirmo') != '1':
        return ir(f'/orgao/{oid}#hospedagem', 'Marque a confirmação para mudar a hospedagem.', request)
    db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (novo, oid))
    limpar_cache()
    msg = f"Hospedagem: {'nó ' + n['nome'] if n else 'esta VPS'}. As licenças passam a ser entregues a quem hospeda o órgão."
    log(g, f"{o['nome']}: {msg}")
    return ir(f'/orgao/{oid}#hospedagem', msg, request)

@r.get('/orgaos/novo')
def novo(request: Request):
    gestor(request)
    from . import cadastro as CD
    return T('novo', request, f={}, erros=[], ufs=CD.UFS, sistemas=CD.SISTEMAS, mods=[m for m in MODULOS if m[3] == 'opc'], cores=CD.COR_PADRAO, nos=_nos_ativos())

@r.get('/orgaos/ibge/{codigo}')
def ibge(request: Request, codigo: str):
    """Município e UF pelo código IBGE (para o formulário de cadastro). Só para gestor logado."""
    from fastapi.responses import JSONResponse
    from . import cadastro as CD
    gestor(request)
    d = CD.consultar_ibge(codigo)
    if not d:
        return JSONResponse({'erro': 'Código IBGE não encontrado (ou o IBGE não respondeu). Confira o código ou preencha o município e a UF.'}, status_code=404)
    return JSONResponse(dict(d, slug_pm=CD.slug_sugerido('executivo', d['municipio']), slug_cm=CD.slug_sugerido('legislativo', d['municipio']),
                             nome_pm=CD.nome_sugerido('executivo', d['municipio']), nome_cm=CD.nome_sugerido('legislativo', d['municipio']), tcesp=CD.slug_municipio(d['municipio'])))

@r.post('/orgaos/novo')
async def novo_post(request: Request):
    """Cadastra o órgão: banco próprio, esquema, identidade, integrações, menus, layout e administrador inicial.
    A senha inicial do administrador é única, aparece UMA vez nesta resposta e não fica gravada em lugar nenhum (só o hash)."""
    g = gestor(request); f = await ler_form(request)
    from . import cadastro as CD
    ocupados = {x['slug'] for x in db.todos(db.PLATAFORMA, 'SELECT slug FROM orgaos')} | {x['dominio'] for x in db.todos(db.PLATAFORMA, 'SELECT dominio FROM orgaos')}
    api = CD.consultar_ibge(re.sub(r'\D', '', f.get('ibge', '')))  # o IBGE manda; sem resposta, valem o município e a UF digitados
    dados, erros = CD.montar(f, api, ocupados)
    no_id = int(f['no_id']) if (f.get('no_id') or '').isdigit() else None
    if no_id and not any(n['id'] == no_id for n in _nos_ativos()):
        erros = ['Nó de hospedagem inválido.']
    if erros:
        return T('novo', request, f=f, erros=erros, ufs=CD.UFS, sistemas=CD.SISTEMAS, mods=[m for m in MODULOS if m[3] == 'opc'], cores=CD.COR_PADRAO, nos=_nos_ativos())
    senha = CD.senha_inicial()
    from . import ordens
    from .security import hash_senha
    try:
        # gestão: órgão, contrato e módulos; quem hospeda (esta VPS na hora, ou o nó pela fila): banco do órgão e administrador
        oid = provision.registrar_controle(dados['slug'], dados['nome'], dados['tipo'], dados['dominio'], dados['banco'], dados['plano'], dados['cor'],
                                           dados['opcionais'], dados['municipio'], dados['ibge'])
        if no_id:
            db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (no_id, oid))
        o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
        carga = {'orgao': {k: o[k] for k in ('id', 'slug', 'nome', 'tipo', 'dominio', 'banco', 'municipio', 'ibge', 'plano', 'cor', 'ativo')},
                 'identidade': dados['identidade'], 'fontes': dados['fontes'], 'email_admin': dados['email_admin'], 'senha_hash': hash_senha(senha)}
        local, res_ordem = ordens.enviar('criar_orgao', carga, orgao=o, no_id=no_id, quem=g['nome'], resumo=f"criar {dados['slug']} ({dados['banco']})")
    except Exception as e:
        return T('novo', request, f=f, erros=[f'Não foi possível criar: {type(e).__name__}: {e}'], ufs=CD.UFS, sistemas=CD.SISTEMAS, mods=[m for m in MODULOS if m[3] == 'opc'], cores=CD.COR_PADRAO, nos=_nos_ativos())
    limpar_cache()
    log(g, f"Cadastrou o órgão {dados['nome']} ({dados['dominio']}, banco {dados['banco']}, IBGE {dados['ibge']}, integrações: {', '.join(sorted(dados['fontes']))})")
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    vizinhos = db.todos(db.PLATAFORMA, 'SELECT nome, dominio FROM orgaos WHERE ibge=%s AND id<>%s', (o['ibge'], oid))
    no_ = db.um(db.PLATAFORMA, 'SELECT nome FROM nos WHERE id=%s', (no_id,)) if no_id else None
    resp = T('criado', request, o=o, dados=dados, senha=senha, vizinhos=vizinhos, sistemas=CD.SISTEMAS, no=no_)
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@r.get('/catalogo')
def catalogo(request: Request):
    gestor(request)
    orgaos = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos ORDER BY id')
    cont = {(x['orgao_id'], x['chave']): x['contratado'] for x in db.todos(db.PLATAFORMA, 'SELECT * FROM orgao_modulos')}
    return T('catalogo', request, mods=MODULOS, orgaos=orgaos, cont=cont, serve=serve)

@r.get('/layout/{oid}')
def layout(request: Request, oid: int):
    gestor(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if o and o.get('no_id'):
        return ir(f'/orgao/{oid}#hospedagem', 'Órgão hospedado em nó: a página inicial é ajustada no painel do órgão (Página inicial). A gestão não acessa o banco do nó.', request)
    bl = db.todos(o['banco'], "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")
    usados = {b['chave'] for b in bl}
    paleta = [(k, v) for k, v in BLOCOS.items() if k not in usados and (v[4] == 'ambos' or v[4] == o['tipo'])]
    return T('layout', request, o=o, bl=[dict(b, info=BLOCOS.get(b['chave'])) for b in bl if b['chave'] in BLOCOS], regioes=REGIOES, reg_nome=dict(REGIOES), paleta=paleta)

@r.post('/layout/{oid}')
async def layout_post(request: Request, oid: int):
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if o and o.get('no_id'):
        return ir(f'/orgao/{oid}#hospedagem', 'Órgão hospedado em nó: a página inicial é ajustada no painel do órgão.', request)
    b = o['banco']; acao = f.get('acao')
    if acao == 'regiao':
        k = db.um(b, 'SELECT chave FROM blocos WHERE id=%s', (int(f['id']),))['chave']
        if f['regiao'] in BLOCOS[k][1] and not BLOCOS[k][3]:
            db.exe(b, 'UPDATE blocos SET regiao=%s WHERE id=%s', (f['regiao'], int(f['id'])))
    elif acao == 'remover':
        k = db.um(b, 'SELECT chave FROM blocos WHERE id=%s', (int(f['id']),))['chave']
        if not BLOCOS[k][3]:
            db.exe(b, 'DELETE FROM blocos WHERE id=%s', (int(f['id']),))
    elif acao == 'adicionar' and f.get('chave') in BLOCOS:
        mx = db.um(b, "SELECT coalesce(max(ordem),0)+1 n FROM blocos WHERE pagina='home'")['n']
        db.exe(b, "INSERT INTO blocos (pagina, chave, regiao, ordem) VALUES ('home',%s,%s,%s) ON CONFLICT DO NOTHING", (f['chave'], BLOCOS[f['chave']][1][0], mx))
    log(g, f"Layout de {o['nome']}: {acao}")
    return ir(f'/layout/{oid}', 'Layout atualizado.', request)

@r.get('/log')
def ver_log(request: Request):
    gestor(request)
    situacao = db.todos(db.LOCAL, """SELECT DISTINCT ON (c.orgao_slug, c.fonte) c.*,
        (SELECT max(fim) FROM coletas v WHERE v.orgao_slug IS NOT DISTINCT FROM c.orgao_slug AND v.fonte=c.fonte AND v.ok) ultima_ok,
        (SELECT count(*) FROM coletas x WHERE x.orgao_slug IS NOT DISTINCT FROM c.orgao_slug AND x.fonte=c.fonte AND NOT x.ok AND x.inicio > now() - interval '24 hours') falhas_24h
        FROM coletas c ORDER BY c.orgao_slug, c.fonte, c.id DESC""")
    situacao.sort(key=lambda x: (x['ok'], x['orgao_slug'] or '', x['fonte']))
    fontes = db.todos(db.PLATAFORMA, 'SELECT o.slug, f.fonte, f.ativo FROM fontes f JOIN orgaos o ON o.id=f.orgao_id ORDER BY o.slug, f.fonte')
    return T('log', request, itens=db.todos(db.PLATAFORMA, 'SELECT * FROM log_console ORDER BY id DESC LIMIT 300'), situacao=situacao, fontes=fontes,
             coletas=db.todos(db.LOCAL, 'SELECT * FROM coletas ORDER BY id DESC LIMIT 80'))

# ---------- Integrações: credenciais de fontes (só gravação) ----------
@r.get('/credenciais')
def credenciais(request: Request):
    gestor(request)
    from . import credenciais as CR
    itens = [dict(chave=k, **v, sit=CR.situacao(k)) for k, v in CR.FONTES.items()]
    return T('credenciais', request, itens=itens, chave_ok=CR.chave_ok())

def _credencial_para_nos(fonte, g, apagar=False):
    """Ordem "credencial" para cada nó ativo: leva o valor CIFRADO (o nó usa a mesma CHAVE_CREDENCIAIS); nunca em claro."""
    from . import ordens
    r_ = None if apagar else db.um(db.LOCAL, 'SELECT dados, configurada_em, configurada_por FROM credenciais_fontes WHERE fonte=%s', (fonte,))
    if not apagar and not r_:
        return 0
    carga = {'fonte': fonte, 'apagar': True} if apagar else {'fonte': fonte, 'dados': r_['dados'], 'configurada_em': r_['configurada_em'].isoformat(), 'configurada_por': r_['configurada_por']}
    n = 0
    for no in _nos_ativos():
        ordens.enviar('credencial', carga, no_id=no['id'], quem=g['nome'], resumo=f"credencial {fonte} {'apagada' if apagar else 'gravada'}")
        n += 1
    return n

@r.post('/credenciais')
async def credenciais_post(request: Request):
    g = gestor(request)
    from fastapi.concurrency import run_in_threadpool
    from . import credenciais as CR
    f = await ler_form(request)
    fonte, acao = f.get('fonte', ''), f.get('acao', '')
    if fonte not in CR.FONTES:
        return ir('/credenciais', 'Fonte desconhecida.', request)
    if acao == 'salvar':
        try:
            r_ = CR.salvar(fonte, f.get('usuario', ''), f.get('senha', ''), g['nome'])
        except CR.SemChave as e:
            return ir('/credenciais', f'Cadastro desligado: {e}.', request)
        except ValueError as e:
            return ir('/credenciais', f'Não gravado: {e}.', request)
        log(g, f'Credencial da fonte {fonte} {r_}')
        nn = _credencial_para_nos(fonte, g)
        return ir('/credenciais', f'Credencial {r_}. O valor não é exibido nem registrado.' + (f' Enviada cifrada a {nn} nó(s).' if nn else ''), request)
    if acao == 'apagar':
        if CR.apagar(fonte):
            log(g, f'Credencial da fonte {fonte} apagada')
            _credencial_para_nos(fonte, g, apagar=True)
            return ir('/credenciais', 'Credencial apagada. A coleta usa a reserva do .env, se houver; senão, fica desligada.', request)
        return ir('/credenciais', 'Não havia credencial cadastrada.', request)
    if acao == 'testar':
        res = await run_in_threadpool(CR.testar, fonte, g['nome'])
        log(g, f'Credencial da fonte {fonte} testada: {res}')
        return ir('/credenciais', f'Teste de conexão: {res}.', request)
    return ir('/credenciais', '', request)


# ---------- Fase 9: aparência da tela de login do console ----------
import re as _re, secrets as _sec
from pathlib import Path as _Path

def _pasta_console():
    p = _Path(config.DADOS_DIR) / '_console'
    p.mkdir(parents=True, exist_ok=True)
    return p

@r.get('/login-fundo/{arquivo}')
def login_fundo(arquivo: str):
    from fastapi.responses import FileResponse
    if not _re.fullmatch(r'[0-9a-f]{32}\.(png|jpg|webp)', arquivo):
        raise HTTPException(404)
    f = _pasta_console() / arquivo
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type={'png': 'image/png', 'jpg': 'image/jpeg', 'webp': 'image/webp'}[arquivo.rsplit('.', 1)[1]], headers={'Cache-Control': 'public, max-age=86400'})

@r.get('/aparencia')
def aparencia(request: Request):
    gestor(request)
    from .web import tela_acesso
    return T('aparencia', request, tela=tela_acesso(request, console=True))

@r.post('/aparencia')
async def aparencia_post(request: Request):
    g = gestor(request); f = await ler_form(request)
    from psycopg.types.json import Jsonb
    from .imagens import validar_upload, LIMITE_UPLOAD
    atual = (db.um(db.LOCAL, "SELECT valor FROM config_console WHERE chave='login'") or {}).get('valor') or {}
    atual['titulo'] = (f.get('titulo') or '').strip()[:120]
    if f.get('acao') == 'remover':
        atual.pop('fundo', None)
    else:
        arq = f.get('arquivo')
        if arq is not None and getattr(arq, 'filename', ''):
            alt = (f.get('credito') or '').strip()
            dados = await arq.read(LIMITE_UPLOAD + 1)
            try:
                ext = validar_upload(dados)
            except ValueError as e:
                return ir('/aparencia', str(e), request)
            nome = f'{_sec.token_hex(16)}.{ext}'
            (_pasta_console() / nome).write_bytes(dados)
            atual['fundo'] = {'url': f'/login-fundo/{nome}', 'credito': alt[:200]}
        if atual.get('fundo'):
            for k in ('foco_x', 'foco_y'):
                v = f.get(k, '50'); atual['fundo'][k] = max(0, min(100, int(v))) if str(v).isdigit() else 50
    db.exe(db.LOCAL, "INSERT INTO config_console (chave, valor) VALUES ('login', %s) ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor", (Jsonb(atual),))
    log(g, 'Aparência da tela de login do console alterada')
    return ir('/aparencia', 'Aparência salva.', request)
