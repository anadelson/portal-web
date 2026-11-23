-- e-SIC e Ouvidoria completos (23/11/2026): prazos legais, histórico, recursos, complementação, encaminhamento entre
-- órgãos (mesma instalação ou outra), código de acesso do cidadão, notificações por e-mail, relatórios e informações
-- classificadas. Idempotente. Dados pessoais (nome, e-mail) continuam só na tabela esic, nunca no portal.

-- situações novas: complementacao (aguardando o cidadão), encaminhado (remetido a outro órgão), encerrado (sem resposta de mérito)
ALTER TABLE esic DROP CONSTRAINT IF EXISTS esic_situacao_check;
ALTER TABLE esic ADD CONSTRAINT esic_situacao_check
  CHECK (situacao IN ('recebido','analise','prorrogado','complementacao','respondido','recurso','encaminhado','encerrado'));

ALTER TABLE esic ADD COLUMN IF NOT EXISTS codigo_hash TEXT;                        -- código de acesso do cidadão (só o hash)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS recebido_em TIMESTAMPTZ;                 -- data e hora do registro
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prazo DATE;                              -- data-limite atual da resposta
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prorrogado_em DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS canal TEXT NOT NULL DEFAULT 'internet';  -- internet, presencial, telefone, carta, email, orgao
ALTER TABLE esic ADD COLUMN IF NOT EXISTS tipo_pessoa TEXT NOT NULL DEFAULT '';    -- fisica, juridica ou '' (estatística, LAI art. 30, III)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS anonimo BOOLEAN NOT NULL DEFAULT FALSE;  -- comunicação de irregularidade sem identificação
ALTER TABLE esic ADD COLUMN IF NOT EXISTS identidade_preservada BOOLEAN NOT NULL DEFAULT FALSE;  -- Lei 13.460, art. 10, § 7º
ALTER TABLE esic ADD COLUMN IF NOT EXISTS decisao TEXT NOT NULL DEFAULT '';        -- pedidos: concedido, parcial, negado, nao_possui, encaminhado
ALTER TABLE esic ADD COLUMN IF NOT EXISTS fundamento TEXT NOT NULL DEFAULT '';     -- base legal da negativa (LAI, art. 11, § 1º, II)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS respondido_por TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_pedido TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_ate DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_restante INT;                -- dias de prazo que faltavam quando o complemento foi pedido
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_usado BOOLEAN NOT NULL DEFAULT FALSE;  -- só uma vez por pedido/manifestação
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_para TEXT NOT NULL DEFAULT '';         -- slug do órgão parceiro
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_nome TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_dominio TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS protocolo_destino TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS origem_orgao TEXT NOT NULL DEFAULT '';             -- recebido de outro órgão (slug)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS origem_nome TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS protocolo_origem TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS avaliacao INT CHECK (avaliacao BETWEEN 1 AND 5);   -- satisfação (Lei 13.460, art. 23)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS avaliacao_resolveu BOOLEAN;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now();
UPDATE esic SET prazo = recebido + CASE WHEN tipo='pedido' THEN 20 + CASE WHEN situacao='prorrogado' THEN 10 ELSE 0 END ELSE 30 END WHERE prazo IS NULL;
UPDATE esic SET decisao='concedido' WHERE tipo='pedido' AND situacao='respondido' AND decisao='';
CREATE INDEX IF NOT EXISTS esic_situacao_idx ON esic (situacao, prazo);
CREATE UNIQUE INDEX IF NOT EXISTS esic_origem_idx ON esic (origem_orgao, protocolo_origem) WHERE origem_orgao <> '';

-- linha do tempo: o que o cidadão vê (publico) e as notas internas da equipe
CREATE TABLE IF NOT EXISTS esic_historico (
  id BIGSERIAL PRIMARY KEY,
  esic_id INT NOT NULL REFERENCES esic(id) ON DELETE CASCADE,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(),
  evento TEXT NOT NULL,          -- registro, setor, prorrogacao, complementacao, complemento, resposta, recurso, decisao_recurso, encaminhamento, retorno, nota, identidade, avaliacao
  publico BOOLEAN NOT NULL DEFAULT TRUE,
  texto TEXT NOT NULL DEFAULT '',
  autor TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS esic_historico_idx ON esic_historico (esic_id, id);

-- recursos (LAI, art. 15: 10 dias para recorrer; a autoridade superior decide em 5 dias)
CREATE TABLE IF NOT EXISTS esic_recursos (
  id SERIAL PRIMARY KEY,
  esic_id INT NOT NULL REFERENCES esic(id) ON DELETE CASCADE,
  instancia INT NOT NULL CHECK (instancia IN (1, 2)),
  texto TEXT NOT NULL,
  recebido DATE NOT NULL,
  prazo DATE NOT NULL,
  decisao TEXT NOT NULL DEFAULT '' CHECK (decisao IN ('', 'provido', 'parcial', 'desprovido', 'nao_conhecido')),
  resposta TEXT NOT NULL DEFAULT '',
  autoridade TEXT NOT NULL DEFAULT '',
  decidido DATE,
  UNIQUE (esic_id, instancia)
);

-- fila de e-mails (registro, prorrogação, resposta, recurso...): enviada pelo worker; falha só fica registrada
CREATE TABLE IF NOT EXISTS notificacoes (
  id BIGSERIAL PRIMARY KEY,
  para TEXT NOT NULL,
  assunto TEXT NOT NULL,
  texto TEXT NOT NULL,
  ref TEXT NOT NULL DEFAULT '',          -- ex.: protocolo
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  enviado_em TIMESTAMPTZ,
  tentativas INT NOT NULL DEFAULT 0,
  erro TEXT NOT NULL DEFAULT ''
);
ALTER TABLE notificacoes ADD COLUMN IF NOT EXISTS ultima_tentativa TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS notificacoes_pendentes_idx ON notificacoes (id) WHERE enviado_em IS NULL;

-- relatório anual de gestão da Ouvidoria (Lei 13.460, arts. 14 e 15): números vêm do sistema; análise e providências, da equipe
CREATE TABLE IF NOT EXISTS ouvidoria_relatorios (
  ano INT PRIMARY KEY,
  analise TEXT NOT NULL DEFAULT '',      -- pontos recorrentes
  providencias TEXT NOT NULL DEFAULT '', -- providências adotadas
  publicado_em TIMESTAMPTZ,
  atualizado_por TEXT NOT NULL DEFAULT ''
);

-- rol de informações classificadas e desclassificadas (LAI, art. 30, I e II; PNTP 12.8 e 12.9)
CREATE TABLE IF NOT EXISTS informacoes_classificadas (
  id SERIAL PRIMARY KEY,
  assunto TEXT NOT NULL,
  grau TEXT NOT NULL CHECK (grau IN ('reservado', 'secreto', 'ultrassecreto')),
  categoria TEXT NOT NULL DEFAULT '',
  fundamento TEXT NOT NULL,              -- dispositivo legal (LAI, art. 23, inciso ...)
  classificada_em DATE NOT NULL,
  prazo_ate DATE NOT NULL,
  autoridade TEXT NOT NULL DEFAULT '',
  desclassificada_em DATE,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- perfis novos: Ouvidoria/SIC e autoridade que decide recursos
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check
  CHECK (perfil IN ('admin','editor','publicador','procuradoria','remetente','redator','validador','ouvidor','autoridade'));
