-- Busca no portal antigo do próprio órgão (24/11/2026). Banco de cada ÓRGÃO. Idempotente.
-- O endereço é cadastrado no painel (/admin/importar/portal); a varredura roda no worker, aos poucos, e tudo o que for achado
-- fica numa área de revisão. Só a confirmação de quem revisa cria RASCUNHOS nas seções; nada é publicado sozinho.
CREATE TABLE IF NOT EXISTS migracao_varreduras (
  id SERIAL PRIMARY KEY,
  url_inicial TEXT NOT NULL,
  dominio TEXT NOT NULL,                       -- host informado; a varredura fica nele e nos subdomínios
  assunto TEXT NOT NULL DEFAULT 'tudo',
  palavras TEXT NOT NULL DEFAULT '',           -- palavras-chave opcionais (separadas por vírgula)
  desde DATE, ate DATE,                        -- período opcional (pela data encontrada na página)
  limite_paginas INT NOT NULL DEFAULT 300,
  situacao TEXT NOT NULL DEFAULT 'aguardando',
  paginas_lidas INT NOT NULL DEFAULT 0,
  itens INT NOT NULL DEFAULT 0,
  bytes BIGINT NOT NULL DEFAULT 0,
  intervalo NUMERIC NOT NULL DEFAULT 1,        -- segundos entre pedidos (1 ou o Crawl-delay do robots.txt, até 10)
  robots TEXT,                                 -- robots.txt lido no início (NULL = ainda não lido)
  msg TEXT NOT NULL DEFAULT '',
  criado_por TEXT NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  iniciado_em TIMESTAMPTZ, concluido_em TIMESTAMPTZ, ultimo_pedido TIMESTAMPTZ
);
ALTER TABLE migracao_varreduras DROP CONSTRAINT IF EXISTS migracao_varreduras_situacao_check;
ALTER TABLE migracao_varreduras ADD CONSTRAINT migracao_varreduras_situacao_check CHECK (situacao IN ('aguardando','rodando','pausada','concluida','erro'));
ALTER TABLE migracao_varreduras DROP CONSTRAINT IF EXISTS migracao_varreduras_assunto_check;
ALTER TABLE migracao_varreduras ADD CONSTRAINT migracao_varreduras_assunto_check CHECK (assunto IN ('tudo','noticias','paginas','sessoes','proposicoes','documentos','fotos'));

-- fila de endereços a visitar (sobrevive a reinícios do worker)
CREATE TABLE IF NOT EXISTS migracao_fila (
  id SERIAL PRIMARY KEY,
  varredura_id INT NOT NULL REFERENCES migracao_varreduras(id) ON DELETE CASCADE,
  url TEXT NOT NULL, prof INT NOT NULL DEFAULT 0,
  rotulo TEXT NOT NULL DEFAULT '',             -- texto do link que trouxe até aqui
  origem TEXT NOT NULL DEFAULT '',             -- página onde o link estava
  data_origem DATE,                            -- data da página de origem (para arquivos sem data própria)
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','lida','ignorada','erro')),
  motivo TEXT NOT NULL DEFAULT '',
  UNIQUE (varredura_id, url)
);
CREATE INDEX IF NOT EXISTS migracao_fila_pend ON migracao_fila (varredura_id, situacao, prof, id);

-- arquivos baixados (fotos e documentos), um por endereço; "usos" conta em quantas páginas a foto aparece (logo, ícone e
-- cabeçalho aparecem em muitas e ficam de fora)
CREATE TABLE IF NOT EXISTS migracao_arquivos (
  id SERIAL PRIMARY KEY,
  varredura_id INT NOT NULL REFERENCES migracao_varreduras(id) ON DELETE CASCADE,
  url TEXT NOT NULL, arquivo TEXT, ext TEXT NOT NULL DEFAULT '', bytes INT NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',
  usos INT NOT NULL DEFAULT 1, erro TEXT NOT NULL DEFAULT '',
  UNIQUE (varredura_id, url)
);

-- o que foi encontrado, para revisão: página (texto e fotos) ou arquivo (PDF, DOCX…)
CREATE TABLE IF NOT EXISTS migracao_itens (
  id SERIAL PRIMARY KEY,
  varredura_id INT NOT NULL REFERENCES migracao_varreduras(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('pagina','arquivo')),
  titulo TEXT NOT NULL DEFAULT '',
  data_original DATE,
  texto TEXT NOT NULL DEFAULT '',              -- texto extraído, com CPF mascarado
  imagens JSONB NOT NULL DEFAULT '[]',         -- [{arquivo_id, alt}]
  arquivo_id INT REFERENCES migracao_arquivos(id) ON DELETE SET NULL,
  origem TEXT NOT NULL DEFAULT '',             -- página onde o arquivo foi achado
  avisos JSONB NOT NULL DEFAULT '[]',          -- LGPD e outros cuidados para quem revisa
  sugestao JSONB NOT NULL DEFAULT '{}',        -- {destino, alvo, rotulo}
  situacao TEXT NOT NULL DEFAULT 'novo' CHECK (situacao IN ('novo','migrado','descartado')),
  destino TEXT NOT NULL DEFAULT '', destino_id INT, migrado_por TEXT NOT NULL DEFAULT '', migrado_em TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (varredura_id, url)
);
CREATE INDEX IF NOT EXISTS migracao_itens_var ON migracao_itens (varredura_id, situacao, id);
