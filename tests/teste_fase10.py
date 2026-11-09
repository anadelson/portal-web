# Fase 10: Carta de Serviços — rascunho → validação → devolução → nova validação → autorização → publicação; publicação bloqueada sem autorização;
# escopo por secretaria; designação por ato; alerta de revisão vencida; busca por sinônimo; avaliação por serviço; exportações; importação; Câmara.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_fase10.py
import os, re, sys, json
from datetime import timedelta
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, carta as CT
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

def cli(host='pmbora.localhost', ip='203.0.113.20'):
    return TestClient(app, base_url=f'http://{host}', headers={'x-forwarded-for': ip})
erros = []
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text) or (sem and sem in r.text):
        erros.append(f'{nome}: {r.status_code} {r.text[:300]}')
    return r
def checa(cond, nome):
    if not cond:
        erros.append(nome)
PM = 'bd_pm_bora'
adm = cli()
ok(entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123'), txt='Visão geral', nome='login admin')

# ---------- pessoas de TESTE (fictícias) ----------
for email, nome, perfil in [('red@teste.localhost', 'Redatora Teste', 'redator'), ('resp@teste.localhost', 'Responsável Teste', 'validador'),
                            ('dtic@teste.localhost', 'DTIC Teste', 'publicador'), ('desig@teste.localhost', 'Designado Teste', 'editor'),
                            ('outro@teste.localhost', 'Validador Outra Secretaria', 'validador')]:
    adm.post('/admin/usuarios', data={'csrf': tok(adm, '/admin/usuarios'), 'acao': 'novo', 'nome': nome, 'email': email, 'perfil': perfil, 'senha': 'provisoria123'})
U = {x['email'].split('@')[0]: x['id'] for x in db.todos(PM, "SELECT id, email FROM usuarios WHERE email LIKE '%%@teste.localhost'")}
checa(len(U) == 5, f'usuários de teste criados: {U}')
ok(adm.get('/admin/carta'), txt='Nenhuma secretaria cadastrada', nome='aviso sem secretarias')
S = '/admin/carta-secretarias'
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'secretaria', 'nome': 'Secretaria de Teste A', 'sigla': 'STA', 'responsavel_id': U['resp']})
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'secretaria', 'nome': 'Secretaria de Teste B', 'sigla': 'STB', 'responsavel_id': U['outro']})
SA = db.um(PM, "SELECT id FROM secretarias WHERE sigla='STA'")['id']
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'redator', 'secretaria_id': SA, 'usuario_id': U['red']})
adm.post(S, data={'csrf': tok(adm, S), 'acao': 'designar', 'secretaria_id': SA, 'usuario_id': U['desig'], 'ato_tipo': 'Portaria', 'ato_numero': '99/2026', 'ato_data': '2026-11-01'})
checa(db.um(PM, 'SELECT perfil, secretaria_id FROM usuarios WHERE id=%s', (U['desig'],)) == {'perfil': 'validador', 'secretaria_id': SA}, 'designado vira validador da secretaria')
ok(adm.get(S), txt='Portaria nº 99/2026', nome='designação aparece com o ato')

red, resp, dtic, desig, outro = cli(ip='203.0.113.21'), cli(ip='203.0.113.22'), cli(ip='203.0.113.23'), cli(ip='203.0.113.24'), cli(ip='203.0.113.25')
for c, e in ((red, 'red'), (resp, 'resp'), (dtic, 'dtic'), (desig, 'desig'), (outro, 'outro')):
    ok(entrar(c, f'{e}@teste.localhost', 'provisoria123', 'senhanova12345'), txt='Visão geral', nome=f'login {e}')

