# Fase 8 — capturas "antes", inventário e esboço (09/11/2026, só leitura)

**Capturas atuais** (`antes/`): página inicial, /painel, /transparencia/receitas e /diario, em 1280 px e 390 px. Nenhuma tem rolagem horizontal.
**Esboço** (`esboco/`): protótipo HTML local, com o CSS e as fotos do próprio portal e os números reais dos indicadores. Comunicados, notícias e serviços aparecem como **exemplo**. Capturas:
- `esboco-inicio-desktop-1280.png` (com o balão ⓘ aberto);
- `esboco-indicadores-balao-1280.png`;
- `esboco-inicio-celular-390.png`, sem rolagem horizontal;
- `esboco-menu-celular-390.png`.

> **Atenção:** o `Docs/referencia/prototipos/Main.dc.html` na VPS **não foi atualizado**. Ele tem a data de 07/11/2026 e é idêntico ao commit da Fase 2. O esboço segue o texto do PEDIDO-FASE8. Se houver uma versão nova do protótipo, envie e eu ajusto o esboço antes de implementar.

## A) Cabeçalho: situação atual e repetições
| Barra atual | Links |
|---|---|
| Barra escura acima do brasão | Transparência · e-SIC (`/acesso`) · Ouvidoria (`/acesso#ouvidoria`) · Diário Oficial · Licitações · Dados abertos · Área restrita · Câmara Municipal |
| Barra do brasão | Início · Serviços · Diário Oficial · Transparência · Notícias · Fale conosco (`/acesso`) |

**Destinos repetidos hoje:**
- `/transparencia` e `/diario` estão nas duas barras.
- `/acesso` aparece como "e-SIC" e como "Fale conosco".
- A Ouvidoria aponta para a mesma página, só com âncora.

**Proposta (esboço):**
| Barra | Itens | Observação |
|---|---|---|
| Serviços (acima do brasão) | IPTU 2ª via · Nota fiscal · Saúde · Educação · Assistência social · Empresas · **Todos os serviços** | Até a Carta de Serviços (Fase 10), cada item aponta para a busca de serviços do portal (`/servicos?q=…`). O endereço real (ex.: sistema de IPTU) é cadastrado pela Prefeitura na tela "Menus". Não invento endereços. |
| Portal (barra do brasão) | Início · Notícias · Fale conosco · Links úteis · Busca | — |
| Transparência e governo (abaixo do brasão) | Transparência · Painel de indicadores · Ouvidoria · e-SIC · Diário Oficial · Licitações e contratos · Legislação · Dados abertos · Proteção de dados (LGPD) | — |

Para que cada destino seja **único**, proponho páginas próprias:
- `/fale-conosco`: canais, sede e horário, com formulário curto;
- `/ouvidoria`: formulário de manifestação;
- `/e-sic`: pedido de informação;
- `/acesso` continua funcionando e redireciona.

O teste automatizado compara destinos normalizados (caminho + âncora) entre as 3 barras.

## C) Inventário de "ver mais / acessar" na página inicial
| Bloco | Hoje | Passa a ser |
|---|---|---|
| Destaque (busca) | "Mais buscados" em pílulas | sem mudança (são filtros de busca, não "ver mais") |
| Acesso direto (4 cartões sob o destaque) | cartões-link | sem mudança; repetem destinos das barras, o que é permitido fora do cabeçalho (ver decisão 6) |
| Serviços mais procurados | link sublinhado "Ver todos os serviços" | vira a faixa **Comunicados × Serviços mais acessados**, com os botões "Todos os comunicados" e "Todos os serviços" (secundários) |
| Acompanhe seu pedido | botão "Consultar" | sem mudança (já é botão) |
| Borá em números | pílulas "Painel de indicadores" (cheia), "Portal da Transparência" e "Dados abertos" | botões "Painel de indicadores" (primário) e "Dados abertos" (secundário). "Portal da Transparência" sai: já está na barra |
| Diário Oficial | link "Todas as edições e verificação de autenticidade" | botões **"Todas as edições"** (primário) e **"Verificar autenticidade"** (secundário) |
| Conheça Borá | pílula "Borá em números"; fotos não clicáveis | 3 fotos viram cartões que abrem `/conheca/<slug>`; botões **"Conheça mais"** (primário) e "Borá em números" (secundário) |
| Paço Municipal | link "Fale conosco" | botão "Fale conosco" (secundário) |
| Comunicados (hoje mostra notícias) | link "Todas as notícias" | vira o **bloco de Notícias** (destaque + 3 + lista), com o botão "Todas as notícias" |

