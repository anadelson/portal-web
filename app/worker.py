"""Worker: roda as coletas de cada órgão conforme as fontes configuradas (tabela `fontes`) e a frequência de cada uma.

  python -m app.worker           # laço contínuo
  python -m app.worker uma-vez   # roda todas as fontes uma vez e sai
A falha de uma fonte (ou de uma base) só é registrada em `coletas`; o portal continua com a última coleta válida."""
import sys, time, traceback
from datetime import datetime
from . import config, db
from .coletores import fiorilli, pncp, siconfi, tcesp, numeros, comum

MODULOS = {'fiorilli': fiorilli, 'pncp': pncp, 'siconfi': siconfi, 'tcesp': tcesp}
# fonte -> (a cada N minutos, horas permitidas)
FREQ = {'fiorilli': (60, range(7, 20)), 'pncp': (360, range(0, 24)), 'siconfi': (24 * 60, range(0, 24)), 'tcesp': (24 * 60, range(0, 24))}

def fontes_ativas():
    return db.todos(db.PLATAFORMA, 'SELECT o.*, f.fonte, f.params FROM fontes f JOIN orgaos o ON o.id=f.orgao_id WHERE f.ativo AND o.ativo ORDER BY o.id, f.fonte')

def tcesp_pendente(o, p):
    """TCESP: mensal (dia 20) ou enquanto faltar algum ano configurado."""
    if config.hoje().day == 20:
        return True
    return any(not db.um(o['banco'], "SELECT 1 FROM receitas WHERE fonte='tcesp' AND ano=%s LIMIT 1", (a,)) for a in p.get('anos', []))

def rodar(o, fonte, p):
    inicio = datetime.now()
    try:
        res = MODULOS[fonte].coletar(o, p)
    except Exception as e:
        res = [(fonte, False, 0, f'{type(e).__name__}: {e}')]
        traceback.print_exc()
    for base, ok, n, msg in res:
        comum.registrar(o['slug'], f'{fonte}:{base}', ok, n, msg, inicio)
        print(datetime.now(), 'OK' if ok else 'FALHA', o['slug'], f'{fonte}:{base}', n, msg, flush=True)
    if o['tipo'] == 'executivo' and fonte in ('fiorilli', 'siconfi'):
        try:
            numeros.atualizar(o)
        except Exception:
            traceback.print_exc()
    return res

def ultimas_execucoes():
    """Lembra a última coleta de cada fonte (no banco), para um reinício não repetir as fontes à toa."""
    r = {}
    for x in db.todos(db.PLATAFORMA, "SELECT orgao_slug, split_part(fonte, ':', 1) f, max(inicio) t FROM coletas WHERE fonte LIKE '%%:%%' GROUP BY 1, 2"):
        r[(x['orgao_slug'], x['f'])] = x['t'].astimezone().replace(tzinfo=None)
    return r

def diario_tick(agora):
    """Rotina do Diário Oficial (Lei 910/2026): edição sem atos, alerta das 16h30 e publicação das 17h, só com edição assinada."""
    from . import diario_servico as DS
    from .web import modulos_do_orgao
    for o in db.todos(db.PLATAFORMA, "SELECT * FROM orgaos WHERE ativo AND tipo='executivo'"):
        try:
            if not modulos_do_orgao(o).get('diario'):
                continue
            for r in DS.tick(o, agora):
                comum.registrar(o['slug'], 'diario:rotina', True, 1, r)
                print(agora, 'DIÁRIO', o['slug'], r, flush=True)
        except Exception as e:
            comum.registrar(o['slug'], 'diario:rotina', False, 0, f'{type(e).__name__}: {e}')
            traceback.print_exc()

def main():
    ultimo = ultimas_execucoes()
    print('worker iniciado', flush=True)
    while True:
        agora = datetime.now()
        try:
            for f in fontes_ativas():
                cada, horas = FREQ[f['fonte']]
                k = (f['slug'], f['fonte'])
                if agora.hour not in horas or (k in ultimo and (agora - ultimo[k]).total_seconds() < cada * 60):
                    continue
                if f['fonte'] == 'tcesp' and not tcesp_pendente(f, f['params']):
                    ultimo[k] = agora
                    continue
                rodar(f, f['fonte'], f['params'])
                ultimo[k] = agora
        except Exception:
            traceback.print_exc()
        diario_tick(datetime.now())
        time.sleep(60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'uma-vez':
        so = set(sys.argv[2:])  # opcional: só estas fontes (ex.: uma-vez fiorilli pncp)
        for f in fontes_ativas():
            if not so or f['fonte'] in so:
                rodar(f, f['fonte'], f['params'])
        db.fechar()
    else:
        main()
