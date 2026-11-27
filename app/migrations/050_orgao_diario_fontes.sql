-- Diário Oficial em plataforma de terceiros (27/11/2026). Banco de CADA ÓRGÃO. Idempotente.
-- Cada plataforma é uma fonte com um adaptador (app/diario_fontes). O portal lê só daqui: lista as edições e o link
-- abre a edição na própria plataforma (o PDF fica lá). A fonte nunca é apagada, só desativada, e o histórico continua.
CREATE TABLE IF NOT EXISTS diario_fontes (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,                              -- chave do adaptador (ex.: dosp)
  nome TEXT NOT NULL,                              -- como aparece em "Fonte oficial:"
  config JSONB NOT NULL DEFAULT '{}',              -- do adaptador (ex.: slug e código do município na DOSP); sem segredos
  ativa BOOLEAN NOT NULL DEFAULT TRUE,
  nova_aba BOOLEAN NOT NULL DEFAULT FALSE,         -- o link da edição abre em nova aba
  intervalo_min INT NOT NULL DEFAULT 60 CHECK (intervalo_min BETWEEN 15 AND 1440),
  ultima_sincronizacao_em TIMESTAMPTZ,
  ultimo_erro TEXT NOT NULL DEFAULT '',
  falhas_seguidas INT NOT NULL DEFAULT 0,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS diario_externo_edicoes (
  id SERIAL PRIMARY KEY,
  fonte_id INT NOT NULL REFERENCES diario_fontes(id) ON DELETE RESTRICT,
  id_externo TEXT NOT NULL,
  numero TEXT NOT NULL DEFAULT '',
  data DATE NOT NULL,
  extra BOOLEAN NOT NULL DEFAULT FALSE,
  url TEXT NOT NULL,                               -- endereço da edição na plataforma
  paginas INT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (fonte_id, id_externo)
);
CREATE INDEX IF NOT EXISTS diario_externo_edicoes_data_idx ON diario_externo_edicoes (data DESC, id DESC);
CREATE TABLE IF NOT EXISTS diario_sincronizacoes (
  id SERIAL PRIMARY KEY,
  fonte_id INT NOT NULL REFERENCES diario_fontes(id) ON DELETE RESTRICT,
  iniciado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  finalizado_em TIMESTAMPTZ,
  novas INT NOT NULL DEFAULT 0,
  atualizadas INT NOT NULL DEFAULT 0,
  erros INT NOT NULL DEFAULT 0,
  mensagem TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS diario_sincronizacoes_fonte_idx ON diario_sincronizacoes (fonte_id, id DESC);
