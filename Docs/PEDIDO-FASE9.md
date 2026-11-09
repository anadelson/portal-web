# Fase 9 — Painel administrativo: blocos com mapa, avaliação, indicadores e consultas, identidade/tema, conteúdo, login

Pedido do gestor em 09/11/2026 após uso do painel da Prefeitura (pmbora.conectatech.tech/admin). Vale para todos os órgãos (o mesmo código atende a Câmara).
REGRAS: as mesmas das fases anteriores (branch fase-9, commits pequenos, tag ao final; migrações idempotentes; aprovação antes de alterar a VPS; testes só em banco de TESTE; nunca mostrar senhas/.env/credenciais; acessibilidade AA; LGPD; nada inventado; PROGRESSO.md).
Antes de implementar: capturas "antes" de cada tela citada (Docs/avaliacao-fase9/antes/), um esboço das telas novas e PARADA para aprovação.

1) Página inicial (blocos): mapa do layout
1.1 Na tela de blocos, à direita da lista, um cartão "Onde fica no portal" com o desenho esquemático da página inicial (cabeçalho, faixas e cada bloco como retângulo na posição e largura reais, em ordem).
1.2 Ao passar o mouse ou focar um bloco na lista, o retângulo correspondente fica destacado (e vice-versa: clicar no retângulo seleciona o bloco na lista). Blocos desligados aparecem tracejados.
1.3 O cartão fica fixo (position: sticky) e sempre visível enquanto a lista rola; no celular vira um botão "Ver mapa do layout".
1.4 Mudou a ordem ou ligou/desligou um bloco: o mapa atualiza na hora, antes de salvar.

2) Avaliação do portal ("Avalie esta página")
2.1 Hoje não foi possível avaliar: diagnostique e corrija (me mostre a causa).
2.2 Controle de repetição por cookie (como pedido): cookie próprio, primário, sem dado pessoal, que registra que aquela página já foi avaliada; nova avaliação da mesma página pelo mesmo navegador só após 30 dias (prazo configurável no painel). Reforço: limite por IP com hash (sem guardar o IP puro) de no máximo 5 avaliações por hora, para conter robôs. Registre isso na página de privacidade/cookies.
2.3 Painel: resultado por página e por mês, comentários com moderação (sem dados pessoais publicados).

3) Indicadores e consultas de dados (vale para TODAS as integrações do portal)
3.1 Tela de indicadores organizada em ABAS por área (Dinheiro público, Contratações, Saúde, Educação, Assistência social, Município e gestão) e, dentro de cada área, SUB-ABAS por fonte (ex.: Educação → INEP | Siconfi | Sistema contábil | Manual).
3.2 Para cada fonte, mostrar "Como a consulta é montada": método (GET/POST), endereço, parâmetros (nome, valor, de onde vem o valor — ex.: código IBGE do órgão, ano corrente), cabeçalhos (sem expor credenciais; mostrar "credencial configurada no console"), formato (JSON/CSV/planilha), mapeamento de campos (campo da fonte → indicador), periodicidade, última execução, resultado (código HTTP, tempo, registros) e um trecho da última resposta.
3.3 Parâmetros EDITÁVEIS pelo painel (com validação, histórico e auditoria) e botão "Testar consulta" que executa sem gravar e mostra a resposta; "Salvar e coletar agora" só depois do teste. Mudança de endereço/parâmetro exige confirmação e fica registrada.
3.4 Isso vale inclusive para a API de dados abertos da Prefeitura (Fiorilli), que hoje não mostra a consulta montada: listar cada endpoint usado (receitas, despesas, empenhos, contratos, licitações, pessoal, diárias etc.) com o GET completo e os parâmetros.
3.5 Todo indicador permite LANÇAMENTO MANUAL quando a consulta falhar (valor, período, fonte informada, motivo), com auditoria e aviso no portal "dado lançado manualmente em <data>".
3.6 A mesma tela de "consulta montada + parâmetros editáveis + teste" deve existir em todas as outras seções do painel que usam integração (transparência, licitações, PNCP, transmissões, IBGE, etc.).

