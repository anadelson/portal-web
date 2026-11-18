"""Painel: autoavaliação PNTP da matriz inteira (Prefeitura e Câmara), com índice estimado, nível e marcação do controle interno.
O cálculo fica em pntp.py; as medições automáticas, em pntp_auto.py."""
import csv, io
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from . import pntp as P
from .admin import T
from .web import ler_form, ir, exige, auditar

r = APIRouter(prefix='/_a')


def _rotas(request):
    return {getattr(x, 'path', '') for x in request.app.routes}


@r.get('/pntp')
def pntp(request: Request, dim: str = '', sit: str = ''):
    u = exige(request, 'pntp_ver')
    o = request.state.orgao
    av = P.avaliar(o, rotas=_rotas(request))
    linhas = av['linhas']
    if dim:
        linhas = [l for l in linhas if l['c']['dimensao'] == dim]
    if sit == 'falta':
        linhas = [l for l in linhas if l['nota'] < 0.999]
    elif sit == 'marcar':
        linhas = [l for l in linhas if l['origem'] in ('sem', 'marcacao')]
    elif sit == 'essenciais':
        linhas = [l for l in linhas if l['c']['classe'] == 'essencial']
    grupos = {}
    for l in linhas:
        grupos.setdefault(l['c']['dimensao'], []).append(l)
    return T('pntp', request, u, av=av, grupos=grupos, dims=[d for d in av['por_dim']], dim=dim, sit=sit, P=P)


@r.post('/pntp')
async def pntp_marcar(request: Request):
    u = exige(request, 'pntp_marcar')
    o = request.state.orgao
    f = await ler_form(request)
    c = P.por_id(f.get('criterio', ''))
    if not c or o['tipo'] not in c['aplica']:
        raise HTTPException(404, 'Critério não encontrado.')
    volta = f"/admin/pntp?dim={c['dimensao']}#c-{c['id'].replace('.', '-')}"
    av = {l['c']['id']: l for l in P.avaliar(o, rotas=_rotas(request))['linhas']}
    if av[c['id']]['origem'] == 'auto':
        return ir(volta, 'Este critério é medido automaticamente pelo portal; não há o que marcar.', request)
    if f.get('acao') == 'apagar':
        P.apagar_marcacao(o['banco'], c['id'])
        auditar(request, f"PNTP {P.CICLO}: marcação do critério {c['id']} apagada")
        return ir(volta, f"Marcação do critério {c['id']} apagada.", request)
    itens = {i: f.get(f'item_{i}') == '1' for i in P.ITENS if c['itens'][i]}
    erros = P.validar_marcacao(c, itens, f.get('link'))
    if erros:
        return ir(volta, f"Critério {c['id']} não foi marcado: " + ' '.join(erros), request)
    P.gravar_marcacao(o['banco'], c['id'], itens, f.get('link'), f.get('obs'), u['nome'])
    marcados = ', '.join(P.NOME_ITEM[i] for i, v in itens.items() if v) or 'não atende'
    auditar(request, f"PNTP {P.CICLO}: critério {c['id']} marcado ({marcados})")
    return ir(volta, f"Critério {c['id']} marcado.", request)


@r.get('/pntp.csv')
def pntp_csv(request: Request):
    """Planilha da autoavaliação, na ordem da matriz, para apoiar o preenchimento no Avalia (separador ";", UTF-8 com BOM)."""
    exige(request, 'pntp_ver')
    o = request.state.orgao
    av = P.avaliar(o, rotas=_rotas(request))
    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(['Critério', 'Dimensão', 'Classificação', 'Pergunta'] + [P.NOME_ITEM[i] for i in P.ITENS] + ['Nota do critério (%)', 'Origem', 'Evidência', 'Detalhe'])
    for l in av['linhas']:
        c = l['c']
        vals = ['Não se aplica' if not c['itens'][i] else ('Sim' if l['itens'] and l['itens'].get(i) else 'Não') for i in P.ITENS]
        origem = {'auto': 'Medido pelo portal', 'marcacao': f"Marcado por {l['marcacao']['por']}" if l['marcacao'] else 'Marcado', 'sem': 'Sem marcação'}[l['origem']]
        link = l['link'] or ''
        if link.startswith('/'):
            link = f"https://{o['dominio']}{link}"
        w.writerow([c['id'], c['dimensao'], P.NOME_CLASSE[c['classe']], c['texto']] + vals + [f"{100 * l['nota']:.0f}", origem, link, l['det'] or l['dica']])
    nome = f"autoavaliacao-pntp-{P.CICLO}-{o['slug']}.csv"
    return Response('﻿' + out.getvalue(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': f'attachment; filename="{nome}"'})
