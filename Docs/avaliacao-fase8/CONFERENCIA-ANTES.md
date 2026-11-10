# Ajustes da Fase 8 — conferência "antes" (10/11/2026) — PARADA para aprovação

Referência: `Docs/referencia/prototipos/Main.dc.html` da VPS, de 09/11/2026 às 14h26 (horário de Brasília), posterior a 12h45; é a versão certa, sem precisar copiar de novo.
Portal: pmbora.conectatech.tech, capturas em 1280 e 390 px em `Docs/avaliacao-fase8/conferencia/antes/`, medidas em `antes/medidas.json`. Só leitura: nada foi gravado.
Branch: `fase-8-ajustes`.

## A) Página inicial

### 1. Notícias + Paço — CONFIRMADO
- **Hoje** (`recorte-noticias-e-paco-1280.png`):
  - Notícias ocupa a largura toda (1160 px) e tem só texto, sem imagem (0 imagens no bloco).
  - O Paço fica embaixo, também com a largura toda (foto à esquerda, texto à direita).
- **No protótipo:**
  - Uma fileira com dois cartões: Notícias (`flex: 2 1 520px`, raio 20 px, padding 24) e Paço (`flex: 1 1 300px`, foto 220 px em cima, texto, botões).
  - Dentro de Notícias:
    - destaque em grade (imagem 16:9 | editoria em maiúsculas na cor principal + data e hora, título 20 px, resumo 15 px);
    - fileira de 3 menores (16:9, data e hora 12 px, título 15 px);
    - lista só de títulos;
    - botão "Todas as notícias" no fim (secundário).
  - No celular, os dois cartões empilham.
- **Imagem neutra:** sem foto cadastrada, o protótipo usa a "Cena" (fundo na cor + ícone). Vou fazer uma imagem neutra por editoria (cor da editoria + ícone, em SVG próprio), nunca foto de banco de imagens nem de outra notícia. **Precisa da decisão D2** (de onde vem a editoria).

### 2. Conheça Borá — CONFIRMADO
- **Hoje** (`recorte-conheca-1280.png`): sem cartão branco e sem brasão. Texto e números ocupam a largura toda; as 3 fotos ficam em fileira abaixo (com "Ver perfil"); os botões vêm no fim.
- **No protótipo:**
  - Cartão branco, raio 24, em duas colunas (`minmax(min(100%,420px),1fr)`).
  - **À esquerda:** brasão 72 px + "CONHEÇA BORÁ", título 30 px, texto, números em caixinhas `#F4F7F9`, fonte, "Conheça mais" (primário) e "Borá em números" (secundário).
  - **À direita:** mosaico `1.1fr 1fr`, com a 1ª foto ocupando 2 linhas, mínimo de 440 px de altura, legenda e etiqueta "Ver perfil".
- **Observação:** hoje há 5 caixinhas de números (3 do IBGE + 2 manuais). Mantenho todas, no estilo do protótipo.

### 3. Transmissões — CONFIRMADO: falta configuração, não é erro de código
- **Por que não aparece:**
  - O item do cabeçalho e o bloco só aparecem com o módulo de transmissão. Na Prefeitura, o módulo **"audiências" não está contratado** (é opcional no catálogo).
  - Além disso, não há canal do YouTube, a chave da YouTube Data API não foi cadastrada no console, e há 0 transmissões.
  - A tela do painel que mostra "Configure o canal" (`/admin/transmissoes`) só existe com o módulo ligado, por isso hoje o aviso não aparece em lugar nenhum.
- **Câmara:** tem o módulo (obrigatório), mas também não tem canal nem vídeos; por isso o bloco não aparece, e o item "Transmissões" aparece na barra dela.
- **O que falta (D5):**
  1. Contratar o módulo "audiências" para a Prefeitura no console; está pendente desde a Fase 8 ("quem contrata").
  2. Cadastrar a chave da YouTube Data API no console (Credenciais de fontes).
  3. Informar o ID do canal (UC…) em Painel → Transmissões, nos dois órgãos.
- **Proposta:** mostrar o aviso também onde o administrador já vê hoje: "Visão geral" e "Integrações". Mensagem: "Transmissões: módulo não contratado / canal não configurado / chave do YouTube ausente".

### 4. Comunicados × Serviços mais acessados — CONFIRMADO OK
- Lado a lado, com a mesma largura e a mesma altura (570 × 212 px cada, `recorte-comunicados-servicos-1280.png`).
- Estado vazio com o mesmo estilo nos dois: caixa `#F4F6F8`, texto 14 px. ("Nenhum comunicado em vigor." / "Nenhum serviço publicado na Carta de Serviços ainda.")
- Nada a corrigir.

## B) Páginas internas — um casco único

### 5. Dois estilos de página — CONFIRMADO (com detalhes que diferem do pedido)
Medidas (1280 px). O H1 já está em 36 px, peso 700, -0,02em em todas.

| página | trilha | introdução | "Base legal:" | observação |
|---|---|---|---|---|
| /noticias | não | não | no fim | título "Notícias e avisos" |
| notícia (/conteudo/<id>) | não | não | não tem | |
| /ouvidoria | não | não | no fim | |
| /e-sic | não | não | no fim | |
| /governo | não | não | no fim | |
| /fale-conosco | sim | **não** (o pedido diz que tem) | no fim | |
| /links-uteis | sim | não | não tem | |
| /mapa-do-site | sim | não | não tem | |
| /acessibilidade | sim | sim | **não tem** | |
| /fotos, /privacidade, /transparencia, /servicos, /diario, /painel, /comunicados, /conheca | sim | sim | **no fim** | |
| /legislacao | sim | sim | no topo | já no formato pedido |
| perfil do Conheça | sim | não | no fim | |
| páginas de secretaria | — | — | — | **não existem** (o /governo não lista secretarias) |
| ficha de serviço (/servicos/<slug>) | sim | descrição | no fim | |

