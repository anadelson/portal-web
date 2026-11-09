"""Fase 8: comunicados, notícias da página inicial, perfis do "Conheça", legislação montada do Diário, links úteis.
Nada inventado: o que não existe fica vazio e o bloco se adapta (ou não aparece)."""
import re, unicodedata
from datetime import date, datetime
from . import config, db, eleicao
from .catalogo import VEDADAS

# ---------- comunicados ----------
TIPOS_COMUNICADO = ['Comunicado', 'Aviso', 'Convocação', 'Convite', 'Nota oficial', 'Edital de chamamento']
PROIBIDOS = ('notícia', 'noticia', 'notícias', 'noticias')

def tipos_comunicado(banco):
    t = db.cfg(banco, 'comunicados_tipos')
    return [x for x in (t or TIPOS_COMUNICADO) if x.strip().lower() not in PROIBIDOS]

def tipo_comunicado_valido(banco, tipo):
    return tipo in tipos_comunicado(banco) and tipo.strip().lower() not in PROIBIDOS

def comunicados(banco, limite=5, tipo='', ano=None, so_validos=True):
    agora = config.agora()
    sql = "SELECT * FROM comunicados WHERE situacao='publicado' AND (publicado_em IS NULL OR publicado_em <= %s)"
    p = [agora]
    if so_validos:
        sql += ' AND (valido_ate IS NULL OR valido_ate >= %s)'; p.append(agora.date())
    if tipo:
        sql += ' AND tipo=%s'; p.append(tipo)
    if ano:
        sql += ' AND extract(year FROM coalesce(publicado_em, criado_em))=%s'; p.append(int(ano))
    sql += ' ORDER BY coalesce(publicado_em, criado_em) DESC, id DESC LIMIT %s'; p.append(limite)
    itens = db.todos(banco, sql, p)
    if eleicao.em_defeso(banco):
        itens = [c for c in itens if c['classe'] not in VEDADAS]
    return itens

# ---------- notícias (bloco da página inicial: destaque, 3 secundárias, lista de 5) ----------
def noticias_home(banco):
    hoje = config.hoje()
    if eleicao.em_defeso(banco):  # notícias são publicidade institucional: somem no defeso, sem deixar espaço
        return None
    itens = db.todos(banco, """SELECT * FROM conteudos WHERE secao='Notícias' AND situacao='publicado' AND (publicar_em IS NULL OR publicar_em <= %s)
                               AND (tirar_em IS NULL OR tirar_em > %s) AND (publicado_em IS NULL OR publicado_em <= %s)
                               ORDER BY coalesce(publicado_em, publicar_em::timestamptz, criado_em) DESC, id DESC LIMIT 20""", (hoje, hoje, config.agora()))
    if not itens:
        return None
    dest = next((c for c in itens if c['destaque']), itens[0])
    resto = [c for c in itens if c['id'] != dest['id']]
    return {'destaque': dest, 'secundarias': resto[:3], 'lista': resto[3:8]}

def quando(c):
    """'08/11/2026, 09h44' (data e hora da publicação)."""
    t = c.get('publicado_em')
    if t:
        t = t.astimezone() if t.tzinfo else t
        return t.strftime('%d/%m/%Y, %Hh%M')
    d = c.get('publicar_em') or c.get('criado_em')
    if isinstance(d, datetime):
        d = (d.astimezone() if d.tzinfo else d)
        return d.strftime('%d/%m/%Y, %Hh%M')
    return d.strftime('%d/%m/%Y') if d else ''

# ---------- serviços mais acessados (contagem mensal, sem dado pessoal) ----------
def contar_acesso(banco, conteudo_id):
    db.exe(banco, """INSERT INTO conteudo_acessos (conteudo_id, mes, n) VALUES (%s,%s,1)
                     ON CONFLICT (conteudo_id, mes) DO UPDATE SET n=conteudo_acessos.n+1""", (conteudo_id, config.hoje().strftime('%Y-%m')))

def servicos_mais_acessados(banco, limite=6):
    from .portal import conteudos_publicos
    publicados = conteudos_publicos(banco, 'Serviços', 200)
    if not publicados:
        return []
    n = {r['conteudo_id']: r['n'] for r in db.todos(banco, 'SELECT conteudo_id, n FROM conteudo_acessos WHERE mes=%s', (config.hoje().strftime('%Y-%m'),))}
    return sorted(publicados, key=lambda c: (-n.get(c['id'], 0), c['titulo']))[:limite]

