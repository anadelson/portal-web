"""Fase 9 — editor de texto: HTML limpo e acessível (lista fechada de tags), com imagens só do próprio portal e texto alternativo obrigatório.
A limpeza é feita SEMPRE no servidor (nh3); a do navegador, ao colar do Word, é só conforto."""
import html as H
import re
import nh3

TAGS = {'h2', 'h3', 'p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'a', 'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'figure', 'img', 'figcaption', 'caption'}
ATRIBUTOS = {'a': {'href'}, 'img': {'src', 'alt'}, 'th': {'scope'}}

def _filtro(tag, attr, valor):
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
    for a, b in (('h1', 'h2'), ('b', 'strong'), ('i', 'em')):
        bruto = re.sub(rf'<(/?){a}(\s[^>]*)?>', rf'<\1{b}>', bruto, flags=re.I)
    limpo = nh3.clean(bruto, tags=TAGS, attributes=ATRIBUTOS, attribute_filter=_filtro, url_schemes={'https', 'mailto'},
                      link_rel='noopener noreferrer', strip_comments=True)
    limpo = re.sub(r'<img(?![^>]*\bsrc=)[^>]*>', '', limpo)  # imagem cujo endereço foi recusado
    problemas = []
    for m in re.finditer(r'<img\b[^>]*>', limpo):
        alt = re.search(r'\balt="([^"]*)"', m.group(0))
        if not alt or len(H.unescape(alt.group(1)).strip()) < 5:
            problemas.append('Há imagem sem texto alternativo (pelo menos 5 caracteres).')
            break
    if bruto.count('<img') > limpo.count('<img'):
        problemas.append('Imagens de fora do portal foram removidas: envie a imagem pelo botão “Imagem” do editor.')
    limpo = re.sub(r'<p>\s*</p>', '', limpo).strip()
    return limpo, problemas

def texto(html):
    """Texto puro (busca e resumo)."""
    t = re.sub(r'<(br|/p|/h[23]|/li|/tr|/blockquote|/figcaption)\s*/?>', '\n', html or '')
    return re.sub(r'\n{3,}', '\n\n', H.unescape(re.sub(r'<[^>]+>', '', t))).strip()
