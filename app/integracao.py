"""Integração entre órgãos do mesmo município — juntos na mesma instalação ou em instalações separadas (23/11/2026).

Antes, a conversa entre Câmara e Prefeitura (remessa ao Diário, legislação, links do portal) só funcionava com os dois
órgãos no MESMO nó: o nó só conhecia os órgãos das próprias licenças, gerava o token do par sozinho e chamava o outro
órgão pelo endereço interno (127.0.0.1). Com a Câmara num nó e a Prefeitura em outro, o par não existia.

Agora a GESTÃO é a fonte da verdade das ligações:
  - `garantir_pares()` (gestão): para cada par de órgãos ativos do mesmo município (código IBGE), um token por sentido,
    gerado uma vez e guardado em `pares_orgaos` no banco de controle;
  - `diretorio_para(no)` (gestão): junto com as licenças, cada nó recebe um DIRETÓRIO ASSINADO (Ed25519) com os
    parceiros dos seus órgãos (nome, tipo, domínio, serviços, onde estão hospedados) e os tokens dos pares que
    envolvem os seus órgãos — e só esses. Nenhum dado pessoal;
  - `guardar_diretorio()` (nó): confere assinatura, destino (NO_NOME) e idade; grava `orgaos_parceiros` e os tokens.

Chamada entre órgãos (`chamar`): se o destino está nesta instalação, vai pelo endereço interno (INTERNO_BASE, com o
Host do órgão); se está em outra, vai pelo domínio público em HTTPS (certificado conferido). Em qualquer caso o pedido
leva X-Portal-Origem, X-Portal-Momento e X-Portal-Assinatura = HMAC-SHA256(token do par, momento\\nMÉTODO\\ncaminho\\n
sha256(corpo)), janela de 5 minutos, e fica em `remessas_log`. Um órgão nunca acessa o banco do outro.

  python -m app.integracao pares        # (gestão) cria os pares que faltam
  python -m app.integracao testar SLUG  # testa a conversa do órgão SLUG com cada parceiro
"""
import hashlib, hmac, json, secrets, sys, time
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from psycopg.types.json import Jsonb
from . import config, db

r = APIRouter(prefix='/_p')
JANELA = 300
SERVICOS_DIRETORIO = ('ouv', 'sic', 'diario', 'carta', 'transp', 'bi', 'audiencias', 'transm', 'integpref')

# ---------- quem são os parceiros ----------
def _servicos_licenca(o, doc=None):
    """Serviços do órgão que interessam aos parceiros: obrigatórios do tipo + contratados (sem dado pessoal)."""
    from .catalogo import MOD, serve
    if doc is None:
        from . import licenca
        doc = licenca.documento(o) if config.PAPEL != 'no' else licenca.vigente(o)
    contratados = set((doc or {}).get('modulos') or [])
    return sorted(k for k in SERVICOS_DIRETORIO if k in MOD and serve(k, o['tipo']) and (MOD[k][3] in ('obr', 'plano') or k in contratados))

def _publico(o, hospedagem='', local=True, servicos=None):
    return {'id': o['id'], 'slug': o['slug'], 'nome': o['nome'], 'tipo': o['tipo'], 'dominio': o['dominio'], 'ibge': o['ibge'],
            'municipio': o.get('municipio') or '', 'ativo': bool(o.get('ativo', True)), 'banco': o.get('banco') if local else None,
            'servicos': servicos if servicos is not None else [], 'hospedagem': hospedagem, 'local': local}

def _locais():
    from . import orgaos
    return {o['id']: o for o in orgaos.todos(ativos=False)}

_memo = {'t': 0.0, 'v': None}
MEMO_S = 30

def limpar_cache():
    _memo['t'] = 0.0

def conhecidos(fresco=False):
    """Todos os órgãos que esta instalação conhece: os daqui (local=True) e os parceiros de outras instalações.
    Guardado por 30 s (é consultado em toda página do portal, para os links do órgão vizinho)."""
    if not fresco and _memo['v'] is not None and time.monotonic() - _memo['t'] < MEMO_S:
        return _memo['v']
    v = _conhecidos()
    _memo.update(t=time.monotonic(), v=v)
    return v

