"""Painel administrativo — Fase 8: Menus (barras, acesso direto, links úteis, aviso, acervo da legislação, VLibras),
Comunicados e Conheça (perfis com fotos e vídeos)."""
import re
from datetime import date, datetime
from fastapi import APIRouter, Request, HTTPException
from . import db, fase8 as F, menus as MN
from .catalogo import CLASSES, VEDADAS
from .web import ler_form, ir, exige, auditar
from .admin import T, salvar_midia

r = APIRouter(prefix='/_a')

# ---------- Menus ----------
@r.get('/menus')
def menus(request: Request):
    u = exige(request, 'config'); b = request.state.orgao['banco']
    return T('menus', request, u, itens=db.todos(b, 'SELECT * FROM menus ORDER BY barra, ordem, id'), barras=MN.BARRAS, atalhos=db.todos(b, 'SELECT * FROM atalhos ORDER BY ordem, id'),
             links=db.cfg(b, 'links_uteis', []) or [], aviso=db.cfg(b, 'aviso_faixa', {}) or {}, acervo=(db.cfg(b, 'legislacao_acervo') or {}).get('url', ''),
             vlibras=(db.cfg(b, 'acessibilidade', {}) or {}).get('vlibras', True), classes=CLASSES)

@r.post('/menus')
async def menus_post(request: Request):
    u = exige(request, 'config'); f = await ler_form(request); b = request.state.orgao['banco']
    acao = f.get('acao', '')
    if acao in ('item', 'novo'):
        barra, rotulo, destino = f.get('barra', ''), f.get('rotulo', '').strip()[:60], f.get('destino', '').strip()
        mid = int(f['id']) if f.get('id') else None
        if barra not in MN.BARRAS or not rotulo or not MN.destino_valido(destino):
            return ir('/admin/menus', 'Preencha a barra, o rótulo e um destino válido (caminho do portal, como /legislacao, ou endereço https://).', request)
        outro = MN.conflito(b, destino, barra, mid)
        if outro:
            return ir('/admin/menus', f"Recusado: o destino {destino} já está na barra “{MN.BARRAS[outro['barra']]}” (item “{outro['rotulo']}”). Cada destino aparece em uma única barra.", request)
        vals = (barra, rotulo, destino, f.get('icone', '')[:30], int(f.get('ordem') or 100), f.get('ativo') == '1', f.get('classe') if f.get('classe') in CLASSES else 'util', f.get('modulo', '')[:20])
        if mid:
            db.exe(b, 'UPDATE menus SET barra=%s, rotulo=%s, destino=%s, icone=%s, ordem=%s, ativo=%s, classe=%s, modulo=%s WHERE id=%s', vals + (mid,))
        else:
            db.exe(b, 'INSERT INTO menus (barra, rotulo, destino, icone, ordem, ativo, classe, modulo) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', vals)
        auditar(request, f"Menus: item “{rotulo}” ({destino}) salvo na barra {MN.BARRAS[barra]}")
        return ir('/admin/menus', 'Item salvo.', request)
    if acao == 'excluir_item':
        m = db.um(b, 'SELECT * FROM menus WHERE id=%s', (int(f.get('id') or 0),))
        if m:
            db.exe(b, 'DELETE FROM menus WHERE id=%s', (m['id'],)); auditar(request, f"Menus: item “{m['rotulo']}” excluído")
        return ir('/admin/menus', 'Item excluído.', request)
    if acao == 'atalho':
        aid = int(f['id']) if f.get('id') else None
        t, dest = f.get('titulo', '').strip()[:60], f.get('destino', '').strip()
        if not t or not MN.destino_valido(dest):
            return ir('/admin/menus#atalhos', 'Informe o título e um destino válido para o botão.', request)
        vals = (t, f.get('descricao', '').strip()[:120], dest, f.get('icone', 'lista')[:30] or 'lista', int(f.get('ordem') or 100), f.get('ativo') == '1')
        if aid:
            db.exe(b, 'UPDATE atalhos SET titulo=%s, descricao=%s, destino=%s, icone=%s, ordem=%s, ativo=%s WHERE id=%s', vals + (aid,))
        else:
            db.exe(b, 'INSERT INTO atalhos (titulo, descricao, destino, icone, ordem, ativo) VALUES (%s,%s,%s,%s,%s,%s)', vals)
        auditar(request, f'Página inicial: botão de acesso direto “{t}” salvo')
        return ir('/admin/menus#atalhos', 'Botão salvo.', request)
    if acao == 'excluir_atalho':
        db.exe(b, 'DELETE FROM atalhos WHERE id=%s', (int(f.get('id') or 0),)); auditar(request, 'Página inicial: botão de acesso direto excluído')
        return ir('/admin/menus#atalhos', 'Botão excluído.', request)
    if acao == 'links':
        links, erros = [], []
        for n, linha in enumerate((f.get('links') or '').splitlines(), 1):
            if not linha.strip():
                continue
            partes = [x.strip() for x in linha.split('|')]
            if len(partes) < 2 or not partes[1].startswith(('https://', '/')):
                erros.append(str(n)); continue
            links.append({'titulo': partes[0][:120], 'url': partes[1][:300], 'descricao': (partes[2] if len(partes) > 2 else '')[:200]})
        if erros:
            return ir('/admin/menus#links', f"Linha(s) {', '.join(erros)}: use “Título | https://endereço | descrição (opcional)”.", request)
        db.set_cfg(b, 'links_uteis', links); auditar(request, f'Links úteis atualizados ({len(links)})')
        return ir('/admin/menus#links', 'Links úteis salvos.', request)
    if acao == 'aviso':
        txt, link = f.get('texto', '').strip()[:240], f.get('link', '').strip()
        if link and not MN.destino_valido(link):
            return ir('/admin/menus#aviso', 'O link do aviso precisa ser um caminho do portal ou https://.', request)
        db.set_cfg(b, 'aviso_faixa', {'texto': txt, 'link': link, 'rotulo': f.get('rotulo', '').strip()[:40], 'ate': f.get('ate', '')})
        auditar(request, 'Faixa de aviso ' + ('atualizada' if txt else 'removida'))
        return ir('/admin/menus#aviso', 'Faixa de aviso salva.', request)
    if acao == 'acervo':
        url = f.get('url', '').strip()
        if url and not url.startswith('https://'):
            return ir('/admin/menus#acervo', 'Informe o endereço https:// da página de legislação do site atual.', request)
        db.set_cfg(b, 'legislacao_acervo', {'url': url}); auditar(request, 'Legislação: endereço do acervo anterior ' + ('definido' if url else 'removido'))
        return ir('/admin/menus#acervo', 'Endereço do acervo salvo.', request)
    if acao == 'vlibras':
        ac = db.cfg(b, 'acessibilidade', {}) or {}; ac['vlibras'] = f.get('vlibras') == '1'
        db.set_cfg(b, 'acessibilidade', ac); auditar(request, 'VLibras ' + ('ligado' if ac['vlibras'] else 'desligado'))
        return ir('/admin/menus#vlibras', 'VLibras ' + ('ligado.' if ac['vlibras'] else 'desligado.'), request)
    return ir('/admin/menus', '', request)

