# Pedido de 16/11/2026: rodapé com imagem de fundo, camada da cor do rodapé com transparência, mascote (lado, tamanho,
# transparência, celular, período eleitoral), cor do rodapé editável no Tema e "Remover imagem"/"Restaurar a anterior" em toda a Identidade.
# Imagens geradas no teste (cores lisas), nada real. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_rodape.py
import io, os, re, sys
from datetime import timedelta
from pathlib import Path
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, config, rodape as ROD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
def cli(host='pmbora.localhost'):
    return TestClient(app, base_url=f'http://{host}')
def img(w=400, h=240, cor=(40, 60, 80), fmt='PNG'):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), cor).save(b, fmt); return b.getvalue()
def post(c, url, dados, de=None, files=None):
    return c.post(url, data=dict({'csrf': tok(c, de or url)}, **dados), files=files, follow_redirects=True)
def msg(r):
    m = re.search(r'class="msg"[^>]*>(.*?)</', r.text, re.S)
    return m.group(1) if m else ''
def rodape_html(c):
    t = c.get('/').text
    return t[t.index('<footer'):t.index('</footer>')]
def ident(b=PM):
    return db.cfg(b, 'identidade', {}) or {}
def midia(c, uso, arquivo=None, **dados):
    files = {'arquivo': ('a.png', arquivo, 'image/png')} if arquivo else None
    return post(c, '/admin/identidade/midia', dict({'uso': uso, 'alt': '', 'credito': 'Teste (imagem gerada)'}, **dados), '/admin/identidade?aba=imagens', files)
def aud(txt, b=PM):
    return db.um(b, 'SELECT count(*) n FROM auditoria WHERE acao LIKE %s', (f'%{txt}%',))['n']
def rodape_form(**k):
    base = {'camada': '85', 'mascote_exibir': '1', 'mascote_lado': 'esq', 'mascote_altura': '220', 'mascote_opacidade': '100', 'mascote_suspender_eleitoral': '1'}
    base.update({a: str(b) for a, b in k.items() if b is not None})
    return {a: b for a, b in base.items() if b != ''}
PASTA = Path(config.DADOS_DIR) / db.um('plataforma', "SELECT slug FROM orgaos WHERE banco=%s", (PM,))['slug'] / 'midia'

adm = cli(); entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
pub = cli()

# 1) padrão: rodapé igual ao de antes (sem style no footer, sem fundo, sem mascote, camada sólida) e padrões gravados pela migração
ft = rodape_html(pub)
checa('<footer class="rodape" id="rodape" tabindex="-1">' in ft, 'padrão: footer sem cores sobrescritas')
checa('f2-fundo' not in ft and 'f2-masc' not in ft, 'padrão: sem imagem de fundo e sem mascote')
checa('--rodape-camada:1;' in ft and 'class="f2-camada"' in ft, 'padrão: camada sólida')
checa('f-mascote' not in ft, 'mascote fora da faixa do nome')
checa((db.cfg(PM, 'rodape') or {}).get('camada') == 85 and (db.cfg(CM, 'rodape') or {}).get('mascote_suspender_eleitoral') is True, 'migração 036: padrões gravados')
checa(ROD.cor_de({}, 'executivo') == '#17212B' and ROD.cor_de({}, 'legislativo') == '#16291A', 'cores padrão de hoje')
checa(ROD.tons('#17212B')['f1'] == '#1E2B37' and ROD.tons('#16291A')['f4'] == '#0F1F12', 'tons padrão idênticos aos de antes')
checa('href="/static/favicon-padrao.svg"' in pub.get('/').text, 'sem favicon: ícone padrão da plataforma')

# 2) CSS: ordem das camadas, mascote sem cliques, alto contraste, prefers-contrast e impressão
css = pub.get('/static/portal.css').text
def z(sel):
    m = re.search(re.escape(sel) + r'\{[^}]*z-index:(\d)', css); return int(m.group(1)) if m else -1
checa(z('.f2-fundo') == 0 and z('.f2-camada') == 1 and z('.f2-masc') == 2 and z('.f2-faixa>.f2') == 3, 'ordem das camadas (z-index 0..3)')
checa(re.search(r'\.f2-masc\{[^}]*pointer-events:none', css) is not None, 'mascote não intercepta cliques')
checa('background-color:rgb(var(--rod-rgb) / var(--rodape-camada,1))' in css, 'transparência só na camada (nunca nos textos)')
checa('.hc .f2-fundo,.hc .f2-masc{display:none}' in css, 'alto contraste esconde fundo e mascote')
checa(re.search(r'@media \(prefers-contrast:more\)\{\.f2-fundo,\.f2-masc\{display:none\}', css) is not None, 'prefers-contrast esconde fundo e mascote')
checa(re.search(r'@media print\{\.f2-fundo,\.f2-masc\{display:none\}', css) is not None, 'impressão esconde fundo e mascote')

