"""Worker: roda as coletas de dados em horários fixos (sem dependências extras)."""
import time, traceback
from datetime import datetime
from . import db
from .coletores import fiorilli, siconfi

AGENDA = [
    # (nome, função, a cada N minutos, só entre estas horas)
    ('Fiorilli: emendas impositivas', fiorilli.coletar_emendas, 60, range(7, 20)),
    ('Siconfi: RGF do Legislativo', siconfi.coletar_rgf_camara, 24 * 60, range(0, 24)),
]

def registrar(fonte, orgao, ok, n, msg):
    db.exe(db.PLATAFORMA, 'INSERT INTO coletas (orgao_slug, fonte, fim, ok, registros, mensagem) VALUES (%s,%s,now(),%s,%s,%s)', (orgao, fonte, ok, n, (msg or '')[:500]))

def rodar(nome, fn):
    try:
        orgao, n, msg = fn()
        registrar(nome, orgao, True, n, msg)
        print(datetime.now(), 'OK', nome, n, msg, flush=True)
    except Exception as e:
        registrar(nome, None, False, 0, f'{type(e).__name__}: {e}')
        print(datetime.now(), 'FALHA', nome, traceback.format_exc(), flush=True)

def main():
    ultimo = {}
    print('worker iniciado', flush=True)
    while True:
        agora = datetime.now()
        for nome, fn, cada, horas in AGENDA:
            if agora.hour in horas and (nome not in ultimo or (agora - ultimo[nome]).total_seconds() >= cada * 60):
                rodar(nome, fn)
                ultimo[nome] = agora
        time.sleep(60)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'uma-vez':
        for nome, fn, _, _ in AGENDA:
            rodar(nome, fn)
    else:
        main()
