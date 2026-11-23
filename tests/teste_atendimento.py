# e-SIC e Ouvidoria (23/11/2026) e integração entre órgãos em INSTALAÇÕES SEPARADAS.
# Parte 1 (papel "tudo"): pedido LAI com código de acesso, prorrogação, complemento, resposta com fundamento, recurso
#   decidido por outra pessoa, ouvidoria com identidade protegida, denúncia anônima, e-mails pela fila do órgão,
#   relatório estatístico, relatório da Ouvidoria, informações classificadas e encaminhamento Prefeitura → Câmara.
# Parte 2 (papel "no" simulado): Prefeitura no nó A e Câmara no nó B, cada um com o próprio banco local; a gestão
#   distribui o diretório assinado; encaminhamento, remessa ao Diário, legislação, teste de conversa e troca de chaves.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_atendimento.py
import os, re, sys, copy
from datetime import date, timedelta, datetime, timezone
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, web, licenca as L, provision, integracao as I, atendimento as A, notificacoes as N, email_saida as EM, remessa as RM
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def msg(r):
    m = re.search(r'<p class="msg"[^>]*>(.*?)</p>', r.text, re.S)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else ''

config.CHAVE_CREDENCIAIS = Fernet.generate_key().decode()
CAIXA = []
EM._smtp_enviar = lambda cfg, senha, m: CAIXA.append(m)
PMo = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'"); CMo = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='cm-bora'")
PM, CM = PMo['banco'], CMo['banco']
I.cliente_local_original = I.cliente_local
I.cliente_local = lambda: TestClient(app, base_url='http://interno')  # o "endereço interno" é o próprio app

pub = TestClient(app, base_url='http://pmbora.localhost')
adm = TestClient(app, base_url='http://pmbora.localhost')
r = entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
checa('Visão geral' in r.text, 'login do administrador')

# ---------- configuração e e-mail do órgão ----------
r = adm.post('/admin/atendimento-config', data={'csrf': tok(adm, '/admin/atendimento-config'), 'acao': 'regras', 'unidade': 'SIC da Prefeitura', 'autoridade_1': 'Chefe de Gabinete',
             'instancias': '2', 'autoridade_2': 'Prefeito', 'norma_lai': 'Decreto nº 1/2012 (exemplo)', 'norma_lai_url': 'https://exemplo.test/decreto', 'email_equipe': 'equipe@pmbora.localhost'}, follow_redirects=True)
checa('Regras do atendimento salvas' in msg(r), 'regras salvas')
r = adm.post('/admin/atendimento-config', data={'csrf': tok(adm, '/admin/atendimento-config'), 'acao': 'smtp', 'servidor': 'smtp.exemplo.test', 'porta': '465', 'seguranca': 'ssl',
             'usuario': 'ouvidoria', 'senha': 'segredo-smtp', 'remetente': 'ouvidoria@pmbora.localhost', 'remetente_nome': 'Ouvidoria'}, follow_redirects=True)
checa('E-mail de saída do órgão salvo' in msg(r) and 'segredo-smtp' not in r.text, 'SMTP do órgão salvo, sem a senha na tela')
c = db.cfg(PM, 'email_saida')
checa(c and c['senha_cifrada'] and 'segredo-smtp' not in str(c), 'senha do SMTP gravada cifrada')
checa(N.caminho(PM) == 'orgao', 'e-mail sai pelo SMTP do próprio órgão')

