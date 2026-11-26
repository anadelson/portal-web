"""Selos e reconhecimentos, galeria de vídeos (YouTube) e câmeras ao vivo (26/11/2026).

- Selos: cadastrados no painel (nome, instituição, como foi conseguido, nota, datas, imagem e documento de concessão).
- Vídeos: vídeos do canal oficial no YouTube (o painel guarda só o ID) + gravações de transmissões com vídeo do YouTube.
  O portal só carrega o player (youtube-nocookie) quando a pessoa clica.
- Câmeras: o endereço RTSP fica CIFRADO no banco do órgão (só gravação). O conversor de vídeo do nó (serviço "cameras",
  MediaMTX) lê a câmera só enquanto alguém assiste e entrega HLS ao navegador pelo próprio portal (/cameras/<id>/…).
  O worker sincroniza o conversor com as câmeras ativas de todos os órgãos do nó.
- Exemplos do piloto: marcados (exemplo = TRUE), sempre com a etiqueta "exemplo" no portal; o admin apaga quando quiser."""
import io, json, random, re, secrets
from datetime import date
from pathlib import Path
from . import config, db

YT_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
_YT_URL = re.compile(r'(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})')
LIMITE_DOC = 20 * 1024 * 1024
DOC_TIPOS = {'pdf': 'PDF', 'png': 'imagem PNG', 'jpg': 'imagem JPG', 'webp': 'imagem WEBP'}
RTSP_OK = re.compile(r'^rtsps?://[^\s/?#]+(:\d{1,5})?(/[^\s]*)?$')
API = config.env('CAMERAS_API', 'http://cameras:9997')
HLS = config.env('CAMERAS_HLS', 'http://cameras:8888')

# ---------------- arquivos (imagem do selo e documento de concessão) ----------------
def pasta_midia(o):
    p = Path(config.DADOS_DIR) / o['slug'] / 'midia'
    p.mkdir(parents=True, exist_ok=True)
    return p

def guardar_imagem(o, dados: bytes, largura_max=600) -> str:
    """Imagem do selo (ou miniatura da câmera): PNG, JPG ou WEBP até 3 MB, convertida para WEBP. Devolve a URL /midia/…"""
    from . import imagens as IM
    ext = IM.validar_upload(dados)
    nome = secrets.token_hex(16)
    tmp = pasta_midia(o) / f'{nome}.{ext}'
    tmp.write_bytes(dados)
    try:
        IM.para_webp(tmp, pasta_midia(o) / f'{nome}.webp', largura_max=largura_max)
    finally:
        if ext != 'webp':
            tmp.unlink(missing_ok=True)
    return f'/midia/{nome}.webp'

def guardar_documento(o, dados: bytes) -> str:
    """Certificado ou documento de concessão: PDF ou imagem, conferido pelo conteúdo, até 20 MB."""
    from . import anexos as AX
    if len(dados) > LIMITE_DOC:
        raise ValueError('Arquivo maior que 20 MB.')
    try:
        ext = AX.detectar(dados)
    except ValueError:
        raise ValueError('Envie o documento em PDF, PNG, JPG ou WEBP.')
    if ext not in DOC_TIPOS:
        raise ValueError('Envie o documento em PDF, PNG, JPG ou WEBP.')
    nome = f'{secrets.token_hex(16)}.{ext}'
    (pasta_midia(o) / nome).write_bytes(dados)
    return f'/midia/{nome}'

def apagar_arquivo(o, url):
    m = re.match(r'^/midia/([0-9a-f]{32}\.(?:webp|png|jpg|pdf))$', url or '')
    if m:
        (pasta_midia(o) / m.group(1)).unlink(missing_ok=True)