def _conhecidos():
    locais = _locais()
    out = {i: _publico(o, local=True, servicos=_servicos_licenca(o)) for i, o in locais.items()}
    if config.PAPEL == 'no':
        for p in db.todos(db.LOCAL, 'SELECT * FROM orgaos_parceiros ORDER BY id') if _tem_diretorio() else []:
            if p['id'] not in out:
                out[p['id']] = dict(p, banco=None, local=False, servicos=list(p['servicos'] or []))
    else:  # gestão/tudo: os órgãos hospedados em nós aparecem como parceiros remotos
        for o in db.todos(db.PLATAFORMA, 'SELECT o.*, n.nome no_nome FROM orgaos o JOIN nos n ON n.id=o.no_id ORDER BY o.id'):
            if o['id'] not in out:
                out[o['id']] = _publico(o, hospedagem=o['no_nome'], local=False, servicos=_servicos_licenca(o))
    return out

def parceiros(o, ativos=True, fresco=True):
    """Órgãos do mesmo município que não são o próprio (Prefeitura ↔ Câmara), daqui ou de outra instalação."""
    return [x for x in conhecidos(fresco).values() if x['ibge'] == o['ibge'] and x['id'] != o['id'] and (not ativos or x['ativo'])]

def parceiro(slug=None, id_=None):
    for x in conhecidos(fresco=True).values():
        if (slug and x['slug'] == slug) or (id_ is not None and x['id'] == id_):
            return x
    return None

def _tem_diretorio():
    try:
        return bool(db.um(db.LOCAL, "SELECT 1 FROM information_schema.tables WHERE table_name='orgaos_parceiros'"))
    except Exception:
        return False

def diretorio_recebido():
    """(nó) Já chegou algum diretório da gestão? Sem ele, o nó segue com os pares que já tinha (compatível com gestão antiga)."""
    if config.PAPEL != 'no' or not _tem_diretorio():
        return False
    return bool(db.um(db.LOCAL, "SELECT 1 FROM config_console WHERE chave='diretorio_recebido_em'"))

# ---------- pares (tokens) ----------
def par(origem, destino):
    return db.um(db.LOCAL, 'SELECT * FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s AND ativo', (origem['id'], destino['id']))