# ---------- pedido LAI pelo portal ----------
t = pub.get('/e-sic').text
checa('SIC da Prefeitura' in t and 'Chefe de Gabinete' in t and 'Decreto nº 1/2012' in t and '10 dias' in t and '2ª instância' in t, 'página do e-SIC: unidade, autoridades, norma e prazos (PNTP 12.1, 12.5, 12.6)')
r = pub.post('/acesso', data={'csrf': tok(pub, '/e-sic'), 'tipo': 'pedido', 'assunto': 'Folha de pagamento', 'texto': 'Quero a folha de outubro.', 'nome': 'Maria Teste', 'email': 'maria@teste.localhost', 'tipo_pessoa': 'fisica'}, follow_redirects=True)
m = re.search(r'Código de acesso: <strong><code>([A-Z0-9-]+)</code>', r.text)
prot = re.search(r'Protocolo (SIC-\d{4}-[0-9A-F]{6})', r.text)
checa(m and prot, 'registro mostra protocolo e código de acesso')
codigo, prot = (m.group(1) if m else ''), (prot.group(1) if prot else '')
p = A.por_protocolo(PM, prot)
checa(p and p['prazo'] == A.limite(config.hoje(), 20) and p['codigo_hash'] and codigo not in str(dict(p)), 'prazo de 20 dias e só o hash do código no banco')
checa('Maria Teste' not in r.text and 'maria@teste' not in r.text, 'nome e e-mail não aparecem no portal')
outro = TestClient(app, base_url='http://pmbora.localhost')
t = outro.get(f'/acesso?protocolo={prot}').text
checa('Recebido' in t and 'Quero a folha' not in t and 'código de acesso' in t, 'sem o código: só a situação')
r = outro.post('/acesso/consultar', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': 'AAAA-BBBB-CCCC'}, follow_redirects=True)
checa('não confere' in msg(r) and 'Quero a folha' not in r.text, 'código errado recusado')
r = outro.post('/acesso/consultar', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'codigo': codigo.lower()}, follow_redirects=True)
checa('Quero a folha' in r.text, 'com o código: conteúdo e andamento')
N.processar(PMo)
ms = [x for x in CAIXA if prot in x['Subject']]
checa(any(x['To'] == 'maria@teste.localhost' and codigo in x.get_content() for x in ms), 'e-mail de registro ao cidadão com protocolo e código')
checa(any(x['To'] == 'equipe@pmbora.localhost' and 'Maria' not in x.get_content() and 'maria@' not in x.get_content() for x in ms), 'aviso à equipe sem dados pessoais')

# ---------- tratamento no painel ----------
pid = p['id']
def acao(c, dados, pid_=None):
    u = f'/admin/atendimento/{pid_ or pid}'
    return c.post(u, data=dict(dados, csrf=tok(c, u)), follow_redirects=True)
t = adm.get('/admin/atendimento').text
checa(prot in t and 'Folha de pagamento' in t, 'pedido na fila do painel')
checa('Maria Teste' in adm.get(f'/admin/atendimento/{pid}').text, 'administrador vê a identificação de pedido comum')
r = acao(adm, {'acao': 'prorrogar', 'justificativa': 'curta'})
checa('justificativa' in msg(r), 'prorrogação exige justificativa')
r = acao(adm, {'acao': 'prorrogar', 'justificativa': 'Levantamento em vários setores.'})
p = A.pega(PM, pid)
checa(p['situacao'] == 'prorrogado' and p['prazo'] == A.limite(A.limite(p['recebido'], 20), 10), 'prorrogado por 10 dias')
checa('única prorrogação' in msg(acao(adm, {'acao': 'prorrogar', 'justificativa': 'De novo, por favor.'})), 'só uma prorrogação')
r = acao(adm, {'acao': 'complemento', 'complemento': 'Informe se quer servidores efetivos ou todos.'})
p = A.pega(PM, pid)
checa(p['situacao'] == 'complementacao' and 'suspenso' in A.prazo_info(p, PM)[0], 'complemento pedido: prazo suspenso')
checa('Aguardando o complemento' in msg(acao(adm, {'acao': 'responder', 'decisao': 'concedido', 'resposta': 'Segue.'})), 'não responde enquanto espera o complemento')
r = outro.post('/acesso/complemento', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'texto': 'Todos os servidores.'}, follow_redirects=True)
p = A.pega(PM, pid)
checa('Complemento recebido' in msg(r) and p['situacao'] == 'prorrogado' and p['prazo'] >= config.hoje(), 'cidadão complementa e o prazo volta a correr')
checa('fundamento' in msg(acao(adm, {'acao': 'responder', 'decisao': 'negado', 'resposta': 'Não podemos fornecer.'})), 'negativa sem fundamento recusada')
checa('CPF' in msg(acao(adm, {'acao': 'responder', 'decisao': 'concedido', 'resposta': 'Servidor 123.456.789-09 recebe X.'})), 'resposta com CPF recusada')
r = acao(adm, {'acao': 'responder', 'decisao': 'parcial', 'resposta': 'Segue a folha sem os descontos individuais.', 'fundamento': 'LAI, art. 31 (informação pessoal)'})
p = A.pega(PM, pid)
checa(p['situacao'] == 'respondido' and p['decisao'] == 'parcial' and p['respondido_por'], 'respondido com resultado e fundamento')
N.processar(PMo)
checa(any(x['To'] == 'maria@teste.localhost' and 'recurso' in x.get_content() and 'Chefe de Gabinete' in x.get_content() for x in CAIXA if 'Resposta' in x['Subject']), 'e-mail da resposta explica o recurso e quem decide')