def info_documento(o, url):
    """('PDF', '230 KB') do documento, ou None se o arquivo sumiu."""
    m = re.match(r'^/midia/([0-9a-f]{32})\.(\w+)$', url or '')
    if not m:
        return None
    f = pasta_midia(o) / f'{m.group(1)}.{m.group(2)}'
    if not f.is_file():
        return None
    n = f.stat().st_size
    tam = f'{n / 1048576:.1f} MB'.replace('.', ',') if n >= 1048576 else f'{max(1, n // 1024)} KB'
    return DOC_TIPOS.get(m.group(2), m.group(2).upper()), tam

# ---------------- selos ----------------
def selos(b, publicos=True, limite=None):
    q = 'SELECT * FROM selos' + (' WHERE visivel' if publicos else '') + ' ORDER BY exemplo, ordem, concedido_em DESC NULLS LAST, id DESC'
    out = db.todos(b, q + (f' LIMIT {int(limite)}' if limite else ''))
    hoje = config.hoje()
    for s in out:
        s['vencido'] = bool(s['valido_ate'] and s['valido_ate'] < hoje)
        s['ano'] = s['concedido_em'].year if s['concedido_em'] else None
    return out

def validar_selo(f):
    d = {k: re.sub(r'\s+', ' ', str(f.get(k) or '')).strip() for k in ('nome', 'instituicao', 'nota', 'link', 'documento_titulo')}
    d['como'] = str(f.get('como') or '').strip()
    if len(d['nome']) < 3:
        raise ValueError('Escreva o nome do selo (ao menos 3 letras).')
    if len(d['instituicao']) < 2:
        raise ValueError('Informe a instituição que concedeu o selo.')
    if len(d['nome']) > 120 or len(d['instituicao']) > 160 or len(d['nota']) > 60 or len(d['como']) > 2000 or len(d['documento_titulo']) > 120:
        raise ValueError('Texto longo demais: nome até 120, instituição até 160, nota até 60 e “como foi conseguido” até 2000 caracteres.')
    if d['link'] and not re.match(r'^https://[^\s]+$', d['link']):
        raise ValueError('O link da instituição precisa começar com https://.')
    for k in ('concedido_em', 'valido_ate'):
        v = str(f.get(k) or '').strip()
        try:
            d[k] = date.fromisoformat(v) if v else None
        except ValueError:
            raise ValueError('Data inválida.')
    if d['concedido_em'] and d['valido_ate'] and d['valido_ate'] < d['concedido_em']:
        raise ValueError('A validade não pode ser antes da concessão.')
    try:
        d['ordem'] = max(0, min(999, int(f.get('ordem') or 100)))
    except ValueError:
        d['ordem'] = 100
    d['visivel'] = f.get('visivel') == '1'
    return d

# ---------------- vídeos ----------------
def youtube_id(texto):
    t = (texto or '').strip()
    if YT_ID.match(t):
        return t
    m = _YT_URL.search(t)
    return m.group(1) if m else ''

def galeria(b, mods, limite=7):
    """Vídeos da galeria + gravações de transmissões (YouTube), do mais recente para o mais antigo. Exemplos por último."""
    itens = [dict(v, origem='galeria', quando=v['publicado_em']) for v in db.todos(b, 'SELECT * FROM videos WHERE visivel ORDER BY exemplo, publicado_em DESC NULLS LAST, id DESC')]
    if mods.get('transm') or mods.get('audiencias'):
        ja = {v['youtube_id'] for v in itens}
        for t in db.todos(b, "SELECT * FROM transmissoes WHERE NOT ao_vivo AND length(video)=11 AND (encerrada_em IS NOT NULL OR previsto_para < now()) ORDER BY coalesce(encerrada_em, previsto_para) DESC NULLS LAST LIMIT 30"):
            if t['video'] not in ja:
                q = t['encerrada_em'] or t['previsto_para']
                itens.append({'id': t['id'], 'titulo': t['titulo'], 'youtube_id': t['video'], 'descricao': t['tipo'], 'exemplo': False, 'origem': 'transmissao',
                              'quando': q.date() if q else None})
    itens.sort(key=lambda v: (v['exemplo'], -(v['quando'].toordinal() if v['quando'] else 0)))
    return itens[:limite] if limite else itens

