-- Fase 7 (layout). Banco de CONTROLE. Idempotente.
-- Fonte 'financas': série mensal do sistema contábil (Fiorilli) para os blocos de finanças do painel.
ALTER TABLE fontes DROP CONSTRAINT IF EXISTS fontes_fonte_check;
ALTER TABLE fontes ADD CONSTRAINT fontes_fonte_check CHECK (fonte IN ('fiorilli','pncp','siconfi','tcesp','ibge','cnes','mds','pni','painel','inep','iegm','financas','youtube','redes'));
