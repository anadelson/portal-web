# Fase 4: coletores, telas, exportação e LGPD — SEM internet, a partir das amostras salvas na descoberta.
# Rode só contra banco de TESTE já provisionado:  TESTE=1 AMOSTRAS=/srv/amostras DATA_SIMULADA=2026-11-06 PYTHONPATH=. python tests/teste_transparencia.py
import copy, csv, io, json, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import db, worker
from app.coletores import fiorilli, pncp, siconfi, tcesp, comum

A = Path(os.environ.get('AMOSTRAS', '/srv/amostras'))
erros = []
def falha(m): erros.append(m)
def amostra(nome):
    return copy.deepcopy(json.loads((A / f'{nome}.json').read_text(encoding='utf-8')).get('amostra', []))

# ---------- dados de entrada: amostras + linhas sintéticas com CPF (devem sumir) ----------
CPF_FALSO = '123.456.789-09'
def emp_extra():
    base = dict(amostra('empenhos')[0])
    base.update({'PKEMP': '999999', 'CODIGO': '9999', 'NOMEFOR': 'FULANO DE TAL 12345678909', 'CPFFORMATADO': CPF_FALSO, 'TPEM': 'OR', 'VINCODIGONOME': '', 'EMPENHADO': '10', 'LIQUIDADO': '0', 'PAGO': '0'})
    return base
def fake(fonte, url, params=None, **kw):
    p = params or {}
    if 'pncp' in url:
        it = amostra('pncp_busca'); return {'items': it, 'total': len(it)}
    if 'tesouro' in url:
        if url.endswith('extrato_entregas'): return {'items': amostra('siconfi_entregas')}
        if url.endswith('rreo'): return {'items': amostra('siconfi_rreo14') if str(p.get('an_exercicio')) == '2025' and str(p.get('nr_periodo')) == '6' else []}
        if url.endswith('rgf'):
            if str(p.get('an_exercicio')) == '2026' and str(p.get('nr_periodo')) == '2':
                return {'items': amostra('siconfi_rgf_leg' if p.get('co_poder') == 'L' else 'siconfi_rgf_exe')}
            return {'items': []}
    if 'tce.sp' in url:
        m = url.rstrip('/').split('/')[-1]
        return amostra('tcesp_receitas_2025_01') if m == '1' else amostra('tcesp_receitas_2025_12') if m == '12' else []
    l = p.get('Listagem')
    if l == 'DespesasGerais':
        d = json.loads((A / 'empenhos.json').read_text(encoding='utf-8'))
        rows = {r['PKEMP']: r for r in d['amostra'] + d.get('amostra_emendas', [])}
        return list(rows.values()) + [emp_extra()]
    if l in ('EmpenhosDespesas_Liquidado_PorNumeroEmpenho', 'EmpenhosDespesas_Pago_PorNumeroEmpenho'):
        det = json.loads((A / 'empenho_detalhes.json').read_text(encoding='utf-8'))
        return det.get(l, []) if str(p.get('intNumeroEmpenho')) == '426' else []
    if l == 'DespesasporExigibilidade':
        rows = amostra('ordem_cronologica' if p.get('strTipoLista') == '1' else 'ordem_cronologica_t2')
        if p.get('strTipoLista') == '1':
            pf = dict(rows[0]); pf.update({'CGC': CPF_FALSO, 'FORNECEDOR': 'PESSOA FISICA TESTE', 'PKEMP': '777', 'VAPAG': '1'}); rows.append(pf)
        return rows
    if l == 'DespesasRestosPagar':
        return amostra('restos_pagar') + [{'EMPRESA': '2', 'CODIGO': '1', 'DESCRICAO': f'{CPF_FALSO} FULANA PF', 'EMPENHADO': '5', 'LIQUIDADO': '5', 'PAGO': '0'}]
    if l == 'Servidores':
        rows = amostra('servidores'); x = dict(rows[0]); x.update({'REGISTRO': '999', 'NOME': 'SERVIDOR TESTE', 'NOME_SOCIAL': ' ', 'CPF': '12345678909', 'CPFFORMATADO': CPF_FALSO, 'DESCONTOS': '999,99'}); return rows + [x]
    nome = {'ReceitaOrcamentaria': 'receitas', 'DespesasPorUnidade': 'despesas_unidade', 'Diarias': 'diarias', 'Licitacoes': 'licitacoes', 'Contratos': 'contratos',
            'Transf': 'transferencias', 'CadEmendasImpositivas': 'emendas_cad_transf'}.get(l)
    if nome:
        return amostra(nome)
    raise AssertionError(f'chamada inesperada: {url} {p}')
