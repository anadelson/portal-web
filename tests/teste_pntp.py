# Pedido de 18/11/2026 (etapa 6): autoavaliação PNTP da matriz inteira nos painéis da Prefeitura e da Câmara, com índice
# estimado (metodologia da Cartilha PNTP 2026), nível, essenciais, medições automáticas e marcação do controle interno.
# Marcações do teste usam links e observações marcados como TESTE; nada real. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_pntp.py
import csv, io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, pntp as P
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
def cli(host='pmbora.localhost'):
    return TestClient(app, base_url=f'http://{host}')
def post(c, url, dados, de=None):
    return c.post(url, data=dict({'csrf': tok(c, de or url)}, **dados), follow_redirects=True)
def msg(r):
    m = re.search(r'class="msg"[^>]*>(.*?)</', r.text, re.S)
    return m.group(1) if m else ''
def kpi(r, rotulo):
    m = re.search(rotulo + r'<b>([^<]+)</b>', r.text)
    return m.group(1) if m else ''
def aud(txt, b=PM):
    return db.um(b, 'SELECT count(*) n FROM auditoria WHERE acao LIKE %s', (f'%{txt}%',))['n']

# 1) matriz oficial: quantidades e classificação da Cartilha PNTP 2026 (Tabela 1)
from collections import Counter
ce, cl = P.criterios('executivo'), P.criterios('legislativo')
checa(len(ce) == 96 and len(cl) == 83, f'quantidade de critérios: {len(ce)} / {len(cl)}')
checa(Counter(c['classe'] for c in ce) == {'essencial': 12, 'obrigatorio': 65, 'recomendado': 19}, 'classes da Prefeitura (12/65/19)')
checa(Counter(c['classe'] for c in cl) == {'essencial': 7, 'obrigatorio': 60, 'recomendado': 16}, 'classes da Câmara (7/60/16)')
checa(not any(c['id'].startswith('20.') for c in ce) and sum(c['id'].startswith('20.') for c in cl) == 11, 'dimensão 20 só na Câmara')
checa(P.por_id('11.8')['aplica'] == ['executivo'] and P.por_id('17.2')['aplica'] == ['executivo'], 'PPA e emendas: só Executivo')
checa(P.PESO_DIM['Receita'] == 4 and P.PESO_DIM['Atividades Finalísticas - PL'] == 3 and P.PESO_DIM['Saúde'] == 1, 'pesos das dimensões (Tabela 2)')

# 2) nota do critério: rateio dos itens que não se aplicam; disponibilidade zera
T = dict(disponibilidade=True, atualidade=True, serie=True, gravacao=True, filtro=True)
checa(P.nota(P.por_id('1.1'), {'disponibilidade': True}) == 1, 'só disponibilidade: 100%')
checa(abs(P.nota(P.por_id('6.3'), {'disponibilidade': True}) - 0.5) < 1e-9, '6.3 (D e A): só D = 50%')
checa(abs(P.nota(P.por_id('2.6'), dict(disponibilidade=True, atualidade=True)) - 60 / 90) < 1e-9, '2.6 (sem gravação): rateio sobre 90')
checa(P.nota(P.por_id('3.1'), dict(T, disponibilidade=False)) == 0, 'sem disponibilidade: zero')
checa(P.nota(P.por_id('3.1'), None) == 0, 'sem avaliação: zero (nada dado como atendido)')

# 3) índice e níveis (Tabela 3)
todos = {c['id']: {'itens': T} for c in ce}
i100, _ = P.indice(todos, 'executivo')
i0, _ = P.indice({}, 'executivo')
checa(abs(i100 - 100) < 1e-9 and i0 == 0, f'índice 100 / 0: {i100} / {i0}')
checa(P.nivel(96, True) == 'Diamante' and P.nivel(90, True) == 'Ouro' and P.nivel(80, True) == 'Prata' and P.nivel(80, False) == 'Elevado', 'níveis com selo')
checa(P.nivel(60, True) == 'Intermediário' and P.nivel(40, True) == 'Básico' and P.nivel(5, True) == 'Inicial' and P.nivel(0, True) == 'Inexistente', 'níveis sem selo')
so_receita = {c['id']: {'itens': T} for c in ce if c['dimensao'] == 'Receita'}
ir_, dims = P.indice(so_receita, 'executivo')
peso_total = sum(P.PESO_DIM[d] for d in {c['dimensao'] for c in ce})
checa(abs(ir_ - 100 * 4 / peso_total) < 1e-9 and dims['Receita'] == 100, f'peso da dimensão Receita (4 de {peso_total})')

