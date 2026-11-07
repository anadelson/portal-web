from datetime import date
from . import config, db
from .catalogo import VEDADAS

PADRAO = {'nome': 'Eleições municipais 2028', 'inicio': '2028-07-01', 'fim': '2028-10-01', 'plano': 'rascunho',
          'trocar_logo': True, 'ocultar_redes': True, 'aviso': True, 'bloquear': True, 'restaurar': True}

def conf(banco):
    c = dict(PADRAO)
    c.update(db.cfg(banco, 'eleicao', {}) or {})
    return c

def em_defeso(banco, d: date | None = None) -> bool:
    c = conf(banco)
    d = d or config.hoje()
    return date.fromisoformat(c['inicio']) <= d <= date.fromisoformat(c['fim'])

def suspenso(item: dict, banco) -> bool:
    return item['classe'] in VEDADAS and not item.get('excecao_eleitoral') and em_defeso(banco)
