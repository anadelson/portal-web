# Fase 8 — Ajustes do portal da Prefeitura (navegação, cartões, botões, Conheça Borá, comunicados e notícias)

Pedido do gestor em 08/11/2026, a partir do uso do piloto em pmbora.conectatech.tech.
Base: Fase 7 e fase-7-layout. Se a fase-7-layout ainda não foi implantada, aplique o item B dentro dela; o restante vai no branch fase-8.
REGRAS: as mesmas das fases anteriores (um código para todos os órgãos; branch fase-8 com commits pequenos e tag ao final; migrações idempotentes via "python -m app.provision atualizar"; aprovação antes de cada comando que altere a VPS; testes só em banco de TESTE; nunca mostrar senhas/.env; acessibilidade AA; LGPD; nada inventado: textos e descrições que não existem ficam vazios e o bloco se adapta, sem "lorem ipsum" no portal; registrar tudo em Docs/PROGRESSO.md).
Antes de implementar: tire capturas atuais (1280 px e 390 px) da página inicial, do /painel e de uma página interna em Docs/avaliacao-fase8/antes/, me mostre um esboço da nova página inicial (pode ser captura de um protótipo HTML local) e PARE para aprovação.

A) Navegação: três barras, sem repetição
1. Ordem de cima para baixo:
   - Barra de acessibilidade (como está).
   - Barra de SERVIÇOS (acima do brasão): atalhos de serviços ao cidadão (ex.: IPTU 2ª via, nota fiscal, saúde, educação, assistência social, empresas) + "Todos os serviços" (Carta de Serviços).
   - Barra do BRASÃO: brasão e título do portal à esquerda; à direita, só links do próprio portal: Início, Notícias, Fale conosco, Links úteis (e Busca).
   - Barra INSTITUCIONAL / TRANSPARÊNCIA (abaixo do brasão): Transparência, Painel de indicadores, Ouvidoria, e-SIC, Diário Oficial, Licitações e contratos, Legislação, Dados abertos, Proteção de dados (LGPD).
2. Regra: cada destino aparece em uma única barra. Crie um teste automatizado que falha se um mesmo link (mesmo destino) aparecer em duas barras do cabeçalho. O rodapé pode repetir links (é mapa do site).
3. Os itens de cada barra são editáveis no painel administrativo (tela "Menus"), com o campo "barra" (serviços / portal / institucional), ordem, ícone e ativo; o painel recusa salvar um destino que já está em outra barra.
4. Celular (390 px): barra de acessibilidade compacta; um botão "Menu" abre um painel com as três seções nomeadas (Serviços, Portal, Transparência e governo), sem rolagem horizontal; foco preso no menu aberto e Esc fecha.
5. Respeite o período eleitoral: itens de classe vedada continuam sumindo como hoje.

B) Cartões de indicadores (/painel e bloco "Indicadores em números" da página inicial)
6. Título em uma linha: crie no catálogo o campo "título curto" (até 32 caracteres, validado no painel administrativo); o nome completo fica na página do indicador e no aria-label do cartão. Nunca cortar texto com reticências sem o título completo acessível.
7. Alinhamento: todos os cartões de uma fileira com a mesma estrutura e altura, em linhas fixas: título curto | valor + unidade | uma linha de contexto (variação ou meta, em texto). Valores com algarismos tabulares, alinhados na mesma altura entre cartões.
8. Fonte oculta: tire do cartão a fonte, datas, método e base legal. Ao lado do título, um botão ⓘ (botão real, aria-label "Sobre este indicador: <título>", aria-expanded) abre um balão (toggletip) com: fonte com link, período de referência, data da atualização, método de cálculo (ex.: por habitante), base legal. Fecha com Esc, clique fora ou no próprio botão; funciona com teclado e leitor de tela; no celular abre como painel inferior. Sem JavaScript, o ⓘ leva à página do indicador.
9. A página de cada indicador continua mostrando tudo (fonte, datas, tabela, downloads) por extenso.

C) Padrão único de acesso a conteúdos: botões
10. Na página inicial e nas páginas de entrada, todo "ver mais / acessar" passa a ser BOTÃO (componente único, com variantes primária e secundária, altura mínima 44 px, mesmo raio, ícone opcional à direita). Links sublinhados ficam só dentro de textos corridos.
11. Exemplos já identificados: Diário Oficial ("Todas as edições e verificação de autenticidade" → botão "Todas as edições" + botão secundário "Verificar autenticidade"); Conheça Borá (manter o botão "Borá em números" no mesmo padrão). Faça o inventário de todos os blocos da página inicial e me mostre a lista do que mudou.

