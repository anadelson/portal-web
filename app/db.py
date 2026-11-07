"""Acesso ao PostgreSQL: um banco de controle (plataforma) e um banco por órgão."""
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

@contextmanager
def conn(banco: str):
    with pool(banco).connection() as c:
        yield c

def todos(banco, sql, params=()):
    with conn(banco) as c:
        return c.execute(sql, params).fetchall()

def um(banco, sql, params=()):
    with conn(banco) as c:
        return c.execute(sql, params).fetchone()

def exe(banco, sql, params=()):
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