**Botão único:** variantes primária e secundária, altura mínima de 44 px, raio de 999 px e seta opcional à direita. Links sublinhados ficam só dentro de textos corridos.

## B) Cartões de indicadores
- **Linhas fixas:** título curto | valor + unidade (algarismos tabulares) | uma linha de contexto (variação ou meta, em texto). Botão ⓘ real, com `aria-expanded`, que abre um balão com fonte (com link), período, data da atualização, método e base legal.
  - Fecha com Esc, com clique fora ou no próprio botão.
  - No celular, abre como painel inferior.
  - Sem JavaScript, o ⓘ leva à página do indicador.
- **Títulos curtos** para os 4 destaques atuais (até 32 caracteres; o nome completo fica no `aria-label` e na página do indicador):
  - "Receita arrecadada";
  - "Saúde: mínimo legal";
  - "Educação: mínimo legal";
  - "População estimada".
- **Onde se aplica:** o mesmo componente vale para os cartões de KPI do /painel.

## Ordem proposta da página inicial
1. Destaque com busca.
2. Acesso direto.
3. **Comunicados | Serviços mais acessados.**
4. Acompanhe seu pedido.
5. Borá em números.
6. Diário Oficial.
7. Conheça Borá.
8. **Notícias**, no lugar onde ficavam os comunicados.
9. Paço Municipal.

No defeso, as notícias somem e o bloco se recolhe sem deixar espaço vazio.

## Decisões que preciso de você
1. **Protótipo:** sigo pelo texto do pedido ou você envia o `Main.dc.html` atualizado?
2. **Destinos únicos:** aprova `/fale-conosco`, `/ouvidoria` e `/e-sic` como páginas próprias (com `/acesso` redirecionando)?
3. **Área restrita e Câmara Municipal** não estão nas listas do pedido. Proponho deixá-las só no rodapé, onde já existem ("Área restrita · painel administrativo" e o cartão da Câmara). Concorda?
4. **"Links úteis" e "Legislação"** ainda não existem. Proponho:
   - "Links úteis" como página editável no painel (lista de links externos com descrição);
   - "Legislação" listando as leis e os decretos publicados no Diário Oficial, mais um link externo configurável para o acervo antigo.
5. **Barra de Serviços:** os endereços reais (IPTU 2ª via, nota fiscal…) devem ser informados pela Prefeitura na tela "Menus". Até lá, cada item aponta para a busca interna de serviços. Concorda?
6. **Acesso direto** (4 cartões sob o destaque): manter ou remover? Eles repetem destinos das barras, o que o pedido permite fora do cabeçalho.
7. **Vídeos do Conheça Borá:** recomendo só links do YouTube (exibidos com youtube-nocookie), sem envio de arquivo de vídeo, por causa do espaço e da memória da VPS. Concorda?

---
# Revisão v2 (09/11/2026): protótipo atualizado e PEDIDO-FASE8 revisado

**Respostas do usuário às 7 decisões:**
1. O `Main.dc.html` atualizado foi enviado.
2. Ok.
3. Ok.
4. "Página acrescentada ao PEDIDO-FASE8.md como item J" (**ver observação abaixo**).
5. Ok.
6. Manter, com opção de personalizar os botões no painel.
7. Ok.

**Esboço v2** (`esboco/esboco-*.png`; a versão anterior ficou em `esboco/v1-*.png`):

- **Cabeçalho**, conforme o protótipo de 09/11 e o item A revisado:
  - barra de acessibilidade com "Câmara Municipal" e "Área restrita" ao final dos atalhos e o botão "Libras";
  - **barra institucional na cor principal**: Transparência, Painel de indicadores, Diário Oficial, Licitações, Legislação, Serviços, Ouvidoria, e-SIC, Dados abertos;
  - barra do brasão com Início, Notícias, Comunicados, Conheça Borá, Fale conosco, Transmissões e o botão Buscar;
  - faixas "AO VIVO" (só durante transmissão) e de aviso;
  - a barra de serviços deixa de existir.
  - Não há destino repetido entre as barras.
