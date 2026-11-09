"""Fase 10 — Carta de Serviços ao Usuário (Lei 13.460/2017, arts. 7º, 23 e 24).

Regras (no servidor e nos testes):
- Ficha só vai para validação com todos os campos obrigatórios do art. 7º preenchidos.
- Só o responsável pela secretaria (ou servidor designado por ato vigente) autoriza; devolver exige comentário.
- Publicar exige autorização VIGENTE da versão ATUAL: o resumo (hash) do conteúdo autorizado tem de bater com o atual.
  Mudança de conteúdo depois de autorizada volta para validação; o DTIC só ajusta categoria, sinônimos e ordem.
- Ficha publicada que passou da data de revisão aparece "em revisão" e gera alerta (continua no ar).
Nada inventado: o portal só lista fichas publicadas; exemplos são marcados."""
import csv, hashlib, io, json, re, unicodedata
from datetime import date, timedelta
from psycopg.types.json import Jsonb
from . import config, db

PUBLICOS = {'cidadao': 'Cidadão', 'empresa': 'Empresa', 'servidor': 'Servidor público', 'orgaos': 'Outros órgãos'}
FORMAS = {'online': 'Online', 'presencial': 'Presencial', 'telefone': 'Telefone', 'whatsapp': 'WhatsApp'}
CATEGORIAS_PADRAO = ['Tributos e taxas', 'Educação', 'Saúde', 'Assistência social', 'Obras, cidade e meio ambiente', 'Empresas e alvarás',
                     'Documentos e certidões', 'Cultura, esporte e lazer', 'Atendimento e ouvidoria', 'Processo legislativo']
SITUACOES = {'rascunho': 'Rascunho', 'em_validacao': 'Em validação', 'devolvido': 'Devolvido', 'autorizado': 'Autorizado', 'publicado': 'Publicado', 'arquivado': 'Arquivado'}

# campo: (rótulo, obrigatório, seção da ficha pública)
CAMPOS = {
    'nome': ('Nome do serviço', True, ''), 'descricao': ('Descrição em linguagem simples (o que é)', True, 'O que é'),
    'secretaria_id': ('Secretaria responsável', True, ''), 'setor': ('Setor', False, ''), 'categoria': ('Categoria', True, ''),
    'publicos': ('Público', True, ''), 'sinonimos': ('Palavras-chave e sinônimos para a busca', False, ''),
    'requisitos': ('Quem pode pedir e requisitos', True, 'Quem pode pedir'), 'documentos': ('Documentos e informações necessários', True, 'Documentos e informações'),
    'etapas': ('Principais etapas (uma por linha)', True, 'Etapas'), 'prazo': ('Prazo máximo de prestação', True, 'Prazo'),
    'formas': ('Forma de prestação', True, ''), 'locais': ('Locais, horários e formas de acesso', True, 'Onde e quando'),
    'custo': ('Custo (escreva "Gratuito" se não houver)', True, 'Custo'), 'custo_base_legal': ('Base legal da cobrança', False, ''),
    'prioridades': ('Prioridades de atendimento', True, 'Prioridades'), 'tempo_espera': ('Previsão de tempo de espera', True, 'Tempo de espera'),
    'comunicacao': ('Como o órgão se comunica com o usuário', True, 'Comunicação com você'), 'manifestacoes': ('Como fazer e acompanhar manifestações', True, 'Reclamações, sugestões e elogios'),
    'acompanhamento': ('Como consultar o andamento (protocolo)', True, 'Como acompanhar'), 'link_online': ('Link “Solicitar online” (https://)', False, ''),
    'legislacao': ('Legislação relacionada', False, 'Legislação'),
}
CONTEUDO = [k for k in CAMPOS if k not in ('categoria', 'sinonimos')]  # o que o validador autoriza (o DTIC só mexe em categoria, sinônimos e ordem)

def faltando(s):
    """Campos obrigatórios vazios (art. 7º). Custo diferente de gratuito exige a base legal da cobrança."""
    f = []
    for k, (rot, obr, _) in CAMPOS.items():
        v = s.get(k)
        if obr and (not v or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)):
            f.append(rot)
    custo = (s.get('custo') or '').strip().lower()
    if custo and not custo.startswith('gratuit') and not (s.get('custo_base_legal') or '').strip():
        f.append(CAMPOS['custo_base_legal'][0])
    return f

