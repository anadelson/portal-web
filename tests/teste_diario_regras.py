# Etapa 3 (11/11/2026): Diário Oficial configurável por órgão — lei, decreto, base legal e horários.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_diario_regras.py
import os, re, sys
from datetime import datetime, date
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, diario as D, diario_servico as DS
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
TER = date(2026, 11, 10)  # terça-feira, dia útil
def em(h, m=0, d=TER):
    return datetime(d.year, d.month, d.day, h, m).astimezone()

# ---------- padrão (igual a antes) e piloto ----------
r = D.regras(PM)
checa((r['corte'], r['alerta'], r['publicacao']) == ('16:00', '16:30', '17:00') and not r['proprios'], 'horários padrão 16h, 16h30 e 17h')
checa((r['corte_txt'], r['alerta_txt'], r['publicacao_txt']) == ('16h', '16h30', '17h'), 'horários por extenso')
checa(r['lei'] == 'Lei Municipal nº 910/2026' and r['decreto'] == 'Decreto de 25/03/2026' and r['base_legal'].startswith('Lei Municipal 910/2026'), 'piloto com lei, decreto e base legal do arquivo de dados')
checa(D.data_alvo(PM, em(15, 59)) == TER and D.data_alvo(PM, em(16, 0)) > TER, 'corte padrão: até 15h59 entra no dia; às 16h vai para o próximo dia útil')

pm = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
U = '/admin/diario/config'
t = pm.get(U).text
checa('Lei, decreto e horários' in t and 'name="corte"' in t and 'value="16:00"' in t and '(em uso)' in t, 'tela com os campos e o padrão em uso')
def salvar(**k):
    d = {'csrf': tok(pm, U), 'acao': 'regras', 'lei': 'Lei Municipal nº 910/2026', 'decreto': 'Decreto de 25/03/2026', 'base_legal': '', 'corte': '14:00', 'alerta': '14:30', 'publicacao': '15:00'}
    d.update(k)
    return pm.post(U, data={x: y for x, y in d.items() if y is not None}, follow_redirects=True)

# ---------- recusas ----------
for k, msg in (({'alerta': '13:30'}, 'nesta ordem'), ({'publicacao': '14:15'}, 'nesta ordem'), ({'corte': '05:00'}, 'entre 6h e 23h'), ({'corte': '25:00'}, 'formato HH:MM'), ({'alerta': 'x'}, 'formato HH:MM')):
    r = salvar(**k)
    checa(msg in r.text and D.regras(PM)['corte'] == '16:00', f'recusa {k}')

# ---------- horários próprios ----------
r = salvar()
checa('Regras do Diário salvas: envio até 14h, alerta às 14h30, publicação automática às 15h' in r.text, 'mensagem com os horários novos')
r2 = D.regras(PM)
checa((r2['corte'], r2['alerta'], r2['publicacao']) == ('14:00', '14:30', '15:00') and r2['proprios'] and r2['base_legal'] == '', 'horários próprios gravados')
checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE %s", ('Diário: lei, decreto e horários alterados%corte: 16:00 → 14:00%',)), 'mudança na auditoria (antes → depois)')
checa(D.data_alvo(PM, em(13, 59)) == TER and D.data_alvo(PM, em(14, 0)) > TER, 'corte do órgão: 14h')
checa(D.base_legal(r2, 'GENÉRICA') == 'Lei Municipal nº 910/2026; Decreto de 25/03/2026; MP 2.200-2/2001 (ICP-Brasil); Lei 14.063/2020.', 'base legal montada com a lei e o decreto')
checa(D.base_legal(dict(r2, lei='', decreto=''), 'GENÉRICA') == 'GENÉRICA', 'sem lei nem decreto: base legal genérica')

# textos no painel, no portal e na Câmara
t = pm.get('/admin/diario').text
checa('Envio até 14h entra na edição do dia útil' in t and 'Lei Municipal nº 910/2026 e Decreto de 25/03/2026: envio até 14h' in t and 'publicação automática às 15h' in t, 'painel do Diário com os horários do órgão')
checa('16h' not in t.split('<main', 1)[1], 'painel do Diário sem "16h" fixo')
p = TestClient(app, base_url='http://pmbora.localhost').get('/diario').text
checa('a partir das 14h' in p and 'Decreto de 25/03/2026; MP 2.200-2/2001' in p, 'portal do Diário com o horário e a base legal do órgão')
cm = TestClient(app, base_url='http://cmbora.localhost')
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
checa('Envio até 14h entra na edição do dia' in cm.get('/admin/remessas?novo=1').text, 'Câmara vê o corte do Diário da Prefeitura de destino')

# ---------- rotina do worker nos horários do órgão ----------
config.DIARIO_AUTOMATICO_TESTE = True
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE banco=%s", (PM,))
checa(DS.tick(o, em(13, 59)) == [], 'antes do corte (13h59): a rotina não faz nada')
db.exe(PM, "UPDATE diario_atos SET situacao='rejeitado' WHERE situacao IN ('revisao','aprovado') AND edicao_id IS NULL")
res = DS.tick(o, em(14, 1))
checa(any('sem atos' in x for x in res), f'no corte (14h01): edição "sem atos" gerada ({res})')
ed = db.um(PM, "SELECT * FROM diario_edicoes WHERE data=%s AND letra='' ORDER BY id DESC LIMIT 1", (TER,))
checa(ed and ed['situacao'] != 'publicada', 'edição do dia ainda não publicada antes das 15h')
res = DS.tick(o, em(15, 1))
ed = db.um(PM, 'SELECT * FROM diario_edicoes WHERE id=%s', (ed['id'],))
checa(ed['situacao'] == 'publicada' and any('publicada' in x for x in res), f'às 15h01 (publicação do órgão) a edição assinada é publicada ({res})')

# ---------- volta ao padrão ----------
r = salvar(padrao_horarios='1')
r3 = D.regras(PM)
checa((r3['corte'], r3['alerta'], r3['publicacao']) == ('16:00', '16:30', '17:00') and not r3['proprios'] and r3['decreto'] == 'Decreto de 25/03/2026', 'volta aos horários padrão mantendo lei e decreto')
anon = TestClient(app, base_url='http://pmbora.localhost')
checa(anon.post(U, data={'acao': 'regras', 'corte': '08:00', 'alerta': '09:00', 'publicacao': '10:00'}, follow_redirects=False).status_code in (302, 303, 400, 401, 403) and D.regras(PM)['corte'] == '16:00', 'sem login não altera')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('regras do diário: tudo ok')
