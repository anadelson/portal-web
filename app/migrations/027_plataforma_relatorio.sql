-- Separação gestão × portais, etapa A4 (11/11/2026): relatório técnico do nó (saúde, coletas, disco, ativações). Banco de CONTROLE. Idempotente.
-- Sem dados pessoais: só versão, IP público do nó, espaço em disco, situação das coletas e das licenças, e os passos das ativações de domínio.
ALTER TABLE nos ADD COLUMN IF NOT EXISTS relatorio JSONB NOT NULL DEFAULT '{}';
ALTER TABLE nos ADD COLUMN IF NOT EXISTS relatorio_em TIMESTAMPTZ;
