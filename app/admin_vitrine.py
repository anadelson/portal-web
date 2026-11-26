"""Painel: selos e reconhecimentos, galeria de vídeos e câmeras ao vivo (26/11/2026)."""
from datetime import date
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from . import db, vitrine as VT
from .web import ir, exige, auditar
from .admin import T

r = APIRouter(prefix='/_a')

def _arquivo(f, k):
    a = f.get(k)
    return a if a is not None and not isinstance(a, str) and getattr(a, 'filename', '') else None

# ---------------- selos ----------------
@r.get('/selos')
def selos(request: Request, ed: int = 0):
    u = exige(request, 'editar'); o = request.state.orgao
    lista = VT.selos(o['banco'], publicos=False)
    for s in lista:
        s['doc'] = VT.info_documento(o, s['documento'])
    atual = next((s for s in lista if s['id'] == ed), None)
    if ed and not atual:
        return ir('/admin/selos', 'Selo não encontrado.', request)
    return T('vitrine_selos', request, u, selos=lista, ed=atual)

@r.post('/selos')
async def selos_post(request: Request):
    u = exige(request, 'editar'); o = request.state.orgao; b = o['banco']
    from .web import ler_form
    f = await ler_form(request)
    acao = f.get('acao', '')
    sid = int(f.get('id') or 0) if str(f.get('id') or '0').isdigit() else 0
    atual = db.um(b, 'SELECT * FROM selos WHERE id=%s', (sid,)) if sid else None
    if sid and not atual:
        return ir('/admin/selos', 'Selo não encontrado.', request)
    volta = f'/admin/selos?ed={sid}' if sid else '/admin/selos'
    if acao == 'apagar' and atual:
        db.exe(b, 'DELETE FROM selos WHERE id=%s', (sid,))
        for k in ('imagem', 'documento'):
            VT.apagar_arquivo(o, atual[k])
        auditar(request, f"Selo apagado: {atual['nome']}")
        return ir('/admin/selos', 'Selo apagado.', request)
    if acao in ('sem_imagem', 'sem_documento') and atual:
        k = 'imagem' if acao == 'sem_imagem' else 'documento'
        VT.apagar_arquivo(o, atual[k])
        db.exe(b, f"UPDATE selos SET {k}='' WHERE id=%s", (sid,))
        auditar(request, f"Selo {atual['nome']}: {k} removido(a)")
        return ir(volta, 'Arquivo removido.', request)
    if acao != 'salvar':
        return ir(volta, '', request)
    try:
        d = VT.validar_selo(f)
        img, doc = _arquivo(f, 'imagem'), _arquivo(f, 'documento')
        nova_img = VT.guardar_imagem(o, await img.read(3 * 1024 * 1024 + 1)) if img else None
        try:
            novo_doc = VT.guardar_documento(o, await doc.read(VT.LIMITE_DOC + 1)) if doc else None
        except ValueError:
            if nova_img:
                VT.apagar_arquivo(o, nova_img)
            raise
    except ValueError as e:
        return ir(volta, f'Não salvo: {e}', request)
    campos = dict(d)
    if nova_img:
        campos['imagem'] = nova_img
    if novo_doc:
        campos['documento'] = novo_doc
    if atual:
        campos['exemplo'] = False  # editado pelo órgão: deixa de ser exemplo
        db.exe(b, 'UPDATE selos SET ' + ', '.join(f'{k}=%s' for k in campos) + ' WHERE id=%s', (*campos.values(), sid))
        for k, novo in (('imagem', nova_img), ('documento', novo_doc)):
            if novo:
                VT.apagar_arquivo(o, atual[k])
        auditar(request, f"Selo editado: {d['nome']}")
        return ir('/admin/selos', 'Selo salvo.', request)
    campos['criado_por'] = u['nome']
    db.exe(b, f"INSERT INTO selos ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))})", tuple(campos.values()))
    auditar(request, f"Selo cadastrado: {d['nome']}")
    return ir('/admin/selos', 'Selo cadastrado.' + ('' if d['visivel'] else ' Está oculto: marque “Mostrar no portal” para publicar.'), request)

