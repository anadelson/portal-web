import os
from datetime import date

def env(k, padrao=''):
    return os.environ.get(k, padrao).strip()

DOMINIO_GESTAO = env('DOMINIO_GESTAO', 'gestao.localhost')
PG_USER = env('PG_USER', 'portal')
PG_PASSWORD = env('PG_PASSWORD', '')
PG_HOST = env('PG_HOST', 'localhost')
PG_PORT = env('PG_PORT', '5432')
SECRET_KEY = env('SECRET_KEY', 'dev-inseguro-troque')
SENHA_INICIAL_GESTOR = env('SENHA_INICIAL_GESTOR', 'troque-agora')
SENHA_INICIAL_ADMIN = env('SENHA_INICIAL_ADMIN', 'troque-agora')
DADOS_DIR = env('DADOS_DIR', '/srv/dados')
COOKIE_SEGURO = env('COOKIE_SEGURO', '1') not in ('0', 'false', 'nao')
# Nome da plataforma (console e título) e identificação dos coletores nas fontes de dados; configuráveis no .env
NOME_PLATAFORMA = env('NOME_PLATAFORMA', 'Portais Municipais')
USER_AGENT = env('USER_AGENT', 'PortaisMunicipais-coletor/1.0')
# Separação gestão × portais (etapa A): papel desta instalação.
#   tudo   = gestão e portais na mesma VPS (padrão; igual a antes)
#   gestao = só o console e o emissor de licenças
#   no     = só portais/painéis/worker; busca as licenças na gestão (GESTAO_URL) com o token do nó (NO_TOKEN)
PAPEL = env('PAPEL', 'tudo') if env('PAPEL', 'tudo') in ('tudo', 'gestao', 'no') else 'tudo'
GESTAO_URL = env('GESTAO_URL')                      # ex.: https://gestao.conectatech.tech (só no papel "no")
NO_TOKEN = env('NO_TOKEN')                          # segredo do nó (só no papel "no"); nunca vai para tela ou log
LICENCA_CHAVE_PUBLICA = env('LICENCA_CHAVE_PUBLICA')  # chave pública da gestão (base64), conferida em cada licença no papel "no"
LICENCA_VALIDADE_DIAS = int(env('LICENCA_VALIDADE_DIAS', '15') or 15)  # sem contato com a gestão por mais que isso: carência

def hoje() -> date:
    """Data de referência. DATA_SIMULADA (AAAA-MM-DD ou AAAA-MM-DDTHH:MM) permite testar período eleitoral, Diário etc."""
    s = env('DATA_SIMULADA')
    if s:
        return date.fromisoformat(s[:10])
    return date.today()

def agora():
    """Data e hora de referência (com DATA_SIMULADA, a data e a hora simuladas; sem hora, a hora real)."""
    from datetime import datetime
    s = env('DATA_SIMULADA')
    if s and len(s) > 10:
        return datetime.fromisoformat(s)
    if s:
        return datetime.combine(hoje(), datetime.now().time())
    return datetime.now()

def dsn(banco: str) -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={banco}"

