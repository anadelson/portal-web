"""Blocos do /painel no formato do protótipo (Main.dc.html, isPainel). Só dados reais coletados; bloco sem dado do ano não
aparece. Valores "por habitante" são cálculo do portal (valor oficial ÷ população estimada do IBGE), sempre identificados."""
import calendar
from datetime import date
from markupsafe import Markup
from . import config, db, painel as P

ESCURO, LARANJA, VERDE = '#1D4E89', '#E8A33D', '#146C43'

NOMES_PROPRIOS = {'união': 'União', 'distrito federal': 'Distrito Federal', 'estados': 'Estados', 'municípios': 'Municípios', 'sus': 'SUS', 'fundeb': 'FUNDEB',
                  'sistema único de saúde': 'Sistema Único de Saúde', 'iptu': 'IPTU', 'iss': 'ISS', 'itbi': 'ITBI', 'irrf': 'IRRF', 'fpm': 'FPM', 'icms': 'ICMS', 'ipva': 'IPVA'}

def frase(t):
    """Texto em caixa alta da fonte → só a primeira letra maiúscula, preservando nomes próprios e siglas comuns."""
    import re
    s = str(t or '').strip().lower()
    for k, v in NOMES_PROPRIOS.items():
        s = re.sub(rf'\b{re.escape(k)}\b', v, s)
    return s[:1].upper() + s[1:]

def mi(v):
    return 'R$ ' + P._br(float(v) / 1e6, 1) + ' mi'

def reais(v):
    return 'R$ ' + P._br(float(v), 0)

def pct(a, b, casas=0):
    return P._br(float(a) / float(b) * 100, casas) + '%' if b else '—'

def dm(d):
    return d.strftime('%d/%m') if d else ''

def _ind(b, chave):
    i = db.um(b, 'SELECT * FROM indicadores WHERE chave=%s AND visivel', (chave,))
    return P.montar(b, i) if i else None

def _serie(b, chave):
    i = db.um(b, 'SELECT * FROM indicadores WHERE chave=%s AND visivel', (chave,))
    return (i, P.serie(b, i['id'])) if i else (None, [])

def _publico(ibge, fonte, chave):
    r = db.um(db.PLATAFORMA, 'SELECT payload, coletado_em FROM dados_publicos WHERE ibge=%s AND fonte=%s AND chave=%s', (str(ibge), fonte, str(chave)))
    return (r['payload'], r['coletado_em']) if r else (None, None)

def selo(o):
    r = db.um(db.PLATAFORMA, "SELECT max(fim) t FROM coletas WHERE orgao_slug=%s AND fonte LIKE 'fiorilli:%%' AND ok", (o['slug'],))
    return r['t'] if r and r['t'] else None

def populacao(b):
    m = _ind(b, 'mun_populacao')
    if not m or m['ult']['valor'] is None:
        return None
    return {'n': float(m['ult']['valor']), 'ano': m['ult']['periodo'], 'nota': m['ult']['nota']}

def _calc(pop):
    return f"cálculo do portal: valor oficial ÷ população estimada (IBGE {pop['ano']}, {P._br(pop['n'], 0)} hab.)"

def areas(b, ano):
    """Valores por área (agrupamento editável das unidades orçamentárias)."""
    return db.todos(b, """SELECT coalesce(a.area, 'Sem área definida') area, sum(d.dotacao_atualizada) dot, sum(d.empenhado) emp, sum(d.pago) pago, count(*) n
                          FROM despesas_unidade d LEFT JOIN areas_unidades a ON a.codigo=d.codigo WHERE d.ano=%s GROUP BY 1 ORDER BY sum(d.empenhado) DESC NULLS LAST""", (ano,))

def unidades_da_area(b, ano, area):
    return db.todos(b, """SELECT d.unidade, d.dotacao_atualizada dot, d.empenhado emp, d.pago FROM despesas_unidade d JOIN areas_unidades a ON a.codigo=d.codigo
                          WHERE d.ano=%s AND a.area=%s ORDER BY d.empenhado DESC NULLS LAST""", (ano, area))

