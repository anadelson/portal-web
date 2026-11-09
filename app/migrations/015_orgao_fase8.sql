-- Fase 8. Banco de cada ÓRGÃO. Idempotente.
-- Menus do cabeçalho: cada destino aparece em uma única barra (UNIQUE em destino).
CREATE TABLE IF NOT EXISTS menus (
  id SERIAL PRIMARY KEY,
  barra TEXT NOT NULL CHECK (barra IN ('institucional','portal')),
  rotulo TEXT NOT NULL,
  destino TEXT NOT NULL UNIQUE,
  icone TEXT NOT NULL DEFAULT '',
  ordem INT NOT NULL DEFAULT 100,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  classe TEXT NOT NULL DEFAULT 'util',      -- classe eleitoral: itens de classe vedada somem no defeso
  modulo TEXT NOT NULL DEFAULT ''           -- módulo exigido (ex.: diario, bi); vazio = sempre
);
-- Acesso direto (botões sob o destaque da página inicial), personalizável no painel
CREATE TABLE IF NOT EXISTS atalhos (
  id SERIAL PRIMARY KEY, titulo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '', destino TEXT NOT NULL,
  icone TEXT NOT NULL DEFAULT 'lista', ordem INT NOT NULL DEFAULT 100, ativo BOOLEAN NOT NULL DEFAULT TRUE
);
-- Comunicados: tipo de conteúdo próprio (nunca "notícia")
CREATE TABLE IF NOT EXISTS comunicados (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL CHECK (lower(tipo) NOT IN ('notícia','noticia','notícias','noticias')),
  titulo TEXT NOT NULL, texto TEXT NOT NULL DEFAULT '',
  publicado_em TIMESTAMPTZ, valido_ate DATE,
  classe TEXT NOT NULL DEFAULT 'util' CHECK (classe IN ('pub','agente','slogan','util','serv','transp','ato')),
  situacao TEXT NOT NULL DEFAULT 'rascunho' CHECK (situacao IN ('rascunho','publicado','arquivado')),
  exemplo BOOLEAN NOT NULL DEFAULT FALSE, autor TEXT NOT NULL DEFAULT '', criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Notícias: destaque, capa 16:9 com texto alternativo e ponto focal, data e hora de publicação
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS destaque BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS imagem_alt TEXT NOT NULL DEFAULT '';
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS foco_x INT NOT NULL DEFAULT 50;
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS foco_y INT NOT NULL DEFAULT 50;
ALTER TABLE conteudos ADD COLUMN IF NOT EXISTS publicado_em TIMESTAMPTZ;
-- Contagem de acessos por mês (serviços mais acessados), sem dado pessoal
CREATE TABLE IF NOT EXISTS conteudo_acessos (conteudo_id INT NOT NULL REFERENCES conteudos(id) ON DELETE CASCADE, mes TEXT NOT NULL, n INT NOT NULL DEFAULT 0, PRIMARY KEY (conteudo_id, mes));
-- Conheça: perfis com galeria e vídeos
CREATE TABLE IF NOT EXISTS perfis (
  id SERIAL PRIMARY KEY, slug TEXT UNIQUE NOT NULL, titulo TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
  categoria TEXT NOT NULL DEFAULT 'Lugares', classe TEXT NOT NULL DEFAULT 'util' CHECK (classe IN ('pub','agente','slogan','util','serv','transp','ato')),
  ordem INT NOT NULL DEFAULT 100, publicado BOOLEAN NOT NULL DEFAULT FALSE, destaque BOOLEAN NOT NULL DEFAULT FALSE, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS perfil_fotos (
  id SERIAL PRIMARY KEY, perfil_id INT NOT NULL REFERENCES perfis(id) ON DELETE CASCADE, url TEXT NOT NULL,
  alt TEXT NOT NULL CHECK (length(trim(alt)) >= 5), legenda TEXT NOT NULL DEFAULT '', credito TEXT NOT NULL DEFAULT '',
  tem_pessoas BOOLEAN NOT NULL DEFAULT FALSE, autorizacao_imagem BOOLEAN NOT NULL DEFAULT FALSE, capa BOOLEAN NOT NULL DEFAULT FALSE, ordem INT NOT NULL DEFAULT 100
);
CREATE TABLE IF NOT EXISTS perfil_videos (
  id SERIAL PRIMARY KEY, perfil_id INT NOT NULL REFERENCES perfis(id) ON DELETE CASCADE,
  youtube_id TEXT NOT NULL CHECK (youtube_id ~ '^[A-Za-z0-9_-]{11}$'), titulo TEXT NOT NULL DEFAULT '', ordem INT NOT NULL DEFAULT 100
);
-- Legislação: montada a partir dos atos do Diário (e acervo importado por planilha), com relações entre atos
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS relacoes JSONB NOT NULL DEFAULT '[]';   -- [{"tipo": "revoga", "alvo": "Lei 12/2020"}]
CREATE TABLE IF NOT EXISTS legislacao (
  id SERIAL PRIMARY KEY, origem TEXT NOT NULL DEFAULT 'diario' CHECK (origem IN ('diario','importado')),
  diario_ato_id INT UNIQUE REFERENCES diario_atos(id) ON DELETE SET NULL,
  tipo TEXT NOT NULL, numero TEXT NOT NULL DEFAULT '', ano INT, data DATE, ementa TEXT NOT NULL, texto TEXT NOT NULL DEFAULT '',
  pdf_url TEXT NOT NULL DEFAULT '', edicao TEXT NOT NULL DEFAULT '', pagina INT, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS legislacao_ato_idx ON legislacao (lower(tipo), numero, ano) WHERE numero <> '';
CREATE TABLE IF NOT EXISTS legislacao_relacoes (
  origem_id INT NOT NULL REFERENCES legislacao(id) ON DELETE CASCADE, destino_id INT NOT NULL REFERENCES legislacao(id) ON DELETE CASCADE,
  tipo TEXT NOT NULL CHECK (tipo IN ('altera','revoga','regulamenta')), PRIMARY KEY (origem_id, destino_id, tipo)
);
-- Indicadores: título curto do cartão (até 32 caracteres)
ALTER TABLE indicadores ADD COLUMN IF NOT EXISTS titulo_curto TEXT NOT NULL DEFAULT '' CHECK (length(titulo_curto) <= 32);
-- Transmissões: vídeo vindo do YouTube (coleta automática) e não repetido
ALTER TABLE transmissoes ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'manual';
CREATE UNIQUE INDEX IF NOT EXISTS transmissoes_video_idx ON transmissoes (video) WHERE video <> '';
