# Anexos dos comunicados (10/11/2026): PDF, imagens, DOCX/XLSX/ODT/ODS e CSV, com tipo conferido pelo conteúdo.
# Só contra banco de TESTE recém-provisionado:  PYTHONPATH=. python tests/teste_anexos.py
import io, os, re, sys, zipfile
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, anexos as AX
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
def zipb(arqs):
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        for n, t in arqs.items():
            z.writestr(n, t)
    return b.getvalue()

PDF = b'%PDF-1.4\n% teste\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64
DOCX = zipb({'[Content_Types].xml': '<x/>', 'word/document.xml': '<w/>'})
XLSX = zipb({'[Content_Types].xml': '<x/>', 'xl/workbook.xml': '<w/>'})
ODT = zipb({'mimetype': 'application/vnd.oasis.opendocument.text', 'content.xml': '<x/>'})
DOCM = zipb({'[Content_Types].xml': '<x/>', 'word/document.xml': '<w/>', 'word/vbaProject.bin': 'macro'})
CSV = 'item;quantidade;valor\nCaneta;10;2,50\n'.encode('utf-8')

# ---------- detecção pelo conteúdo ----------
for dados, nome, ext in ((PDF, 'a.pdf', 'pdf'), (PNG, 'a.png', 'png'), (b'\xff\xd8\xff\xe0' + b'0' * 20, 'a.jpg', 'jpg'), (DOCX, 'a.docx', 'docx'), (XLSX, 'a.xlsx', 'xlsx'), (ODT, 'a.odt', 'odt'), (CSV, 'a.csv', 'csv'),
                        (PDF, 'disfarçado.png', 'pdf')):
    checa(AX.detectar(dados, nome) == ext, f'detecta {nome} como {ext}')
for dados, nome, msg in ((b'MZ\x90\x00' + b'0' * 50, 'programa.pdf', 'Formato não aceito'), (zipb({'a.txt': 'x'}), 'pacote.zip', 'compactado'), (DOCM, 'macro.docx', 'macro'),
                         (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'0' * 50, 'velho.doc', 'antigo'), (b'<html><script>x</script>', 'pagina.csv', 'não é um CSV'), (b'', 'vazio.pdf', 'vazio'),
                         (b'%PDF-' + b'0' * (AX.LIMITE + 1), 'grande.pdf', '20 MB')):
    try:
        AX.detectar(dados, nome); erros.append(f'devia recusar {nome}')
    except ValueError as e:
        checa(msg in str(e), f'{nome}: mensagem clara ({e})')

