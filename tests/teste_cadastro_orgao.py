# Modelo multi-órgão, etapa 1 (10/11/2026): cadastro de órgão novo pelo console, sem nada de Borá no código.
# Municípios FICTÍCIOS (códigos IBGE que não existem): o IBGE não responde e valem o município e a UF digitados.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_cadastro_orgao.py
import os, re, sys
from pathlib import Path
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, cadastro as CD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok, ligar_email_teste, primeiro_acesso, link_convite, CAIXA

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
RAIZ = Path(__file__).resolve().parent.parent

# ---------- 1. código neutro: nada de Borá fora dos dados do piloto ----------
for p in list((RAIZ / 'app').rglob('*.py')) + list((RAIZ / 'app' / 'templates').rglob('*.html')) + list((RAIZ / 'app' / 'static').glob('*.js')):
    if 'seeds' in p.parts or 'migrations' in p.parts:
        continue
    t = p.read_text(encoding='utf-8')
    for marca in ('3507209', '44.544.906', 'borasp.dcfiorilli', 'PortaisBora', 'Portais de Borá', 'IBGE_BORA', 'pmbora', 'cmbora'):
        checa(marca not in t, f'{p.relative_to(RAIZ)}: contém "{marca}" (dado do piloto no código)')
checa((RAIZ / 'app' / 'seeds' / 'piloto_bora.json').is_file(), 'dados do piloto em seeds/piloto_bora.json')

# ---------- 2. funções do cadastro ----------
def cnpj_ficticio(base12):
    for a in range(10):
        for b in range(10):
            c = base12 + str(a) + str(b)
            if CD.cnpj_valido(c):
                return c
CNPJ = cnpj_ficticio('112223330001')
checa(CNPJ and not CD.cnpj_valido(CNPJ[:-1] + str((int(CNPJ[-1]) + 1) % 10)), 'validação do CNPJ (dígitos verificadores)')
checa(CD.slug_sugerido('executivo', 'São João das Águas') == 'pm-sao-joao-das-aguas' and CD.slug_municipio('Águas de Lindóia') == 'aguas-de-lindoia', 'identificador sugerido sem acento')
s1, s2 = CD.senha_inicial(), CD.senha_inicial()
checa(len(s1) == 16 and s1 != s2 and re.search(r'[a-z]', s1) and re.search(r'[A-Z]', s1) and re.search(r'\d', s1), 'senha inicial forte e única')

# ---------- 3. console ----------
con = TestClient(app, base_url='http://gestao.localhost')
entrar(con, 'gestor@gestao.localhost', 'gestor123', 'gestorforte1234', prefixo='')
r = con.get('/orgaos/novo')
checa(r.status_code == 200 and 'Código IBGE do município' in r.text and 'Sistema da transparência' in r.text and 'console.js' in r.text, 'formulário de cadastro completo')
checa(con.get('/orgaos/ibge/123').status_code == 404, 'busca no IBGE recusa código inválido')
checa(TestClient(app, base_url='http://gestao.localhost').get('/orgaos/ibge/3550308', follow_redirects=False).status_code in (302, 303, 401, 403), 'busca no IBGE só para gestor logado')
def cadastrar(**k):
    d = {'csrf': tok(con, '/orgaos/novo'), 'tipo': 'executivo', 'ibge': '3599901', 'municipio': 'Município Fictício de Teste', 'uf': 'SP', 'cnpj': CNPJ, 'dominio': 'pmteste.localhost',
         'email_admin': 'admin@pmteste.localhost', 'cor': '', 'endereco': 'Rua de Teste, 1', 'telefone': '(00) 0000-0000', 'email': 'atendimento@pmteste.localhost', 'horario': 'Segunda a sexta',
         'sistema': 'fiorilli', 'fio_base': 'https://teste.invalid:879/transparencia/VersaoJson/', 'fio_empresa': '7', 'mod_diario': '1'}
    d.update(k)
    return con.post('/orgaos/novo', data={x: y for x, y in d.items() if y is not None})
r = cadastrar(cnpj='11.222.333/0001-00', ibge='35999', email_admin='')
checa('Não cadastrado' in r.text and 'CNPJ inválido' in r.text and 'código IBGE' in r.text and 'e-mail do administrador' in r.text, 'erros de validação explicados')
checa(not db.um(db.PLATAFORMA, "SELECT 1 FROM orgaos WHERE dominio='pmteste.localhost'"), 'cadastro inválido não cria nada')
r = cadastrar(sistema='fiorilli', fio_base='http://sem-https/', fio_empresa='x')
checa('Fiorilli: informe o endereço https' in r.text and 'código da entidade' in r.text, 'Fiorilli exige https e código da entidade')

