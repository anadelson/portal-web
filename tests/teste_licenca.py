# Separação gestão × portais, etapa A1 (11/11/2026): licença assinada por órgão.
# Papel "tudo" (como hoje) tem de dar EXATAMENTE o mesmo resultado de antes; o papel "no" é simulado no mesmo processo.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_licenca.py
import json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, licenca as L, web, worker
from app.catalogo import MOD, serve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
CM = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='cm-bora'")

def antigo(o):
    """modulos_do_orgao como era antes da etapa A1 (leitura direta do banco de controle)."""
    contratados = {r['chave'] for r in db.todos(db.PLATAFORMA, 'SELECT chave FROM orgao_modulos WHERE orgao_id=%s AND contratado', (o['id'],))}
    ligados = db.cfg(o['banco'], 'modulos_ligados', {}) or {}
    c = db.um(db.PLATAFORMA, 'SELECT * FROM contratos WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
    fase = web.situacao_contrato(c)[1] if c else 'impl'
    res = {}
    for k, m in MOD.items():
        if not serve(k, o['tipo']):
            continue
        res[k] = True if m[3] == 'obr' else False if fase in ('carencia', 'fim', 'susp') else ligados.get(k, True) if m[3] == 'plano' else (k in contratados and ligados.get(k, True))
    return res

# ---------- 1. papel "tudo": igual a antes, inclusive mudança feita direto no banco ----------
checa(config.PAPEL == 'tudo', 'papel padrão é "tudo"')
for o in (PM, CM):
    checa(web.modulos_do_orgao(o) == antigo(o), f'{o["slug"]}: módulos iguais aos de antes')
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=FALSE WHERE orgao_id=%s AND chave='bi'", (PM['id'],))
checa(web.modulos_do_orgao(PM)['bi'] is False and web.modulos_do_orgao(PM) == antigo(PM), 'mudança no contrato vale na hora (sem cache no papel "tudo")')
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=TRUE WHERE orgao_id=%s AND chave='bi'", (PM['id'],))
db.exe(db.PLATAFORMA, 'UPDATE contratos SET suspenso=TRUE WHERE orgao_id=%s', (PM['id'],))
checa(web.modulos_do_orgao(PM) == antigo(PM) and web.modulos_do_orgao(PM)['diario'] is False and web.modulos_do_orgao(PM)['transp'], 'suspenso: só o obrigatório, igual a antes')
db.exe(db.PLATAFORMA, 'UPDATE contratos SET suspenso=FALSE WHERE orgao_id=%s', (PM['id'],))

# ---------- 2. chaves e assinatura ----------
imp, pub = L.garantir_chaves()
checa(L.garantir_chaves() == (imp, pub) and len(imp) == 16 and db.um(db.PLATAFORMA, 'SELECT count(*) n FROM licenca_chaves')['n'] == 1, 'par de chaves criado uma vez só (provision)')
cif = db.um(db.PLATAFORMA, 'SELECT privada_cifrada FROM licenca_chaves')['privada_cifrada']
checa(cif.startswith('gAAAA') and pub not in cif, 'chave privada guardada cifrada')
p = L.emitir(PM)
checa(L.verificar(p, pub) == p['doc'] and p['doc']['orgao']['dominio'] == PM['dominio'] and 'diario' in p['doc']['modulos'], 'licença assinada confere')
falsa = json.loads(json.dumps(p)); falsa['doc']['modulos'].append('audiencias')
checa(L.verificar(falsa, pub) is None, 'licença adulterada (módulo a mais) recusada')
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization as S
outra = L._b64(Ed25519PrivateKey.generate().public_key().public_bytes(S.Encoding.Raw, S.PublicFormat.Raw))
checa(L.verificar(p, outra) is None, 'licença conferida com outra chave: recusada')
checa(L.verificar({'doc': p['doc']}, pub) is None and L.verificar({'doc': p['doc'], 'sig': 'x'}, pub) is None, 'licença sem assinatura ou com assinatura inválida: recusada')

# ---------- 3. console: nós, token uma vez, API ----------
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
t = con.get('/nos').text
checa('Nós e licenças' in t and imp in t and pub in t and 'Nenhum nó ainda' in t, 'tela de nós com a chave pública e a impressão digital')
r = con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'criar', 'nome': 'no1.exemplo.test'})
m = re.search(r'<code class="senha">([^<]+)</code>', r.text)
token = m.group(1) if m else ''
checa(len(token) > 30 and r.headers.get('cache-control') == 'no-store' and 'GESTAO_URL' in r.text and pub in r.text, 'token do nó mostrado uma vez, com o que vai no .env')
n = db.um(db.PLATAFORMA, "SELECT * FROM nos WHERE nome='no1.exemplo.test'")
checa(n and token not in json.dumps(n, default=str) and n['token_hash'] != token, 'gestão guarda só o hash do token')
checa(token not in con.get('/nos').text and not db.um(db.PLATAFORMA, 'SELECT 1 FROM log_console WHERE acao LIKE %s', (f'%{token[:12]}%',)), 'token não reaparece nem vai para o registro')
checa('Nome do nó' in con.post('/nos', data={'csrf': tok(con, '/nos'), 'acao': 'criar', 'nome': 'Nome Ruim!'}, follow_redirects=True).text, 'nome de nó inválido recusado')
api = TestClient(app, base_url='http://gestao.localhost')
checa(api.get('/api/no/licencas').status_code == 401 and api.get('/api/no/licencas', headers={'Authorization': 'Bearer errado'}).status_code == 401, 'API sem token ou com token errado: 401')
r = api.get('/api/no/licencas', headers={'Authorization': f'Bearer {token}', 'X-Versao': 'teste-1'})
checa(r.status_code == 200 and r.json()['licencas'] == [] and r.headers.get('cache-control') == 'no-store', 'nó sem órgãos: nenhuma licença')
checa(db.um(db.PLATAFORMA, 'SELECT ultimo_contato, versao FROM nos WHERE id=%s', (n['id'],))['versao'] == 'teste-1', 'contato do nó registrado')
t = con.get(f"/orgao/{PM['id']}").text
checa('Hospedagem e licença' in t and 'esta VPS (gestão e portal juntos)' in t and 'montada na hora' in t and 'Diário Oficial' in t, 'página do órgão mostra hospedagem e o contratado')
r = con.post(f"/orgao/{PM['id']}/hospedagem", data={'csrf': tok(con, f"/orgao/{PM['id']}"), 'no_id': str(n['id'])}, follow_redirects=True)
checa('Marque a confirmação' in r.text and db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (PM['id'],))['no_id'] is None, 'mudar hospedagem exige confirmação')
con.post(f"/orgao/{PM['id']}/hospedagem", data={'csrf': tok(con, f"/orgao/{PM['id']}"), 'no_id': str(n['id']), 'confirmo': '1'}, follow_redirects=True)
r = api.get('/api/no/licencas', headers={'Authorization': f'Bearer {token}'})
lic = r.json()['licencas']
checa(len(lic) == 1 and L.verificar(lic[0], pub)['orgao']['slug'] == 'pm-bora', 'nó recebe a licença assinada do órgão que hospeda')
checa('entregue ao nó em' in con.get(f"/orgao/{PM['id']}").text, 'console mostra quando a licença foi entregue')
checa(web.modulos_do_orgao(PM) == antigo(PM), 'papel "tudo": hospedagem registrada não muda nada no portal desta VPS')