4) Identidade e tema (reorganizar em abas)
4.1 Abas: Tema e cores | Brasão, mascote e imagens de fundo | Favicon | Redes sociais | Dados do município | Fotos e álbuns.
4.2 Tema e cores: cor principal e de destaque com seletor visual de cor (amostra, campo hexadecimal e prévia ao vivo de cabeçalho, botão e cartão), verificação automática de contraste AA com aviso; configuração de design/tema (nível 2 de personalização por blocos, como definido).
4.3 Brasão, mascote e imagens de fundo: envio com recorte, texto alternativo obrigatório e prévia.
4.4 Favicon: envio (PNG/SVG), geração dos tamanhos (16, 32, 180, 512) e prévia na aba do navegador.
4.5 Redes sociais: cadastrar rede (Instagram, Facebook, YouTube, X, TikTok, WhatsApp, LinkedIn, outra) com endereço, ícone da rede exibido automaticamente e ordem; "sincronizar" = mostrar no portal as últimas publicações por meio das APIs/incorporações oficiais de cada rede, quando a rede oferecer e houver credencial no console; sem credencial, só o link com ícone. Durante o período eleitoral, feed das redes suspenso.
4.6 Dados do município: número de habitantes, área, PIB, IDHM e outros indicadores vêm automaticamente da API do IBGE (servicodados.ibge.gov.br) pelo código IBGE do órgão, com data e fonte; atualizam quando o IBGE publicar (verificação semanal). Campos que o IBGE não fornece (ex.: distância da capital) ficam manuais, marcados como tal.
4.7 Fotos e álbuns: álbum com várias fotos; cada foto com título, descrição, crédito, LICENÇA (ex.: CC BY 4.0, todos os direitos reservados), texto alternativo obrigatório, categoria e autorização de uso de imagem (quando há pessoas); escolher a foto principal (destaque) do álbum e do portal; categorias com chave "suspender no período eleitoral" que tira do ar automaticamente as fotos daquela categoria no defeso.

5) Conteúdo (notícias, comunicados, páginas, perfis)
5.1 Editor de texto com formatação (títulos, negrito, itálico, listas, links, citação, tabela simples), colando de Word sem trazer estilos sujos; saída em HTML limpo e acessível.
5.2 Inserir imagens no corpo do texto (com texto alternativo obrigatório, legenda e crédito) e escolher a IMAGEM PRINCIPAL (thumbnail/destaque) com recorte 16:9 e ponto focal; prévia de como fica no bloco de notícias.
5.3 Rascunho, agendamento, revisão e publicação, com histórico de versões.

6) Página de login personalizada (painel do órgão e console)
6.1 Tela própria com: nome do órgão (tenant) e brasão, título configurável (ex.: "Área restrita da Prefeitura de Borá"), formulário de e-mail e senha, link "esqueci minha senha" e, quando liberado, botão "Entrar com gov.br".
6.2 Imagem de fundo escolhida no próprio painel do órgão (e no console, para a tela do gestor), com camada de contraste para manter AA.
6.3 Fluxo em duas etapas: 1º e-mail + senha; só depois de a senha estar correta aparece a tela do segundo fator (código do aplicativo autenticador). Mensagens de erro genéricas (não revelar se o e-mail existe), limite de tentativas e registro na auditoria.

7) Testes e implantação
7.1 Testes (banco de TESTE): mapa do layout acompanha a ordem; avaliação bloqueada por cookie e por limite de IP; teste de consulta sem gravar; lançamento manual com auditoria; contraste AA recusando cores ruins; favicon gerado; IBGE preenche os dados; foto de categoria suspensa some no defeso; login em duas etapas.
7.2 Capturas "depois", implantação com aprovação, merge + tag fase-9, PROGRESSO.md.
