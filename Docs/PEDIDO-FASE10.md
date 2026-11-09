# Fase 10 — Carta de Serviços ao Usuário (Lei 13.460/2017) com fluxo de validação por secretaria

Objetivo: cada secretaria/departamento cadastra seus serviços no painel; a publicação só acontece depois da autorização do responsável pela secretaria (ou servidor designado); o DTIC organiza e publica. Atende à Lei 13.460/2017 (arts. 7º, 23 e 24) e ao Decreto municipal a ser editado.
REGRAS: as mesmas das fases anteriores (branch fase-10, migrações idempotentes, aprovação antes de alterar a VPS, testes no banco de TESTE, acessibilidade AA, LGPD, PROGRESSO.md). Nada de serviço inventado: o protótipo pode ter exemplos marcados como "exemplo"; o portal real só publica fichas validadas.
Referências de navegação pública: SP156 (sp156.prefeitura.sp.gov.br/portal/servicos) e Carta de Serviços de Ubatuba (ubatuba.sp.gov.br/carta-de-servicos) — use como inspiração de organização (busca, categorias, perfis de público, ficha padronizada), sem copiar textos, marcas ou layout.

ETAPA 0 — Proposta e PARADA: modelo de dados, fluxo, telas (esboço) e a ficha padronizada, para minha aprovação.

1) Ficha padronizada do serviço (formulário único, art. 7º)
- Nome do serviço, descrição em linguagem simples, secretaria/setor responsável, categoria e público (cidadão, empresa, servidor, outros órgãos), palavras-chave/sinônimos para busca.
- Requisitos, documentos e informações necessários; principais etapas; prazo máximo de prestação; forma de prestação (online, presencial, telefone, WhatsApp); locais, horários e formas de acesso; custo e base legal da cobrança (se houver).
- (art. 7º, § 3º) Prioridades de atendimento; previsão de tempo de espera; mecanismos de comunicação com o usuário; procedimentos para receber e responder manifestações; como consultar o andamento (protocolo).
- Link "Solicitar online" (quando existir), legislação relacionada, data da última atualização e próxima revisão.

2) Fluxo (as 6 etapas)
2.1 Inventário: cada secretaria lista todos os seus serviços, inclusive os presenciais (cadastro em rascunho; importação por planilha modelo em Docs/modelos/carta-servicos.csv).
2.2 Padronização: o formulário único obriga os campos do art. 7º (o sistema não deixa enviar para validação com campo obrigatório vazio) e checa linguagem (frases longas, siglas sem explicação: aviso, não bloqueio).
2.3 Validação: o responsável pela secretaria (ou designado, com o ato de designação cadastrado) revisa e AUTORIZA ou devolve com comentário. Perfis: redator da secretaria, responsável/validador, DTIC (publicador), gestor do portal.
2.4 Organização e publicação: o DTIC revisa categorias, sinônimos e publica; publicação sem autorização do responsável é impossível (regra no sistema e no teste).
2.5 Regulamentação: gerar em Docs/ uma MINUTA de decreto municipal (para análise jurídica) com responsabilidades, periodicidade de atualização (ex.: revisão a cada 12 meses), fluxo de validação e prazos.
2.6 Monitoramento: painel com serviços por situação (rascunho, em validação, publicado, a revisar), alerta de ficha vencida (passou da data de revisão) ao redator e ao responsável, avaliação dos usuários por serviço (art. 23–24) e manifestações da Ouvidoria vinculadas ao serviço.

3) Portal público "Carta de Serviços"
- Busca por texto com sinônimos, filtros por categoria, público e secretaria; "mais acessados"; lista A–Z.
- Página de cada serviço com a ficha completa em seções (O que é, Quem pode pedir, Documentos, Etapas, Prazo, Custo, Onde e quando, Como acompanhar, Prioridades, Manifestações), botão "Solicitar online" quando houver, data de atualização e "Avalie este serviço".
- Exportação da Carta inteira em PDF e em dados abertos (CSV/JSON), com data.
- Integração com a barra "Serviços" do cabeçalho e o bloco "Serviços mais acessados".

4) Testes e implantação
- Testes (banco de TESTE): fluxo rascunho → validação → devolução → nova validação → publicação; publicação bloqueada sem autorização; alerta de revisão vencida; busca por sinônimo; avaliação por serviço; exportações.
- Implantação com aprovação, merge + tag fase-10, PROGRESSO.md e README (manual curto para as secretarias).
