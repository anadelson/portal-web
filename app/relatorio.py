"""Relatório técnico do nó para a gestão — separação gestão × portais, etapa A4 (11/11/2026).

O nó envia (POST /api/no/relatorio, com o token) a cada 5 minutos — a cada minuto enquanto houver publicação de domínio
em andamento: versão, IP público, espaço em disco, situação das licenças, a última execução de cada coleta por órgão,
ordens com erro e os passos das ativações de domínio. SEM dados pessoais (nada de cidadão, servidor, usuário ou credencial).

A gestão guarda o relatório no cadastro do nó (Nós e licenças) e, com os passos das ativações, atualiza o pedido de domínio
feito no console — do mesmo jeito que o ativador desta VPS faz hoje."""
import json, shutil
from datetime import datetime, timezone
from psycopg.types.json import Jsonb
from . import config, db

MAX_BYTES = 256 * 1024

def _iso(d):
    return d.isoformat() if d else None

# ---------- nó ----------
def montar():
    from . import orgaos, licenca, ativacao
    import os
    try:
        u = shutil.disk_usage(config.DADOS_DIR if os.path.isdir(config.DADOS_DIR) else '/')
        disco = {'total_gb': round(u.total / 2**30, 1), 'livre_gb': round(u.free / 2**30, 1)}
    except OSError:
        disco = {}
    rel = {'v': 1, 'versao': licenca.VERSAO_APP(), 'ip': config.env('VPS_IP') or ativacao.vps_ip(), 'disco': disco,
           'pasta': config.env('NO_PASTA'), 'instancia': config.INSTANCIA,   # onde o nó está instalado na VPS (registrado na gestão)
           'gerado_em': datetime.now(timezone.utc).isoformat(), 'orgaos': {}, 'ativacoes': [], 'dominios': []}
    for o in orgaos.todos(ativos=False):
        c = db.um(db.LOCAL, 'SELECT valida_ate, recebida_em FROM licencas_cache WHERE orgao_id=%s', (o['id'],))
        col = db.todos(db.LOCAL, """SELECT DISTINCT ON (fonte) fonte, ok, inicio, registros, mensagem FROM coletas WHERE orgao_slug=%s
                                    AND inicio > now() - interval '7 days' ORDER BY fonte, id DESC""", (o['slug'],))
        f24 = db.um(db.LOCAL, "SELECT count(*) n FROM coletas WHERE orgao_slug=%s AND NOT ok AND inicio > now() - interval '24 hours'", (o['slug'],))['n']
        rel['orgaos'][o['slug']] = {'id': o['id'], 'licenca_valida_ate': _iso(c and c['valida_ate']), 'licenca_recebida_em': _iso(c and c['recebida_em']),
                                    'licenca_valida': bool(licenca.vigente(o)), 'falhas_24h': f24, 'convites_pendentes': _pendentes(o),
                                    'coletas': [{'fonte': x['fonte'], 'ok': x['ok'], 'inicio': _iso(x['inicio']), 'registros': x['registros'], 'mensagem': (x['mensagem'] or '')[:160]} for x in col[:40]]}
    from . import tarefas
    rel['tarefas'] = tarefas.para_relatorio()
    try:
        rel['ativacoes'] = [{'id': a['id'], 'situacao': a['situacao'], 'passos': a['passos'], 'mensagem': a['mensagem'], 'concluido_em': _iso(a['concluido_em'])}
                            for a in db.todos(db.LOCAL, "SELECT * FROM ativacoes WHERE pedido_em > now() - interval '30 days' ORDER BY id DESC LIMIT 20")]
        rel['dominios'] = [r['dominio'] for r in db.todos(db.LOCAL, 'SELECT dominio FROM dominios_publicados ORDER BY dominio')]
        rel['ordens_com_erro'] = db.um(db.LOCAL, "SELECT count(*) n FROM ordens_feitas WHERE NOT ok AND em > now() - interval '7 days'")['n']
    except Exception:
        pass  # banco local ainda sem as tabelas (antes do provision): manda o resto
    return rel

def _pendentes(o):
    from . import convites
    try:
        return convites.pendentes(o['banco'])
    except Exception:
        return []

def com_pressa():
    """Há publicação de domínio em andamento (ou recém-concluída)? Então o relatório vai a cada minuto."""
    try:
        from . import tarefas
        return tarefas.em_andamento() or bool(db.um(db.LOCAL, "SELECT 1 FROM ativacoes WHERE situacao IN ('pendente','processando') OR concluido_em > now() - interval '10 minutes' LIMIT 1"))
    except Exception:
        return False