# 4) tela da Prefeitura: menu, índice, todos os critérios, medições automáticas e marcação
adm = cli(); entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
r = adm.get('/admin/pntp')
checa(r.status_code == 200 and 'Índice estimado' in r.text and 'Estimativa interna' in r.text, 'tela da Prefeitura')
checa('href="/admin/pntp"' in adm.get('/admin/').text, 'item “Autoavaliação PNTP” no menu da Prefeitura')
checa(len(re.findall(r'<tr id="c-', r.text)) == 96, 'Prefeitura: 96 critérios na tela')
checa('Base legal:' in r.text, 'tela com Base legal')
ind0 = kpi(r, 'Índice estimado')
av = P.avaliar(db.um('plataforma', "SELECT * FROM orgaos WHERE banco=%s", (PM,)) | {'dominio': 'pmbora.localhost'}, rotas={x.path for x in app.routes})
L = {l['c']['id']: l for l in av['linhas']}
checa(L['13.3']['origem'] == 'auto' and L['13.3']['nota'] == 1, 'acessibilidade: medida pelo portal')
checa(L['1.4']['origem'] == 'auto' and L['1.4']['nota'] == 0, 'busca só na Carta: não atende')
checa(L['4.3']['origem'] == 'auto' and L['4.3']['nota'] == 0 and 'objeto' in L['4.3']['det'], '4.3 sem objeto do empenho: não atende (essencial)')
checa(L['2.7']['origem'] == 'sem' and L['2.7']['nota'] == 0, 'perguntas frequentes: sem marcação = zero')
checa(av['nivel'] not in ('Diamante', 'Ouro', 'Prata'), 'sem os essenciais, sem selo')

# 4.1) marcação: link obrigatório, item que não se aplica, critério automático
r = post(adm, '/admin/pntp', {'criterio': '2.7', 'acao': 'marcar', 'item_disponibilidade': '1', 'link': ''})
checa('não foi marcado' in msg(r) and not db.um(PM, "SELECT 1 x FROM pntp_marcacoes WHERE criterio='2.7'"), 'atende sem link: recusado')
r = post(adm, '/admin/pntp', {'criterio': '2.7', 'acao': 'marcar', 'item_disponibilidade': '1', 'item_atualidade': '1', 'link': '/teste-faq'})
checa(db.um(PM, "SELECT itens FROM pntp_marcacoes WHERE criterio='2.7'")['itens'] == {'disponibilidade': True}, 'item que não se aplica (2.7 atualidade): ignorado')
checa(P.validar_marcacao(P.por_id('2.7'), {'disponibilidade': True, 'atualidade': True}, '/x'), 'validação recusa item que não se aplica')
r = post(adm, '/admin/pntp', {'criterio': '13.1', 'acao': 'marcar', 'item_disponibilidade': '1', 'link': '/x'})
checa('automaticamente' in msg(r) and not db.um(PM, "SELECT 1 x FROM pntp_marcacoes WHERE criterio='13.1'"), 'critério automático não é marcado')
r = post(adm, '/admin/pntp', {'criterio': '2.7', 'acao': 'marcar', 'item_disponibilidade': '1', 'link': '/teste-faq', 'obs': 'TESTE'})
m = db.um(PM, "SELECT * FROM pntp_marcacoes WHERE criterio='2.7' AND ciclo=2026")
checa(m and m['itens'] == {'disponibilidade': True} and m['link'] == '/teste-faq' and m['por'], 'marcação gravada')
checa(aud('critério 2.7 marcado') == 2, 'marcações na auditoria')
ind1 = kpi(adm.get('/admin/pntp'), 'Índice estimado')
checa(float(ind1.rstrip('%').replace(',', '.')) > float(ind0.rstrip('%').replace(',', '.')), f'índice sobe com a marcação ({ind0} → {ind1})')
# atualidade marcada há mais de 30 dias deixa de contar
post(adm, '/admin/pntp', {'criterio': '6.6', 'acao': 'marcar', 'item_disponibilidade': '1', 'item_atualidade': '1', 'item_serie': '1', 'item_filtro': '1', 'link': 'https://exemplo.test/concursos'})
n_antes = {l['c']['id']: l for l in P.avaliar(av and db.um('plataforma', "SELECT * FROM orgaos WHERE banco=%s", (PM,)) | {'dominio': 'x'})['linhas']}['6.6']['nota']
from datetime import datetime, time, timedelta
from app import config
db.exe(PM, "UPDATE pntp_marcacoes SET em=%s WHERE criterio='6.6'", (datetime.combine(config.hoje() - timedelta(days=40), time(12)),))  # relativo à data do sistema (pode ser simulada)
l66 = {l['c']['id']: l for l in P.avaliar(db.um('plataforma', "SELECT * FROM orgaos WHERE banco=%s", (PM,)) | {'dominio': 'x'})['linhas']}['6.6']
checa(n_antes == 1 and l66['vencida'] and abs(l66['nota'] - 60 / 90) < 1e-9, f'marcação com 40 dias: atualidade não conta ({l66["nota"]})')
r = post(adm, '/admin/pntp', {'criterio': '6.6', 'acao': 'apagar'})
checa(not db.um(PM, "SELECT 1 x FROM pntp_marcacoes WHERE criterio='6.6'") and aud('6.6 apagada') == 1, 'apagar marcação')

