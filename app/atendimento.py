"""e-SIC (Lei 12.527/2011) e Ouvidoria (Lei 13.460/2017) — regras, prazos, histórico, recursos, encaminhamento entre
órgãos e notificações (23/11/2026). As telas estão em portal_atendimento.py e admin_atendimento.py.

Prazos (dias corridos; se o último dia cair em sábado ou domingo, passa para o próximo dia útil — Lei 9.784/1999, art. 66):
  - pedido de informação: 20 dias, prorrogáveis uma vez por 10 com justificativa comunicada ao requerente (LAI, art. 11);
  - recurso: 10 dias para o requerente recorrer da resposta; a autoridade superior decide em 5 (LAI, art. 15). Uma 2ª
    instância é opcional e depende da norma local (Configuração → instâncias de recurso);
  - manifestação de ouvidoria: 30 dias, prorrogáveis uma vez por 30 com justificativa (Lei 13.460, art. 16);
  - complementação: pedida uma única vez; o cidadão tem 20 dias; o prazo fica suspenso e volta a correr quando ele
    responde (o que faltava, para pedidos; 30 dias novos, para manifestações). Sem resposta, o atendimento é encerrado.
Proteção de dados: nome e e-mail ficam só na tabela `esic`; nunca aparecem no portal; na Ouvidoria a identificação é
informação de acesso restrito (Lei 13.460, art. 10, § 7º) e, em denúncia ou com "preservar identidade", só aparece no
painel para a Ouvidoria/SIC depois de um clique que fica registrado. Encaminhamento a outro órgão com identidade
preservada vai SEM nome e e-mail; a resposta volta pela integração e o órgão de origem avisa o cidadão."""
import hashlib, re, secrets
from datetime import date, timedelta
from . import config, db
from . import notificacoes as N

CATEGORIAS = ['Reclamação', 'Sugestão', 'Elogio', 'Denúncia', 'Solicitação']
SITUACOES = {'recebido': 'Recebido', 'analise': 'Em análise', 'prorrogado': 'Prazo prorrogado', 'complementacao': 'Aguardando complemento do cidadão',
             'respondido': 'Respondido', 'recurso': 'Em recurso', 'encaminhado': 'Encaminhado a outro órgão', 'encerrado': 'Encerrado'}
ABERTAS = ('recebido', 'analise', 'prorrogado', 'complementacao', 'recurso')
DECISOES = {'concedido': 'Acesso concedido', 'parcial': 'Acesso parcialmente concedido', 'negado': 'Acesso negado',
            'nao_possui': 'Informação inexistente ou não produzida por este órgão', 'encaminhado': 'Encaminhado ao órgão competente'}
DECISOES_RECURSO = {'provido': 'Recurso provido (acesso concedido)', 'parcial': 'Recurso parcialmente provido', 'desprovido': 'Recurso não provido (decisão mantida)',
                    'nao_conhecido': 'Recurso não conhecido (fora do prazo ou sem relação com o pedido)'}
CANAIS = {'internet': 'Portal (internet)', 'presencial': 'Presencial', 'telefone': 'Telefone', 'carta': 'Correspondência', 'email': 'E-mail', 'orgao': 'Encaminhado por outro órgão'}
PRAZO = {'pedido': 20, 'manifestacao': 30}
PRORROGA = {'pedido': 10, 'manifestacao': 30}
RECURSO_INTERPOR, RECURSO_DECIDIR, DIAS_COMPLEMENTO = 10, 5, 20
CPF = re.compile(r'\d{3}\.?\d{3}\.?\d{3}-?\d{2}')

CONF_PADRAO = {'unidade': 'Serviço de Informação ao Cidadão (SIC)', 'unidade_ouvidoria': 'Ouvidoria', 'autoridade_1': '', 'autoridade_2': '',
               'instancias': 1, 'norma_lai': '', 'norma_lai_url': '', 'norma_ouvidoria': '', 'norma_ouvidoria_url': '', 'email_equipe': ''}

def conf(b):
    c = dict(CONF_PADRAO)
    c.update(db.cfg(b, 'atendimento', {}) or {})
    c['instancias'] = 2 if str(c.get('instancias')) == '2' else 1
    return c

class Erro(ValueError):
    """Mensagem simples para a tela."""

