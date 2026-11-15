"""Diário Oficial — pré-formatação automática do texto do ato (15/11/2026) e conversão do HTML do editor para o PDF da edição.

Pré-formatação (botão "Pré-formatar" no envio do ato; o servidor de quem envia confere e ajusta depois, documento por documento):
- título do ato (LEI, DECRETO, PORTARIA... com número) centralizado em negrito;
- ementa ("Dispõe sobre...", "Altera...") recuada à direita, como manda a técnica legislativa (LC 95/1998, art. 5º);
- preâmbulo justificado; "DECRETA:", "RESOLVE:" e semelhantes em negrito;
- CAPÍTULO/SEÇÃO/TÍTULO centralizados; artigos com "Art. 1º" até o 9º e "Art. 10." em diante (LC 95/1998, art. 10, I);
  parágrafos "§ 1º", "Parágrafo único.", incisos "I –" e alíneas "a)";
- local e data e o bloco de assinatura centralizados.
Nada é inventado: só muda alinhamento, negrito e a grafia dos rótulos (Art., §, incisos). Texto sem nenhum desses padrões fica justificado.
Tabelas, listas e linhas divisórias ficam como estão. Rodar duas vezes dá o mesmo resultado."""
import html as H
import re
from html.parser import HTMLParser

from . import editor

TIPOS_TITULO = r'(?:LEI(?:\s+COMPLEMENTAR)?|DECRETO(?:\s+LEGISLATIVO)?|PORTARIA|RESOLU[ÇC][ÃA]O|EDITAL|EXTRATO|AVISO|ATO(?:\s+DA\s+MESA)?|INSTRU[ÇC][ÃA]O\s+NORMATIVA|EMENDA|RETIFICA[ÇC][ÃA]O|TERMO|CONTRATO|ERRATA)'
R_TITULO = re.compile(rf'^{TIPOS_TITULO}\b.{{0,120}}$', re.I)
R_EMENTA = re.compile(r'^(Disp[õo]e|Altera|Institui|Autoriza|Regulamenta|Nomeia|Exonera|Concede|Estabelece|Abre|Declara|Cria|Revoga|Fixa|Aprova|Denomina|'
                      r'Homologa|Designa|Disciplina|Ratifica|Prorroga|Convoca|Torna|Retifica|Inclui|Acrescenta|D[áa]\s+nova|Reajusta|Suplementa)\b', re.I)
R_DISPOSITIVO = re.compile(r'^(D\s*E\s*C\s*R\s*E\s*T\s*A|R\s*E\s*S\s*O\s*L\s*V\s*E|DECRETA|RESOLVE|PROMULGA|FAZ\s+SABER[^:]{0,200}|TORNA\s+P[ÚU]BLICO[^:]{0,200}|SANCIONA[^:]{0,200})\s*:?\s*$', re.I)
R_DIVISAO = re.compile(r'^(T[ÍI]TULO|CAP[ÍI]TULO|SE[ÇC][ÃA]O|SUBSE[ÇC][ÃA]O|LIVRO)\s+([IVXLCDM]+|[ÚU]NIC[OA])\b\s*[-–—.]?\s*(.*)$', re.I)
R_ARTIGO = re.compile(r'^Art(?:igo)?\.?\s*(\d+)\s*(?:[º°ª]|o(?=[\s.\-–—]))?\s*\.?\s*[-–—]?\s*', re.I)
R_PARAG = re.compile(r'^§\s*(\d+)\s*(?:[º°ª]|o(?=[\s.\-–—]))?\s*\.?\s*[-–—]?\s*')
R_UNICO = re.compile(r'^Par[áa]grafo\s+[úu]nico\s*[.:\-–—]?\s*', re.I)
R_INCISO = re.compile(r'^([IVXLC]+)\s*[-–—.)]\s+(?=\S)')
R_ALINEA = re.compile(r'^([a-z])\s*\)\s*')
R_DATA = re.compile(r'\b\d{1,2}[º°]?\s+de\s+[a-zç]+\s+de\s+\d{4}\.?\s*$', re.I)
R_FECHO = re.compile(r'^(Registr[ae]-se|Publique-se|Cumpra-se|Registrad[oa]\s+e\s+publicad[oa]|Dê-se\s+ci[êe]ncia)', re.I)

INLINE = {'strong', 'em', 'u', 's', 'sub', 'sup', 'mark', 'a', 'br'}
BLOCOS_TEXTO = {'p', 'h2', 'h3', 'h4', 'blockquote', 'li', 'div'}


