# Instruções para o Claude Code — código dos Portais de Borá

Leia o README.md. Regras:
- Um código para todos os órgãos; nada de código específico por órgão — diferenças vão para configuração/banco.
- Um banco por órgão; a Câmara lê dados da Prefeitura só por API pública.
- Toda página de transparência mostra "Base legal:"; nunca apresentar dado inventado como real; marcar exemplos.
- LGPD: não exibir dados pessoais de solicitantes; CPF nunca completo.
- Na VPS: nunca mostrar senhas/.env; mudanças só com aprovação; snapshot antes; registrar em PROGRESSO.md (pasta acima).
- Testes: `tests/teste_fluxos.py` só contra banco de TESTE.
