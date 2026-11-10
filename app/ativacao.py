"""Ativação de domínio pelo console (etapa 2 do modelo multi-órgão, 10/11/2026).

O app web NUNCA executa comandos na VPS: o console só grava o pedido (tabela `ativacoes`). O ativador da VPS
(deploy/ativador.sh, como root, a cada minuto) chama os comandos abaixo para ler e atualizar a fila e gerar o vhost:

  python -m app.ativacao pendentes              # um pedido por linha: ID<TAB>ACAO<TAB>DOMINIO
  python -m app.ativacao validar ID             # revalida o pedido (domínio cadastrado, formato, DNS na VPS); sai 0 se ok
  python -m app.ativacao vhost [--incluir ID] [--teste DOMINIO]   # imprime o portal-orgaos.conf inteiro
  python -m app.ativacao passo ID "texto"       # registra um passo (aparece no console)
  python -m app.ativacao concluir ID SITUACAO "mensagem"   # no_ar | desativado | erro
"""
import json, re, socket, sys
from . import config, db

DOMINIO = re.compile(r'^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$')
INC = '/etc/nginx/conf.d/portal-comum.inc'

def vps_ip():
    """IP público da VPS: VPS_IP no .env ou o IP para onde aponta o domínio do console."""
    if config.env('VPS_IP'):
        return config.env('VPS_IP')
    try:
        return socket.gethostbyname(config.DOMINIO_GESTAO)
    except OSError:
        return ''

def resolver(dominio):
    """IPs (v4) que o DNS devolve agora para o domínio (lista vazia se não resolve)."""
    try:
        return sorted({x[4][0] for x in socket.getaddrinfo(dominio, 443, socket.AF_INET)})
    except OSError:
        return []

def dns(dominio):
    ips, alvo = resolver(dominio), vps_ip()
    return {'ips': ips, 'vps': alvo, 'ok': bool(ips) and bool(alvo) and ips == [alvo]}

def ultima(oid):
    return db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (oid,))

def pedir(o, acao, quem):
    """Grava o pedido na fila. Devolve (ok, mensagem)."""
    if acao not in ('ativar', 'desativar'):
        return False, 'Ação inválida.'
    if not DOMINIO.match(o['dominio'] or ''):
        return False, 'Domínio do órgão em formato inválido.'
    u = ultima(o['id'])
    if u and u['situacao'] in ('pendente', 'processando'):
        return False, 'Já existe um pedido em andamento para este órgão.'
    if acao == 'ativar':
        d = dns(o['dominio'])
        if not d['ok']:
            return False, f"O DNS de {o['dominio']} ainda não aponta só para a VPS ({d['vps'] or '?'}): hoje devolve {', '.join(d['ips']) or 'nada'}."
    elif not o['vhost_ativo']:
        return False, 'O domínio não está publicado pelo console.'
    db.exe(db.PLATAFORMA, 'INSERT INTO ativacoes (orgao_id, dominio, acao, pedido_por) VALUES (%s,%s,%s,%s)', (o['id'], o['dominio'], acao, quem))
    return True, ('Pedido de ativação registrado: o ativador da VPS emite o certificado, publica o domínio e informa aqui em 1 a 3 minutos.' if acao == 'ativar'
                  else 'Pedido para tirar do ar registrado: o ativador da VPS remove o domínio do nginx em 1 a 3 minutos (o certificado fica guardado).')

def bloco(dominio):
    """Dois blocos do nginx (porta 80 com o desafio do Let's Encrypt e porta 443 com o certificado) para um domínio já validado."""
    if not DOMINIO.match(dominio):
        raise ValueError(f'domínio inválido: {dominio!r}')
    return f"""server {{
    listen 80;
    server_name {dominio};
    location /.well-known/acme-challenge/ {{ root /var/www/certbot; }}
    location / {{ return 301 https://$host$request_uri; }}
}}
server {{
    listen 443 ssl http2;
    server_name {dominio};
    ssl_certificate     /etc/letsencrypt/live/{dominio}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{dominio}/privkey.pem;
    include {INC};
}}
"""