def financas(o, hoje):
    b, ano = o['banco'], hoje.year
    rec = db.um(b, "SELECT sum(arrecadado) liq, sum(coalesce(atualizado, previsto)) prev, max(coletado_em) t FROM receitas WHERE fonte='fiorilli' AND ano=%s AND soma", (ano,))
    if not rec or rec['liq'] is None:
        return None
    ate = rec['t'].astimezone().date() if rec['t'] else hoje
    cod = {r['c']: float(r['v'] or 0) for r in db.todos(b, """SELECT left(codigo, 4) c, sum(arrecadado) v FROM receitas WHERE fonte='fiorilli' AND ano=%s
                                                              AND fonte_recurso='' AND codigo ~ '^[0-9]{4}\\.00\\.0\\.0\\.00\\.00$' GROUP BY 1""", (ano,))}
    bruta = cod.get('1000', 0) + cod.get('2000', 0)
    repasses = cod.get('1700', 0) + cod.get('2400', 0)
    desp = db.um(b, 'SELECT sum(dotacao_atualizada) dot, sum(empenhado) emp, sum(pago) pago FROM despesas_unidade WHERE ano=%s', (ano,))
    ar = areas(b, ano)
    porarea = {a['area']: a for a in ar}
    pop = populacao(b)
    k = [{'l': f'Receita arrecadada em {ano}', 'v': mi(rec['liq']), 'd': f"até {dm(ate)}, {pct(rec['liq'], rec['prev'])} do previsto" if rec['prev'] else f'até {dm(ate)}',
          'cor': 'var(--cor)', 'href': '/painel/fin_receita'}]
    if desp and desp['pago'] is not None:
        k.append({'l': f'Despesa paga em {ano}', 'v': mi(desp['pago']), 'd': f"até {dm(ate)}, {pct(desp['pago'], desp['dot'])} da dotação", 'cor': VERDE, 'href': '/painel/fin_despesa_paga'})
    if pop:
        k.append({'l': 'Receita por habitante', 'v': reais(float(rec['liq']) / pop['n']), 'd': _calc(pop), 'cor': ESCURO})
        for area, cor in (('Saúde', '#C8553D'), ('Educação', '#6B2D5C')):
            if porarea.get(area) and porarea[area]['emp']:
                k.append({'l': f'{area} por habitante', 'v': reais(float(porarea[area]['emp']) / pop['n']), 'd': f'empenhado em {ano}; ' + _calc(pop), 'cor': cor})
    if bruta:
        k.append({'l': 'Receita vinda de repasses', 'v': pct(repasses, bruta), 'd': 'União e Estado; o resto é arrecadação própria', 'cor': LARANJA})
    # mês a mês
    meses = db.todos(b, 'SELECT * FROM fin_mensal WHERE ano=%s ORDER BY mes', (ano,))
    mensal = None
    if meses:
        tr = sum(float(m['receita'] or 0) for m in meses); tp = sum(float(m['despesa_paga'] or 0) for m in meses)
        sup = sum(1 for m in meses if (m['receita'] or 0) >= (m['despesa_paga'] or 0))
        ult = P.MESES[meses[-1]['mes'] - 1]
        mensal = {'meses': meses, 'grafico': grafico_mensal(meses, ano),
                  'frase': f"De janeiro a {ult}{' (mês em andamento)' if meses[-1]['parcial'] else ''} entraram {mi(tr)} e foram pagos {mi(tp)}. A receita superou a despesa paga em {sup} dos {len(meses)} meses.",
                  'coletado': max(m['coletado_em'] for m in meses)}
    # para onde vai
    tot_emp = sum(float(a['emp'] or 0) for a in ar)
    para_onde = None
    if tot_emp:
        mx = max(float(a['emp'] or 0) for a in ar) or 1
        itens = [{'area': a['area'], 'v': mi(a['emp'] or 0), 'p': pct(a['emp'] or 0, tot_emp), 'w': round(float(a['emp'] or 0) / mx * 100, 1)} for a in ar if a['emp']]
        frase_area = ''
        if porarea.get('Saúde') and porarea.get('Educação'):
            frase_area = f"Saúde e educação somam {pct(float(porarea['Saúde']['emp'] or 0) + float(porarea['Educação']['emp'] or 0), tot_emp)} do que a Prefeitura já empenhou em {ano}."
        para_onde = {'itens': itens, 'frase': frase_area, 'n_unid': sum(a['n'] for a in ar)}
    # de onde vem
    de_onde = None
    if bruta:
        top = db.todos(b, """SELECT codigo, nome, arrecadado v FROM receitas WHERE fonte='fiorilli' AND ano=%s AND fonte_recurso=''
                             AND codigo ~ '^[12][0-9][1-9]0\\.00\\.0\\.0\\.00\\.00$' AND arrecadado > 0 ORDER BY arrecadado DESC LIMIT 5""", (ano,))
        rp = round(repasses / bruta * 100)
        de_onde = {'rep': pct(repasses, bruta), 'prop': pct(bruta - repasses, bruta), 'w': round(repasses / bruta * 100, 1),
                   'frase': f'De cada R$ 100 que entram, R$ {rp} vêm de repasses da União e do Estado.',
                   'origens': [{'nome': frase(t['nome']), 'v': mi(t['v']), 'p': pct(t['v'], bruta)} for t in top]}
    # execução
    dias = 366 if calendar.isleap(ano) else 365
    ritmo = (ate - date(ano, 1, 1)).days + 1
    exe = []
    if rec['prev']:
        exe.append({'l': 'Receita arrecadada / prevista', 'p': pct(rec['liq'], rec['prev'], 1), 'w': min(100, float(rec['liq']) / float(rec['prev']) * 100), 'd': f"{mi(rec['liq'])} de {mi(rec['prev'])}", 'cor': 'var(--cor)'})
    if desp and desp['dot']:
        exe.append({'l': 'Despesa empenhada / dotação', 'p': pct(desp['emp'], desp['dot'], 1), 'w': min(100, float(desp['emp']) / float(desp['dot']) * 100), 'd': f"{mi(desp['emp'])} de {mi(desp['dot'])}", 'cor': ESCURO})
        exe.append({'l': 'Despesa paga / dotação', 'p': pct(desp['pago'], desp['dot'], 1), 'w': min(100, float(desp['pago']) / float(desp['dot']) * 100), 'd': f"{mi(desp['pago'])} de {mi(desp['dot'])}", 'cor': VERDE})
    return {'ano': ano, 'ate': ate, 'kpis': k, 'mensal': mensal, 'para_onde': para_onde, 'de_onde': de_onde,
            'execucao': {'itens': exe, 'ritmo_w': round(ritmo / dias * 100, 1), 'ritmo': f"{P._br(ritmo / dias * 100, 0)}% (até {dm(ate)})"} if exe else None}