# ---------- ficha incompleta não vai para validação ----------
COMPLETA = {'nome': 'Emitir segunda via de teste', 'descricao': 'Gera a segunda via do documento de teste. Serviço fictício para teste automatizado.',
            'categoria': 'Tributos e taxas', 'publicos': ['cidadao'], 'requisitos': 'Ser o responsável pelo imóvel de teste.', 'documentos': 'Número da inscrição de teste.',
            'etapas': 'Acessar o sistema\nInformar a inscrição\nImprimir', 'prazo': 'Na hora', 'formas': ['online', 'presencial'], 'locais': 'Setor de teste, seg a sex, 8h–17h.',
            'custo': 'Gratuito', 'prioridades': 'Atendimento prioritário conforme a Lei 10.048/2000.', 'tempo_espera': 'Até 20 minutos no balcão.',
            'comunicacao': 'Por e-mail e telefone do setor.', 'manifestacoes': 'Pela Ouvidoria do portal.', 'acompanhamento': 'Pelo número do protocolo.',
            'sinonimos': 'boleto, carnê, guia', 'link_online': 'https://exemplo.invalid/segunda-via'}
r = red.post('/admin/carta/salvar', data={'csrf': tok(red, '/admin/carta/novo'), 'acao': 'enviar', 'nome': 'Emitir segunda via de teste', 'descricao': 'x'}, follow_redirects=True)
checa('faltam campos obrigatórios' in r.text, 'ficha incompleta não é enviada para validação')
sid = db.um(PM, "SELECT id FROM servicos WHERE nome='Emitir segunda via de teste'")['id']
s = db.um(PM, 'SELECT * FROM servicos WHERE id=%s', (sid,))
checa(s['situacao'] == 'rascunho' and s['secretaria_id'] == SA, 'rascunho na secretaria do redator')
def enviar(c, dados, acao='enviar'):
    d = {'csrf': tok(c, f'/admin/carta/{sid}'), 'acao': acao, 'id': sid}
    d.update(dados)
    return c.post('/admin/carta/salvar', data=d, follow_redirects=True)
# aviso de linguagem (não bloqueia)
r = enviar(red, dict(COMPLETA, descricao='Mediante requerimento o contribuinte poderá obter a segunda via do documento de arrecadação municipal referente ao imposto conforme as normas vigentes e respeitados os procedimentos administrativos estabelecidos pela SEFAZ do município de teste.'), 'rascunho')
r = ok(red.get(f'/admin/carta/{sid}'), txt='Sugestões de linguagem simples', nome='avisos de linguagem')
checa('palavras' in r.text and '“SEFAZ”' in r.text and '“mediante”' in r.text, 'avisos: frase longa, sigla e termo difícil')
r = enviar(red, COMPLETA)
checa(db.um(PM, 'SELECT situacao FROM servicos WHERE id=%s', (sid,))['situacao'] == 'em_validacao', 'ficha completa vai para validação')

# ---------- publicação bloqueada sem autorização ----------
r = dtic.post('/admin/carta/salvar', data={'csrf': tok(dtic, f'/admin/carta/{sid}'), 'acao': 'publicar', 'id': sid}, follow_redirects=True)
checa('Não publicado' in r.text and not db.um(PM, 'SELECT publicado_dados FROM servicos WHERE id=%s', (sid,))['publicado_dados'], 'publicação recusada sem autorização')
try:
    CT.publicar(PM, db.um(PM, 'SELECT * FROM servicos WHERE id=%s', (sid,)), 'teste'); checa(False, 'CT.publicar deveria recusar sem autorização')
except ValueError:
    pass
# outra secretaria não vê nem valida
ok(outro.get(f'/admin/carta/{sid}'), 404, nome='validador de outra secretaria não vê a ficha')
r = outro.post('/admin/carta/salvar', data={'csrf': tok(outro, '/admin/carta/novo'), 'acao': 'autorizar', 'id': sid})
checa(r.status_code == 403 and db.um(PM, 'SELECT situacao FROM servicos WHERE id=%s', (sid,))['situacao'] == 'em_validacao', 'outra secretaria não autoriza')
# administrador sem ser responsável não autoriza
r = adm.post('/admin/carta/salvar', data={'csrf': tok(adm, f'/admin/carta/{sid}'), 'acao': 'autorizar', 'id': sid}, follow_redirects=True)
checa('Só o responsável' in r.text, 'administrador que não é responsável não autoriza')

