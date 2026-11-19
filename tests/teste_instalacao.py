# Instalação de nó pelo console (12/11/2026): pacotes de código e de segredos por link de uso único.
# Valores e nomes FICTÍCIOS. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_instalacao.py
import io, os, re, shutil, subprocess, sys, tarfile, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, instalacao as IN
from app.security import totp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apoio
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
# fontes de implantação fictícias (na imagem real ficam em /srv/fonte)
F = Path(tempfile.mkdtemp())
(F / 'deploy' / 'no').mkdir(parents=True)
for n, t in (('Dockerfile', 'FROM exemplo\n'), ('docker-compose.yml', 'services: {}\n'), ('requirements.txt', 'exemplo\n'), ('deploy/no/instalar.sh', '#!/bin/bash\necho instalador\n')):
    (F / n).write_text(t)
IN.FONTE = F

con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
L.criar_no('no-inst.exemplo.test')
n = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-inst.exemplo.test'")
U = f"/nos/{n['id']}/instalar"
checa('Preparar instalação' in con.get('/nos').text, 'link "Preparar instalação" em Nós e licenças')
t = con.get(U).text
checa('Gerar pacotes e comandos' in t and 'name="minha_senha"' in t and 'name="codigo"' in t and 'checked' in t, 'tela pede senha do pacote, senha do gestor e 2FA (token novo marcado para nó que nunca buscou)')
def gerar(**k):
    d = {'csrf': tok(con, U), 'senha_pacote': 'senha-do-pacote-123', 'senha_pacote2': 'senha-do-pacote-123', 'novo_token': '1',
         'minha_senha': 'gestorforte1234', 'codigo': totp(apoio.SEGREDOS['gestor@gestao.localhost'])}
    d.update(k)
    return con.post(U, data={x: y for x, y in d.items() if y is not None}, follow_redirects=True)
checa('12 caracteres' in gerar(senha_pacote='curta', senha_pacote2='curta').text, 'senha do pacote curta: recusada')
checa('Sua senha não confere' in gerar(minha_senha='errada').text, 'senha do gestor errada: nada gerado')
checa('autenticador incorreto' in gerar(codigo='000000').text, '2FA errado: nada gerado')
checa(db.um(db.PLATAFORMA, 'SELECT count(*) n FROM instalacao_links')['n'] == 0, 'recusas não geram link')
tok_antigo_hash = n['token_hash']
r = gerar()
lk = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
checa(r.headers.get('cache-control') == 'no-store' and len(set(lk)) == 2 and 'bash deploy/no/instalar.sh' in r.text, 'comandos com os dois links de uso único')
cod, seg = lk[0], lk[1]
checa('Pacotes gerados' in r.text and 'Pacotes preparados' in r.text, 'depois de gerar, a tela do nó mostra os pacotes preparados')
reg = db.todos(db.PLATAFORMA, 'SELECT token_cifrado, lote FROM instalacao_links')
checa(all(x['token_cifrado'] and cod not in x['token_cifrado'] and seg not in x['token_cifrado'] for x in reg) and len({x['lote'] for x in reg}) == 1, 'links guardados só cifrados, num lote')
t = con.get(U)
checa(cod in t.text and seg in t.text and t.headers.get('cache-control') == 'no-store' and 'Cancelar estes links' in t.text and 'Gerar novos pacotes' in t.text, 'saindo e voltando: a tela mostra os mesmos comandos')
checa('class="btn" href="' + U in con.get('/nos').text, '"Preparar instalação" é botão')
checa(cod not in TestClient(app, base_url='http://gestao.localhost').get(U).text, 'sem login não vê os links')
checa(db.um(db.PLATAFORMA, 'SELECT token_hash FROM nos WHERE id=%s', (n['id'],))['token_hash'] != tok_antigo_hash, 'token novo do nó gerado (o antigo deixou de valer)')
log = ' '.join(x['acao'] for x in db.todos(db.PLATAFORMA, 'SELECT acao FROM log_console'))
checa('pacotes gerados' in log and 'senha-do-pacote' not in log and cod not in log and seg not in log, 'registro sem senha nem link')
arqs = list(IN.pasta().iterdir())
checa(len(arqs) == 1 and arqs[0].read_bytes()[:8] == b'Salted__' and b'SECRET_KEY' not in arqs[0].read_bytes(), 'no disco só o pacote de segredos cifrado')
# download do código (sem login, como o curl da VPS nova)
anon = TestClient(app, base_url='http://gestao.localhost')
r = anon.get(f'/instalar/{cod}')
checa(r.status_code == 200 and 'attachment' in r.headers.get('content-disposition', '') and r.headers.get('cache-control') == 'no-store', 'pacote de código baixado')
with tarfile.open(fileobj=io.BytesIO(r.content)) as tf:
    nomes = tf.getnames()
    todo = b''.join(tf.extractfile(m).read() for m in tf.getmembers() if m.isfile() and m.name.endswith(('.py', '.yml', '.sh', '.txt', 'Dockerfile')))