# ---------- recurso ----------
t = outro.get(f'/acesso?protocolo={prot}').text
checa('Não concorda com a resposta' in t and 'Chefe de Gabinete' in t, 'portal oferece o recurso de 1ª instância')
r = outro.post('/acesso/recurso', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'texto': 'Os descontos são públicos para agentes políticos.'}, follow_redirects=True)
p = A.pega(PM, pid)
checa('Recurso recebido' in msg(r) and p['situacao'] == 'recurso', 'recurso registrado')
r = acao(adm, {'acao': 'recurso', 'decisao': 'desprovido', 'resposta': 'Mantida a decisão.'})
checa('não pode decidir o recurso' in msg(r), 'quem respondeu não decide o recurso (LAI, art. 15)')
adm.post('/admin/usuarios', data={'csrf': tok(adm, '/admin/usuarios'), 'acao': 'novo', 'nome': 'Autoridade Teste', 'email': 'autoridade@teste.localhost', 'perfil': 'autoridade', 'senha': 'provisoria123'})
adm.post('/admin/usuarios', data={'csrf': tok(adm, '/admin/usuarios'), 'acao': 'novo', 'nome': 'Editor Teste', 'email': 'editor@teste.localhost', 'perfil': 'editor', 'senha': 'provisoria123'})
aut = TestClient(app, base_url='http://pmbora.localhost'); entrar(aut, 'autoridade@teste.localhost', 'provisoria123', 'senhaforte456')
ed = TestClient(app, base_url='http://pmbora.localhost'); entrar(ed, 'editor@teste.localhost', 'provisoria123', 'senhaforte789')
checa(db.um(PM, "SELECT perfil FROM usuarios WHERE email='autoridade@teste.localhost'")['perfil'] == 'autoridade', 'perfil "Autoridade de recurso" criado')
checa(acao(ed, {'acao': 'recurso', 'decisao': 'provido', 'resposta': 'x' * 10}).status_code == 403, 'editor não decide recurso')
r = acao(aut, {'acao': 'recurso', 'decisao': 'desprovido', 'resposta': 'Descontos individuais são informação pessoal.'})
p = A.pega(PM, pid)
checa('Decisão do recurso enviada' in msg(r) and p['situacao'] == 'respondido', 'autoridade decide o recurso')
checa(A.pode_recorrer(PM, p) and A.pode_recorrer(PM, p)[0] == 2, 'cabe 2ª instância (configurada)')
checa('2ª instância' in outro.get(f'/acesso?protocolo={prot}').text, 'portal oferece a 2ª instância')
r = outro.post('/acesso/recurso', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'texto': 'Recorro à 2ª instância, por favor.'}, follow_redirects=True)
checa('não pode decidir' in msg(acao(aut, {'acao': 'recurso', 'decisao': 'provido', 'resposta': 'Revisto.'})), 'quem decidiu a 1ª instância não decide a 2ª')
r = acao(adm, {'acao': 'recurso', 'decisao': 'nao_conhecido', 'resposta': 'Sem fato novo.'})
checa('Quem respondeu' in msg(r), 'nem quem respondeu (administrador) decide a 2ª')
db.exe(PM, "UPDATE esic SET respondido_por='outra pessoa' WHERE id=%s", (pid,))
r = acao(adm, {'acao': 'recurso', 'decisao': 'parcial', 'resposta': 'Liberados os descontos dos agentes políticos.'})
p = A.pega(PM, pid)
checa(p['situacao'] == 'respondido' and p['decisao'] == 'parcial' and not A.pode_recorrer(PM, p), '2ª instância decidida; não cabe outra')
t = outro.get(f'/acesso?protocolo={prot}').text
checa('Recurso de 1ª instância' in t and 'Recurso de 2ª instância' in t and 'Liberados os descontos' in t, 'portal mostra os dois recursos e as decisões')
r = outro.post('/acesso/avaliar', data={'csrf': tok(outro, f'/acesso?protocolo={prot}'), 'protocolo': prot, 'nota': '4', 'resolveu': 'sim'}, follow_redirects=True)
checa('Obrigado' in msg(r) and A.pega(PM, pid)['avaliacao'] == 4, 'avaliação do cidadão')

