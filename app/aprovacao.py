"""Política de aprovação para publicar (15/11/2026): o órgão escolhe, módulo a módulo, se publicar exige aprovação e quem aprova.

Guardada na configuração do órgão (`config.aprovacao`), sem código por órgão. Para cada módulo:
- exige: False = quem edita publica direto; True = só os aprovadores publicam (os demais enviam para aprovação);
- perfis: perfis que aprovam; usuarios: pessoas que aprovam (ids), além dos perfis;
- outro_aprova: quem escreveu não aprova nem publica direto o próprio conteúdo (segregação de funções).
O padrão repete o que o portal já fazia antes desta opção (nada muda até o administrador mudar).

Ficam FORA (regras próprias, não mudam aqui): Diário Oficial (envio, revisão, fechamento e assinatura), Carta de Serviços
(validação pelo responsável da secretaria), exceção do período eleitoral (Procuradoria) e moderação das manifestações do
cidadão (opiniões, tribuna livre e comentários). As travas do período eleitoral valem nos dois modos."""
from . import db
from .catalogo import PODE, PERFIS

# chave, nome no painel, onde vale (None = os dois tipos de órgão), o que entra
MODULOS = [
    ('conteudos', 'Notícias e páginas', None, 'Notícias, páginas, banners e documentos.'),
    ('comunicados', 'Comunicados', None, 'Avisos, convocações, convites, notas oficiais e editais de chamamento.'),
    ('conheca', 'Conheça a cidade', 'executivo', 'Perfis de lugares, eventos e economia, com as fotos de cada perfil.'),
    ('fotos', 'Fotos e álbuns', 'executivo', 'Álbuns da galeria /fotos e as fotos de cada álbum.'),
    ('legislativo', 'Atos da Câmara no portal', 'legislativo', 'Pauta, presença, votação e ata das sessões; pautas e pareceres das comissões; julgamento das contas.'),
]
NOMES = {k: n for k, n, _, _ in MODULOS}
PERFIS_APROVADORES = ['admin', 'publicador', 'editor', 'procuradoria']  # perfis que podem ser marcados como aprovadores
_PADRAO_EXIGE = {'conteudos': True, 'comunicados': True, 'conheca': False, 'fotos': False, 'legislativo': True}
REGRAS_PROPRIAS = [
    ('Diário Oficial', 'envio pelos órgãos cadastrados, revisão, fechamento da edição e assinatura ICP-Brasil (Diário Oficial → Configurações).'),
    ('Carta de Serviços', 'cada ficha é autorizada pelo responsável da secretaria e publicada pelo DTIC (Lei 13.460/2017).'),
    ('Período eleitoral', 'conteúdo vedado não publica no defeso; exceção só com aprovação da Procuradoria (Lei 9.504/1997, art. 73).'),
    ('Manifestações do cidadão', 'opiniões, tribuna livre e comentários passam pela moderação (dado pessoal e ofensa não publicam).'),
]

def modulos(orgao):
    tipo = (orgao or {}).get('tipo')
    return [(k, n, d) for k, n, t, d in MODULOS if t in (None, tipo)]

def padrao(mod):
    return {'exige': _PADRAO_EXIGE.get(mod, True), 'perfis': ['admin', 'publicador'], 'usuarios': [], 'outro_aprova': False}

def politica(banco, mod):
    p = padrao(mod)
    salvo = ((db.cfg(banco, 'aprovacao', {}) or {}).get(mod)) or {}
    if isinstance(salvo, dict):
        p.update({k: salvo[k] for k in p if k in salvo})
    p['perfis'] = [x for x in (p['perfis'] or []) if x in PERFIS_APROVADORES]
    p['usuarios'] = [int(x) for x in (p['usuarios'] or []) if str(x).isdigit()]
    p['exige'], p['outro_aprova'] = bool(p['exige']), bool(p['outro_aprova'])
    return p