D) Conheça Borá: perfis com galeria e "Conheça mais"
12. Cada foto da seção (hoje: "Praça e Igreja Matriz, vistas do alto", "Igreja Matriz", "Agroindústria da cana-de-açúcar") passa a ser um cartão clicável que abre um PERFIL em /conheca/<slug>: título, descrição (texto formatado simples), foto de capa, galeria de fotos (miniaturas + visualização ampliada acessível, navegação por teclado, legenda e crédito de cada foto) e vídeos relacionados (por link do YouTube, exibido com youtube-nocookie; envio de arquivo de vídeo só se você aprovar o limite de tamanho).
13. Botão "Conheça mais" ao final da seção leva a /conheca: galeria com todos os perfis (lugares, patrimônio, eventos, festas, economia), filtro por categoria e busca.
14. Painel administrativo, tela "Conheça Borá": criar/editar perfis, categoria, capa, ordem, fotos (texto alternativo OBRIGATÓRIO, legenda, crédito/autor), vídeos, publicar/despublicar e "destaque na página inicial" (até 3).
15. LGPD e imagem: em fotos com pessoas identificáveis, campo "autorização de uso de imagem registrada" (sim/não); sem autorização, a foto não publica. Período eleitoral: cada perfil tem classe (lugares e patrimônio = utilidade; eventos da gestão = publicidade, suspensos no defeso).
16. Migração: as 3 fotos atuais viram os 3 primeiros perfis, com os títulos e créditos atuais; descrição vazia até a Prefeitura escrever (o perfil mostra só título e fotos enquanto isso).

E) Comunicados ao lado dos serviços mais acessados
17. Nova faixa na página inicial em duas colunas: COMUNICADOS à esquerda e SERVIÇOS MAIS ACESSADOS à direita (no celular, empilha nessa mesma ordem).
18. Comunicados aceita somente os tipos: comunicado, aviso, convocação, convite, nota oficial, edital de chamamento (lista editável no painel, mas sem "notícia"). Cada item: etiqueta do tipo, título, data; validade opcional (some da página inicial após a data). Até 5 itens + botão "Todos os comunicados" (/comunicados, com filtro por tipo e ano).
19. Notícia não pode ser cadastrada como comunicado e vice-versa: são tipos de conteúdo distintos no painel.

F) Notícias no lugar onde ficavam os comunicados
20. Bloco de notícias com:
   - Destaque: imagem grande (16:9), título, data e hora da publicação (ex.: "08/11/2026, 09h44"), resumo opcional.
   - 3 notícias secundárias, menores, lado a lado (imagem 16:9 menor, título, data e hora).
   - Lista com os títulos das notícias seguintes (somente o título, link para a notícia), até 5.
   - Botão "Todas as notícias".
21. Painel: marcar "destaque" (se nenhuma estiver marcada, a mais recente é o destaque); imagem de capa com texto alternativo obrigatório e recorte 16:9 com ponto focal; data e hora de publicação (agendamento opcional).
22. Período eleitoral: notícias são classe publicidade e somem no defeso, como já definido; o bloco se recolhe sem deixar espaço vazio.

G) Testes e implantação
23. Testes (banco de TESTE): nenhuma duplicidade entre as barras; menu do celular com teclado; ⓘ abre/fecha com teclado e Esc; cartões com mesma altura; comunicados não aceitam tipo notícia; perfil sem autorização de imagem não publica foto; ordem do bloco de notícias (destaque, 3, lista); defeso esconde notícias e eventos.
24. Capturas "depois" lado a lado com as "antes" em Docs/avaliacao-fase8/, implantação com aprovação, merge + tag fase-8, PROGRESSO.md e ESPEC-VISUAL.md atualizados.

CRITÉRIOS DE ACEITE
- Nenhum link repetido entre as barras do cabeçalho; serviços acima do brasão, portal na barra do brasão, transparência e governo abaixo.
- Cartões de indicadores com título em uma linha, alinhados, e fonte só pelo ⓘ.
- Todo acesso a "ver mais" na página inicial é botão no mesmo padrão.
- Fotos do Conheça Borá abrem perfis com galeria e vídeos; "Conheça mais" lista todos os perfis.
- Comunicados à esquerda e serviços à direita; notícias com destaque, 3 secundárias e lista de títulos.
