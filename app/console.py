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

@r.get('/convite')
def convite_link(request: Request, t: str = ''):
    """Link do e-mail de convite (sem login). Só encaminha para o painel do órgão quando ele já está publicado e no ar."""
    from fastapi.responses import RedirectResponse
    from .web import tela_acesso
    from . import convites
    c, o, estado = convites.situacao_link(t)
    h = {'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'}
    if estado == 'pronto':
        return RedirectResponse(convites.link_painel(o, t), status_code=303, headers=h)
    tela = tela_acesso(request, console=True); tela['titulo'] = 'Primeiro acesso'
    return templates.TemplateResponse(request, 'acesso/convite.html', dict(request=request, tela=tela, estado=estado, c=c, o=o), headers=h)

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
    pub = {'dns': AT.dns(o['dominio'], AT.ip_do_no(o['no_id']) if o.get('no_id') else None), 'ultima': AT.ultima(oid), 'pilotos': {x['slug'] for x in provision.PILOTO}}
    from . import licenca
    lic = licenca.situacao(o)
    lic['doc'] = licenca.documento(o)
    nos_ = db.todos(db.PLATAFORMA, 'SELECT id, nome, ultimo_contato FROM nos WHERE ativo ORDER BY nome')
    lic['ordens'] = db.todos(db.PLATAFORMA, 'SELECT * FROM ordens WHERE orgao_id=%s ORDER BY id DESC LIMIT 8', (oid,))
    from . import convites, email_saida
    lic['convite'] = convites.ultimo(o)
    lic['email_ok'] = bool(email_saida.config_atual())
    if lic.get('no'):
        n_ = db.um(db.PLATAFORMA, 'SELECT relatorio, relatorio_em FROM nos WHERE id=%s', (o['no_id'],))
        lic['relatorio'] = ((n_ or {}).get('relatorio') or {}).get('orgaos', {}).get(o['slug'])
        lic['relatorio_em'] = (n_ or {}).get('relatorio_em')
    cad = _criacao_pendente(oid)
    from . import mudancas as MU
    mud = MU.ativa(oid)
    mud_tarefas = db.todos(db.PLATAFORMA, 'SELECT t.*, n.nome no_nome FROM tarefas t JOIN nos n ON n.id=t.no_id WHERE t.mudanca_id=%s ORDER BY t.id', (mud['id'],)) if mud else []
    from . import remocoes as RM
    rem = RM.em_andamento(orgao_id=oid) or (lambda x: x if x and x['situacao'] == 'erro' else None)(RM.ultima(orgao_id=oid))
    rem_tarefa = db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE remocao_id=%s ORDER BY id DESC LIMIT 1', (rem['id'],)) if rem else None
    from . import integracao as IG
    IG.garantir_pares()
    integ = IG.pares_do_console(o)
    return T('orgao', request, o=o, c=c, sit=sit, fase=fase, adit=adit, opc=opc, anos=anos, MOD=MOD, pub=pub, lic=lic, nos=nos_, validade=config.LICENCA_VALIDADE_DIAS, integ=integ,
             cad=(cad['payload'].get('identidade') or {}) if cad else None, mud=mud, mud_tarefas=mud_tarefas, mud_destinos=MU.destinos(o), MUD_NOMES=MU.NOMES,
             mud_nos={n['id']: n['nome'] for n in db.todos(db.PLATAFORMA, 'SELECT id, nome FROM nos')}, rem=rem, rem_tarefa=rem_tarefa, REM_NOMES=RM.NOMES)

@r.post('/orgao/{oid}/integracao')
async def orgao_integracao(request: Request, oid: int):
    """Integração entre órgãos do mesmo município (23/11/2026): renovar a chave de um par ou ligar/desligar a conversa.
    Os nós recebem a mudança com o diretório assinado, em até 5 minutos."""
    g = gestor(request); f = await ler_form(request)
    from . import integracao as IG
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    d = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (int(f.get('parceiro') or 0),))
    if not o or not d or d['ibge'] != o['ibge'] or d['id'] == o['id']:
        raise HTTPException(400)
    acao = f.get('acao')
    if acao == 'renovar':
        IG.renovar_par(o['id'], d['id']); msg = f"Chaves da integração com {d['nome']} renovadas. Os nós recebem em até 5 minutos."
    elif acao in ('ligar', 'desligar'):
        IG.ligar_par(o['id'], d['id'], acao == 'ligar'); msg = f"Integração com {d['nome']} {'ligada' if acao == 'ligar' else 'desligada'}."
    else:
        raise HTTPException(400)
    log(g, f"Integração {o['slug']} ↔ {d['slug']}: {acao}")
    return ir(f'/orgao/{oid}#integracao', msg, request)