def todas(banco, orgao):
    return {k: politica(banco, k) for k, _, _ in modulos(orgao)}

def e_aprovador(banco, mod, u, pol=None):
    """Está na lista de quem aprova (perfil marcado ou pessoa escolhida)."""
    pol = pol or politica(banco, mod)
    return bool(u) and (u.get('perfil') in pol['perfis'] or u.get('id') in pol['usuarios'])

def pode_publicar(banco, mod, u, autor=None):
    """Pode publicar (ou aprovar) neste módulo. `autor` = nome de quem escreveu o item, quando houver."""
    if not u or u.get('perfil') not in PODE['editar'] | set(PERFIS_APROVADORES):
        return False
    pol = politica(banco, mod)
    if not pol['exige']:
        return u.get('perfil') in PODE['editar'] or e_aprovador(banco, mod, u, pol)
    if not e_aprovador(banco, mod, u, pol):
        return False
    return not (pol['outro_aprova'] and autor and autor == u.get('nome'))

def quem_aprova(banco, mod):
    """Texto curto para o painel: quem publica neste módulo."""
    pol = politica(banco, mod)
    if not pol['exige']:
        return 'publica direto quem edita'
    partes = [PERFIS[p] for p in pol['perfis'] if p in PERFIS]
    if pol['usuarios']:
        nomes = [r['nome'] for r in db.todos(banco, 'SELECT nome FROM usuarios WHERE id = ANY(%s) ORDER BY nome', (pol['usuarios'],))]
        partes += nomes
    return 'aprovação de ' + (', '.join(partes) or 'ninguém definido')

def validar(form, orgao, usuarios_validos):
    """Formulário do painel -> dict de políticas (ou ValueError com a mensagem)."""
    out = {}
    for k, nome, _ in modulos(orgao):
        exige = form.get(f'{k}_modo') == 'aprovacao'
        perfis = [p for p in PERFIS_APROVADORES if form.get(f'{k}_perfil_{p}') == '1']
        usuarios = sorted(i for i in usuarios_validos if form.get(f'{k}_usuario_{i}') == '1')
        if exige and not perfis and not usuarios:
            raise ValueError(f'{nome}: com aprovação, marque pelo menos um perfil ou uma pessoa que aprova.')
        out[k] = {'exige': exige, 'perfis': perfis, 'usuarios': usuarios, 'outro_aprova': exige and form.get(f'{k}_outro') == '1'}
    return out

def pendentes(banco, orgao):
    """Contadores do menu (itens esperando aprovação) — só dos módulos que existem no órgão."""
    ks = {k for k, _, _ in modulos(orgao)}
    r = db.um(banco, """SELECT (SELECT count(*) FROM comunicados WHERE situacao='revisao') comunicados,
                               (SELECT count(*) FROM perfis WHERE aguarda_aprovacao) conheca,
                               (SELECT count(*) FROM albuns WHERE aguarda_aprovacao) fotos""")
    return {k: (r[k] if k in ks else 0) for k in ('comunicados', 'conheca', 'fotos')}

def salvar_item(banco, mod, u, autor, era_publicado, pediu_publicar):
    """Itens com "Publicado" marcado (Conheça e álbuns). Devolve (publicado, aguarda_aprovacao ou None = não muda, aviso).
    Quem não pode publicar: o item sai do ar (se estava) e fica à espera de quem aprova — nada entra no ar sem aprovação."""
    if pode_publicar(banco, mod, u, autor):
        return pediu_publicar, (False if pediu_publicar else None), ''
    if pediu_publicar or era_publicado:
        return False, True, (' A alteração precisa de aprovação: o item saiu do ar até ser aprovado.' if era_publicado else ' Enviado para aprovação.')
    return False, None, ''

def item_novo_pendente(banco, mod, u, autor):
    """Foto ou vídeo incluído/alterado por quem não pode publicar: fica fora do ar até a aprovação."""
    return not pode_publicar(banco, mod, u, autor)
