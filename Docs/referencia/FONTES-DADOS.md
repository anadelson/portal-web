# Fontes de dados (endereços reais testados em 05/11/2026)

Gerado a partir do protótipo do painel (aba Integrações). Placeholders: {ano}, {mes}, {dia}, {n}, {inicio}, {fim}, {tipo}.

## Sistema contábil da Prefeitura (Fiorilli)
- Órgão: Prefeitura · portal de dados abertos
- Tipo: API JSON · Frequência sugerida: A cada hora, das 7h às 19h
- Alimenta: Receitas, Despesas, Licitações, Contratos, Pessoal, Diárias, Emendas, Repasses, Restos a pagar, Ordem cronológica, Painel
- LGPD: Não grava CPF. Servidores: nome social quando houver, sem descontos pessoais. Pessoas físicas ficam fora das listas de restos a pagar e ordem cronológica.
- Observação: Fonte principal de finanças por ser atualizada em tempo real. A receita de 2025 volta zerada nesta API; o portal usa o TCESP para 2025. Documentação oficial: https://borasp.dcfiorilli.com.br:879/transparencia/versaoJson/DadosAbertos/
  - **Receita orçamentária**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Receitas/?Listagem=ReceitaOrcamentaria&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo={dia}&MesFinalPeriodo={mes}&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Receitas · Painel (receita mês a mês, origens)
  - **Despesa por unidade orçamentária**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Despesas/?Listagem=DespesasPorUnidade&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo={dia}&MesFinalPeriodo={mes}&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Despesas · Painel (para onde vai o dinheiro, saúde, educação, social)
  - **Empenhos (despesas gerais)**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Despesas/?Listagem=DespesasGerais&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo={dia}&MesFinalPeriodo={mes}&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&MostrarFornecedor=True&MostrarCNPJFornecedor=False&ConectarExercicio={ano}` → Despesas (lista de empenhos)
  - **Diárias**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Despesas/?Listagem=Diarias&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo={dia}&MesFinalPeriodo={mes}&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Base Diárias
  - **Restos a pagar**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Despesas/?Listagem=DespesasRestosPagar&DiaInicioPeriodo=01&MesInicialPeriodo=01&DiaFinalPeriodo={dia}&MesFinalPeriodo={mes}&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ApresentaNomeFavorecido=True&ConectarExercicio={ano}` → Base Restos a pagar
  - **Ordem cronológica de pagamentos**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Despesas/?Listagem=DespesasporExigibilidade&DiaInicioPeriodo={inicio}&DiaFinalPeriodo={fim}&strTipoLista={tipo}&Empresa=2&ConectarExercicio={ano}` → Base Ordem cronológica (Lei 14.133, art. 141)
  - **Licitações**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/LicitacoesEContratos/?Listagem=Licitacoes&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Licitações em andamento
  - **Contratos**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/LicitacoesEContratos/?Listagem=Contratos&Ano={ano}&Empresa=2&MostraDadosConsolidado=False&ContratosApenasPublicados=True&ConectarExercicio={ano}` → Base Contratos
  - **Transferências recebidas**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Transferencias/?Listagem=Transf&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Base Repasses
  - **Emendas impositivas**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Transferencias/?Listagem=EmendasImpositivasArt166A&Empresa=2&MostraDadosConsolidado=False&ConectarExercicio={ano}` → Base Emendas
  - **Servidores**: `https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/Pessoal/?Listagem=Servidores&Empresa=2&Ano={ano}&MesFinalPeriodo={mes}&ConectarExercicio={ano}` → Base Pessoal

## PNCP — Portal Nacional de Contratações Públicas
- Órgão: Governo federal (Ministério da Gestão)
- Tipo: API JSON · Frequência sugerida: A cada 6 horas
- Alimenta: Licitações · Painel (contratações por modalidade)
- LGPD: Só dados do órgão e do processo. Nenhum dado pessoal.
- Observação: O filtro por CNPJ do órgão (orgaos=) não retorna resultados; o filtro por município IBGE retorna. Para ver só as abertas, troque status=todos por status=recebendo_proposta.
  - **Busca de contratações do município**: `https://pncp.gov.br/api/search/?tipos_documento=edital&municipios=3507209&status=todos&ordenacao=-data&pagina={n}&tam_pagina=50` → Licitações · Painel

## TCESP — Transparência Municipal (Audesp)
- Órgão: Tribunal de Contas do Estado de São Paulo
- Tipo: API JSON · Frequência sugerida: Mensal, dia 20
- Alimenta: Receitas (série de 2025, só para comparação)
- LGPD: Dados contábeis agregados.
- Observação: Usada só para 2025, porque a API da Prefeitura retorna zero nesse ano. O TCESP atualiza com atraso de um a dois meses, por isso não é fonte do ano corrente.
  - **Receitas por mês**: `https://transparencia.tce.sp.gov.br/api/json/receitas/bora/{ano}/{mes}` → Receitas 2025
  - **Despesas por mês**: `https://transparencia.tce.sp.gov.br/api/json/despesas/bora/{ano}/{mes}` → Reserva (conferência)

