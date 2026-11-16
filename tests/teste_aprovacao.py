# Pedido de 15/11/2026: política de aprovação para publicar, módulo a módulo — exige aprovação (e de quem) ou publica direto.
# Vale para notícias e páginas, comunicados, Conheça, fotos e álbuns e os atos da Câmara; Diário, Carta de Serviços,
# exceção eleitoral e moderação das manifestações têm regras próprias e não mudam.
# Pessoas e conteúdos FICTÍCIOS. Só contra banco de TESTE:  PYTHONPATH=. python tests/teste_aprovacao.py
import io, os, re, sys
if os.environ.get('PG_HOST', 'db') == 'db' or not os.environ.get('TESTE'):
    sys.exit('Recusado: rode só contra o banco de TESTE (TESTE=1 e PG_HOST de teste).')
from fastapi.testclient import TestClient
from app.main import app
from app import db, aprovacao as AP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apoio import entrar, tok

erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
PM, CM = 'bd_pm_bora', 'bd_cm_bora'
def cli(host='pmbora.localhost'):
    return TestClient(app, base_url=f'http://{host}')
def png(w=40, h=30):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (w, h), (14, 77, 100)).save(b, 'PNG'); return b.getvalue()
def post(c, url, dados, de=None, files=None):
    return c.post(url, data=dict({'csrf': tok(c, de or url)}, **dados), files=files, follow_redirects=True)
def msg(r):
    m = re.search(r'class="msg"[^>]*>(.*?)</', r.text, re.S)
    return m.group(1) if m else ''

adm = cli(); entrar(adm, 'admin@pmbora.localhost', 'admin123', 'senhaforte123')
for email, nome, perfil in [('ed@teste.localhost', 'Editora Teste', 'editor'), ('pub@teste.localhost', 'Publicador Teste', 'publicador'),
                            ('apr@teste.localhost', 'Aprovadora Teste', 'editor')]:
    post(adm, '/admin/usuarios', {'acao': 'novo', 'nome': nome, 'email': email, 'perfil': perfil, 'senha': 'provisoria123'})
U = {x['email'].split('@')[0]: x['id'] for x in db.todos(PM, "SELECT id, email FROM usuarios WHERE email LIKE '%%@teste.localhost'")}
checa(len(U) == 3, f'usuários de teste: {U}')
ed, pub, apr = cli(), cli(), cli()
entrar(ed, 'ed@teste.localhost', 'provisoria123', 'senhaforte123'); entrar(pub, 'pub@teste.localhost', 'provisoria123', 'senhaforte123'); entrar(apr, 'apr@teste.localhost', 'provisoria123', 'senhaforte123')

def politica(**mods):
    """Monta o formulário da tela a partir de {modulo: (modo, [perfis], [ids], outro)}; o que não vier fica como está."""
    dados = {}
    for k, p in AP.todas(PM, {'tipo': 'executivo'}).items():
        modo, perfis, ids, outro = mods.get(k, ('aprovacao' if p['exige'] else 'direto', p['perfis'], p['usuarios'], p['outro_aprova']))
        dados[f'{k}_modo'] = modo
        dados.update({f'{k}_perfil_{x}': '1' for x in perfis}); dados.update({f'{k}_usuario_{i}': '1' for i in ids})
        if outro:
            dados[f'{k}_outro'] = '1'
    return post(adm, '/admin/aprovacao', dados)

# ---------- 1) tela e padrão (igual ao que o portal já fazia) ----------
t = adm.get('/admin/aprovacao').text
checa('Aprovação para publicar' in t and 'Base legal:' in t and 'Com regras próprias' in t and 'Diário Oficial' in t and 'Carta de Serviços' in t, 'tela com base legal e regras próprias')
checa(all(f'name="{k}_modo"' in t for k in ('conteudos', 'comunicados', 'conheca', 'fotos')) and 'name="legislativo_modo"' not in t, 'Prefeitura: módulos do executivo (sem atos da Câmara)')
checa('href="/admin/aprovacao"' in t, 'item no menu do administrador')
checa('href="/admin/aprovacao"' not in ed.get('/admin/').text and ed.get('/admin/aprovacao', follow_redirects=False).status_code in (403, 303), 'editor não muda a política')
checa(AP.politica(PM, 'conteudos')['exige'] and AP.politica(PM, 'comunicados')['exige'] and not AP.politica(PM, 'conheca')['exige'], 'padrão = comportamento anterior')
tc = cli('cmbora.localhost'); entrar(tc, 'admin@cmbora.localhost', 'admin123', 'senhaforte123')
t = tc.get('/admin/aprovacao').text
checa('name="legislativo_modo"' in t and 'name="conheca_modo"' not in t and 'name="fotos_modo"' not in t, 'Câmara: atos da Câmara, sem Conheça e Fotos')

