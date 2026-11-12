"""Convite de primeiro acesso do administrador do órgão (12/11/2026).

O console NÃO mostra senha: no cadastro do órgão (ou em "Reenviar convite"), a gestão gera um link de uso único
(vale CONVITE_DIAS dias) e manda por e-mail ao administrador. Ao abrir o link, ele mesmo cria a senha e cadastra o
segundo fator. Ninguém mais conhece a senha.

  - O banco do órgão guarda só o HASH do link (vai na ordem "criar_orgao" ou "convite", executada por quem hospeda).
  - A gestão guarda o link CIFRADO só até o e-mail sair (depois apaga) e o HASH para reconhecer o link.
  - O e-mail sai NA HORA (só depende do e-mail de saída configurado). O link aponta para a GESTÃO (/convite), que está
    sempre no ar: ela confere se o painel do órgão já foi publicado (e o convite já foi gravado por quem hospeda).
    Se ainda não, avisa e não faz nada; se sim, encaminha para o painel do órgão, onde a senha e o 2º fator são criados.
  - "Usado": quando o administrador cria a senha pelo link (órgão nesta VPS: lido no banco dele; no nó: pelo relatório)."""
import base64, hashlib, secrets
from datetime import datetime, timedelta, timezone
from . import config, db

CONVITE_DIAS = 7

def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('convite|' + config.SECRET_KEY).encode()).digest()))

def hash_token(token):
    return hashlib.sha256(('convite|' + token).encode()).hexdigest()

def novo(o, email, quem):
    """Gera o link e registra o convite. Devolve (convite_id, dados para a ordem: email, convite_hash, convite_expira)."""
    token = secrets.token_urlsafe(32)
    expira = datetime.now(timezone.utc) + timedelta(days=CONVITE_DIAS)
    db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='cancelado', token_cifrado=NULL, mensagem='substituído por um convite novo' WHERE orgao_id=%s AND situacao IN ('aguardando','enviado')", (o['id'],))
    r = db.um(db.PLATAFORMA, 'INSERT INTO convites (orgao_id, email, token_cifrado, token_hash, expira_em, criado_por) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
              (o['id'], email, _fernet().encrypt(token.encode()).decode(), hash_token(token), expira, quem))
    return r['id'], {'email': email, 'convite_hash': hash_token(token), 'convite_expira': expira.isoformat()}

def ligar_ordem(convite_id, ordem_id):
    db.exe(db.PLATAFORMA, 'UPDATE convites SET ordem_id=%s WHERE id=%s', (ordem_id, convite_id))

# ---------- em quem hospeda o órgão (executor das ordens) ----------
def aplicar(banco, email, convite_hash, convite_expira):
    """Grava o convite no administrador (por e-mail). A senha antiga deixa de valer (vira um valor que ninguém conhece)."""
    from .security import hash_senha
    u = db.um(banco, "SELECT id, ultimo_acesso FROM usuarios WHERE lower(email)=lower(%s) AND perfil='admin'", (email,))
    if not u:
        raise ValueError('administrador com este e-mail não existe no órgão')
    db.exe(banco, 'UPDATE usuarios SET convite_hash=%s, convite_expira=%s, senha_hash=%s, trocar_senha=FALSE, falhas=0, bloqueado_ate=NULL WHERE id=%s',
           (convite_hash, convite_expira, hash_senha(secrets.token_urlsafe(32)), u['id']))
    return u['id']

def conta_do_token(banco, token):
    """Administrador dono do link, se o link é válido (existe, não venceu, conta ativa)."""
    if not token or len(token) > 100:
        return None
    u = db.um(banco, "SELECT * FROM usuarios WHERE convite_hash=%s AND situacao='ativo'", (hash_token(token),))
    if not u or not u['convite_expira'] or u['convite_expira'] < datetime.now(timezone.utc):
        return None
    return u

