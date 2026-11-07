# Fase 7 — Ajuste do layout do /painel ao protótipo

O /painel implantado está diferente do protótipo. A referência é Docs/referencia/prototipos/Main.dc.html, trecho que começa em `<sc-if value="{{isPainel}}"` (o template usa sc-if/sc-for com estilos inline; a lógica que monta os dados fica no script do mesmo arquivo: procure pTabs, pKpis, pMes, pAreas, pOrigens, pExec). Também vale Docs/referencia/ESPEC-VISUAL.md.
REGRAS: as mesmas da Fase 7 (branch fase-7-layout, commits pequenos, aprovação antes de alterar a VPS, nunca mostrar .env, nada inventado: onde o protótipo tem número de exemplo, usar o dado real coletado ou esconder o bloco).

ETAPA 1 — Avaliação (só leitura) e PARADA
1. Tire capturas da página ao vivo https://pmbora.conectatech.tech/painel com Playwright em 1280 px e em 390 px (celular), página inteira, aba "Tudo" e cada aba. Salve em Docs/avaliacao-painel/ e não mostre dados sensíveis (não há).
2. Leia a estrutura do protótipo e monte uma tabela comparando, bloco a bloco: bloco do protótipo | existe no portal? | diferenças (ordem, título, tipo de gráfico, cores, tamanhos, espaçamento, textos, fonte/data, tabela acessível, downloads) | gravidade (alta/média/baixa) | correção proposta.
3. Blocos do protótipo, na ordem:
   - Cabeçalho: abas em "pílula" (Tudo, Dinheiro público, Contratações, Saúde, Educação, Assistência social, Município e gestão; botões com aria-pressed, altura mínima 44 px, borda arredondada 999 px) à esquerda e, à direita, o selo com ponto verde pulsando "Finanças lidas do sistema contábil em <data/hora>".
   - Dinheiro público: fileira de cartões KPI (grade auto-fill mínimo 220 px; borda superior colorida de 4 px; rótulo 14 px, número 28 px negrito com algarismos tabulares, linha de detalhe 13 px); depois grade de 2 colunas (mínimo 520 px) com 4 seções em cartão branco, borda #DCE1E6, raio 16 px, padding 24 px: "Receita e despesa paga, mês a mês" (barras agrupadas, cor primária x laranja #E8A33D, legenda, frase-resumo, "Ver em tabela" em details, fonte); "Para onde vai o dinheiro" (barras horizontais por área com % e valor em milhões); "De onde vem o dinheiro" (barra única dividida Repasses x arrecadação própria + lista "Maiores origens"); "Execução do orçamento de 2026" (barras de progresso com linha tracejada do ritmo do ano).
   - Contratações publicadas no PNCP.
   - Cada tema (Saúde, Educação, Assistência social) com título 24 px, cartões KPI e cartões internos: "Mínimo exigido por lei" (Siconfi), "IDEB: qualidade do ensino, anos iniciais" (gráfico + notas Saeb), "Onde a população é atendida" (CNES), "Nascimentos e óbitos" (gráfico), "Orçamento da área em 2026", "Benefícios e cadastro social".
   - Município e gestão: "Nota da gestão municipal pelo Tribunal de Contas" (IEG-M, com "Como os municípios paulistas ficaram" + tabela em details) e "O município" (lista de números do IBGE).
   - "Ainda não disponíveis": lista do que falta, sem números.
   - Em todo bloco: linha "Fonte: ..." 12 px cinza #4B5563 com data da consulta; gráfico com role="img" e aria-label descritivo + tabela equivalente.
4. Confira também: fonte, cores e tokens iguais ao resto do portal (cor primária da identidade), contraste AA, sem rolagem horizontal da página em 390 px (gráficos largos rolam dentro do próprio cartão), foco visível nas abas, aba escolhida mantida na URL (?tema=saude).
5. Me mostre a tabela e as capturas e PARE até eu aprovar as correções.

ETAPA 2 — Correção
6. Ajuste templates/CSS para ficar fiel ao protótipo, reaproveitando os componentes do portal (sem CDN externo; gráficos em SVG/HTML gerados no servidor, como já definido).
7. Novas capturas nas mesmas larguras, lado a lado com as anteriores, em Docs/avaliacao-painel/depois/.
8. Testes (banco de TESTE), implantação com aprovação, merge e registro em PROGRESSO.md.
