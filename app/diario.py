"""Geração da edição do Diário Oficial (Lei 910/2026 e decreto de 25/03/2026).

- capa conforme a Lei 910, art. 6º (brasão, título, lei de instituição, data, número, responsável);
- página onde cada ato começa (retorno da remessa da Câmara);
- MODO TESTE: marca d'água "SEM VALOR OFICIAL — TESTE" em todas as páginas;
- PDF/A-2b para arquivo permanente (Lei 910, art. 8º; decreto, art. 5º, VI), convertido ANTES de assinar;
- calendário: sem edição em fins de semana, feriados e dias sem expediente; ponto facultativo conta como dia útil; corte das 16h.
"""
import hashlib, shutil, subprocess, tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Flowable, Image
from . import config, db

LEI_PADRAO = 'Lei Municipal nº 910/2026'

# ---------- calendário ----------
def dia_util(b, d: date) -> bool:
    if d.weekday() >= 5:
        return False
    f = db.um(b, 'SELECT tipo FROM feriados WHERE data=%s', (d,))
    return not f or f['tipo'] == 'ponto_facultativo'

def proximo_dia_util(b, d: date) -> date:
    d = d + timedelta(days=1)
    while not dia_util(b, d):
        d += timedelta(days=1)
    return d

def data_alvo(b, agora: datetime) -> date:
    """Ato enviado até o corte (16h) de um dia útil vai para a edição do dia; depois do corte, para o próximo dia útil."""
    d = agora.date()
    if dia_util(b, d) and agora.hour < config.DIARIO_CORTE_HORA:
        return d
    return proximo_dia_util(b, d)

# ---------- PDF ----------
class Marca(Flowable):
    """Marcador invisível: registra a página em que um ato começa."""
    def __init__(self, ato_id, paginas):
        super().__init__(); self.ato_id, self.paginas = ato_id, paginas
    def wrap(self, *a):
        return 0, 0
    def draw(self):
        self.paginas[self.ato_id] = self.canv.getPageNumber()

def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def codigo_verificacao(edicao, n_atos):
    numero = f"{edicao['numero']}{edicao['letra']}"
    pre = hashlib.sha256(f"{numero}|{edicao['data'].isoformat()}|{n_atos}|{edicao.get('id')}|{config.SECRET_KEY}".encode()).hexdigest().upper()
    return f'{pre[:4]}-{pre[4:8]}-{pre[8:12]}'