def _confirma_gestor(request, g, f, oque):
    """Senha + segundo fator do gestor (com bloqueio por tentativas). Devolve a mensagem de recusa ou None."""
    from . import acesso as AC
    from .security import confere_senha
    c = AC.Conta(request, 'gestor'); conta = c.por_id(g['id'])
    if AC.origem_bloqueada(request, c) or AC.bloqueada(conta):
        return 'Muitas tentativas. Aguarde alguns minutos.'
    if not confere_senha(f.get('minha_senha', ''), conta['senha_hash']):
        ate = AC.registrar_tentativa(request, c, conta, False)
        log(g, f'{oque}: confirmação recusada (senha)')
        return AC.msg_bloqueio(ate) if ate else 'Sua senha não confere. Nada foi feito.'
    ok, _ = AC.conferir_segundo_fator(request, c, conta, f.get('codigo', ''))
    if not ok:
        ate = AC.registrar_tentativa(request, c, conta, False)
        log(g, f'{oque}: confirmação recusada (segundo fator)')
        return AC.msg_bloqueio(ate) if ate else 'Código do autenticador incorreto. Nada foi feito.'
    return None

@r.post('/orgao/{oid}/excluir')
async def orgao_excluir(request: Request, oid: int):
    """Excluir o órgão hospedado num nó: backup final no nó, depois apaga do nó e da gestão (fica o registro em Remoções)."""
    g = gestor(request); f = await ler_form(request)
    from . import remocoes as RM
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    volta = f'/orgao/{oid}#excluir'
    if f.get('slug') != o['slug']:
        return ir(volta, f"Para excluir, digite o identificador do órgão ({o['slug']}).", request)
    erro = _confirma_gestor(request, g, f, f"Exclusão do órgão {o['nome']}")
    if erro:
        return ir(volta, erro, request)
    ok, msg = RM.iniciar_orgao(o, g['nome'])
    if ok:
        log(g, f"{o['nome']} ({o['slug']}): exclusão pedida (backup final no nó antes de apagar)")
    return ir(volta, msg, request)

@r.post('/nos/{nid}/excluir')
async def no_excluir(request: Request, nid: int):
    g = gestor(request); f = await ler_form(request)
    from . import remocoes as RM
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,))
    if not n:
        raise HTTPException(404)
    if f.get('nome') != n['nome']:
        return ir('/nos', f"Para excluir o nó, digite o nome dele ({n['nome']}).", request)
    erro = _confirma_gestor(request, g, f, f"Exclusão do nó {n['nome']}")
    if erro:
        return ir('/nos', erro, request)
    ok, msg = RM.iniciar_no(n, g['nome'])
    if ok:
        log(g, f"Nó {n['nome']}: exclusão pedida")
    return ir('/remocoes' if ok else '/nos', msg, request)

