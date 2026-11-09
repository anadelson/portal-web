# Fase 9 — proposta (09/11/2026) — PARADA para aprovação

Capturas "antes" em `antes/`. O painel foi fotografado em ambiente de TESTE (banco e usuários de teste); não entrei com contas reais. O esboço está em `esboco/index.html`, com capturas `t1`…`t6`. A versão de 390 px do esboço ainda tem rolagem horizontal, que será corrigida na implementação.

## 2.1 Diagnóstico do "Avalie esta página"
- **A avaliação é gravada.** O nginx registra 1 envio real (08/11, 21h29 UTC, página inicial), com resposta 303 e linha no banco.
- **Causa do "não foi possível":** o servidor redireciona para `pagina#avaliar` (o rodapé), mas o "Obrigado pela avaliação!" é escrito no topo do `<main>`. Na reprodução, a tela ficou rolada em 1263 px e a mensagem em 218 px, fora de vista. Ver `antes/avaliar-2-depois-do-clique-tela-visivel.png`.
- **Correção:** mostrar a resposta dentro do próprio formulário (sem recarregar, com JS); cookie de 30 dias configurável; limite de 5 por hora por hash de IP com sal diário; registro na página de privacidade.

## Proposta por item
1. **Mapa do layout:** cartão fixo (sticky) com destaque nos dois sentidos, bloco desligado tracejado, atualização antes de salvar e botão no celular.
2. **Avaliação:** abas "Por página", "Por mês", "Comentários" (moderação) e "Regras".
3. **Consultas:** um mecanismo único para todas as integrações.
   - O coletor roda em **modo ensaio**: registra cada requisição (método, URL, parâmetros, HTTP, tempo, registros, trecho da resposta com CPF mascarado) e não grava nada.
   - Parâmetros editáveis = `fontes.params`, com esquema, validação, histórico e auditoria.
   - Os caminhos dos endpoints ficam fixos no código e são exibidos com o GET completo, inclusive os 11 do Fiorilli.
   - Lançamento manual em todo indicador.
4. **Identidade em 6 abas:**
   - cores com contraste AA calculado e cor ruim recusada;
   - favicon em 16, 32, 180 e 512 px;
   - dados do IBGE reaproveitando a fonte `ibge` semanal;
   - álbuns com licença e categoria "suspender no defeso".
5. **Editor:** próprio sobre `contenteditable`, com limpeza no servidor por lista fechada de tags; imagens no corpo com alt obrigatório; versões com comparar e restaurar.
6. **Login:** tela com brasão, título e fundo configuráveis (camada de contraste). Senha e segundo fator em duas etapas, mensagem genérica, limite de tentativas e auditoria: isso já existe e continua.

## Decisões que preciso de você
1. **Editor:** incluir o pacote Python `nh3` na imagem (limpeza de HTML confiável) ou limpeza própria, sem dependência nova? Recomendo `nh3`.
2. **"Esqueci minha senha":** não há envio de e-mail (SMTP) no sistema. Você contrata ou indica um SMTP, ou, por ora, o link orienta a pedir a redefinição ao administrador do órgão?
3. **Redes sociais "sincronizar":** Instagram e Facebook exigem app e token da Meta, o X é pago e os embeds trazem rastreadores (LGPD). Proponho: links com ícone para todas; últimas publicações só do YouTube (chave já prevista) e da Meta, quando houver token no console.
4. **Fotos e álbuns × Conheça (Fase 8):** a biblioteca de álbuns vira a fonte única de fotos e os perfis do Conheça passam a escolher fotos dela, ou ficam separados?
5. **Painel do órgão no celular:** as tabelas de Comunicados e Conheça (Fase 8) passam da largura em 390 px. Corrijo nesta fase?

## Decisões do usuário (09/11/2026)
- Esboço aprovado.
- Editor: pacote `nh3` na imagem.
- "Esqueci minha senha": por ora orienta a pedir a redefinição ao administrador do órgão (no console, ao gestor); e-mail quando houver SMTP.
- Redes sociais: links com ícone para todas; últimas publicações só do YouTube e da Meta, com credencial no console; feed suspenso no defeso.
- Fotos e álbuns: **separados** do Conheça (o Conheça mantém fotos próprias).
- Item 5 (tabelas do painel no celular): corrigido nesta fase.
