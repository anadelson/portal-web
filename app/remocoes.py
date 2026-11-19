"""Exclusão de órgão e de nó pela GESTÃO, com backup final e registro (19/11/2026).

Excluir ÓRGÃO (hospedado num nó): tira o domínio do ar → tarefa "excluir_orgao" no nó (backup final do banco, dos arquivos
e do banco local, conferido; só então apaga) → a gestão apaga o cadastro (licença, contratos, módulos, ordens, convites,
coletas) e fica só o REGISTRO, com onde está o backup.
Excluir NÓ (sem órgãos): tarefa "desinstalar_no" (backup final de tudo; depois o nó se remove da VPS) → a gestão apaga o
cadastro do nó. Nó que nunca foi instalado (nunca fez contato) sai direto, sem tarefa.
Se o backup falhar, nada é apagado (no nó nem na gestão) e a tela explica. Órgão do piloto (nesta VPS) não sai por aqui."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from . import db, tarefas as TF

ATIVAS = ('retirando', 'backup')
NOMES = {'retirando': 'Tirando o domínio do ar', 'backup': 'Backup final e remoção no nó', 'concluida': 'Concluída',
         'erro': 'Parou com erro (nada foi apagado)', 'cancelada': 'Cancelada'}


def _agora():
    return datetime.now(ZoneInfo('America/Sao_Paulo'))


def _pasta(tipo, nome):
    return f"{TF.PASTA_REMOVIDOS}/{_agora():%Y%m%d-%H%M}-{tipo}-{re.sub(r'[^a-z0-9-]+', '-', nome.lower()).strip('-')[:60]}"


def _hist(r, texto, situacao=None, mensagem=None):
    h = list(r['historico'] or []) + [{'em': _agora().isoformat(timespec='seconds'), 'texto': texto}]
    nova = situacao and situacao != r['situacao']
    db.exe(db.PLATAFORMA, 'UPDATE remocoes SET historico=%s, situacao=COALESCE(%s, situacao), mensagem=COALESCE(%s, mensagem), atualizada_em=now(), '
                          'etapa_desde=CASE WHEN %s THEN now() ELSE etapa_desde END, concluida_em=CASE WHEN %s IN (\'concluida\') THEN now() ELSE concluida_em END WHERE id=%s',
           (Jsonb(h[-60:]), situacao, mensagem, bool(nova), situacao, r['id']))
    r.update(historico=h, situacao=situacao or r['situacao'])


def em_andamento(orgao_id=None, no_id=None):
    if orgao_id:
        return db.um(db.PLATAFORMA, "SELECT * FROM remocoes WHERE orgao_id=%s AND tipo='orgao' AND situacao = ANY(%s) ORDER BY id DESC LIMIT 1", (orgao_id, list(ATIVAS)))
    return db.um(db.PLATAFORMA, "SELECT * FROM remocoes WHERE no_id=%s AND tipo='no' AND situacao = ANY(%s) ORDER BY id DESC LIMIT 1", (no_id, list(ATIVAS)))


def ultima(orgao_id=None, no_id=None):
    if orgao_id:
        return db.um(db.PLATAFORMA, "SELECT * FROM remocoes WHERE orgao_id=%s AND tipo='orgao' ORDER BY id DESC LIMIT 1", (orgao_id,))
    return db.um(db.PLATAFORMA, "SELECT * FROM remocoes WHERE no_id=%s AND tipo='no' ORDER BY id DESC LIMIT 1", (no_id,))


# ---------- cadastro (o que a gestão apaga) ----------
def apagar_cadastro_orgao(oid, slug):
    with db.conn(db.PLATAFORMA) as c:
        with c.transaction():
            for sql, p in (('DELETE FROM coletas WHERE orgao_slug=%s', (slug,)), ('DELETE FROM consulta_amostras WHERE orgao_slug=%s', (slug,)),
                           ('DELETE FROM consulta_testes WHERE orgao_id=%s', (oid,)), ('DELETE FROM fontes_historico WHERE orgao_id=%s', (oid,)),
                           ('DELETE FROM licencas_cache WHERE orgao_id=%s', (oid,)), ('DELETE FROM remessas_log WHERE origem=%s OR destino=%s', (slug, slug)),
                           ('DELETE FROM ordens WHERE orgao_id=%s', (oid,)), ('DELETE FROM mudancas WHERE orgao_id=%s', (oid,)),
                           ('DELETE FROM orgaos WHERE id=%s AND slug=%s', (oid, slug))):
                c.execute(sql, p)


def apagar_cadastro_no(nid):
    with db.conn(db.PLATAFORMA) as c:
        with c.transaction():
            c.execute('DELETE FROM ordens WHERE no_id=%s', (nid,))
            c.execute('UPDATE mudancas SET de_no=NULL WHERE de_no=%s', (nid,))
            c.execute('UPDATE mudancas SET para_no=NULL WHERE para_no=%s', (nid,))
            c.execute('DELETE FROM nos WHERE id=%s', (nid,))


# ---------- início ----------
def iniciar_orgao(o, quem):
    """(ok, mensagem). O órgão precisa estar num nó; o órgão desta VPS (piloto) não é excluído por aqui."""
    from . import mudancas as MU
    if not o.get('no_id'):
        return False, 'Este órgão está nesta VPS (gestão), não num nó: a exclusão pela gestão é só para órgãos hospedados em nós.'
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (o['no_id'],))
    if not MU.suporta_tarefas(n):
        return False, 'O nó deste órgão precisa estar na versão nova (que executa tarefas da gestão): atualize-o antes.'
    m = MU.ativa(o['id'])
    if m and m['situacao'] in MU.ATIVAS + ('concluida',):
        return False, 'Há uma mudança de nó deste órgão em andamento ou aguardando limpeza: termine (ou desfaça) antes.'
    if em_andamento(orgao_id=o['id']):
        return False, 'Já existe uma exclusão deste órgão em andamento.'
    r = db.um(db.PLATAFORMA, """INSERT INTO remocoes (tipo, orgao_id, no_id, nome, detalhes, no_nome, vps_ip, situacao, pasta, pedido_por)
                                VALUES ('orgao',%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
              (o['id'], n['id'], o['nome'], Jsonb({k: o.get(k) for k in ('slug', 'dominio', 'banco', 'tipo', 'municipio', 'ibge')}), n['nome'],
               ((n.get('relatorio') or {}).get('ip') or ''), 'retirando' if o.get('vhost_ativo') else 'backup', _pasta('orgao', o['slug']), quem[:120]))
    _hist(r, f"Exclusão do órgão {o['nome']} ({o['slug']}) pedida por {quem}; backup final no nó {n['nome']}.")
    avancar(r['id'], quem)
    return True, 'Exclusão iniciada: o nó faz o backup final e só então apaga. Acompanhe aqui (cada etapa leva de 1 a 5 minutos).'


