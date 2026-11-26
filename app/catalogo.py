"""Catálogo de módulos, blocos da página inicial e regras do período eleitoral."""

# [chave, nome, descrição, oferta (obr|plano|opc), serve (ambos|executivo|legislativo), depende]
MODULOS = [
    ('transp', 'Portal da Transparência', 'Receitas, despesas, pessoal, contratos, relatórios fiscais', 'obr', 'ambos', None),
    ('sic', 'e-SIC', 'Pedidos de informação com prazos e recursos', 'obr', 'ambos', None),
    ('ouv', 'Ouvidoria', 'Manifestações com protocolo', 'obr', 'ambos', None),
    ('dados', 'Dados abertos', 'CSV, JSON e API', 'obr', 'ambos', None),
    ('licit', 'Licitações e contratos (PNCP)', 'Editais, atas, contratos', 'obr', 'ambos', None),
    ('carta', 'Carta de Serviços', 'Fichas dos serviços com validação por secretaria (Lei 13.460/2017)', 'obr', 'ambos', None),
    ('ver', 'Vereadores e Mesa Diretora', 'Perfis, Mesas, galeria de legislaturas', 'obr', 'legislativo', None),
    ('sess', 'Sessões e votações', 'Pauta, ata, presença, votação nominal', 'obr', 'legislativo', None),
    ('prop', 'Proposições', 'Tramitação com autor e relator', 'obr', 'legislativo', None),
    ('transm', 'Transmissão das sessões', 'Ao vivo e gravações (PNTP 20.9)', 'obr', 'legislativo', None),
    ('noticias', 'Notícias e avisos', 'Com fluxo de aprovação', 'plano', 'ambos', None),
    ('blocos', 'Página inicial em blocos', 'Personalização nível 2', 'plano', 'ambos', None),
    ('eleicao', 'Período eleitoral', 'Suspensão automática no defeso', 'plano', 'ambos', None),
    ('diario', 'Diário Oficial eletrônico', 'Edições com assinatura ICP-Brasil (lei municipal ou resolução da Câmara de instituição)', 'opc', 'ambos', None),  # Câmara: Diário próprio (23/11/2026)
    ('bi', 'Painel de indicadores', 'Saúde, educação, social e gestão (indicadores do município)', 'opc', 'ambos', None),
    ('audiencias', 'Transmissão de audiências', 'Audiências públicas ao vivo e gravações', 'opc', 'executivo', None),
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
    'servicos': ('Serviços mais procurados', ['principal'], 'carta', False, 'ambos'),
    'noticias': ('Notícias', ['principal', 'lateral'], 'noticias', False, 'ambos'),
    'diario': ('Atos oficiais e oportunidades (Diário Oficial)', ['principal', 'lateral'], 'diario', False, 'ambos'),
    'ver': ('Vereadores e Mesa Diretora', ['principal'], 'ver', False, 'legislativo'),
    'contas': ('Prestação de contas', ['principal', 'lateral'], 'transp', False, 'legislativo'),
    'emendas': ('Emendas impositivas', ['principal', 'lateral'], 'emend', False, 'legislativo'),
    'sessoes': ('Últimas sessões', ['principal', 'lateral'], 'sess', False, 'legislativo'),
    'projetos': ('Projetos em tramitação', ['principal', 'lateral'], 'prop', False, 'legislativo'),
    'numeros': ('Acompanhe a gestão (indicadores em números; com o módulo "bi", os destaques do painel)', ['principal'], 'transp', False, 'executivo'),
    'comunicados': ('Comunicados e serviços mais acessados', ['principal'], None, False, 'ambos'),
    'protocolo': ('Acompanhe seu pedido (protocolo)', ['principal', 'lateral'], None, False, 'ambos'),
    'publicacoes': ('Publicações oficiais', ['principal'], 'transp', False, 'executivo'),
    'transmissoes': ('Transmissões (3 últimas gravações; some sem vídeos)', ['principal'], None, False, 'ambos'),
    'conheca': ('Conheça a cidade (mosaico de fotos)', ['principal'], None, False, 'executivo'),
    'sede': ('Sede e atendimento', ['principal', 'lateral'], None, False, 'ambos'),
    'redes': ('Nas redes (últimas publicações; some sem credencial no console e no período eleitoral)', ['principal'], None, False, 'ambos'),
    'fotos': ('Galeria de fotos (últimos álbuns publicados; some sem álbum)', ['principal'], None, False, 'ambos'),
    'selos': ('Selos e reconhecimentos (ao lado de "Atos oficiais" quando vêm em seguida; some sem selo e no período eleitoral)', ['principal'], None, False, 'ambos'),
    'videos': ('Vídeos e câmeras ao vivo (2 colunas: vídeos do YouTube e câmeras; os vídeos saem no período eleitoral; some sem nenhum dos dois)', ['principal'], None, False, 'ambos'),
    'tempo': ('Previsão do tempo (agora e próximos dias; some se a fonte estiver fora do ar)', ['destaque', 'principal'], None, False, 'ambos'),
    'rodape': ('Rodapé com links obrigatórios', ['rodape'], None, True, 'ambos'),
}
# Blocos que entram OCULTOS quando são acrescentados (o órgão liga e posiciona em Página inicial)
COMECA_OCULTO = {'fotos'}
# Bloco novo entra logo ANTES deste bloco (se o órgão o tiver na mesma região); sem ele, vai para o fim
ANTES_DE = {'tempo': 'comunicados'}
# Bloco novo entra logo DEPOIS deste bloco, por tipo de órgão (tem prioridade sobre ANTES_DE)
DEPOIS_DE = {'executivo': {'selos': 'diario'}, 'legislativo': {'selos': 'emendas'}}
# Pares de blocos que dividem a linha quando vêm um logo depois do outro (largura de cada um)
PARES = {('diario', 'selos'): ('l65', 'l35')}
# Largura do bloco na página inicial: blocos "meio" lado a lado; contas × emendas na proporção 55/45
LARGURA = {'contas': 'l55', 'emendas': 'l45', 'sessoes': 'meio', 'projetos': 'meio'}
REGIOES = [('topo', 'Cabeçalho'), ('avisos', 'Faixa de avisos'), ('destaque', 'Destaque'), ('principal', 'Área principal'), ('lateral', 'Coluna lateral'), ('rodape', 'Rodapé')]
LAYOUT_PADRAO = {  # Fase 9: + "Nas redes" depois das notícias
    'executivo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('tempo', 'principal'), ('comunicados', 'principal'), ('protocolo', 'principal'), ('numeros', 'principal'),
                  ('publicacoes', 'principal'), ('diario', 'principal'), ('selos', 'principal'), ('transmissoes', 'principal'), ('conheca', 'principal'), ('noticias', 'principal'), ('redes', 'principal'), ('sede', 'principal'), ('fotos', 'principal'),
                  ('videos', 'principal'), ('rodape', 'rodape')],
    'legislativo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('ver', 'principal'), ('tempo', 'principal'), ('comunicados', 'principal'), ('contas', 'principal'), ('emendas', 'principal'),
                    ('selos', 'principal'), ('sessoes', 'principal'), ('projetos', 'principal'), ('transmissoes', 'principal'), ('videos', 'principal'), ('noticias', 'principal'), ('redes', 'principal'), ('fotos', 'principal'), ('rodape', 'rodape')],
}
LAYOUT_PADRAO_V3 = {  # padrão da Fase 8 (quem estiver exatamente nele recebe o padrão da Fase 9)
    'executivo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('comunicados', 'principal'), ('protocolo', 'principal'), ('numeros', 'principal'),
                  ('publicacoes', 'principal'), ('diario', 'principal'), ('transmissoes', 'principal'), ('conheca', 'principal'), ('noticias', 'principal'), ('sede', 'principal'), ('rodape', 'rodape')],
    'legislativo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('ver', 'principal'), ('comunicados', 'principal'), ('contas', 'principal'), ('emendas', 'principal'),
                    ('sessoes', 'principal'), ('projetos', 'principal'), ('transmissoes', 'principal'), ('noticias', 'principal'), ('rodape', 'rodape')],
}
# Padrão da Fase 3/7: quem ainda estiver exatamente nele recebe o novo padrão inteiro no "provision atualizar"
LAYOUT_PADRAO_V2 = {
    'executivo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('servicos', 'principal'), ('numeros', 'principal'), ('diario', 'principal'), ('conheca', 'principal'), ('sede', 'principal'), ('noticias', 'principal'), ('rodape', 'rodape')],
    'legislativo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('ver', 'principal'), ('contas', 'principal'), ('emendas', 'principal'), ('sessoes', 'principal'), ('projetos', 'principal'), ('noticias', 'principal'), ('rodape', 'rodape')],
}
# Layout padrão da Fase 2: quem ainda está exatamente nele recebe o novo padrão no "provision atualizar"
LAYOUT_PADRAO_V1 = {
    'executivo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('servicos', 'principal'), ('noticias', 'principal'), ('diario', 'lateral'), ('rodape', 'rodape')],
    'legislativo': [('acess', 'topo'), ('defeso', 'avisos'), ('hero', 'destaque'), ('atalhos', 'destaque'), ('ver', 'principal'), ('contas', 'principal'), ('noticias', 'principal'), ('emendas', 'lateral'), ('sessoes', 'lateral'), ('rodape', 'rodape')],
}
# Fotos de tema dos cartões de serviço (campo "imagem" do conteúdo)
TEMAS = {'saude': 'Saúde', 'educacao': 'Educação', 'tributos': 'Tributos', 'empresas': 'Empresas', 'cidade': 'Cidade', 'social': 'Assistência', 'atendimento': 'Atendimento'}

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
SITUACOES = {'rascunho': 'Rascunho', 'revisao': 'Em aprovação', 'devolvido': 'Devolvido', 'agendado': 'Agendado', 'publicado': 'Publicado', 'arquivado': 'Arquivado'}
PERFIS = {'admin': 'Administrador do órgão', 'editor': 'Editor de conteúdo', 'publicador': 'Publicador (DTIC)', 'procuradoria': 'Procuradoria / Controle', 'remetente': 'Remetente do Diário',
          'redator': 'Redator da Carta (secretaria)', 'validador': 'Responsável/validador da Carta (secretaria)',
          'ouvidoria': 'Ouvidoria / SIC (vê a identidade do solicitante)', 'autoridade_recurso': 'Autoridade de recurso (e-SIC)'}
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
    # e-SIC e Ouvidoria (23/11/2026): só a Ouvidoria/SIC e o administrador veem quem pediu; a autoridade de recurso decide recursos
    'atendimento': {'admin', 'publicador', 'editor', 'ouvidoria', 'autoridade_recurso'},
    'atendimento_responder': {'admin', 'publicador', 'editor', 'ouvidoria'},
    'atendimento_identidade': {'admin', 'ouvidoria'},
    'atendimento_config': {'admin', 'ouvidoria'},
    'recurso_decidir': {'admin', 'autoridade_recurso'},
    # Carta de Serviços (Fase 10): redator e validador só na própria secretaria; DTIC (publicador) organiza e publica
    'carta_ver': {'admin', 'publicador', 'editor', 'redator', 'validador'},
    'carta_redigir': {'admin', 'publicador', 'editor', 'redator', 'validador'},
    'carta_validar': {'validador', 'admin'},
    'carta_publicar': {'publicador', 'admin'},
    # Autoavaliação PNTP (18/11/2026): o controle interno (perfil Procuradoria / Controle) marca; DTIC e administrador consultam
    'pntp_ver': {'admin', 'publicador', 'procuradoria'},
    'pntp_marcar': {'admin', 'procuradoria'},
}

