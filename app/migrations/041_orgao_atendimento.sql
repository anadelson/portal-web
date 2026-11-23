-- e-SIC e Ouvidoria completos (23/11/2026). Banco de cada ÓRGÃO. Idempotente.
-- LAI (Lei 12.527/2011) arts. 10, 11, 12, 14, 15, 24, 30, 31; Lei 13.460/2017 arts. 10, 14, 15, 16, 17, 23; LGPD.
-- Regras (app/atendimento.py): código de acesso (só o hash fica aqui), uma prorrogação (LAI 20+10; Ouvidoria 30+30),
-- um pedido de complemento (20 dias para o cidadão; o prazo fica suspenso), recurso em 1ª e 2ª instância (LAI),
-- denúncia anônima só na Ouvidoria, avaliação do atendimento, encaminhamento ao órgão parceiro sem a identidade.

-- perfis novos: Ouvidoria / SIC (vê a identidade) e Autoridade de recurso
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil IN ('admin','editor','publicador','procuradoria','remetente','redator','validador','ouvidoria','autoridade_recurso'));

ALTER TABLE esic ADD COLUMN IF NOT EXISTS codigo_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS anonimo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS perfil_solicitante TEXT NOT NULL DEFAULT '';   -- pf, pj ou '' (não informado): só para a estatística
ALTER TABLE esic ADD COLUMN IF NOT EXISTS canal TEXT NOT NULL DEFAULT 'internet';         -- internet, presencial, encaminhado
ALTER TABLE esic ADD COLUMN IF NOT EXISTS origem_orgao TEXT NOT NULL DEFAULT '';          -- encaminhado por outro órgão (slug)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS origem_protocolo TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prazo DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prorrogado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prorrogado_em DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_pedido TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_pedido_em DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_prazo DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_resposta TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS complemento_respondido_em DATE;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS prazo_restante INT;                             -- dias que faltavam quando o prazo foi suspenso
ALTER TABLE esic ADD COLUMN IF NOT EXISTS resultado TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS fundamento TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS respondido_por TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS respondido_por_id INT;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS avaliacao INT;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS resolveu BOOLEAN;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS avaliacao_comentario TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS avaliado_em TIMESTAMPTZ;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_orgao TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_slug TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_dominio TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_protocolo TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_codigo TEXT NOT NULL DEFAULT '';   -- código do protocolo NOVO (o pedido lá não tem identidade)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_situacao TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encaminhado_consultado_em TIMESTAMPTZ;
ALTER TABLE esic ADD COLUMN IF NOT EXISTS encerrado_motivo TEXT NOT NULL DEFAULT '';
ALTER TABLE esic ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ NOT NULL DEFAULT now();

-- situações novas; as antigas "prorrogado" e "recurso" viram campo/registro próprios
ALTER TABLE esic DROP CONSTRAINT IF EXISTS esic_situacao_check;
UPDATE esic SET prorrogado=TRUE, situacao='analise' WHERE situacao='prorrogado';
ALTER TABLE esic ADD CONSTRAINT esic_situacao_check CHECK (situacao IN ('recebido','analise','complemento','respondido','recurso','encaminhado','encerrado'));
ALTER TABLE esic DROP CONSTRAINT IF EXISTS esic_resultado_check;
ALTER TABLE esic ADD CONSTRAINT esic_resultado_check CHECK (resultado IN ('','concedido','parcial','negado','inexistente'));
ALTER TABLE esic DROP CONSTRAINT IF EXISTS esic_avaliacao_check;
ALTER TABLE esic ADD CONSTRAINT esic_avaliacao_check CHECK (avaliacao IS NULL OR avaliacao BETWEEN 1 AND 5);

-- registros antigos ganham prazo calculado (20 ou 30 dias; +10 ou +30 se prorrogados)
UPDATE esic SET prazo = recebido + (CASE WHEN tipo='pedido' THEN 20 + (CASE WHEN prorrogado THEN 10 ELSE 0 END) ELSE 30 + (CASE WHEN prorrogado THEN 30 ELSE 0 END) END)
 WHERE prazo IS NULL;
CREATE INDEX IF NOT EXISTS esic_situacao_idx ON esic (situacao, prazo);
CREATE INDEX IF NOT EXISTS esic_origem_idx ON esic (origem_orgao, protocolo);