## TCESP — IEG-M (nota da gestão municipal)
- Órgão: Tribunal de Contas do Estado de São Paulo
- Tipo: Consulta do painel (Pentaho CDA) · Frequência sugerida: Anual, ao sair o resultado
- Alimenta: Painel · Município e gestão
- LGPD: Dado institucional, sem pessoas.
- Observação: É a consulta interna que alimenta o painel público do TCESP, sem documentação oficial: pode mudar sem aviso. Filtrar codigo_municipio = 3507209. Recomenda-se pedir ao TCESP um arquivo aberto oficial.
  - **Notas de todos os municípios por ano-base**: `https://painel.tce.sp.gov.br/pentaho/plugin/cda/api/doQuery?path=/public/ieg_m/iegm.cda&dataAccessId=faixaTodosMunicipiosPeriodo&outputType=json&parampExercicio_mapa={ano-base}&parampRegiao=-1` → Painel · IEG-M

## Siconfi — Relatório Resumido da Execução Orçamentária
- Órgão: Tesouro Nacional
- Tipo: API JSON · Frequência sugerida: Bimestral
- Alimenta: Painel · mínimos de saúde, educação e FUNDEB
- LGPD: Dados contábeis agregados.
- Observação: Os Anexos 8 e 12 não constam para Borá; os percentuais vêm do Anexo 14 (demonstrativo simplificado), declarado pela própria Prefeitura.
  - **RREO Anexo 14**: `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo?an_exercicio={ano}&nr_periodo=6&co_tipo_demonstrativo=RREO&no_anexo=RREO-Anexo%2014&id_ente=3507209` → Painel · Saúde e Educação

## CNES — Estabelecimentos de saúde
- Órgão: Ministério da Saúde
- Tipo: API JSON · Frequência sugerida: Mensal
- Alimenta: Painel · Saúde (onde a população é atendida)
- LGPD: Só estabelecimentos. A lista de profissionais da mesma API traz nomes e não é usada.
- Observação: Usa o código IBGE de 6 dígitos (350720). A consulta de profissionais (/assistencia-a-saude/cnes-profissionais) foi descartada: retorna um registro por competência recente e nomes de pessoas.
  - **Estabelecimentos do município**: `https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?codigo_municipio=350720` → Painel · Saúde

## IBGE SIDRA — Registro Civil e Cadastro de Empresas
- Órgão: IBGE
- Tipo: API JSON · Frequência sugerida: Anual
- Alimenta: Painel · Saúde (nascimentos e óbitos)
- LGPD: Contagens de pessoas abaixo de 5 aparecem como "menos de 5".
- Observação: Enviar o cabeçalho Accept: application/json para receber JSON em vez de XML. Tabela 6449 (empresas e pessoal ocupado) vai só até 2021.
  - **Nascidos vivos (tabela 2612)**: `https://apisidra.ibge.gov.br/values/t/2612/n6/3507209/v/all/p/last%206` → Nascimentos
  - **Óbitos (tabela 2654)**: `https://apisidra.ibge.gov.br/values/t/2654/n6/3507209/v/all/p/last%206` → Óbitos
  - **Empresas e pessoal ocupado (tabela 6449)**: `https://apisidra.ibge.gov.br/values/t/6449/n6/3507209/v/all/p/last%205/c12762/117897` → Reserva (série histórica)

## IBGE Cidades — panorama do município
- Órgão: IBGE
- Tipo: Leitura de página · Frequência sugerida: Anual
- Alimenta: Painel · O município (PIB, emprego formal, saneamento, escolarização)
- LGPD: Indicadores agregados.
- Observação: O protótipo leu a página pública. No portal definitivo, trocar pela API de dados do IBGE, que entrega os mesmos indicadores em JSON.
  - **Panorama de Borá**: `https://cidades.ibge.gov.br/brasil/sp/bora/panorama` → Painel · Município
  - **Dados do município (localidades)**: `https://servicodados.ibge.gov.br/api/v1/localidades/municipios/3507209` → Cabeçalho e mapas

## INEP — IDEB e Saeb (consulta via QEdu)
- Órgão: INEP / Fundação Lemann (QEdu)
- Tipo: Leitura de página · Frequência sugerida: A cada dois anos
- Alimenta: Painel · Educação (IDEB e Saeb)
- LGPD: Resultados por rede de ensino; nenhum dado de aluno.
- Observação: A fonte oficial são as planilhas de resultados do INEP, publicadas a cada edição. O protótipo usou a página do QEdu, que reproduz esses dados.
  - **IDEB de Borá**: `https://qedu.org.br/municipio/3507209-bora/ideb` → Painel · Educação