- **Página inicial, na ordem do protótipo:**
  1. Destaque e busca, com o Acesso direto (4 botões personalizáveis no painel).
  2. **Comunicados | Serviços mais acessados.**
  3. Acompanhe seu pedido.
  4. **Acompanhe a gestão**: cartões de indicadores com título curto e ⓘ, e a linha "Atualizado em … · fonte de cada número no ⓘ".
  5. **Publicações oficiais**: cartões com seletor e botão "Ver".
  6. **Atos oficiais e oportunidades**: botões "Todas as edições do Diário" e "Verificar autenticidade".
  7. **Transmissões**: 3 últimas gravações; some sem canal configurado.
  8. **Conheça Borá**: números, 3 cartões "Ver perfil" e os botões "Conheça mais" e "Borá em números".
  9. **Notícias**: destaque, 3 secundárias, lista de títulos e "Todas as notícias".
  10. **Paço Municipal**: botões "Unidades e horários" e "Fale conosco".
- **Botão flutuante do VLibras** no canto inferior direito.
- **Menu do celular** com as seções Portal e Transparência e governo; sem rolagem horizontal em 390 px.

**Item G — diagnóstico das Transmissões** (só leitura):
- **Prefeitura:** `/transmissoes` responde **404**. O módulo opcional "Transmissão de audiências" não está contratado no console (o módulo "transm" é só do Legislativo), e não há canal configurado.
- **Câmara:** a página responde 200, mas não há canal configurado, nenhuma transmissão cadastrada e nenhuma sessão com vídeo, então não há nada para mostrar.
- **Código:** **não existe integração com a API do YouTube**. As transmissões são cadastradas à mão, com o ID do vídeo, e não há chave do YouTube em Credenciais de fontes.
- **Proposta:**
  - credencial `youtube` (chave da YouTube Data API) cadastrada no console, igual à do IEG-M;
  - ID do canal por órgão em /admin/transmissoes;
  - coletor que, a cada 2 minutos e só nos horários da agenda, verifica se há transmissão ao vivo (cada busca gasta 100 unidades de uma cota diária de 10.000);
  - uma vez por dia, lê as últimas gravações pela playlist de envios do canal (1 unidade por consulta);
  - botão "Iniciar transmissão" no painel como alternativa.
  - Para a Prefeitura, o módulo "Transmissão de audiências" precisa ser contratado no console.

**Observações:**
- **O item J não está no `PEDIDO-FASE8.md`** salvo na VPS (09/11, 15h45). O arquivo vai de A até I (Testes e implantação). Pela sua resposta, seria a página de "Links úteis" ou "Legislação"; preciso do texto.
- Os **critérios de aceite** no fim do pedido ainda dizem "serviços acima do brasão". Sigo o item A revisado, que tira a barra de serviços.
- **VLibras:** o widget oficial carrega um script de `vlibras.gov.br` (Governo Federal). Isso exige liberar esse domínio na política de segurança de conteúdo (CSP), que hoje só aceita o próprio portal. O widget pode ser ligado e desligado pelo painel.

**Decisões pendentes:**
1. **Item J:** pode salvar ou reenviar o texto?
2. **Publicações oficiais:** aprova o bloco como no protótipo, com 4 cartões (Diário, Contas públicas, Licitações, Legislação)? "Concursos" só entra quando existir a seção de concursos.
3. **Transmissões:** aprova a integração com o YouTube como proposta? E a contratação do módulo "Transmissão de audiências" para a Prefeitura (feita por você no console, ou por mim com aprovação)?
4. **VLibras:** aprova liberar `vlibras.gov.br` na CSP para o widget oficial?

**Atualização (09/11, 15h55):** o item que faltava é o **I) Página Legislação** (o J virou Testes e implantação).
- `/legislacao` é montada automaticamente a partir dos atos do Diário.
- Filtros por tipo, situação, ano e texto.
- Página de cada ato com a relação com outros atos; a situação muda sozinha quando um ato altera ou revoga outro.
- Exportação em CSV/JSON e base legal.
- A Câmara lê a lista pela API pública.
- Importação opcional do acervo antigo por planilha (`Docs/modelos/legislacao.csv`).
- **Sem raspagem do site antigo.**

**Ainda depende de você:** o **endereço da página de legislação do site atual da Prefeitura**, para o botão "Acervo anterior ao Diário eletrônico" (item 24e pede confirmação antes de fixar).
