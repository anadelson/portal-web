"""Coletores do painel de indicadores (módulo "bi").

Fontes (tabela `fontes`, uma linha por órgão; parâmetro comum: ibge = código de 7 dígitos):
  ibge   — IBGE: estimativas da população (agregados v3), PIB per capita, CEMPRE, Censo 2022 e IDEB (API de pesquisas v1),
           nascidos vivos e óbitos (SIDRA). Dados nacionais: gravados por código IBGE em `indicadores_publicos`.
  cnes   — CNES: estabelecimentos de saúde do município, por tipo (só estabelecimentos; nunca a lista de profissionais).
  mds    — MDS MI Social: Bolsa Família, Cadastro Único e BPC, só totais. Desligado enquanto a fonte estiver fora do ar.
  pni    — Vacinação: conector desligado ("pendente de fonte estável").
  painel — números do próprio órgão (receita, despesa, PNCP, e-SIC/Ouvidoria) e os mínimos de saúde, educação e FUNDEB
           do Siconfi (RREO Anexo 14).
Cada função `ler_*` só lê a fonte e devolve valores; a gravação é separada (permite conferir sem gravar)."""
import re
from datetime import date, timedelta
from .. import config, db
from .. import painel as P
from .comum import buscar, num

IBGE_V1 = 'https://servicodados.ibge.gov.br/api/v1/pesquisas/'
IBGE_V3 = 'https://servicodados.ibge.gov.br/api/v3/agregados/'
SIDRA = 'https://apisidra.ibge.gov.br/values/'
CNES = 'https://apidadosabertos.saude.gov.br/cnes/'
SICONFI = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo'

class Desligado(Exception):
    pass

def _v(x):
    """Valor numérico das APIs do IBGE; '-', '...', 'X' e vazios ficam de fora (sem número divulgado)."""
    if x is None:
        return None
    s = str(x).strip()
    if not s or not re.match(r'^-?\d', s):
        return None
    return float(s)

def _ano(a):
    return int(str(a)[:4])

# ---------- IBGE ----------
# indicador -> (tipo, parâmetros). Códigos oficiais das APIs do IBGE; valem para qualquer município.
IBGE_SPECS = {
    'mun_populacao': ('agregado', {'agregado': 6579, 'variavel': 9324, 'periodos': '-10'}),
    'mun_pib_per_capita': ('pesquisa', {'pesquisa': 38, 'indicador': 47001}),
    'mun_pessoal_ocupado': ('pesquisa', {'pesquisa': 19, 'indicador': 143514, 'ultima_versao': True}),
    'mun_salario_medio': ('pesquisa', {'pesquisa': 19, 'indicador': 143558, 'ultima_versao': True}),
    'mun_esgoto': ('pesquisa', {'pesquisa': 10101, 'indicador': 105286, 'periodos': '2022'}),
    'edu_alfabetizacao': ('pesquisa', {'pesquisa': 10101, 'indicador': 111628, 'periodos': '2022'}),
    'saude_nascidos': ('sidra', {'tabela': 2612, 'variavel': 'Nascidos vivos ocorridos no ano', 'ultimos': 10}),
    'saude_obitos': ('sidra', {'tabela': 2654, 'variavel': 'Número de óbitos ocorridos no ano', 'ultimos': 10}),
}
CENSO = {'mun_populacao': {'agregado': 4709, 'variavel': 93, 'periodo': 2022}}  # nos anos de Censo não há estimativa

def _periodos_ultima_versao(pesquisa):
    """A API de pesquisas só aceita, numa consulta, períodos da mesma versão: usa os da versão mais recente."""
    pers = buscar('ibge', f'{IBGE_V1}{pesquisa}/periodos')
    v = max(p['versao'] for p in pers)
    return '|'.join(p['periodo'] for p in pers if p['versao'] == v)

