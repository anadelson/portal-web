-- Gestão comanda o nó (19/11/2026): TAREFAS que o ativador do nó (root) executa — exportar/importar/limpar um órgão e
-- instalar uma instância nova na mesma VPS — e MUDANÇAS de órgão entre nós, conduzidas passo a passo pela gestão.
CREATE TABLE IF NOT EXISTS tarefas (
  id SERIAL PRIMARY KEY, no_id INT NOT NULL REFERENCES nos(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('exportar','importar','limpar','instalar_instancia')),
  params JSONB NOT NULL DEFAULT '{}', mudanca_id INT,
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','processando','ok','erro')),
  passos JSONB NOT NULL DEFAULT '[]', mensagem TEXT NOT NULL DEFAULT '', resultado JSONB NOT NULL DEFAULT '{}',
  pedido_por TEXT NOT NULL DEFAULT '', criada_em TIMESTAMPTZ NOT NULL DEFAULT now(), concluida_em TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS tarefas_no_idx ON tarefas (no_id, id DESC);
CREATE TABLE IF NOT EXISTS mudancas (
  id SERIAL PRIMARY KEY, orgao_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE,
  de_no INT REFERENCES nos(id), para_no INT REFERENCES nos(id),
  situacao TEXT NOT NULL DEFAULT 'retirando'
    CHECK (situacao IN ('retirando','exportando','importando','hospedagem','publicando','concluida','limpando','finalizada',
                        'desfazendo','desfeita','erro','cancelada')),
  publicar BOOLEAN NOT NULL DEFAULT TRUE,    -- o domínio estava no ar: publica de novo no destino
  arquivo TEXT NOT NULL DEFAULT '', historico JSONB NOT NULL DEFAULT '[]', mensagem TEXT NOT NULL DEFAULT '',
  pedido_por TEXT NOT NULL DEFAULT '', criada_em TIMESTAMPTZ NOT NULL DEFAULT now(), atualizada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  etapa_desde TIMESTAMPTZ NOT NULL DEFAULT now()   -- quando a etapa atual começou (pedidos de domínio desta etapa são os feitos depois disto)
);
CREATE INDEX IF NOT EXISTS mudancas_orgao_idx ON mudancas (orgao_id, id DESC);
