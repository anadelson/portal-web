"""Acesso aos painéis /admin e ao console: senha + segundo fator (TOTP) obrigatório, ou Login Único gov.br (nível prata/ouro);
bloqueio por tentativas, sessão com expiração por inatividade e registro em auditoria/log.
Contas: 'usuario' (tabela usuarios do banco do órgão) e 'gestor' (tabela gestores do banco de controle)."""
import base64, hashlib, json, secrets, time
from datetime import datetime, timedelta, timezone
import httpx
from psycopg.types.json import Jsonb
from . import config, db
from .security import (confere_senha, novo_segredo_totp, confere_totp, cifrar, decifrar, codigos_recuperacao, usar_recuperacao, cpf_hash, otpauth, qr_svg)

class Conta:
    def __init__(self, request, tipo):
        self.tipo = tipo
        self.banco = request.state.orgao['banco'] if tipo == 'usuario' else db.PLATAFORMA
        self.tabela = 'usuarios' if tipo == 'usuario' else 'gestores'
        self.pre = '/admin' if tipo == 'usuario' else ''
        self.chave = 'u' if tipo == 'usuario' else 'gestor'
        self.emissor = (request.state.orgao['nome'] if tipo == 'usuario' else 'Console dos Portais')

    def por_id(self, i):
        return db.um(self.banco, f'SELECT * FROM {self.tabela} WHERE id=%s', (i,))

    def por_email(self, email):
        return db.um(self.banco, f'SELECT * FROM {self.tabela} WHERE lower(email)=lower(%s)', (email or '',))

def _ip(request):
    return config.ip_cliente(request)

def _chave_origem(request, c: Conta):
    return hashlib.sha256(f"{c.tipo}|{getattr(request.state, 'orgao', {}) and request.state.orgao.get('slug')}|{_ip(request)}".encode()).hexdigest()

def origem_bloqueada(request, c: Conta) -> bool:
    """Mais de 3× o limite de falhas da mesma origem em LOGIN_BLOQUEIO_MIN minutos bloqueia a origem."""
    r = db.um(db.LOCAL if c.tipo == 'usuario' else db.PLATAFORMA, "SELECT count(*) n FROM login_tentativas WHERE chave=%s AND NOT ok AND quando > now() - make_interval(mins => %s)", (_chave_origem(request, c), config.LOGIN_BLOQUEIO_MIN))
    return r['n'] >= config.LOGIN_MAX_FALHAS * 3

def registrar_tentativa(request, c: Conta, conta, ok: bool):
    db.exe(db.LOCAL if c.tipo == 'usuario' else db.PLATAFORMA, 'INSERT INTO login_tentativas (chave, ok) VALUES (%s,%s)', (_chave_origem(request, c), ok))
    if not conta:
        return None
    if ok:
        db.exe(c.banco, f'UPDATE {c.tabela} SET falhas=0, bloqueado_ate=NULL WHERE id=%s', (conta['id'],))
        return None
    r = db.exe(c.banco, f'UPDATE {c.tabela} SET falhas=falhas+1 WHERE id=%s RETURNING falhas', (conta['id'],))
    if r and r['falhas'] >= config.LOGIN_MAX_FALHAS:
        ate = datetime.now(timezone.utc) + timedelta(minutes=config.LOGIN_BLOQUEIO_MIN)
        db.exe(c.banco, f'UPDATE {c.tabela} SET falhas=0, bloqueado_ate=%s WHERE id=%s', (ate, conta['id']))
        return ate
    return None

def bloqueada(conta):
    return conta and conta.get('bloqueado_ate') and conta['bloqueado_ate'] > datetime.now(timezone.utc)

def msg_bloqueio(ate):
    return f"Acesso bloqueado temporariamente por excesso de tentativas. Tente de novo depois das {ate.astimezone().strftime('%H:%M')}."

def verificar_senha(request, c: Conta, email, senha):
    """Primeira etapa. Devolve (conta, mensagem_de_erro). Mensagem genérica para não revelar se o e-mail existe."""
    if origem_bloqueada(request, c):
        return None, 'Muitas tentativas a partir desta conexão. Aguarde alguns minutos.'
    conta = c.por_email(email)
    if bloqueada(conta):
        return None, msg_bloqueio(conta['bloqueado_ate'])
    ativa = conta and (conta.get('situacao', 'ativo') == 'ativo' if c.tipo == 'usuario' else conta.get('ativo'))
    valida = conta and ativa and confere_senha(senha or '', conta['senha_hash']) and not (c.tipo == 'usuario' and conta.get('validade') and conta['validade'] < config.hoje())
    if not valida:
        ate = registrar_tentativa(request, c, conta, False)
        return None, (msg_bloqueio(ate) if ate else 'E-mail ou senha incorretos, ou acesso suspenso.')
    return conta, None