DIFICEIS = ['outrossim', 'mediante', 'destarte', 'consoante', 'supracitado', 'retromencionado', 'ensejar', 'protocolizar', 'em epígrafe', 'doravante']
SIGLAS_COMUNS = {'CPF', 'RG', 'CEP', 'CNPJ', 'IPTU', 'PDF', 'SUS', 'CNH', 'ISS', 'WHATSAPP'}

def avisos_linguagem(texto):
    """Sugestões (não bloqueiam): frases longas, siglas sem explicação, termos difíceis."""
    av = []
    for fr in re.split(r'(?<=[.!?])\s+', texto or ''):
        n = len(re.findall(r'\w+', fr))
        if n > 30:
            av.append(f'frase com {n} palavras (sugerido até 30): “{fr[:60]}…”')
    for sg in sorted(set(re.findall(r'\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}\b', texto or ''))):
        if sg not in SIGLAS_COMUNS and not re.search(rf'{sg}\s*\(|\(\s*{sg}\s*\)', texto):
            av.append(f'sigla sem explicação: “{sg}” (escreva por extenso na primeira vez)')
    baixo = (texto or '').lower()
    for t in DIFICEIS:
        if t in baixo:
            av.append(f'termo difícil: “{t}”')
    return av

def resumo_conteudo(s):
    """Hash do conteúdo que o validador autoriza."""
    d = {k: (sorted(s.get(k) or []) if isinstance(s.get(k), list) else (str(s.get(k)) if s.get(k) is not None else '')) for k in CONTEUDO}
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def slug(t):
    s = unicodedata.normalize('NFKD', str(t)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')[:80] or 'servico'

def sem_acento(t):
    return unicodedata.normalize('NFKD', str(t or '')).encode('ascii', 'ignore').decode().lower()

# ---------- permissões por secretaria ----------
def designacao_vigente(banco, u, secretaria_id):
    """Ato de designação vigente do usuário nesta secretaria (ou None)."""
    return db.um(banco, 'SELECT * FROM designacoes_carta WHERE usuario_id=%s AND secretaria_id=%s AND ato_data <= %s AND (ate IS NULL OR ate >= %s) ORDER BY id DESC LIMIT 1',
                 (u['id'], secretaria_id, config.hoje(), config.hoje()))

def pode_validar(banco, u, s):
    """Responsável cadastrado da secretaria ou designado com ato vigente. Devolve (ok, ato_texto)."""
    sec = db.um(banco, 'SELECT * FROM secretarias WHERE id=%s', (s['secretaria_id'],)) if s.get('secretaria_id') else None
    if not sec:
        return False, ''
    if sec['responsavel_id'] == u['id']:
        return True, 'responsável pela secretaria'
    d = designacao_vigente(banco, u, sec['id'])
    if d:
        return True, f"designado: {d['ato_tipo']} nº {d['ato_numero']} de {d['ato_data'].strftime('%d/%m/%Y')}"
    return False, ''

def pode_redigir(banco, u, s):
    if u['perfil'] in ('admin', 'publicador', 'editor'):
        return True
    return bool(u.get('secretaria_id')) and (not s or s.get('secretaria_id') in (None, u.get('secretaria_id')))

# ---------- versões e transições ----------
def versao(banco, sid, situacao, quem, comentario=''):
    s = db.um(banco, 'SELECT * FROM servicos WHERE id=%s', (sid,))
    dados = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in s.items()}
    db.exe(banco, 'INSERT INTO servico_versoes (servico_id, situacao, quem, comentario, dados) VALUES (%s,%s,%s,%s,%s)', (sid, situacao, quem, comentario[:1000], Jsonb(dados)))

def prazo_revisao(banco):
    try:
        m = int((db.cfg(banco, 'carta', {}) or {}).get('revisao_meses', 12))
    except (TypeError, ValueError):
        m = 12
    return max(1, min(m, 36))

