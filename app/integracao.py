"""Integração entre os órgãos do município em QUALQUER instalação (23/11/2026).

Prefeitura e Câmara podem estar na mesma instalação ou em nós diferentes (até em VPS diferentes). A gestão é a fonte da
verdade das ligações, como já é das licenças:
  gestão   garantir_pares()   cria os pares (um token por sentido) entre todos os órgãos do mesmo código IBGE;
           diretorio_para(no) monta o DIRETÓRIO que vai com as licenças: os parceiros dos órgãos do nó (nome, tipo, domínio,
                              serviços e onde estão) e os tokens dos pares que envolvem os órgãos do nó. Assinado com a chave
                              Ed25519 das licenças. Sem banco e sem dado pessoal.
  nó       guardar_diretorio() confere assinatura, destinatário (NO_NOME) e idade (15 min) e grava orgaos_parceiros e pares.
  ambos    chamar()           fala com o parceiro: na mesma instalação, pelo endereço interno (como antes); em outra, pelo
                              domínio público em HTTPS (certificado conferido). HMAC + janela de 5 min + remessas_log nos dois.
Nó sem diretório (gestão antiga) segue com os pares que já tinha."""
import hashlib, hmac, json, secrets, time
from datetime import datetime, timezone
import httpx
from psycopg.types.json import Jsonb
from . import config, db

JANELA = 300
IDADE_MAX = 900


# ---------- gestão ----------
def garantir_pares(ibge=None):
    """Cria os pares que faltam entre os órgãos ativos do mesmo município (os dois sentidos). Devolve quantos criou."""
    n = 0
    sql = 'SELECT id, ibge FROM orgaos WHERE ativo' + (' AND ibge=%s' if ibge else '') + ' ORDER BY id'
    os_ = db.todos(db.PLATAFORMA, sql, (ibge,) if ibge else ())
    for a in os_:
        for b in os_:
            if a['id'] != b['id'] and a['ibge'] and a['ibge'] == b['ibge']:
                r = db.exe(db.PLATAFORMA, 'INSERT INTO pares_orgaos (origem_id, destino_id, token) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1',
                           (a['id'], b['id'], secrets.token_urlsafe(32)))
                n += 1 if r else 0
    return n


def renovar(oid):
    """Troca os tokens de todos os pares do órgão (os dois sentidos). Os nós recebem os novos em até 5 minutos."""
    pares = db.todos(db.PLATAFORMA, 'SELECT origem_id, destino_id FROM pares_orgaos WHERE origem_id=%s OR destino_id=%s', (oid, oid))
    for p in pares:  # token novo de verdade aleatório (secrets), um por sentido
        db.exe(db.PLATAFORMA, 'UPDATE pares_orgaos SET token=%s WHERE origem_id=%s AND destino_id=%s', (secrets.token_urlsafe(32), p['origem_id'], p['destino_id']))
    return len(pares)


def ligar(oid, ativo):
    return len(db.todos(db.PLATAFORMA, 'UPDATE pares_orgaos SET ativo=%s WHERE origem_id=%s OR destino_id=%s RETURNING 1', (ativo, oid, oid)))


def _hospedagem(o, nos):
    return (nos.get(o['no_id']) or {}).get('nome', '?') if o['no_id'] else 'gestao'


def _modulos(oid):
    return sorted(r['chave'] for r in db.todos(db.PLATAFORMA, 'SELECT chave FROM orgao_modulos WHERE orgao_id=%s AND contratado', (oid,)))


