-- Rodapé com imagem de fundo, camada de cor e mascote (16/11/2026): grava os padrões sem sobrescrever o que o órgão já escolheu.
-- Camada 85%; mascote exibido, à esquerda, 220 px, 100% visível, fora do celular, suspenso no período eleitoral.
-- A cor do rodapé (identidade.cor_rodape) e a imagem de fundo (identidade.rodape) começam vazias: o rodapé fica como antes.
INSERT INTO config (chave, valor) VALUES ('rodape', '{"camada": 85, "mascote_exibir": true, "mascote_lado": "esq", "mascote_altura": 220, "mascote_opacidade": 100, "mascote_celular": false, "mascote_suspender_eleitoral": true}'::jsonb)
ON CONFLICT (chave) DO NOTHING;
