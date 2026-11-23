"""e-SIC e Ouvidoria (23/11/2026): regras, prazos, e-mails e números. Usado pelo portal (portal_atendimento), pelo painel
(admin_atendimento), pela integração entre órgãos (encaminhamento) e pelo worker (fila de e-mails e rotina diária).

Regras (LAI = Lei 12.527/2011; CDU = Lei 13.460/2017):
- Pedido de informação: 20 dias, uma prorrogação de 10 com justificativa (LAI art. 11, §§ 1º e 2º).
  Manifestação da Ouvidoria: 30 dias, uma prorrogação de 30 (CDU art. 16).
- Identificação: nome e e-mail, sem documento nem motivo (LAI art. 10, §§ 1º e 3º; CDU art. 10). Anônimo só para denúncia
  na Ouvidoria (e então não há e-mail: o cidadão acompanha pelo protocolo e código).
- Complemento: a equipe pode pedir UMA vez; o cidadão tem 20 dias; o prazo fica suspenso e volta a correr com o que faltava
  (CDU art. 18, parágrafo único). Sem complemento no prazo, o atendimento é encerrado.
- Resposta de pedido: resultado (concedido, parcial, negado, inexistente); negativa ou acesso parcial exige o fundamento legal
  (LAI art. 11, § 1º, II e § 4º; art. 24). Nenhuma resposta leva CPF completo (LGPD).
- Recurso (só pedido de informação): 10 dias depois da resposta; decisão em 5 dias pela autoridade superior (LAI art. 15);
  2ª instância nas mesmas condições (norma local). Quem respondeu não decide o recurso; quem decidiu a 1ª não decide a 2ª.
- Código de acesso: gerado no registro, mostrado uma vez e enviado por e-mail; aqui fica só o hash. Sem código, o
  protocolo mostra só a situação.
- Encaminhamento ao órgão que tem a informação (LAI art. 11, § 1º, III): vai sem nome nem e-mail; lá nasce um protocolo
  novo, cujo código o cidadão recebe daqui.
- E-mails: ao cidadão em cada passo; à equipe sem dado pessoal; saem pelo SMTP próprio do órgão, senão pelo e-mail da
  plataforma (só na instalação "tudo"), senão esperam na fila."""
import hashlib, hmac, re, secrets
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from . import config, db

PRAZO = {'pedido': (20, 10), 'manifestacao': (30, 30)}
COMPLEMENTO_DIAS = 20
RECURSO_DIAS = 10
DECISAO_DIAS = 5
ABERTAS = ('recebido', 'analise', 'complemento', 'recurso')
SITUACOES = {'recebido': 'Recebido', 'analise': 'Em análise', 'complemento': 'Aguardando complemento do cidadão', 'respondido': 'Respondido',
             'recurso': 'Em recurso', 'encaminhado': 'Encaminhado a outro órgão', 'encerrado': 'Encerrado'}
