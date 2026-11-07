"""Painel administrativo de cada órgão (servido em <domínio>/admin)."""
import re, secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from . import config, db, eleicao, diario as diario_pdf
from .catalogo import MOD, serve, BLOCOS, CLASSES, VEDADAS, PERFIS, PODE, TEMAS
from .security import hash_senha, confere_senha
from .web import templates, ctx_orgao, ler_form, ir, usuario, exige, auditar, modulos_do_orgao

r = APIRouter(prefix='/_a')

def pendencias(b):
    """Contadores do menu: conteúdos esperando revisão e pedidos do e-SIC/Ouvidoria em aberto."""
    return db.um(b, "SELECT (SELECT count(*) FROM conteudos WHERE situacao='revisao') revisao, (SELECT count(*) FROM esic WHERE situacao <> 'respondido') esic, (SELECT count(*) FROM opinioes WHERE situacao='pendente') + (SELECT count(*) FROM tribuna_inscricoes WHERE situacao='pendente') opinioes")

def ctx(request, u, **kw):
    c = ctx_orgao(request, u=u, pode=lambda p: u['perfil'] in PODE[p], pend=pendencias(request.state.orgao['banco']), **kw)
    return c

def T(nome, request, u, **kw):
    return templates.TemplateResponse(request, f'admin/{nome}.html', ctx(request, u, **kw))

# ---------- login ----------
@r.get('/login')
def login(request: Request):
    return templates.TemplateResponse(request, 'admin/login.html', ctx_orgao(request))

@r.post('/login')
async def login_post(request: Request):
    f = await ler_form(request)
    o = request.state.orgao
    u = db.um(o['banco'], 'SELECT * FROM usuarios WHERE lower(email)=lower(%s)', (f.get('email', ''),))
    if not u or u['situacao'] != 'ativo' or not confere_senha(f.get('senha', ''), u['senha_hash']) or (u['validade'] and u['validade'] < config.hoje()):
        auditar(request, f"Tentativa de acesso recusada: {f.get('email','')[:60]}", 'anônimo')
        return ir('/admin/login', 'E-mail ou senha incorretos, ou acesso suspenso.', request)
    request.session['u'] = {'id': u['id'], 'nome': u['nome'], 'perfil': u['perfil'], 'orgao': o['slug'], 'trocar': u['trocar_senha']}
    db.exe(o['banco'], 'UPDATE usuarios SET ultimo_acesso=now() WHERE id=%s', (u['id'],))
    auditar(request, 'Entrou no painel', u['nome'])
    return ir('/admin/senha' if u['trocar_senha'] else '/admin/', '', request)

@r.get('/sair')
def sair(request: Request):
    request.session.pop('u', None)
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
    return T('painel', request, u, k=k, sic=sic, log=log)

# ---------- conteúdos ----------
@r.get('/conteudos')
def conteudos(request: Request, sit: str = ''):
    u = exige(request)
    b = request.state.orgao['banco']
    itens = db.todos(b, 'SELECT * FROM conteudos ' + ('WHERE situacao=%s ' if sit else '') + 'ORDER BY atualizado_em DESC', (sit,) if sit else ())
    for c in itens:
        c['suspenso'] = eleicao.suspenso(c, b)
    return T('conteudos', request, u, itens=itens, sit=sit)

@r.get('/conteudos/novo')
def conteudo_novo(request: Request):
    u = exige(request, 'editar')
    return T('conteudo', request, u, c=None, versoes=[])

