"""Carimbos laterais das assinaturas do Diário (16/11/2026; Docs/PEDIDO-DIARIO-CAPA.md, item A.1.2).

Cada assinatura ganha um carimbo vertical em TODAS as páginas: caixa só com borda fina na cor principal, sem fundo,
a 4 mm da borda. Cadernos dos Poderes na lateral esquerda (leitura de baixo para cima, empilhados); assinatura final
na direita (de cima para baixo).

Como a assinatura não pode ser alterada depois de aplicada, o carimbo é a APARÊNCIA DO PRÓPRIO CAMPO DE ASSINATURA:
o campo tem um widget por página e é criado na mesma atualização incremental em que a assinatura é aplicada.
Para as assinaturas anteriores isso é "preenchimento de formulário" (inclusão de campo de assinatura), permitido pelo
PAdES; o pyHanko valida todas como íntegras (verificado nos testes). Os dados vêm do certificado que assina (titular e AC)
e da hora gravada na própria assinatura (a sessão de assinatura usa exatamente a hora mostrada no carimbo).
A fonte (Public Sans) vai embutida no PDF, para manter o PDF/A.

O pyHanko só assina campos com um widget: os dois ajustes abaixo (aplicados só nesta assinatura) deixam usar o
primeiro widget como o do campo e preservam a aparência que já montamos."""
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

FONTES = Path(__file__).parent / 'static' / 'fonts'
TAM, PAD = 6.3, 3.2  # pt


