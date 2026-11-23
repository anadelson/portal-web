# Finanças da Prefeitura no painel da Câmara (23/11/2026) — SEM internet; banco de TESTE com dados FICTÍCIOS de teste.
# Rode só contra banco de TESTE já provisionado:  TESTE=1 DATA_SIMULADA=2026-11-23T10:00 PYTHONPATH=. python tests/teste_financas_prefeitura.py
import os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import date
from fastapi.testclient import TestClient
from app.main import app
from app import db, worker, config, consultas as CS, integracao as IG, orgaos
from app.coletores import financas_prefeitura as FP, comum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar

erros = []
def falha(m): erros.append(m)
def checa(c, m):
    if not c: falha(m)
CM, PM = 'bd_cm_bora', 'bd_pm_bora'
cm = TestClient(app, base_url='http://cmbora.localhost')
pm = TestClient(app, base_url='http://pmbora.localhost')
o_cm = orgaos.por_slug('cm-bora'); o_pm = orgaos.por_slug('pm-bora')
for o in (o_cm, o_pm):
    db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=TRUE WHERE orgao_id=%s AND chave='bi'", (o['id'],))

def _sem_rede(*a, **k): raise AssertionError('chamada à internet no teste')
comum.buscar = FP.buscar = _sem_rede
def publico(destino, caminho):  # Prefeitura cliente na mesma instalação: a API pública dela, servida aqui
    checa(destino['slug'] == 'pm-bora', f'API pública de quem? {destino["slug"]}')
    r = pm.get(caminho)
    r.raise_for_status()
    return r.json()
IG.publico = publico

def fonte_cm():
    return db.um(db.PLATAFORMA, "SELECT * FROM fontes WHERE orgao_id=%s AND fonte='financas_prefeitura'", (o_cm['id'],))
def params(p):
    db.exe(db.PLATAFORMA, "UPDATE fontes SET params=%s WHERE orgao_id=%s AND fonte='financas_prefeitura'", (comum.Jsonb(p), o_cm['id']))
def coletar():
    f = fonte_cm()
    return worker.rodar(dict(o_cm, fonte='financas_prefeitura', params=f['params']), 'financas_prefeitura', f['params'])
def resumo():
    return (FP.atual(CM).get('resumo') or {})
def pagina():
    r = cm.get('/painel?tema=fin'); checa(r.status_code == 200, f'painel da Câmara: {r.status_code}')
    return r.text

# ---------- provisionamento: só a Câmara tem a fonte, em modo automático ----------
f = fonte_cm()
checa(f and f['ativo'] and f['params'].get('modo') == 'auto' and f['params'].get('ibge') == str(o_cm['ibge']), f'fonte da Câmara: {f and f["params"]}')
checa(not db.um(db.PLATAFORMA, "SELECT 1 FROM fontes WHERE orgao_id=%s AND fonte='financas_prefeitura'", (o_pm['id'],)), 'Prefeitura não deveria ter financas_prefeitura')
checa('financas_prefeitura' in worker.PAINEL and worker.FREQ['financas_prefeitura'][1] == range(1, 5), 'fonte fora do agendamento de madrugada do painel')
r = FP.coletar(o_pm, {})
checa(not r[0][1] and 'só para a Câmara' in r[0][3], f'coletor rodando na Prefeitura: {r}')

# ---------- sem resumo: nenhum bloco de finanças na Câmara ----------
t = pagina()
checa('Dinheiro público' not in re.sub(r'<nav class="ppilulas".*?</nav>', '', t, flags=re.S), 'bloco de finanças sem resumo')
checa('Finanças lidas do sistema contábil' not in t, 'selo do sistema contábil na Câmara')

