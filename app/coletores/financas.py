"""Série mensal das finanças (fonte 'financas', uma vez por dia, de madrugada) para os blocos do painel.

Usa a mesma API pública e a mesma entidade da fonte 'fiorilli' do órgão, pedindo cada mês do ano corrente como período
(a API devolve o movimento do período: receita em ARRECADADO_PERIODO; despesa paga e empenhada por unidade).
Também mantém a SUGESTÃO de área de cada unidade orçamentária (função de governo predominante nos empenhos do ano),
que o administrador pode trocar em /admin/indicadores; nada é fixo de um município."""
import calendar, re
from .. import config, db
from .comum import buscar, num

def _per(p, ano, mes, ate_dia=None):
    fim = ate_dia or calendar.monthrange(ano, mes)[1]
    return {'DiaInicioPeriodo': '01', 'MesInicialPeriodo': f'{mes:02d}', 'DiaFinalPeriodo': f'{fim:02d}', 'MesFinalPeriodo': f'{mes:02d}',
            'Ano': str(ano), 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)}

def _get(p, caminho, params):
    d = buscar('fiorilli', p['base'].rstrip('/') + '/' + caminho, params)
    return d if isinstance(d, list) else []

def ler_mes(p, ano, mes, ate_dia=None):
    q = _per(p, ano, mes, ate_dia)
    rec = _get(p, 'Receitas/', dict(q, Listagem='ReceitaOrcamentaria'))
    desp = _get(p, 'Despesas/', dict(q, Listagem='DespesasPorUnidade'))
    receita = sum(num(r.get('ARRECADADO_PERIODO')) or 0 for r in rec if re.match(r'^\d000\.00', str(r.get('CODIGO', ''))) and not r.get('FONTE'))
    return {'receita': round(receita, 2) if rec else None, 'despesa_paga': round(sum(num(r.get('PAGO')) or 0 for r in desp), 2) if desp else None,
            'despesa_empenhada': round(sum(num(r.get('EMPENHADO')) or 0 for r in desp), 2) if desp else None}

def sugerir_areas(b, ano):
    """Área sugerida de cada unidade = função de governo com mais empenho no ano. Não mexe no que o administrador definiu."""
    n = 0
    for u in db.todos(b, """SELECT d.codigo, d.unidade,
                            (SELECT e.funcao FROM empenhos e WHERE e.ano=%s AND upper(e.unidade)=upper(d.unidade) AND e.funcao<>''
                             GROUP BY e.funcao ORDER BY sum(e.empenhado) DESC LIMIT 1) funcao
                            FROM despesas_unidade d WHERE d.ano=%s""", (ano, ano)):
        r = db.exe(b, """INSERT INTO areas_unidades (codigo, unidade, area) VALUES (%s,%s,%s)
                         ON CONFLICT (codigo) DO UPDATE SET unidade=EXCLUDED.unidade,
                         area=CASE WHEN areas_unidades.origem='admin' THEN areas_unidades.area ELSE EXCLUDED.area END RETURNING 1""",
                   (u['codigo'], u['unidade'], u['funcao'] or 'Outras'))
        n += 1 if r else 0
    return n

def coletar(o, p, hoje=None):
    hoje = hoje or config.hoje()
    if not p.get('base') or not p.get('empresa'):
        return [('mensal', False, 0, 'fonte sem base/empresa da Fiorilli')]
    b, ano, n = o['banco'], hoje.year, 0
    for mes in range(1, hoje.month + 1):
        parcial = mes == hoje.month
        v = ler_mes(p, ano, mes, hoje.day if parcial else None)
        if v['receita'] is None and v['despesa_paga'] is None:
            continue
        db.exe(b, """INSERT INTO fin_mensal (ano, mes, receita, despesa_paga, despesa_empenhada, parcial, coletado_em) VALUES (%s,%s,%s,%s,%s,%s,now())
                     ON CONFLICT (ano, mes) DO UPDATE SET receita=EXCLUDED.receita, despesa_paga=EXCLUDED.despesa_paga,
                     despesa_empenhada=EXCLUDED.despesa_empenhada, parcial=EXCLUDED.parcial, coletado_em=now()""",
               (ano, mes, v['receita'], v['despesa_paga'], v['despesa_empenhada'], parcial))
        n += 1
    na = sugerir_areas(b, ano)
    return [('mensal', bool(n), n, f'{n} mês(es) de {ano} (receita, despesa paga e empenhada); {na} unidade(s) no agrupamento por área')]