BASE_LEGAL = {
    'transparencia': 'LAI (Lei 12.527/2011), art. 8º; LRF (LC 101/2000), arts. 48 e 48-A; PNTP 2026.',
    'vereadores': 'PNTP 2026, critérios 20.1 e 20.11; LAI, art. 8º.',
    'sessoes': 'PNTP 2026, critérios 20.4 (pauta), 20.6 (atas com presença), 20.7 (votações nominais) e 20.9 (transmissão); Regimento Interno.',
    'proposicoes': 'PNTP 2026, critérios 20.2 (leis e atos produzidos) e 20.3 (projetos com tramitação, autor, relator e documentos).',
    'emendas': 'Lei Orgânica do Município, art. 127; STF, ADPF 854; PNTP 2026, critérios 17.2 e 17.3.',
    'comissoes': 'PNTP 2026, critério 20.5 (pauta e pareceres das Comissões); Regimento Interno.',
    'contas': 'Constituição, art. 31, §§ 1º e 2º (parecer prévio do Tribunal de Contas, que só deixa de prevalecer por 2/3 dos membros); PNTP 2026, critério 20.8.',
    'transmissoes': 'PNTP 2026, critério 20.9; Lei 13.146/2015, arts. 63 e 67 (legendas e Libras).',
    'participacao': 'Lei 13.460/2017; Regimento Interno (Tribuna Livre); LGPD, art. 7º (dados pessoais só para a Secretaria).',
    'acesso': 'LAI, arts. 9º a 11, 15 e 30; Lei 13.460/2017; LGPD, art. 41.',
    'esic_estatisticas': 'LAI (Lei 12.527/2011), art. 30, III (relatório estatístico anual de pedidos recebidos, atendidos e indeferidos, com informações genéricas sobre os solicitantes); PNTP 2026, critério 12.7.',
    'esic_classificadas': 'LAI (Lei 12.527/2011), arts. 24, 30, I e II, e 31 (rol das informações classificadas em cada grau de sigilo e das desclassificadas nos últimos 12 meses); PNTP 2026, critérios 12.8 e 12.9.',
    'ouvidoria_relatorio': 'Lei 13.460/2017, arts. 14, II, 15 e 23 (relatório de gestão da ouvidoria e avaliação dos serviços pelos usuários); PNTP 2026, critério 15.6.',
    'diario': 'Lei municipal de instituição do Diário Oficial eletrônico; MP 2.200-2/2001 (ICP-Brasil); Lei 14.063/2020.',
    'noticias': 'Constituição, art. 37, § 1º (vedada promoção pessoal); Lei 9.504/1997, art. 73, VI, b.',
    'acessibilidade': 'Lei 13.146/2015 (Estatuto da Pessoa com Deficiência), art. 63; Lei 10.098/2000, art. 17; eMAG 3.1 (Portaria SLTI/MP nº 3/2007); WCAG 2.1, nível AA.',
    'carta': 'Lei 13.460/2017 (Código de Defesa do Usuário do Serviço Público), arts. 7º, 23 e 24; LAI (Lei 12.527/2011), art. 8º.',
    'comunicados': 'Constituição, art. 37, caput e § 1º (publicidade de caráter informativo); Lei 9.504/1997, art. 73, VI, b (período eleitoral).',
    'aprovacao': 'Constituição, art. 37, caput (legalidade, impessoalidade, publicidade e eficiência) e § 1º (publicidade de caráter informativo); LAI (Lei 12.527/2011), art. 8º; Lei 9.504/1997, art. 73, VI, b (período eleitoral).',
    'conheca': 'Constituição, art. 37, § 1º; Código Civil, art. 20, e LGPD (Lei 13.709/2018), art. 7º (uso de imagem só com autorização); Lei 9.610/1998, art. 24 (crédito do autor).',
}
