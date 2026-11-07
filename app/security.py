import hashlib, hmac, os, secrets, base64

def hash_senha(senha: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=2**14, r=8, p=1, dklen=32)
    return 'scrypt$' + base64.b64encode(sal).decode() + '$' + base64.b64encode(h).decode()

def confere_senha(senha: str, guardado: str | None) -> bool:
    if not guardado or not guardado.startswith('scrypt$'):
        return False
    _, s, h = guardado.split('$')
    calc = hashlib.scrypt(senha.encode(), salt=base64.b64decode(s), n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(calc, base64.b64decode(h))

def token() -> str:
    return secrets.token_urlsafe(24)

def mascara_ip(ip: str) -> str:
    p = (ip or '').split('.')
    return f'{p[0]}.***.***.{p[3]}' if len(p) == 4 else '***'

# ---------- segundo fator (TOTP, RFC 6238), códigos de recuperação e hash do CPF (Fase 6) ----------
import struct, time

def novo_segredo_totp() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip('=')

def totp(segredo: str, t: float | None = None, passo: int = 30, digitos: int = 6) -> str:
    chave = base64.b32decode(segredo + '=' * (-len(segredo) % 8))
    contador = int((t if t is not None else time.time()) // passo)
    h = hmac.new(chave, struct.pack('>Q', contador), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digitos).zfill(digitos)

def confere_totp(segredo: str, codigo: str, janela: int = 1) -> bool:
    codigo = ''.join(c for c in (codigo or '') if c.isdigit())
    if len(codigo) != 6 or not segredo:
        return False
    agora = time.time()
    return any(hmac.compare_digest(totp(segredo, agora + d * 30), codigo) for d in range(-janela, janela + 1))

def _fernet():
    from cryptography.fernet import Fernet
    from . import config
    chave = config.TOTP_CHAVE or base64.urlsafe_b64encode(hashlib.sha256(('totp|' + config.SECRET_KEY).encode()).digest()).decode()
    return Fernet(chave.encode())

def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()

def decifrar(texto: str) -> str:
    return _fernet().decrypt(texto.encode()).decode() if texto else ''

def _h(codigo: str) -> str:
    from . import config
    return hmac.new(config.SECRET_KEY.encode(), ('rec|' + codigo.replace('-', '').upper()).encode(), hashlib.sha256).hexdigest()

def codigos_recuperacao(n: int = 10):
    """Devolve (códigos para mostrar UMA vez, hashes para guardar)."""
    cods = ['-'.join(secrets.token_hex(2).upper() for _ in range(3)) for _ in range(n)]
    return cods, [_h(c) for c in cods]

def usar_recuperacao(codigo: str, hashes: list) -> list | None:
    """Se o código vale, devolve a lista sem ele (uso único); senão None."""
    h = _h(codigo or '')
    return [x for x in hashes if x != h] if h in (hashes or []) else None

def cpf_hash(cpf: str) -> str:
    """HMAC do CPF com chave secreta: permite achar o usuário que entrou pelo gov.br sem gravar o CPF."""
    from . import config
    d = ''.join(c for c in (cpf or '') if c.isdigit())
    if len(d) != 11:
        raise ValueError('CPF deve ter 11 dígitos.')
    if not config.CPF_HMAC_CHAVE:
        raise ValueError('Defina CPF_HMAC_CHAVE no .env para vincular CPF (login gov.br).')
    return hmac.new(config.CPF_HMAC_CHAVE.encode(), d.encode(), hashlib.sha256).hexdigest()

def otpauth(segredo: str, conta: str, emissor: str) -> str:
    from urllib.parse import quote
    return f'otpauth://totp/{quote(emissor)}:{quote(conta)}?secret={segredo}&issuer={quote(emissor)}&algorithm=SHA1&digits=6&period=30'

def qr_svg(texto: str) -> str:
    import qrcode, qrcode.image.svg
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding='unicode')
