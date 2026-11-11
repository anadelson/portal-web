"""Transparência com dados próprios: central, páginas por base (filtros, paginação, totais), CSV/JSON e API /dados.

Cada base é descrita uma vez em BASES; as telas, a exportação e a API leem a mesma descrição."""
import csv, io, json
from datetime import date, datetime
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response, JSONResponse
from . import config, db
from .web import templates, ctx_orgao, br

r = APIRouter(prefix='/_p')
LAI, LRF, L14133 = 'LAI (Lei 12.527/2011)', 'LRF (LC 101/2000)', 'Lei 14.133/2021'
POR_PAGINA = 50
MAX_EXPORT = 50000

# campo: (rótulo, formato)  — formatos: t (texto), m (moeda), d (data), n (número), mes, link
BASES = {
    'receitas': dict(titulo='Receitas', icone='grafico', desc='Previsão e arrecadação por natureza da receita.', tipos=('executivo',),
        legal=f'{LRF}, arts. 48 e 48-A, II; {LAI}, art. 8º, § 1º, II.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)', 'tcesp': 'TCESP — Transparência Municipal (2025)'},
        coletas=['fiorilli:receitas', 'govbr:receitas', 'tcesp:receitas_2025'], ordem='ano DESC, mes, codigo, id',
        colunas=[('ano', 'Ano', 'n'), ('mes', 'Mês', 'mes'), ('codigo', 'Código', 't'), ('nome', 'Receita', 't'), ('fonte_recurso', 'Fonte de recurso', 't'),
                 ('previsto', 'Previsto', 'm'), ('atualizado', 'Previsão atualizada', 'm'), ('arrecadado', 'Arrecadado', 'm')],
        mes='mes', unidade=None, credor=None, texto=['nome', 'codigo', 'fonte_recurso'], totais=['arrecadado'], total_onde='soma',
        nota='Total arrecadado: soma das receitas correntes e de capital, menos as deduções (sem dupla contagem). 2026: Fiorilli acumulado no ano (Mês = acumulado). 2025: TCESP, mês a mês, porque a API da Prefeitura devolve 2025 zerado.'),
    'despesas': dict(titulo='Despesas por unidade', icone='lista', desc='Dotação, empenhado, liquidado e pago por unidade orçamentária.', tipos=('executivo',), tabela='despesas_unidade',
        legal=f'{LRF}, arts. 48 e 48-A, I; {LAI}, art. 8º, § 1º, III.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:despesas_unidade', 'govbr:despesas_unidade'],
        ordem='ano DESC, codigo', colunas=[('codigo', 'Código', 't'), ('unidade', 'Unidade orçamentária', 't'), ('dotacao_atualizada', 'Dotação atualizada', 'm'),
                                          ('empenhado', 'Empenhado', 'm'), ('liquidado', 'Liquidado', 'm'), ('pago', 'Pago', 'm')],
        mes=None, unidade=None, credor=None, texto=['unidade'], totais=['dotacao_atualizada', 'empenhado', 'liquidado', 'pago']),
    'empenhos': dict(titulo='Despesas — empenhos', icone='lista', desc='Cada empenho com credor, unidade, ação, liquidado e pago.', tipos=('executivo',),
        legal=f'{LRF}, art. 48-A, I; {LAI}, art. 8º, § 1º, III; Lei 4.320/1964, arts. 58 a 65.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:empenhos', 'govbr:empenhos'],
        ordem='data DESC NULLS LAST, id DESC', colunas=[('data', 'Data', 'd'), ('numero', 'Empenho', 't'), ('tipo', 'Tipo', 't'), ('credor', 'Credor', 't'), ('credor_cnpj', 'CNPJ', 't'),
                                                     ('unidade', 'Unidade', 't'), ('acao', 'Ação', 't'), ('natureza', 'Natureza', 't'), ('modalidade', 'Modalidade', 't'),
                                                     ('empenhado', 'Empenhado', 'm'), ('liquidado', 'Liquidado', 'm'), ('pago', 'Pago', 'm')],
        mes='data', unidade='unidade', credor='credor', texto=['credor', 'acao', 'programa', 'natureza', 'vinculo_nome', 'numero'], totais=['empenhado', 'liquidado', 'pago'],
        nota='Empenhado já líquido das anulações (linhas do tipo AN aparecem com valor negativo). Pessoa física aparece sem documento.'),
    'licitacoes': dict(titulo='Licitações', icone='proposicoes', desc='Processos de compra do sistema da Prefeitura e publicações no PNCP.', tipos=('executivo',),
        legal=f'{L14133}, arts. 54, 94 e 174; {LAI}, art. 8º, § 1º, IV.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema de compras da Prefeitura (Fiorilli)', 'pncp': 'Portal Nacional de Contratações Públicas (PNCP)'},
        coletas=['fiorilli:licitacoes', 'govbr:licitacoes', 'pncp:licitacoes_pncp'], ordem='data DESC NULLS LAST, id DESC',
        colunas=[('data', 'Data', 'd'), ('numero', 'Processo / nº PNCP', 't'), ('modalidade', 'Modalidade', 't'), ('objeto', 'Objeto', 't'), ('situacao', 'Situação', 't'),
                 ('valor', 'Valor', 'm'), ('fonte', 'Fonte', 'fonte'), ('link', 'Ver', 'link')],
        mes='data', unidade='modalidade', unidade_rotulo='Modalidade', credor=None, texto=['objeto', 'numero', 'situacao'], totais=['valor']),
    'contratos': dict(titulo='Contratos', icone='diario', desc='Contratos publicados, com vigência, valor e execução.', tipos=('executivo',),
        legal=f'{L14133}, arts. 94 e 174; {LAI}, art. 8º, § 1º, IV.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema de compras da Prefeitura (Fiorilli)'}, coletas=['fiorilli:contratos', 'govbr:contratos'],
        ordem='assinatura DESC NULLS LAST, id DESC', colunas=[('assinatura', 'Assinatura', 'd'), ('numero', 'Contrato', 't'), ('fornecedor', 'Contratado', 't'), ('objeto', 'Objeto', 't'),
                                                              ('modalidade', 'Modalidade', 't'), ('inicio', 'Início', 'd'), ('fim', 'Fim', 'd'), ('valor', 'Valor', 'm'), ('empenhado', 'Empenhado', 'm')],
        mes='assinatura', unidade='unidade', credor='fornecedor', texto=['objeto', 'fornecedor', 'numero'], totais=['valor', 'empenhado']),
    'servidores': dict(titulo='Pessoal e remuneração', icone='users', desc='Servidores com cargo, vínculo, lotação e remuneração bruta do mês.', tipos=('executivo',),
        legal=f'{LAI}, art. 8º; STF, ARE 652.777 (Tema 483); LGPD, art. 7º, II e III.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Folha de pagamento (Fiorilli)'}, coletas=['fiorilli:servidores', 'govbr:servidores'],
        ordem='ano DESC, mes DESC, nome', colunas=[('mes', 'Mês', 'mes'), ('nome', 'Nome', 't'), ('cargo', 'Cargo', 't'), ('vinculo', 'Vínculo', 't'), ('lotacao', 'Lotação', 't'),
                                                   ('admissao', 'Admissão', 'd'), ('proventos', 'Remuneração bruta', 'm')],
        mes='mes', unidade='lotacao', unidade_rotulo='Lotação', credor='nome', credor_rotulo='Nome', texto=['nome', 'cargo', 'vinculo', 'lotacao'], totais=['proventos'],
        nota='LGPD: o portal não mostra CPF, descontos pessoais nem valor líquido. Quando houver nome social, ele é usado.'),
    'diarias': dict(titulo='Diárias', icone='relogio', desc='Diárias pagas, com favorecido, cargo, motivo e valor.', tipos=('executivo',),
        legal=f'{LAI}, art. 8º; {LRF}, art. 48-A, I.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:diarias', 'govbr:diarias'],
        ordem='data DESC NULLS LAST, id DESC', colunas=[('data', 'Data', 'd'), ('empenho', 'Empenho', 't'), ('favorecido', 'Favorecido', 't'), ('cargo', 'Cargo', 't'),
                                                       ('unidade', 'Unidade', 't'), ('motivo', 'Motivo', 't'), ('valor', 'Valor', 'm')],
        mes='data', unidade='unidade', credor='favorecido', credor_rotulo='Favorecido', texto=['favorecido', 'motivo', 'cargo'], totais=['valor']),
    'transferencias': dict(titulo='Repasses e transferências', icone='integ', desc='Repasses entre órgãos (ex.: duodécimo da Câmara).', tipos=('executivo', 'legislativo'),
        legal=f'{LRF}, art. 48-A, I; Constituição, art. 168 (duodécimo).', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:transferencias', 'govbr:transferencias'],
        ordem='data DESC NULLS LAST, id DESC', colunas=[('data', 'Data', 'd'), ('mes', 'Mês', 'mes'), ('pagadora', 'Pagadora', 't'), ('recebedora', 'Recebedora', 't'),
                                                       ('previsto', 'Previsto', 'm'), ('repasse', 'Repasse', 'm'), ('devolucao', 'Devolução', 'm')],
        mes='mes', unidade=None, credor='recebedora', credor_rotulo='Recebedora', texto=['pagadora', 'recebedora'], totais=['repasse', 'devolucao']),
    'ordem-cronologica': dict(titulo='Ordem cronológica de pagamentos', icone='sessoes', desc='Pagamentos na ordem de exigibilidade, com justificativa quando há quebra.', tipos=('executivo',), tabela='ordem_cronologica',
        legal=f'{L14133}, art. 141; {LAI}, art. 8º.', fontes={'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:ordem_cronologica'],
        ordem='vencimento DESC NULLS LAST, id DESC', colunas=[('vencimento', 'Exigível em', 'd'), ('pagamento', 'Pago em', 'd'), ('empenho', 'Empenho', 't'), ('fornecedor', 'Fornecedor', 't'),
                                                             ('cnpj', 'CNPJ', 't'), ('lista', 'Lista', 't'), ('unidade', 'Unidade', 't'), ('valor', 'Valor', 'm'), ('justificativa', 'Justificativa', 't')],
        mes='pagamento', unidade='unidade', credor='fornecedor', credor_rotulo='Fornecedor', texto=['fornecedor', 'empenho', 'justificativa'], totais=['valor'],
        nota='Pessoas físicas ficam fora desta lista (LGPD).'),
    'restos-a-pagar': dict(titulo='Restos a pagar', icone='bases', desc='Despesas de anos anteriores ainda a pagar.', tipos=('executivo',), tabela='restos_pagar',
        legal=f'{LRF}, arts. 42 e 48-A; Lei 4.320/1964, art. 36.', fontes={'govbr': 'Portal da transparência (GOVBR)', 'fiorilli': 'Sistema contábil da Prefeitura (Fiorilli)'}, coletas=['fiorilli:restos_pagar', 'govbr:restos_pagar'],
        ordem='ano DESC, credor', colunas=[('codigo', 'Código', 't'), ('credor', 'Credor', 't'), ('empenhado', 'Inscrito', 'm'), ('liquidado', 'Liquidado', 'm'), ('pago', 'Pago', 'm')],
        mes=None, unidade=None, credor='credor', texto=['credor'], totais=['empenhado', 'liquidado', 'pago'], nota='Pessoas físicas ficam fora desta lista (LGPD).'),
    'diarias-camara': dict(titulo='Diárias e verbas dos vereadores', icone='relogio', desc='Diárias, adiantamentos e verbas pagos a vereadores e servidores da Câmara.', tipos=('legislativo',), tabela='diarias_legislativo',
        legal=f'PNTP 2026, critério 20.10; {LAI}, art. 8º; Constituição, art. 37, caput (publicidade).', fontes={'cadastro': 'Secretaria da Câmara (cadastro ou planilha importada)'}, coletas=[],
        ordem='inicio DESC NULLS LAST, id DESC', colunas=[('inicio', 'Início', 'd'), ('fim', 'Fim', 'd'), ('beneficiario', 'Beneficiário', 't'), ('cargo', 'Cargo', 't'), ('destino', 'Destino', 't'),
                                                         ('motivo', 'Motivo', 't'), ('valor', 'Valor', 'm')],
        mes='inicio', unidade='cargo', unidade_rotulo='Cargo', credor='beneficiario', credor_rotulo='Beneficiário', texto=['beneficiario', 'destino', 'motivo'], totais=['valor']),
    'relatorios-fiscais': dict(titulo='Relatórios fiscais (RREO e RGF)', icone='indicadores', desc='Demonstrativos entregues ao Tesouro Nacional (Siconfi).', tipos=('executivo', 'legislativo'), tabela='relatorios_fiscais',
        legal=f'{LRF}, arts. 48, 52 a 55; Constituição, art. 165, § 3º.', fontes={'siconfi': 'Siconfi — Tesouro Nacional'}, coletas=['siconfi:rreo_anexo14', 'siconfi:rgf_anexo01'],
        ordem='ano DESC, demonstrativo, periodo DESC, id', colunas=[('demonstrativo', 'Relatório', 't'), ('anexo', 'Anexo', 't'), ('ano', 'Ano', 'n'), ('periodo', 'Período', 'n'),
                                                                   ('conta', 'Conta', 't'), ('coluna', 'Coluna', 't'), ('valor', 'Valor', 'n')],
        mes=None, unidade='demonstrativo', unidade_rotulo='Relatório', credor=None, texto=['conta', 'coluna', 'rotulo'], totais=[]),
}
for k, v in BASES.items():
    v.setdefault('tabela', k)