def enviar_na_gestao(rel):
    import httpx
    r = httpx.post(config.GESTAO_URL.rstrip('/') + '/api/no/relatorio', json=rel, timeout=30,
                   headers={'Authorization': f'Bearer {config.NO_TOKEN}', 'User-Agent': config.USER_AGENT})
    if r.status_code != 200:
        raise RuntimeError(f'gestão respondeu HTTP {r.status_code}')
    return r.json()

def enviar():
    if config.PAPEL != 'no':
        return 'papel não é "no": nada a enviar'
    if not (config.GESTAO_URL and config.NO_TOKEN):
        return 'faltam GESTAO_URL ou NO_TOKEN no .env do nó'
    d = enviar_na_gestao(montar())
    return f"relatório entregue ({d.get('ativacoes', 0)} ativação(ões) atualizada(s) na gestão)"

# ---------- gestão ----------
def receber(no, rel):
    """Guarda o relatório e atualiza os pedidos de domínio dos órgãos DESTE nó. Devolve quantas ativações mudaram."""
    if len(json.dumps(rel, default=str)) > MAX_BYTES:
        raise ValueError('relatório grande demais')
    db.exe(db.PLATAFORMA, 'UPDATE nos SET relatorio=%s, relatorio_em=now(), ultimo_contato=now(), versao=%s WHERE id=%s',
           (Jsonb(dict({k: v for k, v in rel.items() if k not in ('ativacoes', 'tarefas')}, executa_tarefas='tarefas' in rel)), str(rel.get('versao', ''))[:40], no['id']))
    from . import tarefas, mudancas
    nt = tarefas.receber(no, rel.get('tarefas'))
    from . import convites
    for slug, info in (rel.get('orgaos') or {}).items():  # convite usado no nó: o e-mail sai da lista de pendentes
        o = db.um(db.PLATAFORMA, 'SELECT id, no_id FROM orgaos WHERE slug=%s', (slug,))
        if o and o['no_id'] == no['id'] and isinstance(info, dict) and isinstance(info.get('convites_pendentes'), list):
            convites.marcar_usados(o['id'], [str(e) for e in info['convites_pendentes']][:50])
    n = 0
    for a in rel.get('ativacoes') or []:
        if not isinstance(a, dict) or not str(a.get('id', '')).isdigit() or a.get('situacao') not in ('pendente', 'processando', 'no_ar', 'desativado', 'erro'):
            continue
        atual = db.um(db.PLATAFORMA, 'SELECT a.*, o.no_id, o.nome FROM ativacoes a JOIN orgaos o ON o.id=a.orgao_id WHERE a.id=%s', (int(a['id']),))
        if not atual or atual['no_id'] != no['id']:
            continue  # pedido de outro nó ou de órgão desta VPS: ignorado
        passos = [p for p in (a.get('passos') or []) if isinstance(p, dict)][:30]
        if atual['situacao'] == a['situacao'] and atual['passos'] == passos:
            continue
        db.exe(db.PLATAFORMA, 'UPDATE ativacoes SET situacao=%s, passos=%s, mensagem=%s, concluido_em=%s WHERE id=%s',
               (a['situacao'], Jsonb(passos), str(a.get('mensagem', ''))[:500], a.get('concluido_em'), atual['id']))
        if a['situacao'] in ('no_ar', 'desativado') and atual['situacao'] != a['situacao']:
            db.exe(db.PLATAFORMA, 'UPDATE orgaos SET vhost_ativo=%s WHERE id=%s', (a['situacao'] == 'no_ar', atual['orgao_id']))
        if a['situacao'] in ('no_ar', 'desativado', 'erro') and atual['situacao'] != a['situacao']:
            db.exe(db.PLATAFORMA, 'INSERT INTO log_console (quem, acao) VALUES (%s,%s)',
                   (f"ativador do nó {no['nome']}", f"Domínio {atual['dominio']}: {atual['acao']} → {a['situacao']}. {str(a.get('mensagem', ''))[:300]}"))
        n += 1
    if n or nt:  # domínio ou tarefa mudou: a mudança de órgão e a exclusão (se houver) avançam na hora
        from . import remocoes
        mudancas.avancar_todas()
        remocoes.avancar_todas()
    return n

if __name__ == '__main__':  # python -m app.relatorio enviar | ver  (no nó; "ver" mostra o que seria enviado)
    import sys
    try:
        if sys.argv[1:2] == ['enviar']:
            print(enviar())
        elif sys.argv[1:2] == ['ver']:
            print(json.dumps(montar(), ensure_ascii=False, indent=1, default=str))
        else:
            print('uso: python -m app.relatorio enviar|ver', file=sys.stderr); sys.exit(2)
    finally:
        db.fechar()