def usar(banco, conta, senha_hash):
    """Primeiro acesso: grava a senha escolhida e invalida o link. O segundo fator é cadastrado em seguida."""
    db.exe(banco, 'UPDATE usuarios SET senha_hash=%s, convite_hash=NULL, convite_expira=NULL, trocar_senha=FALSE, totp_ativo=FALSE, totp_segredo=%s WHERE id=%s',
           (senha_hash, '', conta['id']))

def hash_email(email):
    """Código do e-mail (o relatório do nó não leva o e-mail em si, só este código)."""
    return hashlib.sha256(('email|' + (email or '').strip().lower()).encode()).hexdigest()[:24]

def pendentes(banco):
    """Códigos dos e-mails com convite ainda não usado (vai no relatório do nó, sem dado pessoal)."""
    return [hash_email(r['email']) for r in db.todos(banco, 'SELECT email FROM usuarios WHERE convite_hash IS NOT NULL')]

# ---------- gestão: envio e situação ----------
def dominio_no_ar(dominio):
    """O painel do órgão responde no domínio? (o link do convite aponta para lá) — os testes trocam esta função."""
    import httpx
    try:
        r = httpx.get(f'https://{dominio}/admin/login', timeout=10, follow_redirects=False, headers={'User-Agent': config.USER_AGENT})
        return r.status_code == 200
    except httpx.HTTPError:
        return False

def link(o, token):
    """Link do e-mail: sempre na GESTÃO (que confere se o painel do órgão já está no ar antes de encaminhar)."""
    return f"https://{config.DOMINIO_GESTAO}/convite?t={token}"

def link_painel(o, token):
    return f"https://{o['dominio']}/admin/primeiro-acesso?t={token}"

def situacao_link(token):
    """Página /convite da gestão: (convite, órgão, estado) com estado em
    invalido | usado | vencido | preparando (quem hospeda ainda não gravou) | fora_do_ar (painel ainda não publicado) | pronto."""
    if not token or len(token) > 100:
        return None, None, 'invalido'
    c = db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE token_hash=%s', (hash_token(token),))
    if not c:
        return None, None, 'invalido'
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (c['orgao_id'],))
    if c['situacao'] in ('cancelado', 'erro') or not o:
        return c, o, 'invalido'
    if c['situacao'] == 'aguardando' or c['situacao'] == 'enviado':
        if not o.get('no_id'):  # órgão nesta VPS: confere direto no banco dele se já foi usado
            try:
                marcar_usados(o['id'], pendentes(o['banco']))
                c = db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE id=%s', (c['id'],))
            except Exception:
                pass
    if c['situacao'] == 'usado':
        return c, o, 'usado'
    if c['situacao'] == 'vencido' or c['expira_em'] < datetime.now(timezone.utc):
        return c, o, 'vencido'
    if c['ordem_id']:
        od = db.um(db.PLATAFORMA, 'SELECT situacao FROM ordens WHERE id=%s', (c['ordem_id'],))
        if not od or od['situacao'] != 'feita':
            return c, o, 'preparando'
    if not dominio_no_ar(o['dominio']):
        return c, o, 'fora_do_ar'
    return c, o, 'pronto'

def _texto(o, url, expira):
    quando = expira.astimezone().strftime('%d/%m/%Y às %H:%M')
    t = (f"Olá,\n\nVocê foi indicado como administrador do painel do portal {o['nome']}.\n\n"
         f"Para o primeiro acesso, abra o link abaixo, crie a sua senha e cadastre o segundo fator (aplicativo autenticador no celular):\n\n{url}\n\n"
         f"Se o painel do órgão ainda não estiver publicado, a página avisa e você pode voltar ao mesmo link depois.\n"
         f"O link vale uma vez só, até {quando}. Depois disso, peça um novo convite à equipe que administra a plataforma.\n"
         f"Ninguém da equipe vai pedir a sua senha.\n\nSe você não esperava este e-mail, pode ignorá-lo.\n\n— {config.NOME_PLATAFORMA}")
    h = (f"<p>Olá,</p><p>Você foi indicado como administrador do painel do portal <strong>{o['nome']}</strong>.</p>"
         f"<p>Para o primeiro acesso, abra o link abaixo, crie a sua senha e cadastre o segundo fator (aplicativo autenticador no celular):</p>"
         f"<p><a href=\"{url}\">Fazer o primeiro acesso</a></p><p>Se o painel do órgão ainda não estiver publicado, a página avisa e você pode voltar ao mesmo link depois.</p><p>O link vale uma vez só, até {quando}. Depois disso, peça um novo convite à equipe que administra a plataforma. "
         f"Ninguém da equipe vai pedir a sua senha.</p><p>Se você não esperava este e-mail, pode ignorá-lo.</p><p>— {config.NOME_PLATAFORMA}</p>")
    return t, h

