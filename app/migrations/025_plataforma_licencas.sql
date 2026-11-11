-- Separação gestão × portais, etapa A1 (11/11/2026): licença assinada por órgão. Banco de CONTROLE. Idempotente.
-- No modo "tudo" (gestão e portais na mesma VPS, como hoje) nada disto muda o que o portal mostra.
CREATE TABLE IF NOT EXISTS licenca_chaves (        -- par Ed25519 da gestão; a privada fica CIFRADA (chave derivada da SECRET_KEY)
  id SERIAL PRIMARY KEY, publica TEXT NOT NULL, privada_cifrada TEXT NOT NULL, impressao TEXT NOT NULL,
  ativa BOOLEAN NOT NULL DEFAULT TRUE, criada_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS nos (                   -- VPS de portais ("nó") que buscam licenças na gestão; o token fica só como hash
  id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL, token_hash TEXT NOT NULL, ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), ultimo_contato TIMESTAMPTZ, ultimo_ip TEXT NOT NULL DEFAULT '', versao TEXT NOT NULL DEFAULT ''
);
ALTER TABLE orgaos ADD COLUMN IF NOT EXISTS no_id INT REFERENCES nos(id);   -- NULL = hospedado nesta VPS (modo "tudo")
CREATE TABLE IF NOT EXISTS licencas_emitidas (     -- lado da gestão: última licença emitida e quando o nó a buscou
  orgao_id INT PRIMARY KEY REFERENCES orgaos(id) ON DELETE CASCADE, serial BIGINT NOT NULL, pacote JSONB NOT NULL,
  emitida_em TIMESTAMPTZ NOT NULL DEFAULT now(), entregue_em TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS licencas_cache (        -- lado do nó: licenças recebidas e conferidas (assinatura) — usadas quando a gestão está longe
  orgao_id INT PRIMARY KEY, slug TEXT NOT NULL, dominio TEXT NOT NULL, serial BIGINT NOT NULL, pacote JSONB NOT NULL,
  valida_ate TIMESTAMPTZ NOT NULL, recebida_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
