-- Banco LOCAL do nó (19/11/2026): fila de TAREFAS (tarefas_no; na gestão a tabela é "tarefas") da gestão para o ativador do nó (root). O id é o mesmo da tarefa na gestão
-- (chega pela ordem "tarefa"); os passos e o resultado voltam pelo relatório do nó.
CREATE TABLE IF NOT EXISTS tarefas_no (
  id INT PRIMARY KEY, tipo TEXT NOT NULL, params JSONB NOT NULL DEFAULT '{}',
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','processando','ok','erro')),
  passos JSONB NOT NULL DEFAULT '[]', mensagem TEXT NOT NULL DEFAULT '', resultado JSONB NOT NULL DEFAULT '{}',
  pedida_em TIMESTAMPTZ NOT NULL DEFAULT now(), concluida_em TIMESTAMPTZ
);
