"""Finanças da PREFEITURA no painel da Câmara (fonte 'financas_prefeitura', 23/11/2026).

Para quando a Câmara contrata o portal e a Prefeitura não, ou quando ela contrata mas está em outra instalação: o painel da Câmara
mostra a receita e a despesa da Prefeitura lidas de FONTE PÚBLICA, nunca do banco da Prefeitura. Os blocos aparecem sempre como
dado da Prefeitura, com a fonte, o link e a data da consulta, e nunca entram na transparência da Câmara.

Parâmetros (tabela `fontes`):
  modo     'auto' (padrão) | 'siconfi' | 'portal'
           auto: Prefeitura cliente → API pública do painel dela (/painel/api/financas.json); senão o portal de dados abertos
           (se houver base e empresa); senão o Siconfi.
  ibge     código do município (Siconfi)
  base, empresa   API pública de dados abertos do portal da transparência da Prefeitura (Fiorilli, VersaoJson) e código da entidade
  link     (opcional) página pública do portal da Prefeitura, mostrada como "ver a fonte"
O resumo fica em cfg 'financas_prefeitura' do banco da Câmara. Se a consulta falha, fica o último resumo válido e o aviso da falha."""
import calendar, re
from datetime import date
from .. import config, db
from .comum import buscar, num, url_exibivel
from . import financas as FI, fiorilli as FIO

SICONFI = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo'
CFG = 'financas_prefeitura'
MODOS = {'auto': 'Automático', 'siconfi': 'Siconfi (Tesouro Nacional)', 'portal': 'Portal de dados abertos da Prefeitura'}
# funções de governo (Portaria MOG 42/1999): no Anexo 2 do RREO, as demais linhas são subfunções
FUNCOES = ('Legislativa', 'Judiciária', 'Essencial à Justiça', 'Administração', 'Defesa Nacional', 'Segurança Pública', 'Relações Exteriores',
           'Assistência Social', 'Previdência Social', 'Saúde', 'Trabalho', 'Educação', 'Cultura', 'Direitos da Cidadania', 'Urbanismo', 'Habitação',
           'Saneamento', 'Gestão Ambiental', 'Ciência e Tecnologia', 'Agricultura', 'Organização Agrária', 'Indústria', 'Comércio e Serviços',
           'Comunicações', 'Energia', 'Transporte', 'Desporto e Lazer', 'Encargos Especiais')
ORIGENS_SIC = {'Impostos': 'Impostos', 'Taxas': 'Taxas', 'ReceitaPatrimonial': 'Receita patrimonial (rendimentos)',
               'TransferenciasCorrentesDaUniaoEDeSuasEntidades': 'Transferências correntes da União',
               'TransferenciasCorrentesDosEstadosEDoDistritoFederalEDeSuasEntidades': 'Transferências correntes do Estado',
               'TransferenciasCorrentesDeOutrasInstituicoesPublicas': 'Transferências de outras instituições públicas',
               'TransferenciasDeCapital': 'Transferências de capital', 'OutrasReceitasCorrentes': 'Outras receitas correntes'}
BIM = ['1º bim.', '2º bim.', '3º bim.', '4º bim.', '5º bim.', '6º bim.']


# ---------- Siconfi: RREO Anexo 1 (balanço orçamentário) e Anexo 2 (despesa por função) ----------
def _rreo(ibge, ano, per, anexo):
    p = {'an_exercicio': ano, 'nr_periodo': per, 'co_tipo_demonstrativo': 'RREO', 'no_anexo': anexo, 'id_ente': ibge}
    d = buscar('siconfi', SICONFI, p)
    return (d.get('items', []) if isinstance(d, dict) else []), url_exibivel(SICONFI, p)

def _v(itens, cod, coluna):
    """Valor da linha (cod_conta) na coluna cujo nome começa com `coluna`."""
    return next((num(i.get('valor')) for i in itens if i.get('cod_conta') == cod and str(i.get('coluna', '')).startswith(coluna)), None)

