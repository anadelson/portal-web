"""Instalação de um nó pelo console (12/11/2026): gerar e baixar os pacotes sem usar o terminal da gestão.

  Pacote de CÓDIGO   a própria versão em produção (o que está na imagem: app/, deploy/, Dockerfile, docker-compose.yml,
                     requirements.txt), com o instalador deploy/no/instalar.sh. Não leva nenhum segredo.
  Pacote de SEGREDOS as chaves que precisam ser IGUAIS no nó (SECRET_KEY, TOTP_CHAVE, CPF_HMAC_CHAVE, CHAVE_CREDENCIAIS…),
                     a pasta segredos/ (certificado do Diário), o nome do nó, o endereço da gestão, a chave pública e,
                     se pedido, um TOKEN NOVO do nó — o instalador já sai preenchido. Vai CIFRADO (AES-256, PBKDF2 600 mil iterações,
                     formato do `openssl enc`) com uma senha de pacote escolhida na hora e que NÃO é guardada.

Para gerar o de segredos o gestor confirma a própria senha e o código do 2FA. Cada pacote sai por um link de USO ÚNICO
(vale 60 minutos; enquanto vale, o gestor pode rever os comandos na tela do nó), que o próprio nó baixa com curl — os arquivos não passam pelo computador de ninguém.
Tudo fica no registro do console (sem senha, token ou link)."""
import hashlib, io, os, re, secrets, tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import config, db

VALIDADE_MIN = 60
ITERACOES = 600_000
FONTE = Path(os.environ.get('FONTE_DIR', '/srv/fonte'))   # Dockerfile, docker-compose.yml, requirements.txt, deploy/ (copiados na imagem)
APP = Path(__file__).resolve().parent
# variáveis do .env que NÃO vão para o nó (o nó gera a dele ou não usa)
FORA = {'PG_PASSWORD', 'PG_HOST', 'PG_PORT', 'SENHA_INICIAL_ADMIN', 'SENHA_INICIAL_GESTOR', 'DOMINIO_PM', 'DOMINIO_CM', 'DATA_SIMULADA', 'TESTE',
        'PAPEL', 'NO_TOKEN', 'NO_NOME', 'GESTAO_URL', 'LICENCA_CHAVE_PUBLICA', 'VPS_IP', 'COMPOSE_FILE', 'REDE_PROXY', 'PROXY_MODO',
        'NGINX_C', 'CERTBOT_C', 'CONF_DIR', 'CERTS_DIR', 'PROXY_CERTS_DIR', 'NO_BANCO', 'FONTE_DIR', 'DADOS_DIR', 'SEGREDOS_DIR'}

def pasta():
    p = Path(config.DADOS_DIR) / '_instalacao'
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)
    return p

def versao():
    try:
        return (APP / 'VERSAO').read_text().strip()[:40] or 'sem versão'
    except OSError:
        return 'sem versão'

def codigo_disponivel():
    return (FONTE / 'docker-compose.yml').is_file() and (FONTE / 'deploy' / 'no' / 'instalar.sh').is_file()

# ---------- pacotes ----------
def _ignora(caminho):
    partes = caminho.parts
    return '__pycache__' in partes or caminho.suffix == '.pyc' or 'conf.d' in partes

def pacote_codigo():
    """tar.gz com a raiz portal_web/ (o que roda em produção). Levanta RuntimeError se a imagem não tiver as fontes."""
    if not codigo_disponivel():
        raise RuntimeError('esta instalação não tem o código de implantação na imagem (gere a imagem de novo)')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for nome in ('Dockerfile', 'docker-compose.yml', 'requirements.txt'):
            t.add(FONTE / nome, arcname=f'portal_web/{nome}')
        for base, dest in ((FONTE / 'deploy', 'portal_web/deploy'), (APP, 'portal_web/app')):
            for p in sorted(base.rglob('*')):
                rel = p.relative_to(base)
                if p.is_file() and not _ignora(rel):
                    t.add(p, arcname=f'{dest}/{rel.as_posix()}', recursive=False)
    return buf.getvalue()

