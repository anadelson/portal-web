"""Ordens da gestão para quem hospeda o órgão — separação gestão × portais, etapa A3 (11/11/2026).

O console não escreve mais direto nos bancos dos órgãos: ele registra uma ORDEM, de uma lista FECHADA de tipos.
  - Órgão hospedado nesta VPS (papel "tudo"): a ordem é executada na hora, no mesmo pedido (como sempre foi).
  - Órgão hospedado num nó: a ordem fica na fila; o nó busca (GET /api/no/ordens, com o token), confere a ASSINATURA
    da gestão, executa uma vez só (registro em ordens_feitas) e devolve o resultado (POST /api/no/ordens/{id}).

Tipos:
  criar_orgao   prepara o banco do órgão (esquema, identidade, integrações, menus, layout, administrador inicial).
                Leva só o HASH da senha inicial do administrador; a senha em claro aparece uma vez no console e não viaja.
  credencial    grava (ou apaga) uma credencial de fonte de dados — vai CIFRADA (CHAVE_CREDENCIAIS, igual na gestão e no nó).
  convite       grava no administrador do órgão o convite de primeiro acesso (só o HASH do link); a senha antiga deixa de valer.
                O e-mail com o link sai da gestão depois que a ordem foi executada e o domínio do órgão responde.
  dominio       põe na fila do ativador do NÓ o pedido de publicar/tirar do ar o domínio do órgão (mesmo id do pedido no console);
                os passos (certificado, nginx, HTTPS) voltam para o console pelo relatório do nó.
"""
import json, sys, time
from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from . import config, db

TIPOS = ('criar_orgao', 'credencial', 'dominio', 'convite')

# ---------- execução (em quem hospeda) ----------
def _criar_orgao(p):
    from . import provision, remessa, web, convites
    from .security import hash_senha
    import secrets as _s
    cv = p.get('convite')
    senha_hash = p.get('senha_hash') or hash_senha(_s.token_urlsafe(32))  # com convite: senha que ninguém conhece até o primeiro acesso
    provision.preparar_orgao(p['orgao'], identidade=p.get('identidade'), fontes=p.get('fontes'), email_admin=p.get('email_admin'), senha_hash=senha_hash)
    if cv:
        convites.aplicar(p['orgao']['banco'], cv['email'], cv['convite_hash'], cv['convite_expira'])
    web.limpar_cache()
    n = remessa.configurar_pares()
    return f"banco {p['orgao']['banco']} preparado (identidade, integrações, menus, layout e administrador)" + (f'; {n} integração(ões) entre órgãos' if n else '')

def _credencial(p):
    if p.get('apagar'):
        n = db.exe(db.LOCAL, 'DELETE FROM credenciais_fontes WHERE fonte=%s RETURNING 1', (p['fonte'],))
        return 'credencial apagada' if n else 'não havia credencial'
    db.exe(db.LOCAL, """INSERT INTO credenciais_fontes (fonte, dados, configurada_em, configurada_por) VALUES (%s,%s,%s,%s)
                        ON CONFLICT (fonte) DO UPDATE SET dados=EXCLUDED.dados, configurada_em=EXCLUDED.configurada_em, configurada_por=EXCLUDED.configurada_por,
                        testada_em=NULL, testada_por=NULL, teste_resultado=NULL""", (p['fonte'], p['dados'], p.get('configurada_em') or datetime.now(timezone.utc), p.get('configurada_por', '')))
    return 'credencial gravada (cifrada)'

def _dominio(p):
    from . import orgaos
    o = orgaos.por_id(p['orgao_id'])
    if not o or o['dominio'] != p['dominio']:
        raise ValueError('domínio do pedido não confere com a licença do órgão neste nó')
    if p['acao'] not in ('ativar', 'desativar'):
        raise ValueError('ação inválida')
    r = db.exe(db.LOCAL, 'INSERT INTO ativacoes (id, orgao_id, dominio, acao, pedido_por) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING id',
               (p['ativacao_id'], p['orgao_id'], p['dominio'], p['acao'], p.get('pedido_por', '')[:120]))
    return f"pedido {p['ativacao_id']} na fila do ativador do nó" if r else 'pedido já estava na fila'

def _convite(p):
    from . import orgaos, convites
    o = orgaos.por_id(p['orgao_id'])
    if not o:
        raise ValueError('órgão não hospedado aqui')
    convites.aplicar(o['banco'], p['email'], p['convite_hash'], p['convite_expira'])
    return f"convite gravado para {p['email']}"

EXECUTA = {'criar_orgao': _criar_orgao, 'credencial': _credencial, 'dominio': _dominio, 'convite': _convite}

def executar(tipo, payload):
    if tipo not in EXECUTA:
        raise ValueError(f'tipo de ordem fora da lista: {tipo!r}')
    return EXECUTA[tipo](payload)

# ---------- gestão ----------
def enviar(tipo, payload, orgao=None, no_id=None, quem='', resumo=''):
    return enviar_com_id(tipo, payload, orgao, no_id, quem, resumo)[1:]

