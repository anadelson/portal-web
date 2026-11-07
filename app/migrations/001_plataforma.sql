-- Banco de CONTROLE da plataforma (console do gestor). Não guarda dados dos órgãos.
CREATE TABLE IF NOT EXISTS orgaos (
  id SERIAL PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,              -- ex.: pm-bora, cm-bora
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('executivo','legislativo')),
  dominio TEXT UNIQUE NOT NULL,
  banco TEXT UNIQUE NOT NULL,             -- um banco por órgão
  municipio TEXT NOT NULL,
  ibge TEXT NOT NULL,
  plano TEXT NOT NULL,
  cor TEXT NOT NULL DEFAULT '#1D4E89',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS contratos (
  id SERIAL PRIMARY KEY,
  orgao_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE,
  numero TEXT NOT NULL DEFAULT '[a registrar]',
  processo TEXT NOT NULL DEFAULT '[a registrar]',
  inicio DATE NOT NULL,
  fim DATE NOT NULL,
  carencia_dias INT NOT NULL DEFAULT 60,
  suspenso BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS aditivos (
  id SERIAL PRIMARY KEY,
  contrato_id INT NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  descricao TEXT NOT NULL,
  novo_fim DATE NOT NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS modulos (
  chave TEXT PRIMARY KEY,
  nome TEXT NOT NULL,
  descricao TEXT NOT NULL,
  oferta TEXT NOT NULL CHECK (oferta IN ('obr','plano','opc')),
  serve TEXT NOT NULL CHECK (serve IN ('ambos','executivo','legislativo')),
  depende TEXT
);
CREATE TABLE IF NOT EXISTS orgao_modulos (
  orgao_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE,
  chave TEXT NOT NULL REFERENCES modulos(chave),
  contratado BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (orgao_id, chave)
);
CREATE TABLE IF NOT EXISTS gestores (
  id SERIAL PRIMARY KEY,
  nome TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  senha_hash TEXT NOT NULL,
  trocar_senha BOOLEAN NOT NULL DEFAULT TRUE,
  ativo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS log_console (
  id BIGSERIAL PRIMARY KEY,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  quem TEXT NOT NULL,
  acao TEXT NOT NULL
);
-- Dados públicos compartilhados por município (IBGE, Siconfi, PNCP...). Somente leitura para os órgãos.
CREATE TABLE IF NOT EXISTS dados_publicos (
  ibge TEXT NOT NULL,
  fonte TEXT NOT NULL,
  chave TEXT NOT NULL,
  payload JSONB NOT NULL,
  coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (ibge, fonte, chave)
);
CREATE TABLE IF NOT EXISTS coletas (
  id BIGSERIAL PRIMARY KEY,
  orgao_slug TEXT,
  fonte TEXT NOT NULL,
  inicio TIMESTAMPTZ NOT NULL DEFAULT now(),
  fim TIMESTAMPTZ,
  ok BOOLEAN,
  registros INT,
  mensagem TEXT
);
