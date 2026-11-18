"""Ativação de domínio pelo console (etapa 2 do modelo multi-órgão, 10/11/2026).

O app web NUNCA executa comandos na VPS: o console só grava o pedido (tabela `ativacoes`). O ativador da VPS
(deploy/ativador.sh, como root, a cada minuto) chama os comandos abaixo para ler e atualizar a fila e gerar o vhost:

  python -m app.ativacao pendentes              # um pedido por linha: ID<TAB>ACAO<TAB>DOMINIO
  python -m app.ativacao validar ID             # revalida o pedido (domínio cadastrado, formato, DNS na VPS); sai 0 se ok
  python -m app.ativacao vhost [--incluir ID] [--teste DOMINIO]   # imprime o portal-orgaos.conf inteiro (nginx)
  python -m app.ativacao vhost --formato traefik [--entrada-http web] [--entrada-https websecure] [--resolvedor letsencrypt] ...
                                                # imprime o portal-orgaos.yml (rotas do Traefik, ex.: VPS com Dokploy)
  python -m app.ativacao passo ID "texto"       # registra um passo (aparece no console)
  python -m app.ativacao concluir ID SITUACAO "mensagem"   # no_ar | desativado | erro

Separação gestão × portais (etapa A4): no papel "no" o mesmo ativador roda no NÓ. A fila (`ativacoes`) e os domínios publicados
(`dominios_publicados`) ficam no banco local; o pedido chega da gestão pela ordem "dominio" e os passos voltam pelo relatório do nó.
Na VPS da gestão (papel "tudo"), o vhost gerado aqui só leva os órgãos hospedados nesta VPS.
"""
import json, re, socket, sys
from . import config, db

DOMINIO = re.compile(r'^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$')
INC = f'/etc/nginx/conf.d/portal-comum{config.SUFIXO}.inc'   # um por instância: aponta para o app da instância (config.APP_ALIAS)
PREFIXO = f'portal-orgaos{config.SUFIXO}'                      # nomes das rotas/middlewares/serviço no Traefik, sem colidir entre instâncias

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

def dns(dominio, alvo=None):
    """O DNS aponta só para a VPS que hospeda o órgão? (alvo = IP do nó; sem alvo, o IP desta VPS)"""
    ips, alvo = resolver(dominio), alvo or vps_ip()
    return {'ips': ips, 'vps': alvo, 'ok': bool(ips) and bool(alvo) and ips == [alvo]}

def ip_do_no(no_id):
    """IP público informado pelo nó no último relatório."""
    n = db.um(db.PLATAFORMA, 'SELECT relatorio FROM nos WHERE id=%s', (no_id,))
    return ((n or {}).get('relatorio') or {}).get('ip', '')

