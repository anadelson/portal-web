-- Fase 7. Banco de CONTROLE. Idempotente.
-- Novas fontes de coleta do painel de indicadores (módulo "bi").
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
-- (lista completa, igual à da 011: as migrações são reaplicadas em ordem a cada atualização e não podem estreitar a regra)
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm'));

-- Indicadores de fontes públicas nacionais (IBGE, INEP via IBGE, CNES, MDS, Siconfi) gravados por código IBGE,
-- para servir a qualquer município da plataforma. Só números agregados; nunca dados de pessoas.
CREATE TABLE IF NOT EXISTS indicadores_publicos (
  ibge TEXT NOT NULL,
  indicador TEXT NOT NULL,          -- chave do catálogo (ex.: mun_populacao)
  periodo TEXT NOT NULL,            -- rótulo do período de referência (ex.: 2024, 3º bim. 2026, nov/2026)
  data_ref DATE NOT NULL,           -- fim do período de referência (ordena a série)
  valor NUMERIC,
  texto TEXT NOT NULL DEFAULT '',   -- valor categórico (ex.: faixa do IEG-M)
  detalhe JSONB,                    -- composição agregada (ex.: estabelecimentos por tipo)
  nota TEXT NOT NULL DEFAULT '',
  parcial BOOLEAN NOT NULL DEFAULT FALSE,
  fonte TEXT NOT NULL,
  coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ibge, indicador, periodo)
);
