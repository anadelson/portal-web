# Pedido de 15/11/2026: no Diário Oficial o órgão vem de uma lista cadastrada (sem digitação livre) e já vem escolhido;
# texto do ato com editor (formatação) e pré-formatação automática, documento por documento, levada ao PDF da edição;
# alinhamento dos campos dos formulários (caixas de marcar na linha do texto, campos lado a lado na mesma altura).
# Dados FICTÍCIOS. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_diario_orgaos.py
import os, re, sys, tempfile
from datetime import date
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, diario as D, diario_formato as DF
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM = 'bd_pm_bora'
pm = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
def msg(r):
    m = re.search(r'class="msg"[^>]*>(.*?)</', r.text, re.S)
    return m.group(1) if m else ''

# ---------- 1) sem órgão cadastrado: aviso e envio recusado ----------
db.exe(PM, 'DELETE FROM diario_orgaos')
f = pm.get('/admin/diario?novo=1').text
checa('Nenhum órgão cadastrado para o Diário' in f and 'href="/admin/diario/orgaos"' in f, 'sem órgãos: aviso com link para o cadastro')
checa('name="orgao"' not in f and 'name="caderno"' not in f and 'name="orgao_id"' in f, 'órgão em lista (sem campo de digitação) e caderno vindo do órgão')
r = pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario?novo=1'), 'acao': 'novo', 'orgao': 'Gabinete digitado', 'tipo': 'Decreto', 'ementa': 'Recusado (teste)', 'texto': 'Art. 1º Teste.'}, follow_redirects=True)
checa('Escolha o órgão na lista' in r.text and not db.um(PM, "SELECT 1 FROM diario_atos WHERE ementa='Recusado (teste)'"), 'envio sem órgão da lista é recusado')

# ---------- 2) cadastro de órgãos ----------
def org(dados):
    return pm.post('/admin/diario/orgaos', data=dict({'csrf': tok(pm, '/admin/diario/orgaos')}, **dados), follow_redirects=True)
org({'acao': 'novo', 'nome': '  Gabinete   do Prefeito (teste) ', 'sigla': 'GP', 'caderno': 'executivo'})
org({'acao': 'novo', 'nome': 'Secretaria de Administração (teste)', 'caderno': 'executivo'})
org({'acao': 'novo', 'nome': 'Mesa Diretora (teste)', 'caderno': 'legislativo'})
r = org({'acao': 'novo', 'nome': 'Gabinete do Prefeito (teste)', 'caderno': 'executivo'})
checa('Já existe um órgão com esse nome' in r.text, 'nome repetido recusado')
r = org({'acao': 'novo', 'nome': 'ab'})
checa('Informe o nome oficial' in r.text, 'nome curto demais recusado')
g = db.um(PM, "SELECT * FROM diario_orgaos WHERE nome='Gabinete do Prefeito (teste)'")
checa(g and g['sigla'] == 'GP', 'espaços do nome normalizados e sigla gravada')
sa = db.um(PM, "SELECT id FROM diario_orgaos WHERE nome='Secretaria de Administração (teste)'")['id']
md = db.um(PM, "SELECT id FROM diario_orgaos WHERE nome='Mesa Diretora (teste)'")['id']
db.exe(PM, "INSERT INTO secretarias (nome, sigla) VALUES ('Secretaria de Obras (teste)', 'SO') ON CONFLICT DO NOTHING")
t = pm.get('/admin/diario/orgaos').text
checa('Secretaria de Obras (teste)' in t and 'Trazer as secretarias cadastradas' in t, 'oferece trazer as secretarias do cadastro de secretarias')
org({'acao': 'importar'})
checa(db.um(PM, "SELECT 1 FROM diario_orgaos WHERE nome='Secretaria de Obras (teste)' AND sigla='SO' AND caderno='executivo'"), 'secretaria trazida como órgão do Diário')
org({'acao': 'padrao', 'id': sa})
checa(db.um(PM, 'SELECT count(*) n FROM diario_orgaos WHERE padrao')['n'] == 1 and db.um(PM, 'SELECT padrao FROM diario_orgaos WHERE id=%s', (sa,))['padrao'], 'um só órgão padrão')

# ---------- 3) envio: órgão já escolhido, lista agrupada por caderno, editor com pré-formatação ----------
f = pm.get('/admin/diario?novo=1').text
checa(re.search(rf'<option value="{sa}" selected>Secretaria de Administração \(teste\)', f), 'quem nunca enviou: vem escolhido o órgão padrão')
checa('<optgroup label="Poder Executivo">' in f and '<optgroup label="Poder Legislativo">' in f, 'lista agrupada por caderno')
checa('data-preformatar="/admin/diario/preformatar"' in f and 'data-cmd="preformatar"' in f, 'editor do Diário com o botão Pré-formatar')
checa('data-cmd="imagem"' not in f and 'data-cmd="video"' not in f and 'data-cmd="tabela"' in f, 'editor do Diário sem imagem e vídeo (tabela continua)')
html = ('<h3 class="al-centro"><strong>DECRETO Nº 9, DE 6 DE NOVEMBRO DE 2026 (EXEMPLO)</strong></h3><p class="al-just"><strong>Art. 1º</strong> Texto fictício.</p>'
        '<figure><img src="/midia/' + 'a' * 32 + '.png" alt=""></figure><script>alert(1)</script>'
        '<table><thead><tr><th scope="col">Cargo</th><th scope="col">Vagas</th></tr></thead><tbody><tr><td>Exemplo</td><td>1</td></tr></tbody></table>')
r = pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario?novo=1'), 'acao': 'novo', 'orgao_id': md, 'tipo': 'Decreto', 'numero': '9/2026', 'ementa': 'Ato formatado (teste)',
                                       'texto': 'texto simples ignorado', 'html': html}, follow_redirects=True)
a = db.um(PM, "SELECT * FROM diario_atos WHERE ementa='Ato formatado (teste)'")
checa(a and a['orgao'] == 'Mesa Diretora (teste)' and a['orgao_id'] == md and a['caderno'] == 'legislativo', 'nome e caderno vêm do órgão da lista')
checa(a and '<h3 class="al-centro">' in a['html'] and '<table>' in a['html'] and '<script' not in a['html'] and '<img' not in a['html'] and '<figure' not in a['html'], 'HTML limpo no servidor e sem imagem')
checa(a and a['texto'].startswith('DECRETO Nº 9') and 'Art. 1º Texto fictício.' in a['texto'], 'texto simples sai do HTML (busca, legislação)')
f = pm.get('/admin/diario?novo=1').text
checa(re.search(rf'<option value="{md}" selected>', f), 'depois do primeiro envio vem escolhido o último órgão usado pela pessoa')
r = pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario?novo=1'), 'acao': 'novo', 'orgao_id': md, 'tipo': 'Decreto', 'ementa': 'CPF (teste)', 'html': '<p>CPF 123.456.789-09</p>'}, follow_redirects=True)
checa('CPF completo' in r.text and not db.um(PM, "SELECT 1 FROM diario_atos WHERE ementa='CPF (teste)'"), 'CPF completo no texto formatado também é recusado (LGPD)')
# renomear corrige atos pendentes; fora de uso some da lista e é recusado
org({'acao': 'salvar', 'id': md, 'nome': 'Mesa da Câmara (teste)', 'caderno': 'legislativo', 'ativo': '1'})
checa(db.um(PM, 'SELECT orgao FROM diario_atos WHERE id=%s', (a['id'],))['orgao'] == 'Mesa da Câmara (teste)', 'renomear corrige o nome nos atos ainda não certificados')
org({'acao': 'salvar', 'id': md, 'nome': 'Mesa da Câmara (teste)', 'caderno': 'legislativo'})
f = pm.get('/admin/diario?novo=1').text
checa(f'value="{md}"' not in f and re.search(rf'<option value="{sa}" selected>', f), 'órgão fora de uso sai da lista; volta o padrão')
r = pm.post('/admin/diario/ato', data={'csrf': tok(pm, '/admin/diario?novo=1'), 'acao': 'novo', 'orgao_id': md, 'tipo': 'Decreto', 'ementa': 'Inativo (teste)', 'texto': 'Art. 1º X.'}, follow_redirects=True)
checa(not db.um(PM, "SELECT 1 FROM diario_atos WHERE ementa='Inativo (teste)'"), 'órgão fora de uso é recusado no envio')
checa('Órgãos' in pm.get('/admin/diario/config').text and 'href="/admin/diario/orgaos"' in pm.get('/admin/diario').text, 'aba Órgãos nas telas do Diário')

# ---------- 4) pré-formatação ----------
bruto = ('DECRETO Nº 123, DE 6 DE NOVEMBRO DE 2026 (EXEMPLO)\nDispõe sobre o expediente (exemplo).\nO PREFEITO MUNICIPAL, no uso de suas atribuições,\nDECRETA:\n'
         'CAPÍTULO I\nDAS DISPOSIÇÕES GERAIS\nArt 1o - Primeiro.\nArt. 10 – Décimo.\n§1º Parágrafo.\nparagrafo unico: Único.\nI - inciso;\nII- outro;\na) alínea;\n'
         'Registre-se e publique-se.\nPrefeitura Municipal de Borá, 6 de novembro de 2026.\nFULANO DE TAL (EXEMPLO)\nPrefeito Municipal')
