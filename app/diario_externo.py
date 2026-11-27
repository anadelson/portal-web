"""Diário Oficial em plataforma de terceiros (27/11/2026): sincronização das fontes e leitura para o portal.

A sincronização pede ao adaptador (app/diario_fontes) a lista de edições e grava no banco do órgão, uma linha por
(fonte, id_externo): rodar duas vezes não duplica nada e só conta como "atualizada" a edição que mudou. O portal só lista
as edições e o link abre a edição na plataforma; desativar a fonte para a sincronização, mas o histórico continua visível.
Depois de 3 falhas seguidas, um alerta aparece no painel do Diário.

Uso (dentro do contêiner):  python -m app.diario_externo sincronizar [--orgao=pm-bora] [--fonte=ID] [--desde=AAAA-MM-DD] [--completo]"""
import sys
from datetime import date, datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from . import db
from . import diario_fontes as DF

FALHAS_ALERTA = 3


def fontes(b, so_ativas=False):
    return db.todos(b, 'SELECT * FROM diario_fontes' + (' WHERE ativa' if so_ativas else '') + ' ORDER BY ativa DESC, id')


def plataforma(tipo):
    c = DF.ADAPTADORES.get(tipo)
    return c.plataforma if c else tipo


def pendentes(b, agora=None):
    """Fontes ativas cuja última sincronização passou do intervalo (ou que nunca sincronizaram)."""
    agora = agora or datetime.now(timezone.utc)
    return [f for f in fontes(b, so_ativas=True)
            if not f['ultima_sincronizacao_em'] or f['ultima_sincronizacao_em'] <= agora - timedelta(minutes=f['intervalo_min'])]


def sincronizar(b, fonte, desde=None, completo=False, http=None):
    """Sincroniza uma fonte. Devolve {'novas', 'atualizadas', 'erro'}; nunca levanta exceção da plataforma."""
    log = db.exe(b, 'INSERT INTO diario_sincronizacoes (fonte_id) VALUES (%s) RETURNING id', (fonte['id'],))['id']
    novas = atualizadas = 0
    try:
        ad = DF.criar(fonte['tipo'], fonte['config'], http)
        eds = ad.listar_edicoes(desde=None if completo else desde)
        for e in eds:
            r = db.exe(b, """INSERT INTO diario_externo_edicoes (fonte_id, id_externo, numero, data, extra, url, paginas) VALUES (%s,%s,%s,%s,%s,%s,%s)
                             ON CONFLICT (fonte_id, id_externo) DO UPDATE SET numero=EXCLUDED.numero, data=EXCLUDED.data, extra=EXCLUDED.extra,
                                    url=EXCLUDED.url, paginas=EXCLUDED.paginas, atualizado_em=now()
                             WHERE (diario_externo_edicoes.numero, diario_externo_edicoes.data, diario_externo_edicoes.extra, diario_externo_edicoes.url,
                                    diario_externo_edicoes.paginas) IS DISTINCT FROM (EXCLUDED.numero, EXCLUDED.data, EXCLUDED.extra, EXCLUDED.url, EXCLUDED.paginas)
                             RETURNING (xmax = 0) AS nova""",
                       (fonte['id'], e.id_externo, e.numero, e.data, e.extra, e.url, e.paginas))
            if r:
                novas += r['nova']
                atualizadas += not r['nova']
        msg = f'{len(eds)} edição(ões) na plataforma; {novas} nova(s), {atualizadas} atualizada(s)'
        db.exe(b, "UPDATE diario_fontes SET config=%s, ultima_sincronizacao_em=now(), ultimo_erro='', falhas_seguidas=0, atualizado_em=now() WHERE id=%s",
               (Jsonb(ad.config), fonte['id']))
        db.exe(b, 'UPDATE diario_sincronizacoes SET finalizado_em=now(), novas=%s, atualizadas=%s, mensagem=%s WHERE id=%s', (novas, atualizadas, msg, log))
        return {'novas': novas, 'atualizadas': atualizadas, 'erro': ''}
    except DF.ErroFonte as e:
        erro = str(e)
    except Exception as e:  # erro inesperado: registra só o tipo (sem detalhe interno no painel)
        erro = f'erro inesperado ({type(e).__name__})'
    f = db.exe(b, 'UPDATE diario_fontes SET ultima_sincronizacao_em=now(), ultimo_erro=%s, falhas_seguidas=falhas_seguidas+1, atualizado_em=now() WHERE id=%s RETURNING falhas_seguidas',
               (erro[:300], fonte['id']))
    db.exe(b, 'UPDATE diario_sincronizacoes SET finalizado_em=now(), novas=%s, atualizadas=%s, erros=1, mensagem=%s WHERE id=%s', (novas, atualizadas, erro[:300], log))
    if f and f['falhas_seguidas'] == FALHAS_ALERTA:
        db.exe(b, 'INSERT INTO diario_alertas (tipo, mensagem) VALUES (%s,%s)',
               ('fonte_externa', f"Diário em {fonte['nome']}: {FALHAS_ALERTA} falhas seguidas na sincronização. Último erro: {erro[:200]}"))
    return {'novas': novas, 'atualizadas': atualizadas, 'erro': erro}


