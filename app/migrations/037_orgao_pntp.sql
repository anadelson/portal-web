-- Autoavaliação PNTP da matriz inteira (18/11/2026): marcações do controle interno, critério a critério, por ciclo.
-- itens: {"disponibilidade": true, "atualidade": false, ...} (só os itens que se aplicam ao critério); link: evidência (obrigatória quando atende).
CREATE TABLE IF NOT EXISTS pntp_marcacoes (
  ciclo INT NOT NULL,
  criterio TEXT NOT NULL,
  itens JSONB NOT NULL DEFAULT '{}',
  link TEXT NOT NULL DEFAULT '',
  obs TEXT NOT NULL DEFAULT '',
  por TEXT NOT NULL,
  em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ciclo, criterio)
);