def publicar(banco, s, quem):
    """Única porta de publicação. Levanta ValueError se não houver autorização vigente da versão atual."""
    if s['situacao'] != 'autorizado' or not s['autorizado_por'] or not s['autorizado_hash']:
        raise ValueError('Só fichas AUTORIZADAS pelo responsável da secretaria podem ser publicadas.')
    if resumo_conteudo(s) != s['autorizado_hash']:
        raise ValueError('O conteúdo mudou depois da autorização: a ficha precisa ser validada de novo.')
    if faltando(s):
        raise ValueError('A ficha tem campo obrigatório vazio.')
    rev = config.hoje() + timedelta(days=30 * prazo_revisao(banco))
    snap = {k: s.get(k) for k in list(CAMPOS) + ['slug', 'exemplo', 'ordem']}
    snap['atualizado_em'] = config.hoje().isoformat()
    db.exe(banco, "UPDATE servicos SET situacao='publicado', publicado_por=%s, publicado_em=now(), revisar_em=%s, publicado_dados=%s WHERE id=%s", (quem, rev, Jsonb(snap), s['id']))

# ---------- leitura pública ----------
def _no_ar(banco):
    """Fichas no ar: a cópia congelada da última publicação (nunca o rascunho em edição)."""
    out = []
    for r in db.todos(banco, """SELECT s.id, s.slug, s.publicado_dados d, s.publicado_em, s.revisar_em, s.situacao, sec.nome secretaria, sec.sigla
                                FROM servicos s LEFT JOIN secretarias sec ON sec.id=(s.publicado_dados->>'secretaria_id')::int
                                WHERE s.publicado_dados IS NOT NULL AND s.situacao <> 'arquivado'"""):
        x = dict(r['d'], id=r['id'], slug=r['slug'], secretaria=r['secretaria'] or '', sigla=r['sigla'] or '', publicado_em=r['publicado_em'], revisar_em=r['revisar_em'])
        x['atualizado_em'] = date.fromisoformat(x['atualizado_em']) if isinstance(x.get('atualizado_em'), str) else x.get('atualizado_em')
        out.append(x)
    return sorted(out, key=lambda x: sem_acento(x['nome']))

def publicados(banco, q='', categoria='', publico='', secretaria='', letra=''):
    itens = _no_ar(banco)
    if categoria:
        itens = [x for x in itens if x['categoria'] == categoria]
    if publico:
        itens = [x for x in itens if publico in (x.get('publicos') or [])]
    if secretaria and str(secretaria).isdigit():
        itens = [x for x in itens if x.get('secretaria_id') == int(secretaria)]
    if letra:
        itens = [x for x in itens if sem_acento(x['nome'])[:1] == letra.lower()]
    if q:
        termos = [t for t in re.split(r'\W+', sem_acento(q)) if len(t) > 1]
        def nota(x):
            alvo = sem_acento(' '.join([x['nome'], x.get('descricao', ''), x.get('sinonimos', ''), x.get('categoria', ''), x.get('secretaria', '')]))
            forte = sem_acento(x['nome'] + ' ' + x.get('sinonimos', ''))
            return sum(3 if t in forte else 1 for t in termos if t in alvo)
        itens = sorted([x for x in itens if nota(x)], key=lambda x: -nota(x))
    hoje = config.hoje()
    for x in itens:
        x['em_revisao'] = bool(x['revisar_em'] and x['revisar_em'] < hoje)
    return itens

def no_ar(banco, slug_):
    return next((x for x in publicados(banco) if x['slug'] == slug_), None)

def mais_acessados(banco, limite=6):
    n = {r['servico_id']: r['n'] for r in db.todos(banco, 'SELECT servico_id, n FROM servico_acessos WHERE mes=%s', (config.hoje().strftime('%Y-%m'),))}
    return sorted(publicados(banco), key=lambda x: (-n.get(x['id'], 0), sem_acento(x['nome'])))[:limite]

def contar_acesso(banco, sid):
    db.exe(banco, 'INSERT INTO servico_acessos (servico_id, mes, n) VALUES (%s,%s,1) ON CONFLICT (servico_id, mes) DO UPDATE SET n=servico_acessos.n+1',
           (sid, config.hoje().strftime('%Y-%m')))