## MDS — MI Social (Cadastro Único, Bolsa Família, BPC)
- Órgão: Ministério do Desenvolvimento e Assistência Social
- Tipo: API JSON (Solr) · Frequência sugerida: Mensal
- Alimenta: Painel · Assistência social (quando voltar)
- LGPD: Só totais do município; contagens abaixo de 5 suprimidas.
- Observação: Fora do ar: manutenção de segurança após alerta de 21/10/2026 (aviso em gov.br/mds/pt-br/avisos). Os nomes dos campos serão confirmados quando o serviço voltar.
  - **Série mensal do município**: `https://aplicacoes.mds.gov.br/sagi/servicos/misocial/?q=*:*&fq=codigo_ibge:350720&fl=codigo_ibge,anomes_s,qtd_familias_beneficiarias_bolsa_familia_s,valor_repassado_bolsa_familia_s&sort=anomes_s%20desc&rows=12&wt=json` → Painel · Assistência social

## Vacinação — doses aplicadas (PNI)
- Órgão: Ministério da Saúde
- Tipo: API JSON · Frequência sugerida: —
- Alimenta: Painel · cobertura vacinal (pendente)
- LGPD: Microdados de vacinação: só seriam usados totais por vacina.
- Observação: A API só aceita limit e offset, sem filtro por município: seria preciso ler a base nacional inteira. Solução: rotina de carga noturna a partir dos arquivos mensais.
  - **Doses aplicadas 2026**: `https://apidadosabertos.saude.gov.br/vacinacao/doses-aplicadas-pni-2026?limit={n}&offset={n}` → —

## YouTube — detecção de transmissão ao vivo
- Órgão: Google (YouTube Data API v3)
- Tipo: API JSON com chave · Frequência sugerida: A cada 2 minutos em horário de sessão
- Alimenta: Barra "ao vivo", aviso diário e página Transmissões
- LGPD: Só dados públicos do canal oficial.
- Observação: Exige chave de API guardada no servidor, nunca na página. Cada busca consome 100 unidades da cota diária de 10.000: consultar só em horário de sessão ou audiência agendada.
  - **Transmissão ao vivo do canal**: `https://www.googleapis.com/youtube/v3/search?part=snippet&channelId={canal oficial}&eventType=live&type=video&key={chave no servidor}` → Transmissões

## e-SIC e Ouvidoria do próprio portal
- Órgão: Prefeitura (módulo interno)
- Tipo: Banco de dados do portal · Frequência sugerida: Tempo real
- Alimenta: Painel · pedidos respondidos no prazo
- LGPD: O painel mostra só prazos e quantidades; nunca o nome de quem pediu.
- Observação: Começa a gerar números quando o portal entrar em operação. Prazo da LAI: 20 dias, prorrogáveis por mais 10 (Lei 12.527/2011, art. 11).


## Notas de campo (descobertas nos testes de 05/11/2026)
- **Emendas impositivas (rastreio por vereador)**: o caminho que funcionou foi pelos empenhos.
  - `Despesas/?Listagem=DespesasGerais` exige também `UFParaFiltroCOVID` e `ApenasIDEmpenho` para responder; o campo `VINCODIGONOME` traz "Emenda Ver. <nome>" e `FONGRUPO` = 08 (emendas parlamentares individuais).
  - Detalhe de um empenho: `Listagem=DetalhesEmpenhoPorNumeroEmpenho`.
  - Liquidações e pagamentos de um empenho: `Listagem=EmpenhosDespesas_Liquidado_PorNumeroEmpenho` e `Listagem=EmpenhosDespesas_Pago_PorNumeroEmpenho` — exigem os parâmetros de período e `IDButton=lnkDespesasPor_NotaEmpenho`.
  - Cadastro de emendas: `Listagem=CadEmendasImpositivas` (validar o caminho base). O valor "pago" do cadastro divergiu do pago nos empenhos em 2 emendas (12/2026 e 13/2026): sempre mostrar as duas fontes.
- **Receita de 2025** volta zerada no Fiorilli: usar TCESP para 2025.
- **PNCP**: filtrar por município IBGE 3507209 (o filtro por CNPJ não retorna). A Câmara não tem publicações no PNCP.
- **Câmara**: portal atual com reCAPTCHA — não fazer raspagem; pedir exportação ao fornecedor (Pronim/Cidade360). Área de dados abertos do Cidade360 vazia.
- **LGPD**: nunca gravar CPF; credor pessoa física aparece sem documento; MEI com CPF no nome (ex.: "NOME 09630942895") → remover os dígitos do nome antes de gravar.
- **Siconfi**: `https://apidatalake.tesouro.gov.br/ords/siconfi/tt/extrato_entregas?id_ente=3507209&an_referencia={ano}`; RGF Anexo 01 do Legislativo: `.../tt/rgf?an_exercicio={ano}&in_periodicidade=Q&nr_periodo={n}&co_tipo_demonstrativo=RGF&no_anexo=RGF-Anexo%2001&co_esfera=M&co_poder=L&id_ente=3507209`.