def _env_origem():
    """Chaves do .env em uso (as que o código lê), menos as que são só da gestão. Valores nunca vão para tela ou log."""
    nomes = set()
    for p in APP.rglob('*.py'):
        nomes |= set(re.findall(r"env\('([A-Z][A-Z0-9_]+)'", p.read_text(encoding='utf-8', errors='ignore')))
    nomes |= {'PG_USER', 'DOMINIO_GESTAO', 'NOME_PLATAFORMA', 'USER_AGENT'}
    return {k: os.environ[k] for k in sorted(nomes - FORA) if os.environ.get(k)}

def pacote_segredos(no, token=None):
    """tar.gz em memória: env-origem e segredos/. O env-origem SEMPRE leva os dados do nó que não são segredo (endereço da
    gestão, nome do nó e chave pública da licença), para o instalador sair preenchido mesmo sem token novo; o token do nó
    só vai quando um token novo é gerado (o atual não fica guardado na gestão, só o hash). Corrigido em 18/11/2026: antes,
    sem token novo, o pacote saía sem o nome do nó e o instalador perdia esse dado."""
    from . import licenca
    env = _env_origem()
    imp, pub = licenca.garantir_chaves()
    env.update({'GESTAO_URL': f'https://{config.DOMINIO_GESTAO}', 'NO_NOME': no['nome'], 'LICENCA_CHAVE_PUBLICA': pub})
    if token:
        env['NO_TOKEN'] = token
    linhas = ''.join(f'{k}={v}\n' for k, v in env.items()).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        info = tarfile.TarInfo('env-origem'); info.size = len(linhas); info.mode = 0o600
        t.addfile(info, io.BytesIO(linhas))
        seg = Path(config.SEGREDOS_DIR)
        if seg.is_dir():
            for p in sorted(seg.rglob('*')):
                if p.is_file():
                    t.add(p, arcname=f'segredos/{p.relative_to(seg).as_posix()}', recursive=False)
    return buf.getvalue()

