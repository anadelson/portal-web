-- Fase 4. Banco de CONTROLE. Idempotente.
-- Fontes de dados configuradas por órgão (nada fixo no código: endereço, entidade, IBGE, município no TCESP...)
CREATE TABLE IF NOT EXISTS fontes (
  orgao_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE,
  fonte TEXT NOT NULL CHECK (fonte IN ('fiorilli','pncp','siconfi','tcesp')),
  params JSONB NOT NULL DEFAULT '{}',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (orgao_id, fonte)
);
CREATE INDEX IF NOT EXISTS coletas_fonte_idx ON coletas (orgao_slug, fonte, id DESC);
