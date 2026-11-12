# Etapa 4 (11/11/2026): coletor do portal TransparênciaBR da GOVBR (exportação XML dentro de ZIP).
# O portal é SIMULADO (nenhum acesso à internet). Todos os registros são EXEMPLOS FICTÍCIOS (nomes "EXEMPLO", documentos inventados).
# Só contra banco de TESTE recém-provisionado, com DATA_SIMULADA=2026-11-10T10:00:  PYTHONPATH=. python tests/teste_govbr.py
import io, os, re, sys, zipfile
import xml.etree.ElementTree as ET
from datetime import date
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
import httpx
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, worker, consultas as CS
from app.coletores import govbr as G
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok, ligar_email_teste, primeiro_acesso
ligar_email_teste()

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
HOJE = config.hoje()
checa(HOJE == date(2026, 11, 10), f'data simulada 10/11/2026 ({HOJE})')
PM, CM = 'PREFEITURA MUNICIPAL EXEMPLO', 'CAMARA MUNICIPAL EXEMPLO'

# ---------- 1. conversões ----------
checa(G.valor('R$ 1.234,56') == 1234.56 and G.valor('R$ -40.000,00') == -40000.0 and G.valor(' ') is None and G.valor('') is None, 'valores "R$ 1.234,56" viram número')
checa(G.mes_num('MARÇO') == 3 and G.mes_num('outubro') == 10 and G.mes_num('x') == 0, 'nome do mês vira número')
checa(G.meses_da_execucao(HOJE, 2026, True, 2)[0][0] == date(2026, 1, 1) and len(G.meses_da_execucao(HOJE, 2026, True, 2)) == 11, 'completa: um período por mês, de janeiro até hoje')
r = G.meses_da_execucao(HOJE, 2026, False, 2)
checa(r == [(date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 11, 1), HOJE)], f'rápida: só os 2 últimos meses, até hoje ({r})')
checa(len(G.meses_da_execucao(HOJE, 2026, False, 9)) == 3, 'rápida: no máximo 3 meses')

# ---------- 2. portal GOVBR simulado ----------
def el(pai, tag, txt=None, **filhos):
    e = ET.SubElement(pai, tag)
    if txt is not None:
        e.text = txt
    for k, v in filhos.items():
        el(e, k, v)
    return e

def reg(raiz, tag, campos):
    r = ET.SubElement(raiz, tag)
    for k, v in campos.items():
        if isinstance(v, dict):
            sub = ET.SubElement(r, k)
            for k2, v2 in v.items():
                el(sub, k2, v2)
        elif isinstance(v, list):
            sub = ET.SubElement(r, k)
            for tag2, campos2 in v:
                reg(sub, tag2, campos2)
        else:
            el(r, k, v)
    return r

def br(d):
    return d.strftime('%d/%m/%Y')

