# Ajustes da Fase 8 — conferência final (10/11/2026)

Capturas lado a lado, portal × protótipo, em 1280 e 390 px: `Docs/avaliacao-fase8/conferencia/index.html`. As capturas "antes" estão em `conferencia/antes/`.
O portal foi capturado em ambiente de TESTE, com notícias e secretarias marcadas "exemplo". Decisões aplicadas: D1 a D5 de `CONFERENCIA-ANTES.md`.
Verificações: axe sem violações em 12 páginas; nenhuma rolagem horizontal em 390 px; 11 suítes de teste (incluindo `tests/teste_ajustes8.py`) com ERROS: 0 / tudo ok.

| item | estava | ficou | ok? |
|---|---|---|---|
| 1. Notícias + Paço | Notícias na largura toda, só texto; Paço embaixo, também na largura toda | Uma fileira: Notícias (`flex 2 1 520px`) e Paço (`flex 1 1 300px`, foto 220 px em cima, dois botões de contorno), que empilham no celular. Dentro de Notícias: destaque em duas colunas (16:9 \| editoria + data e hora, título 20 px, resumo), 3 menores (16:9, data e hora, título 15 px), lista de títulos e "Todas as notícias" no fim. Sem foto: imagem neutra da editoria (cor da secretaria + ícone), nunca foto de banco | ok |
| 2. Conheça Borá | Texto na largura toda; 3 fotos em fileira abaixo | Cartão branco em duas colunas: brasão + "CONHEÇA BORÁ", título 30 px, texto, números em caixinhas, fonte, "Conheça mais" (primário) e "Borá em números" (secundário); à direita, mosaico (1ª foto em duas linhas, as outras empilhadas) com legenda e "Ver perfil" | ok |
| 3. Transmissões | Não aparecia, sem aviso | Causa confirmada: o módulo "audiências" não está contratado na Prefeitura, não há canal e não há chave do YouTube. Agora a Visão geral e Integrações listam o que falta. **Contratar o módulo fica com o usuário (D5)** | ok (configuração pendente) |
| 4. Comunicados × Serviços | Lado a lado, mesma altura, vazio no mesmo estilo | Sem mudança, já estava certo. Agora aparecem os 2 comunicados-exemplo vindos de D1 | ok |
| 5. Casco único | Páginas antigas sem trilha nem introdução; "Base legal" no fim (só a /legislacao no topo); /acessibilidade e a notícia sem base legal | Todas as páginas internas com trilha "Início › (seção-mãe) › Página" (links sublinhados na cor principal), H1 36 px/700/-0,02em, introdução 18 px até 70ch, "Base legal:" 12 px logo abaixo da introdução, conteúdo em cartões, botões no padrão e "Avalie esta página" no fim. Introdução acrescentada em Fale conosco, Links úteis, Mapa do site e Verificar edição. Base legal acrescentada em Acessibilidade (LBI art. 63, eMAG) e na notícia (CF art. 37 § 1º) | ok |
| 6. /noticias | "Notícias e avisos", com comunicados misturados e cartões em grade | "Notícias", só itens do tipo Notícia; filtro por secretaria (editoria); cartões horizontais (16:9 \| editoria + data e hora, título 19 px, resumo). D1: vacinação → comunicado "Aviso" e edital de concurso → comunicado "Convocação", ambos exemplos; os conteúdos de origem foram arquivados | ok |
| 7. Página da notícia | Sem cartão, imagem, hora nem "Voltar" | Cartão até 820 px, imagem 21:9 (foto ou imagem neutra), "Publicado em <data, hora> · <editoria>", texto 18 px e botão secundário "Voltar para notícias" (D4) | ok |
| 8. /ouvidoria e /e-sic | Sem trilha, introdução, pílulas nem "Outros canais" | Casco padrão + pílulas "Ouvidoria \| Acesso à informação" (links entre as duas páginas, com a atual marcada), caixa informativa, formulário e coluna "Outros canais" com os contatos **reais** da Identidade (sem os textos de exemplo do protótipo) e a consulta de protocolo | ok |
| 9. /governo | Só a frase "ainda não foi publicada" | Cartões das secretarias cadastradas na Carta (imagem neutra 16:9, nome 19 px, sigla, resumo — campo novo — e link para os serviços); botões Legislação, Carta de Serviços e Organograma (este só aparece quando o arquivo é enviado pelo painel, D3) | ok |
| 10. Capturas lado a lado | — | `conferencia/index.html`: 10 páginas × 2 larguras | ok |
| 11. Esta tabela, implantação e PROGRESSO | — | Tabela feita; implantação aguardando aprovação | aguardando deploy |

**Diferenças conscientes em relação ao protótipo**
- "Voltar para notícias" é botão secundário, não link sublinhado (D4).
- Os botões de /governo seguem o padrão único (raio 999), não o raio 10 do protótipo.
- A coluna "Outros canais" mostra contatos reais, sem os campos de exemplo `[telefone]`.
- O Conheça mostra os números do IBGE mais os manuais (até 6 caixinhas), em vez de 4 fixos.

**Para depois do deploy (fora do código)**
- Cadastrar as secretarias (resumo e ícone) em Carta de Serviços → Secretarias e responsáveis. Elas alimentam as editorias, o /governo e a imagem neutra.
- Enviar o organograma na mesma tela.
- D5: contratar o módulo "audiências" no console, informar o canal e cadastrar a chave do YouTube.
