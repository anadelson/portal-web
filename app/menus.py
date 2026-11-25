"""Menus do cabeçalho (Fase 8): barra institucional (cor principal) e barra do portal (brasão).
Regra: cada destino aparece em uma única barra (UNIQUE no banco + validação no painel + teste automatizado).
Os itens são editáveis em /admin/menus; os padrões abaixo valem para qualquer órgão do mesmo tipo."""
import re
from urllib.parse import urlsplit
from . import db
from .catalogo import VEDADAS

BARRAS = {'institucional': 'Transparência e governo', 'portal': 'Portal'}

# (barra, rótulo, destino, módulo exigido, classe eleitoral)
PADRAO = {
    'executivo': [
        ('institucional', 'Transparência', '/transparencia', '', 'transp'),
        ('institucional', 'Painel de indicadores', '/painel', 'bi', 'transp'),
        ('institucional', 'Diário Oficial', '/diario', 'diario', 'ato'),
        ('institucional', 'Licitações', '/transparencia/licitacoes', '', 'transp'),
        ('institucional', 'Legislação', '/legislacao', '', 'ato'),
        ('institucional', 'Serviços', '/servicos', '', 'serv'),
        ('institucional', 'Ouvidoria', '/ouvidoria', 'ouv', 'serv'),
        ('institucional', 'e-SIC', '/e-sic', 'sic', 'transp'),
        ('institucional', 'Dados abertos', '/dados-abertos', '', 'transp'),
        ('portal', 'Início', '/', '', 'util'),
        ('portal', 'Notícias', '/noticias', 'noticias', 'util'),
        ('portal', 'Comunicados', '/comunicados', '', 'util'),
        ('portal', 'Conheça {cidade}', '/conheca', '', 'util'),
        ('portal', 'Fale conosco', '/fale-conosco', '', 'serv'),
        ('portal', 'Transmissões', '/transmissoes', 'audiencias', 'transp'),
    ],
    'legislativo': [
        ('institucional', 'Transparência', '/transparencia', '', 'transp'),
        ('institucional', 'Sessões', '/sessoes', 'sess', 'transp'),
        ('institucional', 'Proposições', '/proposicoes', 'prop', 'transp'),
        ('institucional', 'Legislação', '/legislacao', '', 'ato'),
        ('institucional', 'Emendas', '/emendas', 'emend', 'transp'),
        ('institucional', 'Diário Oficial', '/diario', 'diario', 'ato'),  # 25/11/2026: aparece com o módulo ou com o Diário externo (ex.: o da Prefeitura)
        ('institucional', 'Serviços', '/servicos', 'carta', 'serv'),
        ('institucional', 'Ouvidoria', '/ouvidoria', 'ouv', 'serv'),
        ('institucional', 'e-SIC', '/e-sic', 'sic', 'transp'),
        ('institucional', 'Dados abertos', '/dados-abertos', '', 'transp'),
        ('portal', 'Início', '/', '', 'util'),
        ('portal', 'Vereadores', '/vereadores', 'ver', 'util'),
        ('portal', 'Notícias', '/noticias', 'noticias', 'util'),
        ('portal', 'Comunicados', '/comunicados', '', 'util'),
        ('portal', 'Fale conosco', '/fale-conosco', '', 'serv'),
        ('portal', 'Transmissões', '/transmissoes', 'transm', 'transp'),
    ],
}

ATALHOS_PADRAO = {
    'executivo': [('Serviços online', 'Peça e acompanhe sem sair de casa', '/servicos', 'atendimento'),
                  ('Portal da Transparência', 'Receitas, despesas, contratos e obras', '/transparencia', 'grafico'),
                  ('Diário Oficial', 'Edições e busca no acervo', '/diario', 'diario'),
                  ('Ouvidoria e e-SIC', 'Reclame, sugira ou peça informação', '/ouvidoria', 'participacao')],
    'legislativo': [('Sessões e votações', 'Pauta, ata e presença', '/sessoes', 'sessoes'),
                    ('Projetos', 'Indicações, requerimentos e moções', '/proposicoes', 'proposicoes'),
                    ('Gastos da Câmara', 'Duodécimo, pessoal e relatórios fiscais', '/transparencia', 'grafico'),
                    ('Fale com a Câmara', 'e-SIC e Ouvidoria', '/fale-conosco', 'participacao')],
}

