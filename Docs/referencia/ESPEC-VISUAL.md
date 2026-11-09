# Especificação visual (aprovada nos protótipos do canvas)

Os arquivos em `prototipos/` (`Main.dc.html` = Prefeitura, `Camara.dc.html` = Câmara, `Backend.dc.html` = painel único, `Console.dc.html` = console) são a referência **visual e de comportamento**. Eles usam um formato de template próprio do canvas (`{{ }}`, `<sc-if>`, `<sc-for>`): leia como especificação, **não copie o formato** — reproduza em Jinja2 + CSS no app.
Imagens reais em `imagens/` (brasão e fotos enviadas pela Prefeitura; serviços = fotos CC0).

## Tokens
- Fonte: **Public Sans** (Google Fonts) 400/500/600/700/800; fallback system-ui.
- Texto `#17212B`; texto secundário `#4B5563`; bordas `#DCE1E6`; fundo `#F5F7F9`/`#F4F7F9`.
- Prefeitura: primária `#0E4D64` (alternativa `#1D4E89`); destaque amarelo `#F0B429`; sucesso `#146C43`; alerta `#7A4A00` sobre `#FCEFD9`; erro `#9B1C1C` sobre `#FBE4D8`.
- Câmara: primária `#2F5233`, escuro `#1F3A22`, destaque `#F7C948`.
- Raio de cartões 14–22px; sombras leves só no hover; foco visível em **anel duplo**: contorno amarelo `#F0B429` de 3px (afastado 2px) + anel externo escuro `#17212B` e anel interno branco (`box-shadow: 0 0 0 2px #fff, 0 0 0 7px #17212B`), no portal, no painel administrativo e no console — o amarelo sozinho sobre fundo branco tem contraste ≈1,9:1, abaixo do 3:1 da WCAG 1.4.11 (atualizado em 07/11/2026, Fase 7).
- Contraste AA em tudo; nada depende só de cor.

## Prefeitura (Main.dc.html)
1. **Barra utilitária** escura: Transmissões, Transparência, e-SIC, Ouvidoria, Diário Oficial, Licitações, Dados abertos, Área restrita (servidores) e, à direita, "Câmara Municipal" (link para o portal da Câmara). Ferramentas de acessibilidade (contraste, fonte, atalhos).
2. **Cabeçalho**: brasão (`imagens/brasao.png`) + "Prefeitura Municipal de Borá"; menu principal; busca.
3. **Hero** com `vista-aerea.jpg` em largura total, título e busca.
4. **Acesso direto**: cartões sobrepostos à base do hero (Serviços, Transparência, Diário, Fale com a Prefeitura).
5. **Serviços mais procurados**: cartões com foto do tema no canto inferior direito, com máscara em degradê radial (100% visível no canto inferior direito → 0% no canto superior esquerdo): `mask-image: radial-gradient(ellipse 100% 100% at 100% 100%, #000 0%, rgba(0,0,0,.6) 45%, rgba(0,0,0,0) 100%)`; imagem em 66% × 84% do cartão, ancorada embaixo à direita. Fotos: `serv-*.jpg`.
6. **Borá em números** (painel resumido) e **Notícias**.
7. **Conheça Borá**: mosaico com `praca-aerea.jpg`, `igreja-matriz.jpg`, `usina.jpg`, `vista-aerea.jpg`; texto "segundo menor município do Brasil em população".
8. **Paço Municipal**: cartão com `paco-municipal.jpg`, endereço e horário.
9. **Transmissão ao vivo**: faixa vermelha "● Ao vivo" + bloco com player quando houver transmissão.
10. **Rodapé em 4 faixas**: (a) brasão + nome + botões "Radar da Transparência Pública" e "Avalie este portal"; (b) colunas Atendimento (ícones de endereço, horário, telefone, WhatsApp), Acesso à informação, Institucional (com cartão "Câmara Municipal de Borá →"), Privacidade e acessibilidade; (c) redes sociais em pílulas + "Voltar ao topo"; (d) © + CNPJ + data de revisão + créditos das fotos.
- Toda página de transparência: "Base legal:" em fonte pequena sob a introdução.