for m in (fiorilli, pncp, siconfi, tcesp):
    m.buscar = fake

# ---------- coleta ----------
fontes = worker.fontes_ativas()
if {(f['slug'], f['fonte']) for f in fontes} < {('pm-bora', 'fiorilli'), ('pm-bora', 'pncp'), ('pm-bora', 'siconfi'), ('pm-bora', 'tcesp'), ('cm-bora', 'fiorilli'), ('cm-bora', 'siconfi')}:
    falha(f'fontes padrão não configuradas: {[(f["slug"], f["fonte"]) for f in fontes]}')
for f in fontes:
    if f['slug'] in ('pm-bora', 'cm-bora'):
        for base, ok, n, msg in worker.rodar(f, f['fonte'], f['params']):
            if not ok: falha(f'coleta {f["slug"]} {f["fonte"]}:{base} falhou: {msg}')
worker.rodar([f for f in fontes if f['slug'] == 'pm-bora' and f['fonte'] == 'fiorilli'][0], 'fiorilli', [f for f in fontes if f['slug'] == 'pm-bora' and f['fonte'] == 'fiorilli'][0]['params'])  # 2ª vez: idempotente

PM, CM = 'bd_pm_bora', 'bd_cm_bora'
for tab, minimo in [('receitas', 90), ('despesas_unidade', 10), ('empenhos', 30), ('diarias', 20), ('restos_pagar', 20), ('ordem_cronologica', 40), ('licitacoes', 40),
                    ('contratos', 20), ('transferencias', 5), ('servidores', 20), ('relatorios_fiscais', 20)]:
    n = db.um(PM, f'SELECT count(*) n FROM {tab}')['n']
    if n < minimo: falha(f'{tab}: só {n} linhas')
n1 = db.um(PM, 'SELECT count(*) n FROM empenhos')['n']
if db.um(PM, "SELECT count(*) n FROM receitas WHERE fonte='tcesp' AND ano=2025")['n'] == 0: falha('TCESP 2025 não gravou')
if db.um(PM, "SELECT count(*) n FROM licitacoes WHERE fonte='pncp'")['n'] == 0: falha('PNCP não gravou')
# LGPD
pat = re.compile(r'\b\d{3}\.?[\dXx*]{3}\.?[\dXx*]{3}-?\d{2}\b')
for banco in (PM, CM):
    for tab in ('receitas', 'despesas_unidade', 'empenhos', 'licitacoes', 'contratos', 'servidores', 'diarias', 'transferencias', 'ordem_cronologica', 'restos_pagar', 'relatorios_fiscais', 'emendas'):
        cols = [c['column_name'] for c in db.todos(banco, "SELECT column_name FROM information_schema.columns WHERE table_name=%s", (tab,))]
        if any('cpf' in c for c in cols): falha(f'{banco}.{tab} tem coluna de CPF: {cols}')
        for r in db.todos(banco, f'SELECT * FROM {tab}'):
            t = ' '.join(str(v) for k, v in r.items() if k not in ('credor_cnpj', 'cnpj', 'chave') and v is not None)
            if pat.search(t): falha(f'CPF gravado em {banco}.{tab}: {pat.search(t).group(0)}'); break
