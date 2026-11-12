# Convite de primeiro acesso por e-mail e e-mail de saída configurado no console (12/11/2026).
# E-mail SIMULADO (nada sai da máquina); domínios e endereços fictícios. Só contra banco de TESTE.
#   PYTHONPATH=. python tests/teste_convite.py
import os, re, sys, smtplib
from datetime import datetime, timedelta, timezone
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from cryptography.fernet import Fernet
from app.main import app
from app import db, config, convites as CV, email_saida as EM
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apoio
from apoio import entrar, tok, primeiro_acesso, link_convite, CAIXA

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
config.CHAVE_CREDENCIAIS = Fernet.generate_key().decode()
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')

# ---------- 1. e-mail de saída no console ----------
t = con.get('/email').text
checa('E-mail de saída' in t and 'name="servidor"' in t and 'disabled' in t, 'tela do e-mail de saída (teste desligado sem configuração)')
checa('E-mail de saída' in con.get('/').text, 'item no menu do console')
def salvar(**k):
    d = {'csrf': tok(con, '/email'), 'acao': 'salvar', 'servidor': 'smtp.exemplo.test', 'porta': '465', 'seguranca': 'ssl', 'usuario': 'envio@exemplo.test',
         'senha': 'senha-smtp-ficticia-123', 'remetente': 'nao-responda@exemplo.test', 'remetente_nome': 'Portais (teste)'}
    d.update(k)
    return con.post('/email', data=d, follow_redirects=True)
checa('Servidor SMTP inválido' in salvar(servidor='x y').text and 'Porta inválida' in salvar(porta='0').text and 'remetente inválido' in salvar(remetente='sem-arroba').text, 'validação dos campos')
checa('Informe a senha do SMTP' in salvar(senha='').text, 'primeira gravação com usuário exige senha')
r = salvar()
cfg = db.um(db.PLATAFORMA, 'SELECT * FROM email_saida')
checa('E-mail de saída gravado' in r.text and cfg['senha_cifrada'].startswith('gAAAA') and 'senha-smtp-ficticia-123' not in cfg['senha_cifrada'], 'senha do SMTP gravada cifrada')
t = con.get('/email').text
checa('senha-smtp-ficticia-123' not in t and 'guardada cifrada' in t, 'senha nunca volta para a tela')
checa(not db.um(db.PLATAFORMA, 'SELECT 1 FROM log_console WHERE acao LIKE %s', ('%senha-smtp-ficticia%',)), 'senha não vai para o registro')
salvar(senha='', remetente_nome='Portais')
checa(db.um(db.PLATAFORMA, 'SELECT senha_cifrada FROM email_saida')['senha_cifrada'] == cfg['senha_cifrada'], 'senha vazia mantém a senha guardada')
# envio de teste: a conexão SMTP é simulada (recebe a senha decifrada e a mensagem)
ENVIOS = []
def smtp_falso(r, senha, msg):
    if FALHA.get('auth'):
        raise smtplib.SMTPAuthenticationError(535, b'auth')
    if FALHA.get('rede'):
        raise OSError('sem rede')
    ENVIOS.append((senha, msg)); CAIXA.append(msg)
FALHA = {}
EM._smtp_enviar = smtp_falso
r = con.post('/email', data={'csrf': tok(con, '/email'), 'acao': 'testar', 'para': 'gestor@exemplo.test'}, follow_redirects=True)
checa('Teste: enviado para gestor@exemplo.test' in r.text and ENVIOS[-1][0] == 'senha-smtp-ficticia-123' and ENVIOS[-1][1]['From'] == 'Portais <nao-responda@exemplo.test>', 'teste usa a senha decifrada e o remetente')
FALHA['auth'] = True
r = con.post('/email', data={'csrf': tok(con, '/email'), 'acao': 'testar', 'para': 'gestor@exemplo.test'}, follow_redirects=True)
checa('recusou o usuário/senha (código 535)' in r.text and 'senha-smtp' not in r.text, 'falha de autenticação explicada, sem segredo')
FALHA.clear()

# ---------- 2. cadastro sem senha na tela; convite espera o domínio ----------
CV.dominio_no_ar = lambda d: NO_AR.get(d, False)
NO_AR = {}
r = con.post('/orgaos/novo', data={'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599961', 'municipio': 'Município Exemplo Convite', 'uf': 'SP',
                                   'dominio': 'pmconvite.localhost', 'email_admin': 'admin@pmconvite.localhost', 'sistema': 'nenhum'})
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmconvite.localhost'")
c1 = db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE orgao_id=%s', (o['id'],))
checa('class="senha"' not in r.text and 'Senha provisória' not in r.text and 'aguardando' in r.text, 'cadastro: nenhuma senha, convite aguardando')
checa(c1['situacao'] == 'aguardando' and 'aguardando o domínio pmconvite.localhost ficar no ar' in c1['mensagem'] and c1['token_cifrado'], 'domínio fora do ar: convite espera (link guardado cifrado)')
checa('aguardando o domínio' in con.get(f"/orgao/{o['id']}").text, 'página do órgão mostra o motivo')
NO_AR['pmconvite.localhost'] = True
FALHA['rede'] = True
CV.tick()
checa(db.um(db.PLATAFORMA, 'SELECT situacao, mensagem FROM convites WHERE id=%s', (c1['id'],)) == {'situacao': 'aguardando', 'mensagem': 'falha no envio, nova tentativa em seguida: sem conexão com o servidor SMTP (OSError)'}, 'falha do SMTP: tenta de novo depois')
FALHA.clear()
checa(CV.tick() == 1, 'domínio no ar: convite sai')
c1 = db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE id=%s', (c1['id'],))
checa(c1['situacao'] == 'enviado' and c1['token_cifrado'] is None, 'enviado e link apagado da gestão')
url = link_convite('admin@pmconvite.localhost')
m = CAIXA[-1]
checa(url and url.startswith('https://pmconvite.localhost/admin/primeiro-acesso?t=') and 'Primeiro acesso ao painel' in m['Subject'] and m.get_body(preferencelist=('html',)), 'e-mail com o link (texto e HTML)')
checa('senha' not in m.get_body(preferencelist=('plain',)).get_content().lower().split('crie a sua senha')[0], 'e-mail não leva senha nenhuma')
token = url.split('t=')[1]

