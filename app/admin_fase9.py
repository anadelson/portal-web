"""Painel administrativo — Fase 9: integrações (consulta montada, parâmetros editáveis, teste sem gravar)."""
from fastapi import APIRouter, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask
from . import db, consultas as CS
from .web import ir, exige, auditar
from .admin import T

r = APIRouter(prefix='/_a')

def painel_completo(o, fonte):
    cp = CS.painel(o, fonte)
    t = cp['teste']
    form = {}
    if t and t['relatorio'].get('params_form') is not None and CS.hash_params(t['relatorio']['params_form']) != CS.hash_params(cp['params']):
        form = t['relatorio']['params_form']
    cp['form'] = form
    cp['em_teste'] = bool(form)
    cp['pode_salvar'] = CS.teste_valido(o, fonte, form or cp['params'])
    return cp

def _fontes(o):
    return db.todos(db.LOCAL, 'SELECT fonte, ativo FROM fontes WHERE orgao_id=%s ORDER BY fonte', (o['id'],))

@r.get('/integracoes')
def integracoes(request: Request, fonte: str = ''):
    u = exige(request); o = request.state.orgao
    fs = [dict(f, nome=CS.NOMES.get(f['fonte'], f['fonte'])) for f in _fontes(o)]
    sel = fonte if fonte in {f['fonte'] for f in fs} else (fs[0]['fonte'] if fs else '')
    ult = {x['f']: x for x in db.todos(db.LOCAL, "SELECT DISTINCT ON (split_part(fonte, ':', 1)) split_part(fonte, ':', 1) f, inicio, ok, mensagem FROM coletas WHERE orgao_slug=%s ORDER BY split_part(fonte, ':', 1), id DESC", (o['slug'],))}
    from . import avisos
    from .web import modulos_do_orgao
    ag = None
    if sel:
        from . import agenda as AG
        from datetime import datetime
        fr = CS.fonte_do(o, sel) or {}
        atual = AG.da_fonte(dict(fr, fonte=sel))
        u_ini = ult.get(sel, {}).get('inicio')
        u_ini = u_ini.astimezone().replace(tzinfo=None) if u_ini else None
        ag = {'editavel': AG.editavel(sel), 'fixa': AG.FIXAS.get(sel), 'atual': atual, 'propria': bool(fr.get('agenda')), 'descricao': AG.descrever(atual),
              'vezes': AG.vezes_por_dia(atual), 'proximas': AG.proximas(atual, datetime.now(), u_ini, 5) if AG.editavel(sel) else [],
              'minimo': AG._txt_min(AG.MINIMO.get(sel, 60)), 'padrao': AG.descrever(AG.padrao(sel)), 'dias': AG.DIAS}
    return T('integracoes', request, u, fontes=fs, sel=sel, ult=ult, cp=painel_completo(o, sel) if sel else None, aviso_tv=avisos.transmissoes(o, modulos_do_orgao(o)), ag=ag)

@r.post('/integracoes/{fonte}/agenda')
async def integracao_agenda(request: Request, fonte: str):
    """Agenda de execução escolhida pelo órgão (dias, horários e quantas vezes). Gravada em fontes.agenda; o worker lê a cada minuto."""
    u = exige(request, 'config'); o = request.state.orgao
    form = await request.form()
    if form.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    from . import agenda as AG
    from psycopg.types.json import Jsonb
    volta = f'/admin/integracoes?fonte={fonte}#agenda'
    f = CS.fonte_do(o, fonte)
    if not f:
        raise HTTPException(404)
    antes = AG.descrever(AG.da_fonte(dict(f, fonte=fonte)))
    if form.get('acao') == 'padrao':
        db.exe(db.LOCAL, 'UPDATE fontes SET agenda=NULL WHERE orgao_id=%s AND fonte=%s', (o['id'], fonte))
        auditar(request, f'Integrações: agenda da fonte {fonte} voltou ao padrão ({antes} → {AG.descrever(AG.padrao(fonte))})')
        return ir(volta, 'Agenda voltou ao padrão do sistema.', request)
    ag, erros = AG.validar(fonte, form)
    if erros:
        return ir(volta, 'Agenda não salva: ' + ' '.join(erros), request)
    db.exe(db.LOCAL, 'UPDATE fontes SET agenda=%s WHERE orgao_id=%s AND fonte=%s', (Jsonb(ag), o['id'], fonte))
    auditar(request, f'Integrações: agenda da fonte {fonte} alterada ({antes} → {AG.descrever(ag)})')
    return ir(volta, f'Agenda salva: {AG.descrever(ag)}. Vale a partir da próxima verificação do coletor (a cada minuto).', request)

