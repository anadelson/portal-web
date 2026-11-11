-- Banco LOCAL do nó, etapa A4 (11/11/2026): fila do ativador do nó e domínios publicados no nginx do nó. Idempotente.
-- O id da ativação é o mesmo do pedido feito no console da gestão (chega pela ordem "dominio"); os passos voltam pelo relatório do nó.
CREATE TABLE IF NOT EXISTS ativacoes (
  id INT PRIMARY KEY, orgao_id INT, dominio TEXT NOT NULL,
  acao TEXT NOT NULL CHECK (acao IN ('ativar','desativar')),
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','processando','no_ar','desativado','erro')),
  passos JSONB NOT NULL DEFAULT '[]', mensagem TEXT NOT NULL DEFAULT '',
  pedido_por TEXT NOT NULL DEFAULT '', pedido_em TIMESTAMPTZ NOT NULL DEFAULT now(), concluido_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ativacoes_pend_idx ON ativacoes (situacao, id);
CREATE TABLE IF NOT EXISTS dominios_publicados (dominio TEXT PRIMARY KEY, orgao_id INT NOT NULL, desde TIMESTAMPTZ NOT NULL DEFAULT now());
