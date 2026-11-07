# Fase 7 (fontes): planilhas do INEP (IDEB e Saeb) e IEG-M do TCESP — SEM internet: respostas gravadas em tests/fixtures/.
# Rode só contra banco de TESTE já provisionado:  TESTE=1 DATA_SIMULADA=2026-11-06T10:00 PYTHONPATH=. python tests/teste_painel_fontes.py
import csv, io, json, os, re, shutil, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import date
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import db, worker, config, painel as P
from app.coletores import inep_iegm as X, comum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

FX = Path(__file__).parent / 'fixtures'
CDA = json.loads((FX / 'iegm_cda.json').read_text(encoding='utf-8'))
erros = []
def falha(m): erros.append(m)
PM = 'bd_pm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
def ok(r, cod=200, txt=None, nome=''):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {r.text[:200]}')
    return r
def val(chave, per):
    return db.um(PM, 'SELECT v.* FROM indicador_valores v JOIN indicadores i ON i.id=v.indicador_id WHERE i.chave=%s AND v.periodo=%s', (chave, per))

# ---------- respostas gravadas ----------
baixados = []
def cabecalho(url):
    nome = url.rsplit('/', 1)[-1]
    return (200, 'Wed, 05 Aug 2026 20:14:35 GMT', 3000) if (FX / 'inep' / nome).exists() else (404, '', 0)
def baixar(url, destino):
    baixados.append(url)
    shutil.copy(FX / 'inep' / url.rsplit('/', 1)[-1], destino)
    return 1
cda_chamadas = []
def buscar_cda(fonte, url, params=None, auth=None, **kw):
    if fonte != 'iegm' or 'painel.tce.sp.gov.br' not in url: raise AssertionError(f'chamada inesperada {url}')
    if not auth or not all(auth): raise AssertionError('IEG-M chamado sem credencial')
    cda_chamadas.append(params['parampExercicio_mapa'])
    return CDA['larga'].get(str(params['parampExercicio_mapa']), {'metadata': CDA['larga']['2024']['metadata'], 'resultset': []})
X.cabecalho, X.baixar, X.buscar = cabecalho, baixar, buscar_cda

oid = db.um(db.PLATAFORMA, "SELECT id FROM orgaos WHERE slug='pm-bora'")['id']
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=TRUE WHERE orgao_id=%s AND chave='bi'", (oid,))
def fonte(nome):
    return db.um(db.PLATAFORMA, 'SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.fonte=%s', (oid, nome))

# ---------- catálogo e fontes ----------
for k in ('edu_ideb_ai', 'edu_saeb_mat_ai', 'edu_saeb_lp_ai', 'edu_ideb_af', 'edu_saeb_mat_em'):
    if not db.um(PM, 'SELECT 1 FROM indicadores WHERE chave=%s AND visivel', (k,)): falha(f'{k} fora do catálogo')
for k in P.RETIRADOS:
    if db.um(PM, "SELECT 1 FROM indicadores WHERE chave=%s AND (visivel OR coletor<>'')", (k,)): falha(f'{k} deveria estar retirado')
if not (fonte('inep') and fonte('inep')['ativo'] if False else fonte('inep')): falha('fonte inep não criada')
if not fonte('iegm'): falha('fonte iegm não criada')
if db.um(PM, "SELECT modo FROM indicadores WHERE chave='gestao_iegm'")['modo'] != 'manual': falha('IEG-M deveria nascer em modo manual')

# ---------- INEP ----------
res = worker.rodar(fonte('inep'), 'inep', fonte('inep')['params'])
st = {b: o_ for b, o_, _, _ in res}
if not (st.get('ai') and st.get('af')) or st.get('em'): falha(f'coleta INEP por etapa: {res}')
esperado = {('edu_ideb_ai', '2025'): 6.6, ('edu_ideb_ai', '2023'): 7.0, ('edu_ideb_ai', '2017'): 5.0, ('edu_saeb_mat_ai', '2025'): 240.82, ('edu_saeb_lp_ai', '2023'): 232.6,
            ('edu_ideb_af', '2025'): 5.3, ('edu_saeb_mat_af', '2025'): 258.1, ('edu_saeb_lp_af', '2021'): 248.09}