# ---------- Siconfi (modo automático: a Prefeitura cliente ainda não tem finanças → API 404 → Siconfi) ----------
INST = 'Prefeitura Municipal de Teste - SP'
def it(cod, conta, col, v): return {'cod_conta': cod, 'conta': conta, 'coluna': col, 'valor': v, 'instituicao': INST, 'rotulo': 'Padrão'}
def anexo1(per):
    ac = 2_000_000 * per
    return [it('TotalReceitas', 'TOTAL DAS RECEITAS (V) = (III + IV)', 'PREVISÃO ATUALIZADA (a)', 12_000_000), it('TotalReceitas', 'TOTAL DAS RECEITAS (V) = (III + IV)', 'No Bimestre (b)', 2_000_000),
            it('TotalReceitas', 'TOTAL DAS RECEITAS (V) = (III + IV)', 'Até o Bimestre (c)', ac),
            it('TransferenciasCorrentes', 'TRANSFERÊNCIAS CORRENTES', 'Até o Bimestre (c)', 0.8 * ac), it('TransferenciasDeCapital', 'TRANSFERÊNCIAS DE CAPITAL', 'Até o Bimestre (c)', 0.05 * ac),
            it('Impostos', 'Impostos', 'Até o Bimestre (c)', 0.1 * ac), it('Taxas', 'Taxas', 'Até o Bimestre (c)', 0.01 * ac),
            it('TransferenciasCorrentesDaUniaoEDeSuasEntidades', 'Transferências da União e de suas Entidades', 'Até o Bimestre (c)', 0.5 * ac),
            it('TransferenciasCorrentesDosEstadosEDoDistritoFederalEDeSuasEntidades', 'Transferências dos Estados', 'Até o Bimestre (c)', 0.3 * ac),
            it('TotalDespesas', 'TOTAL DAS DESPESAS (XII) = (X + XI)', 'DOTAÇÃO ATUALIZADA (e)', 13_000_000),
            it('TotalDespesas', 'TOTAL DAS DESPESAS (XII) = (X + XI)', 'DESPESAS EMPENHADAS ATÉ O BIMESTRE (f)', 1_800_000 * per),
            it('TotalDespesas', 'TOTAL DAS DESPESAS (XII) = (X + XI)', 'DESPESAS PAGAS ATÉ O BIMESTRE (j)', 1_500_000 * per + (100_000 if per >= 3 else 0))]
ANEXO2 = [it('RREO2TotalDespesas', c, 'DESPESAS EMPENHADAS ATÉ O BIMESTRE (b)', v) for c, v in
          (('Saúde', 3_000_000), ('Atenção Básica', 2_500_000), ('Educação', 2_500_000), ('Ensino Fundamental', 2_000_000), ('Administração', 1_500_000), ('Legislativa', 500_000))] + \
         [it('RREO2TotalDespesas', 'Saúde', 'DOTAÇÃO INICIAL', 9_999_999)]
pedidos = []
def sic(fonte, url, params=None, **kw):
    checa(fonte == 'siconfi' and url == FP.SICONFI, f'consulta fora do Siconfi: {fonte} {url}')
    p = params or {}
    pedidos.append((p['an_exercicio'], p['nr_periodo'], p['no_anexo']))
    if p['an_exercicio'] != 2026 or p['nr_periodo'] > 5:
        return {'items': []}
    return {'items': anexo1(p['nr_periodo']) if p['no_anexo'] == 'RREO-Anexo 01' else ANEXO2}
FP.buscar = sic
checa(pm.get('/painel/api/financas.json').status_code == 404, 'API de finanças da Prefeitura sem dados deveria ser 404')
res = coletar()
checa(res and res[0][1], f'coleta Siconfi: {res}')
rs = resumo()
checa(rs.get('origem') == 'siconfi' and rs.get('ano') == 2026 and rs.get('ate') == '2026-10-31' and rs.get('nome') == INST, f'resumo Siconfi: {rs.get("origem")} {rs.get("ate")} {rs.get("nome")}')
checa((2026, 6, 'RREO-Anexo 01') in pedidos and (2026, 5, 'RREO-Anexo 02') in pedidos and not any(a == 2025 for a, _, _ in pedidos), f'pedidos ao Siconfi: {pedidos}')
s = rs['serie']['itens']
checa(rs['serie']['tipo'] == 'bimestre' and [x['n'] for x in s] == [1, 2, 3, 4, 5], f'série por bimestre: {s}')
checa([x['despesa_paga'] for x in s] == [1_500_000, 1_500_000, 1_600_000, 1_500_000, 1_500_000], f'despesa paga no bimestre (diferença dos acumulados): {[x["despesa_paga"] for x in s]}')
checa([a['area'] for a in rs['areas']['itens']] == ['Saúde', 'Educação', 'Administração', 'Legislativa'] and rs['areas']['tipo'] == 'função de governo', f'funções (sem subfunções): {rs["areas"]}')
checa(rs['receita']['arrecadada'] == 10_000_000 and rs['despesa']['paga'] == 7_600_000 and rs['link'].startswith(FP.SICONFI), f'totais: {rs["receita"]["arrecadada"]} {rs["despesa"]["paga"]}')
checa([o['nome'] for o in rs['receita']['origens']][:2] == ['Transferências correntes da União', 'Transferências correntes do Estado'], f'origens: {rs["receita"]["origens"]}')
t = pagina()
for x in ('Dinheiro público da Prefeitura', f'Números da <strong>{INST}</strong>, não da Câmara', 'Siconfi (Tesouro Nacional) — RREO, Anexos 1 e 2, do 5º bimestre de 2026', 'ver a fonte',
          'Receita da Prefeitura, 2026', 'R$ 10,0 mi', 'até o 5º bimestre de 2026, 83% do previsto', 'Receita vinda de repasses', '85%',
          'Receita e despesa paga, bimestre a bimestre', 'Do 1º ao 5º bimestre de 2026 entraram R$ 10,0 mi e foram pagos R$ 7,6 mi pela Prefeitura', '5º bim.',
          'diferença entre os valores acumulados', 'Para onde vai o dinheiro', 'por função de governo', 'Saúde e educação somam 73%', 'De onde vem o dinheiro',
          'De cada R$ 100 que entram na Prefeitura, R$ 85', 'Execução do orçamento de 2026', 'Base legal:'):
    checa(x in t, f'painel Siconfi: falta "{x}"')
