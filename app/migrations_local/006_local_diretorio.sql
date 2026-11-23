-- Diretório de órgãos parceiros (23/11/2026): os órgãos do mesmo município que estão em OUTRA instalação (outro nó).
-- Vem da gestão, assinado (Ed25519), junto com as licenças; o nó só lê. Sem dado pessoal: nome, tipo, domínio e serviços.
CREATE TABLE IF NOT EXISTS orgaos_parceiros (
  id INT PRIMARY KEY,                       -- id do órgão no cadastro da gestão
  slug TEXT NOT NULL UNIQUE,
  nome TEXT NOT NULL,
  tipo TEXT NOT NULL,
  dominio TEXT NOT NULL,
  ibge TEXT NOT NULL,
  municipio TEXT NOT NULL DEFAULT '',
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  servicos JSONB NOT NULL DEFAULT '[]',     -- módulos disponíveis no parceiro (ex.: ["ouv","sic","diario"])
  hospedagem TEXT NOT NULL DEFAULT '',      -- nome do nó que serve o parceiro ('' = a própria gestão)
  recebido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
