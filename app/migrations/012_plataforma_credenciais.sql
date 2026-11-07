-- Fase 7 (fontes). Banco de CONTROLE. Idempotente.
-- Credenciais de fontes de dados cadastradas pelo console do gestor. O usuário e a senha ficam CIFRADOS (Fernet,
-- chave CHAVE_CREDENCIAIS do .env) num único campo; a tela nunca devolve os valores.
CREATE TABLE IF NOT EXISTS credenciais_fontes (
  fonte TEXT PRIMARY KEY,
  dados TEXT NOT NULL,                 -- token Fernet de {"usuario": ..., "senha": ...}
  configurada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  configurada_por TEXT NOT NULL,
  testada_em TIMESTAMPTZ,
  testada_por TEXT NOT NULL DEFAULT '',
  teste_resultado TEXT NOT NULL DEFAULT ''
);
