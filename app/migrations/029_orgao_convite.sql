-- Convite de primeiro acesso (12/11/2026). Banco de CADA ÓRGÃO. Idempotente.
-- Só o HASH do link fica aqui; ao usar o link, o próprio administrador cria a senha e cadastra o segundo fator.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS convite_hash TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS convite_expira TIMESTAMPTZ;
