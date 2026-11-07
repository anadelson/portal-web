"""Coletor do sistema contábil (Fiorilli, API pública VersaoJson / dados abertos).

Parâmetros por órgão (tabela `fontes`, fonte='fiorilli'):
  base      URL da API (ex.: https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/)
  empresa   código da entidade na Fiorilli (ex.: '2')
  bases     lista das bases a coletar (receitas, despesas_unidade, empenhos, diarias, restos_pagar,
            ordem_cronologica, licitacoes, contratos, transferencias, servidores, emendas)
  recebedora  (opcional) filtra as transferências pelo nome do órgão recebedor (ex.: Câmara)
A Câmara usa a mesma API pública da Prefeitura (nunca o banco da Prefeitura).
"""
import re, unicodedata
from datetime import date, timedelta
from psycopg.types.json import Jsonb
from .. import config, db
from .comum import buscar, num, data_br, txt, sem_cpf, doc_pj, eh_pessoa_fisica, chave, gravar

FONTE = 'fiorilli'

def _per(p, ano, hoje):
    fim = hoje if ano == hoje.year else date(ano, 12, 31)
    return {'DiaInicioPeriodo': '01', 'MesInicialPeriodo': '01', 'DiaFinalPeriodo': f'{fim.day:02d}', 'MesFinalPeriodo': f'{fim.month:02d}',
            'Ano': str(ano), 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)}

def _get(p, caminho, params, cache=True):
    d = buscar(FONTE, p['base'].rstrip('/') + '/' + caminho, params)
    return d if isinstance(d, list) else []

def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()

# ---------- bases da Prefeitura ----------
def receitas(b, p, ano, hoje):
    rows = _get(p, 'Receitas/', dict(_per(p, ano, hoje), Listagem='ReceitaOrcamentaria'))
    L = [{'chave': chave('rec', ano, r['CODIGO'], r.get('FONTE'), r.get('VINCODIGO'), r.get('FONTESTN'), r.get('NOME')), 'fonte': FONTE, 'ano': ano, 'mes': 0,
          'codigo': txt(r['CODIGO'], 40), 'nome': txt(r['NOME'], 300), 'fonte_recurso': txt(r.get('FONTE'), 200),
          'previsto': num(r.get('PREVISAO_INICIAL')), 'atualizado': num(r.get('PREVISAO_ATUALIZADA')), 'arrecadado': num(r.get('ARRECADADO_TOTAL')) or 0,
          'soma': bool(re.match(r'^\d000\.00', r['CODIGO'])) and not r.get('FONTE')} for r in rows]
    return gravar(b, 'receitas', L, {'ano': ano, 'mes': 0}, FONTE)

def despesas_unidade(b, p, ano, hoje):
    rows = _get(p, 'Despesas/', dict(_per(p, ano, hoje), Listagem='DespesasPorUnidade'))
    L = [{'chave': chave('du', ano, r['CODIGO']), 'fonte': FONTE, 'ano': ano, 'codigo': txt(r['CODIGO'], 20), 'unidade': txt(r['DESCRICAO'], 200),
          'dotacao': num(r.get('DOTAC')), 'dotacao_atualizada': num(r.get('DOTACAO_ATUALIZADA')), 'empenhado': num(r.get('EMPENHADO')),
          'liquidado': num(r.get('LIQUIDADO')), 'pago': num(r.get('PAGO'))} for r in rows]
    return gravar(b, 'despesas_unidade', L, {'ano': ano}, FONTE)

def _empenhos_brutos(p, ano, hoje):
    return _get(p, 'Despesas/', dict(_per(p, ano, hoje), Listagem='DespesasGerais', MostrarFornecedor='True', MostrarCNPJFornecedor='True',
                                     UFParaFiltroCOVID='', ApenasIDEmpenho='False'))

