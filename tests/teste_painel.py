# Fase 7: painel de indicadores (módulo "bi") — SEM internet: as respostas das fontes vêm de tests/fixtures/painel_respostas.json.
# Rode só contra banco de TESTE já provisionado:  TESTE=1 DATA_SIMULADA=2026-11-06T10:00 PYTHONPATH=. python tests/teste_painel.py
import csv, io, json, os, re, sys, zipfile
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import db, worker, painel as P
from app.coletores import indicadores as I, comum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

F = json.loads((Path(__file__).parent / 'fixtures' / 'painel_respostas.json').read_text(encoding='utf-8'))
erros = []
def falha(m): erros.append(m)
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
pm, cm = TestClient(app, base_url='http://pmbora.localhost'), TestClient(app, base_url='http://cmbora.localhost')
def ok(r, cod=200, txt=None, nome=''):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {r.text[:200]}')
    return r

chamadas = []
def fake(fonte, url, params=None, **kw):
    p = params or {}
    chamadas.append((fonte, url, dict(p)))
    if 'agregados/6579/' in url: return F['ibge_v3_6579']
    if 'agregados/4709/' in url: return F['ibge_v3_4709']
    if url.endswith('pesquisas/19/periodos'): return F['ibge_periodos_19']
    m = re.search(r'/indicadores/(\d+)/resultados/', url)
    if m:
        if '/19/periodos/' in url and '2021' in url: raise AssertionError('CEMPRE: períodos de versões diferentes na mesma consulta')
        return F[f'ibge_{m.group(1)}']
    m = re.search(r'apisidra.*/t/(\d+)/', url)
    if m: return F[f'sidra_{m.group(1)}']
    if url.endswith('cnes/tipounidades'): return F['cnes_tipos']
    if url.endswith('cnes/estabelecimentos'):
        if p.get('codigo_municipio') != '350720': raise AssertionError('CNES: código IBGE de 6 dígitos esperado')
        return F['cnes_estab'] if p.get('offset', 0) == 0 else {'estabelecimentos': []}
    if 'siconfi/tt/rreo' in url: return {'items': F['siconfi'].get(f"{p['an_exercicio']}-{p['nr_periodo']}", [])}
    if 'misocial' in url: raise ValueError('fonte fora do ar (teste)')
    raise AssertionError(f'chamada inesperada: {url} {p}')
I.buscar = fake

oid = db.um(db.PLATAFORMA, "SELECT id FROM orgaos WHERE slug='pm-bora'")['id']
def bi(lig):
    db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=%s WHERE orgao_id=%s AND chave='bi'", (lig, oid))

# ---------- provisionamento: catálogo e fontes ----------
n = db.um(PM, 'SELECT count(*) n FROM indicadores')['n']
if n != len(P.CATALOGO): falha(f'catálogo semeado com {n} de {len(P.CATALOGO)} indicadores')
if db.um(CM, 'SELECT count(*) n FROM indicadores')['n']: falha('Câmara não deveria ter catálogo (não tem painel nesta fase)')
fts = {f['fonte']: f['ativo'] for f in db.todos(db.PLATAFORMA, 'SELECT fonte, ativo FROM fontes WHERE orgao_id=%s', (oid,))}
if not (fts.get('ibge') and fts.get('cnes') and fts.get('painel') and fts.get('mds') is False and fts.get('pni') is False):
    falha(f'fontes do painel mal configuradas: {fts}')
if db.um(PM, 'SELECT count(*) n FROM indicadores WHERE destaque')['n'] > P.MAX_DESTAQUES: falha('mais de 4 destaques no catálogo padrão')
# idempotência: semear de novo não duplica e não sobrescreve o que o administrador mudou
db.exe(PM, "UPDATE indicadores SET descricao='Texto do administrador', ordem=7 WHERE chave='mun_salario_medio'")
P.semear(PM)
x = db.um(PM, "SELECT * FROM indicadores WHERE chave='mun_salario_medio'")
if x['descricao'] != 'Texto do administrador' or x['ordem'] != 7: falha('semear sobrescreveu a configuração do administrador')

