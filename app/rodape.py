"""Rodapé (16/11/2026): cor editável pelo painel, faixa das colunas com imagem de fundo, camada de cor com transparência e mascote.

Tudo por órgão, sem código por órgão:
- cor do rodapé: `identidade.cor_rodape` (vazio = cor padrão do tipo de órgão, a de sempre); os tons das faixas são derivados dela;
- imagem de fundo: `identidade.rodape` (mesmo formato das outras imagens + url_960, decorativa e lum95);
- camada e mascote: `config.rodape` (padrões em PADRAO; a migração 036 grava os padrões sem sobrescrever).
Camadas da faixa das colunas, de baixo para cima: 0 imagem, 1 camada de cor, 2 mascote, 3 textos."""
import io
from pathlib import Path
from . import db

# cores de hoje (antes desta opção) — continuam o padrão; com elas o rodapé fica idêntico ao anterior
PADRAO_COR = {'executivo': '#17212B', 'legislativo': '#16291A'}
LEGADO = {
    '#17212B': {'f1': '#1E2B37', 'bd': '#2E3A46', 'f4': '#121A22', 'borda': '#3A4856', 'borda2': '#4B5A68', 'viz': '#3A4856', 'bd3': '#2E3A46'},
    '#16291A': {'f1': '#1F3A22', 'bd': '#2C4A30', 'f4': '#0F1F12', 'borda': '#3A4856', 'borda2': '#4B5A68', 'viz': '#3A5A3E', 'bd3': '#2E3A46'},
}
TITULO = {'executivo': '#F0B429', 'legislativo': '#F7C948'}  # títulos das colunas e ícones (não mudam)
TEXTO, TEXTO_F4, BRANCO = '#C9D1D9', '#AEB8C2', '#FFFFFF'
MIN_AA = 4.5

PADRAO = {'camada': 85, 'mascote_exibir': True, 'mascote_lado': 'esq', 'mascote_altura': 220, 'mascote_opacidade': 100,
          'mascote_celular': False, 'mascote_suspender_eleitoral': True}
ALTURA_MIN, ALTURA_MAX, ALTURA_CEL = 120, 320, 140
LARGURAS_FUNDO = (1920, 960)

def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

def _hex(c):
    return '#%02X%02X%02X' % tuple(max(0, min(255, round(x))) for x in c)

def mistura(a, b, t):
    """Mistura #RRGGBB (t = peso da segunda)."""
    return _hex(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))

def _lum(c):
    c = [x / 255 for x in (_rgb(c) if isinstance(c, str) else c)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)

def cor_padrao(tipo):
    return PADRAO_COR.get(tipo, PADRAO_COR['executivo'])

def cor_de(ident, tipo):
    c = (ident or {}).get('cor_rodape') or ''
    return c.upper() if len(c) == 7 and c.startswith('#') else cor_padrao(tipo)

def tons(cor):
    """Tons das faixas do rodapé derivados da cor base (as cores padrão devolvem exatamente os tons de antes)."""
    cor = cor.upper()
    if cor in LEGADO:
        t = LEGADO[cor]
    else:
        bd, borda = mistura(cor, BRANCO, .13), mistura(cor, BRANCO, .18)
        t = {'f1': mistura(cor, BRANCO, .045), 'bd': bd, 'f4': mistura(cor, '#000000', .22), 'borda': borda, 'borda2': mistura(cor, BRANCO, .26), 'viz': borda, 'bd3': bd}
    return dict(t, base=cor, rgb='%d %d %d' % _rgb(cor))

def checar_cor(cor, tipo):
    """Problemas de contraste AA da cor do rodapé com os textos que já existem (lista vazia = ok)."""
    import re
    if not re.fullmatch(r'#[0-9A-Fa-f]{6}', cor or ''):
        return ['Use o formato #RRGGBB.']
    t, erros = tons(cor), []
    for nome, fundo, texto in (('texto das colunas', t['base'], TEXTO), ('títulos das colunas', t['base'], TITULO.get(tipo, TITULO['executivo'])),
                               ('faixa do nome (texto branco)', t['f1'], BRANCO), ('faixa do © (texto)', t['f4'], TEXTO_F4)):
        c = contraste(fundo, texto)
        if c < MIN_AA:
            erros.append(f'{nome}: {c:.1f}:1 (mínimo 4,5:1)'.replace('.', ',', 1))
    return erros