checa('portal_web/app/main.py' in nomes and 'portal_web/deploy/no/instalar.sh' in nomes and 'portal_web/docker-compose.yml' in nomes and 'portal_web/Dockerfile' in nomes, 'código: app, instalador e arquivos de implantação')
checa(not any(x.endswith('.env') or 'env-origem' in x or '/segredos/' in x for x in nomes) and not any('__pycache__' in x for x in nomes), 'código sem .env, sem segredos e sem cache')
checa(anon.get(f'/instalar/{cod}').status_code == 404, 'link de código só vale uma vez')
t = con.get(U).text
checa(cod not in t and seg in t and 'O pacote de código já foi baixado' in t and 'chip ok' in t, 'tela revista: código baixado, segredos ainda disponível')
# download dos segredos: cifrado; o openssl (como no instalador) abre com a senha do pacote
r = anon.get(f'/instalar/{seg}')
checa(r.status_code == 200 and r.content[:8] == b'Salted__', 'pacote de segredos baixado cifrado')
checa(not any(IN.pasta().iterdir()), 'arquivo apagado do disco depois do download')
checa(anon.get(f'/instalar/{seg}').status_code == 404, 'link de segredos só vale uma vez')
t = con.get(U).text
checa(seg not in t and 'bash deploy/no/instalar.sh' in t and 'curl -fsS' not in t, 'os dois baixados: a tela ainda mostra o passo do instalador, sem links')
checa(all(not x['token_cifrado'] for x in db.todos(db.PLATAFORMA, 'SELECT token_cifrado FROM instalacao_links')), 'link baixado não fica guardado')
d = tempfile.mkdtemp(); (Path(d) / 'p.enc').write_bytes(r.content)
abre = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '600000', '-md', 'sha256', '-in', f'{d}/p.enc', '-out', f'{d}/p.tgz', '-pass', 'env:SP'],
                      env=dict(os.environ, SP='senha-do-pacote-123'), capture_output=True)
checa(abre.returncode == 0, f'openssl abre o pacote com a senha ({abre.stderr[:120]})')
errado = subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '600000', '-md', 'sha256', '-in', f'{d}/p.enc', '-out', f'{d}/x', '-pass', 'env:SP'],
                        env=dict(os.environ, SP='senha-errada-123'), capture_output=True)
checa(errado.returncode != 0, 'senha do pacote errada: não abre')
with tarfile.open(f'{d}/p.tgz') as tf:
    env = dict(l.split('=', 1) for l in tf.extractfile('env-origem').read().decode().splitlines() if '=' in l)
checa(env.get('SECRET_KEY') == os.environ['SECRET_KEY'] and env.get('GESTAO_URL') == 'https://gestao.localhost' and env.get('NO_NOME') == 'no-inst.exemplo.test', 'segredos: chaves iguais às da gestão e dados do nó')
checa(L.no_do_token(env.get('NO_TOKEN', '')) and L.no_do_token(env['NO_TOKEN'])['id'] == n['id'], 'token novo do nó no pacote confere com a gestão')
checa(env.get('LICENCA_CHAVE_PUBLICA') == L.garantir_chaves()[1], 'chave pública da licença no pacote')
checa(not ({'PG_PASSWORD', 'SENHA_INICIAL_ADMIN', 'SENHA_INICIAL_GESTOR', 'TESTE', 'PG_HOST'} & set(env)), 'segredos sem a senha do banco da gestão nem senhas iniciais')
shutil.rmtree(d)
# sem token novo (correção de 18/11/2026): o pacote leva mesmo assim o nome do nó, a gestão e a chave pública; o token, não
r = gerar(novo_token=None)
lk = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
d = tempfile.mkdtemp(); (Path(d) / 'p.enc').write_bytes(anon.get(f'/instalar/{lk[1]}').content)
subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '600000', '-md', 'sha256', '-in', f'{d}/p.enc', '-out', f'{d}/p.tgz', '-pass', 'env:SP'],
               env=dict(os.environ, SP='senha-do-pacote-123'), capture_output=True)