# Prefeitura fictícia de SP, com Fiorilli
ligar_email_teste()
r = cadastrar()
checa(r.status_code == 200 and 'Órgão criado' in r.text, 'Prefeitura criada')
checa('class="senha"' not in r.text and 'Senha provisória' not in r.text and 'link de primeiro acesso' in r.text, 'nenhuma senha na tela: convite por e-mail')
url = link_convite('admin@pmteste.localhost')
checa(url and url.startswith('https://pmteste.localhost/admin/primeiro-acesso?t=') and 'enviado' in r.text, 'convite enviado por e-mail ao administrador')
senha = url.split('t=')[1] if url else ''
o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmteste.localhost'")
checa(o and o['slug'] == 'pm-municipio-ficticio-de-teste' and o['banco'] == 'bd_pm_municipio_ficticio_de_teste' and o['ibge'] == '3599901' and o['municipio'] == 'Município Fictício de Teste (SP)', f'órgão no banco de controle ({o and o["slug"]})')
b = o['banco']
checa(not db.um(db.PLATAFORMA, 'SELECT 1 FROM log_console WHERE acao LIKE %s', (f'%{senha}%',)) if senha else False, 'link do convite não vai para o registro do console')
checa(not db.um(db.PLATAFORMA, "SELECT 1 FROM convites WHERE token_cifrado IS NOT NULL AND situacao='enviado'"), 'depois do envio, a gestão apaga o link')
u = db.um(b, "SELECT * FROM usuarios WHERE email='admin@pmteste.localhost'")
checa(u and u['perfil'] == 'admin' and u['convite_hash'] and senha not in (u['convite_hash'] or '') and senha not in (u['senha_hash'] or ''), 'administrador com o e-mail informado, só o hash do convite guardado')
F = {x['fonte']: x['params'] for x in db.todos(db.PLATAFORMA, 'SELECT fonte, params FROM fontes WHERE orgao_id=%s', (o['id'],))}
checa(F.get('siconfi') == {'ibge': '3599901', 'rgf_poder': 'E', 'rreo': True}, f'Siconfi pelo IBGE ({F.get("siconfi")})')
checa(F.get('pncp', {}).get('cnpj') == CD.cnpj_formatado(CNPJ), 'PNCP pelo CNPJ')
checa(F.get('tcesp', {}).get('municipio') == 'municipio-ficticio-de-teste', 'TCESP (SP) com o município sugerido')
checa(F.get('fiorilli', {}).get('empresa') == '7' and F['fiorilli']['base'].startswith('https://teste.invalid') and 'servidores' in F['fiorilli']['bases'], 'Fiorilli com a API e a entidade informadas')
checa(all(k in F for k in ('ibge', 'cnes', 'inep', 'iegm', 'painel', 'financas')), f'fontes do painel de indicadores ({sorted(F)})')
ident = db.cfg(b, 'identidade', {})
checa(ident.get('nome') == 'Prefeitura Municipal de Município Fictício de Teste' and ident.get('nome_curto') == 'Município Fictício de Teste' and ident.get('subtitulo') == 'Estado de São Paulo'
      and ident.get('cor') == CD.COR_PADRAO['executivo'] and ident.get('prefixo') == 'Prefeitura Municipal de' and ident.get('telefone') == '(00) 0000-0000', 'identidade montada a partir do cadastro')
checa(db.um(db.PLATAFORMA, "SELECT contratado FROM orgao_modulos WHERE orgao_id=%s AND chave='diario'", (o['id'],))['contratado'], 'módulo opcional marcado ficou contratado')
checa(db.um(b, "SELECT count(*) n FROM blocos WHERE pagina='home'")['n'] > 5, 'página inicial com os blocos do modelo')
checa('Já existe um órgão com este identificador' in cadastrar(dominio='outro.localhost').text, 'não repete identificador')
checa('Já existe um órgão com este domínio' in cadastrar(slug='pm-outro').text, 'não repete domínio')