MAX_CAMERAS_GALERIA = 2

def sortear_cameras(cams, n=MAX_CAMERAS_GALERIA):
    """Até n câmeras em ordem aleatória a cada carregamento; as reais têm a vez, os exemplos só completam."""
    reais, ex = [c for c in cams if not c['exemplo']], [c for c in cams if c['exemplo']]
    escolha = random.sample(reais, min(n, len(reais)))
    return escolha + random.sample(ex, min(n - len(escolha), len(ex)))

def galeria_unica(b, mods, defeso, limite_videos=7, fotos=None):
    """Seção única (26/11/2026) em 2 colunas: à esquerda (mais larga) os vídeos do YouTube, em destaque + lista;
    à direita as câmeras ao vivo, no máximo 2, sorteadas a cada carregamento; todas ficam em /cameras-ao-vivo (mapa).
    No período eleitoral os vídeos saem e as câmeras ficam.
    fotos (home): quando as câmeras já aparecem no "Conheça" e há álbuns, a 2ª coluna vira a galeria de fotos
    (só junto com vídeos; sem vídeos a seção continua sendo a das câmeras)."""
    cams = cameras(b)
    vids = [] if defeso else galeria(b, mods, limite=limite_videos)
    if not cams and not vids:
        return None
    g = {'videos': {'palco': vids[0], 'lista': vids[1:]} if vids else None, 'cameras': sortear_cameras(cams),
         'n_cameras': len(cams), 'mais_cameras': len(cams) > MAX_CAMERAS_GALERIA, 'n_videos': len(vids), 'fotos': None}
    if fotos and vids:
        g.update(cameras=[], fotos=fotos)
    return g

MAX_CAMERAS_CONHECA = 3

def cameras_conheca(b):
    """Faixa "Ao vivo" na seção Conheça da home (26/11/2026): até 3 câmeras pequenas, sorteadas (reais primeiro)."""
    cams = cameras(b)
    return {'cameras': sortear_cameras(cams, MAX_CAMERAS_CONHECA), 'n': len(cams)} if cams else None

# ---------------- câmeras ----------------
def _fernet():
    from . import credenciais as CR
    return CR._fernet()

def cifrar_rtsp(url):
    url = (url or '').strip()
    if not RTSP_OK.match(url) or len(url) > 500:
        raise ValueError('Endereço inválido: use rtsp://… ou rtsps://… (ex.: rtsp://usuario:senha@IP:554/stream1).')
    return _fernet().encrypt(url.encode()).decode()

def decifrar_rtsp(token):
    from cryptography.fernet import InvalidToken
    from . import credenciais as CR
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, CR.SemChave, ValueError):
        return None

def novo_caminho(o):
    return f"{re.sub(r'[^a-z0-9]', '', o['slug'].lower())[:16]}-{secrets.token_hex(8)}"

def cameras(b, publicas=True):
    q = 'SELECT id, nome, local, caminho, ativa, ordem, exemplo, criado_por, criado_em, (rtsp <> \'\') tem_rtsp, lat::float lat, lon::float lon, miniatura FROM cameras'
    return db.todos(b, q + (' WHERE ativa' if publicas else '') + ' ORDER BY exemplo, ordem, id')

_NUM = r'-?\d{1,3}(?:[.,]\d{1,8})?'
_POS = re.compile(rf'^\s*({_NUM})\s*(?:;|,\s+|\s+|,(?=-?\d{{1,3}}[.]))\s*({_NUM})\s*$')

def ler_posicao(texto):
    """'-22.2442, -50.5021' (como o Google Maps / OpenStreetMap copiam) -> (lat, lon); vazio -> (None, None).
    Aceita vírgula decimal quando separado por ';' ou espaço. ValueError com a explicação se não der para ler."""
    t = ' '.join(str(texto or '').split())
    if not t:
        return None, None
    m = _POS.match(t)
    if not m:
        raise ValueError('posição não reconhecida: use latitude e longitude em graus decimais, ex.: -22.2442, -50.5021')
    lat, lon = (round(float(x.replace(',', '.')), 6) for x in m.groups())
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('posição fora do mapa: latitude vai de -90 a 90 e longitude de -180 a 180 (confira se não estão trocadas)')
    return lat, lon

