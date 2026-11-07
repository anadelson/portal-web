-- Banco de CADA ÓRGÃO (Prefeitura ou Câmara). Mesmo esquema para todos.
CREATE TABLE IF NOT EXISTS config (
  chave TEXT PRIMARY KEY,
  valor JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  cpf_final TEXT,                         -- só os 2 últimos dígitos (LGPD); o login real será gov.br
  setor TEXT NOT NULL DEFAULT '',
  perfil TEXT NOT NULL CHECK (perfil IN ('admin','editor','publicador','procuradoria','remetente')),
  escopo TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'ativo' CHECK (situacao IN ('ativo','convite','suspenso')),
  senha_hash TEXT,
  trocar_senha BOOLEAN NOT NULL DEFAULT TRUE,
  validade DATE,
  ultimo_acesso TIMESTAMPTZ,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conteudos (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,                     -- Notícia, Página, Aviso, Banner, Documento
  secao TEXT NOT NULL DEFAULT 'Notícias',
  titulo TEXT NOT NULL,
  resumo TEXT NOT NULL DEFAULT '',
  texto TEXT NOT NULL DEFAULT '',
  classe TEXT NOT NULL CHECK (classe IN ('pub','agente','slogan','util','serv','transp','ato')),
  situacao TEXT NOT NULL DEFAULT 'rascunho' CHECK (situacao IN ('rascunho','revisao','devolvido','agendado','publicado','arquivado')),
  exemplo BOOLEAN NOT NULL DEFAULT FALSE, -- conteúdo de demonstração do piloto
  autor TEXT NOT NULL,
  comentario TEXT NOT NULL DEFAULT '',
  excecao_eleitoral TEXT NOT NULL DEFAULT '',
  publicar_em DATE,
  tirar_em DATE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conteudo_versoes (
  id SERIAL PRIMARY KEY,
  conteudo_id INT NOT NULL REFERENCES conteudos(id) ON DELETE CASCADE,
  quem TEXT NOT NULL,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  obs TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocos (
  id SERIAL PRIMARY KEY,
  pagina TEXT NOT NULL DEFAULT 'home',
  chave TEXT NOT NULL,
  regiao TEXT NOT NULL,
  ordem INT NOT NULL,
  visivel BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (pagina, chave)
);
CREATE TABLE IF NOT EXISTS esic (
  id SERIAL PRIMARY KEY,
  protocolo TEXT UNIQUE NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'pedido',    -- pedido (LAI) ou manifestação (ouvidoria)
  categoria TEXT NOT NULL DEFAULT '',     -- reclamação, sugestão, elogio, denúncia, solicitação
  assunto TEXT NOT NULL,
  texto TEXT NOT NULL,
  nome TEXT NOT NULL,                     -- dado pessoal: nunca exibido no portal
  email TEXT NOT NULL,
  recebido DATE NOT NULL DEFAULT CURRENT_DATE,
  situacao TEXT NOT NULL DEFAULT 'recebido' CHECK (situacao IN ('recebido','analise','prorrogado','respondido','recurso')),
  setor TEXT NOT NULL DEFAULT '',
  resposta TEXT NOT NULL DEFAULT '',
  justificativa TEXT NOT NULL DEFAULT '',
  respondido DATE
);
CREATE TABLE IF NOT EXISTS auditoria (
  id BIGSERIAL PRIMARY KEY,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  usuario TEXT NOT NULL,
  acao TEXT NOT NULL,
  ip TEXT NOT NULL DEFAULT ''
);
-- Legislativo
CREATE TABLE IF NOT EXISTS vereadores (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  apelido TEXT NOT NULL DEFAULT '',
  partido TEXT NOT NULL,
  legislatura INT NOT NULL,
  votos INT,
  foto_url TEXT NOT NULL DEFAULT '',
  bio TEXT NOT NULL DEFAULT '',
  UNIQUE (nome, legislatura)
);
CREATE TABLE IF NOT EXISTS legislaturas (
  numero INT PRIMARY KEY,
  anos TEXT NOT NULL,
  prefeito TEXT NOT NULL DEFAULT '',
  vice TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS mesas (
  id SERIAL PRIMARY KEY,
  legislatura INT NOT NULL,
  bienio TEXT NOT NULL,
  cargo TEXT NOT NULL,
  nome TEXT                               -- NULL = a eleger
);
CREATE TABLE IF NOT EXISTS sessoes (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  data DATE NOT NULL,
  hora TEXT NOT NULL DEFAULT '19h',
  pauta TEXT NOT NULL DEFAULT '',
  pauta_publicada BOOLEAN NOT NULL DEFAULT FALSE,
  ata TEXT NOT NULL DEFAULT '',
  ata_publicada BOOLEAN NOT NULL DEFAULT FALSE,
  presenca_publicada BOOLEAN NOT NULL DEFAULT FALSE,
  video_url TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS presencas (
  sessao_id INT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  vereador_id INT NOT NULL REFERENCES vereadores(id),
  situacao TEXT NOT NULL CHECK (situacao IN ('presente','ausente','justificada')),
  PRIMARY KEY (sessao_id, vereador_id)
);
CREATE TABLE IF NOT EXISTS proposicoes (
  id SERIAL PRIMARY KEY,
  tipo TEXT NOT NULL,
  numero INT NOT NULL,
  ano INT NOT NULL,
  autor TEXT NOT NULL,
  ementa TEXT NOT NULL,
  situacao TEXT NOT NULL,
  exemplo BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (tipo, numero, ano)
);
CREATE TABLE IF NOT EXISTS emendas (
  numero TEXT PRIMARY KEY,
  autor TEXT NOT NULL,
  objeto TEXT NOT NULL,
  valor NUMERIC(14,2) NOT NULL,
  pago_cadastro NUMERIC(14,2) NOT NULL DEFAULT 0,
  pago_empenho NUMERIC(14,2),
  empenho TEXT NOT NULL DEFAULT '',
  conferencia TEXT NOT NULL DEFAULT 'pendente',
  detalhe JSONB,
  fonte TEXT NOT NULL DEFAULT '',
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Diário Oficial (Lei 910/2026 e decreto de 25/03/2026)
CREATE TABLE IF NOT EXISTS diario_edicoes (
  id SERIAL PRIMARY KEY,
  numero INT NOT NULL,
  letra TEXT NOT NULL DEFAULT '',         -- edição extra: A..Z
  data DATE NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'montagem' CHECK (situacao IN ('montagem','fechada','publicada')),
  sem_atos BOOLEAN NOT NULL DEFAULT FALSE,
  pdf_arquivo TEXT,
  sha256 TEXT,
  codigo TEXT,
  assinatura TEXT NOT NULL DEFAULT 'pendente',  -- pendente | assinada (ICP-Brasil + carimbo do tempo)
  responsavel TEXT NOT NULL DEFAULT '',
  publicada_em TIMESTAMPTZ,
  UNIQUE (numero, letra)
);
CREATE TABLE IF NOT EXISTS diario_atos (
  id SERIAL PRIMARY KEY,
  caderno TEXT NOT NULL CHECK (caderno IN ('executivo','legislativo')),
  tipo TEXT NOT NULL,
  numero TEXT NOT NULL DEFAULT '',
  orgao TEXT NOT NULL,
  ementa TEXT NOT NULL,
  texto TEXT NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'rascunho' CHECK (situacao IN ('rascunho','revisao','devolvido','aprovado','publicado')),
  autor TEXT NOT NULL,
  comentario TEXT NOT NULL DEFAULT '',
  edicao_id INT REFERENCES diario_edicoes(id),
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