# ---------- 2) notícias: com aprovação, editor só envia ----------
def noticia(c, titulo, acao, cid=None):
    d = {'tipo': 'Notícia', 'secao': 'Notícias', 'titulo': titulo, 'resumo': 'r', 'texto': 'Texto de teste.', 'classe': 'util', 'acao': acao}
    if cid:
        d['id'] = cid
    return post(c, '/admin/conteudos/salvar', d, de=f'/admin/conteudos/{cid or "novo"}')
f = ed.get('/admin/conteudos/novo').text
checa('value="revisao">Enviar para aprovação' in f and 'value="publicar">Publicar' not in f, 'editor (com aprovação): só "Enviar para aprovação"')
r = noticia(ed, 'Notícia fictícia A', 'publicar')  # tentativa de publicar direto vira pedido
na = db.um(PM, "SELECT * FROM conteudos WHERE titulo='Notícia fictícia A'")
checa(na and na['situacao'] == 'revisao', f'editor sem permissão: "publicar" vira pedido de aprovação ({na and na["situacao"]})')
f = pub.get('/admin/conteudos/novo').text
checa('value="publicar">Publicar' in f, 'publicador (aprova): pode publicar direto')
r = noticia(pub, 'Notícia fictícia A', 'aprovar', na['id'])
checa(db.um(PM, 'SELECT situacao FROM conteudos WHERE id=%s', (na['id'],))['situacao'] == 'publicado' and 'Aprovou e publicou' in msg(r), 'publicador aprova')
r = noticia(ed, 'Notícia fictícia A (mudada)', 'revisao', na['id'])
checa(r.status_code == 403, 'editor não altera notícia publicada quando exige aprovação')

# ---------- 3) notícias: publica direto ----------
r = politica(conteudos=('direto', [], [], False))
checa('Política de aprovação salva' in msg(r) and not AP.politica(PM, 'conteudos')['exige'], 'salvou "publica direto"')
f = ed.get('/admin/conteudos/novo').text
checa('value="publicar">Publicar' in f and 'Enviar para aprovação' not in f, 'editor (direto): botão Publicar, sem pedido de aprovação')
r = noticia(ed, 'Notícia fictícia B', 'publicar')
nb = db.um(PM, "SELECT * FROM conteudos WHERE titulo='Notícia fictícia B'")
checa(nb and nb['situacao'] == 'publicado' and 'Publicou' in msg(r), 'editor publica direto')
checa('Notícia fictícia B' in cli().get(f"/conteudo/{nb['id']}").text, 'notícia publicada direto aparece no portal')
r = noticia(ed, 'Notícia fictícia B (corrigida)', 'publicar', nb['id'])
checa(db.um(PM, 'SELECT titulo, situacao FROM conteudos WHERE id=%s', (nb['id'],)) == {'titulo': 'Notícia fictícia B (corrigida)', 'situacao': 'publicado'}, 'direto: corrige e continua publicada')

# ---------- 4) validação ----------
r = politica(comunicados=('aprovacao', [], [], False))
checa('marque pelo menos um perfil ou uma pessoa' in msg(r) and AP.politica(PM, 'comunicados')['perfis'] == ['admin', 'publicador'], 'aprovação sem ninguém para aprovar é recusada')

# ---------- 5) comunicados: aprovação por uma PESSOA, sem aprovar o próprio ----------
r = politica(comunicados=('aprovacao', [], [U['apr']], True))
checa(AP.politica(PM, 'comunicados') == {'exige': True, 'perfis': [], 'usuarios': [U['apr']], 'outro_aprova': True}, 'política por pessoa salva')
checa('Aprovadora Teste' in AP.quem_aprova(PM, 'comunicados'), 'texto "quem aprova" com o nome da pessoa')
def comunicado(c, titulo, cid=None):
    d = {'acao': 'salvar', 'tipo': 'Aviso', 'titulo': titulo, 'texto': 'Comunicado de teste.', 'classe': 'util'}
    if cid:
        d['id'] = cid
    return post(c, '/admin/comunicados', d, de='/admin/comunicados?novo=1')
def sit(c, cid, nova, **extra):
    return post(c, '/admin/comunicados', dict({'acao': 'situacao', 'id': cid, 'situacao': nova}, **extra), de=f'/admin/comunicados?id={cid}')
