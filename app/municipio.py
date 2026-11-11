"""Fase 9 — "Dados do município": o que o IBGE publica entra sozinho (código IBGE do órgão, verificação semanal pela fonte "ibge");
o que o IBGE não fornece (ex.: distância da capital, IDHM por município) é digitado no painel e marcado como manual."""
from . import db

AUTO = [('mun_populacao', 'Habitantes (estimativa)', '{:,.0f}', ''), ('mun_area', 'Área territorial', '{:,.1f}', 'km²'),
        ('mun_pib_per_capita', 'PIB per capita', 'R$ {:,.2f}', ''), ('mun_salario_medio', 'Salário médio mensal', '{:,.1f}', 'salários mínimos')]
MANUAIS = [('distancia_capital', 'Distância da capital'), ('idhm', 'IDHM'), ('fundacao', 'Fundação / emancipação'), ('gentilico', 'Gentílico')]

def _br(fmt, v):
    return fmt.format(float(v)).replace(',', 'X').replace('.', ',').replace('X', '.')

def automaticos(ibge):
    out = []
    for chave, rot, fmt, un in AUTO:
        r = db.um(db.LOCAL, 'SELECT * FROM indicadores_publicos WHERE ibge=%s AND indicador=%s AND valor IS NOT NULL ORDER BY data_ref DESC, periodo DESC LIMIT 1', (str(ibge), chave))
        if r:
            out.append({'chave': chave, 'rotulo': rot, 'valor': _br(fmt, r['valor']) + (f' {un}' if un else ''), 'periodo': r['periodo'],
                        'coletado_em': r['coletado_em'], 'fonte': 'IBGE (servicodados.ibge.gov.br)', 'manual': False})
    return out

def manuais(banco):
    m = db.cfg(banco, 'municipio_manual', {}) or {}
    return [{'chave': k, 'rotulo': rot, 'valor': m.get(k, ''), 'manual': True} for k, rot in MANUAIS]

def numeros(o, banco):
    """Lista para o bloco "Conheça a cidade": automáticos primeiro, depois os manuais preenchidos."""
    return automaticos(o['ibge']) + [x for x in manuais(banco) if x['valor']]

def migrar(banco, ident):
    """Fase 9: os números digitados no bloco "Conheça" que o IBGE não fornece passam para os campos manuais (só se ainda vazios)."""
    m = db.cfg(banco, 'municipio_manual', None)
    if m is not None:
        return 0
    m, n = {}, 0
    for rot, val in ((ident or {}).get('conheca') or {}).get('numeros', []) or []:
        r = rot.lower()
        k = 'distancia_capital' if 'dist' in r else 'idhm' if 'idh' in r else None
        if k and val:
            m[k] = str(val)[:60]; n += 1
    db.set_cfg(banco, 'municipio_manual', m)
    return n
