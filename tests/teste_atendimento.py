# e-SIC e Ouvidoria completos + integração entre instalações (23/11/2026). Nomes e e-mails FICTÍCIOS (domínios .invalid/.test),
# e-mail SIMULADO (nada sai da máquina), nós SIMULADOS no mesmo processo com bancos locais próprios.
# Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_atendimento.py
import os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import timedelta
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from app.main import app
from app import db, config, web, provision, licenca as L, integracao as IG, atendimento as A, remessa as RM, orgaos, worker, pntp_auto, email_saida as EM
from app.security import hash_senha
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apoio
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
CM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='cm-bora'")
B = PM['banco']
hoje = config.hoje()
apoio.ligar_email_teste()
CAIXA = apoio.CAIXA
config.CHAVE_CREDENCIAIS = Fernet.generate_key().decode()
def corpo(m):
    return m.get_body(preferencelist=('plain',)).get_content()
def ultimo(para):
    return next((m for m in reversed(CAIXA) if m['To'] == para), None)
def fila():
    A.enviar_fila(PM, 200)

# ---------- usuários fictícios: Ouvidoria/SIC, editor, duas autoridades de recurso ----------
for nome, email, perfil in [('Ouvidora Exemplo', 'ouv@pmbora.localhost', 'ouvidoria'), ('Editor Exemplo', 'ed@pmbora.localhost', 'editor'),
                            ('Autoridade Um', 'aut1@pmbora.localhost', 'autoridade_recurso'), ('Autoridade Dois', 'aut2@pmbora.localhost', 'autoridade_recurso')]:
    db.exe(B, "INSERT INTO usuarios (nome, email, perfil, senha_hash, trocar_senha) VALUES (%s,%s,%s,%s,FALSE) ON CONFLICT (email) DO NOTHING", (nome, email, perfil, hash_senha('senhaforte123')))
UID = {r['email']: r['id'] for r in db.todos(B, 'SELECT id, email FROM usuarios')}
def cli(email=None, host='pmbora.localhost'):
    c = TestClient(app, base_url=f'http://{host}')
    if email:
        entrar(c, email, 'senhaforte123' if email != 'admin@pmbora.localhost' else 'admin123', 'senhaforte123')
    return c
adm, ouv, ed, a1, a2 = cli('admin@pmbora.localhost'), cli('ouv@pmbora.localhost'), cli('ed@pmbora.localhost'), cli('aut1@pmbora.localhost'), cli('aut2@pmbora.localhost')
pub = cli()

# ---------- 1. migração: idempotente; registro antigo ganha prazo ----------
db.exe(B, "ALTER TABLE esic DROP CONSTRAINT IF EXISTS esic_situacao_check")
db.exe(B, "INSERT INTO esic (protocolo, tipo, assunto, texto, nome, email, recebido, situacao) VALUES ('SIC-2026-ANTIGO','pedido','Antigo','Texto','Pessoa Exemplo','pessoa@exemplo.invalid',%s,'prorrogado')", (hoje - timedelta(days=3),))
db.exe(B, "UPDATE esic SET prazo=NULL WHERE protocolo='SIC-2026-ANTIGO'")
provision.aplicar(B, provision.MIG_ORGAO); provision.aplicar(B, provision.MIG_ORGAO)
x = db.um(B, "SELECT * FROM esic WHERE protocolo='SIC-2026-ANTIGO'")
checa(x['prazo'] == hoje - timedelta(days=3) + timedelta(days=30) and x['prorrogado'] and x['situacao'] == 'analise', 'migração: antigo prorrogado ganha prazo 20+10 e vira "em análise"')

# ---------- 2. configuração (PNTP 12.1, 12.5, 12.6, 12.8, 12.9) ----------
med = pntp_auto.medir(PM, hoje)
checa(med['12.1']['itens'] and not med['12.1']['itens']['disponibilidade'] and not med['12.5']['itens']['disponibilidade'] and not med['12.8']['itens']['disponibilidade'], 'PNTP: sem configuração, 12.1/12.5/12.8 pendentes')
checa(ed.get('/admin/atendimento/configuracao').status_code == 403, 'editor não configura')
r = ouv.post('/admin/atendimento/configuracao', data={'csrf': tok(ouv, '/admin/atendimento/configuracao'), 'acao': 'salvar', 'unidade': 'SIC — Secretaria de Administração (exemplo)',
             'autoridade1_cargo': 'Secretário(a) de Administração (exemplo)', 'autoridade1_id': str(UID['aut1@pmbora.localhost']), 'autoridade2_cargo': 'Prefeito(a) (exemplo)',
             'autoridade2_id': str(UID['aut2@pmbora.localhost']), 'norma_nome': 'Decreto de exemplo nº 0/2026', 'norma_url': 'https://pmbora.localhost/legislacao/0',
             'email_equipe': 'equipe@pmbora.invalid', 'sem_classificadas': '1'}, follow_redirects=True)