# ---------- ouvidoria: identidade protegida e denúncia anônima ----------
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Denúncia', 'assunto': 'Obra parada', 'texto': 'Obra parada há meses.', 'nome': 'José Sigilo', 'email': 'jose@teste.localhost'}, follow_redirects=True)
d1 = db.um(PM, "SELECT * FROM esic WHERE assunto='Obra parada'")
checa(d1 and d1['prazo'] == A.limite(config.hoje(), 30) and A.identidade_restrita(d1), 'denúncia: prazo de 30 dias e identidade restrita')
t = adm.get(f"/admin/atendimento/{d1['id']}").text
checa('José Sigilo' not in t and 'Mostrar identificação' in t, 'denúncia: identificação escondida até o clique')
checa('José Sigilo' not in ed.get(f"/admin/atendimento/{d1['id']}").text and 'Mostrar identificação' not in ed.get(f"/admin/atendimento/{d1['id']}").text, 'editor não tem como ver a identificação')
acao(adm, {'acao': 'identidade'}, d1['id'])
checa('José Sigilo' in adm.get(f"/admin/atendimento/{d1['id']}").text and db.um(PM, "SELECT 1 FROM esic_historico WHERE esic_id=%s AND evento='identidade' AND NOT publico", (d1['id'],)), 'identificação mostrada com registro (interno)')
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Denúncia', 'assunto': 'Anônima', 'texto': 'Irregularidade sem identificação.', 'anonimo': '1', 'nome': 'Ignorado', 'email': 'ignorado@teste.localhost'}, follow_redirects=True)
an = db.um(PM, "SELECT * FROM esic WHERE assunto='Anônima'")
checa(an and an['anonimo'] and an['nome'] == '' and an['email'] == '' and 'Código de acesso' in r.text, 'denúncia anônima: nada de nome e e-mail, mas com código')
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Reclamação', 'assunto': 'Sem nome', 'texto': 'x' * 20, 'anonimo': '1'}, follow_redirects=True)
checa('nome' in msg(r) and not db.um(PM, "SELECT 1 FROM esic WHERE assunto='Sem nome'"), 'anonimato só vale para denúncia')