def tick(b, agora=None):
    """Worker: sincroniza as fontes vencidas do órgão. Devolve as mensagens do que rodou."""
    out = []
    for f in pendentes(b, agora):
        r = sincronizar(b, f)
        out.append(f"{f['nome']}: " + (f"falhou: {r['erro']}" if r['erro'] else f"{r['novas']} nova(s), {r['atualizadas']} atualizada(s)"))
    return out


def edicoes(b, limite=None, ano=None):
    """Edições externas para o portal (todas as fontes, ativas ou não: o histórico é permanente)."""
    sql = """SELECT e.*, f.nome fonte_nome, f.tipo fonte_tipo, f.nova_aba FROM diario_externo_edicoes e JOIN diario_fontes f ON f.id=e.fonte_id"""
    p = []
    if ano:
        sql += ' WHERE e.data >= %s AND e.data < %s'
        p += [date(ano, 1, 1), date(ano + 1, 1, 1)]
    sql += ' ORDER BY e.data DESC, e.id DESC' + (' LIMIT %s' if limite else '')
    if limite:
        p.append(limite)
    return [dict(x, externo=True, letra='', modo_teste=False, sem_atos=False) for x in db.todos(b, sql, tuple(p))]


def misturar(nativas, externas, limite=None):
    """Edições do Diário nativo e das plataformas numa lista só, da mais recente para a mais antiga."""
    tudo = [dict(x, externo=False) for x in nativas] + list(externas)
    num = lambda x: int(str(x['numero'])) if str(x['numero']).isdigit() else 0
    tudo.sort(key=lambda x: (x['data'], num(x), x.get('letra') or '', bool(x.get('extra'))), reverse=True)
    return tudo[:limite] if limite else tudo


def principal():
    args = dict(a[2:].split('=', 1) if '=' in a else (a[2:], '1') for a in sys.argv[2:] if a.startswith('--'))
    if len(sys.argv) < 2 or sys.argv[1] != 'sincronizar':
        sys.exit(__doc__)
    from . import orgaos
    desde = date.fromisoformat(args['desde']) if args.get('desde') else None
    for o in orgaos.todos():
        if args.get('orgao') and o['slug'] != args['orgao']:
            continue
        for f in fontes(o['banco'], so_ativas=not args.get('fonte')):
            if args.get('fonte') and str(f['id']) != args['fonte']:
                continue
            r = sincronizar(o['banco'], f, desde=desde, completo=bool(args.get('completo')))
            print(o['slug'], f"fonte {f['id']} ({f['nome']}):", f"falhou: {r['erro']}" if r['erro'] else f"{r['novas']} nova(s), {r['atualizadas']} atualizada(s)")


if __name__ == '__main__':
    principal()
