-- Credenciais de API do PRÓPRIO órgão (25/11/2026): YouTube Data API e Meta Graph API. Banco de cada ÓRGÃO. Idempotente.
-- Cadastradas pelo admin do portal (Administração → Credenciais de API), CIFRADAS (Fernet, CHAVE_CREDENCIAIS do .env, igual em
-- todos os nós); só gravação: nenhuma tela devolve o valor. Cada órgão usa só a sua; não há credencial da plataforma para estas fontes.
CREATE TABLE IF NOT EXISTS credenciais_orgao (
  fonte TEXT PRIMARY KEY,
  dados TEXT NOT NULL,
  configurada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  configurada_por TEXT NOT NULL,
  testada_em TIMESTAMPTZ,
  testada_por TEXT NOT NULL DEFAULT '',
  teste_resultado TEXT NOT NULL DEFAULT ''
);