# ---------- encaminhamento Prefeitura → Câmara (mesma instalação) ----------
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Reclamação', 'assunto': 'Sessões sem áudio', 'texto': 'As sessões da Câmara estão sem áudio.', 'nome': 'Ana Teste', 'email': 'ana@teste.localhost'}, follow_redirects=True)
e1 = db.um(PM, "SELECT * FROM esic WHERE assunto='Sessões sem áudio'")
t = adm.get(f"/admin/atendimento/{e1['id']}").text
checa('Encaminhar ao órgão' in t and 'Câmara Municipal' in t, 'painel oferece a Câmara como destino')
r = acao(adm, {'acao': 'encaminhar_orgao', 'destino_id': str(CMo['id']), 'com_identificacao': '1'}, e1['id'])
e1 = A.pega(PM, e1['id'])
c1 = db.um(CM, "SELECT * FROM esic WHERE origem_orgao='pm-bora' AND protocolo_origem=%s", (e1['protocolo'],))
checa('Encaminhado' in msg(r) and e1['situacao'] == 'encaminhado' and c1 and c1['protocolo'] == e1['protocolo_destino'] and c1['email'] == 'ana@teste.localhost', 'encaminhado: novo protocolo na Câmara com a identificação')
checa(c1 and c1['canal'] == 'orgao' and c1['prazo'] == A.limite(config.hoje(), 30), 'Câmara registra com prazo próprio')
checa(db.um(db.PLATAFORMA, "SELECT 1 FROM remessas_log WHERE origem='pm-bora' AND destino='cm-bora' AND ok AND acao LIKE 'POST /api/atendimento%%'"), 'chamada registrada no log da integração')
# identidade preservada: vai sem nome e e-mail; a resposta volta e a Prefeitura avisa
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Reclamação', 'assunto': 'Vereador ausente', 'texto': 'Reclamação sobre a Câmara.', 'nome': 'Bia Sigilo', 'email': 'bia@teste.localhost', 'preservar': '1'}, follow_redirects=True)
e2 = db.um(PM, "SELECT * FROM esic WHERE assunto='Vereador ausente'")
acao(adm, {'acao': 'encaminhar_orgao', 'destino_id': str(CMo['id']), 'com_identificacao': '1'}, e2['id'])
e2 = A.pega(PM, e2['id'])
c2 = db.um(CM, "SELECT * FROM esic WHERE protocolo_origem=%s", (e2['protocolo'],))
checa(c2 and c2['email'] == '' and 'Bia' not in c2['nome'] and c2['identidade_preservada'], 'identidade preservada: Câmara recebe sem nome e e-mail')
A.responder(CMo, c2, 'Encaminhamos à Mesa Diretora.', '', '', 'Ouvidoria da Câmara')
CAIXA.clear()
r = acao(adm, {'acao': 'atualizar_encaminhamento'}, e2['id'])
N.processar(PMo)
checa('Respondido' in msg(r) and db.um(PM, "SELECT 1 FROM esic_historico WHERE esic_id=%s AND evento='retorno' AND texto LIKE '%%Mesa Diretora%%'", (e2['id'],)), 'resposta da Câmara volta para a Prefeitura')
checa(any(x['To'] == 'bia@teste.localhost' and 'Mesa Diretora' in x.get_content() for x in CAIXA), 'Prefeitura avisa o cidadão com identidade preservada')
acao(adm, {'acao': 'atualizar_encaminhamento'}, e2['id'])
checa(db.um(PM, "SELECT count(*) n FROM esic_historico WHERE esic_id=%s AND evento='retorno'", (e2['id'],))['n'] == 1, 'retorno não se repete')
ruim = TestClient(app, base_url='http://cmbora.localhost').post('/api/atendimento/encaminhamentos', content=b'{}', headers={'X-Portal-Origem': 'pm-bora', 'X-Portal-Momento': '1', 'X-Portal-Assinatura': 'x'})
checa(ruim.status_code == 401, 'encaminhamento sem assinatura válida: 401')

