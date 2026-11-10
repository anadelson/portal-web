-- Etapa 2 do modelo multi-órgão: ativação de domínio pelo console. Banco de CONTROLE. Idempotente.
-- O console só grava o PEDIDO; quem emite o certificado, gera o vhost e recarrega o nginx é o ativador da VPS (deploy/ativador.sh).
ALTER TABLE orgaos ADD COLUMN IF NOT EXISTS vhost_ativo BOOLEAN NOT NULL DEFAULT FALSE;  -- bloco no portal-orgaos.conf gerado pelo ativador
CREATE TABLE IF NOT EXISTS ativacoes (
  id SERIAL PRIMARY KEY,
  orgao_id INT REFERENCES orgaos(id) ON DELETE CASCADE,
  dominio TEXT NOT NULL,
  acao TEXT NOT NULL CHECK (acao IN ('ativar','desativar')),
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','processando','no_ar','desativado','erro')),
  passos JSONB NOT NULL DEFAULT '[]',
  mensagem TEXT NOT NULL DEFAULT '',
  pedido_por TEXT NOT NULL, pedido_em TIMESTAMPTZ NOT NULL DEFAULT now(), concluido_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ativacoes_pend_idx ON ativacoes (situacao, id);