def enviar_com_id(tipo, payload, orgao=None, no_id=None, quem='', resumo=''):
    """Registra a ordem. Sem nó (órgão nesta VPS), executa na hora e devolve (True, resultado) — erro sobe como exceção.
    Com nó, fica na fila e devolve (False, 'na fila do nó')."""
    if tipo not in TIPOS:
        raise ValueError(f'tipo de ordem fora da lista: {tipo!r}')
    r = db.um(db.PLATAFORMA, 'INSERT INTO ordens (no_id, orgao_id, tipo, payload, resumo, criada_por) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id',
              (no_id, orgao['id'] if orgao else None, tipo, Jsonb(payload), resumo[:300], quem[:120]))
    if no_id:
        return r['id'], False, 'na fila do nó'
    try:
        res = executar(tipo, payload)
    except Exception as e:
        concluir(r['id'], False, f'{type(e).__name__}: {e}')
        raise
    concluir(r['id'], True, res)
    return r['id'], True, res

def concluir(oid, ok, resultado):
    db.exe(db.PLATAFORMA, "UPDATE ordens SET situacao=%s, resultado=%s, feita_em=now() WHERE id=%s AND situacao='pendente'",
           ('feita' if ok else 'erro', str(resultado)[:500], oid))

def para_no(no):
    """Ordens pendentes do nó, assinadas pela gestão (a assinatura cobre id, nó, tipo e conteúdo)."""
    from . import licenca
    out = []
    for o in db.todos(db.PLATAFORMA, "SELECT * FROM ordens WHERE no_id=%s AND situacao='pendente' ORDER BY id LIMIT 50", (no['id'],)):
        doc = {'v': 1, 'especie': 'ordem', 'id': o['id'], 'no': no['nome'], 'tipo': o['tipo'], 'orgao_id': o['orgao_id'], 'payload': o['payload'], 'criada_em': o['criada_em'].isoformat()}
        p = licenca.assinar(doc)
        out.append(p)
    return out

def informar(no, oid, ok, resultado):
    """Resultado devolvido pelo nó; só vale para ordem pendente DESTE nó."""
    o = db.um(db.PLATAFORMA, "SELECT * FROM ordens WHERE id=%s AND no_id=%s", (oid, no['id']))
    if not o:
        return False
    concluir(oid, bool(ok), resultado)
    return True

# ---------- nó ----------
def _api(metodo, caminho, corpo=None):
    import httpx
    url = config.GESTAO_URL.rstrip('/') + caminho
    h = {'Authorization': f'Bearer {config.NO_TOKEN}', 'User-Agent': config.USER_AGENT}
    r = httpx.request(metodo, url, headers=h, json=corpo, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f'gestão respondeu HTTP {r.status_code}')
    return r.json()

def buscar_na_gestao():
    return _api('GET', '/api/no/ordens')

def devolver_na_gestao(oid, ok, resultado):
    return _api('POST', f'/api/no/ordens/{oid}', {'ok': ok, 'resultado': resultado})

def puxar():
    """(nó) Busca, confere e executa as ordens; devolve os resultados à gestão. Cada ordem roda uma vez só."""
    from . import licenca
    if config.PAPEL != 'no':
        return 'papel não é "no": nada a buscar'
    if not (config.GESTAO_URL and config.NO_TOKEN and config.LICENCA_CHAVE_PUBLICA):
        return 'faltam GESTAO_URL, NO_TOKEN ou LICENCA_CHAVE_PUBLICA no .env do nó'
    feitas = recusadas = 0
    for p in buscar_na_gestao().get('ordens', []):
        d = licenca.verificar(p, config.LICENCA_CHAVE_PUBLICA)
        if not d or d.get('v') != 1 or d.get('especie') != 'ordem' or d.get('tipo') not in TIPOS:
            recusadas += 1
            continue
        ja = db.um(db.LOCAL, 'SELECT * FROM ordens_feitas WHERE id=%s', (d['id'],))
        if not ja:
            try:
                ok, res = True, executar(d['tipo'], d['payload'])
            except Exception as e:
                ok, res = False, f'{type(e).__name__}: {str(e)[:300]}'
            db.exe(db.LOCAL, 'INSERT INTO ordens_feitas (id, tipo, ok, resultado) VALUES (%s,%s,%s,%s)', (d['id'], d['tipo'], ok, res[:500]))
            ja = {'ok': ok, 'resultado': res}
            feitas += 1
        try:
            devolver_na_gestao(d['id'], ja['ok'], ja['resultado'])
            db.exe(db.LOCAL, 'UPDATE ordens_feitas SET informada=TRUE WHERE id=%s', (d['id'],))
        except Exception:
            pass  # a gestão recebe na próxima busca (a ordem continua pendente lá, mas não roda de novo aqui)
    return f'{feitas} ordem(ns) executada(s)' + (f', {recusadas} RECUSADA(S) (assinatura não confere)' if recusadas else '')

def main(a):
    if a[:1] == ['puxar']:
        print(puxar()); return 0
    print(__doc__, file=sys.stderr); return 2

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