@r.get('/conteudos/{cid}')
def conteudo_ver(request: Request, cid: int):
    u = exige(request)
    b = request.state.orgao['banco']
    c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,))
    if not c:
        raise HTTPException(404)
    return T('conteudo', request, u, c=c, versoes=db.todos(b, 'SELECT * FROM conteudo_versoes WHERE conteudo_id=%s ORDER BY id DESC', (cid,)))

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
    if acao in ('rascunho', 'revisao'):
        if not pode('editar'):
            raise HTTPException(403)
        if not f.get('titulo'):
            return ir(f"/admin/conteudos/{cid or 'novo'}", 'Informe o título.', request)
        img = f.get('imagem', '') if f.get('imagem', '') in TEMAS else ''
        vals = (f.get('tipo', 'Notícia'), f.get('secao', 'Notícias'), f['titulo'], f.get('resumo', ''), f.get('texto', ''), f['classe'], acao, pub, tirar, img)
        if c:
            db.exe(b, 'UPDATE conteudos SET tipo=%s, secao=%s, titulo=%s, resumo=%s, texto=%s, classe=%s, situacao=%s, publicar_em=%s, tirar_em=%s, imagem=%s, atualizado_em=now() WHERE id=%s', vals + (cid,))
        else:
            cid = db.exe(b, 'INSERT INTO conteudos (tipo, secao, titulo, resumo, texto, classe, situacao, publicar_em, tirar_em, imagem, autor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (u['nome'],))['id']
        obs = 'Salvou rascunho' if acao == 'rascunho' else 'Enviou para revisão'
    elif acao in ('aprovar', 'devolver', 'arquivar'):
        if not pode('publicar') or not c:
            raise HTTPException(403)
        if acao == 'aprovar':
            if f['classe'] in VEDADAS and eleicao.em_defeso(b) and eleicao.conf(b).get('bloquear', True) and not c['excecao_eleitoral']:
                return ir(f'/admin/conteudos/{cid}', 'Período eleitoral: esta classificação não pode ser publicada até o fim do defeso.', request)
            nova = 'agendado' if pub and date.fromisoformat(pub) > config.hoje() else 'publicado'
            db.exe(b, 'UPDATE conteudos SET situacao=%s, classe=%s, publicar_em=coalesce(%s::date, %s::date), tirar_em=%s, atualizado_em=now() WHERE id=%s', (nova, f['classe'], pub, config.hoje(), tirar, cid))
            obs = 'Aprovou e ' + ('agendou' if nova == 'agendado' else 'publicou')
        elif acao == 'devolver':
            if not f.get('comentario'):
                return ir(f'/admin/conteudos/{cid}', 'Para devolver, escreva o comentário para o autor.', request)
            db.exe(b, "UPDATE conteudos SET situacao='devolvido', comentario=%s, atualizado_em=now() WHERE id=%s", (f['comentario'], cid))
            obs = 'Devolveu ao autor'
        else:
            db.exe(b, "UPDATE conteudos SET situacao='arquivado', atualizado_em=now() WHERE id=%s", (cid,))
            obs = 'Arquivou (tirou do ar)'
    else:
        raise HTTPException(400)
    db.exe(b, 'INSERT INTO conteudo_versoes (conteudo_id, quem, obs) VALUES (%s,%s,%s)', (cid, u['nome'], obs))
    auditar(request, f"{obs}: {f.get('titulo') or (c and c['titulo'])}")
    return ir('/admin/conteudos', obs + '.', request)

# ---------- página inicial ----------
@r.get('/pagina-inicial')
def pagina_inicial(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    mods = modulos_do_orgao(request.state.orgao)
    bl = [dict(x, info=BLOCOS.get(x['chave'])) for x in db.todos(b, "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")]
    return T('pagina_inicial', request, u, blocos=[x for x in bl if x['info']], mods=mods)

@r.post('/pagina-inicial')
async def pagina_inicial_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    bid = int(f['id']); acao = f['acao']
    bl = db.todos(b, "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")
    i = next(k for k, x in enumerate(bl) if x['id'] == bid)
    info = BLOCOS[bl[i]['chave']]
    if acao == 'visivel' and not info[3]:
        db.exe(b, 'UPDATE blocos SET visivel = NOT visivel WHERE id=%s', (bid,))
    elif acao in ('subir', 'descer'):
        j = i - 1 if acao == 'subir' else i + 1
        if 0 <= j < len(bl) and bl[j]['regiao'] == bl[i]['regiao']:
            db.exe(b, 'UPDATE blocos SET ordem=%s WHERE id=%s', (bl[j]['ordem'], bl[i]['id']))
            db.exe(b, 'UPDATE blocos SET ordem=%s WHERE id=%s', (bl[i]['ordem'], bl[j]['id']))
    auditar(request, f'Alterou a página inicial: {info[0]} ({acao})')
    return ir('/admin/pagina-inicial', 'Página inicial atualizada.', request)

# ---------- funcionalidades ----------
@r.get('/funcionalidades')
def funcionalidades(request: Request):
    u = exige(request)
    o = request.state.orgao
    contratados = {x['chave'] for x in db.todos(db.PLATAFORMA, 'SELECT chave FROM orgao_modulos WHERE orgao_id=%s AND contratado', (o['id'],))}
    ligados = db.cfg(o['banco'], 'modulos_ligados', {}) or {}
    lista = []
    for k, m in MOD.items():
        if not serve(k, o['tipo']):
            continue
        disponivel = m[3] != 'opc' or k in contratados
        lista.append({'chave': k, 'nome': m[1], 'desc': m[2], 'oferta': m[3], 'disponivel': disponivel, 'ligado': m[3] == 'obr' or (disponivel and ligados.get(k, True))})
    return T('funcionalidades', request, u, lista=lista)

@r.post('/funcionalidades')
async def funcionalidades_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    o = request.state.orgao; k = f['chave']
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
        cpf = ''.join(ch for ch in f.get('cpf', '') if ch.isdigit())[-2:]
        try:
            db.exe(b, 'INSERT INTO usuarios (nome, email, cpf_final, setor, perfil, escopo, senha_hash, validade) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                   (f['nome'], f['email'].lower(), cpf, f.get('setor', ''), f['perfil'], f.get('escopo', ''), hash_senha(f['senha']), f.get('validade') or None))
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
    auditar(request, f'Usuário {uid}: {acao}')
    return ir('/admin/usuarios', 'Usuário atualizado.', request)

@r.get('/auditoria')
def auditoria(request: Request):
    u = exige(request)
    return T('auditoria', request, u, itens=db.todos(request.state.orgao['banco'], 'SELECT * FROM auditoria ORDER BY id DESC LIMIT 300'))

# ---------- identidade ----------
CAMPOS_ID = [('nome', 'Nome do órgão'), ('prefixo', 'Linha acima do nome no cabeçalho (ex.: Prefeitura Municipal de)'), ('nome_curto', 'Nome curto no cabeçalho (ex.: Borá)'),
             ('subtitulo', 'Linha abaixo do nome (ex.: Estado de São Paulo)'), ('cnpj', 'CNPJ'), ('endereco', 'Endereço'), ('telefone', 'Telefone'), ('whatsapp', 'WhatsApp'),
             ('email', 'E-mail de atendimento'), ('horario', 'Horário'), ('encarregado', 'Encarregado de dados (LGPD)'), ('encarregado_email', 'E-mail do encarregado'),
             ('cor', 'Cor principal (#RRGGBB)'), ('cor_destaque', 'Cor de destaque (#RRGGBB)'), ('hero_rotulo', 'Destaque: rótulo'), ('hero_titulo', 'Destaque: título'),
             ('hero_texto', 'Destaque: texto'), ('busca_dica', 'Destaque: exemplo na busca'), ('creditos', 'Créditos das fotos (rodapé)')]
COR = re.compile(r'^#[0-9A-Fa-f]{6}$')
USOS = {'brasao': 'Brasão', 'hero': 'Foto do destaque (página inicial)', 'sede': 'Foto da sede', 'conheca': 'Foto do “Conheça a cidade”'}
MAX_CONHECA = 4

async def salvar_midia(request, u, arquivo, uso, alt, credito):
    """Valida e guarda uma imagem enviada (PNG/JPG/WEBP, até 3 MB) em DADOS_DIR/<órgão>/midia. Devolve a URL pública."""
    from .imagens import validar_upload, LIMITE_UPLOAD
    if not alt or len(alt) < 5:
        raise ValueError('Escreva o texto alternativo da imagem (o que ela mostra), com pelo menos 5 caracteres.')
    dados = await arquivo.read(LIMITE_UPLOAD + 1)
    ext = validar_upload(dados)
    o = request.state.orgao
    pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.{ext}'
    (pasta / nome).write_bytes(dados)
    db.exe(o['banco'], 'INSERT INTO midias (arquivo, uso, alt, credito, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s)', (nome, uso, alt[:300], credito[:300], len(dados), u['nome']))
    return f'/midia/{nome}'

@r.get('/identidade')
def identidade(request: Request):
    u = exige(request)
    ident = db.cfg(request.state.orgao['banco'], 'identidade', {}) or {}
    cx = ident.get('conheca') or {}
    return T('identidade', request, u, campos=CAMPOS_ID, usos=USOS, cx=cx, max_conheca=MAX_CONHECA,
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
                return ir('/admin/identidade', 'Cor inválida: use o formato #RRGGBB.', request)
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
    return ir('/admin/identidade', 'Identidade salva.', request)

@r.post('/identidade/midia')
async def identidade_midia(request: Request):
    u = exige(request, 'config'); f = await ler_form(request)
    b = request.state.orgao['banco']
    uso = f.get('uso', '')
    if uso not in USOS:
        raise HTTPException(400)
    ident = db.cfg(b, 'identidade', {}) or {}
    alt, credito = f.get('alt', ''), f.get('credito', '')
    arq = f.get('arquivo')
    tem_arquivo = arq is not None and hasattr(arq, 'read') and getattr(arq, 'filename', '')
    i = int(f.get('indice') or 0)
    if uso == 'conheca':
        fotos = (ident.setdefault('conheca', {})).setdefault('fotos', [])
        if f.get('acao') == 'remover':
            if 0 <= i < len(fotos):
                fotos.pop(i)
            db.set_cfg(b, 'identidade', ident)
            auditar(request, 'Removeu foto do “Conheça a cidade”')
            return ir('/admin/identidade#imagens', 'Foto removida.', request)
        atual = fotos[i] if 0 <= i < len(fotos) else None
    else:
        atual = (ident.get('sede') or {}).get('foto') if uso == 'sede' else ident.get(uso)
    try:
        if tem_arquivo:
            url = await salvar_midia(request, u, arq, uso, alt, credito)
        elif atual and atual.get('url'):
            if not alt or len(alt) < 5:
                raise ValueError('O texto alternativo é obrigatório (pelo menos 5 caracteres).')
            url = atual['url']
        else:
            raise ValueError('Escolha o arquivo da imagem.')
    except ValueError as e:
        return ir('/admin/identidade#imagens', str(e), request)
    item = {'url': url, 'alt': alt[:300], 'credito': credito[:300]}
    if uso == 'conheca':
        item['legenda'] = f.get('legenda', '')[:120]
        if atual is not None:
            fotos[i] = item
        elif len(fotos) < MAX_CONHECA:
            fotos.append(item)
        else:
            return ir('/admin/identidade#imagens', f'O mosaico aceita até {MAX_CONHECA} fotos.', request)
    elif uso == 'sede':
        ident.setdefault('sede', {})['foto'] = item
    else:
        ident[uso] = item
    ident['revisado_em'] = config.hoje().isoformat()
    db.set_cfg(b, 'identidade', ident)
    auditar(request, f'Atualizou a imagem: {USOS[uso]}')
    return ir('/admin/identidade#imagens', f'{USOS[uso]} atualizada.', request)

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
        elif foto and len(alt) < 5:
            raise ValueError('A foto precisa de texto alternativo (pelo menos 5 caracteres).')
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

# ---------- Diário Oficial ----------
def proxima_edicao(b):
    r_ = db.um(b, "SELECT coalesce(max(numero),0) n FROM diario_edicoes WHERE letra=''")
    return r_['n'] + 1

@r.get('/diario')
def diario(request: Request):
    u = exige(request)
    b = request.state.orgao['banco']
    atos = db.todos(b, "SELECT * FROM diario_atos WHERE situacao <> 'publicado' ORDER BY id DESC")
    eds = db.todos(b, 'SELECT * FROM diario_edicoes ORDER BY id DESC LIMIT 20')
    aberta = db.um(b, "SELECT * FROM diario_edicoes WHERE situacao IN ('montagem','fechada') ORDER BY id DESC LIMIT 1")
    agora = datetime.now()
    return T('diario', request, u, atos=atos, eds=eds, aberta=aberta, prox=proxima_edicao(b), corte=agora.hour >= 16)

@r.post('/diario/ato')
async def diario_ato(request: Request):
    u = exige(request, 'diario_enviar'); f = await ler_form(request)
    b = request.state.orgao['banco']; acao = f.get('acao')
    if acao == 'novo':
        if not (f.get('ementa') and f.get('texto') and f.get('tipo')):
            return ir('/admin/diario', 'Preencha tipo, ementa e texto.', request)
        txt = f['texto']
        import re
        if re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', txt):
            return ir('/admin/diario', 'O texto tem CPF completo. Remova ou mascare antes de enviar (LGPD).', request)
        db.exe(b, "INSERT INTO diario_atos (caderno, tipo, numero, orgao, ementa, texto, situacao, autor) VALUES (%s,%s,%s,%s,%s,%s,'revisao',%s)",
               (f.get('caderno', 'executivo'), f['tipo'], f.get('numero', ''), f.get('orgao', ''), f['ementa'], txt, u['nome']))
        msg = 'Ato enviado para revisão.'
    else:
        aid = int(f['id'])
        if acao == 'aprovar' and u['perfil'] in PODE['diario_revisar']:
            db.exe(b, "UPDATE diario_atos SET situacao='aprovado' WHERE id=%s", (aid,)); msg = 'Ato aprovado.'
        elif acao == 'devolver' and u['perfil'] in PODE['diario_revisar']:
            db.exe(b, "UPDATE diario_atos SET situacao='devolvido', comentario=%s WHERE id=%s", (f.get('comentario', ''), aid)); msg = 'Ato devolvido.'
        elif acao == 'excluir':
            db.exe(b, "DELETE FROM diario_atos WHERE id=%s AND edicao_id IS NULL", (aid,)); msg = 'Ato excluído (antes da certificação).'
        else:
            raise HTTPException(403)
    auditar(request, f'Diário: {msg}')
    return ir('/admin/diario', msg, request)

@r.post('/diario/edicao')
async def diario_edicao(request: Request):
    u = exige(request, 'diario_fechar'); f = await ler_form(request)
    o = request.state.orgao; b = o['banco']; acao = f.get('acao')
    if acao in ('abrir', 'extra'):
        if db.um(b, "SELECT 1 FROM diario_edicoes WHERE situacao IN ('montagem','fechada')"):
            return ir('/admin/diario', 'Já existe uma edição em andamento.', request)
        if acao == 'abrir':
            num, letra = proxima_edicao(b), ''
        else:
            ult = db.um(b, "SELECT numero FROM diario_edicoes WHERE letra='' ORDER BY numero DESC LIMIT 1")
            if not ult:
                return ir('/admin/diario', 'Publique uma edição ordinária antes de criar uma extra.', request)
            num = ult['numero']
            l = db.um(b, 'SELECT max(letra) l FROM diario_edicoes WHERE numero=%s', (num,))['l'] or ''
            letra = chr(ord(l) + 1) if l else 'A'
        db.exe(b, 'INSERT INTO diario_edicoes (numero, letra, data, responsavel) VALUES (%s,%s,%s,%s)', (num, letra, config.hoje(), u['nome']))
        msg = f'Edição nº {num}{letra} aberta.'
    else:
        e = db.um(b, "SELECT * FROM diario_edicoes WHERE situacao IN ('montagem','fechada') ORDER BY id DESC LIMIT 1")
        if not e:
            return ir('/admin/diario', 'Nenhuma edição em andamento.', request)
        if acao == 'fechar':
            db.exe(b, "UPDATE diario_atos SET edicao_id=%s WHERE situacao='aprovado' AND edicao_id IS NULL", (e['id'],))
            atos = db.todos(b, 'SELECT * FROM diario_atos WHERE edicao_id=%s ORDER BY caderno, id', (e['id'],))
            ident = db.cfg(b, 'identidade', {}) or {}
            caminho, sha, cod = diario_pdf.gerar_pdf(e, atos, ident, str(Path(config.DADOS_DIR) / o['slug'] / 'diario'))
            assinada = diario_pdf.assinar_edicao(caminho)
            db.exe(b, "UPDATE diario_edicoes SET situacao='fechada', sem_atos=%s, pdf_arquivo=%s, sha256=%s, codigo=%s, assinatura=%s WHERE id=%s",
                   (len(atos) == 0, caminho, sha, cod, 'assinada' if assinada else 'pendente', e['id']))
            msg = f"Edição fechada com {len(atos)} ato(s). Código {cod}." + ('' if assinada else ' Assinatura ICP-Brasil pendente (piloto).')
        elif acao == 'publicar':
            if e['situacao'] != 'fechada':
                return ir('/admin/diario', 'Feche a edição antes de publicar.', request)
            db.exe(b, "UPDATE diario_edicoes SET situacao='publicada', publicada_em=now() WHERE id=%s", (e['id'],))
            db.exe(b, "UPDATE diario_atos SET situacao='publicado' WHERE edicao_id=%s", (e['id'],))
            msg = f"Edição nº {e['numero']}{e['letra']} publicada."
        elif acao == 'reabrir' and e['situacao'] == 'fechada':
            db.exe(b, "UPDATE diario_atos SET edicao_id=NULL WHERE edicao_id=%s", (e['id'],))
            db.exe(b, "UPDATE diario_edicoes SET situacao='montagem', pdf_arquivo=NULL, sha256=NULL, codigo=NULL WHERE id=%s", (e['id'],))
            msg = 'Edição reaberta para ajustes (ainda não publicada).'
        else:
            raise HTTPException(400)
    auditar(request, f'Diário: {msg}')
    return ir('/admin/diario', msg, request)
