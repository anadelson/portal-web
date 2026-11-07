"""Catálogo de módulos, blocos da página inicial e regras do período eleitoral."""

# [chave, nome, descrição, oferta (obr|plano|opc), serve (ambos|executivo|legislativo), depende]
MODULOS = [
    ('transp', 'Portal da Transparência', 'Receitas, despesas, pessoal, contratos, relatórios fiscais', 'obr', 'ambos', None),
    ('sic', 'e-SIC', 'Pedidos de informação com prazos e recursos', 'obr', 'ambos', None),
    ('ouv', 'Ouvidoria', 'Manifestações com protocolo', 'obr', 'ambos', None),
    ('dados', 'Dados abertos', 'CSV, JSON e API', 'obr', 'ambos', None),
    ('licit', 'Licitações e contratos (PNCP)', 'Editais, atas, contratos', 'obr', 'ambos', None),
    ('carta', 'Carta de Serviços', 'Serviços, prazos e canais', 'obr', 'executivo', None),
    ('ver', 'Vereadores e Mesa Diretora', 'Perfis, Mesas, galeria de legislaturas', 'obr', 'legislativo', None),
    ('sess', 'Sessões e votações', 'Pauta, ata, presença, votação nominal', 'obr', 'legislativo', None),
    ('prop', 'Proposições', 'Tramitação com autor e relator', 'obr', 'legislativo', None),
    ('transm', 'Transmissão das sessões', 'Ao vivo e gravações (PNTP 20.9)', 'obr', 'legislativo', None),
    ('noticias', 'Notícias e avisos', 'Com fluxo de aprovação', 'plano', 'ambos', None),
    ('blocos', 'Página inicial em blocos', 'Personalização nível 2', 'plano', 'ambos', None),
    ('eleicao', 'Período eleitoral', 'Suspensão automática no defeso', 'plano', 'ambos', None),
    ('diario', 'Diário Oficial eletrônico', 'Edições com assinatura ICP-Brasil (Lei 910/2026)', 'opc', 'executivo', None),
    ('bi', 'Painel de indicadores', 'Saúde, educação, social e gestão', 'opc', 'executivo', None),
    ('integpref', 'Integração com a Prefeitura', 'Lê a execução orçamentária do Executivo', 'opc', 'legislativo', None),
    ('emend', 'Emendas impositivas', 'Emendas por vereador e execução', 'opc', 'legislativo', 'integpref'),
    ('tema3', 'Tema próprio (nível 3)', 'Layout totalmente redesenhado', 'opc', 'ambos', None),
]
MOD = {m[0]: m for m in MODULOS}

def serve(chave, tipo):
    s = MOD[chave][4]
    return s == 'ambos' or s == tipo

# Blocos da página inicial: chave -> (nome, regiões permitidas, módulo exigido, travado, tipo)
BLOCOS = {
    'acess': ('Barra de acessibilidade', ['topo'], None, True, 'ambos'),
    'defeso': ('Aviso do período eleitoral', ['avisos'], 'eleicao', True, 'ambos'),
    'hero': ('Destaque com busca', ['destaque'], None, False, 'ambos'),
    'atalhos': ('Acesso direto', ['destaque', 'principal'], None, False, 'ambos'),
    'servicos': ('Serviços mais procurados', ['principal'], 'carta', False, 'executivo'),
    'noticias': ('Notícias', ['principal', 'lateral'], 'noticias', False, 'ambos'),
    'diario': ('Últimas edições do Diário', ['principal', 'lateral'], 'diario', False, 'executivo'),
    'ver': ('Vereadores e Mesa Diretora', ['principal'], 'ver', False, 'legislativo'),
    'contas': ('Prestação de contas', ['principal', 'lateral'], 'transp', False, 'legislativo'),
    'emendas': ('Emendas impositivas', ['principal', 'lateral'], 'emend', False, 'legislativo'),
    'sessoes': ('Últimas sessões', ['principal', 'lateral'], 'sess', False, 'legislativo'),
    'rodape': ('Rodapé com links obrigatórios', ['rodape'], None, True, 'ambos'),
}
REGIOES = [('topo', 'Cabeçalho'), ('avisos', 'Faixa de avisos'), ('destaque', 'Destaque'), ('principal', 'Área principal'), ('lateral', 'Coluna lateral'), ('rodape', 'Rodapé')]
LAYOUT_PADRAO = {
    'executivo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('servicos', 'principal'), ('noticias', 'principal'), ('diario', 'lateral'), ('rodape', 'rodape')],
    'legislativo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('ver', 'principal'), ('contas', 'principal'), ('noticias', 'principal'), ('emendas', 'lateral'), ('sessoes', 'lateral'), ('rodape', 'rodape')],
}

# Classificação eleitoral (Lei 9.504/1997, art. 73, VI, b; CF art. 37 §1º)
CLASSES = {
    'pub': ('Publicidade institucional', 'Suspenso no defeso'),
    'agente': ('Menciona agente político', 'Suspenso no defeso'),
    'slogan': ('Marca ou slogan de gestão', 'Suspenso no defeso (usa só o brasão)'),
    'util': ('Utilidade pública', 'Mantido, sem nomes, fotos de agentes ou slogans'),
    'serv': ('Serviço ao cidadão', 'Mantido'),
    'transp': ('Transparência obrigatória', 'Mantido'),
    'ato': ('Ato oficial', 'Mantido'),
}
VEDADAS = ('pub', 'agente', 'slogan')
SITUACOES = {'rascunho': 'Rascunho', 'revisao': 'Em revisão', 'devolvido': 'Devolvido', 'agendado': 'Agendado', 'publicado': 'Publicado', 'arquivado': 'Arquivado'}
PERFIS = {'admin': 'Administrador do órgão', 'editor': 'Editor de conteúdo', 'publicador': 'Publicador', 'procuradoria': 'Procuradoria / Controle', 'remetente': 'Remetente do Diário'}
# Permissões por perfil
PODE = {
    'editar': {'admin', 'editor', 'publicador'},
    'publicar': {'admin', 'publicador'},
    'config': {'admin'},
    'usuarios': {'admin'},
    'eleicao_aprovar': {'procuradoria'},
    'diario_enviar': {'admin', 'editor', 'remetente', 'publicador'},
    'diario_revisar': {'admin', 'publicador'},
    'diario_fechar': {'admin'},
    'atendimento': {'admin', 'publicador', 'editor'},
}

BASE_LEGAL = {
    'transparencia': 'LAI (Lei 12.527/2011), art. 8º; LRF (LC 101/2000), arts. 48 e 48-A; PNTP 2026.',
    'vereadores': 'PNTP 2026, critérios 20.1 e 20.11; LAI, art. 8º.',
    'sessoes': 'PNTP 2026, critérios 20.4, 20.6, 20.7 e 20.9; Regimento Interno.',
    'proposicoes': 'PNTP 2026, critérios 20.2 e 20.3.',
    'emendas': 'Lei Orgânica do Município, art. 127; STF, ADPF 854; PNTP 2026, critérios 17.2 e 17.3.',
    'acesso': 'LAI, arts. 9º a 11, 15 e 30; Lei 13.460/2017; LGPD, art. 41.',
    'diario': 'Lei Municipal 910/2026 e decreto de 25/03/2026; MP 2.200-2/2001 (ICP-Brasil); Lei 14.063/2020.',
    'noticias': 'Constituição, art. 37, § 1º (vedada promoção pessoal); Lei 9.504/1997, art. 73, VI, b.',
}
