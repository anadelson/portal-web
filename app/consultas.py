"""Fase 9 — consultas de dados: como cada integração é montada, parâmetros editáveis, teste sem gravar e histórico.

Vale para todas as integrações (indicadores, transparência/Fiorilli, PNCP, Siconfi, TCESP, IBGE, INEP, CNES, MDS, IEG-M, YouTube).
O teste roda o próprio coletor em modo ENSAIO (db.ENSAIO): toda escrita é bloqueada e cada requisição HTTP é anotada
(método, endereço sem segredos, código HTTP, tempo, registros e trecho da resposta com CPF mascarado)."""
import hashlib, json, re
from datetime import datetime, timedelta, timezone
from psycopg.types.json import Jsonb
from . import config, db

FIORILLI_BASES = {'receitas': 'Receitas', 'despesas_unidade': 'Despesas por unidade', 'empenhos': 'Empenhos', 'diarias': 'Diárias',
                  'restos_pagar': 'Restos a pagar', 'ordem_cronologica': 'Ordem cronológica de pagamentos', 'licitacoes': 'Licitações',
                  'contratos': 'Contratos', 'transferencias': 'Transferências', 'servidores': 'Pessoal (servidores)', 'emendas': 'Emendas impositivas'}

# Campo: (nome, rótulo, tipo, de onde vem o valor). Tipos: url, ibge, int, texto, slug, sn (sim/não), poder, anos, bases
_IBGE = ('ibge', 'Código IBGE do município', 'ibge', 'código IBGE do órgão (cadastro no console)')
ESQUEMA = {
    'fiorilli': [('base', 'Endereço da API de dados abertos', 'url', 'fornecedor do sistema contábil (Fiorilli)'),
                 ('empresa', 'Código da entidade (Empresa)', 'int', 'cadastro da entidade no sistema contábil'),
                 ('bases', 'Bases coletadas', 'bases', 'escolha do órgão'),
                 ('recebedora', 'Nome da recebedora nas transferências (opcional)', 'texto', 'usado pela Câmara para achar os repasses')],
    'financas': [('base', 'Endereço da API de dados abertos', 'url', 'o mesmo da fonte Fiorilli do órgão'),
                 ('empresa', 'Código da entidade (Empresa)', 'int', 'o mesmo da fonte Fiorilli do órgão')],
    'pncp': [_IBGE, ('cnpj', 'CNPJ do órgão', 'texto', 'cadastro do órgão')],
    'siconfi': [_IBGE, ('rreo', 'Coletar o RREO (Anexo 14)', 'sn', 'só o Executivo publica o RREO'), ('rgf_poder', 'Poder do RGF (E ou L)', 'poder', 'E = Executivo, L = Legislativo')],
    'tcesp': [('municipio', 'Município no portal do TCESP', 'slug', 'nome do município no endereço do TCESP'), ('anos', 'Anos fechados a buscar', 'anos', 'anos anteriores sem dado no sistema contábil')],
    'ibge': [_IBGE], 'cnes': [_IBGE], 'inep': [_IBGE], 'iegm': [_IBGE], 'mds': [_IBGE], 'pni': [_IBGE], 'painel': [_IBGE],
    'youtube': [], 'redes': [],
}
NOMES = {'fiorilli': 'Sistema contábil (Fiorilli)', 'financas': 'Sistema contábil — série mensal (Fiorilli)', 'pncp': 'PNCP (contratações públicas)',
         'siconfi': 'Siconfi (Tesouro Nacional)', 'tcesp': 'TCESP — Transparência', 'ibge': 'IBGE', 'cnes': 'CNES (Ministério da Saúde)', 'inep': 'INEP',
         'iegm': 'TCESP — IEG-M', 'mds': 'MDS', 'pni': 'Ministério da Saúde (vacinação)', 'painel': 'Cálculo do painel (dados já coletados + Siconfi)',
         'youtube': 'YouTube (transmissões)', 'redes': 'Redes sociais (últimas publicações)', 'portal': 'Este portal (e-SIC e Ouvidoria)', 'manual': 'Lançamento manual'}