def normalizar(destino):
    """Destino comparável: caminho sem barra final + âncora; endereços externos pelo host+caminho."""
    d = (destino or '').strip()
    u = urlsplit(d)
    if u.scheme in ('http', 'https'):
        return f'{u.netloc.lower()}{u.path.rstrip("/") or "/"}{"#" + u.fragment if u.fragment else ""}'
    caminho = (u.path.rstrip('/').lower() or '/') if u.path else '/'
    return caminho + (f'?{u.query}' if u.query else '') + (f'#{u.fragment}' if u.fragment else '')

def destino_valido(destino):
    d = (destino or '').strip()
    return bool(re.match(r'^(/[^\s]*|https://[^\s]+)$', d)) and len(d) <= 300

def semear(banco, tipo, cidade=''):
    """Cria os itens padrão que ainda não existem (nunca altera o que o órgão editou)."""
    n = 0
    for i, (barra, rotulo, destino, modulo, classe) in enumerate(PADRAO.get(tipo, [])):
        r = db.exe(banco, 'INSERT INTO menus (barra, rotulo, destino, ordem, modulo, classe) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (destino) DO NOTHING RETURNING 1',
                   (barra, rotulo.replace('{cidade}', cidade or 'a cidade'), destino, (i + 1) * 10, modulo, classe))
        n += 1 if r else 0
    if not db.um(banco, 'SELECT 1 FROM atalhos LIMIT 1'):
        for i, (t, d, dest, ic) in enumerate(ATALHOS_PADRAO.get(tipo, [])):
            db.exe(banco, 'INSERT INTO atalhos (titulo, descricao, destino, icone, ordem) VALUES (%s,%s,%s,%s,%s)', (t, d, dest, ic, (i + 1) * 10))
    return n

def conflito(banco, destino, barra, ignorar_id=None):
    """Outro item (em qualquer barra) com o mesmo destino normalizado? Devolve o item ou None."""
    alvo = normalizar(destino)
    for m in db.todos(banco, 'SELECT * FROM menus'):
        if m['id'] != ignorar_id and normalizar(m['destino']) == alvo:
            return m
    return None

def barras(banco, mods, defeso, ao_vivo=False, externos=None):
    """Itens ativos por barra, respeitando módulos e o período eleitoral (classes vedadas somem).
    Diário, e-SIC e Ouvidoria com sistema de terceiros cadastrado levam direto a ele, mesmo sem o módulo próprio."""
    from .sistemas import trocar_destino
    out = {b: [] for b in BARRAS}
    for m in db.todos(banco, 'SELECT * FROM menus WHERE ativo ORDER BY barra, ordem, id'):
        ext = trocar_destino(m['destino'], externos or {})
        if m['modulo'] and not mods.get(m['modulo']) and not ext:
            continue
        if defeso and m['classe'] in VEDADAS:
            continue
        item = dict(m, vivo=bool(ao_vivo and normalizar(m['destino']) == '/transmissoes'), externo=bool(ext), nova_aba=bool(ext and ext['nova_aba']), destino=ext['url'] if ext else m['destino'])
        if item['vivo']:
            item['rotulo'] = 'Ao vivo'
        out[m['barra']].append(item)
    return out

def atalhos(banco, externos=None):
    from .sistemas import trocar_destino
    out = []
    for a in db.todos(banco, 'SELECT * FROM atalhos WHERE ativo ORDER BY ordem, id'):
        ext = trocar_destino(a['destino'], externos or {})
        out.append(dict(a, destino=ext['url'] if ext else a['destino'], externo=bool(ext), nova_aba=bool(ext and ext['nova_aba'])))
    return out
