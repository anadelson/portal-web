-- Fase 7 (fontes). Banco de CONTROLE. Idempotente.
-- Planilhas oficiais do INEP (IDEB e Saeb por município) e IEG-M do TCESP.
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','govbr','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm','financas','youtube','redes','tempo'));
