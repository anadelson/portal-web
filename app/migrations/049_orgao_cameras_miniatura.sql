-- Câmeras ao vivo (26/11/2026): miniatura (foto fixa de fundo do cartão), tirada do RTSP no cadastro ou enviada pelo admin
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS miniatura TEXT NOT NULL DEFAULT '';