with tarfile.open(f'{d}/p.tgz') as tf:
    env = dict(l.split('=', 1) for l in tf.extractfile('env-origem').read().decode().splitlines() if '=' in l)
checa(env.get('NO_NOME') == 'no-inst.exemplo.test' and env.get('GESTAO_URL') == 'https://gestao.localhost' and env.get('LICENCA_CHAVE_PUBLICA') == L.garantir_chaves()[1],
      'pacote sem token novo: leva o nome do nó, a gestão e a chave pública')
checa('NO_TOKEN' not in env, 'pacote sem token novo: não leva token')
checa('O pacote leva o nome do nó (no-inst.exemplo.test)' in con.get(U).text, 'tela explica o que o pacote leva')
checa('nunca na VPS da gestão' in con.get(U).text, 'tela avisa para rodar na VPS do nó, não na gestão')
shutil.rmtree(d)
# vencido
r = gerar(novo_token=None)
lk = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
db.exe(db.PLATAFORMA, 'UPDATE instalacao_links SET expira_em=%s WHERE baixado_em IS NULL', (datetime.now(timezone.utc) - timedelta(minutes=1),))
checa(anon.get(f'/instalar/{lk[1]}').status_code == 404, 'link vencido não baixa')
IN.limpar()
checa(not any(IN.pasta().iterdir()), 'limpeza apaga o pacote vencido do disco')
checa(anon.get('/instalar/qualquer').status_code == 404, 'link inválido: 404')
checa(anon.post(U, data={'senha_pacote': 'x' * 12}, follow_redirects=False).status_code in (302, 303, 307, 400, 401, 403), 'sem login não gera pacote')
# gerar de novo cancela os anteriores; cancelar pelo botão
r = gerar(novo_token=None); l1 = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
r = gerar(novo_token=None); l2 = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
checa('links anteriores foram cancelados' in r.text and not set(l1) & set(l2) and anon.get(f'/instalar/{l1[0]}').status_code == 404, 'gerar de novo cancela os links anteriores')
r = con.post(U + '/cancelar', data={'csrf': tok(con, U)}, follow_redirects=True)
checa('2 link(s) cancelado(s)' in r.text, 'cancelar: mensagem ' + str(re.findall(r'class="msg"[^>]*>([^<]+)', r.text)))
checa('Pacotes preparados' not in r.text, 'cancelar: a tela volta ao formulário')
checa(anon.get(f'/instalar/{l2[1]}').status_code == 404, 'cancelar: links não baixam')
checa(not any(IN.pasta().iterdir()) and all(not x['token_cifrado'] for x in db.todos(db.PLATAFORMA, 'SELECT token_cifrado FROM instalacao_links')), 'cancelar apaga o pacote e o link guardado')
checa(anon.post(U + '/cancelar', data={}, follow_redirects=False).status_code in (302, 303, 307, 400, 401, 403) and 'cancelado(s)' in ' '.join(x['acao'] for x in db.todos(db.PLATAFORMA, 'SELECT acao FROM log_console')), 'cancelar exige login e fica no registro')
# ---------- instância: segundo nó na mesma VPS (18/11/2026) ----------
r = con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'criar', 'nome': 'no-cm.exemplo.test', 'instancia': 'Câmara!'}, follow_redirects=True)
checa('Instância: só letras' in r.text and not db.um(db.PLATAFORMA, "SELECT 1 x FROM nos WHERE nome='no-cm.exemplo.test'"), 'instância inválida: recusada')
r = con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'criar', 'nome': 'no-cm.exemplo.test', 'instancia': 'camara'}, follow_redirects=True)
nc = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no-cm.exemplo.test'")
checa(nc and nc['instancia'] == 'camara' and 'instância camara' in con.get('/nos').text, 'nó com instância cadastrado e mostrado')
UC = f"/nos/{nc['id']}/instalar"
d0 = {'csrf': tok(con, UC), 'senha_pacote': 'senha-do-pacote-123', 'senha_pacote2': 'senha-do-pacote-123', 'novo_token': '1',
      'minha_senha': 'gestorforte1234', 'codigo': totp(apoio.SEGREDOS['gestor@gestao.localhost'])}