@r.post('/integracoes/{fonte}')
async def integracao_post(request: Request, fonte: str):
    u = exige(request, 'config'); o = request.state.orgao
    form = await request.form()
    if form.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    volta = form.get('volta') or f'/admin/integracoes?fonte={fonte}'
    if not volta.startswith('/admin/'):
        volta = '/admin/integracoes'
    f = CS.fonte_do(o, fonte)
    if not f or fonte not in CS.ESQUEMA:
        raise HTTPException(404)
    atual = f['params'] or {}
    novo, erros = CS.validar(fonte, form, atual) if CS.ESQUEMA[fonte] else (dict(atual), [])
    if erros:
        return ir(volta, 'Não testado: ' + ' '.join(erros), request)
    acao = form.get('acao')
    if acao == 'testar':
        rel = await run_in_threadpool(CS.ensaiar, o, fonte, novo, form.get('base') or None)
        rel['params_form'] = novo
        CS.registrar_teste(o, fonte, novo, rel, u['nome'])
        auditar(request, f"Integrações: teste da consulta {fonte}" + (f" (base {form.get('base')})" if form.get('base') else '') + (' sem erro' if rel['ok'] else ' com erro') + ' — nada gravado')
        return ir(volta, 'Teste concluído sem erro (nada foi gravado). Agora você pode salvar e coletar.' if rel['ok'] else 'Teste concluído com erro (nada foi gravado). Veja o relatório.', request)
    if acao == 'salvar':
        if not CS.teste_valido(o, fonte, novo):
            return ir(volta, 'Antes de salvar, teste a consulta com exatamente estes parâmetros (o teste vale por 30 minutos).', request)
        mudou = CS.hash_params(novo) != CS.hash_params(atual)
        if mudou and form.get('confirmo') != '1':
            return ir(volta, 'Marque a confirmação: a mudança de endereço ou parâmetros fica registrada no histórico e na auditoria.', request)
        if mudou:
            CS.salvar(o, fonte, atual, novo, u['nome'])
            difs = '; '.join(f'{k}: {atual.get(k)} → {v}' for k, v in novo.items() if atual.get(k) != v)
            auditar(request, f'Integrações: parâmetros da fonte {fonte} alterados ({difs[:300]})')
        from .worker import rodar
        from . import orgaos
        oo = dict(orgaos.por_id(o['id']) or o)
        resp = ir(volta, ('Parâmetros salvos. ' if mudou else 'Parâmetros sem mudança. ') + 'A coleta começou agora; o resultado aparece em “Última execução” em alguns minutos.', request)
        resp.background = BackgroundTask(rodar, oo, fonte, novo)
        auditar(request, f'Integrações: coleta manual da fonte {fonte} iniciada')
        return resp
    raise HTTPException(400)

# ---------- Identidade e tema (abas) ----------
import io, re, secrets
from pathlib import Path
from . import config
from .web import ler_form

def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def contraste(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)

TEXTO_ESCURO = '#17212B'
REDES = {'instagram': 'Instagram', 'facebook': 'Facebook', 'youtube': 'YouTube', 'x': 'X (Twitter)', 'tiktok': 'TikTok', 'whatsapp': 'WhatsApp', 'linkedin': 'LinkedIn', 'outra': 'Outra'}
HOSTS_REDE = {'instagram': ('instagram.com',), 'facebook': ('facebook.com', 'fb.com'), 'youtube': ('youtube.com', 'youtu.be'), 'x': ('x.com', 'twitter.com'),
              'tiktok': ('tiktok.com',), 'whatsapp': ('wa.me', 'whatsapp.com'), 'linkedin': ('linkedin.com',)}
LICENCAS = ['CC BY 4.0', 'CC BY-SA 4.0', 'CC0 (domínio público)', 'Uso institucional (cedida ao órgão)', 'Todos os direitos reservados']
FOTOS_POR_PAGINA = 48   # miniaturas por página na tela do álbum (painel); no portal, PORTAL_FOTOS_POR_PAGINA
MAX_FOTOS_ENVIO = 20    # fotos por envio (o proxy aceita até 25 MB por requisição)
COR = re.compile(r'^#[0-9A-Fa-f]{6}$')

def checar_cores(cor, dest):
    """Devolve lista de problemas de contraste (WCAG AA 4,5:1): texto branco sobre a cor principal; texto escuro sobre o destaque."""
    erros = []
    if not COR.match(cor or '') or not COR.match(dest or ''):
        return ['Use o formato #RRGGBB.']
    if contraste(cor, '#FFFFFF') < 4.5:
        erros.append(f'Cor principal {cor}: contraste com texto branco {contraste(cor, "#FFFFFF"):.1f}:1 (mínimo 4,5:1).')
    if contraste(dest, TEXTO_ESCURO) < 4.5:
        erros.append(f'Cor de destaque {dest}: contraste com texto escuro {contraste(dest, TEXTO_ESCURO):.1f}:1 (mínimo 4,5:1).')
    return erros