checa('Atenção Básica' not in t and 'Finanças lidas do sistema contábil' not in t, 'subfunção ou selo do sistema contábil no painel da Câmara')
checa(not db.um(CM, 'SELECT 1 FROM receitas LIMIT 1') and not db.um(CM, 'SELECT 1 FROM despesas_unidade LIMIT 1') and not db.um(CM, 'SELECT 1 FROM fin_mensal LIMIT 1'),
      'dado da Prefeitura gravado nas tabelas da transparência da Câmara')

# ---------- falha: mantém o último resumo válido e avisa ----------
def quebra(*a, **k): raise comum.httpx.ConnectError('fonte fora do ar (teste)')
FP.buscar = quebra
res = coletar()
checa(res and not res[0][1] and 'mantido o último resumo válido' in res[0][3], f'falha da fonte: {res}')
checa(resumo().get('origem') == 'siconfi' and FP.atual(CM).get('falha_em'), 'resumo perdido na falha')
t = pagina()
checa('não deu certo. Mostramos o último dado válido' in t and 'R$ 10,0 mi' in t, 'aviso de falha com o último dado válido')

# ---------- Prefeitura cliente com finanças: API pública do painel dela ----------
for i, (cod, nome, prev, arr, soma) in enumerate([('1000.00.0.0.00.00', 'RECEITAS CORRENTES', 2000000, 1800000, True), ('2000.00.0.0.00.00', 'RECEITAS DE CAPITAL', 200000, 200000, True),
                                                  ('9000.00.0.0.00.00', '(R) DEDUCOES DA RECEITA', None, -300000, True), ('1700.00.0.0.00.00', 'TRANSFERÊNCIAS CORRENTES', None, 1500000, False),
                                                  ('2400.00.0.0.00.00', 'TRANSFERÊNCIAS DE CAPITAL', None, 100000, False), ('1710.00.0.0.00.00', 'TRANSFERÊNCIAS DA UNIÃO', None, 1100000, False)]):
    db.exe(PM, "INSERT INTO receitas (chave, fonte, ano, mes, codigo, nome, previsto, arrecadado, soma) VALUES (%s,'fiorilli',2026,0,%s,%s,%s,%s,%s)", (f'fpr{i}', cod, nome, prev, arr, soma))
for i, (cod, un, dot, emp, pago, area) in enumerate([('01', 'FUNDO DE SAUDE TESTE', 1000000, 600000, 500000, 'Saúde'), ('02', 'ENSINO TESTE', 800000, 400000, 300000, 'Educação')]):
    db.exe(PM, "INSERT INTO despesas_unidade (chave, fonte, ano, codigo, unidade, dotacao_atualizada, empenhado, pago) VALUES (%s,'fiorilli',2026,%s,%s,%s,%s,%s)", (f'fpd{i}', cod, un, dot, emp, pago))
    db.exe(PM, "INSERT INTO areas_unidades (codigo, unidade, area) VALUES (%s,%s,%s) ON CONFLICT (codigo) DO UPDATE SET area=EXCLUDED.area", (cod, un, area))
for m in range(1, 12):
    db.exe(PM, "INSERT INTO fin_mensal (ano, mes, receita, despesa_paga, despesa_empenhada, parcial, coletado_em) VALUES (2026,%s,%s,%s,%s,%s,now())", (m, 150000, 70000, 90000, m == 11))
