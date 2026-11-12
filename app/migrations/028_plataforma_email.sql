-- E-mail de saída configurado no console (12/11/2026) e convites de primeiro acesso do administrador do órgão. Banco de CONTROLE. Idempotente.
-- A senha do SMTP fica CIFRADA (mesma chave das credenciais de fontes, CHAVE_CREDENCIAIS); nenhuma tela a devolve.
CREATE TABLE IF NOT EXISTS email_saida (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  servidor TEXT NOT NULL, porta INT NOT NULL, seguranca TEXT NOT NULL CHECK (seguranca IN ('ssl','starttls','nenhuma')),
  usuario TEXT NOT NULL DEFAULT '', senha_cifrada TEXT NOT NULL DEFAULT '',
  remetente TEXT NOT NULL, remetente_nome TEXT NOT NULL DEFAULT '',
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(), atualizado_por TEXT NOT NULL DEFAULT '',
  teste_em TIMESTAMPTZ, teste_por TEXT NOT NULL DEFAULT '', teste_resultado TEXT NOT NULL DEFAULT ''
);
-- Convite de primeiro acesso: o link (token) só existe em claro até o e-mail sair; o banco do órgão guarda só o hash.
CREATE TABLE IF NOT EXISTS convites (
  id BIGSERIAL PRIMARY KEY, orgao_id INT NOT NULL REFERENCES orgaos(id) ON DELETE CASCADE, email TEXT NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'aguardando' CHECK (situacao IN ('aguardando','enviado','usado','vencido','cancelado','erro')),
  token_cifrado TEXT, expira_em TIMESTAMPTZ NOT NULL, ordem_id BIGINT,
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), criado_por TEXT NOT NULL DEFAULT '', enviado_em TIMESTAMPTZ, tentativa_em TIMESTAMPTZ,
  mensagem TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS convites_orgao_idx ON convites (orgao_id, id DESC);
CREATE INDEX IF NOT EXISTS convites_pend_idx ON convites (situacao) WHERE situacao = 'aguardando';
