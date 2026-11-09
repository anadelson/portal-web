# Fase 10 — Carta de Serviços ao Usuário (Lei 13.460/2017) — ETAPA 0: proposta e PARADA

Capturas "antes" em `antes/` (portal real, só leitura). Esboço das telas em `esboco/index.html` (capturas `t1`…`t6`). Exemplos no esboço são marcados "exemplo".

## Situação hoje (diagnóstico)
- **Serviços sem ficha:** os "serviços" são conteúdos genéricos (seção "Serviços"), sem os campos do art. 7º. No portal real há 2, ambos marcados como exemplo; um deles é do tipo "Aviso", que pela Fase 8 virou comunicado.
- **`/servicos`:** não mostra "Base legal:" e a busca não encontra nada (ex.: "iptu" = 0 resultados, porque o exemplo de IPTU é rascunho).
- **Validação:** não há secretaria como entidade nem fluxo de validação; os perfis atuais são administrador, editor, publicador, procuradoria e remetente do Diário.
- **Carta da Câmara:** o módulo "Carta de Serviços" existe no catálogo só para o Executivo.

## 1) Modelo de dados (banco de cada órgão; migração idempotente)
- **`secretarias`:** nome, sigla, responsável (usuário) e unidades orçamentárias ligadas, opcional, para relatórios.
- **`designacoes_carta`:** um servidor designado para validar no lugar do responsável. Campos: secretaria, usuário, ato (tipo, número, data), PDF do ato opcional, vigência; inativa ao expirar.
- **`servicos`:** a ficha.
  - **Identificação:** slug, nome, descrição simples, secretaria, setor, categoria, públicos (cidadão / empresa / servidor / outros órgãos), sinônimos.
  - **Como pedir:** requisitos, documentos, etapas (lista ordenada), prazo máximo, formas de prestação (online / presencial / telefone / WhatsApp), locais e horários, custo e base legal da cobrança.
  - **Art. 7º, § 3º:** prioridades, tempo de espera previsto, comunicação com o usuário, manifestações, como acompanhar o protocolo.
  - **Complementos:** link "Solicitar online", legislação relacionada, datas de atualização e de próxima revisão.
  - **Controle:** situação, campo "exemplo".
- **`servico_versoes`:** cópia completa da ficha a cada mudança de situação (quem, quando, comentário). Mostra o que mudou entre a versão autorizada e a publicada.
- **`servico_avaliacoes`:** nota 1–5 + "conseguiu o que precisava?" + comentário moderado. Usa o mesmo cookie e o mesmo limite por hash de IP da Fase 9 (art. 23–24).
- **Ouvidoria:** a manifestação ganha o campo opcional "serviço", para o painel de monitoramento.
- **Perfis novos:** `redator` (só a própria secretaria) e `validador` (responsável ou designado, só a própria secretaria). O DTIC usa o perfil **publicador**; o gestor do portal, **administrador**.

## 2) Fluxo (máquina de situações — regra no servidor e no teste)
`rascunho` → (redator: Enviar para validação; **bloqueado** se faltar campo obrigatório do art. 7º) → `em_validacao`
→ validador: **Autorizar** (registra quem, quando, ato de designação se não for o responsável e a versão autorizada) → `autorizado`
→ validador: **Devolver** com comentário obrigatório → `devolvido` → (redator corrige) → `em_validacao`
`autorizado` → DTIC: Publicar (pode ajustar só **categoria, sinônimos e ordem**; mudança de conteúdo devolve para validação) → `publicado`
`publicado` → passou da data de revisão → `a_revisar` (continua no ar com o aviso "em revisão"; alerta ao redator e ao validador)
- **Publicar sem a autorização vigente da versão atual é impossível.** O servidor confere `autorizado_por` + o resumo (hash) do conteúdo autorizado.
- **Linguagem:** avisos não bloqueiam. Exemplos: frase com mais de 30 palavras, sigla sem explicação, termos como "outrossim" e "mediante".
- **Inventário:** importação de planilha (`Docs/modelos/carta-servicos.csv`). Cada linha vira rascunho da secretaria indicada, com simulação antes, como na importação da Fase 5.

## 3) Telas
- **Painel → Carta de Serviços:**
  - abas "Minhas fichas / Em validação / Autorizadas / Publicadas / A revisar";
  - ficha em seções com contador de campos obrigatórios;
  - botões por perfil.
- **Painel → Monitoramento:** totais por situação e por secretaria; fichas vencidas; nota média e "conseguiu?" por serviço; manifestações da Ouvidoria por serviço.
- **Painel → Secretarias:** responsável, designações e atos.
- **Portal `/servicos`:**
  - busca com sinônimos;
  - filtros por categoria, público e secretaria;
  - "mais acessados" e lista A–Z;
  - "Base legal: Lei 13.460/2017, art. 7º".
- **Portal `/servicos/<slug>`:** ficha em seções, botão "Solicitar online", data de atualização e "Avalie este serviço".
- **Exportações:** Carta inteira em PDF (reportlab, com sumário e data), CSV e JSON (dados abertos, com data e base legal).
- **Integrações:** item "Serviços" do cabeçalho → `/servicos`; o bloco "Serviços mais acessados" passa a usar as fichas publicadas.

## 4) Ficha padronizada — campos obrigatórios para enviar à validação
Nome · Descrição simples · Secretaria · Categoria · Público (≥1) · Requisitos · Documentos · Etapas (≥1) · Prazo máximo · Forma(s) de prestação · Locais e horários · Custo (ou "gratuito") · Base legal da cobrança (se houver custo) · Prioridades · Tempo de espera previsto · Comunicação com o usuário · Como fazer manifestação · Como acompanhar.
Opcionais: sinônimos, link "Solicitar online", legislação relacionada, setor.

## 5) Documentos que serão gerados
- `Docs/modelos/carta-servicos.csv` (cabeçalho) + instruções em `Docs/modelos/README.md`.
- `Docs/MINUTA-DECRETO-CARTA-SERVICOS.md`: minuta para análise jurídica. Conteúdo: responsabilidades (secretarias, validador, DTIC, Ouvidoria), revisão a cada 12 meses, prazos do fluxo (ex.: validação em 10 dias úteis), designação por ato e avaliação continuada (art. 23–24).
- README: manual curto para as secretarias.

## Decisões que preciso de você
1. **Lista de secretarias e responsáveis:** o orçamento tem 22 unidades em 10 órgãos (Gabinete, Administração, Compras, Obras/Serviços, Educação, Esporte, Saúde, Assistência, Meio Ambiente, TIC), mas sem o nome oficial das secretarias. Você me passa a lista oficial (nome e sigla), ou cadastro só a estrutura vazia e o administrador preenche pelo painel?
2. **Avaliação por serviço:** nota de 1 a 5 + "conseguiu o que precisava?" (recomendo, porque atende à pesquisa de satisfação do art. 23), ou só "útil? sim/não" como nas demais páginas?
3. **Câmara:** ligar a Carta de Serviços também para a Câmara (a Lei 13.460 vale para os três Poderes; ex.: certidões, Tribuna Livre, protocolo), ou só a Prefeitura nesta fase?
4. **Conteúdos antigos de "Serviços"** (2 exemplos): retirar da lista `/servicos` (continuam em `/conteudo/<id>`), recomendado, ou converter em fichas-exemplo?
5. **Prazo de revisão padrão:** 12 meses (recomendado) ou outro?