def linha_empenho(r, ano):
    doc = r.get('CPFFORMATADO') or ''
    return {'chave': chave('emp', ano, r['PKEMP']), 'fonte': FONTE, 'ano': ano, 'pk': txt(r['PKEMP'], 20), 'numero': f"{txt(r['CODIGO'], 12)}/{ano}",
            'tipo': txt(r.get('TPEM'), 4), 'data': data_br(r.get('DATAE')), 'credor': txt(sem_cpf(r.get('NOMEFOR')), 200), 'credor_cnpj': doc_pj(doc),
            'unidade': txt(r.get('NOMELOCAL'), 200), 'funcao': txt(r.get('FUNCAONOME'), 120), 'programa': txt(r.get('PROGRAMANOME'), 200),
            'acao': txt(r.get('PROJETO_ATIVIDADE_NOME'), 200), 'natureza': txt(r.get('NATUREZA'), 40), 'fonte_recurso': txt(r.get('FONGRUPODESC'), 120),
            'vinculo': txt(r.get('VINGRUPO_VINCODIGO'), 20), 'vinculo_nome': txt(r.get('VINCODIGONOME'), 120), 'modalidade': txt(r.get('LICIT'), 60),
            'processo': txt(r.get('NUMLICIT'), 40), 'empenhado': num(r.get('EMPENHADO')) or 0, 'liquidado': num(r.get('LIQUIDADO')) or 0, 'pago': num(r.get('PAGO')) or 0}

def empenhos(b, p, ano, hoje):
    L = [linha_empenho(r, ano) for r in _empenhos_brutos(p, ano, hoje)]
    return gravar(b, 'empenhos', L, {'ano': ano}, FONTE)

def diarias(b, p, ano, hoje):
    rows = _get(p, 'Despesas/', dict(_per(p, ano, hoje), Listagem='Diarias'))
    L = [{'chave': chave('dia', ano, r.get('PKEMP'), r.get('NUMEROLIQUIDACAO'), r.get('ORDEMPAGAMENTO'), r.get('DATA')), 'fonte': FONTE, 'ano': ano,
          'empenho': f"{txt(r.get('NEMPG'), 12)}/{ano}", 'data': data_br(r.get('DATA')), 'favorecido': txt(sem_cpf(r.get('FAVORECIDO')), 200),
          'cargo': txt(r.get('CARGO'), 120), 'unidade': txt(r.get('NOMEUNIDADE') or r.get('NOMEORGAO'), 200), 'motivo': txt(r.get('DESCRICAO'), 600),
          'valor': num(r.get('VALOR')), 'anulado': num(r.get('VALORANULADO'))} for r in rows]
    return gravar(b, 'diarias', L, {'ano': ano}, FONTE)

def restos_pagar(b, p, ano, hoje):
    rows = _get(p, 'Despesas/', dict(_per(p, ano, hoje), Listagem='DespesasRestosPagar', ApresentaNomeFavorecido='True'))
    L = []
    for r in rows:
        credor = txt(r.get('DESCRICAO'), 200)
        m = re.match(r'^([\d./-]+)\s+(.*)$', credor)
        if m and eh_pessoa_fisica(m.group(1)):
            continue  # pessoa física fica fora da lista (LGPD)
        L.append({'chave': chave('rp', ano, r.get('CODIGO'), credor), 'fonte': FONTE, 'ano': ano, 'codigo': txt(r.get('CODIGO'), 20),
                  'credor': sem_cpf(credor), 'empenhado': num(r.get('EMPENHADO')), 'liquidado': num(r.get('LIQUIDADO')), 'pago': num(r.get('PAGO'))})
    return gravar(b, 'restos_pagar', L, {'ano': ano}, FONTE)

def ordem_cronologica(b, p, ano, hoje):
    fim = hoje if ano == hoje.year else date(ano, 12, 31)
    L = []
    for tipo in ('1', '2'):
        rows = _get(p, 'Despesas/', {'Listagem': 'DespesasporExigibilidade', 'DiaInicioPeriodo': f'01/01/{ano}', 'DiaFinalPeriodo': fim.strftime('%d/%m/%Y'),
                                     'strTipoLista': tipo, 'Empresa': p['empresa'], 'ConectarExercicio': str(ano)})
        for r in rows:
            if eh_pessoa_fisica(r.get('CGC')):
                continue  # pessoa física fica fora da lista (LGPD)
            L.append({'chave': chave('oc', ano, tipo, r.get('PKEMP'), r.get('ORDEM_LIQUIDACAO'), r.get('NOTAS'), r.get('VENCI'), r.get('DTPAG'), r.get('VAPAG')),
                      'fonte': FONTE, 'ano': ano, 'lista': 'Até o limite do art. 75, II' if tipo == '1' else 'Acima do limite do art. 75, II',
                      'empenho': txt(r.get('EMPENHO'), 30), 'fornecedor': txt(sem_cpf(r.get('FORNECEDOR')), 200), 'cnpj': doc_pj(r.get('CGC')),
                      'unidade': txt(r.get('UNIDADE_NOME'), 200), 'fonte_recurso': txt(r.get('FONTE_NOME'), 120), 'contrato': txt(r.get('CONTRATO'), 40),
                      'vencimento': data_br(r.get('VENCI')), 'pagamento': data_br(r.get('DTPAG')), 'valor': num(r.get('VAPAG')) or num(r.get('VADEM')),
                      'justificativa': txt(r.get('JUSTIFICATIVA_TEXTO') or r.get('JUSTIFICATIVA'), 600)})
    return gravar(b, 'ordem_cronologica', L, {'ano': ano}, FONTE)

