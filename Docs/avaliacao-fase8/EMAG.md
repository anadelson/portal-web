# Verificação eMAG 3.1 — Fase 8 (09/11/2026)

Ambiente: prévia descartável com cópia dos bancos e o código do branch `fase-8` (produção não alterada).
Ferramentas: Chromium 131 (Playwright 1.49) em 1280 px e 390 px; axe-core 4.10.2 (regras WCAG 2.0/2.1 A e AA); roteiros de teclado automatizados (`verificacoes.json`).
Páginas: início, painel, receitas, Diário, legislação, comunicados, Conheça, fale conosco, acessibilidade (Prefeitura); início, legislação e transmissões (Câmara).

**Legenda:** Atende · Parcial (com observação) · Não verificado (precisa de teste humano).

## Resultado automático
- **axe-core:** 0 violações nas 12 páginas.
  - Corrigidos durante a verificação: listas dentro de `role="img"` nos gráficos do painel (herança da Fase 7) e contraste do cartão do presidente da Câmara (causado por conflito de nome de classe da Fase 8).
- **Rolagem horizontal:** nenhuma em 390 px e 1280 px.
- **Política de segurança (CSP):** nenhuma violação, inclusive com o VLibras aberto.
- **Cabeçalho:** nenhum destino repetido entre a barra institucional e a barra do portal (12 páginas). Também é checado em `tests/teste_fase8.py`.
- **Cartões de indicador:** mesma altura em todas as linhas (início e painel).

## Por seção do eMAG
### 1. Marcação
| Rec. | Requisito | Situação |
|---|---|---|
| 1.1 | Padrões web (HTML5 válido, CSS separado) | Atende. Estilos em `portal.css`; os estilos inline que restam são só posição de foco das fotos e larguras de barras dos gráficos. |
| 1.2 | Código organizado (conteúdo antes da apresentação) | Atende |
| 1.3 | Títulos hierárquicos | Atende. Um `h1` por página e blocos com `h2`/`h3` (axe sem `heading-order`). |
| 1.4 | Ordem lógica de navegação | Atende. A ordem do Tab segue a ordem visual (roteiro do menu do celular). |
| 1.5 | Atalhos de teclado | Atende. Alt+1 a Alt+4 (conteúdo, menu, busca, rodapé). Com o cabeçalho cheio, Alt+3 foca o campo de busca, que se abre. |
| 1.6 | Sem tabelas para diagramação | Atende |
| 1.7 | Blocos de conteúdo separados | Atende. Seções com `aria-labelledby`. |
| 1.8 | Sem atualização automática | Atende |
| 1.9 | Sem nova janela sem aviso | Atende |

### 2. Comportamento
| Rec. | Requisito | Situação |
|---|---|---|
| 2.1 | Tudo funciona pelo teclado | Atende (verificado pelo roteiro de teclado):<br>• **Menu do celular:** Enter abre; o foco fica preso no painel por 40 Tabs e 5 Shift+Tab; Esc fecha e o foco volta ao botão.<br>• **ⓘ:** Enter abre com `aria-expanded`; Esc fecha e devolve o foco; clique fora fecha.<br>• **Galeria:** dialog nativo, setas navegam, Esc fecha e o foco volta à miniatura. Coberta pelo teste de servidor; a prévia não tinha perfil com 2 fotos para o roteiro. |
| 2.2 | Sem script para conteúdo essencial | Atende:<br>• ⓘ sem JS vira link para a página do indicador.<br>• Menu sem JS mostra as barras.<br>• Galeria sem JS abre a imagem. |
| 2.3 | Sem limite de tempo | Atende |
| 2.4 | Sem efeitos piscantes | Atende. O ponto "● Ao vivo" é estático. |
| 2.5 | Sem movimento automático | Atende. O VLibras só abre quando a pessoa pede. |
| 2.6 | Sem atualização automática | Atende |
| 2.7 | Sem redirecionamento automático | Atende. `/acesso` usa 301 do servidor, sem refresh. |