db.set_cfg(PM, 'comunicados_tipos', ['Aviso'])
r = comunicado(ed, 'Comunicado fictício 1')
c1 = db.um(PM, "SELECT * FROM comunicados WHERE titulo='Comunicado fictício 1'")
checa('Envie para aprovação' in msg(r), 'editor: rascunho com orientação de enviar para aprovação')
checa(sit(ed, c1['id'], 'publicado').status_code == 403, 'editor não publica comunicado')
checa(sit(pub, c1['id'], 'publicado').status_code == 403, 'publicador fora da lista não publica')
r = sit(ed, c1['id'], 'revisao')
checa('enviado para aprovação' in msg(r) and db.um(PM, 'SELECT situacao FROM comunicados WHERE id=%s', (c1['id'],))['situacao'] == 'revisao', 'editor envia para aprovação')
checa(re.search(r'Comunicados</span><span class="badge"[^>]*>1<', apr.get('/admin/').text), 'contador de comunicados esperando aprovação no menu')
f = apr.get(f"/admin/comunicados?id={c1['id']}").text
checa('Aprovar e publicar' in f and 'Devolver ao autor' in f, 'aprovadora vê Aprovar e Devolver')
r = sit(apr, c1['id'], 'devolvido')
checa('escreva o comentário' in msg(r), 'devolver exige comentário')
sit(apr, c1['id'], 'devolvido', comentario='Corrigir a data (teste).')
x = db.um(PM, 'SELECT situacao, comentario FROM comunicados WHERE id=%s', (c1['id'],))
checa(x == {'situacao': 'devolvido', 'comentario': 'Corrigir a data (teste).'}, 'devolvido com comentário')
checa('Corrigir a data (teste).' in ed.get(f"/admin/comunicados?id={c1['id']}").text, 'autor vê o comentário')
sit(ed, c1['id'], 'revisao'); r = sit(apr, c1['id'], 'publicado')
checa('aprovado e publicado' in msg(r) and db.um(PM, 'SELECT situacao FROM comunicados WHERE id=%s', (c1['id'],))['situacao'] == 'publicado', 'aprovadora aprova e publica')
db.exe(PM, "UPDATE comunicados SET publicado_em = '2026-01-01 10:00-03' WHERE id=%s", (c1['id'],))  # data fixa no passado: a suíte roda com data simulada e banco de teste em UTC
checa('Comunicado fictício 1' in cli().get('/comunicados').text, 'comunicado aprovado no portal')
r = comunicado(ed, 'Comunicado fictício 1 (alterado)', c1['id'])
checa('fica fora do ar até ser aprovado' in msg(r) and db.um(PM, 'SELECT situacao FROM comunicados WHERE id=%s', (c1['id'],))['situacao'] == 'revisao', 'alteração de quem não aprova: volta para aprovação')
checa('Comunicado fictício 1' not in cli().get('/comunicados').text, 'alterado sem aprovação sai do ar')
comunicado(apr, 'Comunicado fictício 2 (da aprovadora)')
c2 = db.um(PM, "SELECT id FROM comunicados WHERE titulo='Comunicado fictício 2 (da aprovadora)'")['id']
checa(sit(apr, c2, 'publicado').status_code == 403, 'quem escreveu não aprova o próprio')
checa(sit(ed, c2, 'arquivado').status_code == 403, 'quem não aprova não tira do ar')

# ---------- 6) Conheça: com aprovação ----------
politica(conheca=('aprovacao', ['admin', 'publicador'], [], False))
r = post(ed, '/admin/conheca', {'acao': 'perfil', 'titulo': 'Lugar fictício', 'categoria': 'Lugares', 'classe': 'util', 'publicado': '1'}, de='/admin/conheca?novo=1')
p = db.um(PM, "SELECT * FROM perfis WHERE titulo='Lugar fictício'")
checa(p and not p['publicado'] and p['aguarda_aprovacao'] and 'Enviado para aprovação' in msg(r), 'Conheça: editor pede publicação, não publica')
checa(cli().get(f"/conheca/{p['slug']}").status_code == 404, 'perfil à espera não aparece no portal')
checa(re.search(r'Conheça[^<]*</span><span class="badge"', pub.get('/admin/').text), 'contador do Conheça no menu')
post(pub, '/admin/conheca', {'acao': 'aprovar', 'id': p['id']}, de=f"/admin/conheca?id={p['id']}")
checa(db.um(PM, 'SELECT publicado, aguarda_aprovacao FROM perfis WHERE id=%s', (p['id'],)) == {'publicado': True, 'aguarda_aprovacao': False}, 'publicador aprova o perfil')
checa(cli().get(f"/conheca/{p['slug']}").status_code == 200, 'perfil aprovado no portal')
r = post(ed, '/admin/conheca', {'acao': 'video', 'id': p['id'], 'youtube': 'https://www.youtube.com/watch?v=aaaaaaaaaaa', 'titulo': 'Vídeo fictício'}, de=f"/admin/conheca?id={p['id']}")
checa('fora do ar até a aprovação' in msg(r) and 'aaaaaaaaaaa' not in cli().get(f"/conheca/{p['slug']}").text, 'vídeo de quem não aprova fica fora do ar')
checa(db.um(PM, 'SELECT aguarda_aprovacao FROM perfis WHERE id=%s', (p['id'],))['aguarda_aprovacao'], 'perfil volta à fila de aprovação')
r = post(pub, '/admin/conheca', {'acao': 'devolver', 'id': p['id']}, de=f"/admin/conheca?id={p['id']}")
checa('escreva o comentário' in msg(r), 'Conheça: devolver exige comentário')
post(pub, '/admin/conheca', {'acao': 'aprovar', 'id': p['id']}, de=f"/admin/conheca?id={p['id']}")
checa('aaaaaaaaaaa' in cli().get(f"/conheca/{p['slug']}").text, 'vídeo aprovado aparece')
checa(post(ed, '/admin/conheca', {'acao': 'aprovar', 'id': p['id']}, de=f"/admin/conheca?id={p['id']}").status_code == 403, 'editor não aprova perfil')