checa('Configuração salva' in r.text and A.conf(B)['autoridade2_id'] == UID['aut2@pmbora.localhost'], 'Ouvidoria/SIC salva a configuração')
med = pntp_auto.medir(PM, hoje)
checa(all(med[k]['itens'] and all(med[k]['itens'].values()) for k in ('12.1', '12.3', '12.5', '12.6', '12.7', '12.8', '12.9')), 'PNTP 12.1, 12.3, 12.5–12.9 atendidos pela configuração')
t = pub.get('/e-sic').text
checa('SIC — Secretaria de Administração (exemplo)' in t and 'Prefeito(a) (exemplo)' in t and 'Decreto de exemplo' in t and '10 dias depois da resposta' in t and 'Base legal:' in t, 'página do e-SIC: unidade, autoridades, norma, prazo recursal')

# ---------- 3. registro: identificação, anônimo só denúncia, código mostrado uma vez ----------
def enviar(c=pub, **d):
    base = {'csrf': tok(c, '/e-sic'), 'tipo': 'pedido', 'assunto': 'Folha de exemplo', 'texto': 'Quero a folha de pagamento de exemplo.', 'nome': 'Cidadã Exemplo', 'email': 'cidada@exemplo.invalid'}
    base.update(d)
    return c.post('/acesso', data=base, follow_redirects=True)