def de_siconfi(p, hoje):
    ibge = str(p.get('ibge') or '')
    if not ibge:
        raise ValueError('sem código IBGE do município')
    a1, ano, per, link = [], None, None, ''
    for a in (hoje.year, hoje.year - 1):
        for x in range(6, 0, -1):
            a1, link = _rreo(ibge, a, x, 'RREO-Anexo 01')
            if a1 and _v(a1, 'TotalReceitas', 'Até o Bimestre') is not None:
                ano, per = a, x
                break
        if ano:
            break
    if not ano:
        return None
    arrec = _v(a1, 'TotalReceitas', 'Até o Bimestre')
    rep = sum(_v(a1, c, 'Até o Bimestre') or 0 for c in ('TransferenciasCorrentes', 'TransferenciasDeCapital'))
    origens = sorted(({'nome': n, 'v': _v(a1, c, 'Até o Bimestre')} for c, n in ORIGENS_SIC.items()), key=lambda x: -(x['v'] or 0))
    a2, _ = _rreo(ibge, ano, per, 'RREO-Anexo 02')
    areas = [{'area': i['conta'], 'emp': num(i.get('valor'))} for i in a2
             if i.get('conta') in FUNCOES and str(i.get('coluna', '')).startswith('DESPESAS EMPENHADAS ATÉ') and (num(i.get('valor')) or 0) > 0]
    # série por bimestre: receita do bimestre e despesa paga no bimestre (diferença entre os acumulados "pagas até o bimestre")
    serie, pago_ant = [], 0.0
    for x in range(1, per + 1):
        its = a1 if x == per else _rreo(ibge, ano, x, 'RREO-Anexo 01')[0]
        rb, pa = _v(its, 'TotalReceitas', 'No Bimestre'), _v(its, 'TotalDespesas', 'DESPESAS PAGAS ATÉ')
        if rb is None or pa is None:
            serie, pago_ant = [], 0.0  # bimestre faltando: a diferença deixaria de ser do bimestre; recomeça a série
            continue
        serie.append({'n': x, 'rotulo': BIM[x - 1], 'receita': round(rb, 2), 'despesa_paga': round(pa - pago_ant, 2), 'parcial': False})
        pago_ant = pa
    inst = next((i.get('instituicao') for i in a1 if i.get('instituicao')), '') or 'Prefeitura'
    return {'origem': 'siconfi', 'nome': inst, 'ano': ano, 'ate': date(ano, per * 2, calendar.monthrange(ano, per * 2)[1]).isoformat(),
            'periodo': f'até o {per}º bimestre de {ano}',
            'fonte': f'Siconfi (Tesouro Nacional) — RREO, Anexos 1 e 2, do {per}º bimestre de {ano}, publicado pela Prefeitura (valores do município consolidado)',
            'link': link,
            'receita': {'arrecadada': arrec, 'prevista': _v(a1, 'TotalReceitas', 'PREVISÃO ATUALIZADA'), 'repasses': rep, 'base_repasses': arrec,
                        'metodo_repasses': 'transferências correntes e de capital ÷ total das receitas realizadas (RREO, Anexo 1)',
                        'origens': [o for o in origens if o['v']][:5]},
            'despesa': {'dotacao': _v(a1, 'TotalDespesas', 'DOTAÇÃO ATUALIZADA'), 'empenhada': _v(a1, 'TotalDespesas', 'DESPESAS EMPENHADAS ATÉ'),
                        'paga': _v(a1, 'TotalDespesas', 'DESPESAS PAGAS ATÉ')},
            'areas': {'tipo': 'função de governo', 'itens': sorted(areas, key=lambda x: -x['emp'])},
            'serie': {'tipo': 'bimestre', 'itens': serie}}


# ---------- portal de dados abertos da Prefeitura (API pública Fiorilli VersaoJson) ----------
def _fio(p, caminho, params):
    d = buscar('fiorilli', p['base'].rstrip('/') + '/' + caminho, params)
    return d if isinstance(d, list) else []

TOTAL = re.compile(r'^\d000\.00')
NIVEL1 = re.compile(r'^[0-9]{4}\.00\.0\.0\.00\.00$')
ORIGEM = re.compile(r'^[12][0-9][1-9]0\.00\.0\.0\.00\.00$')