def _hex(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _metricas(arquivo):
    from reportlab.pdfbase.ttfonts import TTFontFile
    return TTFontFile(str(FONTES / arquivo))


def _fonte(w, arquivo, nome):
    """Fonte TrueType simples (WinAnsi), embutida inteira (FontFile2): válida para PDF/A."""
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.generic import pdf_name
    t = _metricas(arquivo)
    larg = []
    for code in range(32, 256):
        try:
            ch = bytes([code]).decode('cp1252')
            larg.append(generic.NumberObject(int(round(t.charWidths.get(ord(ch), t.defaultWidth)))))
        except UnicodeDecodeError:
            larg.append(generic.NumberObject(0))
    dados = (FONTES / arquivo).read_bytes()
    ff = generic.StreamObject({pdf_name('/Length1'): generic.NumberObject(len(dados))}, stream_data=dados)
    ff.compress()
    desc = generic.DictionaryObject({
        pdf_name('/Type'): pdf_name('/FontDescriptor'), pdf_name('/FontName'): pdf_name('/' + nome), pdf_name('/Flags'): generic.NumberObject(32),
        pdf_name('/FontBBox'): generic.ArrayObject([generic.FloatObject(round(x, 1)) for x in t.bbox]), pdf_name('/ItalicAngle'): generic.FloatObject(t.italicAngle),
        pdf_name('/Ascent'): generic.FloatObject(t.ascent), pdf_name('/Descent'): generic.FloatObject(t.descent), pdf_name('/CapHeight'): generic.FloatObject(t.capHeight),
        pdf_name('/StemV'): generic.NumberObject(int(t.stemV)), pdf_name('/FontFile2'): w.add_object(ff)})
    return w.add_object(generic.DictionaryObject({
        pdf_name('/Type'): pdf_name('/Font'), pdf_name('/Subtype'): pdf_name('/TrueType'), pdf_name('/BaseFont'): pdf_name('/' + nome),
        pdf_name('/FirstChar'): generic.NumberObject(32), pdf_name('/LastChar'): generic.NumberObject(255), pdf_name('/Widths'): generic.ArrayObject(larg),
        pdf_name('/Encoding'): pdf_name('/WinAnsiEncoding'), pdf_name('/FontDescriptor'): w.add_object(desc)}))


def _fontes_existentes(w):
    """Reaproveita as fontes de um carimbo anterior (mesmo PDF), para não embutir de novo a cada assinatura."""
    af = w.root.get('/AcroForm')
    if af is None:
        return None
    for fr in af.get_object().get('/Fields', []):
        fld = fr.get_object()
        kids = fld.get('/Kids')
        if not kids or not str(fld.get('/T', '')).startswith('Assinatura_'):
            continue
        try:
            res = kids[0].get_object()['/AP']['/N'].get_object()['/Resources']['/Font']
            return res.raw_get('/CR'), res.raw_get('/CB')
        except (KeyError, AttributeError, TypeError):
            continue
    return None


def _esc(s):
    b = s.encode('cp1252', 'replace')
    return b.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')


def _linhas(partes, comp, metr):
    """partes: [(texto, 'B'|'R')]. Quebra em linhas de até `comp` pt (palavras inteiras). Devolve [[(texto, fonte)]] e o tamanho usado."""
    for tam in (TAM, 5.8, 5.3, 4.8):
        linhas, atual, larg = [], [], 0
        for txt, fn in partes:
            for i, pal in enumerate(txt.split(' ')):
                if not pal:
                    continue
                s = (' ' if atual else '') + pal
                lw = sum(metr[fn].charWidths.get(ord(ch), metr[fn].defaultWidth) for ch in s) * tam / 1000
                if larg + lw > comp and atual:
                    linhas.append(atual); atual, larg = [], 0
                    s = pal; lw = sum(metr[fn].charWidths.get(ord(ch), metr[fn].defaultWidth) for ch in s) * tam / 1000
                if atual and atual[-1][1] == fn:
                    atual[-1] = (atual[-1][0] + s, fn)
                else:
                    atual.append((s, fn))
                larg += lw
        if atual:
            linhas.append(atual)
        if len(linhas) <= 2:
            return linhas, tam
    return linhas[:2], 4.8


def _aparencia(w, larg, alt, lado, partes, cor, esc, fontes_ref, metr):
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.generic import pdf_name
    comp = alt - 2 * PAD - 4
    linhas, tam = _linhas(partes, comp, metr)
    lead = tam * 1.32
    asc = tam * .76
    r, g, b = _hex(cor); er, eg, eb = _hex(esc)
    ops = [f'{r:.3f} {g:.3f} {b:.3f} RG 0.85 w 0.45 0.45 {larg - .9:.2f} {alt - .9:.2f} re S']
    bloco = asc + (len(linhas) - 1) * lead + tam * .22
    x0 = (larg - bloco) / 2
    for k, ln in enumerate(linhas):
        wl = sum(sum(metr[fn].charWidths.get(ord(ch), metr[fn].defaultWidth) for ch in s) * tam / 1000 for s, fn in ln)
        if lado == 'esq':   # de baixo para cima: rotação de 90° (anti-horária); o "alto" do texto aponta para a esquerda
            bx = x0 + asc + k * lead; by = (alt - wl) / 2
            ops.append(f'BT 0 1 -1 0 {bx:.2f} {by:.2f} Tm')
        else:               # de cima para baixo: rotação de -90°; o "alto" do texto aponta para a direita
            bx = larg - x0 - asc - k * lead; by = (alt + wl) / 2
            ops.append(f'BT 0 -1 1 0 {bx:.2f} {by:.2f} Tm')
        for s, fn in ln:
            cr = f'{er:.3f} {eg:.3f} {eb:.3f}' if fn == 'B' else '0.114 0.165 0.133'
            ops.append(f'{cr} rg /C{fn} {tam:.2f} Tf (' + _esc(s).decode('latin-1') + ') Tj')
        ops.append('ET')
    st = generic.StreamObject({
        pdf_name('/Type'): pdf_name('/XObject'), pdf_name('/Subtype'): pdf_name('/Form'),
        pdf_name('/BBox'): generic.ArrayObject([generic.FloatObject(0), generic.FloatObject(0), generic.FloatObject(round(larg, 2)), generic.FloatObject(round(alt, 2))]),
        pdf_name('/Resources'): generic.DictionaryObject({pdf_name('/Font'): generic.DictionaryObject({pdf_name('/CR'): fontes_ref[0], pdf_name('/CB'): fontes_ref[1]})})},
        stream_data='\n'.join(ops).encode('latin-1'))
    st.compress()
    return w.add_object(st)


def criar_campo(w, campo, carimbo, titular, ac, momento: datetime, com_carimbo_tempo: bool):
    """Cria o campo de assinatura `campo` com um widget-carimbo em cada página. `carimbo`: dict com
    rotulo, lado ('esq'|'dir'), indice (posição entre os cadernos), n_cadernos, cor, esc."""
    from pyhanko.pdf_utils import generic
    from pyhanko.pdf_utils.generic import pdf_name
    from . import diario_layout as L
    metr = {'R': _metricas('PublicSans-Regular.ttf'), 'B': _metricas('PublicSans-Bold.ttf')}
    fontes_ref = _fontes_existentes(w) or (_fonte(w, 'PublicSans-Regular.ttf', 'PublicSans-Regular'), _fonte(w, 'PublicSans-Bold.ttf', 'PublicSans-Bold'))
    off = momento.strftime('%z'); off = f'{off[:3]}:{off[3:]}' if off else ''
    partes = [('ASSINADO DIGITALMENTE', 'B'),
              (f" · {carimbo['rotulo']} · {titular} · {momento.strftime('%d/%m/%Y %H:%M:%S')} ({off}) · Certificado: {ac}" + (' · Carimbo do tempo aplicado' if com_carimbo_tempo else ''), 'R')]
    ret = L.carimbo_retangulos(carimbo['n_cadernos'])
    fld = generic.DictionaryObject({pdf_name('/FT'): pdf_name('/Sig'), pdf_name('/T'): generic.TextStringObject(campo)})
    fref = w.add_object(fld)
    kids = generic.ArrayObject()
    aps = {}
    paginas = _paginas(w)
    for i, pref in enumerate(paginas):
        tipo = 'capa' if i == 0 else 'miolo'
        x, y, lw, lh = ret[tipo]['esq'][carimbo['indice']] if carimbo['lado'] == 'esq' else ret[tipo]['dir']
        if tipo not in aps:
            aps[tipo] = _aparencia(w, lw, lh, carimbo['lado'], partes, carimbo['cor'], carimbo['esc'], fontes_ref, metr)
        wd = generic.DictionaryObject({
            pdf_name('/Type'): pdf_name('/Annot'), pdf_name('/Subtype'): pdf_name('/Widget'), pdf_name('/F'): generic.NumberObject(4),
            pdf_name('/Rect'): generic.ArrayObject([generic.FloatObject(round(v, 2)) for v in (x, y, x + lw, y + lh)]),
            pdf_name('/AP'): generic.DictionaryObject({pdf_name('/N'): aps[tipo]}), pdf_name('/P'): pref, pdf_name('/Parent'): fref,
            pdf_name('/TU'): generic.TextStringObject(''.join(t for t, _ in partes))})
        ref = w.add_object(wd); kids.append(ref)
        pg = pref.get_object()
        annots = pg.get('/Annots')
        if annots is None:
            pg[pdf_name('/Annots')] = generic.ArrayObject([ref])
        else:
            annots.get_object().append(ref)
            if isinstance(pg.raw_get('/Annots'), generic.IndirectObject):
                w.update_container(annots.get_object())
        w.update_container(pg)
    fld[pdf_name('/Kids')] = kids
    raw = w.root.raw_get('/AcroForm') if '/AcroForm' in w.root else None
    if raw is None:
        w.root[pdf_name('/AcroForm')] = generic.DictionaryObject({pdf_name('/Fields'): generic.ArrayObject([fref]), pdf_name('/SigFlags'): generic.NumberObject(3)})
        w.update_root()
    else:
        af = raw.get_object()
        af['/Fields'].append(fref)
        if isinstance(raw, generic.IndirectObject):
            w.update_container(af)
        else:
            w.update_root()
    return fref


def _paginas(w):
    """Referências das páginas na ordem (percorre a árvore de páginas)."""
    out = []
    def vai(no):
        o = no.get_object()
        if o.get('/Type') == '/Pages':
            for k in o['/Kids']:
                vai(k)
        else:
            out.append(no)
    vai(w.root.raw_get('/Pages'))
    return out


def ajustes_pyhanko():
    """Permite assinar o campo com um widget por página (usa o primeiro como o do campo) sem trocar a aparência já montada."""
    from pyhanko.sign.signers import cms_embedder as CE
    if getattr(CE, '_carimbo_ok', False):
        return
    orig_annot, orig_apply = CE.get_single_field_annot, CE.SigAppearanceSetup.apply
    def annot(field):
        kids = field.get('/Kids')
        if kids and len(kids) > 1 and all('/AP' in k.get_object() for k in kids):
            return kids[0].get_object()
        return orig_annot(field)
    def apply(self, sig_annot, writer):
        if '/AP' in sig_annot:
            return
        return orig_apply(self, sig_annot, writer)
    CE.get_single_field_annot = annot
    CE.SigAppearanceSetup.apply = apply
    CE._carimbo_ok = True


def agora():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(microsecond=0)
