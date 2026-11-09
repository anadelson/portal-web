-- Fase 9: consultas montadas, testes e histórico de parâmetros (idempotente)
CREATE TABLE IF NOT EXISTS consulta_amostras (   -- última resposta de cada consulta (trecho curto, CPF mascarado, sem segredo na URL)
  chave TEXT PRIMARY KEY, orgao_slug TEXT NOT NULL DEFAULT '', fonte TEXT NOT NULL, url TEXT NOT NULL, status INT NOT NULL DEFAULT 0,
  ms INT NOT NULL DEFAULT 0, registros INT NOT NULL DEFAULT 0, trecho TEXT NOT NULL DEFAULT '', erro TEXT NOT NULL DEFAULT '', em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS consulta_testes (      -- "Testar consulta": executa sem gravar; libera "Salvar e coletar agora" para os mesmos parâmetros
  id BIGSERIAL PRIMARY KEY, orgao_id INT NOT NULL, fonte TEXT NOT NULL, params_hash TEXT NOT NULL, ok BOOLEAN NOT NULL,
  relatorio JSONB NOT NULL DEFAULT '{}', quem TEXT NOT NULL, em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS consulta_testes_idx ON consulta_testes (orgao_id, fonte, em DESC);
CREATE TABLE IF NOT EXISTS fontes_historico (      -- mudança de endereço/parâmetro: confirmada, registrada e auditada
  id BIGSERIAL PRIMARY KEY, orgao_id INT NOT NULL, fonte TEXT NOT NULL, antes JSONB NOT NULL, depois JSONB NOT NULL,
  quem TEXT NOT NULL, em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Configurações do console (ex.: imagem de fundo da tela de login do gestor)
CREATE TABLE IF NOT EXISTS config_console (chave TEXT PRIMARY KEY, valor JSONB NOT NULL);
