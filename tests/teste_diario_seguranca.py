# Fase 6 (MODO TESTE): Diário assinado, regras de operação, remessa Câmara → Prefeitura, segundo fator, bloqueio, sessão e gov.br.
#   TESTE=1 DATA_SIMULADA=2026-11-06T10:00 SEGREDOS_DIR=/tmp/segredos PYTHONPATH=. python tests/teste_diario_seguranca.py
# Só em banco de TESTE; certificados gerados só para teste; nenhum dado pessoal real.
import base64, json, os, re, sys, time
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, assinatura as A, diario_servico as DS, remessa as RM, acesso as AC
from app.security import totp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok, SEGREDOS, CODIGOS

erros = []
def falha(m): erros.append(m)
def ok(r, cod=200, txt=None, nome='', sem=None):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {re.sub(r"<[^>]+>", " ", r.text)[:260]}')
    if sem and sem in r.text: falha(f'{nome}: não deveria conter "{sem}"')
    return r
def msg(r):
    m = re.search(r'class="msg" role="(?:status|alert)"[^>]*>(.*?)</p>', r.text, re.S); return re.sub(r'<[^>]+>', ' ', m.group(1)) if m else ''
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
if not A.modo_teste(): sys.exit('Este teste roda em DIARIO_MODO=teste.')
if not Path(config.SEGREDOS_DIR, 'teste', 'raiz.crt').is_file(): A.gerar_cadeia_teste()
O = {o['slug']: o for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos')}

pm = TestClient(app, base_url='http://pmbora.localhost')
# ---------- segundo fator obrigatório ----------
r = pm.post('/admin/login', data={'csrf': tok(pm, '/admin/login'), 'email': 'admin@pmbora.localhost', 'senha': 'admin123'}, follow_redirects=True)
ok(r, txt='Ative o segundo fator', nome='cadastro do autenticador exigido')
ok(pm.get('/admin/', follow_redirects=False), 303, nome='painel bloqueado antes do 2º fator')
r = pm.post('/admin/2fa', data={'csrf': tok(pm, '/admin/2fa'), 'codigo': '000000'}, follow_redirects=True)
if 'não confere' not in msg(r): falha('código errado no cadastro deveria ser recusado')
pm = TestClient(app, base_url='http://pmbora.localhost')
ok(entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123'), txt='Visão geral', nome='login completo')
if len(CODIGOS.get('admin@pmbora.localhost', [])) != 10: falha('10 códigos de recuperação')
u = db.um(PM, "SELECT * FROM usuarios WHERE email='admin@pmbora.localhost'")
if not u['totp_ativo'] or SEGREDOS['admin@pmbora.localhost'] in u['totp_segredo'] or len(u['recuperacao']) != 10: falha('segredo TOTP deveria ficar cifrado e códigos só como hash')
# login seguinte com código; com código de recuperação (uso único)
pm2 = TestClient(app, base_url='http://pmbora.localhost')
ok(entrar(pm2, 'admin@pmbora.localhost', 'senhaforte123'), txt='Visão geral', nome='login com TOTP')
pm3 = TestClient(app, base_url='http://pmbora.localhost')
pm3.post('/admin/login', data={'csrf': tok(pm3, '/admin/login'), 'email': 'admin@pmbora.localhost', 'senha': 'senhaforte123'})
rc = CODIGOS['admin@pmbora.localhost'][0]
ok(pm3.post('/admin/2fa', data={'csrf': tok(pm3, '/admin/2fa'), 'recuperacao': rc}, follow_redirects=True), txt='Restam 9', nome='código de recuperação')
pm4 = TestClient(app, base_url='http://pmbora.localhost')
pm4.post('/admin/login', data={'csrf': tok(pm4, '/admin/login'), 'email': 'admin@pmbora.localhost', 'senha': 'senhaforte123'})
r = pm4.post('/admin/2fa', data={'csrf': tok(pm4, '/admin/2fa'), 'recuperacao': rc}, follow_redirects=True)
if 'inválido' not in msg(r): falha('código de recuperação deveria valer uma vez só')
# ---------- bloqueio por tentativas ----------
pm.post('/admin/usuarios', data={'csrf': tok(pm, '/admin/usuarios'), 'acao': 'novo', 'nome': 'Usuária Teste Bloqueio', 'email': 'bloqueio@teste.localhost', 'perfil': 'editor', 'senha': 'senhaprovisoria1'})
x = TestClient(app, base_url='http://pmbora.localhost')
for i in range(config.LOGIN_MAX_FALHAS):
    r = x.post('/admin/login', data={'csrf': tok(x, '/admin/login'), 'email': 'bloqueio@teste.localhost', 'senha': 'errada'}, follow_redirects=True)
if 'bloqueado temporariamente' not in msg(r): falha(f'bloqueio após {config.LOGIN_MAX_FALHAS} falhas: {msg(r)}')
r = x.post('/admin/login', data={'csrf': tok(x, '/admin/login'), 'email': 'bloqueio@teste.localhost', 'senha': 'senhaprovisoria1'}, follow_redirects=True)
if 'bloqueado temporariamente' not in msg(r): falha('senha certa durante o bloqueio deveria ser recusada')
uid = db.um(PM, "SELECT id FROM usuarios WHERE email='bloqueio@teste.localhost'")['id']
ok(pm.post('/admin/usuarios', data={'csrf': tok(pm, '/admin/usuarios'), 'acao': 'desbloquear', 'id': uid}, follow_redirects=True), txt='Usuário atualizado', nome='desbloquear')
y = TestClient(app, base_url='http://pmbora.localhost')
ok(y.post('/admin/login', data={'csrf': tok(y, '/admin/login'), 'email': 'bloqueio@teste.localhost', 'senha': 'senhaprovisoria1'}, follow_redirects=True), txt='segundo fator', nome='após desbloqueio')
if not db.um(PM, "SELECT 1 FROM auditoria WHERE acao LIKE 'Tentativa de acesso recusada%%'"): falha('tentativas não registradas na auditoria')
# ---------- sessão expira por inatividade ----------
orig = config.SESSAO_INATIVIDADE_MIN
config.SESSAO_INATIVIDADE_MIN = 0
time.sleep(1.1)
r = pm2.get('/admin/', follow_redirects=True)
config.SESSAO_INATIVIDADE_MIN = orig
if 'inatividade' not in r.text: falha('sessão deveria expirar por inatividade')
# ---------- cabeçalhos de segurança ----------
h = pm.get('/').headers
if "frame-ancestors 'none'" not in h.get('content-security-policy', '') or h.get('x-frame-options') != 'DENY' or h.get('x-content-type-options') != 'nosniff': falha(f'cabeçalhos: {dict(h)}')
if 'no-store' not in pm.get('/admin/').headers.get('cache-control', ''): falha('painel sem no-store')
ck = pm.get('/admin/login').headers.get('set-cookie', '')
if ck and ('httponly' not in ck.lower() or 'samesite=lax' not in ck.lower()): falha(f'cookie: {ck}')

# ---------- Diário: designações, calendário, ato com corte, assinatura por caderno ----------
def post(c, url, data, files=None, de=None):
    return c.post(url, data=dict(data, csrf=tok(c, de or url)), files=files, follow_redirects=True)
r = post(pm, '/admin/diario/config', {'acao': 'designar', 'caderno': 'final', 'nome': 'Responsável Teste', 'cargo': 'Chefe de Gabinete (teste)', 'ato': 'Portaria nº 1/2026 (teste)', 'ato_data': '2026-03-25', 'provedor': 'a1', 'certificado': 'responsavel.p12', 'senha_env': 'senha123'})
if 'NOME da variável' not in msg(r): falha('A1 com senha no lugar do nome da variável deveria ser recusado')
for cad, nome in (('executivo', 'Prefeito Teste'), ('legislativo', 'Presidente Teste'), ('final', 'Responsável Teste')):
    post(pm, '/admin/diario/config', {'acao': 'designar', 'caderno': cad, 'nome': nome, 'cargo': 'cargo (teste)', 'ato': f'Portaria {cad} (teste)', 'provedor': 'a3' if cad == 'legislativo' else 'a1', 'certificado': f'{cad}.p12', 'senha_env': f'A1_SENHA_{cad.upper()}'})
if db.um(PM, 'SELECT count(*) n FROM designacoes WHERE ativo')['n'] != 3: falha('designações')
post(pm, '/admin/diario/config', {'acao': 'feriado', 'data': '2026-11-10', 'descricao': 'Feriado de teste', 'tipo': 'feriado'})
post(pm, '/admin/diario/config', {'acao': 'feriado', 'data': '2026-11-11', 'descricao': 'Ponto facultativo de teste', 'tipo': 'ponto_facultativo'})
def novo_ato(c, caderno, ementa, retifica=''):
    return post(c, '/admin/diario/ato', {'acao': 'novo', 'caderno': caderno, 'tipo': 'Decreto', 'numero': f'{caderno[:3]}-1/2026', 'orgao': 'Gabinete (teste)', 'ementa': ementa, 'texto': 'Art. 1º Texto fictício de teste.', 'retifica': retifica}, de='/admin/diario')
r = novo_ato(pm, 'executivo', 'Decreto fictício do Executivo')
if '06/11/2026' not in msg(r): falha(f'ato antes das 16h vai para a edição do dia: {msg(r)}')
novo_ato(pm, 'legislativo', 'Resolução fictícia (caderno Legislativo)')
for a in db.todos(PM, "SELECT id FROM diario_atos WHERE situacao='revisao'"):
    post(pm, '/admin/diario/ato', {'acao': 'aprovar', 'id': a['id']}, de='/admin/diario')
r = post(pm, '/admin/diario/edicao', {'acao': 'abrir'}, de='/admin/diario')
if 'MODO TESTE' not in msg(r): falha(f'abrir: {msg(r)}')
r = post(pm, '/admin/diario/edicao', {'acao': 'fechar'}, de='/admin/diario')
e = DS.em_andamento(PM)
if [x['etapa'] for x in e['assinaturas']] != ['executivo', 'legislativo', 'final']: falha(f'etapas: {e["assinaturas"]}')
if not e['pdfa']: falha('PDF/A-2b não gerado (Ghostscript)')
if b'pdfaid' not in Path(e['pdf_arquivo']).read_bytes(): falha('metadados PDF/A ausentes')
r = post(pm, '/admin/diario/edicao', {'acao': 'publicar'}, de='/admin/diario')
if 'depois de assinada' not in msg(r): falha('publicação sem assinatura deveria ser recusada')
r = post(pm, '/admin/diario/edicao', {'acao': 'assinar'}, de='/admin/diario')
if 'Caderno do Poder Executivo: assinada' not in msg(r): falha(f'assinar executivo: {msg(r)}')
# etapa do Legislativo por upload (A3): o "computador do signatário" assina o PDF baixado
pdf_atual = ok(pm.get(f"/admin/diario/edicao/{e['id']}.pdf"), nome='baixar para A3').content
outro = A.assinar(pdf_atual[:-1] + b'\n', 'legislativo', None, 'documento diferente', 'Teste')  # assinado sobre um arquivo diferente
r = post(pm, '/admin/diario/edicao', {'acao': 'a3'}, files={'arquivo': ('x.pdf', outro, 'application/pdf')}, de='/admin/diario')
if 'não é o PDF desta edição' not in msg(r): falha(f'A3 adulterado deveria ser recusado: {msg(r)}')
assinado = A.assinar(pdf_atual, 'legislativo', None, 'Caderno do Poder Legislativo (teste)', 'Teste')
r = post(pm, '/admin/diario/edicao', {'acao': 'a3'}, files={'arquivo': ('l.pdf', assinado, 'application/pdf')}, de='/admin/diario')
if 'recebida e validada' not in msg(r): falha(f'A3: {msg(r)}')
r = post(pm, '/admin/diario/edicao', {'acao': 'assinar'}, de='/admin/diario')
if 'totalmente assinada' not in msg(r): falha(f'assinatura final: {msg(r)}')
e = db.um(PM, 'SELECT * FROM diario_edicoes WHERE id=%s', (e['id'],))
sigs = A.validar(Path(e['pdf_arquivo']).read_bytes())
if len(sigs) != 3 or not all(s['integra'] and s['valida'] and s['carimbo'] for s in sigs): falha(f'validação PAdES + carimbo: {sigs}')
if 'TESTE' not in sigs[0]['signatario']: falha('signatário de teste')
r = post(pm, '/admin/diario/edicao', {'acao': 'publicar'}, de='/admin/diario')
if 'MODO TESTE' not in msg(r): falha(f'conclusão em teste: {msg(r)}')
ok(pm.get('/diario'), txt='Nenhuma edição oficial publicada', nome='teste nunca vira oficial')
r = ok(pm.get(f"/diario/verificar?codigo={e['codigo']}"), txt='EDIÇÃO DE TESTE', nome='verificação')
for t_ in ('Responsavel pelo Diario - TESTE', 'Prefeito(a) - TESTE', 'validar.iti.gov.br', e['sha256'], 'Íntegra e válida', 'PDF/A-2b'):
    if t_ not in r.text: falha(f'verificação sem "{t_}"')
# ---------- extra, retificação ----------
r = post(pm, '/admin/diario/edicao', {'acao': 'extra'}, de='/admin/diario')
ex = DS.em_andamento(PM)
if not ex or ex['letra'] != 'A' or ex['numero'] != e['numero']: falha(f'edição extra: {msg(r)}')
ato_pub = db.um(PM, "SELECT id FROM diario_atos WHERE situacao='publicado' AND caderno='executivo' LIMIT 1")['id']
novo_ato(pm, 'executivo', 'Retificação fictícia do decreto', retifica=str(ato_pub))
rt = db.um(PM, 'SELECT * FROM diario_atos WHERE retifica_ato_id=%s', (ato_pub,))
post(pm, '/admin/diario/ato', {'acao': 'aprovar', 'id': rt['id']}, de='/admin/diario')
for a in ('fechar', 'assinar', 'assinar', 'publicar'):
    post(pm, '/admin/diario/edicao', {'acao': a}, de='/admin/diario')
if db.um(PM, 'SELECT situacao FROM diario_atos WHERE id=%s', (rt['id'],))['situacao'] != 'publicado': falha('retificação publicada na extra')
# ---------- corte das 16h, calendário, sem atos automático, alerta, publicação só assinada ----------
o = O['pm-bora']
os.environ['DATA_SIMULADA'] = '2026-11-06T16:20'
r = novo_ato(pm, 'executivo', 'Ato enviado depois do corte')
if '09/11/2026' not in msg(r): falha(f'ato depois das 16h de sexta deveria ir para segunda 09/11: {msg(r)}')
db.exe(PM, "DELETE FROM diario_atos WHERE ementa='Ato enviado depois do corte'")
if DS.tick(o, datetime(2026, 11, 7, 16, 5)): falha('sábado não tem edição')
r = DS.tick(o, datetime(2026, 11, 9, 16, 5))
sa = db.um(PM, "SELECT * FROM diario_edicoes WHERE data='2026-11-09'")
if not sa or not sa['sem_atos'] or sa['assinatura'] != 'teste': falha(f'edição sem atos automática e assinada: {r}')
DS.tick(o, datetime(2026, 11, 9, 17, 5))
if db.um(PM, "SELECT situacao FROM diario_edicoes WHERE data='2026-11-09'")['situacao'] != 'publicada': falha('publicação automática às 17h')
if DS.tick(o, datetime(2026, 11, 10, 16, 5)) or db.um(PM, "SELECT 1 FROM diario_edicoes WHERE data='2026-11-10'"): falha('feriado não tem edição')
DS.tick(o, datetime(2026, 11, 11, 16, 5))
if not db.um(PM, "SELECT 1 FROM diario_edicoes WHERE data='2026-11-11'"): falha('ponto facultativo é dia útil')
os.environ['DATA_SIMULADA'] = '2026-11-12T09:00'
novo_ato(pm, 'executivo', 'Ato do dia 12 (alerta)')
post(pm, '/admin/diario/ato', {'acao': 'aprovar', 'id': db.um(PM, "SELECT id FROM diario_atos WHERE ementa='Ato do dia 12 (alerta)'")['id']}, de='/admin/diario')
post(pm, '/admin/diario/edicao', {'acao': 'abrir'}, de='/admin/diario'); post(pm, '/admin/diario/edicao', {'acao': 'fechar'}, de='/admin/diario')
r = DS.tick(o, datetime(2026, 11, 12, 16, 35)); DS.tick(o, datetime(2026, 11, 12, 17, 10))
if 'alerta de assinatura' not in r or not db.um(PM, "SELECT 1 FROM diario_alertas WHERE mensagem LIKE '%%não está assinada%%'"): falha(f'alerta 16h30: {r}')
if db.um(PM, "SELECT situacao FROM diario_edicoes WHERE data='2026-11-12'")['situacao'] == 'publicada': falha('edição não assinada foi publicada')
ok(pm.get('/admin/diario'), txt='ainda não está assinada', nome='alerta no painel')
for a in ('assinar', 'assinar', 'publicar'):
    post(pm, '/admin/diario/edicao', {'acao': a}, de='/admin/diario')
# ---------- invalidação (simula uma edição oficial) ----------
db.exe(PM, "UPDATE diario_edicoes SET modo_teste=FALSE WHERE data='2026-11-09'")
oficial = db.um(PM, "SELECT * FROM diario_edicoes WHERE data='2026-11-09'")
r = post(pm, '/admin/diario/edicao', {'acao': 'invalidar', 'id': oficial['id'], 'ato': 'Decreto nº 99/2026 (teste)', 'comunicado': 'Edição indisponível por falha técnica na geração do arquivo (teste).', 'prorrogacao': 'Prazos prorrogados por 1 dia útil (teste).'}, de='/admin/diario')
r = ok(pm.get('/diario'), txt='Comunicado de indisponibilidade', nome='comunicado de invalidação')
if 'Prazos prorrogados' not in r.text: falha('prorrogação de prazos não exibida')

# ---------- remessa Câmara → Prefeitura ----------
RM._cliente = lambda: TestClient(app, base_url='http://interno')
cm = TestClient(app, base_url='http://cmbora.localhost')
entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
os.environ['DATA_SIMULADA'] = '2026-11-13T09:00'
r = cm.post('/admin/remessas', data={'csrf': tok(cm, '/admin/remessas'), 'acao': 'enviar', 'tipo': 'Ato da Mesa', 'numero': '5/2026', 'ementa': 'Ato da Mesa fictício de teste', 'texto': 'Art. 1º Texto fictício da remessa da Câmara.'}, follow_redirects=True)
if 'enviada ao Diário' not in msg(r): falha(f'remessa: {msg(r)}')
ar = db.um(PM, "SELECT * FROM diario_atos WHERE origem_orgao='cm-bora'")
if not ar or ar['caderno'] != 'legislativo' or ar['situacao'] != 'revisao': falha(f'remessa no Diário da Prefeitura: {ar}')
ruim = TestClient(app, base_url='http://pmbora.localhost').post('/api/diario/remessas', content=b'{}', headers={'X-Portal-Origem': 'cm-bora', 'X-Portal-Momento': str(int(time.time())), 'X-Portal-Assinatura': 'falsa', 'Content-Type': 'application/json'})
if ruim.status_code != 401: falha('remessa com assinatura falsa deveria dar 401')
if not db.um(db.PLATAFORMA, "SELECT 1 FROM remessas_log WHERE NOT ok AND detalhe='assinatura inválida'"): falha('tentativa inválida não registrada')
post(pm, '/admin/diario/ato', {'acao': 'aprovar', 'id': ar['id']}, de='/admin/diario')
for a in ('abrir', 'fechar', 'assinar', 'assinar', 'publicar'):
    post(pm, '/admin/diario/edicao', {'acao': a}, de='/admin/diario')
rid = db.um(CM, 'SELECT id FROM remessas ORDER BY id DESC LIMIT 1')['id']
r = cm.post('/admin/remessas', data={'csrf': tok(cm, '/admin/remessas'), 'acao': 'atualizar', 'id': rid}, follow_redirects=True)
rm = db.um(CM, 'SELECT * FROM remessas WHERE id=%s', (rid,))
if 'publicado' not in rm['situacao'] or not rm['edicao'] or not rm['pagina']: falha(f'retorno da remessa (edição e página): {dict(rm)}')
ok(cm.get('/admin/remessas'), txt=f"Edição nº {rm['edicao']}", nome='Câmara vê edição e página')
if db.um(CM, 'SELECT 1 FROM diario_atos'): falha('Câmara não deve ter atos do Diário no próprio banco')

# ---------- gov.br (simulado: sem acesso real ao gov.br) ----------
ok(pm.get('/admin/govbr'), 404, nome='gov.br desligado sem configuração')
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
nums = chave.public_key().public_numbers()
b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip('=')
JWKS = {'keys': [{'kty': 'RSA', 'kid': 'k1', 'n': b64(nums.n.to_bytes(256, 'big')), 'e': b64(nums.e.to_bytes(3, 'big'))}]}
config.GOVBR_CLIENT_ID, config.GOVBR_CLIENT_SECRET, config.CPF_HMAC_CHAVE = 'cliente-teste', 'segredo-teste', 'chave-hmac-teste'
CPF_FICTICIO = '52998224725'  # CPF fictício válido usado em documentação de testes
nivel = {'v': '2'}
class Resp:
    def __init__(self, d): self.d = d
    def json(self): return self.d
class HttpFalso:
    def __init__(self, *a, **k): pass
    def post(self, url, data=None, auth=None):
        g = state_atual['nonce']
        cab = b64(json.dumps({'alg': 'RS256', 'kid': 'k1'}).encode()); corpo = b64(json.dumps({'sub': CPF_FICTICIO, 'aud': 'cliente-teste', 'iss': config.govbr_urls()['issuer'], 'exp': time.time() + 300, 'nonce': g}).encode())
        ass = b64(chave.sign(f'{cab}.{corpo}'.encode(), padding.PKCS1v15(), hashes.SHA256()))
        return Resp({'id_token': f'{cab}.{corpo}.{ass}', 'access_token': 'at'})
    def get(self, url, headers=None):
        return Resp(JWKS if url.endswith('/jwk') else [{'id': nivel['v']}])
AC.httpx = type('M', (), {'Client': HttpFalso})
state_atual = {}
def govbr_login():
    c = TestClient(app, base_url='http://pmbora.localhost')
    r = c.get('/admin/govbr', follow_redirects=False)
    from urllib.parse import urlparse, parse_qs
    q = parse_qs(urlparse(r.headers['location']).query)
    if 'code_challenge' not in q or q.get('code_challenge_method') != ['S256'] or 'sso.staging.acesso.gov.br' not in r.headers['location']: falha('URL de autorização gov.br')
    sess = json.loads(base64.b64decode(c.cookies.get('sessao').split('.')[0] + '=='))
    state_atual['nonce'] = sess['govbr']['nonce']
    return c, c.get(f"/admin/govbr/retorno?code=abc&state={q['state'][0]}", follow_redirects=True)
c, r = govbr_login()
if 'Peça ao administrador para vincular' not in r.text: falha('gov.br sem vínculo deveria ser recusado')
adm = db.um(PM, "SELECT id FROM usuarios WHERE email='bloqueio@teste.localhost'")['id']
ok(pm.post('/admin/usuarios', data={'csrf': tok(pm, '/admin/usuarios'), 'acao': 'cpf', 'id': adm, 'cpf': '529.982.247-25'}, follow_redirects=True), txt='Usuário atualizado', nome='vincular CPF')
c, r = govbr_login()
ok(r, txt='Visão geral', nome='login gov.br prata')
nivel['v'] = '1'
c, r = govbr_login()
if 'nível prata' not in r.text: falha('conta bronze deveria ser recusada')
# CPF completo nunca gravado
for banco in (PM, CM, db.PLATAFORMA):
    for t in db.todos(banco, "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"):
        for row in db.todos(banco, f'SELECT * FROM {t["table_name"]} LIMIT 2000'):
            if CPF_FICTICIO in json.dumps(row, default=str) or '529.982.247-25' in json.dumps(row, default=str): falha(f'CPF completo gravado em {banco}.{t["table_name"]}'); break
u = db.um(PM, 'SELECT cpf_final, cpf_hash FROM usuarios WHERE id=%s', (adm,))
if u['cpf_final'] != '25' or len(u['cpf_hash'] or '') != 64: falha('CPF deveria ficar só como hash + 2 dígitos')
# console sempre com segundo fator
g = TestClient(app, base_url='http://gestao.localhost')
r = g.post('/login', data={'csrf': tok(g, '/login'), 'email': 'gestor@gestao.localhost', 'senha': 'gestor123'}, follow_redirects=True)
ok(r, txt='Ative o segundo fator', nome='console exige 2º fator')
print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
