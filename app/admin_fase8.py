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
            return ir('/admin/menus?aba=atalhos', 'Informe o título e um destino válido para o botão.', request)
        vals = (t, f.get('descricao', '').strip()[:120], dest, f.get('icone', 'lista')[:30] or 'lista', int(f.get('ordem') or 100), f.get('ativo') == '1')
        if aid:
            db.exe(b, 'UPDATE atalhos SET titulo=%s, descricao=%s, destino=%s, icone=%s, ordem=%s, ativo=%s WHERE id=%s', vals + (aid,))
        else:
            db.exe(b, 'INSERT INTO atalhos (titulo, descricao, destino, icone, ordem, ativo) VALUES (%s,%s,%s,%s,%s,%s)', vals)
        auditar(request, f'Página inicial: botão de acesso direto “{t}” salvo')
        return ir('/admin/menus?aba=atalhos', 'Botão salvo.', request)
    if acao == 'excluir_atalho':
        db.exe(b, 'DELETE FROM atalhos WHERE id=%s', (int(f.get('id') or 0),)); auditar(request, 'Página inicial: botão de acesso direto excluído')
        return ir('/admin/menus?aba=atalhos', 'Botão excluído.', request)
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
            return ir('/admin/menus?aba=links', f"Linha(s) {', '.join(erros)}: use “Título | https://endereço | descrição (opcional)”.", request)
        db.set_cfg(b, 'links_uteis', links); auditar(request, f'Links úteis atualizados ({len(links)})')
        return ir('/admin/menus?aba=links', 'Links úteis salvos.', request)
    if acao == 'aviso':
        txt, link = f.get('texto', '').strip()[:240], f.get('link', '').strip()
        if link and not MN.destino_valido(link):
            return ir('/admin/menus?aba=aviso', 'O link do aviso precisa ser um caminho do portal ou https://.', request)
        db.set_cfg(b, 'aviso_faixa', {'texto': txt, 'link': link, 'rotulo': f.get('rotulo', '').strip()[:40], 'ate': f.get('ate', '')})
        auditar(request, 'Faixa de aviso ' + ('atualizada' if txt else 'removida'))
        return ir('/admin/menus?aba=aviso', 'Faixa de aviso salva.', request)
    if acao == 'acervo':
        url = f.get('url', '').strip()
        if url and not url.startswith('https://'):
            return ir('/admin/menus?aba=acervo', 'Informe o endereço https:// da página de legislação do site atual.', request)
        db.set_cfg(b, 'legislacao_acervo', {'url': url}); auditar(request, 'Legislação: endereço do acervo anterior ' + ('definido' if url else 'removido'))
        return ir('/admin/menus?aba=acervo', 'Endereço do acervo salvo.', request)
    if acao == 'vlibras':
        ac = db.cfg(b, 'acessibilidade', {}) or {}; ac['vlibras'] = f.get('vlibras') == '1'
        db.set_cfg(b, 'acessibilidade', ac); auditar(request, 'VLibras ' + ('ligado' if ac['vlibras'] else 'desligado'))
        return ir('/admin/menus?aba=vlibras', 'VLibras ' + ('ligado.' if ac['vlibras'] else 'desligado.'), request)
    return ir('/admin/menus', '', request)

def _rico(f, campo):
    """Texto do editor: (html_limpo, texto_puro); sem editor (sem JS), ('', texto). Problema: (None, mensagem)."""
    if not (f.get('html') or '').strip():
        return '', f.get(campo, '')
    from . import editor as ED
    html, probs = ED.limpar(f['html'])
    if probs:
        return None, ' '.join(probs)
    return html, ED.texto(html)

