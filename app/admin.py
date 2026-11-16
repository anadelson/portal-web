"""Painel administrativo de cada órgão (servido em <domínio>/admin)."""
import re, secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from psycopg.types.json import Jsonb
from . import config, db, eleicao, diario as diario_pdf
from .catalogo import MOD, serve, BLOCOS, CLASSES, VEDADAS, PERFIS, PODE, TEMAS
from .security import hash_senha, confere_senha, cpf_hash
from .web import templates, ctx_orgao, ler_form, ir, usuario, exige, auditar, modulos_do_orgao, volta_segura

r = APIRouter(prefix='/_a')

def pendencias(b):
    """Contadores do menu: conteúdos esperando revisão e pedidos do e-SIC/Ouvidoria em aberto."""
    return db.um(b, "SELECT (SELECT count(*) FROM conteudos WHERE situacao='revisao') revisao, (SELECT count(*) FROM esic WHERE situacao <> 'respondido') esic, (SELECT count(*) FROM opinioes WHERE situacao='pendente') + (SELECT count(*) FROM tribuna_inscricoes WHERE situacao='pendente') opinioes")

def ctx(request, u, **kw):
    from . import aprovacao as AP
    o = request.state.orgao; b = o['banco']
    pend = dict(pendencias(b) or {}, **AP.pendentes(b, o))
    c = ctx_orgao(request, u=u, pode=lambda p: u['perfil'] in PODE[p], pend=pend,
                  pode_publicar=lambda mod, autor=None: AP.pode_publicar(b, mod, u, autor), quem_aprova=lambda mod: AP.quem_aprova(b, mod), politica=lambda mod: AP.politica(b, mod), **kw)
    return c

def T(nome, request, u, **kw):
    return templates.TemplateResponse(request, f'admin/{nome}.html', ctx(request, u, **kw))

# ---------- login: senha + segundo fator (TOTP) ou gov.br ----------
from . import acesso as AC
TIPOS_CONTEUDO = ['Notícia', 'Página', 'Banner', 'Documento']  # avisos e similares são Comunicados (Fase 8)
templates.env.globals['TIPOS_CONTEUDO'] = TIPOS_CONTEUDO
templates.env.globals['SIT_COMUNICADO'] = {'rascunho': 'Rascunho', 'revisao': 'Em aprovação', 'devolvido': 'Devolvido', 'publicado': 'Publicado', 'arquivado': 'Arquivado'}

@r.get('/login')
def login(request: Request):
    from .web import tela_acesso
    return templates.TemplateResponse(request, 'admin/login.html', ctx_orgao(request, govbr=AC.govbr_ativo(), tela=tela_acesso(request, 1)))

@r.get('/esqueci')
def esqueci(request: Request):
    from .web import tela_acesso
    t = tela_acesso(request); t['titulo'] = 'Esqueci minha senha'
    return templates.TemplateResponse(request, 'acesso/esqueci.html', ctx_orgao(request, tela=t))

@r.post('/login')
async def login_post(request: Request):
    f = await ler_form(request)
    c = AC.Conta(request, 'usuario')
    conta, erro = AC.verificar_senha(request, c, f.get('email', ''), f.get('senha', ''))
    if erro:
        auditar(request, f"Tentativa de acesso recusada: {f.get('email','')[:60]}", 'anônimo')
        return ir('/admin/login', erro, request)
    AC.iniciar_segundo_fator(request, c, conta)
    return ir('/admin/2fa', '', request)

# ---------- primeiro acesso pelo convite (link de uso único enviado por e-mail) ----------
@r.get('/primeiro-acesso')
def primeiro_acesso(request: Request, t: str = ''):
    from .web import tela_acesso
    from . import convites
    conta = convites.conta_do_token(request.state.orgao['banco'], t)
    tela = tela_acesso(request, 1); tela['titulo'] = 'Primeiro acesso'
    return templates.TemplateResponse(request, 'acesso/primeiro.html', ctx_orgao(request, tela=tela, conta=conta, token=t if conta else '', minimo=12),
                                      headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})

@r.post('/primeiro-acesso')
async def primeiro_acesso_post(request: Request):
    f = await ler_form(request)
    from . import convites
    from .security import hash_senha
    c = AC.Conta(request, 'usuario')
    if AC.origem_bloqueada(request, c):
        return ir('/admin/login', 'Muitas tentativas a partir desta conexão. Aguarde alguns minutos.', request)
    t = f.get('t', '')
    conta = convites.conta_do_token(request.state.orgao['banco'], t)
    if not conta:
        AC.registrar_tentativa(request, c, None, False)
        auditar(request, 'Primeiro acesso recusado: link inválido, usado ou vencido', 'anônimo')
        return ir('/admin/primeiro-acesso', 'Link inválido, já usado ou vencido. Peça um novo convite à equipe que administra a plataforma.', request)
    nova = f.get('nova', '')
    if len(nova) < 12 or nova != f.get('conf'):
        return ir(f'/admin/primeiro-acesso?t={t}', 'A senha precisa ter 12 caracteres ou mais e ser igual nos dois campos.', request)
    if nova.lower() in (conta['email'] or '').lower() or len(set(nova)) < 5:
        return ir(f'/admin/primeiro-acesso?t={t}', 'Escolha uma senha menos previsível (não use o e-mail nem repita poucos caracteres).', request)
    convites.usar(request.state.orgao['banco'], conta, hash_senha(nova))
    auditar(request, f"Primeiro acesso pelo convite: senha criada por {conta['email']}", conta['nome'])
    AC.iniciar_segundo_fator(request, c, c.por_id(conta['id']))
    return ir('/admin/2fa', 'Senha criada. Agora cadastre o segundo fator no aplicativo autenticador do celular.', request)

@r.get('/2fa')
def segundo_fator(request: Request):
    c = AC.Conta(request, 'usuario'); conta = AC.pre_conta(request, c)
    if not conta:
        return ir('/admin/login', 'Entre com e-mail e senha.', request)
    cad = None if conta['totp_ativo'] else AC.preparar_cadastro(request, c, conta)
    from .web import tela_acesso
    return templates.TemplateResponse(request, 'acesso/2fa.html', ctx_orgao(request, acao='/admin/2fa', cadastro=cad, titulo='Painel administrativo', codigos=None, sair='/admin/login', tela=tela_acesso(request, 2)))

@r.post('/2fa')
async def segundo_fator_post(request: Request):
    f = await ler_form(request)
    c = AC.Conta(request, 'usuario'); conta = AC.pre_conta(request, c)
    if not conta:
        return ir('/admin/login', 'Tempo esgotado. Entre de novo.', request)
    if not conta['totp_ativo']:
        cods = AC.confirmar_cadastro(request, c, conta, f.get('codigo', ''))
        if not cods:
            return ir('/admin/2fa', 'Código não confere. Confira o horário do celular e digite o código atual do aplicativo.', request)
        AC.concluir_login(request, c, c.por_id(conta['id']), 'senha+totp')
        auditar(request, 'Cadastrou o segundo fator (autenticador) e entrou no painel')
        from .web import tela_acesso
        return templates.TemplateResponse(request, 'acesso/2fa.html', ctx_orgao(request, acao='', cadastro=None, titulo='Painel administrativo', codigos=cods, continuar='/admin/senha' if conta['trocar_senha'] else '/admin/', tela=tela_acesso(request, 2)))
    ok, msg = AC.conferir_segundo_fator(request, c, conta, f.get('codigo', ''), f.get('recuperacao', ''))
    if not ok:
        ate = AC.registrar_tentativa(request, c, conta, False)
        auditar(request, f"Segundo fator incorreto: {conta['email']}", 'anônimo')
        if ate:
            request.session.pop('pre', None)
            return ir('/admin/login', AC.msg_bloqueio(ate), request)
        return ir('/admin/2fa', msg, request)
    AC.concluir_login(request, c, conta, 'senha+totp')
    auditar(request, 'Entrou no painel (senha + segundo fator)', conta['nome'])
    return ir('/admin/senha' if conta['trocar_senha'] else '/admin/', msg, request)

@r.get('/govbr')
def govbr(request: Request):
    if not AC.govbr_ativo():
        raise HTTPException(404, 'Login gov.br ainda não configurado para este órgão.')
    from fastapi.responses import RedirectResponse
    return RedirectResponse(AC.govbr_redirecionar(request, AC.Conta(request, 'usuario')), status_code=303)

@r.get('/govbr/retorno')
def govbr_retorno(request: Request, code: str = '', state: str = ''):
    c = AC.Conta(request, 'usuario')
    conta, erro = AC.govbr_concluir(request, c, code, state)
    if erro:
        auditar(request, f'Login gov.br recusado: {erro[:80]}', 'anônimo')
        return ir('/admin/login', erro, request)
    AC.concluir_login(request, c, conta, 'gov.br')
    auditar(request, 'Entrou no painel (gov.br)', conta['nome'])
    return ir('/admin/', '', request)

@r.get('/sair')
def sair(request: Request):
    request.session.pop('u', None); request.session.pop('ultimo', None)
    return ir('/admin/login', 'Sessão encerrada.', request)

@r.get('/senha')
def senha(request: Request):
    u = exige(request)
    return T('senha', request, u)