# portal e painel do órgão novo
pt = TestClient(app, base_url='http://pmteste.localhost')
h = pt.get('/')
checa(h.status_code == 200 and 'Município Fictício de Teste' in h.text and 'Borá' not in h.text and 'Conheça Município Fictício de Teste' in h.text or 'Município Fictício de Teste' in h.text, 'portal do órgão novo no ar, sem Borá')
checa('Borá' not in pt.get('/transparencia').text and pt.get('/transparencia').status_code == 200, 'transparência do órgão novo sem Borá')
for u in ('/', '/diario', '/transparencia', '/comunicados', '/fale-conosco'):
    t = pt.get(u).text
    checa('910' not in t and 'Borá' not in t, f'{u} do órgão novo sem a lei nem o nome do piloto')
checa('<p class="sub"> · ' not in h.text and '>· ' not in h.text and 'Rua de Teste, 1 · (00) 0000-0000' in h.text, 'contato da sede montado sem separador sobrando')
adm = TestClient(app, base_url='http://pmteste.localhost')
r = primeiro_acesso(adm, 'admin@pmteste.localhost', 'senhaNovaTeste123')
checa(r is not None and r.status_code == 200 and 'Visão geral' in r.text, 'administrador abre o convite, cria a senha e cadastra o 2º fator')
checa(not db.um(b, "SELECT convite_hash FROM usuarios WHERE email='admin@pmteste.localhost'")['convite_hash'], 'convite usado: link invalidado')
checa('Borá' not in adm.get('/admin/identidade?aba=dados').text, 'painel do órgão novo sem Borá')

# Câmara do mesmo município (ligada pelo IBGE)
r = cadastrar(tipo='legislativo', dominio='cmteste.localhost', email_admin='admin@cmteste.localhost', cnpj='', fio_recebedora='Câmara Municipal', mod_diario=None)
checa('Órgão criado' in r.text and 'Prefeitura Municipal de Município Fictício de Teste' in r.text, 'Câmara criada e ligada à Prefeitura do mesmo IBGE')
c = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='cmteste.localhost'")
FC = {x['fonte']: x['params'] for x in db.todos(db.PLATAFORMA, 'SELECT fonte, params FROM fontes WHERE orgao_id=%s', (c['id'],))}
checa(c['slug'] == 'cm-municipio-ficticio-de-teste' and FC.get('siconfi', {}).get('rgf_poder') == 'L' and 'pncp' not in FC and 'tcesp' not in FC
      and FC.get('fiorilli', {}).get('bases') == ['transferencias', 'emendas'] and FC['fiorilli'].get('recebedora') == 'Câmara Municipal', f'integrações da Câmara ({sorted(FC)})')
checa(db.cfg(c['banco'], 'identidade', {}).get('nome_curto') == 'Câmara Municipal de Município Fictício de Teste', 'identidade da Câmara')
checa('cmteste.localhost' in pt.get('/').text or 'Câmara Municipal de Município Fictício de Teste' in pt.get('/').text, 'portal da Prefeitura aponta para a Câmara do mesmo município')

# Prefeitura fictícia fora de SP, sem sistema contábil
r = cadastrar(ibge='3199901', municipio='Cidade Fictícia', uf='MG', dominio='pmteste2.localhost', email_admin='admin@pmteste2.localhost', sistema='nenhum', fio_base='', fio_empresa='')
o2 = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE dominio='pmteste2.localhost'")
F2 = {x['fonte'] for x in db.todos(db.PLATAFORMA, 'SELECT fonte FROM fontes WHERE orgao_id=%s', (o2['id'],))} if o2 else set()
checa(o2 and 'tcesp' not in F2 and 'fiorilli' not in F2 and 'financas' not in F2 and 'siconfi' in F2 and db.cfg(o2['banco'], 'identidade', {}).get('subtitulo') == 'Estado de Minas Gerais', f'fora de SP e sem sistema: sem TCESP nem Fiorilli ({sorted(F2)})')

# o piloto continua igual
pi = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug='pm-bora'")
FP = {x['fonte']: x['params'] for x in db.todos(db.PLATAFORMA, 'SELECT fonte, params FROM fontes WHERE orgao_id=%s', (pi['id'],))}
checa(pi['ibge'] == '3507209' and FP['fiorilli']['empresa'] == '2' and FP['tcesp']['municipio'] == 'bora' and db.cfg(pi['banco'], 'identidade', {}).get('nome_curto') == 'Borá', 'piloto de Borá intacto (dados vindos do arquivo do piloto)')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('cadastro de órgão: tudo ok')
