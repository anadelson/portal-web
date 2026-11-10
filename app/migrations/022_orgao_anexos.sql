-- Arquivos anexos dos comunicados (editais, avisos, convites…). Banco de cada ÓRGÃO. Idempotente.
CREATE TABLE IF NOT EXISTS comunicado_anexos (
  id SERIAL PRIMARY KEY,
  comunicado_id INT NOT NULL REFERENCES comunicados(id) ON DELETE CASCADE,
  arquivo TEXT UNIQUE NOT NULL,                 -- <32 hex>.<ext> em DADOS_DIR/<órgão>/anexos
  nome_original TEXT NOT NULL DEFAULT '',
  titulo TEXT NOT NULL,                         -- o que é o arquivo: texto do link e texto alternativo (obrigatório)
  ext TEXT NOT NULL CHECK (ext IN ('pdf','png','jpg','webp','docx','xlsx','odt','ods','csv')),
  bytes INT NOT NULL, ordem INT NOT NULL DEFAULT 100,
  enviado_por TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS comunicado_anexos_com_idx ON comunicado_anexos (comunicado_id);