for (k, per), v in esperado.items():
    r = val(k, per)
    if not r or r['valor'] is None or abs(float(r['valor']) - v) > 0.001: falha(f'{k} {per}: esperado {v}, gravado {r and r["valor"]}')
r = val('edu_ideb_ai', '2019')
if not r or r['valor'] is not None or r['texto'] != 'não divulgado pelo INEP': falha(f'ND virou número: {r and (r["valor"], r["texto"])}')
r = val('edu_saeb_mat_ai', '2019')
if not r or r['valor'] is not None or '“ND”' not in r['nota']: falha('Saeb ND sem a marca da planilha')
if val('edu_ideb_ai', '2005'): falha('edição anterior à primeira com resultado entrou na série')
r = val('edu_ideb_ai', '2021')
if not r or r['valor'] is not None or r['detalhe'].get('projecao') != 7.1: falha('meta projetada 2021 sem a linha "não divulgado"')
if val('edu_ideb_ai', '2025')['detalhe'].get('rendimento') != 1.0: falha('rendimento não guardado')
if 'rede municipal (responsabilidade da Prefeitura)' not in val('edu_ideb_ai', '2025')['nota']: falha('rede responsável dos anos iniciais')
if 'rede estadual (responsabilidade do Governo do Estado)' not in val('edu_ideb_af', '2025')['nota'] or 'Prefeitura' in val('edu_ideb_af', '2025')['nota']: falha('rede responsável dos anos finais')
if db.um(PM, "SELECT 1 FROM indicador_valores v JOIN indicadores i ON i.id=v.indicador_id WHERE i.chave LIKE 'edu_%%' AND v.nota LIKE '%%Fictício%%'"): falha('linha de outro município gravada')
if not db.um(db.PLATAFORMA, "SELECT 1 FROM indicadores_publicos WHERE ibge='3507209' AND indicador='edu_ideb_ai' AND periodo='2025' AND fonte='inep'"): falha('INEP não gravou por código IBGE')
n_baixados = len(baixados)
worker.rodar(fonte('inep'), 'inep', fonte('inep')['params'])
if len(baixados) != n_baixados + 1:  # só a etapa sem Borá é baixada de novo (não ficou marcada como importada)
    falha(f'planilha já importada foi baixada de novo: {baixados[n_baixados:]}')
# página do indicador: ND como texto, metas projetadas só como referência, rendimento na tabela
t = ok(pm.get('/painel/edu_ideb_ai'), nome='página IDEB').text
for x in ('não divulgado pelo INEP', 'Meta projetada pelo INEP (referência histórica até 2021; não é meta atual)', 'Indicador de rendimento (P)', 'Meta projetada pelo INEP (referência histórica)',
          'rede municipal (responsabilidade da Prefeitura)', '>não</text>', '>divulgado</text>', 'download.inep.gov.br/ideb/resultados/divulgacao_anos_iniciais_municipios_2025.zip'):
    if x not in t: falha(f'página IDEB: falta "{x}"')
desc = re.search(r'<desc id="[^"]+">([^<]+)</desc>', t).group(1)
if '2019: não divulgado pelo INEP' not in desc or 'Metas projetadas pelo INEP' not in desc: falha(f'descrição do gráfico: {desc[:200]}')
if re.search(r'2019</th><td class="num">0', t): falha('ND exibido como zero')
if 'Mínimo' in t or 'Meta: ' in t: falha('meta projetada do INEP tratada como meta atual')
t = ok(pm.get('/painel?aba=edu'), nome='aba educação').text
for x in ('IDEB — anos iniciais do ensino fundamental (rede pública)', 'rede municipal (responsabilidade da Prefeitura)', 'rede estadual (responsabilidade do Governo do Estado)', 'Saeb — Matemática'):
    if x not in t: falha(f'aba educação: falta "{x}"')
