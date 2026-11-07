-- Fase 6: Diário com assinatura, regras de operação, remessa entre órgãos e segurança de acesso. Banco de CADA ÓRGÃO. Idempotente.
ALTER TABLE diario_edicoes ADD COLUMN IF NOT EXISTS modo_teste BOOLEAN NOT NULL DEFAULT FALSE;   -- edição de teste: nunca é oficial
ALTER TABLE diario_edicoes ADD COLUMN IF NOT EXISTS pdfa BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE diario_edicoes ADD COLUMN IF NOT EXISTS assinaturas JSONB NOT NULL DEFAULT '[]';   -- etapas exigidas e feitas
ALTER TABLE diario_edicoes ADD COLUMN IF NOT EXISTS invalidacao JSONB;                         -- ato do Prefeito, comunicado, prorrogação
ALTER TABLE diario_edicoes ADD COLUMN IF NOT EXISTS alerta_assinatura BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE diario_edicoes DROP CONSTRAINT IF EXISTS diario_edicoes_situacao_check;
ALTER TABLE diario_edicoes ADD CONSTRAINT diario_edicoes_situacao_check CHECK (situacao IN ('montagem','fechada','publicada','invalidada'));
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS enviado_em TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS data_alvo DATE;                  -- edição prevista (corte das 16h)
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS pagina INT;                      -- página da edição onde o ato começa
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS retifica_ato_id INT REFERENCES diario_atos(id);
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS origem_orgao TEXT NOT NULL DEFAULT '';   -- remessa de outro órgão (ex.: cm-bora)
ALTER TABLE diario_atos ADD COLUMN IF NOT EXISTS remessa_externa TEXT NOT NULL DEFAULT '';
-- Calendário do Diário (Lei 910/2026 e decreto): feriados e dias sem expediente; ponto facultativo conta como dia útil
CREATE TABLE IF NOT EXISTS feriados (
  data DATE PRIMARY KEY, descricao TEXT NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'feriado' CHECK (tipo IN ('feriado','sem_expediente','ponto_facultativo'))
);
-- Signatários designados por caderno (Lei 910, art. 7º, § 1º; decreto, art. 2º, § 2º)
CREATE TABLE IF NOT EXISTS designacoes (
  id SERIAL PRIMARY KEY,
  caderno TEXT NOT NULL CHECK (caderno IN ('executivo','legislativo','final')),
  nome TEXT NOT NULL, cargo TEXT NOT NULL, ato TEXT NOT NULL DEFAULT '', ato_data DATE,
  provedor TEXT NOT NULL DEFAULT 'a3' CHECK (provedor IN ('a1','nuvem','a3')),
  certificado TEXT NOT NULL DEFAULT '',     -- A1: nome do arquivo .p12 em segredos/a1 (o arquivo nunca vai ao git)
  senha_env TEXT NOT NULL DEFAULT '',       -- A1: nome da variável do .env com a senha do certificado
  ativo BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS diario_alertas (
  id SERIAL PRIMARY KEY, quando TIMESTAMPTZ NOT NULL DEFAULT now(), tipo TEXT NOT NULL, mensagem TEXT NOT NULL, resolvido BOOLEAN NOT NULL DEFAULT FALSE
);
-- Remessas enviadas por este órgão ao Diário de outro órgão (ex.: Câmara → Prefeitura)
CREATE TABLE IF NOT EXISTS remessas (
  id SERIAL PRIMARY KEY, destino TEXT NOT NULL, tipo TEXT NOT NULL, numero TEXT NOT NULL DEFAULT '', ementa TEXT NOT NULL, texto TEXT NOT NULL,
  enviado_por TEXT NOT NULL, enviado_em TIMESTAMPTZ NOT NULL DEFAULT now(), remoto_id INT,
  situacao TEXT NOT NULL DEFAULT 'enviando', edicao TEXT NOT NULL DEFAULT '', pagina INT, data_publicacao DATE,
  atualizado_em TIMESTAMPTZ, erro TEXT NOT NULL DEFAULT ''
);
-- Segurança de acesso: segundo fator (TOTP), códigos de recuperação, vínculo gov.br pelo hash do CPF, bloqueio por tentativas
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_segredo TEXT NOT NULL DEFAULT '';     -- cifrado com TOTP_CHAVE
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS totp_ativo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS recuperacao JSONB NOT NULL DEFAULT '[]';   -- hashes dos códigos de recuperação
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS cpf_hash TEXT;                              -- HMAC do CPF (o CPF completo nunca é gravado)
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS falhas INT NOT NULL DEFAULT 0;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS bloqueado_ate TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS usuarios_cpf_hash_idx ON usuarios (cpf_hash) WHERE cpf_hash IS NOT NULL;