CREATE TABLE IF NOT EXISTS esic_recursos (
  id SERIAL PRIMARY KEY, esic_id INT NOT NULL REFERENCES esic(id) ON DELETE CASCADE,
  instancia INT NOT NULL CHECK (instancia IN (1, 2)), texto TEXT NOT NULL, criado_em DATE NOT NULL DEFAULT CURRENT_DATE, prazo DATE NOT NULL,
  decisao TEXT NOT NULL DEFAULT '', resultado TEXT NOT NULL DEFAULT '' CHECK (resultado IN ('','provido','parcial','improvido')),
  decidido_por TEXT NOT NULL DEFAULT '', decidido_por_id INT, decidido_em DATE,
  UNIQUE (esic_id, instancia)
);
-- recurso registrado antes desta versão (situação "recurso" sem registro próprio)
INSERT INTO esic_recursos (esic_id, instancia, texto, criado_em, prazo)
SELECT e.id, 1, '(recurso registrado antes de 23/11/2026)', COALESCE(e.respondido, e.recebido), COALESCE(e.respondido, e.recebido) + 5
  FROM esic e WHERE e.situacao='recurso' AND NOT EXISTS (SELECT 1 FROM esic_recursos r WHERE r.esic_id=e.id);

-- histórico: o que o cidadão vê (interno=FALSE) e as notas internas da equipe (interno=TRUE)
CREATE TABLE IF NOT EXISTS esic_historico (
  id BIGSERIAL PRIMARY KEY, esic_id INT NOT NULL REFERENCES esic(id) ON DELETE CASCADE,
  quando TIMESTAMPTZ NOT NULL DEFAULT now(), quem TEXT NOT NULL DEFAULT '', acao TEXT NOT NULL, texto TEXT NOT NULL DEFAULT '', interno BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS esic_historico_idx ON esic_historico (esic_id, id);

-- fila de e-mails do atendimento (cidadão e equipe). O texto é apagado depois do envio (leva o código de acesso).
CREATE TABLE IF NOT EXISTS email_fila (
  id BIGSERIAL PRIMARY KEY, para TEXT NOT NULL, assunto TEXT NOT NULL, texto TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL DEFAULT 'cidadao' CHECK (tipo IN ('cidadao','equipe')), esic_id INT REFERENCES esic(id) ON DELETE SET NULL,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), tentativas INT NOT NULL DEFAULT 0, ultima_tentativa TIMESTAMPTZ, enviado_em TIMESTAMPTZ,
  erro TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS email_fila_pend_idx ON email_fila (id) WHERE enviado_em IS NULL;

-- SMTP próprio do órgão (opcional). Senha CIFRADA com a CHAVE_CREDENCIAIS; nenhuma tela a devolve.
CREATE TABLE IF NOT EXISTS atendimento_smtp (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  servidor TEXT NOT NULL, porta INT NOT NULL, seguranca TEXT NOT NULL CHECK (seguranca IN ('ssl','starttls','nenhuma')),
  usuario TEXT NOT NULL DEFAULT '', senha_cifrada TEXT NOT NULL DEFAULT '', remetente TEXT NOT NULL, remetente_nome TEXT NOT NULL DEFAULT '',
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(), atualizado_por TEXT NOT NULL DEFAULT '',
  teste_em TIMESTAMPTZ, teste_resultado TEXT NOT NULL DEFAULT ''
);

-- LAI arts. 24, 30 e 31: informações classificadas (grau, assunto, categoria, fundamento, prazo) e desclassificadas
CREATE TABLE IF NOT EXISTS info_classificadas (
  id SERIAL PRIMARY KEY, referencia TEXT NOT NULL DEFAULT '', assunto TEXT NOT NULL, categoria TEXT NOT NULL DEFAULT '',
  grau TEXT NOT NULL CHECK (grau IN ('reservado','secreto','ultrassecreto')), fundamento TEXT NOT NULL,
  classificada_em DATE NOT NULL, prazo_ate DATE NOT NULL, autoridade TEXT NOT NULL DEFAULT '',
  desclassificada_em DATE, motivo_desclassificacao TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), atualizado_por TEXT NOT NULL DEFAULT ''
);
