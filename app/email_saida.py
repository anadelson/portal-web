"""E-mail de saída da plataforma, configurado no console do gestor (12/11/2026).

Usado para mandar o convite de primeiro acesso ao administrador de cada órgão (e outros avisos no futuro).
  - Os dados do servidor SMTP ficam no banco de controle; a SENHA fica CIFRADA com a CHAVE_CREDENCIAIS do .env
    (a mesma das credenciais de fontes). Nenhuma função devolve a senha para tela, log ou mensagem.
  - Só a gestão envia e-mail: os nós não precisam de configuração de SMTP.
  - Mensagens de erro levam só o tipo do erro e o código do servidor, nunca usuário ou senha."""
import re, smtplib, ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from . import config, db

SEGURANCAS = {'ssl': 'SSL/TLS direto (porta 465)', 'starttls': 'STARTTLS (porta 587)', 'nenhuma': 'Sem criptografia (não recomendado)'}
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$')
SERVIDOR = re.compile(r'^(?=.{3,253}$)[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$')

class NaoConfigurado(Exception):
    """E-mail de saída ainda não configurado no console."""

def _fernet():
    from . import credenciais
    return credenciais._fernet()

def config_atual():
    """Dados para a tela (sem a senha; só se ela existe)."""
    r = db.um(db.PLATAFORMA, 'SELECT * FROM email_saida WHERE id=1')
    if not r:
        return None
    d = {k: r[k] for k in ('servidor', 'porta', 'seguranca', 'usuario', 'remetente', 'remetente_nome', 'atualizado_em', 'atualizado_por', 'teste_em', 'teste_por', 'teste_resultado')}
    d['tem_senha'] = bool(r['senha_cifrada'])
    return d

def validar(f):
    """Lê o formulário. Devolve (dados, erros). Senha vazia = manter a atual."""
    erros = []
    servidor = (f.get('servidor') or '').strip()
    if not SERVIDOR.match(servidor):
        erros.append('Servidor SMTP inválido (ex.: smtp.hostinger.com).')
    try:
        porta = int(f.get('porta') or 0)
        if not 1 <= porta <= 65535:
            raise ValueError
    except ValueError:
        porta = 0; erros.append('Porta inválida (ex.: 465 ou 587).')
    seg = f.get('seguranca') or ''
    if seg not in SEGURANCAS:
        erros.append('Escolha a segurança da conexão.')
    remetente = (f.get('remetente') or '').strip()
    if not EMAIL.match(remetente):
        erros.append('E-mail do remetente inválido (ex.: nao-responda@seudominio.tld).')
    usuario = (f.get('usuario') or '').strip()[:200]
    nome = (f.get('remetente_nome') or '').strip()[:120]
    return {'servidor': servidor, 'porta': porta, 'seguranca': seg, 'usuario': usuario, 'senha': f.get('senha') or '', 'remetente': remetente, 'remetente_nome': nome}, erros

def salvar(d, quem):
    """Grava a configuração. Senha nova é cifrada; senha vazia mantém a anterior."""
    atual = db.um(db.PLATAFORMA, 'SELECT senha_cifrada FROM email_saida WHERE id=1')
    cif = _fernet().encrypt(d['senha'].encode()).decode() if d['senha'] else (atual or {}).get('senha_cifrada', '')
    db.exe(db.PLATAFORMA, """INSERT INTO email_saida (id, servidor, porta, seguranca, usuario, senha_cifrada, remetente, remetente_nome, atualizado_em, atualizado_por)
                             VALUES (1,%s,%s,%s,%s,%s,%s,%s,now(),%s)
                             ON CONFLICT (id) DO UPDATE SET servidor=EXCLUDED.servidor, porta=EXCLUDED.porta, seguranca=EXCLUDED.seguranca, usuario=EXCLUDED.usuario,
                             senha_cifrada=EXCLUDED.senha_cifrada, remetente=EXCLUDED.remetente, remetente_nome=EXCLUDED.remetente_nome,
                             atualizado_em=now(), atualizado_por=EXCLUDED.atualizado_por, teste_em=NULL, teste_resultado=''""",
           (d['servidor'], d['porta'], d['seguranca'], d['usuario'], cif, d['remetente'], d['remetente_nome'], quem))

def _senha(r):
    if not r['senha_cifrada']:
        return ''
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(r['senha_cifrada'].encode()).decode()
    except InvalidToken:
        raise NaoConfigurado('a senha do SMTP não pode ser lida (CHAVE_CREDENCIAIS trocada?): grave a senha de novo')

def _smtp_enviar(r, senha, msg):
    """Conexão de verdade com o servidor SMTP (os testes trocam esta função)."""
    ctx = ssl.create_default_context()
    if r['seguranca'] == 'ssl':
        s = smtplib.SMTP_SSL(r['servidor'], r['porta'], timeout=20, context=ctx)
    else:
        s = smtplib.SMTP(r['servidor'], r['porta'], timeout=20)
    try:
        if r['seguranca'] == 'starttls':
            s.starttls(context=ctx)
        if r['usuario']:
            s.login(r['usuario'], senha)
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:
            pass

def enviar(para, assunto, texto, html=None):
    """Envia um e-mail. Levanta NaoConfigurado ou RuntimeError (com mensagem sem segredos)."""
    r = db.um(db.PLATAFORMA, 'SELECT * FROM email_saida WHERE id=1')
    if not r:
        raise NaoConfigurado('e-mail de saída não configurado no console')
    if not EMAIL.match(para or ''):
        raise RuntimeError('destinatário inválido')
    msg = EmailMessage()
    msg['From'] = formataddr((r['remetente_nome'] or config.NOME_PLATAFORMA, r['remetente']))
    msg['To'] = para
    msg['Subject'] = assunto
    msg['Message-ID'] = make_msgid(domain=r['remetente'].split('@')[1])
    msg.set_content(texto)
    if html:
        msg.add_alternative(html, subtype='html')
    try:
        _smtp_enviar(r, _senha(r), msg)
    except NaoConfigurado:
        raise
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(f'o servidor recusou o usuário/senha (código {e.smtp_code})') from None
    except smtplib.SMTPRecipientsRefused:
        raise RuntimeError('o servidor recusou o destinatário') from None
    except smtplib.SMTPException as e:
        raise RuntimeError(f'erro do servidor SMTP ({type(e).__name__})') from None
    except (OSError, ssl.SSLError) as e:
        raise RuntimeError(f'sem conexão com o servidor SMTP ({type(e).__name__})') from None

def testar(para, quem):
    """Manda um e-mail de teste e guarda o resultado (sem segredos)."""
    try:
        enviar(para, f'Teste do e-mail de saída — {config.NOME_PLATAFORMA}',
               f'Este é um e-mail de teste enviado pelo console do gestor em {datetime.now().strftime("%d/%m/%Y %H:%M")}.\n\nSe chegou, o e-mail de saída está funcionando.')
        res = f'enviado para {para}'
    except (NaoConfigurado, RuntimeError) as e:
        res = f'falhou: {e}'
    db.exe(db.PLATAFORMA, 'UPDATE email_saida SET teste_em=now(), teste_por=%s, teste_resultado=%s WHERE id=1', (quem, res[:300]))
    return res
