-- Banco LOCAL do nó (15/11/2026): fonte "tempo" (previsão do tempo, Open-Meteo). Idempotente.
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','govbr','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm','financas','youtube','redes','tempo','financas_prefeitura'));
