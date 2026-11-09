"""Credenciais de fontes de dados cadastradas no console do gestor (ex.: acesso anônimo do IEG-M publicado pelo TCESP).

- Gravadas CIFRADAS (Fernet) no banco de controle com a chave CHAVE_CREDENCIAIS do .env; perder a chave obriga a
  recadastrar. Sem a chave, o cadastro fica desligado.
- Só gravação: nenhuma função pública devolve os valores para tela, log ou mensagem. `obter()` é usada apenas pelos
  coletores, dentro do processo.
- Mensagens de erro e de teste levam só o tipo do erro, o código HTTP e se veio JSON válido."""
import json
from . import config, db

FONTES = {
    'iegm': {'nome': 'IEG-M do TCESP (painel público, Pentaho CDA)',
             'explica': 'Acesso anônimo publicado pelo próprio TCESP no redirecionamento de iegm.tce.sp.gov.br (uso autorizado pelo órgão em 07/11/2026). '
                        'Consulta sem documentação oficial: pode mudar sem aviso.'},
    'youtube': {'nome': 'YouTube Data API v3 (transmissões)', 'so_chave': True,
                'explica': 'Chave de API do Google Cloud com a YouTube Data API v3 ativada, usada para detectar a transmissão ao vivo e listar as gravações '
                           'do canal oficial de cada órgão (o canal é informado no painel do órgão, em Transmissões). Restrinja a chave à YouTube Data API.'},
}

class SemChave(Exception):
    """CHAVE_CREDENCIAIS ausente ou inválida no .env."""

def _fernet():
    from cryptography.fernet import Fernet
    if not config.CHAVE_CREDENCIAIS:
        raise SemChave('CHAVE_CREDENCIAIS não configurada no .env')
    try:
        return Fernet(config.CHAVE_CREDENCIAIS.encode())
    except Exception:
        raise SemChave('CHAVE_CREDENCIAIS inválida no .env') from None

def chave_ok():
    try:
        _fernet()
        return True
    except SemChave:
        return False

def cifrar(usuario, senha):
    return _fernet().encrypt(json.dumps({'usuario': usuario, 'senha': senha}).encode()).decode()

def decifrar(token):
    """(usuario, senha) ou None se não decifrar (chave trocada/perdida). Nunca levanta exceção com o conteúdo."""
    from cryptography.fernet import InvalidToken
    try:
        d = json.loads(_fernet().decrypt(token.encode()).decode())
        return d['usuario'], d['senha']
    except (InvalidToken, SemChave, ValueError, KeyError):
        return None

def situacao(fonte):
    """Só metadados: quando, por quem e o último teste. Nunca os valores."""
    r = db.um(db.PLATAFORMA, 'SELECT fonte, configurada_em, configurada_por, testada_em, testada_por, teste_resultado, dados FROM credenciais_fontes WHERE fonte=%s', (fonte,))
    if not r:
        return None
    legivel = decifrar(r['dados']) is not None
    return {k: r[k] for k in ('fonte', 'configurada_em', 'configurada_por', 'testada_em', 'testada_por', 'teste_resultado')} | {'legivel': legivel}

def salvar(fonte, usuario, senha, quem):
    if fonte not in FONTES:
        raise ValueError('fonte sem credencial prevista')
    if FONTES[fonte].get('so_chave'):
        usuario = 'chave'
    if not usuario or not senha:
        raise ValueError('preencha usuário e senha' if not FONTES[fonte].get('so_chave') else 'preencha a chave')
    token = cifrar(usuario, senha)
    existia = bool(db.um(db.PLATAFORMA, 'SELECT 1 FROM credenciais_fontes WHERE fonte=%s', (fonte,)))
    db.exe(db.PLATAFORMA, """INSERT INTO credenciais_fontes (fonte, dados, configurada_em, configurada_por) VALUES (%s,%s,now(),%s)
                             ON CONFLICT (fonte) DO UPDATE SET dados=EXCLUDED.dados, configurada_em=now(), configurada_por=EXCLUDED.configurada_por,
                             testada_em=NULL, testada_por='', teste_resultado=''""", (fonte, token, quem))
    return 'trocada' if existia else 'cadastrada'

def apagar(fonte):
    return bool(db.exe(db.PLATAFORMA, 'DELETE FROM credenciais_fontes WHERE fonte=%s RETURNING 1', (fonte,)))

def obter(fonte):
    """Uso interno dos coletores: (usuario, senha) da plataforma ou None."""
    r = db.um(db.PLATAFORMA, 'SELECT dados FROM credenciais_fontes WHERE fonte=%s', (fonte,))
    return decifrar(r['dados']) if r else None

def _http_teste(fonte, auth):
    """Chamada mínima à fonte. Devolve (código HTTP, corpo é JSON válido?). Substituível nos testes."""
    import httpx
    if fonte == 'iegm':
        from .coletores.inep_iegm import IEGM_URL, IEGM_CONSULTA
        with httpx.Client(timeout=60, auth=auth, headers={'User-Agent': 'PortaisBora-coletor/1.0', 'Accept': 'application/json'}) as c:
            r = c.get(IEGM_URL, params={**IEGM_CONSULTA, 'parampExercicio_mapa': config.hoje().year - 1})
        try:
            d = r.json()
            valido = isinstance(d, dict) and 'resultset' in d
        except ValueError:
            valido = False
        return r.status_code, valido
    if fonte == 'youtube':  # consulta mínima (lista de regiões): só confere se a chave é aceita pela API
        from .coletores.youtube import _get
        try:
            d = _get('i18nRegions', {'part': 'snippet', 'hl': 'pt_BR'}, auth[1])
            return 200, isinstance(d, dict) and 'items' in d
        except RuntimeError as e:
            st = str(e)
            return (int(st[5:]) if st.startswith('HTTP ') else 0), False
    raise ValueError('fonte sem teste previsto')

def testar(fonte, quem):
    """Testa a conexão com a credencial cadastrada. Resultado só com código HTTP e validade do JSON."""
    cred = obter(fonte)
    if not cred:
        res = 'sem credencial legível cadastrada'
    else:
        try:
            st, valido = _http_teste(fonte, cred)
            res = f"HTTP {st} · {'JSON válido' if valido else 'resposta não é o JSON esperado'}"
        except Exception as e:  # só o tipo do erro: a mensagem poderia conter dados da requisição
            res = f'falha de conexão ({type(e).__name__})'
    db.exe(db.PLATAFORMA, 'UPDATE credenciais_fontes SET testada_em=now(), testada_por=%s, teste_resultado=%s WHERE fonte=%s', (quem, res, fonte))
    return res