def licitacoes(b, p, ano, hoje):
    rows = _get(p, 'LicitacoesEContratos/', {'Listagem': 'Licitacoes', 'Ano': str(ano), 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)})
    L = [{'chave': chave('lic', ano, r.get('NLICITACAO'), r.get('PROCLIC')), 'fonte': FONTE, 'ano': ano, 'numero': txt(r.get('PROCLIC'), 30),
          'modalidade': txt(r.get('LICIT'), 60).title(), 'objeto': txt(r.get('DISCR'), 800), 'situacao': txt(r.get('SITUACAO'), 60),
          'data': data_br(r.get('DATAE')), 'valor': num(r.get('VALOR')), 'unidade': txt(r.get('NOMEEMPRESA'), 120), 'link': ''} for r in rows]
    return gravar(b, 'licitacoes', L, {'ano': ano}, FONTE)

def contratos(b, p, ano, hoje):
    rows = _get(p, 'LicitacoesEContratos/', {'Listagem': 'Contratos', 'Ano': str(ano), 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False',
                                             'ContratosApenasPublicados': 'True', 'ConectarExercicio': str(ano)})
    L = [{'chave': chave('ct', ano, r.get('CODIGO'), r.get('PROCLIC')), 'fonte': FONTE, 'ano': ano, 'numero': txt(r.get('CODIGO'), 30),
          'fornecedor': txt(sem_cpf(r.get('FORNECEDOR')), 200), 'objeto': txt(r.get('OBJETO_COMPLETO') or r.get('OBJETO'), 800),
          'modalidade': txt(r.get('MODALI'), 60).title(), 'processo': txt(r.get('PROCLIC'), 30), 'assinatura': data_br(r.get('DTASSI')),
          'inicio': data_br(r.get('VIGENI')), 'fim': data_br(r.get('VENCIMENTO_ATUAL') or r.get('VIGENF')), 'unidade': txt(r.get('CODLO_GESTORNOME'), 200),
          'valor': num(r.get('VALCON')), 'empenhado': num(r.get('EMPENHADO')), 'liquidado': num(r.get('LIQUIDADO'))} for r in rows]
    return gravar(b, 'contratos', L, {'ano': ano}, FONTE)

def transferencias(b, p, ano, hoje):
    rows = _get(p, 'Transferencias/', {'Listagem': 'Transf', 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)})
    filtro = norm(p.get('recebedora', ''))
    L = [{'chave': chave('tr', ano, r.get('MES'), r.get('ENTIDADE_PAGADORA'), r.get('ENTIDADE_RECEBEDORA'), r.get('DTLAN')), 'fonte': FONTE, 'ano': ano,
          'mes': int(num(r.get('MES')) or 0) or None, 'data': data_br(r.get('DTLAN')), 'pagadora': txt(r.get('ENTIDADE_PAGADORA'), 200),
          'recebedora': txt(r.get('ENTIDADE_RECEBEDORA'), 200), 'previsto': num(r.get('PREVISTO')), 'repasse': num(r.get('REPASSE')),
          'devolucao': num(r.get('DEVOLUCAO'))} for r in rows if not filtro or filtro in norm(r.get('ENTIDADE_RECEBEDORA'))]
    return gravar(b, 'transferencias', L, {'ano': ano}, FONTE)

def servidores(b, p, ano, hoje):
    rows, mes = [], hoje.month if ano == hoje.year else 12
    for m in (mes, mes - 1):  # folha do mês corrente pode não estar fechada: tenta o anterior
        if m < 1:
            break
        rows = _get(p, 'Pessoal/', {'Listagem': 'Servidores', 'Empresa': p['empresa'], 'Ano': str(ano), 'MesFinalPeriodo': f'{m:02d}', 'ConectarExercicio': str(ano)})
        if rows:
            mes = m
            break
    # LGPD: só nome (nome social quando houver), cargo, vínculo, lotação, admissão e remuneração bruta. CPF e descontos não são lidos.
    L = [{'chave': chave('srv', ano, mes, r.get('REGISTRO'), r.get('CONTRATO')), 'fonte': FONTE, 'ano': ano, 'mes': mes, 'registro': txt(r.get('REGISTRO'), 20),
          'nome': txt(sem_cpf(r.get('NOME_SOCIAL') or r.get('NOME')), 200), 'cargo': txt(r.get('CARGO'), 120), 'vinculo': txt(r.get('VINCULO'), 60),
          'lotacao': txt(r.get('UNIDADE') or r.get('DIVISAO'), 200), 'admissao': data_br(r.get('DATAADMISSAO')), 'proventos': num(r.get('PROVENTOS'))} for r in rows]
    return gravar(b, 'servidores', L, {'ano': ano, 'mes': mes}, FONTE)

