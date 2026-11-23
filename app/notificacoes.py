"""Notificações por e-mail do e-SIC e da Ouvidoria (23/11/2026).

Cada órgão tem a sua fila (tabela `notificacoes` no banco do órgão). O worker envia a cada minuto; falha fica registrada
e é tentada de novo (até 8 vezes, com espera crescente). O portal nunca espera o servidor de e-mail.

De onde sai o e-mail:
  1. SMTP do PRÓPRIO órgão (Painel → e-SIC e Ouvidoria → Configuração): servidor, porta, segurança, usuário, remetente
     (ex.: ouvidoria@camara...). A senha é gravada CIFRADA com a CHAVE_CREDENCIAIS do .env e nunca volta para a tela.
     É o caminho recomendado e o ÚNICO num nó separado: os dados pessoais (e-mail do cidadão, texto) não saem da
     instalação do órgão (LGPD), nem passam pela gestão.
  2. Sem SMTP próprio e com gestão e portais juntos (papel "tudo"): o e-mail de saída da plataforma (console).
  3. Nada configurado: a mensagem fica na fila como "aguardando configuração" e o painel avisa.
Mensagens de erro levam só o tipo do erro e o código do servidor, nunca usuário ou senha."""
import smtplib, ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from . import config, db

MAX_TENTATIVAS = 8

def _fernet():
    from . import credenciais
    return credenciais._fernet()

def smtp_do_orgao(b):
    return db.cfg(b, 'email_saida', None) or None

def smtp_publico(b):
    """Configuração para a tela (sem a senha)."""
    c = smtp_do_orgao(b) or {}
    return {k: c.get(k, '') for k in ('servidor', 'porta', 'seguranca', 'usuario', 'remetente', 'remetente_nome', 'teste_em', 'teste_resultado')} | {'tem_senha': bool(c.get('senha_cifrada'))}

def salvar_smtp(b, d):
    """d = dados validados por email_saida.validar. Senha vazia mantém a atual."""
    from . import credenciais
    atual = smtp_do_orgao(b) or {}
    if d['senha'] and not credenciais.chave_ok():
        raise ValueError('Falta a CHAVE_CREDENCIAIS no .env desta instalação: sem ela a senha não pode ser guardada com segurança.')
    cif = _fernet().encrypt(d['senha'].encode()).decode() if d['senha'] else atual.get('senha_cifrada', '')
    db.set_cfg(b, 'email_saida', {'servidor': d['servidor'], 'porta': d['porta'], 'seguranca': d['seguranca'], 'usuario': d['usuario'], 'senha_cifrada': cif,
                                  'remetente': d['remetente'], 'remetente_nome': d['remetente_nome'], 'teste_em': '', 'teste_resultado': ''})

def apagar_smtp(b):
    db.exe(b, "DELETE FROM config WHERE chave='email_saida'")

def caminho(b):
    """'orgao', 'plataforma' ou '' (sem configuração)."""
    if smtp_do_orgao(b):
        return 'orgao'
    if config.PAPEL != 'no':
        try:
            if db.um(db.PLATAFORMA, 'SELECT 1 FROM email_saida WHERE id=1'):
                return 'plataforma'
        except Exception:
            pass
    return ''

def _enviar_orgao(c, para, assunto, texto):
    from . import email_saida as EM
    from cryptography.fernet import InvalidToken
    senha = ''
    if c.get('senha_cifrada'):
        try:
            senha = _fernet().decrypt(c['senha_cifrada'].encode()).decode()
        except (InvalidToken, Exception):
            raise RuntimeError('a senha do SMTP do órgão não pode ser lida (CHAVE_CREDENCIAIS trocada?): grave a senha de novo')
    if not EM.EMAIL.match(para or ''):
        raise RuntimeError('destinatário inválido')
    msg = EmailMessage()
    msg['From'] = formataddr((c.get('remetente_nome') or '', c['remetente']))
    msg['To'] = para
    msg['Subject'] = assunto
    msg['Message-ID'] = make_msgid(domain=c['remetente'].split('@')[1])
    msg.set_content(texto)
    try:
        EM._smtp_enviar(c, senha, msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f'o servidor recusou o usuário/senha (código {e.smtp_code})') from None
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError('o servidor recusou o destinatário') from None
    except smtplib.SMTPException as e:
        raise RuntimeError(f'erro do servidor SMTP ({type(e).__name__})') from None
    except (OSError, ssl.SSLError) as e:
        raise RuntimeError(f'sem conexão com o servidor SMTP ({type(e).__name__})') from None

