"""Cadastro dos órgãos visto pelo portal, pelo painel e pelo worker (separação gestão × portais, etapa A2).

Papel "tudo"/"gestao": tabela `orgaos` do banco de controle, como sempre foi.
Papel "no": os órgãos das licenças recebidas da gestão (assinatura conferida) — o nó não tem o banco de controle.
Só leitura: criar, mudar e apagar órgão é da gestão."""
from . import config, db

def todos(ativos=True, tipo=None):
    if config.PAPEL == 'no':
        from .web import _orgaos_do_no
        lista = sorted(_orgaos_do_no().values(), key=lambda o: o['id'])
    else:
        lista = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos ORDER BY id')
    return [o for o in lista if (not ativos or o.get('ativo', True)) and (tipo is None or o['tipo'] == tipo)]

def por_id(oid):
    return next((o for o in todos(ativos=False) if o['id'] == oid), None)

def por_slug(slug):
    return next((o for o in todos(ativos=False) if o['slug'] == slug), None)

def executivo_do(ibge):
    """A Prefeitura (ativa) do mesmo município, se estiver neste nó."""
    return next((o for o in todos(tipo='executivo') if o['ibge'] == ibge), None)