def iniciar_segundo_fator(request, c: Conta, conta):
    request.session.pop(c.chave, None)
    request.session['pre'] = {'tipo': c.tipo, 'id': conta['id'], 'quando': time.time(), 'orgao': request.state.orgao['slug'] if c.tipo == 'usuario' else None}

def pre_conta(request, c: Conta):
    p = request.session.get('pre')
    if not p or p.get('tipo') != c.tipo or time.time() - p.get('quando', 0) > 600:
        return None
    if c.tipo == 'usuario' and p.get('orgao') != request.state.orgao['slug']:
        return None
    return c.por_id(p['id'])

def preparar_cadastro(request, c: Conta, conta):
    """Gera um segredo novo (guardado cifrado só na sessão até a confirmação) e devolve dados para a tela."""
    s = request.session.get('totp_novo')
    seg = decifrar(s) if s else novo_segredo_totp()
    request.session['totp_novo'] = cifrar(seg)
    uri = otpauth(seg, conta['email'], c.emissor)
    return {'segredo': ' '.join(seg[i:i + 4] for i in range(0, len(seg), 4)), 'qr': qr_svg(uri)}

def confirmar_cadastro(request, c: Conta, conta, codigo):
    seg = decifrar(request.session.get('totp_novo', ''))
    if not seg or not confere_totp(seg, codigo):
        return None
    cods, hashes = codigos_recuperacao()
    db.exe(c.banco, f'UPDATE {c.tabela} SET totp_segredo=%s, totp_ativo=TRUE, recuperacao=%s WHERE id=%s', (cifrar(seg), Jsonb(hashes), conta['id']))
    request.session.pop('totp_novo', None)
    return cods

def conferir_segundo_fator(request, c: Conta, conta, codigo, recuperacao=''):
    if recuperacao:
        resto = usar_recuperacao(recuperacao, conta['recuperacao'] or [])
        if resto is None:
            return False, 'Código de recuperação inválido.'
        db.exe(c.banco, f'UPDATE {c.tabela} SET recuperacao=%s WHERE id=%s', (Jsonb(resto), conta['id']))
        return True, f'Código de recuperação usado. Restam {len(resto)}.' + (' Gere novos códigos refazendo o cadastro do autenticador.' if len(resto) < 3 else '')
    if confere_totp(decifrar(conta['totp_segredo']), codigo):
        return True, ''
    return False, 'Código do autenticador incorreto.'

def concluir_login(request, c: Conta, conta, metodo):
    request.session.pop('pre', None)
    registrar_tentativa(request, c, conta, True)
    if c.tipo == 'usuario':
        request.session['u'] = {'id': conta['id'], 'nome': conta['nome'], 'perfil': conta['perfil'], 'orgao': request.state.orgao['slug'], 'trocar': conta['trocar_senha'] and metodo != 'gov.br'}
        db.exe(c.banco, 'UPDATE usuarios SET ultimo_acesso=now() WHERE id=%s', (conta['id'],))
    else:
        request.session['gestor'] = {'id': conta['id'], 'nome': conta['nome'], 'trocar': conta['trocar_senha'] and metodo != 'gov.br'}
    request.session['ultimo'] = time.time()

def sessao_expirada(request) -> bool:
    """Expiração por inatividade (SESSAO_INATIVIDADE_MIN). Renova o relógio a cada requisição válida."""
    u = request.session.get('ultimo')
    if u and time.time() - u > config.SESSAO_INATIVIDADE_MIN * 60:
        for k in ('u', 'gestor', 'pre', 'ultimo'):
            request.session.pop(k, None)
        return True
    request.session['ultimo'] = time.time()
    return False

# ---------- Login Único gov.br (OpenID Connect, código + PKCE) ----------
NIVEIS = {'1': 'bronze', '2': 'prata', '3': 'ouro'}

def govbr_ativo():
    return bool(config.GOVBR_CLIENT_ID and config.GOVBR_CLIENT_SECRET and config.CPF_HMAC_CHAVE)

def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip('=')