def ler_ibge(ibge, so=None):
    """Devolve [(chave, periodo, data_ref, valor, nota)] de todos os indicadores do IBGE (ou só dos indicados)."""
    out, erros = [], []
    for chave, (tipo, s) in IBGE_SPECS.items():
        if so and chave not in so:
            continue
        try:
            if tipo == 'agregado':
                d = buscar('ibge', f"{IBGE_V3}{s['agregado']}/periodos/{s['periodos']}/variaveis/{s['variavel']}?localidades=N6[{ibge}]")
                serie = d[0]['resultados'][0]['series'][0]['serie'] if d else {}
                for a, v in serie.items():
                    if _v(v) is not None:
                        out.append((chave, str(a), P.fim_do_ano(a), _v(v), 'estimativa em 1º de julho'))
                c = CENSO.get(chave)
                if c:
                    d = buscar('ibge', f"{IBGE_V3}{c['agregado']}/periodos/{c['periodo']}/variaveis/{c['variavel']}?localidades=N6[{ibge}]")
                    for a, v in (d[0]['resultados'][0]['series'][0]['serie'] if d else {}).items():
                        if _v(v) is not None:
                            out.append((chave, str(a), P.fim_do_ano(a), _v(v), f'Censo Demográfico {a} (contagem)'))
            elif tipo == 'pesquisa':
                pers = _periodos_ultima_versao(s['pesquisa']) if s.get('ultima_versao') else s.get('periodos', 'all')
                d = buscar('ibge', f"{IBGE_V1}{s['pesquisa']}/periodos/{pers}/indicadores/{s['indicador']}/resultados/{ibge}")
                res = d[0]['res'][0]['res'] if d and d[0].get('res') else {}
                for a, v in res.items():
                    if _v(v) is not None:
                        out.append((chave, str(a), P.fim_do_ano(_ano(a)), _v(v), ''))
            elif tipo == 'sidra':
                d = buscar('ibge', f"{SIDRA}t/{s['tabela']}/n6/{ibge}/v/all/p/last%20{s['ultimos']}")
                for l in d[1:]:
                    if l.get('D2N') != s['variavel']:
                        continue
                    v = l.get('V')
                    if v == '-':  # SIDRA: '-' é zero absoluto
                        v = '0'
                    if _v(v) is not None:
                        out.append((chave, str(l['D3C']), P.fim_do_ano(l['D3C']), _v(v), 'ocorridos no ano, registrados em cartório'))
        except Exception as e:
            erros.append(f'{chave}: {type(e).__name__}')
    return out, erros

# ---------- CNES ----------
def ler_cnes(ibge, hoje=None):
    hoje = hoje or config.hoje()
    tipos = {t['codigo_tipo_unidade']: t['descricao_tipo_unidade'].capitalize() for t in buscar('cnes', CNES + 'tipounidades').get('tipos_unidade', [])}
    estab, off = [], 0
    while True:
        d = buscar('cnes', CNES + 'estabelecimentos', {'codigo_municipio': str(ibge)[:6], 'limit': 20, 'offset': off})
        lote = d.get('estabelecimentos', []) if isinstance(d, dict) else []
        estab += lote
        if len(lote) < 20 or off > 2000:
            break
        off += 20
    cont = {}
    for e in estab:
        t = tipos.get(e.get('codigo_tipo_unidade'), f"Tipo {e.get('codigo_tipo_unidade')}")
        cont[t] = cont.get(t, 0) + 1
    det = [[t, n] for t, n in sorted(cont.items(), key=lambda x: (-x[1], x[0]))]
    ler_cnes.ultima_lista = lista_cnes(estab, tipos)
    return [('saude_estabelecimentos', P.rotulo_mes(hoje), P.fim_do_mes(hoje.year, hoje.month), len(estab), 'cadastro vigente na data da coleta', det)]

def lista_cnes(estab, tipos):
    """Só dados institucionais do estabelecimento (nome, tipo, endereço, código CNES). Nunca a lista de profissionais."""
    def t(v):
        return re.sub(r'\s+', ' ', str(v or '')).strip()
    out = []
    for e in estab:
        end = ', '.join(x for x in (t(e.get('endereco_estabelecimento')).title(), t(e.get('numero_estabelecimento')), t(e.get('bairro_estabelecimento')).title()) if x and x not in ('0', 'S/N'))
        out.append({'cnes': t(e.get('codigo_cnes')), 'nome': t(e.get('nome_fantasia') or e.get('nome_razao_social')).title(),
                    'tipo': tipos.get(e.get('codigo_tipo_unidade'), ''), 'endereco': end})
    return sorted(out, key=lambda x: x['nome'])