# ---------- Conheça: perfis ----------
CATEGORIAS = ['Lugares', 'Patrimônio', 'Eventos', 'Festas', 'Economia']

def slug(t):
    s = unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:80] or 'perfil'

def foto_publicavel(f):
    """LGPD/imagem: foto com pessoas identificáveis só publica com autorização de uso registrada."""
    return not f['tem_pessoas'] or f['autorizacao_imagem']

def perfis(banco, categoria='', q='', destaque=False):
    sql, p = 'SELECT * FROM perfis WHERE publicado', []
    if categoria:
        sql += ' AND categoria=%s'; p.append(categoria)
    if q:
        sql += ' AND (titulo ILIKE %s OR descricao ILIKE %s)'; p += [f'%{q}%', f'%{q}%']
    if destaque:
        sql += ' AND destaque'
    itens = db.todos(banco, sql + ' ORDER BY ordem, id', p)
    if eleicao.em_defeso(banco):
        itens = [x for x in itens if x['classe'] not in VEDADAS]
    for x in itens:
        x['capa'] = capa(banco, x['id'])
    return itens

def fotos(banco, perfil_id):
    return [f for f in db.todos(banco, 'SELECT * FROM perfil_fotos WHERE perfil_id=%s ORDER BY capa DESC, ordem, id', (perfil_id,)) if foto_publicavel(f)]

def capa(banco, perfil_id):
    f = fotos(banco, perfil_id)
    return f[0] if f else None

def migrar_conheca(banco, ident):
    """As fotos atuais do bloco "Conheça" viram os primeiros perfis (títulos e créditos atuais; descrição vazia)."""
    if db.um(banco, 'SELECT 1 FROM perfis LIMIT 1'):
        return 0
    n = 0
    for i, f in enumerate(((ident or {}).get('conheca') or {}).get('fotos') or []):
        titulo = (f.get('legenda') or '').strip()
        if not titulo or not f.get('url') or len((f.get('alt') or '').strip()) < 5:
            continue
        cat = 'Patrimônio' if re.search(r'igreja|matriz|capela', titulo, re.I) else 'Economia' if re.search(r'agroind|usina|indústria|cana', titulo, re.I) else 'Lugares'
        pid = db.exe(banco, 'INSERT INTO perfis (slug, titulo, categoria, ordem, publicado, destaque) VALUES (%s,%s,%s,%s,TRUE,TRUE) ON CONFLICT (slug) DO NOTHING RETURNING id',
                     (slug(titulo), titulo, cat, (i + 1) * 10))
        if pid:
            db.exe(banco, 'INSERT INTO perfil_fotos (perfil_id, url, alt, legenda, credito, capa, ordem) VALUES (%s,%s,%s,%s,%s,TRUE,10)',
                   (pid['id'], f['url'], f['alt'], titulo, f.get('credito', '')))
            n += 1
    return n

# ---------- legislação (montada a partir dos atos publicados no Diário) ----------
TIPOS_LEGISLACAO = ['Lei', 'Lei Complementar', 'Decreto', 'Decreto Legislativo', 'Portaria', 'Resolução']
RELACOES = {'altera': ('altera', 'é alterado por'), 'revoga': ('revoga', 'é revogado por'), 'regulamenta': ('regulamenta', 'é regulamentado por')}

def _num_ano(numero, data_pub):
    """'1.234/2026' → ('1234', 2026); sem ano no número, usa o ano da publicação."""
    m = re.match(r'^\s*([\d.]+)\s*(?:/\s*(\d{4}))?', numero or '')
    if not m:
        return (numero or '').strip(), (data_pub.year if data_pub else None)
    return m.group(1).replace('.', ''), int(m.group(2)) if m.group(2) else (data_pub.year if data_pub else None)

