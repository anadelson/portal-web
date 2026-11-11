-- Separação gestão × portais, etapa A3 (11/11/2026): ordens da gestão para quem hospeda o órgão. Banco de CONTROLE. Idempotente.
-- no_id NULL = executada na hora, nesta VPS (papel "tudo"). Lista fechada de tipos (app/ordens.py); o nó só executa ordem assinada.
CREATE TABLE IF NOT EXISTS ordens (
  id BIGSERIAL PRIMARY KEY, no_id INT REFERENCES nos(id), orgao_id INT REFERENCES orgaos(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}', resumo TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','feita','erro')),
  criada_por TEXT NOT NULL DEFAULT '', criada_em TIMESTAMPTZ NOT NULL DEFAULT now(), feita_em TIMESTAMPTZ, resultado TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ordens_no_idx ON ordens (no_id, situacao, id);