# ---------- MDS (MI Social) ----------
MDS_PADRAO = {'url': 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial/',
              # nomes dos campos do serviço Solr (a confirmar quando o serviço voltar); campo vazio = indicador não coletado
              'campos': {'social_bf_familias': 'qtd_familias_beneficiarias_bolsa_familia_s', 'social_bf_valor': 'valor_repassado_bolsa_familia_s',
                         'social_cadunico_familias': '', 'social_bpc': ''}}

def ler_mds(ibge, p):
    conf = {**MDS_PADRAO, **{k: v for k, v in p.items() if k in ('url', 'campos')}}
    campos = {k: v for k, v in conf['campos'].items() if v}
    d = buscar('mds', conf['url'], {'q': '*:*', 'fq': f'codigo_ibge:{str(ibge)[:6]}', 'fl': ','.join(['codigo_ibge', 'anomes_s'] + list(campos.values())),
                                     'sort': 'anomes_s desc', 'rows': 24, 'wt': 'json'})
    docs = (d.get('response') or {}).get('docs', []) if isinstance(d, dict) else []
    out = []
    for doc in docs:
        am = str(doc.get('anomes_s', ''))
        if not re.match(r'^\d{6}$', am):
            continue
        a, m = int(am[:4]), int(am[4:])
        for chave, campo in campos.items():
            v = num(doc.get(campo))
            if v is not None:
                out.append((chave, f'{P.MESES[m - 1]}/{a}', P.fim_do_mes(a, m), v, ''))
    if not out:
        raise ValueError('a fonte respondeu sem os campos esperados (confirme os nomes dos campos)')
    return out

# ---------- Siconfi: mínimos constitucionais (RREO Anexo 14) ----------
MINIMOS = {'saude_minimo': 'AplicacaoTotalDasDespesasComAcoesEServicosPublicosDeSaude',
           'edu_mde_minimo': 'MinimoAnualDasReceitasDeImpostosNaManutencaoEDesenvolvimento',
           'edu_fundeb_minimo': 'MinimoAnualDoFUNDEBNaRemuneracao'}