# ---------- Comunicados ----------
@r.get('/comunicados')
def comunicados(request: Request, id: int = 0):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    return T('comunicados', request, u, itens=db.todos(b, 'SELECT * FROM comunicados ORDER BY coalesce(publicado_em, criado_em) DESC, id DESC LIMIT 200'),
             c=db.um(b, 'SELECT * FROM comunicados WHERE id=%s', (id,)) if id else None, tipos=F.tipos_comunicado(b), classes=CLASSES)

@r.post('/comunicados')
async def comunicados_post(request: Request):
    u = exige(request, 'editar'); f = await ler_form(request); b = request.state.orgao['banco']
    acao = f.get('acao', '')
    if acao == 'tipos':
        exige(request, 'config')
        tipos = [t.strip()[:40] for t in (f.get('tipos') or '').split(',') if t.strip()]
        ruins = [t for t in tipos if t.lower() in F.PROIBIDOS]
        if ruins or not tipos:
            return ir('/admin/comunicados', 'Notícia não é tipo de comunicado: notícias ficam em Conteúdos. Informe os tipos separados por vírgula.', request)
        db.set_cfg(b, 'comunicados_tipos', tipos); auditar(request, 'Comunicados: lista de tipos alterada')
        return ir('/admin/comunicados', 'Tipos salvos.', request)
    cid = int(f['id']) if f.get('id') else None
    if acao == 'situacao' and cid:
        nova = f.get('situacao')
        if nova not in ('publicado', 'arquivado', 'rascunho'):
            raise HTTPException(400)
        if nova == 'publicado':
            exige(request, 'publicar')
            c = db.um(b, 'SELECT * FROM comunicados WHERE id=%s', (cid,))
            from . import eleicao
            if c and c['classe'] in VEDADAS and eleicao.em_defeso(b):
                return ir(f'/admin/comunicados?id={cid}', 'Período eleitoral: esta classificação não pode ser publicada até o fim do defeso.', request)
        db.exe(b, "UPDATE comunicados SET situacao=%s, publicado_em=CASE WHEN %s='publicado' THEN coalesce(publicado_em, now()) ELSE publicado_em END WHERE id=%s", (nova, nova, cid))
        auditar(request, f'Comunicado {cid}: {nova}')
        return ir('/admin/comunicados', 'Situação alterada.', request)
    tipo, titulo = f.get('tipo', ''), f.get('titulo', '').strip()[:200]
    if not F.tipo_comunicado_valido(b, tipo):
        return ir('/admin/comunicados', 'Tipo inválido. Notícia não pode ser cadastrada como comunicado (use Conteúdos → Notícia).', request)
    if not titulo:
        return ir('/admin/comunicados', 'Informe o título.', request)
    try:
        pub = datetime.fromisoformat(f['publicado_em']) if f.get('publicado_em') else None
        val = date.fromisoformat(f['valido_ate']) if f.get('valido_ate') else None
    except ValueError:
        return ir('/admin/comunicados', 'Data inválida.', request)
    classe = f.get('classe') if f.get('classe') in CLASSES else 'util'
    vals = (tipo, titulo, f.get('texto', '')[:20000], pub, val, classe)
    if cid:
        db.exe(b, 'UPDATE comunicados SET tipo=%s, titulo=%s, texto=%s, publicado_em=%s, valido_ate=%s, classe=%s WHERE id=%s', vals + (cid,))
    else:
        cid = db.exe(b, 'INSERT INTO comunicados (tipo, titulo, texto, publicado_em, valido_ate, classe, autor) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (u['nome'],))['id']
    auditar(request, f'Comunicado salvo: {tipo} — {titulo}')
    return ir(f'/admin/comunicados?id={cid}', 'Comunicado salvo como rascunho. Publique quando estiver pronto.' if not f.get('id') else 'Comunicado salvo.', request)

# ---------- Conheça ----------
@r.get('/conheca')
def conheca(request: Request, id: int = 0):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    p = db.um(b, 'SELECT * FROM perfis WHERE id=%s', (id,)) if id else None
    return T('conheca', request, u, perfis=db.todos(b, 'SELECT p.*, (SELECT count(*) FROM perfil_fotos WHERE perfil_id=p.id) nfotos FROM perfis p ORDER BY ordem, id'), p=p,
             fotos=db.todos(b, 'SELECT * FROM perfil_fotos WHERE perfil_id=%s ORDER BY capa DESC, ordem, id', (id,)) if p else [],
             videos=db.todos(b, 'SELECT * FROM perfil_videos WHERE perfil_id=%s ORDER BY ordem, id', (id,)) if p else [], categorias=F.CATEGORIAS, classes=CLASSES)

def _youtube_id(v):
    v = (v or '').strip()
    m = re.search(r'(?:v=|youtu\.be/|embed/|shorts/|live/)([A-Za-z0-9_-]{11})', v)
    return m.group(1) if m else (v if re.match(r'^[A-Za-z0-9_-]{11}$', v) else '')

@r.post('/conheca')
async def conheca_post(request: Request):
    u = exige(request, 'editar'); f = await ler_form(request); b = request.state.orgao['banco']
    acao, pid = f.get('acao', ''), int(f['id']) if f.get('id') else None
    volta = f'/admin/conheca?id={pid}' if pid else '/admin/conheca'
    if acao == 'perfil':
        titulo = f.get('titulo', '').strip()[:120]
        if not titulo:
            return ir(volta, 'Informe o título.', request)
        destaque = f.get('destaque') == '1'
        if destaque and db.um(b, 'SELECT count(*) n FROM perfis WHERE destaque AND id<>%s', (pid or 0,))['n'] >= 3:
            return ir(volta, 'Já há 3 perfis em destaque na página inicial. Tire um deles antes.', request)
        cat = f.get('categoria') if f.get('categoria') in F.CATEGORIAS else 'Lugares'
        classe = 'pub' if cat == 'Eventos' else (f.get('classe') if f.get('classe') in CLASSES else 'util')  # evento da gestão é publicidade (sai no defeso)
        vals = (titulo, f.get('descricao', '')[:20000], cat, classe,
                int(f.get('ordem') or 100), f.get('publicado') == '1', destaque)
        if pid:
            db.exe(b, 'UPDATE perfis SET titulo=%s, descricao=%s, categoria=%s, classe=%s, ordem=%s, publicado=%s, destaque=%s WHERE id=%s', vals + (pid,))
        else:
            s, i = F.slug(titulo), 2
            while db.um(b, 'SELECT 1 FROM perfis WHERE slug=%s', (s,)):
                s = f'{F.slug(titulo)}-{i}'; i += 1
            pid = db.exe(b, 'INSERT INTO perfis (titulo, descricao, categoria, classe, ordem, publicado, destaque, slug) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (s,))['id']
        auditar(request, f'Conheça: perfil “{titulo}” salvo')
        return ir(f'/admin/conheca?id={pid}', 'Perfil salvo.', request)
    if not pid:
        raise HTTPException(400)
    if acao == 'foto':
        arq = f.get('arquivo')
        try:
            url = await salvar_midia(request, u, arq, 'conheca', f.get('alt', '').strip(), f.get('credito', '').strip())
        except ValueError as e:
            return ir(volta, str(e), request)
        pessoas, autoriz = f.get('tem_pessoas') == '1', f.get('autorizacao') == '1'
        capa = f.get('capa') == '1' or not db.um(b, 'SELECT 1 FROM perfil_fotos WHERE perfil_id=%s', (pid,))
        if capa:
            db.exe(b, 'UPDATE perfil_fotos SET capa=FALSE WHERE perfil_id=%s', (pid,))
        db.exe(b, 'INSERT INTO perfil_fotos (perfil_id, url, alt, legenda, credito, tem_pessoas, autorizacao_imagem, capa) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
               (pid, url, f.get('alt', '').strip()[:300], f.get('legenda', '').strip()[:200], f.get('credito', '').strip()[:200], pessoas, autoriz, capa))
        auditar(request, f'Conheça: foto enviada ao perfil {pid}' + (' (com pessoas, autorização ' + ('registrada' if autoriz else 'NÃO registrada: não publica') + ')' if pessoas else ''))
        return ir(volta, 'Foto enviada.' + (' Ela não aparece no portal até a autorização de uso de imagem ser registrada.' if pessoas and not autoriz else ''), request)
    if acao == 'foto_editar':
        fid = int(f.get('foto_id') or 0)
        alt = f.get('alt', '').strip()
        if len(alt) < 5:
            return ir(volta, 'O texto alternativo é obrigatório (pelo menos 5 caracteres).', request)
        if f.get('capa') == '1':
            db.exe(b, 'UPDATE perfil_fotos SET capa=FALSE WHERE perfil_id=%s', (pid,))
        db.exe(b, 'UPDATE perfil_fotos SET alt=%s, legenda=%s, credito=%s, tem_pessoas=%s, autorizacao_imagem=%s, capa=(capa OR %s) WHERE id=%s AND perfil_id=%s',
               (alt[:300], f.get('legenda', '')[:200], f.get('credito', '')[:200], f.get('tem_pessoas') == '1', f.get('autorizacao') == '1', f.get('capa') == '1', fid, pid))
        auditar(request, f'Conheça: foto {fid} do perfil {pid} alterada')
        return ir(volta, 'Foto atualizada.', request)
    if acao == 'foto_excluir':
        db.exe(b, 'DELETE FROM perfil_fotos WHERE id=%s AND perfil_id=%s', (int(f.get('foto_id') or 0), pid)); auditar(request, f'Conheça: foto excluída do perfil {pid}')
        return ir(volta, 'Foto excluída.', request)
    if acao == 'video':
        vid = _youtube_id(f.get('youtube'))
        if not vid:
            return ir(volta, 'Informe o endereço de um vídeo do YouTube.', request)
        db.exe(b, 'INSERT INTO perfil_videos (perfil_id, youtube_id, titulo) VALUES (%s,%s,%s)', (pid, vid, f.get('titulo', '').strip()[:200]))
        auditar(request, f'Conheça: vídeo {vid} no perfil {pid}')
        return ir(volta, 'Vídeo incluído.', request)
    if acao == 'video_excluir':
        db.exe(b, 'DELETE FROM perfil_videos WHERE id=%s AND perfil_id=%s', (int(f.get('video_id') or 0), pid))
        return ir(volta, 'Vídeo excluído.', request)
    return ir(volta, '', request)