# ---------- painel ----------
pm = TestClient(app, base_url='http://pmbora.localhost')
entrar(pm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
r = pm.post('/admin/comunicados', data={'csrf': tok(pm, '/admin/comunicados'), 'acao': 'salvar', 'tipo': 'Edital de chamamento', 'classe': 'util', 'titulo': 'Edital de teste com anexos', 'texto': 'Texto de teste.', 'publicado_em': '2026-11-09T09:00'}, follow_redirects=True)
if 'Edital de chamamento' not in r.text:  # tipo pode não existir no banco de teste
    r = pm.post('/admin/comunicados', data={'csrf': tok(pm, '/admin/comunicados'), 'acao': 'salvar', 'tipo': 'Aviso', 'classe': 'util', 'titulo': 'Edital de teste com anexos', 'texto': 'Texto de teste.', 'publicado_em': '2026-11-09T09:00'}, follow_redirects=True)
cid = int(re.search(r'/admin/comunicados\?id=(\d+)', str(r.url)).group(1))
U = f'/admin/comunicados?id={cid}'
checa('Anexar arquivo' in pm.get(U).text, 'tela de edição com "Anexar arquivo"')
checa('Salve o comunicado primeiro' in pm.get('/admin/comunicados?novo=1').text, 'tela de novo pede para salvar antes de anexar')
def enviar(nome, dados, titulo):
    return pm.post('/admin/comunicados', data={'csrf': tok(pm, U), 'acao': 'anexo', 'id': cid, 'titulo_anexo': titulo}, files={'arquivo': (nome, dados)}, follow_redirects=True)
for nome, dados, titulo in (('edital.pdf', PDF, 'Edital completo'), ('foto.png', PNG, 'Local da reunião'), ('modelo.docx', DOCX, 'Modelo de proposta'), ('precos.xlsx', XLSX, 'Anexo I — Planilha de preços'), ('itens.csv', CSV, 'Lista de itens')):
    r = enviar(nome, dados, titulo)
    checa('Anexo enviado' in r.text, f'envia {nome}')
r = enviar('macro.docx', DOCM, 'Com macro'); checa('Anexo não enviado' in r.text and 'macro' in r.text, 'recusa documento com macro')
r = enviar('programa.pdf', b'MZ\x90\x00' + b'0' * 50, 'Programa'); checa('Anexo não enviado' in r.text, 'recusa executável disfarçado de PDF')
r = enviar('edital2.pdf', PDF, ''); checa('Anexo não enviado' in r.text and 'O que é' not in r.text or 'Escreva o que é o arquivo' in r.text, 'exige a descrição do arquivo')
ax = db.todos('bd_pm_bora', 'SELECT * FROM comunicado_anexos WHERE comunicado_id=%s ORDER BY id', (cid,))
checa([a['ext'] for a in ax] == ['pdf', 'png', 'docx', 'xlsx', 'csv'], f'5 anexos gravados com o tipo real ({[a["ext"] for a in ax]})')
checa(all(re.match(r'^[0-9a-f]{32}\.\w+$', a['arquivo']) for a in ax) and ax[0]['nome_original'] == 'edital.pdf', 'nome interno aleatório e nome original guardado')
checa(db.um('bd_pm_bora', "SELECT 1 FROM auditoria WHERE acao LIKE %s", (f'Comunicado {cid}: anexo enviado%',)), 'envio registrado na auditoria')
t = pm.get(U).text
checa('Edital completo' in t and 'planilha Excel (XLSX)' in t and 'Remover' in t, 'tela lista os anexos com tipo e "Remover"')
checa(re.search(rf'<td>{cid}|Anexos', pm.get('/admin/comunicados').text), 'lista do painel com a coluna Anexos')

# ---------- portal ----------
anon = TestClient(app, base_url='http://pmbora.localhost')
pdf = ax[0]['arquivo']
checa(anon.get(f'/anexo/{pdf}').status_code == 404, 'rascunho: anexo não sai para o público')
checa(pm.get(f'/anexo/{pdf}').status_code == 200, 'rascunho: o painel do órgão pré-visualiza')
pm.post('/admin/comunicados', data={'csrf': tok(pm, '/admin/comunicados'), 'acao': 'situacao', 'id': cid, 'situacao': 'publicado'})
r = anon.get(f'/anexo/{pdf}')
checa(r.status_code == 200 and r.content == PDF and r.headers['content-type'].startswith('application/pdf') and r.headers.get('x-content-type-options') == 'nosniff' and 'inline' in r.headers.get('content-disposition', ''), 'publicado: PDF abre no navegador, com nosniff')
r = anon.get(f"/anexo/{ax[2]['arquivo']}")
checa(r.status_code == 200 and 'attachment' in r.headers.get('content-disposition', '') and 'Modelo-de-proposta.docx' in r.headers.get('content-disposition', ''), 'DOCX vem para baixar, com nome legível')
for ruim in ('../../etc/passwd', '%2e%2e%2fsegredo', 'abc.exe', pdf.replace('.pdf', '.exe'), '0' * 32 + '.pdf'):
    checa(anon.get(f'/anexo/{ruim}').status_code == 404, f'endereço inválido dá 404: {ruim}')
p = anon.get(f'/comunicados/{cid}').text
checa('Arquivos (5)' in p and 'alt="Local da reunião"' in p and 'Anexo I — Planilha de preços' in p and 'planilha Excel (XLSX)' in p, 'página do comunicado lista os arquivos (imagem com texto alternativo)')
checa('5 arquivo(s)' in anon.get('/comunicados').text, 'lista de comunicados mostra a quantidade de arquivos')

# ---------- remover ----------
caminho = AX.pasta(db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE banco='bd_pm_bora'")) / pdf
checa(caminho.is_file(), 'arquivo guardado em anexos/')
r = pm.post('/admin/comunicados', data={'csrf': tok(pm, U), 'acao': 'anexo_remover', 'id': cid, 'anexo_id': ax[0]['id']}, follow_redirects=True)
checa('Anexo removido' in r.text and not caminho.exists() and not db.um('bd_pm_bora', 'SELECT 1 FROM comunicado_anexos WHERE id=%s', (ax[0]['id'],)), 'remover apaga o registro e o arquivo')
checa(anon.get(f'/anexo/{pdf}').status_code == 404, 'anexo removido some do portal')
r = pm.post('/admin/comunicados', data={'csrf': tok(pm, U), 'acao': 'anexo_remover', 'id': cid + 999, 'anexo_id': ax[1]['id']}, follow_redirects=False)
checa(r.status_code == 404 and db.um('bd_pm_bora', 'SELECT 1 FROM comunicado_anexos WHERE id=%s', (ax[1]['id'],)), 'não remove anexo de outro comunicado')
checa(anon.post('/admin/comunicados', data={'acao': 'anexo_remover', 'id': cid, 'anexo_id': ax[1]['id']}, follow_redirects=False).status_code in (302, 303, 400, 401, 403), 'sem login não remove')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('anexos: tudo ok')
