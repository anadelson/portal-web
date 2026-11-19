"""Tarefas que a GESTÃO pede ao NÓ e que o ativador do nó (root, a cada minuto) executa — 19/11/2026.

Por que pelo ativador: mover o banco de um órgão ou criar uma instância nova mexe no Docker e em pastas da VPS, coisa que
o app (sem privilégios) não faz. A gestão continua sem acesso ao nó: ela grava a tarefa e manda uma ORDEM assinada
("tarefa"); o worker do nó põe na fila (tabela tarefas_no do banco local); o ativador executa e anota os passos; o
relatório do nó leva os passos e o resultado de volta (a cada minuto enquanto houver tarefa em andamento).

Tipos (lista fechada; os parâmetros são conferidos aqui e de novo no script que executa):
  exportar            {slug, arquivo}          deploy/no/mover_orgao.sh exportar   (nó de origem)
  importar            {slug, arquivo}          deploy/no/mover_orgao.sh importar   (nó de destino, mesma VPS)
  limpar              {slug, arquivo}          deploy/no/mover_orgao.sh limpar     (nó de origem, depois de conferido)
  instalar_instancia  {instancia, nome, token} deploy/no/criar_instancia.sh       (um nó existente cria outro nó na MESMA VPS)

Linha de comando (no nó, usada pelo ativador):
  python -m app.tarefas pendentes                  # ID<TAB>TIPO<TAB>PARAMS(JSON) por linha (marca como processando)
  python -m app.tarefas passo ID "texto"
  python -m app.tarefas concluir ID ok|erro "mensagem"
  python -m app.tarefas env-instancia ID           # .env de origem da instância nova (com os segredos deste nó): só para o ativador
"""
import json, re, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from . import config, db

TIPOS = ('exportar', 'importar', 'limpar', 'instalar_instancia')
PASTA_TRANSF = '/var/lib/portal-transferencias'          # na VPS (só root); exportar grava, importar lê (mesma VPS)
SLUG = re.compile(r'^[a-z0-9-]{2,40}$')
INST = re.compile(r'^[a-z0-9]{1,20}$')
NOME_NO = re.compile(r'^[a-z0-9][a-z0-9.-]{1,60}$')
ARQ = re.compile(r'^' + re.escape(PASTA_TRANSF) + r'/[a-z0-9-]{1,80}\.tgz$')
SITUACOES = ('pendente', 'processando', 'ok', 'erro')


def validar(tipo, p):
    """Erro (texto) ou '' se os parâmetros são aceitáveis para o tipo."""
    if tipo not in TIPOS:
        return f'tipo de tarefa fora da lista: {tipo!r}'
    if not isinstance(p, dict):
        return 'parâmetros inválidos'
    if tipo in ('exportar', 'importar', 'limpar'):
        if not SLUG.match(str(p.get('slug', ''))) or not ARQ.match(str(p.get('arquivo', ''))):
            return 'slug ou arquivo inválido'
    if tipo == 'instalar_instancia':
        if not INST.match(str(p.get('instancia', ''))) or not NOME_NO.match(str(p.get('nome', ''))) or not p.get('token'):
            return 'instância, nome ou token inválido'
    return ''


# ---------- gestão ----------
def criar(no, tipo, params, quem, mudanca_id=None, resumo=''):
    """Grava a tarefa e manda a ordem ao nó. Devolve o id."""
    err = validar(tipo, params)
    if err:
        raise ValueError(err)
    from . import ordens
    t = db.um(db.PLATAFORMA, 'INSERT INTO tarefas (no_id, tipo, params, mudanca_id, pedido_por) VALUES (%s,%s,%s,%s,%s) RETURNING id',
              (no['id'], tipo, Jsonb({k: v for k, v in params.items() if k != 'token'}), mudanca_id, quem[:120]))
    ordens.enviar('tarefa', {'tarefa_id': t['id'], 'tipo': tipo, 'params': params}, no_id=no['id'], quem=quem,
                  resumo=resumo or f"tarefa {tipo} ({params.get('slug') or params.get('instancia')})")
    return t['id']


def receber(no, lista):
    """(gestão) Atualiza as tarefas DESTE nó com o que veio no relatório. Devolve quantas mudaram."""
    n = 0
    for t in lista or []:
        if not isinstance(t, dict) or not str(t.get('id', '')).isdigit() or t.get('situacao') not in SITUACOES:
            continue
        atual = db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE id=%s', (int(t['id']),))
        if not atual or atual['no_id'] != no['id']:
            continue
        passos = [p for p in (t.get('passos') or []) if isinstance(p, dict)][:40]
        if atual['situacao'] == t['situacao'] and atual['passos'] == passos:
            continue
        res = t.get('resultado') if isinstance(t.get('resultado'), dict) else {}
        db.exe(db.PLATAFORMA, 'UPDATE tarefas SET situacao=%s, passos=%s, mensagem=%s, resultado=%s, concluida_em=%s WHERE id=%s',
               (t['situacao'], Jsonb(passos), str(t.get('mensagem', ''))[:500], Jsonb(res), t.get('concluida_em'), atual['id']))
        if t['situacao'] in ('ok', 'erro') and atual['situacao'] != t['situacao']:
            db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)',
                   (f"ativador do nó {no['nome']}", f"Tarefa {atual['id']} ({atual['tipo']}): {'concluída' if t['situacao'] == 'ok' else 'ERRO'}. {str(t.get('mensagem', ''))[:300]}"))
        n += 1
    return n


