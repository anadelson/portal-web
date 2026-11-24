-- Sessão em linha do tempo (24/11/2026). Banco de cada ÓRGÃO. Idempotente (roda de novo a cada atualização).
-- Nenhum passo é obrigatório: os registros podem ser feitos depois da sessão e cada parte é publicada separadamente.
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS numero INT;
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS situacao TEXT NOT NULL DEFAULT 'agendada';
ALTER TABLE sessoes DROP CONSTRAINT IF EXISTS sessoes_situacao_check;
ALTER TABLE sessoes ADD CONSTRAINT sessoes_situacao_check CHECK (situacao IN ('agendada','realizada','cancelada'));
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS motivo_cancelamento TEXT NOT NULL DEFAULT '';
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS aberta_as TEXT NOT NULL DEFAULT '';      -- hora informada (ex.: 19h05); vazio = não registrada
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS encerrada_as TEXT NOT NULL DEFAULT '';
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS linha_publicada BOOLEAN NOT NULL DEFAULT FALSE;
-- sessão com algum registro do que aconteceu já foi realizada
UPDATE sessoes s SET situacao='realizada' WHERE situacao='agendada'
  AND (presenca_publicada OR votacao_publicada OR ata_publicada OR length(ata) > 0 OR EXISTS (SELECT 1 FROM presencas p WHERE p.sessao_id=s.id)
       OR EXISTS (SELECT 1 FROM pauta_itens i WHERE i.sessao_id=s.id AND i.resultado IS NOT NULL));

-- votação simbólica: só o resultado, sem votos nominais
ALTER TABLE pauta_itens ADD COLUMN IF NOT EXISTS modo_votacao TEXT NOT NULL DEFAULT 'nominal';
ALTER TABLE pauta_itens DROP CONSTRAINT IF EXISTS pauta_itens_modo_votacao_check;
ALTER TABLE pauta_itens ADD CONSTRAINT pauta_itens_modo_votacao_check CHECK (modo_votacao IN ('nominal','simbolica'));
ALTER TABLE pauta_itens ADD COLUMN IF NOT EXISTS observacao TEXT NOT NULL DEFAULT '';

-- acontecimentos da sessão (linha do tempo): hora opcional, vereador e matéria opcionais
CREATE TABLE IF NOT EXISTS sessao_eventos (
  id SERIAL PRIMARY KEY,
  sessao_id INT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  ordem INT NOT NULL DEFAULT 0,
  hora TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL,
  descricao TEXT NOT NULL DEFAULT '',
  vereador_id INT REFERENCES vereadores(id) ON DELETE SET NULL,
  proposicao_id INT REFERENCES proposicoes(id) ON DELETE SET NULL,
  registrado_por TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE sessao_eventos DROP CONSTRAINT IF EXISTS sessao_eventos_tipo_check;
ALTER TABLE sessao_eventos ADD CONSTRAINT sessao_eventos_tipo_check CHECK (tipo IN
  ('expediente','leitura','orador','tribuna','ordem_do_dia','suspensao','reabertura','explicacoes','comunicacao','outro'));
CREATE INDEX IF NOT EXISTS sessao_eventos_sessao ON sessao_eventos (sessao_id, ordem);
CREATE INDEX IF NOT EXISTS sessao_eventos_vereador ON sessao_eventos (vereador_id);

-- vídeos da sessão (YouTube, Facebook ou outro); sessoes.video_url continua sendo o primeiro, para as telas antigas
CREATE TABLE IF NOT EXISTS sessao_videos (
  id SERIAL PRIMARY KEY,
  sessao_id INT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  plataforma TEXT NOT NULL DEFAULT 'outro',
  url TEXT NOT NULL,
  rotulo TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (sessao_id, url)
);
ALTER TABLE sessao_videos DROP CONSTRAINT IF EXISTS sessao_videos_plataforma_check;
ALTER TABLE sessao_videos ADD CONSTRAINT sessao_videos_plataforma_check CHECK (plataforma IN ('youtube','facebook','instagram','outro'));
INSERT INTO sessao_videos (sessao_id, plataforma, url)
  SELECT id, CASE WHEN video_url ~* '(youtube\.com|youtu\.be)' THEN 'youtube' WHEN video_url ~* '(facebook\.com|fb\.watch)' THEN 'facebook' ELSE 'outro' END, video_url
  FROM sessoes WHERE video_url <> ''
  ON CONFLICT (sessao_id, url) DO NOTHING;
