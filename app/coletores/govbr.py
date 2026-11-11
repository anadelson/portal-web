"""Coletor do portal "TransparênciaBR" da GOVBR (Pronim TB) — etapa 4 do modelo multi-órgão (11/11/2026).

A GOVBR não tem API JSON pública: o portal oferece "Exportar Dados", que gera um ZIP com um XML. O coletor faz o
mesmo que o botão do portal, sem login e sem captcha (a única tela com reCAPTCHA, "Salários por colaborador", fica de fora):
  1. GET  {base}index.asp?acao=10&item=N          → lê na própria tela o código do banco de cada ano (muda todo ano)
  2. GET  {base}geraxml.asp?item=N&banco=…&exercicio=…&dataInicial=AAAAMMDD&dataFinal=AAAAMMDD&unidadeGestora=-1
                                                   → devolve um link "dll/<arquivo>.zip" (ou o cabeçalho ERRO)
  3. GET  {base}dll/<arquivo>.zip                  → ZIP com um XML (ISO-8859-1), lido na memória

Parâmetros por órgão (tabela `fontes`, fonte='govbr'):
  base            endereço do portal (ex.: https://<municipio>.cidade360.cloud/pronimtb/)
  unidades        nomes da unidade gestora no XML, separados por vírgula (ex.: PREFEITURA MUNICIPAL; vazio = todas)
  bases           bases a coletar (ver BASES)
  meses_recentes  nas execuções rápidas, quantos meses (o atual e os anteriores) são lidos de novo (1 a 3);
                  uma execução a cada 24 horas é completa (relê o ano inteiro e tira o que sumiu da fonte)
  pessoal         códigos das entidades de pessoal (ex.: DW_LC131_AP_3) — vazio = todas as que a tela oferece
  recebedora      (transferências) filtra pelo órgão recebedor (ex.: PODER LEGISLATIVO, para a Câmara)

Cada base é descrita UMA vez em BASES: o coletor executa essa descrição e a tela "Como a consulta é montada" mostra a
mesma descrição (parâmetros, arquivo, filtros e, coluna por coluna, de que campo do XML vem cada valor do portal).
A banco de cada órgão continua separado; a Câmara lê o portal público da Prefeitura, nunca o banco dela."""
import io, json, re, time, unicodedata, zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
import httpx
from .. import config, db
from . import comum
from .comum import txt, data_br, sem_cpf, doc_pj, eh_pessoa_fisica, chave, gravar

FONTE = 'govbr'
MAX_ZIP = 40 * 1024 * 1024      # tamanho máximo do ZIP baixado
MAX_XML = 200 * 1024 * 1024     # tamanho máximo do XML descompactado
OCULTOS = {'Descontos', 'Liquido', 'CPF', 'CPFCNPJ', 'CNPJCPF', 'NCPJ', 'CNPJFornecedor'}
MESES = ['JANEIRO', 'FEVEREIRO', 'MARÇO', 'ABRIL', 'MAIO', 'JUNHO', 'JULHO', 'AGOSTO', 'SETEMBRO', 'OUTUBRO', 'NOVEMBRO', 'DEZEMBRO']

