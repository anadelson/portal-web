-- Fase 4 (transparência com dados reais). Banco de CADA ÓRGÃO. Idempotente.
-- Toda linha guarda a fonte, a data da coleta e uma chave natural (upsert). LGPD: nenhuma coluna de CPF.
CREATE TABLE IF NOT EXISTS receitas (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, mes INT NOT NULL DEFAULT 0,          -- mes 0 = acumulado no ano (Fiorilli); 1..12 = mês (TCESP)
  codigo TEXT NOT NULL DEFAULT '', nome TEXT NOT NULL, fonte_recurso TEXT NOT NULL DEFAULT '',
  previsto NUMERIC(16,2), atualizado NUMERIC(16,2), arrecadado NUMERIC(16,2) NOT NULL DEFAULT 0,
  soma BOOLEAN NOT NULL DEFAULT FALSE                     -- linhas que entram no total (sem dupla contagem)
);
CREATE TABLE IF NOT EXISTS despesas_unidade (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, codigo TEXT NOT NULL, unidade TEXT NOT NULL,
  dotacao NUMERIC(16,2), dotacao_atualizada NUMERIC(16,2), empenhado NUMERIC(16,2), liquidado NUMERIC(16,2), pago NUMERIC(16,2)
);
CREATE TABLE IF NOT EXISTS empenhos (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, pk TEXT NOT NULL, numero TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT '', data DATE,
  credor TEXT NOT NULL DEFAULT '', credor_cnpj TEXT NOT NULL DEFAULT '',  -- pessoa física: sem documento
  unidade TEXT NOT NULL DEFAULT '', funcao TEXT NOT NULL DEFAULT '', programa TEXT NOT NULL DEFAULT '', acao TEXT NOT NULL DEFAULT '',
  natureza TEXT NOT NULL DEFAULT '', fonte_recurso TEXT NOT NULL DEFAULT '', vinculo TEXT NOT NULL DEFAULT '', vinculo_nome TEXT NOT NULL DEFAULT '',
  modalidade TEXT NOT NULL DEFAULT '', processo TEXT NOT NULL DEFAULT '',
  empenhado NUMERIC(16,2) NOT NULL DEFAULT 0, liquidado NUMERIC(16,2) NOT NULL DEFAULT 0, pago NUMERIC(16,2) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS empenhos_ano_idx ON empenhos (ano, data);
CREATE INDEX IF NOT EXISTS empenhos_vinculo_idx ON empenhos (vinculo);
CREATE TABLE IF NOT EXISTS licitacoes (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, numero TEXT NOT NULL DEFAULT '', modalidade TEXT NOT NULL DEFAULT '', objeto TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT '', data DATE, valor NUMERIC(16,2), unidade TEXT NOT NULL DEFAULT '', link TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS contratos (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, numero TEXT NOT NULL, fornecedor TEXT NOT NULL DEFAULT '', objeto TEXT NOT NULL DEFAULT '', modalidade TEXT NOT NULL DEFAULT '',
  processo TEXT NOT NULL DEFAULT '', assinatura DATE, inicio DATE, fim DATE, unidade TEXT NOT NULL DEFAULT '',
  valor NUMERIC(16,2), empenhado NUMERIC(16,2), liquidado NUMERIC(16,2)
);
CREATE TABLE IF NOT EXISTS servidores (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, mes INT NOT NULL, registro TEXT NOT NULL, nome TEXT NOT NULL, cargo TEXT NOT NULL DEFAULT '', vinculo TEXT NOT NULL DEFAULT '',
  lotacao TEXT NOT NULL DEFAULT '', admissao DATE, proventos NUMERIC(14,2)   -- remuneração bruta; sem descontos pessoais
);
CREATE TABLE IF NOT EXISTS diarias (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, empenho TEXT NOT NULL DEFAULT '', data DATE, favorecido TEXT NOT NULL DEFAULT '', cargo TEXT NOT NULL DEFAULT '',
  unidade TEXT NOT NULL DEFAULT '', motivo TEXT NOT NULL DEFAULT '', valor NUMERIC(14,2), anulado NUMERIC(14,2)
);
CREATE TABLE IF NOT EXISTS transferencias (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, mes INT, data DATE, pagadora TEXT NOT NULL DEFAULT '', recebedora TEXT NOT NULL DEFAULT '',
  previsto NUMERIC(16,2), repasse NUMERIC(16,2), devolucao NUMERIC(16,2)
);
CREATE TABLE IF NOT EXISTS ordem_cronologica (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, lista TEXT NOT NULL DEFAULT '', empenho TEXT NOT NULL DEFAULT '', fornecedor TEXT NOT NULL DEFAULT '', cnpj TEXT NOT NULL DEFAULT '',
  unidade TEXT NOT NULL DEFAULT '', fonte_recurso TEXT NOT NULL DEFAULT '', contrato TEXT NOT NULL DEFAULT '',
  vencimento DATE, pagamento DATE, valor NUMERIC(16,2), justificativa TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS restos_pagar (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, codigo TEXT NOT NULL DEFAULT '', credor TEXT NOT NULL DEFAULT '',
  empenhado NUMERIC(16,2), liquidado NUMERIC(16,2), pago NUMERIC(16,2)
);
CREATE TABLE IF NOT EXISTS relatorios_fiscais (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL, coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, demonstrativo TEXT NOT NULL, anexo TEXT NOT NULL, periodo INT NOT NULL, periodicidade TEXT NOT NULL DEFAULT '',
  poder TEXT NOT NULL DEFAULT '', instituicao TEXT NOT NULL DEFAULT '', rotulo TEXT NOT NULL DEFAULT '', conta TEXT NOT NULL DEFAULT '',
  coluna TEXT NOT NULL DEFAULT '', valor NUMERIC(18,2)
);
-- Emendas (Câmara): execução vinda da Prefeitura pela API pública, com o cadastro separado
ALTER TABLE emendas ADD COLUMN IF NOT EXISTS empenhado_cadastro NUMERIC(14,2);
ALTER TABLE emendas ADD COLUMN IF NOT EXISTS liquidado_cadastro NUMERIC(14,2);
ALTER TABLE emendas ADD COLUMN IF NOT EXISTS empenhado NUMERIC(14,2);
ALTER TABLE emendas ADD COLUMN IF NOT EXISTS liquidado NUMERIC(14,2);
ALTER TABLE emendas ADD COLUMN IF NOT EXISTS coletado_em TIMESTAMPTZ;