# ---------- datas ----------
def util(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d

def limite(inicio: date, dias: int) -> date:
    return util(inicio + timedelta(days=dias))

def prazo_info(p, b=None, hoje=None):
    """(texto, classe) do prazo que está correndo agora (b: banco do órgão, para o prazo do recurso aberto)."""
    hoje = hoje or config.hoje()
    if p['situacao'] in ('respondido', 'encaminhado', 'encerrado'):
        return ('concluído', 'ok')
    if p['situacao'] == 'complementacao':
        return (f"suspenso: aguardando o cidadão até {p['complemento_ate'].strftime('%d/%m/%Y')}" if p.get('complemento_ate') else 'suspenso', 'alerta')
    lim = p.get('prazo')
    if p['situacao'] == 'recurso' and b:
        r = db.um(b, "SELECT prazo FROM esic_recursos WHERE esic_id=%s AND decisao='' ORDER BY instancia DESC LIMIT 1", (p['id'],))
        lim = r['prazo'] if r else lim
    if not lim:
        return ('—', '')
    falta = (lim - hoje).days
    txt = f"vencido há {-falta} dia(s)" if falta < 0 else 'vence hoje' if falta == 0 else f'faltam {falta} dia(s)'
    return (f"{txt} ({lim.strftime('%d/%m/%Y')})", 'erro' if falta <= 2 else 'alerta' if falta <= 5 else '')

# ---------- código de acesso do cidadão ----------
def _sal(b):
    s = db.cfg(b, 'atendimento_sal')
    if not s:
        s = secrets.token_hex(16)
        db.set_cfg(b, 'atendimento_sal', s)
    return s

def _hash(b, protocolo, codigo):
    return hashlib.sha256(f"{_sal(b)}|{protocolo.upper()}|{codigo.upper().replace('-', '').strip()}".encode()).hexdigest()

def novo_codigo():
    a = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'  # sem 0/O, 1/I
    s = ''.join(secrets.choice(a) for _ in range(12))
    return f'{s[:4]}-{s[4:8]}-{s[8:]}'

def confere_codigo(b, p, codigo):
    import hmac
    return bool(p.get('codigo_hash') and codigo and hmac.compare_digest(p['codigo_hash'], _hash(b, p['protocolo'], codigo)))

# ---------- leitura ----------
def pega(b, pid):
    return db.um(b, 'SELECT * FROM esic WHERE id=%s', (pid,))

def por_protocolo(b, protocolo):
    return db.um(b, 'SELECT * FROM esic WHERE protocolo=%s', ((protocolo or '').strip().upper()[:40],))

def historico(b, pid, so_publico=False):
    return db.todos(b, 'SELECT * FROM esic_historico WHERE esic_id=%s' + (' AND publico' if so_publico else '') + ' ORDER BY id', (pid,))

def recursos(b, pid):
    return db.todos(b, 'SELECT * FROM esic_recursos WHERE esic_id=%s ORDER BY instancia', (pid,))

def _hist(b, pid, evento, texto='', autor='', publico=True):
    db.exe(b, 'INSERT INTO esic_historico (esic_id, evento, publico, texto, autor) VALUES (%s,%s,%s,%s,%s)', (pid, evento, publico, (texto or '')[:20000], (autor or '')[:120]))
    db.exe(b, 'UPDATE esic SET atualizado_em=now() WHERE id=%s', (pid,))

def identidade_restrita(p):
    """Identificação que só aparece depois do clique registrado: denúncia, pedido de preservação ou comunicação anônima."""
    return bool(p['anonimo'] or p['identidade_preservada'] or (p['tipo'] == 'manifestacao' and p['categoria'] == 'Denúncia'))

# ---------- e-mails ----------
def _rodape(o, p):
    return (f"\n\nAcompanhe em https://{o['dominio']}/acesso?protocolo={p['protocolo']} (informe o código de acesso que você recebeu no registro).\n"
            f"Esta é uma mensagem automática de {o['nome']}. Não responda a este e-mail.")

def _avisar(o, p, assunto, corpo):
    if p.get('email') and not p.get('anonimo'):
        N.enfileirar(o['banco'], p['email'], f"[{p['protocolo']}] {assunto}", f"Olá, {(p.get('nome') or '').split(' ')[0] or 'cidadão'}.\n\n{corpo}{_rodape(o, p)}", p['protocolo'])

def _avisar_equipe(o, p, assunto, corpo=''):
    c = conf(o['banco'])
    for em in [x.strip() for x in (c.get('email_equipe') or '').replace(';', ',').split(',') if x.strip()]:
        # sem dado pessoal do cidadão: só protocolo, tipo, assunto e prazo
        N.enfileirar(o['banco'], em, f"[{p['protocolo']}] {assunto}",
                     f"{corpo}\n\nProtocolo: {p['protocolo']}\nTipo: {'Pedido de informação (LAI)' if p['tipo'] == 'pedido' else 'Ouvidoria · ' + (p['categoria'] or '')}\n"
                     f"Prazo: {p['prazo'].strftime('%d/%m/%Y') if p.get('prazo') else '—'}\n\nAbra no painel: https://{o['dominio']}/admin/atendimento/{p['id']}", p['protocolo'])

def _tipo_txt(p):
    return 'pedido de acesso à informação' if p['tipo'] == 'pedido' else 'manifestação de ouvidoria'

# ---------- registro ----------
def registrar(o, d, canal='internet', quem='cidadão', origem=None):
    """Registra pedido (tipo='pedido') ou manifestação (tipo='manifestacao'). Devolve (registro, código de acesso).
    d: tipo, categoria, assunto, texto, nome, email, tipo_pessoa, anonimo, preservar, servico_id."""
    b = o['banco']
    tipo = 'pedido' if d.get('tipo') == 'pedido' else 'manifestacao'
    categoria = d.get('categoria') if tipo == 'manifestacao' and d.get('categoria') in CATEGORIAS else ''
    anonimo = tipo == 'manifestacao' and categoria == 'Denúncia' and bool(d.get('anonimo'))
    assunto, texto = (d.get('assunto') or '').strip(), (d.get('texto') or '').strip()
    nome, email = (d.get('nome') or '').strip(), (d.get('email') or '').strip()
    if not assunto or not texto:
        raise Erro('Preencha assunto e texto.')
    if tipo == 'manifestacao' and not categoria:
        raise Erro('Escolha o tipo da manifestação (reclamação, sugestão, elogio, denúncia ou solicitação).')
    if anonimo:
        nome, email = '', ''
    elif canal == 'internet' and (not nome or '@' not in email):
        raise Erro('Preencha seu nome e um e-mail para receber a resposta.')
    elif canal == 'orgao' and not nome:
        nome = 'Identidade preservada pelo órgão de origem'
    elif canal not in ('internet', 'orgao') and not nome:
        raise Erro('Informe o nome do solicitante (a resposta pode ser entregue no balcão, por telefone ou carta).')
    hoje = config.hoje()
    for _ in range(5):
        prot = f"{'SIC' if tipo == 'pedido' else 'OUV'}-{hoje.year}-{secrets.token_hex(3).upper()}"
        if not db.um(b, 'SELECT 1 FROM esic WHERE protocolo=%s', (prot,)):
            break
    codigo = novo_codigo()
    prazo = limite(hoje, PRAZO[tipo])
    p = db.exe(b, """INSERT INTO esic (protocolo, tipo, categoria, assunto, texto, nome, email, recebido, recebido_em, prazo, situacao, canal, tipo_pessoa,
                                       anonimo, identidade_preservada, servico_id, codigo_hash, origem_orgao, origem_nome, protocolo_origem)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,'recebido',%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
               (prot, tipo, categoria, assunto[:200], texto[:20000], nome[:120], email[:120], hoje, prazo, canal if canal in CANAIS else 'internet',
                d.get('tipo_pessoa') if d.get('tipo_pessoa') in ('fisica', 'juridica') else '', anonimo, bool(d.get('preservar')) or anonimo,
                d.get('servico_id'), _hash(b, prot, codigo),
                (origem or {}).get('slug', ''), (origem or {}).get('nome', ''), (d.get('protocolo_origem') or '')[:40]))
    txt = f"{'Pedido de informação' if tipo == 'pedido' else 'Manifestação (' + categoria + ')'} registrado(a) pelo canal {CANAIS.get(p['canal'], p['canal']).lower()}."
    if origem:
        txt = f"Recebido(a) de {origem['nome']} (protocolo de origem {p['protocolo_origem']}), por ser assunto deste órgão."
    _hist(b, p['id'], 'registro', txt, quem)
    corpo = (f"Recebemos o seu {_tipo_txt(p)}.\n\nProtocolo: {prot}\nCódigo de acesso: {codigo}\nAssunto: {p['assunto']}\n"
             f"Prazo para resposta: até {prazo.strftime('%d/%m/%Y')}"
             + (' (20 dias, prorrogáveis por mais 10 com justificativa — Lei 12.527/2011, art. 11).' if tipo == 'pedido' else ' (30 dias, prorrogáveis por mais 30 com justificativa — Lei 13.460/2017, art. 16).')
             + '\n\nGuarde o protocolo e o código: com eles você acompanha o andamento, vê a resposta e, se for o caso, apresenta recurso.')
    if origem:
        corpo = f"O seu {_tipo_txt(p)} feito a {origem['nome']} (protocolo {p['protocolo_origem']}) foi encaminhado a {o['nome']}, que é o órgão responsável pelo assunto (Lei 12.527/2011, art. 11, § 1º, III).\n\n" + corpo
    _avisar(o, p, 'Recebemos o seu ' + _tipo_txt(p), corpo)
    _avisar_equipe(o, p, 'Novo ' + _tipo_txt(p), f"Chegou um novo {_tipo_txt(p)}" + (f" de {origem['nome']}" if origem else '') + '.')
    return p, codigo

# ---------- ações da equipe ----------
def _aberto(p):
    if p['situacao'] not in ABERTAS:
        raise Erro('Este atendimento já foi concluído.')

def andamento(o, p, setor, quem):
    _aberto(p)
    db.exe(o['banco'], "UPDATE esic SET situacao=CASE WHEN situacao IN ('recebido') THEN 'analise' ELSE situacao END, setor=%s WHERE id=%s", (setor[:120], p['id']))
    _hist(o['banco'], p['id'], 'setor', f'Em análise{" no setor " + setor if setor else ""}.', quem)

def nota(o, p, texto, quem):
    if not (texto or '').strip():
        raise Erro('Escreva a nota.')
    _hist(o['banco'], p['id'], 'nota', texto.strip(), quem, publico=False)

def prorrogar(o, p, justificativa, quem):
    _aberto(p)
    if p['prorrogado_em']:
        raise Erro('O prazo já foi prorrogado uma vez (a lei permite uma única prorrogação).')
    if p['situacao'] not in ('recebido', 'analise'):
        raise Erro('Só dá para prorrogar enquanto o pedido está recebido ou em análise.')
    if len((justificativa or '').strip()) < 10:
        raise Erro('Escreva a justificativa da prorrogação (ela é enviada ao cidadão).')
    novo = limite(p['prazo'] or config.hoje(), PRORROGA[p['tipo']])
    db.exe(o['banco'], "UPDATE esic SET situacao='prorrogado', justificativa=%s, prorrogado_em=%s, prazo=%s WHERE id=%s", (justificativa.strip(), config.hoje(), novo, p['id']))
    _hist(o['banco'], p['id'], 'prorrogacao', f"Prazo prorrogado por {PRORROGA[p['tipo']]} dias, até {novo.strftime('%d/%m/%Y')}. Justificativa: {justificativa.strip()}", quem)
    p = pega(o['banco'], p['id'])
    _avisar(o, p, 'Prazo prorrogado', f"O prazo do seu {_tipo_txt(p)} foi prorrogado para {novo.strftime('%d/%m/%Y')}.\n\nJustificativa: {justificativa.strip()}")

def pedir_complemento(o, p, texto, quem):
    _aberto(p)
    if p['situacao'] not in ('recebido', 'analise', 'prorrogado'):
        raise Erro('Não dá para pedir complemento nesta situação.')
    if p['complemento_usado']:
        raise Erro('O complemento já foi pedido uma vez para este atendimento.')
    if p['anonimo'] or not p['email']:
        raise Erro('Sem e-mail do cidadão: o pedido de complemento ficaria sem aviso. Registre uma nota e prossiga com o que há.')
    if len((texto or '').strip()) < 10:
        raise Erro('Explique o que falta (o texto vai para o cidadão).')
    hoje = config.hoje()
    restante = max(0, ((p['prazo'] or hoje) - hoje).days)
    ate = limite(hoje, DIAS_COMPLEMENTO)
    db.exe(o['banco'], "UPDATE esic SET situacao='complementacao', complemento_pedido=%s, complemento_ate=%s, complemento_restante=%s, complemento_usado=TRUE WHERE id=%s",
           (texto.strip(), ate, restante, p['id']))
    _hist(o['banco'], p['id'], 'complementacao', f"Pedido de complemento ao cidadão (responder até {ate.strftime('%d/%m/%Y')}; o prazo fica suspenso): {texto.strip()}", quem)
    p = pega(o['banco'], p['id'])
    _avisar(o, p, 'Precisamos de mais informações', f"Para continuar o atendimento, precisamos que você complemente o seu {_tipo_txt(p)}:\n\n{texto.strip()}\n\n"
            f"Responda pelo portal até {ate.strftime('%d/%m/%Y')}. Enquanto isso o prazo fica suspenso; sem o complemento, o atendimento será encerrado.")

def complementar(o, p, texto):
    """O cidadão responde ao pedido de complemento (pelo portal, com o código de acesso)."""
    if p['situacao'] != 'complementacao':
        raise Erro('Não há complemento pendente neste protocolo.')
    if len((texto or '').strip()) < 3:
        raise Erro('Escreva o complemento.')
    hoje = config.hoje()
    dias = PRAZO['manifestacao'] if p['tipo'] == 'manifestacao' else max(1, p['complemento_restante'] or 1)
    novo = limite(hoje, dias)
    db.exe(o['banco'], "UPDATE esic SET situacao=CASE WHEN prorrogado_em IS NULL THEN 'analise' ELSE 'prorrogado' END, prazo=%s WHERE id=%s", (novo, p['id']))
    _hist(o['banco'], p['id'], 'complemento', texto.strip()[:5000], 'cidadão')
    p = pega(o['banco'], p['id'])
    _avisar_equipe(o, p, 'Complemento recebido', 'O cidadão respondeu ao pedido de complemento. O prazo voltou a correr.')

def responder(o, p, resposta, decisao, fundamento, quem):
    _aberto(p)
    if p['situacao'] == 'recurso':
        raise Erro('Há recurso aberto: a decisão é da autoridade de recurso (tela abaixo).')
    if p['situacao'] == 'complementacao':
        raise Erro('Aguardando o complemento do cidadão. Espere a resposta dele ou o fim do prazo.')
    if len((resposta or '').strip()) < 5:
        raise Erro('Escreva a resposta.')
    if p['tipo'] == 'pedido':
        if decisao not in DECISOES or decisao == 'encaminhado':
            raise Erro('Escolha o resultado do pedido (concedido, parcial, negado ou informação inexistente).')
        if decisao in ('negado', 'parcial') and len((fundamento or '').strip()) < 5:
            raise Erro('Negativa, mesmo parcial, precisa do fundamento legal (LAI, art. 11, § 1º, II; ex.: art. 23, inciso ..., ou art. 31).')
    else:
        decisao, fundamento = '', ''
    if CPF.search(resposta):
        raise Erro('A resposta tem um número de CPF. Retire ou mascare antes de enviar (LGPD).')
    db.exe(o['banco'], "UPDATE esic SET resposta=%s, decisao=%s, fundamento=%s, situacao='respondido', respondido=%s, respondido_por=%s WHERE id=%s",
           (resposta.strip(), decisao, (fundamento or '').strip()[:500], config.hoje(), quem[:120], p['id']))
    _hist(o['banco'], p['id'], 'resposta', (f"{DECISOES[decisao]}. " if decisao else '') + resposta.strip() + (f"\n\nFundamento legal: {fundamento.strip()}" if fundamento else ''), quem)
    p = pega(o['banco'], p['id'])
    corpo = f"O seu {_tipo_txt(p)} foi respondido.\n\n" + (f"Resultado: {DECISOES[decisao]}\n\n" if decisao else '') + f"Resposta:\n{resposta.strip()}"
    if fundamento:
        corpo += f"\n\nFundamento legal: {fundamento.strip()}"
    if p['tipo'] == 'pedido':
        c = conf(o['banco'])
        ate = limite(config.hoje(), RECURSO_INTERPOR)
        corpo += (f"\n\nSe não concordar, você pode apresentar recurso pelo portal até {ate.strftime('%d/%m/%Y')} (10 dias — Lei 12.527/2011, art. 15)."
                  + (f" Quem decide: {c['autoridade_1']}." if c['autoridade_1'] else '') + ' A decisão sai em até 5 dias.')
    else:
        corpo += '\n\nConte para nós se a resposta resolveu: a avaliação está na página do protocolo.'
    _avisar(o, p, 'Resposta ao seu ' + _tipo_txt(p), corpo)

def pode_recorrer(b, p, hoje=None):
    """(instância, até) se o cidadão ainda pode recorrer; None se não."""
    hoje = hoje or config.hoje()
    if p['tipo'] != 'pedido' or p['situacao'] != 'respondido' or not p['respondido']:
        return None
    rs = recursos(b, p['id'])
    c = conf(b)
    if not rs:
        ate = limite(p['respondido'], RECURSO_INTERPOR)
        return (1, ate) if hoje <= ate else None
    ult = rs[-1]
    if ult['instancia'] >= c['instancias'] or not ult['decidido'] or ult['decisao'] == 'provido':
        return None
    ate = limite(ult['decidido'], RECURSO_INTERPOR)
    return (ult['instancia'] + 1, ate) if hoje <= ate else None

def recorrer(o, p, texto):
    pr = pode_recorrer(o['banco'], p)
    if not pr:
        raise Erro('O prazo de recurso terminou ou não cabe recurso nesta situação.')
    if len((texto or '').strip()) < 10:
        raise Erro('Explique por que você não concorda com a resposta.')
    inst, _ = pr
    hoje = config.hoje()
    prazo = limite(hoje, RECURSO_DECIDIR)
    db.exe(o['banco'], 'INSERT INTO esic_recursos (esic_id, instancia, texto, recebido, prazo) VALUES (%s,%s,%s,%s,%s)', (p['id'], inst, texto.strip()[:5000], hoje, prazo))
    db.exe(o['banco'], "UPDATE esic SET situacao='recurso' WHERE id=%s", (p['id'],))
    _hist(o['banco'], p['id'], 'recurso', f"Recurso de {inst}ª instância apresentado (decisão até {prazo.strftime('%d/%m/%Y')}): {texto.strip()[:5000]}", 'cidadão')
    p = pega(o['banco'], p['id'])
    c = conf(o['banco'])
    quem = c['autoridade_1'] if inst == 1 else c['autoridade_2']
    _avisar(o, p, 'Recebemos o seu recurso', f"Recebemos o seu recurso de {inst}ª instância.{(' Quem decide: ' + quem + '.') if quem else ''} A decisão sai até {prazo.strftime('%d/%m/%Y')} (5 dias — Lei 12.527/2011, art. 15, parágrafo único).")
    _avisar_equipe(o, p, f'Recurso de {inst}ª instância', f'O cidadão recorreu da resposta. A autoridade de recurso decide até {prazo.strftime("%d/%m/%Y")}.')

def decidir_recurso(o, p, decisao, resposta, quem):
    if p['situacao'] != 'recurso':
        raise Erro('Não há recurso aberto.')
    r = db.um(o['banco'], "SELECT * FROM esic_recursos WHERE esic_id=%s AND decisao='' ORDER BY instancia DESC LIMIT 1", (p['id'],))
    if not r:
        raise Erro('Não há recurso aberto.')
    if decisao not in DECISOES_RECURSO or len((resposta or '').strip()) < 5:
        raise Erro('Escolha a decisão e escreva a fundamentação.')
    if quem.strip().lower() == (p['respondido_por'] or '').strip().lower():
        raise Erro('Quem respondeu o pedido não pode decidir o recurso: a decisão é da autoridade hierarquicamente superior (LAI, art. 15, parágrafo único).')
    anteriores = db.todos(o['banco'], 'SELECT autoridade FROM esic_recursos WHERE esic_id=%s AND decisao<>%s', (p['id'], ''))
    if any((a['autoridade'] or '').strip().lower() == quem.strip().lower() for a in anteriores):
        raise Erro('Quem decidiu a instância anterior não pode decidir esta.')
    if CPF.search(resposta):
        raise Erro('A decisão tem um número de CPF. Retire ou mascare antes de enviar (LGPD).')
    hoje = config.hoje()
    db.exe(o['banco'], 'UPDATE esic_recursos SET decisao=%s, resposta=%s, autoridade=%s, decidido=%s WHERE id=%s', (decisao, resposta.strip(), quem[:120], hoje, r['id']))
    novo = {'provido': 'concedido', 'parcial': 'parcial'}.get(decisao)
    db.exe(o['banco'], "UPDATE esic SET situacao='respondido'" + (', decisao=%s' if novo else '') + ' WHERE id=%s', ((novo, p['id']) if novo else (p['id'],)))
    _hist(o['banco'], p['id'], 'decisao_recurso', f"{DECISOES_RECURSO[decisao]} ({r['instancia']}ª instância). {resposta.strip()}", quem)
    p = pega(o['banco'], p['id'])
    corpo = f"O seu recurso de {r['instancia']}ª instância foi decidido.\n\nDecisão: {DECISOES_RECURSO[decisao]}\n\n{resposta.strip()}"
    pr = pode_recorrer(o['banco'], p)
    if pr:
        c = conf(o['banco'])
        corpo += f"\n\nAinda cabe recurso de {pr[0]}ª instância{(' a ' + c['autoridade_2']) if c['autoridade_2'] else ''}, pelo portal, até {pr[1].strftime('%d/%m/%Y')}."
    _avisar(o, p, 'Decisão do seu recurso', corpo)

def revelar_identidade(o, p, quem):
    _hist(o['banco'], p['id'], 'identidade', f'Identificação do solicitante consultada por {quem}.', quem, publico=False)

def avaliar(o, p, nota, resolveu):
    if p['situacao'] != 'respondido':
        raise Erro('A avaliação fica disponível depois da resposta.')
    if p['avaliacao']:
        raise Erro('Este atendimento já foi avaliado. Obrigado!')
    try:
        n = int(nota)
        assert 1 <= n <= 5
    except (TypeError, ValueError, AssertionError):
        raise Erro('Escolha uma nota de 1 a 5.')
    db.exe(o['banco'], 'UPDATE esic SET avaliacao=%s, avaliacao_resolveu=%s WHERE id=%s', (n, resolveu == 'sim' if resolveu in ('sim', 'nao') else None, p['id']))
    _hist(o['banco'], p['id'], 'avaliacao', f'Atendimento avaliado pelo cidadão: nota {n}.', 'cidadão', publico=False)

# ---------- encaminhamento entre órgãos (mesma instalação ou outra) ----------
def destinos_possiveis(o, p):
    from . import integracao as I
    srv = 'sic' if p['tipo'] == 'pedido' else 'ouv'
    return [x for x in I.parceiros(o) if srv in (x.get('servicos') or []) and I.par(o, x)]

def encaminhar_orgao(o, p, destino_id, quem, enviar_identificacao=True):
    """Remete o pedido/manifestação ao órgão parceiro competente (LAI, art. 11, § 1º, III; Lei 13.460, art. 13)."""
    from . import integracao as I
    _aberto(p)
    if p['situacao'] == 'recurso':
        raise Erro('Há recurso aberto: não dá para encaminhar.')
    destino = next((x for x in destinos_possiveis(o, p) if x['id'] == int(destino_id or 0)), None)
    if not destino:
        raise Erro('Escolha um órgão parceiro com o serviço ligado e integração ativa.')
    sem_id = p['anonimo'] or p['identidade_preservada'] or not enviar_identificacao
    dados = {'tipo': p['tipo'], 'categoria': p['categoria'], 'assunto': p['assunto'], 'texto': p['texto'], 'tipo_pessoa': p['tipo_pessoa'],
             'protocolo_origem': p['protocolo'], 'recebido_origem': p['recebido'].isoformat(), 'anonimo': p['anonimo'],
             'preservar': bool(p['identidade_preservada']), 'nome': '' if sem_id else p['nome'], 'email': '' if sem_id else p['email']}
    res = I.chamar(o, destino, 'POST', '/api/atendimento/encaminhamentos', dados, rotulo=destino['nome'])
    db.exe(o['banco'], """UPDATE esic SET situacao='encaminhado', decisao=CASE WHEN tipo='pedido' THEN 'encaminhado' ELSE decisao END, respondido=%s, respondido_por=%s,
                          encaminhado_para=%s, encaminhado_nome=%s, encaminhado_dominio=%s, protocolo_destino=%s WHERE id=%s""",
           (config.hoje(), quem[:120], destino['slug'], destino['nome'][:200], destino['dominio'], res.get('protocolo', '')[:40], p['id']))
    _hist(o['banco'], p['id'], 'encaminhamento', f"Encaminhado a {destino['nome']}, órgão responsável pelo assunto, sob o protocolo {res.get('protocolo')}. "
          f"Acompanhe em https://{destino['dominio']}/acesso?protocolo={res.get('protocolo')}"
          + (' (identificação preservada: não foi enviada; a resposta chegará por este órgão).' if sem_id else '.'), quem)
    p = pega(o['banco'], p['id'])
    _avisar(o, p, 'Seu atendimento foi encaminhado', f"O assunto do seu {_tipo_txt(p)} é de responsabilidade de {destino['nome']}. Por isso ele foi encaminhado para lá "
            f"(Lei 12.527/2011, art. 11, § 1º, III), sob o protocolo {res.get('protocolo')}.\n\n"
            + ('Você receberá um e-mail de lá com o código de acesso do novo protocolo.' if not sem_id else 'Como a sua identidade está preservada, ela não foi enviada; quando houver resposta, avisaremos você por aqui.'))
    return res

def atualizar_encaminhamento(o, p, quem='sistema'):
    """Consulta a situação no órgão de destino e traz a resposta quando houver (o cidadão é avisado por aqui se a
    identidade foi preservada, porque o destino não tem o e-mail dele)."""
    from . import integracao as I
    if p['situacao'] != 'encaminhado' or not p['protocolo_destino']:
        raise Erro('Este atendimento não foi encaminhado a outro órgão.')
    destino = I.parceiro(slug=p['encaminhado_para'])
    if not destino:
        raise Erro('O órgão de destino não está mais entre os parceiros.')
    res = I.chamar(o, destino, 'GET', f"/api/atendimento/encaminhamentos/{p['protocolo_destino']}", rotulo=destino['nome'])
    ja = db.um(o['banco'], "SELECT 1 FROM esic_historico WHERE esic_id=%s AND evento='retorno' AND texto LIKE %s", (p['id'], f"%[{res.get('respondido')}]%"))
    if res.get('resposta') and not ja:
        _hist(o['banco'], p['id'], 'retorno', f"Resposta de {destino['nome']} [{res.get('respondido')}]: {res['resposta']}", quem)
        if p['anonimo'] or p['identidade_preservada']:
            _avisar(o, p, 'Resposta do órgão responsável', f"{destino['nome']} respondeu ao seu {_tipo_txt(p)} (protocolo {p['protocolo_destino']}):\n\n{res['resposta']}")
    return res

def receber_encaminhamento(destino, origem, d):
    """Lado do órgão que recebe: registra como novo atendimento (canal 'orgao'). Idempotente pelo protocolo de origem."""
    ja = db.um(destino['banco'], 'SELECT * FROM esic WHERE origem_orgao=%s AND protocolo_origem=%s', (origem['slug'], (d.get('protocolo_origem') or '')[:40]))
    if ja:
        return ja
    if d.get('tipo') not in ('pedido', 'manifestacao') or not d.get('assunto') or not d.get('texto') or not d.get('protocolo_origem'):
        raise Erro('dados do encaminhamento incompletos')
    p, _ = registrar(destino, dict(d, preservar=bool(d.get('preservar')) or not d.get('nome')), canal='orgao', quem=origem['nome'], origem=origem)
    return p

def situacao_publica(destino, origem, protocolo):
    p = db.um(destino['banco'], 'SELECT * FROM esic WHERE protocolo=%s AND origem_orgao=%s', ((protocolo or '').upper()[:40], origem['slug']))
    if not p:
        return None
    return {'protocolo': p['protocolo'], 'situacao': p['situacao'], 'situacao_txt': SITUACOES.get(p['situacao'], p['situacao']),
            'prazo': p['prazo'].isoformat() if p['prazo'] else None, 'respondido': p['respondido'].isoformat() if p['respondido'] else None,
            'decisao': DECISOES.get(p['decisao'], ''), 'resposta': p['resposta'] if p['situacao'] == 'respondido' else ''}

# ---------- estatísticas e relatório ----------
def estatisticas(b, ano):
    """Relatório estatístico do e-SIC (LAI, art. 30, III) e números da Ouvidoria para o ano."""
    x = db.um(b, """SELECT count(*) FILTER (WHERE tipo='pedido') recebidos,
                           count(*) FILTER (WHERE tipo='pedido' AND situacao IN ('respondido','encaminhado','encerrado')) concluidos,
                           count(*) FILTER (WHERE tipo='pedido' AND decisao='concedido') concedidos,
                           count(*) FILTER (WHERE tipo='pedido' AND decisao='parcial') parciais,
                           count(*) FILTER (WHERE tipo='pedido' AND decisao='negado') negados,
                           count(*) FILTER (WHERE tipo='pedido' AND decisao='nao_possui') nao_possui,
                           count(*) FILTER (WHERE tipo='pedido' AND decisao='encaminhado') encaminhados,
                           count(*) FILTER (WHERE tipo='pedido' AND situacao='encerrado') encerrados,
                           count(*) FILTER (WHERE tipo='pedido' AND situacao IN ('recebido','analise','prorrogado','complementacao','recurso')) andamento,
                           count(*) FILTER (WHERE tipo='pedido' AND prorrogado_em IS NOT NULL) prorrogados,
                           count(*) FILTER (WHERE tipo='pedido' AND respondido IS NOT NULL AND respondido <= prazo) no_prazo,
                           round(avg(respondido - recebido) FILTER (WHERE tipo='pedido' AND respondido IS NOT NULL), 1) media_dias,
                           count(*) FILTER (WHERE tipo='pedido' AND tipo_pessoa='fisica') pf,
                           count(*) FILTER (WHERE tipo='pedido' AND tipo_pessoa='juridica') pj,
                           count(*) FILTER (WHERE tipo='pedido' AND tipo_pessoa='') pn
                    FROM esic WHERE extract(year FROM recebido)=%s""", (ano,))
    rec = db.um(b, """SELECT count(*) n, count(*) FILTER (WHERE r.decisao IN ('provido','parcial')) providos, count(*) FILTER (WHERE r.decisao='desprovido') desprovidos,
                             count(*) FILTER (WHERE r.decisao='') pendentes, count(*) FILTER (WHERE r.instancia=2) segunda
                      FROM esic_recursos r JOIN esic e ON e.id=r.esic_id WHERE extract(year FROM r.recebido)=%s""", (ano,))
    meses = db.todos(b, """SELECT extract(month FROM recebido)::int mes, count(*) FILTER (WHERE tipo='pedido') pedidos, count(*) FILTER (WHERE tipo='manifestacao') manifestacoes
                           FROM esic WHERE extract(year FROM recebido)=%s GROUP BY 1 ORDER BY 1""", (ano,))
    canais = db.todos(b, "SELECT canal, count(*) n FROM esic WHERE tipo='pedido' AND extract(year FROM recebido)=%s GROUP BY 1 ORDER BY 2 DESC", (ano,))
    return {'ano': ano, 'pedidos': x, 'recursos': rec, 'meses': meses, 'canais': [dict(c, nome=CANAIS.get(c['canal'], c['canal'])) for c in canais]}

def relatorio_ouvidoria(b, ano):
    """Números do relatório anual de gestão da Ouvidoria (Lei 13.460, art. 15, I e II). Contagens abaixo de 5 por
    serviço aparecem como "menos de 5" nas telas públicas (para ninguém ser identificado pelo assunto)."""
    tot = db.um(b, """SELECT count(*) n, count(*) FILTER (WHERE situacao IN ('respondido','encaminhado','encerrado')) concluidas,
                             count(*) FILTER (WHERE respondido IS NOT NULL AND respondido <= prazo) no_prazo,
                             round(avg(respondido - recebido) FILTER (WHERE respondido IS NOT NULL), 1) media_dias,
                             round(avg(avaliacao), 1) satisfacao, count(avaliacao) avaliacoes, count(*) FILTER (WHERE avaliacao_resolveu) resolveu
                      FROM esic WHERE tipo='manifestacao' AND extract(year FROM recebido)=%s""", (ano,))
    cats = db.todos(b, "SELECT categoria, count(*) n FROM esic WHERE tipo='manifestacao' AND extract(year FROM recebido)=%s GROUP BY 1 ORDER BY 2 DESC", (ano,))
    try:
        servs = db.todos(b, """SELECT s.nome, count(*) n FROM esic e JOIN servicos s ON s.id=e.servico_id
                               WHERE e.tipo='manifestacao' AND extract(year FROM e.recebido)=%s GROUP BY 1 ORDER BY 2 DESC LIMIT 15""", (ano,))
    except Exception:
        servs = []
    txt = db.um(b, 'SELECT * FROM ouvidoria_relatorios WHERE ano=%s', (ano,))
    return {'ano': ano, 'total': tot, 'categorias': cats, 'servicos': servs, 'texto': txt}

def anos(b):
    return [r['a'] for r in db.todos(b, 'SELECT DISTINCT extract(year FROM recebido)::int a FROM esic ORDER BY 1 DESC')] or [config.hoje().year]

# ---------- rotina diária (worker) ----------
def rotina(o, hoje=None):
    """Encerra atendimentos com complemento vencido e manda à equipe o resumo dos prazos que vencem em até 2 dias."""
    b = o['banco']
    hoje = hoje or config.hoje()
    n = 0
    for p in db.todos(b, "SELECT * FROM esic WHERE situacao='complementacao' AND complemento_ate < %s", (hoje,)):
        db.exe(b, "UPDATE esic SET situacao='encerrado', respondido=%s WHERE id=%s", (hoje, p['id']))
        _hist(b, p['id'], 'encerramento', 'Atendimento encerrado: o complemento pedido não foi enviado no prazo. Você pode registrar um novo pedido quando quiser.', 'sistema')
        _avisar(o, pega(b, p['id']), 'Atendimento encerrado', 'O complemento pedido não foi enviado no prazo e o atendimento foi encerrado. Se quiser, registre um novo pedido pelo portal.')
        n += 1
    c = conf(b)
    if c.get('email_equipe'):
        vence = db.todos(b, "SELECT protocolo, tipo, prazo FROM esic WHERE situacao IN ('recebido','analise','prorrogado') AND prazo <= %s ORDER BY prazo", (hoje + timedelta(days=2),))
        rec = db.todos(b, "SELECT e.protocolo, r.prazo FROM esic_recursos r JOIN esic e ON e.id=r.esic_id WHERE r.decisao='' AND r.prazo <= %s ORDER BY r.prazo", (hoje + timedelta(days=1),))
        if vence or rec:
            linhas = [f"{x['protocolo']} · {'pedido' if x['tipo'] == 'pedido' else 'ouvidoria'} · prazo {x['prazo'].strftime('%d/%m/%Y')}{' (VENCIDO)' if x['prazo'] < hoje else ''}" for x in vence]
            linhas += [f"{x['protocolo']} · recurso · decidir até {x['prazo'].strftime('%d/%m/%Y')}" for x in rec]
            for em in [x.strip() for x in c['email_equipe'].replace(';', ',').split(',') if x.strip()]:
                N.enfileirar(b, em, f'Prazos do e-SIC e da Ouvidoria — {hoje.strftime("%d/%m/%Y")}',
                             'Atendimentos com prazo vencendo em até 2 dias ou já vencidos:\n\n' + '\n'.join(linhas) + f"\n\nPainel: https://{o['dominio']}/admin/atendimento", 'resumo')
    return n