## Câmara (Camara.dc.html)
1. **Faixa ao vivo** quando houver sessão no ar; aviso (modal) uma vez por dia.
2. **Hero** com a foto do prédio (`paco-municipal.jpg`) + cartão "Próxima sessão".
3. **Acesso direto** (Sessões e votações, Projetos, Gastos da Câmara, Fale com a Câmara).
4. **Vereadores da 15ª Legislatura**: grade; **presidente ocupa 2 colunas × 2 linhas** (cartão escuro, selo "Presidente da Câmara" em linha única, nome com `text-wrap: balance`); demais cartões verticais com retrato 4:3 e chip do partido. Sem foto oficial → iniciais (não usar fotos de banco como se fossem os vereadores). Card da **Mesa Diretora** em largura total com os dois biênios.
5. **Linha 55% / 45%**: "Prestação de contas — Quanto custa a Câmara" (KPIs + barra de despesa com pessoal vs limite 6% e linha de alerta 5,4%) ao lado do destaque **Emendas impositivas** (KPIs, barra de execução, botão "+ detalhes das emendas").
6. **Últimas sessões** e **Projetos em tramitação**.
7. Páginas: perfil do vereador (KPIs, emendas com execução, indicações, requerimentos/moções, presença, mandatos), galeria de legislaturas (abas 15ª/14ª/13ª/acervo), emendas com "caminho na Prefeitura" (órgão, programa, ação, natureza, fonte, contratação, credor, empenhos com anulações/liquidações/pagamentos e aviso de divergência), transmissões (player, capítulos, agenda, gravações).
8. Rodapé verde no mesmo padrão de 4 faixas.

## Painel (Backend.dc.html) e console (Console.dc.html)
- Menu lateral com **ícones** por função e grupos recolhíveis; badges de pendência; cartão do usuário no rodapé do menu.
- Ícones: traço 24×24 (caminhos SVG estão em `const ICON` no Backend.dc.html).

## Fase 8 (protótipo Main.dc.html de 09/11/2026)
- **Cabeçalho em 3 faixas.**
  - Barra de acessibilidade: atalhos [1–4], Câmara/Prefeitura, Área restrita | A− A A+, contraste, sublinhar, Libras, Acessibilidade.
  - Barra institucional na cor primária.
  - Barra do brasão com os itens do portal e a busca.
  - **Cada destino aparece em uma só barra.** Itens vêm de Painel → Menus e atalhos.
- **Barra do portal cheia (6+ itens):** a busca vira o botão "Buscar" e o campo abre por cima ao receber foco (Alt+3 também abre).
- **Celular (≤ 760 px):** botão "Menu" abre um painel com as seções "Portal" e "Transparência e governo". Foco preso; Esc fecha e devolve o foco.
- **Componente de botão `.btn`:** pílula (raio 999), mínimo 44 px, primário (cheio) ou secundário (`.btn.sec`, contorno) e seta à direita. Todo "ver mais / todas as…" usa esse componente; não usar link solto.
- **Cartão de indicador `.icard`**, em grade `.ics` de cartões com a mesma altura:
  - Linha 1: título curto (até 32 caracteres, reticências) + botão ⓘ (`.ic-info`, 28 px).
  - Linha 2: valor + unidade (28 px, números tabulares).
  - Linha 3: contexto (13 px).
  - Fonte, período, atualização, método e base legal ficam no balão do ⓘ; no celular, o balão vira painel inferior.
  - **Não usar** as classes `.ic` (é do ícone SVG) e `.info` (é dos cartões de vereador).
- **Notícias:** destaque 16:9 com ponto focal + data "dd/mm/aaaa, HHhMM" + resumo; 3 secundárias; lista de 5 títulos; botão "Todas as notícias".
- **Comunicados | Serviços mais acessados:** lado a lado no computador, empilhados no celular. O comunicado tem etiqueta de tipo e nunca é "notícia".
- **Conheça:** grade de perfis com foto de capa; página do perfil com galeria (ampliação em `<dialog>`) e vídeos youtube-nocookie.