# 3) cor do rodapé editável no Tema (sem código); recusa sem contraste AA; volta ao padrão
tema = adm.get('/admin/identidade?aba=tema').text
checa('name="cor_rodape"' in tema and 'value="#17212B"' in tema and 'class="pv-rod"' in tema, 'Tema: campo e prévia da cor do rodapé')
cores = {'cor': '#0E4D64', 'cor_destaque': '#F0B429', 'largura': '1760'}
r = post(adm, '/admin/identidade/cores', dict(cores, cor_rodape='#E8EEF2'), '/admin/identidade?aba=tema')
checa('Recusado' in msg(r) and 'rodapé' in msg(r) and not ident().get('cor_rodape'), f'cor clara recusada: {msg(r)}')
r = post(adm, '/admin/identidade/cores', dict(cores, cor_rodape='#1B2A4A'), '/admin/identidade?aba=tema')
checa(ident().get('cor_rodape') == '#1B2A4A', f'cor escura aceita: {msg(r)}')
ft = rodape_html(pub)
checa('style="--rod:#1B2A4A;--rod-rgb:27 42 74;' in ft, 'portal: footer com a cor escolhida')
checa(aud('rodapé #17212B → #1B2A4A') == 1, 'auditoria da cor do rodapé')
r = post(adm, '/admin/identidade/cores', dict(cores, cor_rodape='#1B2A4A', rodape_padrao='1'), '/admin/identidade?aba=tema')
checa(ident().get('cor_rodape') == '' and rodape_html(pub).startswith('<footer class="rodape" id="rodape" tabindex="-1">'), 'voltar à cor padrão')

# 4) seção Rodapé no painel, sem imagem e sem mascote: deslizante da camada desativado, controles do mascote desativados
im = adm.get('/admin/identidade?aba=imagens').text
checa('id="rodape"' in im and 'Prévia ao vivo' in im and 'id="rod-pv"' in im, 'painel: seção Rodapé com prévia')
checa(re.search(r'id="r-cam"[^>]*disabled', im) is not None and 'Sem imagem de fundo, a cor é sólida.' in im, 'sem fundo: camada desativada (cor sólida)')
checa('Envie um mascote' in im and re.search(r'id="r-alt"[^>]*disabled', im) is not None, 'sem mascote: controles desativados')
checa('Fundo do rodapé' in im, 'cartão "Fundo do rodapé" na grade')

# 5) fundo do rodapé: WebP 1920 e 960, trecho mais claro medido, imagem decorativa, carregamento preguiçoso
r = midia(adm, 'rodape', img(2400, 1200, (30, 40, 30)), decorativa='1')
f = ident().get('rodape') or {}
checa(f.get('url', '').endswith('.webp') and f.get('url_960', '').endswith('.webp') and f.get('decorativa') is True, f'fundo: versões WebP e decorativa: {f}')
from PIL import Image
checa(Image.open(PASTA / f['url'][7:]).width == 1920 and Image.open(PASTA / f['url_960'][7:]).width == 960, 'larguras 1920 e 960')
m2 = ROD.minimo_seguro('#17212B', f['lum95'], 'executivo')
checa(f.get('lum95') is not None and m2 <= 40, f'imagem escura: mínimo baixo ({m2}%, lum95 {f.get("lum95")})')
ft = rodape_html(pub)
checa(re.search(r'<img class="f2-fundo" src="/midia/[0-9a-f]{32}\.webp" srcset="[^"]+960w, [^"]+1920w" sizes="100vw" alt="" aria-hidden="true" loading="lazy" decoding="async"', ft) is not None, 'portal: <img> de fundo decorativo e preguiçoso')
r = post(adm, '/admin/identidade/rodape', rodape_form(camada=60), '/admin/identidade?aba=imagens')
checa(ROD.conf(PM)['camada'] == 60 and 'Rodapé salvo' in msg(r), f'camada 60% aceita com imagem escura: {msg(r)}')
checa('--rodape-camada:0.6;' in rodape_html(pub), 'portal: camada 60%')
# troca por imagem clara: a camada sobe sozinha para o mínimo seguro (nunca fica publicada abaixo de AA)
r = midia(adm, 'rodape', img(1000, 600, (240, 240, 240)), decorativa='1')
mi = ROD.minimo_seguro('#17212B', ident()['rodape']['lum95'], 'executivo')
checa(mi > 60 and ROD.conf(PM)['camada'] == mi and f'{mi}%' in msg(r), f'imagem clara: camada sobe para o mínimo seguro ({mi}%): {msg(r)}')
r = post(adm, '/admin/identidade/rodape', rodape_form(camada=mi - 5), '/admin/identidade?aba=imagens')
checa('Recusado' in msg(r) and ROD.conf(PM)['camada'] == mi, f'abaixo do contraste mínimo: recusado: {msg(r)}')
checa(aud('Rodapé: camada') >= 1, 'auditoria das mudanças do rodapé')

