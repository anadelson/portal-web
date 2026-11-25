"""Busca geral do portal (25/11/2026): /busca?q= procura em tudo o que o portal do órgão publica.

Fontes (só o que já é público, pelas mesmas regras das páginas de cada seção, inclusive o período eleitoral):
páginas do portal (menus e atalhos), serviços da Carta, notícias e páginas, comunicados, legislação, atos do Diário
Oficial publicados, Conheça a cidade, proposições, sessões e vereadores (Câmara), indicadores do painel e as bases da
transparência (contagem de registros, com o link para a consulta já filtrada).

O texto é comparado sem acentos e sem diferença de maiúsculas. Nenhum dado pessoal novo é exposto: só títulos, ementas e
resumos que a própria página já mostra; do Diário, só tipo, número e ementa do ato."""
import os
import re
import unicodedata
from . import db, config

MAX_POR_GRUPO = 8
MIN_CARACTERES = 2


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '').lower())
    return re.sub(r'\s+', ' ', ''.join(c for c in s if unicodedata.category(c) != 'Mn')).strip()


def _termos(q):
    return [t for t in norm(q).split(' ') if t]


def _casa(termos, *campos):
    txt = norm(' '.join(str(c or '') for c in campos))
    return all(t in txt for t in termos)


def _trecho(s, n=180):
    s = re.sub(r'<[^>]+>', ' ', str(s or ''))
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:n] + ('…' if len(s) > n else '')


def _grupo(titulo, itens, mais=''):
    return {'titulo': titulo, 'itens': itens[:MAX_POR_GRUPO], 'total': len(itens), 'mais': mais} if itens else None