EMP = [  # empenhos (e diárias) EXEMPLO
    dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', Departamento='SECRETARIA EXEMPLO', Funcao='Administração',
         Programa='PROGRAMA EXEMPLO', Acao={'Tipo': 'Atividade', 'Descricao': 'AÇÃO EXEMPLO'}, FonteRecurso={'Identificacao': '1', 'Descricao': 'TESOURO'},
         DesdobramentoDespesa={'Identificacao': '3.3.90.39.99', 'Descricao': 'SERVIÇOS'}, NumeroEmpenho='000101', DataEmissaoEmpenho='05/11/2026',
         CategoriaEmpenho='Ordinário', Credor='FORNECEDOR EXEMPLO LTDA', CPFCNPJ='11.222.333/0001-81', ModalidadeLicitacao='Dispensa',
         ValorEmpenhado='R$ 1.000,00', ValorLiquidado='R$ 800,00', ValorPago='R$ 500,00', ValorAnulado=' '),
    dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', Departamento='SECRETARIA EXEMPLO', NumeroEmpenho='000102',
         DataEmissaoEmpenho='03/11/2026', CategoriaEmpenho='Ordinário', Credor='PESSOA EXEMPLO 12345678909', CPFCNPJ='123.456.789-09',
         ObjetivoViagem='CURSO EXEMPLO', Destino='CAPITAL EXEMPLO', DataInicialViagem='04/11/2026', QuantidadeDiasDiarias='2', ValorTotal='R$ 300,00',
         ValorEmpenhado='R$ 300,00', ValorLiquidado='R$ 300,00', ValorPago='R$ 300,00', ValorAnulado=''),
    dict(Exercicio='2026', UnidadeGestora=CM, Orgao='PODER LEGISLATIVO', Unidade='CAMARA', NumeroEmpenho='000103', DataEmissaoEmpenho='06/11/2026',
         Credor='OUTRO FORNECEDOR EXEMPLO', CPFCNPJ='22.333.444/0001-00', ValorEmpenhado='R$ 50,00', ValorLiquidado='', ValorPago='', ValorAnulado=''),
    dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', Departamento='SECRETARIA EXEMPLO', NumeroEmpenho='000090',
         DataEmissaoEmpenho='15/10/2026', CategoriaEmpenho='Global', Credor='FORNECEDOR EXEMPLO LTDA', CPFCNPJ='11.222.333/0001-81',
         ValorEmpenhado='R$ 1.000,00', ValorLiquidado='', ValorPago='', ValorAnulado='R$ 100,00'),
    dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', NumeroEmpenho='000010', DataEmissaoEmpenho='10/03/2026',
         Credor='FORNECEDOR ANTIGO EXEMPLO', CPFCNPJ='33.444.555/0001-00', QuantidadeDiasDiarias='0.0000', ObjetivoViagem='',
         ValorEmpenhado='R$ 70,00', ValorLiquidado='R$ 70,00', ValorPago='R$ 70,00', ValorAnulado=''),
    dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', NumeroEmpenho='000011', DataEmissaoEmpenho='12/03/2026',
         Credor='OUTRA PESSOA EXEMPLO', CPFCNPJ='', QuantidadeDiasDiarias='0.0000', DesdobramentoDespesa={'Identificacao': '3.3.90.14.14', 'Descricao': 'DIÁRIAS CIVIL'},
         ValorEmpenhado='R$ 120,00', ValorLiquidado='R$ 120,00', ValorPago='R$ 120,00', ValorAnulado=''),
]
ARR = [dict(Exercicio='2026', Mes='OUTUBRO', DataArrecadacao='10/10/2026', UnidadeGestora=PM, NaturezaCategoria={'Identificacao': '1.1.1.0', 'Nome': 'IMPOSTO EXEMPLO', 'Nivel': '15'},
            FonteRecurso='TESOURO', ValorArrecadadoLiquido='R$ 1.000,00'),
       dict(Exercicio='2026', Mes='OUTUBRO', DataArrecadacao='20/10/2026', UnidadeGestora=PM, NaturezaCategoria={'Identificacao': '1.1.1.0', 'Nome': 'IMPOSTO EXEMPLO', 'Nivel': '15'},
            FonteRecurso='TESOURO', ValorArrecadadoLiquido='R$ 1.000,00'),
       dict(Exercicio='2026', Mes='NOVEMBRO', DataArrecadacao='03/11/2026', UnidadeGestora=PM, NaturezaCategoria={'Identificacao': '1.1.1.0', 'Nome': 'IMPOSTO EXEMPLO', 'Nivel': '15'},
            FonteRecurso='TESOURO', ValorArrecadadoLiquido='R$ 500,00'),
       dict(Exercicio='2026', Mes='NOVEMBRO', DataArrecadacao='03/11/2026', UnidadeGestora='FUNDO EXEMPLO', NaturezaCategoria={'Identificacao': '1.3.0', 'Nome': 'RENDA', 'Nivel': '15'},
            FonteRecurso='RPPS', ValorArrecadadoLiquido='R$ 9.999,00')]
PLAN = [dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', Departamento='SECRETARIA EXEMPLO', Mes='JANEIRO',
             DotacaoInicial='R$ 10.000,00', DotacaoAtualizada=' ', ValorEmpenhado=' ', ValorLiquidado=' ', ValorPago=' ', ValorAnulado=' '),
        dict(Exercicio='2026', UnidadeGestora=PM, Orgao='PODER EXECUTIVO', Unidade='PODER EXECUTIVO', Departamento='SECRETARIA EXEMPLO', Mes='OUTUBRO',
             DotacaoInicial=' ', DotacaoAtualizada='R$ -1.000,00', ValorEmpenhado='R$ 2.000,00', ValorLiquidado='R$ 1.500,00', ValorPago='R$ 1.000,00', ValorAnulado='R$ 200,00'),
        dict(Exercicio='2026', UnidadeGestora=CM, Orgao='PODER LEGISLATIVO', Unidade='CAMARA', Mes='OUTUBRO', DotacaoAtualizada='R$ 5.000,00', ValorEmpenhado='R$ 5,00')]
RP = [dict(Exercicio='2026', UnidadeGestora=PM, NumeroEmpenho='000500', DataEmissaoEmpenho='10/12/2025', Credor='FORNECEDOR EXEMPLO LTDA', CPFCNPJ='11.222.333/0001-81',
           ValorEmpenhado='R$ 400,00', ValorLiquidacao='R$ 400,00', ValorLiquidado='R$ 0,00', ValorPago='R$ 100,00', ValorAnulado='R$ 0,00'),
      dict(Exercicio='2026', UnidadeGestora=PM, NumeroEmpenho='000500', DataEmissaoEmpenho='10/12/2025', Credor='FORNECEDOR EXEMPLO LTDA', CPFCNPJ='11.222.333/0001-81',
           ValorEmpenhado='R$ 0,00', ValorLiquidacao='R$ 0,00', ValorLiquidado='R$ 0,00', ValorPago='R$ 200,00', ValorAnulado='R$ 50,00'),
      dict(Exercicio='2026', UnidadeGestora=PM, NumeroEmpenho='000501', DataEmissaoEmpenho='11/12/2025', Credor='PESSOA EXEMPLO', CPFCNPJ='123.456.789-09',
           ValorEmpenhado='R$ 50,00', ValorLiquidado='', ValorPago='')]
