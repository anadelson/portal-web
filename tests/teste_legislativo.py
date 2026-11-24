# Fase 5: processo legislativo completo — só em banco de TESTE, com legislatura e pessoas FICTÍCIAS.
#   TESTE=1 DATA_SIMULADA=2029-03-10 PYTHONPATH=. python tests/teste_legislativo.py   (depois de provision init + atualizar)
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
if os.environ.get('DATA_SIMULADA') != '2029-03-10':
    sys.exit('Rode com DATA_SIMULADA=2029-03-10 (a legislatura fictícia de teste é 2029–2032).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, legislativo as L

erros = []
def falha(m): erros.append(m)
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {re.sub(r"<[^>]+>", " ", r.text)[:240]}')
    if sem and sem in r.text: falha(f'{nome}: não deveria conter "{sem}"')
    return r
def tok(c, url):
    m = re.search(r'name="csrf" value="([^"]+)"', c.get(url).text); return m.group(1) if m else ''
def msg(r):
    m = re.search(r'class="msg" role="status">([^<]+)<', r.text); return m.group(1) if m else ''
PDF = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF'
CM = 'bd_cm_bora'

cm = TestClient(app, base_url='http://cmbora.localhost')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
ok(cm.get('/admin/'), txt='Visão geral', nome='login cm')

# ---------- 1. legislatura fictícia, vereadores e Mesa ----------
def post(url, data, files=None, txt=None, nome=''):
    data = dict(data, csrf=tok(cm, '/admin/sessoes' if url == '/admin/sessoes/nova' else url)); return ok(cm.post(url, data=data, files=files, follow_redirects=True), txt=txt, nome=nome)
post('/admin/legislaturas', {'acao': 'nova', 'numero': '16', 'anos': '2029–2032', 'prefeito': 'Prefeito Fictício', 'vice': 'Vice Fictício'}, txt='Legislatura salva', nome='nova legislatura')
NOMES = ['Ana Teste', 'Bruno Teste', 'Carla Teste', 'Diego Teste', 'Elisa Teste', 'Fábio Teste', 'Gina Teste', 'Hugo Teste', 'Íris Teste']
for i, n in enumerate(NOMES):
    post('/admin/legislaturas', {'acao': 'vereador', 'leg': '16', 'nome': n, 'partido': 'PT1' if i % 2 else 'PT2', 'votos': str(100 + i)}, txt='Vereador salvo', nome='vereador ' + n)
mesa = {m['cargo']: m['id'] for m in db.todos(CM, "SELECT * FROM mesas WHERE legislatura=16 AND bienio='2029–2030'")}
post('/admin/legislaturas', {'acao': 'mesa', 'leg': '16', 'bienio': '2029–2030', f"cargo_{mesa['Presidente']}": 'Ana Teste', f"cargo_{mesa['Vice-presidente']}": 'Bruno Teste',
                             'eleicao': '2029-01-01', 'posse': '2029-01-01', 'ato': 'Ata da sessão de instalação (fictícia)'}, txt='Mesa do biênio', nome='mesa')
if L.legislatura_atual(CM) != 16: falha('legislatura atual deveria ser a 16ª')
V = {v['nome']: v['id'] for v in L.vereadores_atuais(CM)}
if (L.presidente_em(CM, L.config.hoje()) or {}).get('nome') != 'Ana Teste': falha('presidente não identificado')
# segundo biênio continua "a eleger" (nada inventado)
if db.um(CM, "SELECT count(*) n FROM mesas WHERE legislatura=16 AND bienio='2031–2032' AND nome IS NOT NULL")['n']: falha('2º biênio veio preenchido')

# ---------- 2. proposição com autores, numeração automática, tramitação e documento ----------
r = post('/admin/proposicoes/nova', {'acao': 'salvar', 'tipo': 'Projeto de Lei', 'ano': '2029', 'ementa': 'Institui o programa municipal de teste de fluxo legislativo.', 'autor': 'Bruno Teste', 'autor_outro': 'Poder Executivo', 'relator': 'Carla Teste', 'situacao': 'Em tramitação'}, txt='Proposição salva', nome='nova PL')
pl = db.um(CM, "SELECT * FROM proposicoes WHERE ano=2029 AND tipo='Projeto de Lei' ORDER BY id DESC LIMIT 1")
if pl['numero'] != 1: falha(f'numeração automática: {pl["numero"]}')
post('/admin/proposicoes/nova', {'acao': 'salvar', 'tipo': 'Projeto de Lei', 'ano': '2029', 'ementa': 'Segundo projeto de teste.', 'autor': 'Diego Teste'}, txt='Proposição salva', nome='PL 2')
if not db.um(CM, "SELECT 1 FROM proposicoes WHERE ano=2029 AND tipo='Projeto de Lei' AND numero=2"): falha('PL 2/2029 não numerada')
autores = {a['nome']: a['vereador_id'] for a in db.todos(CM, 'SELECT * FROM proposicao_autores WHERE proposicao_id=%s', (pl['id'],))}
if autores.get('Bruno Teste') != V['Bruno Teste'] or 'Poder Executivo' not in autores: falha(f'autores: {autores}')
u = f"/admin/proposicoes/{pl['id']}"
post(u, {'acao': 'tramitar', 'data': '2029-03-01', 'fase': 'Leitura em Plenário', 'descricao': 'Lida no expediente.'}, txt='Evento de tramitação', nome='tramitar')
r = post(u, {'acao': 'documento', 'tipo_doc': 'texto', 'titulo': 'Texto original', 'descricao': ''}, files={'arquivo': ('t.pdf', PDF, 'application/pdf')}, nome='doc sem descrição')
if 'descrição' not in msg(r): falha('documento sem descrição deveria ser recusado')
r = post(u, {'acao': 'documento', 'tipo_doc': 'texto', 'titulo': 'Falso', 'descricao': 'Arquivo que não é PDF de verdade.'}, files={'arquivo': ('t.pdf', b'GIF89a', 'application/pdf')}, nome='doc falso')
if 'não é um PDF' not in msg(r): falha('arquivo não PDF deveria ser recusado')
post(u, {'acao': 'documento', 'tipo_doc': 'texto', 'titulo': 'Texto original do projeto', 'descricao': 'Texto integral do projeto de lei de teste, com 3 artigos.'}, files={'arquivo': ('t.pdf', PDF, 'application/pdf')}, txt='Documento anexado', nome='doc')

# ---------- 3. comissão, pauta e parecer ----------
r = post('/admin/comissoes/nova', {'acao': 'salvar', 'nome': 'Comissão de Justiça (teste)', 'tipo': 'permanente', 'ativa': 'on'}, txt='Comissão salva', nome='comissão')
cid = db.um(CM, "SELECT id FROM comissoes WHERE nome='Comissão de Justiça (teste)'")['id']
for n, c in (('Carla Teste', 'Relator'), ('Diego Teste', 'Presidente'), ('Elisa Teste', 'Membro')):
    post(f'/admin/comissoes/{cid}', {'acao': 'membro', 'vereador': V[n], 'cargo': c}, txt='Membro salvo', nome='membro')
post(f'/admin/comissoes/{cid}', {'acao': 'reuniao', 'data': '2029-03-05', 'hora': '14h', 'pauta': f"Parecer ao {L.rotulo(pl)}"}, txt='Reunião cadastrada', nome='reunião')
post(f'/admin/comissoes/{cid}', {'acao': 'pub_reuniao', 'reuniao': db.um(CM, 'SELECT id FROM comissao_reunioes WHERE comissao_id=%s', (cid,))['id']}, txt='Pauta publicada', nome='pub reunião')
post(f'/admin/comissoes/{cid}', {'acao': 'parecer', 'proposicao': pl['id'], 'data': '2029-03-05', 'relator': 'Carla Teste', 'conclusao': 'Favorável', 'texto': 'Constitucional e oportuno.'}, txt='Parecer registrado', nome='parecer')
post(f'/admin/comissoes/{cid}', {'acao': 'pub_parecer', 'parecer': db.um(CM, 'SELECT id FROM pareceres WHERE comissao_id=%s', (cid,))['id']}, txt='Parecer publicado', nome='pub parecer')

# ---------- 4. sessão: pauta → presença → votação nominal → resultado → tramitação ----------
r = post('/admin/sessoes/nova', {'acao': 'criar', 'nome': '5ª Sessão Ordinária de 2029 (teste)', 'data': '2029-03-10', 'hora': '19h', 'tipo': 'Ordinária'}, txt='Sessão criada', nome='criar sessão')
sid = db.um(CM, "SELECT id FROM sessoes WHERE nome='5ª Sessão Ordinária de 2029 (teste)'")['id']; us = f'/admin/sessoes/{sid}'
post(us, {'acao': 'item', 'proposicao': pl['id'], 'quorum': 'simples', 'fase': 'Discussão e votação única'}, txt='Item incluído', nome='item pauta')
pl2 = db.um(CM, "SELECT * FROM proposicoes WHERE ano=2029 AND tipo='Projeto de Lei' AND numero=2")
post(us, {'acao': 'item', 'proposicao': pl2['id'], 'quorum': 'simples'}, txt='Item incluído', nome='item 2')
it1, it2 = [x['id'] for x in db.todos(CM, 'SELECT id FROM pauta_itens WHERE sessao_id=%s ORDER BY ordem', (sid,))]
r = post(us, {'acao': 'votar', 'item': it1, **{f'voto_{V[n]}': 'sim' for n in NOMES}}, nome='votar sem presença')
# 24/11/2026: a presença deixou de ser obrigatória antes da votação; aqui a recusa vem da regra do Presidente (voto fora do empate)
if 'Presidente só vota em caso de empate' not in msg(r): falha(f'votação sem presença: {msg(r)}')
if db.um(CM, 'SELECT 1 FROM votos WHERE item_id=%s', (it1,)): falha('voto gravado apesar da recusa')
pres = {f'pres_{V[n]}': ('ausente' if n == 'Íris Teste' else 'presente') for n in NOMES}
post(us, {'acao': 'presenca', **pres}, txt='Presença registrada', nome='presença')
votos = {f'voto_{V[n]}': v for n, v in zip(NOMES, ['sim', 'sim', 'sim', 'sim', 'nao', 'nao', 'abstencao', 'sim', 'ausente'])}  # Ana (presidente) "sim" sem empate → recusado
r = post(us, {'acao': 'votar', 'item': it1, **votos}, nome='presidente fora do empate')
if 'Presidente só vota em caso de empate' not in msg(r): falha(f'regra do presidente: {msg(r)}')
votos[f"voto_{V['Ana Teste']}"] = 'abstencao'
r = post(us, {'acao': 'votar', 'item': it1, **dict(votos, **{f"voto_{V['Íris Teste']}": 'sim'})}, nome='ausente votando')
if 'não está presente' not in msg(r): falha('ausente votando "sim" deveria ser recusado')
r = post(us, {'acao': 'votar', 'item': it1, **votos}, txt='APROVADO', nome='votação 1')
p = db.um(CM, 'SELECT * FROM proposicoes WHERE id=%s', (pl['id'],))
if p['situacao'] != 'Aprovada' or not db.um(CM, "SELECT 1 FROM tramitacao WHERE proposicao_id=%s AND fase LIKE 'Votação em Plenário%%' AND descricao LIKE 'Aprovado%%4 sim, 2 não%%'", (pl['id'],)):
    falha(f'tramitação/resultado após votação: {p["situacao"]}')
# empate: Presidente desempata
votos2 = {f'voto_{V[n]}': v for n, v in zip(NOMES, ['nao', 'sim', 'sim', 'sim', 'nao', 'nao', 'nao', 'abstencao', 'ausente'])}
r = post(us, {'acao': 'votar', 'item': it2, **votos2}, txt='Empate desfeito pelo voto do Presidente', nome='desempate')
if db.um(CM, 'SELECT resultado FROM pauta_itens WHERE id=%s', (it2,))['resultado'] != 'rejeitado': falha('desempate do presidente "não" deveria rejeitar')
# ainda não publicado: portal não mostra votos nem presença; perfil não soma nada
ok(cm.get(f'/sessoes/{sid}'), txt='Pauta ainda não publicada', nome='sessão antes de publicar', sem='Votação nominal:')
ok(cm.get(f"/vereador/{V['Bruno Teste']}"), txt='Nenhuma sessão com presença ou votação publicada', nome='perfil antes de publicar')
post(us, {'acao': 'ata', 'ata': 'Ata fictícia de teste: aberta a sessão, lidos e votados os itens da pauta, encerrada às 21h.'}, files={'arquivo': ('a.pdf', PDF, 'application/pdf')}, txt='Ata salva', nome='ata')
for a in ('pub_pauta', 'pub_presenca', 'pub_votacao', 'pub_ata'):
    post(us, {'acao': a}, txt='Publicado no portal', nome=a)
r = post(us, {'acao': 'votar', 'item': it1, **votos}, nome='votar depois de publicar')
if 'já publicada' not in msg(r): falha('votação publicada não pode ser alterada')
r = ok(cm.get(f'/sessoes/{sid}'), txt='Votação nominal', nome='sessão publicada')
for t_ in ('Bruno Teste', 'APROVADO', 'REJEITADO', 'Baixar a ata em PDF', 'ausente'):
    if t_ not in r.text: falha(f'sessão publicada sem "{t_}"')
r = ok(cm.get(f"/proposicoes/{pl['id']}"), txt='Votação nominal', nome='página da proposição')
for t_ in ('Leitura em Plenário', 'Parecer — Comissão de Justiça (teste)', 'Incluída na pauta', 'Texto original do projeto', 'Poder Executivo', 'Carla Teste', 'Favorável'):
    if t_ not in r.text: falha(f'proposição sem "{t_}"')
r = ok(cm.get(f"/vereador/{V['Bruno Teste']}"), txt='Presença e votos nominais', nome='perfil')
if not re.search(r'Presenças</dt><dd class="v">1</dd>', r.text) or 'Votos “Sim”</dt><dd class="v">2' not in r.text: falha('perfil: presença/votos calculados errados')
if L.estatisticas_vereador(CM, V['Íris Teste'])[0]['ausente'] != 1: falha('falta da Íris não contada')
ok(cm.get(f"/vereador/{V['Bruno Teste']}"), txt=L.rotulo(pl), nome='proposição no perfil do autor')
ok(cm.get('/proposicoes?tipo=Projeto+de+Lei&ano=2029&autor=Bruno'), txt=L.rotulo(pl), nome='filtro proposições')
ok(cm.get('/proposicoes?q=inexistente-xyz'), txt='Nenhuma proposição', nome='filtro vazio')
ok(cm.get('/comissoes'), txt='Constitucional e oportuno', nome='comissões no portal')

# ---------- 5. julgamento das contas (quórum de 2/3) ----------
post('/admin/contas', {'acao': 'salvar', 'exercicio': '2027', 'responsavel': 'Prefeito Fictício', 'tce_processo': 'TC-000000/2028 (teste)', 'tce_parecer': 'favorável', 'comissao_parecer': 'Pela aprovação', 'decreto': 'Decreto Legislativo nº 1/2029 (teste)'}, txt='Processo de contas salvo', nome='contas')
ct = db.um(CM, 'SELECT * FROM contas_julgamento WHERE exercicio=2027')
post('/admin/contas', {'acao': 'documento', 'contas': ct['id'], 'tipo_doc': 'parecer_tce', 'descricao': 'Parecer prévio fictício do Tribunal de Contas, para teste.'}, files={'arquivo': ('p.pdf', PDF, 'application/pdf')}, txt='Documento anexado', nome='parecer tce')
r = post('/admin/sessoes/nova', {'acao': 'criar', 'nome': '6ª Sessão Ordinária de 2029 (teste)', 'data': '2029-03-10', 'hora': '20h'}, txt='Sessão criada', nome='sessão 2')
sid2 = db.um(CM, "SELECT id FROM sessoes WHERE nome='6ª Sessão Ordinária de 2029 (teste)'")['id']
post('/admin/contas', {'acao': 'pauta', 'contas': ct['id'], 'sessao': sid2}, txt='Incluído na pauta', nome='contas na pauta')
itc = db.um(CM, 'SELECT * FROM pauta_itens WHERE contas_id=%s', (ct['id'],))
post(f'/admin/sessoes/{sid2}', {'acao': 'presenca', **{f'pres_{V[n]}': 'presente' for n in NOMES}}, txt='Presença registrada', nome='presença 2')
r = post(f'/admin/sessoes/{sid2}', {'acao': 'votar', 'item': itc['id'], **{f'voto_{V[n]}': ('sim' if i < 6 else 'nao') for i, n in enumerate(NOMES)}}, txt='APROVADO', nome='votação 2/3')  # 6 de 9 = 2/3
if 'Mínimo exigido: 6' not in msg(r): falha(f'quórum 2/3: {msg(r)}')
post(f'/admin/sessoes/{sid2}', {'acao': 'pub_votacao'}, txt='Publicado', nome='pub votação 2')
post('/admin/contas', {'acao': 'publicar', 'contas': ct['id']}, txt='Publicado', nome='pub contas')
ok(cm.get('/contas'), txt='6 sim', nome='contas no portal')

# ---------- 6. diárias (cadastro, importação CSV e transparência) ----------
post('/admin/diarias', {'acao': 'nova', 'beneficiario': 'Ana Teste', 'cargo': 'Vereadora', 'destino': 'São Paulo (SP)', 'motivo': 'Curso fictício', 'inicio': '2029-02-10', 'fim': '2029-02-11', 'valor': '350,00'}, txt='Diária lançada', nome='diária')
csvd = 'beneficiario;cargo;destino;motivo;inicio;fim;valor\nBruno Teste;Vereador;Assis (SP);Reunião fictícia;15/02/2029;15/02/2029;120,50\nCarla Teste;Vereadora;Marília (SP);Evento fictício;20/02/2029;;99,00\n'.encode()
def importa(modelo, dados, gravar):
    t_ = tok(cm, '/admin/importar'); return ok(cm.post('/admin/importar', data={'csrf': t_, 'modelo': modelo, 'acao': 'gravar' if gravar else 'simular'}, files={'arquivo': (f'{modelo}.csv', dados, 'text/csv')}), nome='importar ' + modelo)
r = importa('diarias', csvd, False)
if '0 gravadas' not in re.sub(r'<[^>]+>', '', r.text) or db.um(CM, "SELECT count(*) n FROM diarias_legislativo WHERE fonte='importacao'")['n']: falha('simulação gravou')
r = importa('diarias', csvd, True)
if db.um(CM, "SELECT count(*) n FROM diarias_legislativo WHERE fonte='importacao'")['n'] != 2: falha('importação de diárias')
ok(cm.get('/transparencia/diarias-camara?ano=2029'), txt='Bruno Teste', nome='diárias no portal')
c_ = ok(cm.get('/transparencia/diarias-camara.csv?ano=2029'), nome='diárias csv')
if c_.text.count('\n') < 4: falha('CSV de diárias')
# importação com erros: relatório linha a linha, nada gravado
ruim = 'nome;data;hora;tipo\nSessão boa (teste);01/03/2029;19h;Ordinária\nSem data;32/13/2029;19h;Ordinária\n;01/03/2029;19h;Ordinária\n'.encode()
r = importa('sessoes', ruim, True)
tx = re.sub(r'<[^>]+>', ' ', r.text)
if 'data inválida' not in tx or 'nome da sessão obrigatório' not in tx or db.um(CM, "SELECT 1 FROM sessoes WHERE nome='Sessão boa (teste)'"): falha('importação com erro deveria ser tudo ou nada com relatório')
r = importa('presencas', 'sessao_data;sessao_nome;vereador;situacao\n10/03/2029;5ª Sessão Ordinária de 2029 (teste);123.456.789-09;presente\n'.encode(), False)
if 'CPF' not in re.sub(r'<[^>]+>', ' ', r.text): falha('linha com CPF deveria ser recusada')
# importação de dados antigos completa (fictícios) via função: proposições, sessão, presença e votos
from app import importar as I
for m, d in [('proposicoes', 'tipo;numero;ano;autores;relator;ementa;situacao\nRequerimento;7;2029;Elisa Teste|Fábio Teste;;Requerimento fictício importado.;Em tramitação\n'),
             ('sessoes', 'nome;data;hora;tipo\n1ª Sessão Extraordinária de 2029 (teste);01/03/2029;19h;Extraordinária\n'),
             ('presencas', ''.join(['sessao_data;sessao_nome;vereador;situacao\n'] + [f'01/03/2029;1ª Sessão Extraordinária de 2029 (teste);{n};presente\n' for n in NOMES])),
             ('votos', ''.join(['sessao_data;tipo;numero;ano;vereador;voto\n'] + [f'01/03/2029;Requerimento;7;2029;{n};{"sim" if i < 5 else "nao"}\n' for i, n in enumerate(NOMES)]))]:
    rel = I.importar(CM, m, d.encode(), simular=False, quem='teste')
    if rel['erros'] or not rel['gravadas']: falha(f'importação {m}: {rel["erros"]}')
I.votacoes_importadas_tramitar(CM)
rq = db.um(CM, "SELECT * FROM proposicoes WHERE tipo='Requerimento' AND numero=7 AND ano=2029")
if not db.um(CM, "SELECT 1 FROM tramitacao WHERE proposicao_id=%s AND fase='Votação em Plenário (importada)'", (rq['id'],)): falha('tramitação dos votos importados')

# ---------- 7. transmissão ao vivo liga e desliga ----------
post('/admin/transmissoes', {'acao': 'config', 'canal': 'UC' + 'x' * 22, 'canal_url': 'https://www.youtube.com/@canal-teste'}, txt='Canal salvo', nome='canal')
r = post('/admin/transmissoes', {'acao': 'nova', 'titulo': 'Transmissão de teste', 'tipo': 'Sessão', 'video': 'javascript:alert(1)', 'sessao': sid}, nome='vídeo inválido')
if 'ID do vídeo' not in msg(r): falha('vídeo inválido deveria ser recusado')
post('/admin/transmissoes', {'acao': 'nova', 'titulo': 'Transmissão de teste', 'tipo': 'Sessão', 'video': 'https://www.youtube.com/watch?v=abcdefghijk', 'sessao': sid, 'legendas': 'on', 'libras': 'on'}, txt='agendada', nome='agendar')
tid = db.um(CM, "SELECT id FROM transmissoes WHERE titulo='Transmissão de teste'")['id']
ok(cm.get('/'), nome='home sem ao vivo', sem='class="ao-vivo"')
post('/admin/transmissoes', {'acao': 'iniciar', 'id': tid}, txt='AO VIVO', nome='iniciar')
r = ok(cm.get('/'), txt='class="ao-vivo"', nome='faixa ao vivo')
if 'aviso-vivo' not in r.text: falha('aviso diário ausente')
ok(cm.get('/transmissoes'), txt='youtube-nocookie.com/embed/abcdefghijk', nome='player')
post('/admin/transmissoes', {'acao': 'encerrar', 'id': tid}, txt='encerrada', nome='encerrar')
ok(cm.get('/'), nome='home depois de encerrar', sem='class="ao-vivo"')
ok(cm.get('/transmissoes'), txt='Gravações', nome='gravação')
pm = TestClient(app, base_url='http://pmbora.localhost')
ok(pm.get('/transmissoes'), 404, nome='prefeitura sem módulo de audiências')

# ---------- 8. participação ----------
sfut = db.exe(CM, "INSERT INTO sessoes (nome, data, hora) VALUES ('7ª Sessão Ordinária de 2029 (teste)', '2029-03-20', '19h') RETURNING id")['id']
t_ = tok(cm, f'/sessoes/{sfut}')
r = ok(cm.post(f'/sessoes/{sfut}/tribuna', data={'csrf': t_, 'nome': 'Fulana Participante Teste', 'contato': 'contato-ficticio-123', 'tema': 'Iluminação da praça (teste)', 'aceite': 'on'}, follow_redirects=True), txt='Inscrição recebida', nome='tribuna')
for pg in ('/', f'/sessoes/{sfut}', '/sessoes', '/transmissoes'):
    tx = cm.get(pg).text
    if 'Fulana Participante' in tx or 'contato-ficticio' in tx: falha(f'dado pessoal da Tribuna exposto em {pg}')
ok(cm.get('/admin/participacao'), txt='Fulana Participante Teste', nome='tribuna no painel')
tr = db.um(CM, 'SELECT id FROM tribuna_inscricoes ORDER BY id DESC LIMIT 1')['id']
post('/admin/participacao', {'acao': 'deferir', 'id': tr}, txt='deferida', nome='deferir')
for texto in ('Sou a favor, me liguem no (18) 99999-1234', 'Isso é coisa de idiota', 'Apoio o projeto porque melhora o atendimento.'):
    t_ = tok(cm, f"/proposicoes/{rq['id']}")
    cm.post(f"/proposicoes/{rq['id']}/opiniao", data={'csrf': t_, 'posicao': 'favor', 'texto': texto})
t_ = tok(cm, f"/proposicoes/{pl2['id']}")
ok(cm.post(f"/proposicoes/{pl2['id']}/opiniao", data={'csrf': t_, 'posicao': 'favor', 'texto': 'Opinião sobre projeto já votado.'}, follow_redirects=True), txt='não recebe mais opiniões', nome='opinião em proposição encerrada')
ops = {o['texto']: o['id'] for o in db.todos(CM, 'SELECT * FROM opinioes')}
r = post('/admin/participacao', {'acao': 'publicar', 'id': ops['Sou a favor, me liguem no (18) 99999-1234']}, nome='publicar com dado pessoal')
if 'Não publicado' not in msg(r): falha('opinião com telefone não pode ser publicada')
post('/admin/participacao', {'acao': 'rejeitar', 'id': ops['Isso é coisa de idiota'], 'motivo': 'Ofensa'}, txt='rejeitada', nome='rejeitar ofensa')
post('/admin/participacao', {'acao': 'publicar', 'id': ops['Apoio o projeto porque melhora o atendimento.']}, txt='publicada', nome='publicar')
r = ok(cm.get(f"/proposicoes/{rq['id']}"), txt='Apoio o projeto porque', nome='opinião publicada', sem='99999-1234')
if 'idiota' in r.text: falha('ofensa publicada')
t_ = tok(cm, '/sessoes')
ok(cm.post('/avaliar', data={'csrf': t_, 'pagina': '/sessoes', 'util': 'sim', 'comentario': 'meu email é fulano@exemplo.com'}, follow_redirects=True), txt='Obrigado', nome='avaliar')
ok(cm.post('/avaliar', data={'csrf': tok(cm, '/'), 'pagina': '//malicioso.example', 'util': 'sim'}, follow_redirects=False), 303, nome='avaliar sem redirecionamento externo')
if db.um(CM, "SELECT 1 FROM avaliacoes WHERE comentario LIKE '%%fulano@%%'"): falha('e-mail gravado no comentário da avaliação')
ok(cm.get('/admin/participacao'), txt='/sessoes', nome='avaliação por página')

# ---------- 9. PNTP (situação real) ----------
r = ok(cm.get('/admin/pntp'), txt='20.11', nome='pntp')
sit = {c: s for c, _, s, _, _ in L.pntp(CM)}
if sit['20.7'] != 'parcial' or sit['20.6'] == 'pendente' or sit['20.5'] != 'atendido' or sit['20.8'] != 'atendido' or sit['20.10'] != 'atendido' or sit['20.1'] != 'parcial':
    falha(f'PNTP: {sit}')
if db.um(CM, "SELECT count(*) n FROM sessoes WHERE pauta_publicada AND pauta='' AND NOT EXISTS (SELECT 1 FROM pauta_itens i WHERE i.sessao_id=sessoes.id) AND data > '2028-03-10'")['n'] and sit['20.4'] == 'atendido':
    falha('20.4 atendido com pauta vazia')
if not db.um(CM, "SELECT 1 FROM proposicao_autores a JOIN proposicoes p ON p.id=a.proposicao_id WHERE p.tipo='Indicação' AND a.vereador_id IS NOT NULL"): falha('autoria antiga não vinculada')
# ---------- 10. sessão em linha do tempo (24/11/2026): agendar, registrar depois, nada obrigatório ----------
r = ok(cm.get('/admin/sessoes?novo=1'), txt='Agendar', nome='tela de agendamento')
r = post('/admin/sessoes/nova', {'acao': 'criar', 'data': '2029-03-08', 'hora': '19:00', 'tipo': 'Extraordinária'}, txt='Sessão criada', nome='agendar extraordinária')
sx = db.um(CM, "SELECT * FROM sessoes WHERE tipo='Extraordinária' ORDER BY id DESC LIMIT 1")
if not sx or sx['nome'] != '1ª Sessão Extraordinária de 2029' or sx['numero'] != 1 or sx['situacao'] != 'agendada' or sx['hora'] != '19h': falha(f'agendamento automático: {sx and (sx["nome"], sx["numero"], sx["situacao"], sx["hora"])}')
post('/admin/sessoes/nova', {'acao': 'criar', 'data': '2029-03-09', 'tipo': 'Extraordinária'}, txt='2ª Sessão Extraordinária de 2029', nome='numeração por tipo')
ux = f"/admin/sessoes/{sx['id']}"
r = ok(cm.get(ux), txt='Nenhuma etapa é obrigatória', nome='tela da sessão')
for t_ in ('Agendamento', 'Pauta (Ordem do Dia)', 'Abertura e presença', 'Acontecimentos', 'Votações', 'Encerramento', 'Vídeos', 'Ata', 'Publicação no portal', 'Matéria nova nesta sessão'):
    if t_ not in r.text: falha(f'tela da sessão sem "{t_}"')
# matéria nova dentro da sessão, com autores, lida e na pauta
r = post(ux, {'acao': 'materia', 'tipo_materia': 'Moção', 'ementa': 'Moção de aplauso fictícia de teste.', 'autor': ['Carla Teste', 'Diego Teste'], 'lida': '1', 'na_pauta': '1', 'quorum': 'simples'},
         txt='Moção nº', nome='matéria nova')
mo = db.um(CM, "SELECT * FROM proposicoes WHERE tipo='Moção' AND ementa LIKE 'Moção de aplauso fictícia%%'")
au = {a['nome']: a['vereador_id'] for a in db.todos(CM, 'SELECT * FROM proposicao_autores WHERE proposicao_id=%s', (mo['id'],))} if mo else {}
if not mo or au.get('Carla Teste') != V['Carla Teste'] or au.get('Diego Teste') != V['Diego Teste']: falha(f'autoria da matéria nova: {au}')
if not db.um(CM, "SELECT 1 FROM sessao_eventos WHERE sessao_id=%s AND tipo='leitura' AND proposicao_id=%s AND vereador_id=%s", (sx['id'], mo['id'], V['Carla Teste'])): falha('leitura da matéria na linha do tempo')
itm = db.um(CM, 'SELECT * FROM pauta_itens WHERE sessao_id=%s AND proposicao_id=%s', (sx['id'], mo['id']))
if not itm: falha('matéria nova não entrou na pauta')
r = post(ux, {'acao': 'materia', 'tipo_materia': 'Requerimento', 'ementa': 'Sem autor.'}, nome='matéria sem autor')
if 'autor' not in msg(r): falha(f'matéria sem autor deveria ser recusada: {msg(r)}')
# votação simbólica sem presença nem horário registrados (registro depois da sessão, passos em branco)
r = post(ux, {'acao': 'simbolica', 'item': itm['id'], 'resultado': 'aprovado', 'observacao': 'por unanimidade dos presentes'}, txt='Resultado registrado: Aprovado', nome='votação simbólica')
if db.um(CM, 'SELECT situacao FROM proposicoes WHERE id=%s', (mo['id'],))['situacao'] != 'Aprovada': falha('moção aprovada em votação simbólica')
if db.um(CM, 'SELECT situacao FROM sessoes WHERE id=%s', (sx['id'],))['situacao'] != 'realizada': falha('sessão deveria virar realizada com o primeiro registro')
if db.um(CM, 'SELECT 1 FROM presencas WHERE sessao_id=%s', (sx['id'],)): falha('presença inventada')
# acontecimentos: hora opcional, vereador, ordem, LGPD
post(ux, {'acao': 'evento', 'tipo': 'orador', 'hora': '19:20', 'vereador': V['Elisa Teste'], 'descricao': 'Falou sobre a iluminação pública (teste).'}, txt='Acontecimento registrado', nome='orador')
post(ux, {'acao': 'evento', 'tipo': 'comunicacao', 'descricao': 'Comunicado de teste da Presidência.'}, txt='Acontecimento registrado', nome='evento sem hora')
r = post(ux, {'acao': 'evento', 'tipo': 'tribuna', 'descricao': 'Cidadão, telefone (14) 99999-1234'}, nome='tribuna com telefone')
if 'dado pessoal' not in msg(r): falha('acontecimento com telefone deveria ser recusado')
r = post(ux, {'acao': 'evento', 'tipo': 'outro', 'hora': '25h'}, nome='hora inválida')
if 'Hora inválida' not in msg(r) and 'Descreva' not in msg(r): falha(f'hora inválida: {msg(r)}')
evs = db.todos(CM, 'SELECT * FROM sessao_eventos WHERE sessao_id=%s ORDER BY ordem, id', (sx['id'],))
post(ux, {'acao': 'subir_evento', 'evento': evs[-1]['id']}, txt='Ordem ajustada', nome='subir')
if [e['id'] for e in db.todos(CM, 'SELECT id FROM sessao_eventos WHERE sessao_id=%s ORDER BY ordem, id', (sx['id'],))][-2] != evs[-1]['id']: falha('reordenar acontecimento')
post(ux, {'acao': 'encerramento', 'hora': '21h10'}, txt='Encerramento registrado às 21h10', nome='encerramento')
# vídeos
r = post(ux, {'acao': 'video', 'url': 'http://inseguro.test/v'}, nome='vídeo http')
if 'https://' not in msg(r): falha('vídeo sem https deveria ser recusado')
post(ux, {'acao': 'video', 'url': 'https://www.youtube.com/watch?v=TESTE123', 'rotulo': 'Transmissão ao vivo'}, txt='YouTube', nome='vídeo YouTube')
post(ux, {'acao': 'video', 'url': 'https://www.facebook.com/camara.teste/videos/123'}, txt='Facebook', nome='vídeo Facebook')
if db.um(CM, 'SELECT video_url FROM sessoes WHERE id=%s', (sx['id'],))['video_url'] != 'https://www.youtube.com/watch?v=TESTE123': falha('vídeo principal sincronizado')
# antes de publicar: nada no portal
r = ok(cm.get(f"/sessoes/{sx['id']}"), nome='portal antes de publicar', sem='Como foi a sessão')
# publicar tudo o que existe: presença e ata não existem e não travam o resto
r = post(ux, {'acao': 'pub_tudo'}, txt='Publicado:', nome='publicar tudo')
if 'presença' not in msg(r) or 'ata' not in msg(r): falha(f'publicar tudo deveria listar o que ficou sem registro: {msg(r)}')
sx2 = db.um(CM, 'SELECT * FROM sessoes WHERE id=%s', (sx['id'],))
if not (sx2['pauta_publicada'] and sx2['linha_publicada'] and sx2['votacao_publicada']) or sx2['presenca_publicada'] or sx2['ata_publicada']: falha('publicação parcial')
r = ok(cm.get(f"/sessoes/{sx['id']}"), txt='Como foi a sessão', nome='portal publicado')
for t_ in ('Sessão Extraordinária', 'Realizada', 'Elisa Teste', '19h20', 'Encerramento da sessão', '21h10', 'votação simbólica', 'por unanimidade', 'Assistir no YouTube', 'Assistir no Facebook', 'Leitura de matéria', 'Presença ainda não publicada'):
    if t_ not in r.text: falha(f'portal da sessão sem "{t_}"')
r = ok(cm.get(f"/vereador/{V['Elisa Teste']}"), txt='Participação nas sessões', nome='perfil com participação')
if 'iluminação pública' not in r.text: falha('participação do vereador no perfil')
r = ok(cm.get(f"/vereador/{V['Carla Teste']}"), txt='Moção de aplauso fictícia', nome='perfil com a moção')
# depois: a presença pode ser registrada e publicada mais tarde
post(ux, {'acao': 'presenca', f"pres_{V['Ana Teste']}": 'presente'}, txt='Presença registrada (1', nome='presença parcial depois')
post(ux, {'acao': 'pub_presenca'}, txt='Publicado no portal', nome='publicar presença depois')
# sessão passada sem nenhum registro: o portal não afirma "Agendada" (nem "Realizada")
s2x = db.um(CM, "SELECT id FROM sessoes WHERE nome='2ª Sessão Extraordinária de 2029'")['id']
r = ok(cm.get(f'/sessoes/{s2x}'), nome='sessão passada sem registro')
if re.search(r'class="chip[^"]*">(Agendada|Realizada)<', r.text): falha('sessão passada sem registro não deveria ter selo de situação')
# sessão futura: horário, presença e votação esperam o dia
post('/admin/sessoes/nova', {'acao': 'criar', 'data': '2029-04-20', 'tipo': 'Ordinária'}, txt='Sessão criada', nome='sessão futura')
sf = db.um(CM, "SELECT id FROM sessoes WHERE data='2029-04-20'")['id']
r = post(f'/admin/sessoes/{sf}', {'acao': 'abertura', 'hora': '19h'}, nome='abertura futura')
if 'dia da sessão' not in msg(r): falha('horário de sessão futura deveria esperar o dia')
r = post(f'/admin/sessoes/{sf}', {'acao': 'situacao', 'situacao': 'cancelada', 'motivo': ''}, nome='cancelar sem motivo')
if 'motivo' not in msg(r): falha('cancelamento exige motivo')
post(f'/admin/sessoes/{sf}', {'acao': 'situacao', 'situacao': 'cancelada', 'motivo': 'Ponto facultativo (teste)'}, txt='cancelada', nome='cancelar')
ok(cm.get(f'/sessoes/{sf}'), txt='Ponto facultativo (teste)', nome='portal sessão cancelada')
post('/admin/sessoes/nova', {'acao': 'criar', 'data': '2029-05-04', 'tipo': 'Ordinária'}, txt='Sessão criada', nome='sessão futura 2')
sf2 = db.um(CM, "SELECT id FROM sessoes WHERE data='2029-05-04'")['id']
ok(cm.get(f'/sessoes/{sf2}'), txt='>Agendada<', nome='sessão futura com selo Agendada')
ok(cm.get('/admin/sessoes'), txt='Cancelada', nome='lista com situação')

# LGPD geral: nenhuma página pública com CPF
for pg in ('/', '/proposicoes', f"/proposicoes/{pl['id']}", '/sessoes', f'/sessoes/{sid}', '/comissoes', '/contas', '/transmissoes', '/transparencia/diarias-camara', f"/vereador/{V['Ana Teste']}"):
    if re.search(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', cm.get(pg).text): falha(f'CPF em {pg}')
print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