# ---------- relatórios públicos ----------
t = pub.get(f'/e-sic/estatisticas?ano={config.hoje().year}').text
checa('Pedidos recebidos' in t and 'Acesso parcialmente concedido' in t and 'Recursos apresentados' in t and 'Base legal' in t, 'relatório estatístico do e-SIC')
cs = pub.get(f'/e-sic/estatisticas.csv?ano={config.hoje().year}')
js = pub.get(f'/e-sic/estatisticas.json?ano={config.hoje().year}').json()
checa(cs.status_code == 200 and 'Pedidos recebidos;1' in cs.text and js['ano'] == config.hoje().year and 'Maria' not in cs.text, 'estatísticas em CSV e JSON, sem dados pessoais')
adm.post('/admin/atendimento-relatorio', data={'csrf': tok(adm, '/admin/atendimento-relatorio'), 'ano': str(config.hoje().year), 'analise': 'Obras paradas.', 'providencias': 'Cronograma publicado.', 'acao': 'publicar'})
t = pub.get(f'/ouvidoria/relatorio?ano={config.hoje().year}').text
checa('Cronograma publicado' in t and 'Denúncia' in t and 'Manifestações recebidas' in t, 'relatório anual da Ouvidoria (Lei 13.460, art. 15)')
t = pub.get('/e-sic/informacoes-classificadas').text
checa('Não há informação classificada' in t, 'rol de classificadas: declara que não há')
hoje = config.hoje()
r = adm.post('/admin/atendimento-classificadas', data={'csrf': tok(adm, '/admin/atendimento-classificadas'), 'acao': 'nova', 'assunto': 'Plano de segurança', 'grau': 'reservado', 'fundamento': 'LAI, art. 23, VII',
             'classificada_em': hoje.isoformat(), 'prazo_ate': (hoje + timedelta(days=365 * 8)).isoformat()}, follow_redirects=True)
checa('no máximo 5 anos' in msg(r), 'grau reservado: no máximo 5 anos')
adm.post('/admin/atendimento-classificadas', data={'csrf': tok(adm, '/admin/atendimento-classificadas'), 'acao': 'nova', 'assunto': 'Plano de segurança', 'grau': 'reservado', 'fundamento': 'LAI, art. 23, VII',
         'classificada_em': hoje.isoformat(), 'prazo_ate': (hoje + timedelta(days=365 * 4)).isoformat()})
checa('Plano de segurança' in pub.get('/e-sic/informacoes-classificadas').text, 'classificada aparece no rol público')

# ---------- fila de e-mail: sem configuração, a mensagem espera sem gastar tentativa ----------
N.apagar_smtp(PM)
CAIXA.clear()
N.enfileirar(PM, 'x@teste.localhost', 'teste', 'teste', 'fila')
antes = config.PAPEL; config.PAPEL = 'no'  # sem SMTP do órgão e sem gestão (nó separado)
N.processar(PMo)
config.PAPEL = antes
f = db.um(PM, "SELECT * FROM notificacoes WHERE ref='fila'")
checa(f['enviado_em'] is None and f['tentativas'] == 0 and 'aguardando configuração' in f['erro'] and not CAIXA, 'nó sem e-mail configurado: mensagem espera na fila')

# ---------- rotina diária: complemento vencido encerra ----------
r = pub.post('/acesso', data={'csrf': tok(pub, '/e-sic'), 'tipo': 'pedido', 'assunto': 'Pedido vago', 'texto': 'Quero tudo.', 'nome': 'Carlos', 'email': 'carlos@teste.localhost'}, follow_redirects=True)
pv = db.um(PM, "SELECT * FROM esic WHERE assunto='Pedido vago'")
A.pedir_complemento(PMo, pv, 'Especifique o período e o assunto.', 'equipe')
checa(A.rotina(PMo, hoje + timedelta(days=40)) == 1 and A.pega(PM, pv['id'])['situacao'] == 'encerrado', 'complemento não enviado no prazo: encerrado')

# ======================================================================================================
# Parte 2: Prefeitura e Câmara em INSTALAÇÕES SEPARADAS (nó A e nó B), simuladas no mesmo processo
# ======================================================================================================
imp, chave_pub = L.garantir_chaves()
tok_a, tok_b = L.criar_no('no-a.exemplo.test'), L.criar_no('no-b.exemplo.test')
NA = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-a.exemplo.test'"); NB = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-b.exemplo.test'")
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (NA['id'], PMo['id']))
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (NB['id'], CMo['id']))
for b_ in ('no_local_a', 'no_local_b'):
    provision.criar_banco(b_); provision.aplicar(b_, provision.MIG_LOCAL)
NOS = {'A': {'local': 'no_local_a', 'nome': NA['nome'], 'no': NA}, 'B': {'local': 'no_local_b', 'nome': NB['nome'], 'no': NB}}
atual = {'n': None}

