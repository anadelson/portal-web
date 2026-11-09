"""Acesso ao PostgreSQL: um banco de controle (plataforma) e um banco por órgão."""
import contextvars, re
from contextlib import contextmanager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from . import config

_pools: dict[str, ConnectionPool] = {}

def pool(banco: str) -> ConnectionPool:
    p = _pools.get(banco)
    if p is None:
        p = ConnectionPool(config.dsn(banco), min_size=1, max_size=5, kwargs={'row_factory': dict_row, 'autocommit': True}, open=True)
        _pools[banco] = p
    return p

# Modo ENSAIO ("Testar consulta"): o coletor roda de verdade, mas nada é gravado.
# Escritas por exe/um/todos são puladas e anotadas; qualquer outra conexão abre em modo somente leitura (rede de segurança).
ENSAIO = contextvars.ContextVar('ensaio', default=None)
_ESCRITA = re.compile(r'^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|TRUNCATE|MERGE)\b', re.I)

def _pular(sql):
    e = ENSAIO.get()
    if e is not None and _ESCRITA.match(sql or ''):
        m = re.match(r'^\s*(\w+)\s+(?:INTO\s+|FROM\s+)?(\w+)', sql, re.I)
        e.setdefault('escritas_evitadas', []).append(f'{m.group(1).upper()} {m.group(2)}' if m else 'escrita')
        return True
    return False

@contextmanager
def conn(banco: str):
    with pool(banco).connection() as c:
        if ENSAIO.get() is None:
            yield c
            return
        c.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY')
        try:
            yield c
        finally:
            try:
                c.execute('SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE')
            except Exception:
                pass

def todos(banco, sql, params=()):
    if _pular(sql):
        return []
    with conn(banco) as c:
        return c.execute(sql, params).fetchall()

def um(banco, sql, params=()):
    if _pular(sql):
        return None
    with conn(banco) as c:
        return c.execute(sql, params).fetchone()

def exe(banco, sql, params=()):
    if _pular(sql):
        return None
    with conn(banco) as c:
        cur = c.execute(sql, params)
        try:
            return cur.fetchone()
        except Exception:
            return None

PLATAFORMA = 'plataforma'

def cfg(banco, chave, padrao=None):
    r = um(banco, 'SELECT valor FROM config WHERE chave=%s', (chave,))
    return r['valor'] if r else padrao

def set_cfg(banco, chave, valor):
    from psycopg.types.json import Jsonb
    exe(banco, 'INSERT INTO config (chave, valor) VALUES (%s,%s) ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor', (chave, Jsonb(valor)))

def fechar():
    for p in _pools.values():
        p.close()
    _pools.clear()
