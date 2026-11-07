"""'<Município> em números' (bloco da página inicial do Executivo), calculado a partir das bases coletadas.
Só grava quando há dados; sem dados o bloco fica oculto."""
from .. import config, db
from ..web import moeda

def _pct(b, termo):
    r = db.um(b, """SELECT valor, ano, periodo FROM relatorios_fiscais WHERE demonstrativo='RREO' AND anexo='Anexo 14' AND conta ILIKE %s AND coluna ILIKE '%%Aplicado%%'
                    ORDER BY ano DESC, periodo DESC LIMIT 1""", (termo,))
    return r

def atualizar(o):
    b, ano = o['banco'], config.hoje().year
    rec = db.um(b, "SELECT sum(arrecadado) v, max(coletado_em) t FROM receitas WHERE fonte='fiorilli' AND ano=%s AND soma", (ano,))
    desp = db.um(b, 'SELECT sum(empenhado) e, sum(pago) p, max(coletado_em) t FROM despesas_unidade WHERE ano=%s', (ano,))
    if not rec or rec['v'] is None:
        return False
    kpis = [{'l': f'Receita arrecadada em {ano}', 'v': moeda(rec['v']), 'd': 'líquida das deduções (FUNDEB)', 'cor': '#146C43'}]
    if desp and desp['e'] is not None:
        kpis += [{'l': 'Despesa empenhada', 'v': moeda(desp['e']), 'd': 'compromissos assumidos no ano'},
                 {'l': 'Despesa paga', 'v': moeda(desp['p']), 'd': 'pagamentos feitos no ano', 'cor': '#7A4A00'}]
    fontes = ['sistema contábil da Prefeitura (Fiorilli)']
    s, e = _pct(b, '%Saúde%'), _pct(b, '%Manutenção e Desenv%')
    if s:
        kpis.append({'l': 'Aplicação em saúde', 'v': f"{float(s['valor']):.2f}%".replace('.', ','), 'd': f"mínimo 15% · RREO {s['periodo']}º bim. {s['ano']}", 'cor': '#9B1C1C'})
    if e:
        kpis.append({'l': 'Aplicação em educação', 'v': f"{float(e['valor']):.2f}%".replace('.', ','), 'd': f"mínimo 25% · RREO {e['periodo']}º bim. {e['ano']}", 'cor': '#1D4E89'})
    if s or e:
        fontes.append('Siconfi (RREO, Anexo 14)')
    t = max(x for x in (rec['t'], desp and desp['t']) if x)
    db.set_cfg(b, 'numeros', {'ano': ano, 'atualizado': t.isoformat(), 'kpis': kpis, 'fonte': ' e '.join(fontes),
                              'links': [['Receitas', '/transparencia/receitas'], ['Despesas', '/transparencia/empenhos'], ['Licitações', '/transparencia/licitacoes'],
                                        ['Contratos', '/transparencia/contratos'], ['Pessoal', '/transparencia/servidores']]})
    return True
