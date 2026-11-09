-- Fase 10: Carta de Serviços ao Usuário (Lei 13.460/2017). Idempotente.
CREATE TABLE IF NOT EXISTS secretarias (
  id SERIAL PRIMARY KEY, nome TEXT NOT NULL UNIQUE, sigla TEXT NOT NULL DEFAULT '', responsavel_id INT REFERENCES usuarios(id) ON DELETE SET NULL,
  unidades TEXT NOT NULL DEFAULT '', ativa BOOLEAN NOT NULL DEFAULT TRUE, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- servidor designado para validar no lugar do responsável (com o ato de designação)
CREATE TABLE IF NOT EXISTS designacoes_carta (
  id SERIAL PRIMARY KEY, secretaria_id INT NOT NULL REFERENCES secretarias(id) ON DELETE CASCADE, usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  ato_tipo TEXT NOT NULL, ato_numero TEXT NOT NULL, ato_data DATE NOT NULL, ate DATE, criado_por TEXT NOT NULL, criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- vínculo do usuário redator/validador com a secretaria
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS secretaria_id INT REFERENCES secretarias(id) ON DELETE SET NULL;
CREATE TABLE IF NOT EXISTS servicos (
  id SERIAL PRIMARY KEY, slug TEXT NOT NULL UNIQUE, nome TEXT NOT NULL, descricao TEXT NOT NULL DEFAULT '',
  secretaria_id INT REFERENCES secretarias(id) ON DELETE SET NULL, setor TEXT NOT NULL DEFAULT '', categoria TEXT NOT NULL DEFAULT '',
  publicos TEXT[] NOT NULL DEFAULT '{}', sinonimos TEXT NOT NULL DEFAULT '',
  requisitos TEXT NOT NULL DEFAULT '', documentos TEXT NOT NULL DEFAULT '', etapas TEXT NOT NULL DEFAULT '', prazo TEXT NOT NULL DEFAULT '',
  formas TEXT[] NOT NULL DEFAULT '{}', locais TEXT NOT NULL DEFAULT '', custo TEXT NOT NULL DEFAULT '', custo_base_legal TEXT NOT NULL DEFAULT '',
  prioridades TEXT NOT NULL DEFAULT '', tempo_espera TEXT NOT NULL DEFAULT '', comunicacao TEXT NOT NULL DEFAULT '', manifestacoes TEXT NOT NULL DEFAULT '',
  acompanhamento TEXT NOT NULL DEFAULT '', link_online TEXT NOT NULL DEFAULT '', legislacao TEXT NOT NULL DEFAULT '',
  situacao TEXT NOT NULL DEFAULT 'rascunho' CHECK (situacao IN ('rascunho','em_validacao','devolvido','autorizado','publicado','arquivado')),
  comentario TEXT NOT NULL DEFAULT '', autorizado_por TEXT NOT NULL DEFAULT '', autorizado_em TIMESTAMPTZ, autorizado_ato TEXT NOT NULL DEFAULT '', autorizado_hash TEXT NOT NULL DEFAULT '',
  publicado_por TEXT NOT NULL DEFAULT '', publicado_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(), revisar_em DATE,
  ordem INT NOT NULL DEFAULT 100, exemplo BOOLEAN NOT NULL DEFAULT FALSE, criado_por TEXT NOT NULL DEFAULT '', criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS servico_versoes (
  id SERIAL PRIMARY KEY, servico_id INT NOT NULL REFERENCES servicos(id) ON DELETE CASCADE, situacao TEXT NOT NULL, quem TEXT NOT NULL,
  comentario TEXT NOT NULL DEFAULT '', dados JSONB NOT NULL, quando TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- avaliação continuada (arts. 23 e 24): nota 1–5, conseguiu?, comentário moderado; sem dado pessoal (IP só como hash, como na Fase 9)
CREATE TABLE IF NOT EXISTS servico_avaliacoes (
  id BIGSERIAL PRIMARY KEY, servico_id INT NOT NULL REFERENCES servicos(id) ON DELETE CASCADE, nota INT NOT NULL CHECK (nota BETWEEN 1 AND 5),
  conseguiu BOOLEAN, comentario TEXT NOT NULL DEFAULT '', moderacao TEXT NOT NULL DEFAULT 'pendente', ip_hash TEXT NOT NULL DEFAULT '', criado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS servico_acessos (servico_id INT NOT NULL REFERENCES servicos(id) ON DELETE CASCADE, mes TEXT NOT NULL, n INT NOT NULL DEFAULT 0, PRIMARY KEY (servico_id, mes));
-- manifestação da Ouvidoria ligada a um serviço (opcional)
ALTER TABLE esic ADD COLUMN IF NOT EXISTS servico_id INT REFERENCES servicos(id) ON DELETE SET NULL;
-- cópia congelada do que está no ar (o portal só lê isto); editar a ficha não muda o público até nova validação e publicação
ALTER TABLE servicos ADD COLUMN IF NOT EXISTS publicado_dados JSONB;
-- perfis novos da Carta (redator e validador por secretaria); lista completa (a migração roda de novo a cada atualização)
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil IN ('admin','editor','publicador','procuradoria','remetente','redator','validador'));