### 3. Conteúdo/informação
| Rec. | Requisito | Situação |
|---|---|---|
| 3.1 | Idioma principal | Atende (`lang="pt-BR"`) |
| 3.2 | Mudança de idioma | Atende. Link do NVDA com `hreflang="en"` e aviso "página em inglês". |
| 3.3 | Título descritivo | Atende |
| 3.4 | Localização (migalhas) | Atende nas páginas internas novas |
| 3.5 | Links descritivos | Atende. Botões "Todas as notícias", "Ver legislação" etc. e ⓘ com `aria-label` "Sobre este indicador: …". |
| 3.6 | Texto alternativo | Atende. Alt **obrigatório** no envio de fotos (Conheça, capa de notícia); fotos decorativas com `alt=""`. |
| 3.7 | Áudio e vídeo | Parcial. A página mostra se o vídeo tem legendas e janela de Libras, mas legendar é responsabilidade de quem publica no canal. |
| 3.8 | Não depender só da cor | Atende. Situação da lei em texto (vigente/alterada/revogada); "Ao vivo" com texto. |
| 3.9 | Contraste | Atende (axe sem `color-contrast`). O alto contraste continua disponível. |
| 3.10 | Foco visível | Atende. Anel duplo da Fase 7. |
| 3.11 | Leitura de textos | Atende. Linguagem simples e sem jargão nos cartões. |
| 3.12 | Documentos em formato acessível | Parcial. Legislação em HTML, CSV e JSON. O PDF assinado do Diário é o original oficial. |

### 4. Apresentação/design
| Rec. | Requisito | Situação |
|---|---|---|
| 4.1 | Contraste mínimo 4,5:1 | Atende (axe) |
| 4.2 | Não usar só cor | Atende |
| 4.3 | Redimensionar texto sem perda | Atende. Botões A+ / A / A−; 390 px sem rolagem horizontal. |
| 4.4 | Foco visível | Atende |

### 5. Multimídia
| Rec. | Requisito | Situação |
|---|---|---|
| 5.1 | Alternativa para vídeo | Parcial (ver 3.7) |
| 5.2 | Legendas | Parcial. Indicador "CC" quando o YouTube informa legendas. |
| 5.3 | Libras | Atende para o texto da página: **VLibras** em todas as páginas. Janela de Libras nos vídeos depende da produção. |
| 5.4 | Controle de áudio | Atende. O player do YouTube não toca sozinho. |

### 6. Formulário
| Rec. | Requisito | Situação |
|---|---|---|
| 6.1 | Alternativa para botões de imagem | Atende |
| 6.2 | Rótulos associados | Atende. axe sem `label`; filtros da legislação e do Conheça com `<label>`. |
| 6.3 | Ordem lógica | Atende |
| 6.4 | Instruções de preenchimento | Atende |
| 6.5 | Erros identificados | Atende (mensagens em texto) |
| 6.6 | Agrupar campos | Atende (`fieldset`/`legend` no painel) |
| 6.7 | CAPTCHA | Não usado |

## O que NÃO foi verificado
- **Leitor de tela real (NVDA):** não foi feito. O NVDA só roda no Windows, e esta verificação rodou num servidor Linux sem tela. O roteiro automático cobre o que um leitor anuncia: nomes acessíveis, `aria-expanded`, foco e ordem. Mesmo assim, **falta o teste humano**.
  - Roteiro sugerido (NVDA + Firefox ou Chrome): início, painel, um serviço, ouvidoria e transmissões.
  - Em cada página: navegar por títulos (H), regiões (D) e Tab; abrir o ⓘ e o menu do celular (janela estreita); preencher a ouvidoria.
  - Anotar os achados neste arquivo.
- **VLibras:** o widget carrega e o botão abre o avatar sem violação de CSP. A qualidade da tradução é do serviço do Governo Federal.
