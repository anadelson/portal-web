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
    """Data de referência. DATA_SIMULADA permite testar o período eleitoral."""
    s = env('DATA_SIMULADA')
    if s:
        return date.fromisoformat(s)
    return date.today()

def dsn(banco: str) -> str:
    return f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={banco}"
