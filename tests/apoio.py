"""Apoio aos testes: login com segundo fator (TOTP) obrigatório. Só para banco de TESTE."""
import re
from app.security import totp

SEGREDOS = {}  # e-mail → segredo TOTP cadastrado no teste (para logins seguintes)
CODIGOS = {}   # e-mail → códigos de recuperação mostrados no cadastro

def tok(c, url):
    m = re.search(r'name="csrf" value="([^"]+)"', c.get(url).text)
    return m.group(1) if m else ''

def entrar(c, email, senha, nova=None, prefixo='/admin'):
    """Senha → segundo fator (cadastro na 1ª vez, código nas seguintes) → troca de senha se exigida. Devolve a última resposta."""
    r = c.post(f'{prefixo}/login', data={'csrf': tok(c, f'{prefixo}/login'), 'email': email, 'senha': senha}, follow_redirects=True)
    if 'Segundo fator' not in r.text and 'autenticador' not in r.text:
        return r
    m = re.search(r'Chave para digitar: <code[^>]*>([A-Z2-7 ]+)</code>', r.text)
    if m:
        seg = m.group(1).replace(' ', '')
        r = c.post(f'{prefixo}/2fa', data={'csrf': tok(c, f'{prefixo}/2fa'), 'codigo': totp(seg)}, follow_redirects=True)
        SEGREDOS[email] = seg
        CODIGOS[email] = re.findall(r'<li>([0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4})</li>', r.text)
        cont = re.search(r'<a class="btn" href="([^"]+)">Já guardei', r.text)
        r = c.get(cont.group(1) if cont else f'{prefixo}/', follow_redirects=True)
    else:
        r = c.post(f'{prefixo}/2fa', data={'csrf': tok(c, f'{prefixo}/2fa'), 'codigo': totp(SEGREDOS[email])}, follow_redirects=True)
    if nova and f'action="{prefixo}/senha"' in r.text:
        r = c.post(f'{prefixo}/senha', data={'csrf': tok(c, f'{prefixo}/senha'), 'atual': senha, 'nova': nova, 'conf': nova}, follow_redirects=True)
    return r
