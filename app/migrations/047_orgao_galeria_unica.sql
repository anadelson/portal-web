-- Vídeos e câmeras ao vivo na mesma seção (26/11/2026), em 2 colunas (bloco "videos"); o bloco "cameras" sai. Idempotente.
DELETE FROM blocos WHERE pagina='home' AND chave='cameras';
