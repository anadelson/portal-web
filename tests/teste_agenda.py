# Agenda das integrações (10/11/2026): o órgão escolhe no painel os dias, os horários e quantas vezes cada fonte roda.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_agenda.py
import os, re, sys
from datetime import datetime, timedelta
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, agenda as AG, worker as W
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)

# ---------- lógica ----------
seg6 = datetime(2026, 11, 9, 6, 0)  # segunda-feira, 6h
h = {'modo': 'horarios', 'dias': [0, 1, 2, 3, 4], 'horarios': ['06:00', '18:00']}
checa(AG.deve_rodar(h, seg6, None), 'horário fixo: roda no horário')
checa(not AG.deve_rodar(h, seg6, seg6), 'horário fixo: não repete o mesmo horário')
checa(not AG.deve_rodar(h, seg6 + timedelta(hours=5), seg6), 'horário fixo: não roda fora dos horários')
checa(AG.deve_rodar(h, seg6 + timedelta(hours=13), seg6), 'horário fixo: recupera o horário perdido no mesmo dia (worker parado às 18h)')
checa(not AG.deve_rodar(h, seg6 + timedelta(hours=14), seg6), 'horário fixo: não recupera depois de 60 min (espera o próximo horário)')
checa(not AG.deve_rodar(h, seg6 + timedelta(hours=8, minutes=44), None), 'horário fixo: agenda nova não dispara fora do horário')
checa(not AG.deve_rodar(h, datetime(2026, 11, 14, 6, 0), None), 'horário fixo: sábado fora dos dias marcados')
checa([t.strftime('%a %H:%M') for t in AG.proximas(h, seg6, None, 3)] == ['Mon 06:00', 'Mon 18:00', 'Tue 06:00'], 'próximas execuções')
checa(AG.vezes_por_dia(h) == 2, 'vezes por dia (horários)')
iv = {'modo': 'intervalo', 'dias': AG.TODOS, 'cada_min': 120, 'inicio': 7, 'fim': 19}
checa(not AG.deve_rodar(iv, seg6, None) and AG.deve_rodar(iv, seg6 + timedelta(hours=1), None), 'intervalo: respeita a faixa de horário')
checa(not AG.deve_rodar(iv, seg6 + timedelta(hours=2), seg6 + timedelta(hours=1)), 'intervalo: respeita o intervalo')
checa(AG.vezes_por_dia(iv) == 6, 'vezes por dia (intervalo)')
for f in AG.PADRAO:  # o padrão reproduz o agendamento que era fixo no código
    cada, horas = W.FREQ[f]
    p = AG.padrao(f)
    checa((p['cada_min'], p['inicio'], p['fim']) == (cada, horas[0], horas[-1] + 1), f'padrão de {f} igual ao de antes')
class Form(dict):
    def getlist(self, k):
        v = self.get(k, []); return v if isinstance(v, list) else [v]
_, e = AG.validar('ibge', Form(modo='intervalo', dias=['0'], cada='2', unidade='h', inicio='0', fim='24'))
checa(e and 'no máximo a cada 1 dia' in e[0], 'IBGE: recusa intervalo menor que 1 dia')
_, e = AG.validar('ibge', Form(modo='horarios', dias=['0'], horarios='02:00, 14:00'))
checa(e, 'IBGE: recusa mais de um horário por dia')
_, e = AG.validar('fiorilli', Form(modo='horarios', dias=['0'], horarios='06:00, 06:10'))
checa(e, 'Fiorilli: recusa horários a menos de 30 minutos')
_, e = AG.validar('fiorilli', Form(modo='horarios', dias=[], horarios='06:00'))
checa(e, 'recusa sem dia da semana')
_, e = AG.validar('youtube', Form(modo='horarios', dias=['0'], horarios='06:00'))
checa(e, 'YouTube: agenda automática, não editável')

# ---------- painel ----------
pm = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pmbora'") or db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio LIKE 'pmbora%%'")
fonte = 'fiorilli' if db.um(db.PLATAFORMA, "SELECT 1 FROM fontes WHERE orgao_id=%s AND fonte='fiorilli'", (o['id'],)) else db.um(db.PLATAFORMA, 'SELECT fonte FROM fontes WHERE orgao_id=%s ORDER BY fonte LIMIT 1', (o['id'],))['fonte']
U = f'/admin/integracoes?fonte={fonte}'
r = pm.get(U)
checa(r.status_code == 200 and 'Agenda de execução' in r.text and 'padrão do sistema' in r.text and 'Próximas execuções' in r.text, 'tela: agenda com o padrão e as próximas execuções')
r = pm.post(f'/admin/integracoes/{fonte}/agenda', data={'csrf': tok(pm, U), 'acao': 'salvar', 'modo': 'horarios', 'dias': ['0', '1', '2', '3', '4'], 'horarios': '06:00, 06:05'}, follow_redirects=True)
checa('Agenda não salva' in r.text and not db.um(db.PLATAFORMA, 'SELECT agenda FROM fontes WHERE orgao_id=%s AND fonte=%s', (o['id'], fonte))['agenda'], 'abaixo do mínimo: recusa e não grava')
r = pm.post(f'/admin/integracoes/{fonte}/agenda', data={'csrf': tok(pm, U), 'acao': 'salvar', 'modo': 'horarios', 'dias': ['0', '1', '2', '3', '4'], 'horarios': '18:00, 06:00'}, follow_redirects=True)
g = db.um(db.PLATAFORMA, 'SELECT agenda FROM fontes WHERE orgao_id=%s AND fonte=%s', (o['id'], fonte))['agenda']
checa(g == {'modo': 'horarios', 'dias': [0, 1, 2, 3, 4], 'horarios': ['06:00', '18:00']}, f'agenda gravada em ordem ({g})')
checa('Agenda salva' in r.text and 'de segunda a sexta, às 06:00, 18:00' in r.text and '2 vez(es) por dia' in r.text, 'tela mostra a agenda salva')
banco = o['banco']
checa(db.um(banco, "SELECT 1 FROM auditoria WHERE acao LIKE %s", (f'%agenda da fonte {fonte} alterada%',)), 'mudança registrada na auditoria')
f = dict(db.um(db.PLATAFORMA, 'SELECT o.*, f.fonte, f.params, f.agenda FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE o.id=%s AND f.fonte=%s', (o['id'], fonte)))
checa(W.pronta(f, seg6, None) and not W.pronta(f, seg6 + timedelta(hours=2), seg6) and not W.pronta(f, datetime(2026, 11, 15, 6, 0), None), 'worker obedece a agenda do órgão')
r = pm.post(f'/admin/integracoes/{fonte}/agenda', data={'csrf': tok(pm, U), 'acao': 'padrao'}, follow_redirects=True)
checa(db.um(db.PLATAFORMA, 'SELECT agenda FROM fontes WHERE orgao_id=%s AND fonte=%s', (o['id'], fonte))['agenda'] is None and 'voltou ao padrão' in r.text, 'voltar ao padrão')
anon = TestClient(app, base_url='http://pmbora.localhost')
checa(anon.post(f'/admin/integracoes/{fonte}/agenda', data={'acao': 'padrao'}, follow_redirects=False).status_code in (303, 302, 400, 401, 403), 'sem login não altera a agenda')

if erros:
    print('ERROS:', len(erros)); [print(x) for x in erros]; sys.exit(1)
print('agenda: tudo ok')