@r.get('/remocoes')
def remocoes_tela(request: Request):
    gestor(request)
    from . import remocoes as RM
    RM.avancar_todas()
    lista = db.todos(db.PLATAFORMA, 'SELECT * FROM remocoes ORDER BY id DESC LIMIT 200')
    tar = {t['remocao_id']: t for t in db.todos(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE remocao_id IS NOT NULL ORDER BY id')}
    return T('remocoes', request, lista=lista, tar=tar, NOMES=RM.NOMES)

@r.post('/remocoes/{rid}')
async def remocoes_post(request: Request, rid: int):
    g = gestor(request); f = await ler_form(request)
    from . import remocoes as RM
    if f.get('acao') == 'encerrar':
        ok, msg = RM.encerrar(rid, g['nome'])
    elif f.get('acao') == 'backup_apagado':
        ok, msg = RM.marcar_backup_apagado(rid, g['nome'])
    else:
        raise HTTPException(400)
    if ok:
        log(g, f'Remoção {rid}: {msg}')
    return ir('/remocoes', msg, request)

@r.post('/orgao/{oid}/mudanca')
async def orgao_mudanca(request: Request, oid: int):
    """Mudar o órgão de nó pela gestão (mesma VPS): iniciar, limpar a origem ou desfazer. Ver mudancas.py."""
    g = gestor(request); f = await ler_form(request)
    from . import mudancas as MU
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    volta, acao = f'/orgao/{oid}#mudanca', f.get('acao', '')
    if acao == 'iniciar':
        if f.get('confirmo') != '1':
            return ir(volta, 'Marque a confirmação para começar a mudança.', request)
        ok, msg = MU.iniciar(o, int(f.get('para_no') or 0), g['nome'])
    elif acao == 'limpar':
        if f.get('slug') != o['slug']:
            return ir(volta, f"Para apagar os dados da origem, digite o identificador do órgão ({o['slug']}).", request)
        ok, msg = MU.limpar(oid, g['nome'])
    elif acao == 'desfazer':
        ok, msg = MU.desfazer(oid, g['nome'])
    elif acao == 'atualizar':
        m = MU.ativa(oid)
        if m:
            MU.avancar(m['id'], g['nome'])
        return ir(volta, '', request)
    else:
        raise HTTPException(400)
    if ok:
        log(g, f"{o['nome']}: mudança de nó — {acao} ({msg})")
    return ir(volta, msg, request)

def _criacao_pendente(oid):
    """Ordem criar_orgao ainda na fila do nó: enquanto não for entregue, a identidade inicial ainda pode ser corrigida
    (a ordem só é assinada na entrega, com o conteúdo do momento)."""
    return db.um(db.PLATAFORMA, "SELECT * FROM ordens WHERE orgao_id=%s AND tipo='criar_orgao' AND situacao='pendente' ORDER BY id DESC LIMIT 1", (oid,))

@r.post('/orgao/{oid}/cadastro')
async def orgao_cadastro(request: Request, oid: int):
    """Corrige os dados do cadastro. Nome e cor valem na gestão (console, e-mails, licença). Se o órgão ainda não foi criado
    pelo nó, corrige também a identidade inicial que vai na ordem; depois de criado, a identidade é do órgão (painel → Identidade)."""
    from psycopg.types.json import Jsonb
    from . import cadastro as CD
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    volta = f'/orgao/{oid}#cadastro'
    nome = re.sub(r'\s+', ' ', f.get('nome') or '').strip()
    cor = (f.get('cor') or '').strip()
    if not 3 <= len(nome) <= 160:
        return ir(volta, 'Informe o nome do órgão (3 a 160 caracteres).', request)
    if not CD.COR.match(cor):
        return ir(volta, 'Cor principal inválida: use o formato #RRGGBB.', request)
    mudou = [x for x, a, b in (('nome', o['nome'], nome), ('cor', o['cor'], cor)) if a != b]
    p = _criacao_pendente(oid)
    if p:
        cnpj = (f.get('cnpj') or '').strip()
        if cnpj and not CD.cnpj_valido(cnpj):
            return ir(volta, 'CNPJ inválido (confira os dígitos).', request)
        carga = p['payload']
        ident = carga.setdefault('identidade', {})
        novos = {'nome': nome, 'cor': cor, 'cnpj': CD.cnpj_formatado(cnpj) if cnpj else '', 'endereco': (f.get('endereco') or '').strip()[:300],
                 'telefone': (f.get('telefone') or '').strip()[:60], 'email': (f.get('email') or '').strip()[:120], 'horario': (f.get('horario') or '').strip()[:120]}
        if o['tipo'] != 'executivo':
            novos['nome_curto'] = nome  # na Câmara o nome curto do cabeçalho é o próprio nome
        mudou += [k for k in ('cnpj', 'endereco', 'telefone', 'email', 'horario') if (ident.get(k) or '') != novos[k]]
        ident.update(novos)
        if o['tipo'] == 'executivo' and 'pncp' in (carga.get('fontes') or {}):
            if novos['cnpj']:
                carga['fontes']['pncp']['cnpj'] = novos['cnpj']
        elif o['tipo'] == 'executivo' and novos['cnpj']:
            carga.setdefault('fontes', {})['pncp'] = {'ibge': o['ibge'], 'cnpj': novos['cnpj']}
        carga.setdefault('orgao', {}).update({'nome': nome, 'cor': cor})
        r_ = db.um(db.PLATAFORMA, "UPDATE ordens SET payload=%s WHERE id=%s AND situacao='pendente' RETURNING id", (Jsonb(carga), p['id']))
        if not r_:
            return ir(volta, 'O nó acabou de receber a criação do órgão; nada foi alterado. Recarregue a página.', request)
    if not mudou:
        return ir(volta, 'Nada mudou.', request)
    db.exe(db.PLATAFORMA, 'UPDATE orgaos SET nome=%s, cor=%s WHERE id=%s', (nome, cor, oid))
    limpar_cache()
    log(g, f"{o['nome']}: corrigiu o cadastro ({', '.join(sorted(set(mudou)))})" + (f" → {nome}" if 'nome' in mudou else ''))
    return ir(volta, 'Cadastro corrigido.' + (' A correção vai junto na criação do órgão no nó.' if p else ''), request)

@r.post('/orgao/{oid}/dominio')
async def orgao_dominio(request: Request, oid: int):
    """Pede ao ativador da VPS para publicar (ou tirar do ar) o domínio do órgão. O console só grava o pedido."""
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    if o['slug'] in {x['slug'] for x in provision.PILOTO} and not o.get('no_id'):
        # nesta VPS o piloto segue no portal-bora.conf (feito à mão); hospedado num nó, é publicado pelo ativador do nó como qualquer órgão
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

@r.post('/api/no/relatorio')
async def api_relatorio(request: Request):
    """Relatório técnico do nó (sem dados pessoais); atualiza também os pedidos de domínio dos órgãos do nó."""
    from fastapi.responses import JSONResponse
    from . import relatorio
    no = _no_da_api(request)
    if not no:
        return JSONResponse({'erro': 'não autorizado'}, status_code=401)
    corpo = await request.body()
    if len(corpo) > relatorio.MAX_BYTES:
        return JSONResponse({'erro': 'relatório grande demais'}, status_code=413)
    try:
        import json as _json
        d = _json.loads(corpo)
        if not isinstance(d, dict):
            raise ValueError
        n = relatorio.receber(no, d)
    except ValueError:
        return JSONResponse({'erro': 'relatório inválido'}, status_code=400)
    return JSONResponse({'ok': True, 'ativacoes': n})

@r.get('/api/no/ordens')
def api_ordens(request: Request):
    """Ordens pendentes do nó do token, assinadas pela gestão."""
    from fastapi.responses import JSONResponse
    from . import ordens
    no = _no_da_api(request)
    if not no:
        return JSONResponse({'erro': 'não autorizado'}, status_code=401, headers={'Cache-Control': 'no-store'})
    db.exe(db.PLATAFORMA, 'UPDATE nos SET ultimo_contato=now() WHERE id=%s', (no['id'],))
    try:
        credenciais_que_faltam(no)
    except Exception:  # falha aqui não pode impedir o nó de receber as outras ordens
        pass
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
    d = licenca.entregar(no, ip=config.ip_cliente(request),
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
        inst = (f.get('instancia') or '').strip().lower()
        if inst and not re.fullmatch(r'[a-z0-9]{1,20}', inst):
            return ir('/nos', 'Instância: só letras minúsculas e números, até 20 (ex.: camara). Deixe vazio para a pasta de sempre.', request)
        token = licenca.criar_no(nome, inst)
        log(g, f'Nó {nome} criado' + (f' (instância {inst}: /opt/portal_web-{inst})' if inst else '') + ' (token mostrado uma vez)')
        n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE nome=%s', (nome,))
    elif acao == 'instancia':
        n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (int(f.get('id') or 0),))
        if not n:
            raise HTTPException(404)
        inst = (f.get('instancia') or '').strip().lower()
        if inst and not re.fullmatch(r'[a-z0-9]{1,20}', inst):
            return ir('/nos', 'Instância: só letras minúsculas e números, até 20 (ex.: camara). Vazio = pasta /opt/portal_web.', request)
        db.exe(db.PLATAFORMA, 'UPDATE nos SET instancia=%s WHERE id=%s', (inst, n['id']))
        pasta = f'/opt/portal_web-{inst}' if inst else '/opt/portal_web'
        log(g, f"Nó {n['nome']}: instância {'“' + inst + '”' if inst else 'padrão'} (pasta {pasta}) — vale para os próximos pacotes")
        return ir('/nos', f"Nó {n['nome']}: pasta na VPS agora é {pasta}. Vale para os próximos pacotes (gere de novo em Preparar instalação).", request)
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

@r.post('/orgao/{oid}/convite')
async def orgao_convite(request: Request, oid: int):
    """Novo convite de primeiro acesso para o administrador do órgão (o anterior deixa de valer; a senha atual dele também)."""
    g = gestor(request); f = await ler_form(request)
    from . import convites, ordens, cadastro as CD
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    if not o:
        raise HTTPException(404)
    email = (f.get('email') or '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        return ir(f'/orgao/{oid}#convite', 'Informe o e-mail do administrador.', request)
    if f.get('confirmo') != '1':
        return ir(f'/orgao/{oid}#convite', 'Marque a confirmação: o acesso atual do administrador deixa de valer até ele usar o convite novo.', request)
    cid, cv = convites.novo(o, email, g['nome'])
    try:
        oid_ordem, local, res = ordens.enviar_com_id('convite', dict(cv, orgao_id=oid), orgao=o, no_id=o.get('no_id'), quem=g['nome'], resumo=f'convite para {email}')
    except Exception as e:
        db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='erro', token_cifrado=NULL, mensagem=%s WHERE id=%s", (f'{type(e).__name__}: {str(e)[:200]}', cid))
        return ir(f'/orgao/{oid}#convite', f'Convite não gravado: {e}', request)
    convites.ligar_ordem(cid, oid_ordem)
    convites.tick()
    log(g, f"{o['nome']}: convite de primeiro acesso para {email}")
    c = convites.ultimo(o)
    return ir(f'/orgao/{oid}#convite', 'Convite enviado por e-mail.' if c and c['situacao'] == 'enviado' else f"Convite registrado: {c['mensagem'] if c else ''}", request)

# ---------- e-mail de saída ----------
@r.get('/email')
def email_cfg(request: Request):
    gestor(request)
    from . import email_saida as EM, credenciais
    return T('email', request, cfg=EM.config_atual(), segs=EM.SEGURANCAS, chave_ok=credenciais.chave_ok())

@r.post('/email')
async def email_cfg_post(request: Request):
    g = gestor(request); f = await ler_form(request)
    from . import email_saida as EM, credenciais
    from fastapi.concurrency import run_in_threadpool
    if f.get('acao') == 'testar':
        para = (f.get('para') or '').strip()
        if not EM.EMAIL.match(para):
            return ir('/email', 'Informe para qual e-mail mandar o teste.', request)
        res = await run_in_threadpool(EM.testar, para, g['nome'])
        log(g, f'E-mail de saída testado: {res}')
        return ir('/email', f'Teste: {res}.', request)
    if not credenciais.chave_ok():
        return ir('/email', 'Não gravado: falta a CHAVE_CREDENCIAIS no .env (ela cifra a senha do SMTP).', request)
    d, erros = EM.validar(f)
    if not EM.config_atual() and not d['senha'] and d['usuario']:
        erros.append('Informe a senha do SMTP.')
    if erros:
        return ir('/email', 'Não gravado: ' + ' '.join(erros), request)
    EM.salvar(d, g['nome'])
    log(g, f"E-mail de saída configurado: {d['servidor']}:{d['porta']} ({d['seguranca']}), remetente {d['remetente']}" + (' — senha trocada' if d['senha'] else ''))
    return ir('/email', 'E-mail de saída gravado. A senha não é exibida. Mande um teste para conferir.', request)

# ---------- instalação de nó pelo console (pacotes por link de uso único) ----------
@r.get('/instalar/{token}')
def instalar_baixar(request: Request, token: str):
    """Download de um pacote de instalação (sem login: o nó baixa com curl). Vale uma vez só e vence em 60 minutos."""
    from fastapi.responses import Response, PlainTextResponse
    from . import instalacao as IN
    if config.PAPEL == 'no':
        raise HTTPException(404)
    ip = config.ip_cliente(request)
    try:
        r = IN.usar_link(token, ip)
    except RuntimeError as e:
        return PlainTextResponse(f'Pacote indisponível: {e}\n', status_code=503, headers={'Cache-Control': 'no-store'})
    if not r:
        return PlainTextResponse('Link inválido, já usado ou vencido. Gere outro em Nós e licenças → Preparar instalação.\n', status_code=404, headers={'Cache-Control': 'no-store'})
    tipo, dados, nome = r
    return Response(dados, media_type='application/octet-stream', headers={'Content-Disposition': f'attachment; filename="{nome}"', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

@r.get('/nos/{nid}/instalar')
def instalar(request: Request, nid: int):
    gestor(request)
    from . import instalacao as IN
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,))
    if not n:
        raise HTTPException(404)
    IN.limpar()
    res = IN.preparados(nid, f'https://{config.DOMINIO_GESTAO}/instalar/')
    # outros nós que usam a MESMA pasta: se ficarem na mesma VPS, um substituiria o outro (o instalador recusa; aqui o aviso vem antes)
    mesma_pasta = db.todos(db.PLATAFORMA, "SELECT nome, ultimo_ip, relatorio->>'pasta' pasta FROM nos WHERE id<>%s AND instancia=%s AND ativo ORDER BY nome", (nid, n['instancia']))
    from . import mudancas as MU
    hosts = [x for x in db.todos(db.PLATAFORMA, 'SELECT * FROM nos WHERE ativo AND id<>%s AND instancia<>%s ORDER BY nome', (nid, n['instancia'])) if MU.suporta_tarefas(x)]
    auto = db.todos(db.PLATAFORMA, "SELECT t.*, h.nome host FROM tarefas t JOIN nos h ON h.id=t.no_id WHERE t.tipo='instalar_instancia' AND t.params->>'nome'=%s ORDER BY t.id DESC LIMIT 3", (n['nome'],))
    r = T('instalar', request, n=n, versao=IN.versao(), codigo_ok=IN.codigo_disponivel(), validade=IN.VALIDADE_MIN, res=res, mesma_pasta=mesma_pasta, hosts=hosts, auto=auto)
    r.headers['Cache-Control'] = 'no-store'; r.headers['Referrer-Policy'] = 'no-referrer'
    return r

@r.post('/nos/{nid}/instalar-auto')
async def instalar_auto(request: Request, nid: int):
    """Instala o nó (com instância) SEM TERMINAL: o ativador de outro nó da mesma VPS cria a pasta, copia o código e roda o
    instalador em modo automático (tarefa "instalar_instancia"). Exige a senha e o 2FA do gestor; gera token novo do nó."""
    g = gestor(request); f = await ler_form(request)
    from . import licenca, acesso as AC, credenciais as CR, tarefas as TF, mudancas as MU
    from .security import confere_senha
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,))
    if not n:
        raise HTTPException(404)
    volta = f'/nos/{nid}/instalar#auto'
    if not n['instancia']:
        return ir(volta, 'Defina antes a instância deste nó (Nós e licenças → Mudar a pasta): a VPS já tem um nó na pasta padrão.', request)
    host = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s AND ativo AND id<>%s', (int(f.get('host') or 0), nid))
    if not host or not MU.suporta_tarefas(host) or host['instancia'] == n['instancia']:
        return ir(volta, 'Escolha um nó já instalado na VPS onde este nó vai ficar (na versão nova e com outra pasta).', request)
    if not CR.chave_ok():
        return ir(volta, 'A CHAVE_CREDENCIAIS da gestão não está configurada: não dá para mandar o token cifrado.', request)
    c = AC.Conta(request, 'gestor'); conta = c.por_id(g['id'])
    if AC.origem_bloqueada(request, c) or AC.bloqueada(conta):
        return ir(volta, 'Muitas tentativas. Aguarde alguns minutos.', request)
    if not confere_senha(f.get('minha_senha', ''), conta['senha_hash']):
        ate = AC.registrar_tentativa(request, c, conta, False)
        return ir(volta, AC.msg_bloqueio(ate) if ate else 'Sua senha não confere. Nada foi pedido.', request)
    ok, msg = AC.conferir_segundo_fator(request, c, conta, f.get('codigo', ''))
    if not ok:
        ate = AC.registrar_tentativa(request, c, conta, False)
        return ir(volta, AC.msg_bloqueio(ate) if ate else 'Código do autenticador incorreto. Nada foi pedido.', request)
    token = licenca.novo_token(n['id'])
    tid = TF.criar(host, 'instalar_instancia', {'instancia': n['instancia'], 'nome': n['nome'], 'token': CR.cifrar('no', token)}, g['nome'],
                   resumo=f"instalar o nó {n['nome']} em /opt/portal_web-{n['instancia']}")
    credenciais_que_faltam(n, g['nome'], forcar=True)
    log(g, f"Nó {n['nome']}: instalação pedida ao ativador do nó {host['nome']} (mesma VPS, pasta /opt/portal_web-{n['instancia']}; token novo; tarefa {tid})")
    return ir(volta, f"Pedido enviado ao nó {host['nome']}: em até 5 minutos o nó {n['nome']} aparece instalado (acompanhe abaixo).", request)

@r.post('/nos/{nid}/instalar/cancelar')
async def instalar_cancelar(request: Request, nid: int):
    g = gestor(request); await ler_form(request)
    from . import instalacao as IN
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,))
    if not n:
        raise HTTPException(404)
    q = IN.cancelar(nid)
    if q:
        log(g, f"Instalação do nó {n['nome']}: {q} link(s) cancelado(s)")
    return ir(f'/nos/{nid}/instalar', f'{q} link(s) cancelado(s): não baixam mais.' if q else 'Não havia link válido para cancelar.', request)

