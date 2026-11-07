# Projeto Portais de Borá — instruções para o Claude Code

## Contexto
Plataforma multi-órgão (multi-tenant) de portais públicos municipais:
- Console do gestor (cadastro de órgãos/tenants, licenças, catálogo de módulos, editor de regiões)
- Portal da Prefeitura de Borá + painel administrativo em /admin
- Portal da Câmara Municipal de Borá + painel administrativo em /admin
Fase atual: PILOTO FUNCIONAL em URLs provisórias. DNS administrado na Hostinger (domínio conectatech.tech).

## Endereços do piloto
| URL | Uso |
|---|---|
| https://gestao.conectatech.tech | Console do gestor (tenants, licenças, catálogo, regiões) |
| https://pmbora.conectatech.tech | Portal da Prefeitura de Borá |
| https://pmbora.conectatech.tech/admin | Painel administrativo da Prefeitura |
| https://cmbora.conectatech.tech | Portal da Câmara Municipal de Borá |
| https://cmbora.conectatech.tech/admin | Painel administrativo da Câmara |
Cada subdomínio precisa de registro DNS tipo A apontando para o IP da VPS (e AAAA, se a VPS tiver IPv6). Os domínios oficiais (bora.sp.gov.br, camarabora.sp.gov.br) só entram depois do piloto aprovado, sem mudar código: o domínio é configuração do tenant.
Destino do código na VPS: /opt/portal_web

## Decisões já tomadas (não mudar sem perguntar)
- Um servidor PostgreSQL com UM BANCO POR ÓRGÃO (bd_pm_bora, bd_cm_bora) + serviço compartilhado de dados públicos (somente leitura).
- Câmara lê dados da Prefeitura (ex.: execução de emendas) pela API pública, nunca direto no banco.
- Frontend: tema base com personalização nível 2 (blocos); tema próprio (nível 3) só sob demanda.
- Docker Compose: app, worker, agendador, PostgreSQL, Redis. Proxy/SSL: **nginx já existente na VPS** (container `nginx` do projeto hotspot, certificados pelo `certbot` existente), com 3 vhosts para os domínios do piloto — decidido em 2026-11-06 porque 80/443 já estão ocupadas; o projeto não publica 80/443 nem usa Caddy próprio.
- Capacidade: seguir no plano atual (1 vCPU, 3,8 GiB, VPS compartilhada com outros 5 sistemas) com **limite de memória em todo container** (`mem_limit`), total do projeto ≤ 1,3 GiB — orçamento em PROGRESSO.md. Decidido em 2026-11-06; upgrade só se o piloto mostrar falta de memória.
- Toda página de transparência mostra "Base legal:"; nada inventado é apresentado como dado real; LGPD (CPF mascarado).
- Diário Oficial segue a Lei 910/2026 e o decreto de 25/03/2026 de Borá.

## Regras de trabalho na VPS
1. FASE 1 É SÓ LEITURA: não instalar, não alterar, não reiniciar nada sem aprovação explícita do usuário.
2. Usar sempre `ssh -o BatchMode=yes` (sem prompt de senha). Se falhar por senha, parar e pedir ao usuário para configurar a chave SSH.
3. Nunca exibir, copiar ou registrar senhas, chaves privadas, tokens ou conteúdo de arquivos .env.
4. Antes de qualquer mudança: confirmar que existe snapshot recente da VPS no painel da Hostinger.
5. Registrar o andamento em PROGRESSO.md nesta pasta (o que foi feito, o que falta, onde parou).

## Tarefa atual (Fase 1 — diagnóstico)
Ver PEDIDO-FASE1.md.