# 4.2) planilha CSV
r = adm.get('/admin/pntp.csv')
linhas = list(csv.reader(io.StringIO(r.content.decode('utf-8-sig')), delimiter=';'))
checa(r.status_code == 200 and len(linhas) == 97 and linhas[0][0] == 'Critério', f'CSV: {len(linhas)} linhas')
l27 = next(x for x in linhas if x[0] == '2.7')
checa(l27[4] == 'Sim' and l27[5] == 'Não se aplica' and l27[11] == 'https://pmbora.localhost/teste-faq', f'CSV 2.7: {l27[4:12]}')

# 5) perfis: editor não vê; procuradoria marca
post(adm, '/admin/usuarios', {'acao': 'novo', 'nome': 'Editor PNTP Teste', 'email': 'edp@teste.localhost', 'perfil': 'editor', 'senha': 'provisoria123'})
post(adm, '/admin/usuarios', {'acao': 'novo', 'nome': 'Controle Interno Teste', 'email': 'ci@teste.localhost', 'perfil': 'procuradoria', 'senha': 'provisoria123'})
ed, ci = cli(), cli()
entrar(ed, 'edp@teste.localhost', 'provisoria123', 'senhaforte123'); entrar(ci, 'ci@teste.localhost', 'provisoria123', 'senhaforte123')
checa(ed.get('/admin/pntp').status_code == 403 and 'href="/admin/pntp"' not in ed.get('/admin/').text, 'editor: sem acesso e sem item no menu')
r = post(ci, '/admin/pntp', {'criterio': '15.6', 'acao': 'marcar', 'link': '', 'obs': 'TESTE: sem pesquisa de satisfação'})
m = db.um(PM, "SELECT * FROM pntp_marcacoes WHERE criterio='15.6'")
checa(m and m['itens'] == {'disponibilidade': False} and m['por'] == 'Controle Interno Teste', 'controle interno marca “não atende” sem link')

# 6) Câmara: mesma tela, 83 critérios, dimensão 20 da autoavaliação legislativa
cm = cli('cmbora.localhost'); entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
r = cm.get('/admin/pntp')
checa(r.status_code == 200 and len(re.findall(r'<tr id="c-', r.text)) == 83, 'Câmara: 83 critérios na tela')
checa('id="c-20-11"' in r.text and 'Atividades Finalísticas - PL' in r.text, 'Câmara: dimensão 20')
checa('href="/admin/pntp"' in cm.get('/admin/').text, 'item no menu da Câmara')
oc = db.um('plataforma', "SELECT * FROM orgaos WHERE banco=%s", (CM,))
Lc = {l['c']['id']: l for l in P.avaliar(oc, rotas=set())['linhas']}
checa(Lc['4.3']['nota'] == 0 and 'não oferece' in Lc['4.3']['det'], 'Câmara: empenhos ainda não oferecidos')
checa(Lc['20.1']['origem'] == 'auto', 'Câmara: 20.x medidos pelo portal')
checa(not db.um(CM, 'SELECT 1 x FROM pntp_marcacoes'), 'marcações da Prefeitura não vão para a Câmara')
r = cm.get('/admin/pntp?sit=essenciais')
checa(len(re.findall(r'<tr id="c-', r.text)) == 7, 'filtro: só os essenciais (7)')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