def govbr_redirecionar(request, c: Conta):
    """Monta a URL de autorização (state, nonce e PKCE na sessão)."""
    from urllib.parse import urlencode
    verif = secrets.token_urlsafe(48)
    st, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    request.session['govbr'] = {'state': st, 'nonce': nonce, 'verif': verif, 'tipo': c.tipo, 'quando': time.time()}
    q = {'response_type': 'code', 'client_id': config.GOVBR_CLIENT_ID, 'scope': 'openid email profile govbr_confiabilidades',
         'redirect_uri': retorno(request, c), 'nonce': nonce, 'state': st, 'code_challenge': _b64(hashlib.sha256(verif.encode()).digest()), 'code_challenge_method': 'S256'}
    return config.govbr_urls()['authorize'] + '?' + urlencode(q)

def retorno(request, c: Conta):
    host = request.headers.get('host', '').split(':')[0]
    return f"https://{host}{c.pre}/govbr/retorno"

def _verificar_jwt(token, nonce, http):
    """Valida o id_token (RS256) com a chave pública do gov.br (JWKS), emissor, audiência, validade e nonce."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    cab, corpo, ass = token.split('.')
    dec = lambda s: base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
    h, p = json.loads(dec(cab)), json.loads(dec(corpo))
    if h.get('alg') != 'RS256':
        raise ValueError('algoritmo do token não aceito')
    jwks = http.get(config.govbr_urls()['jwks']).json()
    k = next((k for k in jwks.get('keys', []) if k.get('kid') == h.get('kid')), None)
    if not k:
        raise ValueError('chave do token não encontrada no gov.br')
    pub = rsa.RSAPublicNumbers(int.from_bytes(dec(k['e']), 'big'), int.from_bytes(dec(k['n']), 'big')).public_key()
    pub.verify(dec(ass), f'{cab}.{corpo}'.encode(), padding.PKCS1v15(), hashes.SHA256())
    aud = p.get('aud')
    if (aud != config.GOVBR_CLIENT_ID and config.GOVBR_CLIENT_ID not in (aud or [])) or p.get('nonce') != nonce or p.get('exp', 0) < time.time() or not str(p.get('iss', '')).rstrip('/').startswith(config.govbr_urls()['issuer'].rstrip('/')):
        raise ValueError('token do gov.br inválido (emissor, audiência, validade ou nonce)')
    return p

def govbr_concluir(request, c: Conta, code, state, http=None):
    """Troca o código pelo token, valida, confere o nível (prata/ouro) e acha a conta pelo hash do CPF. Devolve (conta, erro)."""
    g = request.session.pop('govbr', None)
    if not g or g.get('tipo') != c.tipo or not state or state != g.get('state') or time.time() - g.get('quando', 0) > 600:
        return None, 'Sessão de login gov.br expirada ou inválida. Tente de novo.'
    http = http or httpx.Client(timeout=20)
    try:
        t = http.post(config.govbr_urls()['token'], data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': retorno(request, c), 'code_verifier': g['verif']},
                      auth=(config.GOVBR_CLIENT_ID, config.GOVBR_CLIENT_SECRET)).json()
        p = _verificar_jwt(t['id_token'], g['nonce'], http)
        cpf = ''.join(ch for ch in str(p.get('sub', '')) if ch.isdigit())
        niveis = http.get(config.govbr_urls()['niveis'].format(cpf=cpf), headers={'Authorization': f"Bearer {t['access_token']}"}).json()
        nomes = {NIVEIS.get(str(n.get('id')), '') for n in (niveis if isinstance(niveis, list) else [])}
        exigido = {'prata', 'ouro'} if config.GOVBR_NIVEL_MINIMO == 'prata' else {'ouro'}
        if not nomes & exigido:
            return None, f'Sua conta gov.br precisa ser nível {config.GOVBR_NIVEL_MINIMO} ou superior para acessar o painel.'
        h = cpf_hash(cpf)
    except Exception as e:
        return None, f'Não foi possível concluir o login gov.br ({type(e).__name__}).'
    conta = db.um(c.banco, f'SELECT * FROM {c.tabela} WHERE cpf_hash=%s', (h,))
    ativa = conta and (conta.get('situacao', 'ativo') == 'ativo' if c.tipo == 'usuario' else conta.get('ativo'))
    if not ativa:
        return None, 'Conta gov.br sem acesso a este painel. Peça ao administrador para vincular seu CPF ao seu usuário.'
    return conta, None