# ---------- Comunicados ----------
@r.get('/comunicados')
def comunicados(request: Request, id: int = 0, aba: str = ''):
    u = exige(request, 'editar'); b = request.state.orgao['banco']
    from . import anexos as AX
    filtro = "situacao='arquivado'" if aba == 'arquivados' else "situacao<>'arquivado'"  # arquivado só na aba "Arquivados"
    itens = db.todos(b, f'SELECT * FROM comunicados WHERE {filtro} ORDER BY coalesce(publicado_em, criado_em) DESC, id DESC LIMIT 200')
    c = db.um(b, 'SELECT * FROM comunicados WHERE id=%s', (id,)) if id else None
    return T('comunicados', request, u, itens=itens, c=c, tipos=F.tipos_comunicado(b), classes=CLASSES,
             anexos=AX.listar(b, c['id']) if c else [], n_anexos=AX.contagem(b, [x['id'] for x in itens]), aceitos=AX.ACEITOS, max_anexos=AX.MAX_POR_COMUNICADO)

@r.post('/comunicados')
async def comunicados_post(request: Request):
    u = exige(request, 'editar'); f = await ler_form(request); b = request.state.orgao['banco']
    acao = f.get('acao', '')
    if acao == 'tipos':  # lista editável: renomear (atualiza os comunicados), remover, adicionar
        exige(request, 'config')
        volta = '/admin/comunicados?aba=config'
        n = int(f.get('n') or 0) if str(f.get('n') or '0').isdigit() else 0
        rem = int(f['remover']) if str(f.get('remover', '')).isdigit() else None
        pares = [(f.get(f'antigo_{i}', ''), re.sub(r'\s+', ' ', f.get(f'tipo_{i}', '')).strip()[:40]) for i in range(min(n, 100)) if i != rem]
        tipos = [novo for _, novo in pares if novo]
        novo = re.sub(r'\s+', ' ', f.get('novo', '')).strip()[:40]
        if novo:
            tipos.append(novo)
        if any(t.lower() in F.PROIBIDOS for t in tipos):
            return ir(volta, 'Notícia não é tipo de comunicado: notícias ficam em “Notícias e páginas”.', request)
        if not tipos:
            return ir(volta, 'Deixe pelo menos um tipo de comunicado.', request)
        if len({t.lower() for t in tipos}) != len(tipos):
            return ir(volta, 'Há dois tipos com o mesmo nome.', request)
        for antigo, novo_nome in pares:
            if antigo and novo_nome and antigo != novo_nome:
                db.exe(b, 'UPDATE comunicados SET tipo=%s WHERE tipo=%s', (novo_nome, antigo))
        db.set_cfg(b, 'comunicados_tipos', tipos); auditar(request, f"Comunicados: tipos — {', '.join(tipos)[:300]}")
        return ir(volta, 'Tipo removido.' if rem is not None else 'Tipo adicionado.' if novo else 'Tipos salvos.', request)
    cid = int(f['id']) if f.get('id') else None
    if acao in ('anexo', 'anexo_remover') and cid:
        from . import anexos as AX
        o = request.state.orgao
        if not db.um(b, 'SELECT 1 FROM comunicados WHERE id=%s', (cid,)):
            raise HTTPException(404)
        volta = f'/admin/comunicados?id={cid}#anexos'
        if acao == 'anexo_remover':
            a = AX.remover(o, int(f.get('anexo_id') or 0), cid)
            if a:
                auditar(request, f'Comunicado {cid}: anexo removido ({a["titulo"]}, {a["nome_original"]})')
            return ir(volta, 'Anexo removido.' if a else 'Anexo não encontrado.', request)
        try:
            aid = await AX.salvar(o, cid, f.get('arquivo'), f.get('titulo_anexo', ''), u['nome'])
        except ValueError as e:
            return ir(volta, f'Anexo não enviado: {e}', request)
        a = db.um(b, 'SELECT * FROM comunicado_anexos WHERE id=%s', (aid,))
        auditar(request, f'Comunicado {cid}: anexo enviado ({a["titulo"]}, {a["nome_original"]}, {AX.tamanho(a["bytes"])})')
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(AX.capa, o, a)  # miniatura já pronta para a página inicial (falha não impede o envio)
        return ir(volta, f'Anexo enviado: {a["titulo"]} ({AX.TIPOS[a["ext"]][1]}, {AX.tamanho(a["bytes"])}).', request)
    from . import aprovacao as AP
    if acao == 'situacao' and cid:
        nova = f.get('situacao')
        if nova not in ('publicado', 'arquivado', 'rascunho', 'revisao', 'devolvido'):
            raise HTTPException(400)
        c = db.um(b, 'SELECT * FROM comunicados WHERE id=%s', (cid,))
        if not c:
            raise HTTPException(404)
        direto = AP.pode_publicar(b, 'comunicados', u, c['autor'])
        if nova in ('publicado', 'arquivado', 'devolvido') and not direto:  # publicar, tirar do ar e devolver: só quem publica
            raise HTTPException(403)
        if nova == 'rascunho' and not direto and c['situacao'] not in ('revisao', 'devolvido'):  # quem não publica só retira o próprio pedido
            raise HTTPException(403)
        if nova == 'revisao' and c['situacao'] not in ('rascunho', 'devolvido'):
            return ir(f'/admin/comunicados?id={cid}', 'Só rascunho ou comunicado devolvido vai para aprovação.', request)
        if nova == 'devolvido':
            if c['situacao'] != 'revisao':
                raise HTTPException(400)
            if not f.get('comentario', '').strip():
                return ir(f'/admin/comunicados?id={cid}', 'Para devolver, escreva o comentário para o autor.', request)
        if nova == 'publicado':
            from . import eleicao
            if c['classe'] in VEDADAS and eleicao.em_defeso(b):
                return ir(f'/admin/comunicados?id={cid}', 'Período eleitoral: esta classificação não pode ser publicada até o fim do defeso.', request)
        db.exe(b, "UPDATE comunicados SET situacao=%s, comentario=%s, publicado_em=CASE WHEN %s='publicado' THEN coalesce(publicado_em, now()) ELSE publicado_em END WHERE id=%s",
               (nova, f.get('comentario', '').strip()[:2000] if nova == 'devolvido' else ('' if nova in ('publicado', 'revisao') else c['comentario']), nova, cid))
        msg = {'publicado': ('Comunicado aprovado e publicado.' if c['situacao'] == 'revisao' else 'Comunicado publicado.'), 'arquivado': 'Comunicado tirado do ar.',
               'rascunho': 'Comunicado voltou a rascunho.', 'revisao': 'Comunicado enviado para aprovação.', 'devolvido': 'Comunicado devolvido ao autor.'}[nova]
        auditar(request, f"Comunicado {cid}: {nova}" + (' (aprovado)' if nova == 'publicado' and c['situacao'] == 'revisao' else ''))
        return ir('/admin/comunicados', msg, request)
    tipo, titulo = f.get('tipo', ''), f.get('titulo', '').strip()[:200]
    atual = db.um(b, 'SELECT tipo FROM comunicados WHERE id=%s', (cid,)) if cid else None
    if not F.tipo_comunicado_valido(b, tipo) and not (atual and atual['tipo'] == tipo and tipo.strip().lower() not in F.PROIBIDOS):  # tipo removido da lista: o comunicado antigo mantém o seu
        return ir('/admin/comunicados', 'Tipo inválido. Notícia não pode ser cadastrada como comunicado (use Conteúdos → Notícia).', request)
    if not titulo:
        return ir('/admin/comunicados', 'Informe o título.', request)
    try:
        from .web import data_hora_form
        pub = data_hora_form(f)
        val = date.fromisoformat(f['valido_ate']) if f.get('valido_ate') else None
    except ValueError:
        return ir('/admin/comunicados', 'Data inválida.', request)
    classe = f.get('classe') if f.get('classe') in CLASSES else 'util'
    html, texto = _rico(f, 'texto')
    if html is None:
        return ir(f'/admin/comunicados?id={cid}' if cid else '/admin/comunicados', texto, request)
    vals = (tipo, titulo, texto[:20000], html, pub, val, classe)
    antes = db.um(b, 'SELECT situacao, autor FROM comunicados WHERE id=%s', (cid,)) if cid else None
    direto = AP.pode_publicar(b, 'comunicados', u, antes['autor'] if antes else u['nome'])
    volta_aprov = bool(antes) and antes['situacao'] in ('publicado', 'revisao') and not direto  # mudou sem poder publicar: sai do ar e espera aprovação
    if cid:
        db.exe(b, 'UPDATE comunicados SET tipo=%s, titulo=%s, texto=%s, html=%s, publicado_em=%s, valido_ate=%s, classe=%s WHERE id=%s', vals + (cid,))
        if volta_aprov:
            db.exe(b, "UPDATE comunicados SET situacao='revisao' WHERE id=%s", (cid,))
    else:
        cid = db.exe(b, 'INSERT INTO comunicados (tipo, titulo, texto, html, publicado_em, valido_ate, classe, autor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (u['nome'],))['id']
    auditar(request, f'Comunicado salvo: {tipo} — {titulo}' + (' (voltou para aprovação)' if volta_aprov else ''))
    if volta_aprov:
        msg = 'Comunicado salvo. A alteração precisa de aprovação: ele fica fora do ar até ser aprovado.' if antes['situacao'] == 'publicado' else 'Comunicado salvo; continua em aprovação.'
    elif not f.get('id'):
        msg = 'Comunicado salvo como rascunho. ' + ('Publique quando estiver pronto.' if direto else 'Envie para aprovação quando estiver pronto.')
    else:
        msg = 'Comunicado salvo.'
    return ir(f'/admin/comunicados?id={cid}', msg, request)

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
    from . import aprovacao as AP, eleicao
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
        html, desc = _rico(f, 'descricao')
        if html is None:
            return ir(volta, desc, request)
        antes = db.um(b, 'SELECT publicado, autor FROM perfis WHERE id=%s', (pid,)) if pid else None
        publicado, aguarda, aviso = AP.salvar_item(b, 'conheca', u, (antes or {}).get('autor') or u['nome'], bool(antes and antes['publicado']), f.get('publicado') == '1')
        vals = (titulo, desc[:20000], cat, classe,
                int(f.get('ordem') or 100), publicado, destaque)
        if pid:
            db.exe(b, 'UPDATE perfis SET titulo=%s, descricao=%s, categoria=%s, classe=%s, ordem=%s, publicado=%s, destaque=%s, html=%s WHERE id=%s', vals + (html, pid))
        else:
            s, i = F.slug(titulo), 2
            while db.um(b, 'SELECT 1 FROM perfis WHERE slug=%s', (s,)):
                s = f'{F.slug(titulo)}-{i}'; i += 1
            pid = db.exe(b, 'INSERT INTO perfis (titulo, descricao, categoria, classe, ordem, publicado, destaque, slug, html, autor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', vals + (s, html, u['nome']))['id']
        if aguarda is not None:
            db.exe(b, "UPDATE perfis SET aguarda_aprovacao=%s, comentario=CASE WHEN %s THEN '' ELSE comentario END WHERE id=%s", (aguarda, aguarda, pid))
        auditar(request, f'Conheça: perfil “{titulo}” salvo' + (' (aguarda aprovação)' if aguarda else ''))
        return ir(f'/admin/conheca?id={pid}', 'Perfil salvo.' + aviso, request)
    if not pid:
        raise HTTPException(400)
    perfil = db.um(b, 'SELECT * FROM perfis WHERE id=%s', (pid,))
    if not perfil:
        raise HTTPException(404)
    pendente = AP.item_novo_pendente(b, 'conheca', u, perfil['autor'] or None)
    if pendente and acao in ('foto', 'foto_editar', 'video'):  # o perfil entra na fila de aprovação; a foto/vídeo fica fora do ar até lá
        db.exe(b, "UPDATE perfis SET aguarda_aprovacao=TRUE WHERE id=%s", (pid,))
    if acao in ('aprovar', 'devolver'):
        if not AP.pode_publicar(b, 'conheca', u, perfil['autor'] or None) or not perfil['aguarda_aprovacao']:
            raise HTTPException(403)
        if acao == 'aprovar':
            if perfil['classe'] in VEDADAS and eleicao.em_defeso(b):
                return ir(volta, 'Período eleitoral: esta classificação não pode ser publicada até o fim do defeso.', request)
            db.exe(b, "UPDATE perfis SET publicado=TRUE, aguarda_aprovacao=FALSE, comentario='' WHERE id=%s", (pid,))
            db.exe(b, 'UPDATE perfil_fotos SET aguarda_aprovacao=FALSE WHERE perfil_id=%s', (pid,))
            db.exe(b, 'UPDATE perfil_videos SET aguarda_aprovacao=FALSE WHERE perfil_id=%s', (pid,))
            auditar(request, f"Conheça: perfil “{perfil['titulo']}” aprovado e publicado por {u['nome']}")
            return ir(volta, 'Perfil aprovado e publicado, com as fotos e vídeos que esperavam aprovação.', request)
        if not f.get('comentario', '').strip():
            return ir(volta, 'Para devolver, escreva o comentário para quem enviou.', request)
        db.exe(b, 'UPDATE perfis SET aguarda_aprovacao=FALSE, comentario=%s WHERE id=%s', (f['comentario'].strip()[:2000], pid))
        auditar(request, f"Conheça: perfil “{perfil['titulo']}” devolvido")
        return ir(volta, 'Perfil devolvido. O que esperava aprovação continua fora do ar.', request)
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
        db.exe(b, 'INSERT INTO perfil_fotos (perfil_id, url, alt, legenda, credito, tem_pessoas, autorizacao_imagem, capa, aguarda_aprovacao) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)',
               (pid, url, f.get('alt', '').strip()[:300], f.get('legenda', '').strip()[:200], f.get('credito', '').strip()[:200], pessoas, autoriz, capa, pendente))
        auditar(request, f'Conheça: foto enviada ao perfil {pid}' + (' (com pessoas, autorização ' + ('registrada' if autoriz else 'NÃO registrada: não publica') + ')' if pessoas else ''))
        return ir(volta, 'Foto enviada.' + (' Ela não aparece no portal até a autorização de uso de imagem ser registrada.' if pessoas and not autoriz else '')
                  + (' Ela fica fora do ar até a aprovação.' if pendente else ''), request)
    if acao == 'foto_editar':
        fid = int(f.get('foto_id') or 0)
        alt = f.get('alt', '').strip()
        if f.get('capa') == '1':
            db.exe(b, 'UPDATE perfil_fotos SET capa=FALSE WHERE perfil_id=%s', (pid,))
        db.exe(b, 'UPDATE perfil_fotos SET alt=%s, legenda=%s, credito=%s, tem_pessoas=%s, autorizacao_imagem=%s, capa=(capa OR %s), aguarda_aprovacao=(aguarda_aprovacao OR %s) WHERE id=%s AND perfil_id=%s',
               (alt[:300], f.get('legenda', '')[:200], f.get('credito', '')[:200], f.get('tem_pessoas') == '1', f.get('autorizacao') == '1', f.get('capa') == '1', pendente, fid, pid))
        auditar(request, f'Conheça: foto {fid} do perfil {pid} alterada' + (' (aguarda aprovação)' if pendente else ''))
        return ir(volta, 'Foto atualizada.' + (' Ela fica fora do ar até a aprovação.' if pendente else ''), request)
    if acao == 'foto_excluir':
        db.exe(b, 'DELETE FROM perfil_fotos WHERE id=%s AND perfil_id=%s', (int(f.get('foto_id') or 0), pid)); auditar(request, f'Conheça: foto excluída do perfil {pid}')
        return ir(volta, 'Foto excluída.', request)
    if acao == 'video':
        vid = _youtube_id(f.get('youtube'))
        if not vid:
            return ir(volta, 'Informe o endereço de um vídeo do YouTube.', request)
        db.exe(b, 'INSERT INTO perfil_videos (perfil_id, youtube_id, titulo, aguarda_aprovacao) VALUES (%s,%s,%s,%s)', (pid, vid, f.get('titulo', '').strip()[:200], pendente))
        auditar(request, f'Conheça: vídeo {vid} no perfil {pid}' + (' (aguarda aprovação)' if pendente else ''))
        return ir(volta, 'Vídeo incluído.' + (' Ele fica fora do ar até a aprovação.' if pendente else ''), request)
    if acao == 'video_excluir':
        db.exe(b, 'DELETE FROM perfil_videos WHERE id=%s AND perfil_id=%s', (int(f.get('video_id') or 0), pid))
        return ir(volta, 'Vídeo excluído.', request)
    return ir(volta, '', request)