def iniciar_no(n, quem):
    """(ok, mensagem). Só nó sem órgãos. Nó que nunca fez contato sai direto (não há o que desinstalar)."""
    from . import mudancas as MU
    if db.um(db.PLATAFORMA, 'SELECT 1 x FROM orgaos WHERE no_id=%s LIMIT 1', (n['id'],)):
        return False, 'Este nó ainda hospeda órgão(s): exclua ou mude cada órgão para outro nó antes.'
    if em_andamento(no_id=n['id']):
        return False, 'Já existe uma exclusão deste nó em andamento.'
    pasta_no = (n.get('relatorio') or {}).get('pasta') or ('/opt/portal_web' + (f"-{n['instancia']}" if n['instancia'] else ''))
    det = {'instancia': n['instancia'], 'pasta_no': pasta_no, 'versao': n.get('versao') or ''}
    if not n.get('ultimo_contato'):
        r = db.um(db.PLATAFORMA, """INSERT INTO remocoes (tipo, no_id, nome, detalhes, no_nome, situacao, pedido_por, concluida_em)
                                    VALUES ('no',%s,%s,%s,%s,'concluida',%s,now()) RETURNING *""", (n['id'], n['nome'], Jsonb(det), n['nome'], quem[:120]))
        _hist(r, f'Nó {n["nome"]} excluído por {quem}: nunca foi instalado (sem backup a fazer).')
        apagar_cadastro_no(n['id'])
        return True, f"Nó {n['nome']} excluído (nunca tinha sido instalado)."
    if not MU.suporta_tarefas(n):
        return False, 'O nó precisa estar na versão nova (que executa tarefas da gestão) para se desinstalar sozinho: atualize-o antes.'
    r = db.um(db.PLATAFORMA, """INSERT INTO remocoes (tipo, no_id, nome, detalhes, no_nome, vps_ip, situacao, pasta, pedido_por)
                                VALUES ('no',%s,%s,%s,%s,%s,'backup',%s,%s) RETURNING *""",
              (n['id'], n['nome'], Jsonb(det), n['nome'], ((n.get('relatorio') or {}).get('ip') or ''), _pasta('no', n['instancia'] or n['nome']), quem[:120]))
    _hist(r, f"Exclusão do nó {n['nome']} ({pasta_no}) pedida por {quem}.")
    avancar(r['id'], quem)
    return True, 'Exclusão iniciada: o nó faz o backup final, avisa a gestão e se remove da VPS (os outros sistemas e nós não são tocados).'


# ---------- andamento ----------
def _tarefa(r):
    return db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE remocao_id=%s ORDER BY id DESC LIMIT 1', (r['id'],))