def gestao():
    config.PAPEL = 'tudo'; db.LOCAL = db.PLATAFORMA; os.environ.pop('NO_NOME', None)
    web.limpar_cache(); L._memo.clear(); I.limpar_cache(); atual['n'] = None

def no(k):
    config.PAPEL = 'no'; db.LOCAL = NOS[k]['local']; os.environ['NO_NOME'] = NOS[k]['nome']; config.LICENCA_CHAVE_PUBLICA = chave_pub
    web.limpar_cache(); L._memo.clear(); I.limpar_cache(); atual['n'] = k

def puxar(k):
    gestao(); pac = L.entregar(NOS[k]['no']); no(k)
    L.guardar(pac['licencas'], chave_pub)
    return pac, I.guardar_diretorio(pac['diretorio'], chave_pub)

ONDE = {'pmbora.localhost': 'A', 'cmbora.localhost': 'B'}
class ClienteOutroNo:
    """Faz o papel da internet: a chamada HTTPS para o domínio do parceiro é atendida pela instalação dele."""
    def __init__(self, dominio):
        self.dominio = dominio
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def request(self, metodo, caminho, content=None, headers=None):
        volta = atual['n']; no(ONDE[self.dominio])
        try:
            return TestClient(app, base_url=f'https://{self.dominio}').request(metodo, caminho, content=content, headers=headers)
        finally:
            no(volta)
    def get(self, caminho, **kw):
        return self.request('GET', caminho, headers=kw.get('headers'))
I.cliente_remoto = ClienteOutroNo

# gestão monta o diretório de cada nó
gestao()
pa = L.entregar(NA)
da = L.verificar(pa['diretorio'], chave_pub)
checa(da and da['no'] == NA['nome'] and [x['slug'] for x in da['parceiros']] == ['cm-bora'] and da['parceiros'][0]['hospedagem'] == NB['nome'], 'diretório do nó A: a Câmara, hospedada no nó B')
checa(all(PMo['id'] in (x['origem_id'], x['destino_id']) for x in da['pares']) and len(da['pares']) == 2, 'diretório do nó A: só os tokens dos pares da Prefeitura')
checa('banco' not in da['parceiros'][0] and 'Ana' not in str(da) and 'email' not in str(da['parceiros']), 'diretório sem banco e sem dado pessoal')
mexido = copy.deepcopy(pa['diretorio']); mexido['doc']['parceiros'][0]['dominio'] = 'atacante.exemplo.test'
no('A')
checa('RECUSADO' in I.guardar_diretorio(mexido, chave_pub) and not db.um('no_local_a', 'SELECT 1 FROM orgaos_parceiros'), 'diretório adulterado: recusado')
gestao(); pb = L.entregar(NB); no('A')
checa(I.guardar_diretorio(pb['diretorio'], chave_pub) == '' and not db.um('no_local_a', 'SELECT 1 FROM orgaos_parceiros'), 'diretório de outro nó: ignorado')
_, ra = puxar('A'); _, rb = puxar('B')
checa(ra.startswith('diretório: 1 parceiro') and rb.startswith('diretório: 1 parceiro'), f'nós guardam o diretório ({ra} | {rb})')

# nó A: Prefeitura local, Câmara remota
no('A')
cm_a = I.parceiro(slug='cm-bora')
checa(cm_a and not I.e_local(cm_a) and 'ouv' in cm_a['servicos'] and I.par(PMo, cm_a), 'no nó A a Câmara é parceira de outra instalação, com par ativo')
checa('cmbora.localhost' in TestClient(app, base_url='http://pmbora.localhost').get('/').text, 'portal da Prefeitura (nó A) mostra o link da Câmara (nó B)')
ok, txt = I.testar(PMo, cm_a)
checa(ok and 'serviços' in txt, f'teste de conversa A → B ({txt})')
checa(db.um('no_local_a', "SELECT 1 FROM remessas_log WHERE acao='GET /api/integracao/ping' AND ok") and db.um('no_local_b', "SELECT 1 FROM remessas_log WHERE acao='ping recebido'"), 'cada nó registra a sua ponta da conversa')