def vencidas(banco, secretaria_id=None):
    return db.todos(banco, """SELECT s.*, sec.nome secretaria FROM servicos s LEFT JOIN secretarias sec ON sec.id=s.secretaria_id
                               WHERE s.publicado_dados IS NOT NULL AND s.situacao <> 'arquivado' AND s.revisar_em < %s""" + (' AND s.secretaria_id=%s' if secretaria_id else '') + ' ORDER BY s.revisar_em',
                    (config.hoje(), secretaria_id) if secretaria_id else (config.hoje(),))

def avaliacao_resumo(banco, sid):
    return db.um(banco, """SELECT count(*) n, round(avg(nota)::numeric, 1) media, count(*) FILTER (WHERE conseguiu) sim, count(*) FILTER (WHERE conseguiu IS FALSE) nao
                           FROM servico_avaliacoes WHERE servico_id=%s""", (sid,))

# ---------- exportação ----------
COLUNAS_EXPORT = ['nome', 'descricao', 'secretaria', 'setor', 'categoria', 'publicos', 'requisitos', 'documentos', 'etapas', 'prazo', 'formas', 'locais', 'custo',
                  'custo_base_legal', 'prioridades', 'tempo_espera', 'comunicacao', 'manifestacoes', 'acompanhamento', 'link_online', 'legislacao', 'atualizado_em', 'revisar_em']

def registros(banco):
    out = []
    for x in publicados(banco):
        r = {k: x.get(k) for k in COLUNAS_EXPORT}
        r['publicos'] = ', '.join(PUBLICOS.get(p, p) for p in (x['publicos'] or []))
        r['formas'] = ', '.join(FORMAS.get(p, p) for p in (x['formas'] or []))
        r['atualizado_em'] = x['atualizado_em'].isoformat() if x.get('atualizado_em') else None
        r['revisar_em'] = x['revisar_em'].isoformat() if x['revisar_em'] else None
        r['endereco'] = f"/servicos/{x['slug']}"
        out.append(r)
    return out

def csv_texto(banco):
    buf = io.StringIO(); w = csv.DictWriter(buf, fieldnames=COLUNAS_EXPORT + ['endereco'], extrasaction='ignore')
    w.writeheader(); [w.writerow(r) for r in registros(banco)]
    return '﻿' + buf.getvalue()