# ---------- árvore simples do HTML limpo (lista fechada de tags do editor) ----------
class _No:
    def __init__(self, tag, attrs=None, pai=None):
        self.tag, self.attrs, self.pai, self.filhos = tag, dict(attrs or []), pai, []

class _Arvore(HTMLParser):
    VAZIAS = {'br', 'hr', 'img'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = _No('raiz'); self.atual = self.raiz
    def handle_starttag(self, tag, attrs):
        n = _No(tag, attrs, self.atual); self.atual.filhos.append(n)
        if tag not in self.VAZIAS:
            self.atual = n
    def handle_startendtag(self, tag, attrs):
        self.atual.filhos.append(_No(tag, attrs, self.atual))
    def handle_endtag(self, tag):
        n = self.atual
        while n is not self.raiz and n.tag != tag:
            n = n.pai
        if n is not self.raiz:
            self.atual = n.pai
    def handle_data(self, d):
        self.atual.filhos.append(d)

def arvore(html):
    p = _Arvore(); p.feed(html or ''); p.close()
    return p.raiz

def _texto(n):
    if isinstance(n, str):
        return n
    if n.tag == 'br':
        return '\n'
    return ''.join(_texto(f) for f in n.filhos)

def _html(n):
    if isinstance(n, str):
        return H.escape(n, quote=False)
    attrs = ''.join(f' {k}="{H.escape(v or "", quote=True)}"' for k, v in n.attrs.items())
    if n.tag in _Arvore.VAZIAS:
        return f'<{n.tag}{attrs}>'
    return f'<{n.tag}{attrs}>' + ''.join(_html(f) for f in n.filhos) + f'</{n.tag}>'

def _so_texto_ou_negrito_inicial(n):
    """Bloco sem formatação interna (ou só o rótulo em negrito no começo, como a própria pré-formatação deixa)."""
    fs = [f for f in n.filhos if not (isinstance(f, str) and not f.strip())]
    for i, f in enumerate(fs):
        if isinstance(f, str) or f.tag == 'br':
            continue
        if f.tag == 'strong' and i == 0:
            continue
        return False
    return True


# ---------- pré-formatação ----------
def _ordinal(n, sinal):
    n = int(n)
    return f'{sinal} {n}º' if n <= 9 else f'{sinal} {n}.'

def _p(classe, conteudo, tag='p'):
    return f'<{tag}{f" class={chr(34)}{classe}{chr(34)}" if classe else ""}>{conteudo}</{tag}>'

def _e(t):
    return H.escape(t, quote=False)

def _linhas(raiz):
    """Lista de ('texto', linha, nó_original) ou ('bruto', html) em ordem. <br> dentro de parágrafo vira linha própria."""
    out = []
    def visitar(n):
        for f in n.filhos:
            if isinstance(f, str):
                for l in f.split('\n'):
                    if l.strip():
                        out.append(('texto', l, None))
                continue
            if f.tag in ('table', 'ul', 'ol', 'hr', 'figure', 'img'):
                out.append(('bruto', _html(f)))
            elif f.tag in BLOCOS_TEXTO:
                if any(not isinstance(x, str) and x.tag in ('table', 'ul', 'ol', 'p', 'figure') for x in f.filhos):
                    visitar(f)
                elif _so_texto_ou_negrito_inicial(f):
                    for l in _texto(f).split('\n'):
                        if l.strip():
                            out.append(('texto', l, None))
                else:
                    out.append(('texto', _texto(f).replace('\n', ' '), f))
            else:
                t = _texto(f)
                for l in t.split('\n'):
                    if l.strip():
                        out.append(('texto', l, None))
    visitar(raiz)
    return out

def preformatar(html_ou_texto):
    """HTML do editor (ou texto simples) → HTML pré-formatado (já passado pela limpeza do editor)."""
    entrada = html_ou_texto or ''
    if '<' not in entrada:  # texto simples: cada linha vira um parágrafo
        entrada = ''.join(f'<p>{_e(l)}</p>' for l in entrada.splitlines() if l.strip())
    limpo, _ = editor.limpar(entrada)
    itens = _linhas(arvore(limpo))
    out, i_titulo, dispositivo_visto, fecho = [], None, False, False
    textos = [k for k, it in enumerate(itens) if it[0] == 'texto']
    # bloco de assinatura: depois da linha de local e data, as linhas curtas finais
    i_data = next((k for k in reversed(textos) if R_DATA.search(re.sub(r'\s+', ' ', itens[k][1]).strip()) and len(itens[k][1]) <= 160), None)
    for k, it in enumerate(itens):
        if it[0] == 'bruto':
            out.append(it[1]); continue
        t = re.sub(r'\s+', ' ', it[1]).strip()
        orig = it[2]
        def com_formatacao(classe, tag='p'):  # bloco com negrito/itálico/link no meio: mantém o conteúdo e só ajusta o alinhamento
            return _p(classe, ''.join(_html(f) for f in orig.filhos).strip(), tag)
        primeiro = k == (textos[0] if textos else -1)
        if i_titulo is None and k in textos[:3] and R_TITULO.match(t) and len(t) <= 140 and not R_ARTIGO.match(t):
            i_titulo = k
            out.append(_p('al-centro', f'<strong>{_e(t.upper())}</strong>', 'h3')); continue
        if i_titulo is not None and not dispositivo_visto and k == next((x for x in textos if x > i_titulo), None) and R_EMENTA.match(t):
            out.append(_p('al-just', com_formatacao('').removeprefix('<p>').removesuffix('</p>') if orig else _e(t), 'blockquote')); continue
        if R_DISPOSITIVO.match(t) and len(t) <= 220:
            dispositivo_visto = True
            out.append(_p('', f'<strong>{_e(t.upper() if len(t) < 30 else t)}</strong>')); continue
        m = R_DIVISAO.match(t)
        if m and len(t) <= 160:
            rot = f'{m.group(1).upper()} {m.group(2).upper()}'
            out.append(_p('al-centro', f'<strong>{_e(rot)}</strong>' + (f'<br>{_e(m.group(3).upper())}' if m.group(3) else ''), 'h4')); continue
        if out and out[-1].startswith('<h4') and '<br>' not in out[-1] and len(t) <= 120 and t.upper() == t and re.search('[A-ZÀ-Ú]', t):
            out.append(_p('al-centro', f'<strong>{_e(t)}</strong>')); continue  # nome do capítulo/seção na linha de baixo
        if i_data is not None and k == i_data:
            fecho = True
            out.append(_p('al-centro', _e(t))); continue
        if R_FECHO.match(t):
            out.append(_p('al-just', _e(t))); continue
        if fecho and len(t) <= 100 and not R_ARTIGO.match(t):
            # bloco de assinatura: o nome (primeira linha depois da data) em negrito; cargo e demais linhas normais
            primeira = out and out[-1].startswith('<p class="al-centro">') and R_DATA.search(re.sub('<[^>]+>', '', out[-1]))
            out.append(_p('al-centro', f'<strong>{_e(t.upper())}</strong>' if primeira else _e(t))); continue
        for rx, rot in ((R_ARTIGO, 'Art.'), (R_PARAG, '§')):
            m = rx.match(t)
            if m and t[m.end():].strip():
                out.append(_p('al-just', f'<strong>{_ordinal(m.group(1), rot)}</strong> {_e(t[m.end():].strip())}')); break
        else:
            m = R_UNICO.match(t)
            if m and t[m.end():].strip():
                out.append(_p('al-just', f'<strong>Parágrafo único.</strong> {_e(t[m.end():].strip())}')); continue
            m = R_INCISO.match(t)
            if m and not primeiro:
                out.append(_p('al-just', f'{m.group(1).upper()} – {_e(t[m.end():].strip())}')); continue
            m = R_ALINEA.match(t)
            if m and not primeiro:
                out.append(_p('al-just', f'{m.group(1)}) {_e(t[m.end():].strip())}')); continue
            if R_FECHO.match(t):
                out.append(_p('al-just', _e(t))); continue
            out.append(com_formatacao('al-just') if orig else _p('al-just', _e(t)))
    final, _ = editor.limpar(''.join(out))
    return final


# ---------- HTML do editor → elementos do PDF (reportlab) ----------
def _inline(n):
    """Conteúdo de um bloco → marcação de parágrafo do reportlab (b, i, u, strike, super, sub, link)."""
    if isinstance(n, str):
        return H.escape(n, quote=False)
    dentro = ''.join(_inline(f) for f in n.filhos)
    t = n.tag
    if t == 'br':
        return '<br/>'
    if t == 'strong':
        return f'<b>{dentro}</b>'
    if t == 'em':
        return f'<i>{dentro}</i>'
    if t == 'u':
        return f'<u>{dentro}</u>'
    if t == 's':
        return f'<strike>{dentro}</strike>'
    if t == 'sup':
        return f'<super>{dentro}</super>'
    if t == 'sub':
        return f'<sub>{dentro}</sub>'
    if t == 'mark':
        return f'<font backColor="#FFF0A6">{dentro}</font>'
    if t == 'a':
        href = n.attrs.get('href', '')
        if href.startswith('https://') or href.startswith('mailto:'):
            return f'<link href="{H.escape(href, quote=True)}" color="#0E4D64"><u>{dentro}</u></link>'
        return dentro
    return dentro

def elementos_pdf(html, corpo):
    """Flowables do reportlab para o texto formatado do ato. `corpo` é o estilo de parágrafo base da edição."""
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle
    ALN = {'al-centro': TA_CENTER, 'al-dir': TA_RIGHT, 'al-just': TA_JUSTIFY}
    def estilo(base, n, **kw):
        al = next((ALN[c] for c in (n.attrs.get('class') or '').split() if c in ALN), kw.pop('alignment', TA_LEFT))
        return ParagraphStyle(f'x{id(n)}', parent=base, alignment=al, **kw)
    h = {'h2': dict(fontName='Helvetica-Bold', fontSize=12.5, leading=16, spaceBefore=8, spaceAfter=4),
         'h3': dict(fontName='Helvetica-Bold', fontSize=11.5, leading=15, spaceBefore=6, spaceAfter=4),
         'h4': dict(fontName='Helvetica-Bold', fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=2)}
    el = []
    def lista(n, nivel):
        num = 0
        for li in [f for f in n.filhos if not isinstance(f, str) and f.tag == 'li']:
            num += 1
            sub = [f for f in li.filhos if not isinstance(f, str) and f.tag in ('ul', 'ol')]
            txt = ''.join(_inline(f) for f in li.filhos if isinstance(f, str) or f.tag not in ('ul', 'ol')).strip()
            if txt:
                el.append(Paragraph(txt, estilo(corpo, li, leftIndent=14 * (nivel + 1), bulletIndent=14 * nivel + 2, spaceAfter=2),
                                    bulletText=f'{num}.' if n.tag == 'ol' else '•'))
            for s in sub:
                lista(s, nivel + 1)
    def bloco(n):
        if isinstance(n, str):
            if n.strip():
                el.append(Paragraph(H.escape(n.strip(), quote=False), corpo))
            return
        t = n.tag
        if t == 'p' or t == 'div':
            txt = ''.join(_inline(f) for f in n.filhos).strip()
            if txt:
                el.append(Paragraph(txt, estilo(corpo, n, spaceAfter=4)))
        elif t in h:
            el.append(Paragraph(''.join(_inline(f) for f in n.filhos).strip(), estilo(corpo, n, **h[t])))
        elif t == 'blockquote':
            el.append(Paragraph(''.join(_inline(f) for f in n.filhos).strip(), estilo(corpo, n, leftIndent=8 * cm, spaceBefore=4, spaceAfter=8, alignment=TA_JUSTIFY)))
        elif t in ('ul', 'ol'):
            lista(n, 0)
        elif t == 'hr':
            el.append(HRFlowable(width='100%', thickness=0.6, color='#9AA3AD', spaceBefore=6, spaceAfter=6))
        elif t == 'table':
            linhas = []
            for tr in _todos(n, 'tr'):
                cels = [c for c in tr.filhos if not isinstance(c, str) and c.tag in ('td', 'th')]
                linhas.append([Paragraph(('<b>%s</b>' if c.tag == 'th' else '%s') % ''.join(_inline(f) for f in c.filhos).strip(),
                                         estilo(corpo, c, fontSize=9.5, leading=12)) for c in cels])
            if linhas:
                ncol = max(len(l) for l in linhas)
                linhas = [l + [''] * (ncol - len(l)) for l in linhas]
                tb = Table(linhas, colWidths=[17 * cm / ncol] * ncol, repeatRows=1 if any(c.tag == 'th' for c in _todos(n, 'th')) else 0)
                tb.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, '#9AA3AD'), ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                        ('LEFTPADDING', (0, 0), (-1, -1), 4), ('RIGHTPADDING', (0, 0), (-1, -1), 4)]))
                el.append(tb); el.append(Spacer(1, 6))
        elif t in ('figure', 'img', 'figcaption'):
            return  # o Diário não leva imagens no texto do ato (o editor do Diário não oferece imagem)
        else:
            for f in n.filhos:
                bloco(f)
    for f in arvore(html).filhos:
        bloco(f)
    return el

def _todos(n, tag):
    r = []
    for f in n.filhos:
        if isinstance(f, str):
            continue
        if f.tag == tag:
            r.append(f)
        r.extend(_todos(f, tag))
    return r
