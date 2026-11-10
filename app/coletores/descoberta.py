"""Fase de descoberta (só leitura): chama cada endpoint de Docs/referencia/FONTES-DADOS.md, guarda uma amostra
(sem CPF) em DADOS_DIR/amostras e imprime o quadro endpoint · status · registros · campos.

Uso: python -m app.coletores.descoberta SLUG_DO_ORGAO [ano]   (ex.: pm-nome-do-municipio)
Não grava nada no banco. Respeita 1 requisição por segundo por fonte.
"""
from .. import config
import json, re, sys, time
from datetime import date
from pathlib import Path
import httpx

# alvo da descoberta: lido da tabela de fontes do órgão informado (nada de município fixo no código)
ALVO = {'fio': '', 'empresa': '', 'ibge': '', 'tcesp': ''}
CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')
_ultimo = {}

def sem_cpf(x):
    """Remove qualquer sequência com formato de CPF (11 dígitos) de textos da amostra."""
    if isinstance(x, str):
        return CPF.sub('[removido]', x)
    if isinstance(x, list):
        return [sem_cpf(i) for i in x]
    if isinstance(x, dict):
        return {k: sem_cpf(v) for k, v in x.items()}
    return x

def get(fonte, url, params=None, headers=None, tentativas=3):
    espera = 1.0 - (time.monotonic() - _ultimo.get(fonte, 0))
    if espera > 0:
        time.sleep(espera)
    erro = None
    for i in range(tentativas):
        try:
            _ultimo[fonte] = time.monotonic()
            with httpx.Client(timeout=60, follow_redirects=True, headers={'User-Agent': config.USER_AGENT, **(headers or {})}) as c:
                r = c.get(url, params=params)
            return r
        except httpx.HTTPError as e:
            erro = e
            time.sleep(2 * (i + 1))
    raise erro

def linhas(dados):
    if isinstance(dados, list):
        return dados
    if isinstance(dados, dict):
        for k in ('items', 'data', 'dados', 'Dados', 'resultado', 'value'):
            if isinstance(dados.get(k), list):
                return dados[k]
    return []