def centro(ibge):
    """Centro do município (o mesmo da previsão do tempo, coletado do IBGE), ou None."""
    if not ibge:
        return None
    try:
        r = db.um(db.LOCAL, "SELECT payload FROM dados_publicos WHERE ibge=%s AND fonte='tempo' AND chave='previsao'", (str(ibge),))
        p = (r or {}).get('payload') or {}
        lat, lon = float(p['lat']), float(p['lon'])
        return {'lat': lat, 'lon': lon} if -90 <= lat <= 90 and -180 <= lon <= 180 else None
    except Exception:
        return None

# câmeras de exemplo sem posição: postas em volta do centro só para ilustrar o mapa (sempre marcadas "exemplo")
_DESLOC_EXEMPLO = [(0.0018, -0.0026), (-0.0022, 0.0031), (0.0030, 0.0024), (-0.0012, -0.0038)]

ZOOM_MIN, ZOOM_MAX = 3, 19

def visao_mapa(b):
    """Visão fixa do mapa escolhida no painel ({lat, lon, zoom, travar}) ou None (automático: enquadra as câmeras)."""
    v = db.cfg(b, 'cameras_mapa')
    try:
        if v and -90 <= float(v['lat']) <= 90 and -180 <= float(v['lon']) <= 180 and ZOOM_MIN <= int(v['zoom']) <= ZOOM_MAX:
            return {'lat': float(v['lat']), 'lon': float(v['lon']), 'zoom': int(v['zoom']), 'travar': bool(v.get('travar'))}
    except (KeyError, TypeError, ValueError):
        pass
    return None

def ler_visao(f):
    """Formulário do painel -> visão válida; ValueError com a explicação."""
    try:
        lat, lon, zoom = float(str(f.get('lat', '')).replace(',', '.')), float(str(f.get('lon', '')).replace(',', '.')), int(f.get('zoom', ''))
    except (TypeError, ValueError):
        raise ValueError('visão do mapa não recebida: mova o mapa até o enquadramento desejado e clique em “Usar esta visão”')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and ZOOM_MIN <= zoom <= ZOOM_MAX):
        raise ValueError(f'visão do mapa inválida (zoom de {ZOOM_MIN} a {ZOOM_MAX})')
    return {'lat': round(lat, 6), 'lon': round(lon, 6), 'zoom': zoom, 'travar': f.get('travar') in ('1', 'on', 'sim')}

def mapa_cameras(cams, ibge, visao=None):
    """Dados do mapa de /cameras-ao-vivo: só id, nome, local, posição e se é exemplo (nunca endereço nem caminho).
    Com "visao" (escolhida no painel), o mapa abre sempre nela, sem enquadrar sozinho; "travar" impede mudar o zoom."""
    c = centro(ibge)
    pontos, i = [], 0
    for x in cams:
        lat, lon, ilustr = x['lat'], x['lon'], False
        if lat is None and x['exemplo'] and c:
            dl = _DESLOC_EXEMPLO[i % len(_DESLOC_EXEMPLO)]; i += 1
            lat, lon, ilustr = round(c['lat'] + dl[0], 6), round(c['lon'] + dl[1], 6), True
        if lat is not None:
            pontos.append({'id': x['id'], 'nome': x['nome'], 'local': x['local'], 'lat': lat, 'lon': lon, 'exemplo': x['exemplo'], 'ilustrativa': ilustr})
    if not pontos and not c and not visao:
        return None
    return {'centro': c or ({'lat': visao['lat'], 'lon': visao['lon']} if visao else {'lat': pontos[0]['lat'], 'lon': pontos[0]['lon']}),
            'pontos': pontos, 'visao': visao}

