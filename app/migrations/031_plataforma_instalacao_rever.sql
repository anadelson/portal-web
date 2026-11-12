-- Instalação de nó pelo console (12/11/2026): rever os comandos enquanto os links valem. Banco de CONTROLE. Idempotente.
-- token_cifrado: o link (cifrado com chave derivada da SECRET_KEY) só até ser baixado, vencer ou ser cancelado; depois fica vazio.
-- lote: os dois links (código e segredos) gerados juntos.
ALTER TABLE instalacao_links ADD COLUMN IF NOT EXISTS token_cifrado TEXT NOT NULL DEFAULT '';
ALTER TABLE instalacao_links ADD COLUMN IF NOT EXISTS lote TEXT NOT NULL DEFAULT '';
ALTER TABLE instalacao_links ADD COLUMN IF NOT EXISTS token_novo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE instalacao_links ADD COLUMN IF NOT EXISTS cancelado_em TIMESTAMPTZ;
