import os
from datetime import date

def env(k, padrao=''):
    return os.environ.get(k, padrao).strip()

DOMINIO_GESTAO = env('DOMINIO_GESTAO', 'gestao.localhost')
DOMINIO_PM = env('DOMINIO_PM', 'pmbora.localhost')
DOMINIO_CM = env('DOMINIO_CM', 'cmbora.localhost')
PG_USER = env('PG_USER', 'portal')
PG_PASSWORD = env('PG_PASSWORD', '')
PG_HOST = env('PG_HOST', 'localhost')
PG_PORT = env('PG_PORT', '5432')
SECRET_KEY = env('SECRET_KEY', 'dev-inseguro-troque')
SENHA_INICIAL_GESTOR = env('SENHA_INICIAL_GESTOR', 'troque-agora')
SENHA_INICIAL_ADMIN = env('SENHA_INICIAL_ADMIN', 'troque-agora')
DADOS_DIR = env('DADOS_DIR', '/srv/dados')
COOKIE_SEGURO = env('COOKIE_SEGURO', '1') not in ('0', 'false', 'nao')
IBGE_BORA = '3507209'

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
# Preenchido só no .env da VPS; vazio = coleta automática do IEG-M desligada, sem erro.
IEGM_USUARIO = env('IEGM_USUARIO')
IEGM_SENHA = env('IEGM_SENHA')
CERTS_DIR = env('CERTS_DIR', '/srv/deploy/certs')                # certificados intermediários públicos (só completam a cadeia TLS)

def govbr_urls():
    sso = 'https://sso.acesso.gov.br' if GOVBR_AMBIENTE == 'producao' else 'https://sso.staging.acesso.gov.br'
    api = 'https://api.acesso.gov.br' if GOVBR_AMBIENTE == 'producao' else 'https://api.staging.acesso.gov.br'
    return {'authorize': sso + '/authorize', 'token': sso + '/token', 'jwks': sso + '/jwk', 'logout': sso + '/logout', 'niveis': api + '/confiabilidades/v3/contas/{cpf}/niveis', 'issuer': sso + '/'}
