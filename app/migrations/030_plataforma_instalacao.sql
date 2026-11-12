-- Instalação de nó pelo console (12/11/2026): links de download de uso único dos pacotes (código e segredos). Banco de CONTROLE. Idempotente.
-- O pacote de segredos fica no disco só CIFRADO com a senha do pacote (que não é guardada) e é apagado no download ou ao vencer.
CREATE TABLE IF NOT EXISTS instalacao_links (
  id BIGSERIAL PRIMARY KEY, no_id INT NOT NULL REFERENCES nos(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('codigo','segredos')), token_hash TEXT NOT NULL UNIQUE,
  arquivo TEXT NOT NULL DEFAULT '', tamanho BIGINT NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',
  criado_por TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), expira_em TIMESTAMPTZ NOT NULL,
  baixado_em TIMESTAMPTZ, baixado_ip TEXT NOT NULL DEFAULT ''
);
