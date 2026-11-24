-- Pauta simplificada e PDFs vinculados aos itens da pauta (24/11/2026). Banco de cada ÓRGÃO. Idempotente.
-- A "fase da votação" saiu do cadastro: itens novos ficam com fase vazia (os antigos continuam como estão).
ALTER TABLE pauta_itens ALTER COLUMN fase SET DEFAULT '';
-- PDF (texto da matéria, parecer, emenda…) ligado a um item da pauta; sem o item, o PDF continua só na sessão
ALTER TABLE documentos ADD COLUMN IF NOT EXISTS pauta_item_id INT REFERENCES pauta_itens(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS documentos_pauta_item ON documentos (pauta_item_id);
