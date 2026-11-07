-- Fase 7 (layout). Banco de cada ÓRGÃO. Idempotente.
-- Série mensal das finanças (coletor diário da Fiorilli, de madrugada) e agrupamento editável das unidades por área.
CREATE TABLE IF NOT EXISTS fin_mensal (
  ano INT NOT NULL,
  mes INT NOT NULL CHECK (mes BETWEEN 1 AND 12),
  receita NUMERIC(16,2),             -- arrecadado no mês, já descontado o FUNDEB (soma das naturezas 1000, 2000 e 9000)
  despesa_paga NUMERIC(16,2),
  despesa_empenhada NUMERIC(16,2),
  parcial BOOLEAN NOT NULL DEFAULT FALSE,   -- mês em andamento
  coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ano, mes)
);
CREATE TABLE IF NOT EXISTS areas_unidades (
  codigo TEXT PRIMARY KEY,           -- código da unidade orçamentária
  unidade TEXT NOT NULL,
  area TEXT NOT NULL,
  origem TEXT NOT NULL DEFAULT 'sugestao' CHECK (origem IN ('sugestao','admin')),   -- sugestão = função de governo predominante nos empenhos
  usuario TEXT NOT NULL DEFAULT '',
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