# 6) mascote: só no rodapé; esquerda/direita, tamanho, transparência, celular; aria-hidden e sem alt
midia(adm, 'mascote', img(200, 260, (60, 120, 80)), alt='Mascote de teste')
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi, mascote_altura=260, mascote_opacidade=50), '/admin/identidade?aba=imagens')
ft = rodape_html(pub)
checa('<div class="f2-masc esq" aria-hidden="true"><div class="int"><img src="/midia/' in ft and 'alt="" loading="lazy"' in ft, 'mascote à esquerda, decorativo')
checa('--masc-alt:260px;--masc-op:0.5' in ft, 'tamanho e transparência do mascote')
c = ROD.conf(PM)
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi, mascote_lado='dir', mascote_celular='1'), '/admin/identidade?aba=imagens')
ft = rodape_html(pub)
checa('class="f2-masc dir cel"' in ft and 'com-masc-cel' in ft, 'mascote à direita e no celular')
checa('f-mascote' not in pub.get('/').text and pub.get('/').text.count(ident()['mascote']['url']) == 1, 'mascote aparece só no rodapé')
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi, mascote_exibir=''), '/admin/identidade?aba=imagens')
checa('f2-masc' not in rodape_html(pub) and ident()['mascote'].get('url'), 'exibir desligado: some do rodapé sem apagar a imagem')
checa(ROD.validar({'camada': '999', 'mascote_altura': '5', 'mascote_opacidade': '-3'}) ['camada'] == 100 and ROD.validar({'mascote_altura': '5'})['mascote_altura'] == ROD.ALTURA_MIN, 'limites dos controles')

# 7) período eleitoral: suspender (padrão ligado) tira o mascote; desligado mantém
hoje = config.hoje()
db.set_cfg(PM, 'eleicao', dict(db.cfg(PM, 'eleicao', {}) or {}, inicio=(hoje - timedelta(days=1)).isoformat(), fim=(hoje + timedelta(days=1)).isoformat()))
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi), '/admin/identidade?aba=imagens')
checa('f2-masc' not in rodape_html(pub), 'defeso: mascote suspenso (padrão)')
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi, mascote_suspender_eleitoral=''), '/admin/identidade?aba=imagens')
checa('f2-masc' in rodape_html(pub), 'defeso: com a chave desligada o mascote aparece')
db.set_cfg(PM, 'eleicao', dict(db.cfg(PM, 'eleicao', {}) or {}, inicio='2028-07-01', fim='2028-10-01'))
post(adm, '/admin/identidade/rodape', rodape_form(camada=mi), '/admin/identidade?aba=imagens')

# 8) remover e restaurar em todas as imagens da Identidade: só desvincula, arquivo e biblioteca ficam; fallback sem <img> quebrada
for uso in ('brasao', 'hero', 'login', 'sede', 'mascote', 'rodape'):
    if uso not in ('mascote', 'rodape'):
        midia(adm, uso, img(300, 200, (20, 70, 90)))
    atual = (ident().get('sede') or {}).get('foto') if uso == 'sede' else ident().get(uso)
    url = atual['url']
    tela = adm.get(f'/admin/identidade?aba=imagens&uso={uso}').text
    checa('Remover imagem' in tela and 'O portal ficará sem esta imagem. O arquivo continua na biblioteca de mídia e pode ser reutilizado.' in tela, f'{uso}: botão Remover com confirmação')
    r = midia(adm, uso, acao='remover')
    depois = (ident().get('sede') or {}).get('foto') if uso == 'sede' else ident().get(uso)
    checa(depois is None and (PASTA / url[7:]).is_file() and db.um(PM, 'SELECT count(*) n FROM midias WHERE arquivo=%s', (url[7:],))['n'] >= (0 if uso == 'rodape' else 1),
          f'{uso}: removida só da configuração (arquivo e biblioteca ficam)')
    for pg in ('/', '/fale-conosco'):
        rp = pub.get(pg)
        checa(rp.status_code == 200 and url not in rp.text, f'{uso}: {pg} sem a imagem removida ({rp.status_code})')
    if uso == 'login':
        rl = cli().get('/admin/login'); checa(rl.status_code == 200 and url not in rl.text and 'com-foto' not in rl.text, 'login: sem fundo, cor sólida')
    if uso == 'brasao':
        checa('class="selo"' in pub.get('/').text and 'class="f-bras"' not in pub.get('/').text, 'sem brasão: só o nome (selo com iniciais no cabeçalho)')
    if uso == 'rodape':
        checa('f2-fundo' not in rodape_html(pub) and '--rodape-camada:1;' in rodape_html(pub), 'sem fundo do rodapé: cor sólida')
    if uso == 'mascote':
        checa('f2-masc' not in rodape_html(pub), 'sem mascote: rodapé sem mascote')
        checa('Envie um mascote' in adm.get('/admin/identidade?aba=imagens').text, 'sem mascote: nota no painel')
    checa(aud(f'Removeu a imagem: ') >= 1, f'{uso}: auditoria da remoção')
    tela = adm.get(f'/admin/identidade?aba=imagens&uso={uso}').text
    checa('Restaurar a anterior' in tela, f'{uso}: botão Restaurar a anterior')
    r = midia(adm, uso, acao='restaurar')
    volta = (ident().get('sede') or {}).get('foto') if uso == 'sede' else ident().get(uso)
    checa(volta and volta['url'] == url, f'{uso}: anterior restaurada: {msg(r)}')