# ---------- módulo desligado: nada do painel aparece ----------
bi(False)
ok(pm.get('/painel'), 404, nome='painel sem módulo')
ok(pm.get('/painel/api/indicadores.json'), 404, nome='api sem módulo')
if 'ind-home' in pm.get('/').text: falha('bloco de indicadores na home sem o módulo')
f_ibge = db.um(db.PLATAFORMA, "SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.fonte='ibge'", (oid,))
if worker.bi_ligado(f_ibge): falha('worker acha que o bi está ligado')

# ---------- dados do próprio órgão (fictícios, só no banco de TESTE) ----------
for i, (fonte, ano, mes, arr, prev, soma) in enumerate([('fiorilli', 2026, 0, 1000000, 2000000, True), ('fiorilli', 2026, 0, 500000, None, True), ('fiorilli', 2026, 0, 999999, None, False)]
                                                      + [('tcesp', 2025, m, 100000, None, True) for m in range(1, 13)]):
    db.exe(PM, 'INSERT INTO receitas (chave, fonte, ano, mes, nome, previsto, arrecadado, soma) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (f'teste-{i}', fonte, ano, mes, 'Receita de teste', prev, arr, soma))
for i, (d, e, pg) in enumerate([(1000000, 600000, 300000), (1000000, 400000, 200000)]):
    db.exe(PM, "INSERT INTO despesas_unidade (chave, fonte, ano, codigo, unidade, dotacao_atualizada, empenhado, pago) VALUES (%s,'fiorilli',2026,%s,'UNIDADE TESTE',%s,%s,%s)", (f'du-{i}', str(i), d, e, pg))
for i, (ano, mod, v) in enumerate([(2024, 'Dispensa', 50), (2025, 'Dispensa', 1000), (2025, 'Dispensa', 1000), (2025, 'Pregão - Eletrônico', 5000), (2025, 'Inexigibilidade', None),
                                   (2026, 'Dispensa', 200), (2026, 'Dispensa', 300), (2026, 'Concorrência - Presencial', 10000)]):
    db.exe(PM, "INSERT INTO licitacoes (chave, fonte, ano, modalidade, objeto, valor) VALUES (%s,'pncp',%s,%s,'Objeto de teste',%s)", (f'lic-{i}', ano, mod, v))
for i in range(7):  # 6 pedidos respondidos (5 no prazo, 1 com 25 dias sem justificativa) e 1 em aberto; 3 manifestações
    resp = None if i == 6 else (date(2026, 3, 1 + i) if i < 5 else date(2026, 3, 26))
    db.exe(PM, "INSERT INTO esic (protocolo, tipo, assunto, texto, nome, email, recebido, situacao, respondido) VALUES (%s,'pedido','Assunto','Texto','Pessoa de Teste','teste@exemplo.invalid',%s,%s,%s)",
           (f'SIC-T{i}', date(2026, 3, 1), 'respondido' if resp else 'recebido', resp))
for i in range(3):
    db.exe(PM, "INSERT INTO esic (protocolo, tipo, assunto, texto, nome, email, recebido) VALUES (%s,'manifestacao','Assunto','Texto','Pessoa de Teste','teste@exemplo.invalid',%s)", (f'OUV-T{i}', date(2026, 4, 1)))

# ---------- coleta ----------
bi(True)
fontes = [f for f in worker.fontes_ativas() if f['slug'] == 'pm-bora' and f['fonte'] in worker.PAINEL]
if {f['fonte'] for f in fontes} != {'ibge', 'cnes', 'painel'}: falha(f"fontes ativas do painel: {[f['fonte'] for f in fontes]}")
for f in fontes:
    for base, ok_, n_, msg in worker.rodar(f, f['fonte'], f['params']):
        if not ok_: falha(f"coleta {f['fonte']}:{base} falhou: {msg}")
        if f['fonte'] == 'ibge' and 'sem resposta' in msg: falha(f'IBGE com indicador sem resposta: {msg}')
for f in fontes:  # 2ª vez: idempotente
    worker.rodar(f, f['fonte'], f['params'])
if db.um(db.PLATAFORMA, "SELECT count(*) n FROM coletas WHERE orgao_slug='pm-bora' AND fonte LIKE 'painel:%%'")['n'] < 2: falha('coleta do painel não registrada em coletas')
if not db.um(db.PLATAFORMA, "SELECT 1 FROM indicadores_publicos WHERE ibge='3507209' AND indicador='mun_populacao' AND periodo='2026' AND valor=935"): falha('dado nacional não gravado por código IBGE')

def val(chave, per):
    r = db.um(PM, 'SELECT v.* FROM indicador_valores v JOIN indicadores i ON i.id=v.indicador_id WHERE i.chave=%s AND v.periodo=%s', (chave, per))
    return r
esperado = {('mun_populacao', '2026'): 935, ('mun_populacao', '2022'): 907, ('mun_pib_per_capita', '2023'): 133365.32, ('mun_pessoal_ocupado', '2024'): 1306,
            ('mun_salario_medio', '2023'): 2.5, ('mun_esgoto', '2022'): 84.78, ('edu_alfabetizacao', '2022'): 94.36, ('edu_ideb_ai_mun', '2025'): 6.6,
            ('edu_ideb_af_est', '2025'): 5.3, ('saude_nascidos', '2023'): 1, ('saude_obitos', '2024'): 7, ('saude_estabelecimentos', 'nov/2026'): 2,
            ('saude_minimo', '2025'): 20.36, ('edu_mde_minimo', '2024'): 28.58, ('edu_fundeb_minimo', '2025'): 97.73, ('saude_minimo', '2026'): 16.95,
            ('fin_receita', '2026'): 1500000, ('fin_receita', '2025'): 1200000, ('fin_receita_prevista', '2026'): 75, ('fin_despesa_paga', '2026'): 500000,
            ('fin_empenhada_dotacao', '2026'): 50, ('cont_publicadas', '2025'): 4, ('cont_publicadas', '2026'): 3, ('cont_dispensa', '2025'): 50, ('cont_valor', '2025'): 7000,
            ('gestao_sic_pedidos', '2026'): 7, ('gestao_ouv_manifestacoes', '2026'): 3}
for (k, per), v in esperado.items():
    r = val(k, per)
    if not r or r['valor'] is None or abs(float(r['valor']) - v) > 0.01: falha(f'{k} {per}: esperado {v}, gravado {r and r["valor"]}')
r = val('gestao_sic_no_prazo', '2026')
if not r or abs(float(r['valor']) - 500 / 6) > 0.01: falha(f'e-SIC no prazo: {r and r["valor"]}')
if val('edu_ideb_ai_mun', '2019'): falha('IDEB "-" virou número')
if val('edu_fundeb_minimo', '2026'): falha('FUNDEB 2026 inventado (o RREO não traz)')
if not val('saude_minimo', '2026')['parcial'] or val('saude_minimo', '2025')['parcial']: falha('marca de período parcial do RREO')
if '1 publicação' not in val('cont_valor', '2025')['nota']: falha('nota de publicações sem valor')
if val('mun_populacao', '2023'): falha('população 2023 inventada (não há estimativa nem Censo)')
if val('cont_publicadas', '2024'): falha('PNCP: ano mais antigo da coleta (possivelmente incompleto) foi publicado')
# coleta parcial do PNCP: se o banco perde a cobertura do ano anterior, o ano deixa de ser publicado
db.exe(PM, "UPDATE licitacoes SET ano=2025 WHERE fonte='pncp' AND ano=2024")
fp = [f for f in fontes if f['fonte'] == 'painel'][0]
worker.rodar(fp, 'painel', fp['params'])
if val('cont_publicadas', '2025') or val('cont_valor', '2025') or not val('cont_publicadas', '2026'): falha('PNCP: ano incompleto continuou publicado')
db.exe(PM, "UPDATE licitacoes SET ano=2024 WHERE chave='lic-0'")
worker.rodar(fp, 'painel', fp['params'])
if not val('cont_publicadas', '2025') or float(val('cont_publicadas', '2025')['valor']) != 4: falha('PNCP: ano completo não voltou')
for k in ('social_bf_familias', 'saude_vacinacao', 'edu_saeb', 'gestao_iegm'):
    if db.um(PM, 'SELECT 1 FROM indicador_valores v JOIN indicadores i ON i.id=v.indicador_id WHERE i.chave=%s', (k,)): falha(f'{k} tem valor sem fonte')
# fontes desligadas falham sem derrubar nada
for fonte in ('mds', 'pni'):
    f = db.um(db.PLATAFORMA, "SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.fonte=%s", (oid, fonte))
    res = worker.rodar(f, fonte, f['params'])
    if any(x[1] for x in res): falha(f'{fonte} deveria falhar (fonte fora do ar / desligada)')

# ---------- páginas públicas ----------
r = ok(pm.get('/painel'), txt='Base legal:', nome='painel')
for t in ('Dinheiro público', 'Contratações', 'Saúde', 'Educação', 'Assistência social', 'Município e gestão', 'Tudo', 'População estimada', 'Fonte:', 'atualizado em', 'Referência:'):
    if t not in r.text: falha(f'painel: falta "{t}"')
if 'aria-current="page">Tudo' not in r.text: falha('aba atual sem aria-current')
if 'Mínimo legal: 15% · atingido' not in r.text: falha('texto da meta de saúde')
if 'ainda em andamento: sem comparação' not in r.text: falha('variação do ano parcial deveria ser só texto, sem comparação')
if '+0,3% em relação a 2025' not in r.text: falha('variação da população 2026 × 2025 em texto')  # 935/932 = +0,32%
if 'Pessoa de Teste' in r.text or 'teste@exemplo' in r.text: falha('dado pessoal no painel')
if 'aparecem quando a fonte oficial do Ministério' not in r.text: falha('aviso neutro da assistência social')
if 'Doses de vacina' in r.text or 'IEG-M' in r.text: falha('indicador sem dado apareceu')
r = ok(pm.get('/painel?aba=saude'), nome='aba saúde')
if 'IDEB' in r.text or 'Nascidos vivos' not in r.text: falha('filtro da aba saúde')
if 'menos de 5' not in r.text: falha('nascidos vivos 2024 (4) deveria aparecer como "menos de 5"')
ok(pm.get('/painel?aba=xyz'), txt='aria-current="page">Tudo', nome='aba inválida')
# página do indicador: gráfico SVG acessível + tabela equivalente
r = ok(pm.get('/painel/saude_nascidos'), nome='indicador nascidos')
t = r.text
if not re.search(r'<svg class="grafico"[^>]*role="img"[^>]*aria-labelledby="[^"]+"', t) or '<title id=' not in t or '<desc id=' not in t: falha('gráfico sem role/título/descrição')
if '<caption>' not in t or '<th scope="row">2023</th>' not in t: falha('tabela equivalente ao gráfico')
desc = re.search(r'<desc id="[^"]+">([^<]+)</desc>', t).group(1)
for per in ('2020', '2021', '2022', '2023', '2024'):
    if per not in desc or f'<th scope="row">{per}</th>' not in t: falha(f'período {per} fora do gráfico ou da tabela')
if '2023: menos de 5' not in desc: falha('descrição do gráfico mostra contagem pequena')
if re.search(r'<td class="num">[1-4]</td>', t): falha('contagem abaixo de 5 exibida na tabela')
if 'stroke-dasharray="4 3"' not in t: falha('barra tracejada para "menos de 5"')
for x in ('Base legal:', 'Periodicidade', 'Data de referência', 'Última atualização', 'sidra.ibge.gov.br/tabela/2612'):
    if x not in t: falha(f'indicador: falta "{x}"')
r = ok(pm.get('/painel/saude_minimo'), nome='indicador saúde')
if 'Mínimo 15%' not in r.text or 'stroke-dasharray="7 5"' not in r.text: falha('linha da meta no gráfico')
if 'apidatalake.tesouro.gov.br' not in r.text or 'id_ente=3507209' not in r.text: falha('link da fonte com o código IBGE')
r = ok(pm.get('/painel/saude_estabelecimentos'), txt='Composição em nov/2026', nome='composição CNES')
ok(pm.get('/painel/cont_publicadas'), txt='Concorrência - Presencial', nome='composição por modalidade (último período)')
ok(pm.get('/painel/edu_saeb'), 404, nome='indicador sem dado não aparece')
ok(pm.get('/painel/nao_existe'), 404, nome='indicador inexistente')
# downloads
c = ok(pm.get('/painel/baixar/saude_nascidos.csv'), nome='csv indicador')
rows = list(csv.DictReader(io.StringIO(c.content.decode('utf-8-sig'))))
r23 = [x for x in rows if x['periodo'] == '2023']
if not r23 or r23[0]['valor'] != '' or r23[0]['valor_exibido'] != 'menos de 5' or not r23[0]['fonte'] or not r23[0]['data_referencia'] or not r23[0]['coletado_em']:
    falha(f'CSV: supressão ou colunas de fonte/data: {r23}')
j = ok(pm.get('/painel/baixar/saude_nascidos.json'), nome='json indicador').json()
if any(x['valor'] is not None and x['valor'] < 5 for x in j['registros']) or not j['base_legal']: falha('JSON com contagem pequena ou sem base legal')
o = ok(pm.get('/painel/baixar/saude_nascidos.ods'), nome='ods indicador')
z = zipfile.ZipFile(io.BytesIO(o.content))
if z.namelist()[0] != 'mimetype' or z.read('mimetype') != b'application/vnd.oasis.opendocument.spreadsheet' or z.getinfo('mimetype').compress_type != zipfile.ZIP_STORED: falha('ODS: mimetype')
cx = z.read('content.xml').decode()
if 'menos de 5' not in cx or 'office:value="1.0"' in cx or 'link_fonte' not in cx: falha('ODS: conteúdo')
todos = list(csv.DictReader(io.StringIO(ok(pm.get('/painel/baixar/painel.csv'), nome='csv painel').content.decode('utf-8-sig'))))
if len({x['chave'] for x in todos}) < 20: falha(f"CSV do painel com poucos indicadores: {len({x['chave'] for x in todos})}")
if any('Pessoa de Teste' in json.dumps(x) for x in todos): falha('dado pessoal no download')
jp = ok(pm.get('/painel/baixar/painel.json'), nome='json painel').json()
zp = zipfile.ZipFile(io.BytesIO(ok(pm.get('/painel/baixar/painel.ods'), nome='ods painel').content))
if len(jp['registros']) != len(todos) or zp.read('content.xml').decode().count('<table:table-row>') != len(todos) + 1: falha('CSV, JSON e ODS do painel inconsistentes')
ok(pm.get('/painel/baixar/saude_nascidos.xls'), 404, nome='formato inválido')
ok(pm.get('/dados-abertos'), txt='/painel/baixar/saude_nascidos.ods', nome='dados abertos lista o painel')
api = ok(pm.get('/painel/api/indicadores.json'), nome='api').json()
pop = [x for x in api['indicadores'] if x['chave'] == 'mun_populacao']
if not pop or pop[0]['valor'] != 935 or pop[0]['periodo'] != '2026' or not pop[0]['fonte']: falha(f'API: {pop}')
if [x for x in api['indicadores'] if x['chave'] == 'gestao_ouv_manifestacoes'][0]['valor'] is not None: falha('API devolve contagem pequena')
ok(pm.get('/painel/api/saude_minimo.json'), txt='registros', nome='api indicador')
ok(cm.get('/painel'), 404, nome='Câmara sem painel próprio')
# home: bloco com os destaques do catálogo
r = ok(pm.get('/'), txt='ind-home', nome='home com destaques')
if r.text.count('/painel/') < 4 or 'Borá em números' not in r.text: falha('bloco "Indicadores em números" com os destaques')
ok(pm.get('/transparencia'), txt='href="/painel"', nome='atalho na central de transparência')

# ---------- falha da fonte: mantém o último valor com aviso ----------
def quebra(*a, **k): raise comum.httpx.ConnectError('fonte fora do ar (teste)')
I.buscar = quebra
res = worker.rodar(f_ibge, 'ibge', f_ibge['params'])
if any(x[1] for x in res): falha('coleta do IBGE deveria falhar')
if float(val('mun_populacao', '2026')['valor']) != 935: falha('falha da fonte apagou o valor')
r = ok(pm.get('/painel/mun_populacao'), txt='a última consulta à fonte falhou', nome='aviso dado antigo')
if 'Dado de ' not in r.text or '935' not in r.text: falha('aviso "dado de <data>" com o último valor válido')
if 'a última consulta à fonte falhou' in pm.get('/painel/fin_receita').text: falha('aviso de falha em indicador de outra fonte')
I.buscar = fake
worker.rodar(f_ibge, 'ibge', f_ibge['params'])
if 'a última consulta à fonte falhou' in pm.get('/painel/mun_populacao').text: falha('aviso continuou depois de coleta boa')

# ---------- painel administrativo ----------
entrar(pm, 'admin@pmbora.localhost', os.environ.get('SENHA_INICIAL_ADMIN', 'admin123'), 'adminforte12345')
r = ok(pm.get('/admin/indicadores'), txt='Catálogo de indicadores', nome='admin lista')
for x in ('aguardando primeira coleta', 'Coletar agora', 'Pendente de fonte estável', 'Histórico de alterações', 'href="/admin/indicadores"'):
    if x not in r.text: falha(f'admin: falta "{x}"')
iegm = db.um(PM, "SELECT id FROM indicadores WHERE chave='gestao_iegm'")['id']
url = f'/admin/indicadores/{iegm}'
ok(pm.get(url), txt='Lançamento manual', nome='admin indicador manual')
r = pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2024', 'data_ref': '2024-12-31', 'texto': 'B', 'nota': 'resultado publicado pelo TCESP',
                       'motivo': 'abc'}, follow_redirects=True)
