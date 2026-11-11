-- Banco LOCAL do nó, etapa A3 (11/11/2026): ordens já executadas (nunca executa a mesma ordem duas vezes). Idempotente.
CREATE TABLE IF NOT EXISTS ordens_feitas (
  id BIGINT PRIMARY KEY, tipo TEXT NOT NULL, ok BOOLEAN NOT NULL, resultado TEXT NOT NULL DEFAULT '',
  em TIMESTAMPTZ NOT NULL DEFAULT now(), informada BOOLEAN NOT NULL DEFAULT FALSE
);
