"""Coletor do PNCP (Portal Nacional de Contratações Públicas): editais e contratações do município.

Parâmetros (fonte='pncp'): ibge (código do município), cnpj (opcional: só publicações deste órgão), paginas_max.
Filtra por município porque o filtro por CNPJ do órgão não retorna resultados (FONTES-DADOS.md)."""
import re
from .comum import buscar, num, data_br, txt, chave, gravar

FONTE = 'pncp'
API = 'https://pncp.gov.br/api/search/'

def coletar(orgao, p, hoje=None):
    cnpj = re.sub(r'\D', '', p.get('cnpj', ''))
    L, pagina, total, erro = [], 1, None, None
    while pagina <= int(p.get('paginas_max', 60)):
        try:  # a API do PNCP derruba conexões com frequência: mais tentativas, e o que já chegou é aproveitado
            d = buscar(FONTE, API, {'tipos_documento': 'edital', 'municipios': p['ibge'], 'status': 'todos', 'ordenacao': '-data', 'pagina': pagina, 'tam_pagina': 50}, tentativas=6)
        except Exception as e:
            if pagina == 1:
                raise
            erro = f'parcial: parou na página {pagina} ({type(e).__name__})'
            break
        itens = d.get('items', []) if isinstance(d, dict) else []
        total = d.get('total') if isinstance(d, dict) else total
        for i in itens:
            if cnpj and re.sub(r'\D', '', str(i.get('orgao_cnpj', ''))) != cnpj:
                continue
            dt = data_br(i.get('data_publicacao_pncp'))
            L.append({'chave': chave('pncp', i.get('numero_controle_pncp') or i.get('id')), 'fonte': FONTE, 'ano': int(i.get('ano') or (dt.year if dt else 0)),
                      'numero': txt(i.get('numero_controle_pncp'), 60), 'modalidade': txt(i.get('modalidade_licitacao_nome'), 60),
                      'objeto': txt(i.get('description') or i.get('title'), 800), 'situacao': txt(i.get('situacao_nome'), 60), 'data': dt,
                      'valor': num(i.get('valor_global')), 'unidade': txt(i.get('unidade_nome'), 200),
                      'link': ('https://pncp.gov.br/app' + i['item_url']) if i.get('item_url') else ''})
        if not itens or len(itens) < 50:
            break
        pagina += 1
    n = gravar(orgao['banco'], 'licitacoes', L)
    return [('licitacoes_pncp', True, n, f'{n} publicações do órgão ({total} no município)' + (f' · {erro}' if erro else ''))]