LIC = [dict(UnidadeGestora=PM, NumeroProcesso='10/2026', Modalidade='Pregão Eletrônico', Objeto='AQUISIÇÃO EXEMPLO', DataJulgamento=' ', DataHomologacao='05/11/2026',
            ValorProcesso='R$ 5.000,00', SituacaoProcesso='Concluída',
            InstrumentosContratuais=[('InstrumentoContratual', dict(UnidadeGestora=PM, NumeroInstrumentoContratual='7/2026', NomeFornecedor='FORNECEDOR EXEMPLO LTDA',
                                     CNPJFornecedor='11.222.333/0001-81', Objeto='CONTRATO EXEMPLO', DataEmissao='06/11/2026', DataExpiracao='06/11/2027',
                                     ValorInstrumentoContratual='R$ 4.000,00',
                                     Aditivos=[('Aditivo', dict(NumeroAditivo='1', DataExpiracao='06/05/2028', ValorAditivado='R$ 100,00'))]))]),
       dict(UnidadeGestora=CM, NumeroProcesso='3/2026', Modalidade='Dispensa', Objeto='CÂMARA EXEMPLO', DataHomologacao='05/11/2026', ValorProcesso='R$ 10,00', SituacaoProcesso='Concluída')]
# folha: a entidade 1 ainda não publicou outubro; a 2 já publicou outubro e setembro → vale setembro (as duas)
UM = dict(NomServidor='SERVIDOR EXEMPLO UM', Cargo='AUXILIAR', Lotacao='SAUDE', SalarioBase='R$ 2.000,00', Proventos='R$ 2.500,00', Descontos='R$ 400,00', Liquido='R$ 2.100,00')
DOIS = dict(NomServidor='SERVIDORA EXEMPLO DOIS', Cargo='PROFESSORA', Lotacao='EDUCACAO', Proventos='R$ 3.000,00', Descontos='R$ 500,00', Liquido='R$ 2.500,00')
FOLHA = {('DW_X_AP_1', '202609'): [dict(UM, Competencia='09/2026')], ('DW_X_AP_2', '202610'): [dict(DOIS, Competencia='10/2026')],
         ('DW_X_AP_2', '202609'): [dict(DOIS, Competencia='09/2026')]}
TR = {11: [dict(Identificacao='15', OrgaoConcessor='PODER EXECUTIVO', OrgaoRecebedor='PODER LEGISLATIVO', DataMovimento='01/01/2026', TipoMovimento='Programação Inicial', ValorMovimento='R$ 2.400.000,00'),
           dict(Identificacao='16', OrgaoConcessor='PODER EXECUTIVO', OrgaoRecebedor='PODER LEGISLATIVO', DataMovimento='01/02/2026', TipoMovimento='Concessão', ValorMovimento='R$ 200.000,00')],
      12: [dict(Identificacao='99', OrgaoConcessor='PODER EXECUTIVO', OrgaoRecebedor='PODER LEGISLATIVO', DataMovimento='01/02/2026', TipoMovimento='Recebimento', ValorMovimento='R$ 200.000,00'),
           dict(Identificacao='98', OrgaoConcessor='FUNDO EXEMPLO', OrgaoRecebedor='PODER EXECUTIVO', DataMovimento='05/02/2026', TipoMovimento='Recebimento', ValorMovimento='R$ 1,00')]}
ITEM = {6: ('Empenhos', 'Principal', 'empenhos.zip', EMP, 'DataEmissaoEmpenho'), 3: ('Arrecadacoes', 'Arrecadacao', 'Arrecadacao.zip', ARR, 'DataArrecadacao'),
        4: ('Planejamento', 'Principal', 'Planejamento.zip', PLAN, None), 7: ('RestosPagar', 'Principal', 'RestosPagar.zip', RP, None),
        1: ('ProcessosLicitatorios', 'ProcessoLicitatorio', 'administracao.zip', LIC, 'DataHomologacao')}
TELA = ('<select name="cmbAno" id="cmbAno"><option value="2027|DW_X_FC_32|">2027</option><option value="2026|DW_X_FC_31|">2026</option></select>'
        '<select name="cmbUnidadeLC" id="cmbUnidadeLC"><option value="DW_X_AG_0">LICITAÇÕES</option></select>'
        '<select name="cmbUnidadeAR" id="cmbUnidadeAR"><option value="DW_X_AP_1">GESTÃO DE PESSOAL - 0001</option><option value="DW_X_AP_2">GESTÃO DE PESSOAL - 0004</option></select>')
CHAMADAS, FALHA = [], {}

def xml(raiz_tag, reg_tag, regs):
    raiz = ET.Element(raiz_tag)
    for r in regs:
        reg(raiz, reg_tag, r)
    corpo = ET.tostring(raiz, encoding='ISO-8859-1')
    if FALHA.get('doctype') and raiz_tag == 'Planejamento':
        corpo = corpo.replace(b"?>", b"?><!DOCTYPE x [<!ENTITY a 'b'>]>", 1)
    return corpo

def no_periodo(r, campo, ini, fim):
    if not campo:
        return True
    d = r.get(campo) or ''
    m = re.match(r'(\d\d)/(\d\d)/(\d{4})', d)
    return bool(m) and ini <= m.group(3) + m.group(2) + m.group(1) <= fim