def grafico_mensal(meses, ano):
    """Barras agrupadas receita × despesa paga, com valores escritos e descrição; a tabela equivalente fica em details."""
    W, H, ml, mb, mt = 720, 260, 8, 40, 26
    mx = max([float(m['receita'] or 0) for m in meses] + [float(m['despesa_paga'] or 0) for m in meses] + [1])
    n = len(meses); passo = (W - 2 * ml) / max(n, 1); lb = min(26, passo * 0.36); base = H - mb
    y = lambda v: base - float(v or 0) / mx * (H - mt - mb)
    desc = '; '.join(f"{P.MESES[m['mes'] - 1]}: receita {mi(m['receita'] or 0)}, despesa paga {mi(m['despesa_paga'] or 0)}" for m in meses)
    p = [f'<svg class="grafico" viewBox="0 0 {W} {H}" role="img" aria-labelledby="gm-t gm-d" xmlns="http://www.w3.org/2000/svg"><title id="gm-t">Receita e despesa paga por mês, {ano}</title><desc id="gm-d">{P._esc(desc)}</desc>',
         f'<line x1="{ml}" y1="{base}" x2="{W - ml}" y2="{base}" stroke="#9AA5B1"/>']
    for i, m in enumerate(meses):
        cx = ml + passo * i + passo / 2
        for j, (v, cor) in enumerate(((m['receita'], 'var(--cor)'), (m['despesa_paga'], LARANJA))):
            x = cx - lb - 1 if j == 0 else cx + 1
            p.append(f'<rect x="{x:.1f}" y="{y(v):.1f}" width="{lb:.1f}" height="{max(base - y(v), 1):.1f}" rx="2" style="fill:{cor}"/>')
        p.append(f'<text x="{cx:.1f}" y="{base + 16}" text-anchor="middle" font-size="12" fill="#17212B">{P.MESES[m["mes"] - 1]}</text>')
        if m['parcial']:
            p.append(f'<text x="{cx:.1f}" y="{base + 30}" text-anchor="middle" font-size="10" fill="#4B5563">parcial</text>')
    p.append('</svg>')
    return Markup(''.join(p))

