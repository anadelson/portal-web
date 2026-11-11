-- Banco LOCAL do nó (separação gestão × portais, etapa A2, 11/11/2026). Idempotente.
-- Tabelas operacionais que, com gestão e portais juntos (papel "tudo"), ficam no banco de controle; no papel "no" ficam aqui.
-- Mesmo esquema das tabelas do banco de controle (conferido pelo tests/teste_no_local.py), sem chaves estrangeiras para `orgaos`
-- (o cadastro dos órgãos vem das licenças assinadas). Mudou uma destas tabelas numa migração do controle? Mude aqui também.


SET statement_timeout = 0;
CREATE TABLE IF NOT EXISTS coletas (
    id bigint NOT NULL,
    orgao_slug text,
    fonte text NOT NULL,
    inicio timestamp with time zone DEFAULT now() NOT NULL,
    fim timestamp with time zone,
    ok boolean,
    registros integer,
    mensagem text
);
CREATE SEQUENCE IF NOT EXISTS coletas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE coletas_id_seq OWNED BY coletas.id;
CREATE TABLE IF NOT EXISTS config_console (
    chave text NOT NULL,
    valor jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS consulta_amostras (
    chave text NOT NULL,
    orgao_slug text DEFAULT ''::text NOT NULL,
    fonte text NOT NULL,
    url text NOT NULL,
    status integer DEFAULT 0 NOT NULL,
    ms integer DEFAULT 0 NOT NULL,
    registros integer DEFAULT 0 NOT NULL,
    trecho text DEFAULT ''::text NOT NULL,
    erro text DEFAULT ''::text NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS consulta_testes (
    id bigint NOT NULL,
    orgao_id integer NOT NULL,
    fonte text NOT NULL,
    params_hash text NOT NULL,
    ok boolean NOT NULL,
    relatorio jsonb DEFAULT '{}'::jsonb NOT NULL,
    quem text NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS consulta_testes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE consulta_testes_id_seq OWNED BY consulta_testes.id;
CREATE TABLE IF NOT EXISTS credenciais_fontes (
    fonte text NOT NULL,
    dados text NOT NULL,
    configurada_em timestamp with time zone DEFAULT now() NOT NULL,
    configurada_por text NOT NULL,
    testada_em timestamp with time zone,
    testada_por text DEFAULT ''::text NOT NULL,
    teste_resultado text DEFAULT ''::text NOT NULL
);
CREATE TABLE IF NOT EXISTS dados_publicos (
    ibge text NOT NULL,
    fonte text NOT NULL,
    chave text NOT NULL,
    payload jsonb NOT NULL,
    coletado_em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS fontes (
    orgao_id integer NOT NULL,
    fonte text NOT NULL,
    params jsonb DEFAULT '{}'::jsonb NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    agenda jsonb,
    CONSTRAINT fontes_fonte_check CHECK ((fonte = ANY (ARRAY['fiorilli'::text, 'govbr'::text, 'pncp'::text, 'siconfi'::text, 'tcesp'::text, 'ibge'::text, 'cnes'::text, 'mds'::text, 'pni'::text, 'painel'::text, 'inep'::text, 'iegm'::text, 'financas'::text, 'youtube'::text, 'redes'::text])))
);
CREATE TABLE IF NOT EXISTS fontes_historico (
    id bigint NOT NULL,
    orgao_id integer NOT NULL,
    fonte text NOT NULL,
    antes jsonb NOT NULL,
    depois jsonb NOT NULL,
    quem text NOT NULL,
    em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS fontes_historico_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE fontes_historico_id_seq OWNED BY fontes_historico.id;
CREATE TABLE IF NOT EXISTS indicadores_publicos (
    ibge text NOT NULL,
    indicador text NOT NULL,
    periodo text NOT NULL,
    data_ref date NOT NULL,
    valor numeric,
    texto text DEFAULT ''::text NOT NULL,
    detalhe jsonb,
    nota text DEFAULT ''::text NOT NULL,
    parcial boolean DEFAULT false NOT NULL,
    fonte text NOT NULL,
    coletado_em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS licencas_cache (
    orgao_id integer NOT NULL,
    slug text NOT NULL,
    dominio text NOT NULL,
    serial bigint NOT NULL,
    pacote jsonb NOT NULL,
    valida_ate timestamp with time zone NOT NULL,
    recebida_em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS login_tentativas (
    id bigint NOT NULL,
    quando timestamp with time zone DEFAULT now() NOT NULL,
    chave text NOT NULL,
    ok boolean NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS login_tentativas_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE login_tentativas_id_seq OWNED BY login_tentativas.id;
CREATE TABLE IF NOT EXISTS pares_orgaos (
    origem_id integer NOT NULL,
    destino_id integer NOT NULL,
    token text NOT NULL,
    ativo boolean DEFAULT true NOT NULL,
    criado_em timestamp with time zone DEFAULT now() NOT NULL
);
CREATE TABLE IF NOT EXISTS remessas_log (
    id bigint NOT NULL,
    quando timestamp with time zone DEFAULT now() NOT NULL,
    origem text NOT NULL,
    destino text NOT NULL,
    acao text NOT NULL,
    ok boolean NOT NULL,
    detalhe text DEFAULT ''::text NOT NULL
);
CREATE SEQUENCE IF NOT EXISTS remessas_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE remessas_log_id_seq OWNED BY remessas_log.id;
ALTER TABLE ONLY coletas ALTER COLUMN id SET DEFAULT nextval('coletas_id_seq'::regclass);
ALTER TABLE ONLY consulta_testes ALTER COLUMN id SET DEFAULT nextval('consulta_testes_id_seq'::regclass);
ALTER TABLE ONLY fontes_historico ALTER COLUMN id SET DEFAULT nextval('fontes_historico_id_seq'::regclass);
ALTER TABLE ONLY login_tentativas ALTER COLUMN id SET DEFAULT nextval('login_tentativas_id_seq'::regclass);
ALTER TABLE ONLY remessas_log ALTER COLUMN id SET DEFAULT nextval('remessas_log_id_seq'::regclass);
DO $$ BEGIN
  ALTER TABLE ONLY coletas
    ADD CONSTRAINT coletas_pkey PRIMARY KEY (id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY config_console
    ADD CONSTRAINT config_console_pkey PRIMARY KEY (chave);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY consulta_amostras
    ADD CONSTRAINT consulta_amostras_pkey PRIMARY KEY (chave);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY consulta_testes
    ADD CONSTRAINT consulta_testes_pkey PRIMARY KEY (id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY credenciais_fontes
    ADD CONSTRAINT credenciais_fontes_pkey PRIMARY KEY (fonte);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY dados_publicos
    ADD CONSTRAINT dados_publicos_pkey PRIMARY KEY (ibge, fonte, chave);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY fontes_historico
    ADD CONSTRAINT fontes_historico_pkey PRIMARY KEY (id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY fontes
    ADD CONSTRAINT fontes_pkey PRIMARY KEY (orgao_id, fonte);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY indicadores_publicos
    ADD CONSTRAINT indicadores_publicos_pkey PRIMARY KEY (ibge, indicador, periodo);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY licencas_cache
    ADD CONSTRAINT licencas_cache_pkey PRIMARY KEY (orgao_id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY login_tentativas
    ADD CONSTRAINT login_tentativas_pkey PRIMARY KEY (id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY pares_orgaos
    ADD CONSTRAINT pares_orgaos_pkey PRIMARY KEY (origem_id, destino_id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE ONLY remessas_log
    ADD CONSTRAINT remessas_log_pkey PRIMARY KEY (id);
EXCEPTION WHEN duplicate_object OR duplicate_table OR invalid_table_definition THEN NULL; END $$;
CREATE INDEX IF NOT EXISTS coletas_fonte_idx ON coletas USING btree (orgao_slug, fonte, id DESC);
CREATE INDEX IF NOT EXISTS consulta_testes_idx ON consulta_testes USING btree (orgao_id, fonte, em DESC);
CREATE INDEX IF NOT EXISTS login_tentativas_idx ON login_tentativas USING btree (chave, quando DESC);