ZIPS = {}
def falso_get(self, caminho, params=None):
    params = dict(params or {})
    CHAMADAS.append((caminho, params))
    req = httpx.Request('GET', self.base + caminho, params=params)
    if caminho == 'index.asp':
        return httpx.Response(200, content=('<html>' + TELA + '</html>').encode('latin-1'), request=req)
    if caminho.startswith('dll/'):
        return httpx.Response(200, content=ZIPS[caminho], request=req)
    assert caminho == 'geraxml.asp', caminho
    item, ini, fim, banco = int(params['item']), params['dataInicial'], params['dataFinal'], params['banco']
    sem = httpx.Response(200, content=b'', headers={'ERRO': 'Nao ha dados a serem exportados.'}, request=req)
    if item == 8:
        regs, raiz, tag, arq = FOLHA.get((banco, ini[:6]), []), 'FolhasPagamento', 'FolhaPagamento', 'FolhaPagamento.zip'
    elif item in (11, 12):
        regs, raiz, tag, arq = [r for r in TR[item] if no_periodo(r, 'DataMovimento', ini, fim)], 'TransferenciasFinanceiras', 'TransferenciaFinanceira', 'TransferenciaFinanceira.zip'
    else:
        raiz, tag, arq, base, campo = ITEM[item]
        regs = [r for r in base if no_periodo(r, campo, ini, fim)]
        if FALHA.get('exercicio') and item == 7:
            regs = [dict(r, Exercicio='2025') for r in regs]
    if not regs:
        return sem
    z = io.BytesIO()
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr(arq.replace('.zip', '.xml'), xml(raiz, tag, regs))
    ZIPS['dll/' + arq] = z.getvalue()
    return httpx.Response(200, content=f"<a id='lnkDownload' href='dll/{arq}'>Arquivo</a>".encode(), request=req)
G.Portal._get = falso_get

# ---------- 3. cadastro de Prefeitura e Câmara com GOVBR pelo console ----------
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
t = con.get('/orgaos/novo').text
checa('GOVBR' in t and 'name="gov_base"' in t and 'console.js?v=2' in t, 'cadastro oferece a GOVBR com os campos dela')
def cadastrar(**k):
    d = {'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599931', 'municipio': 'Município Exemplo GOVBR', 'uf': 'SP', 'dominio': 'pmgov.localhost',
         'email_admin': 'admin@pmgov.localhost', 'sistema': 'govbr', 'gov_base': 'https://portal-exemplo.invalid/pronimtb/', 'gov_unidades': 'PREFEITURA MUNICIPAL EXEMPLO'}
    d.update(k)
    return con.post('/orgaos/novo', data={x: y for x, y in d.items() if y is not None})
checa('GOVBR: informe o endereço https' in cadastrar(gov_base='http://sem-https').text, 'GOVBR exige endereço https do portal')
r = cadastrar()
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmgov.localhost'")
F = {x['fonte']: x['params'] for x in db.todos(db.PLATAFORMA, 'SELECT fonte, params FROM fontes WHERE orgao_id=%s', (o['id'],))} if o else {}
g = F.get('govbr', {})
checa(g.get('base') == 'https://portal-exemplo.invalid/pronimtb/' and g.get('unidades') == PM and g.get('meses_recentes') == 2 and 'servidores' in g.get('bases', [])
      and 'fiorilli' not in F and 'financas' not in F, f'Prefeitura com a fonte govbr ({g})')
