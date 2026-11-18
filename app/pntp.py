"""Autoavaliação PNTP (Programa Nacional de Transparência Pública, Atricon) — matriz inteira, Prefeitura e Câmara (18/11/2026).

A matriz oficial do ciclo (critérios, classificação e itens de verificação aplicáveis) fica em pntp_matriz_2026.json,
gerado da planilha "Matriz de Critérios 2026 (Final)" da Atricon. O cálculo segue a Cartilha PNTP 2026, seção III:
- peso da dimensão (4, 3, 2 ou 1); dentro da dimensão, os critérios dividem o peso dela conforme a classificação
  (essencial 2, obrigatório 1,5, recomendado 1);
- itens de verificação: disponibilidade 30%, atualidade 30%, série histórica 20%, gravação de relatórios 10% e
  filtro de pesquisa 10%; o item que não se aplica tem o percentual rateado entre os demais;
- disponibilidade não atendida zera o critério inteiro;
- Diamante (≥ 95%), Ouro (≥ 85%) e Prata (≥ 75%) exigem 100% dos critérios essenciais; sem eles, "Elevado".

Cada critério é avaliado de um de dois jeitos:
- automático: o portal mede sozinho, com os dados publicados (pntp_auto.py);
- marcação: o controle interno marca, item a item, com o link da evidência (tabela pntp_marcacoes). Marcação com mais
  de 30 dias não conta a atualidade (ela vale "na data da consulta").
Sem marcação, o critério conta zero: nada é dado como atendido sem evidência. É uma ESTIMATIVA interna; a nota oficial
é a do sistema Avalia da Atricon, depois da validação do Tribunal de Contas."""
import json
from datetime import timedelta
from pathlib import Path
from . import config, db

MATRIZ = json.loads((Path(__file__).parent / 'pntp_matriz_2026.json').read_text(encoding='utf-8'))
CICLO = MATRIZ['ciclo']
ITENS = ['disponibilidade', 'atualidade', 'serie', 'gravacao', 'filtro']
NOME_ITEM = {'disponibilidade': 'Disponibilidade', 'atualidade': 'Atualidade', 'serie': 'Série histórica', 'gravacao': 'Gravação de relatórios', 'filtro': 'Filtro de pesquisa'}
SIGLA_ITEM = {'disponibilidade': 'D', 'atualidade': 'A', 'serie': 'S', 'gravacao': 'G', 'filtro': 'F'}
PESO_ITEM = MATRIZ['pesos_itens']
PESO_CLASSE = MATRIZ['pesos_classe']
PESO_DIM = {d['nome']: d['peso'] for d in MATRIZ['dimensoes']}
NOME_CLASSE = {'essencial': 'Essencial', 'obrigatorio': 'Obrigatório', 'recomendado': 'Recomendado'}
VALIDADE_MARCACAO = 30  # dias: a atualidade marcada à mão só vale por 30 dias (regra geral da cartilha)
AVALIA = 'https://avalia.atricon.org.br'
RADAR = 'https://radardatransparencia.atricon.org.br'


def criterios(tipo):
    """Critérios do PNTP que valem para o tipo de órgão ('executivo' ou 'legislativo'), na ordem da matriz."""
    return [c for c in MATRIZ['criterios'] if tipo in c['aplica']]


def por_id(cid):
    return next((c for c in MATRIZ['criterios'] if c['id'] == cid), None)


def aplicaveis(c):
    return [i for i in ITENS if c['itens'][i]]


def nota(c, itens):
    """Fração (0 a 1) do critério: soma dos pesos dos itens atendidos sobre a soma dos aplicáveis; sem disponibilidade, 0."""
    if not itens or not itens.get('disponibilidade'):
        return 0.0
    ap = aplicaveis(c)
    total = sum(PESO_ITEM[i] for i in ap)
    return sum(PESO_ITEM[i] for i in ap if itens.get(i)) / total


def nivel(indice, essenciais_ok):
    """Nível de transparência da Tabela 3 da cartilha."""
    if indice >= 75:
        if not essenciais_ok:
            return 'Elevado'
        return 'Diamante' if indice >= 95 else 'Ouro' if indice >= 85 else 'Prata'
    if indice >= 50:
        return 'Intermediário'
    if indice >= 30:
        return 'Básico'
    return 'Inicial' if indice > 0 else 'Inexistente'


def indice(avaliacoes, tipo):
    """avaliacoes: {id: {'itens': {...}}}. Devolve (índice 0–100, {dimensão: % da dimensão})."""
    dims = {}
    for c in criterios(tipo):
        d = dims.setdefault(c['dimensao'], [0.0, 0.0])
        w = PESO_CLASSE[c['classe']]
        d[0] += w * nota(c, (avaliacoes.get(c['id']) or {}).get('itens'))
        d[1] += w
    por_dim = {k: 100 * v[0] / v[1] for k, v in dims.items()}
    soma_pesos = sum(PESO_DIM[k] for k in dims)
    return sum(PESO_DIM[k] * por_dim[k] / 100 for k in dims) / soma_pesos * 100, por_dim