def contratacoes(o):
    m = _ind(o['banco'], 'cont_publicadas')
    if not m or not isinstance(m['ult']['detalhe'], list) or not m['ult']['detalhe']:
        return None
    det = m['ult']['detalhe']; tot = sum(x[1] for x in det); mx = max(x[1] for x in det) or 1
    disp = sum(x[1] for x in det if str(x[0]).lower().startswith('dispensa'))
    return {'ano': m['ult']['periodo'], 'nota': m['ult']['nota'], 'total': tot, 'coletado': m['ult']['coletado_em'],
            'itens': [{'l': x[0], 'n': P._br(x[1], 0), 'p': pct(x[1], tot, 1), 'w': round(x[1] / mx * 100, 1)} for x in det],
            'frase': f"Das {P._br(tot, 0)} contratações publicadas pelo município em {m['ult']['periodo']} ({m['ult']['nota']}), {pct(disp, tot, 1)} são dispensas de licitação." if disp else ''}

def minimos(b, chaves):
    out = []
    for ch in chaves:
        i, s = _serie(b, ch)
        if not s:
            continue
        esc = max([float(x['valor']) for x in s if x['valor'] is not None] + [float(i['meta'] or 0) * 1.6, 1])
        out.append({'l': i['nome'], 'base': i['meta_base_legal'], 'meta': P._br(float(i['meta']), 0) + '%' if i['meta'] is not None else '', 'href': f"/painel/{ch}",
                    'meta_w': round(float(i['meta']) / esc * 100, 1) if i['meta'] is not None else None,
                    'anos': [{'ano': x['periodo'] + (' (parcial)' if x['parcial'] else ''), 'p': P.exibir(i, x), 'w': round(float(x['valor']) / esc * 100, 1)} for x in s[-5:] if x['valor'] is not None],
                    'coletado': max(x['coletado_em'] for x in s)})
    return out

def orcamento_area(b, ano, area):
    us = unidades_da_area(b, ano, area)
    if not us or not any(u['emp'] for u in us):
        return None
    tot = {k: sum(float(u[k] or 0) for u in us) for k in ('dot', 'emp', 'pago')}
    return {'area': area, 'tot': tot, 'itens': [{'nome': u['unidade'].title(), 'we': round(float(u['emp'] or 0) / float(u['dot']) * 100, 1) if u['dot'] else 0,
                                                 'wp': round(float(u['pago'] or 0) / float(u['dot']) * 100, 1) if u['dot'] else 0, 'p': pct(u['emp'] or 0, u['dot']) if u['dot'] else '—',
                                                 'd': f"Empenhado {mi(u['emp'] or 0)} · pago {mi(u['pago'] or 0)} · dotação {mi(u['dot'] or 0)}"} for u in us]}

