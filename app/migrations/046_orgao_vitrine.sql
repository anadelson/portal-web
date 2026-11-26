-- Selos e reconhecimentos, galeria de vídeos (YouTube) e câmeras ao vivo (26/11/2026). Banco de cada ÓRGÃO. Idempotente.
-- Selos: o que o órgão conquistou, de qual instituição, como, com que nota; imagem e documento de concessão opcionais
-- (arquivos em DADOS_DIR/<órgão>/midia, servidos por /midia). "exemplo" = ilustração do piloto, sempre marcada no portal.
CREATE TABLE IF NOT EXISTS selos (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL CHECK (length(nome) BETWEEN 3 AND 120),
  instituicao TEXT NOT NULL CHECK (length(instituicao) BETWEEN 2 AND 160),
  como TEXT NOT NULL DEFAULT '' CHECK (length(como) <= 2000),
  nota TEXT NOT NULL DEFAULT '' CHECK (length(nota) <= 60),
  concedido_em DATE,
  valido_ate DATE,
  link TEXT NOT NULL DEFAULT '' CHECK (link = '' OR link ~ '^https://'),
  imagem TEXT NOT NULL DEFAULT '',
  documento TEXT NOT NULL DEFAULT '',
  documento_titulo TEXT NOT NULL DEFAULT '',
  ordem INT NOT NULL DEFAULT 100,
  visivel BOOLEAN NOT NULL DEFAULT TRUE,
  exemplo BOOLEAN NOT NULL DEFAULT FALSE,
  criado_por TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Galeria de vídeos: vídeos do canal oficial no YouTube (só o ID de 11 caracteres; exibidos por youtube-nocookie, ao clicar)
CREATE TABLE IF NOT EXISTS videos (
  id SERIAL PRIMARY KEY,
  titulo TEXT NOT NULL CHECK (length(titulo) BETWEEN 3 AND 160),
  youtube_id TEXT NOT NULL DEFAULT '' CHECK (youtube_id = '' OR youtube_id ~ '^[A-Za-z0-9_-]{11}$'),
  descricao TEXT NOT NULL DEFAULT '' CHECK (length(descricao) <= 500),
  publicado_em DATE,
  visivel BOOLEAN NOT NULL DEFAULT TRUE,
  exemplo BOOLEAN NOT NULL DEFAULT FALSE,
  criado_por TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (exemplo OR youtube_id <> '')
);
CREATE UNIQUE INDEX IF NOT EXISTS videos_youtube_idx ON videos (youtube_id) WHERE youtube_id <> '';
-- Câmeras ao vivo: endereço RTSP CIFRADO (Fernet, CHAVE_CREDENCIAIS), só gravação: nenhuma tela devolve o endereço.
-- "caminho" é o nome público e aleatório da câmera no conversor de vídeo (não revela o endereço da câmera).
CREATE TABLE IF NOT EXISTS cameras (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL CHECK (length(nome) BETWEEN 3 AND 80),
  local TEXT NOT NULL DEFAULT '' CHECK (length(local) <= 160),
  rtsp TEXT NOT NULL DEFAULT '',
  caminho TEXT NOT NULL UNIQUE,
  ativa BOOLEAN NOT NULL DEFAULT TRUE,
  ordem INT NOT NULL DEFAULT 100,
  exemplo BOOLEAN NOT NULL DEFAULT FALSE,
  criado_por TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (exemplo OR rtsp <> '')
);