# encaminhamento A → B
pa_ = TestClient(app, base_url='http://pmbora.localhost')
pa_.post('/acesso', data={'csrf': tok(pa_, '/e-sic'), 'tipo': 'pedido', 'assunto': 'Gastos da Câmara', 'texto': 'Quanto a Câmara gastou com diárias?', 'nome': 'Rui Teste', 'email': 'rui@teste.localhost'}, follow_redirects=True)
x = db.um(PM, "SELECT * FROM esic WHERE assunto='Gastos da Câmara'")
res = A.encaminhar_orgao(PMo, x, CMo['id'], 'SIC da Prefeitura')
cx = db.um(CM, 'SELECT * FROM esic WHERE protocolo=%s', (res['protocolo'],))
checa(cx and cx['origem_orgao'] == 'pm-bora' and cx['tipo'] == 'pedido' and cx['email'] == 'rui@teste.localhost', 'pedido encaminhado do nó A chega à Câmara no nó B')
checa(A.pega(PM, x['id'])['decisao'] == 'encaminhado', 'estatística da Prefeitura conta como encaminhado')
no('B'); A.responder(CMo, cx, 'Diárias: R$ 1.000,00 em 2026.', 'concedido', '', 'SIC da Câmara'); no('A')
s = A.atualizar_encaminhamento(PMo, A.pega(PM, x['id']))
checa(s['situacao'] == 'respondido' and 'Diárias' in s['resposta'], 'nó A consulta a situação no nó B')

# remessa ao Diário: Câmara (nó B) → Prefeitura (nó A)
no('B')
dest = RM.destino_do(CMo)
checa(dest and dest['slug'] == 'pm-bora' and not I.e_local(dest), 'no nó B o Diário de destino é a Prefeitura do nó A')
rid = RM.enviar(CMo, 'Mesa', 'Ato da Mesa', '9/2026', 'Ato da Mesa fictício entre nós', 'Art. 1º Texto fictício enviado entre instalações.')
checa(db.um(PM, "SELECT 1 FROM diario_atos WHERE remessa_externa=%s AND caderno='legislativo'", (f'cm-bora:{rid}',)), 'remessa ao Diário atravessa as instalações')
t = TestClient(app, base_url='http://cmbora.localhost').get('/legislacao').text
checa('Legislação' in t and 'não foi possível' not in t.lower(), 'Câmara (nó B) lê a legislação pública da Prefeitura (nó A)')

# troca de chaves na gestão: até o nó B buscar, a conversa B → A é recusada; depois volta
gestao(); I.renovar_par(PMo['id'], CMo['id'])
puxar('A')
no('B')
ok, txt = I.testar(CMo, I.parceiro(slug='pm-bora'))
checa(not ok and '401' in txt, 'chave antiga no nó B: recusada pela Prefeitura')
puxar('B')
ok, txt = I.testar(CMo, I.parceiro(slug='pm-bora'))
checa(ok, f'depois de buscar o diretório, B → A volta a conversar ({txt})')
# desligar a integração no console tira o par dos dois nós
gestao(); I.ligar_par(PMo['id'], CMo['id'], False); puxar('A'); puxar('B')
no('B')
checa(RM.destino_do(CMo) is None, 'integração desligada: sem destino')
gestao(); I.ligar_par(PMo['id'], CMo['id'], True)

# diretório antigo não vale
gestao(); pv_ = L.entregar(NB)
velho = L.assinar(dict(L.verificar(pv_['diretorio'], chave_pub), emitido_em=(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()))
no('B')
checa(I.guardar_diretorio(velho, chave_pub) == 'diretório ignorado (antigo)', 'diretório antigo: ignorado')

# de volta ao papel "tudo"
gestao()
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=NULL WHERE id IN (%s,%s)', (PMo['id'], CMo['id']))
I.cliente_local = I.cliente_local_original
if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('atendimento e integração: tudo ok')