@r.post('/nos/{nid}/instalar')
async def instalar_post(request: Request, nid: int):
    """Gera os links dos pacotes. O de segredos exige a senha e o 2FA do gestor e sai cifrado com a senha do pacote (não guardada)."""
    g = gestor(request); f = await ler_form(request)
    from . import instalacao as IN, licenca, acesso as AC
    from .security import confere_senha
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,))
    if not n:
        raise HTTPException(404)
    volta = f'/nos/{nid}/instalar'
    if not IN.codigo_disponivel():
        return ir(volta, 'O código de implantação não está na imagem desta VPS: gere a imagem de novo (implantação) antes de preparar o nó.', request)
    senha_pac, conf = f.get('senha_pacote', ''), f.get('senha_pacote2', '')
    if len(senha_pac) < 12 or senha_pac != conf:
        return ir(volta, 'A senha do pacote precisa ter 12 caracteres ou mais e ser igual nos dois campos.', request)
    c = AC.Conta(request, 'gestor'); conta = c.por_id(g['id'])
    if AC.origem_bloqueada(request, c) or AC.bloqueada(conta):
        return ir(volta, 'Muitas tentativas. Aguarde alguns minutos.', request)
    if not confere_senha(f.get('minha_senha', ''), conta['senha_hash']):
        ate = AC.registrar_tentativa(request, c, conta, False)
        log(g, f"Instalação do nó {n['nome']}: confirmação recusada (senha)")
        return ir(volta, AC.msg_bloqueio(ate) if ate else 'Sua senha não confere. Nada foi gerado.', request)
    ok, msg = AC.conferir_segundo_fator(request, c, conta, f.get('codigo', ''))
    if not ok:
        ate = AC.registrar_tentativa(request, c, conta, False)
        log(g, f"Instalação do nó {n['nome']}: confirmação recusada (segundo fator)")
        return ir(volta, AC.msg_bloqueio(ate) if ate else 'Código do autenticador incorreto. Nada foi gerado.', request)
    token = licenca.novo_token(n['id']) if f.get('novo_token') == '1' else None
    antigos = IN.cancelar(n['id'])  # só um par de links válido por nó
    lote = IN.novo_lote()
    IN.novo_link(n, 'codigo', g['nome'], lote=lote, token_novo=bool(token))
    IN.novo_link(n, 'segredos', g['nome'], IN.cifrar(IN.pacote_segredos(n, token), senha_pac), lote=lote, token_novo=bool(token))
    if token:  # token novo = (re)instalação: o banco do nó pode estar vazio; as credenciais esperam na fila até ele conectar
        credenciais_que_faltam(n, g['nome'], forcar=True)
    log(g, f"Instalação do nó {n['nome']}: pacotes gerados (código {IN.versao()} e segredos cifrados{', com token NOVO do nó' if token else ''}); links de uso único por {IN.VALIDADE_MIN} min"
           + (f'; {antigos} link(s) anterior(es) cancelado(s)' if antigos else ''))
    return ir(f'/nos/{nid}/instalar', 'Pacotes gerados. Os comandos ficam nesta tela enquanto os links valem.' + (' Os links anteriores foram cancelados.' if antigos else ''), request)

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
    if novo != o.get('no_id') and o.get('vhost_ativo'):
        # mover com o domínio no ar deixaria o nó antigo e o novo disputando o mesmo domínio (18/11/2026)
        return ir(f'/orgao/{oid}#hospedagem', 'Tire o domínio do ar antes de mudar a hospedagem (Publicação → Tirar do ar). Depois de mover os dados '
                  '(deploy/no/mover_orgao.sh), mude a hospedagem e publique de novo: o nó novo emite o certificado.', request)
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
    from . import ordens, convites
    try:
        # gestão: órgão, contrato e módulos; quem hospeda (esta VPS na hora, ou o nó pela fila): banco do órgão e administrador
        oid = provision.registrar_controle(dados['slug'], dados['nome'], dados['tipo'], dados['dominio'], dados['banco'], dados['plano'], dados['cor'],
                                           dados['opcionais'], dados['municipio'], dados['ibge'])
        if no_id:
            db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (no_id, oid))
        o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
        # sem senha na tela: o administrador recebe por e-mail um link de primeiro acesso (cria a própria senha e o segundo fator)
        cid, cv = convites.novo(o, dados['email_admin'], g['nome'])
        carga = {'orgao': {k: o[k] for k in ('id', 'slug', 'nome', 'tipo', 'dominio', 'banco', 'municipio', 'ibge', 'plano', 'cor', 'ativo')},
                 'identidade': dados['identidade'], 'fontes': dados['fontes'], 'email_admin': dados['email_admin'], 'convite': cv}
        oid_ordem, local, res_ordem = ordens.enviar_com_id('criar_orgao', carga, orgao=o, no_id=no_id, quem=g['nome'], resumo=f"criar {dados['slug']} ({dados['banco']})")
        convites.ligar_ordem(cid, oid_ordem)
        convites.tick()  # se o domínio já responde e o e-mail de saída está configurado, o convite sai agora
    except Exception as e:
        return T('novo', request, f=f, erros=[f'Não foi possível criar: {type(e).__name__}: {e}'], ufs=CD.UFS, sistemas=CD.SISTEMAS, mods=[m for m in MODULOS if m[3] == 'opc'], cores=CD.COR_PADRAO, nos=_nos_ativos())
    limpar_cache()
    log(g, f"Cadastrou o órgão {dados['nome']} ({dados['dominio']}, banco {dados['banco']}, IBGE {dados['ibge']}, integrações: {', '.join(sorted(dados['fontes']))})")
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
    vizinhos = db.todos(db.PLATAFORMA, 'SELECT nome, dominio FROM orgaos WHERE ibge=%s AND id<>%s', (o['ibge'], oid))
    no_ = db.um(db.PLATAFORMA, 'SELECT nome FROM nos WHERE id=%s', (no_id,)) if no_id else None
    resp = T('criado', request, o=o, dados=dados, convite=convites.ultimo(o), vizinhos=vizinhos, sistemas=CD.SISTEMAS, no=no_)
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
    return T('credenciais', request, itens=itens, chave_ok=CR.chave_ok(), nos=_nos_ativos())