if 'Indicador de rendimento' in t: falha('rendimento não deveria ter cartão próprio')
rows = list(csv.DictReader(io.StringIO(ok(pm.get('/painel/baixar/edu_ideb_ai.csv'), nome='csv IDEB').content.decode('utf-8-sig'))))
r19 = [x for x in rows if x['periodo'] == '2019'][0]
if r19['valor'] != '' or r19['valor_exibido'] != 'não divulgado pelo INEP' or 'meta projetada pelo INEP (referência histórica) 6,9' not in r19['complemento']: falha(f'CSV IDEB 2019: {r19}')
if 'rendimento (P) 1,000' not in [x for x in rows if x['periodo'] == '2025'][0]['complemento']: falha('CSV sem rendimento')
# certificado intermediário: aviso 60 dias antes do vencimento
if X.validade_certificados() and X.aviso_certificado(date(2026, 11, 7)): falha('aviso de certificado antes da hora')
if X.validade_certificados():
    fim = X.validade_certificados()[0][1]
    if 'vence em' not in X.aviso_certificado(date.fromordinal(fim.toordinal() - 59)): falha('sem aviso 59 dias antes do vencimento')
    if X.aviso_certificado(date.fromordinal(fim.toordinal() - 61)): falha('aviso 61 dias antes do vencimento')
ctx = X.contexto_tls()
if ctx.verify_mode != __import__('ssl').CERT_REQUIRED or not ctx.check_hostname: falha('verificação TLS desligada')

# ---------- IEG-M: mapeamento por metadata.colName ----------
v, cols = X.mapear_iegm(CDA['larga']['2024'], '3507209')
if set(v) != set(X.IEGM_CHAVES) or v['gestao_iegm'][0] not in P.FAIXAS_IEGM or v['gestao_iegm'][1] is None: falha(f'mapeamento tabela larga: {v}')
v, _ = X.mapear_iegm(CDA['longa'], '3507209')
if v.get('gestao_iegm') != ('B', 0.61) or v.get('gestao_iegm_educ') != ('B+', 0.7) or v.get('gestao_iegm_ti') != ('C', 0.4) or len(v) != 3: falha(f'mapeamento tabela longa: {v}')
if X.mapear_iegm(CDA['outra'], '3507209')[0]: falha('colunas desconhecidas deveriam dar vazio')
v, _ = X.mapear_iegm(CDA['larga']['2024'], '3507209', {'codigo': 'codigo_municipio', 'gestao_iegm': {'faixa': 'faixa_i_amb', 'nota': 'nota_i_amb'}})
if v.get('gestao_iegm') != (CDA['larga']['2024']['resultset'][0][13], CDA['larga']['2024']['resultset'][0][14]): falha(f'mapeamento fixo pelo parâmetro: {v}')

# ---------- IEG-M: desligado sem credencial ou em modo manual (sem erro) ----------
config.IEGM_USUARIO, config.IEGM_SENHA = '', ''
antes = db.um(db.PLATAFORMA, "SELECT count(*) n FROM coletas WHERE fonte LIKE 'iegm:%%'")['n']
if worker.rodar(fonte('iegm'), 'iegm', fonte('iegm')['params']): falha('IEG-M sem credencial deveria não coletar')
config.IEGM_USUARIO, config.IEGM_SENHA = 'usuario-de-teste', 'senha-de-teste'  # valores fictícios só do teste
if worker.rodar(fonte('iegm'), 'iegm', fonte('iegm')['params']): falha('IEG-M em modo manual deveria não coletar')
if db.um(db.PLATAFORMA, "SELECT count(*) n FROM coletas WHERE fonte LIKE 'iegm:%%'")['n'] != antes or cda_chamadas: falha('IEG-M desligado registrou coleta ou chamou a fonte')

# ---------- admin: modo automático com auditoria ----------
entrar(pm, 'admin@pmbora.localhost', os.environ.get('SENHA_INICIAL_ADMIN', 'admin123'), 'adminforte12345')
gid = db.um(PM, "SELECT id FROM indicadores WHERE chave='gestao_iegm'")['id']
url = f'/admin/indicadores/{gid}'
t = ok(pm.get(url), txt='Modo de atualização', nome='admin IEG-M').text
for x in ('sem documentação oficial e pode mudar sem aviso', 'Automático (acesso anônimo do TCESP)', 'preenchida', 'Lançamento manual'):
    if x not in t: falha(f'admin IEG-M: falta "{x}"')