def gerar_pdf(edicao: dict, atos: list[dict], ident: dict, destino_dir: str, teste: bool = False, brasao: str | None = None, lei: str | None = None) -> tuple[str, str, str, dict]:
    """Gera o PDF e devolve (caminho, sha256, código, {ato_id: página})."""
    Path(destino_dir).mkdir(parents=True, exist_ok=True)
    numero = f"{edicao['numero']}{edicao['letra']}"
    data = edicao['data'].strftime('%d/%m/%Y')
    codigo = codigo_verificacao(edicao, len(atos))
    municipio = ident.get('nome_curto') or 'do Município'
    caminho = str(Path(destino_dir) / f"diario-{edicao['data'].isoformat()}-{numero}{'-TESTE' if teste else ''}.pdf")
    st = getSampleStyleSheet()
    titulo = ParagraphStyle('t', parent=st['Title'], fontSize=22, leading=27, alignment=TA_CENTER, spaceAfter=8)
    centro = ParagraphStyle('c', parent=st['Normal'], fontSize=11, leading=15, alignment=TA_CENTER, textColor='#17212B')
    sub = ParagraphStyle('s', parent=st['Normal'], fontSize=10, textColor='#4B5563', alignment=TA_CENTER)
    sec = ParagraphStyle('sec', parent=st['Heading2'], fontSize=13, spaceBefore=12)
    corpo = ParagraphStyle('p', parent=st['Normal'], fontSize=10.5, leading=14)
    paginas = {}
    # capa (Lei 910, art. 6º)
    el = [Spacer(1, 2 * cm)]
    if brasao and Path(brasao).is_file():
        el += [Image(brasao, width=3.2 * cm, height=2.8 * cm, kind='proportional'), Spacer(1, 10)]
    el += [Paragraph(f'DIÁRIO OFICIAL ELETRÔNICO DO MUNICÍPIO DE {_esc(municipio.upper())}', titulo),
           Paragraph(f'Instituído pela {_esc(lei or LEI_PADRAO)}', centro), Spacer(1, 18),
           Paragraph(f"<b>Edição nº {numero}</b>{' — edição extra' if edicao['letra'] else ''}", centro),
           Paragraph(f'{data}', centro), Spacer(1, 10),
           Paragraph(f"Responsável pela edição: {_esc(edicao.get('responsavel') or '[responsável designado]')}", centro), Spacer(1, 30),
           Paragraph(f"{_esc(ident.get('nome', ''))} · {_esc(ident.get('endereco', ''))}{' · CNPJ ' + _esc(ident['cnpj']) if ident.get('cnpj') else ''}", sub),
           Paragraph(f'Código de verificação: <b>{codigo}</b> · confira a autenticidade no Portal ({_esc(ident.get("dominio", ""))}/diario/verificar)', sub)]
    if teste:
        el += [Spacer(1, 20), Paragraph('<b>EDIÇÃO DE TESTE — SEM VALOR OFICIAL</b>', ParagraphStyle('x', parent=centro, textColor='#9B1C1C', fontSize=14))]
    el.append(PageBreak())
    if not atos:
        el.append(Paragraph('SEM ATOS OFICIAIS A SEREM PUBLICADOS NESTA DATA', sec))
    for caderno in ('executivo', 'legislativo'):
        lista = [a for a in atos if a['caderno'] == caderno]
        if not lista:
            continue
        el.append(Paragraph('PODER EXECUTIVO' if caderno == 'executivo' else 'PODER LEGISLATIVO', sec))
        for a in lista:
            el.append(Marca(a['id'], paginas))
            el.append(Paragraph(f"<b>{_esc(a['tipo'])} {_esc(a['numero'])}</b> · {_esc(a['orgao'])}", corpo))
            if a.get('retifica'):
                el.append(Paragraph(f"<i>RETIFICAÇÃO — {_esc(a['retifica'])}</i>", corpo))
            el.append(Paragraph(f"<i>{_esc(a['ementa'])}</i>", corpo))
            for par in _esc(a['texto']).split('\n'):
                if par.strip():
                    el.append(Paragraph(par, corpo))
            el.append(Spacer(1, 10))

    def pagina(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(2 * cm, 1.2 * cm, f'Diário Oficial Eletrônico do Município de {municipio} · Edição nº {numero} · {data}')
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'Código de verificação: {codigo} · página {doc.page}')
        if teste:
            canvas.setFillColorRGB(0.75, 0.1, 0.1, alpha=0.18)
            canvas.setFont('Helvetica-Bold', 44)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, 'SEM VALOR OFICIAL — TESTE')
        canvas.restoreState()
    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f'Diário Oficial de {municipio} nº {numero}' + (' (TESTE)' if teste else ''), author=ident.get('nome', ''))
    doc.build(el, onFirstPage=pagina, onLaterPages=pagina)
    sha = hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    return caminho, sha, codigo, paginas

def para_pdfa(caminho: str) -> bool:
    """Converte para PDF/A-2b com o Ghostscript (antes de assinar: assinar depois mantém a assinatura válida).
    Devolve False (e mantém o original) se o Ghostscript ou o perfil de cor não estiverem disponíveis."""
    gs = shutil.which('gs')
    icc = next(iter(sorted(Path('/usr/share/ghostscript').glob('*/iccprofiles/srgb.icc'))), None) if Path('/usr/share/ghostscript').is_dir() else None
    if not gs or not icc:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        defs = Path(tmp) / 'PDFA_def.ps'
        defs.write_text(f"""%!
/ICCProfile ({icc}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc_PDFA}} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
""")
        saida = Path(tmp) / 'saida.pdf'
        r = subprocess.run([gs, '-dPDFA=2', '-dBATCH', '-dNOPAUSE', '-dNOOUTERSAVE', '-dQUIET', '-sColorConversionStrategy=RGB', '-sProcessColorModel=DeviceRGB',
                            '-sDEVICE=pdfwrite', '-dPDFACompatibilityPolicy=1', f'--permit-file-read={icc}', f'-sOutputFile={saida}', str(defs), caminho],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not saida.is_file() or saida.stat().st_size < 1000:
            return False
        shutil.copyfile(saida, caminho)
    return True