# ---------- emendas (banco da Câmara, lidas da API pública da Prefeitura) ----------
TIPOS = {'OR': 'Ordinário', 'GL': 'Global', 'ES': 'Estimativo'}

def _d(v):
    d = data_br(v)
    return d.strftime('%d/%m/%Y') if d else ''

def _por_empenho(p, ano, numero, tipo, listagem):
    rows = _get(p, 'Despesas/', {'ConectarExercicio': str(ano), 'Listagem': listagem, 'intNumeroEmpenho': numero, 'strTipoEmpenho': tipo,
                                 'DiaInicioPeriodo': '01', 'MesInicialPeriodo': '01', 'DiaFinalPeriodo': '31', 'MesFinalPeriodo': '12', 'Ano': str(ano),
                                 'Empresa': p['empresa'], 'IDButton': 'lnkDespesasPor_NotaEmpenho', 'MostrarFornecedor': 'True', 'MostraDadosConsolidado': 'False'})
    return [[_d(r.get('DATAE')), num(r.get('VALOR')) or 0] for r in rows]

def emendas(b, p, ano, hoje):
    cad = [e for e in _get(p, 'Transferencias/', {'Listagem': 'CadEmendasImpositivas', 'Empresa': p['empresa'], 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)})
           if str(e.get('ESFERA_ORIGEM', '')).strip().upper() == 'MUNICIPAL' and str(e.get('ANO')) == str(ano)]
    if not cad:
        return 0
    brutos = [r for r in _empenhos_brutos(p, ano, hoje) if 'emenda' in norm(r.get('VINCODIGONOME'))]
    # empenhos de emenda agrupados pelo número; o vínculo "Emenda Ver. <nome>" identifica o vereador
    grupos = {}
    for r in brutos:
        grupos.setdefault(r['CODIGO'], []).append(r)
    por_autor = {}
    for e in cad:
        por_autor.setdefault(norm(e.get('AUTOR')), []).append(e)
    def autor_do_vinculo(v):
        n = norm(v).replace('emenda ver.', '').replace('emenda ver', '').strip()
        return next((a for a in por_autor if a.startswith(n) or n.startswith(a)), None) if n else None
    exec_emenda, nao_atrib = {}, set()
    for numero, rs in grupos.items():
        autor = autor_do_vinculo(rs[0].get('VINCODIGONOME'))
        if not autor:
            continue
        candidatas = [e for e in por_autor[autor] if (num(e.get('EMPENHADO')) or 0) > 0] or (por_autor[autor] if len(por_autor[autor]) == 1 else [])
        if len(candidatas) != 1:
            nao_atrib.update(f"{e['NUMERO_EMENDA']}/{ano}" for e in por_autor[autor])
            continue
        exec_emenda.setdefault(f"{candidatas[0]['NUMERO_EMENDA']}/{ano}", []).append(rs)
    n = 0
    lida = hoje.strftime('%d/%m/%Y')
    for e in cad:
        nume = f"{e['NUMERO_EMENDA']}/{ano}"
        det, emp, liq, pag = None, None, None, None
        if nume in exec_emenda:
            empenhos_det, emp, liq, pag = [], 0, 0, 0
            base = None
            for rs in exec_emenda[nume]:
                orig = next((r for r in rs if r.get('TPEM') != 'AN'), rs[0])
                base = base or orig
                anul = [[_d(r.get('DATAE')), abs(num(r.get('EMPENHADO')) or 0)] for r in rs if r.get('TPEM') == 'AN']
                liqs = _por_empenho(p, ano, orig['CODIGO'], orig.get('TPEM') or 'OR', 'EmpenhosDespesas_Liquidado_PorNumeroEmpenho')
                pags = _por_empenho(p, ano, orig['CODIGO'], orig.get('TPEM') or 'OR', 'EmpenhosDespesas_Pago_PorNumeroEmpenho')
                valor = num(orig.get('EMPENHADO')) or 0
                emp += valor - sum(a[1] for a in anul); liq += sum(x[1] for x in liqs); pag += sum(x[1] for x in pags)
                empenhos_det.append({'num': f"{orig['CODIGO']}/{ano}", 'tipo': TIPOS.get(orig.get('TPEM'), orig.get('TPEM')), 'data': _d(orig.get('DATAE')),
                                     'valor': valor, 'anul': anul, 'liq': liqs, 'pag': pags})
            det = {'vinculo': f"{base.get('VINGRUPO_VINCODIGO')} · {txt(base.get('VINCODIGONOME'))}", 'ato': txt(e.get('ATO_NORMATIVO')),
                   'destinacao': txt(e.get('DESTINACAO_DESCR')), 'orgao': txt(base.get('NOMELOCAL')), 'programa': txt(base.get('PROGRAMANOME')),
                   'acao': txt(base.get('PROJETO_ATIVIDADE_NOME')), 'natureza': txt(base.get('NATUREZA')), 'fonte': txt(base.get('FONGRUPODESC')),
                   'contratacao': ' '.join(x for x in (txt(base.get('LICIT')), txt(base.get('NUMLICIT'))) if x), 'credor': txt(sem_cpf(base.get('NOMEFOR'))),
                   'empenhos': empenhos_det, 'pagoCad': num(e.get('PAGO')) or 0}
        pago_cad = num(e.get('PAGO')) or 0
        if nume in nao_atrib and nume not in exec_emenda:
            conf = 'nao_atribuivel'
        elif pag is None:
            conf = 'sem_execucao' if not pago_cad else 'divergente'
        else:
            conf = 'conferido' if abs(pag - pago_cad) < 0.01 else 'divergente'
        objeto = txt(e.get('OBJETO') or e.get('RESUMO'), 400)
        db.exe(b, """INSERT INTO emendas (numero, autor, objeto, valor, pago_cadastro, empenhado_cadastro, liquidado_cadastro, empenhado, liquidado, pago_empenho, empenho, conferencia, detalhe, fonte, atualizado_em, coletado_em)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),now())
                     ON CONFLICT (numero) DO UPDATE SET autor=EXCLUDED.autor, objeto=coalesce(nullif(emendas.objeto, ''), EXCLUDED.objeto), valor=EXCLUDED.valor,
                     pago_cadastro=EXCLUDED.pago_cadastro, empenhado_cadastro=EXCLUDED.empenhado_cadastro, liquidado_cadastro=EXCLUDED.liquidado_cadastro,
                     empenhado=EXCLUDED.empenhado, liquidado=EXCLUDED.liquidado, pago_empenho=EXCLUDED.pago_empenho, empenho=EXCLUDED.empenho,
                     conferencia=EXCLUDED.conferencia, detalhe=EXCLUDED.detalhe, fonte=EXCLUDED.fonte, atualizado_em=now(), coletado_em=now()""",
               (nume, txt(e.get('AUTOR'), 120), objeto, num(e.get('VALOR_TOTAL')) or 0, pago_cad, num(e.get('EMPENHADO')), num(e.get('LIQUIDADO')),
                emp, liq, pag, ', '.join(x['num'] for x in (det or {}).get('empenhos', [])), conf, Jsonb(det) if det else None,
                f'Fiorilli (Prefeitura), API pública: cadastro de emendas e empenhos, lidos em {lida}'))
        n += 1
    return n

BASES = {'receitas': receitas, 'despesas_unidade': despesas_unidade, 'empenhos': empenhos, 'diarias': diarias, 'restos_pagar': restos_pagar,
         'ordem_cronologica': ordem_cronologica, 'licitacoes': licitacoes, 'contratos': contratos, 'transferencias': transferencias,
         'servidores': servidores, 'emendas': emendas}

def coletar(orgao, p, hoje=None):
    """Roda as bases configuradas do órgão. Devolve [(base, ok, registros, mensagem)]; a falha de uma base não para as outras."""
    hoje = hoje or config.hoje()
    res = []
    for base in p.get('bases', []):
        fn = BASES.get(base)
        if not fn:
            continue
        try:
            n = fn(orgao['banco'], p, hoje.year, hoje)
            res.append((base, True, n, f'{n} registros de {hoje.year}'))
        except Exception as e:
            res.append((base, False, 0, f'{type(e).__name__}: {e}'))
    return res
