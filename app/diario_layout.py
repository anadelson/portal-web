"""Diagramação da edição do Diário Oficial (16/11/2026; Docs/PEDIDO-DIARIO-CAPA.md).

- Capa própria (função `desenhar_capa`, separada do miolo): faixa de identidade na cor do órgão, cartão da edição,
  "Nesta edição" (sumário com a página de cada ato; continua em "Sumário (continuação)" se não couber),
  tarja de TESTE, bloco de autenticidade com QR Code e linha institucional.
- Miolo em 2 colunas com preenchimento SEQUENCIAL: enche a coluna da esquerda até o fim da área útil e só então
  passa para a direita; depois, a página seguinte. Caixa do Poder na largura total; caixa do tipo na largura da coluna.
  Os Poderes nunca se misturam e seguem na mesma página (decisão do usuário): só a última página de um Poder que é
  seguido por outro tem as colunas equilibradas, para a caixa do Poder seguinte entrar logo abaixo, na largura total.
- Título do ato e caixa do tipo nunca ficam sozinhos no pé da coluna (seguem com as primeiras linhas do texto).
- Rodapé em todas as páginas: linha de sempre + linha da MP nº 2.200-2/2001. Marca d'água de teste em todas as páginas.
- Os carimbos laterais das assinaturas NÃO são desenhados aqui: são a aparência dos campos de assinatura (assinatura.py),
  aplicada na hora de cada assinatura, com os dados do próprio certificado. `carimbo_retangulos` diz onde ficam.
Cores e fonte vêm do órgão (cor principal da Identidade e derivadas; Public Sans embutida). Nada fixo por órgão."""
import copy, io
from datetime import date
from pathlib import Path
from reportlab.lib.colors import HexColor, white, Color
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Flowable, Paragraph, Spacer
from . import diario_texto as DT

W, H = A4
FONTES = Path(__file__).parent / 'static' / 'fonts'
PESOS = ('Light', 'Regular', 'Italic', 'SemiBold', 'Bold', 'ExtraBold')
MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro']
DIAS = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo']
# grupos de publicação dentro de cada Poder (ordem do miolo e do sumário); tipo fora da lista vai para "Outros atos"
GRUPOS = [('Leis Complementares', ('Lei Complementar',)), ('Leis', ('Lei',)), ('Decretos Legislativos', ('Decreto Legislativo',)),
          ('Decretos', ('Decreto',)), ('Resoluções', ('Resolução',)), ('Atos da Mesa', ('Ato da Mesa',)), ('Portarias', ('Portaria',)),
          ('Editais', ('Edital',)), ('Licitações e Contratos', ('Aviso de licitação', 'Extrato de contrato')), ('Retificações', ('Retificação',))]
PODERES = (('executivo', 'PODER EXECUTIVO', 'Poder Executivo'), ('legislativo', 'PODER LEGISLATIVO', 'Poder Legislativo'))

# geometria (mm): miolo e carimbos laterais
MARGEM, GAP = 20 * mm, 7 * mm
TOPO_MIOLO, BASE_MIOLO = H - 26 * mm, 24 * mm
CARIMBO_X, CARIMBO_L = 4 * mm, 9 * mm


# ---------- fontes, cores e textos ----------
def fontes():
    """Registra a Public Sans (uma vez). Sem os arquivos, cai na Helvetica (o PDF continua válido)."""
    if 'PS-Regular' in pdfmetrics.getRegisteredFontNames():
        return True
    if not all((FONTES / f'PublicSans-{p}.ttf').is_file() for p in PESOS):
        return False
    for p in PESOS:
        pdfmetrics.registerFont(TTFont(f'PS-{p}', str(FONTES / f'PublicSans-{p}.ttf')))
    return True

def f(peso):
    return f'PS-{peso}' if fontes() else ('Helvetica-Bold' if peso in ('SemiBold', 'Bold', 'ExtraBold') else ('Helvetica-Oblique' if peso == 'Italic' else 'Helvetica'))

def tokens(cor):
    """Cor principal do órgão e derivadas (as mesmas regras do portal). Faixa com texto branco só se der 4,5:1; senão, a escurecida."""
    from .rodape import mistura, contraste
    cor = (cor or '#0E4D64').upper()
    esc, clara = mistura(cor, '#000000', .25), mistura(cor, '#FFFFFF', .9)
    return {'cor': cor, 'esc': esc, 'clara': clara, 'faixa': cor if contraste(cor, '#FFFFFF') >= 4.5 else esc,
            'anel': mistura(cor, '#FFFFFF', .28), 'tinta': '#14181F', 'suave': '#4A5361', 'linha': '#D5DAE1'}

def por_extenso(d: date):
    return f'{d.day} de {MESES[d.month - 1]} de {d.year}'

