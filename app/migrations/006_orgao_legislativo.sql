-- Fase 5 (Câmara completa). Banco de CADA ÓRGÃO (as tabelas existem em todos; só o Legislativo usa a maioria). Idempotente.
-- Votos, presenças e atas NUNCA são pré-preenchidos: só entram quando a Secretaria registra ou importa de arquivo oficial.

-- Mesa: eleição e posse de cada biênio
CREATE TABLE IF NOT EXISTS mesa_bienios (
  legislatura INT NOT NULL, bienio TEXT NOT NULL, eleicao DATE, posse DATE, ato TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (legislatura, bienio)
);
-- Proposições: relator, datas e autoria estruturada
ALTER TABLE proposicoes ADD COLUMN IF NOT EXISTS relator TEXT NOT NULL DEFAULT '';
ALTER TABLE proposicoes ADD COLUMN IF NOT EXISTS apresentada DATE;
ALTER TABLE proposicoes ADD COLUMN IF NOT EXISTS criado_em TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE proposicoes ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'cadastro';   -- cadastro | importacao | seed
CREATE TABLE IF NOT EXISTS proposicao_autores (
  id SERIAL PRIMARY KEY,
  proposicao_id INT NOT NULL REFERENCES proposicoes(id) ON DELETE CASCADE,
  vereador_id INT REFERENCES vereadores(id),
  nome TEXT NOT NULL,                       -- nome do vereador, "Poder Executivo", "Mesa Diretora", "Comissão de ..."
  UNIQUE (proposicao_id, nome)
);
CREATE TABLE IF NOT EXISTS tramitacao (
  id SERIAL PRIMARY KEY,
  proposicao_id INT NOT NULL REFERENCES proposicoes(id) ON DELETE CASCADE,
  data DATE NOT NULL, fase TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
  sessao_id INT, origem TEXT NOT NULL DEFAULT 'cadastro', registrado_por TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tramitacao_prop_idx ON tramitacao (proposicao_id, data);
-- Documentos em PDF (texto, parecer, autógrafo, lei, ata, parecer do TCESP, decreto legislativo...)
CREATE TABLE IF NOT EXISTS documentos (
  id SERIAL PRIMARY KEY,
  arquivo TEXT UNIQUE NOT NULL, tipo TEXT NOT NULL, titulo TEXT NOT NULL,
  descricao TEXT NOT NULL,                  -- descrição acessível do conteúdo (obrigatória)
  proposicao_id INT REFERENCES proposicoes(id) ON DELETE CASCADE,
  sessao_id INT REFERENCES sessoes(id) ON DELETE CASCADE,
  comissao_id INT, contas_id INT,
  bytes INT NOT NULL, enviado_por TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Comissões (PNTP 20.5)
CREATE TABLE IF NOT EXISTS comissoes (
  id SERIAL PRIMARY KEY, nome TEXT UNIQUE NOT NULL,
  tipo TEXT NOT NULL DEFAULT 'permanente' CHECK (tipo IN ('permanente','temporaria')),
  finalidade TEXT NOT NULL DEFAULT '', inicio DATE, fim DATE, ativa BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS comissao_membros (
  comissao_id INT NOT NULL REFERENCES comissoes(id) ON DELETE CASCADE,
  vereador_id INT NOT NULL REFERENCES vereadores(id),
  cargo TEXT NOT NULL DEFAULT 'Membro',     -- Presidente | Relator | Membro
  PRIMARY KEY (comissao_id, vereador_id)
);
CREATE TABLE IF NOT EXISTS comissao_reunioes (
  id SERIAL PRIMARY KEY, comissao_id INT NOT NULL REFERENCES comissoes(id) ON DELETE CASCADE,
  data DATE NOT NULL, hora TEXT NOT NULL DEFAULT '', pauta TEXT NOT NULL DEFAULT '', publicada BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS pareceres (
  id SERIAL PRIMARY KEY, comissao_id INT NOT NULL REFERENCES comissoes(id) ON DELETE CASCADE,
  proposicao_id INT REFERENCES proposicoes(id) ON DELETE CASCADE,
  relator TEXT NOT NULL DEFAULT '', conclusao TEXT NOT NULL, texto TEXT NOT NULL DEFAULT '', data DATE NOT NULL,
  documento_id INT REFERENCES documentos(id), publicado BOOLEAN NOT NULL DEFAULT FALSE
);
-- Sessões: tipo, votação e ata em PDF
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'Ordinária';
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS votacao_publicada BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'cadastro';
CREATE TABLE IF NOT EXISTS pauta_itens (
  id SERIAL PRIMARY KEY, sessao_id INT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  ordem INT NOT NULL DEFAULT 0, proposicao_id INT REFERENCES proposicoes(id),
  descricao TEXT NOT NULL DEFAULT '', fase TEXT NOT NULL DEFAULT 'Discussão e votação única',
  quorum TEXT NOT NULL DEFAULT 'simples' CHECK (quorum IN ('simples','absoluta','dois_tercos')),
  resultado TEXT CHECK (resultado IN ('aprovado','rejeitado','retirado','adiado')),
  votado_em TIMESTAMPTZ, contas_id INT
);
CREATE TABLE IF NOT EXISTS votos (
  item_id INT NOT NULL REFERENCES pauta_itens(id) ON DELETE CASCADE,
  vereador_id INT NOT NULL REFERENCES vereadores(id),
  voto TEXT NOT NULL CHECK (voto IN ('sim','nao','abstencao','ausente')),
  origem TEXT NOT NULL DEFAULT 'cadastro',
  PRIMARY KEY (item_id, vereador_id)
);
ALTER TABLE presencas ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'cadastro';
-- Julgamento das contas do Prefeito (PNTP 20.8; Constituição, art. 31, §§ 1º e 2º)
CREATE TABLE IF NOT EXISTS contas_julgamento (
  id SERIAL PRIMARY KEY, exercicio INT UNIQUE NOT NULL, responsavel TEXT NOT NULL,
  tce_processo TEXT NOT NULL DEFAULT '', tce_parecer TEXT NOT NULL DEFAULT '',   -- favorável | desfavorável
  comissao_parecer TEXT NOT NULL DEFAULT '', pauta_item_id INT REFERENCES pauta_itens(id),
  decreto TEXT NOT NULL DEFAULT '', resultado TEXT NOT NULL DEFAULT '', publicado BOOLEAN NOT NULL DEFAULT FALSE
);
-- Diárias e verbas dos vereadores e servidores da Câmara (PNTP 20.10)
CREATE TABLE IF NOT EXISTS diarias_legislativo (
  id BIGSERIAL PRIMARY KEY, chave TEXT UNIQUE NOT NULL, fonte TEXT NOT NULL DEFAULT 'cadastro', coletado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
  ano INT NOT NULL, beneficiario TEXT NOT NULL, cargo TEXT NOT NULL DEFAULT '', destino TEXT NOT NULL DEFAULT '', motivo TEXT NOT NULL DEFAULT '',
  inicio DATE, fim DATE, valor NUMERIC(14,2) NOT NULL
);
-- Transmissões (PNTP 20.9)
CREATE TABLE IF NOT EXISTS transmissoes (
  id SERIAL PRIMARY KEY, titulo TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT 'Sessão',
  previsto_para TIMESTAMPTZ, video TEXT NOT NULL DEFAULT '',      -- ID do vídeo do YouTube ou URL https do player
  sessao_id INT REFERENCES sessoes(id) ON DELETE SET NULL,
  ao_vivo BOOLEAN NOT NULL DEFAULT FALSE, iniciada_em TIMESTAMPTZ, encerrada_em TIMESTAMPTZ,
  capitulos JSONB NOT NULL DEFAULT '[]', legendas BOOLEAN NOT NULL DEFAULT FALSE, libras BOOLEAN NOT NULL DEFAULT FALSE
);
-- Participação (dados pessoais só para a Secretaria; nunca exibidos no portal)
CREATE TABLE IF NOT EXISTS tribuna_inscricoes (
  id SERIAL PRIMARY KEY, sessao_id INT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
  nome TEXT NOT NULL, contato TEXT NOT NULL, tema TEXT NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','deferida','indeferida')),
  motivo TEXT NOT NULL DEFAULT '', criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS opinioes (
  id SERIAL PRIMARY KEY, proposicao_id INT NOT NULL REFERENCES proposicoes(id) ON DELETE CASCADE,
  posicao TEXT NOT NULL CHECK (posicao IN ('favor','contra','sugestao')), texto TEXT NOT NULL,
  situacao TEXT NOT NULL DEFAULT 'pendente' CHECK (situacao IN ('pendente','publicada','rejeitada')),
  motivo TEXT NOT NULL DEFAULT '', criado_em TIMESTAMPTZ NOT NULL DEFAULT now(), moderado_em TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS avaliacoes (
  id BIGSERIAL PRIMARY KEY, pagina TEXT NOT NULL, util BOOLEAN NOT NULL, comentario TEXT NOT NULL DEFAULT '',
  criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS importacoes (
  id SERIAL PRIMARY KEY, modelo TEXT NOT NULL, arquivo TEXT NOT NULL, linhas INT NOT NULL, gravadas INT NOT NULL,
  erros JSONB NOT NULL DEFAULT '[]', simulacao BOOLEAN NOT NULL, quem TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