def enviar_agora(b, para, assunto, texto):
    """Envio imediato (usado pelo worker e pelo botão de teste). Levanta RuntimeError com mensagem sem segredos."""
    from . import email_saida as EM
    via = caminho(b)
    if via == 'orgao':
        return _enviar_orgao(smtp_do_orgao(b), para, assunto, texto)
    if via == 'plataforma':
        try:
            return EM.enviar(para, assunto, texto)
        except EM.NaoConfigurado as e:
            raise RuntimeError(str(e))
    raise RuntimeError('aguardando configuração do e-mail de saída do órgão')

def testar(b, para, quem):
    try:
        enviar_agora(b, para, 'Teste do e-mail do e-SIC e da Ouvidoria', f'E-mail de teste enviado pelo painel em {datetime.now().strftime("%d/%m/%Y %H:%M")} por {quem}.\n\nSe chegou, as notificações aos cidadãos vão funcionar.')
        res = f'enviado para {para}'
    except RuntimeError as e:
        res = f'falhou: {e}'
    c = smtp_do_orgao(b)
    if c:
        c.update(teste_em=datetime.now().strftime('%d/%m/%Y %H:%M'), teste_resultado=res[:300])
        db.set_cfg(b, 'email_saida', c)
    return res

# ---------- fila ----------
def enfileirar(b, para, assunto, texto, ref=''):
    """Põe a mensagem na fila do órgão (sem enviar). Sem destinatário (comunicação anônima), não faz nada."""
    if not para or '@' not in para:
        return None
    r = db.exe(b, 'INSERT INTO notificacoes (para, assunto, texto, ref) VALUES (%s,%s,%s,%s) RETURNING id', (para[:200], assunto[:200], texto[:20000], ref[:60]))
    return r and r['id']

def _espera(tentativas):
    return timedelta(minutes=min(2 ** tentativas, 240))

def processar(o, limite=30, agora=None):
    """Envia as mensagens pendentes do órgão. Devolve (enviadas, falhas)."""
    b = o['banco']
    agora = agora or datetime.now(timezone.utc)
    ok = ruim = 0
    for m in db.todos(b, 'SELECT * FROM notificacoes WHERE enviado_em IS NULL AND tentativas < %s ORDER BY id LIMIT %s', (MAX_TENTATIVAS, limite)):
        if m['tentativas'] and m.get('ultima_tentativa') and agora - m['ultima_tentativa'] < _espera(m['tentativas']):
            continue
        try:
            enviar_agora(b, m['para'], m['assunto'], m['texto'])
            db.exe(b, "UPDATE notificacoes SET enviado_em=now(), erro='' WHERE id=%s", (m['id'],))
            ok += 1
        except RuntimeError as e:
            espera_config = 'aguardando configuração' in str(e)
            # sem configuração não gasta tentativa: a mensagem sai quando o órgão configurar o e-mail
            db.exe(b, 'UPDATE notificacoes SET tentativas=tentativas + %s, erro=%s, ultima_tentativa=now() WHERE id=%s', (0 if espera_config else 1, str(e)[:300], m['id']))
            ruim += 1
            if espera_config:
                break
    return ok, ruim

def situacao_fila(b):
    return db.um(b, """SELECT count(*) FILTER (WHERE enviado_em IS NULL AND tentativas < %s) pendentes,
                              count(*) FILTER (WHERE enviado_em IS NULL AND tentativas >= %s) desistidas,
                              count(*) FILTER (WHERE enviado_em > now() - interval '30 days') enviadas_30d,
                              max(erro) FILTER (WHERE enviado_em IS NULL) ultimo_erro FROM notificacoes""", (MAX_TENTATIVAS, MAX_TENTATIVAS))