def buscar(ctx, q):
    """Devolve (grupos, total). Cada grupo: titulo, itens [{t, d, href, meta}], total, mais (link para ver tudo na seção)."""
    from urllib.parse import quote
    termos = _termos(q)
    if not termos or len(''.join(termos)) < MIN_CARACTERES:
        return [], 0
    o, mods = ctx['orgao'], ctx['mods']
    b, leg, qq = o['banco'], o['tipo'] == 'legislativo', quote(q.strip())
    grupos = []

    def tenta(f):
        try:
            g = f()
        except Exception:  # uma seção sem tabela/migração não derruba a busca inteira (no banco de TESTE, o erro aparece)
            if os.environ.get('TESTE'):
                raise
            g = None
        if g:
            grupos.append(g)

    # páginas do portal: itens dos menus e atalhos (já respeitam módulos, defeso e sistemas de terceiros)
    def paginas():
        vistos, out = set(), []
        from . import menus as MN
        fixas = [{'rotulo': 'Transparência', 'destino': '/transparencia'}, {'rotulo': 'Dados abertos', 'destino': '/dados-abertos'},
                 {'rotulo': 'Fale conosco', 'destino': '/fale-conosco'}, {'rotulo': 'Acessibilidade', 'destino': '/acessibilidade'},
                 {'rotulo': 'Privacidade (LGPD)', 'destino': '/privacidade'}]
        cands = [m for bar in ctx['barras'].values() for m in bar] + [{'rotulo': a['titulo'], 'destino': a['destino'], 'descricao': a.get('descricao', ''), 'externo': a.get('externo'), 'nova_aba': a.get('nova_aba')}
                                                                     for a in MN.atalhos(b, ctx.get('externos'))] + fixas
        for m in cands:
            if m['destino'] in vistos or not _casa(termos, m['rotulo'], m.get('descricao', '')):
                continue
            vistos.add(m['destino'])
            out.append({'t': m['rotulo'], 'd': m.get('descricao', '') or ('Sistema externo' if m.get('externo') else ''), 'href': m['destino'],
                        'externo': bool(m.get('externo')), 'nova_aba': bool(m.get('nova_aba'))})
        return _grupo('Páginas do portal', out)
    tenta(paginas)

    if mods.get('carta'):
        def servicos():
            from . import carta as CT
            its = [x for x in CT.publicados(b) if _casa(termos, x.get('nome'), x.get('descricao'), x.get('categoria'), x.get('setor'),
                                                         ' '.join(x['sinonimos']) if isinstance(x.get('sinonimos'), list) else x.get('sinonimos'))]
            return _grupo('Serviços', [{'t': x['nome'], 'd': _trecho(x.get('descricao')), 'href': f"/servicos/{x['slug']}", 'exemplo': x.get('exemplo')} for x in its], f'/servicos?q={qq}')
        tenta(servicos)

    def conteudos():
        from .portal import conteudos_publicos
        its = [c for c in conteudos_publicos(b, limite=2000) if _casa(termos, c.get('titulo'), c.get('resumo'), c.get('texto'), c.get('secao'))]
        return _grupo('Notícias e páginas', [{'t': c['titulo'], 'd': _trecho(c.get('resumo') or c.get('texto')), 'href': f"/conteudo/{c['id']}", 'exemplo': c.get('exemplo'),
                                             'meta': (c.get('tipo') or '') + (' · ' + c['publicar_em'].strftime('%d/%m/%Y') if c.get('publicar_em') else '')} for c in its],
                      '/noticias' if ctx['mods'].get('noticias') else '')
    tenta(conteudos)

    def comunicados():
        from . import fase8 as F8
        its = [c for c in F8.comunicados(b, limite=500, so_validos=False) if _casa(termos, c.get('titulo'), c.get('texto'), c.get('tipo'))]
        return _grupo('Comunicados', [{'t': c['titulo'], 'd': _trecho(c.get('texto')), 'href': f"/comunicados/{c['id']}", 'meta': c.get('tipo', ''), 'exemplo': c.get('exemplo')} for c in its], '/comunicados')
    tenta(comunicados)

    def legislacao():
        from . import fase8 as F8
        its = [x for x in F8.lista_legislacao(b) if _casa(termos, x.get('tipo'), x.get('numero'), x.get('ano'), x.get('ementa'), x.get('texto'))]
        return _grupo('Legislação', [{'t': f"{x['tipo']} nº {x['numero']}" + (f"/{x['ano']}" if x.get('ano') else ''), 'd': _trecho(x.get('ementa')), 'href': f"/legislacao/{x['id']}",
                                      'meta': x.get('situacao', '')} for x in its], f'/legislacao?q={qq}')
    tenta(legislacao)

    if mods.get('diario') and not (ctx.get('externos') or {}).get('diario'):
        def diario():
            from .diario import mostrar_teste
            rs = db.todos(b, """SELECT a.tipo, a.numero, a.ementa, e.id eid, e.numero en, e.letra, e.data, e.sha256 FROM diario_atos a JOIN diario_edicoes e ON e.id=a.edicao_id
                                WHERE a.situacao='publicado' AND e.situacao='publicada' AND (NOT e.modo_teste OR %s) ORDER BY e.data DESC, a.id DESC LIMIT 3000""", (mostrar_teste(b),))
            its = [x for x in rs if _casa(termos, x['tipo'], x['numero'], x['ementa'])]
            return _grupo('Diário Oficial', [{'t': f"{x['tipo']}{' nº ' + x['numero'] if x['numero'] else ''}", 'd': _trecho(x['ementa']),
                                              'href': f"/diario/{x['eid']}.pdf" + (f"?v={x['sha256'][:12]}" if x['sha256'] else ''),
                                              'meta': f"Edição nº {x['en']}{x['letra']} de {x['data'].strftime('%d/%m/%Y')}"} for x in its], '/diario')
        tenta(diario)

    def conheca():
        from . import fase8 as F8
        its = [x for x in F8.perfis(b) if _casa(termos, x.get('titulo'), x.get('descricao'), x.get('categoria'))]
        return _grupo(f"Conheça {ctx['ident'].get('nome_curto') or 'a cidade'}", [{'t': x['titulo'], 'd': _trecho(x.get('descricao')), 'href': f"/conheca/{x['slug']}"} for x in its], '/conheca')
    tenta(conheca)

    if leg:
        if mods.get('prop'):
            def proposicoes():
                rs = db.todos(b, 'SELECT id, tipo, numero, ano, ementa, autor, situacao, exemplo FROM proposicoes ORDER BY ano DESC, numero DESC LIMIT 5000')
                its = [x for x in rs if _casa(termos, x['tipo'], f"{x['numero']}/{x['ano']}", x['ementa'], x['autor'])]
                return _grupo('Proposições', [{'t': f"{x['tipo']} nº {x['numero']}/{x['ano']}", 'd': _trecho(x['ementa']), 'href': f"/proposicoes/{x['id']}",
                                                'meta': ' · '.join(v for v in (x.get('autor'), x.get('situacao')) if v), 'exemplo': x.get('exemplo')} for x in its], f'/proposicoes?q={qq}')
            tenta(proposicoes)
        if mods.get('sess'):
            def sessoes():
                rs = db.todos(b, 'SELECT id, nome, data FROM sessoes ORDER BY data DESC LIMIT 3000')
                its = [x for x in rs if _casa(termos, x['nome'], x['data'].strftime('%d/%m/%Y') if x['data'] else '')]
                return _grupo('Sessões', [{'t': x['nome'], 'd': '', 'href': f"/sessoes/{x['id']}", 'meta': x['data'].strftime('%d/%m/%Y') if x['data'] else ''} for x in its], '/sessoes')
            tenta(sessoes)
        if mods.get('ver'):
            def vereadores():
                rs = db.todos(b, 'SELECT DISTINCT ON (nome) id, nome, apelido, partido, legislatura FROM vereadores ORDER BY nome, legislatura DESC')
                its = [x for x in rs if _casa(termos, x['nome'], x['apelido'], x['partido'])]
                return _grupo('Vereadores', [{'t': x['apelido'] or x['nome'], 'd': x['nome'] if x['apelido'] else '', 'href': f"/vereadores/{x['id']}", 'meta': x['partido']} for x in its], '/vereadores')
            tenta(vereadores)

    if mods.get('bi'):
        def indicadores():
            from . import painel as P
            its = [i for i in P.catalogo(b) if i.get('visivel', True) and _casa(termos, i.get('nome'), i.get('descricao'))
                   and db.um(b, 'SELECT 1 FROM indicador_valores WHERE indicador_id=%s LIMIT 1', (i['id'],))]
            return _grupo('Painel de indicadores', [{'t': i['nome'], 'd': _trecho(i.get('descricao')), 'href': f"/painel/{i['chave']}"} for i in its], '/painel')
        tenta(indicadores)

    def transparencia():
        from . import transparencia as TR
        out = []
        for nome, base in TR.bases_do(o).items():
            if not base.get('texto'):
                continue
            try:
                where, p, _ = TR.filtros(base, {'q': q.strip()})
                n = db.um(b, f"SELECT count(*) n FROM {base['tabela']}{where}", p)['n']
            except Exception:
                continue
            if n:
                out.append({'t': base['titulo'], 'd': f"{n} registro(s) com “{q.strip()[:60]}”", 'href': f'/transparencia/{nome}?q={qq}', 'meta': 'Transparência'})
        return _grupo('Transparência (registros)', out, '/transparencia')
    tenta(transparencia)

    return grupos, sum(g['total'] for g in grupos)
