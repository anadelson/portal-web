-- Fase 3 (identidade visual). Banco de CADA ÓRGÃO. Idempotente: pode rodar quantas vezes for preciso.
-- Foto de tema do cartão de serviço (saude, educacao, tributos, empresas, cidade, social, atendimento; vazio = sem foto)
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS imagem TEXT NOT NULL DEFAULT '';
-- Vereadores: foto oficial com texto alternativo e crédito; contato do gabinete
ALTER TABLE vereadores ADD COLUMN IF NOT EXISTS foto_alt TEXT NOT NULL DEFAULT '';
ALTER TABLE vereadores ADD COLUMN IF NOT EXISTS foto_credito TEXT NOT NULL DEFAULT '';
ALTER TABLE vereadores ADD COLUMN IF NOT EXISTS contato TEXT NOT NULL DEFAULT '';
-- Mídias enviadas pelo painel (brasão, foto do destaque, fotos do "Conheça"), guardadas em /srv/dados/<órgão>/midia
CREATE TABLE IF NOT EXISTS midias (
  id SERIAL PRIMARY KEY,
  arquivo TEXT UNIQUE NOT NULL,           -- nome gerado pelo sistema (hex + extensão)
  uso TEXT NOT NULL,                      -- brasao | hero | conheca | sede | vereador
  alt TEXT NOT NULL,                      -- texto alternativo (obrigatório)
  credito TEXT NOT NULL DEFAULT '',       -- autoria e licença
  bytes INT NOT NULL,
  enviado_por TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
