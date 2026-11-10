# Painel reorganizado (10/11/2026): menu por tarefa, padrão "lista → tela de edição", Identidade dividida, Conheça reunido,
# retorno seguro ("volta"), nenhum formulário dentro de formulário e tela de login.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_painel_admin.py
import os, re, sys
from html.parser import HTMLParser
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.web import volta_segura
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def cli(host):
    return TestClient(app, base_url=f'http://{host}')
pm, cm = cli('pmbora.localhost'), cli('cmbora.localhost')

class Aninhado(HTMLParser):
    """Conta <form> aberto dentro de outro <form> (o navegador fecharia o de fora antes da hora)."""
    def __init__(self):
        super().__init__(); self.n = 0; self.max = 0
    def handle_starttag(self, t, a):
        if t == 'form':
            self.n += 1; self.max = max(self.max, self.n)
    def handle_endtag(self, t):
        if t == 'form':
            self.n = max(0, self.n - 1)
def sem_aninhado(html, nome):
    p = Aninhado(); p.feed(html); checa(p.max <= 1, f'{nome}: formulário dentro de formulário')

# ---------- login ----------
r = pm.get('/admin/login')
checa('Área restrita' in r.text and 'Entrar no painel' in r.text and 'Voltar ao portal' in r.text, 'login: rótulo, título e "Voltar ao portal"')
checa(r.text.count('Prefeitura Municipal de Borá') <= 2, 'login: nome do órgão sem repetição no corpo')  # <title> + marca
checa(entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123').status_code == 200, 'login da Prefeitura')
checa(entrar(cm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123').status_code == 200, 'login da Câmara')

# ---------- menu por tarefa ----------
h = pm.get('/admin/').text
menu = h[h.find('id="menu-painel"'):h.find('</nav>', h.find('id="menu-painel"'))]
grupos = re.findall(r'<summary>([^<]+)</summary>', menu)
checa(grupos == ['Publicar', 'Cidade', 'Atendimento', 'Transparência', 'Aparência do portal', 'Administração'] or grupos == ['Publicar', 'Cidade', 'Atendimento', 'Aparência do portal', 'Administração'], f'Prefeitura: grupos do menu {grupos}')
for rot in ('Notícias e páginas', 'Comunicados', 'Conheça Borá', 'Fotos e álbuns', 'e-SIC e Ouvidoria', 'Página inicial (blocos)', 'Menus e atalhos', 'Identidade visual', 'Dados do órgão', 'Usuários e perfis'):
    checa(f'<span>{rot}</span>' in menu, f'Prefeitura: item "{rot}" no menu')
checa('banco bd_pm_bora' not in h[:h.find('<main')], 'topo sem domínio/banco')
checa('class="btn-menu"' in h and 'Ver portal' in h, 'botão Menu (celular) e "Ver portal"')
hc = cm.get('/admin/').text
mc = hc[hc.find('id="menu-painel"'):hc.find('</nav>', hc.find('id="menu-painel"'))]
checa('<summary>Legislativo</summary>' in mc and '<span>Vereadores e Mesas</span>' in mc and '<span>Enviar ao Diário</span>' in mc and 'Cidade' not in mc, 'Câmara: grupo Legislativo e itens próprios')

# ---------- padrão lista → tela de edição ----------
for u, novo in (('/admin/comunicados', 'Novo comunicado'), ('/admin/conheca', 'Novo perfil'), ('/admin/usuarios', 'Novo usuário'), ('/admin/carta-secretarias', 'Nova secretaria'),
                ('/admin/diario', 'Enviar ato'), ('/admin/identidade?aba=fotos', 'Novo álbum')):
    t = pm.get(u).text
    m = t[t.find('<main'):]
    checa(f'+ {novo}' in m and 'method="post"' not in m[:m.find('+ ' + novo)], f'{u}: botão "+ {novo}" no cabeçalho, antes de qualquer formulário')
    alvo = re.search(r'href="([^"]+)">\+ ' + re.escape(novo), m)
    if alvo:
        t2 = pm.get(alvo.group(1).replace('&amp;', '&')).text
        checa('class="voltar"' in t2 and 'method="post"' in t2, f'{u}: tela de criação com "Voltar" e formulário')
        sem_aninhado(t2, alvo.group(1))
for u, novo in (('/admin/sessoes', 'Nova sessão'), ('/admin/remessas', 'Nova remessa'), ('/admin/diarias', 'Novo lançamento'), ('/admin/contas', 'Novo exercício'), ('/admin/transmissoes', 'Agendar transmissão')):
    t = cm.get(u).text; m = t[t.find('<main'):]
    checa(f'+ {novo}' in m, f'Câmara {u}: botão "+ {novo}"')
    sem_aninhado(cm.get(u + '?novo=1').text, f'Câmara {u}?novo=1')
sem_aninhado(pm.get('/admin/conteudos/novo').text, 'novo conteúdo')
checa(not re.search(r'<form\s', Path(__file__).resolve().parent.parent.joinpath('app/templates/partials/editor.html').read_text()), 'editor sem <form> interno')

# ---------- Identidade dividida e Conheça reunido ----------
for aba, h1 in (('tema', 'Identidade visual'), ('imagens', 'Identidade visual'), ('favicon', 'Identidade visual'), ('dados', 'Dados do órgão'), ('redes', 'Dados do órgão'),
                ('conheca', 'Conheça Borá'), ('municipio', 'Conheça Borá'), ('fotos', 'Fotos e álbuns')):
    t = pm.get(f'/admin/identidade?aba={aba}').text
    checa(re.search(r'<h1>\s*' + re.escape(h1), t), f'identidade aba {aba}: título "{h1}"')
t = pm.get('/admin/identidade?aba=dados').text
checa('conheca_titulo' not in t and 'Proteção de dados (LGPD)' in t, 'Dados do órgão sem o bloco do Conheça, com grupos de campos')
t = pm.get('/admin/identidade?aba=conheca').text
checa('name="conheca_titulo"' in t and 'Fotos do bloco' in t and 'href="/admin/conheca"' in t, 'Conheça: texto do bloco, fotos e aba Perfis')
checa('uso=conheca' not in pm.get('/admin/identidade?aba=imagens').text, 'fotos do Conheça fora de "Brasão, mascote e fundos"')
r = pm.post('/admin/identidade', data={'csrf': tok(pm, '/admin/identidade?aba=conheca'), 'volta': '/admin/identidade?aba=conheca', 'conheca_titulo': 'Título de teste', 'conheca_rotulo': 'Conheça', 'conheca_texto': 'Texto de teste.'}, follow_redirects=False)
checa(r.headers.get('location', '').endswith('/admin/identidade?aba=conheca'), 'salvar o bloco volta para a tela do Conheça')
nome_antes = pm.get('/admin/identidade?aba=dados').text
checa('Prefeitura Municipal de Borá' in nome_antes, 'salvar só o bloco não apaga os dados do órgão')

# ---------- retorno seguro ----------
for v, ok_ in (('/admin/identidade?aba=conheca', True), ('https://exemplo.com/', False), ('//exemplo.com/admin/', False), ('/admin/../x', False), ('/portal', False), ('/admin/menus?aba=links', True)):
    checa((volta_segura({'volta': v}, 'PADRAO') == v) == ok_, f'volta_segura({v!r})')

# ---------- menus em abas; organograma em aba ----------
t = pm.get('/admin/menus?aba=atalhos').text
checa('Acesso direto' in t and 'Itens da barra' not in t, 'Menus: uma seção por aba')
r = pm.post('/admin/menus', data={'csrf': tok(pm, '/admin/menus'), 'acao': 'aviso', 'texto': '', 'link': '', 'ate': ''}, follow_redirects=False)
checa('aba=' in r.headers.get('location', '') or r.status_code == 303, 'Menus: salvar volta para a aba')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('painel admin: tudo ok')