checa('nome e um e-mail' in enviar(email='').text, 'pedido sem e-mail recusado')
checa('Só a denúncia pode ser anônima' in enviar(tipo='manifestacao', categoria='Reclamação', anonimo='1', nome='', email='').text, 'anônimo fora da denúncia recusado')
r = enviar(perfil_solicitante='pf')
prot = re.search(r'Protocolo (SIC-\d{4}-[0-9A-F]+)', r.text).group(1)
cod = re.search(r'<code>([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})</code>', r.text).group(1)
P = A.por_protocolo(B, prot)
checa(P['codigo_hash'] and cod not in str(P) and P['prazo'] == hoje + timedelta(days=20), 'só o hash do código no banco; prazo de 20 dias')
fila()
m = ultimo('cidada@exemplo.invalid')
checa(m and cod in corpo(m) and prot in corpo(m), 'e-mail ao cidadão com protocolo e código')
eq = ultimo('equipe@pmbora.invalid')
checa(eq and prot in corpo(eq) and 'Cidadã' not in corpo(eq) and 'cidada@' not in corpo(eq) and 'folha' not in corpo(eq).lower(), 'e-mail à equipe sem dado pessoal nem conteúdo')
checa(not db.um(B, "SELECT 1 x FROM email_fila WHERE enviado_em IS NOT NULL AND texto<>''"), 'texto apagado da fila depois do envio')
t = pub.get(f'/acesso?protocolo={prot}').text
checa('Recebido' in t and 'Folha de exemplo' not in t and 'Quero a folha' not in t, 'protocolo sem código: só a situação')
def ver(c=pub, codigo=None):
    return c.post('/acesso/consulta', data={'csrf': tok(c, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': codigo or cod}, follow_redirects=True)
checa('não confere' in ver(codigo='AAAA-BBBB-CCCC').text, 'código errado recusado')
checa('Quero a folha' in ver().text and 'Cidadã Exemplo' not in ver().text, 'com o código: conteúdo completo, sem o nome')
r = enviar(tipo='manifestacao', categoria='Denúncia', anonimo='1', nome='Ignorado', email='ignorado@exemplo.invalid', assunto='Denúncia de exemplo', texto='Fato de exemplo.')
DEN = A.por_protocolo(B, re.search(r'Protocolo (OUV-\d{4}-[0-9A-F]+)', r.text).group(1))
checa(DEN['anonimo'] and DEN['nome'] == '' and DEN['email'] == '' and DEN['prazo'] == hoje + timedelta(days=30), 'denúncia anônima: sem identidade, prazo de 30 dias')

# ---------- 4. painel: identidade só para Ouvidoria/SIC e administrador ----------
pid = P['id']
checa('Cidadã Exemplo' in ouv.get(f'/admin/atendimento/{pid}').text and 'Cidadã Exemplo' in adm.get(f'/admin/atendimento/{pid}').text, 'Ouvidoria/SIC e administrador veem a identidade')
t = ed.get(f'/admin/atendimento/{pid}').text
checa('Cidadã Exemplo' not in t and 'cidada@' not in t and 'restrita' in t, 'editor não vê a identidade')
checa(prot in ed.get('/admin/atendimento?situacao=abertos&tipo=pedido').text and prot not in ed.get('/admin/atendimento?tipo=manifestacao').text, 'filtros da lista')
def acao(c, p, **d):
    return c.post(f"/admin/atendimento/{p['id']}", data=dict({'csrf': tok(c, f"/admin/atendimento/{p['id']}")}, **d), follow_redirects=True)
acao(ed, P, acao='nota', texto='Nota interna de exemplo')
acao(ed, P, acao='setor', setor='Recursos Humanos (exemplo)')
checa('Nota interna de exemplo' not in ver().text and 'Recursos Humanos (exemplo)' in ed.get('/admin/atendimento?setor=Recursos+Humanos+(exemplo)').text, 'nota interna não aparece ao cidadão; filtro por setor')
checa(a1.post(f'/admin/atendimento/{pid}', data={'csrf': tok(a1, f'/admin/atendimento/{pid}'), 'acao': 'nota', 'texto': 'x'}).status_code == 403, 'autoridade de recurso não responde pedidos')

# ---------- 5. prorrogação única, complemento único ----------
checa('justificativa' in acao(ed, P, acao='prorrogar', justificativa='').text.lower(), 'prorrogação exige justificativa')
acao(ed, P, acao='prorrogar', justificativa='Volume de documentos (exemplo).')
P = A.por_protocolo(B, prot)
checa(P['prorrogado'] and P['prazo'] == hoje + timedelta(days=30), 'prorrogado por 10 dias')
checa('só uma prorrogação' in acao(ed, P, acao='prorrogar', justificativa='De novo').text, 'segunda prorrogação recusada')
acao(ed, P, acao='complemento', texto='Informe o mês de referência (exemplo).')
P = A.por_protocolo(B, prot)
checa(P['situacao'] == 'complemento' and P['prazo_restante'] == 30 and P['complemento_prazo'] == hoje + timedelta(days=20), 'complemento: prazo suspenso, 20 dias ao cidadão')
fila(); checa('complemente' in corpo(ultimo('cidada@exemplo.invalid')), 'e-mail do complemento')
r = pub.post('/acesso/acao', data={'csrf': tok(pub, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': cod, 'acao': 'complementar', 'texto': 'Março (exemplo).'}, follow_redirects=True)
P = A.por_protocolo(B, prot)
checa('Complemento enviado' in r.text and P['situacao'] == 'analise' and P['prazo'] == hoje + timedelta(days=30), 'complemento enviado: prazo volta a correr com o que faltava')
checa('só é permitido um' in acao(ed, P, acao='complemento', texto='Outro').text, 'segundo pedido de complemento recusado')

# ---------- 6. resposta: resultado, fundamento na negativa, CPF recusado ----------
checa('Escolha o resultado' in acao(ed, P, acao='responder', resposta='Segue.').text, 'pedido exige resultado')
checa('fundamento' in acao(ed, P, acao='responder', resposta='Negado.', resultado='negado', fundamento='').text, 'negativa exige fundamento')
checa('CPF' in acao(ed, P, acao='responder', resposta='Servidor 123.456.789-09 recebe X.', resultado='concedido').text, 'resposta com CPF completo recusada')
acao(ed, P, acao='responder', resposta='Acesso parcial (exemplo).', resultado='parcial', fundamento='LAI, art. 31 (dados pessoais) — exemplo')
P = A.por_protocolo(B, prot)
checa(P['situacao'] == 'respondido' and P['resultado'] == 'parcial' and P['respondido_por_id'] == UID['ed@pmbora.localhost'], 'respondido com resultado e autor')
fila(); checa('recorrer em até 10 dias' in corpo(ultimo('cidada@exemplo.invalid')), 'e-mail da resposta fala do recurso')

# ---------- 7. recurso: 1ª instância, quem respondeu não decide, autoridade configurada; 2ª instância ----------
def recorrer(texto='Discordo (exemplo).'):
    return pub.post('/acesso/acao', data={'csrf': tok(pub, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': cod, 'acao': 'recorrer', 'texto': texto}, follow_redirects=True)
checa('Recurso registrado' in recorrer().text and A.por_protocolo(B, prot)['situacao'] == 'recurso', 'recurso de 1ª instância')
P = A.por_protocolo(B, prot)
db.exe(B, "UPDATE usuarios SET perfil='autoridade_recurso' WHERE email='ed@pmbora.localhost'")  # o autor da resposta, mesmo virando autoridade, não decide
ok_, mot = A.pode_decidir(PM, P, {'id': UID['ed@pmbora.localhost'], 'perfil': 'autoridade_recurso', 'nome': 'Editor Exemplo'}, A.recurso_pendente(B, P))
checa(not ok_ and 'Quem respondeu' in mot, 'quem respondeu não decide o recurso')
db.exe(B, "UPDATE usuarios SET perfil='editor' WHERE email='ed@pmbora.localhost'")
checa('outra pessoa' in acao(a2, P, acao='decidir', decisao='x', resultado='provido').text, '1ª instância só pela autoridade configurada')
acao(a1, P, acao='decidir', decisao='Mantida a resposta (exemplo).', resultado='improvido')
P = A.por_protocolo(B, prot)
checa(P['situacao'] == 'respondido' and A.recursos(B, pid)[0]['resultado'] == 'improvido', '1ª instância decidida')
checa('Recurso registrado' in recorrer('Segunda instância (exemplo).').text, 'recurso de 2ª instância')
P = A.por_protocolo(B, prot)
ok_, mot = A.pode_decidir(PM, P, {'id': UID['aut1@pmbora.localhost'], 'perfil': 'autoridade_recurso', 'nome': 'x'}, A.recurso_pendente(B, P))
checa(not ok_ and '1ª instância não pode' in mot, 'quem decidiu a 1ª não decide a 2ª')
acao(a2, P, acao='decidir', decisao='Provido parcialmente (exemplo).', resultado='parcial')
checa('Não cabe novo recurso' in A.pode_recorrer(B, A.por_protocolo(B, prot))[1], 'depois da 2ª instância, sem novo recurso')
# prazo de recurso vencido
p2, c2, _ = A.registrar(PM, {'tipo': 'pedido', 'assunto': 'Outro', 'texto': 'Outro pedido de exemplo.', 'nome': 'Pessoa Exemplo', 'email': 'p2@exemplo.invalid'})
A.responder(PM, p2, {'id': UID['ouv@pmbora.localhost'], 'nome': 'Ouvidora Exemplo'}, 'Concedido (exemplo).', 'concedido')
db.exe(B, 'UPDATE esic SET respondido=%s WHERE id=%s', (hoje - timedelta(days=11), p2['id']))
checa('prazo de recurso terminou' in (A.recorrer(PM, A.por_protocolo(B, p2['protocolo']), 'tarde') or ''), 'recurso fora dos 10 dias recusado')

# ---------- 8. avaliação ----------
r = pub.post('/acesso/acao', data={'csrf': tok(pub, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': cod, 'acao': 'avaliar', 'nota': '4', 'resolveu': 'sim'}, follow_redirects=True)
checa('Obrigado' in r.text and A.por_protocolo(B, prot)['avaliacao'] == 4, 'avaliação registrada')
checa('já foi avaliado' in (A.avaliar(PM, A.por_protocolo(B, prot), 5, 'sim') or ''), 'avaliação só uma vez')

# ---------- 9. Ouvidoria: prorrogação 30+30; complemento vencido encerra; resumo diário ----------
A.prorrogar(PM, DEN, {'id': UID['ouv@pmbora.localhost'], 'nome': 'Ouvidora Exemplo'}, 'Apuração (exemplo).')
checa(A.por_protocolo(B, DEN['protocolo'])['prazo'] == hoje + timedelta(days=60), 'Ouvidoria: prorrogação de 30 dias')
p3, c3, _ = A.registrar(PM, {'tipo': 'manifestacao', 'categoria': 'Sugestão', 'assunto': 'Sugestão', 'texto': 'Sugestão de exemplo.', 'nome': 'Pessoa Exemplo', 'email': 'p3@exemplo.invalid'})
A.pedir_complemento(PM, p3, {'id': UID['ouv@pmbora.localhost'], 'nome': 'Ouvidora Exemplo'}, 'Detalhe o local (exemplo).')
db.exe(B, 'UPDATE esic SET complemento_prazo=%s WHERE id=%s', (hoje - timedelta(days=1), p3['id']))
p4, _, _ = A.registrar(PM, {'tipo': 'pedido', 'assunto': 'Vencendo', 'texto': 'Pedido de exemplo vencendo.', 'nome': 'Pessoa Exemplo', 'email': 'p4@exemplo.invalid'})
db.exe(B, 'UPDATE esic SET prazo=%s WHERE id=%s', (hoje + timedelta(days=1), p4['id']))
db.set_cfg(B, 'atendimento_rotina', '')
from datetime import datetime
worker.atendimento_tick(datetime.now().replace(hour=8))
checa(A.por_protocolo(B, p3['protocolo'])['situacao'] == 'encerrado', 'worker: complemento vencido encerra')
res = next((m for m in reversed(CAIXA) if m['To'] == 'equipe@pmbora.invalid' and 'vencendo' in m['Subject']), None)
checa(res and p4['protocolo'] in corpo(res) and 'p4@' not in corpo(res) and 'Pessoa' not in corpo(res), 'resumo diário à equipe, sem dado pessoal')
n = len(CAIXA); worker.atendimento_tick(datetime.now().replace(hour=9)); fila()
checa(not any('vencendo' in m['Subject'] for m in CAIXA[n:]), 'resumo só uma vez por dia')

# ---------- 10. registro presencial; SMTP próprio; sem SMTP a fila espera ----------
r = ouv.post('/admin/atendimento/novo', data={'csrf': tok(ouv, '/admin/atendimento/novo'), 'tipo': 'pedido', 'assunto': 'Balcão', 'texto': 'Pedido no balcão (exemplo).', 'nome': 'Pessoa Balcão Exemplo'}, follow_redirects=True)
checa(re.search(r'código <strong><code>[A-Z0-9-]{14}</code>', r.text) and db.um(B, "SELECT 1 x FROM esic WHERE canal='presencial' AND assunto='Balcão'"), 'registro presencial com protocolo e código')
r = ouv.post('/admin/atendimento/configuracao', data={'csrf': tok(ouv, '/admin/atendimento/configuracao'), 'acao': 'smtp', 'servidor': 'smtp.pmbora.test', 'porta': '465', 'seguranca': 'ssl',
             'usuario': 'sic', 'senha': 'senha-de-exemplo-123', 'remetente': 'sic@pmbora.test', 'remetente_nome': 'SIC Exemplo'}, follow_redirects=True)
s = db.um(B, 'SELECT * FROM atendimento_smtp')
checa('gravado' in r.text and s and 'senha-de-exemplo-123' not in s['senha_cifrada'] and 'senha-de-exemplo-123' not in ouv.get('/admin/atendimento/configuracao').text, 'SMTP próprio: senha cifrada e nunca mostrada')
r = ouv.post('/admin/atendimento/configuracao', data={'csrf': tok(ouv, '/admin/atendimento/configuracao'), 'acao': 'smtp_testar', 'para': 'teste@pmbora.invalid'}, follow_redirects=True)
checa('SMTP do órgão' in r.text and ultimo('teste@pmbora.invalid')['From'].endswith('<sic@pmbora.test>'), 'teste do SMTP próprio')
A.enfileirar(B, 'x@exemplo.invalid', 'Assunto', 'Texto'); fila()
checa(ultimo('x@exemplo.invalid')['From'].endswith('<sic@pmbora.test>'), 'com SMTP próprio, sai por ele')
A.smtp_remover(B); db.exe(db.PLATAFORMA, 'DELETE FROM email_saida')
A.enfileirar(B, 'y@exemplo.invalid', 'Assunto', 'Texto'); fila()
checa(not ultimo('y@exemplo.invalid') and 'aguardando' in db.um(B, "SELECT erro FROM email_fila WHERE para='y@exemplo.invalid'")['erro'], 'sem SMTP: e-mail espera na fila')
apoio.ligar_email_teste(); fila()
checa(ultimo('y@exemplo.invalid'), 'SMTP configurado: a fila sai')

# ---------- 11. páginas públicas: estatísticas, classificadas, relatório ----------
t = pub.get('/e-sic/estatisticas').text
checa('Base legal:' in t and 'Acesso parcialmente concedido' in t and 'pessoa física' in t, 'estatísticas do e-SIC')
j = pub.get('/e-sic/estatisticas?formato=json').json()
checa(j['indicadores']['parciais'] >= 1 and j['indicadores']['recursos_2'] >= 1 and j['indicadores']['pf'] >= 1, 'estatísticas em JSON')
checa(pub.get('/e-sic/estatisticas?formato=csv').headers['content-type'].startswith('text/csv'), 'estatísticas em CSV')
checa('Cidadã' not in t and 'cidada@' not in t, 'estatísticas sem dado pessoal')
checa('Declaração do órgão' in pub.get('/e-sic/informacoes-classificadas').text, 'classificadas: declaração de inexistência')
ouv.post('/admin/atendimento/classificadas', data={'csrf': tok(ouv, '/admin/atendimento/classificadas'), 'grau': 'reservado', 'assunto': 'Plano de exemplo', 'fundamento': 'LAI, art. 23, VIII (exemplo)',
          'classificada_em': hoje.isoformat(), 'prazo_ate': (hoje + timedelta(days=365 * 6)).isoformat()}, follow_redirects=True)
checa(not db.um(B, "SELECT 1 x FROM info_classificadas WHERE assunto='Plano de exemplo'"), 'reservado acima de 5 anos recusado')
ouv.post('/admin/atendimento/classificadas', data={'csrf': tok(ouv, '/admin/atendimento/classificadas'), 'grau': 'reservado', 'assunto': 'Plano de exemplo', 'fundamento': 'LAI, art. 23, VIII (exemplo)',
          'classificada_em': hoje.isoformat()}, follow_redirects=True)
ci = db.um(B, "SELECT * FROM info_classificadas WHERE assunto='Plano de exemplo'")
checa(ci and ci['prazo_ate'] == hoje + timedelta(days=365 * 5) and 'Plano de exemplo' in pub.get('/e-sic/informacoes-classificadas').text, 'classificada publicada com prazo máximo do grau')
ouv.post('/admin/atendimento/classificadas', data={'csrf': tok(ouv, '/admin/atendimento/classificadas'), 'id': str(ci['id']), 'acao': 'desclassificar', 'motivo': 'Fim da necessidade (exemplo)'}, follow_redirects=True)
t = pub.get('/e-sic/informacoes-classificadas').text
checa('Fim da necessidade (exemplo)' in t and 'desclassificada' in pub.get('/e-sic/informacoes-classificadas?formato=csv').text, 'desclassificada aparece na lista dos 12 meses (página e CSV)')
t = pub.get('/ouvidoria/relatorio').text
checa('Base legal:' in t and 'Denúncia' in t and 'Denúncias anônimas' in t, 'relatório da Ouvidoria')
checa(pub.get('/ouvidoria/relatorio?formato=json').json()['totais']['anonimas'] >= 1, 'relatório em JSON')
checa(ouv.get('/admin/atendimento/relatorio').status_code == 200 and 'Últimos e-mails' in ouv.get('/admin/atendimento/relatorio').text, 'relatório no painel')

# ---------- 12. duas instalações: PM no nó A, CM no nó B, bancos locais separados ----------
_, pubk = L.garantir_chaves()
config.GESTAO_URL, config.NO_TOKEN, config.LICENCA_CHAVE_PUBLICA = 'https://gestao.exemplo.test', 'token-de-teste', pubk
LA, LB = 'no_a_atend_teste', 'no_b_atend_teste'
for nome_b in (LA, LB):
    provision.criar_banco(nome_b); provision.aplicar(nome_b, provision.MIG_LOCAL)
L.criar_no('no-a.exemplo.test'); L.criar_no('no-b.exemplo.test')
NA = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-a.exemplo.test'")
NB = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-b.exemplo.test'")
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (NA['id'], PM['id']))
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (NB['id'], CM['id']))
ESTADO = {'no': None}
def gestao(fn, *a):
    papel, local = config.PAPEL, db.LOCAL
    config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA
    try:
        return fn(*a)
    finally:
        config.PAPEL, db.LOCAL = papel, local
def no(n):
    """Passa a "ser" o nó n (None = gestão)."""
    ESTADO['no'] = n
    if n is None:
        config.PAPEL, db.LOCAL = 'tudo', db.PLATAFORMA
        os.environ.pop('NO_NOME', None)
    else:
        config.PAPEL, db.LOCAL = 'no', (LA if n['id'] == NA['id'] else LB)
        os.environ['NO_NOME'] = n['nome']
    web.limpar_cache(); L._memo.clear()
def puxar(n):
    no(n); L.buscar_na_gestao = lambda: gestao(L.entregar, db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (n['id'],)))
    return L.puxar()
DONO = {PM['slug']: NA, CM['slug']: NB}
CHAMADAS = []
class Cli:
    """Cliente do parceiro: atende a requisição "dentro" do nó do destino; registra se foi por HTTPS (outra instalação)."""
    def __init__(s, d): s.d = d
    def __enter__(s): return s
    def __exit__(s, *a): return False
    def request(s, metodo, caminho, content=None, headers=None):
        CHAMADAS.append((s.d['slug'], bool(s.d.get('parceiro'))))
        antes = ESTADO['no']; no(DONO[s.d['slug']])
        try:
            return TestClient(app, base_url=f"https://{s.d['dominio']}").request(metodo, caminho, content=content, headers=headers)
        finally:
            no(antes)
    def get(s, caminho, headers=None): return s.request('GET', caminho, headers=headers)
IG._cliente = lambda d: Cli(d)
m1 = puxar(NA); m2 = puxar(NB)
checa('1 órgão(s) parceiro(s)' in m1 and '1 órgão(s) parceiro(s)' in m2, f'cada nó recebe o diretório com o parceiro ({m1} | {m2})')
no(NA)
pm_a = orgaos.por_slug('pm-bora'); cm_em_a = IG.orgao(slug='cm-bora')
checa(pm_a and orgaos.por_slug('cm-bora') is None and cm_em_a and cm_em_a.get('parceiro'), 'nó A: PM local, CM é parceiro de outra instalação')
checa(IG.parceiros(pm_a)[0]['mesma_instalacao'] is False and db.um(LA, 'SELECT count(*) n FROM pares_orgaos')['n'] == 2, 'nó A conhece o par nos dois sentidos')
r = IG.chamar(pm_a, cm_em_a, 'GET', '/api/integracao/ping', None, 'teste')
checa(r.get('ok') and r.get('slug') == 'cm-bora' and r.get('papel') == 'no' and CHAMADAS[-1] == ('cm-bora', True), 'ping PM(A) → CM(B) por HTTPS')
no(NB); cm_b = orgaos.por_slug('cm-bora'); pm_em_b = IG.orgao(slug='pm-bora')
checa(IG.chamar(cm_b, pm_em_b, 'GET', '/api/integracao/ping').get('slug') == 'pm-bora', 'ping CM(B) → PM(A)')
checa(orgaos.executivo_do(cm_b['ibge'])['slug'] == 'pm-bora', 'executivo_do na Câmara (nó B) acha a Prefeitura de outra instalação')
from app import portal_fase8 as F8
leg, pm_leg = F8._leg_prefeitura(cm_b)
checa(leg is not None and pm_leg['slug'] == 'pm-bora' and CHAMADAS[-1] == ('pm-bora', True), 'Câmara lê a legislação da Prefeitura por API pública em outra instalação')
checa(RM.destino_do(cm_b) and RM.destino_do(cm_b)['slug'] == 'pm-bora', 'remessa: Diário de destino é a Prefeitura do outro nó')
try:
    rid = RM.enviar(cm_b, 'Teste', 'Portaria da Câmara', '1/2026', 'Ementa de exemplo', 'Texto de exemplo da remessa.')
    no(NA); ato = db.um(B, "SELECT * FROM diario_atos WHERE origem_orgao='cm-bora' ORDER BY id DESC LIMIT 1")
    checa(ato and ato['remessa_externa'] == f'cm-bora:{rid}', 'remessa CM(B) → Diário da PM(A)')
except ValueError as e:
    checa(False, f'remessa entre instalações falhou: {e}')
# painel "Órgãos parceiros" (nó B) com teste de conversa
no(NB)
CMB = CM['banco']
db.exe(CMB, "INSERT INTO usuarios (nome, email, perfil, senha_hash, trocar_senha) VALUES ('Admin CM Exemplo','admcm@cmbora.localhost','admin',%s,FALSE) ON CONFLICT (email) DO NOTHING", (hash_senha('senhaforte123'),))
cmadm = cli('admcm@cmbora.localhost', 'cmbora.localhost')
t = cmadm.get('/admin/parceiros').text
checa('outra instalação' in t and 'ativa' in t, 'painel Órgãos parceiros mostra a PM em outra instalação')
r = cmadm.post('/admin/parceiros', data={'csrf': tok(cmadm, '/admin/parceiros'), 'id': str(PM['id'])}, follow_redirects=True)
checa('Conversa ok' in r.text and 'outra instalação' in r.text, 'testar conversa pelo painel')
# encaminhamento: pedido na CM (B) é da PM (A): vai sem identidade; novo protocolo; consulta de situação
no(NB)
pc, cc, _ = A.registrar(cm_b, {'tipo': 'pedido', 'assunto': 'Obra de exemplo', 'texto': 'Contrato da obra de exemplo.', 'nome': 'Cidadão Exemplo', 'email': 'cidadao@exemplo.invalid'})
db.exe(CMB, "UPDATE usuarios SET perfil='ouvidoria' WHERE email='admcm@cmbora.localhost'")
cmadm2 = cli('admcm@cmbora.localhost', 'cmbora.localhost')
r = cmadm2.post(f"/admin/atendimento/{pc['id']}", data={'csrf': tok(cmadm2, f"/admin/atendimento/{pc['id']}"), 'acao': 'encaminhar', 'destino': str(PM['id'])}, follow_redirects=True)
pc = A.por_protocolo(CMB, pc['protocolo'])
checa('Encaminhado' in r.text and pc['situacao'] == 'encaminhado' and pc['encaminhado_protocolo'].startswith('SIC-'), 'encaminhado com novo protocolo')
no(NA)
novo = A.por_protocolo(B, pc['encaminhado_protocolo'])
checa(novo and novo['nome'] == '' and novo['email'] == '' and novo['canal'] == 'encaminhado' and novo['origem_orgao'] == 'cm-bora' and A.confere(novo, pc['encaminhado_codigo']),
      'no destino: sem identidade, canal encaminhado, código vale')
checa('Cidadão Exemplo' not in str(db.todos(B, 'SELECT * FROM esic_historico WHERE esic_id=%s', (novo['id'],))), 'histórico do destino sem identidade')
no(NB); A.enviar_fila(cm_b, 100)
checa(not ultimo('cidadao@exemplo.invalid') and 'aguardando' in db.um(CMB, "SELECT erro FROM email_fila WHERE para='cidadao@exemplo.invalid' ORDER BY id DESC LIMIT 1")['erro'],
      'nó sem SMTP próprio: e-mail espera na fila (o e-mail da plataforma é só da instalação principal)')
checa(A.smtp_salvar(CMB, {'servidor': 'smtp.cmbora.test', 'porta': '465', 'seguranca': 'ssl', 'usuario': 'sic', 'senha': 'senha-de-exemplo-456', 'remetente': 'sic@cmbora.test'}, 'teste') is None, 'SMTP próprio da Câmara')
A.enviar_fila(cm_b, 100)
m = ultimo('cidadao@exemplo.invalid')
checa(m and pc['encaminhado_protocolo'] in corpo(m) and pc['encaminhado_codigo'] in corpo(m), 'cidadão recebe o novo protocolo e o código')
no(NA); A.responder(pm_a, novo, {'id': 1, 'nome': 'Servidor Exemplo'}, 'Resposta de exemplo.', 'concedido')
no(NB)
r = cmadm2.post(f"/admin/atendimento/{pc['id']}", data={'csrf': tok(cmadm2, f"/admin/atendimento/{pc['id']}"), 'acao': 'consultar'}, follow_redirects=True)
checa(A.por_protocolo(CMB, pc['protocolo'])['encaminhado_situacao'] == 'respondido', 'consulta da situação no destino')
# renovação de chaves: até os dois nós buscarem, a conversa falha; depois volta
gestao(IG.renovar, PM['id'])
puxar(NA)  # só o nó A buscou
no(NA)
try:
    IG.chamar(orgaos.por_slug('pm-bora'), IG.orgao(slug='cm-bora'), 'GET', '/api/integracao/ping'); checa(False, 'chave nova num nó e velha no outro: deveria recusar')
except ValueError as e:
    checa('recusou' in str(e), 'chave renovada só num lado: recusada')
puxar(NB); no(NA)
checa(IG.chamar(orgaos.por_slug('pm-bora'), IG.orgao(slug='cm-bora'), 'GET', '/api/integracao/ping').get('ok'), 'chaves renovadas nos dois nós: conversa volta')
# diretório adulterado, de outro nó ou antigo: ignorado
no(NA)
d = gestao(IG.diretorio_para, NA)
ad = dict(d); ad['doc'] = dict(d['doc'], parceiros=[]); checa(IG.guardar_diretorio(ad, pubk) is None, 'diretório adulterado recusado')
checa(IG.guardar_diretorio(gestao(IG.diretorio_para, NB), pubk) is None, 'diretório de outro nó recusado')
velho = gestao(lambda: L.assinar(dict(d['doc'], emitido_em=(datetime.fromisoformat(d['doc']['emitido_em']) - timedelta(minutes=10)).isoformat(), parceiros=[])))
checa(IG.guardar_diretorio(velho, pubk) is None and IG.parceiros_no_no(), 'diretório mais antigo que o guardado: ignorado')
# integração desligada pela gestão: depois da busca, nenhum dos dois conversa
gestao(IG.ligar, PM['id'], False)
puxar(NA); puxar(NB); no(NA)
try:
    IG.chamar(orgaos.por_slug('pm-bora'), IG.orgao(slug='cm-bora'), 'GET', '/api/integracao/ping'); checa(False, 'integração desligada: deveria recusar')
except ValueError as e:
    checa('Não há integração ativa' in str(e), 'integração desligada: recusa já na origem')
no(NB)
checa(RM.destino_do(orgaos.por_slug('cm-bora')) is None, 'integração desligada: Câmara sem Diário de destino')
gestao(IG.ligar, PM['id'], True)

# ---------- volta ao normal ----------
no(None)
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=NULL WHERE id IN (%s,%s)', (PM['id'], CM['id']))
print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
