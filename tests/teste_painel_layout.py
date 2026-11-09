# Fase 7 (layout): /painel no formato do protótipo — SEM internet; banco de TESTE com dados FICTÍCIOS de teste.
# Rode só contra banco de TESTE já provisionado:  TESTE=1 DATA_SIMULADA=2026-11-06T10:00 PYTHONPATH=. python tests/teste_painel_layout.py
import os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import db, worker, painel as P
from app.coletores import financas as FI, comum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def falha(m): erros.append(m)
PM = 'bd_pm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
def ok(r, cod=200, txt=None, nome=''):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {r.text[:200]}')
    return r
oid = db.um(db.PLATAFORMA, "SELECT id FROM orgaos WHERE slug='pm-bora'")['id']
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=TRUE WHERE orgao_id=%s AND chave='bi'", (oid,))

# ---------- sem dado do ano: os blocos de finanças não aparecem ----------
t = ok(pm.get('/painel?tema=fin'), nome='painel fin vazio').text
if 'Receita e despesa paga, mês a mês' in t or 'Para onde vai o dinheiro' in t or 'Finanças lidas do sistema contábil' in t: falha('bloco de finanças sem dado do ano')

# ---------- dados fictícios do órgão (só no banco de TESTE) ----------
for i, (cod, nome, prev, arr, soma) in enumerate([('1000.00.0.0.00.00', 'RECEITAS CORRENTES', 2000000, 1800000, True), ('2000.00.0.0.00.00', 'RECEITAS DE CAPITAL', 200000, 200000, True),
                                                  ('9000.00.0.0.00.00', '(R) DEDUCOES DA RECEITA', None, -300000, True), ('1700.00.0.0.00.00', 'TRANSFERÊNCIAS CORRENTES', None, 1500000, False),
                                                  ('2400.00.0.0.00.00', 'TRANSFERÊNCIAS DE CAPITAL', None, 100000, False), ('1710.00.0.0.00.00', 'TRANSFERÊNCIAS DA UNIÃO', None, 1100000, False),
                                                  ('1720.00.0.0.00.00', 'TRANSFERÊNCIAS DOS ESTADOS', None, 400000, False), ('1110.00.0.0.00.00', 'IMPOSTOS', None, 250000, False)]):
    db.exe(PM, "INSERT INTO receitas (chave, fonte, ano, mes, codigo, nome, previsto, arrecadado, soma) VALUES (%s,'fiorilli',2026,0,%s,%s,%s,%s,%s)", (f'r{i}', cod, nome, prev, arr, soma))
for i, (cod, un, dot, emp, pago, func) in enumerate([('01', 'FUNDO DE SAUDE TESTE', 1000000, 600000, 500000, 'Saúde'), ('02', 'ENSINO TESTE', 800000, 400000, 300000, 'Educação'),
                                                     ('03', 'GABINETE TESTE', 500000, 200000, 150000, 'Administração'), ('04', 'MERENDA TESTE', 100000, 50000, 40000, 'Assistência Social')]):
    db.exe(PM, "INSERT INTO despesas_unidade (chave, fonte, ano, codigo, unidade, dotacao_atualizada, empenhado, pago) VALUES (%s,'fiorilli',2026,%s,%s,%s,%s,%s)", (f'd{i}', cod, un, dot, emp, pago))
    db.exe(PM, "INSERT INTO empenhos (chave, fonte, ano, pk, numero, unidade, funcao, empenhado, data) VALUES (%s,'fiorilli',2026,%s,%s,%s,%s,%s,%s)", (f'e{i}', str(i), str(i), un, func, emp, date(2026, 3, 1)))
db.exe(db.PLATAFORMA, "INSERT INTO coletas (orgao_slug, fonte, inicio, fim, ok, registros, mensagem) VALUES ('pm-bora','fiorilli:receitas', now(), now(), TRUE, 8, 'teste')")
P.gravar(PM, 'mun_populacao', '2026', date(2026, 12, 31), 1000, nota='estimativa em 1º de julho')
for a, v in ((2024, 20.41), (2025, 20.36)):
    P.gravar(PM, 'saude_minimo', str(a), date(a, 12, 31), v, nota='RREO do 6º bimestre (ano completo)')
P.gravar(PM, 'saude_minimo', '2026', date(2026, 6, 30), 16.95, nota='RREO do 3º bimestre', parcial=True)
for a, n1, n2 in ((2023, 1, 7), (2024, 6, 7)):
    P.gravar(PM, 'saude_nascidos', str(a), date(a, 12, 31), n1); P.gravar(PM, 'saude_obitos', str(a), date(a, 12, 31), n2)