@r.post('/senha')
async def senha_post(request: Request):
    u = exige(request); f = await ler_form(request)
    if len(f.get('nova', '')) < 10 or f.get('nova') != f.get('conf'):
        return ir('/admin/senha', 'A nova senha precisa ter 10 caracteres ou mais e ser igual nos dois campos.', request)
    b = request.state.orgao['banco']
    atual = db.um(b, 'SELECT senha_hash FROM usuarios WHERE id=%s', (u['id'],))
    if not confere_senha(f.get('atual', ''), atual['senha_hash']):
        return ir('/admin/senha', 'Senha atual incorreta.', request)
    db.exe(b, 'UPDATE usuarios SET senha_hash=%s, trocar_senha=FALSE WHERE id=%s', (hash_senha(f['nova']), u['id']))
    u['trocar'] = False; request.session['u'] = u
    auditar(request, 'Trocou a própria senha')
    return ir('/admin/', 'Senha alterada.', request)

# ---------- visão geral ----------
@r.get('/')
def painel(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    k = db.um(b, """SELECT count(*) FILTER (WHERE situacao='revisao') revisao, count(*) FILTER (WHERE situacao='devolvido') devolvido,
        count(*) FILTER (WHERE situacao='agendado') agendado, count(*) FILTER (WHERE situacao='publicado') publicado,
        count(*) FILTER (WHERE situacao IN ('publicado','agendado') AND classe = ANY(%s) AND excecao_eleitoral='') vedados FROM conteudos""", (list(VEDADAS),))
    sic = db.um(b, "SELECT count(*) FILTER (WHERE situacao NOT IN ('respondido')) abertos FROM esic")
    log = db.todos(b, 'SELECT * FROM auditoria ORDER BY id DESC LIMIT 8')
    from . import avisos
    return T('painel', request, u, k=k, sic=sic, log=log, aviso_tv=avisos.transmissoes(request.state.orgao, modulos_do_orgao(request.state.orgao)))

# ---------- conteúdos ----------
@r.get('/conteudos')
def conteudos(request: Request, sit: str = ''):
    u = exige(request)
    b = request.state.orgao['banco']
    # "Todos" = tudo menos o arquivado; arquivado só na aba "Arquivado"
    itens = db.todos(b, 'SELECT * FROM conteudos ' + ('WHERE situacao=%s ' if sit else "WHERE situacao<>'arquivado' ") + 'ORDER BY atualizado_em DESC', (sit,) if sit else ())
    for c in itens:
        c['suspenso'] = eleicao.suspenso(c, b)
    return T('conteudos', request, u, itens=itens, sit=sit)

def _secretarias_ativas(request):
    try:
        return db.todos(request.state.orgao['banco'], 'SELECT id, nome FROM secretarias WHERE ativa ORDER BY nome')
    except Exception:
        return []

@r.get('/conteudos/novo')
def conteudo_novo(request: Request):
    u = exige(request, 'editar')
    return T('conteudo', request, u, c=None, versoes=[], secretarias=_secretarias_ativas(request))

@r.get('/conteudos/{cid}')
def conteudo_ver(request: Request, cid: int):
    u = exige(request)
    b = request.state.orgao['banco']
    c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,))
    if not c:
        raise HTTPException(404)
    return T('conteudo', request, u, c=c, versoes=db.todos(b, 'SELECT * FROM conteudo_versoes WHERE conteudo_id=%s ORDER BY id DESC', (cid,)), secretarias=_secretarias_ativas(request))

@r.post('/conteudos/salvar')
async def conteudo_salvar(request: Request):
    u = exige(request); f = await ler_form(request)
    b = request.state.orgao['banco']
    acao = f.get('acao')
    cid = int(f['id']) if f.get('id') else None
    c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,)) if cid else None
    pode = lambda p: u['perfil'] in PODE[p]
    if f.get('classe') not in CLASSES:
        return ir(f"/admin/conteudos/{cid or 'novo'}", 'Escolha a classificação eleitoral.', request)
    pub = f.get('publicar_em') or None
    tirar = f.get('tirar_em') or None
    from . import aprovacao as AP
    direto = AP.pode_publicar(b, 'conteudos', u, c['autor'] if c else u['nome'])
    if acao == 'publicar' and not direto:  # sem permissão de publicar direto: vai para aprovação
        acao = 'revisao'
    if acao in ('rascunho', 'revisao', 'publicar'):
        if not pode('editar'):
            raise HTTPException(403)
        if c and c['situacao'] in ('publicado', 'agendado', 'arquivado') and not direto:
            raise HTTPException(403)
        if not f.get('titulo'):
            return ir(f"/admin/conteudos/{cid or 'novo'}", 'Informe o título.', request)
        volta = f"/admin/conteudos/{cid or 'novo'}"
        tipo = f.get('tipo', 'Notícia')
        if tipo not in TIPOS_CONTEUDO and not (c and c['tipo'] == tipo):
            return ir(volta, 'Tipo inválido. Avisos, convocações, convites, notas oficiais e editais de chamamento são cadastrados em Comunicados.', request)
        # imagem: foto enviada (capa da notícia, alt obrigatório) ou foto de tema (cartões de serviço)
        img, alt = (f.get('imagem', '') if f.get('imagem', '') in TEMAS else ''), ''
        arq = f.get('capa')
        if c and (c['imagem'] or '').startswith('/') and f.get('remover_capa') != '1':
            img, alt = c['imagem'], f.get('imagem_alt', '').strip() or c['imagem_alt']
        if arq is not None and getattr(arq, 'filename', ''):
            try:
                img = await salvar_midia(request, u, arq, 'noticia', f.get('imagem_alt', '').strip(), f.get('imagem_credito', '').strip())
            except ValueError as e:
                return ir(volta, str(e), request)
            alt = f.get('imagem_alt', '').strip()
        foco = lambda k: max(0, min(100, int(f.get(k) or 50))) if str(f.get(k) or '50').isdigit() else 50
        try:
            from .web import data_hora_form
            pub_em = data_hora_form(f)
        except ValueError:
            return ir(volta, 'Data e hora da publicação inválidas.', request)
        destaque = f.get('destaque') == '1' and tipo == 'Notícia'
        from . import editor as ED
        html, texto = '', f.get('texto', '')
        if (f.get('html') or '').strip():
            html, probs = ED.limpar(f['html'])
            if probs:
                return ir(volta, ' '.join(probs), request)
            texto = ED.texto(html)
        guarda = 'rascunho' if acao == 'publicar' else acao  # "publicar": salva e publica logo abaixo (mesma regra da aprovação)
        vals = (tipo, f.get('secao', 'Notícias'), f['titulo'], f.get('resumo', ''), texto, html, f['classe'], guarda, pub, tirar, img, alt[:300], foco('foco_x'), foco('foco_y'), destaque, pub_em)
        if c:
            db.exe(b, 'UPDATE conteudos SET tipo=%s, secao=%s, titulo=%s, resumo=%s, texto=%s, html=%s, classe=%s, situacao=%s, publicar_em=%s, tirar_em=%s, imagem=%s, imagem_alt=%s, foco_x=%s, foco_y=%s, destaque=%s, publicado_em=%s, atualizado_em=now() WHERE id=%s', vals + (cid,))
        else:
            cid = db.exe(b, 'INSERT INTO conteudos (tipo, secao, titulo, resumo, texto, html, classe, situacao, publicar_em, tirar_em, imagem, imagem_alt, foco_x, foco_y, destaque, publicado_em, autor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (u['nome'],))['id']
        sec_id = int(f['secretaria_id']) if str(f.get('secretaria_id', '')).isdigit() else None
        db.exe(b, 'UPDATE conteudos SET secretaria_id=%s WHERE id=%s', (sec_id, cid))
        if destaque:  # uma notícia em destaque por vez
            db.exe(b, 'UPDATE conteudos SET destaque=FALSE WHERE destaque AND id<>%s', (cid,))
        obs = 'Salvou rascunho' if acao == 'rascunho' else 'Enviou para aprovação'
        if acao == 'publicar':
            c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,))
    if acao in ('aprovar', 'devolver', 'arquivar', 'publicar'):
        if not c or not AP.pode_publicar(b, 'conteudos', u, c['autor']):
            raise HTTPException(403)
        if acao in ('aprovar', 'publicar'):
            if f['classe'] in VEDADAS and eleicao.em_defeso(b) and eleicao.conf(b).get('bloquear', True) and not c['excecao_eleitoral']:
                return ir(f'/admin/conteudos/{cid}', 'Período eleitoral: esta classificação não pode ser publicada até o fim do defeso.', request)
            nova = 'agendado' if pub and date.fromisoformat(pub) > config.hoje() else 'publicado'
            db.exe(b, 'UPDATE conteudos SET situacao=%s, classe=%s, publicar_em=coalesce(%s::date, %s::date), tirar_em=%s, publicado_em=coalesce(publicado_em, CASE WHEN %s::date IS NULL THEN now() ELSE %s::date + time \'08:00\' END), atualizado_em=now() WHERE id=%s',
                   (nova, f['classe'], pub, config.hoje(), tirar, pub, pub, cid))
            obs = {('publicar', 'publicado'): 'Publicou', ('publicar', 'agendado'): 'Agendou a publicação',
                   ('aprovar', 'publicado'): 'Aprovou e publicou', ('aprovar', 'agendado'): 'Aprovou e agendou'}[(acao, nova)]
        elif acao == 'devolver':
            if not f.get('comentario'):
                return ir(f'/admin/conteudos/{cid}', 'Para devolver, escreva o comentário para o autor.', request)
            db.exe(b, "UPDATE conteudos SET situacao='devolvido', comentario=%s, atualizado_em=now() WHERE id=%s", (f['comentario'], cid))
            obs = 'Devolveu ao autor'
        else:
            db.exe(b, "UPDATE conteudos SET situacao='arquivado', atualizado_em=now() WHERE id=%s", (cid,))
            obs = 'Arquivou (tirou do ar)'
    elif acao not in ('rascunho', 'revisao'):
        raise HTTPException(400)
    snap = db.um(b, 'SELECT titulo, resumo, texto, html, imagem, imagem_alt, classe FROM conteudos WHERE id=%s', (cid,))
    db.exe(b, 'INSERT INTO conteudo_versoes (conteudo_id, quem, obs, dados) VALUES (%s,%s,%s,%s)', (cid, u['nome'], obs, Jsonb(snap) if snap else None))
    auditar(request, f"{obs}: {f.get('titulo') or (c and c['titulo'])}")
    return ir('/admin/conteudos', obs + '.', request)