# ---------- devolução com comentário ----------
r = resp.post('/admin/carta/salvar', data={'csrf': tok(resp, f'/admin/carta/{sid}'), 'acao': 'devolver', 'id': sid, 'comentario': ''}, follow_redirects=True)
checa('escreva o comentário' in r.text, 'devolver exige comentário')
resp.post('/admin/carta/salvar', data={'csrf': tok(resp, f'/admin/carta/{sid}'), 'acao': 'devolver', 'id': sid, 'comentario': 'Explique melhor o prazo.'})
checa(db.um(PM, 'SELECT situacao, comentario FROM servicos WHERE id=%s', (sid,)) == {'situacao': 'devolvido', 'comentario': 'Explique melhor o prazo.'}, 'ficha devolvida com o comentário')
ok(red.get(f'/admin/carta/{sid}'), txt='Explique melhor o prazo.', nome='redator vê o comentário')
enviar(red, dict(COMPLETA, prazo='Na hora, pela internet; no balcão, no mesmo dia.'))
checa(db.um(PM, 'SELECT situacao FROM servicos WHERE id=%s', (sid,))['situacao'] == 'em_validacao', 'nova validação depois da devolução')

# ---------- autorização pelo responsável; mudança depois da autorização volta para validação ----------
resp.post('/admin/carta/salvar', data={'csrf': tok(resp, f'/admin/carta/{sid}'), 'acao': 'autorizar', 'id': sid})
s = db.um(PM, 'SELECT * FROM servicos WHERE id=%s', (sid,))
checa(s['situacao'] == 'autorizado' and s['autorizado_por'] == 'Responsável Teste' and 'responsável' in s['autorizado_ato'], 'autorizado pelo responsável')
enviar(red, dict(COMPLETA, prazo='Até 2 dias úteis.', descricao=COMPLETA['descricao']), 'rascunho')
checa(db.um(PM, 'SELECT situacao FROM servicos WHERE id=%s', (sid,))['situacao'] == 'rascunho', 'mudança de conteúdo depois de autorizada volta a rascunho')
r = dtic.post('/admin/carta/salvar', data={'csrf': tok(dtic, f'/admin/carta/{sid}'), 'acao': 'publicar', 'id': sid}, follow_redirects=True)
checa('Não publicado' in r.text, 'conteúdo mudado depois da autorização não publica')
enviar(red, dict(COMPLETA, prazo='Até 2 dias úteis.'))
# designado autoriza (ato registrado)
desig.post('/admin/carta/salvar', data={'csrf': tok(desig, f'/admin/carta/{sid}'), 'acao': 'autorizar', 'id': sid})
s = db.um(PM, 'SELECT * FROM servicos WHERE id=%s', (sid,))
checa(s['situacao'] == 'autorizado' and 'Portaria nº 99/2026' in s['autorizado_ato'], f"designado autoriza com o ato registrado: {s['autorizado_ato']}")
# ---------- DTIC organiza e publica ----------
dtic.post('/admin/carta/salvar', data={'csrf': tok(dtic, f'/admin/carta/{sid}'), 'acao': 'organizar', 'id': sid, 'categoria': 'Tributos e taxas', 'sinonimos': 'boleto, carnê, guia, papelzinho', 'ordem': '10'})
checa(db.um(PM, 'SELECT situacao FROM servicos WHERE id=%s', (sid,))['situacao'] == 'autorizado', 'organizar (categoria/sinônimos) não invalida a autorização')
r = dtic.post('/admin/carta/salvar', data={'csrf': tok(dtic, f'/admin/carta/{sid}'), 'acao': 'publicar', 'id': sid}, follow_redirects=True)
s = db.um(PM, 'SELECT * FROM servicos WHERE id=%s', (sid,))
checa(s['situacao'] == 'publicado' and s['publicado_dados'] and s['revisar_em'] and (s['revisar_em'] - config.hoje()).days >= 350, f'publicado com revisão em ~12 meses: {s["revisar_em"]}')
checa(db.um(PM, "SELECT count(*) n FROM servico_versoes WHERE servico_id=%s", (sid,))['n'] >= 6, 'histórico de versões')
checa(db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Carta: publicação RECUSADA%%'") and db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE '%%AUTORIZADA por%%'"), 'auditoria de recusa e autorização')

# ---------- portal ----------
pub = cli(ip='198.51.100.30')
r = ok(pub.get('/servicos'), txt='Emitir segunda via de teste', nome='/servicos lista a ficha publicada')
checa('Base legal:' in r.text and 'Lei 13.460' in r.text, '/servicos com base legal')
checa('Vacinação contra a gripe' not in r.text, 'conteúdos-exemplo antigos fora da lista')
ok(pub.get('/servicos?q=papelzinho'), txt='Emitir segunda via de teste', nome='busca por sinônimo')
ok(pub.get('/servicos?q=boleto'), txt='Emitir segunda via de teste', nome='busca por sinônimo (2)')
ok(pub.get('/servicos?q=matricula'), txt='0 serviço(s)', nome='busca sem resultado')
ok(pub.get('/servicos?categoria=Tributos e taxas&publico=cidadao'), txt='Emitir segunda via de teste', nome='filtros')
ok(pub.get('/servicos?letra=E'), txt='Emitir segunda via de teste', nome='lista A–Z')
slug = s['slug']
r = ok(pub.get(f'/servicos/{slug}'), txt='Solicitar online', nome='ficha pública')
for sec in ('Quem pode pedir', 'Documentos e informações', 'Etapas', 'Prazo', 'Custo', 'Onde e quando', 'Prioridades', 'Como acompanhar', 'Reclamações, sugestões e elogios', 'Avalie este serviço'):
    checa(sec in r.text, f'ficha pública: seção {sec}')
checa('Até 2 dias úteis.' in r.text, 'ficha pública mostra a versão autorizada')
# edição de ficha no ar não muda o público até nova publicação
enviar(red, dict(COMPLETA, nome='Nome alterado sem validação'), 'rascunho')
checa('Nome alterado sem validação' not in pub.get(f'/servicos/{slug}').text and 'Emitir segunda via de teste' in pub.get('/servicos').text, 'o que está no ar não muda sem nova validação')
enviar(red, dict(COMPLETA, prazo='Até 2 dias úteis.'), 'rascunho')
# ---------- avaliação por serviço ----------
t = re.search(r'name="csrf" value="([^"]+)"', pub.get(f'/servicos/{slug}').text).group(1)
r = pub.post(f'/servicos/{slug}/avaliar', data={'csrf': t, 'nota': '9'}, headers={'Accept': 'application/json'})
checa(r.status_code == 400, 'nota fora de 1–5 recusada')
r = pub.post(f'/servicos/{slug}/avaliar', data={'csrf': t, 'nota': '4', 'conseguiu': 'sim', 'comentario': 'Comentário de teste'}, headers={'Accept': 'application/json'})
checa(r.status_code == 200 and r.json()['ok'], 'avaliação registrada')
r = pub.post(f'/servicos/{slug}/avaliar', data={'csrf': t, 'nota': '1'}, headers={'Accept': 'application/json'})
checa(not r.json()['ok'], 'segunda avaliação do mesmo navegador recusada')
checa(db.um(PM, 'SELECT count(*) n, max(nota) m FROM servico_avaliacoes WHERE servico_id=%s', (sid,)) == {'n': 1, 'm': 4}, 'só uma avaliação gravada')
ok(adm.get('/admin/carta-monitoramento'), txt='Comentário de teste', nome='monitoramento com avaliação e comentário para moderar')
# ---------- manifestação ligada ao serviço ----------
ok(pub.get(f'/ouvidoria?servico={slug}'), txt='Sobre qual serviço?', nome='ouvidoria oferece o serviço')
r = pub.post('/acesso', data={'csrf': tok(pub, '/ouvidoria'), 'tipo': 'manifestacao', 'categoria': 'Sugestão', 'assunto': 'Teste', 'texto': 'Manifestação de teste.', 'nome': 'Pessoa Teste', 'email': 'p@teste.localhost', 'servico_id': sid}, follow_redirects=True)
checa(db.um(PM, 'SELECT 1 FROM esic WHERE servico_id=%s', (sid,)), 'manifestação vinculada ao serviço')
r = ok(adm.get('/admin/carta-monitoramento'), nome='monitoramento')
checa(re.search(r'Emitir segunda via de teste</td><td>1</td>', r.text), 'manifestação conta no monitoramento')
# ---------- revisão vencida ----------
db.exe(PM, 'UPDATE servicos SET revisar_em=%s WHERE id=%s', (config.hoje() - timedelta(days=1), sid))
ok(red.get('/admin/carta'), txt='Revisão vencida', nome='alerta de revisão vencida para o redator')
ok(resp.get('/admin/carta?aba=revisar'), txt='Emitir segunda via de teste', nome='aba A revisar')
ok(pub.get(f'/servicos/{slug}'), txt='em revisão', nome='portal sinaliza ficha em revisão')
# ---------- exportações ----------
j = pub.get('/carta-de-servicos.json').json()
checa(j['base_legal'] and j['gerado_em'] and any(x['nome'] == 'Emitir segunda via de teste' for x in j['servicos']), 'JSON com base legal, data e o serviço')
rc = pub.get('/carta-de-servicos.csv'); checa(rc.status_code == 200 and rc.text.lstrip('﻿').startswith('nome,descricao'), 'CSV')
rp = pub.get('/carta-de-servicos.pdf'); checa(rp.status_code == 200 and rp.content[:4] == b'%PDF' and len(rp.content) > 1500, 'PDF')
# ---------- importação do inventário ----------
cab = ';'.join(CT.COLUNAS_IMPORT)
ruim = (cab + '\nSecretaria Inexistente;Serviço X;d;Educação;cidadao;r;d;e;p;online;l;Gratuito;;p;t;c;m;a;;;\n').encode()
r = ok(red.post('/admin/carta-importar', data={'csrf': tok(red, '/admin/carta-importar'), 'acao': 'simular'}, files={'arquivo': ('c.csv', ruim, 'text/csv')}), txt='não cadastrada', nome='importação recusa secretaria inexistente')
bom = (cab + '\nSTA;Matrícula de teste;Matrícula fictícia de teste.;Educação;cidadao;r;d;e;10 dias;presencial;l;Gratuito;;p;t;c;m;a;;;matricula, vaga\n').encode()
ok(red.post('/admin/carta-importar', data={'csrf': tok(red, '/admin/carta-importar'), 'acao': 'gravar'}, files={'arquivo': ('c.csv', bom, 'text/csv')}), txt='1 gravadas', nome='importação gera rascunho')
checa(db.um(PM, "SELECT situacao, secretaria_id FROM servicos WHERE nome='Matrícula de teste'") == {'situacao': 'rascunho', 'secretaria_id': SA}, 'importado vira rascunho (não publica)')
checa('Matrícula de teste' not in pub.get('/servicos').text, 'importado não aparece no portal')
outra = (cab + '\nSTB;Serviço da outra;d;Educação;cidadao;r;d;e;p;online;l;Gratuito;;p;t;c;m;a;;;\n').encode()
ok(red.post('/admin/carta-importar', data={'csrf': tok(red, '/admin/carta-importar'), 'acao': 'gravar'}, files={'arquivo': ('c.csv', outra, 'text/csv')}), txt='só pode importar serviços da sua secretaria', nome='redator não importa para outra secretaria')
# ---------- Câmara ----------
ok(cli('cmbora.localhost').get('/servicos'), txt='Carta de Serviços', nome='Câmara tem a Carta')
ok(cli('cmbora.localhost').get('/carta-de-servicos.json'), nome='Câmara exporta a Carta')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('fase 10: tudo ok')
