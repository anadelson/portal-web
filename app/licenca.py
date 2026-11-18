"""Licença assinada por órgão — separação gestão × portais, etapa A1 (11/11/2026).

A gestão é a única fonte da verdade do que cada órgão contratou (contrato, vigência, carência, suspensão, módulos).
Ela emite, para cada órgão, um documento ASSINADO (Ed25519). Um nó (VPS de portais) busca as licenças na gestão
(o nó sempre chama; a gestão nunca acessa o nó), confere a assinatura com a chave pública e guarda em cache.

  papel "tudo"  (padrão, igual a antes): o documento é montado na hora a partir do banco de controle — sem cache,
                 sem diferença nenhuma no que o portal mostra.
  papel "no":    só vale a licença do cache com assinatura conferida e dentro da validade. Sem licença válida
                 (gestão fora do ar por mais de LICENCA_VALIDADE_DIAS, licença adulterada): carência — só os
                 módulos obrigatórios (transparência, e-SIC, ouvidoria) seguem no ar. Nunca derruba a transparência.

A chave privada fica no banco de controle CIFRADA com uma chave derivada da SECRET_KEY; nenhuma função a devolve.
O token do nó só existe em claro na tela de criação (uma vez) e no .env do nó; a gestão guarda o hash.

  python -m app.licenca chaves          # garante o par de chaves (gestão) e mostra só a impressão digital e a chave pública
  python -m app.licenca puxar           # (nó) busca as licenças na gestão agora
"""
import base64, hashlib, hmac, json, secrets, sys, time
from datetime import date, datetime, timedelta, timezone
from psycopg.types.json import Jsonb
from . import config, db

VERSAO = 1
_memo = {}  # orgao_id → (instante, documento) no papel "no"
MEMO_S = 30

# ---------- chaves ----------
def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('licenca|' + config.SECRET_KEY).encode()).digest()))

def _b64(b):
    return base64.b64encode(b).decode()

def impressao(publica_b64):
    return hashlib.sha256(base64.b64decode(publica_b64)).hexdigest()[:16]

def garantir_chaves():
    """Cria o par Ed25519 da gestão se ainda não existir. Devolve (impressão, chave pública em base64)."""
    r = db.um(db.PLATAFORMA, 'SELECT publica, impressao FROM licenca_chaves WHERE ativa ORDER BY id DESC LIMIT 1')
    if r:
        return r['impressao'], r['publica']
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization as S
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(S.Encoding.Raw, S.PrivateFormat.Raw, S.NoEncryption())
    pub = _b64(k.public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw))
    db.exe(db.PLATAFORMA, 'INSERT INTO licenca_chaves (publica, privada_cifrada, impressao) VALUES (%s,%s,%s)',
           (pub, _fernet().encrypt(priv).decode(), impressao(pub)))
    return impressao(pub), pub

def _privada():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    r = db.um(db.PLATAFORMA, 'SELECT privada_cifrada FROM licenca_chaves WHERE ativa ORDER BY id DESC LIMIT 1')
    if not r:
        garantir_chaves()
        r = db.um(db.PLATAFORMA, 'SELECT privada_cifrada FROM licenca_chaves WHERE ativa ORDER BY id DESC LIMIT 1')
    return Ed25519PrivateKey.from_private_bytes(_fernet().decrypt(r['privada_cifrada'].encode()))

def chave_publica():
    """Chave pública usada para conferir: no nó, a do .env; na gestão/tudo, a do banco de controle."""
    if config.PAPEL == 'no':
        return config.LICENCA_CHAVE_PUBLICA
    r = db.um(db.PLATAFORMA, 'SELECT publica FROM licenca_chaves WHERE ativa ORDER BY id DESC LIMIT 1')
    return r['publica'] if r else ''

# ---------- documento ----------
def _iso(d):
    return d.isoformat() if isinstance(d, (date, datetime)) else d

