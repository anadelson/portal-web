"""Mudança de órgão entre nós conduzida pela GESTÃO, sem terminal (19/11/2026).

Uma mudança avança sozinha (worker da gestão, a cada minuto, e a cada relatório que chega), uma etapa por vez:
  retirando   tira o domínio do ar no nó de origem (se estava publicado)
  exportando  tarefa "exportar" no nó de origem (banco, contagens, arquivos e banco local do órgão)
  importando  tarefa "importar" no nó de destino (restaura e confere tabela por tabela)
  hospedagem  o órgão passa a ser do nó de destino (licença entregue a ele; o de origem esquece pelo inventário)
  publicando  quando o destino já tem a licença, publica o domínio lá
  concluida   pronto; os dados ainda estão na origem — "Desfazer" volta tudo; "Limpar" apaga da origem (com confirmação)
  limpando → finalizada  |  desfazendo → desfeita  |  erro (para e explica; nada é apagado)
Só entre nós da MESMA VPS (o arquivo de transferência fica numa pasta da VPS que os dois nós enxergam)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from . import db, tarefas as TF

ATIVAS = ('retirando', 'exportando', 'importando', 'hospedagem', 'publicando', 'limpando', 'desfazendo')
NOMES = {'retirando': 'Tirando o domínio do ar', 'exportando': 'Copiando os dados no nó de origem', 'importando': 'Restaurando e conferindo no nó de destino',
         'hospedagem': 'Trocando a hospedagem', 'publicando': 'Publicando o domínio no nó de destino', 'concluida': 'Concluída (dados ainda guardados na origem)',
         'limpando': 'Apagando o que ficou na origem', 'finalizada': 'Finalizada', 'desfazendo': 'Desfazendo (voltando para a origem)',
         'desfeita': 'Desfeita: o órgão voltou para a origem', 'erro': 'Parou com erro', 'cancelada': 'Cancelada'}


def _no(nid):
    return db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE id=%s', (nid,)) if nid else None


def _hist(m, texto, situacao=None, mensagem=None):
    h = list(m['historico'] or []) + [{'em': datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(timespec='seconds'), 'texto': texto}]
    nova = situacao and situacao != m['situacao']
    db.exe(db.PLATAFORMA, 'UPDATE mudancas SET historico=%s, situacao=COALESCE(%s, situacao), mensagem=COALESCE(%s, mensagem), atualizada_em=now(), '
                          'etapa_desde=CASE WHEN %s THEN now() ELSE etapa_desde END WHERE id=%s',
           (Jsonb(h[-60:]), situacao, mensagem, bool(nova), m['id']))
    m.update(historico=h, situacao=situacao or m['situacao'], mensagem=mensagem if mensagem is not None else m['mensagem'])


def mesma_vps(a, b):
    ia, ib = ((a or {}).get('relatorio') or {}).get('ip'), ((b or {}).get('relatorio') or {}).get('ip')
    return bool(ia) and ia == ib


def suporta_tarefas(n):
    return bool(((n or {}).get('relatorio') or {}).get('executa_tarefas'))   # o nó manda a lista de tarefas no relatório (versão nova)


def destinos(o):
    """Nós para onde o órgão pode ir pela gestão: outros nós da mesma VPS, já na versão que executa tarefas."""
    de = _no(o.get('no_id'))
    if not de:
        return []
    return [n for n in db.todos(db.PLATAFORMA, 'SELECT * FROM nos WHERE ativo AND id<>%s ORDER BY nome', (de['id'],)) if mesma_vps(de, n) and suporta_tarefas(n)]


def ativa(oid):
    return db.um(db.PLATAFORMA, 'SELECT * FROM mudancas WHERE orgao_id=%s ORDER BY id DESC LIMIT 1', (oid,))


def iniciar(o, para_id, quem):
    """Começa a mudança. Devolve (ok, mensagem)."""
    de, para = _no(o.get('no_id')), _no(para_id)
    if not de:
        return False, 'O órgão está nesta VPS (gestão), não num nó: a mudança pela gestão é entre nós.'
    if not para or para['id'] == de['id']:
        return False, 'Escolha o nó de destino.'
    if not mesma_vps(de, para):
        return False, 'Os dois nós precisam estar na mesma VPS (mesmo IP no relatório). Para outra VPS, use o roteiro manual (deploy/no/mover_orgao.sh).'
    if not (suporta_tarefas(de) and suporta_tarefas(para)):
        return False, 'Os dois nós precisam estar na versão nova (que executa tarefas da gestão): atualize-os antes.'
    m = ativa(o['id'])
    if m and m['situacao'] in ATIVAS + ('concluida',):
        return False, 'Já existe uma mudança deste órgão em andamento (ou concluída e aguardando limpeza/desfazer).'
    m = db.um(db.PLATAFORMA, 'INSERT INTO mudancas (orgao_id, de_no, para_no, publicar, pedido_por) VALUES (%s,%s,%s,%s,%s) RETURNING *',
              (o['id'], de['id'], para['id'], bool(o.get('vhost_ativo')), quem[:120]))
    arquivo = f"{TF.PASTA_TRANSF}/mover-{o['slug']}-{m['id']}.tgz"
    db.exe(db.PLATAFORMA, 'UPDATE mudancas SET arquivo=%s WHERE id=%s', (arquivo, m['id']))
    m['arquivo'] = arquivo
    _hist(m, f"Mudança pedida por {quem}: de {de['nome']} para {para['nome']}.")
    avancar(m['id'])
    return True, 'Mudança iniciada: acompanhe os passos aqui (cada etapa leva de 1 a 5 minutos).'


def _tarefa(m, tipo):
    return db.um(db.PLATAFORMA, 'SELECT * FROM tarefas WHERE mudanca_id=%s AND tipo=%s ORDER BY id DESC LIMIT 1', (m['id'], tipo))


def _esperar_tarefa(m, no, tipo, seguinte, quem):
    """Cria a tarefa se ainda não existe; avança quando ela termina bem; para com erro se falhar."""
    o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (m['orgao_id'],))
    t = _tarefa(m, tipo)
    if not t:
        TF.criar(no, tipo, {'slug': o['slug'], 'arquivo': m['arquivo']}, quem, mudanca_id=m['id'])
        _hist(m, f"Tarefa \"{tipo}\" enviada ao nó {no['nome']}.")
        return False
    if t['situacao'] == 'ok':
        _hist(m, f"Tarefa \"{tipo}\" concluída no nó {no['nome']}. {t['mensagem']}", situacao=seguinte)
        return True
    if t['situacao'] == 'erro':
        _hist(m, f"Tarefa \"{tipo}\" falhou no nó {no['nome']}: {t['mensagem']}", situacao='erro',
              mensagem=f"{tipo}: {t['mensagem']} Nada foi apagado; o órgão continua no nó {'de origem' if tipo != 'limpar' else 'de destino'}.")
    return False


def _licenca_no(no, slug):
    no = _no(no['id'])
    return slug in (((no or {}).get('relatorio') or {}).get('orgaos') or {})


def _dominio(m, o, no, acao, seguinte, quem):
    """Pede publicar/retirar o domínio e espera o resultado (ativação concluída depois do início desta etapa)."""
    from . import ativacao as AT
    u = AT.ultima(o['id'])
    marca = m['etapa_desde']
    if u and u['acao'] == acao and u['pedido_em'] >= marca:
        if u['situacao'] in ('no_ar', 'desativado'):
            _hist(m, f"Domínio {o['dominio']}: {'publicado' if acao == 'ativar' else 'fora do ar'} no nó {no['nome']}.", situacao=seguinte)
            return True
        if u['situacao'] == 'erro':
            _hist(m, f"Domínio {o['dominio']}: {u['mensagem']}", situacao='erro', mensagem=f"Domínio: {u['mensagem']}")
        return False
    if u and u['situacao'] in ('pendente', 'processando'):
        return False
    ok, msg = AT.pedir(dict(o, no_id=no['id']), acao, quem)
    _hist(m, f"{'Publicação' if acao == 'ativar' else 'Retirada'} do domínio pedida ao nó {no['nome']}." if ok else f'Domínio: {msg}',
          situacao=None if ok else 'erro', mensagem=None if ok else msg)
    return False


def avancar(mid, quem='gestão (mudança automática)'):
    """Leva a mudança adiante o quanto der agora. Devolve a situação."""
    for _ in range(6):
        m = db.um(db.PLATAFORMA, 'SELECT * FROM mudancas WHERE id=%s', (mid,))
        if not m or m['situacao'] not in ATIVAS:
            return m and m['situacao']
        o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (m['orgao_id'],))
        de, para = _no(m['de_no']), _no(m['para_no'])
        s = m['situacao']
        if s == 'retirando':
            if not o['vhost_ativo']:
                _hist(m, 'Domínio fora do ar no nó de origem.', situacao='exportando')
                continue
            if not _dominio(m, o, de, 'desativar', 'exportando', quem):
                return s
        elif s == 'exportando':
            if not _esperar_tarefa(m, de, 'exportar', 'importando', quem):
                return m['situacao']
        elif s == 'importando':
            if not _esperar_tarefa(m, para, 'importar', 'hospedagem', quem):
                return m['situacao']
        elif s == 'hospedagem':
            db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (para['id'], o['id']))
            _hist(m, f"Hospedagem: o órgão agora é do nó {para['nome']} (o de origem deixa de servi-lo em até 5 minutos).",
                  situacao='publicando' if m['publicar'] else 'concluida')
        elif s == 'publicando':
            if not _licenca_no(para, o['slug']):
                return s  # espera o nó de destino receber a licença (relatório)
            if not _dominio(m, o, para, 'ativar', 'concluida', quem):
                return m['situacao']
        elif s == 'limpando':
            if not _esperar_tarefa(m, de, 'limpar', 'finalizada', quem):
                return m['situacao']
        elif s == 'desfazendo':
            if o['no_id'] == para['id']:
                if o['vhost_ativo']:
                    if not _dominio(m, o, para, 'desativar', 'desfazendo', quem):
                        return s
                    continue
                db.exe(db.PLATAFORMA, 'UPDATE orgaos SET no_id=%s WHERE id=%s', (de['id'], o['id']))
                _hist(m, f"Hospedagem de volta ao nó {de['nome']}.")
                continue
            if not m['publicar']:
                _hist(m, 'Desfeita: o órgão voltou para o nó de origem.', situacao='desfeita'); continue
            if not _licenca_no(de, o['slug']):
                return s
            if not _dominio(m, o, de, 'ativar', 'desfeita', quem):
                return m['situacao']
    return db.um(db.PLATAFORMA, 'SELECT situacao FROM mudancas WHERE id=%s', (mid,))['situacao']


def avancar_todas():
    n = 0
    for m in db.todos(db.PLATAFORMA, 'SELECT id FROM mudancas WHERE situacao = ANY(%s) ORDER BY id', (list(ATIVAS),)):
        try:
            avancar(m['id']); n += 1
        except Exception as e:  # uma mudança com problema não trava as outras
            db.exe(db.PLATAFORMA, 'UPDATE mudancas SET mensagem=%s WHERE id=%s', (f'{type(e).__name__}: {str(e)[:200]}', m['id']))
    return n


def limpar(oid, quem):
    m = ativa(oid)
    if not m or m['situacao'] != 'concluida':
        return False, 'Só dá para limpar uma mudança concluída.'
    _hist(m, f'Limpeza da origem pedida por {quem}.', situacao='limpando')
    avancar(m['id'], quem)
    return True, 'Limpeza pedida: o nó de origem guarda uma cópia do banco e apaga o resto do órgão.'


def desfazer(oid, quem):
    m = ativa(oid)
    if not m or m['situacao'] not in ('concluida', 'erro'):
        return False, 'Só dá para desfazer uma mudança concluída (antes da limpeza) ou parada com erro.'
    o = db.um(db.PLATAFORMA, 'SELECT no_id FROM orgaos WHERE id=%s', (oid,))
    if m['situacao'] == 'erro' and o['no_id'] == m['de_no']:
        _hist(m, f'Encerrada por {quem}: o órgão continua no nó de origem.', situacao='cancelada')
        return True, 'Mudança encerrada; o órgão continua no nó de origem. Se o domínio estava no ar, publique de novo.'
    _hist(m, f'Desfazer pedido por {quem}.', situacao='desfazendo')
    avancar(m['id'], quem)
    return True, 'Desfazendo: o órgão volta para o nó de origem (os dados de lá continuam intactos).'