def ultima(oid):
    return db.um(db.LOCAL, 'SELECT * FROM ativacoes WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (oid,))

def pedir(o, acao, quem):
    """Grava o pedido na fila. Devolve (ok, mensagem)."""
    if acao not in ('ativar', 'desativar'):
        return False, 'Ação inválida.'
    if not DOMINIO.match(o['dominio'] or ''):
        return False, 'Domínio do órgão em formato inválido.'
    u = ultima(o['id'])
    if u and u['situacao'] in ('pendente', 'processando'):
        return False, 'Já existe um pedido em andamento para este órgão.'
    no_id = o.get('no_id')
    alvo = ip_do_no(no_id) if no_id else None
    if no_id and not alvo:
        return False, 'O nó ainda não informou o IP público dele (relatório do nó). Confira em Nós e licenças.'
    if acao == 'ativar':
        d = dns(o['dominio'], alvo)
        if not d['ok']:
            return False, f"O DNS de {o['dominio']} ainda não aponta só para {'o nó' if no_id else 'a VPS'} ({d['vps'] or '?'}): hoje devolve {', '.join(d['ips']) or 'nada'}."
    elif not o['vhost_ativo']:
        return False, 'O domínio não está publicado pelo console.'
    a = db.um(db.PLATAFORMA, 'INSERT INTO ativacoes (orgao_id, dominio, acao, pedido_por) VALUES (%s,%s,%s,%s) RETURNING id', (o['id'], o['dominio'], acao, quem))
    if no_id:  # o pedido vai para o ativador do nó; os passos voltam pelo relatório do nó
        from . import ordens
        ordens.enviar('dominio', {'ativacao_id': a['id'], 'orgao_id': o['id'], 'dominio': o['dominio'], 'acao': acao, 'pedido_por': quem},
                      orgao=o, no_id=no_id, quem=quem, resumo=f"{'publicar' if acao == 'ativar' else 'tirar do ar'} {o['dominio']}")
        return True, ('Pedido enviado ao nó: o ativador do nó emite o certificado, publica o domínio e os passos aparecem aqui em até 5 minutos.' if acao == 'ativar'
                      else 'Pedido para tirar do ar enviado ao nó: os passos aparecem aqui em até 5 minutos (o certificado fica guardado no nó).')
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

def dominios(incluir=None, teste=None, excluir=None):
    """Domínios a publicar: órgãos com vhost_ativo, mais o do pedido em processamento (incluir), menos o retirado (excluir)
    e, no modo de teste do ativador, um domínio de teste (sem órgão)."""
    if config.PAPEL == 'no':
        doms = [r['dominio'] for r in db.todos(db.LOCAL, 'SELECT dominio FROM dominios_publicados ORDER BY orgao_id, dominio')]
    else:  # só os órgãos hospedados nesta VPS (os dos nós são publicados pelo ativador de cada nó)
        doms = [o['dominio'] for o in db.todos(db.PLATAFORMA, 'SELECT dominio FROM orgaos WHERE vhost_ativo AND no_id IS NULL ORDER BY id')]
    if incluir:
        a = db.um(db.LOCAL, 'SELECT dominio FROM ativacoes WHERE id=%s', (incluir,))
        if a and a['dominio'] not in doms:
            doms.append(a['dominio'])
    if excluir:
        a = db.um(db.LOCAL, 'SELECT dominio FROM ativacoes WHERE id=%s', (excluir,))
        doms = [d for d in doms if not a or d != a['dominio']]
    if teste and teste not in doms:
        doms.append(teste)
    return doms

def vhost(incluir=None, teste=None, excluir=None):
    """Conteúdo inteiro do portal-orgaos.conf (nginx)."""
    doms = dominios(incluir, teste, excluir)
    cab = ('# GERADO pelo ativador dos Portais (/opt/portal_web/deploy/ativador.sh) a partir do banco de controle. NÃO EDITE À MÃO.\n'
           '# Um par de blocos por órgão publicado pelo console. O piloto continua em portal-bora.conf.\n\n')
    return cab + '\n'.join(bloco(d) for d in doms)

NOME_TRAEFIK = re.compile(r'^[A-Za-z0-9_-]{1,40}$')

def rotas_traefik(incluir=None, teste=None, excluir=None, entrada_http='web', entrada_https='websecure', resolvedor='letsencrypt'):
    """Conteúdo inteiro do portal-orgaos.yml para o provedor de arquivos do Traefik (VPS em que o Traefik, ex.: do Dokploy,
    ocupa as portas 80/443). O corpo é JSON — que também é YAML válido —, então nunca sai um arquivo malformado.
    Tudo leva o prefixo "portal-orgaos-" para não colidir com rotas de outros sistemas. O Traefik emite e renova o
    certificado sozinho (resolvedor ACME já configurado nele) e recarrega o arquivo ao ser trocado.
    Equivale ao portal-comum.inc do nginx: cabeçalhos de segurança, envio até 25 MB, compressão e http → https."""
    for n in (entrada_http, entrada_https, resolvedor):
        if not NOME_TRAEFIK.match(n or ''):
            raise ValueError(f'nome inválido para o Traefik: {n!r}')
    routers = {}
    for d in dominios(incluir, teste, excluir):
        if not DOMINIO.match(d):
            raise ValueError(f'domínio inválido: {d!r}')
        nome = f'{PREFIXO}-' + d.replace('.', '-')
        regra = f'Host(`{d}`)'
        routers[nome + '-http'] = {'rule': regra, 'entryPoints': [entrada_http], 'middlewares': [f'{PREFIXO}-https'],
                                   'service': f'{PREFIXO}-app'}
        routers[nome] = {'rule': regra, 'entryPoints': [entrada_https], 'service': f'{PREFIXO}-app', 'tls': {'certResolver': resolvedor},
                         'middlewares': [f'{PREFIXO}-cabecalhos', f'{PREFIXO}-limite', f'{PREFIXO}-gzip']}
    conf = {'http': {
        'routers': routers,
        'middlewares': {
            f'{PREFIXO}-https': {'redirectScheme': {'scheme': 'https', 'permanent': True}},
            f'{PREFIXO}-cabecalhos': {'headers': {'contentTypeNosniff': True, 'referrerPolicy': 'strict-origin-when-cross-origin',
                                                     'stsSeconds': 31536000}},
            f'{PREFIXO}-limite': {'buffering': {'maxRequestBodyBytes': 25 * 1024 * 1024}},
            f'{PREFIXO}-gzip': {'compress': {}},
        },
        'services': {f'{PREFIXO}-app': {'loadBalancer': {'passHostHeader': True, 'servers': [{'url': f'http://{config.APP_ALIAS}:8000'}]}}},
    }}
    cab = ('# GERADO pelo ativador dos Portais (/opt/portal_web/deploy/ativador.sh) a partir do banco. NÃO EDITE À MÃO.\n'
           '# Rotas do Traefik para os órgãos publicados pelo console (formato JSON, que o Traefik lê como YAML).\n')
    return cab + json.dumps(conf, indent=2, ensure_ascii=False) + '\n'

def validar(aid):
    if config.PAPEL == 'no':
        from . import orgaos
        a = db.um(db.LOCAL, 'SELECT * FROM ativacoes WHERE id=%s', (aid,))
        o = orgaos.por_id(a['orgao_id']) if a else None
        if a:
            a = dict(a, dom_orgao=(o or {}).get('dominio'))
    else:
        a = db.um(db.PLATAFORMA, 'SELECT a.*, o.dominio dom_orgao, o.vhost_ativo FROM ativacoes a JOIN orgaos o ON o.id=a.orgao_id WHERE a.id=%s AND o.no_id IS NULL', (aid,))
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
    db.exe(db.LOCAL, "UPDATE ativacoes SET situacao=CASE WHEN situacao='pendente' THEN 'processando' ELSE situacao END, passos = passos || %s::jsonb WHERE id=%s",
           (json.dumps([{'em': config.agora().strftime('%d/%m %H:%M:%S'), 'txt': txt[:300]}]), aid))

def concluir(aid, situacao, msg):
    if situacao not in ('no_ar', 'desativado', 'erro'):
        raise ValueError(situacao)
    a = db.um(db.LOCAL, 'SELECT * FROM ativacoes WHERE id=%s', (aid,))
    db.exe(db.LOCAL, 'UPDATE ativacoes SET situacao=%s, mensagem=%s, concluido_em=now() WHERE id=%s', (situacao, msg[:500], aid))
    if config.PAPEL == 'no':  # nó: domínios publicados ficam no banco local; o console recebe pelo relatório do nó
        if situacao == 'no_ar':
            db.exe(db.LOCAL, 'INSERT INTO dominios_publicados (dominio, orgao_id) VALUES (%s,%s) ON CONFLICT (dominio) DO UPDATE SET orgao_id=EXCLUDED.orgao_id', (a['dominio'], a['orgao_id']))
        elif situacao == 'desativado':
            db.exe(db.LOCAL, 'DELETE FROM dominios_publicados WHERE dominio=%s', (a['dominio'],))
        return
    if situacao in ('no_ar', 'desativado'):
        db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=%s WHERE id=%s', (situacao == 'no_ar', a['orgao_id']))
    db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)', ('ativador da VPS', f"Domínio {a['dominio']}: {a['acao']} → {situacao}. {msg[:300]}"))

