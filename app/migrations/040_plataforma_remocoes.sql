-- Exclusão pela gestão (19/11/2026): órgão (com backup final no nó) e nó (backup final e desinstalação).
-- REMOCOES é o registro que fica depois que o órgão/nó some do cadastro: o quê, quando, quem e onde está o backup.
ALTER TABLE tarefas DROP CONSTRAINT IF EXISTS tarefas_tipo_check;
ALTER TABLE tarefas ADD CONSTRAINT tarefas_tipo_check CHECK (tipo IN ('exportar','importar','limpar','instalar_instancia','excluir_orgao','desinstalar_no'));
ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS remocao_id INT;
CREATE TABLE IF NOT EXISTS remocoes (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (tipo IN ('orgao','no')),
  orgao_id INT, no_id INT,                       -- sem chave estrangeira: o registro fica depois que o órgão/nó some
  nome TEXT NOT NULL, detalhes JSONB NOT NULL DEFAULT '{}', no_nome TEXT NOT NULL DEFAULT '', vps_ip TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'backup' CHECK (situacao IN ('retirando','backup','concluida','erro','cancelada')),
  pasta TEXT NOT NULL DEFAULT '', backup JSONB NOT NULL DEFAULT '{}',
  historico JSONB NOT NULL DEFAULT '[]', mensagem TEXT NOT NULL DEFAULT '',
  pedido_por TEXT NOT NULL DEFAULT '', criada_em TIMESTAMPTZ NOT NULL DEFAULT now(), atualizada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  etapa_desde TIMESTAMPTZ NOT NULL DEFAULT now(), concluida_em TIMESTAMPTZ,
  backup_apagado_em TIMESTAMPTZ, backup_apagado_por TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS remocoes_idx ON remocoes (id DESC);