# ---------- descrição de cada base (o coletor executa; a tela de Integrações mostra) ----------
# item: tela "Exportar Dados" (index.asp?acao=10&item=N); banco: de onde vem o código do banco
#   ano = combo de anos da tela ("2026|DW_LC131_FC_31|"); adm = combo de entidade da tela de licitações; pessoal = entidades de pessoal
# janela: mes = um pedido por mês (execução completa: o ano todo; rápida: os últimos meses) · ano = um pedido de 01/01 até hoje
# colunas: (coluna da tabela, rótulo no portal, campo do XML, regra aplicada)
BASES = {
    'empenhos': dict(rotulo='Empenhos', item=6, banco='ano', janela='mes', arquivo='empenhos.zip', registro='Principal', tabela='empenhos',
        tela='empenhos', titulo='Despesas — empenhos', filtro='UnidadeGestora',
        colunas=[('data', 'Data', 'DataEmissaoEmpenho', ''), ('numero', 'Empenho', 'NumeroEmpenho', 'número/ano'), ('tipo', 'Tipo', 'CategoriaEmpenho', ''),
                 ('credor', 'Credor', 'Credor', 'sem CPF no nome'), ('credor_cnpj', 'CNPJ', 'CPFCNPJ', 'só CNPJ; CPF nunca é gravado'),
                 ('unidade', 'Unidade', 'Unidade › Departamento', ''), ('acao', 'Ação', 'Acao/Descricao', ''), ('natureza', 'Natureza', 'DesdobramentoDespesa/Identificacao', ''),
                 ('modalidade', 'Modalidade', 'ModalidadeLicitacao', ''), ('empenhado', 'Empenhado', 'ValorEmpenhado − ValorAnulado', 'R$ → número'),
                 ('liquidado', 'Liquidado', 'ValorLiquidado', 'R$ → número'), ('pago', 'Pago', 'ValorPago', 'R$ → número')]),
    'diarias': dict(rotulo='Diárias', item=6, banco='ano', janela='mes', arquivo='empenhos.zip', registro='Principal', tabela='diarias',
        tela='diarias', titulo='Diárias', filtro='UnidadeGestora', de='empenhos',
        nota='Lidas do mesmo arquivo dos empenhos: entram só os empenhos com QuantidadeDiasDiarias maior que zero, ObjetivoViagem informado ou natureza de diária (3.3.90.14 civil, 3.3.90.15 militar).',
        colunas=[('data', 'Data', 'DataInicialViagem (ou DataEmissaoEmpenho)', ''), ('empenho', 'Empenho', 'NumeroEmpenho', 'número/ano'),
                 ('favorecido', 'Favorecido', 'Credor', 'sem CPF no nome'), ('unidade', 'Unidade', 'Departamento', ''),
                 ('motivo', 'Motivo', 'ObjetivoViagem + Destino', ''), ('valor', 'Valor', 'ValorTotal (ou ValorEmpenhado)', 'R$ → número')]),
    'receitas': dict(rotulo='Receitas (arrecadação)', item=3, banco='ano', janela='mes', arquivo='Arrecadacao.zip', registro='Arrecadacao', tabela='receitas',
        tela='receitas', titulo='Receitas', filtro='UnidadeGestora',
        nota='O XML traz cada arrecadação do dia; o coletor soma por mês, natureza e fonte de recurso (Mês = 1 a 12). Valores já líquidos das deduções.',
        colunas=[('ano', 'Ano', 'Exercicio', ''), ('mes', 'Mês', 'Mes', 'JANEIRO → 1'), ('codigo', 'Código', 'NaturezaCategoria/Identificacao', ''),
                 ('nome', 'Receita', 'NaturezaCategoria/Nome', ''), ('fonte_recurso', 'Fonte de recurso', 'FonteRecurso', ''),
                 ('arrecadado', 'Arrecadado', 'ValorArrecadadoLiquido', 'soma do mês')]),
    'despesas_unidade': dict(rotulo='Despesas por unidade', item=4, banco='ano', janela='ano', arquivo='Planejamento.zip', registro='Principal', tabela='despesas_unidade',
        tela='despesas', titulo='Despesas por unidade', filtro='UnidadeGestora',
        nota='O XML traz o movimento de cada mês: a dotação inicial vem em janeiro e o campo DotacaoAtualizada de cada mês é só a variação (créditos adicionais e reduções). O coletor soma o ano por unidade.',
        colunas=[('codigo', 'Código', 'Orgao', ''), ('unidade', 'Unidade orçamentária', 'Unidade › Departamento', ''),
                 ('dotacao_atualizada', 'Dotação atualizada', 'DotacaoInicial + DotacaoAtualizada', 'inicial (janeiro) + variações do ano'),
                 ('empenhado', 'Empenhado', 'ValorEmpenhado − ValorAnulado', 'soma do ano'), ('liquidado', 'Liquidado', 'ValorLiquidado', 'soma do ano'), ('pago', 'Pago', 'ValorPago', 'soma do ano')]),
    'restos_pagar': dict(rotulo='Restos a pagar', item=7, banco='ano', janela='ano', arquivo='RestosPagar.zip', registro='Principal', tabela='restos_pagar',
        tela='restos-a-pagar', titulo='Restos a pagar', filtro='UnidadeGestora',
        nota='Cada linha do XML é um movimento do resto (inscrição, liquidação, pagamento, anulação): o coletor soma por empenho. Pessoa física (CPF) fica fora da lista (LGPD).',
        colunas=[('codigo', 'Código', 'NumeroEmpenho/ano do empenho', ''), ('credor', 'Credor', 'Credor', 'sem CPF; pessoa física fora'),
                 ('empenhado', 'Inscrito', 'ValorEmpenhado − ValorAnulado', 'soma dos movimentos'), ('liquidado', 'Liquidado', 'ValorLiquidacao', 'soma dos movimentos'),
                 ('pago', 'Pago', 'ValorPago', 'soma dos movimentos')]),
    'licitacoes': dict(rotulo='Licitações', item=1, banco='adm', janela='mes', arquivo='administracao.zip', registro='ProcessoLicitatorio', tabela='licitacoes',
        tela='licitacoes', titulo='Licitações', filtro='UnidadeGestora', extra={'TipoEsportacaoDados': '2'},
        colunas=[('data', 'Data', 'DataHomologacao (ou DataJulgamento)', ''), ('numero', 'Processo', 'NumeroProcesso', ''), ('modalidade', 'Modalidade', 'Modalidade', ''),
                 ('objeto', 'Objeto', 'Objeto', ''), ('situacao', 'Situação', 'SituacaoProcesso', ''), ('valor', 'Valor', 'ValorProcesso', 'R$ → número')]),
    'contratos': dict(rotulo='Contratos', item=1, banco='adm', janela='mes', arquivo='administracao.zip', registro='ProcessoLicitatorio', tabela='contratos',
        tela='contratos', titulo='Contratos', filtro='InstrumentoContratual/UnidadeGestora', de='licitacoes', extra={'TipoEsportacaoDados': '2'},
        nota='Lidos do mesmo arquivo das licitações (InstrumentosContratuais de cada processo). O fim da vigência considera o último aditivo.',
        colunas=[('assinatura', 'Assinatura', 'InstrumentoContratual/DataEmissao', ''), ('numero', 'Contrato', 'NumeroInstrumentoContratual', ''),
                 ('fornecedor', 'Contratado', 'NomeFornecedor', 'sem CPF no nome'), ('objeto', 'Objeto', 'InstrumentoContratual/Objeto', ''),
                 ('modalidade', 'Modalidade', 'Modalidade do processo', ''), ('inicio', 'Início', 'DataEmissao', ''), ('fim', 'Fim', 'DataExpiracao (ou do último aditivo)', ''),
                 ('valor', 'Valor', 'ValorInstrumentoContratual + ValorAditivado', 'R$ → número')]),
    'servidores': dict(rotulo='Pessoal (folha)', item=8, banco='pessoal', janela='folha', arquivo='FolhaPagamento.zip', registro='*', tabela='servidores',
        tela='servidores', titulo='Pessoal e remuneração', filtro='entidades de pessoal escolhidas',
        nota='Vale a competência mais recente (até 3 meses para trás) que todas as entidades escolhidas já publicaram, para não mostrar meio quadro de pessoal. LGPD: descontos e líquido NÃO são lidos; só a remuneração bruta.',
        colunas=[('mes', 'Mês', 'Competencia', ''), ('nome', 'Nome', 'NomServidor', 'sem CPF no nome'), ('cargo', 'Cargo', 'Cargo', ''),
                 ('lotacao', 'Lotação', 'Lotacao', ''), ('proventos', 'Remuneração bruta', 'Proventos (ou VencimentosTotais)', 'R$ → número')]),
    'transferencias': dict(rotulo='Transferências (duodécimo)', item=11, banco='ano', janela='ano', arquivo='TransferenciaFinanceira.zip', registro='TransferenciaFinanceira', tabela='transferencias',
        tela='transferencias', titulo='Repasses e transferências', filtro='OrgaoRecebedor (parâmetro “recebedora”)', itens_extra=[12],
        nota='Concessão (item 11) e recebimento (item 12). “Programação Inicial” vira o previsto; “Concessão” e “Recebimento” viram o repasse; “Devolução”, a devolução.',
        colunas=[('data', 'Data', 'DataMovimento', ''), ('mes', 'Mês', 'DataMovimento', 'mês da data'), ('pagadora', 'Pagadora', 'OrgaoConcessor', ''),
                 ('recebedora', 'Recebedora', 'OrgaoRecebedor', ''), ('previsto', 'Previsto', 'ValorMovimento (Programação Inicial)', ''),
                 ('repasse', 'Repasse', 'ValorMovimento (Concessão/Recebimento)', ''), ('devolucao', 'Devolução', 'ValorMovimento (Devolução)', '')]),
}
# o que fica de fora, e por quê (aparece na tela)
FORA = [('Ordem cronológica de pagamentos', 'a GOVBR não oferece essa tela em “Exportar Dados” (só consulta na tela)'),
        ('Salários por colaborador', 'tela protegida por reCAPTCHA no portal: não é coletada'),
        ('Lançamento das receitas', 'a exportação devolve “Não há dados a serem exportados” neste portal')]
PADRAO_BASES = {'executivo': ['receitas', 'despesas_unidade', 'empenhos', 'diarias', 'restos_pagar', 'licitacoes', 'contratos', 'servidores', 'transferencias'],
                'legislativo': ['transferencias']}

# ---------- conversões ----------
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()

def valor(v):
    """'R$ 1.234,56' / 'R$ -40.000,00' / ' ' → float ou None."""
    s = str(v or '').replace('R$', '').replace('\xa0', '').strip()
    if not s:
        return None
    return comum.num(s)