def parceiros_na_gestao(o):
    """(gestão) Os outros órgãos do município, com onde estão e o par de cada sentido."""
    nos = {n['id']: n for n in db.todos(db.PLATAFORMA, 'SELECT id, nome FROM nos')}
    out = []
    for p in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE ibge=%s AND id<>%s ORDER BY id', (o['ibge'], o['id'])):
        ida = db.um(db.PLATAFORMA, 'SELECT ativo, criado_em FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (o['id'], p['id']))
        volta = db.um(db.PLATAFORMA, 'SELECT ativo FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s', (p['id'], o['id']))
        out.append(dict(p, hospedagem=_hospedagem(p, nos), mesma_instalacao=p['no_id'] == o['no_id'], par_ida=ida, par_volta=volta))
    return out


def diretorio_para(no):
    """(gestão) Diretório assinado para o nó: parceiros dos órgãos dele e os pares que os envolvem."""
    from . import licenca
    garantir_pares()
    nos = {n['id']: n for n in db.todos(db.PLATAFORMA, 'SELECT id, nome FROM nos')}
    meus = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE no_id=%s', (no['id'],))
    ids = {o['id'] for o in meus}
    ibges = sorted({o['ibge'] for o in meus if o['ibge']})
    parceiros = [o for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE ibge = ANY(%s) ORDER BY id', (ibges,)) if o['id'] not in ids] if ibges else []
    pares = db.todos(db.PLATAFORMA, 'SELECT origem_id, destino_id, token, ativo FROM pares_orgaos WHERE origem_id = ANY(%s) OR destino_id = ANY(%s) ORDER BY 1, 2',
                     (list(ids), list(ids))) if ids else []
    doc = {'tipo': 'diretorio', 'no': no['nome'], 'emitido_em': datetime.now(timezone.utc).isoformat(),
           'parceiros': [{'id': o['id'], 'slug': o['slug'], 'nome': o['nome'], 'tipo': o['tipo'], 'dominio': o['dominio'], 'ibge': o['ibge'] or '',
                          'ativo': bool(o['ativo']), 'modulos': _modulos(o['id']), 'hospedagem': _hospedagem(o, nos)} for o in parceiros],
           'pares': [dict(p) for p in pares]}
    return licenca.assinar(doc)


# ---------- nó ----------
def guardar_diretorio(pacote, publica, agora=None):
    """(nó) Confere e grava o diretório. Devolve quantos parceiros gravou, ou None se o diretório foi recusado/ignorado."""
    from . import licenca
    if db.LOCAL == db.PLATAFORMA:
        return None  # nunca grava no banco de controle (gestão e portais juntos não usam diretório)
    d = licenca.verificar(pacote, publica) if pacote else None
    if not d or d.get('tipo') != 'diretorio' or d.get('no') != config.env('NO_NOME') or not isinstance(d.get('parceiros'), list):
        return None
    try:
        emitido = datetime.fromisoformat(d['emitido_em'])
    except (KeyError, ValueError, TypeError):
        return None
    idade = ((agora or datetime.now(timezone.utc)) - emitido).total_seconds()
    if not -300 <= idade <= IDADE_MAX:
        return None
    est = db.um(db.LOCAL, 'SELECT emitido_em FROM diretorio_estado WHERE id=1')
    if est and est['emitido_em'] and est['emitido_em'] > emitido:
        return None  # diretório mais antigo que o já guardado: ignorado
    with db.conn(db.LOCAL) as c:
        with c.transaction():
            c.execute('DELETE FROM orgaos_parceiros')
            for p in d['parceiros']:
                c.execute('INSERT INTO orgaos_parceiros (id, slug, nome, tipo, dominio, ibge, ativo, modulos, hospedagem) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                          (int(p['id']), str(p['slug'])[:60], str(p['nome'])[:200], str(p['tipo'])[:20], str(p['dominio'])[:253], str(p.get('ibge', ''))[:10],
                           bool(p.get('ativo', True)), Jsonb([str(m) for m in p.get('modulos') or []][:60]), str(p.get('hospedagem', ''))[:120]))
            c.execute('DELETE FROM pares_orgaos')
            for p in d.get('pares') or []:
                c.execute('INSERT INTO pares_orgaos (origem_id, destino_id, token, ativo) VALUES (%s,%s,%s,%s)',
                          (int(p['origem_id']), int(p['destino_id']), str(p['token']), bool(p.get('ativo', True))))
            c.execute('INSERT INTO diretorio_estado (id, emitido_em, recebido_em) VALUES (1,%s,now()) ON CONFLICT (id) DO UPDATE SET emitido_em=EXCLUDED.emitido_em, recebido_em=now()',
                      (emitido,))
    return len(d['parceiros'])


def tem_diretorio():
    if db.LOCAL == db.PLATAFORMA:
        return False
    try:
        return bool(db.um(db.LOCAL, 'SELECT 1 x FROM diretorio_estado WHERE id=1'))
    except Exception:
        return False


def parceiros_em_nos():
    """(gestão/tudo) Órgãos cadastrados aqui mas hospedados em nós: são de OUTRA instalação (falar por HTTPS)."""
    if config.PAPEL == 'no':
        return []
    nos = {n['id']: n for n in db.todos(db.PLATAFORMA, 'SELECT id, nome FROM nos')}
    return [dict(o, parceiro=True, modulos=_modulos(o['id']), hospedagem=_hospedagem(o, nos))
            for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE no_id IS NOT NULL AND ativo ORDER BY id')]


def de_fora():
    """Órgãos de outras instalações que esta conhece: no nó, os do diretório; na gestão, os hospedados em nós."""
    return parceiros_no_no() if config.PAPEL == 'no' else parceiros_em_nos()


def parceiros_no_no():
    if db.LOCAL == db.PLATAFORMA:
        return []
    try:
        return [dict(p, parceiro=True) for p in db.todos(db.LOCAL, 'SELECT * FROM orgaos_parceiros WHERE ativo ORDER BY id')]
    except Exception:
        return []


# ---------- quem é quem (vale nos dois papéis) ----------
def locais():
    from . import orgaos
    return orgaos.todos()


def orgao(slug=None, id_=None):
    """Órgão desta instalação ou parceiro de outra (só leitura). Parceiro vem marcado com parceiro=True."""
    from . import orgaos
    o = orgaos.por_slug(slug) if slug else orgaos.por_id(id_)
    if o:
        return o
    return next((p for p in de_fora() if (slug and p['slug'] == slug) or (id_ and p['id'] == id_)), None)


def parceiros(o):
    """Os outros órgãos do mesmo município, onde quer que estejam. Cada um com mesma_instalacao=True/False."""
    from . import orgaos
    aqui = [dict(x, mesma_instalacao=True) for x in orgaos.todos() if x['ibge'] == o['ibge'] and x['id'] != o['id']]
    ids = {x['id'] for x in aqui}
    fora = [dict(p, mesma_instalacao=False) for p in de_fora() if p['ibge'] == o['ibge'] and p['id'] not in ids and p['id'] != o['id']]
    return aqui + fora


def par(origem, destino):
    return db.um(db.LOCAL, 'SELECT * FROM pares_orgaos WHERE origem_id=%s AND destino_id=%s AND ativo', (origem['id'], destino['id']))


def assinatura(token, momento, metodo, caminho, corpo: bytes):
    msg = f'{momento}\n{metodo}\n{caminho}\n{hashlib.sha256(corpo).hexdigest()}'.encode()
    return hmac.new(token.encode(), msg, hashlib.sha256).hexdigest()


def log(origem, destino, acao, ok, detalhe=''):
    db.exe(db.LOCAL, 'INSERT INTO remessas_log (origem, destino, acao, ok, detalhe) VALUES (%s,%s,%s,%s,%s)', (origem, destino, acao[:200], ok, detalhe[:500]))


def _cliente(destino):
    """Cliente HTTP para o parceiro (substituível nos testes). Mesma instalação: endereço interno com o Host do parceiro.
    Outra: o domínio público em HTTPS, com certificado conferido. Chamar fora do laço de eventos (pode ser o próprio processo)."""
    if destino.get('parceiro'):
        return httpx.Client(base_url=f"https://{destino['dominio']}", timeout=30, verify=True)
    return httpx.Client(base_url=config.INTERNO_BASE, timeout=30)


def _host(destino):
    """Cabeçalhos de cada requisição: na mesma instalação, o Host do parceiro (o endereço é o interno)."""
    return {} if destino.get('parceiro') else {'Host': destino['dominio'], 'X-Forwarded-Proto': 'https'}


def _pedir(destino, metodo, caminho, content=None, headers=None):
    """Uma requisição ao parceiro. Mesma instalação: endereço interno (INTERNO_BASE, o serviço "app" do compose, que o app
    e o worker alcançam); se ele não responder (ex.: o órgão mudou de instalação e o diretório ainda não chegou), tenta o
    domínio público em HTTPS, com certificado conferido. Outra instalação: direto pelo domínio público."""
    h = dict(headers or {})
    if not destino.get('parceiro'):
        try:
            with _cliente(destino) as c:
                return c.request(metodo, caminho, content=content, headers=dict(h, **_host(destino)))
        except (httpx.ConnectError, httpx.ConnectTimeout):
            pass
    with _cliente(dict(destino, parceiro=True)) as c:
        return c.request(metodo, caminho, content=content, headers=h)


def chamar(origem, destino, metodo, caminho, dados=None, acao=''):
    """Chamada assinada ao parceiro. Devolve o JSON da resposta ou levanta ValueError com a explicação."""
    p = par(origem, destino)
    if not p:
        raise ValueError('Não há integração ativa entre os órgãos (par sem token ou desligado).')
    corpo = json.dumps(dados or {}, ensure_ascii=False).encode() if metodo == 'POST' else b''
    m = str(int(time.time()))
    h = {'Content-Type': 'application/json', 'X-Portal-Origem': origem['slug'], 'X-Portal-Momento': m,
         'X-Portal-Assinatura': assinatura(p['token'], m, metodo, caminho, corpo)}
    try:
        resp = _pedir(destino, metodo, caminho, content=corpo or None, headers=h)
        ok = resp.status_code < 400
        log(origem['slug'], destino['slug'], acao or f'{metodo} {caminho}', ok, '' if ok else resp.text[:200])
        if not ok:
            erro = resp.json().get('erro', '') if resp.headers.get('content-type', '').startswith('application/json') else ''
            raise ValueError(f"{destino['nome']} recusou ({resp.status_code}){': ' + erro if erro else ''}.")
        return resp.json()
    except httpx.HTTPError as e:
        log(origem['slug'], destino['slug'], acao or f'{metodo} {caminho}', False, type(e).__name__)
        raise ValueError(f"Não foi possível falar com {destino['nome']} ({type(e).__name__}).")


def publico(destino, caminho):
    """GET de uma API PÚBLICA do parceiro (ex.: /legislacao.json), interna ou por HTTPS conforme onde ele está."""
    resp = _pedir(destino, 'GET', caminho)
    resp.raise_for_status()
    return resp.json()


async def autenticar(request):
    """(servidor) Confere origem, horário e assinatura da chamada. Devolve (origem, destino, corpo)."""
    from fastapi import HTTPException
    destino = request.state.orgao
    origem = orgao(slug=request.headers.get('x-portal-origem', ''))
    corpo = await request.body()
    m = request.headers.get('x-portal-momento', '')
    if not origem or not m.isdigit() or abs(time.time() - int(m)) > JANELA:
        log(request.headers.get('x-portal-origem', '?')[:40], destino['slug'], request.url.path, False, 'origem ou momento inválido')
        raise HTTPException(401, 'Recusado: origem ou horário inválido.')
    p = par(origem, destino)
    caminho = request.url.path.replace('/_p', '', 1)
    if not p or not hmac.compare_digest(assinatura(p['token'], m, request.method, caminho, corpo), request.headers.get('x-portal-assinatura', '')):
        log(origem['slug'], destino['slug'], caminho, False, 'assinatura inválida')
        raise HTTPException(401, 'Recusado: assinatura inválida.')
    return origem, destino, corpo