def endpoints(ano, mes, dia):
    per = {'DiaInicioPeriodo': '01', 'MesInicialPeriodo': '01', 'DiaFinalPeriodo': f'{dia:02d}', 'MesFinalPeriodo': f'{mes:02d}', 'Ano': str(ano),
           'Empresa': ALVO['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)}
    base = {'Empresa': ALVO['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)}
    e = [
        ('fiorilli', 'receitas', ALVO['fio'] + 'Receitas/', dict(per, Listagem='ReceitaOrcamentaria')),
        ('fiorilli', 'receitas_2025', ALVO['fio'] + 'Receitas/', dict(per, Listagem='ReceitaOrcamentaria', Ano=str(ano - 1), ConectarExercicio=str(ano - 1), DiaFinalPeriodo='31', MesFinalPeriodo='12')),
        ('fiorilli', 'despesas_unidade', ALVO['fio'] + 'Despesas/', dict(per, Listagem='DespesasPorUnidade')),
        ('fiorilli', 'empenhos', ALVO['fio'] + 'Despesas/', dict(per, Listagem='DespesasGerais', MostrarFornecedor='True', MostrarCNPJFornecedor='False')),
        ('fiorilli', 'empenhos_covid', ALVO['fio'] + 'Despesas/', dict(per, Listagem='DespesasGerais', MostrarFornecedor='True', MostrarCNPJFornecedor='True', UFParaFiltroCOVID='SP', ApenasIDEmpenho='False')),
        ('fiorilli', 'diarias', ALVO['fio'] + 'Despesas/', dict(per, Listagem='Diarias')),
        ('fiorilli', 'restos_pagar', ALVO['fio'] + 'Despesas/', dict(per, Listagem='DespesasRestosPagar', ApresentaNomeFavorecido='True')),
        ('fiorilli', 'ordem_cronologica', ALVO['fio'] + 'Despesas/', dict(base, Listagem='DespesasporExigibilidade', DiaInicioPeriodo=f'01/01/{ano}', DiaFinalPeriodo=f'{dia:02d}/{mes:02d}/{ano}', strTipoLista='1')),
        ('fiorilli', 'ordem_cronologica_t2', ALVO['fio'] + 'Despesas/', dict(base, Listagem='DespesasporExigibilidade', DiaInicioPeriodo=f'01/01/{ano}', DiaFinalPeriodo=f'{dia:02d}/{mes:02d}/{ano}', strTipoLista='2')),
        ('fiorilli', 'licitacoes', ALVO['fio'] + 'LicitacoesEContratos/', dict(base, Listagem='Licitacoes', Ano=str(ano))),
        ('fiorilli', 'contratos', ALVO['fio'] + 'LicitacoesEContratos/', dict(base, Listagem='Contratos', Ano=str(ano), ContratosApenasPublicados='True')),
        ('fiorilli', 'transferencias', ALVO['fio'] + 'Transferencias/', dict(base, Listagem='Transf')),
        ('fiorilli', 'emendas_art166a', ALVO['fio'] + 'Transferencias/', dict(base, Listagem='EmendasImpositivasArt166A')),
        ('fiorilli', 'emendas_cad_transf', ALVO['fio'] + 'Transferencias/', dict(base, Listagem='CadEmendasImpositivas')),
        ('fiorilli', 'emendas_cad_desp', ALVO['fio'] + 'Despesas/', dict(base, Listagem='CadEmendasImpositivas', Ano=str(ano))),
        ('fiorilli', 'servidores', ALVO['fio'] + 'Pessoal/', dict(base, Listagem='Servidores', Ano=str(ano), MesFinalPeriodo=f'{max(mes - 1, 1):02d}')),
        ('pncp', 'pncp_busca', 'https://pncp.gov.br/api/search/', {'tipos_documento': 'edital', 'municipios': ALVO['ibge'], 'status': 'todos', 'ordenacao': '-data', 'pagina': '1', 'tam_pagina': '50'}),
        ('siconfi', 'siconfi_entregas', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas', {'id_ente': ALVO['ibge'], 'an_referencia': str(ano)}),
        ('siconfi', 'siconfi_rreo14', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo', {'an_exercicio': str(ano - 1), 'nr_periodo': '6', 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': ALVO['ibge']}),
        ('siconfi', 'siconfi_rreo14_atual', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo', {'an_exercicio': str(ano), 'nr_periodo': '4', 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': ALVO['ibge']}),
        ('siconfi', 'siconfi_rgf_leg', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf', {'an_exercicio': str(ano), 'in_periodicidade': 'Q', 'nr_periodo': '2', 'co_tipo_demonstrativo': 'RGF', 'no_anexo': 'RGF-Anexo 01', 'co_esfera': 'M', 'co_poder': 'L', 'id_ente': ALVO['ibge']}),
        ('siconfi', 'siconfi_rgf_exe', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rgf', {'an_exercicio': str(ano), 'in_periodicidade': 'Q', 'nr_periodo': '2', 'co_tipo_demonstrativo': 'RGF', 'no_anexo': 'RGF-Anexo 01', 'co_esfera': 'M', 'co_poder': 'E', 'id_ente': ALVO['ibge']}),
        ('tcesp', 'tcesp_receitas_2025_01', f'https://transparencia.tce.sp.gov.br/api/json/receitas/{ALVO['tcesp']}/{ano - 1}/1', None),
        ('tcesp', 'tcesp_receitas_2025_12', f'https://transparencia.tce.sp.gov.br/api/json/receitas/{ALVO['tcesp']}/{ano - 1}/12', None),
    ]
    return e

def resumo_campos(rows):
    if not rows or not isinstance(rows[0], dict):
        return ''
    return ', '.join(list(rows[0].keys())[:14])

def alvo(slug):
    """Preenche ALVO com a fonte Fiorilli e o código IBGE do órgão cadastrado."""
    from .. import db
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE slug=%s', (slug,))
    if not o:
        sys.exit(f'Órgão {slug} não cadastrado.')
    f = db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='fiorilli'", (o['id'],))
    p = (f or {}).get('params') or {}
    t = db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='tcesp'", (o['id'],))
    ALVO.update(fio=p.get('base', ''), empresa=str(p.get('empresa', '')), ibge=o['ibge'], tcesp=((t or {}).get('params') or {}).get('municipio', ''))

def main(ano=None):
    hoje = date.today()
    ano = ano or hoje.year
    pasta = Path('/srv/dados/amostras'); pasta.mkdir(parents=True, exist_ok=True)
    quadro = []
    for fonte, nome, url, params in endpoints(ano, hoje.month, hoje.day):
        try:
            r = get(fonte, url, params, headers={'Accept': 'application/json'})
            st = r.status_code
            try:
                dados = r.json()
            except ValueError:
                dados = None
            rows = linhas(dados)
            extra = ''
            if isinstance(dados, dict) and not rows:
                extra = 'chaves: ' + ', '.join(list(dados.keys())[:10])
            amostra = {'url': str(r.url), 'status': st, 'coletado_em': hoje.isoformat(), 'registros': len(rows),
                       'amostra': sem_cpf(rows[:30] if rows else (dados if dados is not None else r.text[:2000]))}
            (pasta / f'{nome}.json').write_text(json.dumps(amostra, ensure_ascii=False, indent=1), encoding='utf-8')
            quadro.append((nome, st, len(rows), resumo_campos(rows) or extra or r.text[:120].replace('\n', ' ')))
        except Exception as e:
            quadro.append((nome, 'ERRO', 0, f'{type(e).__name__}: {e}'[:160]))
    (pasta / '_quadro.json').write_text(json.dumps(quadro, ensure_ascii=False, indent=1), encoding='utf-8')
    for q in quadro:
        print(' | '.join(str(x) for x in q))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit('Uso: python -m app.coletores.descoberta SLUG_DO_ORGAO [ano]')
    alvo(sys.argv[1])
    main(int(sys.argv[2]) if len(sys.argv) > 2 else None)