def vhost(incluir=None, teste=None, excluir=None):
    """Conteúdo inteiro do portal-orgaos.conf: órgãos com vhost_ativo, mais o do pedido em processamento (incluir) e,
    no modo de teste do ativador, um domínio de teste (sem órgão)."""
    doms = [o['dominio'] for o in db.todos(db.PLATAFORMA, 'SELECT dominio FROM orgaos WHERE vhost_ativo ORDER BY id')]
    if incluir:
        a = db.um(db.PLATAFORMA, 'SELECT dominio FROM ativacoes WHERE id=%s', (incluir,))
        if a and a['dominio'] not in doms:
            doms.append(a['dominio'])
    if excluir:
        a = db.um(db.PLATAFORMA, 'SELECT dominio FROM ativacoes WHERE id=%s', (excluir,))
        doms = [d for d in doms if not a or d != a['dominio']]
    if teste and teste not in doms:
        doms.append(teste)
    cab = ('# GERADO pelo ativador dos Portais (/opt/portal_web/deploy/ativador.sh) a partir do banco de controle. NÃO EDITE À MÃO.\n'
           '# Um par de blocos por órgão publicado pelo console. O piloto continua em portal-bora.conf.\n\n')
    return cab + '\n'.join(bloco(d) for d in doms)

def validar(aid):
    a = db.um(db.PLATAFORMA, 'SELECT a.*, o.dominio dom_orgao, o.vhost_ativo FROM ativacoes a JOIN orgaos o ON o.id=a.orgao_id WHERE a.id=%s', (aid,))
    if not a:
        return 'pedido inexistente'
    if a['situacao'] not in ('pendente', 'processando'):
        return f"pedido já concluído ({a['situacao']})"
    if a['dominio'] != a['dom_orgao'] or not DOMINIO.match(a['dominio']):
        return 'domínio do pedido não confere com o cadastro do órgão'
    if a['acao'] == 'ativar' and not dns(a['dominio'])['ok']:
        return 'o DNS não aponta para a VPS'
    return ''

def passo(aid, txt):
    db.exe(db.PLATAFORMA, "UPDATE ativacoes SET situacao=CASE WHEN situacao='pendente' THEN 'processando' ELSE situacao END, passos = passos || %s::jsonb WHERE id=%s",
           (json.dumps([{'em': config.agora().strftime('%d/%m %H:%M:%S'), 'txt': txt[:300]}]), aid))

def concluir(aid, situacao, msg):
    if situacao not in ('no_ar', 'desativado', 'erro'):
        raise ValueError(situacao)
    a = db.um(db.PLATAFORMA, 'SELECT * FROM ativacoes WHERE id=%s', (aid,))
    db.exe(db.PLATAFORMA, 'UPDATE ativacoes SET situacao=%s, mensagem=%s, concluido_em=now() WHERE id=%s', (situacao, msg[:500], aid))
    if situacao in ('no_ar', 'desativado'):
        db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=%s WHERE id=%s', (situacao == 'no_ar', a['orgao_id']))
    db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)', ('ativador da VPS', f"Domínio {a['dominio']}: {a['acao']} → {situacao}. {msg[:300]}"))

def main(args):
    cmd = args[0] if args else ''
    if cmd == 'pendentes':
        for a in db.todos(db.PLATAFORMA, "SELECT id, acao, dominio FROM ativacoes WHERE situacao='pendente' ORDER BY id"):
            print(f"{a['id']}\t{a['acao']}\t{a['dominio']}")
    elif cmd == 'validar':
        erro = validar(int(args[1]))
        print(erro or 'ok')
        return 1 if erro else 0
    elif cmd == 'vhost':
        op = dict(zip(args[1::2], args[2::2]))
        if '--teste' in op and not DOMINIO.match(op['--teste']):
            print('domínio de teste inválido', file=sys.stderr); return 2
        sys.stdout.write(vhost(int(op['--incluir']) if '--incluir' in op else None, op.get('--teste'), int(op['--excluir']) if '--excluir' in op else None))
    elif cmd == 'passo':
        passo(int(args[1]), args[2])
    elif cmd == 'concluir':
        concluir(int(args[1]), args[2], args[3] if len(args) > 3 else '')
    elif cmd == 'vps-ip':
        print(vps_ip())
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
