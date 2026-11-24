"""Regras do processo legislativo (um código para qualquer Câmara): numeração, autoria, tramitação,
votação nominal com quórum, estatísticas do vereador (só de sessões publicadas) e autoavaliação PNTP (dimensão 20).
Nada aqui inventa votos, presenças ou atas: tudo é calculado do que a Secretaria registrou ou importou."""
import math, re, secrets
from datetime import date
from pathlib import Path
from . import config, db

TIPOS = [('Projeto de Lei', 'PL'), ('Projeto de Lei Complementar', 'PLC'), ('Projeto de Resolução', 'PR'), ('Projeto de Decreto Legislativo', 'PDL'),
         ('Indicação', 'IND'), ('Requerimento', 'REQ'), ('Moção', 'MOC'), ('Emenda', 'EME'), ('Veto', 'VET')]
TIPO_SIGLA = dict(TIPOS)
PROJETOS = ('Projeto de Lei', 'Projeto de Lei Complementar', 'Projeto de Resolução', 'Projeto de Decreto Legislativo')
SITUACOES_PROP = ['Em tramitação', 'Em comissão', 'Pronta para a pauta', 'Aprovada', 'Aprovado', 'Rejeitada', 'Rejeitado', 'Retirada', 'Arquivada',
                  'Encaminhada ao Executivo', 'Sancionada', 'Promulgada', 'Vetada']
QUORUNS = {'simples': 'Maioria simples (dos votos)', 'absoluta': 'Maioria absoluta (dos membros)', 'dois_tercos': 'Dois terços dos membros'}
VOTOS = {'sim': 'Sim', 'nao': 'Não', 'abstencao': 'Abstenção', 'ausente': 'Ausente'}
DOC_TIPOS = {'texto': 'Texto da proposição', 'parecer': 'Parecer', 'autografo': 'Autógrafo', 'lei': 'Lei sancionada / norma publicada', 'ata': 'Ata',
             'parecer_tce': 'Parecer prévio do TCESP', 'decreto': 'Decreto legislativo', 'outro': 'Outro documento'}
LIMITE_PDF = 20 * 1024 * 1024

def legislatura_atual(b):
    return db.um(b, 'SELECT max(numero) n FROM legislaturas')['n']

def vereadores_atuais(b):
    return db.todos(b, 'SELECT * FROM vereadores WHERE legislatura=%s ORDER BY nome', (legislatura_atual(b),))

def bienio_de(bienio: str, ano: int) -> bool:
    try:
        a, z = [int(x) for x in bienio.replace('–', '-').split('-')[:2]]
        return a <= ano <= z
    except ValueError:
        return False

def presidente_em(b, data: date):
    """Vereador que preside na data (Mesa do biênio em curso)."""
    leg = legislatura_atual(b)
    for m in db.todos(b, "SELECT bienio, nome FROM mesas WHERE legislatura=%s AND cargo='Presidente' AND nome IS NOT NULL", (leg,)):
        if bienio_de(m['bienio'], data.year):
            return db.um(b, 'SELECT * FROM vereadores WHERE legislatura=%s AND nome=%s', (leg, m['nome']))
    return None

# ---------- proposições ----------
def proximo_numero(b, tipo, ano):
    return db.um(b, 'SELECT coalesce(max(numero),0)+1 n FROM proposicoes WHERE tipo=%s AND ano=%s', (tipo, ano))['n']

def rotulo(p):
    return f"{p['tipo']} nº {p['numero']}/{p['ano']}"

