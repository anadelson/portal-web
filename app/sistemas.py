"""Sistemas de terceiros (25/11/2026): endereços de sistemas contratados pelo órgão que ficam fora deste portal.

  transparencia  portal da transparência da empresa contratada (ex.: o que publica receitas, despesas e dados abertos);
                 aparece como "Transparência em detalhes" na página inicial, no painel de indicadores e na Transparência
  diario         Diário Oficial (na Câmara, pode ser o Diário da Prefeitura, onde ela publica os atos)
  esic           e-SIC (pedidos de acesso à informação)
  ouvidoria      Ouvidoria

Com o endereço preenchido, os menus e atalhos levam direto ao sistema externo e as páginas próprias (/diario, /e-sic,
/ouvidoria) mostram de onde o serviço é prestado, com o botão para lá — o formulário próprio deixa de ser oferecido, para o
cidadão não ter dois canais. Cada órgão cadastra os seus (configuração 'sistemas_terceiros' do banco do órgão)."""
import re
from urllib.parse import urlsplit
from . import db

CHAVE = 'sistemas_terceiros'

# chave: (nome, para que serve, caminho próprio substituído ou None)
SISTEMAS = {
    'transparencia': ('Portal da Transparência em detalhes', 'Portal da transparência mantido pela empresa contratada, com receitas, despesas, '
                      'licitações, contratos e pessoal em detalhe.', None),
    'diario': ('Diário Oficial', 'Sistema onde o órgão publica os atos oficiais.', '/diario'),
    'esic': ('e-SIC', 'Sistema de pedidos de acesso à informação (LAI).', '/e-sic'),
    'ouvidoria': ('Ouvidoria', 'Sistema de reclamações, sugestões, elogios e denúncias.', '/ouvidoria'),
}
POR_CAMINHO = {c: k for k, (_, _, c) in SISTEMAS.items() if c}

BASE_LEGAL = {
    'transparencia': 'Lei Complementar nº 101/2000 (LRF), arts. 48 e 48-A; Lei nº 12.527/2011 (LAI), art. 8º',
    'diario': 'Constituição Federal, art. 37 (princípio da publicidade)',
    'esic': 'Lei nº 12.527/2011 (LAI), arts. 9º a 14',
    'ouvidoria': 'Lei nº 13.460/2017, arts. 9º a 17',
}


def url_valida(url):
    """Endereço de um sistema externo: http(s), com domínio, sem espaços, até 300 caracteres."""
    u = (url or '').strip()
    if not u or len(u) > 300 or re.search(r'\s', u):
        return False
    p = urlsplit(u)
    return p.scheme in ('http', 'https') and '.' in (p.hostname or '')


def conf(banco):
    """{chave: {'url', 'empresa', 'nome', 'base'}} só dos sistemas com endereço válido."""
    try:
        bruto = db.cfg(banco, CHAVE, {}) or {}
    except Exception:
        return {}
    out = {}
    for k, (nome, _, _) in SISTEMAS.items():
        x = bruto.get(k) or {}
        if url_valida(x.get('url')):
            out[k] = {'url': x['url'].strip(), 'empresa': (x.get('empresa') or '').strip()[:120], 'nome': nome, 'base': BASE_LEGAL[k]}
    return out


def salvar(banco, form):
    """Lê o formulário do admin (url_<k>, empresa_<k>). Devolve (dados, erros); grava só se não houver erro."""
    dados, erros = {}, []
    for k, (nome, _, _) in SISTEMAS.items():
        url = (form.get(f'url_{k}') or '').strip()
        emp = (form.get(f'empresa_{k}') or '').strip()[:120]
        if url and not url_valida(url):
            erros.append(f'{nome}: endereço inválido (use o endereço completo, começando por https://)')
            continue
        if url:
            dados[k] = {'url': url, 'empresa': emp}
    if not erros:
        db.set_cfg(banco, CHAVE, dados)
    return dados, erros


def trocar_destino(destino, externos):
    """Destino de menu/atalho próprio (/diario, /e-sic, /ouvidoria) → endereço externo, se cadastrado."""
    from .menus import normalizar
    k = POR_CAMINHO.get(normalizar(destino))
    return externos[k]['url'] if k and k in externos else None


INTRO = {
    'diario': ('o', 'Atos oficiais publicados pelo órgão: leis, decretos, portarias, editais e demais publicações.'),
    'esic': ('o', 'Peça qualquer informação pública. Você não precisa explicar o motivo do pedido.'),
    'ouvidoria': ('a', 'Reclamações, sugestões, elogios, denúncias e solicitações sobre os serviços públicos.'),
}


def pagina(request, chave):
    """Página própria (/diario, /e-sic, /ouvidoria) quando o serviço é prestado em sistema de terceiros; None se não houver."""
    from .web import templates, ctx_orgao
    ctx = ctx_orgao(request)
    x = ctx['externos'].get(chave)
    if not x or chave not in INTRO:
        return None
    artigo, intro = INTRO[chave]
    return templates.TemplateResponse(request, 'portal/externo.html', dict(ctx, x=x, chave=chave, artigo=artigo, intro=intro, legal=None))