P.gravar(PM, 'saude_estabelecimentos', 'nov/2026', date(2026, 11, 30), 2, detalhe=[['Centro de saude/unidade basica', 1], ['Central de gestao em saude', 1]])
comum.guardar_publico('3507209', 'cnes_lista', 'atual', {'competencia': 'nov/2026', 'estabelecimentos': [{'cnes': '0000001', 'nome': 'Unidade De Teste', 'tipo': 'Centro de saude/unidade basica', 'endereco': 'Rua Teste, 1, Centro'}]})
for a, v, proj in ((2021, None, 7.1), (2023, 7.0, None), (2025, 6.6, None)):
    P.gravar(PM, 'edu_ideb_ai', str(a), date(a, 12, 31), v, texto='' if v else 'não divulgado pelo INEP', nota='rede pública = rede municipal (responsabilidade da Prefeitura); planilha do INEP, edição 2025',
             detalhe={'rendimento': 0.99, 'projecao': proj, 'responsavel': 'rede municipal (responsabilidade da Prefeitura)'})
P.gravar(PM, 'edu_saeb_mat_ai', '2025', date(2025, 12, 31), 240.82); P.gravar(PM, 'edu_saeb_lp_ai', '2025', date(2025, 12, 31), 220.24)
comum.guardar_publico('35', 'ideb_comparacao', 'ai', {'nome': 'São Paulo', 'rede': 'Pública', 'edicao': 2025, 'serie': {'2025': {'ideb': 6.5}}})
comum.guardar_publico('BR', 'ideb_comparacao', 'ai', {'nome': 'Brasil', 'rede': 'Pública', 'edicao': 2025, 'serie': {'2025': {'ideb': 6.1}}})
comum.guardar_publico('BR', 'ideb_comparacao', 'em', {'nome': 'Brasil', 'rede': 'Pública', 'edicao': 2025, 'serie': {'2025': {'ideb': 4.3}}})
for ch, f in zip([k for k, _ in P._IEGM], ['C+', 'B', 'B', 'C', 'B', 'B', 'C+', 'A']):
    P.gravar(PM, ch, '2024', date(2024, 12, 31), None, texto=f, nota='edição 2025 (ano-base 2024)')
comum.guardar_publico('35', 'iegm_distribuicao', '2024', {'faixas': {'A': 10, 'B+': 50, 'B': 200, 'C+': 300, 'C': 84}, 'total': 644, 'edicao': 2025})

# ---------- coletor mensal (Fiorilli por período de cada mês) ----------
pedidos = []
def fake(fonte, url, params=None, **kw):
    p = params or {}
    pedidos.append((p.get('Listagem'), p.get('MesInicialPeriodo'), p.get('MesFinalPeriodo'), p.get('DiaFinalPeriodo')))
    m = int(p['MesInicialPeriodo'])
    if p.get('MesInicialPeriodo') != p.get('MesFinalPeriodo'): raise AssertionError('período mensal esperado')
    if p['Listagem'] == 'ReceitaOrcamentaria':
        return [{'CODIGO': '1000.00.0.0.00.00', 'ARRECADADO_PERIODO': str(100000 * m)}, {'CODIGO': '9000.00.0.0.00.00', 'ARRECADADO_PERIODO': '-10000'},
                {'CODIGO': '1700.00.0.0.00.00', 'ARRECADADO_PERIODO': '99999'}, {'CODIGO': '1000.00.0.0.00.00', 'FONTE': '01', 'ARRECADADO_PERIODO': '77777'}]
    if p['Listagem'] == 'DespesasPorUnidade':
        return [{'CODIGO': '01', 'DESCRICAO': 'X', 'PAGO': str(50000 * m), 'EMPENHADO': str(60000 * m)}]
    raise AssertionError(p)
FI.buscar = fake
f = db.um(db.PLATAFORMA, "SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.fonte='financas'", (oid,))
if not f or not f['params'].get('base') or not f['params'].get('empresa'): falha(f'fonte financas sem os parâmetros da fiorilli: {f and f["params"]}')
if not f or f['fonte'] not in worker.PAINEL or worker.FREQ['financas'][1] != range(1, 5): falha('financas fora do agendamento de madrugada')
res = worker.rodar(f, 'financas', f['params'])
if not res or not res[0][1]: falha(f'coleta mensal: {res}')
ms = db.todos(PM, 'SELECT * FROM fin_mensal WHERE ano=2026 ORDER BY mes')
if len(ms) != 11 or float(ms[0]['receita']) != 90000 or float(ms[2]['despesa_paga']) != 150000 or not ms[-1]['parcial'] or ms[0]['parcial']: falha(f'série mensal: {[(m["mes"], m["receita"], m["parcial"]) for m in ms]}')
if ('ReceitaOrcamentaria', '11', '11', '06') not in pedidos: falha('mês corrente deveria ir até o dia de hoje')
ar = {a['codigo']: a for a in db.todos(PM, 'SELECT * FROM areas_unidades')}
if ar.get('01', {}).get('area') != 'Saúde' or ar.get('04', {}).get('area') != 'Assistência Social' or ar['01']['origem'] != 'sugestao': falha(f'sugestão de áreas: {ar}')