# ---------- nó ----------
def enfileirar(p):
    """(nó) Executa a ordem "tarefa": põe na fila do ativador. Idempotente pelo id."""
    tipo, params = p.get('tipo'), p.get('params') or {}
    err = validar(tipo, params)
    if err:
        raise ValueError(err)
    if tipo == 'instalar_instancia':  # o token do nó novo chega cifrado (CHAVE_CREDENCIAIS, igual na gestão e no nó)
        from . import credenciais as CR
        if not CR.decifrar(params['token']):
            raise ValueError('token do nó novo não decifra com a CHAVE_CREDENCIAIS deste nó')
    r = db.exe(db.LOCAL, 'INSERT INTO tarefas_no (id, tipo, params) VALUES (%s,%s,%s) ON CONFLICT (id) DO NOTHING RETURNING id',
               (int(p['tarefa_id']), tipo, Jsonb(params)))
    return f"tarefa {p['tarefa_id']} ({tipo}) na fila do ativador do nó" if r else 'tarefa já estava na fila'


def para_relatorio():
    try:
        return [{'id': t['id'], 'situacao': t['situacao'], 'passos': t['passos'], 'mensagem': t['mensagem'], 'resultado': t['resultado'],
                 'concluida_em': t['concluida_em'].isoformat() if t['concluida_em'] else None}
                for t in db.todos(db.LOCAL, "SELECT * FROM tarefas_no WHERE pedida_em > now() - interval '30 days' ORDER BY id DESC LIMIT 20")]
    except Exception:
        return []


def em_andamento():
    try:
        return bool(db.um(db.LOCAL, "SELECT 1 x FROM tarefas_no WHERE situacao IN ('pendente','processando') OR concluida_em > now() - interval '10 minutes' LIMIT 1"))
    except Exception:
        return False


def _passo(tid, texto):
    db.exe(db.LOCAL, "UPDATE tarefas_no SET passos = passos || %s WHERE id=%s",
           (Jsonb([{'em': datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds'), 'texto': str(texto)[:300]}]), tid))


def env_instancia(tid):
    """.env de origem da instância nova: as chaves que precisam ser iguais (as deste nó) + a identidade do nó novo."""
    from . import credenciais as CR
    t = db.um(db.LOCAL, "SELECT * FROM tarefas_no WHERE id=%s AND tipo='instalar_instancia'", (tid,))
    if not t:
        raise SystemExit('tarefa não encontrada')
    p = t['params']
    tok = CR.decifrar(p['token'])
    if not tok:
        raise SystemExit('token do nó novo não decifra')
    chaves = ('SECRET_KEY', 'TOTP_CHAVE', 'CPF_HMAC_CHAVE', 'CHAVE_CREDENCIAIS', 'PG_USER', 'DOMINIO_GESTAO', 'NOME_PLATAFORMA', 'USER_AGENT', 'DIARIO_MODO')
    linhas = [f'{k}={config.env(k)}' for k in chaves if config.env(k)]
    linhas += [f"GESTAO_URL={config.GESTAO_URL}", f"NO_NOME={p['nome']}", f"NO_TOKEN={tok[1]}", f"LICENCA_CHAVE_PUBLICA={config.LICENCA_CHAVE_PUBLICA}",
               f"INSTANCIA={p['instancia']}"]
    return '\n'.join(linhas) + '\n'


def main(a):
    if config.PAPEL != 'no':
        print('tarefas: comandos do nó (PAPEL=no)', file=sys.stderr); return 2
    if a[:1] == ['pendentes']:
        for t in db.todos(db.LOCAL, "UPDATE tarefas_no SET situacao='processando' WHERE situacao='pendente' RETURNING id, tipo, params"):
            p = {k: v for k, v in t['params'].items() if k != 'token'}
            print(f"{t['id']}\t{t['tipo']}\t{json.dumps(p, ensure_ascii=False)}")
    elif a[:1] == ['passo'] and len(a) == 3:
        _passo(int(a[1]), a[2])
    elif a[:1] == ['concluir'] and len(a) >= 4 and a[2] in ('ok', 'erro'):
        res = {}
        if len(a) > 4:
            try:
                res = json.loads(a[4])
            except ValueError:
                res = {}
        db.exe(db.LOCAL, 'UPDATE tarefas_no SET situacao=%s, mensagem=%s, resultado=%s, concluida_em=now() WHERE id=%s', (a[2], a[3][:500], Jsonb(res), int(a[1])))
    elif a[:1] == ['env-instancia'] and len(a) == 2:
        sys.stdout.write(env_instancia(int(a[1])))
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
