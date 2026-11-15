"""Fase 9 — editor de texto: HTML limpo e acessível (lista fechada de tags), com imagens só do próprio portal e texto alternativo obrigatório.
A limpeza é feita SEMPRE no servidor (nh3); a do navegador, ao colar do Word, é só conforto."""
import html as H
import re
import nh3

TAGS = {'h2', 'h3', 'h4', 'p', 'br', 'strong', 'em', 'u', 's', 'sub', 'sup', 'mark', 'hr', 'ul', 'ol', 'li', 'a', 'blockquote',
        'table', 'thead', 'tbody', 'tr', 'th', 'td', 'figure', 'img', 'figcaption', 'caption'}
ATRIBUTOS = {'a': {'href'}, 'img': {'src', 'alt'}, 'th': {'scope'}}
# 15/11/2026: alinhamento por classe (nunca style) e vídeo do YouTube como link marcado (vira player só na exibição)
ALINHA = {'al-centro', 'al-dir', 'al-just'}
CLASSES = {t: ALINHA for t in ('p', 'h2', 'h3', 'h4', 'figure', 'td', 'th', 'li', 'blockquote')}
CLASSES['a'] = {'video'}
for _t, _c in CLASSES.items():
    ATRIBUTOS[_t] = ATRIBUTOS.get(_t, set()) | {'class'}
YOUTUBE = re.compile(r'^https://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube-nocookie\.com/embed/|youtube\.com/embed/)([\w-]{11})')

def _filtro(tag, attr, valor):
    if attr == 'class':  # só as classes da lista (alinhamento, vídeo); o resto cai
        v = ' '.join(x for x in (valor or '').split() if x in CLASSES.get(tag, ()))
        return v or None
    if tag == 'img' and attr == 'src':
        return valor if re.fullmatch(r'/midia/[0-9a-f]{32}\.(png|jpg|webp)', valor or '') else None
    if tag == 'a' and attr == 'href':
        return valor if re.match(r'^(https://|mailto:|/)[^\s"<>]*$', valor or '') and not (valor or '').startswith('//') else None
    if tag == 'th' and attr == 'scope':
        return valor if valor in ('col', 'row') else None
    return valor

def limpar(html):
    """Devolve (html_limpo, problemas). Problemas: imagem sem texto alternativo, imagem de fora do portal."""
    bruto = html or ''
    # equivalências antes da lista fechada: h1 vira h2 (o título da página é o h1), b/i viram strong/em
    for a, b in (('h1', 'h2'), ('b', 'strong'), ('i', 'em'), ('strike', 's'), ('del', 's'), ('ins', 'u'), ('h5', 'h4'), ('h6', 'h4')):
        bruto = re.sub(rf'<(/?){a}(\s[^>]*)?>', rf'<\1{b}>', bruto, flags=re.I)
    limpo = nh3.clean(bruto, tags=TAGS, attributes=ATRIBUTOS, attribute_filter=_filtro, url_schemes={'https', 'mailto'},
                      link_rel='noopener noreferrer', strip_comments=True)
    limpo = re.sub(r'<img(?![^>]*\bsrc=)[^>]*>', '', limpo)  # imagem cujo endereço foi recusado
    problemas = []  # texto alternativo opcional (14/11/2026): imagem sem alt fica como decorativa (alt="")
    limpo = re.sub(r'<img\b(?![^>]*\balt=)', '<img alt=""', limpo)
    if bruto.count('<img') > limpo.count('<img'):
        problemas.append('Imagens de fora do portal foram removidas: envie a imagem pelo botão “Imagem” do editor.')
    limpo = re.sub(r'<p>\s*</p>', '', limpo).strip()
    return limpo, problemas

def texto(html):
    """Texto puro (busca e resumo)."""
    t = re.sub(r'<(br|/p|/h[23]|/li|/tr|/blockquote|/figcaption)\s*/?>', '\n', html or '')
    return re.sub(r'\n{3,}', '\n\n', H.unescape(re.sub(r'<[^>]+>', '', t))).strip()

def exibir(html):
    """HTML já limpo -> HTML do portal: o link marcado como vídeo do YouTube vira player youtube-nocookie (com título)."""
    from markupsafe import Markup
    def video(m):
        attrs, rotulo = m.group(1), m.group(2)
        h = re.search(r'href="([^"]+)"', attrs)
        y = YOUTUBE.match(H.unescape(h.group(1))) if h else None
        if not y:
            return m.group(0)
        titulo = re.sub(r'<[^>]+>', '', rotulo).strip() or 'Vídeo'
        return (f'<span class="video"><iframe src="https://www.youtube-nocookie.com/embed/{y.group(1)}" title="{H.escape(H.unescape(titulo), quote=True)}" loading="lazy" '
                f'allow="accelerometer; encrypted-media; gyroscope; picture-in-picture" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></span>')
    saida = re.sub(r'<a\b([^>]*\bclass="video"[^>]*)>(.*?)</a>', video, html or '', flags=re.S)
    saida = re.sub(r'<p>\s*(<span class="video">.*?</span>)\s*</p>', r'<div>\1</div>', saida, flags=re.S)
    return Markup(saida)
