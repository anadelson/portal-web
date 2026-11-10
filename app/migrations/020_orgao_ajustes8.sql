-- Ajustes da Fase 8 (portal × protótipo). Idempotente.
-- editoria da notícia = secretaria cadastrada (Carta de Serviços); sem secretaria, a editoria é o próprio órgão
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS secretaria_id INT REFERENCES secretarias(id) ON DELETE SET NULL;
-- cartões do /governo: o que a secretaria faz e o ícone da imagem neutra
ALTER TABLE secretarias ADD COLUMN IF NOT EXISTS resumo TEXT NOT NULL DEFAULT '';
ALTER TABLE secretarias ADD COLUMN IF NOT EXISTS icone TEXT NOT NULL DEFAULT 'predio';
