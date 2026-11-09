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