FORMATO = {'inep': 'planilha (ZIP com XLSX)', 'painel': 'cálculo interno + JSON', 'portal': 'banco do próprio portal', 'manual': '—'}
CREDENCIAL = {'iegm': 'iegm', 'youtube': 'youtube', 'redes': 'meta'}

# Como a consulta é montada (endpoints), com o significado de cada parâmetro
def endpoints(fonte, p):
    ano = config.hoje().year
    ib = str(p.get('ibge', '{ibge}'))
    per = {'Ano': ano, 'Empresa': p.get('empresa', '{empresa}'), 'DiaInicioPeriodo': '01', 'MesInicialPeriodo': '01', 'DiaFinalPeriodo': '{dia de hoje}',
           'MesFinalPeriodo': '{mês de hoje}', 'MostraDadosConsolidado': 'False', 'ConectarExercicio': ano}
    base = (p.get('base') or '{base}').rstrip('/')
    if fonte == 'fiorilli':
        out = []
        for k in (p.get('bases') or []):
            caminho, q = {'receitas': ('Receitas/', dict(per, Listagem='ReceitaOrcamentaria')), 'despesas_unidade': ('Despesas/', dict(per, Listagem='DespesasPorUnidade')),
                          'empenhos': ('Despesas/', dict(per, Listagem='DespesasGerais', MostrarFornecedor='True', MostrarCNPJFornecedor='True')),
                          'diarias': ('Despesas/', dict(per, Listagem='Diarias')), 'restos_pagar': ('Despesas/', dict(per, Listagem='DespesasRestosPagar', ApresentaNomeFavorecido='True')),
                          'ordem_cronologica': ('Despesas/', {'Listagem': 'DespesasporExigibilidade', 'DiaInicioPeriodo': f'01/01/{ano}', 'DiaFinalPeriodo': '{hoje dd/mm/aaaa}', 'Empresa': p.get('empresa')}),
                          'licitacoes': ('LicitacoesEContratos/', {'Listagem': 'Licitacoes', 'Ano': ano, 'Empresa': p.get('empresa'), 'MostraDadosConsolidado': 'False', 'ConectarExercicio': ano}),
                          'contratos': ('LicitacoesEContratos/', {'Listagem': 'Contratos', 'Ano': ano, 'Empresa': p.get('empresa'), 'MostraDadosConsolidado': 'False', 'ConectarExercicio': ano}),
                          'transferencias': ('Transferencias/', {'Listagem': 'Transf', 'Empresa': p.get('empresa'), 'MostraDadosConsolidado': 'False', 'ConectarExercicio': ano}),
                          'servidores': ('Pessoal/', {'Listagem': 'Servidores', 'Empresa': p.get('empresa'), 'Ano': ano, 'MesFinalPeriodo': '{cada mês}', 'ConectarExercicio': ano}),
                          'emendas': ('Transferencias/', {'Listagem': 'CadEmendasImpositivas', 'Empresa': p.get('empresa'), 'MostraDadosConsolidado': 'False', 'ConectarExercicio': ano}),
                          }.get(k, ('', {}))
            if caminho:
                out.append((FIORILLI_BASES.get(k, k), 'GET', f'{base}/{caminho}', q, k))
        return out
    if fonte == 'financas':
        return [('Receitas do mês', 'GET', f'{base}/Receitas/', dict(per, Listagem='ReceitaOrcamentaria', MesFinalPeriodo='{cada mês}'), ''),
                ('Despesas do mês', 'GET', f'{base}/Despesas/', dict(per, Listagem='DespesasPorUnidade', MesFinalPeriodo='{cada mês}'), '')]
    if fonte == 'pncp':
        return [('Editais publicados', 'GET', 'https://pncp.gov.br/api/search/', {'tipos_documento': 'edital', 'municipios': ib, 'status': 'todos', 'ordenacao': '-data', 'pagina': '{1, 2, …}', 'tam_pagina': 50}, '')]
    if fonte == 'siconfi':
        T = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/'
        return [('Extrato de entregas', 'GET', T + 'extrato_entregas', {'id_ente': ib, 'an_referencia': ano}, ''),
                ('RREO — Anexo 14', 'GET', T + 'rreo', {'an_exercicio': '{ano}', 'nr_periodo': '{bimestre}', 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': ib}, ''),
                ('RGF — Anexo 01', 'GET', T + 'rgf', {'an_exercicio': '{ano}', 'in_periodicidade': 'Q', 'nr_periodo': '{quadrimestre}', 'co_tipo_demonstrativo': 'RGF', 'co_poder': p.get('rgf_poder', 'E'), 'id_ente': ib}, '')]
    if fonte == 'tcesp':
        return [('Receitas do mês', 'GET', f"https://transparencia.tce.sp.gov.br/api/json/receitas/{p.get('municipio', '{municipio}')}/{{ano}}/{{mês}}", {}, '')]
    if fonte == 'ibge':
        return [('Períodos da pesquisa', 'GET', 'https://servicodados.ibge.gov.br/api/v1/pesquisas/{pesquisa}/periodos', {}, ''),
                ('Agregados (população, PIB…)', 'GET', 'https://servicodados.ibge.gov.br/api/v3/agregados/{agregado}/periodos/{período}/variaveis/{variável}', {'localidades': f'N6[{ib}]'}, ''),
                ('Tabelas SIDRA (registro civil)', 'GET', f'https://apisidra.ibge.gov.br/values/t/{{tabela}}/n6/{ib}/v/all/p/last%20{{n}}', {}, '')]
    if fonte == 'cnes':
        return [('Estabelecimentos de saúde', 'GET', 'https://apidadosabertos.saude.gov.br/cnes/estabelecimentos', {'codigo_municipio': ib[:6], 'limit': 20, 'offset': '{0, 20, …}'}, ''),
                ('Tipos de unidade', 'GET', 'https://apidadosabertos.saude.gov.br/cnes/tipounidades', {}, '')]
    if fonte == 'inep':
        return [('IDEB por município (cada etapa)', 'HEAD/GET', 'https://download.inep.gov.br/ideb/resultados/divulgacao_{etapa}_municipios_{edição}.zip', {}, ''),
                ('Comparação SP e Brasil', 'HEAD/GET', 'https://download.inep.gov.br/ideb/resultados/divulgacao_{brasil|regioes_ufs}_ideb_{edição}.zip', {}, '')]
    if fonte == 'iegm':
        return [('Painel IEG-M (Pentaho CDA)', 'GET', 'https://painel.tce.sp.gov.br/pentaho/plugin/cda/api/doQuery', {'parampExercicio_mapa': '{ano}', '…': 'consulta do painel público'}, '')]
    if fonte == 'mds':
        return [('MI Social', 'GET', 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial/', {'q': '*:*', 'fq': f'codigo_ibge:{ib[:6]}', 'fl': '{campos}'}, '')]
    if fonte == 'painel':
        return [('RREO Anexo 14 (mínimos de saúde e educação)', 'GET', 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo', {'an_exercicio': '{ano}', 'nr_periodo': '{bimestre}', 'co_tipo_demonstrativo': 'RREO', 'no_anexo': 'RREO-Anexo 14', 'id_ente': ib}, ''),
                ('Cálculos sobre dados já coletados', '—', 'banco do órgão (receitas, despesas, contratações, e-SIC, ouvidoria)', {}, '')]
    if fonte == 'youtube':
        return [('Vídeos recentes do canal', 'GET', 'https://www.googleapis.com/youtube/v3/playlistItems', {'part': 'contentDetails', 'playlistId': 'UU{canal sem UC}', 'maxResults': 10, 'key': '***'}, ''),
                ('Detalhes dos vídeos', 'GET', 'https://www.googleapis.com/youtube/v3/videos', {'part': 'snippet,liveStreamingDetails,contentDetails', 'id': '{ids}', 'key': '***'}, '')]
    if fonte == 'redes':
        return [('YouTube — últimos vídeos', 'GET', 'https://www.googleapis.com/youtube/v3/playlistItems', {'part': 'snippet', 'playlistId': 'UU{canal sem UC}', 'maxResults': 6, 'key': '***'}, ''),
                ('Instagram — últimas publicações', 'GET', 'https://graph.facebook.com/v21.0/{conta}/media', {'fields': 'caption,media_type,media_url,thumbnail_url,permalink,timestamp', 'limit': 6, 'access_token': '***'}, ''),
                ('Facebook — últimas publicações', 'GET', 'https://graph.facebook.com/v21.0/{página}/posts', {'fields': 'message,permalink_url,created_time,full_picture', 'limit': 6, 'access_token': '***'}, '')]
    return []

# Campo da fonte → onde vai (lido do código dos coletores)
MAPEAMENTO = {
    'fiorilli': [('CODIGO, NOME, PREVISAO_INICIAL, PREVISAO_ATUALIZADA, ARRECADADO_TOTAL', 'Receitas (transparência)'),
                 ('CODIGO, DESCRICAO, DOTAC, DOTACAO_ATUALIZADA, EMPENHADO, LIQUIDADO, PAGO', 'Despesas por unidade'),
                 ('Empenho, fornecedor (CNPJ; pessoa física sem CPF), valores', 'Empenhos'), ('Beneficiário, destino, motivo, período, valor', 'Diárias'),
                 ('Licitação, modalidade, objeto, situação', 'Licitações'), ('Contrato, fornecedor, vigência, valor', 'Contratos'),
                 ('Servidor, cargo, vínculo, remuneração', 'Pessoal'), ('Arrecadado e pago acumulados', 'Indicadores de Dinheiro público')],
    'financas': [('ARRECADADO_TOTAL e PAGO por mês', 'Série mensal do painel (receita × despesa)')],
    'pncp': [('título, modalidade, valor, data, situação, item_url', 'Contratações publicadas no PNCP (indicadores de Contratações)')],
    'siconfi': [('RREO Anexo 14 / RGF Anexo 01 (conta, coluna, valor)', 'Relatórios fiscais (transparência)')],
    'tcesp': [('receitas mensais (ano fechado)', 'Receitas de anos anteriores')],
    'ibge': [('população estimada, PIB per capita, pessoal ocupado, salário médio, nascidos vivos, óbitos', 'Indicadores de Município e gestão / Saúde')],
    'cnes': [('estabelecimentos do município (contagem e lista)', 'Estabelecimentos de saúde no CNES')],
    'inep': [('VL_OBSERVADO_{ano}, notas Saeb (Matemática, Língua Portuguesa) da rede pública', 'IDEB e Saeb por etapa')],
    'iegm': [('faixa e nota por índice (i-Educ, i-Saúde, i-Planejamento…)', 'IEG-M — resultado geral e por índice')],
    'mds': [('famílias no Bolsa Família, valor repassado, Cadastro Único, BPC', 'Assistência social')],
    'painel': [('RREO Anexo 14: % aplicado em saúde e em educação', 'Mínimos constitucionais'), ('dados já coletados', 'Dinheiro público, Contratações e Gestão')],
    'redes': [('título/legenda, link, data e miniatura (baixada para o portal)', 'Bloco “Nas redes” (suspenso no período eleitoral)')],
    'youtube': [('liveBroadcastContent, actualStartTime/EndTime, caption', 'Transmissões (ao vivo e gravações)')],
}

def periodicidade(fonte, f=None):
    """Quando a fonte roda: a agenda do órgão (se houver linha em `fontes`) ou o padrão do sistema."""
    from . import agenda as AG
    if fonte in AG.FIXAS:
        return AG.FIXAS[fonte]
    if fonte in AG.PADRAO:
        return AG.descrever(AG.da_fonte(dict(f or {}, fonte=fonte)))
    from .worker import FREQ
    if fonte not in FREQ:
        return '—'
    cada, horas = FREQ[fonte]
    t = f'a cada {cada} min' if cada < 60 else f'a cada {cada // 60} h' if cada < 24 * 60 else f'a cada {cada // (24 * 60)} dia(s)'
    return t + ('' if len(horas) == 24 else f', entre {horas[0]}h e {horas[-1] + 1}h')

# ---------- origem de cada indicador (sub-abas) ----------
def origem(ind):
    c, k = ind['coletor'], ind['chave']
    if not c or ind['modo'] == 'manual':
        return 'manual'
    if c == 'painel':
        if k.startswith('fin_'):
            return 'financas'
        if k.startswith('cont_'):
            return 'pncp'
        if k.startswith('gestao_'):
            return 'portal'
        return 'painel'
    return c

# ---------- parâmetros ----------
def validar(fonte, form, atual):
    """Lê do formulário os campos do esquema. Devolve (novo_params, erros). Campos fora do esquema são preservados."""
    novo, erros = dict(atual or {}), []
    for nome, rot, tipo, _ in ESQUEMA.get(fonte, []):
        v = (form.get(f'p_{nome}') or '').strip() if tipo not in ('bases', 'sn') else None
        if tipo == 'url':
            if not re.match(r'^https://[\w.-]+(:\d+)?(/[\w./%-]*)?$', v):
                erros.append(f'{rot}: informe um endereço https:// válido.')
            novo[nome] = v
        elif tipo == 'ibge':
            if not re.fullmatch(r'\d{7}', v):
                erros.append(f'{rot}: são 7 dígitos.')
            novo[nome] = v
        elif tipo == 'int':
            if not v.isdigit():
                erros.append(f'{rot}: só números.')
            novo[nome] = v
        elif tipo == 'slug':
            if not re.fullmatch(r'[a-z0-9-]{2,60}', v):
                erros.append(f'{rot}: letras minúsculas, números e hífen.')
            novo[nome] = v
        elif tipo == 'poder':
            if v not in ('E', 'L'):
                erros.append(f'{rot}: E ou L.')
            novo[nome] = v
        elif tipo == 'anos':
            anos = [int(x) for x in re.split(r'[,\s]+', v) if x.isdigit()]
            if v and (not anos or any(a < 2000 or a > config.hoje().year for a in anos)):
                erros.append(f'{rot}: anos entre 2000 e {config.hoje().year}, separados por vírgula.')
            novo[nome] = anos
        elif tipo == 'sn':
            novo[nome] = form.get(f'p_{nome}') == '1'
        elif tipo == 'bases':
            sel = [b for b in form.getlist(f'p_{nome}') if b in FIORILLI_BASES] if hasattr(form, 'getlist') else []
            if not sel:
                erros.append(f'{rot}: escolha ao menos uma.')
            novo[nome] = sel
        elif tipo == 'texto':
            novo[nome] = v[:120]
    return novo, erros

def hash_params(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

def fonte_do(o, fonte):
    return db.um(db.PLATAFORMA, 'SELECT * FROM fontes WHERE orgao_id=%s AND fonte=%s', (o['id'], fonte))

# ---------- ensaio ----------
def ensaiar(o, fonte, params, base=None):
    """Roda o coletor sem gravar. `base` (Fiorilli): testa só essa base. Devolve o relatório."""
    from .worker import MODULOS
    from .coletores import comum
    p = dict(params)
    if fonte == 'fiorilli' and base:
        p['bases'] = [base]
    rel = {'fonte': fonte, 'params': p, 'inicio': datetime.now(timezone.utc).isoformat()}
    tok = db.ENSAIO.set(rel); tok2 = comum.ORGAO.set(o['slug'])
    t0 = datetime.now()
    try:
        res = MODULOS[fonte].coletar(o, p)
        rel['resultado'] = [{'base': b, 'ok': ok, 'registros': n, 'mensagem': str(m)[:300]} for b, ok, n, m in (res or [])]
        rel['ok'] = bool(rel.get('requisicoes')) and all(r['status'] and r['status'] < 400 for r in rel['requisicoes']) and all(x['ok'] for x in rel['resultado'])
    except Exception as e:
        rel['resultado'] = [{'base': fonte, 'ok': False, 'registros': 0, 'mensagem': f'{type(e).__name__}: {str(e)[:200]}'}]
        rel['ok'] = False
    finally:
        db.ENSAIO.reset(tok); comum.ORGAO.reset(tok2)
    rel['segundos'] = round((datetime.now() - t0).total_seconds(), 1)
    if not rel.get('requisicoes'):
        rel['aviso'] = 'Nenhuma requisição foi feita (fonte desligada, sem credencial, sem módulo ou nada a consultar agora).'
    return rel

def registrar_teste(o, fonte, params, rel, quem):
    db.exe(db.PLATAFORMA, 'INSERT INTO consulta_testes (orgao_id, fonte, params_hash, ok, relatorio, quem) VALUES (%s,%s,%s,%s,%s,%s)',
           (o['id'], fonte, hash_params(params), rel['ok'], Jsonb(rel), quem))

def teste_valido(o, fonte, params):
    """Teste bem-sucedido com exatamente estes parâmetros nos últimos 30 minutos."""
    return bool(db.um(db.PLATAFORMA, "SELECT 1 FROM consulta_testes WHERE orgao_id=%s AND fonte=%s AND params_hash=%s AND ok AND em > now() - interval '30 minutes'",
                      (o['id'], fonte, hash_params(params))))

def ultimo_teste(o, fonte):
    return db.um(db.PLATAFORMA, 'SELECT * FROM consulta_testes WHERE orgao_id=%s AND fonte=%s ORDER BY id DESC LIMIT 1', (o['id'], fonte))

def salvar(o, fonte, antes, depois, quem):
    db.exe(db.PLATAFORMA, 'UPDATE fontes SET params=%s WHERE orgao_id=%s AND fonte=%s', (Jsonb(depois), o['id'], fonte))
    db.exe(db.PLATAFORMA, 'INSERT INTO fontes_historico (orgao_id, fonte, antes, depois, quem) VALUES (%s,%s,%s,%s,%s)', (o['id'], fonte, Jsonb(antes), Jsonb(depois), quem))

def painel(o, fonte):
    """Tudo o que a tela "Como a consulta é montada" mostra para uma fonte do órgão."""
    from . import credenciais as CR
    f = fonte_do(o, fonte)
    p = (f or {}).get('params') or {}
    amostras = db.todos(db.PLATAFORMA, "SELECT * FROM consulta_amostras WHERE fonte=%s AND orgao_slug=%s ORDER BY em DESC LIMIT 15",
                        ('fiorilli' if fonte == 'financas' else fonte, o['slug']))
    coletas = db.todos(db.PLATAFORMA, "SELECT * FROM coletas WHERE orgao_slug=%s AND split_part(fonte, ':', 1)=%s ORDER BY id DESC LIMIT 8", (o['slug'], fonte))
    cred = CREDENCIAL.get(fonte)
    return {'fonte': fonte, 'nome': NOMES.get(fonte, fonte), 'cadastrada': bool(f), 'ativa': bool(f and f['ativo']), 'params': p,
            'esquema': [(n, r, t, de, p.get(n)) for n, r, t, de in ESQUEMA.get(fonte, [])], 'endpoints': endpoints(fonte, p),
            'mapeamento': MAPEAMENTO.get(fonte, []), 'formato': FORMATO.get(fonte, 'JSON'), 'periodicidade': periodicidade(fonte, f),
            'credencial': ('configurada no console' if CR.situacao(cred) else 'NÃO configurada no console') if cred else 'não usa',
            'amostras': amostras, 'coletas': coletas, 'teste': ultimo_teste(o, fonte),
            'historico': db.todos(db.PLATAFORMA, 'SELECT * FROM fontes_historico WHERE orgao_id=%s AND fonte=%s ORDER BY id DESC LIMIT 10', (o['id'], fonte)),
            'bases_opcoes': FIORILLI_BASES}