def cifrar(dados, senha):
    """Mesmo formato de `openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -md sha256 -salt` (o instalador decifra com o openssl)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes, padding
    sal = secrets.token_bytes(8)
    km = PBKDF2HMAC(algorithm=hashes.SHA256(), length=48, salt=sal, iterations=ITERACOES).derive(senha.encode())
    p = padding.PKCS7(128).padder(); dados = p.update(dados) + p.finalize()
    c = Cipher(algorithms.AES(km[:32]), modes.CBC(km[32:])).encryptor()
    return b'Salted__' + sal + c.update(dados) + c.finalize()

def decifrar(cifrado, senha):
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes, padding
    if cifrado[:8] != b'Salted__':
        raise ValueError('formato inválido')
    km = PBKDF2HMAC(algorithm=hashes.SHA256(), length=48, salt=cifrado[8:16], iterations=ITERACOES).derive(senha.encode())
    d = Cipher(algorithms.AES(km[:32]), modes.CBC(km[32:])).decryptor()
    dados = d.update(cifrado[16:]) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    return u.update(dados) + u.finalize()

# ---------- links de uso único ----------
def _hash(token):
    return hashlib.sha256(('instalacao|' + token).encode()).hexdigest()

def _fernet():
    import base64
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('instalacao|' + config.SECRET_KEY).encode()).digest()))

def novo_link(no, tipo, quem, dados=None, lote='', token_novo=False):
    """Registra um link de uso único. Para 'segredos', grava o arquivo JÁ CIFRADO (só root e o app leem). Devolve o token.
    O token fica guardado cifrado só enquanto o link vale, para o gestor poder rever os comandos."""
    token = secrets.token_urlsafe(32)
    arquivo, tam, sha = '', 0, ''
    if dados is not None:
        nome = secrets.token_hex(16) + '.enc'
        caminho = pasta() / nome
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(dados)
        arquivo, tam, sha = nome, len(dados), hashlib.sha256(dados).hexdigest()
    db.exe(db.PLATAFORMA, 'INSERT INTO instalacao_links (no_id, tipo, token_hash, token_cifrado, lote, token_novo, arquivo, tamanho, sha256, criado_por, expira_em) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
           (no['id'], tipo, _hash(token), _fernet().encrypt(token.encode()).decode(), lote, token_novo, arquivo, tam, sha, quem, datetime.now(timezone.utc) + timedelta(minutes=VALIDADE_MIN)))
    return token

def novo_lote():
    return secrets.token_hex(8)

def cancelar(no_id):
    """Encerra os lotes do nó (ao gerar novos ou pelo botão Cancelar): links não usados deixam de valer. Devolve quantos não usados."""
    r = db.todos(db.PLATAFORMA, "UPDATE instalacao_links SET cancelado_em=now(), expira_em=LEAST(expira_em, now()), token_cifrado='' "
                                "WHERE no_id=%s AND cancelado_em IS NULL AND expira_em > now() RETURNING baixado_em", (no_id,))
    limpar()
    return sum(1 for x in r if x['baixado_em'] is None)  # os já baixados só saem da tela

def preparados(no_id, base):
    """Último lote do nó ainda no prazo e não cancelado: links (só os não usados), situação de cada um e validade. None se não houver."""
    u = db.um(db.PLATAFORMA, "SELECT lote FROM instalacao_links WHERE no_id=%s AND lote<>'' AND cancelado_em IS NULL AND expira_em > now() ORDER BY id DESC LIMIT 1", (no_id,))
    if not u:
        return None
    itens = {r['tipo']: r for r in db.todos(db.PLATAFORMA, 'SELECT * FROM instalacao_links WHERE no_id=%s AND lote=%s', (no_id, u['lote']))}
    out = {'token_novo': any(r['token_novo'] for r in itens.values()), 'criado_em': min(r['criado_em'] for r in itens.values()),
           'expira_em': max(r['expira_em'] for r in itens.values()), 'criado_por': next(iter(itens.values()))['criado_por']}
    for tipo in ('codigo', 'segredos'):
        r = itens.get(tipo)
        if not r:
            continue
        link = ''
        if r['baixado_em'] is None and r['token_cifrado']:
            link = base + _fernet().decrypt(r['token_cifrado'].encode()).decode()
        out[tipo] = {'link': link, 'baixado_em': r['baixado_em'], 'baixado_ip': r['baixado_ip'], 'expira_em': r['expira_em']}
    return out

def usar_link(token, ip=''):
    """Download: devolve (tipo, bytes, nome_do_arquivo) uma vez só; None se inválido, usado ou vencido."""
    if not token or len(token) > 100:
        return None
    r = db.um(db.PLATAFORMA, "UPDATE instalacao_links SET baixado_em=now(), baixado_ip=%s, token_cifrado='' WHERE token_hash=%s AND baixado_em IS NULL AND cancelado_em IS NULL AND expira_em > now() RETURNING *",
              (ip[:60], _hash(token)))
    if not r:
        return None
    n = db.um(db.PLATAFORMA, 'SELECT nome FROM nos WHERE id=%s', (r['no_id'],))
    if r['tipo'] == 'codigo':
        dados, nome = pacote_codigo(), f"portal-codigo-{re.sub(r'[^A-Za-z0-9._-]', '_', versao())}.tar.gz"
    else:
        p = pasta() / r['arquivo']
        try:
            dados = p.read_bytes()
        finally:
            p.unlink(missing_ok=True)
        nome = 'segredos-no.tar.gz.enc'
    db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)',
           ('instalação de nó', f"Pacote de {r['tipo']} do nó {n['nome'] if n else r['no_id']} baixado (IP {ip or '?'})"))
    return r['tipo'], dados, nome

def limpar():
    """Apaga arquivos e links guardados de links vencidos, cancelados ou já usados."""
    db.exe(db.PLATAFORMA, "UPDATE instalacao_links SET token_cifrado='' WHERE token_cifrado<>'' AND (expira_em < now() OR baixado_em IS NOT NULL)")
    for r in db.todos(db.PLATAFORMA, "SELECT id, arquivo FROM instalacao_links WHERE arquivo <> '' AND (expira_em <= now() OR baixado_em IS NOT NULL)"):
        (pasta() / r['arquivo']).unlink(missing_ok=True)
        db.exe(db.PLATAFORMA, "UPDATE instalacao_links SET arquivo='' WHERE id=%s", (r['id'],))
