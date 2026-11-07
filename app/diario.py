"""Geração da edição do Diário Oficial (Lei 910/2026 e decreto de 25/03/2026).

O PDF é gerado aqui; a assinatura ICP-Brasil + carimbo do tempo é feita em assinar_edicao(),
que no piloto fica pendente até a contratação do certificado e da Autoridade de Carimbo do Tempo.
"""
import hashlib
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from . import config

def _rodape(codigo, numero, data):
    def f(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(2 * cm, 1.2 * cm, f'Diário Oficial Eletrônico do Município de Borá · Edição nº {numero} · {data}')
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'Código de verificação: {codigo} · página {doc.page}')
        canvas.restoreState()
    return f

def gerar_pdf(edicao: dict, atos: list[dict], ident: dict, destino_dir: str) -> tuple[str, str, str]:
    """Gera o PDF e devolve (caminho, sha256, codigo)."""
    Path(destino_dir).mkdir(parents=True, exist_ok=True)
    numero = f"{edicao['numero']}{edicao['letra']}"
    data = edicao['data'].strftime('%d/%m/%Y')
    pre = hashlib.sha256(f"{numero}|{data}|{len(atos)}|{config.SECRET_KEY}".encode()).hexdigest().upper()
    codigo = f'{pre[:4]}-{pre[4:8]}-{pre[8:12]}'
    caminho = str(Path(destino_dir) / f"diario-{edicao['data'].isoformat()}-{numero}.pdf")
    st = getSampleStyleSheet()
    h = ParagraphStyle('h', parent=st['Heading1'], fontSize=18, spaceAfter=6)
    sub = ParagraphStyle('s', parent=st['Normal'], fontSize=10, textColor='#4B5563')
    sec = ParagraphStyle('sec', parent=st['Heading2'], fontSize=13, spaceBefore=12)
    corpo = ParagraphStyle('c', parent=st['Normal'], fontSize=10.5, leading=14)
    el = [Paragraph('DIÁRIO OFICIAL ELETRÔNICO DO MUNICÍPIO DE BORÁ', h),
          Paragraph('Instituído pela Lei Municipal nº 910, de 27 de janeiro de 2026', sub),
          Paragraph(f"Edição nº {numero}{' (extra)' if edicao['letra'] else ''} · {data} · Responsável: {edicao.get('responsavel') or '[responsável designado]'}", sub),
          Paragraph(f"{ident.get('nome','')} · {ident.get('endereco','')} · CNPJ {ident.get('cnpj','')}", sub), Spacer(1, 12)]
    if not atos:
        el.append(Paragraph('SEM ATOS OFICIAIS A SEREM PUBLICADOS NESTA DATA', sec))
    for caderno in ('executivo', 'legislativo'):
        lista = [a for a in atos if a['caderno'] == caderno]
        if not lista:
            continue
        el.append(Paragraph('PODER EXECUTIVO' if caderno == 'executivo' else 'PODER LEGISLATIVO', sec))
        for a in lista:
            esc = lambda s: (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            el.append(Paragraph(f"<b>{esc(a['tipo'])} {esc(a['numero'])}</b> · {esc(a['orgao'])}", corpo))
            el.append(Paragraph(f"<i>{esc(a['ementa'])}</i>", corpo))
            for par in esc(a['texto']).split('\n'):
                if par.strip():
                    el.append(Paragraph(par, corpo))
            el.append(Spacer(1, 10))
    doc = SimpleDocTemplate(caminho, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f'Diário Oficial de Borá nº {numero}', author=ident.get('nome', ''))
    f = _rodape(codigo, numero, data)
    doc.build(el, onFirstPage=f, onLaterPages=f)
    sha = hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    return caminho, sha, codigo

def assinar_edicao(caminho_pdf: str) -> bool:
    """Ponto de integração da assinatura ICP-Brasil (PAdES) + carimbo do tempo (RFC 3161).
    Implementar quando houver: certificado do responsável (A1 em cofre, ou nuvem via API do provedor)
    e contrato com uma ACT credenciada (ex.: Serpro, Prodesp). No piloto, retorna False (pendente)."""
    return False