if 'usuario-de-teste' in t or 'senha-de-teste' in t: falha('credencial exibida na tela')
pm.post(url, data={'csrf': tok(pm, url), 'acao': 'modo', 'modo': 'automatico'})
if db.um(PM, "SELECT count(*) n FROM indicadores WHERE chave LIKE 'gestao_iegm%%' AND modo='automatico'")['n'] != 8: falha('modo automático não aplicado aos 8 indicadores')
if not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE '%%IEG-M — modo de atualização alterado para automático%%'"): falha('troca de modo sem auditoria')
P.semear(PM)
if db.um(PM, "SELECT modo FROM indicadores WHERE chave='gestao_iegm'")['modo'] != 'automatico': falha('semear desfez o modo escolhido pelo administrador')
# lançamento manual de reserva (ano-base antigo) antes da coleta: a coleta não sobrescreve
pm.post(url, data={'csrf': tok(pm, url), 'acao': 'lancar', 'periodo': '2014', 'data_ref': '2014-12-31', 'texto': 'C', 'motivo': 'Valor FICTÍCIO de teste do lançamento de reserva'})
if not val('gestao_iegm', '2014') or val('gestao_iegm', '2014')['origem'] != 'manual': falha('lançamento de reserva com modo automático')
r = pm.post(url, data={'csrf': tok(pm, url), 'acao': 'coletar'}, follow_redirects=True)
if 'OK:' not in r.text: falha(f'coletar agora (IEG-M): {r.text[:300]}')
v24 = val('gestao_iegm', '2024')
if not v24 or v24['texto'] not in P.FAIXAS_IEGM or v24['valor'] is None or 'edição 2025 (ano-base 2024)' not in v24['nota']: falha(f'IEG-M 2024: {v24}')
for k in X.IEGM_CHAVES:
    if not val(k, '2023') or not val(k, '2024'): falha(f'{k}: sem as duas edições')
if val('gestao_iegm', '2014')['origem'] != 'manual': falha('coleta sobrescreveu o lançamento manual')
if not db.um(db.PLATAFORMA, "SELECT 1 FROM indicadores_publicos WHERE ibge='3507209' AND fonte='iegm' AND indicador='gestao_iegm_ti' AND periodo='2024'"): falha('IEG-M não gravou por código IBGE')
if any(x in json.dumps(db.todos(db.PLATAFORMA, "SELECT mensagem FROM coletas WHERE fonte LIKE 'iegm:%%'")) for x in ('usuario-de-teste', 'senha-de-teste')): falha('credencial em coletas')
ok(pm.get('/painel?aba=mun'), txt='IEG-M — governança de TI', nome='IEG-M no painel')
# falha da consulta: mantém o último valor, aviso no painel e coleta com falha registrada
def quebra(*a, **k): raise comum.httpx.ConnectError('fonte fora do ar (teste)')
X.buscar = quebra
res = worker.rodar(fonte('iegm'), 'iegm', fonte('iegm')['params'])
if not res or res[0][1] or 'pode ter mudado' not in res[0][3]: falha(f'falha do IEG-M: {res}')
if val('gestao_iegm', '2024')['texto'] != v24['texto']: falha('falha apagou o IEG-M')
ok(pm.get('/painel/gestao_iegm'), txt='a última consulta à fonte falhou', nome='aviso IEG-M no painel')
if not db.um(db.PLATAFORMA, "SELECT 1 FROM coletas WHERE fonte='iegm:iegm' AND NOT ok"): falha('falha do IEG-M fora da tela de coletas')
t = ok(pm.get(url), nome='admin IEG-M após falha').text
if 'falhou' not in t: falha('situação da última coleta no admin')
X.buscar = lambda *a, **k: CDA['outra']
res = worker.rodar(fonte('iegm'), 'iegm', fonte('iegm')['params'])
if not res or res[0][1] or 'colunas recebidas: x' not in res[0][3]: falha(f'consulta mudou de formato: {res}')
X.buscar = buscar_cda
# volta ao manual: a coleta para
pm.post(url, data={'csrf': tok(pm, url), 'acao': 'modo', 'modo': 'manual'})
if worker.rodar(fonte('iegm'), 'iegm', fonte('iegm')['params']): falha('modo manual continuou coletando')
# aviso do certificado no painel administrativo
X.aviso_certificado = lambda hoje=None: 'O certificado intermediário teste.pem (cadeia TLS do INEP) vence em 01/01/2031 (30 dias).'
ok(pm.get('/admin/indicadores'), txt='vence em 01/01/2031', nome='aviso do certificado no admin')

print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