def de_portal(p, hoje):
    if not p.get('base') or not p.get('empresa'):
        raise ValueError('modo portal sem o endereço da API (base) ou o código da entidade (empresa)')
    ano = hoje.year
    q = FIO._per(p, ano, hoje)
    rec = [r for r in _fio(p, 'Receitas/', dict(q, Listagem='ReceitaOrcamentaria')) if not r.get('FONTE')]
    if not rec:
        return None
    desp = _fio(p, 'Despesas/', dict(q, Listagem='DespesasPorUnidade'))
    tot = [r for r in rec if TOTAL.match(str(r.get('CODIGO', '')))]
    arrec = sum(num(r.get('ARRECADADO_TOTAL')) or 0 for r in tot)
    prev = sum((num(r.get('PREVISAO_ATUALIZADA')) if num(r.get('PREVISAO_ATUALIZADA')) is not None else num(r.get('PREVISAO_INICIAL'))) or 0 for r in tot)
    cod = {}
    for r in rec:
        if NIVEL1.match(str(r.get('CODIGO', ''))):
            cod[r['CODIGO'][:4]] = cod.get(r['CODIGO'][:4], 0) + (num(r.get('ARRECADADO_TOTAL')) or 0)
    bruta = cod.get('1000', 0) + cod.get('2000', 0)
    from ..painel_blocos import frase
    orig = sorted(({'nome': frase(r.get('NOME')) + (' (capital)' if str(r['CODIGO']).startswith('2') else ''), 'v': num(r.get('ARRECADADO_TOTAL'))} for r in rec
                   if ORIGEM.match(str(r.get('CODIGO', ''))) and (num(r.get('ARRECADADO_TOTAL')) or 0) > 0), key=lambda x: -x['v'])[:5]
    serie = []
    for mes in range(1, hoje.month + 1):
        parcial = mes == hoje.month
        qm = FI._per(p, ano, mes, hoje.day if parcial else None)
        rm = _fio(p, 'Receitas/', dict(qm, Listagem='ReceitaOrcamentaria'))
        dm = _fio(p, 'Despesas/', dict(qm, Listagem='DespesasPorUnidade'))
        if not rm and not dm:
            continue
        serie.append({'n': mes, 'rotulo': '', 'parcial': parcial,
                      'receita': round(sum(num(r.get('ARRECADADO_PERIODO')) or 0 for r in rm if TOTAL.match(str(r.get('CODIGO', ''))) and not r.get('FONTE')), 2),
                      'despesa_paga': round(sum(num(r.get('PAGO')) or 0 for r in dm), 2)})
    soma = lambda k: round(sum(num(r.get(k)) or 0 for r in desp), 2) if desp else None
    return {'origem': 'portal', 'nome': p.get('nome') or 'Prefeitura', 'ano': ano, 'ate': hoje.isoformat(), 'periodo': f"até {hoje.strftime('%d/%m/%Y')}",
            'fonte': 'portal da transparência da Prefeitura (API pública de dados abertos do sistema contábil)', 'link': p.get('link') or p['base'],
            'receita': {'arrecadada': round(arrec, 2), 'prevista': round(prev, 2) or None, 'repasses': cod.get('1700', 0) + cod.get('2400', 0), 'base_repasses': bruta,
                        'metodo_repasses': 'transferências correntes e de capital (naturezas 1.7 e 2.4) ÷ receita bruta (1 + 2), antes das deduções do FUNDEB',
                        'origens': orig},
            'despesa': {'dotacao': soma('DOTACAO_ATUALIZADA'), 'empenhada': soma('EMPENHADO'), 'paga': soma('PAGO')},
            'areas': {'tipo': 'unidade orçamentária', 'itens': sorted(({'area': frase(r.get('DESCRICAO')), 'emp': num(r.get('EMPENHADO'))} for r in desp if (num(r.get('EMPENHADO')) or 0) > 0),
                                                                    key=lambda x: -x['emp'])},
            'serie': {'tipo': 'mes', 'itens': serie}}


# ---------- Prefeitura cliente: API pública do painel dela (mesma instalação ou outra) ----------
def de_cliente(o):
    from .. import orgaos, integracao
    pm = orgaos.executivo_do(o['ibge'])
    if not pm:
        return None
    try:
        d = integracao.publico(pm, '/painel/api/financas.json')
    except Exception:
        return None  # sem o painel contratado (404) ou fora do ar: segue para a fonte pública seguinte
    if not isinstance(d, dict) or not d.get('receita'):
        return None
    d['origem'] = 'cliente'
    d['link'] = f"https://{pm['dominio']}/painel?tema=fin" if pm.get('dominio') else d.get('link', '')
    return d


def resumo(o, p, hoje):
    """(resumo, origem tentada) pela ordem do modo escolhido."""
    modo = p.get('modo') or 'auto'
    if modo == 'siconfi':
        return de_siconfi(p, hoje)
    if modo == 'portal':
        return de_portal(p, hoje)
    r = de_cliente(o)
    if r:
        return r
    if p.get('base') and p.get('empresa'):
        r = de_portal(p, hoje)
        if r:
            return r
    return de_siconfi(dict(p, ibge=p.get('ibge') or o.get('ibge')), hoje)


def atual(b):
    return db.cfg(b, CFG, {}) or {}


def coletar(o, p, hoje=None):
    hoje = hoje or config.hoje()
    if o['tipo'] != 'legislativo':
        return [('resumo', False, 0, 'só para a Câmara: a Prefeitura publica as finanças pela própria fonte "financas"')]
    b = o['banco']
    guardado = atual(b)
    try:
        r = resumo(o, p, hoje)
        erro = '' if r else 'a fonte não devolveu dados do ano corrente nem do anterior'
    except Exception as e:
        r, erro = None, f'{type(e).__name__}: {str(e)[:150]}'
    if not r:
        guardado.update({'falha_em': config.agora().isoformat(), 'falha_msg': erro})
        db.set_cfg(b, CFG, guardado)
        return [('resumo', False, 0, erro + ('; mantido o último resumo válido' if guardado.get('resumo') else ''))]
    r['coletado_em'] = config.agora().isoformat()
    db.set_cfg(b, CFG, {'resumo': r})
    return [('resumo', True, len(r['serie']['itens']), f"{MODOS.get(r['origem'], 'Prefeitura cliente')}: {r['periodo']}, {len(r['serie']['itens'])} período(s), "
                                                       f"{len(r['areas']['itens'])} {r['areas']['tipo']}(s)")]