# ---------- página inicial ----------
@r.get('/pagina-inicial')
def pagina_inicial(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    mods = modulos_do_orgao(request.state.orgao)
    bl = [dict(x, info=BLOCOS.get(x['chave'])) for x in db.todos(b, "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")]
    from .catalogo import LARGURA, REGIOES
    return T('pagina_inicial', request, u, blocos=[x for x in bl if x['info']], mods=mods, largura=LARGURA, regioes=dict(REGIOES))

@r.post('/pagina-inicial')
async def pagina_inicial_post(request: Request):
    """Sem JS: cada botão (subir:ID, descer:ID, visivel:ID) salva na hora. Com JS: "salvar" grava a ordem e a exibição de uma vez."""
    u = exige(request, 'config')
    form = await request.form()
    if form.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    b = request.state.orgao['banco']
    bl = db.todos(b, "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")
    por_id = {x['id']: x for x in bl}
    acao, _, alvo = (form.get('acao') or '').partition(':')
    if acao == 'salvar':
        ids = [int(x) for x in form.getlist('ordem') if x.isdigit() and int(x) in por_id]
        if sorted(ids) != sorted(por_id):
            return ir('/admin/pagina-inicial', 'A lista mudou enquanto você editava. Confira e salve de novo.', request)
        regioes = [por_id[i]['regiao'] for i in ids]
        if regioes != [x['regiao'] for x in bl]:  # só se reordena dentro da mesma região
            return ir('/admin/pagina-inicial', 'Os blocos só mudam de posição dentro da mesma região.', request)
        vis = {int(x) for x in form.getlist('visivel') if x.isdigit()}
        mudou = []
        for k, i in enumerate(ids):
            v = True if BLOCOS[por_id[i]['chave']][3] else (i in vis)
            if por_id[i]['ordem'] != k + 1 or por_id[i]['visivel'] != v:
                db.exe(b, 'UPDATE blocos SET ordem=%s, visivel=%s WHERE id=%s', (k + 1, v, i)); mudou.append(BLOCOS[por_id[i]['chave']][0])
        auditar(request, 'Alterou a página inicial (ordem e exibição): ' + (', '.join(mudou) or 'sem mudança'))
        return ir('/admin/pagina-inicial', 'Página inicial salva.' if mudou else 'Nada mudou.', request)
    if not alvo.isdigit() or int(alvo) not in por_id:
        raise HTTPException(400)
    i = next(k for k, x in enumerate(bl) if x['id'] == int(alvo))
    info = BLOCOS[bl[i]['chave']]
    if acao == 'visivel' and not info[3]:
        db.exe(b, 'UPDATE blocos SET visivel = NOT visivel WHERE id=%s', (bl[i]['id'],))
    elif acao in ('subir', 'descer'):
        j = i - 1 if acao == 'subir' else i + 1
        if 0 <= j < len(bl) and bl[j]['regiao'] == bl[i]['regiao']:
            db.exe(b, 'UPDATE blocos SET ordem=%s WHERE id=%s', (bl[j]['ordem'], bl[i]['id']))
            db.exe(b, 'UPDATE blocos SET ordem=%s WHERE id=%s', (bl[i]['ordem'], bl[j]['id']))
    auditar(request, f'Alterou a página inicial: {info[0]} ({acao})')
    return ir('/admin/pagina-inicial', 'Página inicial atualizada.', request)

# ---------- política de aprovação para publicar ----------
def _aprovadores_possiveis(b):
    from . import aprovacao as AP
    return db.todos(b, "SELECT id, nome, perfil FROM usuarios WHERE situacao='ativo' AND perfil = ANY(%s) ORDER BY nome", (AP.PERFIS_APROVADORES,))

@r.get('/aprovacao')
def aprovacao(request: Request):
    u = exige(request, 'config')
    from . import aprovacao as AP
    o = request.state.orgao; b = o['banco']
    return T('aprovacao', request, u, modulos=AP.modulos(o), pol=AP.todas(b, o), perfis_aprov=AP.PERFIS_APROVADORES, pessoas=_aprovadores_possiveis(b), regras=AP.REGRAS_PROPRIAS)

@r.post('/aprovacao')
async def aprovacao_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    from . import aprovacao as AP
    o = request.state.orgao; b = o['banco']
    try:
        nova = AP.validar(f, o, [x['id'] for x in _aprovadores_possiveis(b)])
    except ValueError as e:
        return ir('/admin/aprovacao', str(e), request)
    atual = db.cfg(b, 'aprovacao', {}) or {}
    db.set_cfg(b, 'aprovacao', dict(atual, **nova))
    auditar(request, 'Aprovação para publicar: ' + '; '.join(f"{AP.NOMES[k]} = {AP.quem_aprova(b, k)}" + (' (quem escreveu não aprova)' if v['outro_aprova'] else '') for k, v in nova.items())[:900])
    return ir('/admin/aprovacao', 'Política de aprovação salva. Vale a partir de agora para tudo o que for publicado.', request)

# ---------- funcionalidades ----------
@r.get('/funcionalidades')
def funcionalidades(request: Request):
    u = exige(request)
    o = request.state.orgao
    from . import licenca
    doc = licenca.vigente(o)
    contratados = set(doc['modulos']) if doc else set()
    ligados = db.cfg(o['banco'], 'modulos_ligados', {}) or {}
    lista = []
    for k, m in MOD.items():
        if not serve(k, o['tipo']):
            continue
        disponivel = m[3] != 'opc' or k in contratados
        lista.append({'chave': k, 'nome': m[1], 'desc': m[2], 'oferta': m[3], 'disponivel': disponivel, 'ligado': m[3] == 'obr' or (disponivel and ligados.get(k, True))})
    return T('funcionalidades', request, u, lista=lista, oculto=bool(db.cfg(o['banco'], 'portal_oculto', False)))

@r.post('/funcionalidades')
async def funcionalidades_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    o = request.state.orgao; k = f.get('chave', '')
    if k == '_visibilidade':  # portal oculto enquanto é configurado (só quem entrou no painel deste órgão vê o portal)
        oculto = f.get('oculto') == '1'
        db.set_cfg(o['banco'], 'portal_oculto', oculto)
        from .web import limpar_cache_oculto
        limpar_cache_oculto(o['slug'])
        auditar(request, 'Visibilidade do portal: ' + ('OCULTO (só a equipe com o painel aberto vê)' if oculto else 'PUBLICADO (aberto ao público)'))
        return ir('/admin/funcionalidades', 'Portal oculto: só a equipe, com o painel aberto, vê o portal.' if oculto else 'Portal publicado: aberto ao público.', request)
    if k not in MOD or MOD[k][3] == 'obr':
        raise HTTPException(400)
    lig = db.cfg(o['banco'], 'modulos_ligados', {}) or {}
    lig[k] = not lig.get(k, True)
    db.set_cfg(o['banco'], 'modulos_ligados', lig)
    auditar(request, f"{'Ligou' if lig[k] else 'Desligou'} a funcionalidade {MOD[k][1]}")
    return ir('/admin/funcionalidades', f"{MOD[k][1]} {'ligada' if lig[k] else 'desligada'}.", request)

# ---------- período eleitoral ----------
@r.get('/eleicao')
def eleicao_ver(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    imp = db.todos(b, "SELECT * FROM conteudos WHERE situacao IN ('publicado','agendado') AND classe = ANY(%s) ORDER BY id", (list(VEDADAS),))
    return T('eleicao', request, u, conf=eleicao.conf(b), imp=imp, ativo=eleicao.em_defeso(b))

@r.post('/eleicao')
async def eleicao_post(request: Request):
    u = exige(request); f = await ler_form(request)
    b = request.state.orgao['banco']
    c = eleicao.conf(b); acao = f.get('acao')
    if acao == 'salvar' and u['perfil'] in PODE['config'] and c['plano'] != 'aprovado':
        for k in ('nome', 'inicio', 'fim'):
            if f.get(k):
                c[k] = f[k]
        for k in ('trocar_logo', 'ocultar_redes', 'aviso', 'bloquear', 'restaurar'):
            c[k] = f.get(k) == 'on'
        msg = 'Plano salvo.'
    elif acao == 'enviar' and u['perfil'] in PODE['config']:
        c['plano'] = 'enviado'; msg = 'Plano enviado para a Procuradoria.'
    elif acao in ('aprovar', 'devolver') and u['perfil'] in PODE['eleicao_aprovar'] and c['plano'] == 'enviado':
        c['plano'] = 'aprovado' if acao == 'aprovar' else 'rascunho'; msg = 'Plano ' + ('aprovado.' if acao == 'aprovar' else 'devolvido.')
    elif acao == 'reabrir' and u['perfil'] in PODE['config']:
        c['plano'] = 'rascunho'; msg = 'Plano reaberto.'
    elif acao == 'excecao' and u['perfil'] in PODE['eleicao_aprovar'] and f.get('decisao'):
        db.exe(b, 'UPDATE conteudos SET excecao_eleitoral=%s WHERE id=%s', (f['decisao'][:200], int(f['id'])))
        auditar(request, f"Registrou exceção eleitoral ({f['decisao'][:60]}) no conteúdo {f['id']}")
        return ir('/admin/eleicao', 'Exceção registrada.', request)
    else:
        raise HTTPException(403, 'Ação não permitida para o seu perfil.')
    db.set_cfg(b, 'eleicao', c)
    auditar(request, f'Período eleitoral: {msg}')
    return ir('/admin/eleicao', msg, request)

# ---------- e-SIC e Ouvidoria ----------
def prazo(p):
    if p['situacao'] == 'respondido':
        return ('Concluído', '')
    if p['situacao'] == 'recurso':
        return ('Decidir em até 5 dias', 'alerta')
    dias = (20 if p['tipo'] == 'pedido' else 30) + (10 if p['tipo'] == 'pedido' and p['situacao'] == 'prorrogado' else 0)
    lim = p['recebido'] + timedelta(days=dias)
    falta = (lim - config.hoje()).days
    return (f"{'vencido há ' + str(-falta) + ' dia(s)' if falta < 0 else 'vence hoje' if falta == 0 else 'faltam ' + str(falta) + ' dia(s)'} ({lim.strftime('%d/%m/%Y')})", 'erro' if falta <= 5 else '')

@r.get('/atendimento')
def atendimento(request: Request):
    u = exige(request, 'atendimento')
    itens = db.todos(request.state.orgao['banco'], 'SELECT * FROM esic ORDER BY (situacao=%s), recebido', ('respondido',))
    for p in itens:
        p['prazo'], p['prazo_cls'] = prazo(p)
    return T('atendimento', request, u, itens=itens)

@r.get('/atendimento/{pid}')
def atendimento_ver(request: Request, pid: int):
    u = exige(request, 'atendimento')
    p = db.um(request.state.orgao['banco'], 'SELECT * FROM esic WHERE id=%s', (pid,))
    if not p:
        raise HTTPException(404)
    p['prazo'], p['prazo_cls'] = prazo(p)
    return T('atendimento_item', request, u, p=p)

@r.post('/atendimento/{pid}')
async def atendimento_post(request: Request, pid: int):
    u = exige(request, 'atendimento'); f = await ler_form(request)
    b = request.state.orgao['banco']
    p = db.um(b, 'SELECT * FROM esic WHERE id=%s', (pid,))
    acao = f.get('acao')
    if acao == 'responder':
        if not f.get('resposta'):
            return ir(f'/admin/atendimento/{pid}', 'Escreva a resposta.', request)
        db.exe(b, "UPDATE esic SET resposta=%s, situacao='respondido', respondido=CURRENT_DATE, setor=%s WHERE id=%s", (f['resposta'], f.get('setor', ''), pid))
    elif acao == 'prorrogar':
        if p['tipo'] != 'pedido' or p['situacao'] not in ('recebido', 'analise') or not f.get('justificativa'):
            return ir(f'/admin/atendimento/{pid}', 'Prorrogação só para pedidos e com justificativa.', request)
        db.exe(b, "UPDATE esic SET situacao='prorrogado', justificativa=%s WHERE id=%s", (f['justificativa'], pid))
    elif acao == 'encaminhar':
        db.exe(b, "UPDATE esic SET situacao='analise', setor=%s WHERE id=%s", (f.get('setor', ''), pid))
    auditar(request, f"Atendimento {p['protocolo']}: {acao}")
    return ir('/admin/atendimento', 'Atendimento atualizado.', request)

# ---------- usuários ----------
@r.get('/usuarios')
def usuarios(request: Request):
    u = exige(request)
    return T('usuarios', request, u, itens=db.todos(request.state.orgao['banco'], 'SELECT id, nome, email, cpf_final, setor, perfil, escopo, situacao, validade, ultimo_acesso, trocar_senha FROM usuarios ORDER BY nome'))

@r.post('/usuarios')
async def usuarios_post(request: Request):
    u = exige(request, 'usuarios'); f = await ler_form(request)
    b = request.state.orgao['banco']; acao = f.get('acao')
    if acao == 'novo':
        if not (f.get('nome') and '@' in f.get('email', '') and f.get('perfil') in PERFIS and len(f.get('senha', '')) >= 10):
            return ir('/admin/usuarios', 'Preencha nome, e-mail, perfil e uma senha provisória de 10+ caracteres.', request)
        cpf_d = ''.join(ch for ch in f.get('cpf', '') if ch.isdigit())
        try:
            h = cpf_hash(cpf_d) if len(cpf_d) == 11 and config.CPF_HMAC_CHAVE else None
        except ValueError:
            h = None
        try:
            db.exe(b, 'INSERT INTO usuarios (nome, email, cpf_final, cpf_hash, setor, perfil, escopo, senha_hash, validade) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                   (f['nome'], f['email'].lower(), cpf_d[-2:], h, f.get('setor', ''), f['perfil'], f.get('escopo', ''), hash_senha(f['senha']), f.get('validade') or None))
        except Exception:
            return ir('/admin/usuarios', 'Já existe usuário com esse e-mail.', request)
        auditar(request, f"Cadastrou usuário {f['nome']} ({PERFIS[f['perfil']]})")
        return ir('/admin/usuarios', 'Usuário cadastrado. Ele troca a senha no primeiro acesso.', request)
    uid = int(f['id'])
    if uid == u['id']:
        return ir('/admin/usuarios', 'Você não pode alterar o próprio acesso por aqui.', request)
    if acao == 'suspender':
        db.exe(b, "UPDATE usuarios SET situacao='suspenso' WHERE id=%s", (uid,))
    elif acao == 'reativar':
        db.exe(b, "UPDATE usuarios SET situacao='ativo' WHERE id=%s", (uid,))
    elif acao == 'perfil' and f.get('perfil') in PERFIS:
        db.exe(b, 'UPDATE usuarios SET perfil=%s WHERE id=%s', (f['perfil'], uid))
    elif acao == 'reset_2fa':
        db.exe(b, "UPDATE usuarios SET totp_ativo=FALSE, totp_segredo='', recuperacao='[]' WHERE id=%s", (uid,))
    elif acao == 'desbloquear':
        db.exe(b, 'UPDATE usuarios SET falhas=0, bloqueado_ate=NULL WHERE id=%s', (uid,))
    elif acao == 'senha_provisoria':
        if len(f.get('senha', '')) < 10:
            return ir('/admin/usuarios', 'A senha provisória precisa ter 10 caracteres ou mais.', request)
        db.exe(b, 'UPDATE usuarios SET senha_hash=%s, trocar_senha=TRUE, falhas=0, bloqueado_ate=NULL WHERE id=%s', (hash_senha(f['senha']), uid))
    elif acao == 'cpf':
        try:
            d = ''.join(ch for ch in f.get('cpf', '') if ch.isdigit())
            db.exe(b, 'UPDATE usuarios SET cpf_hash=%s, cpf_final=%s WHERE id=%s', (cpf_hash(d), d[-2:], uid))
        except ValueError as e:
            return ir('/admin/usuarios', str(e), request)
        except Exception:
            return ir('/admin/usuarios', 'Esse CPF já está vinculado a outro usuário.', request)
    auditar(request, f'Usuário {uid}: {acao}')
    return ir('/admin/usuarios', 'Usuário atualizado.', request)

@r.get('/auditoria')
def auditoria(request: Request):
    u = exige(request)
    return T('auditoria', request, u, itens=db.todos(request.state.orgao['banco'], 'SELECT * FROM auditoria ORDER BY id DESC LIMIT 300'))

# ---------- identidade ----------
CAMPOS_ID = [('nome', 'Nome do órgão'), ('prefixo', 'Linha acima do nome no cabeçalho (ex.: Poder Executivo, Poder Legislativo)'), ('nome_curto', 'Nome curto (menus e títulos, ex.: “Conheça” + nome do município)'),
             ('subtitulo', 'Linha abaixo do nome (ex.: Estado de São Paulo)'), ('cnpj', 'CNPJ'), ('endereco', 'Endereço'), ('telefone', 'Telefone'), ('whatsapp', 'WhatsApp'),
             ('email', 'E-mail de atendimento'), ('horario', 'Horário'), ('encarregado', 'Encarregado de dados (LGPD)'), ('encarregado_email', 'E-mail do encarregado'),
             ('login_titulo', 'Título da tela de login (vazio = “Entrar no painel”)'), ('hero_rotulo', 'Destaque: rótulo'), ('hero_titulo', 'Destaque: título'),
             ('hero_texto', 'Destaque: texto'), ('busca_dica', 'Destaque: exemplo na busca'), ('creditos', 'Créditos das fotos (rodapé)')]
COR = re.compile(r'^#[0-9A-Fa-f]{6}$')
USOS = {'brasao': 'Brasão', 'mascote': 'Mascote', 'hero': 'Imagem de fundo do destaque (página inicial)', 'login': 'Imagem de fundo da tela de login', 'sede': 'Foto da sede', 'conheca': 'Foto do “Conheça a cidade”',
        'rodape': 'Imagem de fundo do rodapé'}
MAX_CONHECA = 4

async def salvar_midia(request, u, arquivo, uso, alt, credito):
    """Valida e guarda uma imagem enviada (PNG/JPG/WEBP, até 3 MB) em DADOS_DIR/<órgão>/midia. Devolve a URL pública."""
    from .imagens import validar_upload, LIMITE_UPLOAD
    # texto alternativo é opcional (pedido do órgão, 14/11/2026): vazio = imagem decorativa (alt=""), ou o portal usa o título ao lado
    dados = await arquivo.read(LIMITE_UPLOAD + 1)
    ext = validar_upload(dados)
    o = request.state.orgao
    pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.{ext}'
    (pasta / nome).write_bytes(dados)
    db.exe(o['banco'], 'INSERT INTO midias (arquivo, uso, alt, credito, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s)', (nome, uso, alt[:300], credito[:300], len(dados), u['nome']))
    return f'/midia/{nome}'

ABAS_ID = [('dados', 'Dados e textos'), ('tema', 'Tema e cores'), ('imagens', 'Brasão, mascote e fundos'), ('favicon', 'Favicon'), ('redes', 'Redes sociais'),
           ('municipio', 'Números do município'), ('fotos', 'Fotos e álbuns'), ('conheca', 'Bloco da página inicial')]

@r.get('/identidade')
def identidade(request: Request, aba: str = 'dados', album: int = 0):
    u = exige(request)
    o = request.state.orgao; b = o['banco']
    ident = db.cfg(b, 'identidade', {}) or {}
    cx = ident.get('conheca') or {}
    from . import admin_fase9 as F9, municipio
    aba = aba if aba in dict(ABAS_ID) else 'dados'
    extra = {}
    if aba == 'tema':
        cor, dest = ident.get('cor') or o['cor'], ident.get('cor_destaque') or '#F0B429'
        from .web import LARGURAS, LARGURA_PADRAO
        from . import rodape as ROD
        rod = ROD.cor_de(ident, o['tipo'])
        extra = dict(cor=cor, dest=dest, c_cor=F9.contraste(cor, '#FFFFFF'), c_dest=F9.contraste(dest, F9.TEXTO_ESCURO), erros_cor=F9.checar_cores(cor.upper(), dest.upper()),
                     larguras=LARGURAS, largura=ident.get('largura') if ident.get('largura') in LARGURAS else LARGURA_PADRAO,
                     cor_rodape=rod, rodape_padrao=ROD.cor_padrao(o['tipo']), c_rodape=ROD.contraste(rod, ROD.TEXTO), erros_rodape=ROD.checar_cor(rod, o['tipo']),
                     rodape_titulo=ROD.TITULO.get(o['tipo']), rodape_tons=ROD.tons(rod))
    elif aba == 'imagens':
        from . import rodape as ROD, imagens as IMG
        rod = ROD.cor_de(ident, o['tipo']); fundo = ident.get('rodape') or {}
        extra = dict(rod=ROD.conf(b), rod_cor=rod, rod_rgb=ROD.tons(rod)['rgb'], rod_titulo=ROD.TITULO.get(o['tipo']), rod_texto=ROD.TEXTO,
                     rod_lum95=fundo.get('lum95'), rod_minimo=ROD.minimo_seguro(rod, fundo.get('lum95'), o['tipo']) if fundo.get('url') else 0,
                     rod_lim=(ROD.ALTURA_MIN, ROD.ALTURA_MAX, ROD.ALTURA_CEL),
                     anteriores={k: IMG.tem_anterior(ident, k) for k in USOS})
    elif aba == 'favicon':
        from . import imagens as IMG
        extra = dict(fav_anterior=IMG.tem_anterior(ident, 'favicon'))
    if aba == 'conheca':
        from . import imagens as IMG
        extra = dict(extra, anteriores={'conheca': IMG.tem_anterior(ident, 'conheca')})
    elif aba == 'redes':
        redes = ident.get('redes_v2') or [{'tipo': next((k for k, v in F9.REDES.items() if v.lower() == n.lower()), 'outra'), 'url': url, 'ordem': (i + 1) * 10, 'conta': ''} for i, (n, url) in enumerate(ident.get('redes', []))]
        extra = dict(redes=redes, tipos_rede=F9.REDES)
    elif aba == 'municipio':
        extra = dict(auto=municipio.automaticos(o['ibge']), manuais=municipio.manuais(b), ibge=o['ibge'])
    elif aba == 'fotos':
        cats = db.todos(b, 'SELECT * FROM foto_categorias ORDER BY nome')
        albs = db.todos(b, 'SELECT a.*, (SELECT count(*) FROM album_fotos WHERE album_id=a.id) n, c.nome categoria FROM albuns a LEFT JOIN foto_categorias c ON c.id=a.categoria_id ORDER BY a.ordem, a.id DESC')
        al = db.um(b, 'SELECT * FROM albuns WHERE id=%s', (album,)) if album else None
        # álbum com centenas de fotos: grade de miniaturas paginada; cada foto é editada na sua própria tela (?foto=id)
        q = request.query_params
        pg = max(1, int(q.get('pg'))) if str(q.get('pg', '')).isdigit() else 1
        total = db.um(b, 'SELECT count(*) n FROM album_fotos WHERE album_id=%s', (album,))['n'] if al else 0
        foto = db.um(b, 'SELECT * FROM album_fotos WHERE id=%s AND album_id=%s', (int(q['foto']), album)) if al and str(q.get('foto', '')).isdigit() else None
        extra = dict(categorias=cats, albuns=albs, album=al, licencas=F9.LICENCAS, foto=foto, pg=pg, paginas=max(1, -(-total // F9.FOTOS_POR_PAGINA)), total_fotos=total,
                     fotos=db.todos(b, 'SELECT * FROM album_fotos WHERE album_id=%s ORDER BY principal DESC, ordem, id LIMIT %s OFFSET %s',
                                    (album, F9.FOTOS_POR_PAGINA, (pg - 1) * F9.FOTOS_POR_PAGINA)) if al else [])
    return T('identidade', request, u, aba=aba, abas=ABAS_ID, campos=CAMPOS_ID, usos=USOS, cx=cx, max_conheca=MAX_CONHECA, **extra,
             redes_txt='\n'.join(f'{a} | {b}' for a, b in ident.get('redes', [])),
             numeros_txt='\n'.join(f'{a} | {b}' for a, b in cx.get('numeros', [])))

def _linhas(txt):
    out = []
    for l in (txt or '').splitlines():
        if '|' in l:
            a, b = [x.strip() for x in l.split('|', 1)]
            if a and b:
                out.append([a[:80], b[:300]])
    return out

@r.post('/identidade')
async def identidade_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    ident = db.cfg(b, 'identidade', {}) or {}
    for k, _ in CAMPOS_ID:
        if k in f:
            if k in ('cor', 'cor_destaque') and f[k] and not COR.match(f[k]):
                return ir(volta_segura(f, '/admin/identidade'), 'Cor inválida: use o formato #RRGGBB.', request)
            ident[k] = f[k][:400]
    if 'redes' in f:
        ident['redes'] = [r for r in _linhas(f['redes']) if r[1].startswith('https://')]
    if 'conheca_titulo' in f:
        cx = ident.get('conheca') or {}
        cx.update({'rotulo': f.get('conheca_rotulo', '')[:80], 'titulo': f['conheca_titulo'][:160], 'texto': f.get('conheca_texto', '')[:1200],
                   'fonte': f.get('conheca_fonte', '')[:300], 'numeros': _linhas(f.get('conheca_numeros', ''))[:6]})
        ident['conheca'] = cx
    if 'sede_titulo' in f:
        ident.setdefault('sede', {})['titulo'] = f['sede_titulo'][:120]
    ident['revisado_em'] = config.hoje().isoformat()
    db.set_cfg(b, 'identidade', ident)
    auditar(request, 'Atualizou a identidade do órgão')
    return ir(volta_segura(f, '/admin/identidade?aba=dados'), 'Identidade salva.', request)

@r.post('/identidade/midia')
async def identidade_midia(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']
    from . import imagens as IMG, rodape as ROD
    uso = f.get('uso', '')
    if uso not in USOS:
        raise HTTPException(400)
    volta = volta_segura(f, '/admin/identidade?aba=conheca' if uso == 'conheca' else '/admin/identidade?aba=imagens')
    ident = db.cfg(b, 'identidade', {}) or {}
    alt, credito = f.get('alt', ''), f.get('credito', '')
    arq = f.get('arquivo')
    tem_arquivo = arq is not None and hasattr(arq, 'read') and getattr(arq, 'filename', '')
    i = int(f.get('indice') or 0)
    acao = f.get('acao')
    if uso == 'conheca':
        fotos = (ident.setdefault('conheca', {})).setdefault('fotos', [])
        if acao == 'remover':
            if 0 <= i < len(fotos):
                IMG.guardar_anterior(ident, 'conheca', fotos.pop(i))
            db.set_cfg(b, 'identidade', ident)
            auditar(request, 'Removeu foto do “Conheça a cidade” (o arquivo continua na biblioteca de mídia)')
            return ir(volta, 'Foto removida. O arquivo continua na biblioteca de mídia.', request)
        if acao == 'restaurar':
            if len(fotos) >= MAX_CONHECA:
                return ir(volta, f'O mosaico aceita até {MAX_CONHECA} fotos: remova uma antes de restaurar.', request)
            volta_item = IMG.restaurar_anterior(ident, 'conheca', None)
            if volta_item:
                fotos.append(volta_item)
                db.set_cfg(b, 'identidade', ident)
                auditar(request, 'Restaurou foto anterior do “Conheça a cidade”')
            return ir(volta, 'Foto anterior restaurada.' if volta_item else 'Não há foto anterior.', request)
        atual = fotos[i] if 0 <= i < len(fotos) else None
    else:
        atual = (ident.get('sede') or {}).get('foto') if uso == 'sede' else ident.get(uso)

    def grava(item):
        if uso == 'sede':
            ident.setdefault('sede', {})['foto'] = item
        else:
            ident[uso] = item

    if uso != 'conheca' and acao in ('remover', 'restaurar'):
        if acao == 'remover':
            if not (atual and atual.get('url')):
                return ir(volta, 'Não há imagem para remover.', request)
            IMG.guardar_anterior(ident, uso, atual); grava(None)
            txt = f'Removeu a imagem: {USOS[uso]} (o arquivo continua na biblioteca de mídia)'
            msg = f'{USOS[uso]}: imagem removida. O arquivo continua na biblioteca de mídia.'
        else:
            item = IMG.restaurar_anterior(ident, uso, atual if atual and atual.get('url') else None)
            if not item:
                return ir(volta, 'Não há imagem anterior para restaurar.', request)
            grava(item)
            txt, msg = f'Restaurou a imagem anterior: {USOS[uso]}', f'{USOS[uso]}: imagem anterior restaurada.'
        ident['revisado_em'] = config.hoje().isoformat()
        db.set_cfg(b, 'identidade', ident)
        auditar(request, txt)
        return ir(volta, msg, request)
    try:
        if tem_arquivo:
            if uso == 'rodape':  # fundo do rodapé: WebP 1920 e 960 px + trecho mais claro (para o contraste)
                from .imagens import validar_upload, LIMITE_UPLOAD
                dados = await arq.read(LIMITE_UPLOAD + 1)
                validar_upload(dados)
                pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'; pasta.mkdir(parents=True, exist_ok=True)
                v = ROD.gerar_versoes(dados, pasta)
                lum95 = ROD.luminancia_p95(dados)
                for w, (nome, n) in v.items():
                    db.exe(b, 'INSERT INTO midias (arquivo, uso, alt, credito, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s)', (nome, f'rodape-{w}', '', credito[:300], n, u['nome']))
                url, url_960 = f'/midia/{v[1920][0]}', f'/midia/{v[960][0]}'
            else:
                url = await salvar_midia(request, u, arq, uso, alt, credito)
        elif atual and atual.get('url'):
            url = atual['url']
        else:
            raise ValueError('Escolha o arquivo da imagem.')
    except ValueError as e:
        return ir(volta, str(e), request)
    except Exception:
        return ir(volta, 'Não foi possível ler a imagem. Envie PNG, JPG ou WEBP.', request)
    item = {'url': url, 'alt': alt[:300], 'credito': credito[:300]}
    if uso in ('hero', 'login', 'sede', 'rodape'):  # ponto focal: define o recorte da imagem em cada formato de tela
        fx, fy = f.get('foco_x', '50'), f.get('foco_y', '50')
        item['foco_x'] = max(0, min(100, int(fx))) if str(fx).isdigit() else 50
        item['foco_y'] = max(0, min(100, int(fy))) if str(fy).isdigit() else 50
    if uso == 'rodape':
        item['decorativa'] = f.get('decorativa') == '1'
        if item['decorativa']:
            item['alt'] = ''
        if tem_arquivo:
            item['url_960'], item['lum95'] = url_960, lum95
        else:
            item['url_960'], item['lum95'] = (atual or {}).get('url_960', url), (atual or {}).get('lum95')
    if tem_arquivo and atual and atual.get('url') and uso != 'conheca':
        IMG.guardar_anterior(ident, uso, atual)  # trocar também guarda a anterior (pode ser restaurada)
    if uso == 'conheca':
        item['legenda'] = f.get('legenda', '')[:120]
        if atual is not None:
            fotos[i] = item
        elif len(fotos) < MAX_CONHECA:
            fotos.append(item)
        else:
            return ir(volta, f'O mosaico aceita até {MAX_CONHECA} fotos.', request)
    else:
        grava(item)
    ident['revisado_em'] = config.hoje().isoformat()
    db.set_cfg(b, 'identidade', ident)
    auditar(request, f'Atualizou a imagem: {USOS[uso]}')
    if uso == 'rodape':
        c = ROD.conf(b); cor = ROD.cor_de(ident, o['tipo']); m = ROD.minimo_seguro(cor, item.get('lum95'), o['tipo'])
        if c['camada'] < m:  # nova imagem mais clara: a camada sobe para o mínimo seguro (nunca publica abaixo de AA)
            c['camada'] = m; db.set_cfg(b, 'rodape', c)
            auditar(request, f'Rodapé: camada de cor ajustada para {m}% (mínimo seguro de contraste da nova imagem)')
            return ir(volta, f'{USOS[uso]} atualizada. A camada de cor subiu para {m}%, o mínimo com contraste AA para esta imagem.', request)
    return ir(volta, f'{USOS[uso]} atualizada.', request)

# ---------- Câmara: vereadores ----------
@r.get('/vereadores')
def vereadores_adm(request: Request, leg: int | None = None):
    u = exige(request)
    o = request.state.orgao
    if o['tipo'] != 'legislativo':
        raise HTTPException(404)
    b = o['banco']
    legs = db.todos(b, 'SELECT * FROM legislaturas ORDER BY numero DESC')
    leg = leg or (legs[0]['numero'] if legs else 0)
    return T('vereadores', request, u, legs=legs, leg=leg, itens=db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (leg,)))

@r.get('/vereadores/{vid}')
def vereador_adm(request: Request, vid: int):
    u = exige(request)
    o = request.state.orgao
    v = db.um(o['banco'], 'SELECT * FROM vereadores WHERE id=%s', (vid,)) if o['tipo'] == 'legislativo' else None
    if not v:
        raise HTTPException(404)
    return T('vereador', request, u, v=v)

@r.post('/vereadores/{vid}')
async def vereador_adm_post(request: Request, vid: int):
    u = exige(request, 'editar'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']
    v = db.um(b, 'SELECT * FROM vereadores WHERE id=%s', (vid,)) if o['tipo'] == 'legislativo' else None
    if not v:
        raise HTTPException(404)
    if not f.get('partido'):
        return ir(f'/admin/vereadores/{vid}', 'Informe o partido.', request)
    foto, alt, cred = v['foto_url'], f.get('foto_alt', ''), f.get('foto_credito', '')
    arq = f.get('foto')
    try:
        if f.get('remover_foto'):
            foto, alt, cred = '', '', ''
        elif arq is not None and hasattr(arq, 'read') and getattr(arq, 'filename', ''):
            foto = await salvar_midia(request, u, arq, 'vereador', alt, cred)
    except ValueError as e:
        return ir(f'/admin/vereadores/{vid}', str(e), request)
    db.exe(b, 'UPDATE vereadores SET apelido=%s, partido=%s, bio=%s, contato=%s, foto_url=%s, foto_alt=%s, foto_credito=%s WHERE id=%s',
           (f.get('apelido', '')[:60], f['partido'][:20], f.get('bio', '')[:3000], f.get('contato', '')[:300], foto, alt[:300], cred[:300], vid))
    auditar(request, f"Atualizou o perfil do vereador {v['nome']}")
    return ir(f"/admin/vereadores?leg={v['legislatura']}", 'Perfil salvo.', request)

# ---------- Câmara: emendas (sessões, pauta e votação ficam em admin_leg.py) ----------
@r.get('/emendas')
def emendas(request: Request):
    u = exige(request)
    return T('emendas', request, u, itens=db.todos(request.state.orgao['banco'], 'SELECT * FROM emendas ORDER BY (conferencia=%s) DESC, split_part(numero, %s, 1)::int', ('divergente', '/')))

@r.post('/emendas')
async def emendas_post(request: Request):
    u = exige(request, 'publicar'); f = await ler_form(request)
    db.exe(request.state.orgao['banco'], "UPDATE emendas SET conferencia='conferido' WHERE numero=%s", (f['numero'],))
    auditar(request, f"Marcou a emenda {f['numero']} como conferida")
    return ir('/admin/emendas', 'Emenda marcada como conferida.', request)

# ---------- Diário Oficial (Fase 6: assinatura por caderno, regras da Lei 910/2026) ----------
from . import diario_servico as DS, assinatura as AS
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse as _FR

@r.get('/diario')
def diario(request: Request):
    u = exige(request)
    o = request.state.orgao; b = o['banco']
    if not modulos_do_orgao(o).get('diario'):
        raise HTTPException(404)
    agora = config.agora()
    return T('diario', request, u, atos=db.todos(b, "SELECT * FROM diario_atos WHERE situacao <> 'publicado' ORDER BY id DESC"),
             eds=db.todos(b, 'SELECT * FROM diario_edicoes ORDER BY id DESC LIMIT 20'), aberta=DS.em_andamento(b), prox=DS.proxima_ordinaria(b),
             corte=agora.time() >= diario_pdf.regras(b)['t_corte'], alvo=diario_pdf.data_alvo(b, agora), modo_teste=AS.modo_teste(), diario_teste_publico=diario_pdf.mostrar_teste(b),
             alertas=db.todos(b, 'SELECT * FROM diario_alertas WHERE NOT resolvido ORDER BY id DESC LIMIT 10'),
             publicados=db.todos(b, "SELECT a.id, a.tipo, a.numero, a.ementa, e.numero en, e.letra el FROM diario_atos a JOIN diario_edicoes e ON e.id=a.edicao_id WHERE a.situacao='publicado' ORDER BY a.id DESC LIMIT 100"),
             designacoes={d['caderno']: d for d in db.todos(b, 'SELECT * FROM designacoes WHERE ativo ORDER BY id')},
             orgaos_diario=db.todos(b, 'SELECT * FROM diario_orgaos WHERE ativo ORDER BY caderno, nome'), orgao_escolhido=_orgao_escolhido(b, u))

def _orgao_escolhido(b, u):
    """Órgão que já vem escolhido no envio: o do último ato que esta pessoa enviou; senão o marcado como padrão."""
    r = db.um(b, "SELECT a.orgao_id FROM diario_atos a JOIN diario_orgaos o ON o.id=a.orgao_id AND o.ativo WHERE a.autor=%s ORDER BY a.id DESC LIMIT 1", (u['nome'],))
    if r:
        return r['orgao_id']
    r = db.um(b, 'SELECT id FROM diario_orgaos WHERE ativo ORDER BY padrao DESC, nome LIMIT 1')
    return r['id'] if r else None

@r.post('/diario/preformatar')
async def diario_preformatar(request: Request):
    """Pré-formatação automática do texto do ato (o resultado volta para o editor; nada é gravado)."""
    from fastapi.responses import JSONResponse
    from . import diario_formato as DF
    exige(request, 'diario_enviar'); f = await ler_form(request)
    return JSONResponse({'html': DF.preformatar((f.get('html') or '')[:400_000])})

@r.get('/diario/orgaos')
def diario_orgaos(request: Request):
    u = exige(request); b = request.state.orgao['banco']
    if not modulos_do_orgao(request.state.orgao).get('diario'):
        raise HTTPException(404)
    return T('diario_orgaos', request, u, orgaos=db.todos(b, "SELECT o.*, (SELECT count(*) FROM diario_atos a WHERE a.orgao_id=o.id) n FROM diario_orgaos o ORDER BY o.ativo DESC, o.caderno, o.nome"),
             secretarias=db.todos(b, "SELECT nome, sigla FROM secretarias WHERE ativa AND nome NOT IN (SELECT nome FROM diario_orgaos) ORDER BY nome"))

@r.post('/diario/orgaos')
async def diario_orgaos_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    acao = f.get('acao'); volta = '/admin/diario/orgaos'
    nome = re.sub(r'\s+', ' ', f.get('nome', '')).strip()[:120]
    sigla = re.sub(r'\s+', ' ', f.get('sigla', '')).strip()[:20]
    caderno = f.get('caderno') if f.get('caderno') in ('executivo', 'legislativo') else 'executivo'
    if acao in ('novo', 'salvar') and len(nome) < 3:
        return ir(volta, 'Informe o nome oficial do órgão (ex.: Gabinete do Prefeito).', request)
    try:
        if acao == 'novo':
            db.exe(b, 'INSERT INTO diario_orgaos (nome, sigla, caderno) VALUES (%s,%s,%s)', (nome, sigla, caderno)); msg = f'Órgão “{nome}” cadastrado.'
        elif acao == 'salvar':
            oid = int(f['id'])
            db.exe(b, 'UPDATE diario_orgaos SET nome=%s, sigla=%s, caderno=%s, ativo=%s WHERE id=%s', (nome, sigla, caderno, f.get('ativo') == '1', oid))
            db.exe(b, 'UPDATE diario_atos SET orgao=%s WHERE orgao_id=%s AND edicao_id IS NULL', (nome, oid))  # só atos ainda não certificados
            msg = f'Órgão “{nome}” salvo.'
        elif acao == 'padrao':
            oid = int(f['id'])
            db.exe(b, 'UPDATE diario_orgaos SET padrao=(id=%s)', (oid,)); msg = 'Órgão padrão definido: ele já vem escolhido para quem ainda não enviou atos.'
        elif acao == 'importar':
            n = 0
            for s_ in db.todos(b, "SELECT nome, sigla FROM secretarias WHERE ativa AND nome NOT IN (SELECT nome FROM diario_orgaos)"):
                db.exe(b, 'INSERT INTO diario_orgaos (nome, sigla, caderno) VALUES (%s,%s,%s) ON CONFLICT (nome) DO NOTHING', (s_['nome'], s_['sigla'], 'legislativo' if request.state.orgao.get('tipo') == 'legislativo' else 'executivo')); n += 1
            msg = f'{n} secretaria(s) trazida(s) do cadastro de secretarias.'
        else:
            raise HTTPException(400)
    except HTTPException:
        raise
    except Exception:
        return ir(volta, 'Já existe um órgão com esse nome.', request)
    auditar(request, f'Diário: {msg}')
    return ir(volta, msg, request)

@r.post('/diario/ato')
async def diario_ato(request: Request):
    u = exige(request, 'diario_enviar'); f = await ler_form(request)
    b = request.state.orgao['banco']; acao = f.get('acao')
    if acao == 'novo':
        from . import editor as ED
        html = ''
        if (f.get('html') or '').strip():  # texto formatado no editor: limpo no servidor; o texto simples sai dele
            html, _ = ED.limpar(re.sub(r'<(figure|img)\b[^>]*>.*?</figure>|<img\b[^>]*>', '', f['html'], flags=re.S | re.I))
            f['texto'] = ED.texto(html)
        org = db.um(b, 'SELECT * FROM diario_orgaos WHERE id=%s AND ativo', (int(f['orgao_id']),)) if str(f.get('orgao_id', '')).isdigit() else None
        if not org:
            return ir('/admin/diario?novo=1', 'Escolha o órgão na lista (os órgãos são cadastrados em Diário Oficial → Órgãos).', request)
        f['orgao'], f['caderno'] = org['nome'], org['caderno']
        if not (f.get('ementa') and f.get('texto') and f.get('tipo')):
            return ir('/admin/diario', 'Preencha tipo, ementa e texto.', request)
        if re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', f['texto'] + f['ementa']):
            return ir('/admin/diario', 'O texto tem CPF completo. Remova ou mascare antes de enviar (LGPD).', request)
        ret = int(f['retifica']) if f.get('retifica', '').isdigit() else None
        alvo = diario_pdf.data_alvo(b, config.agora())
        rels = [{'tipo': f.get(f'rel_tipo_{i}'), 'alvo': f.get(f'rel_alvo_{i}', '').strip()[:60]} for i in range(5)
                if f.get(f'rel_tipo_{i}') in ('altera', 'revoga', 'regulamenta') and f.get(f'rel_alvo_{i}', '').strip()]
        db.exe(b, "INSERT INTO diario_atos (caderno, tipo, numero, orgao, orgao_id, ementa, texto, html, situacao, autor, retifica_ato_id, data_alvo, relacoes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'revisao',%s,%s,%s,%s)",
               (f['caderno'], f['tipo'], f.get('numero', ''), f['orgao'], org['id'], f['ementa'], f['texto'], html, u["nome"], ret, alvo, Jsonb(rels)))
        msg = f"Ato enviado para revisão. Edição prevista: {alvo.strftime('%d/%m/%Y')}" + (f" (passou do horário de corte das {diario_pdf.regras(b)['corte_txt']})." if alvo > config.hoje() else '.')
    else:
        aid = int(f['id'])
        if acao == 'aprovar' and u['perfil'] in PODE['diario_revisar']:
            db.exe(b, "UPDATE diario_atos SET situacao='aprovado' WHERE id=%s", (aid,)); msg = 'Ato aprovado.'
        elif acao == 'devolver' and u['perfil'] in PODE['diario_revisar']:
            db.exe(b, "UPDATE diario_atos SET situacao='devolvido', comentario=%s WHERE id=%s", (f.get('comentario', ''), aid)); msg = 'Ato devolvido.'
        elif acao == 'excluir':
            db.exe(b, "DELETE FROM diario_atos WHERE id=%s AND edicao_id IS NULL AND origem_orgao=''", (aid,)); msg = 'Ato excluído (antes da certificação).'
        else:
            raise HTTPException(403)
    auditar(request, f'Diário: {msg}')
    return ir('/admin/diario', msg, request)

@r.post('/diario/edicao')
async def diario_edicao(request: Request):
    u = exige(request, 'diario_fechar'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']; acao = f.get('acao')
    try:
        if acao in ('abrir', 'extra'):
            e = DS.abrir(b, u['nome'], extra=acao == 'extra')
            msg = f"Passo 1 de 4: edição nº {e['numero']}{e['letra']} criada" + (' em MODO TESTE (sem valor oficial)' if e['modo_teste'] else '') + '. Próximo: fechar a edição e gerar o PDF.'
        elif acao == 'invalidar':
            e = db.um(b, 'SELECT * FROM diario_edicoes WHERE id=%s', (int(f['id']),))
            DS.invalidar(o, e, f.get('ato', ''), f.get('comunicado', ''), f.get('prorrogacao', ''), u['nome'])
            msg = f"Edição nº {e['numero']}{e['letra']} invalidada; comunicado publicado no portal."
        else:
            e = DS.em_andamento(b)
            if not e:
                raise ValueError('Nenhuma edição em andamento.')
            if acao == 'fechar':
                if e['situacao'] != 'montagem':
                    raise ValueError('A edição já está fechada.')
                n, cod, pdfa = DS.fechar(o, e, u['nome'])
                msg = f"Edição fechada com {n} ato(s). Código {cod}. {'PDF/A-2b gerado.' if pdfa else 'Atenção: conversão para PDF/A indisponível.'} Passo 3 de 4: assine as etapas."
            elif acao == 'assinar':
                rot, completa = await run_in_threadpool(DS.assinar_etapa, o, e, u['nome'])  # pyHanko usa asyncio.run: fora do laço
                msg = f'{rot}: assinada.' + (' Edição totalmente assinada. Passo 4 de 4: publicar.' if completa else ' Próximo: assinar a etapa seguinte.')
            elif acao == 'a3':
                arq = f.get('arquivo')
                if arq is None or not getattr(arq, 'filename', ''):
                    raise ValueError('Escolha o PDF assinado.')
                rot, completa = await run_in_threadpool(DS.receber_a3, o, e, await arq.read(30 * 1024 * 1024), u['nome'])
                msg = f'{rot}: assinatura recebida e validada.' + (' Edição totalmente assinada. Passo 4 de 4: publicar.' if completa else ' Próximo: assinar a etapa seguinte.')
            elif acao == 'publicar':
                teste = DS.publicar(o, e, u['nome'])
                msg = f"Edição nº {e['numero']}{e['letra']} " + (('publicada em MODO TESTE, no portal com a legenda “' + diario_pdf.LEGENDA_TESTE + '”.') if teste and diario_pdf.mostrar_teste(b) else
                                                                  ('concluída em MODO TESTE: não aparece no portal (opção “Edições de teste no portal” desligada).' if teste else 'publicada.'))
            elif acao == 'reabrir':
                if any(x['feita'] for x in e['assinaturas']):
                    raise ValueError('Edição já assinada não pode ser reaberta: use retificação ou edição extra.')
                db.exe(b, 'UPDATE diario_atos SET edicao_id=NULL, pagina=NULL WHERE edicao_id=%s', (e['id'],))
                db.exe(b, "UPDATE diario_edicoes SET situacao='montagem', pdf_arquivo=NULL, sha256=NULL, codigo=NULL, assinaturas='[]', assinatura='pendente' WHERE id=%s", (e['id'],))
                msg = 'Fechamento desfeito: a edição voltou ao passo 2 e aceita novos atos aprovados (ainda não assinada nem publicada).'
            else:
                raise HTTPException(400)
    except AS.NaoConfigurado as ex:
        return ir('/admin/diario', f'Assinatura não configurada: {ex}', request)
    except ValueError as ex:
        return ir('/admin/diario', str(ex), request)
    auditar(request, f'Diário: {msg}')
    return ir('/admin/diario', msg, request)

@r.get('/diario/edicao/{eid}.pdf')
def diario_edicao_pdf(request: Request, eid: int):
    """PDF atual da edição (para o signatário com token A3 assinar no próprio computador)."""
    u = exige(request, 'diario_fechar')
    e = db.um(request.state.orgao['banco'], 'SELECT * FROM diario_edicoes WHERE id=%s', (eid,))
    if not e or not e['pdf_arquivo'] or not Path(e['pdf_arquivo']).is_file():
        raise HTTPException(404)
    auditar(request, f"Baixou a edição nº {e['numero']}{e['letra']} para assinar")
    return _FR(e['pdf_arquivo'], media_type='application/pdf', headers={'Cache-Control': 'no-store'}, filename=f"diario-{e['numero']}{e['letra']}-para-assinar.pdf")

@r.post('/diario/alertas')
async def diario_alertas(request: Request):
    u = exige(request, 'diario_fechar'); f = await ler_form(request)
    db.exe(request.state.orgao['banco'], 'UPDATE diario_alertas SET resolvido=TRUE WHERE id=%s', (int(f['id']),))
    return ir('/admin/diario', 'Alerta marcado como resolvido.', request)

@r.get('/diario/config')
def diario_config(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    return T('diario_config', request, u, desig=db.todos(b, 'SELECT * FROM designacoes ORDER BY ativo DESC, caderno, id DESC'), etapas=AS.ETAPAS,
             feriados=db.todos(b, 'SELECT * FROM feriados WHERE data >= %s ORDER BY data', (config.hoje().replace(month=1, day=1),)), conf=db.cfg(b, 'diario', {}) or {}, mostrar_teste=diario_pdf.mostrar_teste(b), modo_teste=AS.modo_teste(), rd=diario_pdf.regras(b))

@r.post('/diario/config')
async def diario_config_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    b = request.state.orgao['banco']; acao = f.get('acao')
    try:
        if acao == 'designar':
            if f.get('caderno') not in AS.ETAPAS or not f.get('nome') or not f.get('cargo') or not f.get('ato'):
                raise ValueError('Informe caderno, nome, cargo e o ato de designação.')
            if f.get('provedor') == 'a1' and not (re.fullmatch(r'[\w.-]+\.(p12|pfx)', f.get('certificado', '')) and re.fullmatch(r'[A-Z][A-Z0-9_]{2,40}', f.get('senha_env', ''))):
                raise ValueError('A1: informe o nome do arquivo .p12 (em segredos/a1) e o NOME da variável do .env com a senha (ex.: A1_SENHA_PREFEITO). Nunca digite a senha aqui.')
            db.exe(b, 'UPDATE designacoes SET ativo=FALSE WHERE caderno=%s', (f['caderno'],))
            db.exe(b, 'INSERT INTO designacoes (caderno, nome, cargo, ato, ato_data, provedor, certificado, senha_env) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                   (f['caderno'], f['nome'][:120], f['cargo'][:120], f['ato'][:200], f.get('ato_data') or None, f.get('provedor') if f.get('provedor') in ('a1', 'nuvem', 'a3') else 'a3', f.get('certificado', '')[:120], f.get('senha_env', '')[:60]))
            msg = 'Signatário designado.'
        elif acao == 'feriado':
            if not f.get('data') or not f.get('descricao'):
                raise ValueError('Informe data e descrição.')
            db.exe(b, 'INSERT INTO feriados (data, descricao, tipo) VALUES (%s,%s,%s) ON CONFLICT (data) DO UPDATE SET descricao=EXCLUDED.descricao, tipo=EXCLUDED.tipo',
                   (f['data'], f['descricao'][:120], f.get('tipo') if f.get('tipo') in ('feriado', 'sem_expediente', 'ponto_facultativo') else 'feriado'))
            msg = 'Data cadastrada no calendário do Diário.'
        elif acao == 'tirar_feriado':
            db.exe(b, 'DELETE FROM feriados WHERE data=%s', (f['data'],)); msg = 'Data removida.'
        elif acao == 'lei':
            conf = db.cfg(b, 'diario', {}) or {}
            conf['lei'] = f.get('lei', '')[:200]
            db.set_cfg(b, 'diario', conf); msg = 'Texto da lei de instituição salvo.'
        elif acao == 'teste_publico':  # edições de teste no portal, com a legenda (16/11/2026)
            conf = db.cfg(b, 'diario', {}) or {}
            antes = diario_pdf.mostrar_teste(b)
            conf['mostrar_teste'] = f.get('mostrar_teste') == '1'; db.set_cfg(b, 'diario', conf)
            auditar(request, f"Diário: edições de teste no portal {'sim' if antes else 'não'} → {'sim' if conf['mostrar_teste'] else 'não'}")
            msg = ('As edições de teste publicadas aparecem no portal com a legenda “' + diario_pdf.LEGENDA_TESTE + '”.') if conf['mostrar_teste'] else 'As edições de teste não aparecem mais no portal.'
        elif acao == 'regras':  # etapa 3: lei, decreto, base legal e horários do órgão
            novo, erros = diario_pdf.validar_regras(f)
            if erros:
                raise ValueError(' '.join(erros))
            conf = db.cfg(b, 'diario', {}) or {}
            antes = diario_pdf.regras(b)
            if f.get('padrao_horarios') == '1':  # volta aos horários padrão (sem gravar horários próprios)
                for k in diario_pdf.HORARIOS:
                    novo.pop(k, None); conf.pop(k, None)
            conf.update(novo); db.set_cfg(b, 'diario', conf)
            depois = diario_pdf.regras(b)
            mud = '; '.join(f'{k}: {antes[k] or "—"} → {depois[k] or "—"}' for k in ('lei', 'decreto', 'base_legal', 'corte', 'alerta', 'publicacao') if antes[k] != depois[k])
            auditar(request, f'Diário: lei, decreto e horários alterados ({mud[:400] or "sem mudança"})')
            msg = f"Regras do Diário salvas: envio até {depois['corte_txt']}, alerta às {depois['alerta_txt']}, publicação automática às {depois['publicacao_txt']}." 
        else:
            raise HTTPException(400)
    except ValueError as ex:
        return ir('/admin/diario/config', str(ex), request)
    auditar(request, f'Diário (configuração): {acao}')
    return ir('/admin/diario/config', msg, request)

# ---------- remessa ao Diário de outro órgão (ex.: Câmara → caderno Legislativo da Prefeitura) ----------
from . import remessa as RM
from starlette.concurrency import run_in_threadpool

@r.get('/remessas')
def remessas(request: Request):
    u = exige(request)
    o = request.state.orgao
    destino = RM.destino_do(o)
    if not destino:
        raise HTTPException(404, 'Este órgão não envia atos ao Diário de outro órgão.')
    return T('remessas', request, u, destino=destino, tipos=RM.TIPOS_REMESSA, itens=db.todos(o['banco'], 'SELECT * FROM remessas ORDER BY id DESC LIMIT 100'))

@r.post('/remessas')
async def remessas_post(request: Request):
    u = exige(request, 'diario_enviar'); f = await ler_form(request)
    o = request.state.orgao
    try:
        if f.get('acao') == 'enviar':
            rid = await run_in_threadpool(RM.enviar, o, u['nome'], f.get('tipo', ''), f.get('numero', ''), f.get('ementa', ''), f.get('texto', ''))
            msg = f'Remessa nº {rid} enviada ao Diário. Acompanhe a situação abaixo.'
        elif f.get('acao') == 'atualizar':
            res = await run_in_threadpool(RM.atualizar, o, int(f['id']))
            msg = f"Situação: {res['situacao']}" + (f" · edição nº {res['edicao']}, página {res['pagina']}" if res.get('edicao') else '')
        else:
            raise HTTPException(400)
    except ValueError as e:
        return ir('/admin/remessas', str(e), request)
    auditar(request, f'Remessa ao Diário: {msg}')
    return ir('/admin/remessas', msg, request)
