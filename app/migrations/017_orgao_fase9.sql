-- Fase 9 (idempotente)
-- Avaliação do portal: hash do IP (sal diário, nunca o IP puro) para o limite por hora; moderação dos comentários
ALTER TABLE avaliacoes ADD COLUMN IF NOT EXISTS ip_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE avaliacoes ADD COLUMN IF NOT EXISTS moderacao TEXT NOT NULL DEFAULT 'pendente';
CREATE INDEX IF NOT EXISTS avaliacoes_ip_idx ON avaliacoes (ip_hash, criado_em);
-- Fotos e álbuns (separados do Conheça): licença, categoria que pode ser suspensa no período eleitoral, autorização de imagem
CREATE TABLE IF NOT EXISTS foto_categorias (
  id SERIAL PRIMARY KEY, nome TEXT NOT NULL UNIQUE, suspender_defeso BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS albuns (
  id SERIAL PRIMARY KEY, titulo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', categoria_id INT REFERENCES foto_categorias(id) ON DELETE SET NULL,
  publicado BOOLEAN NOT NULL DEFAULT FALSE, ordem INT NOT NULL DEFAULT 100, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS album_fotos (
  id SERIAL PRIMARY KEY, album_id INT NOT NULL REFERENCES albuns(id) ON DELETE CASCADE, url TEXT NOT NULL,
  titulo TEXT NOT NULL DEFAULT '', descricao TEXT NOT NULL DEFAULT '', credito TEXT NOT NULL DEFAULT '', licenca TEXT NOT NULL DEFAULT '',
  alt TEXT NOT NULL CHECK (length(alt) >= 5), categoria_id INT REFERENCES foto_categorias(id) ON DELETE SET NULL,
  tem_pessoas BOOLEAN NOT NULL DEFAULT FALSE, autorizacao_imagem BOOLEAN NOT NULL DEFAULT FALSE,
  principal BOOLEAN NOT NULL DEFAULT FALSE, ordem INT NOT NULL DEFAULT 100, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Conteúdo: corpo em HTML limpo (editor) e versões com o texto completo para comparar/restaurar
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS html TEXT NOT NULL DEFAULT '';
ALTER TABLE conteudo_versoes ADD COLUMN IF NOT EXISTS dados JSONB;
ALTER TABLE comunicados ADD COLUMN IF NOT EXISTS html TEXT NOT NULL DEFAULT '';
ALTER TABLE perfis ADD COLUMN IF NOT EXISTS html TEXT NOT NULL DEFAULT '';
