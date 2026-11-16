# Pedido de 16/11/2026 (Docs/PEDIDO-DIARIO-CAPA.md): capa nova, miolo em 2 colunas com preenchimento sequencial, caixas de Poder e de tipo,
# linha da MP no rodapé. Atos FICTÍCIOS (marcados EXEMPLO). Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_diario_capa.py
import os, re, subprocess, sys, tempfile
from datetime import date
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from app import diario as D, diario_layout as L, diario_texto as DT

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)

# 1) quebras do texto de origem: junta as linhas do parágrafo, sem mudar uma palavra
orig = """FULANO DE TAL (EXEMPLO), Prefeito Municipal de Exemplo,
Estado de São Paulo, no uso de suas atribuições legais,
RESOLVE:
Art. 1º. Fica nomeada a Sra. Beltrana de Tal (EXEMPLO) para
o conselho municipal de exemplo, por força de eleição
entre seus pares.
Parágrafo único. O mandato é de dois anos.
I - primeiro inciso de exemplo;
II - segundo inciso de exemplo.
Art. 2º. Esta Portaria entra em vigor na data de sua
publicação.
Publique-se
e
Cumpra-se.
Exemplo, 13 de novembro de 2026.
FULANO DE TAL (EXEMPLO)
PREFEITO MUNICIPAL
Registrada nesta Secretaria em livro próprio, na data
supra e publicada por edital afixado em lugar público de
costume.
BELTRANA DE TAL (EXEMPLO)"""
e = DT.estrutura(orig)
checa(e['corpo'][0].endswith('atribuições legais,') and e['corpo'][1] == 'RESOLVE:', f'parágrafo inicial e RESOLVE: {e["corpo"][:2]}')
checa(e['corpo'][2].startswith('Art. 1º.') and e['corpo'][2].endswith('entre seus pares.'), 'Art. 1º num parágrafo só')
checa('Parágrafo único. O mandato é de dois anos.' in e['corpo'] and 'I - primeiro inciso de exemplo;' in e['corpo'], 'quebra antes de Parágrafo e incisos')
checa('Publique-se e Cumpra-se.' in e['corpo'], '"Publique-se / e / Cumpra-se." numa linha')
checa(e['data'] == 'Exemplo, 13 de novembro de 2026.' and e['assinatura'] == ['FULANO DE TAL (EXEMPLO)', 'PREFEITO MUNICIPAL'], f'data e assinatura: {e["data"]} {e["assinatura"]}')
checa(e['registro'].startswith('Registrada nesta Secretaria') and e['registro_ass'] == ['BELTRANA DE TAL (EXEMPLO)'], 'registro e quem registrou')
junto = ' '.join(e['corpo'] + [e['data']] + e['assinatura'] + [e['registro']] + e['registro_ass'])
checa(DT.texto_plano(orig) == DT.texto_plano(junto), 'texto do ato idêntico (só mudam as quebras)')

# 2) tokens: texto branco sobre a cor do órgão precisa de 4,5:1; senão a faixa usa a cor escurecida
from app.rodape import contraste
checa(L.tokens('#0E4D64')['faixa'] == '#0E4D64', 'cor com contraste: faixa na cor principal')
t = L.tokens('#6FB1D9'); checa(t['faixa'] == t['esc'] and contraste(t['faixa'], '#FFFFFF') >= 4.5 or contraste(t['esc'], '#FFFFFF') < 4.5, 'cor clara: faixa na cor escurecida')
checa(L.romano(1) == 'I' and L.romano(4) == 'IV' and L.romano(14) == 'XIV', 'ano em romanos')
checa(L.plural(1, 'ato publicado', 'atos publicados') == '1 ato publicado' and L.plural(2, 'página', 'páginas') == '2 páginas', 'singular e plural')
checa(L.por_extenso(date(2026, 11, 16)) == '16 de novembro de 2026', 'data por extenso')

# 3) preenchimento sequencial: a coluna da esquerda enche até o fim antes de passar para a direita
from reportlab.platypus import Paragraph
from reportlab.lib.units import mm
es = L.estilos(L.tokens('#0E4D64'))
fila = [Paragraph('Texto de exemplo para encher a coluna. ' * 12, es['corpo']) for _ in range(30)]
cols = [L.Coluna(0, 200 * mm, 80 * mm, 150 * mm), L.Coluna(90 * mm, 200 * mm, 80 * mm, 150 * mm)]
from reportlab.pdfgen import canvas as rlc
import io
L.encher(fila, cols, rlc.Canvas(io.BytesIO()))
checa(cols[0].livre() < 12.5 + 1.6 * mm + 1 and not cols[1].vazia(), f'coluna da esquerda cheia até o fim antes da direita (sobrou {cols[0].livre():.1f} pt)')

# 4) edição de teste com 12 atos dos dois Poderes (4+ páginas): caixas, sumário com continuação, numeração e rodapé da MP
FR = 'as despesas decorrentes da execução desta norma correrão por conta das dotações orçamentárias próprias, suplementadas se necessário'
def ato(i, cad, tipo, n_art):
    txt = '\n'.join(['FULANO DE TAL (EXEMPLO), no uso de suas atribuições legais,', 'RESOLVE:'] +
                    [f'Art. {k}º {FR.capitalize()}, {FR}.' for k in range(1, n_art + 1)] +
                    ['Publique-se', 'e', 'Cumpra-se.', 'Exemplo, 14 de novembro de 2026.', 'FULANO DE TAL (EXEMPLO)', 'CARGO DE EXEMPLO'])
    return {'id': i, 'caderno': cad, 'tipo': tipo, 'numero': f'{i}/2026', 'orgao': 'Órgão de exemplo', 'ementa': f'Ementa fictícia nº {i} para teste da diagramação, com texto longo o bastante para ocupar duas linhas no sumário da capa (EXEMPLO).', 'texto': txt, 'html': None}