def _rreo(ibge, ano, per):
    d = buscar('siconfi', SICONFI, {'an_exercicio': ano, 'nr_periodo': per, 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': ibge})
    return d.get('items', []) if isinstance(d, dict) else []

def _aplicado(itens, prefixo):
    for i in itens:
        if (i.get('cod_conta') or '').startswith(prefixo) and (i.get('coluna') or '').startswith('% Aplicado') and i.get('valor') is not None:
            return float(i['valor'])
    return None

def ler_minimos(ibge, anos, hoje=None):
    """Para cada ano, o último bimestre em que cada mínimo foi declarado. 6º bimestre = ano completo."""
    hoje = hoje or config.hoje()
    out = []
    for ano in anos:
        faltam = set(MINIMOS)
        for per in range(6, 0, -1):
            if not faltam:
                break
            if ano == hoje.year and per * 2 > hoje.month:
                continue
            itens = _rreo(ibge, ano, per)
            for chave in list(faltam):
                v = _aplicado(itens, MINIMOS[chave])
                if v is not None:
                    faltam.discard(chave)
                    parcial = per < 6
                    out.append((chave, str(ano), P.fim_do_mes(ano, per * 2), v, f'RREO do {per}º bimestre' + (' (acumulado até o bimestre)' if parcial else ' (ano completo)'), parcial))
    return out

# ---------- dados do próprio órgão ----------
CONT = ('cont_publicadas', 'cont_valor', 'cont_dispensa')

def anos_pncp_completos(b, ano):
    """Anos do PNCP lidos por inteiro. A busca vem da publicação mais recente para a mais antiga e o PNCP às vezes
    derruba a conexão no meio: um ano só está completo se o banco já tem publicações do ano anterior a ele."""
    r = db.um(b, "SELECT min(ano) a FROM licitacoes WHERE fonte='pncp' AND ano BETWEEN 2000 AND %s", (ano,))
    return list(range(r['a'] + 1, ano + 1)) if r and r['a'] else []

def ler_proprios(o, hoje=None):
    hoje = hoje or config.hoje()
    b, ano, out = o['banco'], hoje.year, []
    r = db.um(b, "SELECT sum(arrecadado) a, sum(coalesce(atualizado, previsto)) p, max(coletado_em) t FROM receitas WHERE fonte='fiorilli' AND ano=%s AND soma", (ano,))
    if r and r['a'] is not None:
        dt = r['t'].date() if r['t'] else hoje
        out.append(('fin_receita', str(ano), dt, float(r['a']), f'acumulado de 1º/01 a {dt.strftime("%d/%m/%Y")}', True, None))
        if r['p']:
            out.append(('fin_receita_prevista', str(ano), dt, float(r['a']) / float(r['p']) * 100, f'arrecadado até {dt.strftime("%d/%m/%Y")} sobre a previsão do ano', True, None))
    for x in db.todos(b, "SELECT ano, sum(arrecadado) a, count(DISTINCT mes) m FROM receitas WHERE fonte='tcesp' AND ano < %s AND soma GROUP BY ano", (ano,)):
        if x['m'] == 12 and x['a'] is not None:
            out.append(('fin_receita', str(x['ano']), P.fim_do_ano(x['ano']), float(x['a']), 'ano completo (TCESP — Transparência Municipal)', False, None))
    d = db.um(b, 'SELECT sum(dotacao_atualizada) d, sum(empenhado) e, sum(pago) p, max(coletado_em) t FROM despesas_unidade WHERE ano=%s', (ano,))
    if d and d['p'] is not None:
        dt = d['t'].date() if d['t'] else hoje
        out.append(('fin_despesa_paga', str(ano), dt, float(d['p']), f'acumulado de 1º/01 a {dt.strftime("%d/%m/%Y")}', True, None))
        if d['d']:
            out.append(('fin_empenhada_dotacao', str(ano), dt, float(d['e'] or 0) / float(d['d']) * 100, f'empenhado até {dt.strftime("%d/%m/%Y")} sobre a dotação atualizada', True, None))
    for x in db.todos(b, """SELECT ano, count(*) n, sum(valor) v, count(valor) nv, count(*) FILTER (WHERE modalidade ILIKE 'Dispensa%%') nd
                            FROM licitacoes WHERE fonte='pncp' AND ano = ANY(%s) GROUP BY ano ORDER BY ano""", (anos_pncp_completos(b, ano),)):
        mods = db.todos(b, "SELECT coalesce(nullif(modalidade,''),'Não informada') m, count(*) n, sum(valor) v FROM licitacoes WHERE fonte='pncp' AND ano=%s GROUP BY 1 ORDER BY 2 DESC, 1", (x['ano'],))
        parcial = x['ano'] == ano
        dt = hoje if parcial else P.fim_do_ano(x['ano'])
        nota = f"publicadas até {hoje.strftime('%d/%m/%Y')}" if parcial else 'ano completo'
        out.append(('cont_publicadas', str(x['ano']), dt, x['n'], nota, parcial, [[m['m'], m['n']] for m in mods]))
        out.append(('cont_dispensa', str(x['ano']), dt, x['nd'] / x['n'] * 100, nota, parcial, None))
        if x['nv']:
            sem = x['n'] - x['nv']
            out.append(('cont_valor', str(x['ano']), dt, float(x['v']), nota + (f'; {sem} publicação(ões) sem valor informado' if sem else ''), parcial,
                        [[m['m'], float(m['v'] or 0)] for m in mods]))
    for x in db.todos(b, """SELECT extract(year FROM recebido)::int ano, count(*) FILTER (WHERE tipo='pedido') ped, count(*) FILTER (WHERE tipo<>'pedido') man,
                            count(*) FILTER (WHERE tipo='pedido' AND respondido IS NOT NULL) resp,
                            count(*) FILTER (WHERE tipo='pedido' AND respondido IS NOT NULL AND respondido - recebido <= CASE WHEN justificativa<>'' THEN 30 ELSE 20 END) prazo,
                            avg(respondido - recebido) FILTER (WHERE tipo='pedido' AND respondido IS NOT NULL) media
                            FROM esic WHERE recebido <= %s GROUP BY 1 ORDER BY 1""", (hoje,)):
        parcial = x['ano'] == ano
        dt = hoje if parcial else P.fim_do_ano(x['ano'])
        nota = f"até {hoje.strftime('%d/%m/%Y')}" if parcial else 'ano completo'
        if x['ped']:
            out.append(('gestao_sic_pedidos', str(x['ano']), dt, x['ped'], nota, parcial, None))
        if x['man']:
            out.append(('gestao_ouv_manifestacoes', str(x['ano']), dt, x['man'], nota, parcial, None))
        if x['resp'] >= P.SUPRESSAO:  # percentuais e médias de bases pequenas não são publicados (LGPD)
            out.append(('gestao_sic_no_prazo', str(x['ano']), dt, x['prazo'] / x['resp'] * 100, f"{nota}; {x['resp']} pedidos respondidos", parcial, None))
            out.append(('gestao_sic_prazo_medio', str(x['ano']), dt, float(x['media']), f"{nota}; {x['resp']} pedidos respondidos", parcial, None))
    return out

# ---------- coleta (chamada pelo worker e pelo botão "coletar agora") ----------
def _chaves(coletor):
    return [c['chave'] for c in P.CATALOGO if c['coletor'] == coletor]

def coletar_ibge(o, p, hoje=None):
    ibge = p.get('ibge') or o['ibge']
    vals, erros = ler_ibge(ibge)
    for chave, per, dref, v, nota in vals:
        P.gravar_publico(ibge, chave, per, dref, 'ibge', v, nota=nota)
    n = P.copiar_publicos(o['banco'], ibge, _chaves('ibge'))
    ok = bool(vals)
    msg = f'{len(vals)} valores de {len({v[0] for v in vals})} indicadores' + (f'; sem resposta: {", ".join(erros)}' if erros else '')
    falharam = {e.split(':')[0] for e in erros}
    P.marcar_coleta(o['banco'], 'ibge', True, msg, [c for c in _chaves('ibge') if c not in falharam])
    if falharam:
        P.marcar_coleta(o['banco'], 'ibge', False, msg, list(falharam))
    return [('indicadores', ok, n, msg)]

def coletar_cnes(o, p, hoje=None):
    ibge = p.get('ibge') or o['ibge']
    try:
        vals = ler_cnes(ibge, hoje)
    except Exception as e:
        P.marcar_coleta(o['banco'], 'cnes', False, f'{type(e).__name__}')
        raise
    for chave, per, dref, v, nota, det in vals:
        P.gravar_publico(ibge, chave, per, dref, 'cnes', v, detalhe=det, nota=nota)
    from .comum import guardar_publico
    guardar_publico(ibge, 'cnes_lista', 'atual', {'competencia': vals[0][1], 'estabelecimentos': getattr(ler_cnes, 'ultima_lista', [])})
    n = P.copiar_publicos(o['banco'], ibge, _chaves('cnes'))
    P.marcar_coleta(o['banco'], 'cnes', True, f'{vals[0][3]:.0f} estabelecimentos')
    return [('estabelecimentos', True, n, f'{vals[0][3]:.0f} estabelecimentos no CNES')]

def coletar_mds(o, p, hoje=None):
    ibge = p.get('ibge') or o['ibge']
    try:
        vals = ler_mds(ibge, p)
    except Exception as e:
        P.marcar_coleta(o['banco'], 'mds', False, f'{type(e).__name__}: {str(e)[:120]}')
        raise
    for chave, per, dref, v, nota in vals:
        P.gravar_publico(ibge, chave, per, dref, 'mds', v, nota=nota)
    n = P.copiar_publicos(o['banco'], ibge, _chaves('mds'))
    P.marcar_coleta(o['banco'], 'mds', True, f'{len(vals)} valores')
    return [('assistencia_social', True, n, f'{len(vals)} valores mensais')]

def coletar_pni(o, p, hoje=None):
    P.marcar_coleta(o['banco'], 'pni', False, 'conector desligado: pendente de fonte estável')
    raise Desligado('Vacinação (PNI): pendente de fonte estável — a API não filtra por município e devolve registros individuais.')

def coletar_painel(o, p, hoje=None):
    """Números do próprio órgão (a cada hora) e mínimos do Siconfi (no máximo uma consulta por dia; anos fechados só uma vez)."""
    hoje = hoje or config.hoje()
    ibge = p.get('ibge') or o['ibge']
    res = []
    vals = ler_proprios(o, hoje)
    for chave, per, dref, v, nota, parcial, det in vals:
        P.gravar(o['banco'], chave, per, dref, v, detalhe=det, nota=nota, parcial=parcial)
    # anos do PNCP que deixaram de estar cobertos por inteiro (ou nunca estiveram) não ficam publicados
    db.exe(o['banco'], """DELETE FROM indicador_valores v USING indicadores i WHERE i.id=v.indicador_id AND i.chave = ANY(%s)
                          AND v.origem='coletor' AND NOT (v.periodo = ANY(%s))""", (list(CONT), [str(a) for a in anos_pncp_completos(o['banco'], hoje.year)]))
    proprios = sorted({c for c in _chaves('painel') if c not in MINIMOS})
    P.marcar_coleta(o['banco'], 'painel', True, f'{len(vals)} valores', proprios)
    res.append(('proprios', True, len(vals), f'{len(vals)} valores de receita, despesa, PNCP e e-SIC'))
    anos = int(p.get('anos_minimos', 5))
    feitos = {(x['indicador'], x['periodo']) for x in db.todos(db.PLATAFORMA, "SELECT indicador, periodo FROM indicadores_publicos WHERE ibge=%s AND fonte='siconfi' AND NOT parcial", (str(ibge),))}
    # no máximo uma consulta ao Siconfi por dia (anos fechados já gravados não são pedidos de novo; anos sem os mínimos
    # no Anexo 14 — ex.: 2022 e 2023 em Borá — ficam em branco e são tentados de novo só no dia seguinte)
    ult = db.cfg(o['banco'], 'painel_siconfi_consulta')
    pedir = []
    if not ult or ult < (config.agora() - timedelta(hours=20)).isoformat():
        pedir = [a for a in range(hoje.year - anos, hoje.year) if not all((k, str(a)) in feitos for k in MINIMOS)] + [hoje.year]
    if pedir:
        try:
            mins = ler_minimos(ibge, pedir, hoje)
            for chave, per, dref, v, nota, parcial in mins:
                P.gravar_publico(ibge, chave, per, dref, 'siconfi', v, nota=nota, parcial=parcial)
            db.set_cfg(o['banco'], 'painel_siconfi_consulta', config.agora().isoformat())
            P.marcar_coleta(o['banco'], 'painel', True, f'Siconfi: {len(mins)} valores', list(MINIMOS))
            res.append(('minimos_siconfi', True, len(mins), f"mínimos de saúde, educação e FUNDEB: {len(mins)} valores ({', '.join(map(str, pedir))})"))
        except Exception as e:
            P.marcar_coleta(o['banco'], 'painel', False, f'Siconfi: {type(e).__name__}', list(MINIMOS))
            res.append(('minimos_siconfi', False, 0, f'Siconfi: {type(e).__name__}: {str(e)[:150]}'))
    P.copiar_publicos(o['banco'], ibge, list(MINIMOS))
    return res

from .inep_iegm import coletar_inep, coletar_iegm
from . import financas as _financas
COLETORES = {'ibge': coletar_ibge, 'cnes': coletar_cnes, 'mds': coletar_mds, 'pni': coletar_pni, 'painel': coletar_painel, 'inep': coletar_inep, 'iegm': coletar_iegm,
             'financas': _financas.coletar}

class _Modulo:
    """Adaptador para o worker (MODULOS[fonte].coletar(o, p))."""
    def __init__(self, f):
        self.coletar = f

MODULOS = {k: _Modulo(f) for k, f in COLETORES.items()}
