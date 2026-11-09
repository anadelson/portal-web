-- Fase 8. Banco de CONTROLE. Idempotente. Fonte 'youtube' (detecção de transmissão ao vivo e gravações do canal).
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm','financas','youtube'));