def localizar(banco, texto):
    """'Lei 12/2020' ou 'Lei Complementar 3/2019' → id na legislação."""
    m = re.match(r'^\s*(.+?)\s+(?:n[º°o.]*\s*)?([\d.]+)\s*/\s*(\d{4})\s*$', texto or '', re.I)
    if not m:
        return None
    r = db.um(banco, 'SELECT id FROM legislacao WHERE lower(tipo)=lower(%s) AND numero=%s AND ano=%s', (m.group(1).strip(), m.group(2).replace('.', ''), int(m.group(3))))
    return r['id'] if r else None

def sincronizar(banco):
    """Ato de tipo legislativo publicado (edição publicada, inclusive retificações) entra sozinho na lista; relações aplicadas."""
    n = 0
    atos = db.todos(banco, """SELECT a.*, e.data edata, e.numero enum, e.letra eletra, e.id eid, e.modo_teste FROM diario_atos a JOIN diario_edicoes e ON e.id=a.edicao_id
                              WHERE e.situacao='publicada' AND a.tipo = ANY(%s) ORDER BY e.data, a.id""", (TIPOS_LEGISLACAO,))
    for a in atos:
        if a['modo_teste']:
            continue  # edição de teste não tem valor oficial
        num, ano = _num_ano(a['numero'], a['edata'])
        r = db.exe(banco, """INSERT INTO legislacao (origem, diario_ato_id, tipo, numero, ano, data, ementa, texto, pdf_url, edicao, pagina)
                             VALUES ('diario',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id""",
                   (a['id'], a['tipo'], num, ano, a['edata'], a['ementa'], a['texto'], f"/diario/{a['eid']}.pdf", f"{a['enum']}{a['eletra']}", a['pagina']))
        n += 1 if r else 0
    for a in atos:
        if a['modo_teste']:
            continue
        orig = db.um(banco, 'SELECT id FROM legislacao WHERE diario_ato_id=%s', (a['id'],))
        for rel in (a['relacoes'] or []):
            alvo = localizar(banco, rel.get('alvo', ''))
            if orig and alvo and rel.get('tipo') in RELACOES and alvo != orig['id']:
                db.exe(banco, 'INSERT INTO legislacao_relacoes (origem_id, destino_id, tipo) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (orig['id'], alvo, rel['tipo']))
    return n

def situacao(banco, lid):
    rs = {r['tipo'] for r in db.todos(banco, 'SELECT tipo FROM legislacao_relacoes WHERE destino_id=%s', (lid,))}
    return 'revogada' if 'revoga' in rs else 'alterada' if 'altera' in rs else 'vigente'

def lista_legislacao(banco, tipo='', sit='', ano='', q=''):
    sql, p = 'SELECT * FROM legislacao WHERE TRUE', []
    if tipo:
        sql += ' AND tipo=%s'; p.append(tipo)
    if ano and str(ano).isdigit():
        sql += ' AND ano=%s'; p.append(int(ano))
    if q:
        sql += ' AND (ementa ILIKE %s OR numero ILIKE %s OR texto ILIKE %s)'; p += [f'%{q}%', f'%{q.replace(".", "")}%', f'%{q}%']
    itens = db.todos(banco, sql + ' ORDER BY data DESC NULLS LAST, ano DESC NULLS LAST, id DESC', p)
    for x in itens:
        x['situacao'] = situacao(banco, x['id'])
    if sit:
        itens = [x for x in itens if x['situacao'] == sit]
    return itens

def relacoes_do(banco, lid):
    # a relação vem como "rel" (l.* também tem a coluna "tipo", do ato)
    ida = db.todos(banco, 'SELECT r.tipo rel, l.* FROM legislacao_relacoes r JOIN legislacao l ON l.id=r.destino_id WHERE r.origem_id=%s', (lid,))
    volta = db.todos(banco, 'SELECT r.tipo rel, l.* FROM legislacao_relacoes r JOIN legislacao l ON l.id=r.origem_id WHERE r.destino_id=%s', (lid,))
    return [{'rot': RELACOES[r['rel']][0], 'ato': r} for r in ida] + [{'rot': RELACOES[r['rel']][1], 'ato': r} for r in volta]

def rotulo(x):
    return f"{x['tipo']} nº {x['numero']}/{x['ano']}" if x['numero'] else x['tipo']

# ---------- links úteis ----------
def links_uteis(banco):
    return [l for l in (db.cfg(banco, 'links_uteis', []) or []) if l.get('titulo') and l.get('url')]