p = DF.preformatar(bruto)
for trecho, nome in [('<h3 class="al-centro"><strong>DECRETO Nº 123', 'título centralizado em negrito'), ('<blockquote class="al-just">Dispõe sobre', 'ementa recuada'),
                     ('<p><strong>DECRETA:</strong></p>', 'DECRETA em negrito'), ('<h4 class="al-centro"><strong>CAPÍTULO I</strong></h4><p class="al-centro"><strong>DAS DISPOSIÇÕES GERAIS', 'capítulo e nome centralizados'),
                     ('<strong>Art. 1º</strong> Primeiro.', 'Art. 1º (ordinal até o 9º)'), ('<strong>Art. 10.</strong> Décimo.', 'Art. 10. (cardinal do 10 em diante)'),
                     ('<strong>§ 1º</strong> Parágrafo.', '§ 1º'), ('<strong>Parágrafo único.</strong> Único.', 'Parágrafo único.'), ('<p class="al-just">I – inciso;', 'inciso com travessão'),
                     ('<p class="al-just">II – outro;', 'inciso sem espaço normalizado'), ('<p class="al-just">a) alínea;', 'alínea'), ('<p class="al-just">Registre-se e publique-se.', 'fecho justificado'),
                     ('<p class="al-centro">Prefeitura Municipal de Borá, 6 de novembro de 2026.</p><p class="al-centro"><strong>FULANO DE TAL (EXEMPLO)</strong></p><p class="al-centro">Prefeito Municipal</p>', 'local, data e assinatura centralizados')]:
    checa(trecho in p, f'pré-formatação: {nome}')
checa(DF.preformatar(p) == p, 'pré-formatar duas vezes dá o mesmo resultado')
checa('João' not in p and p.count('<p') + p.count('<h') + p.count('<blockquote') >= 17, 'nada é inventado (só os blocos do texto)')
m = DF.preformatar('<p>Texto com <em>itálico</em> e <a href="https://exemplo.org">link</a> no meio.</p><ul><li>item</li></ul>')
checa('<em>itálico</em>' in m and 'href="https://exemplo.org"' in m and '<ul><li>item</li></ul>' in m, 'formatação no meio do parágrafo, listas e links preservados')
r = pm.post('/admin/diario/preformatar', data={'csrf': tok(pm, '/admin/diario?novo=1'), 'html': '<p>Art 2o teste</p>'})
checa(r.status_code == 200 and '<strong>Art. 2º</strong> teste' in r.json().get('html', ''), 'rota de pré-formatação devolve o HTML ao editor')
an = TestClient(app, base_url='http://pmbora.localhost')
checa(an.post('/admin/diario/preformatar', data={'html': 'x'}, follow_redirects=False).status_code in (303, 307, 403), 'pré-formatação exige login')

# ---------- 5) PDF da edição com o texto formatado ----------
ato = dict(id=999, caderno='executivo', tipo='Decreto', numero='123/2026', orgao='Gabinete do Prefeito (teste)', ementa='Exemplo', texto=DF.editor.texto(p),
           html=p + '<ol><li>um</li><li>dois<ul><li>sub</li></ul></li></ol><hr><p class="al-dir">à direita <sup>2</sup> <s>x</s> <mark>m</mark></p>'
           '<table><thead><tr><th scope="col">Cargo</th><th scope="col">Vagas</th></tr></thead><tbody><tr><td>Exemplo</td><td>1</td></tr></tbody></table>')
with tempfile.TemporaryDirectory() as tmp:
    caminho, sha, cod, pags = D.gerar_pdf({'numero': 1, 'letra': '', 'data': date(2026, 11, 6), 'id': 1}, [ato], {'nome_curto': 'Borá'}, tmp, teste=True)
    import subprocess
    txt = subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=txtwrite', '-sOutputFile=-', caminho], capture_output=True, text=True).stdout
    txt = re.sub(r'\s+', ' ', txt)
    checa('Art. 1º' in txt and 'Parágrafo único.' in txt and 'Vagas' in txt and 'FULANO DE TAL (EXEMPLO)' in txt and 'CAPÍTULO I' in txt, f'PDF da edição com o texto formatado ({txt[:120]!r})')
    checa(pags.get(999) == 2, 'página onde o ato começa continua registrada')

# ---------- 6) alinhamento dos campos (regra geral do painel) ----------
css = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'static', 'admin.css')).read()
checa('input[type=checkbox],input[type=radio]{min-height:0!important' in css, 'caixa de marcar sem a altura mínima dos campos')
checa('label:has(> input:is([type=checkbox],[type=radio])){display:flex;flex-direction:row!important;align-items:flex-start!important' in css, 'caixa de marcar na linha do texto')
checa('.campos-m :is(input:not([type=checkbox],[type=radio]),select,textarea){width:100%' in css, 'largura total só para campos de texto (16/11/2026)')
checa('.grade2>label:not(:has(>input[type=checkbox],>input[type=radio],' in css and 'justify-content:flex-end' in css, 'campos lado a lado na mesma altura')
cf = pm.get('/admin/diario/config').text
checa('<form class="inline" method="post" action="/admin/diario/config"><input type="hidden" name="csrf" value="' not in cf.split('Calendário')[1].split('</section>')[0], 'cadastro de feriado em grade (sem rolagem no celular)')
checa('admin.css?v=31' in cf and 'admin.js?v=9' in cf, 'versões novas do CSS e do JS do painel')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
