-- Agenda de execução das integrações, escolhida pelo órgão no painel (Integrações → Agenda). Banco de CONTROLE. Idempotente.
-- NULL = padrão do sistema (o mesmo agendamento que já rodava).
ALTER TABLE fontes ADD COLUMN IF NOT EXISTS agenda JSONB;
