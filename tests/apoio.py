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


# ---------- convite de primeiro acesso (e-mail SIMULADO: nada sai da máquina) ----------
CAIXA = []  # mensagens que teriam sido enviadas

def ligar_email_teste(dominio_no_ar=True):
    """Configura um e-mail de saída fictício, guarda as mensagens em CAIXA e considera os domínios no ar."""
    from app import db, email_saida as EM, convites
    EM._smtp_enviar = lambda cfg, senha, msg: CAIXA.append(msg)
    convites.dominio_no_ar = (lambda d: True) if dominio_no_ar else (lambda d: False)
    db.exe(db.PLATAFORMA, """INSERT INTO email_saida (id, servidor, porta, seguranca, remetente, remetente_nome) VALUES (1,'smtp.exemplo.test',465,'ssl','nao-responda@exemplo.test','Teste')
                             ON CONFLICT (id) DO NOTHING""")

def link_convite(email):
    """Link de primeiro acesso do último convite enviado para o e-mail (lido da mensagem simulada)."""
    for m in reversed(CAIXA):
        if m['To'] == email:
            corpo = m.get_body(preferencelist=('plain',)).get_content()
            r = re.search(r'https://[^\s]+/admin/primeiro-acesso\?t=[A-Za-z0-9_\-]+', corpo)
            return r.group(0) if r else None
    return None

def primeiro_acesso(c, email, nova, prefixo='/admin'):
    """Abre o link do convite, cria a senha e cadastra o segundo fator. Devolve a última resposta (painel)."""
    url = link_convite(email)
    if not url:
        return None
    caminho = url.split('/admin/', 1)[1]
    t = caminho.split('t=', 1)[1]
    c.get('/admin/' + caminho)
    r = c.post(f'{prefixo}/primeiro-acesso', data={'csrf': tok(c, '/admin/' + caminho), 't': t, 'nova': nova, 'conf': nova}, follow_redirects=True)
    m = re.search(r'Chave para digitar: <code[^>]*>([A-Z2-7 ]+)</code>', r.text)
    if not m:
        return r
    seg = m.group(1).replace(' ', '')
    r = c.post(f'{prefixo}/2fa', data={'csrf': tok(c, f'{prefixo}/2fa'), 'codigo': totp(seg)}, follow_redirects=True)
    SEGREDOS[email] = seg
    CODIGOS[email] = re.findall(r'<li>([0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4})</li>', r.text)
    cont = re.search(r'<a class="btn" href="([^"]+)">Já guardei', r.text)
    return c.get(cont.group(1) if cont else f'{prefixo}/', follow_redirects=True)