if val('gestao_iegm', '2024'): falha('lançamento sem motivo aceito')
r = pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2024', 'data_ref': '2024-12-31', 'texto': 'Z', 'motivo': 'Resultado publicado pelo Tribunal (teste)'}, follow_redirects=True)
if val('gestao_iegm', '2024'): falha('faixa inválida aceita')
r = pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2024', 'data_ref': '2024-12-31', 'texto': 'B', 'nota': 'documento de teste',
                       'motivo': 'Valor de TESTE para conferir o fluxo de lançamento'}, follow_redirects=True)
v = val('gestao_iegm', '2024')
if not v or v['texto'] != 'B' or v['origem'] != 'manual' or not v['usuario'] or 'TESTE' not in v['motivo']: falha(f'lançamento manual: {v}')
if not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Painel de indicadores: lançamento manual%%'"): falha('lançamento manual sem auditoria')
if not db.um(PM, "SELECT 1 FROM indicador_historico WHERE indicador_id=%s AND acao LIKE 'Lançamento manual%%'", (iegm,)): falha('lançamento manual sem histórico')
ok(pm.get('/painel?aba=mun'), txt='IEG-M — resultado geral', nome='IEG-M lançado aparece')
ok(pm.get('/painel/gestao_iegm'), txt='Lançamento manual', nome='origem manual na tabela')
auto = db.um(PM, "SELECT id FROM indicadores WHERE chave='mun_populacao'")['id']
pm.post(f'/admin/indicadores/{auto}', data={'csrf': tok(pm, f'/admin/indicadores/{auto}'), 'acao': 'lancar', 'periodo': '2027', 'data_ref': '2027-12-31', 'valor': '999', 'motivo': 'tentativa indevida de teste'})
if val('mun_populacao', '2027'): falha('lançamento manual aceito em indicador automático')
# configuração: meta com base legal, texto neutro, destaque limitado
sm = db.um(PM, "SELECT id FROM indicadores WHERE chave='mun_salario_medio'")['id']
u2 = f'/admin/indicadores/{sm}'
pm.post(u2, data={'csrf': tok(pm, u2), 'acao': 'config', 'descricao': 'Graças à atual gestão do prefeito, o melhor salário da região!', 'ordem': '7', 'visivel': '1'})
if 'Graças' in db.um(PM, 'SELECT descricao FROM indicadores WHERE id=%s', (sm,))['descricao']: falha('texto com tom de propaganda aceito')
pm.post(u2, data={'csrf': tok(pm, u2), 'acao': 'config', 'descricao': 'Média salarial dos trabalhadores formais.', 'ordem': '7', 'visivel': '1', 'meta': '3', 'meta_base_legal': ''})
if db.um(PM, 'SELECT meta FROM indicadores WHERE id=%s', (sm,))['meta'] is not None: falha('meta sem base legal aceita')
pm.post(u2, data={'csrf': tok(pm, u2), 'acao': 'config', 'descricao': 'Média salarial dos trabalhadores formais.', 'ordem': '7', 'visivel': '1', 'destaque': '1'})
if db.um(PM, 'SELECT destaque FROM indicadores WHERE id=%s', (sm,))['destaque']: falha('5º destaque aceito')
pm.post(u2, data={'csrf': tok(pm, u2), 'acao': 'config', 'descricao': 'Média salarial dos trabalhadores formais.', 'ordem': '7'})
if 'Salário médio' in pm.get('/painel?aba=mun').text: falha('indicador oculto continua no portal')
if not db.um(PM, "SELECT 1 FROM indicador_historico WHERE indicador_id=%s AND acao LIKE 'Configuração alterada%%visivel%%'", (sm,)): falha('ocultar sem histórico')
r = pm.post('/admin/indicadores', data={'csrf': tok(pm, '/admin/indicadores'), 'acao': 'coletar'}, follow_redirects=True)
if 'Coleta concluída' not in r.text: falha(f'coletar agora: {r.text[:300]}')
# exclusão de lançamento manual com motivo
vid = val('gestao_iegm', '2024')['id']
pm.post(url, data={'csrf': tok(pm, url), 'acao': 'excluir', 'valor_id': vid, 'motivo': 'Exclusão do valor de teste'})
if val('gestao_iegm', '2024'): falha('exclusão do lançamento manual')
if not db.um(PM, "SELECT 1 FROM indicador_historico WHERE indicador_id=%s AND acao LIKE 'Lançamento manual excluído%%'", (iegm,)): falha('exclusão sem histórico')

# ---------- desligar o módulo tira tudo do ar ----------
bi(False)
ok(pm.get('/painel'), 404, nome='painel desligado')
ok(pm.get('/painel/mun_populacao'), 404, nome='indicador desligado')
ok(pm.get('/painel/baixar/painel.csv'), 404, nome='download desligado')
if 'ind-home' in pm.get('/').text: falha('bloco da home continuou com o módulo desligado')
if '/painel/baixar' in pm.get('/dados-abertos').text: falha('dados abertos continuou listando o painel')
ok(pm.get('/admin/indicadores'), 404, nome='tela admin desligada')
if 'href="/admin/indicadores"' in pm.get('/admin/').text: falha('menu mostra o painel com o módulo desligado')
if worker.bi_ligado(f_ibge): falha('worker continua coletando com o módulo desligado')

print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