def romano(n):
    out = ''
    for v, s in ((1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')):
        while n >= v:
            out += s; n -= v
    return out

def plural(n, um, varios):
    return f'{n} {um if n == 1 else varios}'

def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def grupo_de(tipo):
    for i, (nome, tipos) in enumerate(GRUPOS):
        if tipo in tipos:
            return i, nome
    return len(GRUPOS), 'Outros atos'

def organizar(atos):
    """[(caderno, rótulo, [(grupo, [atos])])] na ordem do miolo: Poder → grupo de publicação → ordem de envio."""
    out = []
    for cad, rot, _ in PODERES:
        lista = [a for a in atos if a['caderno'] == cad]
        if not lista:
            continue
        grupos = {}
        for a in lista:
            grupos.setdefault(grupo_de(a['tipo']), []).append(a)
        out.append((cad, rot, [(g[1], grupos[g]) for g in sorted(grupos)]))
    return out


# ---------- estilos do miolo (Helvetica 9,5 pt, justificado, hifenização em português) ----------
def _hifen():
    try:
        import pyphen  # noqa: F401
        return {'hyphenationLang': 'pt_BR', 'embeddedHyphenation': 1, 'uriWasteReduce': 0.3}
    except ImportError:
        return {}

def estilos(tk):
    hf = _hifen()
    base = ParagraphStyle('corpo', fontName='Helvetica', fontSize=9.5, leading=12.5, alignment=TA_JUSTIFY, spaceAfter=1.6 * mm, **hf)
    return {'corpo': base,
            'titulo': ParagraphStyle('tt', parent=base, fontName='Helvetica-Bold', fontSize=10, leading=12.5, alignment=TA_LEFT, spaceAfter=0, keepWithNext=1),
            'retifica': ParagraphStyle('rt', parent=base, fontName='Helvetica-Oblique', alignment=TA_LEFT, spaceAfter=0, keepWithNext=1),
            'ementa': ParagraphStyle('em', parent=base, fontName='Helvetica-Oblique', leftIndent=6 * mm, spaceBefore=1 * mm, spaceAfter=2.5 * mm, keepWithNext=1),
            'ass': ParagraphStyle('as', parent=base, alignment=TA_CENTER, spaceBefore=3 * mm, spaceAfter=0),
            'reg': ParagraphStyle('rg', parent=base, fontSize=8.5, leading=11, spaceAfter=0),
            'reg_ass': ParagraphStyle('ra', parent=base, fontSize=8.5, leading=11, alignment=TA_CENTER, spaceBefore=1 * mm, spaceAfter=0),
            'vazio': ParagraphStyle('vz', parent=base, fontName='Helvetica-Bold', fontSize=11, leading=15, alignment=TA_CENTER)}


class CaixaTipo(Flowable):
    """Caixa do tipo de publicação: largura da coluna, fundo claro da cor principal, filete de 1,4 mm, caixa alta."""
    keepWithNext = 1
    def __init__(self, texto, tk):
        super().__init__(); self.texto, self.tk = texto.upper(), tk
    def wrap(self, aw, ah):
        self.width = aw; self.height = 8.2 * mm; return aw, self.height
    def getSpaceAfter(self):
        return 3 * mm
    def draw(self):
        c = self.canv
        c.setFillColor(HexColor(self.tk['clara'])); c.rect(0, 0, self.width, self.height, stroke=0, fill=1)
        c.setFillColor(HexColor(self.tk['cor'])); c.rect(0, 0, 1.4 * mm, self.height, stroke=0, fill=1)
        c.setFillColor(HexColor(self.tk['esc'])); c.setFont('Helvetica-Bold', 9.5)
        c._code.append('0.8 Tc'); c.drawString(4.4 * mm, 2.9 * mm, self.texto); c._code.append('0 Tc')


class FioPontilhado(Flowable):
    def wrap(self, aw, ah):
        self.width = aw; return aw, 2 * mm
    def getSpaceBefore(self):
        return 3 * mm
    def draw(self):
        self.canv.setStrokeColor(HexColor('#999999')); self.canv.setLineWidth(.25 * mm / 1.5); self.canv.setDash(1, 1.5)
        self.canv.line(0, 1.5 * mm, self.width, 1.5 * mm)


class Marca(Flowable):
    """Marcador invisível: registra a página em que um ato começa (retorno da remessa da Câmara e sumário)."""
    def __init__(self, ato_id, paginas):
        super().__init__(); self.ato_id, self.paginas = ato_id, paginas
    def wrap(self, *a):
        return 0, 0
    def draw(self):
        self.paginas.setdefault(self.ato_id, getattr(self.canv, '_pg', None) or self.canv.getPageNumber())


def flowables_ato(a, es, paginas):
    el = [Marca(a['id'], paginas), Paragraph(f"<b>{_esc(a['tipo'])} {_esc(a['numero'])}</b>" + (f" <font name='Helvetica'>· {_esc(a['orgao'])}</font>" if a.get('orgao') else ''), es['titulo'])]
    if a.get('retifica'):
        el.append(Paragraph(f"RETIFICAÇÃO — {_esc(a['retifica'])}", es['retifica']))
    if a.get('ementa'):
        el.append(Paragraph(_esc(a['ementa']), es['ementa']))
    if a.get('html'):  # texto formatado no editor: parágrafos e alinhamentos do próprio ato
        from .diario_formato import elementos_pdf
        el += elementos_pdf(a['html'], es['corpo'])
    else:
        e = DT.estrutura(a.get('texto'))
        el += [Paragraph(_esc(p), es['corpo']) for p in e['corpo']]
        if e['data']:
            el.append(Paragraph(_esc(e['data']), es['corpo']))
        if e['assinatura']:
            el.append(Paragraph('<br/>'.join([f'<b>{_esc(e["assinatura"][0])}</b>'] + [_esc(x) for x in e['assinatura'][1:]]), es['ass']))
        if e['registro'] or e['registro_ass']:
            el.append(FioPontilhado())
            if e['registro']:
                el.append(Paragraph(_esc(e['registro']), es['reg']))
            if e['registro_ass']:
                el.append(Paragraph('<br/>'.join([f'<b>{_esc(e["registro_ass"][0])}</b>'] + [_esc(x) for x in e['registro_ass'][1:]]), es['reg_ass']))
    el.append(Spacer(1, 5 * mm))
    return el


# ---------- motor de colunas (preenchimento sequencial) ----------
class Coluna:
    def __init__(self, x, topo, largura, altura):
        self.x, self.topo, self.w, self.base = x, topo, largura, topo - altura
        self.cursor = topo
    def livre(self):
        return self.cursor - self.base
    def vazia(self):
        return self.cursor >= self.topo - .01


def _sb(fl):
    return fl.getSpaceBefore() if hasattr(fl, 'getSpaceBefore') else 0

def _sa(fl):
    return fl.getSpaceAfter() if hasattr(fl, 'getSpaceAfter') else 0

def _kwn(fl):
    return bool(getattr(fl, 'keepWithNext', 0) or getattr(getattr(fl, 'style', None), 'keepWithNext', 0))

def _cabeca(fila, w):
    """Altura que precisa caber junto: flowables 'keepWithNext' seguidos + 2 linhas do primeiro texto que vem depois."""
    h, i = 0, 0
    while i < len(fila) and (_kwn(fila[i]) or isinstance(fila[i], Marca)):
        _, hh = fila[i].wrap(w, 10 ** 6); h += hh + _sa(fila[i]) + (_sb(fila[i]) if i else 0); i += 1
    if i == 0:
        return 0
    if i < len(fila):
        nxt = fila[i]
        lead = getattr(getattr(nxt, 'style', None), 'leading', None)
        h += _sb(nxt) + (2 * lead if lead else min(nxt.wrap(w, 10 ** 6)[1], 12 * mm))
    return h


def encher(fila, colunas, canv):
    """Enche as colunas em sequência (a 1ª até o fim, depois a 2ª). Consome a fila; devolve True se esvaziou."""
    for col in colunas:
        while fila:
            fl = fila[0]
            sb = 0 if col.vazia() else _sb(fl)
            cab = _cabeca(fila, col.w)
            if cab and not col.vazia() and cab + sb > col.livre():
                break  # título/caixa do tipo não fica sozinho no pé da coluna
            avail = col.livre() - sb
            w, h = fl.wrap(col.w, avail)
            if h <= avail + .01:
                col.cursor -= sb
                if canv is not None:
                    fl.drawOn(canv, col.x, col.cursor - h)
                col.cursor -= h + _sa(fl)
                fila.pop(0)
                continue
            partes = fl.split(col.w, avail) if avail > 0 else []
            if len(partes) >= 2:
                w0, h0 = partes[0].wrap(col.w, avail)
                col.cursor -= sb
                if canv is not None:
                    partes[0].drawOn(canv, col.x, col.cursor - h0)
                col.cursor -= h0
                fila[0:1] = partes[1:]
            elif col.vazia():  # mais alto que a coluna inteira e indivisível: desenha e segue (nunca trava)
                if canv is not None:
                    fl.drawOn(canv, col.x, col.cursor - min(h, col.livre()))
                col.cursor = col.base; fila.pop(0)
            break
    return not fila


class Miolo:
    """Pagina o miolo num canvas (de verdade ou só para medir: as páginas de cada ato e o total de páginas)."""
    def __init__(self, tk, es, rodape_fn, cabecalho_fn, primeira_pagina):
        self.tk, self.es, self.rodape, self.cabecalho, self.pg0 = tk, es, rodape_fn, cabecalho_fn, primeira_pagina

    def _colunas(self, topo, altura):
        lw = (W - 2 * MARGEM - GAP) / 2
        return [Coluna(MARGEM, topo, lw, altura), Coluna(MARGEM + lw + GAP, topo, lw, altura)]

    def _fio(self, canv, topo, base):
        if topo - base > 2 * mm:
            canv.setStrokeColor(HexColor('#C9CED6')); canv.setLineWidth(.25 * mm); canv.setDash()
            canv.line(W / 2, base, W / 2, topo)

    def _caixa_poder(self, canv, y, texto):
        h = 9 * mm
        canv.setFillColor(HexColor(self.tk['faixa'])); canv.roundRect(MARGEM, y - h, W - 2 * MARGEM, h, 1.2 * mm, stroke=0, fill=1)
        canv.setFillColor(white); canv.setFont('Helvetica-Bold', 12); canv._code.append('0.7 Tc')
        canv.drawString(MARGEM + 4 * mm, y - h + 3 * mm, texto); canv._code.append('0 Tc')
        return h + 4 * mm

    def paginar(self, poderes, canv):
        """poderes: [(rótulo, [flowables])]. Devolve o número de páginas do miolo."""
        pg = self.pg0
        def abre():
            canv._pg = pg; self.cabecalho(canv, pg); return TOPO_MIOLO
        def fecha():
            self.rodape(canv, pg); canv.showPage()
        y = abre()
        if not poderes:
            p = Paragraph('SEM ATOS OFICIAIS A SEREM PUBLICADOS NESTA DATA', self.es['vazio']); _, hh = p.wrap(W - 2 * MARGEM, 50 * mm)
            p.drawOn(canv, MARGEM, y - hh - 20 * mm); fecha()
            return 1
        for i, (rot, fls) in enumerate(poderes):
            ultimo = i == len(poderes) - 1
            if y < TOPO_MIOLO and y - BASE_MIOLO < 45 * mm:  # pouco espaço para a caixa do Poder e as primeiras linhas
                fecha(); pg += 1; y = abre()
            y -= self._caixa_poder(canv, y, rot)
            fila = list(fls)
            while True:
                altura = y - BASE_MIOLO
                if not ultimo and encher(copy.deepcopy(fila), self._colunas(y, altura), None):
                    # última página deste Poder, com outro Poder depois: colunas equilibradas (a menor altura que comporta tudo),
                    # para a caixa do Poder seguinte entrar logo abaixo, na largura total
                    lo, hi = 8 * mm, altura
                    while hi - lo > 1.5:
                        mid = (lo + hi) / 2
                        if encher(copy.deepcopy(fila), self._colunas(y, mid), None):
                            hi = mid
                        else:
                            lo = mid
                    altura = hi
                cols = self._colunas(y, altura)
                fim = encher(fila, cols, canv)
                if not cols[1].vazia():
                    self._fio(canv, y, min(c.cursor for c in cols) if fim else cols[0].base)
                if fim:
                    y = min(c.cursor for c in cols) - 5 * mm
                    break
                fecha(); pg += 1; y = abre()
        fecha()
        return pg - self.pg0 + 1


# ---------- capa ----------
def _txt(c, x, y, s, fonte, tam, cor, track=0, alinhar='l'):
    c.setFont(fonte, tam); c.setFillColor(HexColor(cor) if isinstance(cor, str) else cor)
    if track:
        c._code.append(f'{track} Tc')
    if alinhar == 'r':
        c.drawRightString(x, y, s)
    elif alinhar == 'c':
        c.drawCentredString(x, y, s)
    else:
        c.drawString(x, y, s)
    if track:
        c._code.append('0 Tc')

def _trunca(texto, fonte, tam, largura, linhas=2):
    """Quebra em até `linhas` linhas; corta com "…" só se sobrar (usado só no sumário)."""
    pal, out, atual = (texto or '').split(), [], ''
    for i, p in enumerate(pal):
        t = f'{atual} {p}'.strip()
        if pdfmetrics.stringWidth(t, fonte, tam) <= largura:
            atual = t; continue
        out.append(atual); atual = p
        if len(out) == linhas:
            resto = ' '.join([atual] + pal[i + 1:])
            ult = out[-1]
            while pdfmetrics.stringWidth(ult + '…', fonte, tam) > largura and ' ' in ult:
                ult = ult.rsplit(' ', 1)[0]
            out[-1] = ult + '…' if resto else ult
            return out
    if atual:
        out.append(atual)
    return out[:linhas]


class Sumario:
    """Itens do "Nesta edição" e o desenho em áreas (capa e páginas de continuação)."""
    def __init__(self, organizados, paginas, tk):
        self.tk, self.itens = tk, []
        for cad, rot, grupos in organizados:
            self.itens.append(('poder', rot))
            for _, lista in grupos:
                for a in lista:
                    self.itens.append(('ato', a, paginas.get(a['id'])))

    def _altura(self, item, largura):
        if item[0] == 'poder':
            return 10 * mm
        em = _trunca(item[1].get('ementa') or '', f('Italic'), 8.6, largura - 20 * mm)
        return (5.2 + 3.4 * len(em) + 2.6) * mm

    def desenhar(self, c, x, topo, base, largura, inicio=0):
        """Desenha a partir do item `inicio` até acabar o espaço. Devolve o índice do próximo item (len = acabou)."""
        y, i = topo, inicio
        while i < len(self.itens):
            it = self.itens[i]
            h = self._altura(it, largura)
            if it[0] == 'poder' and i + 1 < len(self.itens):
                h += self._altura(self.itens[i + 1], largura)  # Poder não fica sozinho no fim da área
            if y - h < base:
                break
            if it[0] == 'poder':
                _txt(c, x, y - 7 * mm, it[1], f('ExtraBold'), 10, self.tk['tinta'], track=0.4)
                y -= 10 * mm
            else:
                a, pag = it[1], it[2]
                tt = f"{a['tipo']} {a['numero']}"
                _txt(c, x, y - 4.4 * mm, tt, f('Bold'), 9.5, self.tk['tinta'])
                wt = pdfmetrics.stringWidth(tt, f('Bold'), 9.5)
                if a.get('orgao'):
                    org = f" · {a['orgao']}"
                    while pdfmetrics.stringWidth(org, f('Regular'), 9.5) > largura - wt - 20 * mm and len(org) > 6:
                        org = org[:-2].rstrip() + '…'
                    _txt(c, x + wt, y - 4.4 * mm, org, f('Regular'), 9.5, self.tk['suave'])
                _txt(c, x + largura, y - 4.4 * mm, f'pág. {pag}' if pag else '', f('Bold'), 9.5, self.tk['esc'], alinhar='r')
                em = _trunca(a.get('ementa') or '', f('Italic'), 8.6, largura - 20 * mm)
                for k, linha in enumerate(em):
                    _txt(c, x, y - (8.4 + 3.4 * k) * mm, linha, f('Italic'), 8.6, self.tk['suave'])
                y -= self._altura(it, largura)
                c.setStrokeColor(HexColor('#B9C0CA')); c.setLineWidth(.25 * mm); c.setDash(.6, 1.6)
                c.line(x, y + .8 * mm, x + largura, y + .8 * mm); c.setDash()
            i += 1
        return i



def _qr(url):
    import qrcode
    q = qrcode.QRCode(border=0, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8); q.add_data(url); q.make(fit=True)
    b = io.BytesIO(); q.make_image(fill_color='black', back_color='white').save(b, 'PNG'); b.seek(0)
    return ImageReader(b)


def desenhar_capa(c, d, sumario, tk):
    """Página 1. `d`: dados da edição (ver gerar). Devolve o índice do sumário onde parou (para a continuação)."""
    # 1. faixa de identidade
    c.setFillColor(HexColor(tk['faixa'])); c.rect(0, H - 80 * mm, W, 80 * mm, stroke=0, fill=1)
    c.setFillColor(HexColor(tk['esc'])); c.rect(0, H - 80 * mm, W, 3 * mm, stroke=0, fill=1)
    cx, cy = 18 * mm + 15.5 * mm, H - 16 * mm - 15.5 * mm
    c.setFillColor(HexColor(tk['anel'])); c.circle(cx, cy, 15.5 * mm + 1.4 * mm, stroke=0, fill=1)
    c.setFillColor(white); c.circle(cx, cy, 15.5 * mm, stroke=0, fill=1)
    if d.get('brasao') and Path(d['brasao']).is_file():
        try:
            img = ImageReader(d['brasao']); iw, ih = img.getSize(); bw = 24 * mm; bh = bw * ih / iw
            if bh > 26 * mm:
                bh = 26 * mm; bw = bh * iw / ih
            c.drawImage(img, cx - bw / 2, cy - bh / 2, bw, bh, mask='auto')
        except Exception:
            pass
    tx = 18 * mm + 31 * mm + 7 * mm
    _txt(c, tx, H - 23 * mm, d['entidade'].upper(), f('SemiBold'), 10, white, track=1.4)
    _txt(c, tx, H - 35 * mm, 'DIÁRIO OFICIAL', f('ExtraBold'), 30, white, track=-0.3)
    _txt(c, tx, H - 44.5 * mm, f"Eletrônico do Município de {d['municipio']}", f('Light'), 21, white, track=0.2)
    _txt(c, 18 * mm, H - 60 * mm, f"Instituído pela {d['lei']} · Meio oficial de publicação dos atos do Município", f('Regular'), 9.5, white)
    # 2. cartão da edição (sobre a borda da faixa)
    x0, x1, top, h = 18 * mm, W - 18 * mm, H - 68 * mm, 27 * mm
    c.setFillColor(Color(20 / 255, 24 / 255, 31 / 255, alpha=.08)); c.roundRect(x0 + .6 * mm, top - h - 1.2 * mm, x1 - x0, h, 2.5 * mm, stroke=0, fill=1)
    c.setFillColor(white); c.setStrokeColor(HexColor(tk['linha'])); c.setLineWidth(.3 * mm); c.roundRect(x0, top - h, x1 - x0, h, 2.5 * mm, stroke=1, fill=1)
    nw = 42 * mm
    c.setFillColor(HexColor(tk['clara'])); c.roundRect(x0, top - h, nw + 3 * mm, h, 2.5 * mm, stroke=0, fill=1)
    c.setFillColor(white); c.rect(x0 + nw, top - h + .2 * mm, 3 * mm, h - .4 * mm, stroke=0, fill=1)
    c.setStrokeColor(HexColor(tk['linha'])); c.roundRect(x0, top - h, x1 - x0, h, 2.5 * mm, stroke=1, fill=0)
    _txt(c, x0 + nw / 2, top - 8 * mm, 'EDIÇÃO', f('SemiBold'), 7.5, tk['suave'], track=0.9, alinhar='c')
    _txt(c, x0 + nw / 2, top - 18.5 * mm, f"nº {d['numero']}", f('ExtraBold'), 30 if len(d['numero']) <= 3 else 24, tk['esc'], alinhar='c')
    _txt(c, x0 + nw / 2, top - 23.5 * mm, f"Ano {d['ano_romano']}", f('Regular'), 8.5, tk['suave'], alinhar='c')
    dx = x0 + nw + 6 * mm
    _txt(c, dx, top - 8 * mm, 'PUBLICADA EM', f('SemiBold'), 7.5, tk['suave'], track=0.9)
    _txt(c, dx, top - 15.5 * mm, d['data_extenso'], f('Bold'), 16, tk['tinta'])
    _txt(c, dx, top - 21.5 * mm, d['linha_data'], f('Regular'), 9, tk['suave'])
    tw = 54 * mm; tx0 = x1 - tw
    c.setStrokeColor(HexColor(tk['linha'])); c.line(tx0, top - h, tx0, top)
    chip = 'EDIÇÃO EXTRA' if d['extra'] else 'EDIÇÃO ORDINÁRIA'
    cw = pdfmetrics.stringWidth(chip, f('Bold'), 8) + 0.5 * len(chip) + 6 * mm
    c.setFillColor(HexColor(tk['faixa'])); c.roundRect(x1 - 6 * mm - cw, top - 11.5 * mm, cw, 5.6 * mm, 2.8 * mm, stroke=0, fill=1)
    _txt(c, x1 - 6 * mm - cw / 2, top - 9.7 * mm, chip, f('Bold'), 8, white, track=0.5, alinhar='c')
    resp = f"Responsável: {d['responsavel']}"
    for k, linha in enumerate(_trunca(resp, f('Regular'), 9, tw - 12 * mm, 2)):
        _txt(c, x1 - 6 * mm, top - (17 + 4 * k) * mm, linha, f('Regular'), 9, tk['suave'], alinhar='r')
    # 3. sumário
    sy = top - h - 8 * mm
    _txt(c, 18 * mm, sy, 'NESTA EDIÇÃO', f('ExtraBold'), 9, tk['esc'], track=1.3)
    lw = pdfmetrics.stringWidth('NESTA EDIÇÃO', f('ExtraBold'), 9) + 1.3 * 12 + 3 * mm
    c.setStrokeColor(HexColor(tk['linha'])); c.setLineWidth(.3 * mm); c.line(18 * mm + lw, sy + 1.1 * mm, W - 18 * mm, sy + 1.1 * mm)
    base_sum = (84 + 9 + 4) * mm if d['teste'] else (78 + 4) * mm
    if not sumario.itens:
        _txt(c, 18 * mm, sy - 8 * mm, 'Sem atos oficiais a serem publicados nesta data.', f('Italic'), 9.5, tk['suave'])
        prox = 0
    else:
        prox = sumario.desenhar(c, 18 * mm, sy - 2 * mm, base_sum, W - 36 * mm)
        if prox < len(sumario.itens):
            _txt(c, W - 18 * mm, base_sum - 3 * mm, 'continua na página seguinte →', f('Italic'), 8.5, tk['suave'], alinhar='r')
    # 4. tarja de teste
    if d['teste']:
        c.setFillColor(HexColor('#FDF2F2')); c.setStrokeColor(HexColor('#A3232B')); c.setLineWidth(.4 * mm)
        c.roundRect(18 * mm, 84 * mm, W - 36 * mm, 9 * mm, 2 * mm, stroke=1, fill=1)
        _txt(c, W / 2, 87.2 * mm, d['legenda_teste'].upper(), f('ExtraBold'), 11, '#A3232B', track=0.4, alinhar='c')
    # 5. autenticidade
    ax, ay, aw, ah = 18 * mm, 38 * mm, W - 36 * mm, 40 * mm
    c.setFillColor(HexColor('#FAFBFC')); c.setStrokeColor(HexColor(tk['linha'])); c.setLineWidth(.3 * mm); c.roundRect(ax, ay, aw, ah, 2.5 * mm, stroke=1, fill=1)
    c.drawImage(_qr(d['url_verificar_qr']), ax + 5 * mm, ay + 5 * mm, 30 * mm, 30 * mm)
    tx = ax + 41 * mm
    _txt(c, tx, ay + 31 * mm, 'Autenticidade', f('Bold'), 10, tk['tinta'])
    _txt(c, tx, ay + 24.5 * mm, 'Código de verificação: ', f('Regular'), 8.6, tk['suave'])
    _txt(c, tx + pdfmetrics.stringWidth('Código de verificação: ', f('Regular'), 8.6), ay + 24.5 * mm, d['codigo'], 'Courier-Bold', 12, tk['tinta'], track=0.7)
    _txt(c, tx, ay + 17.5 * mm, f"Confira em {d['url_verificar']} ou aponte a câmera para o QR Code.", f('Regular'), 8.6, tk['suave'])
    frase = 'Edição de teste: sem assinatura com validade jurídica.' if d['teste'] else 'Documento assinado digitalmente com certificado ICP-Brasil, conforme a MP nº 2.200-2/2001.'
    _txt(c, tx, ay + 12 * mm, frase, f('SemiBold' if d['teste'] else 'Regular'), 8.6, '#A3232B' if d['teste'] else tk['suave'])
    # 6. linha institucional (sem quebrar o CNPJ)
    c.setStrokeColor(HexColor(tk['linha'])); c.setLineWidth(.3 * mm); c.line(18 * mm, 22 * mm + 9 * mm, W - 18 * mm, 22 * mm + 9 * mm)
    p = Paragraph(_esc(d['institucional']).replace('CNPJ ', 'CNPJ&nbsp;'), ParagraphStyle('in', fontName=f('Regular'), fontSize=8, leading=12, alignment=TA_CENTER, textColor=HexColor(tk['suave'])))
    _, ph = p.wrap(W - 36 * mm, 20 * mm); p.drawOn(c, 18 * mm, 22 * mm + 9 * mm - 2.5 * mm - ph)
    return prox


def carimbo_retangulos(n_cadernos):
    """Onde ficam os carimbos laterais em cada tipo de página (para assinatura.py): {'capa'|'miolo': {'esq': [(x, y, w, h)...], 'dir': (x, y, w, h)}}.
    Capa: abaixo da faixa de identidade (84 mm do topo) até 10 mm da base. Miolo: 22 mm do topo e da base. Cadernos empilhados na esquerda."""
    out = {}
    for tipo, (topo, base) in {'capa': (H - 84 * mm, 10 * mm), 'miolo': (H - 22 * mm, 22 * mm)}.items():
        n = max(1, n_cadernos); gap = 4 * mm; seg = (topo - base - gap * (n - 1)) / n
        esq = [(CARIMBO_X, topo - (i + 1) * seg - i * gap, CARIMBO_L, seg) for i in range(n)]
        out[tipo] = {'esq': esq, 'dir': (W - CARIMBO_X - CARIMBO_L, base, CARIMBO_L, topo - base)}
    return out


# ---------- edição completa ----------
def gerar(caminho, ed, atos, ident, meta):
    """Gera o PDF da edição. `meta`: municipio, uf, entidade, lei, dominio, cor, ano_inicio, teste, codigo, legenda_teste, brasao.
    Devolve {ato_id: página} e o total de páginas."""
    fontes()
    tk = tokens(meta.get('cor'))
    es = estilos(tk)
    numero = f"{ed['numero']}{ed['letra']}"
    data = ed['data']
    org = organizar(atos)
    titulo_cab = f"Diário Oficial Eletrônico do Município de {meta['municipio']}"

    def poderes_fl(paginas):
        out = []
        for cad, rot, grupos in org:
            fl = []
            for nome, lista in grupos:
                fl.append(CaixaTipo(nome, tk))
                for a in lista:
                    fl += flowables_ato(a, es, paginas)
            out.append((rot, fl))
        return out

    def rodape(c, pg):
        c.saveState()
        c.setFont('Helvetica', 8); c.setFillColor(HexColor('#000000'))
        c.drawString(MARGEM, 15.5 * mm, f"{titulo_cab} · Edição nº {numero} · {data.strftime('%d/%m/%Y')}")
        c.drawRightString(W - MARGEM, 15.5 * mm, f"Código de verificação: {meta['codigo']} · página {pg}")
        c.setFont('Helvetica', 6.8); c.setFillColor(HexColor('#333333'))
        c.drawCentredString(W / 2, 10 * mm, f"Documento assinado digitalmente conforme a MP nº 2.200-2/2001, que institui a ICP-Brasil · Verifique em {meta['dominio']}/diario/verificar")
        if meta['teste']:
            c.setFillColorRGB(0.75, 0.1, 0.1, alpha=0.18); c.setFont('Helvetica-Bold', 30)
            c.translate(W / 2, H / 2); c.rotate(45); c.drawCentredString(0, 0, meta['legenda_teste'].upper())
        c.restoreState()

    def cabecalho(c, pg):
        c.saveState()
        _txt(c, MARGEM, H - 19 * mm, titulo_cab, 'Helvetica-Bold', 10, tk['esc'])
        _txt(c, W - MARGEM, H - 19 * mm, f'Edição nº {numero} · {por_extenso(data)}', 'Helvetica', 8, '#000000', alinhar='r')
        c.setStrokeColor(HexColor(tk['cor'])); c.setLineWidth(.6 * mm); c.line(MARGEM, H - 21.5 * mm, W - MARGEM, H - 21.5 * mm)
        c.restoreState()

    def sumario_cont(c, sumario, inicio, pg):
        _txt(c, MARGEM, H - 30 * mm, 'SUMÁRIO (CONTINUAÇÃO)', f('ExtraBold'), 9, tk['esc'], track=1.3)
        prox = sumario.desenhar(c, MARGEM, H - 33 * mm, 30 * mm, W - 2 * MARGEM, inicio)
        rodape(c, pg); c.showPage()
        return prox

    dados = {'entidade': f"{meta['entidade']} · {meta['uf']}" if meta.get('uf') else meta['entidade'], 'municipio': meta['municipio'],
             'lei': meta['lei'], 'numero': numero, 'extra': bool(ed['letra']), 'teste': meta['teste'], 'legenda_teste': meta['legenda_teste'],
             'data_extenso': por_extenso(data), 'responsavel': ed.get('responsavel') or 'responsável designado', 'brasao': meta.get('brasao'),
             'ano_romano': romano(max(1, data.year - (meta.get('ano_inicio') or data.year) + 1)), 'codigo': meta['codigo'],
             'url_verificar': f"{meta['dominio']}/diario/verificar", 'url_verificar_qr': f"https://{meta['dominio']}/diario/verificar?c={meta['codigo']}",
             'institucional': meta['institucional']}

    # 1ª passada: mede o miolo para saber a página de cada ato; o sumário pode precisar de páginas de continuação
    n_capa, paginas, total = 1, {}, 0
    for _ in range(4):
        paginas = {}
        medidor = rl_canvas.Canvas(io.BytesIO(), pagesize=A4)
        n_miolo = Miolo(tk, es, rodape, cabecalho, n_capa + 1).paginar(poderes_fl(paginas), medidor)
        total = n_capa + n_miolo
        sm = Sumario(org, paginas, tk)
        dados['linha_data'] = f"{DIAS[data.weekday()]} · {plural(total, 'página', 'páginas')} · {plural(len(atos), 'ato publicado', 'atos publicados')}"
        teste_c = rl_canvas.Canvas(io.BytesIO(), pagesize=A4)
        prox = desenhar_capa(teste_c, dados, sm, tk); precisa = 1
        while prox < len(sm.itens):
            prox = sm.desenhar(teste_c, MARGEM, H - 33 * mm, 30 * mm, W - 2 * MARGEM, prox); precisa += 1
        if precisa == n_capa:
            break
        n_capa = precisa
    # 2ª passada: desenha de verdade
    c = rl_canvas.Canvas(caminho, pagesize=A4, pageCompression=1)
    c.setTitle(f"Diário Oficial de {meta['municipio']} nº {numero}" + (' (TESTE)' if meta['teste'] else '')); c.setAuthor(ident.get('nome', ''))
    c.setSubject(f"Edição nº {numero} de {data.strftime('%d/%m/%Y')}"); c.setCreator('Portal — Diário Oficial Eletrônico')
    final = {}
    sm = Sumario(org, paginas, tk)
    prox = desenhar_capa(c, dados, sm, tk); rodape(c, 1); c.showPage()
    pg = 2
    while prox < len(sm.itens):
        prox = sumario_cont(c, sm, prox, pg); pg += 1
    Miolo(tk, es, rodape, cabecalho, pg).paginar(poderes_fl(final), c)
    c.save()
    return final, total, n_capa