def mes_num(v):
    s = norm(v).upper()
    for i, m in enumerate(MESES, 1):
        if norm(m).upper() == s:
            return i
    return int(s) if s.isdigit() and 1 <= int(s) <= 12 else 0

def lista(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in str(v or '').split(',') if x.strip()]

def t(e, caminho):
    return txt(e.findtext(caminho) if e is not None else '')

def liq(x):
    """Liquidado da linha: os arquivos da GOVBR usam ValorLiquidado (empenhos, despesas) ou ValorLiquidacao (restos a pagar)."""
    return valor(x.findtext('ValorLiquidado')) or valor(x.findtext('ValorLiquidacao')) or 0

def da_unidade(p, nome):
    """O registro é de uma das unidades gestoras do órgão? (vazio = todas)."""
    us = [norm(u) for u in lista(p.get('unidades'))]
    return not us or any(u in norm(nome) for u in us)

# ---------- HTTP (um cliente por execução: a tela guarda o cookie de sessão do portal) ----------
class Portal:
    def __init__(self, base):
        self.base = base.rstrip('/') + '/'
        self.c = httpx.Client(timeout=180, follow_redirects=True, headers={'User-Agent': config.USER_AGENT})
        self.telas = {}

    def fechar(self):
        self.c.close()

    def _get(self, caminho, params=None):
        espera = comum.INTERVALO * 2 - (time.monotonic() - comum._ultimo.get(FONTE, 0))  # 1 pedido a cada 2 s
        if espera > 0:
            time.sleep(espera)
        comum._ultimo[FONTE] = time.monotonic()
        return self.c.get(self.base + caminho, params=params)

    def tela(self, item):
        """HTML da tela "Exportar Dados" (item N): de onde saem os códigos dos bancos."""
        if item not in self.telas:
            r = self._get('index.asp', {'acao': 10, 'item': item})
            r.raise_for_status()
            self.telas[item] = r.content.decode('latin-1', 'replace')
        return self.telas[item]

    def opcoes(self, item, combo):
        m = re.search(r'<select name="%s".*?</select>' % combo, self.tela(item), re.S)
        return [(a, re.sub(r'\s+', ' ', b).strip()) for a, b in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', m.group(0))] if m else []

    def banco(self, d, ano):
        if d['banco'] == 'ano':
            for v, _ in self.opcoes(d['item'], 'cmbAno'):
                if v.startswith(f'{ano}|'):
                    return v.split('|')[1]
            raise LookupError(f'o portal não oferece o ano {ano} na tela de exportação (item {d["item"]})')
        if d['banco'] == 'adm':
            ops = [v for v, _ in self.opcoes(d['item'], 'cmbUnidadeLC') if v]
            if not ops:
                raise LookupError('o portal não oferece a entidade de licitações na tela de exportação')
            return ops[0]
        raise ValueError(d['banco'])

    def exportar(self, item, banco, ano, ini, fim, extra=None):
        """Pede a exportação e devolve a raiz do XML, ou None se o portal disser que não há dados."""
        q = {'item': item, 'banco': banco, 'exercicio': ano, 'dataInicial': ini.strftime('%Y%m%d'), 'dataFinal': fim.strftime('%Y%m%d'),
             'unidadeGestora': -1, 'nmFornecedor': '', **(extra or {})}
        t0 = time.monotonic()
        r = self._get('geraxml.asp', q)
        ms = int((time.monotonic() - t0) * 1000)
        m = re.search(r"href='(dll/[\w.-]+\.zip)'", r.text or '')
        if not m:
            erro = r.headers.get('ERRO') or ''
            if r.status_code == 200 and 'dados a serem exportados' in erro.lower():
                comum.anotar(FONTE, self.base + 'geraxml.asp', q, r.status_code, ms, [], erro='')
                return None
            comum.anotar(FONTE, self.base + 'geraxml.asp', q, r.status_code, ms, erro=erro or 'resposta sem link do arquivo')
            raise RuntimeError(f'item {item}: o portal não gerou o arquivo ({erro or f"HTTP {r.status_code}"})')
        t0 = time.monotonic()
        z = self._get(m.group(1))
        z.raise_for_status()
        if len(z.content) > MAX_ZIP:
            raise RuntimeError(f'arquivo {m.group(1)} maior que o limite ({len(z.content) // 1048576} MB)')
        zf = zipfile.ZipFile(io.BytesIO(z.content))
        nomes = [n for n in zf.namelist() if n.lower().endswith('.xml')]
        if not nomes or zf.getinfo(nomes[0]).file_size > MAX_XML:
            raise RuntimeError('ZIP sem XML ou XML grande demais')
        bruto = zf.read(nomes[0])
        if b'<!DOCTYPE' in bruto[:4096] or b'<!ENTITY' in bruto[:4096]:
            raise RuntimeError('XML com DOCTYPE/ENTITY recusado')
        raiz = ET.fromstring(bruto)
        regs = list(raiz)
        # amostra para a tela: os 2 primeiros registros, sem descontos/líquido da folha nem documentos (LGPD)
        amostra = [{e.tag: (e.text or '').strip() for e in x if not len(e) and e.tag not in OCULTOS} for x in regs[:2]]
        comum.anotar(FONTE, self.base + 'geraxml.asp', dict(q, arquivo=m.group(1)), r.status_code, int((time.monotonic() - t0) * 1000) + ms,
                     amostra + ([{}] * max(0, len(regs) - 2)))
        return raiz

def meses_da_execucao(hoje, ano, completa, recentes):
    """Lista de (início, fim) mês a mês: o ano todo (completa) ou só os últimos meses (rápida)."""
    ult = hoje.month if ano == hoje.year else 12
    prim = 1 if completa else max(1, ult - max(1, min(3, int(recentes or 2))) + 1)
    out = []
    for m in range(prim, ult + 1):
        ini = date(ano, m, 1)
        fim = (date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        out.append((ini, min(fim, hoje)))
    return out

def baixar(pt, d, ano, periodos):
    """Junta os registros de todos os períodos (um pedido por período). Confere o exercício de cada registro."""
    banco = pt.banco(d, ano)
    regs = []
    for item in [d['item']] + d.get('itens_extra', []):
        for ini, fim in periodos:
            raiz = pt.exportar(item, banco, ano, ini, fim, d.get('extra'))
            if raiz is None:
                continue
            for x in raiz:
                ex = x.findtext('Exercicio')
                if ex and ex.strip() and ex.strip() != str(ano):
                    raise RuntimeError(f'o arquivo veio de outro exercício ({ex.strip()}); outro pedido simultâneo no portal? tente de novo')
                x.set('_item', str(item))
                regs.append(x)
    return regs

# ---------- montagem das linhas de cada tabela ----------
def _unidade(x):
    u, dep = t(x, 'Unidade'), t(x, 'Departamento')
    return f'{u} › {dep}' if dep and dep != u else u

def linhas_empenhos(regs, p, ano):
    L = []
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')):
            continue
        doc = t(x, 'CPFCNPJ')
        emp = (valor(x.findtext('ValorEmpenhado')) or 0) - (valor(x.findtext('ValorAnulado')) or 0)
        L.append({'chave': chave('gemp', ano, t(x, 'UnidadeGestora'), t(x, 'NumeroEmpenho'), t(x, 'CategoriaEmpenho')), 'fonte': FONTE, 'ano': ano,
                  'pk': txt(t(x, 'NumeroEmpenho'), 20), 'numero': f"{txt(t(x, 'NumeroEmpenho'), 12)}/{ano}", 'tipo': txt(t(x, 'CategoriaEmpenho'), 4),
                  'data': data_br(t(x, 'DataEmissaoEmpenho')), 'credor': txt(sem_cpf(t(x, 'Credor')), 200), 'credor_cnpj': doc_pj(doc),
                  'unidade': txt(_unidade(x), 200), 'funcao': txt(t(x, 'Funcao'), 120), 'programa': txt(t(x, 'Programa'), 200),
                  'acao': txt(t(x, 'Acao/Descricao'), 200), 'natureza': txt(t(x, 'DesdobramentoDespesa/Identificacao'), 40),
                  'fonte_recurso': txt(t(x, 'FonteRecurso/Descricao'), 120), 'vinculo': txt(t(x, 'FonteRecurso/Identificacao'), 20),
                  'vinculo_nome': txt(t(x, 'FonteRecurso/Descricao'), 120), 'modalidade': txt(t(x, 'ModalidadeLicitacao'), 60),
                  'processo': txt(t(x, 'ProcessoCompra') or t(x, 'NumeroLicitacao'), 40), 'empenhado': emp,
                  'liquidado': liq(x), 'pago': valor(x.findtext('ValorPago')) or 0})
    return L

NATUREZA_DIARIAS = ('3.3.90.14', '3.3.90.15', '3.1.90.14', '3.1.90.15')  # diárias civil e militar

def eh_diaria(x):
    """Empenho de diária: com dias de viagem (> 0), objetivo de viagem informado ou natureza de diária.
    Alguns portais mandam QuantidadeDiasDiarias = 0.0000 em TODOS os empenhos: campo preenchido não basta."""
    return ((valor(x.findtext('QuantidadeDiasDiarias')) or 0) > 0 or bool(t(x, 'ObjetivoViagem'))
            or t(x, 'DesdobramentoDespesa/Identificacao').startswith(NATUREZA_DIARIAS) or t(x, 'ElementoDespesa/Identificacao').startswith(NATUREZA_DIARIAS))

def linhas_diarias(regs, p, ano):
    L = []
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')) or not eh_diaria(x):
            continue
        motivo = ' — '.join(v for v in (t(x, 'ObjetivoViagem'), t(x, 'Destino')) if v)
        L.append({'chave': chave('gdia', ano, t(x, 'UnidadeGestora'), t(x, 'NumeroEmpenho')), 'fonte': FONTE, 'ano': ano,
                  'empenho': f"{txt(t(x, 'NumeroEmpenho'), 12)}/{ano}", 'data': data_br(t(x, 'DataInicialViagem')) or data_br(t(x, 'DataEmissaoEmpenho')),
                  'favorecido': txt(sem_cpf(t(x, 'Credor')), 200), 'cargo': '', 'unidade': txt(t(x, 'Departamento') or t(x, 'Unidade'), 200),
                  'motivo': txt(motivo, 600), 'valor': valor(x.findtext('ValorTotal')) or valor(x.findtext('ValorEmpenhado')),
                  'anulado': valor(x.findtext('ValorAnulado'))})
    return L

def linhas_receitas(regs, p, ano):
    soma = {}
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')):
            continue
        m = mes_num(t(x, 'Mes')) or ((data_br(t(x, 'DataArrecadacao')) or date(ano, 1, 1)).month)
        k = (m, t(x, 'NaturezaCategoria/Identificacao'), t(x, 'FonteRecurso'))
        r = soma.setdefault(k, {'chave': chave('grec', ano, *k), 'fonte': FONTE, 'ano': ano, 'mes': m, 'codigo': txt(k[1], 40),
                                'nome': txt(t(x, 'NaturezaCategoria/Nome'), 300), 'fonte_recurso': txt(k[2], 200),
                                'previsto': None, 'atualizado': None, 'arrecadado': 0.0, 'soma': True})
        r['arrecadado'] += valor(x.findtext('ValorArrecadadoLiquido')) or 0
    return list(soma.values())

def linhas_despesas_unidade(regs, p, ano):
    soma = {}
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')):
            continue
        k = (t(x, 'Orgao'), _unidade(x))
        r = soma.setdefault(k, {'chave': chave('gdu', ano, *k), 'fonte': FONTE, 'ano': ano, 'codigo': txt(k[0], 20), 'unidade': txt(k[1], 200),
                                'dotacao': 0.0, 'dotacao_atualizada': 0.0, 'empenhado': 0.0, 'liquidado': 0.0, 'pago': 0.0})
        # DotacaoInicial vem só em janeiro; DotacaoAtualizada de cada mês é a VARIAÇÃO (créditos adicionais e reduções)
        r['dotacao'] += valor(x.findtext('DotacaoInicial')) or 0
        r['dotacao_atualizada'] += (valor(x.findtext('DotacaoInicial')) or 0) + (valor(x.findtext('DotacaoAtualizada')) or 0)
        r['empenhado'] += (valor(x.findtext('ValorEmpenhado')) or 0) - (valor(x.findtext('ValorAnulado')) or 0)
        r['liquidado'] += liq(x)
        r['pago'] += valor(x.findtext('ValorPago')) or 0
    return list(soma.values())

def linhas_restos_pagar(regs, p, ano):
    """Cada linha do XML é um MOVIMENTO do resto (inscrição, liquidação, pagamento, anulação): soma por empenho."""
    soma = {}
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')) or eh_pessoa_fisica(t(x, 'CPFCNPJ')):
            continue  # pessoa física fica fora da lista (LGPD)
        de = data_br(t(x, 'DataEmissaoEmpenho'))
        cod = f"{t(x, 'NumeroEmpenho')}/{de.year if de else ''}"
        k = (t(x, 'UnidadeGestora'), cod)
        r = soma.setdefault(k, {'chave': chave('grp', ano, *k), 'fonte': FONTE, 'ano': ano, 'codigo': txt(cod, 20),
                                'credor': txt(sem_cpf(t(x, 'Credor')), 200), 'empenhado': 0.0, 'liquidado': 0.0, 'pago': 0.0})
        r['empenhado'] += (valor(x.findtext('ValorEmpenhado')) or 0) - (valor(x.findtext('ValorAnulado')) or 0)
        r['liquidado'] += liq(x)
        r['pago'] += valor(x.findtext('ValorPago')) or 0
    return list(soma.values())

def linhas_licitacoes(regs, p, ano):
    L = []
    for x in regs:
        if not da_unidade(p, t(x, 'UnidadeGestora')):
            continue
        L.append({'chave': chave('glic', ano, t(x, 'UnidadeGestora'), t(x, 'NumeroProcesso'), t(x, 'Modalidade')), 'fonte': FONTE, 'ano': ano,
                  'numero': txt(t(x, 'NumeroProcesso'), 30), 'modalidade': txt(t(x, 'Modalidade'), 60), 'objeto': txt(t(x, 'Objeto'), 800),
                  'situacao': txt(t(x, 'SituacaoProcesso'), 60), 'data': data_br(t(x, 'DataHomologacao')) or data_br(t(x, 'DataJulgamento')),
                  'valor': valor(x.findtext('ValorProcesso')), 'unidade': txt(t(x, 'UnidadeGestora'), 120), 'link': ''})
    return L

def linhas_contratos(regs, p, ano):
    L = []
    for x in regs:
        for c in x.iter('InstrumentoContratual'):
            if not da_unidade(p, t(c, 'UnidadeGestora') or t(x, 'UnidadeGestora')):
                continue
            adit = list(c.iter('Aditivo'))
            fins = [d for d in [data_br(t(c, 'DataExpiracao'))] + [data_br(t(a, 'DataExpiracao')) for a in adit] if d]
            v = valor(c.findtext('ValorInstrumentoContratual'))
            if v is not None:
                v += sum(valor(a.findtext('ValorAditivado')) or 0 for a in adit)
            L.append({'chave': chave('gct', ano, t(c, 'UnidadeGestora'), t(c, 'NumeroInstrumentoContratual'), t(x, 'NumeroProcesso')), 'fonte': FONTE, 'ano': ano,
                      'numero': txt(t(c, 'NumeroInstrumentoContratual'), 30), 'fornecedor': txt(sem_cpf(t(c, 'NomeFornecedor')), 200),
                      'objeto': txt(t(c, 'Objeto') or t(x, 'Objeto'), 800), 'modalidade': txt(t(x, 'Modalidade'), 60), 'processo': txt(t(x, 'NumeroProcesso'), 30),
                      'assinatura': data_br(t(c, 'DataEmissao')), 'inicio': data_br(t(c, 'DataEmissao')), 'fim': max(fins) if fins else None,
                      'unidade': txt(t(c, 'UnidadeGestora') or t(x, 'UnidadeGestora'), 200), 'valor': v, 'empenhado': None, 'liquidado': None})
    return L

def _grupo(tipo):
    return 'prev' if 'programacao' in tipo else 'dev' if 'devolu' in tipo else 'rep'

def linhas_transferencias(regs, p, ano):
    """Concessão (item 11) e recebimento (item 12) podem trazer o MESMO movimento visto dos dois lados: um movimento só conta
    uma vez (para cada movimento igual, vale o maior número de ocorrências entre os dois itens)."""
    from collections import Counter
    filtro = norm(p.get('recebedora', ''))
    por_item, exemplo = {}, {}
    for x in regs:
        if filtro and filtro not in norm(t(x, 'OrgaoRecebedor')):
            continue
        k = (_grupo(norm(t(x, 'TipoMovimento'))), t(x, 'DataMovimento'), t(x, 'OrgaoConcessor'), t(x, 'OrgaoRecebedor'), valor(x.findtext('ValorMovimento')))
        por_item.setdefault(x.get('_item'), Counter())[k] += 1
        exemplo[k] = x
    total = Counter()
    for c in por_item.values():
        for k, n in c.items():
            total[k] = max(total[k], n)
    L = []
    for k, n in total.items():
        g, _, pag, rec, v = k
        d = data_br(k[1])
        for i in range(n):
            L.append({'chave': chave('gtr', ano, *k, i), 'fonte': FONTE, 'ano': ano, 'mes': d.month if d else None, 'data': d,
                      'pagadora': txt(pag, 200), 'recebedora': txt(rec, 200), 'previsto': v if g == 'prev' else None,
                      'repasse': v if g == 'rep' else None, 'devolucao': v if g == 'dev' else None})
    return L

def linhas_servidores(regs, p, ano, mes):
    L = []
    for x in regs:
        # LGPD: só nome, cargo, lotação e remuneração bruta. Descontos e líquido não são lidos.
        nome = txt(sem_cpf(t(x, 'NomServidor')), 200)
        if not nome:
            continue
        L.append({'chave': chave('gsrv', ano, mes, x.get('_entidade', ''), nome, t(x, 'Cargo'), t(x, 'Lotacao')), 'fonte': FONTE, 'ano': ano, 'mes': mes,
                  'registro': txt(t(x, 'Matricula'), 20), 'nome': nome, 'cargo': txt(t(x, 'Cargo'), 120), 'vinculo': '', 'lotacao': txt(t(x, 'Lotacao'), 200), 'admissao': None,
                  'proventos': valor(x.findtext('Proventos')) if valor(x.findtext('Proventos')) is not None else valor(x.findtext('VencimentosTotais'))})
    return L

MONTA = {'empenhos': linhas_empenhos, 'diarias': linhas_diarias, 'receitas': linhas_receitas, 'despesas_unidade': linhas_despesas_unidade,
         'restos_pagar': linhas_restos_pagar, 'licitacoes': linhas_licitacoes, 'contratos': linhas_contratos, 'transferencias': linhas_transferencias}

# ---------- API de dados abertos da GOVBR (só alguns portais têm: …/dadosabertos/, com Swagger) ----------
# Cobre só receitas, despesas (empenhos e diárias) e pessoal (folha). As demais bases vêm sempre do XML.
PAGINA = 200          # registros por página na API
MAX_PAGINAS = 500     # trava contra laço sem fim
API = {
    'receitas': dict(rota='Receitas/buscarDadosReceitas/{ano}/{pagina}/{entidade}', q={'unidadeGestora': '{cada unidade gestora do órgão}'}, area='Financeira',
        obrig=('Exercicio', 'ValorArrecadadoLiquido'), nota='A API traz também a previsão da receita (o XML não traz). Lê o exercício inteiro em toda execução, 200 registros por página.',
        colunas={'ano': 'Exercicio', 'mes': 'Mes', 'codigo': 'SubAlinea › Alinea › Rubrica › Especie › Origem (o nível mais detalhado preenchido)',
                 'nome': 'ds… do mesmo nível (ex.: dsAlinea)', 'fonte_recurso': 'FonteRecurso', 'arrecadado': 'ValorArrecadadoLiquido'}),
    'empenhos': dict(rota='Despesas/buscarDadosDespesas/{ano}/{pagina}/{entidade}', q={'unidadeGestora': '{cada unidade gestora do órgão}'}, area='Financeira',
        obrig=('NumeroEmpenho', 'ValorEmpenhado'), nota='Mesmos campos da exportação XML. Lê o exercício inteiro em toda execução, 200 registros por página.', colunas={}),
    'diarias': dict(rota='Despesas/buscarDadosDespesas/{ano}/{pagina}/{entidade}', q={'unidadeGestora': '{cada unidade gestora do órgão}'}, area='Financeira',
        obrig=('NumeroEmpenho', 'ValorEmpenhado'), de='empenhos', nota='Lidas da mesma resposta dos empenhos (consulta feita uma vez só).', colunas={}),
    'servidores': dict(rota='FolhaPagamento', q={'dataInicial': '{1º dia do mês, dd/mm/aaaa}', 'dataFinal': '{último dia do mês, dd/mm/aaaa}', 'numeroPagina': '{1, 2, …}',
                                                 'nomeBase': '{entidade de pessoal}'}, area='GestaoPessoas', obrig=('NomeServidor',),
        nota='LGPD: CPF, descontos e líquido vêm na API e são descartados antes de qualquer gravação.',
        colunas={'mes': 'Competencia', 'nome': 'NomeServidor', 'cargo': 'Cargo', 'lotacao': 'Lotacao', 'proventos': 'Proventos (ou VencimentosTotais)'}),
}
MODOS = {'auto': 'Automático: API; se falhar, XML', 'api': 'Só API', 'xml': 'Só XML (exportação)'}
DESCARTAR = {'CPF', 'CPFCNPJ', 'Descontos', 'Liquido'}  # campos da API de pessoal que nunca passam adiante

class ApiErro(Exception):
    """A API não existe, respondeu erro (mesmo com HTTP 200) ou mandou um formato que o coletor não reconhece."""

class Api:
    def __init__(self, base):
        self.base = base.rstrip('/') + '/'
        self.c = httpx.Client(timeout=180, follow_redirects=True, headers={'User-Agent': config.USER_AGENT, 'Accept': 'application/json'})

    def fechar(self):
        self.c.close()

    def _raw(self, caminho, params=None):
        espera = comum.INTERVALO * 2 - (time.monotonic() - comum._ultimo.get(FONTE, 0))
        if espera > 0:
            time.sleep(espera)
        comum._ultimo[FONTE] = time.monotonic()
        r = self.c.get(self.base + caminho, params=params)
        return r.status_code, r.text

    def get(self, caminho, params=None, amostra=True):
        """GET na API. A GOVBR às vezes devolve o JSON dentro de uma string, e às vezes um erro do servidor como texto com HTTP 200."""
        t0 = time.monotonic()
        try:
            st, texto = self._raw(caminho, params)
        except httpx.HTTPError as e:
            raise ApiErro(f'sem resposta da API ({type(e).__name__})')
        ms = int((time.monotonic() - t0) * 1000)
        url = self.base + caminho
        try:
            d = json.loads(texto) if texto.strip() else None
            if isinstance(d, str) and d.strip()[:1] in '[{':
                d = json.loads(d)
        except ValueError:
            d = texto
        if st >= 400 or d is None or isinstance(d, str):
            msg = (d.get('errors') or d.get('title')) if isinstance(d, dict) else (d or '').strip().splitlines()[0] if d else ''
            comum.anotar(FONTE, url, params, st, ms, erro=f'API: {str(msg)[:150]}')
            raise ApiErro(f'HTTP {st}' + (f': {str(msg)[:160]}' if msg else ' sem conteúdo'))
        if amostra:
            linhas = d if isinstance(d, list) else [d]
            limpo = [{k: v for k, v in x.items() if k not in OCULTOS and k not in DESCARTAR} if isinstance(x, dict) else x for x in linhas[:2]]
            comum.anotar(FONTE, url, params, st, ms, limpo + [{}] * max(0, len(linhas) - 2))
        return d

    def entidades(self, ano, area):
        d = self.get(f'dbdestino/buscarEntidadesArea{area}/{ano}')
        return [str(x) for x in d] if isinstance(d, list) else []

    def unidades(self, ano, entidade):
        d = self.get(f'unidadeGestora/buscarUnidadesGestoras/{ano}/{entidade}')
        return [x.get('ds_UnidadeGestora', '') for x in d if isinstance(x, dict)] if isinstance(d, list) else []

    def paginas(self, rota, params, obrig, exercicio=None, pagina_na_rota=True, **fmt):
        """Todas as páginas (200 registros cada) até vir uma página incompleta. No teste (ensaio), só a primeira."""
        out = []
        for pg in range(1, MAX_PAGINAS + 1):
            caminho = rota.format(pagina=pg, **fmt) if pagina_na_rota else rota
            q = dict(params) if pagina_na_rota else dict(params, numeroPagina=pg)
            d = self.get(caminho, q, amostra=pg == 1)
            if not isinstance(d, list):
                raise ApiErro('formato não reconhecido (esperava uma lista)')
            for x in d:
                if not isinstance(x, dict) or any(k not in x for k in obrig):
                    raise ApiErro(f'formato não reconhecido (faltam campos: {", ".join(k for k in obrig if not isinstance(x, dict) or k not in x)})')
                if exercicio and x.get('Exercicio') not in (None, '') and str(x['Exercicio']) != str(exercicio):
                    raise ApiErro(f'a API devolveu outro exercício ({x["Exercicio"]})')
            out += d
            if len(d) < PAGINA or db.ENSAIO.get() is not None:
                return out, pg
        raise ApiErro(f'mais de {MAX_PAGINAS} páginas: consulta interrompida')

def elem(d, tag='r'):
    """Registro da API (dict) → elemento no formato do XML, para as mesmas regras de montagem valerem nos dois caminhos."""
    e = ET.Element(tag)
    for k, v in d.items():
        if v is None or isinstance(v, list) or k in DESCARTAR:
            continue
        if isinstance(v, dict):
            e.append(elem(v, k))
        else:
            ET.SubElement(e, k).text = str(v)
    return e

NIVEIS = ('SubAlinea', 'Alinea', 'Rubrica', 'Especie', 'Origem', 'CategoriaEconomica')

def linhas_receitas_api(regs, p, ano):
    soma = {}
    for x in regs:
        if not da_unidade(p, x.get('UnidadeGestora')):
            continue
        nivel = next((n for n in NIVEIS if str(x.get(n) or '').strip()), 'CategoriaEconomica')
        codigo = str(x.get(nivel) or '').strip()
        nome = next((str(x.get('ds' + n)).strip() for n in NIVEIS[NIVEIS.index(nivel):] if str(x.get('ds' + n) or '').strip()), codigo)
        m = mes_num(x.get('Mes')) or ((data_br(x.get('DataArrecadacao')) or date(ano, 1, 1)).month)
        k = (m, codigo, txt(x.get('FonteRecurso')))
        r = soma.setdefault(k, {'chave': chave('grec', ano, *k), 'fonte': FONTE, 'ano': ano, 'mes': m, 'codigo': txt(codigo, 40), 'nome': txt(nome, 300),
                                'fonte_recurso': txt(k[2], 200), 'previsto': 0.0, 'atualizado': None, 'arrecadado': 0.0, 'soma': True})
        r['previsto'] += valor(x.get('ValorPrevistoLiquido')) or 0
        r['arrecadado'] += valor(x.get('ValorArrecadadoLiquido')) or 0
    return list(soma.values())

def unidades_api(api, p, ano, ent):
    todas = api.unidades(ano, ent)
    sel = [u for u in todas if da_unidade(p, u)]
    if not sel:
        raise ApiErro(f"nenhuma unidade gestora da API confere com “{p.get('unidades')}”; a API oferece: {', '.join(todas) or 'nenhuma'}")
    return sel

def via_api(api, orgao, p, base, ano, hoje, cache):
    """Coleta uma base pela API. Devolve (registros, mensagem) ou levanta ApiErro."""
    d = API[base]
    if base == 'servidores':
        return folha_api(api, orgao, p, ano, hoje)
    ent = p.get('api_entidade') or next(iter(api.entidades(ano, d['area'])), '')
    if not ent:
        raise ApiErro('a API não oferece entidade para este exercício')
    k = ('api', d['rota'], ent)
    if k not in cache:
        regs, pgs = [], 0
        for ug in unidades_api(api, p, ano, ent):
            r, n = api.paginas(d['rota'], {'unidadeGestora': ug}, d['obrig'], exercicio=ano, ano=ano, entidade=ent)
            regs += r; pgs += n
        cache[k] = (regs, pgs)
    regs, pgs = cache[k]
    L = linhas_receitas_api(regs, p, ano) if base == 'receitas' else MONTA[base]([elem(x) for x in regs], p, ano)
    n = gravar(orgao['banco'], BASES[base]['tabela'], L, {'ano': ano}, FONTE)
    return n, f'{n} registros de {ano} ({pgs} página(s) da API)'

def folha_api(api, orgao, p, ano, hoje):
    """Folha pela API, com a mesma regra do XML: a competência mais recente (até 3 meses) que todas as entidades já publicaram."""
    ents = lista(p.get('api_pessoal')) or api.entidades(ano, 'GestaoPessoas')
    if not ents:
        raise ApiErro('a API não oferece entidades de pessoal')
    mes = hoje.month if ano == hoje.year else 12
    melhor, erro, respondeu = None, None, False
    for m in range(mes, max(0, mes - 3), -1):
        ini = date(ano, m, 1); fim = date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        regs, com = [], 0
        for e in ents:
            try:
                r, _ = api.paginas('FolhaPagamento', {'dataInicial': ini.strftime('%d/%m/%Y'), 'dataFinal': fim.strftime('%d/%m/%Y'), 'nomeBase': e},
                                   API['servidores']['obrig'], pagina_na_rota=False)
                respondeu = True
            except ApiErro as x:  # a API responde erro também para mês sem folha: só conta como falha se nenhum pedido der certo
                erro = x; continue
            if r:
                com += 1
                for x in r:
                    el = elem({('NomServidor' if k == 'NomeServidor' else k): v for k, v in x.items()})
                    el.set('_entidade', e); regs.append(el)
        if regs and (melhor is None or com > melhor[1]):
            melhor = (m, com, regs)
        if com == len(ents):
            break
    if not melhor:
        if not respondeu and erro:
            raise erro
        return 0, f'nenhuma folha publicada de {max(1, mes - 2):02d}/{ano} a {mes:02d}/{ano}'
    m, com, regs = melhor
    L = linhas_servidores(regs, p, ano, m)
    falta = '' if com == len(ents) else f'; só {com} de {len(ents)} entidade(s) já publicaram'
    return gravar(orgao['banco'], 'servidores', L, {'ano': ano, 'mes': m}, FONTE), f'folha de {m:02d}/{ano} ({com} entidade(s){falta})'

def modo_de(p, base):
    """Caminho escolhido para a base: só as bases que a API cobre podem usar a API."""
    if base not in API:
        return 'xml'
    m = (p.get('modos') or {}).get(base, 'auto')
    return m if m in MODOS else 'auto'

# ---------- execução ----------
def completa_agora(orgao, base):
    """Uma execução a cada 24 horas (de cada base) relê o ano inteiro; as demais, só os últimos meses. No teste, só o mês atual."""
    if db.ENSAIO.get() is not None:
        return False
    return not db.um(db.LOCAL, "SELECT 1 FROM coletas WHERE orgao_slug=%s AND fonte=%s AND ok AND mensagem LIKE %s AND inicio > now() - interval '24 hours'",
                     (orgao['slug'], f'{FONTE}:{base}', '%completa%'))

def servidores(pt, orgao, p, ano, hoje):
    """Cada entidade de pessoal publica a folha no seu ritmo: vale a competência mais recente (até 3 meses para trás) que TODAS
    as entidades escolhidas já publicaram — assim o portal nunca mostra meio quadro de pessoal. Se nenhuma servir, a que tiver mais entidades."""
    ents = lista(p.get('pessoal')) or [v for v, _ in pt.opcoes(8, 'cmbUnidadeAR') if v]
    if not ents:
        raise LookupError('o portal não oferece entidades de pessoal na tela de exportação')
    mes = hoje.month if ano == hoje.year else 12
    melhor = None
    for m in range(mes, max(0, mes - 3), -1):
        ini = date(ano, m, 1); fim = date(ano + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        regs, com = [], 0
        for e in ents:
            raiz = pt.exportar(8, e, ano, ini, fim)
            if raiz is not None and len(raiz):
                com += 1
                for x in raiz:
                    x.set('_entidade', e); regs.append(x)
        if regs and (melhor is None or com > melhor[1]):
            melhor = (m, com, regs)
        if com == len(ents):
            break
    if not melhor:
        return 0, f'nenhuma folha publicada de {max(1, mes - 2):02d}/{ano} a {mes:02d}/{ano}'
    m, com, regs = melhor
    L = linhas_servidores(regs, p, ano, m)
    falta = '' if com == len(ents) else f'; só {com} de {len(ents)} entidade(s) já publicaram'
    return gravar(orgao['banco'], 'servidores', L, {'ano': ano, 'mes': m}, FONTE), f'folha de {m:02d}/{ano} ({com} entidade(s){falta})'

def via_xml(pt, orgao, p, base, ano, hoje, cache, forcar_completa=False):
    d = BASES[base]
    if base == 'servidores':
        return servidores(pt, orgao, p, ano, hoje)
    completa = d['janela'] == 'ano' or ((forcar_completa or completa_agora(orgao, base)) and db.ENSAIO.get() is None)  # o teste lê só o mês atual
    recentes = 1 if db.ENSAIO.get() is not None else p.get('meses_recentes', 2)  # o teste lê só o mês atual
    periodos = [(date(ano, 1, 1), hoje if ano == hoje.year else date(ano, 12, 31))] if d['janela'] == 'ano' \
        else meses_da_execucao(hoje, ano, completa, recentes)
    fonte_arq = d.get('de', base)
    k = (fonte_arq, tuple(periodos))
    if k not in cache:
        cache[k] = baixar(pt, BASES[fonte_arq], ano, periodos)
    L = MONTA[base](cache[k], p, ano)
    if completa:
        n = gravar(orgao['banco'], d['tabela'], L, {'ano': ano}, FONTE)  # ano inteiro: o que sumiu da fonte sai daqui também
    elif base == 'receitas':
        n = sum(gravar(orgao['banco'], 'receitas', [x for x in L if x['mes'] == m], {'ano': ano, 'mes': m}, FONTE) for m in sorted({x['mes'] for x in L}))
    else:
        n = gravar(orgao['banco'], d['tabela'], L, None, FONTE)
    return n, f"{'completa' if completa else 'rápida'}: {n} registros de {ano} ({len(periodos)} período(s) lido(s))"

def coletar(orgao, p, hoje=None):
    """Roda as bases configuradas. Devolve [(base, ok, registros, mensagem)]; a falha de uma base não para as outras.
    Cada base segue o caminho escolhido no painel (automático, só API ou só XML). No automático, se a API falhar, a base vem do XML
    nessa execução, relendo o ano inteiro (para não misturar códigos dos dois caminhos). Bases do mesmo arquivo/consulta baixam uma vez só."""
    hoje = hoje or config.hoje()
    ano = hoje.year
    if not p.get('base'):
        return [('config', False, 0, 'endereço do portal não configurado')]
    pt = Portal(p['base'])
    api = Api(p['api']) if p.get('api') else None
    res, cache = [], {}
    try:
        for base in p.get('bases', []):
            if base not in BASES:
                continue
            modo = modo_de(p, base)
            try:
                aviso = ''
                if modo in ('api', 'auto') and api:
                    try:
                        n, msg = via_api(api, orgao, p, base, ano, hoje, cache)
                        res.append((base, True, n, f'via API: {msg}')); continue
                    except ApiErro as e:
                        if modo == 'api':
                            raise
                        aviso = f'API falhou ({str(e)[:160]}); usado o XML — '
                elif modo == 'api':
                    raise ApiErro('endereço da API não configurado')
                n, msg = via_xml(pt, orgao, p, base, ano, hoje, cache, forcar_completa=bool(aviso))
                res.append((base, True, n, f'{aviso}via XML: {msg}'))
            except Exception as e:
                res.append((base, False, 0, f'{type(e).__name__}: {e}'))
    finally:
        pt.fechar()
        if api:
            api.fechar()
    return res

# ---------- descrição para a tela "Como a consulta é montada" ----------
def endpoints(p):
    base = (p.get('base') or '{base}').rstrip('/') + '/'
    ano = config.hoje().year
    out = []
    for k in p.get('bases') or []:
        d = BASES.get(k)
        if not d:
            continue
        if k == 'servidores':
            q = {'item': 8, 'banco': ', '.join(lista(p.get('pessoal'))) or '{cada entidade de pessoal da tela}', 'exercicio': ano,
                 'dataInicial': '{1º dia do mês}', 'dataFinal': '{último dia do mês}', 'unidadeGestora': -1}
        else:
            per = ('{01/01} → {hoje}' if d['janela'] == 'ano' else '{1º dia do mês} → {último dia do mês}, um pedido por mês')
            q = {'item': d['item'] if not d.get('itens_extra') else f"{d['item']} e {', '.join(map(str, d['itens_extra']))}",
                 'banco': '{código do ano ' + str(ano) + ', lido na tela}' if d['banco'] == 'ano' else '{entidade de licitações, lida na tela}',
                 'exercicio': ano, 'dataInicial / dataFinal': per, 'unidadeGestora': -1, **(d.get('extra') or {})}
        modo = modo_de(p, k)
        if modo != 'xml' and k in API:
            a = API[k]
            api = (p.get('api') or '{endereço da API — não configurado}').rstrip('/') + '/'
            qa = dict(a['q'], **({'entidade': p.get('api_entidade') or '{a primeira oferecida pela API}'} if '{entidade}' in a['rota'] else {}))
            out.append((f"{d['rotulo']} — API ({MODOS[modo]})", 'GET', api + a['rota'].replace('{ano}', str(ano)), qa, ''))
        out.append((d['rotulo'] + (' — XML' if k in API and modo != 'xml' else ''), 'GET', f'{base}geraxml.asp  →  {base}dll/{d["arquivo"]}', q, k))
    return out

def telas(p):
    """Para cada base escolhida: a tela do portal que ela alimenta, o arquivo, o filtro e coluna por coluna de onde vem cada valor."""
    out = []
    for k in p.get('bases') or []:
        d = BASES.get(k)
        if not d:
            continue
        if k == 'servidores':
            filtro = 'entidades de pessoal: ' + (', '.join(lista(p.get('pessoal'))) or 'todas as oferecidas pela tela')
        elif k == 'transferencias':
            filtro = f"órgão recebedor contém “{p.get('recebedora')}”" if p.get('recebedora') else 'todas as transferências'
        else:
            filtro = f"{d['filtro']} contém " + ' ou '.join(f'“{u}”' for u in lista(p.get('unidades'))) if lista(p.get('unidades')) else f"{d['filtro']}: todas as unidades"
        janela = {'mes': f"um pedido por mês — uma execução a cada 24 h relê o ano inteiro (completa); as demais, só os últimos {p.get('meses_recentes', 2)} mês(es) (rápida)",
                  'ano': 'um pedido de 01/01 até hoje (o ano inteiro em toda execução)',
                  'folha': 'um pedido por entidade e mês: do mês atual para trás (até 3 meses), até achar a folha de todas as entidades'}[d['janela']]
        modo = modo_de(p, k)
        a = API.get(k) if modo != 'xml' else None
        if k not in API:
            caminho = 'Só XML: a API de dados abertos da GOVBR não oferece esta base'
        elif modo == 'xml':
            caminho = MODOS['xml'] + ' (escolhido no painel)'
        elif not p.get('api'):
            caminho = f"{MODOS[modo]} — mas o endereço da API não foi informado: " + ('a base falha' if modo == 'api' else 'usa o XML')
        else:
            caminho = MODOS[modo]
        colunas = [(c, r, campo, regra, (a['colunas'].get(c, campo) if a else '')) for c, r, campo, regra in d['colunas']]
        out.append({'base': k, 'rotulo': d['rotulo'], 'titulo': d['titulo'], 'rota': f"/transparencia/{d['tela']}", 'tabela': d['tabela'],
                    'arquivo': d['arquivo'], 'registro': d['registro'], 'item': d['item'], 'filtro': filtro, 'janela': janela,
                    'nota': d.get('nota', ''), 'de': BASES[d['de']]['rotulo'] if d.get('de') else '', 'colunas': colunas,
                    'caminho': caminho, 'api_rota': ((p.get('api') or '{endereço da API}').rstrip('/') + '/' + a['rota']) if a else '',
                    'api_nota': a['nota'] if a else ''})
    return out