# ---------------- vídeos ----------------
@r.get('/videos')
def videos(request: Request):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    lista = db.todos(b, 'SELECT * FROM videos ORDER BY exemplo DESC, publicado_em DESC NULLS LAST, id DESC')
    from .web import ctx_orgao
    mods = ctx_orgao(request)['mods']
    n_tv = len([v for v in VT.galeria(b, mods, limite=0) if v['origem'] == 'transmissao'])
    return T('vitrine_videos', request, u, videos=lista, n_transmissoes=n_tv, com_transm=bool(mods.get('transm') or mods.get('audiencias')))

@r.post('/videos')
async def videos_post(request: Request):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    from .web import ler_form
    f = await ler_form(request)
    acao, vid = f.get('acao', ''), int(f.get('id') or 0) if str(f.get('id') or '0').isdigit() else 0
    v = db.um(b, 'SELECT * FROM videos WHERE id=%s', (vid,)) if vid else None
    if acao == 'apagar' and v:
        db.exe(b, 'DELETE FROM videos WHERE id=%s', (vid,))
        auditar(request, f"Vídeo apagado da galeria: {v['titulo']}")
        return ir('/admin/videos', 'Vídeo apagado da galeria (no YouTube ele continua).', request)
    if acao == 'visivel' and v:
        db.exe(b, 'UPDATE videos SET visivel = NOT visivel WHERE id=%s', (vid,))
        auditar(request, f"Vídeo {'ocultado' if v['visivel'] else 'mostrado'}: {v['titulo']}")
        return ir('/admin/videos', 'Vídeo ' + ('ocultado.' if v['visivel'] else 'mostrado no portal.'), request)
    if acao != 'adicionar':
        return ir('/admin/videos', '', request)
    yid = VT.youtube_id(f.get('link', ''))
    titulo = ' '.join(str(f.get('titulo') or '').split())
    if not yid:
        return ir('/admin/videos', 'Não salvo: cole o link do vídeo no YouTube (youtube.com/watch?v=…, youtu.be/…, /shorts/… ou /live/…).', request)
    if not 3 <= len(titulo) <= 160:
        return ir('/admin/videos', 'Não salvo: o título deve ter de 3 a 160 caracteres.', request)
    if db.um(b, 'SELECT 1 FROM videos WHERE youtube_id=%s', (yid,)):
        return ir('/admin/videos', 'Este vídeo já está na galeria.', request)
    try:
        quando = date.fromisoformat(f['publicado_em']) if f.get('publicado_em') else None
    except ValueError:
        return ir('/admin/videos', 'Não salvo: data inválida.', request)
    db.exe(b, 'INSERT INTO videos (titulo, youtube_id, descricao, publicado_em, criado_por) VALUES (%s,%s,%s,%s,%s)',
           (titulo, yid, str(f.get('descricao') or '').strip()[:500], quando, u['nome']))
    auditar(request, f'Vídeo acrescentado à galeria: {titulo}')
    return ir('/admin/videos', 'Vídeo acrescentado à galeria.', request)

# ---------------- câmeras ----------------
@r.get('/cameras')
async def cameras(request: Request):
    u = exige(request, 'config'); o = request.state.orgao
    from . import credenciais as CR
    ok = await run_in_threadpool(VT.conversor_ok)
    cams = VT.cameras(o['banco'], publicas=False)
    centro = VT.centro(o.get('ibge')) or next(({'lat': c['lat'], 'lon': c['lon']} for c in cams if c['lat'] is not None), None)
    return T('vitrine_cameras', request, u, cameras=cams, conversor=ok, chave_ok=CR.chave_ok(), centro=centro, visao=VT.visao_mapa(o['banco']))