# ---------- 4. papel "no" simulado: licença em cache, gestão fora do ar, vencida, adulterada ----------
def gestao_responde():
    papel = config.PAPEL; config.PAPEL = 'tudo'
    try:
        return L.entregar(n)
    finally:
        config.PAPEL = papel
L.buscar_na_gestao = gestao_responde
config.PAPEL, config.GESTAO_URL, config.NO_TOKEN, config.LICENCA_CHAVE_PUBLICA = 'no', 'https://gestao.exemplo.test', token, pub
web.limpar_cache(); L._memo.clear()
pt = TestClient(app, base_url='http://pmbora.localhost')
checa(pt.get('/').status_code == 404 or 'não encontrado' in pt.get('/').text.lower() or web.orgao_por_dominio('pmbora.localhost') is None, 'nó sem licença: domínio ainda não servido')
checa(L.puxar() == '1 licença(s) aceitas', 'nó busca e confere a licença')
web.limpar_cache(); L._memo.clear()
checa(web.orgao_por_dominio('pmbora.localhost') and web.modulos_do_orgao(web.orgao_por_dominio('pmbora.localhost')) == antigo(PM), 'nó: mesmos módulos da gestão, vindos da licença')
checa(pt.get('/').status_code == 200 and pt.get('/transparencia').status_code == 200, 'nó serve o portal pela licença')
checa(TestClient(app, base_url='http://gestao.localhost').get('/login').status_code == 404, 'nó não serve o console')
checa(web.orgao_por_dominio('cmbora.localhost') is None, 'nó só serve os órgãos que hospeda')
# a gestão contrata/desliga: o nó só muda depois de buscar de novo
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=FALSE WHERE orgao_id=%s AND chave='bi'", (PM['id'],)); L._memo.clear()
checa(web.modulos_do_orgao(PM)['bi'] is True, 'mudança na gestão só chega ao nó na próxima busca')
L.puxar(); checa(web.modulos_do_orgao(PM)['bi'] is False, 'depois da busca, o nó segue a gestão')
db.exe(db.PLATAFORMA, "UPDATE orgao_modulos SET contratado=TRUE WHERE orgao_id=%s AND chave='bi'", (PM['id'],)); L.puxar()
# gestão fora do ar: segue com a licença guardada; a falha fica registrada
def fora(): raise RuntimeError('gestão respondeu HTTP 502')
L.buscar_na_gestao = fora
worker.licencas_tick({}); L._memo.clear()
checa(db.um(db.PLATAFORMA, "SELECT ok, mensagem FROM coletas WHERE fonte='licencas:gestao' ORDER BY id DESC LIMIT 1") == {'ok': False, 'mensagem': 'RuntimeError: gestão respondeu HTTP 502'}, 'falha da busca registrada')
checa(web.modulos_do_orgao(PM)['diario'] is True and pt.get('/').status_code == 200, 'gestão fora do ar: portal segue com a licença guardada')
# licença vencida (sem contato por mais que a validade): carência — só o obrigatório, portal e transparência no ar
L.buscar_na_gestao = gestao_responde
config.LICENCA_VALIDADE_DIAS = -1; L.puxar(); config.LICENCA_VALIDADE_DIAS = 15
L._memo.clear(); web.limpar_cache()
md = web.modulos_do_orgao(PM)
checa(md['transp'] and md['sic'] and md['ouv'] and not md['diario'] and not md['bi'], f'licença vencida: carência, só o obrigatório ({md})')
checa(pt.get('/').status_code == 200 and pt.get('/transparencia').status_code == 200, 'licença vencida: portal e transparência continuam no ar')
L.puxar(); L._memo.clear()
checa(web.modulos_do_orgao(PM)['diario'] is True, 'licença renovada: módulos de volta')
# licença adulterada no banco do nó: recusada
db.exe(db.PLATAFORMA, """UPDATE licencas_cache SET pacote = jsonb_set(pacote, '{doc,modulos}', '["audiencias","bi","diario"]') WHERE orgao_id=%s""", (PM['id'],))
L._memo.clear(); web.limpar_cache()
checa(L.vigente(PM) is None and web.orgao_por_dominio('pmbora.localhost') is None, 'licença adulterada no nó: não vale (nem para contratar, nem para servir o domínio)')
checa(L.guardar([falsa], pub) == (0, 1), 'busca com licença adulterada: recusada e contada')
L.puxar(); L._memo.clear(); web.limpar_cache()
checa(L.vigente(PM) and web.orgao_por_dominio('pmbora.localhost'), 'nova busca corrige o cache')
# licença antiga não sobrescreve a nova
velho = L.assinar(dict(L.documento(PM), serial=1))
L.guardar([velho], pub)
checa(db.um(db.PLATAFORMA, 'SELECT serial FROM licencas_cache WHERE orgao_id=%s', (PM['id'],))['serial'] > 1, 'licença mais antiga não substitui a mais nova')
checa(L.puxar() and 'gestão' not in L.puxar(), 'puxar sem erro')
config.NO_TOKEN = ''
checa('faltam' in L.puxar(), 'nó sem token: mensagem explica o que falta')

# ---------- 5. papel "gestao": só o console ----------
config.PAPEL = 'gestao'; web.limpar_cache(); L._memo.clear()
rg, rp = TestClient(app, base_url='http://gestao.localhost').get('/login'), TestClient(app, base_url='http://pmbora.localhost').get('/')
checa(rg.status_code == 200 and rp.status_code == 404, f'gestão sozinha: console sim, portais não ({rg.status_code}, {rp.status_code})')
config.PAPEL = 'tudo'; web.limpar_cache(); L._memo.clear()
db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=NULL WHERE id=%s', (PM['id'],))
checa(pt.get('/').status_code == 200 and web.modulos_do_orgao(PM) == antigo(PM), 'de volta ao papel "tudo": igual a antes')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('licença: tudo ok')