def garantir_pares():
    """(gestão ou tudo) Um token por sentido para cada par de órgãos do mesmo município. Devolve quantos criou.
    No nó isto só roda enquanto a gestão não mandou diretório (instalação antiga): aí só há órgãos daqui."""
    if config.PAPEL == 'no' and diretorio_recebido():
        return 0
    if config.PAPEL == 'no':
        from . import orgaos
        lista = orgaos.todos()
    else:
        lista = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE ativo ORDER BY id')
    n = 0
    for a in lista:
        for b in lista:
            if a['id'] != b['id'] and a['ibge'] == b['ibge'] and not db.um(db.LOCAL, 'SELECT 1 FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (a['id'], b['id'])):
                db.exe(db.LOCAL, 'INSERT INTO pares_orgaos (origem_id, destino_id, token) VALUES (%s,%s,%s)', (a['id'], b['id'], secrets.token_urlsafe(32)))
                n += 1
    return n

def renovar_par(a_id, b_id):
    """(gestão) Troca os tokens dos dois sentidos de um par. Os nós recebem os novos em até 5 minutos (com o diretório)."""
    for o, d in ((a_id, b_id), (b_id, a_id)):
        db.exe(db.PLATAFORMA, """INSERT INTO pares_orgaos (origem_id, destino_id, token) VALUES (%s,%s,%s)
                                 ON CONFLICT (origem_id, destino_id) DO UPDATE SET token=EXCLUDED.token, criado_em=now()""", (o, d, secrets.token_urlsafe(32)))

def ligar_par(a_id, b_id, ativo):
    db.exe(db.PLATAFORMA, 'UPDATE pares_orgaos SET ativo=%s WHERE (origem_id=%s AND destino_id=%s) OR (origem_id=%s AND destino_id=%s)', (bool(ativo), a_id, b_id, b_id, a_id))

def pares_do_console(o):
    """(gestão) Pares do órgão para a tela do console: parceiro, onde está, ativo, criado em (nunca o token)."""
    out = []
    for p in db.todos(db.PLATAFORMA, """SELECT d.id, d.nome, d.dominio, d.tipo, n.nome no_nome, x.ativo, x.criado_em
                                        FROM pares_orgaos x JOIN orgaos d ON d.id=x.destino_id LEFT JOIN nos n ON n.id=d.no_id
                                        WHERE x.origem_id=%s ORDER BY d.id""", (o['id'],)):
        out.append(p)
    return out

# ---------- diretório (gestão → nó) ----------
def diretorio_para(no, assinar):
    """(gestão) Diretório assinado para o nó: parceiros dos órgãos dele (que estão em OUTRA hospedagem) e os tokens dos
    pares que envolvem os órgãos dele. `assinar` é licenca.assinar (passado para evitar import circular)."""
    garantir_pares()
    meus = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE no_id=%s', (no['id'],))
    ids = {o['id'] for o in meus}
    ibges = {o['ibge'] for o in meus}
    parceiros_ = []
    if ibges:
        for o in db.todos(db.PLATAFORMA, """SELECT o.*, coalesce(n.nome, '') no_nome FROM orgaos o LEFT JOIN nos n ON n.id=o.no_id
                                            WHERE o.ibge = ANY(%s) AND o.id <> ALL(%s) ORDER BY o.id""", (sorted(ibges), sorted(ids) or [0])):
            d = _publico(o, hospedagem=o['no_nome'], local=False, servicos=_servicos_licenca(o))
            d.pop('banco', None); d.pop('local', None)
            parceiros_.append(d)
    pares = [{'origem_id': p['origem_id'], 'destino_id': p['destino_id'], 'token': p['token'], 'ativo': p['ativo']}
             for p in db.todos(db.PLATAFORMA, 'SELECT * FROM pares_orgaos WHERE origem_id = ANY(%s) OR destino_id = ANY(%s) ORDER BY origem_id, destino_id',
                               (sorted(ids) or [0], sorted(ids) or [0]))]
    return assinar({'tipo': 'diretorio', 'no': no['nome'], 'orgaos': sorted(ids), 'parceiros': parceiros_, 'pares': pares,
                    'emitido_em': datetime.now(timezone.utc).isoformat()})

def guardar_diretorio(pacote, publica, agora=None):
    """(nó) Confere e aplica o diretório. Só vale com assinatura da gestão, para ESTE nó (NO_NOME) e recente (15 min).
    Devolve uma frase para o registro (ou '' se não havia diretório na resposta)."""
    from . import licenca
    if not pacote:
        return ''
    d = licenca.verificar(pacote, publica)
    if not d or d.get('tipo') != 'diretorio' or not isinstance(d.get('parceiros'), list):
        return 'diretório RECUSADO (assinatura não confere)'
    if d.get('no') != config.env('NO_NOME'):
        return ''  # diretório de outro nó (ou NO_NOME ausente): ignora sem apagar nada, como o inventário
    try:
        idade = ((agora or datetime.now(timezone.utc)) - datetime.fromisoformat(d['emitido_em'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return 'diretório RECUSADO (data inválida)'
    if not -300 <= idade <= 900:
        return 'diretório ignorado (antigo)'
    ids_parc = []
    for p in d['parceiros']:
        db.exe(db.LOCAL, """INSERT INTO orgaos_parceiros (id, slug, nome, tipo, dominio, ibge, municipio, ativo, servicos, hospedagem, recebido_em)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                            ON CONFLICT (id) DO UPDATE SET slug=EXCLUDED.slug, nome=EXCLUDED.nome, tipo=EXCLUDED.tipo, dominio=EXCLUDED.dominio,
                              ibge=EXCLUDED.ibge, municipio=EXCLUDED.municipio, ativo=EXCLUDED.ativo, servicos=EXCLUDED.servicos,
                              hospedagem=EXCLUDED.hospedagem, recebido_em=now()""",
               (int(p['id']), p['slug'], p['nome'], p['tipo'], p['dominio'], p['ibge'], p.get('municipio', ''), bool(p.get('ativo', True)),
                Jsonb(list(p.get('servicos') or [])), p.get('hospedagem', '')))
        ids_parc.append(int(p['id']))
    db.exe(db.LOCAL, 'DELETE FROM orgaos_parceiros WHERE NOT (id = ANY(%s))', (ids_parc or [0],))
    meus = [int(x) for x in d.get('orgaos') or []]
    chaves = set()
    for p in d.get('pares') or []:
        o_, d_ = int(p['origem_id']), int(p['destino_id'])
        if o_ not in meus and d_ not in meus:
            continue  # nunca guarda token de par que não envolve órgão deste nó
        chaves.add((o_, d_))
        db.exe(db.LOCAL, """INSERT INTO pares_orgaos (origem_id, destino_id, token, ativo) VALUES (%s,%s,%s,%s)
                            ON CONFLICT (origem_id, destino_id) DO UPDATE SET token=EXCLUDED.token, ativo=EXCLUDED.ativo""",
               (o_, d_, p['token'], bool(p.get('ativo', True))))
    for x in db.todos(db.LOCAL, 'SELECT origem_id, destino_id FROM pares_orgaos WHERE origem_id = ANY(%s) OR destino_id = ANY(%s)', (meus or [0], meus or [0])):
        if (x['origem_id'], x['destino_id']) not in chaves:  # par que a gestão tirou (órgão saiu, par desligado de vez)
            db.exe(db.LOCAL, 'DELETE FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (x['origem_id'], x['destino_id']))
    db.exe(db.LOCAL, """INSERT INTO config_console (chave, valor) VALUES ('diretorio_recebido_em', %s)
                        ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor""", (Jsonb({'em': d['emitido_em']}),))
    limpar_cache()
    return f'diretório: {len(ids_parc)} parceiro(s) em outra instalação, {len(chaves)} par(es)'

# ---------- chamada entre órgãos ----------
def assinatura(token, momento, metodo, caminho, corpo: bytes):
    msg = f'{momento}\n{metodo}\n{caminho}\n{hashlib.sha256(corpo).hexdigest()}'.encode()
    return hmac.new(token.encode(), msg, hashlib.sha256).hexdigest()

def log(origem, destino, acao, ok, detalhe=''):
    db.exe(db.LOCAL, 'INSERT INTO remessas_log (origem, destino, acao, ok, detalhe) VALUES (%s,%s,%s,%s,%s)', (origem, destino, acao[:200], ok, (detalhe or '')[:500]))

def cliente_local():
    """Cliente para órgão DESTA instalação (substituível nos testes). Chame fora do laço de eventos (run_in_threadpool)."""
    import httpx
    return httpx.Client(base_url=config.INTERNO_BASE, timeout=30)

def cliente_remoto(dominio):
    """Cliente para órgão de OUTRA instalação: HTTPS pelo domínio público, certificado conferido (substituível nos testes)."""
    import httpx
    return httpx.Client(base_url=f'https://{dominio}', timeout=30, headers={'User-Agent': config.USER_AGENT})

def e_local(destino):
    return bool(destino.get('local', destino.get('banco')))

def chamar(origem, destino, metodo, caminho, dados=None, cliente=None, rotulo='órgão de destino'):
    """Chama a API do órgão parceiro (daqui ou de outra instalação). Devolve o JSON; ValueError com mensagem simples se falhar."""
    import httpx
    destino = parceiro(id_=destino['id']) or destino
    p = par(origem, destino)
    if not p:
        raise ValueError('Não há integração ativa entre os órgãos (par sem token). Peça ao gestor da plataforma para conferir as integrações.')
    corpo = json.dumps(dados or {}, ensure_ascii=False).encode() if metodo == 'POST' else b''
    m = str(int(time.time()))
    h = {'Content-Type': 'application/json', 'X-Portal-Origem': origem['slug'], 'X-Portal-Momento': m,
         'X-Portal-Assinatura': assinatura(p['token'], m, metodo, caminho, corpo)}
    if e_local(destino):
        h.update({'Host': destino['dominio'], 'X-Forwarded-Proto': 'https'})
        c = (cliente or cliente_local)()
    else:
        c = cliente_remoto(destino['dominio'])
    try:
        with c:
            resp = c.request(metodo, caminho, content=corpo or None, headers=h)
        ok = resp.status_code < 400
        log(origem['slug'], destino['slug'], f'{metodo} {caminho}', ok, '' if ok else resp.text[:200])
        if not ok:
            erro = resp.json().get('erro', '') if resp.headers.get('content-type', '').startswith('application/json') else ''
            raise ValueError(f'O {rotulo} recusou ({resp.status_code}){": " + erro if erro else ""}.')
        return resp.json()
    except httpx.HTTPError as e:
        log(origem['slug'], destino['slug'], f'{metodo} {caminho}', False, type(e).__name__)
        raise ValueError(f'Não foi possível falar com o {rotulo} ({type(e).__name__}).')

async def autenticar(request: Request):
    """Lado de quem recebe: confere origem, horário e assinatura. Devolve (origem, destino, corpo)."""
    destino = request.state.orgao
    origem = parceiro(slug=request.headers.get('x-portal-origem', ''))
    corpo = await request.body()
    m = request.headers.get('x-portal-momento', '')
    caminho = request.url.path.replace('/_p', '', 1)
    if not origem or not m.isdigit() or abs(time.time() - int(m)) > JANELA:
        log(request.headers.get('x-portal-origem', '?')[:40], destino['slug'], caminho, False, 'origem ou momento inválido')
        raise HTTPException(401, 'Pedido recusado: origem ou horário inválido.')
    p = par(origem, destino)
    if not p or not hmac.compare_digest(assinatura(p['token'], m, request.method, caminho, corpo), request.headers.get('x-portal-assinatura', '')):
        log(origem['slug'], destino['slug'], caminho, False, 'assinatura inválida')
        raise HTTPException(401, 'Pedido recusado: assinatura inválida.')
    return origem, destino, corpo

# ---------- teste de conversa ----------
@r.get('/api/integracao/ping')
async def ping(request: Request):
    origem, destino, _ = await autenticar(request)
    log(origem['slug'], destino['slug'], 'ping recebido', True)
    from .web import modulos_do_orgao
    mods = modulos_do_orgao(destino)
    return {'orgao': destino['nome'], 'slug': destino['slug'], 'tipo': destino['tipo'],
            'servicos': sorted(k for k in SERVICOS_DIRETORIO if mods.get(k)), 'hora': datetime.now(timezone.utc).isoformat(),
            'versao': _versao()}

def _versao():
    from . import licenca
    return licenca.VERSAO_APP()

def testar(origem, destino, cliente=None):
    """Faz um ping assinado no parceiro. Devolve (ok, frase)."""
    t = time.monotonic()
    try:
        d = chamar(origem, destino, 'GET', '/api/integracao/ping', cliente=cliente, rotulo=destino['nome'])
        ms = int((time.monotonic() - t) * 1000)
        return True, f"{d.get('orgao')} respondeu em {ms} ms · serviços: {', '.join(d.get('servicos') or []) or 'nenhum'}"
    except ValueError as e:
        return False, str(e)

def historico(o, limite=30):
    return db.todos(db.LOCAL, 'SELECT * FROM remessas_log WHERE origem=%s OR destino=%s ORDER BY id DESC LIMIT %s', (o['slug'], o['slug'], limite))

def main(args):
    cmd = args[0] if args else ''
    if cmd == 'pares':
        print(garantir_pares(), 'par(es) criado(s)')
    elif cmd == 'testar' and len(args) > 1:
        from . import orgaos
        o = orgaos.por_slug(args[1])
        if not o:
            print('órgão não está nesta instalação'); return 2
        for p in parceiros(o):
            ok, msg = testar(o, p)
            print('OK ' if ok else 'FALHA', p['slug'], '·', 'mesma instalação' if e_local(p) else f"outra instalação ({p['dominio']})", '·', msg)
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