def tick():
    """Gestão: manda os convites registrados (na hora; só depende do e-mail de saída). Devolve quantos saíram.
    Se quem hospeda não conseguir gravar o convite (ordem com erro), o convite vira "erro" e não sai."""
    from . import email_saida as EM
    if config.PAPEL == 'no':
        return 0
    n = 0
    for c in db.todos(db.PLATAFORMA, "SELECT c.*, o.nome, o.dominio, o.slug FROM convites c JOIN orgaos o ON o.id=c.orgao_id WHERE c.situacao='aguardando' ORDER BY c.id"):
        def motivo(m):
            db.exe(db.PLATAFORMA, 'UPDATE convites SET mensagem=%s, tentativa_em=now() WHERE id=%s', (m[:300], c['id']))
        if c['expira_em'] < datetime.now(timezone.utc):
            db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='vencido', token_cifrado=NULL, mensagem='venceu antes de ser enviado' WHERE id=%s", (c['id'],)); continue
        if c['ordem_id']:
            od = db.um(db.PLATAFORMA, 'SELECT situacao, resultado FROM ordens WHERE id=%s', (c['ordem_id'],))
            if od and od['situacao'] == 'erro':
                db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='erro', token_cifrado=NULL, mensagem=%s WHERE id=%s", (f"o servidor do órgão não gravou o convite: {od['resultado'][:200]}", c['id'])); continue
        try:
            token = _fernet().decrypt(c['token_cifrado'].encode()).decode()
            t, h = _texto(c, link(c, token), c['expira_em'])
            EM.enviar(c['email'], f"Primeiro acesso ao painel — {c['nome']}", t, h)
        except EM.NaoConfigurado as e:
            motivo(f'convite não enviado: {e}'); continue
        except Exception as e:
            motivo(f'falha no envio, nova tentativa em seguida: {str(e)[:200]}'); continue
        db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='enviado', enviado_em=now(), token_cifrado=NULL, mensagem='' WHERE id=%s", (c['id'],))
        db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)', ('plataforma', f"Convite de primeiro acesso enviado para {c['email']} ({c['nome']})"))
        n += 1
    return n

def marcar_usados(orgao_id, pendentes_no_orgao):
    """Convites enviados cujo e-mail (pelo código) não está mais pendente no órgão viraram "usado"."""
    pend = set(pendentes_no_orgao)
    for c in db.todos(db.PLATAFORMA, "SELECT id, email, expira_em FROM convites WHERE orgao_id=%s AND situacao='enviado'", (orgao_id,)):
        if hash_email(c['email']) not in pend:
            db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='usado', mensagem='' WHERE id=%s", (c['id'],))
        elif c['expira_em'] < datetime.now(timezone.utc):
            db.exe(db.PLATAFORMA, "UPDATE convites SET situacao='vencido', mensagem='o link venceu sem ser usado' WHERE id=%s", (c['id'],))

def ultimo(o):
    """Último convite do órgão, já com "usado"/"vencido" atualizados (órgão nesta VPS: lê o banco dele)."""
    if not o.get('no_id'):
        try:
            marcar_usados(o['id'], pendentes(o['banco']))
        except Exception:
            pass
    return db.um(db.PLATAFORMA, 'SELECT * FROM convites WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (o['id'],))