def css_vars(ident, tipo):
    """Atributo style do <footer> só quando a cor foi mudada no painel (sem mudança, vale o CSS de sempre)."""
    cor = cor_de(ident, tipo)
    if cor == cor_padrao(tipo):
        return ''
    t = tons(cor)
    return (f"--rod:{t['base']};--rod-rgb:{t['rgb']};--rod-f1:{t['f1']};--rod-bd:{t['bd']};--rod-f4:{t['f4']};"
            f"--rod-borda:{t['borda']};--rod-borda2:{t['borda2']};--rod-viz:{t['viz']};--rod-bd3:{t['bd3']}")

# ---- camada e mascote ----
def conf(banco):
    c = dict(PADRAO)
    salvo = db.cfg(banco, 'rodape', {}) or {}
    if isinstance(salvo, dict):
        c.update({k: salvo[k] for k in PADRAO if k in salvo})
    return c

def _int(v, a, b, padrao, passo=1):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return padrao
    return max(a, min(b, round(n / passo) * passo))

def validar(form):
    """Formulário da seção Rodapé -> conf (valores sempre dentro dos limites)."""
    return {'camada': _int(form.get('camada'), 0, 100, PADRAO['camada'], 5),
            'mascote_exibir': form.get('mascote_exibir') == '1',
            'mascote_lado': 'dir' if form.get('mascote_lado') == 'dir' else 'esq',
            'mascote_altura': _int(form.get('mascote_altura'), ALTURA_MIN, ALTURA_MAX, PADRAO['mascote_altura'], 10),
            'mascote_opacidade': _int(form.get('mascote_opacidade'), 0, 100, PADRAO['mascote_opacidade'], 5),
            'mascote_celular': form.get('mascote_celular') == '1',
            'mascote_suspender_eleitoral': form.get('mascote_suspender_eleitoral') == '1'}

def fundo_pior(cor, lum95, camada):
    """Cor de fundo no pior caso: a cor do rodapé, na opacidade da camada, sobre o trecho mais claro da imagem."""
    g = 255 * (lum95 if lum95 is not None else 1.0)
    return mistura(_hex((g, g, g)), cor, camada / 100)

def contraste_camada(cor, lum95, camada, tipo):
    f = fundo_pior(cor, lum95, camada)
    return contraste(f, TEXTO), contraste(f, TITULO.get(tipo, TITULO['executivo']))

def minimo_seguro(cor, lum95, tipo):
    """Menor opacidade da camada (passo de 5%) com textos e títulos em AA."""
    for a in range(0, 101, 5):
        if min(contraste_camada(cor, lum95, a, tipo)) >= MIN_AA:
            return a
    return 100

def luminancia_p95(dados):
    """Luminância relativa (0–1, sRGB linear achatado em cinza) do percentil 95: o trecho mais claro da imagem."""
    from PIL import Image
    im = Image.open(io.BytesIO(dados)).convert('RGB')
    im.thumbnail((480, 480))
    v = sorted(_lum(c) for c in im.getdata())
    l = v[min(len(v) - 1, int(len(v) * 0.95))]
    # volta para valor de cinza sRGB (0–1) equivalente, que é o que fundo_pior mistura
    x = l * 12.92 if l <= 0.0031308 else 1.055 * l ** (1 / 2.4) - 0.055
    return round(x, 4)

def gerar_versoes(dados, pasta: Path):
    """WebP 1920 e 960 px do fundo do rodapé (nomes aleatórios, como os demais arquivos de mídia). Devolve {largura: (nome, bytes)}."""
    import secrets
    from PIL import Image
    im = Image.open(io.BytesIO(dados)); im.load()
    if im.mode != 'RGB':
        im = im.convert('RGB')
    out = {}
    for w in LARGURAS_FUNDO:
        x = im if im.width <= w else im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        x.save(buf, 'WEBP', quality=78, method=6)
        nome = f'{secrets.token_hex(16)}.webp'
        (pasta / nome).write_bytes(buf.getvalue())
        out[w] = (nome, buf.tell())
    return out

def mascote_visivel(ident, c, defeso):
    m = (ident or {}).get('mascote') or {}
    return bool(m.get('url')) and c['mascote_exibir'] and not (defeso and c['mascote_suspender_eleitoral'])
