-- Etapa 4 do modelo multi-órgão (11/11/2026): coletor do portal TransparênciaBR da GOVBR (Pronim TB). Banco de CONTROLE. Idempotente.
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','govbr','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm','financas','youtube','redes'));