def avancar(rid, quem='gestão (exclusão automática)'):
    from . import ativacao as AT
    for _ in range(4):
        r = db.um(db.PLATAFORMA, 'SELECT * FROM remocoes WHERE id=%s', (rid,))
        if not r or r['situacao'] not in ATIVAS:
            return r and r['situacao']
        n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (r['no_id'],))
        if r['tipo'] == 'orgao':
            o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (r['orgao_id'],))
            if not o or not n:
                _hist(r, 'O órgão ou o nó não existe mais no cadastro.', situacao='erro', mensagem='Cadastro mudou durante a exclusão.')
                return 'erro'
            if r['situacao'] == 'retirando':
                if not o['vhost_ativo']:
                    _hist(r, 'Domínio fora do ar.', situacao='backup'); continue
                u = AT.ultima(o['id'])
                if u and u['acao'] == 'desativar' and u['pedido_em'] >= r['etapa_desde']:
                    if u['situacao'] == 'erro':
                        _hist(r, f"Domínio: {u['mensagem']}", situacao='erro', mensagem=f"Domínio: {u['mensagem']} Nada foi apagado.")
                    return r['situacao']
                if not (u and u['situacao'] in ('pendente', 'processando')):
                    ok, msg = AT.pedir(o, 'desativar', quem)
                    _hist(r, 'Retirada do domínio pedida ao nó.' if ok else f'Domínio: {msg}', situacao=None if ok else 'erro', mensagem=None if ok else msg)
                return r['situacao']
            t = _tarefa(r)
            if not t:
                TF.criar(n, 'excluir_orgao', {'slug': o['slug'], 'pasta': r['pasta']}, quem, remocao_id=r['id'], resumo=f"excluir {o['slug']} (backup antes)")
                _hist(r, f"Tarefa enviada ao nó {n['nome']}: backup final e exclusão.")
                return r['situacao']
            if t['situacao'] == 'ok':
                db.exe(db.PLATAFORMA, 'UPDATE remocoes SET backup=%s WHERE id=%s', (Jsonb(t['resultado'] or {}), r['id']))
                apagar_cadastro_orgao(o['id'], o['slug'])
                _hist(r, f"Backup final guardado no nó e órgão apagado do nó e da gestão. {t['mensagem']}", situacao='concluida')
                return 'concluida'
            if t['situacao'] == 'erro':
                _hist(r, f"O nó não concluiu: {t['mensagem']}", situacao='erro', mensagem=f"{t['mensagem']} Nada foi apagado da gestão.")
            return r['situacao']
        # nó
        if not n:
            _hist(r, 'O nó não existe mais no cadastro.', situacao='erro', mensagem='Cadastro mudou durante a exclusão.')
            return 'erro'
        t = _tarefa(r)
        if not t:
            TF.criar(n, 'desinstalar_no', {'pasta': r['pasta']}, quem, remocao_id=r['id'], resumo=f"desinstalar {n['nome']} (backup antes)")
            _hist(r, 'Tarefa enviada ao nó: backup final e desinstalação.')
            return r['situacao']
        if t['situacao'] == 'ok':
            db.exe(db.PLATAFORMA, 'UPDATE remocoes SET backup=%s WHERE id=%s', (Jsonb(t['resultado'] or {}), r['id']))
            apagar_cadastro_no(n['id'])
            _hist(r, f"Backup final guardado na VPS; o nó se remove em seguida e foi apagado da gestão. {t['mensagem']}", situacao='concluida')
            return 'concluida'
        if t['situacao'] == 'erro':
            _hist(r, f"O nó não concluiu: {t['mensagem']}", situacao='erro', mensagem=f"{t['mensagem']} Nada foi apagado.")
        return r['situacao']
    return db.um(db.PLATAFORMA, 'SELECT situacao FROM remocoes WHERE id=%s', (rid,))['situacao']


def avancar_todas():
    for r in db.todos(db.PLATAFORMA, 'SELECT id FROM remocoes WHERE situacao = ANY(%s) ORDER BY id', (list(ATIVAS),)):
        try:
            avancar(r['id'])
        except Exception as e:
            db.exe(db.PLATAFORMA, 'UPDATE remocoes SET mensagem=%s WHERE id=%s', (f'{type(e).__name__}: {str(e)[:200]}', r['id']))


def encerrar(rid, quem):
    """Encerra uma exclusão parada com erro (nada foi apagado): o órgão/nó continua como estava."""
    r = db.um(db.PLATAFORMA, 'SELECT * FROM remocoes WHERE id=%s', (rid,))
    if not r or r['situacao'] != 'erro':
        return False, 'Só dá para encerrar uma exclusão parada com erro.'
    _hist(r, f'Encerrada por {quem}; nada foi apagado.', situacao='cancelada')
    return True, 'Exclusão encerrada; nada foi apagado.'


def marcar_backup_apagado(rid, quem):
    r = db.um(db.PLATAFORMA, 'SELECT * FROM remocoes WHERE id=%s', (rid,))
    if not r or r['situacao'] != 'concluida' or not r['pasta'] or r['backup_apagado_em']:
        return False, 'Nada a marcar.'
    db.exe(db.PLATAFORMA, 'UPDATE remocoes SET backup_apagado_em=now(), backup_apagado_por=%s WHERE id=%s', (quem[:120], rid))
    return True, 'Registrado: o backup foi apagado da VPS.'