# ---------- 3. primeiro acesso ----------
adm = TestClient(app, base_url='http://pmconvite.localhost')
r = adm.get(f'/admin/primeiro-acesso?t={token}')
checa('admin@pmconvite.localhost' in r.text and 'Criar senha e continuar' in r.text and r.headers.get('cache-control') == 'no-store' and r.headers.get('referrer-policy') == 'no-referrer', 'página de primeiro acesso (sem cache, sem referer)')
checa('inválido, já foi usado ou venceu' in adm.get('/admin/primeiro-acesso?t=errado').text, 'link inválido: explica')
def criar(nova, conf=None, t_=token):
    return adm.post('/admin/primeiro-acesso', data={'csrf': tok(adm, f'/admin/primeiro-acesso?t={t_}'), 't': t_, 'nova': nova, 'conf': conf or nova}, follow_redirects=True)
checa('12 caracteres' in criar('curta').text and '12 caracteres' in criar('senhaLongaUm123', 'outraSenhaLonga1').text, 'senha curta ou diferente: recusada')
checa('menos previsível' in criar('aaaaaaaaaaaaaa').text, 'senha previsível: recusada')
r = criar('senhaDoAdmin2026!')
checa('cadastre o segundo fator' in r.text and 'Chave para digitar' in r.text, 'senha criada: segue para o cadastro do segundo fator')
u = db.um(o['banco'], "SELECT * FROM usuarios WHERE email='admin@pmconvite.localhost'")
checa(u['convite_hash'] is None and not u['totp_ativo'], 'link invalidado; segundo fator ainda por cadastrar')
checa('inválido, já foi usado ou venceu' in adm.get(f'/admin/primeiro-acesso?t={token}').text, 'link usado não vale de novo')
seg = re.search(r'Chave para digitar: <code[^>]*>([A-Z2-7 ]+)</code>', r.text).group(1).replace(' ', '')
from app.security import totp
r = adm.post('/admin/2fa', data={'csrf': tok(adm, '/admin/2fa'), 'codigo': totp(seg)}, follow_redirects=True)
apoio.SEGREDOS['admin@pmconvite.localhost'] = seg
checa('Já guardei' in r.text, 'segundo fator cadastrado, códigos de recuperação mostrados')
checa('Visão geral' in adm.get('/admin/', follow_redirects=True).text, 'administrador dentro do painel')
checa(db.um(o['banco'], "SELECT 1 FROM auditoria WHERE acao LIKE %s", ('Primeiro acesso pelo convite%',)), 'primeiro acesso na auditoria')
t = con.get(f"/orgao/{o['id']}").text
checa('usado (administrador já criou a senha)' in t, 'console mostra o convite como usado')

# ---------- 4. reenviar: link e senha anteriores deixam de valer ----------
r = con.post(f"/orgao/{o['id']}/convite", data={'csrf': tok(con, f"/orgao/{o['id']}"), 'email': 'admin@pmconvite.localhost'}, follow_redirects=True)
checa('Marque a confirmação' in r.text, 'reenviar exige confirmação')
r = con.post(f"/orgao/{o['id']}/convite", data={'csrf': tok(con, f"/orgao/{o['id']}"), 'email': 'admin@pmconvite.localhost', 'confirmo': '1'}, follow_redirects=True)
url2 = link_convite('admin@pmconvite.localhost')
checa('Convite enviado por e-mail' in r.text and url2 and url2 != url, 'novo convite enviado')
fora = TestClient(app, base_url='http://pmconvite.localhost')
checa('Segundo fator' not in fora.post('/admin/login', data={'csrf': tok(fora, '/admin/login'), 'email': 'admin@pmconvite.localhost', 'senha': 'senhaDoAdmin2026!'}, follow_redirects=True).text, 'senha anterior deixou de valer')
# link vencido
db.exe(o['banco'], "UPDATE usuarios SET convite_expira=%s WHERE email='admin@pmconvite.localhost'", (datetime.now(timezone.utc) - timedelta(minutes=1),))
checa('inválido, já foi usado ou venceu' in adm.get('/admin/primeiro-acesso?t=' + url2.split('t=')[1]).text, 'link vencido não vale')
# sem e-mail de saída: convite fica aguardando com o motivo
db.exe(db.PLATAFORMA, 'DELETE FROM email_saida')
r = con.post(f"/orgao/{o['id']}/convite", data={'csrf': tok(con, f"/orgao/{o['id']}"), 'email': 'admin@pmconvite.localhost', 'confirmo': '1'}, follow_redirects=True)
checa('e-mail de saída não configurado' in r.text and 'configure em E-mail de saída' in r.text, 'sem e-mail de saída: o console explica e o convite aguarda')
checa(db.um(db.PLATAFORMA, "SELECT count(*) n FROM convites WHERE orgao_id=%s AND situacao='aguardando'", (o['id'],))['n'] == 1, 'só um convite aguardando (os anteriores são substituídos)')
anon = TestClient(app, base_url='http://gestao.localhost')
checa(anon.post(f"/orgao/{o['id']}/convite", data={'email': 'x@y.z', 'confirmo': '1'}, follow_redirects=False).status_code in (302, 303, 307, 400, 401, 403), 'sem login não reenvia convite')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('convite: tudo ok')
