# Fase 2 — Implantar o piloto na VPS (/opt/portal_web)

Pré-requisitos: Fase 1 concluída (diagnostico-vps.txt e PROGRESSO.md), snapshot da VPS feito, registros DNS A de gestao, pmbora e cmbora (conectatech.tech) apontando para o IP da VPS.

Cole no Claude Code (troque USUARIO e IP_DA_VPS):

---
Trabalhe na pasta C:\Users\BORA\Documents\portais-bora. Leia CLAUDE.md, PROGRESSO.md, diagnostico-vps.txt e portal_web\README.md.

Objetivo: implantar o piloto (pasta portal_web) na VPS USUARIO@IP_DA_VPS em /opt/portal_web, com os domínios gestao.conectatech.tech, pmbora.conectatech.tech e cmbora.conectatech.tech.

Regras: use ssh -o BatchMode=yes; antes de CADA comando que altere a VPS, mostre o comando e espere minha aprovação; nunca mostre senhas nem o conteúdo do .env; registre tudo em PROGRESSO.md.

1. Confirme comigo que o snapshot da VPS foi feito.
2. Verifique (só leitura): DNS dos 3 domínios = IP da VPS; portas 80/443 livres; Docker e Docker Compose instalados. Se algo faltar, proponha o passo (ex.: instalar Docker pelo repositório oficial, liberar 80/443 no firewall, parar um serviço que use a porta 80) e espere aprovação.
3. Copie a pasta portal_web para /opt/portal_web (scp -r; crie a pasta com sudo e ajuste o dono para o usuário de deploy).
4. Na VPS, crie /opt/portal_web/.env a partir de .env.example gerando valores fortes com openssl rand para PG_PASSWORD, SECRET_KEY, SENHA_INICIAL_GESTOR e SENHA_INICIAL_ADMIN; EMAIL_SSL = um e-mail que eu informar; chmod 600. Não me mostre os valores: me diga o comando para eu ler as senhas iniciais direto na VPS.
5. Rode: docker compose up -d --build; depois docker compose exec app python -m app.provision init.
6. Teste: docker compose ps; curl -sI https://gestao.conectatech.tech, https://pmbora.conectatech.tech e https://cmbora.conectatech.tech (esperado 200 ou 303 e certificado válido); docker compose logs --tail 50 app worker caddy.
7. Rode uma coleta: docker compose exec app python -m app.worker uma-vez e anote o resultado (falhas de coletor não bloqueiam o piloto).
8. Proponha o agendamento do backup (deploy/backup.sh no crontab às 2h) e espere aprovação.
9. Atualize PROGRESSO.md com o que foi feito, endereços, como acessar e pendências. Pare e me mostre o resumo.
---