def pdf(banco, orgao_nome, base_legal):
    """Carta inteira em PDF (reportlab): capa com data, sumário por categoria e uma ficha por serviço."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from xml.sax.saxutils import escape as esc
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f'Carta de Serviços — {orgao_nome}', author=orgao_nome, lang='pt-BR')
    st = getSampleStyleSheet()
    itens = publicados(banco)
    el = [Paragraph(esc(f'Carta de Serviços ao Usuário — {orgao_nome}'), st['Title']),
          Paragraph(esc(f"Gerada em {config.hoje().strftime('%d/%m/%Y')} · {len(itens)} serviço(s) publicado(s)"), st['Normal']),
          Paragraph(esc('Base legal: ' + base_legal), st['Normal']), Spacer(1, 8 * mm), Paragraph('Sumário', st['Heading2'])]
    for cat in sorted({x['categoria'] for x in itens}):
        el.append(Paragraph(f'<b>{esc(cat)}</b>: ' + esc(', '.join(x['nome'] for x in itens if x['categoria'] == cat)), st['Normal']))
    for x in itens:
        el += [PageBreak(), Paragraph(esc(x['nome']), st['Heading1']),
               Paragraph(esc(f"{x['categoria']} · {x.get('secretaria') or ''} · atualizado em {x['atualizado_em'].strftime('%d/%m/%Y') if x.get('atualizado_em') else ''}"), st['Normal'])]
        for k, (rot, _, secao) in CAMPOS.items():
            if not secao or not x.get(k):
                continue
            el.append(Paragraph(esc(secao), st['Heading3']))
            v = x[k]
            for linha in (v if isinstance(v, list) else str(v).splitlines()):
                if str(linha).strip():
                    el.append(Paragraph(esc(str(linha)), st['Normal']))
        if x.get('link_online'):
            el.append(Paragraph(esc('Solicitar online: ' + x['link_online']), st['Normal']))
    doc.build(el)
    return buf.getvalue()

# ---------- importação (inventário) ----------
COLUNAS_IMPORT = ['secretaria', 'nome', 'descricao', 'categoria', 'publicos', 'requisitos', 'documentos', 'etapas', 'prazo', 'formas', 'locais', 'custo',
                  'custo_base_legal', 'prioridades', 'tempo_espera', 'comunicacao', 'manifestacoes', 'acompanhamento', 'link_online', 'legislacao', 'sinonimos']

def importar(banco, dados: bytes, quem, simular=True, secretaria_unica=None):
    """Cada linha vira RASCUNHO da secretaria indicada (pelo nome ou sigla cadastrados). Tudo ou nada; simulação não grava."""
    try:
        linhas = list(csv.DictReader(io.StringIO(dados.decode('utf-8-sig')), delimiter=';'))
    except UnicodeDecodeError:
        return {'linhas': 0, 'validas': 0, 'gravadas': 0, 'erros': [{'linha': 0, 'erro': 'arquivo não está em UTF-8'}], 'simulacao': simular}
    if linhas and set(COLUNAS_IMPORT) - set(linhas[0].keys()):
        return {'linhas': len(linhas), 'validas': 0, 'gravadas': 0, 'erros': [{'linha': 1, 'erro': 'cabeçalho deve ter as colunas: ' + ';'.join(COLUNAS_IMPORT)}], 'simulacao': simular}
    secs = {sem_acento(x['nome']): x['id'] for x in db.todos(banco, 'SELECT id, nome FROM secretarias')}
    secs.update({sem_acento(x['sigla']): x['id'] for x in db.todos(banco, "SELECT id, sigla FROM secretarias WHERE sigla<>''")})
    prontos, erros = [], []
    for i, l in enumerate(linhas, start=2):
        l = {k: (v or '').strip() for k, v in l.items() if k}
        sid = secs.get(sem_acento(l['secretaria']))
        if not sid:
            erros.append({'linha': i, 'erro': f"secretaria “{l['secretaria']}” não cadastrada (cadastre em Carta → Secretarias)"}); continue
        if secretaria_unica is not None and sid != secretaria_unica:
            erros.append({'linha': i, 'erro': 'você só pode importar serviços da sua secretaria'}); continue
        if not l['nome']:
            erros.append({'linha': i, 'erro': 'nome do serviço vazio'}); continue
        if re.search(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', ' '.join(l.values())):
            erros.append({'linha': i, 'erro': 'a linha contém um número com formato de CPF (LGPD)'}); continue
        pubs = [p for p in re.split(r'[,|]\s*', sem_acento(l['publicos'])) if p]
        mapa_p = {'cidadao': 'cidadao', 'empresa': 'empresa', 'empresas': 'empresa', 'servidor': 'servidor', 'servidores': 'servidor', 'outros orgaos': 'orgaos', 'orgaos': 'orgaos'}
        forms = [p for p in re.split(r'[,|]\s*', sem_acento(l['formas'])) if p]
        if any(p not in mapa_p for p in pubs) or any(fm not in FORMAS for fm in forms):
            erros.append({'linha': i, 'erro': 'público: cidadao, empresa, servidor, orgaos · formas: online, presencial, telefone, whatsapp (separados por vírgula)'}); continue
        if l['link_online'] and not l['link_online'].startswith('https://'):
            erros.append({'linha': i, 'erro': 'link_online deve começar com https://'}); continue
        prontos.append(dict(l, secretaria_id=sid, publicos=[mapa_p[p] for p in pubs], formas=forms))
    gravadas = 0
    if not simular and not erros:
        for l in prontos:
            s, k = slug(l['nome']), 2
            while db.um(banco, 'SELECT 1 FROM servicos WHERE slug=%s', (s,)):
                s = f"{slug(l['nome'])}-{k}"; k += 1
            cols = [c for c in COLUNAS_IMPORT if c != 'secretaria'] + ['secretaria_id']
            db.exe(banco, f"INSERT INTO servicos (slug, criado_por, {', '.join(cols)}) VALUES (%s,%s,{', '.join(['%s'] * len(cols))})", (s, quem) + tuple(l[c] for c in cols))
            gravadas += 1
    return {'linhas': len(linhas), 'validas': len(prontos), 'gravadas': gravadas, 'erros': erros, 'simulacao': simular}
