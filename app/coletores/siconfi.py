"""Coletor do Siconfi (Tesouro Nacional): RREO Anexo 14 (saúde e educação), RGF Anexo 01 (pessoal) e extrato de entregas.

Parâmetros (fonte='siconfi'): ibge, rreo (bool: coleta RREO Anexo 14), rgf_poder ('E' Executivo, 'L' Legislativo)."""
from .. import config, db
from .comum import buscar, num, txt, chave, gravar, guardar_publico

FONTE = 'siconfi'
API = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/'

def _itens(caminho, params):
    d = buscar(FONTE, API + caminho, params)
    return d.get('items', []) if isinstance(d, dict) else []

def _linhas(itens, dem, anexo, ano, per, poder=''):
    return [{'chave': chave('sic', dem, anexo, ano, per, poder, i.get('instituicao'), i.get('rotulo'), i.get('cod_conta'), i.get('conta'), i.get('coluna')),
             'fonte': FONTE, 'ano': ano, 'demonstrativo': dem, 'anexo': anexo, 'periodo': per, 'periodicidade': txt(i.get('periodicidade'), 4),
             'poder': poder, 'instituicao': txt(i.get('instituicao'), 200), 'rotulo': txt(i.get('rotulo'), 200), 'conta': txt(i.get('conta'), 400),
             'coluna': txt(i.get('coluna'), 200), 'valor': num(i.get('valor'))} for i in itens]

def ultimo(fn, ano):
    """Procura o período mais recente com dados: ano corrente do fim para o começo, depois o ano anterior."""
    for a, pers in ((ano, range(6, 0, -1)), (ano - 1, range(6, 0, -1))):
        for per in pers:
            itens = fn(a, per)
            if itens:
                return a, per, itens
    return None, None, []

def coletar(orgao, p, hoje=None):
    hoje = hoje or config.hoje()
    b, res = orgao['banco'], []
    ent = _itens('extrato_entregas', {'id_ente': p['ibge'], 'an_referencia': hoje.year})
    guardar_publico(p['ibge'], 'siconfi_entregas', hoje.year, ent)
    res.append(('siconfi_entregas', True, len(ent), f'{len(ent)} entregas do município em {hoje.year}'))
    if p.get('rreo'):
        a, per, itens = ultimo(lambda a, per: _itens('rreo', {'an_exercicio': a, 'nr_periodo': per, 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': p['ibge']}), hoje.year)
        n = gravar(b, 'relatorios_fiscais', _linhas(itens, 'RREO', 'Anexo 14', a, per)) if itens else 0
        msg = f'RREO Anexo 14 de {a}, {per}º bimestre: {n} linhas' if itens else 'RREO Anexo 14 não encontrado'
        # o período mais recente pode vir sem as linhas de saúde e educação: guarda também o último que as tem
        tem_minimos = lambda its: any('Aplicado' in (i.get('coluna') or '') and ('Saúde' in (i.get('conta') or '') or 'Manutenção' in (i.get('conta') or '')) for i in its)
        if itens and not tem_minimos(itens):
            for a2, per2 in [(a, x) for x in range(per - 1, 0, -1)] + [(a - 1, x) for x in range(6, 0, -1)]:
                its = _itens('rreo', {'an_exercicio': a2, 'nr_periodo': per2, 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': p['ibge']})
                if its and tem_minimos(its):
                    n2 = gravar(b, 'relatorios_fiscais', _linhas(its, 'RREO', 'Anexo 14', a2, per2))
                    msg += f'; mínimos de saúde e educação do {per2}º bimestre de {a2} ({n2} linhas)'
                    break
        res.append(('rreo_anexo14', bool(itens), n, msg))
    if p.get('rgf_poder'):
        pod = p['rgf_poder']
        q = lambda a, per: _itens('rgf', {'an_exercicio': a, 'in_periodicidade': 'Q', 'nr_periodo': per, 'co_tipo_demonstrativo': 'RGF', 'no_anexo': 'RGF-Anexo 01', 'co_esfera': 'M', 'co_poder': pod, 'id_ente': p['ibge']}) if per <= 3 else []
        a, per, itens = ultimo(q, hoje.year)
        n = gravar(b, 'relatorios_fiscais', _linhas(itens, 'RGF', 'Anexo 01', a, per, pod)) if itens else 0
        res.append(('rgf_anexo01', bool(itens), n, f'RGF Anexo 01 ({pod}) de {a}, {per}º quadrimestre: {n} linhas' if itens else 'RGF não encontrado'))
        if itens and orgao['tipo'] == 'legislativo':
            atualizar_financas(b, a, per, itens)
    return res

def atualizar_financas(b, ano, per, itens):
    """Atualiza a despesa com pessoal da Câmara (bloco 'Quanto custa a Câmara') a partir do RGF."""
    v = next((num(i['valor']) for i in itens if i['conta'].startswith('DESPESA TOTAL COM PESSOAL') and i['coluna'] == 'Valor'), None)
    pct = next((num(i['valor']) for i in itens if i['conta'].startswith('DESPESA TOTAL COM PESSOAL') and i['coluna'].startswith('%')), None)
    if v is None or pct is None:
        return
    fin = db.cfg(b, 'financas', {}) or {}
    dtp = [x for x in fin.get('dtp', []) if x[0] != ano]
    dtp.append([ano, f'{per}º quadr.', v, pct])
    fin['dtp'] = sorted(dtp)
    fin['fonte'] = f'Siconfi (RGF do Legislativo, {per}º quadrimestre de {ano}), coleta automática'
    db.set_cfg(b, 'financas', fin)
