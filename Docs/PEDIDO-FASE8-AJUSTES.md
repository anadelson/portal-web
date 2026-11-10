# Fase 8 — Ajustes: portal publicado x protótipo (conferência de 09/11/2026)

Conferência feita em pmbora.conectatech.tech (1280 px) contra Docs/referencia/prototipos/Main.dc.html (versão de 09/11, com notícias ao lado do Paço). Copie de novo esse Main.dc.html do meu PC se o da VPS for anterior a 09/11 12h45.
REGRAS: as mesmas (branch fase-8-ajustes, aprovação antes de alterar a VPS, testes no banco de TESTE, nada inventado). Antes de corrigir, me mostre a lista abaixo confirmada (ou corrigida) com capturas "antes" e PARE.

A) Página inicial
1. NOTÍCIAS: hoje ocupa a largura toda, só com texto, e o Paço Municipal fica embaixo, também com largura toda. No protótipo: uma fileira com o cartão de Notícias (≈ 2/3, flex 2 1 520px) e o cartão do Paço (≈ 1/3, flex 1 1 300px, foto em cima e botões "Unidades e horários" e "Fale conosco" embaixo); no celular empilham.
   Dentro do cartão de Notícias: (a) destaque em duas colunas: imagem 16:9 à esquerda e, à direita, editoria + data e hora, título 20 px e resumo; (b) fileira com 3 notícias menores (imagem 16:9, data e hora, título 15 px); (c) lista "só títulos" das seguintes; (d) botão "Todas as notícias" no fim do cartão.
   Sem imagem cadastrada: usar uma imagem neutra por editoria (fundo na cor da editoria + ícone), NUNCA foto de banco de imagens nem foto de outra notícia.
2. CONHEÇA BORÁ: hoje o texto ocupa a largura toda e as 3 fotos ficam em fileira abaixo. No protótipo: cartão branco de duas colunas — à esquerda brasão + "Conheça Borá", título, texto, números do IBGE em caixinhas e os botões "Conheça mais" (primário) e "Borá em números" (secundário); à direita mosaico de fotos (a primeira ocupa duas linhas à esquerda; as outras duas empilhadas à direita), cada foto clicável com legenda e etiqueta "Ver perfil".
3. TRANSMISSÕES: o item não aparece no cabeçalho e não há bloco na página inicial. Confirme se é porque o canal do YouTube não está configurado (item G do PEDIDO-FASE8). Se for, mostre no painel o aviso "configure o canal" e me diga o que falta.
4. COMUNICADOS e SERVIÇOS MAIS ACESSADOS estão vazios ("Nenhum comunicado em vigor", "Nenhum serviço publicado"). Isso é esperado sem cadastro; confirme apenas que os dois cartões ficam lado a lado com a mesma altura e que o estado vazio tem o mesmo estilo (caixa cinza clara, texto 14 px).

B) Páginas internas: um único "casco" para todas
5. Há dois estilos diferentes de página interna. As páginas novas (/transparencia, /servicos, /legislacao, /diario, /painel, /comunicados, /conheca, /fale-conosco) têm trilha "Você está em", título e introdução. As antigas NÃO têm trilha nem introdução: /noticias, /ouvidoria, /e-sic, /governo (e confira as demais: /noticias/<item>, /fotos, /links-uteis, /privacidade, /acessibilidade, /mapa-do-site, páginas de secretaria e de serviço).
   Crie (ou use) UM template base para página interna e passe TODAS as páginas por ele, na ordem do protótipo:
   - trilha "Início › (seção-mãe) › Página" (14 px, links sublinhados na cor principal);
   - H1 36 px, peso 700, espaçamento -0,02em;
   - introdução 18 px, cor #4B5563, até 70 caracteres por linha;
   - "Base legal:" em 12 px LOGO ABAIXO da introdução (no protótipo fica no topo; hoje está no fim da página — mova para o topo);
   - conteúdo em cartões brancos com borda #DCE1E6 e raio 14–16 px; botões no padrão único (primário cheio / secundário com contorno, 44 px, raio 999 px);
   - "Avalie esta página" no fim, igual em todas.
6. /noticias: título deve ser "Notícias" (não "Notícias e avisos") e a lista mostra SÓ notícias. Hoje aparecem itens que são comunicados (edital de concurso, aviso de vacinação): mova-os para Comunicados (tipo convocação/aviso) ou me pergunte. Layout do protótipo: filtro por secretaria e lista de cartões horizontais (imagem 16:9 à esquerda, editoria + data e hora, título e resumo à direita).
7. Página da notícia: cartão branco até 820 px, imagem 21:9 no topo, "Publicado em <data, hora> · <editoria>", texto 18 px, botão "Voltar para notícias" no padrão de botão.
8. /ouvidoria e /e-sic: mantenha as duas páginas (são itens separados do menu), mas no casco padrão (trilha, intro, base legal) e com as abas em pílula "Ouvidoria | Acesso à informação" no topo, como no protótipo, e a coluna lateral "Outros canais".
9. /governo: casco padrão; cartões das secretarias com imagem 16:9, nome 19 px e resumo; botões de Legislação/Organograma no padrão.

C) Conferência final
10. Gere capturas lado a lado (portal x protótipo) das páginas: inicial, notícias, notícia, comunicados, conheça, perfil, ouvidoria, e-SIC, governo, legislação, em 1280 e 390 px, em Docs/avaliacao-fase8/conferencia/. Para o protótipo, use as medidas e estilos do Main.dc.html como referência (o arquivo usa estilos inline).
11. Tabela final "item | estava | ficou | ok?" em Docs/avaliacao-fase8/CONFERENCIA.md. Implantação com aprovação, merge e PROGRESSO.md.