atos = [ato(1, 'executivo', 'Lei Complementar', 9), ato(2, 'executivo', 'Decreto', 8), ato(3, 'executivo', 'Decreto', 5), ato(4, 'executivo', 'Portaria', 4),
        ato(5, 'executivo', 'Portaria', 3), ato(6, 'executivo', 'Edital', 6), ato(7, 'executivo', 'Aviso de licitação', 3), ato(8, 'executivo', 'Extrato de contrato', 3),
        ato(9, 'legislativo', 'Resolução', 7), ato(10, 'legislativo', 'Decreto Legislativo', 3), ato(11, 'legislativo', 'Ato da Mesa', 3), ato(12, 'legislativo', 'Portaria', 3)]
ed = {'id': 99, 'numero': 2, 'letra': '', 'data': date(2026, 11, 17), 'responsavel': 'Responsável de exemplo'}
ident = {'nome': 'Prefeitura Municipal de Exemplo', 'nome_curto': 'Exemplo', 'endereco': 'Rua de Exemplo, 1 · CEP 00000-000', 'cnpj': '00.000.000/0001-00', 'cor': '#0E4D64', 'dominio': 'exemplo.localhost'}
with tempfile.TemporaryDirectory() as tmp:
    cam, sha, cod, pags = D.gerar_pdf(ed, atos, ident, tmp, teste=True, lei='Lei Municipal nº 1/2026 (exemplo)', orgao={'municipio': 'Exemplo (SP)', 'dominio': 'exemplo.localhost'}, ano_inicio=2026)
    txt = subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=txtwrite', '-sOutputFile=-', cam], capture_output=True, text=True).stdout
    from pyhanko.pdf_utils.reader import PdfFileReader
    n_pag = len(PdfFileReader(open(cam, 'rb')).root['/Pages']['/Kids'])
    pg = [subprocess.run(['gs', '-q', '-dNOPAUSE', '-dBATCH', '-sDEVICE=txtwrite', f'-dFirstPage={n}', f'-dLastPage={n}', '-sOutputFile=-', cam], capture_output=True, text=True).stdout for n in range(1, n_pag + 1)]
t = ' '.join(txt.split())
n = len(pg)
checa(n >= 4, f'4 páginas ou mais ({n})')
checa(set(pags) == set(range(1, 13)) and all(3 <= v <= n for v in pags.values()), f'página de cada ato: {pags}')
checa(all(f'página {k}' in ' '.join(pg[k - 1].split()) for k in range(1, n + 1)), 'numeração em todas as páginas')
checa(all('conforme a MP nº 2.200-2/2001, que institui a ICP-Brasil · Verifique em exemplo.localhost/diario/verificar' in ' '.join(p.split()) for p in pg), 'linha da MP em todas as páginas')
checa('SUMÁRIO (CONTINUAÇÃO)' in ' '.join(pg[1].split()), 'sumário continua na página 2')
checa('PODER EXECUTIVO' in t and 'PODER LEGISLATIVO' in t and t.index('PODER EXECUTIVO') < t.index('PODER LEGISLATIVO'), 'caixas dos Poderes, Executivo antes')
miolo = ' '.join(' '.join(p.split()) for p in pg[2:])
checa(miolo.rfind('Órgão de exemplo', 0, miolo.find('PODER LEGISLATIVO')) >= 0 and all(miolo.find(f'{k}/2026') < miolo.find('PODER LEGISLATIVO') for k in range(1, 9)), 'Poderes não se misturam')
for g in ('LEIS COMPLEMENTARES', 'DECRETOS', 'PORTARIAS', 'EDITAIS', 'LICITAÇÕES E CONTRATOS', 'RESOLUÇÕES', 'DECRETOS LEGISLATIVOS', 'ATOS DA MESA'):
    checa(g in miolo, f'caixa do tipo "{g}"')
checa(f'{n} páginas · 12 atos publicados' in t and 'Ano I' in t and 'EDIÇÃO ORDINÁRIA' in t, 'cartão da edição com contagens reais')
checa('NESTA EDIÇÃO' in t and 'pág. 3' in t and 'Edição de teste: sem assinatura com validade jurídica.' in t, 'sumário e bloco de autenticidade')
checa('CNPJ 00.000.000/0001-00' in t, 'linha institucional com CNPJ inteiro')

# 5) verificação pelo QR Code: /diario/verificar?c=CÓDIGO
from fastapi.testclient import TestClient
from app.main import app
r = TestClient(app, base_url='http://pmbora.localhost').get('/diario/verificar?c=ZZZZ-ZZZZ-ZZZZ')
checa(r.status_code == 200 and 'ZZZZ-ZZZZ-ZZZZ' in r.text, 'verificar aceita ?c= do QR Code')

print('ERROS:', len(erros))
for x in erros:
    print(' -', x)
sys.exit(1 if erros else 0)