def definir_autores(b, pid, autores: list[str]):
    """autores: nomes de vereadores da legislatura atual ou 'Poder Executivo', 'Mesa Diretora', 'Comissão de ...'."""
    leg = legislatura_atual(b)
    db.exe(b, 'DELETE FROM proposicao_autores WHERE proposicao_id=%s', (pid,))
    nomes = []
    for a in autores:
        a = a.strip()
        if not a or a in nomes:
            continue
        v = db.um(b, 'SELECT id FROM vereadores WHERE legislatura=%s AND lower(nome)=lower(%s)', (leg, a)) or db.um(b, 'SELECT id FROM vereadores WHERE lower(nome)=lower(%s) ORDER BY legislatura DESC LIMIT 1', (a,))
        db.exe(b, 'INSERT INTO proposicao_autores (proposicao_id, vereador_id, nome) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (pid, v['id'] if v else None, a))
        nomes.append(a)
    db.exe(b, 'UPDATE proposicoes SET autor=%s WHERE id=%s', ('; '.join(nomes), pid))

def tramitar(b, pid, data, fase, descricao='', sessao_id=None, quem='', origem='cadastro', situacao=None):
    db.exe(b, 'INSERT INTO tramitacao (proposicao_id, data, fase, descricao, sessao_id, registrado_por, origem) VALUES (%s,%s,%s,%s,%s,%s,%s)',
           (pid, data, fase[:120], descricao[:2000], sessao_id, quem, origem))
    if situacao:
        db.exe(b, 'UPDATE proposicoes SET situacao=%s WHERE id=%s', (situacao, pid))

def proposicoes_do_vereador(b, v):
    """Pela autoria estruturada; registros antigos (sem vínculo) pelo nome."""
    ids = {r['proposicao_id'] for r in db.todos(b, 'SELECT proposicao_id FROM proposicao_autores WHERE vereador_id=%s', (v['id'],))}
    n = _norm(v['nome'])
    return [p for p in db.todos(b, 'SELECT * FROM proposicoes ORDER BY ano DESC, numero DESC') if p['id'] in ids or n in _norm(p['autor'])]

def _norm(s):
    import unicodedata
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower().replace('luiz', 'luis')

# ---------- votação nominal ----------
def apurar(b, item, votos: dict[int, str], membros: list, presidente_id=None):
    """Valida e apura uma votação. votos = {vereador_id: 'sim'|'nao'|'abstencao'|'ausente'}.
    Regras: todo membro precisa ter voto registrado; presidente só vota no desempate (Regimento).
    Devolve (resultado, contagem, aviso) ou levanta ValueError com a explicação."""
    faltam = [m['nome'] for m in membros if m['id'] not in votos]
    if faltam:
        raise ValueError('Registre o voto de todos os vereadores (inclusive "Ausente"): faltam ' + ', '.join(faltam) + '.')
    cont = {k: 0 for k in VOTOS}
    for vid, v in votos.items():
        if v not in VOTOS:
            raise ValueError('Voto inválido.')
        if vid != presidente_id:
            cont[v] += 1
    aviso = ''
    voto_pres = votos.get(presidente_id) if presidente_id else None
    total = len(membros)
    if item['quorum'] == 'simples':
        empate = cont['sim'] == cont['nao']
        if voto_pres in ('sim', 'nao') and not empate:
            raise ValueError('O Presidente só vota em caso de empate (Regimento Interno). Registre o voto do Presidente como "Abstenção" ou "Ausente".')
        if empate and voto_pres in ('sim', 'nao'):
            cont[voto_pres] += 1
            aviso = f'Empate desfeito pelo voto do Presidente ({VOTOS[voto_pres]}).'
        elif empate:
            aviso = 'Empate sem voto de desempate do Presidente: proposição não aprovada.'
        resultado = 'aprovado' if cont['sim'] > cont['nao'] else 'rejeitado'
    else:
        # quórum qualificado: conta sobre o total de membros; o voto do Presidente entra (Regimento)
        if voto_pres in ('sim', 'nao'):
            cont[voto_pres] += 1
            aviso = 'Quórum qualificado: o voto do Presidente foi computado.'
        minimo = math.floor(total / 2) + 1 if item['quorum'] == 'absoluta' else math.ceil(total * 2 / 3)
        resultado = 'aprovado' if cont['sim'] >= minimo else 'rejeitado'
        aviso = (aviso + f' Mínimo exigido: {minimo} votos "Sim" de {total} membros.').strip()
    return resultado, cont, aviso

def contagem(b, item_id):
    r = {k: 0 for k in VOTOS}
    for x in db.todos(b, 'SELECT voto, count(*) n FROM votos WHERE item_id=%s GROUP BY voto', (item_id,)):
        r[x['voto']] = x['n']
    return r

def estatisticas_vereador(b, vid):
    """Presença e votos calculados SOMENTE de sessões com presença/votação publicadas."""
    pres = db.um(b, """SELECT count(*) FILTER (WHERE p.situacao='presente') presente, count(*) FILTER (WHERE p.situacao='ausente') ausente,
                       count(*) FILTER (WHERE p.situacao='justificada') justificada, count(*) total
                       FROM presencas p JOIN sessoes s ON s.id=p.sessao_id WHERE s.presenca_publicada AND p.vereador_id=%s""", (vid,))
    votos = db.todos(b, """SELECT s.id sessao_id, s.nome sessao, s.data, i.id item_id, i.descricao, i.resultado, v.voto, p.id pid, p.tipo, p.numero, p.ano, p.ementa
                           FROM votos v JOIN pauta_itens i ON i.id=v.item_id JOIN sessoes s ON s.id=i.sessao_id LEFT JOIN proposicoes p ON p.id=i.proposicao_id
                           WHERE s.votacao_publicada AND v.vereador_id=%s ORDER BY s.data DESC, i.ordem""", (vid,))
    resumo = {k: sum(1 for x in votos if x['voto'] == k) for k in VOTOS}
    return pres, votos, resumo

# ---------- documentos PDF ----------
async def salvar_pdf(request, arquivo, tipo, titulo, descricao, quem, **vinculo):
    if tipo not in DOC_TIPOS:
        raise ValueError('Tipo de documento inválido.')
    if not titulo or len(descricao or '') < 10:
        raise ValueError('Informe o título e uma descrição do conteúdo do documento (pelo menos 10 caracteres), para quem usa leitor de tela.')
    dados = await arquivo.read(LIMITE_PDF + 1)
    if len(dados) > LIMITE_PDF:
        raise ValueError('PDF maior que 20 MB.')
    if not dados.startswith(b'%PDF-'):
        raise ValueError('O arquivo não é um PDF.')
    o = request.state.orgao
    pasta = Path(config.DADOS_DIR) / o['slug'] / 'docs'
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.pdf'
    (pasta / nome).write_bytes(dados)
    cols = ['arquivo', 'tipo', 'titulo', 'descricao', 'bytes', 'enviado_por'] + list(vinculo)
    vals = [nome, tipo, titulo[:200], descricao[:1000], len(dados), quem] + list(vinculo.values())
    return db.exe(o['banco'], f"INSERT INTO documentos ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id", vals)['id']

# ---------- participação: dados pessoais e ofensas ----------
PESSOAL = [re.compile(p) for p in (r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b', r'[\w.+-]+@[\w-]+\.[\w.]+', r'\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b', r'\b\d{2}\.?\d{3}\.?\d{3}-?[\dxX]\b')]
OFENSAS = ('idiota', 'imbecil', 'ladrão', 'ladrao', 'vagabund', 'canalha', 'safad', 'corrupto', 'lixo', 'burro', 'otário', 'otario', 'merda', 'porra', 'caralho')

def problemas_texto(t: str):
    """Avisos para o moderador: dado pessoal (CPF, e-mail, telefone, RG) ou possível ofensa."""
    avisos = []
    if any(p.search(t or '') for p in PESSOAL):
        avisos.append('contém dado pessoal (CPF, e-mail, telefone ou RG)')
    if any(w in (t or '').lower() for w in OFENSAS):
        avisos.append('possível ofensa')
    return avisos

# ---------- autoavaliação PNTP, dimensão 20 ----------
def _sit(feito, total):
    if total == 0 or feito == 0:
        return 'pendente'
    return 'atendido' if feito >= total else 'parcial'

def pntp(b, hoje=None):
    """Situação real de cada critério 20.1 a 20.11, calculada dos dados. Devolve [(cód, critério, situação, detalhe, link)]."""
    hoje = hoje or config.hoje()
    leg = legislatura_atual(b)
    um = lambda sql, *p: db.um(b, sql, p)
    v = um("SELECT count(*) n, count(*) FILTER (WHERE partido<>'') partido, count(*) FILTER (WHERE foto_url<>'' AND bio<>'') completo FROM vereadores WHERE legislatura=%s", leg)
    r = []
    r.append(('20.1', 'Composição e biografia dos vereadores', 'pendente' if not v['n'] else ('atendido' if v['completo'] == v['n'] else 'parcial'),
              f"{v['n']} vereadores na {leg}ª Legislatura; {v['completo']} com foto oficial e biografia.", '/vereadores'))
    leis = um("SELECT count(*) n, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM documentos d WHERE d.proposicao_id=p.id AND d.tipo IN ('lei','autografo'))) doc FROM proposicoes p WHERE p.tipo = ANY(%s) AND p.situacao IN ('Aprovada','Aprovado','Sancionada','Promulgada')", list(PROJETOS))
    r.append(('20.2', 'Leis e atos produzidos', _sit(leis['doc'], leis['n']), f"{leis['n']} projetos aprovados; {leis['doc']} com autógrafo ou norma publicada em PDF.", '/proposicoes?situacao=Aprovada'))
    pj = um("""SELECT count(*) n, count(*) FILTER (WHERE relator<>'' AND EXISTS (SELECT 1 FROM tramitacao t WHERE t.proposicao_id=p.id)
               AND EXISTS (SELECT 1 FROM documentos d WHERE d.proposicao_id=p.id) AND EXISTS (SELECT 1 FROM proposicao_autores a WHERE a.proposicao_id=p.id)) ok
               FROM proposicoes p WHERE p.tipo = ANY(%s) AND p.ano >= %s""", list(PROJETOS), hoje.year - 1)
    r.append(('20.3', 'Projetos com tramitação, autor, relator e documentos', _sit(pj['ok'], pj['n']), f"{pj['n']} projetos de {hoje.year - 1}–{hoje.year}; {pj['ok']} completos.", '/proposicoes'))
    ses = um("SELECT count(*) n, count(*) FILTER (WHERE pauta_publicada AND (pauta<>'' OR EXISTS (SELECT 1 FROM pauta_itens i WHERE i.sessao_id=s.id))) pauta, count(*) FILTER (WHERE ata_publicada AND presenca_publicada) ata, count(*) FILTER (WHERE votacao_publicada) vot, count(*) FILTER (WHERE video_url<>'' OR EXISTS (SELECT 1 FROM transmissoes t WHERE t.sessao_id=s.id AND t.video<>'')) video FROM sessoes s WHERE data <= %s AND data > %s", hoje, date(hoje.year - 1, hoje.month, min(hoje.day, 28)))
    r.append(('20.4', 'Pauta das sessões do Plenário', _sit(ses['pauta'], ses['n']), f"{ses['n']} sessões nos últimos 12 meses; {ses['pauta']} com pauta publicada no portal (texto ou itens).", '/sessoes'))
    com = um("SELECT count(*) n, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM comissao_reunioes r WHERE r.comissao_id=c.id AND r.publicada) OR EXISTS (SELECT 1 FROM pareceres p WHERE p.comissao_id=c.id AND p.publicado)) ok FROM comissoes c WHERE ativa")
    r.append(('20.5', 'Pauta e pareceres das Comissões', _sit(com['ok'], com['n']), f"{com['n']} comissões ativas; {com['ok']} com pauta ou parecer publicado.", '/comissoes'))
    r.append(('20.6', 'Atas das sessões com presença', _sit(ses['ata'], ses['n']), f"{ses['ata']} de {ses['n']} sessões com ata e presença publicadas.", '/sessoes'))
    vi = um("SELECT count(DISTINCT s.id) n, count(DISTINCT s.id) FILTER (WHERE s.votacao_publicada) pub FROM sessoes s JOIN pauta_itens i ON i.sessao_id=s.id WHERE i.resultado IN ('aprovado','rejeitado') AND s.data <= %s", hoje)
    r.append(('20.7', 'Votações nominais', _sit(vi['pub'], vi['n']), f"{vi['n']} sessões com itens votados; {vi['pub']} com votação nominal publicada.", '/sessoes'))
    ct = um("SELECT count(*) n, count(*) FILTER (WHERE publicado AND decreto<>'' AND pauta_item_id IS NOT NULL AND EXISTS (SELECT 1 FROM documentos d WHERE d.contas_id=c.id AND d.tipo='parecer_tce')) ok FROM contas_julgamento c")
    r.append(('20.8', 'Julgamento das contas do Prefeito', _sit(ct['ok'], ct['n']), f"{ct['n']} exercícios cadastrados; {ct['ok']} com parecer do TCESP, votação e decreto publicados.", '/contas'))
    r.append(('20.9', 'Transmissão das sessões e audiências', _sit(ses['video'], ses['n']), f"{ses['video']} de {ses['n']} sessões com vídeo vinculado.", '/transmissoes'))
    di = um('SELECT count(*) n FROM diarias_legislativo WHERE ano >= %s', hoje.year - 1)
    decl = (db.cfg(b, 'diarias_declaracao') or {}).get(str(hoje.year))
    r.append(('20.10', 'Diárias e verbas dos parlamentares', 'atendido' if di['n'] or decl else 'pendente',
              f"{di['n']} lançamentos em {hoje.year - 1}–{hoje.year}." + (f" Declaração de {hoje.year}: {decl}" if decl else ''), '/transparencia/diarias-camara'))
    at = um("""SELECT count(*) n, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM proposicao_autores a WHERE a.vereador_id=v.id)
               AND EXISTS (SELECT 1 FROM presencas p JOIN sessoes s ON s.id=p.sessao_id WHERE p.vereador_id=v.id AND s.presenca_publicada)) ok FROM vereadores v WHERE legislatura=%s""", leg)
    r.append(('20.11', 'Atividade dos parlamentares', _sit(at['ok'], at['n']), f"{at['ok']} de {at['n']} perfis com proposições vinculadas e presença publicada.", '/vereadores'))
    return r

def vincular_autores_antigos(b):
    """Proposições antigas (seed/importação sem autoria estruturada): cria os vínculos a partir do autor em texto,
    ligando ao vereador quando o nome bate exatamente. Idempotente; não inventa autoria."""
    n = 0
    for p in db.todos(b, 'SELECT id, autor, ano FROM proposicoes p WHERE autor<>\'\' AND NOT EXISTS (SELECT 1 FROM proposicao_autores a WHERE a.proposicao_id=p.id)'):
        for nome in [x.strip() for x in re.split(r'[;|]', p['autor']) if x.strip()]:
            v = db.um(b, 'SELECT id FROM vereadores WHERE lower(nome)=lower(%s) ORDER BY abs(legislatura - 15) LIMIT 1', (nome,))
            db.exe(b, 'INSERT INTO proposicao_autores (proposicao_id, vereador_id, nome) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (p['id'], v['id'] if v else None, nome))
        n += 1
    return n

# ---------- sessão em linha do tempo (24/11/2026): nenhum passo é obrigatório; registro pode ser feito depois ----------
TIPOS_SESSAO = ['Ordinária', 'Extraordinária', 'Solene', 'Especial']
SITUACOES_SESSAO = {'agendada': 'Agendada', 'realizada': 'Realizada', 'cancelada': 'Cancelada'}
EVENTOS = {'expediente': 'Expediente (leitura de correspondências e comunicações)', 'leitura': 'Leitura de matéria',
           'orador': 'Uso da palavra por vereador(a)', 'tribuna': 'Tribuna livre (cidadão)', 'ordem_do_dia': 'Início da Ordem do Dia',
           'suspensao': 'Suspensão da sessão', 'reabertura': 'Reabertura', 'explicacoes': 'Explicações pessoais',
           'comunicacao': 'Comunicação da Presidência', 'outro': 'Outro registro'}
PLATAFORMAS = {'youtube': 'YouTube', 'facebook': 'Facebook', 'instagram': 'Instagram', 'outro': 'Vídeo'}
RESULTADOS_ITEM = {'aprovado': 'Aprovado', 'rejeitado': 'Rejeitado', 'retirado': 'Retirado de pauta', 'adiado': 'Adiado'}
FEMININOS = ('Indicação', 'Moção', 'Emenda')

def plataforma(url):
    u = (url or '').lower()
    if re.search(r'(youtube\.com|youtu\.be)', u):
        return 'youtube'
    if re.search(r'(facebook\.com|fb\.watch)', u):
        return 'facebook'
    if 'instagram.com' in u:
        return 'instagram'
    return 'outro'

def hora(h):
    """'19:05', '19h05', '19h', '19' → '19h05' / '19h'; vazio → ''. Levanta ValueError se não for hora."""
    h = (h or '').strip().lower().replace(' ', '')
    if not h:
        return ''
    m = re.fullmatch(r'(\d{1,2})(?:[:h](\d{2})?)?(?:min)?', h)
    if not m or int(m.group(1)) > 23 or (m.group(2) and int(m.group(2)) > 59):
        raise ValueError(f'Hora inválida: "{h}". Use, por exemplo, 19h05 ou 19:05.')
    return f"{int(m.group(1))}h{m.group(2) if m.group(2) and m.group(2) != '00' else ''}"

def proximo_numero_sessao(b, tipo, ano):
    return db.um(b, 'SELECT coalesce(max(numero), 0) + 1 n FROM sessoes WHERE tipo=%s AND extract(year FROM data)=%s', (tipo, ano))['n']

def nome_sessao(numero, tipo, ano):
    return f'{numero}ª Sessão {tipo} de {ano}'

def marcar_realizada(b, sid):
    """Qualquer registro do que aconteceu (presença, votação, horário, acontecimento, ata) mostra que a sessão foi realizada."""
    db.exe(b, "UPDATE sessoes SET situacao='realizada' WHERE id=%s AND situacao='agendada'", (sid,))

def sincronizar_video(b, sid):
    """sessoes.video_url = primeiro vídeo cadastrado (as telas antigas e a autoavaliação PNTP usam esse campo)."""
    v = db.um(b, 'SELECT url FROM sessao_videos WHERE sessao_id=%s ORDER BY id LIMIT 1', (sid,))
    db.exe(b, 'UPDATE sessoes SET video_url=%s WHERE id=%s', (v['url'] if v else '', sid))

def situacao_apos_votacao(b, item, resultado, s, quem, detalhe=''):
    """Tramitação e situação da proposição depois do resultado do item (nominal ou simbólico)."""
    if not item['proposicao_id']:
        return
    pr = db.um(b, 'SELECT tipo FROM proposicoes WHERE id=%s', (item['proposicao_id'],))
    if resultado in ('aprovado', 'rejeitado'):
        fem = pr['tipo'] in FEMININOS or pr['tipo'].startswith('Proposta') or pr['tipo'] in PROJETOS
        sit = ('Aprovada' if fem else 'Aprovado') if resultado == 'aprovado' else ('Rejeitada' if fem else 'Rejeitado')
        tramitar(b, item['proposicao_id'], s['data'], f"Votação em Plenário — {item['fase']}",
                 f"{'Aprovado' if resultado == 'aprovado' else 'Rejeitado'} na {s['nome']}{': ' + detalhe if detalhe else '.'}".strip(), sessao_id=s['id'], quem=quem, situacao=sit)
    else:
        tramitar(b, item['proposicao_id'], s['data'], RESULTADOS_ITEM[resultado], f"{s['nome']}{': ' + detalhe if detalhe else ''}", sessao_id=s['id'], quem=quem)

def eventos(b, sid):
    return db.todos(b, """SELECT e.*, v.nome vereador, p.tipo ptipo, p.numero pnumero, p.ano pano, p.ementa pementa FROM sessao_eventos e
                          LEFT JOIN vereadores v ON v.id=e.vereador_id LEFT JOIN proposicoes p ON p.id=e.proposicao_id
                          WHERE e.sessao_id=%s ORDER BY e.ordem, e.id""", (sid,))

def videos(b, sid):
    return db.todos(b, 'SELECT * FROM sessao_videos WHERE sessao_id=%s ORDER BY id', (sid,))

def passos(b, s):
    """O que já foi registrado e publicado em cada etapa. Só informa: nada bloqueia as demais etapas nem a publicação."""
    sid = s['id']
    n_itens = db.um(b, 'SELECT count(*) n FROM pauta_itens WHERE sessao_id=%s', (sid,))['n']
    n_vot = db.um(b, 'SELECT count(*) n FROM pauta_itens WHERE sessao_id=%s AND resultado IS NOT NULL', (sid,))['n']
    n_pres = db.um(b, 'SELECT count(*) n FROM presencas WHERE sessao_id=%s', (sid,))['n']
    n_ev = db.um(b, 'SELECT count(*) n FROM sessao_eventos WHERE sessao_id=%s', (sid,))['n']
    n_vid = db.um(b, 'SELECT count(*) n FROM sessao_videos WHERE sessao_id=%s', (sid,))['n']
    tem_ata = len(s['ata'] or '') >= 20 or bool(db.um(b, "SELECT 1 FROM documentos WHERE sessao_id=%s AND tipo='ata'", (sid,)))
    membros = len(vereadores_atuais(b))
    P = lambda k, t, feito, resumo, pub=None: {'chave': k, 'titulo': t, 'feito': feito, 'resumo': resumo, 'publicado': pub}
    return [P('agenda', 'Agendamento', True, f"{s['tipo']} · {s['data'].strftime('%d/%m/%Y')} às {s['hora']} · {SITUACOES_SESSAO[s['situacao']]}"),
            P('pauta', 'Pauta (Ordem do Dia)', n_itens > 0 or bool(s['pauta']), f'{n_itens} item(ns)' if n_itens else 'nenhum item', s['pauta_publicada']),
            P('abertura', 'Abertura e presença', bool(s['aberta_as']) or n_pres > 0,
              ' · '.join(x for x in (f"aberta às {s['aberta_as']}" if s['aberta_as'] else '', f'presença de {n_pres} de {membros}' if n_pres else '') if x) or 'não registrada', s['presenca_publicada']),
            P('acontecimentos', 'Acontecimentos', n_ev > 0, f'{n_ev} registro(s)' if n_ev else 'nenhum registro', s['linha_publicada']),
            P('votacoes', 'Votações', n_vot > 0, f'{n_vot} de {n_itens} item(ns) com resultado' if n_itens else 'sem itens na pauta', s['votacao_publicada']),
            P('encerramento', 'Encerramento', bool(s['encerrada_as']), f"encerrada às {s['encerrada_as']}" if s['encerrada_as'] else 'não registrado', s['linha_publicada']),
            P('videos', 'Vídeos', n_vid > 0, f'{n_vid} vídeo(s)' if n_vid else 'nenhum vídeo', True if n_vid else None),
            P('ata', 'Ata', tem_ata, 'registrada' if tem_ata else 'não registrada', s['ata_publicada'])]

def participacao_vereador(b, vid):
    """Acontecimentos em que o(a) vereador(a) aparece, só de sessões com a linha do tempo publicada."""
    return db.todos(b, """SELECT e.tipo, e.hora, e.descricao, s.id sessao_id, s.nome sessao, s.data, p.id pid, p.tipo ptipo, p.numero pnumero, p.ano pano
                          FROM sessao_eventos e JOIN sessoes s ON s.id=e.sessao_id LEFT JOIN proposicoes p ON p.id=e.proposicao_id
                          WHERE s.linha_publicada AND e.vereador_id=%s ORDER BY s.data DESC, e.ordem, e.id LIMIT 200""", (vid,))