MESES = ['acumulado', 'jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

SISTEMAS = ('fiorilli', 'govbr')  # sistemas da transparência: cada órgão usa um; o rótulo mostrado é o do sistema que ele usa

def _fontes_visiveis(fontes, do_orgao):
    vis = {k: v for k, v in fontes.items() if k not in SISTEMAS or k in do_orgao}
    return vis or {k: v for k, v in fontes.items() if k != 'govbr'}

def bases_do(o):
    do_orgao = {f['fonte'] for f in db.todos(db.PLATAFORMA, 'SELECT fonte FROM fontes WHERE orgao_id=%s', (o['id'],))} if o.get('id') else set()
    return {k: dict(v, fontes=_fontes_visiveis(v['fontes'], do_orgao)) for k, v in BASES.items() if o['tipo'] in v['tipos']}

def _base(request, nome):
    o = request.state.orgao
    b = bases_do(o).get(nome)
    if not b:
        raise HTTPException(404, 'Base não disponível neste portal.')
    return o, b

def filtros(b, q):
    """Monta o WHERE a partir dos filtros da URL (ano, mes, unidade, credor, texto). Tudo parametrizado."""
    w, p, f = [], [], {}
    try:
        f['ano'] = int(q.get('ano')) if q.get('ano') else None
    except ValueError:
        f['ano'] = None
    if f['ano']:
        w.append('ano=%s'); p.append(f['ano'])
    try:
        f['mes'] = int(q.get('mes')) if q.get('mes') not in (None, '') else None
    except ValueError:
        f['mes'] = None
    if f['mes'] is not None and b.get('mes'):
        if b['mes'] == 'mes':
            w.append('mes=%s')
        else:
            w.append(f"extract(month from {b['mes']})=%s")
        p.append(f['mes'])
    for chave_, col in (('unidade', b.get('unidade')), ('credor', b.get('credor'))):
        v = (q.get(chave_) or '').strip()[:120]
        f[chave_] = v
        if v and col:
            w.append(f'{col} ILIKE %s'); p.append(f'%{v}%')
    t = (q.get('q') or '').strip()[:120]
    f['q'] = t
    if t and b['texto']:
        w.append('(' + ' OR '.join(f"coalesce({c}::text,'') ILIKE %s" for c in b['texto']) + ')'); p += [f'%{t}%'] * len(b['texto'])
    return (' WHERE ' + ' AND '.join(w)) if w else '', p, f

def situacao(o, b):
    """Data da última coleta válida e, se a última tentativa falhou, o aviso."""
    tab = b['tabela']
    atualizado = db.um(o['banco'], f'SELECT max(coletado_em) t, count(*) n FROM {tab}')
    ult = db.um(db.PLATAFORMA, 'SELECT * FROM coletas WHERE orgao_slug=%s AND fonte = ANY(%s) ORDER BY id DESC LIMIT 1', (o['slug'], b['coletas'])) if b['coletas'] else None
    return {'atualizado': atualizado['t'], 'n': atualizado['n'], 'falhou': ult if ult and not ult['ok'] else None}

def consulta(o, b, q, limite=POR_PAGINA, pagina=1):
    tab = b['tabela']
    where, p, f = filtros(b, q)
    cols = [c[0] for c in b['colunas']] + (['fonte'] if 'fonte' not in [c[0] for c in b['colunas']] else [])
    n = db.um(o['banco'], f'SELECT count(*) n FROM {tab}{where}', p)['n']
    tot = {}
    if b['totais']:
        cond = where + ((' AND ' if where else ' WHERE ') + b['total_onde'] if b.get('total_onde') else '')
        tot = db.um(o['banco'], f"SELECT {', '.join(f'sum({c}) {c}' for c in b['totais'])} FROM {tab}{cond}", p)
    linhas = db.todos(o['banco'], f"SELECT {', '.join(dict.fromkeys(cols))}, coletado_em FROM {tab}{where} ORDER BY {b['ordem']} LIMIT %s OFFSET %s", p + [limite, (pagina - 1) * limite])
    return linhas, n, tot, f

def opcoes(o, b):
    anos = [x['ano'] for x in db.todos(o['banco'], f"SELECT DISTINCT ano FROM {b['tabela']} ORDER BY ano DESC")]
    uni = [x['v'] for x in db.todos(o['banco'], f"SELECT DISTINCT {b['unidade']} v FROM {b['tabela']} WHERE coalesce({b['unidade']},'')<>'' ORDER BY 1 LIMIT 200")] if b.get('unidade') else []
    return anos, uni

# ---------- telas ----------
@r.get('/transparencia')
def central(request: Request):
    ctx = ctx_orgao(request); o = ctx['orgao']
    cards = []
    for k, b in bases_do(o).items():
        cards.append(dict(chave=k, **{x: b[x] for x in ('titulo', 'icone', 'desc')}, **situacao(o, b)))
    fin = db.cfg(o['banco'], 'financas', {}) if o['tipo'] == 'legislativo' else None
    return templates.TemplateResponse(request, 'portal/transparencia.html', dict(ctx, cards=cards, fin=fin, legal='transparencia'))

def _export_resp(o, b, nome, q, formato):
    linhas, n, tot, f = consulta(o, b, q, limite=MAX_EXPORT)
    st = situacao(o, b)
    campos = [c[0] for c in b['colunas'] if c[2] != 'link'] + (['link'] if any(c[2] == 'link' for c in b['colunas']) else [])
    if 'fonte' not in campos:
        campos.append('fonte')
    def val(v):
        if isinstance(v, Decimal):
            return float(v)
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        return v
    regs = [{c: val(l.get(c)) for c in campos} for l in linhas]
    if formato == 'json':
        corpo = {'base': nome, 'titulo': b['titulo'], 'orgao': o['nome'], 'fontes': b['fontes'], 'base_legal': b['legal'],
                 'atualizado_em': val(st['atualizado']), 'filtros': {k: v for k, v in f.items() if v not in (None, '')},
                 'total_registros': n, 'registros_nesta_resposta': len(regs), 'limite': MAX_EXPORT,
                 'totais': {k: val(v) for k, v in (tot or {}).items()}, 'campos': {c[0]: c[1] for c in b['colunas']}, 'registros': regs}
        return JSONResponse(corpo, headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=300'})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(campos)
    for x in regs:
        w.writerow(['' if x[c] is None else x[c] for c in campos])
    return Response('﻿' + buf.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{o["slug"]}-{nome}.csv"', 'Cache-Control': 'public, max-age=300'})

@r.get('/transparencia/{nome}.csv')
def exportar_csv(request: Request, nome: str):
    o, b = _base(request, nome)
    return _export_resp(o, b, nome, request.query_params, 'csv')

@r.get('/transparencia/{nome}.json')
def exportar_json(request: Request, nome: str):
    o, b = _base(request, nome)
    return _export_resp(o, b, nome, request.query_params, 'json')

@r.get('/dados/{nome}.json')
def api(request: Request, nome: str):
    o, b = _base(request, nome)
    return _export_resp(o, b, nome, request.query_params, 'json')

@r.get('/transparencia/{nome}')
def pagina(request: Request, nome: str, pagina: int = 1):
    ctx = ctx_orgao(request); o, b = _base(request, nome)
    pagina = max(1, min(pagina, 10000))
    linhas, n, tot, f = consulta(o, b, request.query_params, pagina=pagina)
    anos, uni = opcoes(o, b)
    from urllib.parse import urlencode
    qs = urlencode({k: v for k, v in request.query_params.items() if k != 'pagina' and v})
    return templates.TemplateResponse(request, 'portal/base_dados.html', dict(ctx, nome=nome, b=b, linhas=linhas, n=n, tot=tot or {}, f=f, anos=anos, uni=uni,
        pagina=pagina, paginas=max(1, -(-n // POR_PAGINA)), qs=qs, st=situacao(o, b), meses=MESES, legal_txt=b['legal']))

@r.get('/dados-abertos')
def dados_abertos(request: Request):
    ctx = ctx_orgao(request); o = ctx['orgao']
    bs = [dict(chave=k, **b, **situacao(o, b)) for k, b in bases_do(o).items()]
    from .portal_painel import blocos_dados_abertos
    inds = blocos_dados_abertos(o) if ctx['mods'].get('bi') else []
    return templates.TemplateResponse(request, 'portal/dados_abertos.html', dict(ctx, bases=bs, inds=inds, legal_txt=f'{LAI}, art. 8º, § 3º, II e III; Decreto 8.777/2016 (Política de Dados Abertos).'))