r = cadastrar(tipo='legislativo', dominio='cmgov.localhost', email_admin='admin@cmgov.localhost', gov_unidades='')
c = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='cmgov.localhost'")
gc = (db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='govbr'", (c['id'],)) or {}).get('params', {}) if c else {}
checa(gc.get('bases') == ['transferencias'] and gc.get('recebedora') == 'PODER LEGISLATIVO' and gc.get('unidades') == 'CAMARA', f'Câmara com GOVBR: só transferências, recebedora Poder Legislativo ({gc})')

# ---------- 4. coleta completa (pelo worker) ----------
b = o['banco']
res = worker.rodar(o, 'govbr', g)
R = {x[0]: x for x in res}
checa(all(x[1] for x in res) and len(res) == 9, f'todas as bases ok ({res})')
checa(R['empenhos'][3].startswith('via XML: completa: 5 registros') and '11 período' in R['empenhos'][3], f'1ª execução completa, um pedido por mês ({R["empenhos"][3]})')
n_emp = sum(1 for c_, p in CHAMADAS if c_ == 'geraxml.asp' and p['item'] == 6)
checa(n_emp == 11, f'empenhos e diárias baixam o mesmo arquivo uma vez só por mês ({n_emp} pedidos)')
checa(all(p['banco'] == 'DW_X_FC_31' for c_, p in CHAMADAS if c_ == 'geraxml.asp' and p['item'] in (3, 4, 6, 7, 11, 12)), 'código do banco do ano lido na tela do portal')
E = {x['pk']: x for x in db.todos(b, "SELECT * FROM empenhos WHERE fonte='govbr'")}
checa(set(E) == {'000101', '000102', '000090', '000010', '000011'}, f'só os empenhos da unidade gestora do órgão ({sorted(E)})')
checa(E['000101']['credor_cnpj'] == '11.222.333/0001-81' and float(E['000101']['liquidado']) == 800 and E['000101']['numero'] == '000101/2026', 'empenho com CNPJ e valores')
checa(E['000102']['credor_cnpj'] == '' and '12345678909' not in E['000102']['credor'] and E['000102']['credor'] == 'PESSOA EXEMPLO', 'LGPD: CPF nunca gravado, nem no nome')
checa(float(E['000090']['empenhado']) == 900, 'empenhado líquido da anulação')
D = {x['empenho']: x for x in db.todos(b, "SELECT * FROM diarias WHERE fonte='govbr'")}
checa(set(D) == {'000102/2026', '000011/2026'} and D['000102/2026']['favorecido'] == 'PESSOA EXEMPLO' and float(D['000102/2026']['valor']) == 300
      and 'CURSO EXEMPLO' in D['000102/2026']['motivo'] and D['000102/2026']['data'] == date(2026, 11, 4) and float(D['000011/2026']['valor']) == 120,
      f'diárias: com dias > 0 ou natureza de diária; "0.0000" sozinho não conta ({sorted(D)})')
RC = {(x['mes'], x['codigo']): x for x in db.todos(b, "SELECT * FROM receitas WHERE fonte='govbr'")}
checa(set(RC) == {(10, '1.1.1.0'), (11, '1.1.1.0')} and float(RC[(10, '1.1.1.0')]['arrecadado']) == 2000 and RC[(10, '1.1.1.0')]['soma'], f'receitas somadas por mês, sem o fundo ({RC.keys()})')
DU = db.todos(b, "SELECT * FROM despesas_unidade WHERE fonte='govbr'")
checa(len(DU) == 1 and float(DU[0]['dotacao']) == 10000 and float(DU[0]['dotacao_atualizada']) == 9000 and float(DU[0]['empenhado']) == 1800 and float(DU[0]['pago']) == 1000,
      f'despesas por unidade: dotação inicial + variações, empenhado líquido das anulações ({DU})')
RPg = db.todos(b, "SELECT * FROM restos_pagar WHERE fonte='govbr'")
checa(len(RPg) == 1 and RPg[0]['codigo'] == '000500/2025' and float(RPg[0]['empenhado']) == 350 and float(RPg[0]['liquidado']) == 400 and float(RPg[0]['pago']) == 300,
      f'restos a pagar: movimentos somados por empenho (liquidado de ValorLiquidacao), sem pessoa física ({RPg})')
L = db.todos(b, "SELECT * FROM licitacoes WHERE fonte='govbr'")
checa(len(L) == 1 and L[0]['numero'] == '10/2026' and float(L[0]['valor']) == 5000 and L[0]['data'] == date(2026, 11, 5), 'licitação da Prefeitura (a da Câmara fica de fora)')
CT = db.todos(b, "SELECT * FROM contratos WHERE fonte='govbr'")
checa(len(CT) == 1 and CT[0]['fim'] == date(2028, 5, 6) and float(CT[0]['valor']) == 4100 and CT[0]['modalidade'] == 'Pregão Eletrônico', f'contrato com o aditivo (fim e valor) ({CT})')
checa(sum(1 for c_, p in CHAMADAS if c_ == 'geraxml.asp' and p['item'] == 1) == 11, 'licitações e contratos: um arquivo por mês, baixado uma vez')
S = db.todos(b, "SELECT * FROM servidores WHERE fonte='govbr' ORDER BY nome")
SN = {s['nome']: s for s in S}
checa(len(S) == 2 and all(s['mes'] == 9 for s in S) and float(SN['SERVIDOR EXEMPLO UM']['proventos']) == 2500, f'folha: competência mais recente com todas as entidades (setembro) ({S})')
checa(R['servidores'][3] == 'via XML: folha de 09/2026 (2 entidade(s))', R['servidores'][3])
T = db.todos(b, "SELECT * FROM transferencias WHERE fonte='govbr'")
checa(len(T) == 3 and sum(float(x['repasse'] or 0) for x in T) == 200001 and sum(float(x['previsto'] or 0) for x in T) == 2400000, f'concessão e recebimento do mesmo repasse contam uma vez ({T})')
n = db.cfg(b, 'numeros', {})
checa('GOVBR' in (n.get('fonte') or '') and n.get('kpis'), f'"em números" da página inicial com a receita da GOVBR ({n.get("fonte")})')
checa(db.um(db.PLATAFORMA, "SELECT count(*) n FROM coletas WHERE orgao_slug=%s AND fonte LIKE 'govbr:%%' AND ok", (o['slug'],))['n'] == 9, 'coletas registradas por base')

# ---------- 5. execução rápida, falhas isoladas ----------
CHAMADAS.clear()
res = worker.rodar(o, 'govbr', g)
R = {x[0]: x for x in res}
checa(R['empenhos'][3].startswith('via XML: rápida:') and sum(1 for c_, p in CHAMADAS if c_ == 'geraxml.asp' and p['item'] == 6) == 2, f'2ª execução rápida: só os 2 últimos meses ({R["empenhos"][3]})')
checa('000010' in {x['pk'] for x in db.todos(b, "SELECT pk FROM empenhos WHERE fonte='govbr'")}, 'execução rápida não apaga os meses antigos')
FALHA.update(exercicio=True, doctype=True)
res = {x[0]: x for x in G.coletar(o, dict(g, bases=['restos_pagar', 'despesas_unidade', 'licitacoes']))}
FALHA.clear()
checa(not res['restos_pagar'][1] and 'outro exercício' in res['restos_pagar'][3], f'arquivo de outro exercício recusado ({res["restos_pagar"]})')
checa(not res['despesas_unidade'][1] and 'DOCTYPE' in res['despesas_unidade'][3], 'XML com DOCTYPE recusado')
checa(res['licitacoes'][1], 'falha de uma base não para as outras')
checa(len(db.todos(b, "SELECT 1 FROM restos_pagar WHERE fonte='govbr'")) == 1, 'falha não apaga o que já havia')
checa(G.coletar(o, {'bases': ['empenhos']})[0][1] is False, 'sem endereço do portal: falha explicada')

# ---------- 6. portal ----------
pt = TestClient(app, base_url='http://pmgov.localhost')
t = pt.get('/transparencia/empenhos').text
checa('FORNECEDOR EXEMPLO LTDA' in t and 'Portal da transparência (GOVBR)' in t and 'Fiorilli' not in t and '123.456.789-09' not in t and 'Base legal' in t, 'tela de empenhos com a fonte GOVBR, sem CPF')
t = pt.get('/transparencia/servidores').text
checa('SERVIDOR EXEMPLO UM' in t and '2.100' not in t and '400,00' not in t, 'pessoal sem descontos nem líquido')
tb = TestClient(app, base_url='http://pmbora.localhost').get('/transparencia/empenhos').text
checa('Fiorilli' in tb and 'GOVBR' not in tb, 'piloto continua mostrando só a Fiorilli')

# ---------- 7. painel: parâmetros, periodicidade e como cada tela é montada ----------
adm = TestClient(app, base_url='http://pmgov.localhost')
primeiro_acesso(adm, 'admin@pmgov.localhost', 'senhaNovaGov1234')
t = adm.get('/admin/integracoes?fonte=govbr').text
checa('Portal da transparência (GOVBR' in t and 'XML dentro de ZIP' in t and 'Agenda de execução' in t and 'a cada 3 horas' in t, 'tela com nome, formato e periodicidade (padrão a cada 3 h)')
checa('geraxml.asp' in t and 'dll/empenhos.zip' in t and 'código do ano 2026, lido na tela' in t, 'como a consulta é montada (endereço, arquivo e banco do ano)')
checa('Como cada tela do portal é montada' in t and '/transparencia/empenhos' in t and 'DataEmissaoEmpenho' in t and 'só CNPJ; CPF nunca é gravado' in t
      and 'UnidadeGestora contém “PREFEITURA MUNICIPAL EXEMPLO”' in t and 'uma execução a cada 24 h relê o ano inteiro' in t, 'cada tela: rota, filtro, período e coluna ← campo do XML')
checa('Fica de fora' in t and 'reCAPTCHA' in t and 'Ordem cronológica' in t, 'mostra o que fica de fora e por quê')
checa('name="p_meses_recentes"' in t and 'name="p_pessoal"' in t and 'value="empenhos"' in t and 'Folha' in t, 'parâmetros editáveis')
U = '/admin/integracoes/govbr'
def form(**k):
    d = {'csrf': tok(adm, '/admin/integracoes?fonte=govbr'), 'volta': '/admin/integracoes?fonte=govbr', 'p_base': g['base'], 'p_unidades': g['unidades'],
         'p_meses_recentes': '2', 'p_pessoal': '', 'p_recebedora': '', 'p_bases': ['empenhos', 'servidores']}
    d.update(k)
    return adm.post(U, data=d, follow_redirects=True)
checa('de 1 a 3' in form(acao='testar', p_meses_recentes='7').text, 'meses relidos limitados a 3')
checa('só códigos como DW_LC131_AP_3' in form(acao='testar', p_pessoal='x;y').text, 'entidades de pessoal só com códigos')
antes = db.um(b, "SELECT count(*) n FROM empenhos")['n']
CHAMADAS.clear()
r = form(acao='testar')
tst = CS.ultimo_teste(o, 'govbr')
checa(tst and tst['ok'] and 'nada gravado' in r.text and db.um(b, "SELECT count(*) n FROM empenhos")['n'] == antes, f'testar consulta: roda sem gravar ({tst and tst["relatorio"].get("resultado")})')
q = (tst or {}).get('relatorio', {}).get('requisicoes', [])
checa(q and all('geraxml.asp' in x['url'] for x in q) and sum(1 for x in q if 'item=6' in x['url']) == 1, 'teste lê só o mês atual')
checa(all('Descontos' not in x['trecho'] and 'Liquido' not in x['trecho'] and '123.456.789-09' not in x['trecho'] for x in q), 'trecho do teste sem descontos, líquido nem CPF')
checa('dll/FolhaPagamento.zip' in r.text or 'arquivo=dll' in r.text, 'relatório mostra o arquivo baixado')

# ---------- 8. API de dados abertos (alguns portais GOVBR têm): automático, só API e só XML por base ----------
import json
API_DESP = {'modo': 'erro'}
CHAMADAS_API = []
UG_API = 'MUNICIPIO EXEMPLO'
def rec_api(i):
    return {'id': i, 'Exercicio': 2026, 'Mes': 'OUTUBRO' if i % 2 else 'JANEIRO', 'DataArrecadacao': '2026-10-05' if i % 2 else '2026-01-01', 'UnidadeGestora': UG_API,
            'CategoriaEconomica': '1.0.0.0', 'dsCategoriaEconomica': 'Receitas Correntes', 'Rubrica': '1.1.1.3', 'dsRubrica': 'Impostos',
            'Alinea': f'1.1.1.3.{i % 3:02d}', 'dsAlinea': f'IMPOSTO EXEMPLO {i % 3}', 'SubAlinea': None, 'FonteRecurso': 'Recursos Ordinários (Livres)',
            'ValorPrevistoLiquido': 0.0 if i % 2 else 100.0, 'ValorArrecadadoLiquido': 10.0 if i % 2 else 0.0}
REC_API = [rec_api(i) for i in range(203)]  # 2 páginas: 200 + 3
EMP_API = [dict(e, UnidadeGestora=UG_API) for e in EMP[:2]]
def falso_api(self, caminho, params=None):
    CHAMADAS_API.append((caminho, dict(params or {})))
    q = dict(params or {})
    if caminho.startswith('dbdestino/'):
        return 200, json.dumps(['PREFEITURA EXEMPLO'])
    if caminho.startswith('unidadeGestora/'):
        return 200, json.dumps([{'ds_UnidadeGestora': UG_API}, {'ds_UnidadeGestora': 'CAMARA MUNICIPAL EXEMPLO'}])
    m = re.match(r'(Receitas|Despesas)/buscarDados\w+/2026/(\d+)/PREFEITURA EXEMPLO$', caminho)
    if m:
        if q.get('unidadeGestora') != UG_API:
            return 200, json.dumps(json.dumps([]))
        pg = int(m.group(2))
        if m.group(1) == 'Receitas':
            return 200, json.dumps(json.dumps(REC_API[(pg - 1) * 200: pg * 200]))  # JSON dentro de uma string, como a GOVBR faz
        if API_DESP['modo'] == 'erro':
            return 200, json.dumps('Erro ao obter dados de despesas com os parametros informados: SqlException: Invalid column name (exemplo)')
        return 200, json.dumps(json.dumps(EMP_API if pg == 1 else []))
    if caminho == 'FolhaPagamento':
        if q.get('dataInicial') != '01/10/2026':
            return 200, json.dumps('Erro ao obter dados personalizados: Index was out of range.')
        return 200, json.dumps(json.dumps([{'id': 1, 'Matricula': '777', 'CPF': '123.456.789-09', 'Competencia': '10/2026', 'NomeServidor': 'SERVIDOR API EXEMPLO',
                                            'Cargo': 'AGENTE', 'Lotacao': 'OBRAS', 'Proventos': 1800.0, 'Descontos': 300.0, 'Liquido': 1500.0}]))
    return 404, ''
G.Api._raw = falso_api

r = cadastrar(dominio='pmapi.localhost', email_admin='admin@pmapi.localhost', ibge='3599932', municipio='Município Exemplo API', gov_api='http://sem-https')
checa('API de dados abertos precisa ser https' in r.text, 'endereço da API exige https')
r = cadastrar(dominio='pmapi.localhost', email_admin='admin@pmapi.localhost', ibge='3599932', municipio='Município Exemplo API',
              gov_api='https://portal-exemplo.invalid/dadosabertos/', gov_unidades=f'{UG_API}, {PM}')
oa = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmapi.localhost'")
ga = db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='govbr'", (oa['id'],))['params'] if oa else {}
checa(ga.get('api') == 'https://portal-exemplo.invalid/dadosabertos/' and ga.get('modos') == {}, f'cadastro com a API (todas as bases no automático) ({ga})')
ba = oa['banco']
ga['bases'] = ['receitas', 'empenhos', 'diarias', 'servidores', 'licitacoes']
CHAMADAS.clear()
R = {x[0]: x for x in G.coletar(oa, ga)}
checa(R['receitas'][1] and R['receitas'][3].startswith('via API:') and '2 página(s) da API' in R['receitas'][3], f'receitas pela API, duas páginas ({R["receitas"]})')
RA = db.todos(ba, "SELECT * FROM receitas WHERE fonte='govbr'")
checa(len(RA) == 6 and abs(sum(float(x['arrecadado']) for x in RA) - 1010) < 0.01 and abs(sum(float(x['previsto'] or 0) for x in RA) - 10200) < 0.01
      and {x['codigo'] for x in RA} == {'1.1.1.3.00', '1.1.1.3.01', '1.1.1.3.02'} and 'IMPOSTO EXEMPLO 1' in {x['nome'] for x in RA}, f'receitas da API com previsão, somadas por mês e alínea ({len(RA)})')
checa(R['empenhos'][1] and 'API falhou' in R['empenhos'][3] and 'Invalid column name' in R['empenhos'][3] and 'via XML: completa' in R['empenhos'][3],
      f'automático: despesas da API com erro (HTTP 200 com texto de erro) → XML do ano inteiro ({R["empenhos"][3]})')
checa(len(db.todos(ba, "SELECT 1 FROM empenhos WHERE fonte='govbr'")) == 5, 'empenhos vieram do XML')
checa(R['diarias'][1] and 'via XML' in R['diarias'][3], 'diárias também caem para o XML')
checa(R['licitacoes'][3].startswith('via XML:'), 'base sem API vem sempre do XML')
checa(R['servidores'][1] and R['servidores'][3] == 'via API: folha de 10/2026 (1 entidade(s))', f'folha pela API (novembro ainda sem folha) ({R["servidores"]})')
SV = db.um(ba, "SELECT * FROM servidores WHERE fonte='govbr'")
checa(SV and SV['registro'] == '777' and SV['nome'] == 'SERVIDOR API EXEMPLO' and float(SV['proventos']) == 1800 and '123.456' not in json.dumps(SV, default=str)
      and '1500' not in json.dumps(SV, default=str), 'folha da API sem CPF, descontos nem líquido; matrícula guardada')
amo = db.todos(db.PLATAFORMA, "SELECT trecho FROM consulta_amostras WHERE fonte='govbr' AND url LIKE %s", ('%dadosabertos%',))
checa(amo and all('123.456.789' not in a['trecho'] and 'Descontos' not in a['trecho'] for a in amo), 'amostras da API sem CPF nem descontos')
# só API: a falha aparece e nada é apagado
ga2 = dict(ga, bases=['empenhos'], modos={'empenhos': 'api'})
R = {x[0]: x for x in G.coletar(oa, ga2)}
checa(not R['empenhos'][1] and 'ApiErro' in R['empenhos'][3] and len(db.todos(ba, "SELECT 1 FROM empenhos WHERE fonte='govbr'")) == 5, f'só API: falha registrada, dados mantidos ({R["empenhos"]})')
# API de despesas volta a funcionar: o automático usa a API e o ano inteiro é substituído
API_DESP['modo'] = 'ok'
R = {x[0]: x for x in G.coletar(oa, dict(ga, bases=['empenhos', 'diarias']))}
EA = {x['pk'] for x in db.todos(ba, "SELECT pk FROM empenhos WHERE fonte='govbr'")}
checa(R['empenhos'][3].startswith('via API:') and EA == {'000101', '000102'}, f'automático com a API boa: empenhos da API ({R["empenhos"]}, {EA})')
checa(sum(1 for c_, _ in CHAMADAS_API if c_.startswith('Despesas/')) and R['diarias'][3].startswith('via API:'), 'diárias pela mesma consulta da API')
n_desp = sum(1 for c_, _ in CHAMADAS_API if c_.startswith('Despesas/'))
CHAMADAS_API.clear(); G.coletar(oa, dict(ga, bases=['empenhos', 'diarias']))
checa(sum(1 for c_, _ in CHAMADAS_API if c_.startswith('Despesas/')) == 1, 'empenhos e diárias consultam a API uma vez só (1 página da única unidade gestora que confere)')
# só XML: a API nem é consultada
CHAMADAS_API.clear()
R = {x[0]: x for x in G.coletar(oa, dict(ga, bases=['receitas'], modos={'receitas': 'xml'}))}
checa(R['receitas'][3].startswith('via XML') and not any(c_.startswith('Receitas/') for c_, _ in CHAMADAS_API), 'só XML: a API não é consultada')
# unidade gestora que não existe na API: erro explica o que a API oferece
R = {x[0]: x for x in G.coletar(oa, dict(ga, bases=['receitas'], unidades='OUTRA COISA', modos={'receitas': 'api'}))}
checa(not R['receitas'][1] and f'a API oferece: {UG_API}' in R['receitas'][3], f'unidade gestora inexistente: a mensagem lista as da API ({R["receitas"][3]})')
checa(G.coletar(oa, dict(ga, api='', bases=['receitas'], modos={'receitas': 'api'}))[0][3].endswith('endereço da API não configurado'), 'só API sem endereço: falha explicada')
# parâmetros e tela
v, e = CS.validar('govbr', {'p_base': ga['base'], 'p_unidades': 'X', 'p_meses_recentes': '2', 'p_api': 'http://x', 'p_modo_receitas': 'xml', 'p_bases': None}, ga)
checa(any('API de dados abertos' in x for x in e), 'validação: API só com https')
class F(dict):
    def getlist(self, k): return self.get(k + '[]', [])
v, e = CS.validar('govbr', F({'p_base': ga['base'], 'p_unidades': 'X', 'p_meses_recentes': '2', 'p_api': '', 'p_modo_receitas': 'xml', 'p_modo_empenhos': 'qualquer', 'p_bases[]': ['receitas']}), ga)
checa(not e and v['modos'] == {'receitas': 'xml', 'empenhos': 'auto', 'diarias': 'auto', 'servidores': 'auto'} and v['api'] == '', f'validação: escolha por base ({e}, {v.get("modos")})')
ad = TestClient(app, base_url='http://pmapi.localhost')
primeiro_acesso(ad, 'admin@pmapi.localhost', 'senhaNovaApi1234')
t = ad.get('/admin/integracoes?fonte=govbr').text
checa('Como buscar cada base' in t and 'name="p_modo_receitas"' in t and 'Automático: API; se falhar, XML' in t and 'name="p_api"' in t, 'tela: escolha por base e endereço da API')
checa('Campo da API' in t and 'buscarDadosReceitas' in t and 'ValorArrecadadoLiquido' in t and 'Só XML: a API de dados abertos da GOVBR não oferece esta base' in t,
      'como cada tela é montada: caminho, rota da API e campo da API ao lado do XML')
checa('— API (Automático' in t and '— XML' in t, 'como a consulta é montada: a rota da API e a do XML')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('govbr: tudo ok')