# ---------- marcações do controle interno ----------
def marcacoes(banco, ciclo=CICLO):
    return {m['criterio']: m for m in db.todos(banco, 'SELECT * FROM pntp_marcacoes WHERE ciclo=%s', (ciclo,))}


def validar_marcacao(c, itens, link):
    """Erros da marcação (lista vazia = válida). Regras do Avalia: item "atende" exige o link da evidência; sem disponibilidade, nada mais conta."""
    erros = []
    if any(itens.get(i) for i in ITENS if not c['itens'][i]):
        erros.append('Há item marcado que não se aplica a este critério.')
    if any(itens.values()) and not itens.get('disponibilidade'):
        erros.append('Sem disponibilidade, os demais itens não contam: marque a disponibilidade ou desmarque os outros.')
    if itens.get('disponibilidade'):
        l = (link or '').strip()
        if not (l.startswith('https://') or l.startswith('http://') or l.startswith('/')) or len(l) > 500 or any(ch in l for ch in ' <>"\''):
            erros.append('Informe o link da evidência (endereço completo, ou caminho do portal começando com “/”).')
    return erros


def gravar_marcacao(banco, cid, itens, link, obs, por, ciclo=CICLO):
    from psycopg.types.json import Jsonb
    db.exe(banco, """INSERT INTO pntp_marcacoes (ciclo, criterio, itens, link, obs, por, em) VALUES (%s,%s,%s,%s,%s,%s,now())
                     ON CONFLICT (ciclo, criterio) DO UPDATE SET itens=EXCLUDED.itens, link=EXCLUDED.link, obs=EXCLUDED.obs, por=EXCLUDED.por, em=now()""",
           (ciclo, cid, Jsonb(itens), (link or '').strip(), (obs or '').strip()[:1000], por))


def apagar_marcacao(banco, cid, ciclo=CICLO):
    db.exe(banco, 'DELETE FROM pntp_marcacoes WHERE ciclo=%s AND criterio=%s', (ciclo, cid))


def _da_marcacao(c, m, hoje):
    itens = {i: bool((m['itens'] or {}).get(i)) and c['itens'][i] for i in ITENS}
    vencida = c['itens']['atualidade'] and m['em'] and m['em'].date() < hoje - timedelta(days=VALIDADE_MARCACAO)
    if vencida:
        itens['atualidade'] = False
    return itens, vencida


# ---------- avaliação completa ----------
def avaliar(orgao, hoje=None, rotas=()):
    """Avalia todos os critérios do órgão. Devolve dict com 'linhas' (uma por critério), 'indice', 'nivel', 'por_dim' e contagens."""
    from . import pntp_auto
    hoje = hoje or config.hoje()
    tipo, banco = orgao['tipo'], orgao['banco']
    auto = pntp_auto.medir(orgao, hoje, rotas)
    marc = marcacoes(banco)
    linhas, aval = [], {}
    for c in criterios(tipo):
        a = auto.get(c['id'])
        m = marc.get(c['id'])
        if a is not None and a.get('itens') is not None:
            itens = {i: bool(a['itens'].get(i)) and c['itens'][i] for i in ITENS}
            origem, vencida = 'auto', False
        elif m:
            itens, vencida = _da_marcacao(c, m, hoje)
            origem = 'marcacao'
        else:
            itens, vencida, origem = None, False, 'sem'
        aval[c['id']] = {'itens': itens}
        linhas.append(dict(c=c, itens=itens, nota=nota(c, itens), origem=origem, vencida=vencida, marcacao=m,
                           det=(a or {}).get('det', ''), dica=(a or {}).get('dica', ''), link=(a or {}).get('link') or (m['link'] if m else '')))
    ind, por_dim = indice(aval, tipo)
    ess = [l for l in linhas if l['c']['classe'] == 'essencial']
    ess_ok = [l for l in ess if l['nota'] >= 0.999]
    return dict(linhas=linhas, indice=ind, por_dim=por_dim, nivel=nivel(ind, len(ess_ok) == len(ess)), essenciais=len(ess), essenciais_ok=len(ess_ok),
                ess_falta=[l for l in ess if l['nota'] < 0.999], auto=sum(1 for l in linhas if l['origem'] == 'auto'),
                marcados=sum(1 for l in linhas if l['origem'] == 'marcacao'), sem=sum(1 for l in linhas if l['origem'] == 'sem'),
                vencidas=sum(1 for l in linhas if l['vencida']), total=len(linhas), hoje=hoje)
