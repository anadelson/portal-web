# Fase 4 — Transparência com dados reais (coletores + telas próprias + dados abertos)

Cole no Claude Code (troque USUARIO e IP_DA_VPS). Faça depois da Fase 3, ou em paralelo num branch separado.

---
Contexto: piloto dos Portais de Borá em /opt/portal_web na VPS USUARIO@IP_DA_VPS (domínios pmbora/cmbora/gestao.conectatech.tech). Leia: /opt/portal_web/Docs/CLAUDE.md, /opt/portal_web/CLAUDE.md, README.md, Docs/PROGRESSO.md e principalmente Docs/referencia/FONTES-DADOS.md (endereços reais da API Fiorilli, PNCP, Siconfi, TCESP, IBGE, com parâmetros e notas de campo). Se a pasta referencia não estiver na VPS, proponha copiá-la do meu PC (C:\Users\BORA\Documents\portais-bora\referencia) com scp -r.

REGRAS
- Mesmo código para todos os órgãos; cada órgão tem suas fontes configuradas (tabela/config de fontes por órgão), nada fixo para Borá no código além de valores padrão de configuração.
- Dados financeiros da Prefeitura ficam no banco da Prefeitura (bd_pm_bora); da Câmara no dela. A Câmara lê dados da Prefeitura só pela API pública (ex.: execução das emendas).
- LGPD: nunca gravar CPF; remover dígitos de CPF que venham no nome de credor/MEI; pessoa física sem documento; servidores sem dados pessoais além do exigido (nome, cargo, lotação, remuneração).
- Git: branch fase-4, commits pequenos. Migrações idempotentes (app/migrations/003_...sql) aplicadas por "python -m app.provision atualizar".
- Antes de cada comando que altere a VPS, mostre e espere minha aprovação. Nunca mostre senhas nem o .env.
- Respeitar as fontes: no máximo 1 requisição por segundo por fonte, timeout, novas tentativas com espera; registrar cada coleta na tabela coletas (já existe) com quantidade e mensagem.
- Registre o andamento em Docs/PROGRESSO.md.

ESCOPO
1. Fase de descoberta (só leitura, sem gravar): de dentro do container app, chame cada endpoint de FONTES-DADOS.md para o ano corrente, salve 1 amostra de cada resposta em /srv/dados/amostras/ e me mostre um quadro: endpoint · status HTTP · nº de registros · campos principais. Confirme com isso a listagem correta de emendas (CadEmendasImpositivas vs EmendasImpositivasArt166A vs DespesasGerais com VINCODIGONOME) e os campos de empenho/liquidação/pagamento. Pare e espere minha aprovação do mapeamento antes de criar tabelas.
2. Modelo de dados (migração 003): tabelas no banco do órgão para receitas, despesas (empenhos com liquidado e pago), licitações, contratos, servidores/remuneração (sem CPF), diárias, transferências recebidas, ordem cronológica de pagamentos, e relatórios fiscais (RREO/RGF do Siconfi). Cada linha com fonte, data de coleta e chave natural para atualização (upsert).
3. Coletores (app/coletores/): Fiorilli (todas as listagens do FONTES-DADOS.md), PNCP (licitações do município), Siconfi (RREO/RGF e extrato de entregas), TCESP (receitas de 2025, porque o Fiorilli devolve 2025 zerado). Agendamento no worker conforme a frequência sugerida. Emendas: atualizar a tabela emendas da Câmara com empenho, liquidado e pago por emenda, mantendo o "pago no cadastro" separado e marcando divergência.
4. Telas no portal (Prefeitura e Câmara, conforme o tipo e os módulos):
   - /transparencia como central com cartões por base e a data da última atualização de cada uma;
   - uma página por base com filtros (ano, mês, unidade/órgão, fornecedor/credor, texto), tabela paginada, totais, "Fonte: ... · atualizado em ..." e "Base legal:" em fonte pequena (LRF arts. 48 e 48-A; LAI art. 8º; Lei 14.133 arts. 94, 141 e 174 conforme a base);
   - botões "Baixar CSV" e "Baixar JSON" com os mesmos filtros (dados abertos) e rota de API /dados/<base>.json documentada numa página /dados-abertos.
5. "Borá em números" (bloco da página inicial da Prefeitura, criado na Fase 3): receita arrecadada no ano, despesa empenhada e paga, aplicação em saúde e educação (RREO), atualizados pelos coletores; o bloco só aparece se houver dados.
6. Console: na tela de coletas, situação por fonte (última execução, OK/falha, registros) e destaque das falhas.
7. Testes: banco de TESTE separado com as amostras salvas no passo 1 (sem acessar a internet), testando parse, upsert, filtros, exportação CSV/JSON e remoção de CPF.
8. Implantação (com aprovação): build, up -d, provision atualizar, rodar "python -m app.worker uma-vez", conferir 3 registros de cada base contra o portal oficial da fonte e anotar o resultado em PROGRESSO.md.
9. Me mostre o resumo: bases no ar, quantidades, conferências feitas, falhas de fonte e pendências.

CRITÉRIOS DE ACEITE
- Receitas, despesas, contratos, licitações, pessoal, diárias, repasses e ordem cronológica do ano corrente aparecem com filtros e exportação CSV/JSON.
- Cada página mostra fonte, data de atualização e base legal.
- Nenhum CPF gravado ou exibido.
- Emendas da Câmara mostram empenho, liquidado e pago vindos da Prefeitura, com divergências sinalizadas.
- Falha de uma fonte não derruba o portal: a página mostra a última coleta válida e a data.
---