RESULTADOS = {'concedido': 'Acesso concedido', 'parcial': 'Acesso parcialmente concedido', 'negado': 'Acesso negado', 'inexistente': 'Informação inexistente'}
DECISOES = {'provido': 'Recurso provido', 'parcial': 'Recurso parcialmente provido', 'improvido': 'Recurso não provido'}
CATEGORIAS = ['Reclamação', 'Sugestão', 'Elogio', 'Denúncia', 'Solicitação']
PERFIS_SOLICITANTE = {'pf': 'Pessoa física', 'pj': 'Pessoa jurídica', '': 'Não informado'}
CANAIS = {'internet': 'Internet', 'presencial': 'Presencial', 'encaminhado': 'Encaminhado por outro órgão'}
GRAUS = {'reservado': ('Reservado', 5), 'secreto': ('Secreto', 15), 'ultrassecreto': ('Ultrassecreto', 25)}  # LAI art. 24, § 1º (anos)
CPF = re.compile(r'(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
_ALFA = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # sem 0/O, 1/I


def hoje():
    return config.hoje()


# ---------- configuração do atendimento (por órgão) ----------
def conf(b):
    c = db.cfg(b, 'atendimento', {}) or {}
    for k in ('unidade', 'unidade_ouvidoria', 'autoridade1_cargo', 'autoridade2_cargo', 'norma_nome', 'norma_url', 'email_equipe', 'sem_classificadas'):
        c.setdefault(k, '')
    for k in ('autoridade1_id', 'autoridade2_id'):
        c.setdefault(k, None)
    return c


def tem_cpf(*textos):
    return any(CPF.search(t or '') for t in textos)


# ---------- protocolo e código ----------
def _hash(protocolo, codigo):
    return hashlib.sha256(f"{protocolo}:{codigo.replace('-', '').strip().upper()}".encode()).hexdigest()


def novo_codigo():
    c = ''.join(secrets.choice(_ALFA) for _ in range(12))
    return f'{c[:4]}-{c[4:8]}-{c[8:]}'


def confere(p, codigo):
    return bool(p and p['codigo_hash'] and codigo and hmac.compare_digest(p['codigo_hash'], _hash(p['protocolo'], codigo)))


def por_protocolo(b, protocolo):
    return db.um(b, 'SELECT * FROM esic WHERE protocolo=%s', ((protocolo or '').strip().upper()[:40],))


def hist(b, eid, quem, acao, texto='', interno=False):
    db.exe(b, 'INSERT INTO esic_historico (esic_id, quem, acao, texto, interno) VALUES (%s,%s,%s,%s,%s)', (eid, quem[:120], acao[:200], texto[:5000], interno))


def historico(b, eid, internos=False):
    return db.todos(b, 'SELECT * FROM esic_historico WHERE esic_id=%s' + ('' if internos else ' AND NOT interno') + ' ORDER BY id', (eid,))


def recursos(b, eid):
    return db.todos(b, 'SELECT * FROM esic_recursos WHERE esic_id=%s ORDER BY instancia', (eid,))


def rotulo(p):
    return 'pedido de informação' if p['tipo'] == 'pedido' else 'manifestação'


def _assinatura(o):
    return f"\n\n—\n{o['nome']}\nhttps://{o['dominio']}\nEste e-mail foi enviado automaticamente; não responda a ele."


def _link(o, p):
    return f"https://{o['dominio']}/acesso?protocolo={p['protocolo']}"


def registrar(o, d, canal='internet', quem='cidadão', origem=None):
    """Registra um pedido ou manifestação. d: tipo, categoria, assunto, texto, nome, email, anonimo, perfil_solicitante, servico_id.
    Devolve (registro, código, erro)."""
    b = o['banco']
    tipo = 'pedido' if d.get('tipo') == 'pedido' else 'manifestacao'
    categoria = (d.get('categoria') or '') if tipo == 'manifestacao' else ''
    if categoria and categoria not in CATEGORIAS:
        categoria = ''
    anonimo = bool(d.get('anonimo')) and not origem
    nome, email = (d.get('nome') or '').strip()[:120], (d.get('email') or '').strip()[:120]
    if not (d.get('assunto') and d.get('texto')):
        return None, None, 'Preencha o assunto e o texto.'
    if anonimo:
        if tipo != 'manifestacao' or categoria != 'Denúncia':
            return None, None, 'Só a denúncia pode ser anônima (Lei 13.460/2017). Para os demais, informe nome e e-mail.'
        nome, email = '', ''
    elif origem:
        nome, email = '', ''  # encaminhado: a identidade fica no órgão de origem
    elif canal == 'presencial':
        if not nome:
            return None, None, 'Informe o nome de quem fez o pedido (o e-mail é opcional no atendimento presencial).'
        if email and not EMAIL.match(email):
            return None, None, 'E-mail inválido.'
    elif not (nome and EMAIL.match(email)):
        return None, None, 'Preencha nome e um e-mail válido para a resposta.'
    prefixo = 'SIC' if tipo == 'pedido' else 'OUV'
    for _ in range(5):
        prot = f"{prefixo}-{hoje().year}-{secrets.token_hex(3).upper()}"
        if not por_protocolo(b, prot):
            break
    codigo = novo_codigo()
    perfil = d.get('perfil_solicitante') if d.get('perfil_solicitante') in ('pf', 'pj') else ''
    prazo = hoje() + timedelta(days=PRAZO[tipo][0])
    p = db.um(b, """INSERT INTO esic (protocolo, tipo, categoria, assunto, texto, nome, email, servico_id, codigo_hash, anonimo, perfil_solicitante, canal,
                    origem_orgao, origem_protocolo, recebido, prazo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
              (prot, tipo, categoria, d['assunto'][:200], d['texto'][:5000], nome, email, d.get('servico_id'), _hash(prot, codigo), anonimo, perfil, canal,
               (origem or {}).get('slug', ''), (origem or {}).get('protocolo', '')[:40], hoje(), prazo))
    hist(b, p['id'], quem, 'Registrado' + (f" (encaminhado por {origem['nome']}, protocolo {origem['protocolo']})" if origem else ' (atendimento presencial)' if canal == 'presencial' else ''))
    if email:
        enfileirar(b, email, f"{o['nome']}: protocolo {prot}",
                   f"Recebemos o seu {rotulo(p)}: “{p['assunto']}”.\n\nProtocolo: {prot}\nCódigo de acesso: {codigo}\n"
                   f"Prazo de resposta: {prazo:%d/%m/%Y}.\n\nGuarde o protocolo e o código. Para acompanhar e ver a resposta: {_link(o, p)}" + _assinatura(o), 'cidadao', p['id'])
    avisar_equipe(o, p, 'novo ' + rotulo(p) + (' (encaminhado por outro órgão)' if origem else ''))
    return p, codigo, None


def avisar_equipe(o, p, oque):
    """E-mail para a equipe, SEM dado pessoal: só o protocolo, o tipo, o prazo e o caminho no painel."""
    para = conf(o['banco'])['email_equipe']
    if para and EMAIL.match(para):
        enfileirar(o['banco'], para, f"[{o['nome']}] {oque}: {p['protocolo']}",
                   f"{oque[:1].upper() + oque[1:]}: {p['protocolo']}.\nPrazo: {p['prazo']:%d/%m/%Y}.\n\nVeja no painel: https://{o['dominio']}/admin/atendimento/{p['id']}" + _assinatura(o),
                   'equipe', p['id'])


def _cidadao(o, p, assunto, texto):
    if p['email']:
        enfileirar(o['banco'], p['email'], f"{o['nome']}: {assunto} ({p['protocolo']})", texto + f"\n\nProtocolo {p['protocolo']}: {_link(o, p)}" + _assinatura(o), 'cidadao', p['id'])


def _recarregar(b, p):
    return db.um(b, 'SELECT * FROM esic WHERE id=%s', (p['id'],))


# ---------- ações da equipe (cada uma devolve uma mensagem de erro ou None) ----------
def prorrogar(o, p, u, justificativa):
    b = o['banco']
    if p['situacao'] not in ('recebido', 'analise'):
        return 'Só é possível prorrogar um atendimento em aberto.'
    if p['prorrogado']:
        return 'O prazo já foi prorrogado uma vez (a lei permite só uma prorrogação).'
    if not justificativa:
        return 'Escreva a justificativa da prorrogação (ela vai para o cidadão).'
    if tem_cpf(justificativa):
        return 'A justificativa tem um CPF: retire o dado pessoal.'
    extra = PRAZO[p['tipo']][1]
    novo = p['prazo'] + timedelta(days=extra)
    db.exe(b, "UPDATE esic SET prorrogado=TRUE, prorrogado_em=%s, justificativa=%s, prazo=%s, situacao='analise' WHERE id=%s", (hoje(), justificativa[:2000], novo, p['id']))
    hist(b, p['id'], u['nome'], f'Prazo prorrogado por {extra} dias (novo prazo: {novo:%d/%m/%Y})', justificativa)
    _cidadao(o, p, 'prazo prorrogado', f"O prazo do seu {rotulo(p)} foi prorrogado por {extra} dias, até {novo:%d/%m/%Y}.\nJustificativa: {justificativa}")
    return None


def pedir_complemento(o, p, u, texto):
    b = o['banco']
    if p['situacao'] not in ('recebido', 'analise'):
        return 'Só é possível pedir complemento de um atendimento em aberto.'
    if p['complemento_pedido_em']:
        return 'O complemento já foi pedido uma vez (só é permitido um pedido).'
    if not texto:
        return 'Escreva o que o cidadão precisa complementar.'
    if tem_cpf(texto):
        return 'O texto tem um CPF: retire o dado pessoal.'
    if not p['email'] and not p['anonimo']:
        return 'Sem e-mail do solicitante: peça o complemento pelo canal em que ele foi atendido e registre como nota.'
    restante = max((p['prazo'] - hoje()).days, 1)
    limite = hoje() + timedelta(days=COMPLEMENTO_DIAS)
    db.exe(b, "UPDATE esic SET situacao='complemento', complemento_pedido=%s, complemento_pedido_em=%s, complemento_prazo=%s, prazo_restante=%s WHERE id=%s",
           (texto[:3000], hoje(), limite, restante, p['id']))
    hist(b, p['id'], u['nome'], f'Pedido de complemento (o cidadão tem até {limite:%d/%m/%Y}; o prazo de resposta fica suspenso)', texto)
    _cidadao(o, p, 'precisamos de um complemento', f"Para responder ao seu {rotulo(p)}, precisamos que você complemente:\n\n{texto}\n\n"
             f"Envie o complemento até {limite:%d/%m/%Y} pela página do protocolo (com o seu código de acesso). Sem o complemento, o atendimento será encerrado.")
    return None


def responder(o, p, u, resposta, resultado='', fundamento=''):
    b = o['banco']
    if p['situacao'] not in ('recebido', 'analise'):
        return 'Este atendimento não está aberto para resposta.'
    if not resposta:
        return 'Escreva a resposta.'
    if tem_cpf(resposta, fundamento):
        return 'A resposta tem um CPF completo: retire ou mascare o dado pessoal (LGPD).'
    if p['tipo'] == 'pedido':
        if resultado not in RESULTADOS:
            return 'Escolha o resultado do pedido (concedido, parcial, negado ou inexistente).'
        if resultado in ('negado', 'parcial') and len(fundamento) < 10:
            return 'Negativa ou acesso parcial exige o fundamento legal (LAI, art. 11, § 1º, II, e art. 24).'
    else:
        resultado = ''
    db.exe(b, """UPDATE esic SET situacao='respondido', resposta=%s, resultado=%s, fundamento=%s, respondido=%s, respondido_por=%s, respondido_por_id=%s, setor=COALESCE(NULLIF(%s,''), setor)
                 WHERE id=%s""", (resposta[:20000], resultado, fundamento[:3000], hoje(), u['nome'], u['id'], (u.get('setor') or ''), p['id']))
    hist(b, p['id'], u['nome'], 'Respondido' + (f' — {RESULTADOS[resultado]}' if resultado else ''))
    t = f"O seu {rotulo(p)} foi respondido" + (f" ({RESULTADOS[resultado]})" if resultado else '') + '. Veja a resposta na página do protocolo, com o seu código de acesso.'
    if p['tipo'] == 'pedido':
        t += f"\n\nSe não concordar, você pode recorrer em até {RECURSO_DIAS} dias, na mesma página (LAI, art. 15)."
    else:
        t += '\n\nNa mesma página você pode avaliar o atendimento.'
    _cidadao(o, p, 'resposta', t)
    return None


def nota(o, p, u, texto):
    if not texto:
        return 'Escreva a nota.'
    hist(o['banco'], p['id'], u['nome'], 'Nota interna', texto[:5000], interno=True)
    return None


def setor(o, p, u, s):
    db.exe(o['banco'], "UPDATE esic SET setor=%s, situacao=CASE WHEN situacao='recebido' THEN 'analise' ELSE situacao END WHERE id=%s", (s[:120], p['id']))
    hist(o['banco'], p['id'], u['nome'], f'Enviado ao setor: {s}' if s else 'Setor retirado', interno=True)
    if p['situacao'] == 'recebido':
        hist(o['banco'], p['id'], 'sistema', 'Em análise')
    return None


def pode_decidir(o, p, u, rec):
    """(True, '') ou (False, motivo). Quem respondeu não decide; quem decidiu a 1ª não decide a 2ª; autoridade configurada."""
    from .catalogo import PODE
    if u['perfil'] not in PODE['recurso_decidir']:
        return False, 'Só a autoridade de recurso (ou o administrador) decide recursos.'
    if p['respondido_por_id'] and p['respondido_por_id'] == u['id']:
        return False, 'Quem respondeu o pedido não pode decidir o recurso.'
    if rec['instancia'] == 2:
        r1 = next((r for r in recursos(o['banco'], p['id']) if r['instancia'] == 1), None)
        if r1 and r1['decidido_por_id'] == u['id']:
            return False, 'Quem decidiu a 1ª instância não pode decidir a 2ª.'
    aut = conf(o['banco']).get(f"autoridade{rec['instancia']}_id")
    if aut and int(aut) != u['id']:
        return False, f"A autoridade da {rec['instancia']}ª instância configurada é outra pessoa."
    return True, ''


def recurso_pendente(b, p):
    return next((r for r in recursos(b, p['id']) if not r['resultado']), None)


def decidir(o, p, u, decisao, resultado):
    b = o['banco']
    rec = recurso_pendente(b, p)
    if p['situacao'] != 'recurso' or not rec:
        return 'Não há recurso pendente.'
    ok, motivo = pode_decidir(o, p, u, rec)
    if not ok:
        return motivo
    if resultado not in DECISOES or not decisao:
        return 'Escreva a decisão e escolha o resultado.'
    if tem_cpf(decisao):
        return 'A decisão tem um CPF completo: retire o dado pessoal.'
    db.exe(b, 'UPDATE esic_recursos SET decisao=%s, resultado=%s, decidido_por=%s, decidido_por_id=%s, decidido_em=%s WHERE id=%s',
           (decisao[:20000], resultado, u['nome'], u['id'], hoje(), rec['id']))
    db.exe(b, "UPDATE esic SET situacao='respondido' WHERE id=%s", (p['id'],))
    hist(b, p['id'], u['nome'], f"Recurso de {rec['instancia']}ª instância decidido — {DECISOES[resultado]}")
    t = f"O recurso de {rec['instancia']}ª instância foi decidido: {DECISOES[resultado]}. Veja a decisão na página do protocolo."
    if rec['instancia'] == 1 and resultado != 'provido':
        t += f"\n\nSe não concordar, você pode recorrer à 2ª instância em até {RECURSO_DIAS} dias."
    _cidadao(o, p, 'decisão do recurso', t)
    return None


def encaminhar(o, p, u, destino):
    """Manda o pedido ao órgão parceiro que tem a informação, SEM a identidade. Lá nasce um protocolo novo."""
    from . import integracao as IG
    b = o['banco']
    if p['situacao'] not in ('recebido', 'analise'):
        return 'Só é possível encaminhar um atendimento em aberto.'
    if p['canal'] == 'encaminhado':
        return 'Este pedido já veio encaminhado por outro órgão: responda ou devolva com uma resposta.'
    try:
        r = IG.chamar(o, destino, 'POST', '/api/integracao/esic', {'tipo': p['tipo'], 'categoria': p['categoria'], 'assunto': p['assunto'], 'texto': p['texto'],
                                                                  'protocolo': p['protocolo']}, f"encaminhamento {p['protocolo']}")
    except ValueError as e:
        return f'Não foi encaminhado: {e}'
    if not (r.get('protocolo') and r.get('codigo')):
        return 'Não foi encaminhado: resposta inesperada do órgão parceiro.'
    db.exe(b, """UPDATE esic SET situacao='encaminhado', encaminhado_orgao=%s, encaminhado_slug=%s, encaminhado_dominio=%s, encaminhado_protocolo=%s, encaminhado_codigo=%s,
                 encaminhado_situacao=%s, encaminhado_consultado_em=now(), respondido=%s, respondido_por=%s, respondido_por_id=%s WHERE id=%s""",
           (destino['nome'], destino['slug'], destino['dominio'], r['protocolo'], r['codigo'], r.get('situacao', 'recebido'), hoje(), u['nome'], u['id'], p['id']))
    hist(b, p['id'], u['nome'], f"Encaminhado a {destino['nome']} (novo protocolo {r['protocolo']}), que tem a informação (LAI, art. 11, § 1º, III)")
    _cidadao(o, p, 'encaminhado a outro órgão',
             f"O seu {rotulo(p)} trata de informação de {destino['nome']} e foi encaminhado para lá, sem o seu nome e e-mail.\n\n"
             f"Novo protocolo: {r['protocolo']}\nCódigo de acesso: {r['codigo']}\nAcompanhe em: https://{destino['dominio']}/acesso?protocolo={r['protocolo']}")
    return None


def consultar_encaminhado(o, p):
    from . import integracao as IG
    destino = IG.orgao(slug=p['encaminhado_slug'])
    if not destino:
        return 'O órgão de destino não é mais conhecido por esta instalação.'
    try:
        r = IG.chamar(o, destino, 'GET', f"/api/integracao/esic/{p['encaminhado_protocolo']}", None, f"situação {p['encaminhado_protocolo']}")
    except ValueError as e:
        return str(e)
    db.exe(o['banco'], 'UPDATE esic SET encaminhado_situacao=%s, encaminhado_consultado_em=now() WHERE id=%s', (r.get('situacao', '')[:40], p['id']))
    return None


# ---------- ações do cidadão (com protocolo + código) ----------
def complementar(o, p, texto):
    b = o['banco']
    if p['situacao'] != 'complemento':
        return 'Este protocolo não está aguardando complemento.'
    if p['complemento_prazo'] < hoje():
        return 'O prazo para o complemento terminou.'
    if not texto:
        return 'Escreva o complemento.'
    novo = hoje() + timedelta(days=p['prazo_restante'] or 1)
    db.exe(b, "UPDATE esic SET situacao='analise', complemento_resposta=%s, complemento_respondido_em=%s, prazo=%s WHERE id=%s", (texto[:5000], hoje(), novo, p['id']))
    hist(b, p['id'], 'cidadão', f'Complemento enviado (o prazo volta a correr: resposta até {novo:%d/%m/%Y})')
    avisar_equipe(o, _recarregar(b, p), 'complemento recebido')
    return None


def pode_recorrer(b, p):
    """(instância, prazo final) ou (None, motivo)."""
    if p['tipo'] != 'pedido':
        return None, 'Recurso é para pedido de informação (na Ouvidoria, avalie o atendimento ou faça nova manifestação).'
    if p['situacao'] != 'respondido':
        return None, 'Só cabe recurso depois da resposta.'
    rs = recursos(b, p['id'])
    if not rs:
        lim = p['respondido'] + timedelta(days=RECURSO_DIAS)
        return (1, lim) if hoje() <= lim else (None, f'O prazo de recurso terminou em {lim:%d/%m/%Y}.')
    if len(rs) == 1 and rs[0]['resultado'] in ('parcial', 'improvido'):
        lim = rs[0]['decidido_em'] + timedelta(days=RECURSO_DIAS)
        return (2, lim) if hoje() <= lim else (None, f'O prazo de recurso à 2ª instância terminou em {lim:%d/%m/%Y}.')
    return None, 'Não cabe novo recurso.'


def recorrer(o, p, texto):
    b = o['banco']
    inst, lim = pode_recorrer(b, p)
    if not inst:
        return lim
    if not texto:
        return 'Escreva as razões do recurso.'
    prazo = hoje() + timedelta(days=DECISAO_DIAS)
    db.exe(b, 'INSERT INTO esic_recursos (esic_id, instancia, texto, criado_em, prazo) VALUES (%s,%s,%s,%s,%s)', (p['id'], inst, texto[:5000], hoje(), prazo))
    db.exe(b, "UPDATE esic SET situacao='recurso' WHERE id=%s", (p['id'],))
    hist(b, p['id'], 'cidadão', f'Recurso de {inst}ª instância apresentado (decisão até {prazo:%d/%m/%Y})')
    a = conf(b).get(f'autoridade{inst}_cargo')
    _cidadao(o, p, 'recurso recebido', f"Recebemos o seu recurso de {inst}ª instância. Ele será decidido até {prazo:%d/%m/%Y}" + (f" por: {a}" if a else '') + '.')
    avisar_equipe(o, dict(_recarregar(b, p), prazo=prazo), f'recurso de {inst}ª instância')
    return None


def avaliar(o, p, nota_, resolveu, comentario=''):
    if p['situacao'] not in ('respondido', 'encerrado'):
        return 'A avaliação fica disponível depois da resposta.'
    if p['avaliado_em']:
        return 'Este atendimento já foi avaliado.'
    try:
        n = int(nota_)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= 5 or resolveu not in ('sim', 'nao'):
        return 'Escolha uma nota de 1 a 5 e diga se a resposta resolveu.'
    db.exe(o['banco'], 'UPDATE esic SET avaliacao=%s, resolveu=%s, avaliacao_comentario=%s, avaliado_em=now() WHERE id=%s',
           (n, resolveu == 'sim', (comentario or '')[:1000], p['id']))
    hist(o['banco'], p['id'], 'cidadão', 'Atendimento avaliado')
    return None


# ---------- rotina diária ----------
def encerrar_complementos(o):
    b = o['banco']; n = 0
    for p in db.todos(b, "SELECT * FROM esic WHERE situacao='complemento' AND complemento_prazo < %s", (hoje(),)):
        db.exe(b, "UPDATE esic SET situacao='encerrado', encerrado_motivo='complemento não enviado no prazo', respondido=%s WHERE id=%s", (hoje(), p['id']))
        hist(b, p['id'], 'sistema', 'Encerrado: o complemento não foi enviado no prazo')
        _cidadao(o, p, 'atendimento encerrado', f"O seu {rotulo(p)} foi encerrado porque o complemento pedido não foi enviado até {p['complemento_prazo']:%d/%m/%Y}. Você pode fazer um novo pedido.")
        n += 1
    return n


def vencendo(b, dias=2):
    """Prazos que vencem em até `dias` dias (ou vencidos): atendimentos abertos e recursos pendentes."""
    lim = hoje() + timedelta(days=dias)
    a = db.todos(b, "SELECT protocolo, tipo, prazo, situacao FROM esic WHERE situacao IN ('recebido','analise') AND prazo <= %s ORDER BY prazo", (lim,))
    r = db.todos(b, """SELECT e.protocolo, e.tipo, r.prazo, 'recurso' situacao, r.instancia FROM esic_recursos r JOIN esic e ON e.id=r.esic_id
                       WHERE r.resultado='' AND e.situacao='recurso' AND r.prazo <= %s ORDER BY r.prazo""", (lim,))
    return a + r


def resumo_equipe(o):
    b = o['banco']; para = conf(b)['email_equipe']
    itens = vencendo(b)
    if not (itens and para and EMAIL.match(para)):
        return 0
    linhas = [f"- {x['protocolo']} ({'recurso ' + str(x['instancia']) + 'ª inst.' if x['situacao'] == 'recurso' else 'pedido' if x['tipo'] == 'pedido' else 'ouvidoria'}): "
              f"{'VENCIDO em' if x['prazo'] < hoje() else 'vence em'} {x['prazo']:%d/%m/%Y}" for x in itens]
    enfileirar(b, para, f"[{o['nome']}] {len(itens)} prazo(s) do e-SIC/Ouvidoria vencendo",
               'Prazos que vencem nos próximos 2 dias (ou já vencidos):\n\n' + '\n'.join(linhas) + f"\n\nPainel: https://{o['dominio']}/admin/atendimento" + _assinatura(o), 'equipe')
    return len(itens)


def rotina_diaria(o):
    b = o['banco']
    if (db.cfg(b, 'atendimento_rotina') or '') == hoje().isoformat():
        return None
    db.set_cfg(b, 'atendimento_rotina', hoje().isoformat())
    return {'encerrados': encerrar_complementos(o), 'resumo': resumo_equipe(o)}


# ---------- e-mail: fila, SMTP próprio do órgão ou da plataforma ----------
def enfileirar(b, para, assunto, texto, tipo='cidadao', eid=None):
    db.exe(b, 'INSERT INTO email_fila (para, assunto, texto, tipo, esic_id) VALUES (%s,%s,%s,%s,%s)', (para[:200], assunto[:250], texto, tipo, eid))


def smtp_atual(b):
    r = db.um(b, 'SELECT * FROM atendimento_smtp WHERE id=1')
    if not r:
        return None
    d = {k: r[k] for k in ('servidor', 'porta', 'seguranca', 'usuario', 'remetente', 'remetente_nome', 'atualizado_em', 'atualizado_por', 'teste_em', 'teste_resultado')}
    d['tem_senha'] = bool(r['senha_cifrada'])
    return d


def smtp_salvar(b, f, quem):
    from . import email_saida as EM, credenciais
    d, erros = EM.validar(f)
    if erros:
        return ' '.join(erros)
    atual = db.um(b, 'SELECT senha_cifrada FROM atendimento_smtp WHERE id=1')
    try:
        cif = credenciais._fernet().encrypt(d['senha'].encode()).decode() if d['senha'] else (atual or {}).get('senha_cifrada', '')
    except credenciais.SemChave:
        return 'Não gravado: falta a CHAVE_CREDENCIAIS da instalação (ela cifra a senha do SMTP). Peça à equipe técnica.'
    db.exe(b, """INSERT INTO atendimento_smtp (id, servidor, porta, seguranca, usuario, senha_cifrada, remetente, remetente_nome, atualizado_em, atualizado_por)
                 VALUES (1,%s,%s,%s,%s,%s,%s,%s,now(),%s) ON CONFLICT (id) DO UPDATE SET servidor=EXCLUDED.servidor, porta=EXCLUDED.porta, seguranca=EXCLUDED.seguranca,
                 usuario=EXCLUDED.usuario, senha_cifrada=EXCLUDED.senha_cifrada, remetente=EXCLUDED.remetente, remetente_nome=EXCLUDED.remetente_nome,
                 atualizado_em=now(), atualizado_por=EXCLUDED.atualizado_por, teste_em=NULL, teste_resultado=''""",
           (d['servidor'], d['porta'], d['seguranca'], d['usuario'], cif, d['remetente'], d['remetente_nome'], quem))
    return None


def smtp_remover(b):
    db.exe(b, 'DELETE FROM atendimento_smtp WHERE id=1')


def _via(b):
    """Função de envio (para, assunto, texto) e o nome do caminho, ou (None, motivo)."""
    from . import email_saida as EM
    r = db.um(b, 'SELECT * FROM atendimento_smtp WHERE id=1')
    if r:
        def proprio(para, assunto, texto):
            msg = EmailMessage()
            msg['From'] = formataddr((r['remetente_nome'] or r['remetente'], r['remetente']))
            msg['To'] = para; msg['Subject'] = assunto
            msg['Message-ID'] = make_msgid(domain=r['remetente'].split('@')[1])
            msg.set_content(texto)
            try:
                EM._smtp_enviar(r, EM._senha(r), msg)
            except EM.NaoConfigurado as e:
                raise RuntimeError(str(e)) from None
            except Exception as e:  # mensagem sem segredos: só o tipo do erro
                raise RuntimeError(f'falha no SMTP do órgão ({type(e).__name__})') from None
        return proprio, 'SMTP do órgão'
    if config.PAPEL != 'no' and db.LOCAL == db.PLATAFORMA and db.um(db.PLATAFORMA, 'SELECT 1 x FROM email_saida WHERE id=1'):
        return (lambda para, assunto, texto: EM.enviar(para, assunto, texto)), 'e-mail da plataforma'
    return None, 'aguardando: configure o SMTP do órgão em e-SIC e Ouvidoria → Configuração'


def enviar_fila(o, limite=30):
    b = o['banco']
    pend = db.todos(b, """SELECT * FROM email_fila WHERE enviado_em IS NULL AND tentativas < 6
                          AND (ultima_tentativa IS NULL OR ultima_tentativa < now() - (interval '5 minutes' * tentativas)) ORDER BY id LIMIT %s""", (limite,))
    if not pend:
        return 0
    via, nome = _via(b)
    if not via:
        db.exe(b, 'UPDATE email_fila SET erro=%s WHERE enviado_em IS NULL AND erro<>%s', (nome, nome))
        return 0
    n = 0
    for m in pend:
        try:
            via(m['para'], m['assunto'], m['texto'])
            db.exe(b, "UPDATE email_fila SET enviado_em=now(), texto='', erro=%s WHERE id=%s", (f'enviado ({nome})', m['id']))
            n += 1
        except Exception as e:
            db.exe(b, 'UPDATE email_fila SET tentativas=tentativas+1, ultima_tentativa=now(), erro=%s WHERE id=%s', (str(e)[:300], m['id']))
    return n


def smtp_testar(o, para, quem):
    b = o['banco']
    if not EMAIL.match(para or ''):
        return 'Informe um e-mail válido para o teste.'
    via, nome = _via(b)
    if not via:
        res = 'falhou: ' + nome
    else:
        try:
            via(para, f"Teste do e-mail do e-SIC/Ouvidoria — {o['nome']}", 'Se chegou, o e-mail do atendimento está funcionando.' + _assinatura(o))
            res = f'enviado para {para} ({nome})'
        except Exception as e:
            res = f'falhou: {e}'
    db.exe(b, 'UPDATE atendimento_smtp SET teste_em=now(), teste_resultado=%s WHERE id=1', (res[:300],))
    return res


# ---------- números públicos (sem dado pessoal) ----------
def anos(b):
    return [r['a'] for r in db.todos(b, 'SELECT DISTINCT EXTRACT(YEAR FROM recebido)::int a FROM esic ORDER BY 1 DESC')] or [hoje().year]


def estatisticas(b, ano):
    """Relatório estatístico do e-SIC (LAI art. 30, III): pedidos recebidos, atendidos, indeferidos, recursos e perfil."""
    w = "tipo='pedido' AND EXTRACT(YEAR FROM recebido)=%s"
    s = db.um(b, f"""SELECT count(*) recebidos,
        count(*) FILTER (WHERE situacao IN ('respondido','recurso')) respondidos,
        count(*) FILTER (WHERE situacao IN ('respondido','recurso') AND respondido <= prazo) no_prazo,
        count(*) FILTER (WHERE situacao IN ('respondido','recurso') AND respondido > prazo) fora_prazo,
        count(*) FILTER (WHERE situacao IN ('recebido','analise','complemento')) em_aberto,
        count(*) FILTER (WHERE situacao='encaminhado') encaminhados,
        count(*) FILTER (WHERE situacao='encerrado') encerrados,
        count(*) FILTER (WHERE prorrogado) prorrogados,
        count(*) FILTER (WHERE resultado='concedido') concedidos, count(*) FILTER (WHERE resultado='parcial') parciais,
        count(*) FILTER (WHERE resultado='negado') negados, count(*) FILTER (WHERE resultado='inexistente') inexistentes,
        round(avg(respondido - recebido) FILTER (WHERE situacao IN ('respondido','recurso')), 1) dias_medios,
        count(*) FILTER (WHERE perfil_solicitante='pf') pf, count(*) FILTER (WHERE perfil_solicitante='pj') pj, count(*) FILTER (WHERE perfil_solicitante='') perfil_nao_informado,
        count(*) FILTER (WHERE canal='internet') internet, count(*) FILTER (WHERE canal='presencial') presencial, count(*) FILTER (WHERE canal='encaminhado') recebidos_de_outro_orgao
        FROM esic WHERE {w}""", (ano,))
    r = db.um(b, """SELECT count(*) FILTER (WHERE r.instancia=1) recursos_1, count(*) FILTER (WHERE r.instancia=1 AND r.resultado IN ('provido','parcial')) providos_1,
        count(*) FILTER (WHERE r.instancia=2) recursos_2, count(*) FILTER (WHERE r.instancia=2 AND r.resultado IN ('provido','parcial')) providos_2
        FROM esic_recursos r JOIN esic e ON e.id=r.esic_id WHERE e.tipo='pedido' AND EXTRACT(YEAR FROM e.recebido)=%s""", (ano,))
    d = dict(ano=ano, **{k: (float(v) if v is not None and k == 'dias_medios' else (v or 0)) for k, v in s.items()}, **r)
    return d


ROTULOS_EST = [('recebidos', 'Pedidos recebidos'), ('respondidos', 'Respondidos'), ('no_prazo', 'Respondidos no prazo'), ('fora_prazo', 'Respondidos fora do prazo'),
               ('em_aberto', 'Em aberto'), ('prorrogados', 'Com prazo prorrogado'), ('encaminhados', 'Encaminhados ao órgão competente'), ('encerrados', 'Encerrados sem complemento'),
               ('concedidos', 'Acesso concedido'), ('parciais', 'Acesso parcialmente concedido'), ('negados', 'Acesso negado (indeferidos)'), ('inexistentes', 'Informação inexistente'),
               ('dias_medios', 'Tempo médio de resposta (dias)'), ('recursos_1', 'Recursos em 1ª instância'), ('providos_1', '… providos (total ou parcialmente)'),
               ('recursos_2', 'Recursos em 2ª instância'), ('providos_2', '… providos (total ou parcialmente)'),
               ('pf', 'Solicitantes: pessoa física'), ('pj', 'Solicitantes: pessoa jurídica'), ('perfil_nao_informado', 'Solicitantes: não informado'),
               ('internet', 'Canal: internet'), ('presencial', 'Canal: presencial'), ('recebidos_de_outro_orgao', 'Recebidos de outro órgão')]


def relatorio_ouvidoria(b, ano):
    """Relatório de gestão da Ouvidoria (CDU arts. 14, II, e 15) e resultado da avaliação (art. 23)."""
    w = "tipo='manifestacao' AND EXTRACT(YEAR FROM recebido)=%s"
    tot = db.um(b, f"""SELECT count(*) recebidas, count(*) FILTER (WHERE situacao='respondido') respondidas,
        count(*) FILTER (WHERE situacao='respondido' AND respondido <= prazo) no_prazo, count(*) FILTER (WHERE situacao IN ('recebido','analise','complemento')) em_aberto,
        count(*) FILTER (WHERE anonimo) anonimas, count(*) FILTER (WHERE prorrogado) prorrogadas,
        round(avg(respondido - recebido) FILTER (WHERE situacao='respondido'), 1) dias_medios,
        count(avaliacao) avaliacoes, round(avg(avaliacao), 1) nota_media, count(*) FILTER (WHERE resolveu) resolveu, count(*) FILTER (WHERE resolveu = FALSE) nao_resolveu
        FROM esic WHERE {w}""", (ano,))
    cats = db.todos(b, f"SELECT COALESCE(NULLIF(categoria,''),'Sem categoria') categoria, count(*) n FROM esic WHERE {w} GROUP BY 1 ORDER BY 2 DESC, 1", (ano,))
    try:
        servs = db.todos(b, f"SELECT s.nome, count(*) n FROM esic e JOIN servicos s ON s.id=e.servico_id WHERE e.{w.replace('recebido', 'e.recebido')} GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 10", (ano,))
    except Exception:
        servs = []
    t = {k: (float(v) if k in ('dias_medios', 'nota_media') and v is not None else v) for k, v in tot.items()}
    return dict(ano=ano, totais=t, categorias=cats, servicos=servs)


def classificadas(b, hoje_=None):
    h = hoje_ or hoje()
    ativas = db.todos(b, "SELECT * FROM info_classificadas WHERE desclassificada_em IS NULL ORDER BY array_position(ARRAY['ultrassecreto','secreto','reservado'], grau), classificada_em DESC")
    descl = db.todos(b, 'SELECT * FROM info_classificadas WHERE desclassificada_em IS NOT NULL AND desclassificada_em >= %s ORDER BY desclassificada_em DESC', (h - timedelta(days=365),))
    return ativas, descl
