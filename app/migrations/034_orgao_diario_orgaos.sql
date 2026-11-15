-- 15/11/2026: órgãos que publicam no Diário (lista cadastrada, sem digitação livre) e texto formatado do ato
CREATE TABLE IF NOT EXISTS diario_orgaos (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL UNIQUE,
  sigla TEXT NOT NULL DEFAULT '',
  caderno TEXT NOT NULL DEFAULT 'executivo' CHECK (caderno IN ('executivo', 'legislativo')),
  padrao BOOLEAN NOT NULL DEFAULT FALSE,      -- já vem escolhido no envio (quando o usuário ainda não enviou nenhum ato)
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS orgao_id INT REFERENCES diario_orgaos(id) ON DELETE SET NULL;
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS html TEXT NOT NULL DEFAULT '';   -- texto formatado (limpo no servidor); vazio = texto simples