@r.post('/cameras')
async def cameras_post(request: Request):
    u = exige(request, 'config'); o = request.state.orgao; b = o['banco']
    from .web import ler_form
    from . import credenciais as CR
    f = await ler_form(request)
    acao, cid = f.get('acao', ''), int(f.get('id') or 0) if str(f.get('id') or '0').isdigit() else 0
    c = db.um(b, 'SELECT id, nome, ativa, exemplo, miniatura FROM cameras WHERE id=%s', (cid,)) if cid else None
    msg = ''
    try:
        if acao == 'adicionar':
            nome, local = ' '.join(str(f.get('nome') or '').split()), ' '.join(str(f.get('local') or '').split())
            if not 3 <= len(nome) <= 80 or len(local) > 160:
                return ir('/admin/cameras', 'Não salvo: nome de 3 a 80 caracteres e local até 160.', request)
            lat, lon = VT.ler_posicao(f.get('posicao'))
            rtsp = VT.cifrar_rtsp(f.get('rtsp', ''))
            novo = db.exe(b, 'INSERT INTO cameras (nome, local, rtsp, caminho, criado_por, lat, lon) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                          (nome, local, rtsp, VT.novo_caminho(o), u['nome'], lat, lon))['id']
            auditar(request, f'Câmera cadastrada: {nome} (endereço cifrado, não registrado)')
            msg = 'Câmera cadastrada. O endereço foi gravado cifrado e não volta para a tela. ' + _msg_miniatura(await run_in_threadpool(VT.gerar_miniatura, o, novo))
        elif acao == 'trocar' and c:
            db.exe(b, 'UPDATE cameras SET rtsp=%s, exemplo=FALSE WHERE id=%s', (VT.cifrar_rtsp(f.get('rtsp', '')), cid))
            auditar(request, f"Câmera {c['nome']}: endereço trocado (não registrado)")
            msg = 'Endereço trocado. ' + _msg_miniatura(await run_in_threadpool(VT.gerar_miniatura, o, cid))
        elif acao == 'miniatura' and c:  # imagem enviada pelo admin no lugar da tirada da câmera
            img = _arquivo(f, 'imagem')
            if not img:
                return ir('/admin/cameras', 'Não salvo: escolha uma imagem (PNG, JPG ou WEBP, até 3 MB).', request)
            dados = await img.read(3 * 1024 * 1024 + 1)
            if len(dados) > 3 * 1024 * 1024:
                return ir('/admin/cameras', 'Não salvo: imagem maior que 3 MB.', request)
            nova = VT.guardar_imagem(o, dados, VT.LARGURA_MINIATURA)
            db.exe(b, 'UPDATE cameras SET miniatura=%s WHERE id=%s', (nova, cid))
            VT.apagar_arquivo(o, c['miniatura'])
            auditar(request, f"Câmera {c['nome']}: miniatura enviada")
            return ir('/admin/cameras', 'Miniatura trocada pela imagem enviada.', request)
        elif acao == 'miniatura_gerar' and c and not c['exemplo']:
            res = await run_in_threadpool(VT.gerar_miniatura, o, cid)
            auditar(request, f"Câmera {c['nome']}: miniatura tirada da câmera ({'ok' if not res else res})")
            return ir('/admin/cameras', _msg_miniatura(res), request)
        elif acao == 'miniatura_tirar' and c:
            db.exe(b, "UPDATE cameras SET miniatura='' WHERE id=%s", (cid,))
            VT.apagar_arquivo(o, c['miniatura'])
            auditar(request, f"Câmera {c['nome']}: miniatura removida")
            return ir('/admin/cameras', 'Miniatura removida: o cartão volta ao fundo padrão.', request)
        elif acao == 'visao':
            v = VT.ler_visao(f)
            db.set_cfg(b, 'cameras_mapa', v)
            auditar(request, f"Mapa das câmeras: visão fixa gravada (zoom {v['zoom']}{', travado' if v['travar'] else ''})")
            return ir('/admin/cameras', f"Visão do mapa gravada: o mapa abre sempre nela, no zoom {v['zoom']}" + (', com o zoom travado.' if v['travar'] else '.'), request)
        elif acao == 'visao_auto':
            db.set_cfg(b, 'cameras_mapa', None)
            auditar(request, 'Mapa das câmeras: visão automática')
            return ir('/admin/cameras', 'Mapa no automático: enquadra as câmeras cadastradas.', request)
        elif acao == 'posicao' and c:
            lat, lon = VT.ler_posicao(f.get('posicao'))
            db.exe(b, 'UPDATE cameras SET lat=%s, lon=%s WHERE id=%s', (lat, lon, cid))
            auditar(request, f"Câmera {c['nome']}: posição no mapa {'apagada' if lat is None else 'gravada'}")
            return ir('/admin/cameras', 'Posição no mapa apagada.' if lat is None else 'Posição no mapa gravada.', request)
        elif acao == 'ativa' and c:
            db.exe(b, 'UPDATE cameras SET ativa = NOT ativa WHERE id=%s', (cid,))
            auditar(request, f"Câmera {'desligada' if c['ativa'] else 'ligada'}: {c['nome']}")
            msg = 'Câmera ' + ('desligada: saiu do portal.' if c['ativa'] else 'ligada.')
        elif acao == 'apagar' and c:
            db.exe(b, 'DELETE FROM cameras WHERE id=%s', (cid,))
            VT.apagar_arquivo(o, c['miniatura'])
            auditar(request, f"Câmera apagada: {c['nome']}")
            msg = 'Câmera apagada.'
        elif acao == 'testar' and c:
            res = await run_in_threadpool(testar, o, cid)
            auditar(request, f"Câmera {c['nome']}: teste ({res})")
            return ir('/admin/cameras', f'Teste: {res}.', request)
        else:
            return ir('/admin/cameras', '', request)
    except CR.SemChave:
        return ir('/admin/cameras', 'Cadastro desligado: falta a chave de cifra no servidor. Fale com o suporte da plataforma.', request)
    except ValueError as e:
        return ir('/admin/cameras', f'Não salvo: {e}', request)
    sinc = await run_in_threadpool(VT.sincronizar_quieto)
    return ir('/admin/cameras', msg + ('' if sinc else ' O conversor de vídeo não respondeu agora; ele é atualizado automaticamente em até 1 minuto.'), request)

def _msg_miniatura(res):
    return 'Miniatura tirada da câmera.' if not res else f'Sem miniatura ({res}): envie uma imagem ou tente "Tirar da câmera" depois.'

def testar(o, cid):
    """Pede o vídeo ao conversor como um visitante faria (abre a câmera por alguns segundos). Nunca mostra o endereço."""
    import httpx
    c = db.um(o['banco'], 'SELECT caminho, rtsp, exemplo, ativa FROM cameras WHERE id=%s', (cid,))
    if not c or c['exemplo'] or not c['rtsp']:
        return 'câmera de exemplo, sem endereço'
    if not VT.decifrar_rtsp(c['rtsp']):
        return 'endereço ilegível: cadastre de novo'
    if not c['ativa']:
        return 'câmera desligada: ligue para testar'
    if VT.sincronizar_quieto() is None:
        return 'conversor de vídeo fora do ar'
    try:
        # o conversor responde ao 1º pedido com 302 (checagem de cookie, "?cookieCheck=1"): segue dentro do servidor
        with httpx.Client(timeout=25, follow_redirects=True, max_redirects=3) as cli:
            r = cli.get(f"{VT.HLS}/{c['caminho']}/index.m3u8")
    except httpx.HTTPError:
        return 'sem resposta da câmera em 25 s (confira endereço, usuário, senha e se a porta está liberada para o servidor)'
    if r.status_code == 200 and '#EXTM3U' in r.text:
        return 'ok, vídeo recebido'
    return f'a câmera não entregou vídeo (código {r.status_code}); confira endereço, usuário e senha'
