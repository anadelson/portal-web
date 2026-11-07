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