def kpi_ind(m, rotulo=None, detalhe=None, cor=None):
    if not m:
        return None
    return {'l': rotulo or m['nome'], 'v': m['valor_curto'], 'd': detalhe or (f"{m['ult']['periodo']} · {m['meta_txt']}" if m['meta_txt'] else f"{m['ult']['periodo']} · {m['ult']['nota']}"),
            'cor': cor or 'var(--cor)', 'href': f"/painel/{m['chave']}"}

def vitais(b):
    i1, s1 = _serie(b, 'saude_nascidos'); i2, s2 = _serie(b, 'saude_obitos')
    if not s1 and not s2:
        return None
    anos = sorted({x['periodo'] for x in s1 + s2})[-6:]
    d1 = {x['periodo']: x for x in s1}; d2 = {x['periodo']: x for x in s2}
    linhas = [{'ano': a, 'nv': P.exibir(i1, d1[a]) if a in d1 else '—', 'ob': P.exibir(i2, d2[a]) if a in d2 else '—',
               'nv_v': None if a not in d1 or P.suprimido(i1, d1[a]) else float(d1[a]['valor']), 'ob_v': None if a not in d2 or P.suprimido(i2, d2[a]) else float(d2[a]['valor'])} for a in anos]
    mx = max([x['nv_v'] or 0 for x in linhas] + [x['ob_v'] or 0 for x in linhas] + [1])
    for x in linhas:
        x['nv_h'] = round((x['nv_v'] or 0) / mx * 120); x['ob_h'] = round((x['ob_v'] or 0) / mx * 120)
    aria = 'Nascidos vivos e óbitos por ano: ' + '; '.join(f"{x['ano']}: {x['nv']} nascimentos, {x['ob']} óbitos" for x in linhas) + '.'
    return {'linhas': linhas, 'aria': aria, 'coletado': max(x['coletado_em'] for x in s1 + s2)}

def cnes(o):
    lst, t = _publico(o['ibge'], 'cnes_lista', 'atual')
    m = _ind(o['banco'], 'saude_estabelecimentos')
    if not m:
        return None
    return {'lista': (lst or {}).get('estabelecimentos', []), 'n': m['valor_curto'], 'competencia': m['ult']['periodo'], 'coletado': m['ult']['coletado_em']}

def ideb(o):
    b = o['banco']
    i, s = _serie(b, 'edu_ideb_ai')
    if not s:
        return None
    m = P.montar(b, i)
    saeb = []
    for ch, nome in (('edu_saeb_mat_ai', 'Matemática'), ('edu_saeb_lp_ai', 'Língua Portuguesa')):
        mm = _ind(b, ch)
        if mm:
            saeb.append({'l': nome, 'v': mm['valor_txt'], 'per': mm['ult']['periodo'], 'href': f'/painel/{ch}'})
    comp = []
    per = m['ult']['periodo']
    for esc, cod in (('Estado', str(o['ibge'])[:2]), ('Brasil', 'BR')):
        pl, _ = _publico(cod, 'ideb_comparacao', 'ai')
        if pl and pl.get('rede') == 'Pública' and per in pl.get('serie', {}) and pl['serie'][per].get('ideb') is not None:
            comp.append({'l': f"{pl['nome']} (rede pública)", 'v': P._br(pl['serie'][per]['ideb'], 1)})
    resp = (m['ult']['detalhe'] or {}).get('responsavel', '') if isinstance(m['ult']['detalhe'], dict) else ''
    return {'m': m, 'grafico': P.grafico(i, s, 'g-ideb-painel'), 'saeb': saeb, 'comp': comp, 'per': per, 'resp': resp}

