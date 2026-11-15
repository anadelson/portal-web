-- Texto alternativo opcional (pedido do órgão, 14/11/2026). Banco do ÓRGÃO. Idempotente.
-- Vazio = imagem decorativa (alt=""); na galeria do portal, o título da foto ou "Foto N do álbum" ocupa o lugar.
ALTER TABLE album_fotos DROP CONSTRAINT IF EXISTS album_fotos_alt_check;
ALTER TABLE perfil_fotos DROP CONSTRAINT IF EXISTS perfil_fotos_alt_check;