# ---------------- miniatura da câmera (26/11/2026) ----------------
# Foto fixa de fundo do cartão, no lugar do cinza: tirada do RTSP UMA vez, quando o endereço é cadastrado ou trocado
# (nada fica atualizando sozinho), ou enviada pelo admin. O vídeo continua só no clique; o portal não grava vídeo.
LARGURA_MINIATURA = 800

def quadro_rtsp(url, espera=10):
    """Primeiro quadro-chave do RTSP (H.264 ou H.265) como PNG. ValueError com texto curto e SEM o endereço."""
    import time
    try:
        import av
    except ImportError:
        raise ValueError('leitor de vídeo não instalado neste servidor')
    t0 = time.monotonic()
    try:
        with av.open(url, options={'rtsp_transport': 'tcp'}, timeout=(espera, espera)) as ct:
            st = ct.streams.video[0]
            st.codec_context.skip_frame = 'NONKEY'  # só quadros completos (sem imagem borrada do meio do GOP)
            for pk in ct.demux(st):
                if time.monotonic() - t0 > espera * 2:
                    break  # sem quadro-chave em tempo razoável
                for fr in pk.decode():
                    img = fr.to_image()
                    img.thumbnail((LARGURA_MINIATURA * 2, LARGURA_MINIATURA * 2))
                    b = io.BytesIO(); img.save(b, 'PNG')
                    return b.getvalue()
    except Exception:
        pass  # a mensagem do leitor pode conter o endereço com usuário e senha: nunca repassar
    raise ValueError('a câmera não entregou imagem')

def gerar_miniatura(o, cid):
    """Tira a miniatura do RTSP e grava na câmera (apaga a anterior). Devolve '' se deu certo ou o motivo, sem endereço."""
    c = db.um(o['banco'], 'SELECT rtsp, exemplo, miniatura FROM cameras WHERE id=%s', (cid,))
    url = decifrar_rtsp(c['rtsp']) if c and c['rtsp'] and not c['exemplo'] else ''
    if not url:
        return 'câmera sem endereço'
    try:
        nova = guardar_imagem(o, quadro_rtsp(url), LARGURA_MINIATURA)
    except ValueError as e:
        return str(e)
    db.exe(o['banco'], 'UPDATE cameras SET miniatura=%s WHERE id=%s', (nova, cid))
    apagar_arquivo(o, c['miniatura'])
    return ''

def _api(metodo, caminho, corpo=None, timeout=5):
    import httpx
    r = httpx.request(metodo, API + caminho, json=corpo, timeout=timeout)
    r.raise_for_status()
    return r.json() if r.content else {}

def conversor_ok():
    try:
        _api('GET', '/v3/config/global/get', timeout=3)
        return True
    except Exception:
        return False

def desejadas():
    """{caminho: rtsp} das câmeras ativas (não exemplo) de todos os órgãos deste nó."""
    from . import orgaos as ORG
    out = {}
    for o in ORG.todos():
        try:
            linhas = db.todos(o['banco'], "SELECT caminho, rtsp FROM cameras WHERE ativa AND NOT exemplo AND rtsp <> ''")
        except Exception:
            continue  # migração ainda não aplicada neste órgão
        for c in linhas:
            url = decifrar_rtsp(c['rtsp'])
            if url:
                out[c['caminho']] = url
    return out