# ---------- 7) Fotos: com aprovação ----------
politica(fotos=('aprovacao', ['admin'], [], False))
post(adm, '/admin/identidade/fotos', {'acao': 'album', 'titulo': 'Álbum fictício', 'publicado': '1'}, de='/admin/identidade?aba=fotos&novo=1')
al = db.um(PM, "SELECT * FROM albuns WHERE titulo='Álbum fictício'")
checa(al['publicado'] and not al['aguarda_aprovacao'], 'administrador (aprova) publica o álbum direto')
r = post(ed, '/admin/identidade/fotos', {'acao': 'foto', 'album_id': al['id'], 'licenca': 'CC BY 4.0', 'titulo': 'Foto fictícia'}, de=f"/admin/identidade?aba=fotos&album={al['id']}",
         files={'arquivo': ('f.png', png(), 'image/png')})
fo = db.um(PM, 'SELECT * FROM album_fotos WHERE album_id=%s', (al['id'],))
checa(fo and fo['aguarda_aprovacao'] and 'fora do ar até a aprovação' in msg(r), f'foto de quem não aprova fica à espera ({msg(r)[:120]})')
checa(cli().get(f"/fotos/{al['id']}").status_code == 404, 'álbum sem foto aprovada não aparece')
checa(post(pub, '/admin/identidade/fotos', {'acao': 'aprovar', 'album_id': al['id']}, de=f"/admin/identidade?aba=fotos&album={al['id']}").status_code == 403, 'publicador fora da lista (só admin) não aprova fotos')
post(adm, '/admin/identidade/fotos', {'acao': 'aprovar', 'album_id': al['id']}, de=f"/admin/identidade?aba=fotos&album={al['id']}")
checa(cli().get(f"/fotos/{al['id']}").status_code == 200, 'foto aprovada: álbum no portal')
r = post(ed, '/admin/identidade/fotos', {'acao': 'album', 'album_id': al['id'], 'titulo': 'Álbum fictício (alterado)', 'publicado': '1'}, de=f"/admin/identidade?aba=fotos&album={al['id']}")
checa('saiu do ar até ser aprovado' in msg(r) and not db.um(PM, 'SELECT publicado FROM albuns WHERE id=%s', (al['id'],))['publicado'], 'alteração do álbum por quem não aprova: sai do ar até aprovar')

# ---------- 8) Câmara: atos no portal (regra) ----------
u_ed, u_pub = {'id': 0, 'nome': 'X', 'perfil': 'editor'}, {'id': 0, 'nome': 'Y', 'perfil': 'publicador'}
checa(not AP.pode_publicar(CM, 'legislativo', u_ed) and AP.pode_publicar(CM, 'legislativo', u_pub), 'Câmara padrão: só publicador/admin publica pauta, votação e ata')
db.set_cfg(CM, 'aprovacao', {'legislativo': {'exige': False}})
checa(AP.pode_publicar(CM, 'legislativo', u_ed), 'Câmara direto: editor publica')
checa(not AP.pode_publicar(CM, 'legislativo', {'id': 0, 'nome': 'Z', 'perfil': 'remetente'}), 'perfil sem edição nunca publica')
db.set_cfg(CM, 'aprovacao', {})

# ---------- 9) regras próprias intactas ----------
checa(not any(k in AP.NOMES for k in ('diario', 'carta')), 'Diário e Carta fora da política (regras próprias)')
checa('Aprovação para publicar' in db.um(PM, "SELECT acao FROM auditoria WHERE acao LIKE 'Aprovação para publicar%%' ORDER BY id DESC LIMIT 1")['acao'], 'mudança da política vai para a auditoria')

print('ERROS:', len(erros))
for e in erros:
    print(' -', e)
sys.exit(1 if erros else 0)
