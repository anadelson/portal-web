-- Câmeras ao vivo: posição geográfica opcional (26/11/2026), para a página /cameras-ao-vivo mostrar as câmeras sobre o mapa.
-- Banco de cada ÓRGÃO. Idempotente. Latitude e longitude em graus decimais (WGS 84), as duas juntas ou nenhuma.
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS lat NUMERIC(9,6);
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS lon NUMERIC(9,6);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cameras_posicao_ok') THEN
    ALTER TABLE cameras ADD CONSTRAINT cameras_posicao_ok CHECK (
      (lat IS NULL AND lon IS NULL) OR (lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180));
  END IF;
END $$;
