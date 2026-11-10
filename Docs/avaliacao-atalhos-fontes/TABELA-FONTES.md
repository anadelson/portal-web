# Fontes — "elemento | atual | protótipo" (10/11/2026) — PARADA para aprovação antes de corrigir

**Como foi medido**
- **Painel e console:** em ambiente de TESTE (banco de teste, usuários de teste), em 1366 px com zoom 100%. São os valores calculados pelo navegador (`getComputedStyle`), dados como tamanho mais comum (mín.–máx.).
  - Telas do painel: Início, Página inicial (blocos), Identidade, Conteúdos, Novo conteúdo e Usuários.
  - Telas do console: Início (órgãos), Órgão, Catálogo, Aparência e Credenciais.
  - Medidas brutas: `antes/fontes-adm-atual.json`.
- **Protótipos:** estilos inline de `Docs/referencia/prototipos/Backend.dc.html` e `Console.dc.html`, conferidos com a tabela do pedido.
- **Indicadores** deu 404 no banco de teste, porque o módulo de BI não está contratado lá. A tela usa a mesma folha (`admin.css`) e os mesmos componentes das outras.

**Resultado:** painel e console já usam Public Sans 15 px / 1,5 no texto base. A diferença está nos títulos, nos campos, nas tabelas, nas notas e nos botões. O painel e o console compartilham a mesma folha, então os valores são iguais nas duas telas.

## Painel administrativo e console

| elemento | atual (painel) | atual (console) | protótipo | proposta |
|---|---|---|---|---|
| Texto base | 15 px / 1,5 | 15 px / 1,5 | 15 px / 1,5 | sem mudança |
| Título da tela (H1) | **21 px** / 700 | **21 px** / 700 | 22–24 px (protótipo: 22) | **23 px** / 700 |
| Título de seção/cartão (H2) | **17 px** / 700 | **17 px** / 700 | 18 px | **18 px** / 700 |
| Subtítulo dentro de cartão (H3) | — | — | 15 px | 15 px / 700 |
| Menu lateral (itens) | 15 px / 600 (cabeçalhos dos grupos 13 px) | 15 px / 600 (grupos 13 px) | 14–15 px (grupos 12–13) | sem mudança (15 px; grupos 13 px) |
| Rótulos de campo | **13 px** / 600 (Página inicial: 15 px / 400) | **13 px** / 600 | 14 px / 600 (13 px nos compactos) | **14 px** / 600 em todas as telas |
| Campos (input, select, textarea) | **13 px**; no Novo conteúdo, alguns **13,3 px** (padrão do navegador) | **13 px** | 15 px | **15 px** (`font: inherit`) |
| Altura dos campos | 38 px (Usuários: 35; Novo conteúdo: 24 no seletor de arquivo) | 38 px | 38–42 px | **mínimo de 40 px** |
| Cabeçalho de tabela | **12 px** / 700 | **12 px** / 700 | 12–13 px | **13 px** / 700 |
| Célula de tabela | 14 px | 14 px | 13–14 px | sem mudança (14 px) |
| Ajuda/nota (small, .ajuda, .legal) | **11,7 px** (mín. 10,8 px no Novo conteúdo) | **11,7 px** | 12 px | **12 px**, que vira o mínimo absoluto |
| Botões | 15 px / **700**, altura **38 px** (no Novo conteúdo, alguns 13,3 px) | **14 px** / **700**, altura **38 px** | 14–15 px / 600, altura ≥ 40 px | **15 px / 600, altura mínima de 40 px** em todos |
| Etiquetas (badge, chip) | 11–12 px | 11–12 px | 11–12 px / 700 | **12 px** (11 px só em "exemplo") |

## Portal (para referência; a escala do pedido já está definida)

Medido no ar em 10/11/2026, página inicial e /noticias em 1920 px. Medidas brutas: `antes/antes-medidas.json`.

| elemento | atual | protótipo/pedido |
|---|---|---|
| Texto base | 17 px | 17 px / 1,55 |
| Barra institucional | 15 px / 600 | 15 px / 600 |
| Menu da barra do brasão | **17 px** / 600 | **16 px** / 600 |
| Hero: título / subtítulo | 50 / 19 px | 50 / 19 px |
| H1 interno / introdução | 36 / 18 px | 36 / 18 px |
| H2 de seção da página inicial | **22 px** (18–30) | **26 px** (Acompanhe a gestão 28, Conheça 30, títulos dentro de cartões 22) |
| H3 de cartão | 18–20 px / 700 | 17–20 px / 600–700 |
| Descrição de cartão, subtítulo de seção | **13–14 px** | **14–15 px** |
| Data, metadados | 13–14 px | 13 px |
| Etiquetas, fonte/nota | **11–12 px** | **12 px** (só "exemplo" 11 px) |
| Botões | 17 px / 700 (alguns 14) | 16–17 px / 600, altura ≥ 44 px |
| Número de indicador | 28 px / 700 | 28 px / 700 |

## Como será feito (depois da aprovação)
- **Escala em variáveis no `:root`:**
  - portal: `--fs-base`, `--fs-h2`, `--fs-desc`, `--fs-meta`, `--fs-etq`, `--fs-btn` …, em `portal.css`;
  - painel e console: `--fs-tela`, `--fs-secao`, `--fs-rotulo`, `--fs-campo`, `--fs-tab-cab`, `--fs-nota`, `--fs-btn` …, em `admin.css`.
- **Troca dos `font-size` soltos pelas variáveis:**
  - templates do portal: 31 (estilo inline);
  - templates do painel e do console: 5;
  - regras em `portal.css`: 191;
  - regras em `admin.css`: 32.
- **Capturas antes/depois** em 1920, 1366 e 390 px, mais teste automatizado que falha se aparecer texto abaixo de 12 px (exceto "exemplo").