- **Proposta:** um bloco-base de página interna com:
  - trilha "Início › (seção-mãe) › Página" (14 px, links sublinhados na cor principal);
  - H1;
  - introdução 18 px `#4B5563` até 70ch;
  - **"Base legal:" 12 px logo abaixo da introdução**;
  - conteúdo em cartões (`#DCE1E6`, raio 14–16);
  - botões no padrão único;
  - "Avalie esta página" no fim.
- **Todas as páginas passam a usá-lo.** Páginas sem base legal hoje recebem a aplicável: Acessibilidade (Lei 13.146/2015, art. 63; eMAG 3.1) e notícia (CF, art. 37, § 1º). Links úteis e Mapa do site não são de transparência e ficam sem.

### 6. /noticias — CONFIRMADO
- O título é "Notícias e avisos".
- A lista mostra **tudo o que está publicado**, sem filtrar a seção. Por isso aparecem:
  - "Edital de concurso público nº [1]/2026" (tipo Documento, seção Transparência, exemplo);
  - "Vacinação contra a gripe…" (tipo Aviso, seção Serviços, exemplo).
- A única notícia de fato é "[Prefeito] entrega a reforma…" (exemplo).
- Os itens são cartões em grade de 3 colunas, sem imagem e sem filtro.
- **Correção:**
  - título "Notícias";
  - lista só com tipo Notícia da seção Notícias;
  - filtro por secretaria (editoria, ver D2);
  - cartões horizontais (imagem 16:9 de 220 px | editoria + data e hora, título 19 px, resumo).
- Os 2 itens que não são notícia: **D1**.

### 7. Página da notícia — CONFIRMADO
- **Hoje:** sem cartão, sem imagem, sem trilha; linha "Notícia · Notícias · 06/11/2026" sem hora; texto corrido; sem "Voltar".
- **No protótipo:** cartão até 820 px, imagem 21:9 no topo, "Publicado em <data, hora> · <editoria>", parágrafos 18 px (70ch), "Voltar para notícias".
- **Diferença:** no protótipo o "Voltar" é um link sublinhado, mas o pedido diz "no padrão de botão". Sigo o pedido (botão secundário), salvo orientação contrária (D4).

### 8. /ouvidoria e /e-sic — CONFIRMADO
- **Hoje:** sem trilha, sem introdução, sem abas em pílula, sem a coluna "Outros canais"; a base legal fica no fim.
- **No protótipo:**
  - um cartão (`flex 999 1 560px`) com o grupo "Tipo de atendimento" em pílulas (44 px, raio 999, `aria-pressed`);
  - caixa informativa `#F5F7F9`;
  - formulário;
  - à direita, o cartão "Outros canais" (`flex 1 1 280px`), com telefone, WhatsApp, presencial e o link "Estatísticas de pedidos e informações classificadas".
- **Correção:**
  - mantenho as duas páginas;
  - as pílulas viram links entre `/ouvidoria` e `/e-sic`, com a da página atual marcada;
  - "Outros canais" com os contatos reais cadastrados em Identidade (telefone, WhatsApp, endereço e horário), sem os textos de exemplo do protótipo.

### 9. /governo — CONFIRMADO
- **Hoje:** só a frase "A estrutura do governo… ainda não foi publicada" e a base legal no fim.
- **No protótipo:** grade de cartões por secretaria (imagem 16:9, nome 19 px, resumo 15 px) e botões Legislação / Organograma / (3º link).
- **Dados:** o sistema não tem cadastro de "resumo" das secretarias. A tabela de secretarias da Carta de Serviços (Fase 10) existe, mas está vazia. Ver **D3**.

## C) Conferência final (itens 10 e 11)
- Feita depois da correção: capturas lado a lado portal × protótipo em `Docs/avaliacao-fase8/conferencia/` e a tabela em `CONFERENCIA.md`.
- O `Main.dc.html` usa componentes (`sc-for`, `dc-import`) que não renderizam no navegador. A coluna "protótipo" será feita reconstruindo os blocos com as medidas e estilos inline do arquivo, como na Fase 8.

## Decisões que preciso de você
- **D1 — itens que não são notícia** (ambos exemplos): mover para Comunicados como exemplo (vacinação → tipo "Aviso"; edital de concurso → tipo "Convocação"), que é o recomendado, ou só tirar de /noticias e deixar como estão?
- **D2 — editoria das notícias** (para o filtro "Secretaria" e a imagem neutra): usar as **secretarias cadastradas na Carta de Serviços** (o administrador cadastra; cada uma ganha um ícone escolhido numa lista e uma cor de uma paleta fixa com contraste AA), que é o recomendado? Enquanto não houver secretaria cadastrada, a editoria é "Prefeitura" (cor principal + ícone genérico).
- **D3 — /governo:** montar os cartões a partir dessas mesmas secretarias, com um campo novo "resumo" (o que a secretaria faz)? O botão "Organograma" apareceria só quando o órgão enviar o organograma (PDF ou imagem) pelo painel; "Legislação" vai para /legislacao.
- **D4 — "Voltar para notícias":** botão secundário (como o pedido diz) ou link sublinhado (como no protótipo)?
- **D5 — Transmissões:** contrato eu o módulo "audiências" da Prefeitura no console? É uma alteração na VPS, então só com sua aprovação. Ou você contrata?
