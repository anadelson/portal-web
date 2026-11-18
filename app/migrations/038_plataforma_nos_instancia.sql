-- Mais de um nó na mesma VPS (18/11/2026): instância do nó = pasta /opt/portal_web-<instância> na VPS do nó.
-- Vazio = a instalação de sempre (/opt/portal_web). Vai no pacote de segredos e nos comandos da tela "Instalação do nó".
ALTER TABLE nos ADD COLUMN IF NOT EXISTS instancia TEXT NOT NULL DEFAULT '';
DO $$ BEGIN
  ALTER TABLE nos ADD CONSTRAINT nos_instancia_formato CHECK (instancia ~ '^[a-z0-9]{0,20}$');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
