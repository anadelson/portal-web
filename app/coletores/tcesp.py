"""Coletor do TCESP (Transparência Municipal / Audesp): receitas mensais por alínea.

Usado para 2025, porque a API da Prefeitura devolve 2025 zerado. Parâmetros (fonte='tcesp'): municipio (ex.: 'bora'), anos."""
from .comum import buscar, num, txt, chave, gravar

FONTE = 'tcesp'
API = 'https://transparencia.tce.sp.gov.br/api/json/'

def coletar(orgao, p, hoje=None):
    res = []
    for ano in p.get('anos', []):
        L = []
        for mes in range(1, 13):
            itens = buscar(FONTE, f"{API}receitas/{p['municipio']}/{ano}/{mes}")
            for i in (itens if isinstance(itens, list) else []):
                alinea = txt(i.get('ds_alinea'), 300)
                nome = alinea.split(' - ', 1)[-1] + (f" · {txt(i.get('ds_subalinea'), 200)}" if i.get('ds_subalinea') else '')
                L.append({'chave': chave('tce', ano, mes, i.get('ds_fonte_recurso'), i.get('ds_cd_aplicacao_fixo'), alinea, i.get('ds_subalinea')), 'fonte': FONTE,
                          'ano': ano, 'mes': mes, 'codigo': alinea.split(' - ', 1)[0][:40], 'nome': nome[:300], 'fonte_recurso': txt(i.get('ds_fonte_recurso'), 200),
                          'previsto': None, 'atualizado': None, 'arrecadado': num(i.get('vl_arrecadacao')) or 0, 'soma': True})
        n = gravar(orgao['banco'], 'receitas', L, {'ano': ano}, FONTE)
        res.append((f'receitas_{ano}', bool(L), n, f'{n} linhas de receita de {ano} (12 meses)'))
    return res