def _carga_credencial(r_):
    return {'fonte': r_['fonte'], 'dados': r_['dados'], 'configurada_em': r_['configurada_em'].isoformat(), 'configurada_por': r_['configurada_por']}

def _credencial_para_nos(fonte, g, apagar=False):
    """Ordem "credencial" para cada nó ativo: leva o valor CIFRADO (o nó usa a mesma CHAVE_CREDENCIAIS); nunca em claro."""
    from . import ordens
    r_ = None if apagar else db.um(db.LOCAL, 'SELECT fonte, dados, configurada_em, configurada_por FROM credenciais_fontes WHERE fonte=%s', (fonte,))
    if not apagar and not r_:
        return 0
    carga = {'fonte': fonte, 'apagar': True} if apagar else _carga_credencial(r_)
    n = 0
    for no in _nos_ativos():
        ordens.enviar('credencial', carga, no_id=no['id'], quem=g['nome'], resumo=f"credencial {fonte} {'apagada' if apagar else 'gravada'}")
        n += 1
    return n

def credenciais_que_faltam(no, quem='plataforma', forcar=False):
    """Manda ao nó (cifradas) as credenciais cadastradas que ele ainda não recebeu: nó novo ou credencial gravada antes de o
    nó existir. Conta como recebida qualquer ordem dessa fonte para o nó criada depois da gravação (mesmo com erro: não
    repete a cada minuto; o botão "Reenviar aos nós" refaz). forcar=True (reinstalação com token novo) manda todas."""
    from . import ordens
    n = 0
    for r_ in db.todos(db.LOCAL, 'SELECT fonte, dados, configurada_em, configurada_por FROM credenciais_fontes ORDER BY fonte'):
        if not forcar and db.um(db.PLATAFORMA, "SELECT 1 FROM ordens WHERE no_id=%s AND tipo='credencial' AND payload->>'fonte'=%s AND criada_em>=%s LIMIT 1",
                                (no['id'], r_['fonte'], r_['configurada_em'])):
            continue
        ordens.enviar('credencial', _carga_credencial(r_), no_id=no['id'], quem=quem, resumo=f"credencial {r_['fonte']} gravada (o nó ainda não tinha)")
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
    if acao == 'reenviar':
        nn = _credencial_para_nos(fonte, g)
        if nn:
            log(g, f'Credencial da fonte {fonte} reenviada (cifrada) a {nn} nó(s)')
        return ir('/credenciais', f'Credencial reenviada cifrada a {nn} nó(s). Cada nó grava em cerca de 1 minuto.' if nn else 'Nada a reenviar (sem credencial ou sem nós ativos).', request)
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