if db.um(PM, "SELECT 1 FROM empenhos WHERE credor ~ '[0-9]{11}' OR credor LIKE '%%12345678909%%'"): falha('dígitos de CPF no nome do credor')
if not db.um(PM, "SELECT 1 FROM empenhos WHERE credor='FULANO DE TAL' AND credor_cnpj=''"): falha('credor pessoa física deveria ficar sem documento')
if db.um(PM, "SELECT 1 FROM ordem_cronologica WHERE fornecedor='PESSOA FISICA TESTE'"): falha('pessoa física na ordem cronológica')
if db.um(PM, "SELECT 1 FROM restos_pagar WHERE credor LIKE '%%FULANA PF%%'"): falha('pessoa física nos restos a pagar')
# emendas da Câmara (cadastro + empenhos da Prefeitura pela API)
e22 = db.um(CM, "SELECT * FROM emendas WHERE numero='22/2026'")
if not e22 or float(e22['pago_empenho'] or 0) != 1160 or e22['conferencia'] != 'conferido' or not e22['detalhe'] or not e22['detalhe']['empenhos'][0]['pag']:
    falha(f'emenda 22 sem execução correta: {e22 and (e22["pago_empenho"], e22["conferencia"])}')
if db.um(CM, 'SELECT count(*) n FROM emendas')['n'] < 29: falha('cadastro de emendas incompleto')
if db.um(CM, "SELECT count(*) n FROM transferencias WHERE recebedora NOT ILIKE '%%Câmara%%'")['n']: falha('Câmara gravou transferência de outro órgão')
if not (db.cfg(CM, 'financas') or {}).get('dtp'): falha('financas.dtp da Câmara não atualizado pelo RGF')
num = db.cfg(PM, 'numeros')
if db.um(PM, "SELECT count(*) n FROM servidores WHERE nome=''")['n']: falha('servidor sem nome')
if not num or not num['kpis'] or 'Receita arrecadada' not in num['kpis'][0]['l']: falha(f'números do município não calculados: {num}')

# ---------- telas, exportação e API ----------
pm, cm = TestClient(app, base_url='http://pmbora.localhost'), TestClient(app, base_url='http://cmbora.localhost')
def ok(r, cod=200, txt=None, nome=''):
    if r.status_code != cod or (txt and txt not in r.text): falha(f'{nome}: {r.status_code} {r.text[:200]}')
    return r
ok(pm.get('/transparencia'), txt='Despesas — empenhos', nome='central pm')
for base in ('receitas', 'despesas', 'empenhos', 'licitacoes', 'contratos', 'servidores', 'diarias', 'transferencias', 'ordem-cronologica', 'restos-a-pagar', 'relatorios-fiscais'):
    r = ok(pm.get(f'/transparencia/{base}?ano=2026'), nome='pagina ' + base)
    for t in ('Base legal:', 'Fonte:', 'atualizado em', 'Baixar CSV', 'Baixar JSON'):
        if t not in r.text: falha(f'{base}: falta "{t}"')
    if pat.search(re.sub(r'<[^>]+>', ' ', r.text)): falha(f'CPF exibido em {base}')
    c = ok(pm.get(f'/transparencia/{base}.csv?ano=2026'), nome='csv ' + base)
    if 'text/csv' not in c.headers.get('content-type', ''): falha(f'csv {base} content-type')
    rows = list(csv.reader(io.StringIO(c.text.lstrip('﻿'))))
    j = ok(pm.get(f'/dados/{base}.json?ano=2026'), nome='json ' + base).json()
    if len(rows) - 1 != j['registros_nesta_resposta'] or j['total_registros'] != len(j['registros']) or not j['base_legal'] or 'atualizado_em' not in j:
        falha(f'{base}: csv/json inconsistentes ({len(rows) - 1} × {j["registros_nesta_resposta"]})')
