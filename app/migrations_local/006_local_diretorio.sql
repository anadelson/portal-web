-- Banco LOCAL do nó (23/11/2026): DIRETÓRIO dos órgãos parceiros do município, recebido da gestão junto com as licenças
-- (assinado com a mesma chave). Com ele, Prefeitura e Câmara em instalações diferentes continuam conversando: o nó sabe
-- onde está o parceiro (domínio, serviços) e recebe da gestão os tokens dos pares (pares_orgaos). Sem banco nem dado pessoal.
CREATE TABLE IF NOT EXISTS orgaos_parceiros (
  id INT PRIMARY KEY, slug TEXT NOT NULL, nome TEXT NOT NULL, tipo TEXT NOT NULL, dominio TEXT NOT NULL, ibge TEXT NOT NULL DEFAULT '',
  ativo BOOLEAN NOT NULL DEFAULT TRUE, modulos JSONB NOT NULL DEFAULT '[]', hospedagem TEXT NOT NULL DEFAULT '',
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS diretorio_estado (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1), emitido_em TIMESTAMPTZ, recebido_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