def documento(o, emitida=None):
    """O que o órgão contratou, montado do banco de controle (só a gestão faz isto)."""
    c = db.um(db.PLATAFORMA, 'SELECT * FROM contratos WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
    mods = sorted(r['chave'] for r in db.todos(db.PLATAFORMA, 'SELECT chave FROM orgao_modulos WHERE orgao_id=%s AND contratado', (o['id'],)))
    emitida = emitida or datetime.now(timezone.utc)
    return {'v': VERSAO, 'serial': int(emitida.timestamp() * 1000),
            'orgao': {k: o.get(k) for k in ('id', 'slug', 'nome', 'tipo', 'dominio', 'banco', 'municipio', 'ibge', 'plano', 'cor', 'ativo')},
            'modulos': mods,
            'contrato': {'inicio': _iso(c['inicio']), 'fim': _iso(c['fim']), 'carencia_dias': c['carencia_dias'], 'suspenso': bool(c['suspenso'])} if c else None,
            'emitida_em': emitida.isoformat(), 'valida_ate': (emitida + timedelta(days=config.LICENCA_VALIDADE_DIAS)).isoformat()}

def _canon(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()

def assinar(doc):
    return {'doc': doc, 'sig': _b64(_privada().sign(_canon(doc))), 'chave': impressao(garantir_chaves()[1])}

def verificar(pacote, publica_b64):
    """Documento se a assinatura confere com a chave pública; None se não confere (adulterado, outra chave, formato errado)."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(publica_b64)).verify(base64.b64decode(pacote['sig']), _canon(pacote['doc']))
        return pacote['doc']
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return None

def emitir(o):
    """Assina a licença atual do órgão e guarda como a última emitida."""
    p = assinar(documento(o))
    db.exe(db.PLATAFORMA, """INSERT INTO licencas_emitidas (orgao_id, serial, pacote, emitida_em) VALUES (%s,%s,%s,now())
                             ON CONFLICT (orgao_id) DO UPDATE SET serial=EXCLUDED.serial, pacote=EXCLUDED.pacote, emitida_em=now()""",
           (o['id'], p['doc']['serial'], Jsonb(p)))
    return p

# ---------- nós ----------
def _hash_token(t):
    return hashlib.sha256(('no|' + t).encode()).hexdigest()

def criar_no(nome, instancia=''):
    """Cria o nó e devolve o token EM CLARO (mostrado uma vez só; a gestão guarda o hash).
    instancia: pasta /opt/portal_web-<instancia> na VPS (mais de um nó na mesma VPS); vazio = /opt/portal_web."""
    token = secrets.token_urlsafe(32)
    db.exe(db.PLATAFORMA, 'INSERT INTO nos (nome, token_hash, instancia) VALUES (%s,%s,%s)', (nome, _hash_token(token), instancia or ''))
    return token

def novo_token(no_id):
    token = secrets.token_urlsafe(32)
    db.exe(db.PLATAFORMA, 'UPDATE nos SET token_hash=%s WHERE id=%s', (_hash_token(token), no_id))
    return token

def no_do_token(token):
    if not token:
        return None
    h = _hash_token(token)
    for n in db.todos(db.PLATAFORMA, 'SELECT * FROM nos WHERE ativo'):
        if hmac.compare_digest(n['token_hash'], h):
            return n
    return None

def entregar(no, ip='', versao=''):
    """Resposta da API da gestão para um nó: as licenças (recém-assinadas) dos órgãos hospedados nele."""
    db.exe(db.PLATAFORMA, 'UPDATE nos SET ultimo_contato=now(), ultimo_ip=%s, versao=%s WHERE id=%s', (ip[:60], versao[:40], no['id']))
    out, ids = [], []
    for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE no_id=%s ORDER BY id', (no['id'],)):
        out.append(emitir(o)); ids.append(o['id'])
        db.exe(db.PLATAFORMA, 'UPDATE licencas_emitidas SET entregue_em=now() WHERE orgao_id=%s', (o['id'],))
    agora = datetime.now(timezone.utc)
    # inventário ASSINADO (18/11/2026): a lista completa dos órgãos do nó. Com ele o nó esquece o órgão que mudou de nó
    # (sem isso, a licença antiga ficava no cache e o nó antigo seguia servindo o portal até ela vencer). Nó antigo ignora.
    inv = assinar({'tipo': 'inventario', 'no': no['nome'], 'orgaos': ids, 'emitido_em': agora.isoformat()})
    return {'chave': chave_publica(), 'impressao': impressao(chave_publica()), 'licencas': out, 'inventario': inv, 'gerado_em': agora.isoformat()}

# ---------- lado do nó ----------
def guardar(pacotes, publica):
    """Confere e guarda no cache as licenças recebidas. Devolve (aceitas, recusadas). Licença mais antiga que a do cache é ignorada."""
    ok = ruim = 0
    for p in pacotes:
        d = verificar(p, publica)
        if not d or d.get('v') != VERSAO or 'orgao' not in d or 'modulos' not in d:  # só licença (ordem assinada não vale como licença)
            ruim += 1
            continue
        o = d['orgao']
        db.exe(db.LOCAL, """INSERT INTO licencas_cache (orgao_id, slug, dominio, serial, pacote, valida_ate, recebida_em) VALUES (%s,%s,%s,%s,%s,%s,now())
                                 ON CONFLICT (orgao_id) DO UPDATE SET slug=EXCLUDED.slug, dominio=EXCLUDED.dominio, serial=EXCLUDED.serial, pacote=EXCLUDED.pacote,
                                 valida_ate=EXCLUDED.valida_ate, recebida_em=now() WHERE licencas_cache.serial <= EXCLUDED.serial""",
               (o['id'], o['slug'], o['dominio'], d['serial'], Jsonb(p), d['valida_ate']))
        _memo.pop(o['id'], None)
        ok += 1
    return ok, ruim

def buscar_na_gestao():
    """GET {GESTAO_URL}/api/no/licencas com o token do nó. Devolve o JSON (ou levanta exceção, sem o token na mensagem)."""
    import httpx
    url = config.GESTAO_URL.rstrip('/') + '/api/no/licencas'
    r = httpx.get(url, headers={'Authorization': f'Bearer {config.NO_TOKEN}', 'User-Agent': config.USER_AGENT, 'X-Versao': VERSAO_APP()}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'gestão respondeu HTTP {r.status_code}')
    return r.json()

def VERSAO_APP():
    try:
        from pathlib import Path
        return (Path(__file__).resolve().parent / 'VERSAO').read_text().strip()[:40]
    except Exception:
        return ''

def puxar():
    """(nó) Busca e guarda as licenças. A chave pública que vale é a do .env do nó, nunca a que veio na resposta."""
    if config.PAPEL != 'no':
        return 'papel não é "no": nada a buscar'
    if not (config.GESTAO_URL and config.NO_TOKEN and config.LICENCA_CHAVE_PUBLICA):
        return 'faltam GESTAO_URL, NO_TOKEN ou LICENCA_CHAVE_PUBLICA no .env do nó'
    d = buscar_na_gestao()
    ok, ruim = guardar(d.get('licencas', []), config.LICENCA_CHAVE_PUBLICA)
    saiu = esquecer(d.get('inventario'), config.LICENCA_CHAVE_PUBLICA)
    return (f'{ok} licença(s) aceitas' + (f', {ruim} RECUSADA(S) (assinatura não confere)' if ruim else '')
            + (f'; {saiu} órgão(s) que saíram deste nó (licença removida)' if saiu else ''))

def esquecer(inventario, publica, agora=None):
    """(nó) Remove do cache as licenças dos órgãos que não estão mais no inventário assinado da gestão. Só vale inventário
    com assinatura conferida, deste nó (NO_NOME) e recente (até 15 minutos): resposta antiga ou de outro nó não apaga nada."""
    d = verificar(inventario, publica) if inventario else None
    if not d or d.get('tipo') != 'inventario' or d.get('no') != config.env('NO_NOME') or not isinstance(d.get('orgaos'), list):
        return 0
    try:
        idade = ((agora or _agora()) - datetime.fromisoformat(d['emitido_em'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return 0
    if not -300 <= idade <= 900:
        return 0
    fora = db.todos(db.LOCAL, 'SELECT orgao_id FROM licencas_cache WHERE NOT (orgao_id = ANY(%s))', ([int(x) for x in d['orgaos']],))
    for r in fora:
        db.exe(db.LOCAL, 'DELETE FROM licencas_cache WHERE orgao_id=%s', (r['orgao_id'],))
        _memo.pop(r['orgao_id'], None)
    return len(fora)

# ---------- uso pelo portal, painel e worker ----------
def _agora():
    return datetime.now(timezone.utc)

def vigente(o):
    """Documento da licença em vigor para o órgão, ou None (só no papel "no": sem licença válida)."""
    if config.PAPEL != 'no':
        return documento(o)  # gestão e portais juntos: direto do banco de controle, como sempre foi
    m = _memo.get(o['id'])
    if m and time.monotonic() - m[0] < MEMO_S:
        return m[1]
    r = db.um(db.LOCAL, 'SELECT pacote FROM licencas_cache WHERE orgao_id=%s', (o['id'],))
    d = verificar(r['pacote'], chave_publica()) if r else None
    d = d if d and 'modulos' in d else None
    if d and datetime.fromisoformat(d['valida_ate']) < _agora():
        d = None  # vencida: a gestão está sem contato há mais que a validade
    _memo[o['id']] = (time.monotonic(), d)
    return d

def contrato_de(doc):
    """Contrato da licença no formato que web.situacao_contrato espera."""
    c = (doc or {}).get('contrato')
    if not c:
        return None
    return {'inicio': date.fromisoformat(c['inicio']), 'fim': date.fromisoformat(c['fim']), 'carencia_dias': c['carencia_dias'], 'suspenso': c['suspenso']}

def situacao(o):
    """Resumo para telas: de onde vem a licença, quando foi emitida/recebida e até quando vale."""
    if config.PAPEL != 'no':
        e = db.um(db.PLATAFORMA, 'SELECT * FROM licencas_emitidas WHERE orgao_id=%s', (o['id'],))
        n = db.um(db.PLATAFORMA, 'SELECT n.* FROM nos n JOIN orgaos o ON o.no_id=n.id WHERE o.id=%s', (o['id'],))
        return {'modo': 'no' if n else 'local', 'no': n, 'emitida': e}
    r = db.um(db.LOCAL, 'SELECT recebida_em, valida_ate FROM licencas_cache WHERE orgao_id=%s', (o['id'],))
    return {'modo': 'recebida', 'recebida_em': r and r['recebida_em'], 'valida_ate': r and r['valida_ate'], 'valida': bool(vigente(o))}

def main(args):
    cmd = args[0] if args else ''
    if cmd == 'chaves':
        imp, pub = garantir_chaves()
        print(f'impressão digital: {imp}\nchave pública (vai no .env do nó como LICENCA_CHAVE_PUBLICA): {pub}')
    elif cmd == 'puxar':
        print(puxar())
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