r = pm.get('/painel/api/financas.json')
checa(r.status_code == 200 and r.json().get('receita', {}).get('arrecadada') == 1_700_000 and r.headers.get('access-control-allow-origin') == '*', f'API de finanças da Prefeitura: {r.status_code} {r.text[:200]}')
checa(not re.search(r'\d{3}\.\d{3}\.\d{3}-\d{2}', r.text) and 'base_legal' in r.json(), 'API de finanças: CPF ou sem base legal')
checa(cm.get('/painel/api/financas.json').status_code == 404, 'API de finanças só existe no Executivo')
FP.buscar = _sem_rede  # com a Prefeitura cliente, nada de Siconfi
res = coletar()
rs = resumo()
checa(res and res[0][1] and rs.get('origem') == 'cliente' and rs['serie']['tipo'] == 'mes' and len(rs['serie']['itens']) == 11, f'modo automático com a Prefeitura cliente: {res} {rs.get("origem")}')
checa(rs['link'] == f"https://{o_pm['dominio']}/painel?tema=fin" and [a['area'] for a in rs['areas']['itens']] == ['Saúde', 'Educação'], f'link e áreas: {rs.get("link")} {rs["areas"]}')
checa(not FP.atual(CM).get('falha_em'), 'aviso de falha deveria sumir depois de uma coleta boa')
t = pagina()
for x in ('Dinheiro público da Prefeitura', 'Receita e despesa paga, mês a mês', 'De janeiro a novembro (mês em andamento) de 2026', 'R$ 1,7 mi', 'Saúde e educação somam 100%', 'por área'):
    checa(x in t, f'painel cliente: falta "{x}"')
checa('não deu certo' not in t, 'aviso de falha antigo')

# ---------- portal de dados abertos da Prefeitura (Fiorilli), mês a mês ----------
BASE = 'https://portal.prefeitura-teste.test/transparencia/VersaoJson/'
params({'modo': 'portal', 'ibge': str(o_cm['ibge']), 'base': BASE, 'empresa': '7', 'nome': 'Prefeitura de Teste'})
fpedidos = []
def fio(fonte, url, params=None, **kw):
    p = params or {}
    checa(fonte == 'fiorilli' and url.startswith(BASE) and p.get('Empresa') == '7', f'consulta ao portal: {fonte} {url} {p.get("Empresa")}')
    mensal = p['MesInicialPeriodo'] == p['MesFinalPeriodo']
    fpedidos.append((p['Listagem'], p['MesInicialPeriodo'], p['MesFinalPeriodo'], p['DiaFinalPeriodo']))
    if p['Listagem'] == 'ReceitaOrcamentaria':
        if mensal:
            return [{'CODIGO': '1000.00.0.0.00.00', 'ARRECADADO_PERIODO': '800000'}, {'CODIGO': '1700.00.0.0.00.00', 'ARRECADADO_PERIODO': '99999'}]
        return [{'CODIGO': '1000.00.0.0.00.00', 'NOME': 'RECEITAS CORRENTES', 'PREVISAO_ATUALIZADA': '10000000', 'ARRECADADO_TOTAL': '9000000'},
                {'CODIGO': '2000.00.0.0.00.00', 'NOME': 'RECEITAS DE CAPITAL', 'PREVISAO_ATUALIZADA': '1000000', 'ARRECADADO_TOTAL': '1000000'},
                {'CODIGO': '9000.00.0.0.00.00', 'NOME': '(R) DEDUCOES', 'ARRECADADO_TOTAL': '-500000'},
                {'CODIGO': '1700.00.0.0.00.00', 'NOME': 'TRANSFERENCIAS CORRENTES', 'ARRECADADO_TOTAL': '7000000'},
                {'CODIGO': '2400.00.0.0.00.00', 'NOME': 'TRANSFERENCIAS DE CAPITAL', 'ARRECADADO_TOTAL': '300000'},
                {'CODIGO': '1710.00.0.0.00.00', 'NOME': 'TRANSFERENCIAS DA UNIAO', 'ARRECADADO_TOTAL': '4000000'},
                {'CODIGO': '1110.00.0.0.00.00', 'NOME': 'IMPOSTOS', 'ARRECADADO_TOTAL': '800000'},
                {'CODIGO': '1000.00.0.0.00.00', 'FONTE': '01', 'NOME': 'RECEITAS CORRENTES', 'ARRECADADO_TOTAL': '7777777'}]
    if p['Listagem'] == 'DespesasPorUnidade':
        if mensal:
            return [{'CODIGO': '01', 'DESCRICAO': 'X', 'PAGO': '400000'}]
        return [{'CODIGO': '01', 'DESCRICAO': 'FUNDO MUNICIPAL DE SAUDE', 'DOTACAO_ATUALIZADA': '5000000', 'EMPENHADO': '3000000', 'PAGO': '2500000'},
                {'CODIGO': '02', 'DESCRICAO': 'EDUCACAO', 'DOTACAO_ATUALIZADA': '4000000', 'EMPENHADO': '2000000', 'PAGO': '1800000'}]
    raise AssertionError(p)