@r.post('/identidade/cores')
async def ident_cores(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    cor, dest = (f.get('cor') or '').upper(), (f.get('cor_destaque') or '').upper()
    erros = checar_cores(cor, dest)
    if erros:
        return ir('/admin/identidade?aba=tema', 'Recusado (acessibilidade AA): ' + ' '.join(erros), request)
    ident = db.cfg(b, 'identidade', {}) or {}
    antes = (ident.get('cor'), ident.get('cor_destaque'))
    from .web import LARGURAS, LARGURA_PADRAO
    v = f.get('largura', '')
    larg = 'tela' if v == 'tela' else (int(v) if str(v).isdigit() and int(v) in LARGURAS else LARGURA_PADRAO)
    antes_l = ident.get('largura') or LARGURA_PADRAO
    from . import rodape as ROD
    tipo = request.state.orgao['tipo']
    rod_antes = ROD.cor_de(ident, tipo)
    rod = ROD.cor_padrao(tipo) if f.get('rodape_padrao') == '1' else ((f.get('cor_rodape') or '').upper() or rod_antes)
    erros_rod = ROD.checar_cor(rod, tipo)
    if erros_rod:
        return ir('/admin/identidade?aba=tema', f'Recusado (acessibilidade AA): cor do rodapé {rod}: ' + '; '.join(erros_rod) + '.', request)
    ident['cor'], ident['cor_destaque'], ident['largura'] = cor, dest, larg
    ident['cor_rodape'] = '' if rod == ROD.cor_padrao(tipo) else rod  # vazio = cor padrão do tipo de órgão
    db.set_cfg(b, 'identidade', ident)
    auditar(request, f'Identidade: cores {antes[0]}/{antes[1]} → {cor}/{dest}; rodapé {rod_antes} → {rod}; largura máxima {antes_l} → {larg}')
    msg = 'Tema salvo.'
    fundo = ident.get('rodape') or {}
    if fundo.get('url'):  # com imagem no rodapé, a camada nunca fica abaixo do mínimo seguro para a nova cor
        c = ROD.conf(b); m = ROD.minimo_seguro(rod, fundo.get('lum95'), tipo)
        if c['camada'] < m:
            c['camada'] = m; db.set_cfg(b, 'rodape', c)
            auditar(request, f'Rodapé: camada de cor ajustada para {m}% (mínimo seguro com a nova cor)')
            msg += f' A camada de cor do rodapé subiu para {m}%, o mínimo com contraste AA.'
    return ir('/admin/identidade?aba=tema', msg, request)

@r.post('/identidade/rodape')
async def ident_rodape(request: Request):
    """Seção Rodapé: transparência da camada de cor e mascote (lado, tamanho, transparência, celular, período eleitoral)."""
    u = exige(request, 'config'); f = await ler_form(request); o = request.state.orgao; b = o['banco']
    from . import rodape as ROD
    ident = db.cfg(b, 'identidade', {}) or {}
    antes, novo = ROD.conf(b), ROD.validar(f)
    fundo = ident.get('rodape') or {}
    if fundo.get('url'):
        m = ROD.minimo_seguro(ROD.cor_de(ident, o['tipo']), fundo.get('lum95'), o['tipo'])
        if novo['camada'] < m:
            t, h = ROD.contraste_camada(ROD.cor_de(ident, o['tipo']), fundo.get('lum95'), novo['camada'], o['tipo'])
            return ir('/admin/identidade?aba=imagens#rodape', f'Recusado (acessibilidade AA): com a camada em {novo["camada"]}% o contraste fica em '
                      f'{min(t, h):.1f}:1 (mínimo 4,5:1). Use pelo menos {m}%.'.replace('.', ',', 1), request)
    else:
        novo['camada'] = antes['camada']  # sem imagem de fundo a cor é sólida; o valor guardado não muda
    if not ((ident.get('mascote') or {}).get('url')):
        for k in novo:
            if k.startswith('mascote_'):
                novo[k] = antes[k]  # sem mascote os controles ficam desativados
    db.set_cfg(b, 'rodape', novo)
    mud = [f'{k}: {antes[k]} → {novo[k]}' for k in novo if antes.get(k) != novo[k]]
    auditar(request, 'Rodapé: ' + ('; '.join(mud) if mud else 'salvo sem mudanças'))
    return ir('/admin/identidade?aba=imagens#rodape', 'Rodapé salvo.', request)

FAVICON_TAMANHOS = (16, 32, 180, 512)
SVG_PROIBIDO = re.compile(r'<\s*(script|foreignObject|iframe|object|embed)|\son\w+\s*=|javascript:|xlink:href\s*=\s*["\'](?!#)|href\s*=\s*["\'](?!#)', re.I)

def gerar_favicon(dados_png, pasta):
    from PIL import Image
    im = Image.open(io.BytesIO(dados_png)); im.load()
    if im.width < 180 or im.height < 180:
        raise ValueError('Use uma imagem PNG quadrada de pelo menos 180×180 (ideal 512×512).')
    if abs(im.width - im.height) > max(im.width, im.height) * 0.05:
        raise ValueError('A imagem do favicon precisa ser quadrada.')
    im = im.convert('RGBA')
    sufixo, out = secrets.token_hex(8), {}
    for t in FAVICON_TAMANHOS:
        nome = f'favicon-{sufixo}-{t}.png'
        im.resize((t, t), Image.LANCZOS).save(pasta / nome, 'PNG', optimize=True)
        out[str(t)] = f'/midia/{nome}'
    return out

@r.post('/identidade/favicon')
async def ident_favicon(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); o = request.state.orgao; b = o['banco']
    from .imagens import LIMITE_UPLOAD
    ident = db.cfg(b, 'identidade', {}) or {}
    from . import imagens as IMG
    if f.get('acao') == 'remover':
        IMG.guardar_anterior(ident, 'favicon', ident.pop('favicon', None)); db.set_cfg(b, 'identidade', ident)
        auditar(request, 'Identidade: favicon removido (os arquivos continuam na biblioteca de mídia)')
        return ir('/admin/identidade?aba=favicon', 'Favicon removido: o portal volta ao ícone padrão da plataforma. Os arquivos continuam guardados.', request)
    if f.get('acao') == 'restaurar':
        fav = IMG.restaurar_anterior(ident, 'favicon', ident.get('favicon'))
        if not fav:
            return ir('/admin/identidade?aba=favicon', 'Não há favicon anterior para restaurar.', request)
        ident['favicon'] = fav; db.set_cfg(b, 'identidade', ident); auditar(request, 'Identidade: favicon anterior restaurado')
        return ir('/admin/identidade?aba=favicon', 'Favicon anterior restaurado.', request)
    png, svg = f.get('png'), f.get('svg')
    pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'; pasta.mkdir(parents=True, exist_ok=True)
    try:
        if not (png is not None and getattr(png, 'filename', '')):
            raise ValueError('Envie o PNG quadrado (gera os tamanhos 16, 32, 180 e 512).')
        dados = await png.read(LIMITE_UPLOAD + 1)
        if len(dados) > LIMITE_UPLOAD or dados[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('O arquivo precisa ser PNG de até 3 MB.')
        fav = gerar_favicon(dados, pasta)
        if svg is not None and getattr(svg, 'filename', ''):
            sd = await svg.read(200_000)
            txt = sd.decode('utf-8', 'replace')
            if '<svg' not in txt[:2000] or SVG_PROIBIDO.search(txt):
                raise ValueError('SVG recusado: precisa ser um desenho simples, sem scripts, eventos ou links externos.')
            nome = f'favicon-{secrets.token_hex(8)}.svg'
            (pasta / nome).write_bytes(sd); fav['svg'] = f'/midia/{nome}'
    except ValueError as e:
        return ir('/admin/identidade?aba=favicon', str(e), request)
    IMG.guardar_anterior(ident, 'favicon', ident.get('favicon'))
    ident['favicon'] = fav; db.set_cfg(b, 'identidade', ident)
    auditar(request, 'Identidade: favicon atualizado (' + ', '.join(fav) + ')')
    return ir('/admin/identidade?aba=favicon', 'Favicon gerado nos tamanhos 16, 32, 180 e 512.', request)

def rede_valida(tipo, url):
    if tipo not in REDES or not re.match(r'^https://[^\s"<>]+$', url or ''):
        return False
    host = re.sub(r'^https://(www\.|m\.)?', '', url).split('/')[0].lower()
    return tipo == 'outra' or any(host == h or host.endswith('.' + h) for h in HOSTS_REDE.get(tipo, ()))

@r.post('/identidade/redes')
async def ident_redes(request: Request):
    u = exige(request, 'config'); b = request.state.orgao['banco']
    form = await request.form()
    if form.get('csrf') != request.session.get('csrf'):
        raise HTTPException(400, 'Formulário expirado. Volte e tente de novo.')
    tipos, urls, ords, contas = form.getlist('tipo'), form.getlist('url'), form.getlist('ordem'), form.getlist('conta')
    redes, erros = [], []
    for k, (t, url) in enumerate(zip(tipos, urls)):
        url = (url or '').strip()
        if not url:
            continue
        if not rede_valida(t, url):
            erros.append(f'linha {k + 1} ({REDES.get(t, t)}): endereço https:// da própria rede')
            continue
        conta = (contas[k] if k < len(contas) else '').strip()[:60]
        if conta and not re.fullmatch(r'[\w-]{3,60}', conta):
            erros.append(f'linha {k + 1}: identificador da conta só com letras, números, _ e -')
            continue
        redes.append({'tipo': t, 'nome': REDES[t], 'url': url[:300], 'ordem': int(ords[k]) if k < len(ords) and str(ords[k]).isdigit() else 100, 'conta': conta})
    if erros:
        return ir('/admin/identidade?aba=redes', 'Não salvo: ' + '; '.join(erros) + '.', request)
    redes.sort(key=lambda x: x['ordem'])
    ident = db.cfg(b, 'identidade', {}) or {}
    ident['redes_v2'] = redes
    ident['redes'] = [[x['nome'], x['url']] for x in redes]  # compatibilidade com o rodapé antigo
    db.set_cfg(b, 'identidade', ident)
    auditar(request, f'Identidade: redes sociais ({len(redes)})')
    return ir('/admin/identidade?aba=redes', 'Redes sociais salvas.', request)

@r.post('/identidade/municipio')
async def ident_municipio(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    from . import municipio
    m = {k: (f.get(k) or '').strip()[:60] for k, _ in municipio.MANUAIS}
    db.set_cfg(b, 'municipio_manual', m)
    auditar(request, 'Identidade: dados manuais do município atualizados')
    from .web import volta_segura
    return ir(volta_segura(f, '/admin/identidade?aba=municipio'), 'Dados do município salvos.', request)

# ---------- Fotos e álbuns ----------
def _int(v):
    return int(v) if str(v or '').isdigit() else None

@r.post('/identidade/fotos')
async def ident_fotos(request: Request):
    u = exige(request, 'editar'); f = await ler_form(request); b = request.state.orgao['banco']
    from .admin import salvar_midia
    from . import aprovacao as AP
    acao = f.get('acao', ''); aid = _int(f.get('album_id'))
    volta = f'/admin/identidade?aba=fotos' + (f'&album={aid}' if aid else '')
    if acao == 'categorias':  # lista editável: renomear, suspender no defeso, remover, adicionar
        volta = '/admin/identidade?aba=fotos&sub=categorias'
        rem = _int(f.get('remover'))
        if rem:
            db.exe(b, 'DELETE FROM foto_categorias WHERE id=%s', (rem,)); auditar(request, f'Fotos: categoria {rem} removida (álbuns ficam sem categoria)')
            return ir(volta, 'Categoria removida. Os álbuns dela ficaram sem categoria.', request)
        n = _int(f.get('n')) or 0
        lista = [(_int(f.get(f'cat_id_{i}')), re.sub(r'\s+', ' ', f.get(f'cat_nome_{i}', '')).strip()[:60], f.get(f'cat_susp_{i}') == '1') for i in range(min(n, 200))]
        novo = re.sub(r'\s+', ' ', f.get('novo', '')).strip()[:60]
        nomes = [x[1].lower() for x in lista if x[1]] + ([novo.lower()] if novo else [])
        if len(set(nomes)) != len(nomes):
            return ir(volta, 'Há duas categorias com o mesmo nome.', request)
        for cid_, nome, susp in lista:
            if cid_ and nome:
                db.exe(b, 'UPDATE foto_categorias SET nome=%s, suspender_defeso=%s WHERE id=%s', (nome, susp, cid_))
        if novo:
            db.exe(b, 'INSERT INTO foto_categorias (nome, suspender_defeso) VALUES (%s,%s)', (novo, f.get('novo_susp') == '1'))
        auditar(request, 'Fotos: categorias alteradas' + (f' (nova: {novo})' if novo else ''))
        return ir(volta, 'Categoria adicionada.' if novo else 'Categorias salvas.', request)
    if acao == 'categoria':
        nome = re.sub(r'\s+', ' ', f.get('nome', '')).strip()[:60]
        if not nome:
            return ir(volta, 'Informe o nome da categoria.', request)
        db.exe(b, 'INSERT INTO foto_categorias (nome, suspender_defeso) VALUES (%s,%s) ON CONFLICT (nome) DO UPDATE SET suspender_defeso=EXCLUDED.suspender_defeso', (nome, f.get('suspender') == '1'))
        auditar(request, f'Fotos: categoria “{nome}”' + (' (suspensa no período eleitoral)' if f.get('suspender') == '1' else ''))
        return ir(volta, 'Categoria salva.', request)
    if acao == 'album':
        t = f.get('titulo', '').strip()[:160]
        if not t:
            return ir(volta, 'Informe o título do álbum.', request)
        antes = db.um(b, 'SELECT publicado, autor FROM albuns WHERE id=%s', (aid,)) if aid else None
        publicado, aguarda, aviso = AP.salvar_item(b, 'fotos', u, (antes or {}).get('autor') or u['nome'], bool(antes and antes['publicado']), f.get('publicado') == '1')
        vals = (t, f.get('descricao', '')[:2000], _int(f.get('categoria_id')), publicado)
        if aid:
            db.exe(b, 'UPDATE albuns SET titulo=%s, descricao=%s, categoria_id=%s, publicado=%s WHERE id=%s', vals + (aid,))
        else:
            aid = db.exe(b, 'INSERT INTO albuns (titulo, descricao, categoria_id, publicado, autor) VALUES (%s,%s,%s,%s,%s) RETURNING id', vals + (u['nome'],))['id']
        if aguarda is not None:
            db.exe(b, "UPDATE albuns SET aguarda_aprovacao=%s, comentario=CASE WHEN %s THEN '' ELSE comentario END WHERE id=%s", (aguarda, aguarda, aid))
        auditar(request, f'Fotos: álbum “{t}” salvo' + (' (aguarda aprovação)' if aguarda else ''))
        return ir(f'/admin/identidade?aba=fotos&album={aid}', 'Álbum salvo.' + aviso, request)
    if not aid:
        raise HTTPException(400)
    alb = db.um(b, 'SELECT * FROM albuns WHERE id=%s', (aid,))
    if not alb:
        raise HTTPException(404)
    pendente = AP.item_novo_pendente(b, 'fotos', u, alb['autor'] or None)
    if acao in ('aprovar', 'devolver'):
        if not AP.pode_publicar(b, 'fotos', u, alb['autor'] or None) or not alb['aguarda_aprovacao']:
            raise HTTPException(403)
        if acao == 'aprovar':
            db.exe(b, "UPDATE albuns SET publicado=TRUE, aguarda_aprovacao=FALSE, comentario='' WHERE id=%s", (aid,))
            db.exe(b, 'UPDATE album_fotos SET aguarda_aprovacao=FALSE WHERE album_id=%s', (aid,))
            auditar(request, f"Fotos: álbum “{alb['titulo']}” aprovado e publicado por {u['nome']}")
            return ir(volta, 'Álbum aprovado e publicado, com as fotos que esperavam aprovação.', request)
        if not f.get('comentario', '').strip():
            return ir(volta, 'Para devolver, escreva o comentário para quem enviou.', request)
        db.exe(b, 'UPDATE albuns SET aguarda_aprovacao=FALSE, comentario=%s WHERE id=%s', (f['comentario'].strip()[:2000], aid))
        auditar(request, f"Fotos: álbum “{alb['titulo']}” devolvido")
        return ir(volta, 'Álbum devolvido. As fotos que esperavam aprovação continuam fora do ar.', request)
    if acao == 'foto':  # uma ou várias fotos por envio; crédito, licença, categoria e autorização valem para todas
        if f.get('licenca') not in LICENCAS:
            return ir(volta, 'Escolha a licença das fotos.', request)
        arquivos = [x for x in (await request.form()).getlist('arquivo') if getattr(x, 'filename', '')]
        if not arquivos:
            return ir(volta, 'Escolha pelo menos uma foto.', request)
        if len(arquivos) > MAX_FOTOS_ENVIO:
            return ir(volta, f'Envie no máximo {MAX_FOTOS_ENVIO} fotos por vez.', request)
        pessoas, autoriz = f.get('tem_pessoas') == '1', f.get('autorizacao') == '1'
        ok, erros = 0, []
        for arq in arquivos:
            try:
                url = await salvar_midia(request, u, arq, 'album', f.get('alt', '').strip(), f.get('credito', '').strip())
            except ValueError as e:
                erros.append(f'{arq.filename}: {e}'); continue
            primeira = not db.um(b, 'SELECT 1 FROM album_fotos WHERE album_id=%s', (aid,))
            db.exe(b, '''INSERT INTO album_fotos (album_id, url, titulo, descricao, credito, licenca, alt, categoria_id, tem_pessoas, autorizacao_imagem, principal, aguarda_aprovacao)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (aid, url, f.get('titulo', '')[:160], f.get('descricao', '')[:1000], f.get('credito', '')[:200],
                                                                      f['licenca'], f.get('alt', '').strip()[:300], _int(f.get('categoria_id')), pessoas, autoriz, primeira, pendente))
            ok += 1
        if ok and pendente:
            db.exe(b, 'UPDATE albuns SET aguarda_aprovacao=TRUE WHERE id=%s', (aid,))
        auditar(request, f'Fotos: {ok} foto(s) enviada(s) ao álbum {aid}' + (' (com pessoas, sem autorização: não publicam)' if pessoas and not autoriz else '') + (f'; {len(erros)} recusada(s)' if erros else ''))
        msg = f'{ok} foto(s) enviada(s).' + (' Elas só aparecem no portal com a autorização de uso de imagem registrada.' if ok and pessoas and not autoriz else '') + (' Elas ficam fora do ar até a aprovação.' if ok and pendente else '')
        if erros:
            msg += ' Não enviadas: ' + '; '.join(erros)[:400]
        return ir(volta + '#fotos', msg, request)
    fid = _int(f.get('foto_id'))
    x = db.um(b, 'SELECT * FROM album_fotos WHERE id=%s AND album_id=%s', (fid, aid)) if fid else None
    if not x:
        raise HTTPException(404)
    if acao == 'foto_editar':
        alt = f.get('alt', '').strip()
        if f.get('licenca') not in LICENCAS:
            return ir(volta, 'Escolha a licença da foto.', request)
        db.exe(b, '''UPDATE album_fotos SET titulo=%s, descricao=%s, credito=%s, licenca=%s, alt=%s, categoria_id=%s, tem_pessoas=%s, autorizacao_imagem=%s, aguarda_aprovacao=(aguarda_aprovacao OR %s) WHERE id=%s''',
               (f.get('titulo', '')[:160], f.get('descricao', '')[:1000], f.get('credito', '')[:200], f['licenca'], alt[:300], _int(f.get('categoria_id')),
                f.get('tem_pessoas') == '1', f.get('autorizacao') == '1', pendente, fid))
        if pendente:
            db.exe(b, 'UPDATE albuns SET aguarda_aprovacao=TRUE WHERE id=%s', (aid,))
        auditar(request, f'Fotos: foto {fid} alterada' + (' (aguarda aprovação)' if pendente else ''))
        return ir(f'{volta}&foto={fid}#foto', 'Foto salva.' + (' Ela fica fora do ar até a aprovação.' if pendente else ''), request)
    if acao == 'foto_excluir':
        db.exe(b, 'DELETE FROM album_fotos WHERE id=%s', (fid,)); auditar(request, f'Fotos: foto {fid} excluída')
        return ir(volta, 'Foto excluída.', request)
    if acao == 'principal':
        db.exe(b, 'UPDATE album_fotos SET principal=(id=%s) WHERE album_id=%s', (fid, aid)); auditar(request, f'Fotos: foto {fid} é a principal do álbum {aid}')
        return ir(f'{volta}&foto={fid}#foto', 'Esta foto agora é a capa do álbum.', request)
    if acao == 'destaque_portal':
        exige(request, 'config')
        if x['tem_pessoas'] and not x['autorizacao_imagem']:
            return ir(volta, 'Esta foto tem pessoas sem autorização de uso de imagem: não pode ser o destaque do portal.', request)
        ident = db.cfg(b, 'identidade', {}) or {}
        ident['hero'] = {'url': x['url'], 'alt': x['alt'], 'credito': (x['credito'] + (f' · {x["licenca"]}' if x['licenca'] else '')).strip(' ·')}
        db.set_cfg(b, 'identidade', ident); auditar(request, f'Fotos: foto {fid} virou o destaque da página inicial')
        return ir(volta, 'Foto definida como destaque da página inicial.', request)
    raise HTTPException(400)

# ---------- Editor: imagem no corpo do texto; versões (comparar e restaurar) ----------
from fastapi.responses import JSONResponse

@r.post('/editor/imagem')
async def editor_imagem(request: Request):
    u = exige(request, 'editar'); f = await ler_form(request)
    from .admin import salvar_midia
    try:
        url = await salvar_midia(request, u, f.get('arquivo'), 'conteudo', (f.get('alt') or '').strip(), (f.get('credito') or '').strip())
    except (ValueError, AttributeError) as e:
        return JSONResponse({'erro': str(e) or 'Arquivo inválido.'}, status_code=400)
    auditar(request, 'Editor: imagem enviada para o corpo de um texto')
    return JSONResponse({'url': url})

def _linhas_dif(a, b):
    import difflib
    out = []
    for l in difflib.ndiff((a or '').splitlines(), (b or '').splitlines()):
        if l.startswith('? '):
            continue
        out.append({'tipo': {'- ': 'removido', '+ ': 'incluido'}.get(l[:2], 'igual'), 'texto': l[2:]})
    return out

@r.get('/conteudos/{cid}/versao/{vid}')
def versao(request: Request, cid: int, vid: int):
    u = exige(request); b = request.state.orgao['banco']
    c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,))
    v = db.um(b, 'SELECT * FROM conteudo_versoes WHERE id=%s AND conteudo_id=%s', (vid, cid))
    if not c or not v or not v['dados']:
        raise HTTPException(404, 'Versão sem cópia do texto (anterior à Fase 9).')
    d = v['dados']
    campos = [('Título', d.get('titulo'), c['titulo']), ('Resumo', d.get('resumo'), c['resumo']), ('Texto', d.get('texto'), c['texto'])]
    return T('versao', request, u, c=c, v=v, difs=[(n, _linhas_dif(a, b2)) for n, a, b2 in campos])

@r.post('/conteudos/{cid}/versao/{vid}')
async def versao_restaurar(request: Request, cid: int, vid: int):
    u = exige(request, 'editar'); f = await ler_form(request); b = request.state.orgao['banco']
    c = db.um(b, 'SELECT * FROM conteudos WHERE id=%s', (cid,))
    v = db.um(b, 'SELECT * FROM conteudo_versoes WHERE id=%s AND conteudo_id=%s', (vid, cid))
    if not c or not v or not v['dados']:
        raise HTTPException(404)
    if c['situacao'] not in ('rascunho', 'devolvido', 'revisao'):
        return ir(f'/admin/conteudos/{cid}', 'Para restaurar, o conteúdo precisa estar em rascunho (tire do ar e arquive, ou crie um rascunho).', request)
    d = v['dados']
    db.exe(b, "UPDATE conteudos SET titulo=%s, resumo=%s, texto=%s, html=%s, situacao='rascunho', atualizado_em=now() WHERE id=%s",
           (d.get('titulo') or c['titulo'], d.get('resumo') or '', d.get('texto') or '', d.get('html') or '', cid))
    from psycopg.types.json import Jsonb
    db.exe(b, 'INSERT INTO conteudo_versoes (conteudo_id, quem, obs, dados) VALUES (%s,%s,%s,%s)', (cid, u['nome'], f"Restaurou a versão de {v['quando'].astimezone().strftime('%d/%m/%Y %H:%M')}", Jsonb(d)))
    auditar(request, f'Conteúdo {cid}: versão {vid} restaurada (volta como rascunho)')
    return ir(f'/admin/conteudos/{cid}', 'Versão restaurada como rascunho. Publique ou envie para aprovação quando estiver pronto.', request)


# ---------- 25/11/2026: sistemas de terceiros (transparência da empresa contratada, Diário, e-SIC, Ouvidoria) ----------
@r.get('/sistemas-terceiros')
def sistemas_terceiros(request: Request):
    u = exige(request, 'config')
    from . import sistemas as SIS
    cad = db.cfg(request.state.orgao['banco'], SIS.CHAVE, {}) or {}
    return T('sistemas_terceiros', request, u, sis=SIS.SISTEMAS, cad=cad, base=SIS.BASE_LEGAL, erros=[])

@r.post('/sistemas-terceiros')
async def sistemas_terceiros_salvar(request: Request):
    u = exige(request, 'config')
    from .web import ler_form
    from . import sistemas as SIS
    f = await ler_form(request)
    dados, erros = SIS.salvar(request.state.orgao['banco'], f)
    if erros:
        cad = {k: {'url': f.get(f'url_{k}', ''), 'empresa': f.get(f'empresa_{k}', ''), 'nova_aba': f.get(f'aba_{k}') == 'nova'} for k in SIS.SISTEMAS}
        return T('sistemas_terceiros', request, u, sis=SIS.SISTEMAS, cad=cad, base=SIS.BASE_LEGAL, erros=erros)
    auditar(request, 'Sistemas de terceiros: ' + (', '.join(SIS.SISTEMAS[k][0] for k in dados) or 'nenhum endereço'))
    return ir('/admin/sistemas-terceiros', 'Endereços salvos.', request)


# ---------- Credenciais de API do próprio órgão (25/11/2026): YouTube e Meta; só gravação ----------
@r.get('/credenciais-api')
def credenciais_api(request: Request):
    u = exige(request, 'config')
    from . import credenciais as CR
    b = request.state.orgao['banco']
    itens = [dict(v, chave=k, sit=CR.situacao_orgao(b, k)) for k, v in CR.FONTES_ORGAO.items()]
    return T('credenciais_api', request, u, itens=itens, chave_ok=CR.chave_ok())

@r.post('/credenciais-api')
async def credenciais_api_post(request: Request):
    u = exige(request, 'config')
    from .web import ler_form
    from . import credenciais as CR
    b = request.state.orgao['banco']
    f = await ler_form(request)
    fonte, acao = f.get('fonte', ''), f.get('acao', '')
    volta = '/admin/credenciais-api'
    if fonte not in CR.FONTES_ORGAO:
        return ir(volta, 'Fonte desconhecida.', request)
    nome = CR.FONTES_ORGAO[fonte]['nome']
    if acao == 'salvar':
        try:
            res = CR.salvar_orgao(b, fonte, f.get('chave', ''), u['nome'])
        except CR.SemChave:
            return ir(volta, 'Cadastro desligado: falta a chave de cifra no servidor. Fale com o suporte da plataforma.', request)
        except ValueError as e:
            return ir(volta, f'Não gravado: {e}.', request)
        auditar(request, f'Credencial de API {nome}: {res}')
        return ir(volta, f'Credencial {res}. O valor não é exibido nem registrado.', request)
    if acao == 'apagar':
        if CR.apagar_orgao(b, fonte):
            auditar(request, f'Credencial de API {nome}: apagada')
            return ir(volta, 'Credencial apagada. A consulta a esta API fica desligada até cadastrar outra.', request)
        return ir(volta, 'Não havia credencial cadastrada.', request)
    if acao == 'testar':
        res = await run_in_threadpool(CR.testar_orgao, b, fonte, u['nome'])
        auditar(request, f'Credencial de API {nome}: testada ({res})')
        return ir(volta, f'Teste de conexão: {res}.', request)
    return ir(volta, '', request)