def main(args):
    cmd = args[0] if args else ''
    if cmd == 'pendentes':
        sql = ("SELECT id, acao, dominio FROM ativacoes WHERE situacao='pendente' ORDER BY id" if config.PAPEL == 'no' else  # pedidos de órgão de nó são do ativador do nó
               "SELECT a.id, a.acao, a.dominio FROM ativacoes a JOIN orgaos o ON o.id=a.orgao_id WHERE a.situacao='pendente' AND o.no_id IS NULL ORDER BY a.id")
        for a in db.todos(db.LOCAL, sql):
            print(f"{a['id']}\t{a['acao']}\t{a['dominio']}")
    elif cmd == 'validar':
        erro = validar(int(args[1]))
        print(erro or 'ok')
        return 1 if erro else 0
    elif cmd == 'vhost':
        op = dict(zip(args[1::2], args[2::2]))
        if '--teste' in op and not DOMINIO.match(op['--teste']):
            print('domínio de teste inválido', file=sys.stderr); return 2
        alvo = (int(op['--incluir']) if '--incluir' in op else None, op.get('--teste'), int(op['--excluir']) if '--excluir' in op else None)
        if op.get('--formato') == 'traefik':
            try:
                sys.stdout.write(rotas_traefik(*alvo, entrada_http=op.get('--entrada-http', 'web'),
                                               entrada_https=op.get('--entrada-https', 'websecure'), resolvedor=op.get('--resolvedor', 'letsencrypt')))
            except ValueError as e:
                print(e, file=sys.stderr); return 2
        else:
            sys.stdout.write(vhost(*alvo))
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