# ---------- Fase 6: Diário com assinatura, gov.br e segurança ----------
SEGREDOS_DIR = env('SEGREDOS_DIR', '/srv/segredos')          # montado só leitura no container
DIARIO_MODO = env('DIARIO_MODO', 'teste').lower()             # 'teste' (padrão) ou 'oficial' (exige certificado e ACT reais)
DIARIO_CORTE_HORA = int(env('DIARIO_CORTE_HORA', '16'))       # envio até 16h (decreto)
DIARIO_PUBLICACAO_HORA = int(env('DIARIO_PUBLICACAO_HORA', '17'))
DIARIO_ALERTA = env('DIARIO_ALERTA', '16:30')
DIARIO_AUTOMATICO_TESTE = env('DIARIO_AUTOMATICO_TESTE', '0') == '1'   # em modo teste, a rotina automática (sem atos/publicação) só roda se ligada
ACT_URL = env('ACT_URL')                                      # URL RFC 3161 da Autoridade de Carimbo do Tempo
ACT_USUARIO = env('ACT_USUARIO')
ACT_SENHA = env('ACT_SENHA')
ACT_CERT = env('ACT_CERT')                                    # opcional: certificado de cliente (.p12) em segredos/act
ACT_CERT_SENHA = env('ACT_CERT_SENHA')
ICP_RAIZES = env('ICP_RAIZES', 'icp')                         # pasta em segredos com as AC Raiz ICP-Brasil (.crt/.cer)
GOVBR_CLIENT_ID = env('GOVBR_CLIENT_ID')
GOVBR_CLIENT_SECRET = env('GOVBR_CLIENT_SECRET')
GOVBR_AMBIENTE = env('GOVBR_AMBIENTE', 'staging')             # staging (homologação) ou producao
GOVBR_NIVEL_MINIMO = env('GOVBR_NIVEL_MINIMO', 'prata')       # prata ou ouro
CPF_HMAC_CHAVE = env('CPF_HMAC_CHAVE')                        # chave do HMAC do CPF (obrigatória para usar gov.br)
TOTP_CHAVE = env('TOTP_CHAVE')                                # chave Fernet que cifra os segredos TOTP (se vazia, derivada da SECRET_KEY)
SESSAO_INATIVIDADE_MIN = int(env('SESSAO_INATIVIDADE_MIN', '30'))
LOGIN_MAX_FALHAS = int(env('LOGIN_MAX_FALHAS', '5'))
LOGIN_BLOQUEIO_MIN = int(env('LOGIN_BLOQUEIO_MIN', '15'))
INTERNO_BASE = env('INTERNO_BASE', 'http://127.0.0.1:8000')   # endereço interno da API entre órgãos

# ---------- Fase 7 (fontes): IEG-M do TCESP e planilhas do INEP ----------
# Acesso anônimo publicado pelo próprio TCESP (uso autorizado pelo órgão em 07/11/2026; ver Docs/PROGRESSO.md).
# Reserva: a credencial principal é cadastrada no console do gestor (Credenciais de fontes). Vazio = sem reserva.
IEGM_USUARIO = env('IEGM_USUARIO')
IEGM_SENHA = env('IEGM_SENHA')
# Chave Fernet que cifra as credenciais de fontes cadastradas no console (gerada na VPS, só no .env).
# Perder a chave obriga a recadastrar as credenciais pela tela.
CHAVE_CREDENCIAIS = env('CHAVE_CREDENCIAIS')
CERTS_DIR = env('CERTS_DIR', '/srv/deploy/certs')                # certificados intermediários públicos (só completam a cadeia TLS)

def govbr_urls():
    sso = 'https://sso.acesso.gov.br' if GOVBR_AMBIENTE == 'producao' else 'https://sso.staging.acesso.gov.br'
    api = 'https://api.acesso.gov.br' if GOVBR_AMBIENTE == 'producao' else 'https://api.staging.acesso.gov.br'
    return {'authorize': sso + '/authorize', 'token': sso + '/token', 'jwks': sso + '/jwk', 'logout': sso + '/logout', 'niveis': api + '/confiabilidades/v3/contas/{cpf}/niveis', 'issuer': sso + '/'}

def ip_cliente(request):
    """IP de quem acessou. O proxy da frente (nginx ou Traefik) grava em X-Real-IP o endereço de quem conectou nele e
    descarta o que o visitante mandar nesse cabeçalho. Sem ele, vale o ÚLTIMO endereço do X-Forwarded-For (o que o
    proxy acrescentou; os anteriores podem ter sido inventados pelo visitante) e, por fim, o endereço da conexão."""
    ip = (request.headers.get('x-real-ip') or '').strip()
    if not ip:
        ip = (request.headers.get('x-forwarded-for') or '').split(',')[-1].strip()
    return ip or (request.client.host if request.client else '')