checa(aud('Restaurou a imagem anterior') >= 6, 'auditoria das restaurações')
# trocar também guarda a anterior
u1 = ident()['brasao']['url']; midia(adm, 'brasao', img(310, 200, (90, 20, 20)))
midia(adm, 'brasao', acao='restaurar'); checa(ident()['brasao']['url'] == u1, 'troca guarda a anterior para restaurar')

# favicon: remover (volta ao padrão da plataforma) e restaurar
r = adm.post('/admin/identidade/favicon', data={'csrf': tok(adm, '/admin/identidade?aba=favicon'), 'acao': 'enviar'}, files={'png': ('f.png', img(512, 512, (14, 77, 100)), 'image/png')}, follow_redirects=True)
fav = ident().get('favicon'); checa(fav and fav.get('32'), 'favicon enviado')
checa('Remover favicon' in adm.get('/admin/identidade?aba=favicon').text, 'favicon: botão Remover com confirmação')
r = post(adm, '/admin/identidade/favicon', {'acao': 'remover'}, '/admin/identidade?aba=favicon')
checa(not ident().get('favicon') and 'favicon-padrao.svg' in pub.get('/').text and (PASTA / fav['32'][7:]).is_file(), 'favicon removido: padrão neutro; arquivos ficam')
r = post(adm, '/admin/identidade/favicon', {'acao': 'restaurar'}, '/admin/identidade?aba=favicon')
checa((ident().get('favicon') or {}).get('32') == fav['32'] and fav['32'] in pub.get('/').text, 'favicon anterior restaurado')

# 9) arquivo sumido (cópia de banco sem a pasta de mídia): nunca <img> quebrada
i = ident(); i['brasao'] = {'url': '/midia/' + 'f' * 32 + '.png', 'alt': ''}; db.set_cfg(PM, 'identidade', i)
t = pub.get('/').text
checa(('/midia/' + 'f' * 32) not in t and 'class="selo"' in t, 'brasão com arquivo ausente não vira <img> quebrada (fallback: selo)')
checa(pub.get('/').status_code == 200, 'sem erro 500')

# 10) Câmara: mesmo código, cor padrão própria, sem imagens
ftc = rodape_html(cli('cmbora.localhost'))
checa('<footer class="rodape" id="rodape" tabindex="-1">' in ftc and 'f2-fundo' not in ftc, 'Câmara: rodapé padrão (verde de sempre)')
cmadm = cli('cmbora.localhost'); entrar(cmadm, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
checa('value="#16291A"' in cmadm.get('/admin/identidade?aba=tema').text, 'Câmara: cor padrão do rodapé no Tema')

# 11) sem permissão de configuração: não salva
ed_email = 'ed-rod@teste.localhost'
post(adm, '/admin/usuarios', {'acao': 'novo', 'nome': 'Editor Rodapé Teste', 'email': ed_email, 'perfil': 'editor', 'senha': 'provisoria123'})
ed = cli(); entrar(ed, ed_email, 'provisoria123', 'senhaforte123')
antes = ROD.conf(PM)
r = ed.post('/admin/identidade/rodape', data={'csrf': tok(ed, '/admin'), 'camada': '100'}, follow_redirects=False)
checa(r.status_code in (403, 303) and ROD.conf(PM) == antes, f'editor não muda o rodapé ({r.status_code})')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