import time as _t; _t.sleep(31)  # outro código do autenticador (o mesmo não vale duas vezes)
d0['codigo'] = totp(apoio.SEGREDOS['gestor@gestao.localhost'])
r = con.post(UC, data=d0, follow_redirects=True)
checa('mkdir -p /opt/portal_web-camara' in r.text and '--strip-components=1' in r.text and '/root/segredos-no@camara.tar.gz.enc' in r.text
      and '/root/portal-codigo@camara.tar.gz' in r.text, 'instância: comandos com a pasta e os arquivos da instância')
lk = re.findall(r'https://gestao\.localhost/instalar/([A-Za-z0-9_\-]+)', r.text)
d = tempfile.mkdtemp(); (Path(d) / 'p.enc').write_bytes(anon.get(f'/instalar/{lk[1]}').content)
subprocess.run(['openssl', 'enc', '-d', '-aes-256-cbc', '-pbkdf2', '-iter', '600000', '-md', 'sha256', '-in', f'{d}/p.enc', '-out', f'{d}/p.tgz', '-pass', 'env:SP'],
               env=dict(os.environ, SP='senha-do-pacote-123'), capture_output=True)
with tarfile.open(f'{d}/p.tgz') as tf:
    env = dict(l.split('=', 1) for l in tf.extractfile('env-origem').read().decode().splitlines() if '=' in l)
checa(env.get('INSTANCIA') == 'camara' and env.get('NO_NOME') == 'no-cm.exemplo.test', 'instância: o pacote leva a instância do nó')
shutil.rmtree(d)
# ---------- pasta do nó (19/11/2026): aviso de pasta em uso, editar a instância e pasta vinda do relatório ----------
L.criar_no('no-outro.exemplo.test')   # outro nó na pasta padrão, como o no-inst
t = con.get(U).text
checa('Onde este nó fica' in t and 'na pasta <code>/opt/portal_web</code>' in t and 'no-outro.exemplo.test' in t and 'preencha antes uma instância diferente' in t,
      'instalação: avisa que outro nó usa a mesma pasta')
checa('preencha antes uma instância diferente' not in con.get(UC).text, 'nó com instância própria: sem aviso')
r = con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'instancia', 'id': str(nc['id']), 'instancia': 'X y'}, follow_redirects=True)
checa('Instância: só letras' in r.text and db.um(db.PLATAFORMA, 'SELECT instancia FROM nos WHERE id=%s', (nc['id'],))['instancia'] == 'camara', 'mudar instância inválida: recusada')
r = con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'instancia', 'id': str(nc['id']), 'instancia': 'cmx'}, follow_redirects=True)
checa('pasta na VPS agora é /opt/portal_web-cmx' in r.text and db.um(db.PLATAFORMA, 'SELECT instancia FROM nos WHERE id=%s', (nc['id'],))['instancia'] == 'cmx'
      and 'instância “cmx”' in ' '.join(x['acao'] for x in db.todos(db.PLATAFORMA, 'SELECT acao FROM log_console')), 'mudar instância: gravada e registrada')
db.exe(db.PLATAFORMA, """UPDATE nos SET relatorio='{"pasta": "/opt/portal_web", "ip": "192.0.2.10"}', relatorio_em=now() WHERE id=%s""", (nc['id'],))
t = con.get('/nos').text
checa('pasta na VPS: <code>/opt/portal_web</code>' in t and 'o cadastro indica /opt/portal_web-cmx' in t, 'Nós e licenças: pasta do relatório e alerta quando difere do cadastro')
from app import relatorio as RL
checa('pasta' in RL.montar() and 'instancia' in RL.montar(), 'relatório do nó leva a pasta e a instância')
IN.FONTE = Path('/nao/existe')
checa('gere a imagem de novo' in con.get(U).text, 'sem as fontes na imagem: avisa e não gera')
shutil.rmtree(F)

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('instalação pelo console: tudo ok')
