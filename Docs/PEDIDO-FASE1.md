# Fase 1 — Diagnóstico da VPS (somente leitura)

Cole no Claude Code, trocando USUARIO e IP:

---
Leia o CLAUDE.md desta pasta. Depois:
1. Teste a conexão: `ssh -o BatchMode=yes -o ConnectTimeout=10 USUARIO@IP "echo conectado; hostname"`.
   Se pedir senha ou falhar, pare e me explique como configurar a chave SSH.
2. Rode o diagnóstico somente leitura desta pasta na VPS e salve o resultado aqui:
   `ssh -o BatchMode=yes USUARIO@IP "tr -d '\r' | bash -s -- gestao.conectatech.tech pmbora.conectatech.tech cmbora.conectatech.tech" < diag-vps.sh > diagnostico-vps.txt`
3. Confira se o arquivo diagnostico-vps.txt foi gerado e não está vazio.
4. Escreva em PROGRESSO.md um resumo do que encontrou (recursos, portas 80/443, firewall, SSH, Docker, /opt, saída para internet, e se os 3 subdomínios já apontam para o IP público da VPS) e os riscos para instalar o projeto em /opt/portal_web.
Não altere nada na VPS.
---