def sincronizar():
    """Deixa o conversor com exatamente as câmeras ativas. Devolve texto curto (sem endereços) ou levanta exceção."""
    alvo = desejadas()
    atuais = {p['name']: p for p in (_api('GET', '/v3/config/paths/list?itemsPerPage=1000').get('items') or [])}
    conf = lambda url: {'source': url, 'sourceOnDemand': True, 'sourceOnDemandStartTimeout': '15s', 'sourceOnDemandCloseAfter': '30s', 'rtspTransport': 'tcp'}
    n = {'+': 0, '~': 0, '-': 0}
    for nome, url in alvo.items():
        if nome not in atuais:
            _api('POST', f'/v3/config/paths/add/{nome}', conf(url)); n['+'] += 1
        elif atuais[nome].get('source') != url:
            _api('PATCH', f'/v3/config/paths/patch/{nome}', conf(url)); n['~'] += 1
    for nome in atuais:
        if nome not in alvo and nome not in ('all', 'all_others', '~^.*$'):
            _api('DELETE', f'/v3/config/paths/delete/{nome}'); n['-'] += 1
    return f"{len(alvo)} câmera(s) no conversor ({n['+']} nova(s), {n['~']} trocada(s), {n['-']} removida(s))"

def sincronizar_quieto():
    try:
        return sincronizar()
    except Exception:
        return None

# ---------------- exemplos do piloto ----------------
SELOS_EXEMPLO = [
    ('Selo de exemplo — Transparência', 'Instituição de exemplo', 'Texto de exemplo: aqui vai como o selo foi conseguido (programa, critérios avaliados, ano da avaliação).', '95,4 de 100', 'exemplo-selo-1.svg'),
    ('Selo de exemplo — Gestão fiscal', 'Instituição de exemplo', 'Texto de exemplo: descreva a avaliação e o que o órgão fez para alcançar a nota.', 'Nota A', 'exemplo-selo-2.svg'),
    ('Selo de exemplo — Atendimento', 'Instituição de exemplo', 'Texto de exemplo: descreva o reconhecimento recebido.', '4,8 de 5', 'exemplo-selo-3.svg'),
]
VIDEOS_EXEMPLO = ['Vídeo de exemplo — destaque', 'Vídeo de exemplo — evento na cidade', 'Vídeo de exemplo — prestação de contas', 'Vídeo de exemplo — serviço ao cidadão', 'Vídeo de exemplo — obra concluída']
CAMERAS_EXEMPLO = [('Câmera de exemplo — Praça central', 'Local de exemplo'), ('Câmera de exemplo — Entrada da cidade', 'Local de exemplo')]

def semear_exemplos(o, cameras_tambem=False):
    """Uma única vez por órgão do piloto (marca em config); apagados pelo admin, não voltam."""
    b = o['banco']
    if db.cfg(b, 'vitrine_exemplos'):
        return 0
    n = 0
    hoje = config.hoje()
    if not db.um(b, 'SELECT 1 FROM selos LIMIT 1'):
        for i, (nome, inst, como, nota, img) in enumerate(SELOS_EXEMPLO):
            db.exe(b, 'INSERT INTO selos (nome, instituicao, como, nota, concedido_em, imagem, ordem, exemplo, criado_por) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s)',
                   (nome, inst, como, nota, date(hoje.year, 1, 1), f'/static/img/{img}', i, 'exemplo do piloto')); n += 1
    if not db.um(b, 'SELECT 1 FROM videos LIMIT 1'):
        for i, t in enumerate(VIDEOS_EXEMPLO):
            db.exe(b, "INSERT INTO videos (titulo, descricao, publicado_em, exemplo, criado_por) VALUES (%s,'Ilustração: aqui aparece o vídeo do canal oficial no YouTube.',%s,TRUE,'exemplo do piloto')",
                   (t, date.fromordinal(hoje.toordinal() - i * 7))); n += 1
    if cameras_tambem and not db.um(b, 'SELECT 1 FROM cameras LIMIT 1'):
        for i, (nome, local) in enumerate(CAMERAS_EXEMPLO):
            db.exe(b, "INSERT INTO cameras (nome, local, caminho, ordem, exemplo, criado_por) VALUES (%s,%s,%s,%s,TRUE,'exemplo do piloto')", (nome, local, novo_caminho(o), i)); n += 1
    db.set_cfg(b, 'vitrine_exemplos', {'em': hoje.isoformat(), 'n': n})
    return n