# ---------- página ----------
t = ok(pm.get('/painel'), nome='painel tudo').text
for x in ('Finanças lidas do sistema contábil em', 'class="pulso"', 'Receita e despesa paga, mês a mês', 'Para onde vai o dinheiro', 'De onde vem o dinheiro', 'Execução do orçamento de 2026',
          'Receita por habitante', 'cálculo do portal: valor oficial ÷ população estimada (IBGE 2026, 1.000 hab.)', 'Saúde por habitante', 'Educação por habitante', 'Receita vinda de repasses',
          'Ver em tabela', 'De cada R$ 100 que entram, R$ 80 vêm de repasses', 'A linha tracejada marca quanto do ano já passou',
          'Mínimo exigido por lei', 'Onde a população é atendida', 'Unidade De Teste', 'Nascimentos e óbitos', 'menos de 5', 'Orçamento da área em 2026', 'Fundo De Saude Teste',
          'IDEB: qualidade do ensino, anos iniciais', 'São Paulo (rede pública) 6,5', 'Brasil (rede pública) 6,1', 'rede municipal (responsabilidade da Prefeitura)',
          'Nota da gestão municipal pelo Tribunal de Contas', 'a mesma de 300 dos 644 municípios paulistas avaliados', 'Ver a evolução por edição',
          'Benefícios e cadastro social', 'O município', 'Ainda não disponíveis', 'Doses de vacina aplicadas', 'Pendente de fonte estável', 'Fonte:'):
    if x not in t: falha(f'painel: falta "{x}"')
if re.search(r'<li><strong>População estimada</strong>', t): falha('indicador com dado listado em "Ainda não disponíveis"')
if 'Saúde e educação somam' not in t: falha('frase de saúde e educação')
if t.count('role="img"') < 8: falha(f'gráficos sem role=img: {t.count(chr(114) + "ole=" + chr(34) + "img")}')
if '<nav class="ppilulas"' not in t or 'aria-current="page">Tudo' not in t or 'href="/painel?tema=saude"' not in t: falha('abas em pílula com aria-current e ?tema=')
nav = re.search(r'<nav class="ppilulas".*?</nav>', t, re.S).group(0)
if 'aria-pressed' in nav or '<button' in nav or nav.count('<a ') != 7: falha('abas são 7 links (aria-current), não botões')
# só a mesma etapa e o mesmo tipo de rede: a comparação dos anos iniciais não usa a do ensino médio
if '4,3' in re.sub(r'<[^>]+>', ' ', t.split('IDEB: qualidade do ensino')[1].split('</section>')[0]): falha('comparação de etapa errada')
# abas
r = pm.get('/painel?aba=saude', follow_redirects=False)
if r.status_code != 301 or r.headers.get('location') != '/painel?tema=saude': falha(f'redirecionamento ?aba=: {r.status_code} {r.headers.get("location")}')
t = ok(pm.get('/painel?tema=saude'), nome='tema saúde').text
if 'Dinheiro público' in re.sub(r'<nav class="ppilulas".*?</nav>', '', t, flags=re.S) or 'Nota da gestão municipal' in t or 'Ainda não disponíveis' in t or 'Onde a população é atendida' not in t: falha('filtro do tema saúde')
if 'aria-current="page">Saúde' not in t: falha('aba saúde marcada')
# sem linha equivalente, sem comparação
db.exe(db.PLATAFORMA, "DELETE FROM dados_publicos WHERE fonte='ideb_comparacao' AND ibge='35'")
t = ok(pm.get('/painel?tema=edu'), nome='tema edu').text
if 'São Paulo (rede pública)' in t or 'Brasil (rede pública) 6,1' not in t: falha('comparação sem a linha da UF')

# ---------- admin: agrupamento editável ----------
entrar(pm, 'admin@pmbora.localhost', os.environ.get('SENHA_INICIAL_ADMIN', 'admin123'), 'adminforte12345')
t = ok(pm.get('/admin/indicadores?area=geral'), txt='Agrupamento das unidades por área', nome='admin áreas').text
if 'GABINETE TESTE' not in t or 'sugestão automática' not in t: falha('tabela de áreas no admin')
pm.post('/admin/indicadores', data={'csrf': tok(pm, '/admin/indicadores'), 'acao': 'areas', 'area_04': 'Educação'})
a = db.um(PM, "SELECT * FROM areas_unidades WHERE codigo='04'")
if a['area'] != 'Educação' or a['origem'] != 'admin': falha(f'troca de área: {a}')
if not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Painel de indicadores: agrupamento das unidades por área alterado%%'"): falha('troca de área sem auditoria')
worker.rodar(f, 'financas', f['params'])
if db.um(PM, "SELECT area FROM areas_unidades WHERE codigo='04'")['area'] != 'Educação': falha('coleta desfez a área definida pelo administrador')
t = pm.get('/painel?tema=edu').text
if 'Merenda Teste' not in t: falha('orçamento da área não seguiu o agrupamento editado')
pm.post('/admin/indicadores', data={'csrf': tok(pm, '/admin/indicadores'), 'acao': 'areas', 'sugestao_04': '1', 'area_04': 'Educação'})
worker.rodar(f, 'financas', f['params'])
if db.um(PM, "SELECT area FROM areas_unidades WHERE codigo='04'")['area'] != 'Assistência Social': falha('voltar à sugestão')

# ---------- foco em anel duplo no portal e no admin ----------
for css in ('app/static/portal.css', 'app/static/admin.css'):
    if '0 0 0 7px #17212B' not in Path(css).read_text(): falha(f'{css} sem o anel duplo de foco')

print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