def iegm(o):
    b = o['banco']
    i, s = _serie(b, 'gestao_iegm')
    if not s:
        return None
    ult = s[-1]
    dims = []
    for ch, nome in P._IEGM[1:]:
        _, sd = _serie(b, ch)
        x = next((v for v in sd if v['periodo'] == ult['periodo']), None)
        if x:
            rot = nome.split('— ')[-1]
            dims.append({'l': rot[:1].upper() + rot[1:], 'f': x['texto'], 'href': f'/painel/{ch}'})
    dist, _ = _publico(str(o['ibge'])[:2], 'iegm_distribuicao', ult['periodo'])
    leg = {'A': 'altamente efetiva', 'B+': 'muito efetiva', 'B': 'efetiva', 'C+': 'em fase de adequação', 'C': 'baixo nível de adequação'}
    distrib = None
    if dist and dist.get('total'):
        distrib = {'total': dist['total'], 'itens': [{'f': f, 'n': dist['faixas'].get(f, 0), 'w': round(dist['faixas'].get(f, 0) / dist['total'] * 100, 2), 'eh': f == ult['texto']}
                                                     for f in P.FAIXAS_IEGM if dist['faixas'].get(f)]}
        distrib['frase'] = (f"Na {ult['nota'].split(';')[0]}, o município ficou na faixa {ult['texto']} ({leg.get(ult['texto'], '')}), "
                            f"a mesma de {dist['faixas'].get(ult['texto'], 0)} dos {dist['total']} municípios paulistas avaliados.")
    # evolução: edição × dimensão
    evol = []
    for ch, nome in P._IEGM:
        _, sd = _serie(b, ch)
        mp = {v['periodo']: v['texto'] for v in sd}
        evol.append({'l': (lambda r: r[:1].upper() + r[1:])(nome.split('— ')[-1]), 'cells': [mp.get(v['periodo'], '—') for v in s]})
    return {'ult': ult, 'leg': leg, 'dims': dims, 'distrib': distrib, 'evol': evol, 'edicoes': [v['nota'].split(';')[0] for v in s], 'coletado': ult['coletado_em']}

def municipio(b):
    out = []
    for ch in ('mun_populacao', 'mun_pib_per_capita', 'mun_pessoal_ocupado', 'mun_salario_medio', 'mun_esgoto', 'edu_alfabetizacao'):
        m = _ind(b, ch)
        if m:
            out.append({'l': m['nome'], 'v': m['valor_txt'] + (f" {m['unidade']}" if m['formato'] not in ('moeda', 'pct') and m['unidade'] else ''), 'f': f"{m['ult']['periodo']} · {m['fonte']}", 'href': f'/painel/{ch}'})
    return out

def pendentes(b):
    """Gerado do catálogo: indicadores ativos (visíveis) ainda sem dado, com o motivo."""
    return [{'nome': i['nome'], 'motivo': i['pendente'] or 'aguardando a primeira coleta da fonte oficial.'}
            for i in db.todos(b, """SELECT i.* FROM indicadores i WHERE i.visivel AND NOT EXISTS (SELECT 1 FROM indicador_valores v WHERE v.indicador_id=i.id)
                                    ORDER BY array_position(%s::text[], i.tema), i.ordem""", ([t for t, _ in P.TEMAS],))]

def links_tema(b, tema):
    return [{'chave': m['chave'], 'nome': m['nome']} for m in P.painel(b, tema)]

