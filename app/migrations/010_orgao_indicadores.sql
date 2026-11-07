-- Fase 7. Banco de cada ÓRGÃO. Idempotente.
-- Catálogo do painel de indicadores (módulo "bi") e série de valores.
CREATE TABLE IF NOT EXISTS indicadores (
  id SERIAL PRIMARY KEY,
  chave TEXT UNIQUE NOT NULL,
  tema TEXT NOT NULL CHECK (tema IN ('fin','cont','saude','edu','social','mun')),
  nome TEXT NOT NULL,
  descricao TEXT NOT NULL DEFAULT '',          -- explicação em linguagem simples (sem tom de propaganda)
  unidade TEXT NOT NULL DEFAULT '',            -- R$, %, pessoas, estabelecimentos, nota...
  formato TEXT NOT NULL DEFAULT 'numero' CHECK (formato IN ('numero','moeda','pct','nota','faixa')),
  casas INT NOT NULL DEFAULT 0,
  fonte TEXT NOT NULL DEFAULT '',
  fonte_link TEXT NOT NULL DEFAULT '',
  periodicidade TEXT NOT NULL DEFAULT '',
  modo TEXT NOT NULL DEFAULT 'automatico' CHECK (modo IN ('automatico','manual')),
  coletor TEXT NOT NULL DEFAULT '',            -- fonte de coleta (ibge, cnes, painel, mds, pni) ou vazio se manual
  pendente TEXT NOT NULL DEFAULT '',           -- aviso administrativo (ex.: pendente de fonte estável)
  meta NUMERIC,
  meta_base_legal TEXT NOT NULL DEFAULT '',
  sentido TEXT NOT NULL DEFAULT 'neutro' CHECK (sentido IN ('maior','menor','neutro')),
  suprimir BOOLEAN NOT NULL DEFAULT FALSE,     -- contagem de pessoas: abaixo de 5 vira "menos de 5" (LGPD)
  base_legal TEXT NOT NULL DEFAULT '',
  visivel BOOLEAN NOT NULL DEFAULT TRUE,
  destaque BOOLEAN NOT NULL DEFAULT FALSE,     -- até 4 aparecem no bloco "Indicadores em números" da página inicial
  ordem INT NOT NULL DEFAULT 100,
  ultima_tentativa TIMESTAMPTZ,
  ultima_ok TIMESTAMPTZ,
  ultima_msg TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS indicador_valores (
  id BIGSERIAL PRIMARY KEY,
  indicador_id INT NOT NULL REFERENCES indicadores(id) ON DELETE CASCADE,
  periodo TEXT NOT NULL,
  data_ref DATE NOT NULL,
  valor NUMERIC,
  texto TEXT NOT NULL DEFAULT '',
  detalhe JSONB,
  nota TEXT NOT NULL DEFAULT '',
  parcial BOOLEAN NOT NULL DEFAULT FALSE,      -- período ainda aberto (ex.: ano corrente até a data da coleta): não é comparado
  origem TEXT NOT NULL DEFAULT 'coletor' CHECK (origem IN ('coletor','manual')),
  coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  usuario TEXT NOT NULL DEFAULT '',
  motivo TEXT NOT NULL DEFAULT '',
  UNIQUE (indicador_id, periodo)
);
CREATE INDEX IF NOT EXISTS indicador_valores_serie_idx ON indicador_valores (indicador_id, data_ref);
CREATE TABLE IF NOT EXISTS indicador_historico (
  id BIGSERIAL PRIMARY KEY,
  indicador_id INT REFERENCES indicadores(id) ON DELETE CASCADE,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  usuario TEXT NOT NULL,
  acao TEXT NOT NULL,
  antes JSONB,
  depois JSONB
);
