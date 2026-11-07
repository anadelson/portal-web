-- Fase 6. Banco de CONTROLE. Idempotente.
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS totp_segredo TEXT NOT NULL DEFAULT '';
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS totp_ativo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS recuperacao JSONB NOT NULL DEFAULT '[]';
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS cpf_hash TEXT;
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS cpf_final TEXT;
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS falhas INT NOT NULL DEFAULT 0;
ALTER TABLE gestores ADD COLUMN IF NOT EXISTS bloqueado_ate TIMESTAMPTZ;
-- Tentativas de login por origem (IP mascarado + conta), para o bloqueio temporário
CREATE TABLE IF NOT EXISTS login_tentativas (
  id BIGSERIAL PRIMARY KEY, quando TIMESTAMPTZ NOT NULL DEFAULT now(), chave TEXT NOT NULL, ok BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS login_tentativas_idx ON login_tentativas (chave, quando DESC);
-- API interna entre órgãos (ex.: Câmara → Diário da Prefeitura): um token por par, com registro de cada chamada
CREATE TABLE IF NOT EXISTS pares_orgaos (
  origem_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE, destino_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE,
  token TEXT NOT NULL, ativo BOOLEAN NOT NULL DEFAULT TRUE, criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (origem_id, destino_id)
);
CREATE TABLE IF NOT EXISTS remessas_log (
  id BIGSERIAL PRIMARY KEY, quando TIMESTAMPTZ NOT NULL DEFAULT now(), origem TEXT NOT NULL, destino TEXT NOT NULL,
  acao TEXT NOT NULL, ok BOOLEAN NOT NULL, detalhe TEXT NOT NULL DEFAULT ''
);
