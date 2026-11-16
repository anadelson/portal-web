-- Política de aprovação para publicar (15/11/2026): comunicados ganham "em aprovação" e "devolvido";
-- Conheça e álbuns ganham o pedido de aprovação; foto enviada por quem não aprova fica fora do ar até a aprovação.
ALTER TABLE comunicados DROP CONSTRAINT IF EXISTS comunicados_situacao_check;
ALTER TABLE comunicados ADD CONSTRAINT comunicados_situacao_check CHECK (situacao IN ('rascunho','revisao','devolvido','publicado','arquivado'));
ALTER TABLE comunicados ADD COLUMN IF NOT EXISTS comentario TEXT NOT NULL DEFAULT '';
ALTER TABLE perfis ADD COLUMN IF NOT EXISTS aguarda_aprovacao BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE perfis ADD COLUMN IF NOT EXISTS comentario TEXT NOT NULL DEFAULT '';
ALTER TABLE perfis ADD COLUMN IF NOT EXISTS autor TEXT NOT NULL DEFAULT '';
ALTER TABLE albuns ADD COLUMN IF NOT EXISTS aguarda_aprovacao BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE albuns ADD COLUMN IF NOT EXISTS comentario TEXT NOT NULL DEFAULT '';
ALTER TABLE albuns ADD COLUMN IF NOT EXISTS autor TEXT NOT NULL DEFAULT '';
ALTER TABLE perfil_fotos ADD COLUMN IF NOT EXISTS aguarda_aprovacao BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE album_fotos ADD COLUMN IF NOT EXISTS aguarda_aprovacao BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE perfil_videos ADD COLUMN IF NOT EXISTS aguarda_aprovacao BOOLEAN NOT NULL DEFAULT FALSE;
