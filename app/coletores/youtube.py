"""Transmissões pelo YouTube (Fase 8): detecção de "ao vivo" e gravações do canal oficial do órgão.

- Chave da YouTube Data API v3 cadastrada no console (Credenciais de fontes, fonte "youtube"); nunca no .env nem no git.
- Canal por órgão: Painel → Transmissões → "ID do canal" (UC…).
- Ao vivo: verificado a cada 2 minutos só dentro das janelas da agenda (15 min antes do início previsto até 4 h depois)
  ou enquanto houver transmissão marcada como ao vivo. Fora disso não consulta nada (lista vazia).
- Gravações: uma vez por dia, lê os últimos vídeos do canal e registra só os que foram transmissões ao vivo encerradas
  (vídeos comuns do canal, como propaganda, não entram).
- Custo: 2 unidades da cota por consulta (playlistItems + videos), bem abaixo da cota diária gratuita.
- Erros registram só o código HTTP ou o tipo do erro: a URL leva a chave e nunca vai para o log."""
from datetime import datetime, timedelta, timezone
from .. import db, credenciais as CR

API = 'https://www.googleapis.com/youtube/v3'
JANELA_ANTES, JANELA_DEPOIS = timedelta(minutes=15), timedelta(hours=4)
VARREDURA = timedelta(hours=20)

def chave():
    c = CR.obter('youtube')
    return c[1] if c else None

def _get(caminho, params, key):
    """GET na API. Devolve o JSON; em erro levanta RuntimeError só com o código HTTP ou o tipo do erro."""
    import httpx
    try:
        with httpx.Client(timeout=30, headers={'User-Agent': 'PortaisBora-coletor/1.0', 'Accept': 'application/json'}) as c:
            r = c.get(f'{API}/{caminho}', params={**params, 'key': key})
    except Exception as e:
        raise RuntimeError(f'falha de conexão ({type(e).__name__})') from None
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}')
    try:
        return r.json()
    except ValueError:
        raise RuntimeError('resposta não é JSON') from None

def videos_recentes(canal, key, n=10):
    """Últimos vídeos do canal (playlist de envios UU…), com estado de transmissão."""
    if not (canal or '').startswith('UC') or len(canal) != 24:
        raise RuntimeError('ID do canal inválido (deve começar com UC e ter 24 caracteres)')
    pl = _get('playlistItems', {'part': 'contentDetails', 'playlistId': 'UU' + canal[2:], 'maxResults': n}, key)
    ids = [x['contentDetails']['videoId'] for x in pl.get('items', []) if x.get('contentDetails', {}).get('videoId')]
    if not ids:
        return []
    vs = _get('videos', {'part': 'snippet,liveStreamingDetails,contentDetails', 'id': ','.join(ids)}, key)
    out = []
    for v in vs.get('items', []):
        sn, lv = v.get('snippet', {}), v.get('liveStreamingDetails') or {}
        out.append({'id': v['id'], 'titulo': (sn.get('title') or '')[:200], 'estado': sn.get('liveBroadcastContent', 'none'),
                    'foi_ao_vivo': bool(lv), 'inicio': _dt(lv.get('actualStartTime')), 'fim': _dt(lv.get('actualEndTime')),
                    'publicado': _dt(sn.get('publishedAt')), 'legendas': (v.get('contentDetails') or {}).get('caption') == 'true'})
    return out

def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError:
        return None

def em_janela(banco, agora):
    if db.um(banco, 'SELECT 1 FROM transmissoes WHERE ao_vivo LIMIT 1'):
        return True
    return bool(db.um(banco, 'SELECT 1 FROM transmissoes WHERE encerrada_em IS NULL AND previsto_para BETWEEN %s AND %s LIMIT 1',
                      (agora - JANELA_DEPOIS, agora + JANELA_ANTES)))

def aplicar(banco, videos, agora, varrer):
    """Atualiza a tabela transmissoes com o que o canal informa. Devolve um resumo."""
    fatos = []
    for v in videos:
        t = db.um(banco, 'SELECT * FROM transmissoes WHERE video=%s', (v['id'],))
        if v['estado'] == 'live':
            if not t:  # vincula à transmissão agendada na janela, sem vídeo; senão cria
                t = db.um(banco, "SELECT * FROM transmissoes WHERE video='' AND encerrada_em IS NULL AND previsto_para BETWEEN %s AND %s ORDER BY previsto_para LIMIT 1",
                          (agora - JANELA_DEPOIS, agora + JANELA_ANTES))
                if t:
                    db.exe(banco, 'UPDATE transmissoes SET video=%s WHERE id=%s', (v['id'], t['id']))
                else:
                    t = db.exe(banco, "INSERT INTO transmissoes (titulo, tipo, video, origem, legendas) VALUES (%s,'Transmissão',%s,'youtube',%s) RETURNING *", (v['titulo'] or 'Transmissão ao vivo', v['id'], v['legendas']))
            if not t['ao_vivo']:
                db.exe(banco, 'UPDATE transmissoes SET ao_vivo=FALSE WHERE ao_vivo AND id<>%s', (t['id'],))
                db.exe(banco, 'UPDATE transmissoes SET ao_vivo=TRUE, iniciada_em=coalesce(iniciada_em, %s, now()), encerrada_em=NULL WHERE id=%s', (v['inicio'], t['id']))
                fatos.append(f"ao vivo: {v['id']}")
        elif t and t['ao_vivo'] and v['fim']:
            db.exe(banco, 'UPDATE transmissoes SET ao_vivo=FALSE, encerrada_em=%s, legendas=(legendas OR %s) WHERE id=%s', (v['fim'], v['legendas'], t['id']))
            fatos.append(f"encerrada: {v['id']}")
        elif varrer and not t and v['estado'] == 'none' and v['foi_ao_vivo'] and v['fim']:
            db.exe(banco, "INSERT INTO transmissoes (titulo, tipo, video, origem, legendas, iniciada_em, encerrada_em) VALUES (%s,'Transmissão',%s,'youtube',%s,%s,%s) ON CONFLICT DO NOTHING",
                   (v['titulo'] or 'Transmissão', v['id'], v['legendas'], v['inicio'], v['fim']))
            fatos.append(f"gravação: {v['id']}")
    return fatos

def coletar(o, p, agora=None, buscar=None):
    """Para o worker. Sem módulo, canal ou chave: lista vazia (não é erro, só não há o que fazer)."""
    from ..web import modulos_do_orgao
    agora = agora or datetime.now(timezone.utc)
    mods = modulos_do_orgao(o)
    if not (mods.get('transm') or mods.get('audiencias')):
        return []
    b = o['banco']
    conf = db.cfg(b, 'transmissao', {}) or {}
    canal = (conf.get('canal') or '').strip()
    key = chave()
    if not canal or not key:
        return []
    est = db.cfg(b, 'youtube_estado', {}) or {}
    ult = _dt(est.get('varredura'))
    varrer = not ult or agora - ult >= VARREDURA
    if not varrer and not em_janela(b, agora):
        return []
    try:
        vids = (buscar or videos_recentes)(canal, key)
    except RuntimeError as e:
        return [('canal', False, 0, str(e))]
    fatos = aplicar(b, vids, agora, varrer)
    if varrer:
        est['varredura'] = agora.isoformat()
    est['consulta'] = agora.isoformat()
    db.set_cfg(b, 'youtube_estado', est)
    return [('canal', True, len(fatos), '; '.join(fatos) or ('varredura diária sem novidades' if varrer else 'sem mudança'))]