# filtros
todos = pm.get('/dados/empenhos.json?ano=2026').json()['total_registros']
cred = db.um(PM, "SELECT credor FROM empenhos WHERE credor<>'' ORDER BY id LIMIT 1")['credor']
f1 = pm.get('/dados/empenhos.json', params={'ano': 2026, 'credor': cred[:8]}).json()
if not (0 < f1['total_registros'] <= todos) or any(cred[:8].lower() not in x['credor'].lower() for x in f1['registros']): falha('filtro de credor')
mes = db.um(PM, 'SELECT extract(month from data)::int m FROM empenhos WHERE data IS NOT NULL LIMIT 1')['m']
f2 = pm.get('/dados/empenhos.json', params={'ano': 2026, 'mes': mes}).json()
if any(int(x['data'][5:7]) != mes for x in f2['registros']): falha('filtro de mês')
f3 = pm.get('/dados/receitas.json', params={'ano': 2026}).json()
soma = db.um(PM, "SELECT sum(arrecadado) v FROM receitas WHERE ano=2026 AND soma")['v']
if abs(f3['totais']['arrecadado'] - float(soma)) > .01: falha('total de receitas sem dupla contagem')
ok(pm.get("/dados/empenhos.json?credor=%27%3B%20DROP%20TABLE%20empenhos%3B--"), nome='injeção no filtro')
if db.um(PM, 'SELECT count(*) n FROM empenhos')['n'] != n1: falha('tabela alterada pelo filtro')
ok(pm.get('/transparencia/empenhos?pagina=2&ano=2026'), nome='paginação')
ok(pm.get('/transparencia/nao-existe'), 404, nome='base inexistente')
ok(pm.get('/dados-abertos'), txt='/dados/', nome='dados abertos')
ok(pm.get('/'), txt='Borá em números', nome='bloco números')
ok(pm.get('/'), txt='Receita arrecadada', nome='kpi receita')
# Câmara: só as bases do Legislativo
ok(cm.get('/transparencia'), txt='Repasses e transferências', nome='central cm')
ok(cm.get('/transparencia/empenhos'), 404, nome='cm sem empenhos')
ok(cm.get('/transparencia/transferencias'), txt='CÂMARA', nome='cm duodécimo')
ok(cm.get('/emendas'), txt='Liquidado', nome='cm emendas')
ok(cm.get('/emendas/2026/22'), txt='Pagamento', nome='caminho com pagamento')
# falha de fonte não derruba o portal
def quebra(*a, **k): raise comum.httpx.ConnectError('fonte fora do ar (teste)')
fiorilli.buscar = quebra
f = [f for f in fontes if f['slug'] == 'pm-bora' and f['fonte'] == 'fiorilli'][0]
res = worker.rodar(f, 'fiorilli', f['params'])
if any(ok_ for _, ok_, _, _ in res): falha('coleta deveria falhar')
if db.um(PM, 'SELECT count(*) n FROM empenhos')['n'] != n1: falha('falha da fonte apagou dados')
ok(pm.get('/transparencia/empenhos'), txt='última coleta válida', nome='aviso de falha')
ok(pm.get('/'), nome='home com fonte fora')
g = TestClient(app, base_url='http://gestao.localhost')
r = g.get('/login'); t = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
g.post('/login', data={'csrf': t, 'email': 'gestor@gestao.localhost', 'senha': os.environ.get('SENHA_INICIAL_GESTOR', 'gestor123')})
r = g.get('/senha'); m = re.search(r'name="csrf" value="([^"]+)"', r.text)
if m: g.post('/senha', data={'csrf': m.group(1), 'atual': 'gestor123', 'nova': 'gestorforte1234', 'conf': 'gestorforte1234'})
ok(g.get('/log'), txt='Situação por fonte', nome='console situação')
ok(g.get('/log'), txt='fonte(s) com falha', nome='console destaca falha')
print('ERROS:', len(erros)); print('\n'.join(erros))
sys.exit(1 if erros else 0)
