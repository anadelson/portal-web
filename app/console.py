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
    return T('login', request)

@r.post('/login')
async def login_post(request: Request):
    f = await ler_form(request)
    g = db.um(db.PLATAFORMA, 'SELECT * FROM gestores WHERE lower(email)=lower(%s) AND ativo', (f.get('email', ''),))
    if not g or not confere_senha(f.get('senha', ''), g['senha_hash']):
        return ir('/login', 'E-mail ou senha incorretos.', request)
    request.session['gestor'] = {'id': g['id'], 'nome': g['nome'], 'trocar': g['trocar_senha']}
    log(request.session['gestor'], 'Entrou no console')
    return ir('/senha' if g['trocar_senha'] else '/', '', request)

@r.get('/sair')
def sair(request: Request):
    request.session.pop('gestor', None)
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
    return T('orgao', request, o=o, c=c, sit=sit, fase=fase, adit=adit, opc=opc, anos=anos, MOD=MOD)

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

@r.get('/orgaos/novo')
def novo(request: Request):
    gestor(request)
    return T('novo', request)

@r.post('/orgaos/novo')
async def novo_post(request: Request):
    g = gestor(request); f = await ler_form(request)
    slug = f.get('slug', '').lower()
    if not re.fullmatch(r'[a-z0-9-]{3,30}', slug) or not f.get('nome') or not f.get('dominio') or f.get('tipo') not in ('executivo', 'legislativo'):
        return ir('/orgaos/novo', 'Preencha nome, tipo, domínio e um identificador (3 a 30 letras minúsculas, números ou hífen).', request)
    banco = 'bd_' + slug.replace('-', '_')
    try:
        provision.registrar_orgao(slug, f['nome'], f['tipo'], f['dominio'].lower(), banco, 'Executivo' if f['tipo'] == 'executivo' else 'Legislativo',
                                  '#1D4E89' if f['tipo'] == 'executivo' else '#2F5233', {}, municipio=f.get('municipio', ''), ibge=f.get('ibge', ''))
    except Exception as e:
        return ir('/orgaos/novo', f'Não foi possível criar: {e}', request)
    limpar_cache()
    log(g, f"Cadastrou o órgão {f['nome']} ({f['dominio']}, banco {banco})")
    return ir('/', f"Órgão criado em implantação. Aponte o DNS de {f["dominio"]} para a VPS, emita o certificado e inclua o domínio no vhost do nginx (Docs/PROGRESSO.md).", request)

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
    bl = db.todos(o['banco'], "SELECT * FROM blocos WHERE pagina='home' ORDER BY ordem")
    usados = {b['chave'] for b in bl}
    paleta = [(k, v) for k, v in BLOCOS.items() if k not in usados and (v[4] == 'ambos' or v[4] == o['tipo'])]
    return T('layout', request, o=o, bl=[dict(b, info=BLOCOS.get(b['chave'])) for b in bl if b['chave'] in BLOCOS], regioes=REGIOES, reg_nome=dict(REGIOES), paleta=paleta)

@r.post('/layout/{oid}')
async def layout_post(request: Request, oid: int):
    g = gestor(request); f = await ler_form(request)
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,))
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
    return T('log', request, itens=db.todos(db.PLATAFORMA, 'SELECT * FROM log_console ORDER BY id DESC LIMIT 300'),
             coletas=db.todos(db.PLATAFORMA, 'SELECT * FROM coletas ORDER BY id DESC LIMIT 50'))