FP.buscar = fio
res = coletar()
rs = resumo()
checa(res and res[0][1] and rs.get('origem') == 'portal' and rs['link'] == BASE and rs['nome'] == 'Prefeitura de Teste', f'modo portal: {res} {rs.get("origem")}')
checa(rs['receita']['arrecadada'] == 9_500_000 and rs['receita']['prevista'] == 11_000_000 and rs['receita']['repasses'] == 7_300_000 and rs['receita']['base_repasses'] == 10_000_000, f'receitas do portal: {rs["receita"]}')
checa(rs['despesa'] == {'dotacao': 9_000_000, 'empenhada': 5_000_000, 'paga': 4_300_000}, f'despesas do portal: {rs["despesa"]}')
s = rs['serie']['itens']
checa(len(s) == 11 and s[-1]['parcial'] and not s[0]['parcial'] and s[0]['receita'] == 800000 and s[0]['despesa_paga'] == 400000, f'série mensal do portal: {s[:2]} … {s[-1:]}')
checa(('ReceitaOrcamentaria', '11', '11', '23') in fpedidos, 'mês corrente deveria ir até o dia de hoje')
checa(rs['areas']['tipo'] == 'unidade orçamentária' and rs['areas']['itens'][0]['area'] == 'Fundo municipal de saude', f'unidades: {rs["areas"]}')
t = pagina()
for x in ('Números da <strong>Prefeitura de Teste</strong>, não da Câmara', 'portal da transparência da Prefeitura (API pública de dados abertos do sistema contábil)',
          'Receita e despesa paga, mês a mês', 'R$ 9,5 mi', 'por unidade orçamentária', '73%'):
    checa(x in t, f'painel portal: falta "{x}"')

# ---------- validação dos parâmetros (tela de integrações) ----------
def val(**form):
    base = {'p_modo': 'auto', 'p_ibge': '3507209', 'p_base': '', 'p_empresa': '', 'p_link': '', 'p_nome': ''}
    base.update(form)
    return CS.validar('financas_prefeitura', base, {})
n, e = val()
checa(not e and n['modo'] == 'auto', f'parâmetros válidos recusados: {e}')
n, e = val(p_modo='siconfi', p_link='https://www.prefeitura-teste.test/transparencia')
checa(not e and n['modo'] == 'siconfi', f'siconfi com link: {e}')
for form, msg in (({'p_modo': 'qualquer'}, 'escolha uma das opções'), ({'p_modo': 'portal'}, 'Modo portal'), ({'p_base': 'http://portal.teste.test/x/'}, 'https://'),
                  ({'p_base': 'https://localhost/x/', 'p_empresa': '1'}, 'domínio público'), ({'p_base': 'https://10.0.0.5/x/', 'p_empresa': '1'}, 'domínio público'),
                  ({'p_link': 'https://db/'}, 'domínio público'), ({'p_empresa': 'abc'}, 'só números'), ({'p_ibge': '123'}, '7 dígitos')):
    n, e = val(**form)
    checa(any(msg in x for x in e), f'validação deveria recusar {form}: {e}')

# ---------- administração ----------
c = TestClient(app, base_url='http://cmbora.localhost')
checa(entrar(c, 'admin@cmbora.localhost', 'admin123', 'senhaforte123').status_code == 200, 'login da Câmara')
t = c.get('/admin/indicadores?area=geral').text
for x in ('Finanças da Prefeitura no painel', 'publicado', 'Portal de dados abertos da Prefeitura', '/admin/integracoes?fonte=financas_prefeitura'):
    checa(x in t, f'admin indicadores: falta "{x}"')
r = c.get('/admin/integracoes?fonte=financas_prefeitura')
checa(r.status_code == 200 and 'Finanças da Prefeitura (fonte pública)' in r.text and '<option value="siconfi"' in r.text and 'selected' in r.text, f'tela de integrações: {r.status_code}')
checa('RREO-Anexo 01' in r.text or 'Portal da Prefeitura — receitas' in r.text, 'endpoints da consulta')
p2 = TestClient(app, base_url='http://pmbora.localhost')
checa(entrar(p2, 'admin@pmbora.localhost', 'admin123', 'senhaforte123').status_code == 200, 'login da Prefeitura')
checa('Finanças da Prefeitura no painel' not in p2.get('/admin/indicadores?area=geral').text, 'quadro da Câmara na Prefeitura')

print('FALHAS:' if erros else 'OK: finanças da Prefeitura no painel da Câmara (Siconfi, portal, Prefeitura cliente, falha, validação, administração)')
for x in erros:
    print(' -', x)
sys.exit(1 if erros else 0)
