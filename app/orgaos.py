"""Cadastro dos órgãos visto pelo portal, pelo painel e pelo worker (separação gestão × portais, etapa A2).

Papel "tudo"/"gestao": tabela `orgaos` do banco de controle, como sempre foi.
Papel "no": os órgãos das licenças recebidas da gestão (assinatura conferida) — o nó não tem o banco de controle.
Só leitura: criar, mudar e apagar órgão é da gestão."""
from . import config, db

def todos(ativos=True, tipo=None):
    if config.PAPEL == 'no':
        from .web import _orgaos_do_no
        lista = sorted(_orgaos_do_no().values(), key=lambda o: o['id'])
    else:  # esta VPS só hospeda os órgãos sem nó; os de nó são servidos (banco, worker, Diário) pelo próprio nó
        lista = db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE no_id IS NULL ORDER BY id')
    return [o for o in lista if (not ativos or o.get('ativo', True)) and (tipo is None or o['tipo'] == tipo)]

def por_id(oid):
    return next((o for o in todos(ativos=False) if o['id'] == oid), None)

def por_slug(slug):
    return next((o for o in todos(ativos=False) if o['slug'] == slug), None)

def executivo_do(ibge):
    """A Prefeitura (ativa) do mesmo município: nesta instalação ou, desde 23/11/2026, em outra (diretório da gestão).
    O resultado traz 'local' (True = mesma instalação) para quem for chamar a API pública dela."""
    from . import integracao
    return next((o for o in sorted(integracao.conhecidos().values(), key=lambda x: x['id']) if o['tipo'] == 'executivo' and o['ibge'] == ibge and o['ativo']), None)