def montar(o, tema):
    hoje = config.hoje()
    b = o['banco']
    d = {'selo': selo(o), 'tema': tema}
    quer = lambda t: tema in ('tudo', t)
    if quer('fin'):
        d['fin'] = financas(o, hoje)
        d['fin_links'] = links_tema(b, 'fin')
    if quer('cont'):
        d['cont'] = contratacoes(o)
    if quer('saude') or quer('edu') or quer('social'):
        fin = d.get('fin') or financas(o, hoje)
        pop = populacao(b)
        porarea = {a['area']: a for a in areas(b, hoje.year)} if fin else {}
    if quer('saude'):
        sm = _ind(b, 'saude_minimo')
        ul = None
        if sm:
            fechados = [x for x in sm['serie'] if not x['parcial'] and x['valor'] is not None]
            ul = fechados[-1] if fechados else None
        k = []
        if ul:
            k.append({'l': f"Aplicado em saúde em {ul['periodo']}", 'v': P.exibir(sm, ul), 'd': 'da receita de impostos; mínimo legal 15%', 'cor': '#C8553D', 'href': '/painel/saude_minimo'})
        a = porarea.get('Saúde')
        if a and a['emp']:
            k.append({'l': f'Saúde empenhada em {hoje.year}', 'v': mi(a['emp']), 'd': f"pago {mi(a['pago'] or 0)}; {pct(a['emp'], a['dot'])} da dotação", 'cor': ESCURO})
            if pop:
                k.append({'l': 'Saúde por habitante', 'v': reais(float(a['emp']) / pop['n']), 'd': _calc(pop), 'cor': '#C8553D'})
        k.append(kpi_ind(_ind(b, 'saude_estabelecimentos'), 'Estabelecimentos no CNES', cor=VERDE))
        d['saude'] = {'kpis': [x for x in k if x], 'minimos': minimos(b, ['saude_minimo']), 'cnes': cnes(o), 'vitais': vitais(b),
                      'orc': orcamento_area(b, hoje.year, 'Saúde'), 'links': links_tema(b, 'saude')}
    if quer('edu'):
        k = []
        for ch, rot, cor in (('edu_mde_minimo', 'Aplicado em educação', '#6B2D5C'), ('edu_fundeb_minimo', 'FUNDEB com profissionais', '#6B2D5C')):
            m = _ind(b, ch)
            if m:
                fech = [x for x in m['serie'] if not x['parcial'] and x['valor'] is not None]
                if fech:
                    k.append({'l': f"{rot} em {fech[-1]['periodo']}", 'v': P.exibir(m, fech[-1]), 'd': m['meta_base_legal'].split(';')[0] if m['meta_base_legal'] else '', 'cor': cor, 'href': f'/painel/{ch}'})
        idb = ideb(o)
        if idb and idb['m']['ult']['valor'] is not None:
            k.append({'l': f"IDEB {idb['per']}, anos iniciais", 'v': idb['m']['valor_txt'],
                      'd': (idb['resp'] or 'rede pública') + ('; ' + '; '.join(f"{c['l']}: {c['v']}" for c in idb['comp']) if idb['comp'] else ''), 'cor': ESCURO, 'href': '/painel/edu_ideb_ai'})
        a = porarea.get('Educação')
        if a and a['emp']:
            k.append({'l': f'Educação empenhada em {hoje.year}', 'v': mi(a['emp']), 'd': (f"{reais(float(a['emp']) / pop['n'])} por habitante; " + _calc(pop)) if pop else f"pago {mi(a['pago'] or 0)}", 'cor': VERDE})
        d['edu'] = {'kpis': k, 'minimos': minimos(b, ['edu_mde_minimo', 'edu_fundeb_minimo']), 'ideb': idb, 'orc': orcamento_area(b, hoje.year, 'Educação'), 'links': links_tema(b, 'edu')}
    if quer('social'):
        k = []
        a = porarea.get('Assistência Social')
        if a and a['emp']:
            k.append({'l': f'Assistência social empenhada, {hoje.year}', 'v': mi(a['emp']), 'd': f"{pct(a['emp'], a['dot'])} da dotação", 'cor': VERDE})
            k.append({'l': 'Já pago pela área social', 'v': mi(a['pago'] or 0), 'd': f"{pct(a['pago'] or 0, a['emp'])} do empenhado", 'cor': ESCURO})
            if pop:
                k.append({'l': 'Área social por habitante', 'v': reais(float(a['emp']) / pop['n']), 'd': _calc(pop), 'cor': VERDE})
        beneficios = [m for m in P.painel(b, 'social')]
        d['social'] = {'kpis': k, 'orc': orcamento_area(b, hoje.year, 'Assistência Social'), 'beneficios': beneficios, 'links': links_tema(b, 'social')}
    if quer('mun'):
        sic = [m for m in P.painel(b, 'mun') if m['chave'].startswith(('gestao_sic', 'gestao_ouv'))]
        d['mun'] = {'iegm': iegm(o), 'municipio': municipio(b), 'sic': sic}
    if tema == 'tudo':
        d['pendentes'] = pendentes(b)
    return d
