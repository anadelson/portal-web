# PROGRESSO — Portais de Borá · Fase 1 (diagnóstico somente leitura)

Data: 2026-11-06 (UTC) · Host: `srv1598950` · IP público: `76.13.167.181` / `2a02:4780:6e:eab3::1`

> **Observação de ambiente:** a sessão do Claude Code roda **diretamente na VPS** (como `root`), não no Windows.
> Os arquivos da pasta do Windows foram copiados para `/opt/portal_web/Docs`; o `CLAUDE.md` foi lido e seguido.
> Por isso o SSH (regra 2) não se aplicou: o `diag-vps.sh` foi revisado (somente leitura) e executado localmente.
> Arquivos nesta pasta:
> - `diagnostico-vps.txt` — saída do `diag-vps.sh` (469 linhas, sem erros; permissão 600).
> - `diagnostico-complementar.txt` — comandos extras de leitura (containers, nginx, certificados, DNS externo, saída).

## 1. Resumo da VPS
| Item | Valor |
|---|---|
| Sistema | Ubuntu 24.04.4 LTS, kernel 6.8.0-147, uptime 14 dias |
| CPU | **1 vCPU** (AMD EPYC 9355P) — load 1,71 / 0,90 / 0,53 no momento |
| Memória | **3,8 GiB** total · 1,8 GiB usada · ~2,0 GiB disponível |
| Swap | 4 GiB (`/swapfile`) · **1,2 GiB já em uso** |
| Disco | `/` 48 GB · 31 GB usados (65%) · **18 GB livres**; Docker: 14,7 GB em imagens (6,6 GB recuperáveis) |
| Fuso | **Etc/UTC**, NTP ativo e sincronizado |

## 2. Portas em uso
| Porta | Quem ocupa |
|---|---|
| **80/tcp, 443/tcp** (v4+v6) | container **`nginx`** (projeto Compose `hotspot`) — proxy reverso de todos os sites atuais |
| 22/tcp | sshd |
| 8088/tcp | `mei-nginx` (rede host; liberado só p/ redes Docker internas) |
| 127.0.0.1:3050 | `mei-firebird` |
| 172.17.0.1:18080 | `pmunix-central-caddy` (atrás do nginx) |
| 51820/udp | wg-easy (WireGuard) |
| 1812-1813/udp | freeradius |
| 53 (local) / 5353 udp | systemd-resolved / avahi |

Sites já atendidos pelo nginx: conectatech.tech, hotspot, casemaster.hotspot, controle-hotspot, evolution, api-hotspot,
evo.vendasgov, vendasgov, mei, pmunix, wg-hotspot (todos `*.conectatech.tech`). Certificados via container `certbot` (webroot).
`default.conf` atende `listen 80 default_server` com ACME challenge.

## 3. Firewall e SSH
- **UFW ativo**: entrada negada por padrão; liberados 22, 80, 443, 51820/udp, 1812-1813/udp; 8088 só de 172.17/16 e 172.22/16. (Regra 22/tcp duplicada — inofensiva.)
- **SSH**: porta 22, `PermitRootLogin yes`, **`PasswordAuthentication yes`**, chave pública habilitada (1 chave em `/root/.ssh/authorized_keys`). Usuário extra: `deploy`.
- **fail2ban ativo**: jails `sshd`, `nginx-http-auth`, `hotspot-auth`.

## 4. O que já está instalado/rodando
- **Docker 29.5.1 + Compose v5.1.3** · 29 containers, todos rodando · 5 projetos Compose:
  `conectatech` (/opt/conectatech), `hotspot` (/opt/hotspot, 11 containers, dono do nginx 80/443), `pmunix-central`
  (/opt/conectatech/pmunix-central), `sistemamei` (/opt/sistemamei), `vendasgov` (/opt/vendasgov).
- **Proxy web**: nginx 1.26 (container), Caddy 2.8 interno do pmunix-central. **Nada** de nginx/apache/caddy/traefik instalado no host.
- **Bancos (todos em container, sem porta pública)**: 3× PostgreSQL 16, 2× MySQL 8.0, 3× Redis 7, Firebird 5, Meilisearch.
- **Outros**: 3× Evolution API (WhatsApp), wg-easy, freeradius, **autoheal** (reinicia containers com label `autoheal`), certbot.
- **No host**: Node 22.23.1, npm 10.9.8, Python 3.12.3. Sem PostgreSQL/Redis/PHP/Java/Go no host.
- Serviços do host relevantes: docker, containerd, fail2ban, cron, unattended-upgrades, qemu-guest-agent. **Nenhum serviço com falha.**
- Usuários com shell: `root` e `deploy` (este no grupo `sudo`).
- Cron: sem crontab do root; em `/etc/cron.d`: docker-builder-prune, e2scrub_all, hotspot-radius, sysstat.
- **74 pacotes com atualização pendente**; sem reinício pendente. `vm.swappiness=60`, limite de arquivos abertos 1.048.576.

## 5. /opt e /opt/portal_web
- `/opt/portal_web` existe, dono `root:root`, 755. Contém apenas `Docs/` (arquivos do projeto + estes relatórios); ainda sem código.
- ⚠️ `Docs/` está com permissão `drwsrwsrwt` (gravável por qualquer usuário). Recomenda-se corrigir para 755 — **não alterado**, aguarda aprovação.
- Demais em /opt: conectatech 249M, hotspot 502M (dono `deploy`), pmunix 1,1M, pmunix-src 522M, sistemamei 229M, vendasgov 899M.
- Atenção: `/opt/pmunix` e `/opt/sistemamei` têm permissão `drwsrwsrwt` (gravável por todos) — não é do nosso projeto, só registro.

## 6. Saída para a internet
| Destino | Resultado |
|---|---|
| Siconfi (apidatalake.tesouro.gov.br) | 200 OK |
| IBGE (servicodados.ibge.gov.br) | 200 OK |
| PNCP API (pncp.gov.br/api/...) | 200 OK (a raiz `https://pncp.gov.br` dá erro de conexão — "falhou" no script —, mas a API responde) |
| npm registry | 200 OK |
| Docker Hub | 401 (normal, sem login = acessível) |
| Fiorilli Borá (`borasp.dcfiorilli.com.br:879`) | raiz 403 (IIS), mas **`/Transparencia/` responde 200** — acessível |

## 7. DNS (consultado em 1.1.1.1)
- `gestao`, `pmbora`, `cmbora` `.conectatech.tech` → **A = 76.13.167.181** ✅ (IP desta VPS). Sem AAAA, sem CAA.
- Não há wildcard (subdomínio aleatório não resolve). NS: Hostinger (dns-parking.com).

## 8. Riscos e conflitos para o Docker Compose em /opt/portal_web
1. **80/443 ocupadas pelo nginx do `hotspot`** — conflita com a decisão do CLAUDE.md ("proxy Caddy com SSL automático para os 3 domínios"); **precisa da sua decisão**. O Caddy do projeto **não pode** publicar 80/443. Opções:
   (a) adicionar 3 vhosts no nginx existente apontando para o app via rede Docker compartilhada + certificados pelo certbot existente (**recomendado**, mesmo padrão dos outros sites); ou
   (b) manter o Caddy do projeto sem TLS numa porta interna (ex.: `172.17.0.1:18081`), com o nginx na frente — igual ao `pmunix-central`.
   Qualquer opção exige **mexer na config do nginx do hotspot** e recarregá-lo — afeta todos os sites.
2. **Memória/CPU apertadas**: 1 vCPU, 3,8 GiB, swap já com 1,2 GiB em uso e 29 containers. Somar app + worker + agendador + PostgreSQL (2 bancos) + Redis pode gerar lentidão/OOM afetando os outros sistemas. Recomenda-se **limites de memória** por container (`mem_limit`), Postgres com `shared_buffers` baixo, Redis com `maxmemory` — ou **upgrade do plano** (ex.: 2 vCPU / 8 GB).
3. **Disco**: 18 GB livres é suficiente para o piloto, mas sem folga para backups locais grandes. 6,6 GB de imagens recuperáveis (limpeza só com aprovação — são de outros projetos).
4. **Nomes de containers**: já existem `nginx`, `redis`, `mysql`, `evolution`, `certbot`. Não usar `container_name` genérico; prefixar (`portal-…`) ou deixar o Compose nomear pelo projeto `portal_web`.
5. **Redes**: faixas 172.17–172.24 usadas; deixar o Docker escolher a sub-rede ou fixar uma livre (ex.: 172.30.0.0/24).
6. **Fuso**: host em UTC. Definir `TZ=America/Sao_Paulo` nos containers (agendador!), **não** mudar o fuso do host (afeta os outros projetos).
7. **Bancos sem porta pública**: manter PostgreSQL/Redis só na rede interna (não publicar 5432/6379) — padrão já seguido na VPS.
8. **autoheal**: só atua em containers com label `autoheal=true`; pode ser aproveitado de propósito.
9. **Segurança do SSH**: root com senha liberado na internet (mitigado pelo fail2ban). Não bloqueia a instalação, mas é risco.
10. **unattended-upgrades** ativo: pode reiniciar serviços/Docker em atualizações — monitorar.
11. **Variáveis no nginx** (`${DOMAIN_HOTSPOT}` etc.): a config do nginx usa templates; editar errado pode derrubar o hotspot. Testar com `nginx -t` antes de recarregar.

## 9. O que fazer ANTES da instalação (em ordem)
1. 🔒 **[Aprovação]** Confirmar **snapshot recente da VPS** no painel da Hostinger (regra 4 do CLAUDE.md) antes de qualquer mudança.
2. 🔒 **[Aprovação]** Decidir estratégia de proxy (muda a decisão "Caddy com SSL" do CLAUDE.md): vhosts no nginx do hotspot (recomendado) **ou** Caddy interno sem TLS atrás do nginx.
3. 🔒 **[Aprovação]** Decidir capacidade: seguir com limites de memória no plano atual **ou** fazer upgrade da VPS.
4. 🔒 **[Aprovação]** Fazer backup da pasta `/opt/hotspot/nginx/conf.d` antes de qualquer mudança no nginx.
5. (Opcional) Confirmar quais endpoints do Fiorilli o coletor usa — `/Transparencia/` já responde 200.
6. 🔒 **[Aprovação]** Ajustar dono/permissão de `/opt/portal_web` e corrigir `Docs/` (hoje gravável por todos) e copiar o código do projeto.
7. Preparar o `.env` de produção (senhas fortes, bancos `bd_pm_bora` e `bd_cm_bora` + usuário somente leitura para o serviço de dados públicos) — fora do repositório, `chmod 600`.
8. Ajustar o `docker-compose.yml`: sem portas 80/443, sem `container_name` genéricos, `TZ=America/Sao_Paulo`, `mem_limit`, rede compartilhada com o nginx.
9. 🔒 **[Aprovação]** Emitir certificados para `gestao`, `pmbora`, `cmbora` via certbot existente e adicionar os vhosts (`nginx -t` + reload).
10. Definir rotina de backup do PostgreSQL (pg_dump diário por banco + cópia externa).
11. 🔒 **[Aprovação — opcional]** Aplicar as 74 atualizações pendentes (com snapshot antes; pode reiniciar Docker e afetar os outros sistemas).
12. 🔒 **[Aprovação — opcional]** Endurecer SSH (desativar senha / root por senha) depois de garantir acesso por chave — afeta todos os acessos à VPS.

## Encerramento da Fase 1
- **Nada foi alterado na VPS**: só comandos de leitura (`ss`, `ufw status`, `sshd -T`, `docker ps/inspect/stats`, `dig`, `curl` de saída). Nenhum serviço instalado, alterado ou reiniciado. Nenhum `.env`, senha ou chave foi lido ou exibido.
- Os únicos arquivos criados na VPS são este `PROGRESSO.md`, `diagnostico-vps.txt` e `diagnostico-complementar.txt` (ambos 600), em `/opt/portal_web/Docs`, com sua autorização.
- **Onde parou:** Fase 1 concluída.

## Decisões e ações de 2026-11-06 (após a Fase 1)
- ✅ **Item 1 — snapshot:** usuário confirmou que existe snapshot recente da VPS na Hostinger.
- ✅ **Item 2 — proxy:** decidido usar o **nginx existente** (vhosts + certbot existente). Caddy próprio descartado; CLAUDE.md atualizado.
- ✅ **Item 6 (parcial) — permissão:** `/opt/portal_web/Docs` corrigida de `7777` (`drwsrwsrwt`) para `755` com aprovação do usuário. Única alteração feita na VPS além destes relatórios.
- ✅ **Item 3 — capacidade:** decidido **limitar memória** (sem upgrade por ora). Orçamento abaixo.
- ✅ **Item 4 — backup do nginx:** `/opt/hotspot/nginx/conf.d` (15 arquivos) salvo em
  `/opt/portal_web/backups/nginx-conf.d-hotspot-20261106-234149.tar.gz` (pasta 700, arquivo 600; sha256 começa com `cba0a03a9acf754e`).
  Restaurar: `tar -xzpf <arquivo> -C /opt/hotspot/nginx` e depois `docker exec nginx nginx -t && docker exec nginx nginx -s reload`.
  Nada no nginx foi alterado.
- ⏳ **Pendente:** código do projeto em `/opt/portal_web` e itens 5 a 12.

### Orçamento de memória (piloto)
Medido agora: ~2,0 GiB disponíveis na RAM, swap com 1,2 GiB de 4 GiB em uso. Meta: o projeto inteiro ≤ 1,3 GiB.

| Container | `mem_limit` | Ajustes |
|---|---|---|
| PostgreSQL (`bd_pm_bora` + `bd_cm_bora`) | 384m | `shared_buffers=96MB`, `work_mem=4MB`, `max_connections=40`, `effective_cache_size=256MB` |
| Redis | 96m | `maxmemory 64mb`, `maxmemory-policy allkeys-lru` (se for só cache/fila sem persistência crítica) |
| app | 384m | 1 processo/worker web; Node: `NODE_OPTIONS=--max-old-space-size=288` |
| worker | 256m | concorrência 1–2 |
| agendador | 128m | só dispara tarefas; o trabalho pesado vai para o worker |
| **Total** | **~1,25 GiB** | |

Outras regras: `memswap_limit` igual ao `mem_limit` (evitar empurrar mais coisas para a swap), `restart: unless-stopped`,
label `autoheal=true` com healthcheck, `cpus` ≤ 0,5 por serviço pesado. Rever os números depois de uma semana de uso (`docker stats`).
- Fase 2 **não iniciada** — aguardando seu pedido.

---

# Fase 2 — Implantação do piloto (iniciada em 2026-11-07)

## Passo 0 — Leitura (concluído, nada alterado)
- O código veio como `Docs/portal_web.tgz` (88 itens: `portal_web/` + `PEDIDO-FASE2.md`). Foi extraído **só para leitura** numa pasta temporária da sessão.
- Stack real: FastAPI/uvicorn (Python 3.12) + PostgreSQL 16. Compose original: `caddy`, `app`, `worker`, `db`. **Não há Redis nem agendador separado** (o `worker` faz o agendamento).
- Pré-requisitos rechecados: DNS dos 3 domínios = 76.13.167.181 ✅; UFW libera 80/443 ✅; Docker 29.5.1 + Compose v5.1.3 ✅;
  80/443 **ocupadas pelo nginx do hotspot** (esperado — decisão: usar esse nginx); certbot existente tem conta ACME registrada ✅.

### Desvios necessários no compose (decisões já aprovadas: nginx + limite de memória)
1. Remover o serviço `caddy` (ele tentaria publicar 80/443 e falharia).
2. Ligar o `app` à rede externa `hotspot_shared-net` com o alias único `portal-web-app` (mesmo padrão do vendasgov); `db` e `worker` ficam só na rede interna do projeto.
3. `mem_limit`/`memswap_limit`: db 384m, app 384m, worker 256m (total ≈ 1 GiB); Postgres com `shared_buffers=96MB`, `max_connections=40`.
4. Healthcheck do app em `/saude` + label `autoheal=true`.
5. HTTPS: 3 certificados pelo certbot existente (webroot) + 3 vhosts no nginx (`portal-bora.conf`), com `nginx -t` antes do reload.

## Passo 1 — Código em /opt/portal_web (concluído, aprovado em 2026-11-07)
- `tar -xzf Docs/portal_web.tgz -C /opt/portal_web --strip-components=1 portal_web/` → 74 arquivos, incluindo `.env.example` e `.gitignore`. `Docs/` e `backups/` intactas. Dono mantido `root:root`.

## Compose adaptado (concluído, aprovado em 2026-11-07)
- Original guardado em `docker-compose.original.yml`; `docker-compose.yml` agora sem Caddy, `app` na rede `hotspot_shared-net` (alias `portal-web-app`), limites app 384m / worker 256m / db 384m, `cpus: 0.5`, healthcheck `/saude` + `autoheal=true`. Validado com `docker compose config`.

## Passo 2 — Pré-requisitos (2026-11-07)
- ✅ Snapshot reconfirmado pelo usuário em 2026-11-07. ✅ DNS, firewall, Docker (ver Passo 0). 80/443 com o nginx do hotspot (decisão aprovada).
- `EMAIL_SSL` informado pelo usuário.

## Passo 3 — .env (concluído, aprovado em 2026-11-07)
- `/opt/portal_web/.env` criado a partir de `.env.example`, permissão 600 (root). Gerados com `openssl rand`: PG_PASSWORD (hex 24), SECRET_KEY (hex 32), SENHA_INICIAL_GESTOR e SENHA_INICIAL_ADMIN (base64 18). EMAIL_SSL preenchido. Domínios conferidos. Valores não exibidos.
- Ler senhas iniciais na VPS: `grep SENHA_INICIAL /opt/portal_web/.env`

## Passo 4a — docker compose up -d --build (executado, aprovado em 2026-11-07 00:28 UTC)
- Imagens `portal_web-app`/`portal_web-worker` construídas; volumes novos `portal_web_pg` e `portal_web_dados` (criados neste comando).
- `db` healthy (46 MiB/384), `app` healthy (49 MiB/384, `/saude` 200).
- ⚠️ `worker` em loop de reinício: `relation "coletas" / "dados_publicos" does not exist` — esperado, as tabelas só existem depois do `provision init`. Não foi corrigido nada; aguardando aprovação.

## Passo 4b — provision init (concluído, aprovado em 2026-11-07)
- Bancos: `plataforma`, `bd_pm_bora`, `bd_cm_bora`. Usuários iniciais: gestor@gestao.conectatech.tech, admin@pmbora.conectatech.tech, admin@cmbora.conectatech.tech (senhas no `.env`; troca obrigatória no 1º acesso). Conteúdos de exemplo da Prefeitura (marcados) e dados reais da Câmara carregados.
- `worker` estabilizou após o provision (11 reinícios antes, todos por tabela inexistente). 1ª coleta automática: `OK Siconfi: RGF do Legislativo 0 — 26 entregas do município; 0 de RGF`. Fiorilli só roda 7h–20h (horário de Brasília).
- Teste ACME (leitura): `http://<domínio>/.well-known/acme-challenge/...` → 404 do `default_server` do nginx, sem redirecionamento ✅ — certbot webroot vai funcionar.

## Passo 4c — Certificados (concluído, aprovado em 2026-11-07)
- `certbot certonly --webroot` para gestao, pmbora e cmbora (conta ACME existente). Válidos até **04/02/2027**; renovação automática pelo loop do container `certbot` (12h).
- ⚠️ Pendência pré-existente (afeta TODOS os sites da VPS): após renovar, nada recarrega o nginx (sem deploy-hook nem cron). Sugestão futura: cron diário `docker exec nginx nginx -s reload`. Não alterado.

## Passo 4d — vhost nginx (concluído, aprovado em 2026-11-07)
- Instalados `/opt/hotspot/nginx/conf.d/portal-bora.conf` (80→301 + 3 blocos 443) e `portal-bora.inc` (proxy para `portal-web-app:8000`, cabeçalhos de segurança, 25M). `nginx -t` ok (só avisos de `http2` obsoleto, iguais aos dos outros sites) → `nginx -s reload`.
- Para desfazer: remover os 2 arquivos e `docker exec nginx nginx -s reload`.

## Passo 5 — Testes (2026-11-07)
| URL | Resultado |
|---|---|
| https://gestao.conectatech.tech | 303 → /login ("Console do gestor") ✅ |
| https://pmbora.conectatech.tech | 200 ("Prefeitura Municipal de Borá") ✅ |
| https://cmbora.conectatech.tech | 200 ("Câmara Municipal de Borá") ✅ |
| https://pmbora.conectatech.tech/admin/login e cmbora .../admin/login | 200 ✅ |
| http://pmbora.conectatech.tech | 301 → https ✅ |
- Certificados Let's Encrypt (YE2) válidos, verificação SSL ok; HSTS, nosniff e Referrer-Policy presentes.
- Sites existentes conferidos após o reload: conectatech, hotspot, vendasgov, pmunix, mei, controle-hotspot, evolution → todos 200 ✅.
- Logs: app sem erros; nginx sem erros para os novos domínios; IP real do visitante chega ao app.
- ⚠️ Observação: `curl -I` (HEAD) retorna **405** — o app (FastAPI) só aceita GET nessas rotas. Com GET está 200/303. Afeta só monitores que usem HEAD.
- ⚠️ `deploy/backup.sh`: a linha `tar ... -C /var/lib/docker/volumes . --wildcards '*_dados'` não funciona como esperado na criação de arquivo e o erro é escondido (`2>/dev/null || true`) — o backup de arquivos enviados sairia vazio sem aviso. Correção proposta, aguardando aprovação.

### Coleta manual (aprovada)
`docker compose exec -T app python -m app.worker uma-vez`:
- `OK Fiorilli: emendas impositivas — 2 linhas guardadas em dados_publicos (mapeamento para a tabela emendas a validar)`
- `OK Siconfi: RGF do Legislativo — 26 entregas do município; 0 de RGF`

## Passo 6 — Backup (concluído, aprovado em 2026-11-07)
- `deploy/backup.sh` corrigido (original em `deploy/backup.sh.original`): o arquivo do volume agora é `tar -czf ... -C /var/lib/docker/volumes/portal_web_dados _data`, sem esconder erro.
- Teste: `plataforma`, `bd_pm_bora`, `bd_cm_bora` (.dump, legíveis por `pg_restore --list`: 9/16/16 tabelas com dados) + `dados-2026-11-07.tgz` (volume ainda vazio). Log em `backups/backup.log`.
- Crontab do root: `0 5 * * * /opt/portal_web/deploy/backup.sh >> /opt/portal_web/backups/backup.log 2>&1` (05:00 UTC = **02:00 de Brasília**). Guarda 14 dias.

## Resumo da implantação
| Endereço | Uso | Usuário inicial |
|---|---|---|
| https://gestao.conectatech.tech | Console do gestor | gestor@gestao.conectatech.tech |
| https://pmbora.conectatech.tech (+ /admin) | Prefeitura | admin@pmbora.conectatech.tech |
| https://cmbora.conectatech.tech (+ /admin) | Câmara | admin@cmbora.conectatech.tech |
Senhas iniciais: `grep SENHA_INICIAL /opt/portal_web/.env` (na VPS). Troca obrigatória no 1º acesso.

O que foi alterado na VPS (tudo aprovado): código em `/opt/portal_web` (+ `.env` 600, compose adaptado, backup.sh corrigido); containers `portal_web-{app,worker,db}` e volumes `portal_web_pg`/`portal_web_dados`; 3 certificados no certbot existente; `portal-bora.conf` + `portal-bora.inc` no nginx do hotspot (reload); 1 linha no crontab do root; permissão de `Docs/`.

## Pendências
1. **Trocar as senhas iniciais** nos 3 painéis (1º acesso).
2. **Reload do nginx após renovação de certificado** — não existe para nenhum site da VPS (pré-existente). Sugestão: cron diário `docker exec nginx nginx -s reload`. Prazo: antes de ~05/01/2027 (1ª renovação dos novos).
3. **Cópia externa dos backups** — hoje ficam só na própria VPS.
4. Fiorilli: validar o mapeamento das linhas coletadas para a tabela `emendas` (2 linhas em `dados_publicos`).
5. Siconfi: 0 RGF encontrados entre 26 entregas — verificar filtro do coletor.
6. HEAD retorna 405 (só afeta monitores que usem HEAD).
7. Rever `mem_limit` após 1 semana (`docker stats`).
8. Opcionais já listados na Fase 1: SSH (root/senha), 74 atualizações de pacotes.

## Onde parou
**Fase 2 concluída em 2026-11-07.** Piloto no ar. Nenhuma ação em andamento.


---

# Fase 3 — Identidade visual (iniciada em 2026-11-07)

## Feito (sem alterar a VPS em produção)
- Referência `Docs/fase34.tgz` extraída em `Docs/` (PEDIDO-FASE3/4, ESPEC-VISUAL, FONTES-DADOS, 4 protótipos, 13 imagens).
- **Git**: `/opt/portal_web` virou repositório. `main` = commit "piloto fase 2" + tag **`fase-2`** (estado em produção). `.gitignore` exclui `.env`, `backups/`, `Docs/diagnostico-*.txt`, `Docs/*.tgz` e os `.webp` gerados.
- Branch **`fase-3`** com commits pequenos:
  1. imagens em `app/static/img` (+ `.webp` ≤ 250 KB geradas no build com Pillow), migração `003_orgao_identidade.sql`, `python -m app.provision atualizar`;
  2. base do portal (barra de acessibilidade, barra utilitária, cabeçalho com brasão, menu, busca, rodapé em 4 faixas, Public Sans, tokens de cor), página inicial em blocos, páginas da Câmara (galeria, perfil, caminho da emenda), privacidade/acessibilidade/mapa do site, rota `/midia/`;
  3. painel e console com menu de ícones; identidade com upload de imagens; vereadores no /admin; foto de tema no conteúdo;
  4. testes de ponta a ponta (recusam rodar fora do banco de teste).
- Os 45 modelos Jinja compilam sem erro (checagem no host).
- Observação: instalar Pillow numa pasta temporária do host foi bloqueado pela política de segurança; por isso as `.webp` são geradas dentro do build da imagem.

## Decisões de implementação
- `provision atualizar`: aplica todas as migrações (idempotentes) em todos os bancos, completa a identidade **sem sobrescrever** o que o órgão definiu e acrescenta blocos novos. Se o layout ainda é exatamente o padrão da Fase 2, aplica o novo padrão inteiro (para a Câmara ficar com contas 55% × emendas 45%).
- Cor da Prefeitura: troca `#1D4E89` (padrão da Fase 2) por `#0E4D64` (protótipo) só se ainda estiver no padrão.
- Câmara: o destaque usa `paco-municipal.jpg` (conforme ESPEC-VISUAL) com texto alternativo honesto ("Fachada do Paço Municipal"); a Câmara deve enviar a foto do próprio prédio em /admin/identidade.
- "Borá em números" fica oculto até a Fase 4 gravar `config.numeros`.

## Implantação (aprovada em 2026-11-07)
1. `docker compose build app worker` → 13 `.webp` geradas (15–206 KB, todas ≤ 250 KB).
2. Testes em PostgreSQL descartável (rede `portal-teste`, removidos ao fim). 1ª rodada: 1 falha real — a aprovação de conteúdo gravava `publicar_em` com o `CURRENT_DATE` do banco (UTC) e o portal compara com a data do app (Brasília): perto da meia-noite o conteúdo ficava "para amanhã". **Corrigido** (usa `config.hoje()`), rebuild, 2ª rodada: **ERROS: 0**.
   Comando de teste: `docker network create portal-teste && docker run -d --name portal-teste-db --network portal-teste --memory 256m -e POSTGRES_USER=portal -e POSTGRES_PASSWORD=teste -e POSTGRES_DB=plataforma postgres:16`, aguardar `pg_isready`, depois `docker run --rm --network portal-teste -v /opt/portal_web/tests:/srv/tests:ro -e TESTE=1 -e PG_HOST=portal-teste-db -e PG_USER=portal -e PG_PASSWORD=teste -e DOMINIO_GESTAO=gestao.localhost -e DOMINIO_PM=pmbora.localhost -e DOMINIO_CM=cmbora.localhost -e SENHA_INICIAL_GESTOR=gestor123 -e SENHA_INICIAL_ADMIN=admin123 -e SECRET_KEY=teste -e COOKIE_SEGURO=0 -e DADOS_DIR=/tmp/dados portal_web-app sh -c 'python -m app.provision init && python -m app.provision atualizar && PYTHONPATH=. python tests/teste_fluxos.py'` e remover `portal-teste-db` e a rede.
3. Backup antes (`plataforma`, `bd_pm_bora`, `bd_cm_bora` ok) → `docker compose up -d app worker` → `provision atualizar`: identidade completada e layout novo aplicado nos dois órgãos.

## Conferência (2026-11-07)
- 3 domínios, `/admin/login`, vereadores, perfil, caminho da emenda, Diário, e-SIC, privacidade e `.webp`: todos 200. Cores aplicadas: Prefeitura `#0E4D64`, Câmara `#2F5233`.
- Página inicial da Prefeitura: hero, Acesso direto, Serviços, Conheça Borá, Paço Municipal, rodapé com Radar. Câmara: Próxima sessão, Presidente 2×2, Mesa, Quanto custa a Câmara × Emendas, Últimas sessões, Projetos.
- Critérios: todas as `<img>` com `alt` (testado em 18 páginas); contraste AA dos 16 pares de cor do tema (testado ≥ 4,5:1); foco visível amarelo; blocos novos no /admin e no editor de regiões (testado); sem regressão em e-SIC, Diário (PDF + verificação), período eleitoral, login e console (testado).
- Logs do app sem erro; worker estável; demais sites da VPS 200.
- ⚠️ **Não verificado visualmente em 375 px**: a extensão do navegador não estava conectada. Revisão do CSS: grades com `min(100%, …)`, blocos lado a lado quebram de linha, tabelas com rolagem própria. **Pendente: conferir no celular.**

## Pendências da Fase 3
- Conferir no celular (375 px) as duas páginas iniciais.
- Câmara: enviar foto do prédio da Câmara (hoje o destaque usa a foto do Paço, com alt honesto) e as fotos oficiais dos vereadores.
- Prefeitura: cadastrar os serviços reais (hoje só 1 serviço de exemplo publicado) escolhendo a foto de tema.
- Redes sociais oficiais e WhatsApp: preencher em /admin/identidade (o rodapé só mostra o que estiver cadastrado).
- e-SIC: `recebido`/`respondido` ainda usam `CURRENT_DATE` do banco (o banco de produção está em America/Sao_Paulo, então está correto; revisar se o banco mudar de fuso).

## Como desfazer a Fase 3
`cd /opt/portal_web && git checkout fase-2 -- . && docker compose build app worker && docker compose up -d app worker` (a migração 003 só acrescenta colunas/tabela; pode ficar). Restaurar layout/identidade: `pg_restore` dos dumps de `backups/*-2026-11-07.dump`.

## Onde parou
Fase 3 concluída e implantada; merge em `main` + tag `fase-3`. Próximo: Fase 4, passo 1 (descoberta, só leitura).

---

# Fase 4 — Transparência com dados reais (iniciada em 2026-11-07)

## Passo 1 — Descoberta (só leitura; nenhuma tabela criada)
Roteiro `app/coletores/descoberta.py` executado dentro do container `app` (1 req/s por fonte, timeout 60 s, 3 tentativas). Amostras **sem CPF** em `/srv/dados/amostras/` (volume `portal_web_dados`): campos com "CPF" no nome removidos e qualquer sequência no formato de CPF (inclusive mascarada `000.XXX.XXX-00`) trocada por `[removido]`; conferido: nenhuma amostra com CPF.

| Endpoint (ano 2026, até 06/11) | HTTP | Registros | Campos principais |
|---|---|---|---|
| Fiorilli Receitas `ReceitaOrcamentaria` | 200 | 244 | CODIGO, NOME, PREVISAO_INICIAL/ATUALIZADA, ARRECADADO_TOTAL (receitas correntes 2026: R$ 26.574.852,37) |
| Fiorilli Receitas 2025 | 200 | 244 | idem — **tudo zerado** (confirma uso do TCESP para 2025) |
| Fiorilli `DespesasPorUnidade` | 200 | 22 | CODIGO, DESCRICAO, DOTACAO_ATUALIZADA, EMPENHADO, LIQUIDADO, PAGO |
| Fiorilli `DespesasGerais` (empenhos) | 200 | 4.735 | PKEMP, CODIGO, TPEM, DATAE, NOMEFOR, órgão/unidade/função/programa/ação, NATUREZA, FONGRUPO, LICIT, EMPENHADO, ANULADO, LIQUIDADO, PAGO, VINGRUPO_VINCODIGO, VINCODIGONOME (CPFFORMATADO descartado). Só responde com `UFParaFiltroCOVID=` (vazio) e `ApenasIDEmpenho=False`; sem eles: HTTP 500; com `UFParaFiltroCOVID=SP`: vazio |
| Fiorilli `Diarias` | 200 | 675 | NEMPG, DATA, VALOR, VALORANULADO, FAVORECIDO, CARGO, NOMEORGAO, NOMEUNIDADE, DESCRICAO |
| Fiorilli `DespesasRestosPagar` | 200 | 58 | CODIGO, DESCRICAO (credor), EMPENHADO, LIQUIDADO, PAGO |
| Fiorilli `DespesasporExigibilidade` tipo 1 / tipo 2 | 200 | 1.851 / 1.505 | TIPOLISTA (1 = até o limite do art. 75, II; 2 = acima), EMPENHO, FORNECEDOR, CGC, VADEM, VAPAG, VENCI, DTPAG, JUSTIFICATIVA, FONTE_NOME, UNIDADE_NOME, CONTRATO |
| Fiorilli `Licitacoes` | 200 | 786 | PROCLIC, LICIT (modalidade), DISCR (objeto), SITUACAO, DATAE, VALOR, CODTCE |
| Fiorilli `Contratos` | 200 | 133 | CODIGO, FORNECEDOR, OBJETO_COMPLETO, VALCON, DTASSI, VIGENI, VIGENF, MODALI, PROCLIC, EMPENHADO, LIQUIDADO |
| Fiorilli `Transf` | 200 | 11 | MES, ENTIDADE_PAGADORA/RECEBEDORA, PREVISTO, REPASSE, DEVOLUCAO, DTLAN (duodécimo da Câmara) |
| Fiorilli `EmendasImpositivasArt166A` | 200 | 2 | TIPOTRANSF, EMPENHADO, LIQUIDADO, PAGO — só totais de transferências estadual/federal, **não serve por emenda** |
| Fiorilli `CadEmendasImpositivas` (em `Transferencias/`) | 200 | 30 (29 municipais 2026) | NUMERO_EMENDA, ANO, AUTOR, OBJETO, RESUMO, VALOR_TOTAL, EMPENHADO, LIQUIDADO, PAGO, ESFERA_ORIGEM, ATO_NORMATIVO |
| Fiorilli `CadEmendasImpositivas` (em `Despesas/`) | 200 | 0 | página HTML (caminho errado) |
| Fiorilli `Servidores` (out/2026) | 200 | 159 | REGISTRO, NOME, NOME_SOCIAL, CARGO, VINCULO, DIVISAO/UNIDADE (lotação), DATAADMISSAO, PROVENTOS (CPF, DESCONTOS e líquido descartados) |
| Fiorilli detalhes por empenho (`intNumeroEmpenho`, `strTipoEmpenho`) | 200 | 1 cada | Detalhes (órgão, programa, ação, natureza, fonte, licitação, contrato), Empenhado, Liquidado, Pago e Pago com ordem de pagamento — datas e valores |
| PNCP `api/search` (município 3507209) | 200 | 50/página, total 1.460 | numero_controle_pncp, title, modalidade_licitacao_nome, situacao_nome, valor_global, data_publicacao_pncp, unidade_nome, item_url |
| Siconfi `extrato_entregas` 2026 | 200 | 26 | entregavel, periodo, status_relatorio, data_status, instituicao |
| Siconfi RREO Anexo 14 (2025, 6º bim.) | 200 | 46 | rotulo, conta, coluna, valor — **saúde 20,36%** (mín. 15%), **MDE 31,23%** (mín. 25%), FUNDEB 70%: 97,73% |
| Siconfi RREO Anexo 14 (2026, 4º bim.) | 200 | 33 | idem, mas sem as linhas de saúde/MDE neste período |
| Siconfi RGF Anexo 01 (2026, 2º quadr.) Legislativo / Executivo | 200 | 64 / 112 | despesa com pessoal × RCL |
| TCESP receitas 2025 (jan / dez) | 200 | 40 / 49 | mes, ds_fonte_recurso, ds_alinea, ds_subalinea, vl_arrecadacao |

### Emendas: listagem correta
- **Cadastro por emenda: `Transferencias/?Listagem=CadEmendasImpositivas`.** Traz as 29 emendas municipais de 2026 com autor, objeto, valor e empenhado/liquidado/pago **do cadastro** (total: R$ 408.240,00 indicados; R$ 5.985,00 pagos).
- **Execução pelos empenhos: `Despesas/?Listagem=DespesasGerais`**, linhas com `VINCODIGONOME = "Emenda Ver. <nome>"` (fonte 08). O código de vínculo `804.0NN` identifica o **vereador**, não a emenda. Hoje há 3 vereadores com execução e cada um tem só 1 emenda em execução, então a ligação é inequívoca: 12/2026 (empenho 111), 13/2026 (empenho 83) e 22/2026 (empenho 426). As datas de liquidação e pagamento vêm das consultas por número de empenho.
- `EmendasImpositivasArt166A`: só totais de transferências, descartada para emendas.
- Na leitura de hoje, o pago do cadastro **bate** com o pago dos empenhos nas emendas 12 e 13, que divergiam em 05/11. A conferência passará a ser recalculada a cada coleta.

✅ **Mapeamento aprovado pelo usuário em 2026-11-07.**

## Passos 2 a 7 — implementação (branch `fase-4`)
- Migrações: `004_plataforma_fontes.sql` (tabela `fontes` por órgão) e `005_orgao_transparencia.sql` (receitas, despesas_unidade, empenhos, licitacoes, contratos, servidores, diarias, transferencias, ordem_cronologica, restos_pagar, relatorios_fiscais; colunas novas em emendas). Idempotentes, aplicadas por `provision atualizar`, que também cadastra as fontes padrão.
- Coletores: `fiorilli.py` (11 bases + emendas), `pncp.py`, `siconfi.py` (RREO 14, RGF 01, entregas; atualiza a despesa com pessoal da Câmara), `tcesp.py` (receitas 2025 mês a mês), `numeros.py` ("Borá em números"), `comum.py` (1 req/s, timeout, novas tentativas, upsert, LGPD).
- Worker por fonte: Fiorilli de hora em hora das 7h às 19h, PNCP a cada 6 h, Siconfi diária, TCESP no dia 20 ou enquanto faltar 2025.
- Telas: `/transparencia` (central com cartões e data de cada base), `/transparencia/<base>` (filtros de ano, mês, unidade, credor e texto; paginação; totais; fonte e data de atualização; "Base legal:"; aviso quando a última coleta falhou), `.csv`/`.json`, API `/dados/<base>.json`, página `/dados-abertos`.
- Console: "Registro e coletas" com a situação de cada fonte e as falhas em destaque.
- Testes offline (`tests/teste_transparencia.py`) com as amostras e linhas sintéticas com CPF. Amostras completas do RGF Legislativo (64 linhas) e do RREO 14 (46 linhas) salvas para os testes.

## Passo 8 — Implantação (aprovada em 2026-11-07)
- Build ok. Testes em bancos descartáveis: `teste_fluxos` **ERROS: 0**; `teste_transparencia` **ERROS: 0** (1ª tentativa tinha limite de teste errado: 90 = 3 amostras × 30, corrigido).
- Backup → `up -d` → `provision atualizar` (fontes: 4 da Prefeitura, 2 da Câmara; migrações 004/005) → `worker uma-vez` (1 min 42 s).
- Resultado da 1ª coleta: Fiorilli 10/10 bases OK (receitas 244, despesas 22, empenhos 4.738, diárias 675, restos 58, ordem cronológica 3.356, licitações 786, contratos 133, transferências 11, servidores 159); Siconfi OK (RREO 14 de 2026/4º bim., RGF E 2026/2º quadr., RGF L); TCESP 2025 OK (571 linhas, 12 meses); Câmara: 29 emendas e 11 repasses. "Borá em números": receita R$ 22.565.789,79, empenhado R$ 22.424.024,18.
- ⚠️ **PNCP falhou**: a API derruba conexões (teste manual: das páginas 1, 2 e 5, só a 2 respondeu). Corrigido no código: 6 tentativas e aproveitamento das páginas já lidas (coleta parcial registrada).
- ⚠️ RREO de 2026/4º bim. vem sem as linhas de saúde/MDE: o coletor passa a guardar também o último período que as tem (2025, 6º bim.: saúde 20,36%, MDE 31,23%).

## Conferência de 3 registros por base contra a fonte oficial (2026-11-07)
Registros sorteados do portal público (`/dados/<base>.json`) comparados com nova consulta à fonte; empenhos conferidos na consulta de **detalhe** por número (independente da listagem).
| Base | Registros conferidos | Resultado |
|---|---|---|
| Receitas 2026 (Fiorilli) | 1311.01.1.3, 1114.51.1.2 (R$ 812,23), 1323.00 (R$ 19.457,95) | 3/3 OK |
| Receitas 2025 (TCESP) | fev/11210100 (R$ 317,46), fev/17215200, dez/17135100 (R$ 22.994,62) | 3/3 OK — a fonte tem duas linhas para fev/17215200 (R$ 3.278,56 e dedução −R$ 655,72); o portal mostra as duas |
| Despesas por unidade | 020201, 020502, 020803 (pago) | 3/3 OK |
| Empenhos | 4359/2026, 237/2026, 2904/2026 (valor e credor) | 3/3 OK |
| Diárias | 4514, 4192, 1920 | 3/3 OK |
| Restos a pagar | 2797, 6739, 5368 | 3/3 OK |
| Licitações (Fiorilli) | 000404/26, 000131/25, 000060/26 | 3/3 OK |
| Contratos | 0035/26, 0020/26, 0003/26 | 3/3 OK |
| Transferências | jan (2 lançamentos: R$ 25.000 + R$ 70.800 = R$ 95.800), out (R$ 95.800) | 3/3 OK (a conferência somou o mês) |
| Servidores | 2 nomes OK; **1 sem nome** | ❌ **defeito**: 103 de 159 sem nome (NOME_SOCIAL vem com espaço). Corrigido no código e no teste; precisa de rebuild + nova coleta |
| Ordem cronológica | 2006, 608, 92 (valor pago) | 3/3 OK |
| Relatórios fiscais (Siconfi) | RREO 2026/4 total, RGF 2026/2 vencimentos, ACS | 3/3 OK |
| Câmara: repasses | 3 meses, todos para a Câmara | 3/3 OK |
| Câmara: emendas | 22, 12, 13: pago no cadastro = pago nos empenhos (R$ 1.160, R$ 1.225, R$ 3.600) | 3/3 OK — a divergência de 05/11 nas 12 e 13 não existe mais na fonte |
| Licitações (PNCP) | — | não conferido: coleta falhou (fonte instável) |

## Correção e reimplantação (aprovada em 2026-11-07)
- Rebuild; testes: `teste_fluxos` **ERROS: 0**, `teste_transparencia` **ERROS: 0** (agora reproduz o nome social em branco).
- `up -d` + `worker uma-vez fiorilli pncp siconfi`: Fiorilli 10/10 OK; **PNCP parcial: 600 publicações (12 páginas), parou na 13ª por queda da API** — as próximas coletas (a cada 6 h) completam, sem apagar o que já entrou; Siconfi OK, com os mínimos de saúde/educação do 3º bimestre de 2026.
- Reconferência: **servidores 0 de 159 sem nome**; 3 sorteados (Neide Albertini, Mayra G. M. Nunes, Ricardo de B. Pereira): cargo e remuneração = fonte ✅. **PNCP** 3 sorteados (000273/2026, 000279/2026, 000483/2025) contra a consulta individual da API do PNCP: modalidade e situação ✅; o **valor não vem na busca** do PNCP (só na consulta individual) → coluna vazia (pendência).
- "Borá em números" no ar: receita R$ 22.565.789,79 · empenhado R$ 22.424.024,18 · pago R$ 19.999.531,48 · saúde 16,95% · educação 32,81% (RREO 3º bim. 2026).
- Produção: 16 páginas/exportações conferidas (200, < 0,2 s), nenhum CPF na tela, app sem erros, memória app 56 MiB / worker 42 MiB / db 100 MiB; demais sites da VPS 200.

## Pendências da Fase 4
1. PNCP: completar as 1.460 publicações (automático a cada 6 h) e trazer o valor estimado pela consulta individual de cada compra (~1 req/s).
2. Licitações em duas fontes (Fiorilli e PNCP) aparecem na mesma lista, marcadas pela fonte; ainda não há ligação entre o processo da Fiorilli e o número de controle do PNCP.
3. Emendas: se um vereador tiver mais de uma emenda em execução, o empenho fica "não atribuível" até a Prefeitura indicar a emenda (hoje nenhum caso).
4. Câmara: o portal atual dela não tem dados abertos (reCAPTCHA); despesas próprias da Câmara dependem de exportação do fornecedor (Pronim/Cidade360).
5. Coletores não incluídos nesta fase: CNES, IBGE SIDRA/Cidades, IEG-M, MDS (fora do ar), vacinação, YouTube.
6. Pendências da Fase 3 continuam (conferência em 375 px no celular, fotos oficiais, serviços reais).

## Como desfazer
- Fase 4: `git checkout fase-3 -- . && docker compose build app worker && docker compose up -d app worker` (as tabelas novas ficam sem uso; a tabela `fontes` pode ser desativada com `UPDATE fontes SET ativo=false`).
- Fase 3: tag `fase-2` (ver seção da Fase 3). Dumps dos bancos antes de cada implantação: `backups/*-2026-11-07.dump`.

## Onde parou
**Fases 3 e 4 concluídas e implantadas em 2026-11-07.** `main` com merge de `fase-4` e tag **`fase-4`**. Nenhuma ação em andamento.

---

# Fase 5 — Câmara completa (iniciada em 2026-11-07)

## Passo 0 — Conferência (só leitura)
`Docs/fase56.tgz` extraído (PEDIDO-FASE5, PEDIDO-FASE6, modelos/README). Fases 3 e 4 conferidas: tags `fase-3`/`fase-4`, `main` no merge da Fase 4; pmbora `/transparencia` 200 com "Atualizado em" e CSV/JSON; cmbora com "Próxima sessão", card do presidente 2×2 (`vcard pres`) e faixa 55/45 (`l55`/`l45`). Nada faltando.

## Implementação (branch `fase-5`)
- Migração `006_orgao_legislativo.sql`: Mesa por biênio (eleição, posse, ato), autoria estruturada, tramitação, documentos PDF, comissões (membros, reuniões, pareceres), pauta, votos nominais, contas do Prefeito, diárias da Câmara, transmissões, Tribuna Livre, opiniões, avaliações, histórico de importações.
- `app/legislativo.py`: numeração automática por tipo/ano; votação nominal com quórum simples/absoluta/2/3; Presidente só vota no desempate (maioria simples), computado nos quóruns qualificados; resultado atualiza tramitação e situação; estatísticas do vereador só de sessões publicadas; autoavaliação PNTP 20.1–20.11 (critérios do protótipo).
- `app/admin_leg.py` (painel): Legislaturas e Mesas, Proposições (autores, relator, tramitação, PDFs com descrição obrigatória), Comissões, Sessões (pauta → presença → votação → ata → publicação separada; presença e votos só no dia da sessão ou depois; votação publicada não muda), Contas do Prefeito (parecer TCESP, comissão, pauta com 2/3, decreto), Diárias (lançamento, importação, declaração "sem diárias"), Transmissões (canal, agenda, iniciar/encerrar, capítulos, legendas/Libras), Participação (Tribuna Livre, moderação de opiniões com detecção de dado pessoal/ofensa, avaliação por página), Importar dados antigos (CSV), Autoavaliação PNTP.
- `app/portal_leg.py` (portal): proposições com filtros e página com linha do tempo, documentos, pareceres, votações nominais e opiniões; sessões com pauta/presença/votação/ata/vídeo publicados; comissões; contas; transmissões com player youtube-nocookie; Tribuna Livre; "Avalie esta página"; PDFs em `/documento/`.
- Faixa "● Ao vivo" + aviso uma vez por dia em todos os portais com transmissão; módulo novo `audiencias` (opcional, Prefeitura).
- Base "Diárias e verbas dos vereadores" (`/transparencia/diarias-camara`, CSV/JSON).
- `app/importar.py` + `Docs/modelos/*.csv`: 9 modelos, simulação, relatório por linha, tudo ou nada, recusa CPF. CLI: `python -m app.importar MODELO arquivo.csv --orgao cm-bora [--gravar]`.
- Testes `tests/teste_legislativo.py`: legislatura e pessoas FICTÍCIAS (16ª, 2029–2032), data simulada 10/03/2029.

## Implantação (aprovada em 2026-11-07)
- Build; testes em bancos descartáveis: `teste_fluxos` **ERROS: 0**, `teste_transparencia` **ERROS: 0**, `teste_legislativo` **ERROS: 0** (antes: 1 erro do próprio teste — token da tela errada; 1 expectativa de votos calculada no momento errado; 1 falha real corrigida: o texto do parecer não aparecia na página de comissões).
- Backup → `up -d` → `provision atualizar` (migração 006 nos dois bancos).
- Conferência: 16 páginas novas e antigas 200 (< 0,25 s); Prefeitura `/transmissoes` 404 (módulo de audiências não contratado, correto); logs sem erro; demais sites da VPS 200.
- **Produção sem nenhum voto, presença, item de pauta, ata ou transmissão inventados** (todos 0): entram quando a Secretaria registrar ou importar.

## Autoavaliação PNTP real da Câmara (07/11/2026)
20.1 parcial (9 vereadores, 0 com foto e biografia) · 20.2 a 20.11 pendentes, exceto 20.4.
⚠️ O 20.4 aparecia **atendido** sem merecer: as 8 sessões importadas do portal antigo vieram marcadas "pauta publicada", mas sem o conteúdo aqui. **Corrigido** (só conta pauta com texto ou itens) e as proposições antigas passam a ter a autoria vinculada aos vereadores pelo nome exato. Commit no branch `fase-5`, **aguardando aprovação para rebuild → testes → reimplantação**.

## Reimplantação da correção (aprovada em 2026-11-07)
- Rebuild; 3 suítes **ERROS: 0**; backup → `up -d` → `provision atualizar`: **40 proposições antigas com autoria vinculada** (41 vínculos, todos a vereadores cadastrados, pelo nome exato).
- PNTP real da Câmara agora: **20.1 parcial; 20.2 a 20.11 pendentes** (20.4: 0 de 8 sessões com pauta no portal). Logs sem erro; domínios 200.

## Pendências da Fase 5
1. Câmara: fotos oficiais e biografias (20.1), cadastro das comissões e membros (20.5), e passar a registrar pauta, presença, votação nominal e ata de cada sessão (20.4, 20.6, 20.7) — o painel está pronto.
2. Importar o histórico (proposições, tramitação, sessões, presenças, votos) a partir da exportação do fornecedor (Pronim/Cidade360) com os modelos de `Docs/modelos/`.
3. Cadastrar o canal oficial do YouTube e vincular as gravações às sessões (20.9); lançar ou declarar diárias (20.10); cadastrar o julgamento das contas (20.8).
4. Prefeitura: contratar/ligar o módulo `audiencias` no console se quiser transmitir audiências.

## Como desfazer a Fase 5
`git checkout fase-4 -- . && docker compose build app worker && docker compose up -d app worker` (as tabelas da migração 006 ficam sem uso). Dumps antes da implantação: `backups/*-2026-11-07.dump`.

## Onde parou
**Fase 5 concluída e implantada em 2026-11-07**; `main` com merge de `fase-5` e tag **`fase-5`**. Aguardando o "ok" do usuário para a Fase 6 (modo teste).

---

# Fase 6 — Diário assinado, remessa da Câmara e login gov.br (MODO TESTE, iniciada em 2026-11-07)

## Implementação (branch `fase-6`)
- **Assinatura** (`app/assinatura.py`, pyHanko 0.37.0): PAdES com carimbo do tempo RFC 3161 e LTV quando a cadeia permite; provedores **A1** (PKCS#12 em `segredos/a1`, senha em variável do .env indicada na designação), **nuvem** (interface pronta; sem endpoint inventado — falta o provedor fornecer API/credenciais), **A3** (download do PDF, assinatura no computador do signatário, upload validado: preserva o documento, exatamente 1 assinatura nova, todas íntegras, signatário designado); **MODO TESTE** com AC raiz, signatários e ACT de TESTE gerados localmente (`python -m app.assinatura gerar-teste`) e marca “SEM VALOR OFICIAL — TESTE”.
- **Diário** (`app/diario.py`, `app/diario_servico.py`): capa (Lei 910, art. 6º), página de cada ato, PDF/A-2b (Ghostscript) antes de assinar, assinaturas por caderno (Executivo, Legislativo, final), publicação só com edição totalmente assinada, edição de teste nunca oficial; calendário (feriado/sem expediente sem edição; ponto facultativo é dia útil), corte das 16h, edição “sem atos” automática às 16h (assinada por A1 ou teste), alerta às 16h30, publicação às 17h, extra com letra, retificação apontando o ato original, invalidação por ato do Prefeito com comunicado e prorrogação de prazos; verificação pública com signatários, carimbo, SHA-256 e link ao validar.iti.gov.br.
- **Remessa Câmara → Prefeitura** (`app/remessa.py`): API interna com token por par de órgãos (banco de controle), assinatura HMAC, janela de 5 min e registro; retorno com situação, número da edição e página. A Câmara não acessa o banco da Prefeitura.
- **Acesso** (`app/acesso.py`): segundo fator TOTP obrigatório (painéis e console) com QR code e 10 códigos de recuperação (só hash); segredo cifrado (Fernet); bloqueio após 5 falhas (15 min) por conta e por origem; sessão expira após 30 min sem uso; Login Único gov.br (OIDC + PKCE, id_token validado pela JWKS, nível prata/ouro) com vínculo pelo HMAC do CPF + 2 últimos dígitos (CPF completo nunca gravado); cabeçalhos CSP (`frame-ancestors 'none'`), X-Frame-Options, Referrer-Policy, Permissions-Policy, no-store nos painéis.
- Migrações `007_orgao_diario_seguranca.sql` e `008_plataforma_seguranca.sql`.
- Testes: suítes anteriores adaptadas ao 2º fator (`tests/apoio.py`) e nova `tests/teste_diario_seguranca.py`.

## Implantação (aprovada em 2026-11-07)
- Build (pyHanko 0.37.0, pyhanko-certvalidator 0.32.1, qrcode 8.2, requests 2.32.3, Ghostscript 10.05.1).
- Testes em bancos descartáveis: **4 suítes ERROS: 0** (`teste_diario_seguranca`, `teste_fluxos`, `teste_transparencia`, `teste_legislativo`). Falhas reais encontradas e corrigidas antes: (1) assinatura chamada dentro do laço de eventos (pyHanko usa `asyncio.run`) → movida para thread; (2) `no-store` dos painéis não saía (caminho reescrito pelo roteador) → corrigido; (3) arquivos da cadeia de teste saíam 644 → 600 e teste passou a verificar.
- `segredos/` criada (700, dono 1001; `a1/`, `icp/`, `act/`, `teste/`), cadeia de TESTE gerada (arquivos 600), montada **só leitura** nos containers (conferido: escrita recusada).
- `.env` (600): acrescentadas sem exibir valores `DIARIO_MODO=teste`, `TOTP_CHAVE`, `CPF_HMAC_CHAVE` (gerados) e, em branco para o órgão, `ACT_URL`, `ACT_USUARIO`, `ACT_SENHA`, `GOVBR_CLIENT_ID`, `GOVBR_CLIENT_SECRET`, `GOVBR_AMBIENTE=staging`.
- Backup → `up -d` → `provision atualizar`: migrações 007/008 e 1 integração Câmara → Prefeitura (token no banco de controle).
- Conferência em produção: domínios 200; `/admin/2fa` sem login → volta ao login; `/admin/govbr` 404 (sem credenciais, correto); CSP com `frame-ancestors 'none'`, X-Frame-Options DENY, `no-store` no painel; cadeia de teste carregando; logs sem erro; demais sites 200; **0 edições do Diário em produção**.
- ⚠️ Achado na conferência: em modo teste, o worker geraria a edição “sem atos” a partir de segunda (16h) e gastaria a numeração oficial com edições de teste. **Corrigido no código** (`DIARIO_AUTOMATICO_TESTE=0` por padrão + comando `limpar-teste`), **aguardando reimplantação** (precisa ser antes de segunda, 09/11, 16h).

## Variáveis do .env que o órgão (você) preenche
- `A1_SENHA_<NOME>` — senha de cada certificado A1 (uma variável por signatário; o nome é informado na designação).
- `ACT_URL`, `ACT_USUARIO`, `ACT_SENHA` — dados do contrato com a ACT.
- `GOVBR_CLIENT_ID`, `GOVBR_CLIENT_SECRET`, `GOVBR_AMBIENTE` (staging → producao), opcional `GOVBR_NIVEL_MINIMO` (prata|ouro).
- `DIARIO_MODO=oficial` — só depois de certificado, AC Raiz e ACT prontos.
- Já preenchidas (não alterar): `TOTP_CHAVE`, `CPF_HMAC_CHAVE`.
Comando para editar na VPS: `nano /opt/portal_web/.env` (depois `docker compose up -d app worker`).

## O que o órgão precisa providenciar para sair do modo teste
1. Certificado ICP-Brasil **A1** do responsável pela edição (assinatura final automática) e certificados dos signatários dos cadernos (A1, em nuvem ou A3/token).
2. **Contrato com uma ACT credenciada** (ex.: Serpro, Prodesp) com URL RFC 3161 e credenciais.
3. **Atos de designação** dos signatários (Prefeito e Presidente da Câmara, ou servidores designados) e do setor responsável pela edição.
4. **Solicitação de integração ao Login Único gov.br** com as 3 URLs de retorno (README, Fase 6).
5. AC Raiz ICP-Brasil em `segredos/icp/` (download no ITI) e, se usar certificado em nuvem, a API e as credenciais do provedor.

## Pendências da Fase 6
- Reimplantar a correção da rotina automática em modo teste (antes de 09/11, 16h).
- Login: na próxima entrada, os administradores da Prefeitura, da Câmara e o gestor cadastram o autenticador e guardam os códigos de recuperação.
- Conformidade PDF/A-2b não validada com veraPDF (não instalado); a conversão é feita pelo Ghostscript com perfil sRGB e metadados PDF/A.
- Integração real com ACT, certificado em nuvem e gov.br só testável com os contratos (o fluxo gov.br foi testado com servidor simulado).

## Como desfazer a Fase 6
`git checkout fase-5 -- . && docker compose build app worker && docker compose up -d app worker` (tabelas das migrações 007/008 ficam sem uso; `segredos/` pode ser mantida). Dumps de antes: `backups/*-2026-11-07.dump`.

## Onde parou
**Fase 6 concluída em MODO TESTE (07/11/2026).** Correção da rotina automática reimplantada (backup antes; 4 suítes com ERROS: 0 na imagem nova): em modo teste o worker não cria/publica edições sozinho (`DIARIO_AUTOMATICO_TESTE=0`); produção com 0 edições do Diário em pm-bora e cm-bora; branch `fase-6` mesclada em `main` com tag `fase-6`.

Para passar a OFICIAL falta (com o órgão): certificados A1/A3 ICP-Brasil reais em `segredos/a1` e raízes em `segredos/icp`, contrato com ACT (preencher `ACT_*`), credenciais gov.br (`GOVBR_CLIENT_ID`/`GOVBR_CLIENT_SECRET`), lei municipal do Diário e designações; depois `DIARIO_MODO=oficial` e `python -m app.diario_servico limpar-teste` — cada passo com aprovação.

## Fase 7 — Painel de indicadores (módulo "bi")

### ETAPA 0 — Descoberta (07/11/2026, só leitura, a partir da VPS)
- Fase 6 conferida: tag `fase-6` contida em `main`. **`Docs/fase7.tgz` não existe na VPS**; `Docs/PEDIDO-FASE7.md` e as referências (FONTES-DADOS.md de 05/11, protótipos) já estavam presentes e foram usados.
- Respondem: Fiorilli (receitas/despesas 2026 até 06/11), PNCP (falhou na 1ª tentativa, respondeu na 2ª), TCESP receitas (último mês com dados: set/2026; out/2026 vazio), Siconfi RREO Anexo 14 (último com saúde/MDE/FUNDEB: 2026 3º bim; 1º, 2º e 4º bim. vêm sem essas linhas), CNES (2 estabelecimentos), SIDRA 2612/2654 (até 2024), SIDRA 6449 (até 2021), IBGE agregados v3 (população estimada 2026, Censo 2022, PIB até 2023), IBGE pesquisas v1 (PIB per capita, IDEB 40, CEMPRE 19 até 2024, Censo 2022 alfabetização e esgotamento).
- Não respondem / bloqueados: TCESP IEG-M Pentaho (401 — exige autenticação, não contornado), MDS MI Social (302 para aviso de manutenção), INEP download.inep.gov.br (conexão TLS encerrada pelo servidor a partir da VPS — não contornado), QEdu (robots.txt 403 — descartado).
- Vacinação PNI: responde, mas devolve microdados individuais e sem filtro por município → mantém desligado; a amostra de 1 registro foi apagada na hora.
- e-SIC/Ouvidoria do portal: tabela `esic` (tipo pedido/manifestação) com 0 registros em pm-bora e cm-bora.
- Arquivos temporários da descoberta apagados. Lista de fontes **aprovada pelo usuário em 07/11/2026** ("Aprovo a lista").

### Implementação (branch `fase-7`, 07/11/2026)
- **Migrações** `009_plataforma_indicadores` (fontes novas `ibge`, `cnes`, `mds`, `pni`, `painel`; tabela `indicadores_publicos` por código IBGE, para servir a outros municípios) e `010_orgao_indicadores` (`indicadores` = catálogo; `indicador_valores` = série com período, data de referência, valor, nota, parcial, origem coletor/manual, usuário e motivo; `indicador_historico`). Idempotentes, via `provision atualizar`.
- **Catálogo** (`app/painel.py`): 42 indicadores em 6 áreas, sendo 8 do IEG-M (resultado geral e 7 dimensões). Textos neutros (classe transparência). Até 4 destaques na página inicial (padrão: receita do ano, saúde 15%, educação 25%, população). O código atualiza fonte, link e unidade; texto explicativo, meta, visibilidade, ordem e destaque são do administrador e nunca são sobrescritos.
- **Coletores** (`app/coletores/indicadores.py`, no worker, só com o módulo "bi" ligado):
  - IBGE (população 6579 + Censo 4709, PIB per capita 38/47001, CEMPRE 19 pela última versão, Censo 2022 10101, IDEB 40, SIDRA 2612/2654): semanal.
  - CNES por tipo: semanal.
  - `painel` (receita/despesa Fiorilli, TCESP para anos fechados, PNCP, e-SIC/Ouvidoria e mínimos do Siconfi): a cada hora das 7h às 19h; o Siconfi, no máximo 1 vez por dia, e anos fechados só uma vez.
  - MDS e PNI ficam prontos e **desligados**.
- **Correção da Fase 4:** a busca do PNCP traz `valor_global` sempre vazio; o coletor agora grava o homologado ou, se não houver, o estimado.
- **Siconfi:** em 2022 e 2023 o Anexo 14 de Borá não traz as linhas dos mínimos, então esses anos ficam sem valor (nada inventado). Em 2026, o FUNDEB ainda não aparece em nenhum bimestre.
- **LGPD:**
  - Contagens de pessoas abaixo de 5 aparecem como "menos de 5" em telas, gráficos, CSV, JSON, ODS e API (valor vazio).
  - Percentual e prazo médio do e-SIC só são calculados com 5 ou mais pedidos respondidos.
  - Nunca nome de solicitante; nunca a lista de profissionais do CNES; vacinação desligada (microdados).
- **Portal:**
  - `/painel` com abas, cartões (número, unidade, referência, variação em texto, situação da meta em texto, mini gráfico decorativo, fonte e atualização, aviso "dado de <data>" se a última coleta falhou).
  - `/painel/<indicador>` com gráfico SVG gerado no servidor (paleta Okabe-Ito, rótulos em todas as barras, meta tracejada, barra tracejada para "menos de 5", `role=img` com título e descrição), tabela equivalente, ficha (fonte com link, periodicidade, referência, atualização) e "Base legal:".
  - Downloads CSV/JSON/ODS por indicador e do painel inteiro, também listados em `/dados-abertos`.
  - API pública `/painel/api/indicadores.json` e `/painel/api/<indicador>.json`; a Câmara deve ler por aqui, se precisar.
- **Página inicial:** o bloco "Indicadores em números" mostra os destaques do catálogo quando o módulo está ligado; sem o módulo, volta ao conteúdo da Fase 4.
- **Painel administrativo** `/admin/indicadores` (só perfil admin, só com "bi"):
  - situação da última coleta, ativar/ocultar, ordem e meta (exige base legal);
  - texto explicativo, recusado se tiver tom de propaganda;
  - destaque (máximo 4);
  - lançamento manual só para indicadores sem fonte automática (IEG-M e Saeb), com motivo obrigatório, histórico e auditoria; exclusão com motivo;
  - botão "Coletar agora".
- **Testes** (`tests/teste_painel.py`, respostas gravadas em `tests/fixtures/painel_respostas.json`, sem internet, banco de TESTE): coleta e série, falha mantendo o último valor com aviso, "menos de 5", lançamento manual com auditoria e histórico, CSV/JSON/ODS, módulo desligado esconde tudo, acessibilidade (gráfico com título/descrição e tabela equivalente). Resultado: **ERROS: 0**; as 4 suítes anteriores também com **ERROS: 0** (código novo montado na imagem atual, sem build).
- **Conferência só de leitura dos coletores contra as fontes reais** (sem gravar): população 2026 = 935; IDEB anos iniciais (municipal) 2025 = 6,6; saúde 2025 = 20,36%; MDE 2025 = 31,23%; FUNDEB 2025 = 97,73%; CNES = 2 estabelecimentos. Tudo bate com a ETAPA 0.

### Onde parou
Código pronto e testado na branch `fase-7` (sem build nem implantação). **Aguardando aprovação** para:
1. snapshot;
2. build;
3. backup e `up -d`;
4. `provision atualizar`;
5. ligar o módulo "bi" da Prefeitura no console;
6. primeira coleta real;
7. conferência de 5 indicadores com a fonte;
8. merge e tag `fase-7`.

### Implantação (07/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Build feito; as 5 suítes com a imagem nova deram ERROS: 0. Backup feito, `up -d` de app e worker (app saudável) e `provision atualizar` (42 indicadores e 5 fontes do painel em pm-bora; migração 010 também no banco da Câmara, sem catálogo).
- Módulo "bi" contratado para pm-bora (UPDATE em `orgao_modulos` + registro em `log_console`). `/painel` responde 200.
- Primeira coleta: CNES ok (2), IBGE ok (67 valores de 11 indicadores), Siconfi ok (11 valores), dados próprios ok.
- **Problema encontrado:** o PNCP derrubou a conexão nas páginas 7 e 11, então a coleta foi parcial. Os registros de 2025 no banco vão só de 07/08 a 18/12/2025, mas o painel publicou 2025 como "ano completo" (184 contratações). Decisão do usuário: "Aprovo os dois".
- **Correção (aprovada):**
  - Os 3 indicadores de contratações foram ocultados de imediato.
  - Código: um ano do PNCP só é publicado se o banco já tem publicações do ano anterior (a busca vem da mais recente para a mais antiga), e valores de anos incompletos são apagados. Há teste novo para isso.
  - As 5 suítes deram ERROS: 0. Depois: build, backup, `up -d` e a coleta do painel.
  - Hoje o painel publica só 2026 (466 contratações, parcial, até 07/11). Os 3 indicadores voltaram a ficar visíveis.
  - Pendente: o PNCP derruba a conexão por volta da página 7 a 11. Os anos anteriores entram quando uma coleta de 6 em 6 horas conseguir ler mais páginas. Uma melhoria futura é retomar a paginação de onde parou.
- **Conferência de 5 indicadores no domínio × fonte original** (07/11/2026, 13h54 de Brasília; valor do domínio lido em `/painel/api/<indicador>.json`, valor da fonte lido direto da API oficial):

| Indicador | Domínio (pmbora.conectatech.tech) | Fonte original | Resposta da fonte | Confere |
|---|---|---|---|---|
| População estimada 2026 | 935 | IBGE agregados v3, tabela 6579, variável 9324, N6[3507209] | `{'2026': '935'}` | sim |
| PIB per capita 2023 | R$ 133.365,32 | IBGE pesquisas v1, 38/47001/3507209 | `{'2023': '133365.32'}` | sim |
| IDEB anos iniciais, rede municipal, 2025 | 6,6 | IBGE pesquisas v1, 40/78188/3507209 (INEP) | `{'2025': '6.6'}` | sim |
| Aplicação em saúde 2025 | 20,36% | Siconfi RREO 2025, 6º bimestre, Anexo 14, id_ente 3507209 | "% Aplicado Até o Bimestre" = 20.36 | sim |
| Estabelecimentos de saúde (nov/2026) | 2 | CNES, `estabelecimentos?codigo_municipio=350720` | 2 (tipos 2 e 68) | sim |

- Verificação final:
  - pmbora: `/`, `/painel`, `/painel/saude_minimo`, `/dados-abertos`, download ODS e `/admin/login` respondem 200; a página inicial mostra o bloco de destaques.
  - cmbora responde 200, e `/painel` da Câmara responde 404 (sem painel próprio, como pedido).
  - Worker sem erros; demais sites da VPS no ar.

### Onde parou
Fase 7 concluída (07/11/2026): implantada, conferida, `fase-7` mesclada em `main` com tag `fase-7` (aprovado: "Aprovo o merge"). Pendências fora do código: PNCP instável (anos anteriores entram quando uma coleta ler mais páginas), MDS fora do ar (ligar a fonte `mds` quando voltar), IEG-M e Saeb por lançamento manual, `Docs/fase7.tgz` nunca chegou à VPS.

## Fase 7 — fontes IEG-M e Saeb/IDEB (branch `fase-7-fontes`)

### Revisão (07/11/2026, só leitura)
- IEG-M (Pentaho do TCESP): 401 `Basic realm="Pentaho Realm"` nos anos-base 2021 a 2024, também com User-Agent de navegador + Referer. O endereço público `iegm.tce.sp.gov.br` redireciona para o painel com credencial anônima publicada pelo próprio Tribunal; não foi usada.
- INEP: planilhas oficiais `https://download.inep.gov.br/ideb/resultados/divulgacao_{anos_iniciais|anos_finais|ensino_medio}_municipios_{ANO}.zip` (edição 2025 publicada em 05/08/2026). O servidor não envia o certificado intermediário "RNP ICPEdu GR46 OV TLS CA 2025" (GlobalSign); com ele (obtido do endereço oficial AIA do próprio certificado e conferido contra a raiz GlobalSign R46), a verificação TLS passa normalmente. Linhas de Borá conferidas (IDEB igual ao do IBGE).

### Decisões do usuário (07/11/2026)
- **IEG-M: o usuário (DTIC da Prefeitura de Borá) AUTORIZOU, por decisão própria em 07/11/2026, o uso do usuário/senha anônimos publicados pelo TCESP no redirecionamento de iegm.tce.sp.gov.br.** O Claude não lê, não copia e não mostra essa credencial: variáveis `IEGM_USUARIO` e `IEGM_SENHA` no `.env.example` (vazias); o próprio usuário preenche no `.env` da VPS. Sem elas, a coleta fica desligada sem erro.
- IEG-M com modo de atualização automático (acesso anônimo do TCESP) ou manual em /admin/indicadores, com auditoria; lançamento manual como reserva.
- Saeb/IDEB pelas planilhas do INEP: 3 etapas; cartão pela rede Pública com o nome da rede responsável; Matemática e Língua Portuguesa como indicadores; rendimento na página do indicador; metas projetadas (até 2021) só como referência histórica no gráfico; ND = "não divulgado pelo INEP", nunca zero; certificado intermediário em `deploy/certs/` com aviso 60 dias antes do vencimento.

### Implementação (branch `fase-7-fontes`, 07/11/2026)
- **INEP (fonte `inep`, verificada a cada 30 dias):**
  - Baixa a edição mais recente de cada etapa (anos iniciais, anos finais, ensino médio); a planilha traz a série inteira.
  - Filtra o código IBGE do órgão (nada fixo de Borá) e grava em `indicadores_publicos`.
  - Arquivo com a mesma data de modificação não é baixado de novo.
  - Leitura do `.xlsx` em fluxo (`app/coletores/planilha.py`), sem biblioteca nova: pico de 91 MB no container com limite de 256 MB.
  - O servidor do INEP derruba conexões às vezes: 4 tentativas com espera.
- **Indicadores do INEP:**
  - IDEB, Saeb de Matemática e Saeb de Língua Portuguesa por etapa, da rede **Pública**.
  - Cada valor diz a rede responsável: anos iniciais = "rede municipal (responsabilidade da Prefeitura)"; anos finais e ensino médio = "rede estadual (responsabilidade do Governo do Estado)".
  - O rendimento (P) fica na página do IDEB (coluna da tabela e downloads), sem cartão próprio.
  - As metas projetadas do INEP (até 2021) aparecem só como referência histórica no gráfico (losangos verdes com legenda), nunca como meta atual.
  - "ND" e "-" viram "não divulgado pelo INEP": nunca zero; no gráfico, sem barra.
  - Os indicadores de IDEB que vinham do IBGE (`edu_ideb_*_mun/est`) e o `edu_saeb` manual foram **retirados**: ficam ocultos, sem coletor e com a série guardada.
- **Certificado:** `deploy/certs/rnp-icpedu-gr46-ov-tls-ca-2025.pem`, válido até **19/11/2030**, com origem e SHA-256 em `deploy/certs/LEIAME.md`.
  - Ele é usado junto com as raízes do certifi: a verificação TLS e a do nome continuam ligadas.
  - Aviso no painel administrativo e na mensagem da coleta 60 dias antes do vencimento.
- **IEG-M (fonte `iegm`, verificada a cada 30 dias):**
  - Consulta `faixaTodosMunicipiosPeriodo` por ano-base (2014 até o ano anterior), com Basic auth usando `IEGM_USUARIO` e `IEGM_SENHA` do `.env`.
  - Sem credencial ou com o IEG-M em modo manual, não consulta e não registra erro.
  - As colunas são mapeadas por `metadata[].colName` (tabela larga ou longa), com filtro pelo código IBGE. O mapeamento pode ser fixado no parâmetro `colunas` da fonte.
  - Se as colunas não forem reconhecidas, a coleta falha com a lista dos **nomes** das colunas recebidas, sem valores e sem credencial.
  - Grava a faixa (texto) e a nota (valor) do resultado geral e das 7 dimensões, por edição: período = ano-base, nota "edição N+1".
  - Falha: mantém o último valor válido, mostra o aviso "dado de <data>" no portal e registra a coleta com falha no console.
- **Admin:**
  - No IEG-M: "Modo de atualização: automático (acesso anônimo do TCESP) / manual", com a explicação de que a consulta não tem documentação oficial e pode mudar sem aviso. A troca vale para os 8 indicadores e fica na auditoria e no histórico.
  - Mostra se a credencial está preenchida (sem mostrar o valor), a situação da última coleta e o botão "Coletar agora" da fonte.
  - Lançamento manual de reserva no IEG-M e nos indicadores do INEP; a coleta nunca sobrescreve um período lançado à mão.
- **Testes:** `tests/teste_painel_fontes.py`, com planilhas reduzidas no formato real do INEP e respostas do CDA com **valores fictícios**, sem internet. ERROS: 0, e as outras 6 suítes também deram ERROS: 0.
- **Ressalva:** os nomes reais das colunas do CDA do IEG-M só serão confirmados na primeira coleta com a credencial preenchida.

### Onde parou
Código pronto e testado na branch `fase-7-fontes`, ainda não implantado. Aguardando aprovação para:
1. build;
2. testes com a imagem nova;
3. backup e `up -d`;
4. `provision atualizar`;
5. coleta do INEP.

Depois disso, o usuário preenche `IEGM_USUARIO` e `IEGM_SENHA` no `.env` da VPS. Em seguida vêm: `up -d` para carregar o `.env`, IEG-M em modo automático, primeira coleta e conferência das colunas.

### Implantação (07/11/2026, aprovada: "Aprovo os 5 passos")
- Build; 6 suítes com a imagem nova: ERROS: 0. Backup; `up -d` de app e worker (saudáveis); `provision atualizar`: migração 011, 9 indicadores novos e as fontes `inep` e `iegm`; os 6 indicadores antigos foram retirados (ocultos, sem coletor; `/painel/edu_ideb_ai_mun` responde 404).
- Coleta do INEP (edição 2025, 3 etapas, worker com 47 MB): anos iniciais com 30 valores (redes Municipal e Pública), anos finais com 21 (Estadual e Pública), ensino médio com 15 (Estadual e Pública).
- Conferência no domínio (`/painel/api/...`) com as linhas da planilha do INEP mostradas antes:

| Indicador | No portal | Na planilha |
|---|---|---|
| IDEB anos iniciais 2025 | 6,6 | 6.6 |
| Saeb Matemática, anos iniciais 2025 | 240,82 | 240.82 |
| IDEB anos finais 2025 | 5,3 | 5.3 |
| Saeb Língua Portuguesa, anos finais 2025 | 267,26 | 267.26 |
| IDEB ensino médio 2025 | "não divulgado pelo INEP" | "-" |

  Rendimento e meta projetada aparecem na tabela e nos downloads; a rede responsável é mostrada nos cartões; "não divulgado" no gráfico, sem barra.

### Onde parou
INEP no ar e conferido. **Aguardando o usuário preencher `IEGM_USUARIO` e `IEGM_SENHA` no `.env` da VPS.** Depois, com aprovação:
1. `up -d` para carregar o `.env`;
2. IEG-M em modo automático;
3. primeira coleta e conferência das colunas;
4. merge de `fase-7-fontes` e tag;
5. ETAPA 1 do `Docs/PEDIDO-FASE7-LAYOUT.md`.

### Mudança pedida pelo usuário (07/11/2026): credencial do IEG-M pelo console, não pelo .env
- **Console → Integrações → Credenciais de fontes**, só para o gestor da plataforma; o domínio do órgão responde 404 e o console sem login redireciona.
  - Por fonte, começando pelo `iegm`: usuário e senha só de gravação. A tela mostra "configurada em <data> por <usuário>", com os botões Trocar, Apagar e "Testar conexão".
  - O teste mostra só o código HTTP e se veio JSON válido; em erro, só o tipo do erro.
- **Gravação:** tabela `credenciais_fontes` (migração 012), cifrada com Fernet usando `CHAVE_CREDENCIAIS` do `.env`. Sem a chave, o cadastro fica desligado; com chave errada, a credencial aparece como "ilegível: recadastre".
- **Ordem de leitura no coletor:** console, depois reserva `IEGM_USUARIO`/`IEGM_SENHA` do `.env`, depois nenhuma (desligado, sem erro).
- **Admin do órgão:** continua só "automático/manual". Em automático sem credencial, aparece "aguardando configuração da plataforma" na tela do IEG-M e na lista.
- **Auditoria:** cadastrar, trocar, apagar e testar vão para o `log_console`, sem valores. O teste confere que nenhum valor aparece em `log_console`, `coletas`, `auditoria`, `indicador_historico`, no resultado do teste nem na saída do processo.
- **Backup:** `deploy/backup.sh` passa a copiar o `.env` (com `CHAVE_CREDENCIAIS`) para `backups/env-AAAA-MM-DD`, com permissão 600 e retenção de 14 dias. O README avisa que perder a chave obriga a recadastrar.
- **Testes:** `teste_painel_fontes` e as outras 5 suítes deram ERROS: 0 (código montado na imagem atual).

### Onde parou
Aguardando aprovação para:
1. build;
2. 6 suítes com a imagem nova;
3. backup;
4. gerar `CHAVE_CREDENCIAIS` direto no `.env`, sem exibir;
5. `up -d`;
6. `provision atualizar` (migração 012).

Depois, o usuário cadastra a credencial pela tela. Em seguida vêm: modo automático do IEG-M, primeira coleta, merge e tag, e a ETAPA 1 do layout.

### Implantação das credenciais (07/11/2026, aprovada: "Aprovo os 6 passos")
- Build feito; as 6 suítes com a imagem nova deram ERROS: 0; backup feito (agora inclui `backups/env-2026-11-07`, permissão 600).
- `CHAVE_CREDENCIAIS` gerada direto no `.env`, sem exibir: 1 linha, `.env` com permissão 600 e dono root. A cópia do `.env` no backup de hoje foi atualizada para conter a chave.
- `up -d` de app e worker (saudáveis; a chave carregou e é válida); `provision atualizar` aplicou a migração 012 (`credenciais_fontes` vazia).
- Verificação: `gestao.../credenciais` sem login redireciona para `/login`; `pmbora.../credenciais` responde 404; `/painel` responde 200.

### Onde parou
**Aguardando o usuário cadastrar a credencial do IEG-M** em gestao.conectatech.tech → Integrações → Credenciais de fontes. Depois, com aprovação: modo automático do IEG-M, primeira coleta e conferência das colunas, merge de `fase-7-fontes` e tag, e ETAPA 1 do layout.

### Incidente: IEG-M com o resultado geral trocado pela dimensão de TI (07/11/2026)
- **O que houve:** na primeira coleta real (15h13), a consulta do TCESP veio com 12 colunas: `exercicio_ref, ano_apuracao, codigo_municipio, nome, iegm, iplanejamento, ifiscal, ieduc, isaude, iamb, icidade, igov`.
  - O mapeamento não reconhecia `igov` como governança de TI e, sem regra, encaixou essa coluna como "resultado geral", sobrescrevendo a coluna `iegm`.
  - Ficaram publicados por cerca de 10 minutos: o resultado geral com a faixa de TI (ex.: "A" em 2024 em vez de "C+") e a dimensão de TI sem dado. As outras 6 dimensões estavam corretas.
- **Contenção (aprovada: "Aprovo os 4 passos"):** os 8 indicadores foram ocultados.
  - Conferido que sumiram de `/painel` (todas as abas), da página inicial, dos downloads CSV/JSON/ODS (do painel inteiro e de cada indicador: 404), de `/dados-abertos` e da API pública (lista e por indicador: 404), também sem o parâmetro anti-cache.
  - Não há cache no proxy (sem `proxy_cache` no nginx); só o navegador guarda a API e os downloads por até 5 minutos.
- **Correção do código:**
  - Só nomes conhecidos são aceitos: `iegm` = geral, `ieduc`, `isaude`, `iplanejamento`, `ifiscal`, `iamb`, `icidade`, `igov` = TI.
  - As colunas de identificação (`exercicio_ref`, `ano_apuracao`, `codigo_municipio`, `nome`) ficam fora do mapeamento.
  - Coluna desconhecida é ignorada e aparece como "AVISO: colunas desconhecidas ignoradas" na coleta e no console; nunca é encaixada por falta de regra.
  - Duas colunas para o mesmo indicador fazem a coleta ser recusada sem gravar nada.
  - O rótulo vem da própria resposta: período = `exercicio_ref` (ano-base) e "edição `ano_apuracao`"; ano-base divergente ou edição repetida é recusado.
  - Teste com exatamente as 12 colunas reais (valores fictícios). As 6 suítes deram ERROS: 0; depois vieram build, backup e `up -d`.
- **Dados:** os valores errados (77 no órgão e 77 em `indicadores_publicos`) foram exportados para `backups/iegm-valores-errados-2026-11-07.csv` (permissão 600) e apagados. Não havia lançamento manual.
  - A nova coleta trouxe 88 valores: 11 edições × 8 indicadores, sem colunas ignoradas e sem edição repetida. O TCESP não envia nota numérica, só a faixa.
  - Os 8 indicadores receberam no histórico a nota "valores corrigidos em 07/11/2026 por erro de importação", e a correção foi registrada na auditoria.
- **Situação:** os indicadores continuam **ocultos** até o ok do usuário, depois da comparação com o painel do TCESP.
- **Reexibição (07/11/2026, ok do usuário: "Confere, reexibir"):** a série foi conferida pelo usuário com o painel do TCESP. Os 8 indicadores voltaram a ficar visíveis, com histórico e auditoria. API: resultado geral 2024 = C+ e i-Gov TI 2024 = A; o CSV do painel tem 88 linhas do IEG-M.
- `fase-7-fontes` mesclada em `main` com a tag `fase-7-fontes`.

### Onde parou
Fontes da Fase 7 concluídas: INEP e IEG-M no ar, credencial pelo console. Próximo passo: ETAPA 1 do `Docs/PEDIDO-FASE7-LAYOUT.md` (avaliação só leitura), numa branch própria.

## Fase 7 — layout do /painel (branch `fase-7-layout`)
### ETAPA 1 — Avaliação (07/11/2026, só leitura)
- **Capturas:** feitas com o Playwright 1.49, num container descartável da imagem `mcr.microsoft.com/playwright:v1.49.0-jammy`, que já existia na VPS. O `playwright-core` foi instalado só dentro desse container, que foi removido; nada foi instalado na VPS.
  - 14 capturas de página inteira (7 abas × 1280 px e 390 px) e 2 do foco das abas, em `Docs/avaliacao-painel/`, com as medidas em `medidas.json`.
- **Tabela comparativa:** está em `Docs/avaliacao-painel/AVALIACAO.md`.
  - **O que está igual:** fonte e cores, nenhuma rolagem horizontal em 390 px, aba guardada na URL.
  - **Divergências principais:**
    - abas em caixas em vez de pílulas, e sem o selo da data das finanças;
    - faltam os gráficos de finanças (mês a mês, para onde vai, de onde vem, execução);
    - as seções por tema estão em cartões genéricos;
    - o IEG-M está sem o bloco próprio e sem a distribuição dos municípios;
    - falta a lista "Ainda não disponíveis";
    - o foco amarelo tem contraste baixo sobre fundo branco.
- **Parado aguardando aprovação das correções** e de 5 decisões: cálculo por habitante, coletor mensal da Fiorilli, semântica das abas, comparação do IDEB com SP e Brasil, e novos dados agregados do CNES e do IEG-M.

### ETAPA 2 — Correção (07/11/2026, aprovada com as 5 decisões do usuário)
- **Abas e selo:** links com `aria-current`, em pílula (44 px, raio 999 px), `?tema=` (o `?aba=` antigo redireciona com 301). Selo "Finanças lidas do sistema contábil em <data/hora>" com a última coleta Fiorilli ok; o ponto pulsante desliga com `prefers-reduced-motion`.
- **Dinheiro público:**
  - KPIs no padrão do protótipo. Os valores por habitante mostram o ano da estimativa do IBGE e "cálculo do portal: valor oficial ÷ população estimada".
  - "Receita e despesa paga, mês a mês" (SVG + tabela) vem da nova fonte `financas` (Fiorilli por mês, diária de madrugada, tabela `fin_mensal`, migrações 013/014). A API devolve o movimento do período; janeiro + fevereiro = acumulado, conferido.
  - "Para onde vai o dinheiro" usa o agrupamento editável das unidades por área (`areas_unidades`): a sugestão é a função de governo predominante nos empenhos, e o administrador troca em /admin/indicadores, com auditoria.
  - "De onde vem o dinheiro": repasses 1700 + 2400 sobre a receita bruta, e as 5 maiores origens.
  - "Execução do orçamento": 3 barras e a linha do ritmo do ano.
  - Sem dado do ano, cada bloco não aparece.
- **Contratações:** barras por modalidade.
- **Saúde, Educação e Assistência social:** KPIs; mínimos legais com linha tracejada; CNES com nome, tipo e endereço (dado institucional, tabela compartilhada `dados_publicos/cnes_lista`); nascimentos e óbitos, com "menos de 5"; orçamento da área por unidade; benefícios com o aviso do MDS.
- **IDEB:** comparação com SP e Brasil só na mesma etapa e na rede pública, pelas planilhas `divulgacao_regioes_ufs_ideb_{ANO}` e `divulgacao_brasil_ideb_{ANO}` do INEP; sem linha equivalente, não aparece. Em 2025 a planilha de SP não tem rede pública no ensino médio, então essa comparação fica fora.
- **IEG-M:** faixa em destaque, dimensões, "Como os municípios paulistas ficaram" (contagem agregada por faixa em `dados_publicos/iegm_distribuicao`) e evolução em `details`.
- **Demais blocos:** "O município"; "Acesso à informação"; "Ainda não disponíveis", gerado do catálogo (indicadores visíveis sem dado, com o motivo).
- **Acessibilidade e datas:**
  - Foco em anel duplo (amarelo + escuro) no portal, no admin e no console; ESPEC-VISUAL.md atualizado.
  - O filtro de datas passa a converter para o horário local.
- **Testes:** `tests/teste_painel_layout.py` (dados fictícios) e as 6 suítes anteriores: todas com ERROS: 0.
- **Capturas "depois":**
  - Feitas numa prévia descartável: PostgreSQL de teste com cópia dos bancos atuais (`pg_dump`, só leitura), app com o código novo e as coletas novas rodando contra a cópia. A prévia foi desligada e a cópia apagada.
  - Arquivos em `Docs/avaliacao-painel/depois/` e, lado a lado com as atuais, em `Docs/avaliacao-painel/lado-a-lado/`.
  - Sem rolagem horizontal em 390 px; pílulas com 44 px.
  - O brasão quebrado aparece só na prévia: as imagens `.webp` são geradas no build.
- **Onde parou:** aguardando aprovação para implantar (build, testes, backup, `up -d`, `provision atualizar`, primeiras coletas `financas`, `cnes`, `inep` e `iegm`), merge e tag.

### Implantação do layout (07/11/2026, aprovada: "Aprovo os 6 passos")
- Build; as 7 suítes com a imagem nova deram ERROS: 0. Backup; `up -d` de app e worker (saudáveis). `provision atualizar` aplicou as migrações 013 e 014 e cadastrou a fonte `financas`, que herda `base` e `empresa` da `fiorilli`.
- **Primeiras coletas:**
  - `financas`: 11 meses de 2026 e 22 unidades no agrupamento por área.
  - `cnes`: lista com 2 estabelecimentos.
  - `iegm`: distribuição dos 644 municípios.
  - `inep`: comparação com UF e Brasil, ok.
- **Conferência no domínio:**
  - Todos os blocos presentes; o selo mostra "07/11/2026 19:05" (horário local).
  - `?aba=saude` redireciona com 301 para `?tema=saude`.
  - A **soma dos meses é igual ao acumulado**: receita R$ 22.565.789,79 e despesa paga R$ 19.999.531,48.
  - Comparação do IDEB: SP 6,5 e Brasil 6,1 (rede pública, anos iniciais, 2025). IEG-M: C+, a mesma faixa de 261 dos 644 municípios.
  - Capturas da página no ar em `Docs/avaliacao-painel/implantado/`: nenhuma rolagem horizontal em 390 px, pílulas com 44 px e selo em todas as abas.
- `fase-7-layout` mesclada em `main` com a tag `fase-7-layout`.

### Onde parou
Fase 7 (painel, fontes e layout) concluída e no ar. Pendências fora do código:
- PNCP instável: os anos anteriores entram quando uma coleta conseguir ler mais páginas.
- MDS fora do ar.
- Vacinação aguardando uma fonte estável.

## Fase 8 — ajustes do portal da Prefeitura (branch `fase-8`)
### Antes de implementar (09/11/2026, só leitura)
- Pedidos das Fases 8, 9 e 10 versionados.
- **`Docs/referencia/prototipos/Main.dc.html` não foi atualizado na VPS:** data 07/11 e conteúdo idêntico ao da Fase 2.
- **Capturas atuais:** em `Docs/avaliacao-fase8/antes/` (início, /painel, receitas e Diário; 1280 e 390 px).
- **Esboço da nova página inicial:** protótipo HTML local, com capturas em `Docs/avaliacao-fase8/esboco/`.
- **Inventário e proposta:** em `Docs/avaliacao-fase8/PROPOSTA.md`.
  - Destinos repetidos hoje no cabeçalho: `/transparencia`, `/diario` e `/acesso` (e-SIC = Fale conosco).
- **Parado aguardando aprovação** do esboço e de 7 decisões.
- **Revisão v2 (09/11/2026):**
  - **Recebido:** `Main.dc.html` atualizado e `PEDIDO-FASE8.md` revisado, com o cabeçalho novo e os itens G (Transmissões), H (VLibras, eMAG, DOSVOX, MOTRIX) e I. O item J citado pelo usuário **não está no arquivo**.
  - **Feito:** esboço refeito na ordem do protótipo, com as capturas da v1 guardadas. Diagnóstico das Transmissões: na Prefeitura falta o módulo contratado e o canal; na Câmara não há canal nem vídeos; não existe integração com a API do YouTube.
  - **Parado aguardando:** o item J e mais 3 decisões (Publicações oficiais, YouTube e módulo, VLibras na CSP).
- **Decisões recebidas (09/11/2026):** item I (Legislação) acrescentado ao pedido; "Aprovo os 3" — bloco Publicações oficiais, integração com o YouTube (chave no console, canal por órgão, ao vivo a cada 2 min só na janela da agenda, gravações uma vez por dia) e VLibras liberado na CSP.

### Implementação (09/11/2026, branch `fase-8`, sem tocar a VPS de produção)
- **Banco:** migração `015_orgao_fase8.sql` (menus, atalhos, comunicados, perfis do Conheça com fotos e vídeos, legislação e relações; campos novos em conteúdos, atos do Diário, indicadores e transmissões) e `016_plataforma_fontes_youtube.sql` (fonte `youtube`). Idempotentes.
- **A) Cabeçalho:** barra de acessibilidade (com Câmara/Prefeitura, Área restrita e botão Libras), barra institucional na cor primária e barra do portal, vindas da tabela `menus`. A tela **Menus e atalhos** recusa destino repetido entre barras. Menu do celular em painel com seções, foco preso e Esc. Faixa de aviso configurável. Itens com classe vedada somem no defeso.
- **B) Cartões de indicador:** título curto (até 32 caracteres, obrigatório no painel e travado no banco), valor + unidade, contexto; fonte e datas no ⓘ (toggletip acessível; painel inferior no celular; sem JS, link para a página do indicador).
- **C) Botões:** "ver mais" da página inicial viraram o componente `.btn` (primário/secundário, 44 px).
- **D) Conheça:** perfis `/conheca/<slug>` com galeria (ampliação em `<dialog>`, setas, Esc, foco devolvido) e vídeos por youtube-nocookie; `/conheca` com filtro e busca; texto alternativo obrigatório; foto com pessoas só publica com autorização registrada; até 3 destaques; categoria Eventos = publicidade. As 3 fotos atuais viram perfis com descrição vazia.
- **E) Comunicados:** tipos editáveis (notícia recusada aqui; tipos de comunicado recusados em Conteúdos); validade; até 5 na página inicial; `/comunicados` com filtros por tipo e ano. À direita, "Serviços mais acessados" (contagem mensal de acessos, sem dado pessoal).
- **F) Notícias:** destaque (16:9, data e hora "08/11/2026, 09h44", resumo), 3 secundárias, lista de 5 e botão; capa com alt obrigatório, ponto focal, data/hora e agendamento. Some no defeso sem deixar espaço.
- **G) Transmissões:** coletor `coletores/youtube.py` (2 unidades de cota por consulta; só dentro da janela da agenda ou com transmissão ao vivo; varredura diária registra só vídeos que foram transmissões — vídeo comum do canal não entra). Erros só com código HTTP: a chave nunca vai para log. Chave cadastrada no console (campo único "Chave da API"). ID do canal validado (UC…) e aviso "Configure o canal" no painel.
- **H) Acessibilidade:** VLibras em todas as páginas (liga/desliga no painel). Achado: `vlibras.gov.br/app` redireciona para a pasta oficial no jsDelivr (`cdn.jsdelivr.net/gh/spbgovbr-vlibras/…`), então a CSP libera **só esse caminho**, além de `*.vlibras.gov.br`. Página Acessibilidade com VLibras, NVDA, DOSVOX e MOTRIX (endereços conferidos: respondem 200).
- **I) Legislação:** `/legislacao` montada sozinha com os atos (Lei, Lei Complementar, Decreto, Decreto Legislativo, Portaria, Resolução) das edições **oficiais** publicadas do Diário — edição de teste não entra. Relações (altera/revoga/regulamenta) informadas no envio do ato definem a situação. Página do ato, CSV/JSON com base legal. Importação opcional do acervo antigo por planilha (`Docs/modelos/legislacao.csv`, com simulação, tudo ou nada). A Câmara lê pela API pública da Prefeitura. **Limitação:** a proposição da Câmara não tem campo "norma gerada", então o vínculo lei ↔ proposição não é feito (nada inventado); fica para quando houver o campo.
- **J) Testes:** `tests/teste_fase8.py` novo, tudo ok. Cobre:
  - barras sem destino repetido e recusa no painel;
  - `/acesso` → 301;
  - comunicado recusa notícia, e conteúdo recusa tipo de comunicado;
  - foto com pessoas sem autorização não publica;
  - ordem do bloco de notícias e defeso;
  - legislação (Diário oficial × teste, relações, filtros, CSV/JSON, importação, Câmara pela API);
  - YouTube com dados simulados;
  - VLibras e CSP.
  - Suítes existentes atualizadas onde a Fase 8 mudou o esperado (bloco de serviços, título curto obrigatório, canal UC…) e **todas passam**: fluxos, painel, painel_layout, painel_fontes, diario_seguranca, transparencia e legislativo.
- **Prévia (cópia dos bancos, nada na produção):** a migração rodou limpa sobre os dados reais. Itens criados na cópia:
  - Prefeitura: 15 itens de menu; as 3 fotos atuais viraram perfis.
  - Câmara: 14 itens de menu.
  - Nas duas: fonte `youtube`.
- **Verificações no navegador (`Docs/avaliacao-fase8/depois/verificacoes.json`):**
  - axe sem violações em 12 páginas;
  - teclado ok (menu do celular, ⓘ);
  - CSP sem violação com o VLibras carregado e aberto;
  - sem rolagem horizontal;
  - cartões com a mesma altura.
  - Relatório em `Docs/avaliacao-fase8/EMAG.md`. **Teste com NVDA real não feito:** o NVDA só roda no Windows; o roteiro está no arquivo.
- **Corrigido durante a verificação:**
  - `.ic`/`.info` dos cartões colidiam com o ícone SVG e o cartão de vereador; renomeados para `.icard`/`.ic-info`.
  - Listas dentro de `role="img"` no painel (herança da Fase 7).
  - Na Câmara (6 itens + nome longo), a busca caía para a 2ª linha; agora vira o item "Buscar", como no protótipo.
  - Relações da legislação: coluna `tipo` sobrescrita no JOIN.
- **Capturas antes × depois:** `Docs/avaliacao-fase8/comparacao.html`, com as páginas novas e os estados (menu aberto, ⓘ, VLibras, busca aberta).

### Onde parou (Fase 8)
Código pronto e testado no branch `fase-8`. **Nada foi aplicado na VPS de produção.** Aguardando:
1. Aprovação do deploy (backup, build, testes, up -d, `provision atualizar`).
2. Quem contrata o módulo "audiencias" para a Prefeitura.
3. O endereço do acervo antigo de legislação.
4. A chave da YouTube Data API cadastrada no console e os IDs dos canais.

### Implantação da Fase 8 (09/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Snapshot da VPS confirmado pelo usuário. Backup com `deploy/backup.sh`: 3 bancos, mídia e `.env` (permissão 600).
- Build de app e worker. As **8 suítes** com a imagem nova (sem montar código) deram ERROS: 0 / tudo ok.
- `up -d` de app e worker: app saudável. `provision atualizar` aplicou as migrações 015 e 016:
  - Prefeitura: 15 itens de menu e 3 perfis do Conheça (das fotos atuais, descrição vazia);
  - Câmara: 14 itens de menu;
  - fonte `youtube` nas duas (inativa na prática até haver chave e canal).
- **Conferência no domínio** (`Docs/avaliacao-fase8/implantado/`): mesmo resultado da prévia.
  - axe sem violações em 12 páginas;
  - teclado ok (menu do celular, ⓘ);
  - VLibras carregado sem violação de CSP;
  - sem rolagem horizontal e sem destino repetido entre as barras.
  - `/acesso` responde 301 para `/fale-conosco`; `/legislacao.json` responde 200; a Câmara lê `/legislacao`.
  - Logs de app e worker sem erro.
- `fase-8` mesclada em `main` com a tag `fase-8`.

### Pendências da Fase 8 (dependem do usuário)
- Quem contrata o módulo "audiencias" da Prefeitura.
- O endereço do acervo antigo de legislação (Painel → Menus e atalhos → Legislação).
- A chave da YouTube Data API (console → Credenciais de fontes) e os IDs dos canais (Painel → Transmissões).
- O teste com NVDA real (roteiro em `Docs/avaliacao-fase8/EMAG.md`).

## Fase 9 — painel administrativo (branch `fase-9`)
### Antes de implementar (09/11/2026)
- Capturas "antes" em `Docs/avaliacao-fase9/antes/`, feitas em ambiente de teste descartável (removido depois).
- Esboço em `Docs/avaliacao-fase9/esboco/` e proposta em `Docs/avaliacao-fase9/PROPOSTA.md`.
- **Diagnóstico da avaliação:** o envio é gravado; a mensagem de agradecimento fica fora de vista (topo × âncora no rodapé).
- **Parado aguardando** aprovação do esboço e 5 decisões.

### Implementação (09/11/2026, branch `fase-9`, nada aplicado na VPS)
- Aprovado: o esboço e as decisões (registradas em `avaliacao-fase9/PROPOSTA.md`): `nh3`; "esqueci a senha" via administrador; redes: links + YouTube/Meta com credencial; álbuns separados do Conheça; tabelas do painel no celular.
- **Migrações:** `017_orgao_fase9.sql` (avaliação com hash de IP e moderação; álbuns, fotos e categorias; HTML do editor em conteúdos, comunicados e perfis; cópia do texto nas versões) e `018_plataforma_consultas.sql` (amostras das respostas, testes de consulta, histórico de parâmetros, configuração do console). Fonte `redes` acrescentada à lista completa de fontes (009/011/014/016).
- **1) Mapa do layout:** cartão "Onde fica no portal" fixo ao lado da lista. Destaque nos dois sentidos, bloco desligado tracejado. Ordem e liga/desliga mudam o mapa antes de salvar, com um botão "Salvar". No celular vira o botão "Ver mapa do layout". Sem JS, cada botão salva na hora. A reordenação entre regiões é recusada no servidor.
- **2) Avaliação:** causa corrigida (a resposta aparece no próprio bloco; com JS, sem recarregar).
  - Cookie próprio `aval` (código da página + dia) com prazo configurável (padrão 30 dias).
  - Limite de 5 avaliações por hora por conexão, com IP guardado só como hash com sal diário e apagado em 2 dias.
  - Abas Por página, Por mês, Comentários (moderação) e Regras. Política de privacidade atualizada.
- **3) Consultas:**
  - **Modo ensaio na camada de dados:** o coletor real roda, mas escritas são puladas e a conexão fica somente leitura. Cada requisição é anotada (método, URL sem segredo, HTTP, tempo, registros, trecho com CPF mascarado). Fora do ensaio, guarda a última resposta de cada consulta.
  - **Tela Integrações:** todas as fontes do órgão, inclusive os 11 endpoints do Fiorilli com o GET montado. Mostra parâmetros com a origem de cada valor, credencial ("configurada no console"), formato, periodicidade e mapeamento campo → destino.
  - **Teste e salvamento:** "Testar consulta" não grava. "Salvar e coletar agora" só com teste ok dos mesmos parâmetros nos últimos 30 minutos; a mudança exige confirmação e vai para o histórico e a auditoria.
  - **Indicadores:** abas por área e sub-abas por fonte, com a mesma tela de consulta. O lançamento manual agora fica liberado quando a coleta automática falha e exige a fonte informada.
- **4) Identidade em 7 abas:**
  - **Dados e textos:** inclui o título da tela de login.
  - **Tema e cores:** seletor visual + hexadecimal, contraste calculado na hora e prévia ao vivo; o servidor recusa cor abaixo de 4,5:1.
  - **Brasão, mascote e fundos:** destaque, login e sede com ponto focal e prévia dos recortes. O recorte é feito pelo ponto focal, não com ferramenta de corte livre.
  - **Favicon:** PNG gerando 16/32/180/512; SVG opcional, filtrado e servido com CSP própria.
  - **Redes sociais:** ícones, ordem, validação do domínio de cada rede. A sincronização (fonte `redes`, a cada 6 h) usa só YouTube (chave do console) e Meta (token "meta" no console); as miniaturas são servidas pelo portal e o bloco "Nas redes" some no defeso.
  - **Dados do município:** IBGE automático (população, área — pesquisa 33 —, PIB per capita, salário médio). Distância e IDHM ficam manuais e marcados (a API do IBGE não traz IDHM por município).
  - **Fotos e álbuns:** licença obrigatória e autorização de uso de imagem; categoria "suspender no período eleitoral"; foto principal do álbum e destaque do portal; páginas `/fotos` e `/fotos/<id>`.
- **5) Editor:** próprio, com formatação limitada (títulos, negrito, itálico, listas, links, citação, tabela, imagem). Ao colar do Word, os estilos são limpos no navegador e de novo no servidor (`nh3`, lista fechada). Imagem no corpo do texto só do próprio portal e com texto alternativo obrigatório. Prévia no bloco de notícias. Versões com cópia do texto, para comparar (diferenças marcadas em texto, não só por cor) e restaurar como rascunho. Vale para conteúdos, comunicados e perfis.
- **6) Login:** moldura comum (órgão e console) com brasão, título configurável, fundo com camada de contraste e etapas "1 · E-mail e senha / 2 · Código". "Esqueci minha senha" orienta a pedir a redefinição; o administrador ganhou "senha provisória" na tela de usuários. O console tem a tela "Aparência do login".
- **Testes:** `tests/teste_fase9.py` (tudo ok). Usa APIs simuladas (PNCP, YouTube/Meta, IBGE), sem rede. Os testes rodam com `nh3` instalado só dentro do contêiner de teste; na imagem ele entra pelo `requirements.txt` no próximo build, que depende de aprovação.
- **Verificação "depois"** (ambiente de teste, `Docs/avaliacao-fase9/depois/` e `comparacao.html`):
  - axe sem violações em todas as telas do painel, do console e de login;
  - sem rolagem horizontal em 390 px (corrigido: grade da consulta, `.grade2` e editor no celular — item 5);
  - foco num bloco destaca o mapa, e "descer" muda o mapa antes de salvar;
  - prévia de cor avisa "2,2:1 abaixo de 4,5:1";
  - editor ativo;
  - "Obrigado" visível na tela depois de avaliar.
- **Corrigido durante a verificação:** seções "Agrupamento" e "Histórico" que tinham sumido da tela de indicadores ao dividir em abas; selo "travado" esticado; fonte da tela de login.
- **Suítes:** as 10 deram ERROS: 0 / tudo ok (fluxos, painel_layout, painel, painel_fontes, diario_seguranca, transparencia, legislativo, fase8, fase9). As suítes antigas foram ajustadas só para abrir a aba nova onde o conteúdo foi parar.

### Onde parou (Fase 9)
Código pronto e testado no branch `fase-9`. **Nada aplicado na VPS.** Aguardando aprovação do deploy: snapshot, backup, build (instala `nh3`), 10 suítes com a imagem nova, `up -d`, `provision atualizar` (migrações 017 e 018, fonte `redes`, layout com "Nas redes"), conferência no domínio, merge e tag `fase-9`.
Depois: credenciais opcionais no console (token "meta" para Instagram/Facebook) e conta de cada rede em Identidade → Redes sociais.

### Implantação da Fase 9 (09/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Snapshot confirmado pelo usuário. Backup com `deploy/backup.sh` (substituiu o backup das 17h18 de hoje; ficam os de 07 e 08/11).
- **Build:** instalou o `nh3` 0.2.18. Como o `requirements.txt` mudou, as dependências indiretas sem versão fixada foram atualizadas (ex.: cryptography 50, pydantic 2.14). As **9 suítes** com a imagem nova deram ERROS: 0 / tudo ok; o traceback do `teste_painel` é a falha simulada de propósito. Correção: antes eu tinha escrito "10 suítes", mas são 9.
- **Subida:** `up -d` de app e worker, app saudável. `provision atualizar` aplicou as migrações 017 e 018; cadastrou a fonte `redes` nos dois órgãos; o layout, que estava no padrão da Fase 8, recebeu o padrão com "Nas redes" (o bloco só aparece com credencial e conta); os números manuais de distância e IDHM foram para "Dados do município".
- **Conferência no domínio** (`Docs/avaliacao-fase9/implantado/`):
  - axe sem violações e sem violação de CSP;
  - sem rolagem horizontal e sem destino repetido;
  - login com etapas e "Esqueci minha senha" (órgão e console);
  - `/fotos` e `/privacidade` (cookie `aval`) respondem;
  - formulário de avaliação novo na página inicial;
  - logs sem erro.
  - Nada foi enviado ao portal real (nenhuma avaliação nem formulário).
- **Bloco do município:** IBGE automático (população 935, estimativa de 2026; PIB per capita; salário médio) + distância e IDHM marcados como informados pela Prefeitura. A área territorial entra na próxima coleta semanal do IBGE (2h–6h).
- `fase-9` mesclada em `main` com a tag `fase-9`.

### Pendências (dependem do usuário)
- Token da Meta (console → Credenciais → "Meta Graph API") e IDs das contas em Identidade → Redes sociais, se quiser as publicações no portal.
- Continuam da Fase 8: módulo de audiências, endereço do acervo de legislação, chave do YouTube e canais, teste com NVDA.

## Fase 10 — Carta de Serviços (branch `fase-10`)
### ETAPA 0 (09/11/2026, só leitura na VPS)
- Capturas "antes" do portal real em `Docs/avaliacao-fase10/antes/`. Diagnóstico: os serviços são conteúdos genéricos sem os campos do art. 7º (2, ambos exemplo; um do tipo "Aviso"); `/servicos` sem "Base legal:"; busca por "iptu" sem resultado; sem secretarias nem fluxo de validação.
- Proposta (modelo de dados, fluxo com publicação impossível sem autorização da versão atual, telas, ficha padronizada, documentos) em `Docs/avaliacao-fase10/PROPOSTA.md`; esboço em `Docs/avaliacao-fase10/esboco/` (6 telas, 1280 e 390 px).
- **Parado aguardando** aprovação e 5 decisões: lista oficial de secretarias e responsáveis; avaliação 1–5 ou sim/não; Carta também na Câmara; destino dos 2 conteúdos-exemplo de Serviços; prazo de revisão.
- **Decisões (09/11/2026):** proposta aprovada.
  - Secretarias e responsáveis cadastrados pelo administrador no painel.
  - Avaliação com nota 1–5 + "conseguiu?".
  - Carta na Prefeitura e na Câmara.
  - Conteúdos-exemplo fora de `/servicos`.
  - Revisão a cada 12 meses.

### Implementação (09/11/2026, branch `fase-10`, nada aplicado na VPS)
- **Migração `019_orgao_carta.sql`:** secretarias; designações (ato tipo/número/data/vigência); fichas; versões; avaliações; acessos; manifestação ↔ serviço (`esic.servico_id`); perfis `redator` e `validador` incluídos na lista fechada de perfis.
- **Regras (`app/carta.py`):**
  - envio para validação só com os campos do art. 7º preenchidos;
  - avisos de linguagem (frase > 30 palavras, sigla sem explicação, termos difíceis) que não bloqueiam;
  - só o responsável ou o designado com ato vigente autoriza; devolver exige comentário;
  - **publicar exige autorização da versão atual** (hash do conteúdo); mudança depois da autorização volta a rascunho;
  - o DTIC só ajusta categoria, sinônimos e ordem;
  - o portal lê uma **cópia congelada** do que foi publicado, então editar a ficha não muda o público até nova validação;
  - ficha vencida ganha o aviso "em revisão" e alerta no painel.
- **Painel:**
  - Fichas em abas: Rascunhos/devolvidas, Em validação, Autorizadas, Publicadas, A revisar, Todas.
  - Ficha em seções, com a situação em etapas.
  - Secretarias e responsáveis: designação por ato, vínculo de redatores.
  - Monitoramento: totais por situação e secretaria, vencidas, notas, manifestações da Ouvidoria por serviço, moderação de comentários, prazo de revisão e categorias.
  - Importação do inventário por planilha: vira rascunho, com simulação; redator só importa para a própria secretaria.
- **Portal:**
  - `/servicos` com busca por sinônimos (sem acento), públicos, filtros por categoria/público/secretaria, mais acessados, A–Z e "Base legal".
  - `/servicos/<slug>` com a ficha em seções, "Solicitar online", data de atualização e próxima revisão, e "Avalie este serviço" (nota 1–5, conseguiu?, comentário; cookie e limite por hash de IP da Fase 9).
  - Exportação da Carta inteira em PDF, CSV e JSON, com data e base legal.
  - Ouvidoria com "Sobre qual serviço?".
  - Bloco "Serviços mais acessados" e busca do cabeçalho usando as fichas; Câmara com "Serviços" na barra institucional.
- **Documentos:** `Docs/modelos/carta-servicos.csv` + instruções; `Docs/MINUTA-DECRETO-CARTA-SERVICOS.md` (minuta para a Procuradoria, com pontos a decidir); manual curto no `README.md`.
- **Testes:** `tests/teste_fase10.py` deu tudo ok. Cobre o fluxo completo (rascunho → validação → devolução → nova validação → autorização → publicação), publicação bloqueada sem autorização, escopo por secretaria, administrador que não é responsável não autoriza, designado com ato, revisão vencida, busca por sinônimo, avaliação, manifestação vinculada, exportações, importação e Câmara.
- **Suítes:** as 10 dão ERROS: 0 / tudo ok. Na `teste_fluxos`, só mudou a expectativa de "Serviços mais acessados", que agora vem das fichas da Carta (os conteúdos-exemplo saíram, por decisão).
- **Verificação "depois"** (ambiente de teste com 2 fichas marcadas "exemplo"; `Docs/avaliacao-fase10/depois/` e `comparacao.html`): axe sem violações em 12 telas (portal, painel e Câmara); sem rolagem horizontal em 390 px. Corrigido durante a verificação: lista de colunas da importação e asterisco de obrigatório no rótulo.

### Onde parou (Fase 10)
Código pronto e testado no branch `fase-10`. **Nada aplicado na VPS.** Aguardando aprovação do deploy: snapshot, backup, build, 10 suítes, `up -d`, `provision atualizar` (migração 019; item "Serviços" na barra da Câmara), conferência, merge e tag `fase-10`.
Depois do deploy: o administrador cadastra as secretarias e os responsáveis; as secretarias fazem o inventário. A minuta do decreto vai para a Procuradoria.

### Implantação da Fase 10 (09/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Snapshot confirmado pelo usuário. Backup com `deploy/backup.sh` às 23h47 (substituiu o das 22h17; ficam os de 07 e 08/11).
- **Build:** as **10 suítes** com a imagem nova deram ERROS: 0 / tudo ok.
- **Subida:** `up -d` de app e worker, app saudável. `provision atualizar` aplicou a migração 019 nos dois órgãos e criou o item "Serviços" na barra institucional da Câmara.
- **Conferência no domínio** (`Docs/avaliacao-fase10/implantado/`):
  - axe sem violações, sem violação de CSP, sem rolagem horizontal e sem destino repetido;
  - `/servicos` (Prefeitura e Câmara) mostra "A Carta de Serviços está sendo organizada pelas secretarias" e a base legal;
  - exportações JSON e PDF respondem;
  - `/admin/carta` exige login;
  - logs sem erro.
  - Nenhum dado foi gravado no portal real.
- `fase-10` mesclada em `main` com a tag `fase-10`.

### Onde parou (fases 8, 9 e 10 concluídas e no ar)
Próximos passos dependem das pessoas:
- **Carta de Serviços:** o administrador de cada órgão cadastra secretarias, responsáveis, designações e redatores; as secretarias fazem o inventário; a minuta do decreto vai para a Procuradoria.
- **Pendências anteriores:** módulo de audiências (Prefeitura), endereço do acervo de legislação, chave do YouTube e canais, token da Meta (opcional) e teste com NVDA.

## Ajustes da Fase 8 — portal × protótipo (branch `fase-8-ajustes`)
### Conferência "antes" (10/11/2026, só leitura)
- `Docs/PEDIDO-FASE8-AJUSTES.md` versionado. O `Main.dc.html` da VPS é de 09/11 às 14h26 (BRT), a versão certa.
- Capturas e medidas do portal real em `Docs/avaliacao-fase8/conferencia/antes/`. Confirmação item a item em `Docs/avaliacao-fase8/CONFERENCIA-ANTES.md`:
  - **Confirmados:** itens 1, 2, 5, 6, 7, 8 e 9.
  - **Item 3:** transmissões ausentes por falta de módulo, canal e chave.
  - **Item 4:** já está OK.
  - **Diferenças com o pedido:** /fale-conosco não tem introdução; /acessibilidade e a página da notícia não têm base legal; não existem páginas de secretaria; o "Voltar" do protótipo é link.
- **Parado aguardando** aprovação e as decisões D1 a D5.

### INCIDENTE — disco cheio e portal fora do ar (10/11/2026)
- **O que aconteceu:**
  - O disco da VPS (48 GB) encheu (0 MB livres). O contêiner do app do portal parou, e o portal respondeu **502** nos três domínios.
  - Dois contêineres do sistema **hotspot** (`hotspot-backend` e `hotspot-backend-casemaster`) também pararam, às 10h11 UTC, com código 127.
- **Causa (minha):** cada execução das suítes de teste e das prévias criava um PostgreSQL descartável, removido com `docker rm -f`, que **não apaga o volume anônimo**. Acumularam **199 volumes de ~74 MB (~14 GB)** entre 07 e 10/11, mais as imagens antigas dos builds e o cache de build.
- **Correção, com aprovação do usuário a cada passo:**
  1. Limpeza segura: `docker builder prune -f`, `docker image prune -f` e remoção dos contêineres de teste que sobraram.
  2. Remoção **só** dos 199 volumes anônimos de teste criados entre 07 e 10/11. Os 9 volumes nomeados de outros sistemas (`pmuinix-central_*`, `wg-config`) foram preservados.
  3. Disco de 99% para 69% (15 GB livres).
  4. O app não voltava com `up -d` ("unable to find user portal": a camada de escrita do contêiner se corrompeu com o disco cheio). Foi recriado com `docker compose up -d --force-recreate app`, a mesma imagem, sem build. Depois disso, os três domínios responderam 200.
  5. Hotspot: os dois serviços foram recriados com `docker compose up -d --no-build --no-deps --force-recreate` e ficaram saudáveis.
  6. Banco e worker do portal não registraram erro de escrita.
- **Prevenção:** os scripts de teste e prévia passaram a usar `docker rm -fv` (apaga o volume junto). Antes de cada rodada de testes, conferir `df -h`.

### Ajustes da Fase 8 — implementação (10/11/2026, branch `fase-8-ajustes`, nada aplicado na VPS)
- **Decisões do usuário:**
  - D1: exemplos para Comunicados.
  - D2/D3: editoria e /governo a partir das secretarias da Carta (com campo "resumo" e ícone); organograma enviado pelo painel.
  - D4: "Voltar" como botão secundário.
  - D5: o usuário contrata o módulo "audiências" no console.
- **Migração `020_orgao_ajustes8.sql`:** editoria da notícia (`conteudos.secretaria_id`), resumo e ícone das secretarias.
- **Dados (D1):** feito pelo `provision atualizar`, uma vez só; mexe só em exemplos.
- **Implementado:**
  - casco único de todas as páginas internas, com a "Base legal" logo abaixo da introdução;
  - início com a fileira Notícias + Paço e o cartão do Conheça com mosaico;
  - /noticias só com notícias, com filtro por secretaria e cartões horizontais;
  - página da notícia em cartão com imagem 21:9;
  - Ouvidoria/e-SIC com pílulas e "Outros canais" (contatos reais);
  - /governo com cartões das secretarias, mais Legislação, Carta e Organograma;
  - imagem neutra por editoria (cor AA + ícone, nunca foto de banco);
  - avisos "Transmissões: o que falta" na Visão geral e em Integrações.
- **Testes:**
  - `tests/teste_ajustes8.py` deu tudo ok.
  - As 10 suítes anteriores passam. Ajustes nos testes antigos: o conteúdo 1 virou comunicado (D1), e a estrutura do bloco de notícias mudou.
- **Conferência:** `Docs/avaliacao-fase8/conferencia/index.html` (portal × reconstrução do protótipo, 10 páginas, 1280/390 px) e `Docs/avaliacao-fase8/CONFERENCIA.md` (tabela item | estava | ficou | ok?). axe sem violações em 12 páginas; sem rolagem horizontal.
- **Onde parou:** aguardando aprovação do deploy: snapshot, backup, build, 11 suítes, `up -d`, `provision atualizar` (migração 020 e D1), conferência no domínio, merge e tag `fase-8-ajustes`.

### Implantação dos ajustes da Fase 8 (10/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Snapshot confirmado pelo usuário. Disco antes: 69%. Backup às 11h02 UTC.
- **Build e testes:** as **11 suítes** com a imagem nova deram ERROS: 0 / tudo ok, sem nenhum volume solto.
- **Subida:** `up -d` de app e worker, app saudável. `provision atualizar` aplicou a migração 020; o D1 transformou 2 conteúdos-exemplo em comunicados-exemplo.
- **Limpeza:** imagem antiga removida (`docker image prune -f`). Disco depois: 70%.
- **Conferência no domínio** (`Docs/avaliacao-fase8/conferencia/implantado/`):
  - axe sem violações; sem violação de CSP; sem rolagem horizontal; sem destino repetido;
  - todas as páginas internas com trilha e com a base legal logo abaixo da introdução;
  - página inicial com o Conheça em cartão e mosaico (fotos reais) e a fileira Notícias + Paço;
  - /noticias só com notícias; comunicados-exemplo em /comunicados e na página inicial;
  - Ouvidoria/e-SIC com pílulas e "Outros canais";
  - /governo mostra "ainda não foi publicada" até as secretarias serem cadastradas;
  - logs sem erro.
- `fase-8-ajustes` mesclada em `main` com a tag `fase-8-ajustes`.

## Largura do portal: 1200 → 1320 px (10/11/2026, branch `largura-portal`, nada aplicado na VPS)
- **Pedido:** largura máxima 1320 px em todo o portal, com variável `--largura`; configurável em Identidade > Tema (1200, 1320 ou 1440 px; padrão 1320); larguras de leitura mantidas; margem lateral de 24 px.
- **Levantamento:**
  - Só dois containers tinham 1200 px: `main` e `.int`. O `.int` é usado no cabeçalho, nas barras, no destaque e no rodapé.
  - A margem lateral real era **20 px** (não 24); passou a 24 px (`--margem`), como no protótipo e no pedido.
- **Feito:**
  - `:root{--largura:1320px;--margem:24px}`; `main` e `.int` com `max-width:var(--largura)`.
  - O valor do órgão vai no estilo inline do `base.html` (`tokens.largura`, validado em 1200/1320/1440).
  - Painel → Identidade → Tema e cores: grupo "Largura máxima do conteúdo"; o salvamento entra no histórico e na auditoria.
  - Mantidos: `.intro` 70ch, base legal 110ch, `.materia` 820 px.
- **Dois defeitos achados nas capturas "antes" (já estavam em produção) e corrigidos:**
  1. Em `/painel`, as barras do cabeçalho apareciam **vazias**: a macro `barras` do painel (gráficos da Fase 7) tinha o mesmo nome da variável do cabeçalho. Renomeada para `grafico_barras`. Teste novo em `teste_painel` e `teste_ajustes8`.
  2. Em `/painel`, a "Base legal" **sobrepunha** a última linha da introdução, porque a introdução tinha margem inline. A base legal passou a ter margem própria (`.intro:has(+ .legal-topo)`).
- **Capturas** antes/depois em 1920, 1366 e 390 px: `Docs/avaliacao-largura/index.html`, com a tabela de medidas.
  - Depois: conteúdo de 1320 px em 1920 e 1366, margem de 24 px e sem rolagem horizontal.
- **Testes:** as 11 suítes deram ERROS: 0 / tudo ok; `teste_fase9` agora testa a largura (padrão, 1440 aplicada, valor inválido volta a 1320).
- **Onde parou:** aguardando aprovação para implantar.

### Implantação da largura do portal (10/11/2026, aprovada: "Aprovo os 6 passos" + "Snapshot ok")
- Snapshot confirmado pelo usuário. Backup às 11h28 UTC.
- **Build e testes:** as **11 suítes** com a imagem nova deram ERROS: 0 / tudo ok, sem volume solto.
- **Subida:** `up -d` de app e worker, app saudável. Imagem antiga removida. Disco em 70%. Sem migração de banco.
- **Conferência no domínio** (`Docs/avaliacao-largura/implantado/`):
  - conteúdo de 1320 px em 1920 e 1366; margem de 24 px; sem rolagem horizontal;
  - axe sem violações; sem violação de CSP; sem destino repetido;
  - `/painel` com as barras do cabeçalho preenchidas (9 itens na institucional);
  - Câmara e console respondem 200; logs sem erro.
- `largura-portal` mesclado em `main` com a tag `largura-portal`.

## Largura fluida: até 1760 px (10/11/2026, branch `largura-fluida`, nada aplicado na VPS)
- **Pedido (chat):** largura fluida em todo o portal; `--largura-max: 1760px` e `--margem: clamp(16px, 3.5vw, 64px)` no `:root`; larguras de leitura mantidas; grades da página inicial aproveitando a largura, com no máximo 4 a 5 colunas; Identidade > Tema com 1320, 1600, 1760 ou "tela toda" (padrão 1760). Substitui o pedido de 1320 px.
- **Feito:**
  - `main` e `.int` (cabeçalho, barras, destaque e rodapé): `width:100%; max-width:var(--largura-max); margin:0 auto; box-sizing:border-box`, com padding lateral `var(--margem)`.
  - O valor do órgão vai no estilo inline do `base.html` (`tokens.largura_css`; "tela toda" vira `none`). Valor inválido volta a 1760.
  - Painel → Identidade → Tema: grupo "Largura máxima do conteúdo" com 4 opções; o salvamento entra na auditoria.
  - Corpo de texto limitado a 70ch (`.texto`, `.texto-rico`, ficha de serviço, matéria, páginas de texto); `.intro` 70ch, base legal 110ch e `.materia` 820 px mantidos.
  - Limite de colunas na página inicial, com `auto-fill` e `minmax(max(mín., (100% − espaços)/N), 1fr)`:
    - atalhos 4, indicadores 5, serviços 4, publicações 4, atos 4;
    - gravações e redes 3, trilho 4;
    - vereadores 6 trilhas (o cartão da presidência ocupa 2, então são 5 cartões por fileira).
  - As páginas internas crescem livremente (ex.: indicadores do /painel chegam a 6 colunas em 1920).
  - Defeito que já existia: a caixa "Mesa Diretora" da Câmara usava só uma faixa no meio do cartão. Agora usa a largura toda, com os biênios lado a lado.
- **Capturas** antes/depois em 1920, 1366 e 390 px: `Docs/avaliacao-largura-fluida/index.html`.
  - Fonte: prévia com cópia dos bancos, removida com `rm -fv`.
  - Depois: conteúdo de 1760 px em 1920 (margem 64), 1366 em 1366 (margem ≈ 48) e 390 em 390 (margem 16); sem rolagem horizontal.
- **Observação:** no celular a margem passa de 24 para 16 px (mínimo do clamp pedido).
- **Testes:** as 11 suítes (código montado, banco de TESTE) deram ERROS: 0 / tudo ok; nenhum volume solto criado pelos testes. `teste_fase9` testa a largura: padrão 1760, "tela toda" → none, 1600 aplicada, inválida → 1760.
- **Onde parou:** aguardando aprovação para implantar (sem migração de banco).
- **Encontrado depois:** `Docs/PEDIDO-LARGURA-E-CARDS.md` (11h44). O usuário confirmou que esse é o pedido (ver a seção seguinte).

## Fileiras de cartões (10/11/2026, `Docs/PEDIDO-LARGURA-E-CARDS.md`, mesma branch `largura-fluida`, nada aplicado na VPS)
- **Parte 1, largura fluida:** já feita (seção anterior).
- **Parte 2, componente único `fileira_cartoes`** (`app/templates/partials/fileira.html` + CSS + `portal.js`):
  - 1 a 5 cartões: N colunas iguais em 100% (`grid-auto-columns`), sem sobra e com a mesma altura.
  - 6 ou mais: carrossel de 5 por vez, com scroll-snap e setas (`aria-label` + `aria-controls`). As setas só aparecem quando o trilho transborda.
  - Contagem "1–5 de 8" (aria-live). Setas do teclado só com o foco num cartão (não em campos). Sem rolagem automática; com "reduzir movimento", sem animação.
  - Sem JavaScript: o trilho continua rolável e as setas ficam ocultas.
  - Responsivo: mínimo de 220 px por cartão, por container query (1920 e 1366 → 5; 768 → 3; abaixo de 454 px → 1 e meio, com o próximo aparecendo pela metade).
- **Inventário — onde o componente passou a ser usado:**
  - **Início:** atalhos, publicações, indicadores, números, atos/edições do Diário, transmissões, serviços, redes e vereadores (Câmara).
  - **Páginas internas:** hub da Transparência (dois órgãos), cada grupo do Painel e secretarias em Governo.
- **Ficaram fora:**
  - mosaico do Conheça (aprovado nos ajustes 8);
  - listas completas com filtro (/conheca, /fotos, /vereadores, /noticias);
  - números dentro de cartões (Quanto custa a Câmara, Emendas);
  - listas de Comunicados e Serviços.
- **Mudanças de layout que vieram junto:**
  - **Vereadores:** carrossel de 5 por vez; o cartão da presidência ocupa uma posição. A Mesa Diretora virou caixa própria abaixo da fileira.
  - **Hub da Transparência:** 13 cartões, então mostra 5 por vez em carrossel.
  - **Balão ⓘ:** dentro do trilho fica fixo na tela (senão seria cortado) e fecha ao rolar.
- **Acessibilidade:**
  - Os limites de colunas da etapa anterior foram removidos; o componente os substitui.
  - Corrigido no /painel: o gráfico rolável (`.prola`) não era focável. A falha já existia em 390 px na produção e, com a largura nova, aparecia também em 1920. Agora tem `tabindex`, `role=region` e rótulo.
  - axe sem violações nas 8 combinações (início, transparência e painel da Prefeitura, mais o início da Câmara, em 1920 e 390).
- **Testes:**
  - `tests/teste_fileira.py`: HTML do componente com 1, 2, 3, 5 e 8 cartões; uso nos templates.
  - `tests/fileira_navegador.js`: larguras e alturas iguais, sem sobra, setas só quando transborda, "4–8 de 8" depois de "Próximos" e seta do teclado em 1920, 1366, 768 e 390. Ambos deram tudo ok.
- **Capturas** antes (produção) e depois (prévia com cópia dos bancos, removida com `rm -fv`) em 1920, 1366, 768 e 390 px: `Docs/avaliacao-largura-cards/index.html`, com a tabela de medidas e o inventário.

### Implantação da largura fluida e das fileiras de cartões (10/11/2026, aprovada: "Aprovo os 6 passos" + "sim existe e pode prosseguir")
- Snapshot confirmado pelo usuário. Backup às 12h21 UTC.
- **Build e testes:** as **12 suítes** com a imagem nova deram ERROS: 0 / tudo ok (11 de antes + `teste_fileira`). Nenhum volume solto.
- **Subida:** `up -d` de app e worker; app saudável. Sem migração de banco. Disco em 71%.
- **Conferência no domínio** (`Docs/avaliacao-largura-cards/implantado/`, 1920, 1366, 768 e 390 px):
  - conteúdo de 1760 px em 1920; sem rolagem horizontal da página;
  - fileiras de até 5 sem sobra; carrosséis com "1–5 de 13" (Transparência), "1–5 de 6" (Painel) e "1–5 de 9" (vereadores);
  - axe sem violações em 8 combinações;
  - CSS v=20 e JS v=6 servidos; Câmara 200, console 303 (login); logs sem erro.
- `largura-fluida` mesclada em `main` com a tag `largura-fluida`.

## Atalhos do topo e escala tipográfica (10/11/2026, `Docs/PEDIDO-ATALHOS-E-FONTES.md`, branch `atalhos-fontes`, nada aplicado na VPS)
- **1) Atalhos do topo (feito, exceção à fileira):**
  - Saíram do componente de fileira.
  - Grupo centralizado até 1200 px; cada cartão entre 230 e 280 px (`repeat(auto-fit, minmax(230px, 280px))`, `justify-content: center`, espaço de 14 px).
  - Cerca de 55% do cartão fica sobre a foto: `margin-top` −72 px no computador e −48 px no celular; padding inferior do hero de 96 px.
  - No celular, empilhados na largura do conteúdo.
  - Câmara: mesmo grupo centralizado, abaixo da foto, como antes, porque o hero dela tem o cartão da próxima sessão.
  - Medido na prévia: 4 × 280 px em 1920 e 1366 (grupo de 1162 px centralizado); 55% sobre a foto em 1920, 1366 e 390; sem rolagem horizontal.
- **2) Fontes:** a tabela foi aprovada ("Aprovo a escala"); ver a seção seguinte.
- **Fontes (histórico): PARADO para aprovação.**
  - Tabela "elemento | atual | protótipo" do painel e do console (e do portal, para referência) em `Docs/avaliacao-atalhos-fontes/TABELA-FONTES.md`.
  - Medição em ambiente de TESTE (removido com `rm -fv`). Capturas "antes" em `Docs/avaliacao-atalhos-fontes/antes/`.

### Escala tipográfica aplicada (10/11/2026, aprovada: "Aprovo a escala"; mesma branch, nada aplicado na VPS)
- **Portal (`portal.css`):**
  - escala em variáveis no `:root` (`--fs-base` 17/1,55, `--fs-h2` 26, `--fs-h2-gestao` 28, `--fs-h2-destaque` 30, `--fs-h2-cartao` 22, `--fs-desc` 15, `--fs-meta` 13, `--fs-etq` 12, `--fs-exemplo` 11, `--fs-btn` 17, `--fs-num` 28 …);
  - os 191 `font-size` da folha e os 31 inline dos templates passaram a usar as variáveis.
- **Correções do pedido no portal:**
  - títulos de seção da página inicial: 22 → 26 px (Acompanhe a gestão 28; Conheça 30; Notícias e Paço continuam 22, como no protótipo);
  - descrições e subtítulos: 13–14 → 15 px;
  - menu da barra do brasão: 17 → 16 px;
  - etiquetas: no mínimo 12 px;
  - botões com peso 600; `.btn.mini` com 16 px e 44 px de altura;
  - cargo da Mesa Diretora: 11,7 → 12 px.
- **Painel e console (`admin.css`):**
  - escala no `:root` (título da tela 23, seção 18, rótulo 14, campo 15, tabela 14 com cabeçalho 13, nota 12, botão 15/600, altura 40);
  - os campos deixaram de herdar os 13 px do rótulo;
  - os `<small>` não ficam mais abaixo de 12 px;
  - os 5 `font-size` inline viraram classes.
- **Conferência:**
  - menor texto visível de 12 px em todas as telas medidas (portal 1920/1366/390, painel e console 1366); sem rolagem horizontal;
  - atalhos com 55% sobre a foto nas três larguras;
  - axe sem violações em 8 combinações;
  - a tela de Indicadores do painel deu 404 no banco de teste (módulo de BI não contratado lá) e usa a mesma folha.
- **Teste novo:** `tests/teste_escala.py` acusa `font-size` em px nos templates e nas folhas, e variáveis abaixo de 12 px (exceto "exemplo").
- **Capturas** antes/depois: `Docs/avaliacao-atalhos-fontes/index.html`.
- **Testes:** as 13 suítes (11 de antes + `teste_fileira` + `teste_escala`) deram ERROS: 0 / tudo ok no banco de TESTE; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar (sem migração de banco).

### Implantação dos atalhos do topo e da escala tipográfica (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 15h15 UTC.
- **Build e testes:** as **13 suítes** com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida:** `up -d` de app e worker; app saudável. Sem migração de banco. Disco em 72%.
- **Conferência no domínio** (`Docs/avaliacao-atalhos-fontes/implantado/`, 1920, 1366 e 390 px):
  - menor texto visível de 12 px; sem rolagem horizontal;
  - atalhos de 280 px com 55% sobre a foto (no celular, 358 px empilhados);
  - títulos de seção com 26 px, descrições com 15, menu com 16;
  - axe sem violações em 8 combinações;
  - portal.css v=22, portal.js v=6 e admin.css v=8 servidos; Câmara 200, console 303 (login); logs sem erro.
- `atalhos-fontes` mesclado em `main` com a tag `atalhos-fontes`.

## Painel administrativo reorganizado (10/11/2026, branch `painel-admin`, nada aplicado na VPS)
- **Pedido:** painel limpo, padronizado e fácil de achar, sem quebrar nada, incluindo o login.
  - Queixas: lista ora acima, ora abaixo do formulário; fontes pequenas; "Conheça" espalhado.
- **Diagnóstico e decisões:** `Docs/avaliacao-painel-admin/DIAGNOSTICO-E-PROPOSTA.md`. Decisões do usuário:
  - padrão "lista → tela de edição";
  - menu por tarefa aprovado;
  - **manter a escala de fontes** aprovada hoje;
  - entrega única.
- **Feito:**
  - **Menu por tarefa**, mesmo código para os dois órgãos, conforme o tipo de órgão e os módulos contratados:
    - grupos: Publicar, Legislativo, Cidade, Atendimento, Transparência, Aparência do portal e Administração;
    - nome dos grupos em 13 px, sem caixa alta; o menu lembra quais grupos estavam abertos;
    - no celular, botão "Menu" com o menu por cima da tela (foco preso, Esc fecha);
    - topo de cada tela com título e "Ver portal"; domínio e banco foram para a Visão geral.
  - **Padrão lista → tela de edição** (só nos templates; as rotas e os envios POST não mudaram). Lista primeiro com "+ Novo …"; criar e editar por `?novo=1` / `?id=` com "← Voltar", rótulo em cima e barra de ações no rodapé:
    - Comunicados, com os tipos numa aba;
    - Conheça, Usuários ("Gerenciar") e Secretarias da Carta, com o organograma numa aba;
    - Diário (Enviar ato) e Fotos e álbuns, com as categorias numa aba;
    - Câmara: Sessões, Remessas, Diárias, Contas, Transmissões (canal numa aba) e Legislaturas.
  - **Abas:**
    - Menus e atalhos: 6 abas, no lugar de uma tela de 3.760 px;
    - Diário: edições | signatários e calendário;
    - Carta: fichas | secretarias | monitoramento;
    - Vereadores e Mesas: perfis | legislaturas.
  - **Identidade dividida** (o POST só grava os campos enviados, então nada é apagado):
    - Identidade visual: tema, imagens e favicon; as imagens viraram grade de miniaturas, e cada imagem abre a própria edição;
    - Dados do órgão: campos em grupos (órgão, atendimento, LGPD, textos do portal) e redes sociais;
    - Fotos e álbuns: item próprio no menu.
  - **Conheça reunido:** perfis, bloco da página inicial (texto e as fotos que estavam em "Brasão, mascote e fundos") e números do município.
  - **Retorno seguro:** campo `volta` só aceito se for uma tela `/admin/…` (`volta_segura`). Os redirecionamentos de Menus e do organograma levam à aba certa.
  - **Login:** brasão centralizado, nome do órgão uma vez só, "Área restrita" como rótulo, título "Entrar no painel", ajuda em 14 px e "← Voltar ao portal". Sem foto cadastrada, o fundo usa a cor do tema. Segurança sem mudança.
  - **Defeitos encontrados e corrigidos:**
    - **Formulário dentro de formulário no editor de texto (desde a Fase 9):** no navegador, datas, "Publicado/Destaque" e o botão Salvar de Comunicados, Conheça e Conteúdos ficavam fora do formulário. Agora a caixa de imagem é um `<div>`. Teste ponta a ponta no navegador: salvar comunicado e perfil funciona.
    - O quadro do Organograma estava dentro do título (`h1`) da tela de Secretarias.
    - Os ícones `cor` e `estrutura` não existiam (Comissões mostrava o ícone genérico).
- **Conferência** (ambiente de TESTE, removido com `rm -fv`):
  - 74 telas e modos sem erro;
  - telas com formulário de cadastro acima da lista: de 13 para 4 (tabelas editáveis e a edição em andamento do Diário);
  - axe sem violações em 24 combinações;
  - capturas em `Docs/avaliacao-painel-admin/index.html`.
- **Testes:** novo `tests/teste_painel_admin.py`. Ajustadas 2 verificações que dependiam do HTML antigo (`teste_fluxos`: grade de imagens; `teste_fase10`: designação na tela da secretaria).
- **Onde parou:** aguardando aprovação para implantar (sem migração de banco).

### Implantação do painel reorganizado (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 16h16 UTC.
- **Build e testes:** as **14 suítes** com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida:** `up -d` de app e worker; app saudável. Sem migração de banco. Disco em 72%.
- **Conferência no domínio**, só leitura, sem entrar no painel (`Docs/avaliacao-painel-admin/implantado/`):
  - login novo da Prefeitura, da Câmara e do console ("Entrar no painel", "Área restrita", "Voltar ao portal");
  - admin.css v=9 e admin.js v=4 servidos, com o menu do celular e a correção do editor;
  - axe sem violações nos 3 logins em 1366 e 390 px;
  - portais 200, console 303 (login); logs sem erro.
- **Pendente do lado do usuário:** entrar no painel e conferir as telas no uso real, em especial salvar um comunicado e um perfil do Conheça pelo botão Salvar. Essas telas tinham o defeito do formulário aninhado no ar desde 09/11.
- `painel-admin` mesclado em `main` com a tag `painel-admin`.

## Ajuste: formulários do painel na largura toda (10/11/2026, branch `form-largura`, nada aplicado na VPS)
- **Pedido:** o formulário "Dados do órgão" não ocupava a largura toda como os demais quadros.
- **Causa:** a classe `.form-tela` limitava as telas de edição a 860 px, enquanto título, abas e listas usam a largura toda.
- **Feito:** `.form-tela{max-width:none}` (vale para todas as telas de edição); admin.css v=10.
- **Conferência** em ambiente de TESTE: o cartão do formulário tem a mesma largura das abas e das listas (1062 px em 1366, 1616 em 1920, 342 no celular), sem rolagem horizontal. Capturas em `Docs/avaliacao-painel-admin/form-largura/`.
- **Onde parou:** aguardando aprovação para implantar (sem migração de banco).

### Implantação do ajuste de largura dos formulários (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 17h26 UTC.
- **Build e testes:** as 14 suítes com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida:** `up -d` de app e worker; app saudável. Sem migração de banco. Disco em 72%.
- **Conferência no domínio:** admin.css v=10 servido, com `.form-tela{max-width:none}`; portais 200, console 303 (login); logs sem erro.
- `form-largura` mesclado em `main` com a tag `form-largura`.

## Agenda das integrações no painel (10/11/2026, branch `agenda-integracoes`, nada aplicado na VPS)
- **Pedido:** o próprio órgão configura no painel, para cada integração, os dias, o horário e quantas vezes ela roda, sem mexer no código.
- **Antes:** o agendamento era fixo no código (`FREQ` no `worker.py`), igual para todos os órgãos.
- **Feito:**
  - **Migração `021_plataforma_agenda.sql`:** coluna `fontes.agenda` (JSONB). Vazia = padrão do sistema, idêntico ao agendamento de antes (o teste confere fonte por fonte). Nada muda até alguém configurar.
  - **`app/agenda.py`:**
    - dois modos: horários fixos ("06:00, 18:00") ou "repetir a cada N minutos/horas/dias, das X às Y h";
    - em ambos, os dias da semana;
    - mostra as próximas execuções e quantas vezes por dia;
    - horário fixo perdido é recuperado só até 60 min depois.
  - **Proteção das fontes externas:** intervalo mínimo por fonte. Fiorilli 30 min; Painel 15 min; PNCP e redes 1 h; Siconfi, TCESP e série mensal 6 h; IBGE, CNES, MDS, PNI, INEP e IEG-M 1 dia (um horário por dia).
  - **YouTube:** continua com a agenda automática (só dentro da janela de cada transmissão), sem edição.
  - **Worker:** lê a agenda de cada órgão a cada minuto (`pronta()`). As regras do TCESP (dia 20 ou ano faltante) e do módulo de BI continuam valendo.
  - **Painel → Integrações → cada fonte:** quadro "Agenda de execução" com:
    - a agenda em vigor ("padrão do sistema" ou a do órgão), as próximas 5 execuções e as vezes por dia;
    - o formulário e o botão "Voltar ao padrão".
    Só o perfil com permissão de configuração altera; toda mudança vai para a auditoria ("antes → depois").
  - A "Periodicidade" na descrição da consulta passou a mostrar a agenda do órgão.
- **Conferência** (ambiente de TESTE, removido com `rm -fv`):
  - salvar uma agenda pelo navegador funciona; horários a menos do mínimo são recusados com explicação;
  - axe sem violações no quadro; sem rolagem horizontal em 390 px;
  - capturas em `Docs/avaliacao-agenda-integracoes/`.
- **Teste novo:** `tests/teste_agenda.py` (lógica, limites, painel, auditoria, worker obedecendo a agenda, volta ao padrão, acesso sem login).
- **Testes:** as 15 suítes (14 de antes + `teste_agenda`) deram ERROS: 0 / tudo ok no banco de TESTE; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar. **Tem migração** (021): no passo 5 roda também `python -m app.provision atualizar`.

### Implantação da agenda das integrações (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 17h58 UTC.
- **Build e testes:** as 15 suítes com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida:** `up -d` de app e worker, e `provision atualizar` aplicou a `021_plataforma_agenda.sql`. Disco em 72%.
- **Ocorrência:** o worker subiu segundos antes da migração e registrou "column f.agenda does not exist" no laço. O laço é tolerante a falhas, então só tentou de novo no minuto seguinte, sem perda nem efeito no portal. Reiniciado depois da migração: 0 erros desde então, e coletas de 15:05 (horário de Brasília) com sucesso.
  - **Lição:** quando houver migração, aplicar `provision atualizar` ANTES de subir o worker (ou reiniciar o worker logo depois).
- **Conferência:**
  - 18 fontes, nenhuma com agenda própria (todas no padrão, igual a antes);
  - admin.css v=11 servido; portais 200, console 303 (login).
- `agenda-integracoes` mesclada em `main` com a tag `agenda-integracoes`.
- **Para o usuário:** em Painel → Integrações → cada fonte → "Agenda de execução", escolher os dias e os horários de cada integração.

## Visual da Prefeitura igual ao da Câmara (10/11/2026, branch `visual-prefeitura`, nada aplicado na VPS)
- **Pedido:** a letra e o visual do portal da Prefeitura devem ser iguais aos da Câmara, que é o padrão. Esclarecido: "visual geral (letras e cartões)".
- **Medição no ar** (26 elementos, 1920 e 390 px): mesma família (Public Sans), mesmos tamanhos e pesos. Só duas coisas diferiam:
  1. o nome no cabeçalho em tela grande: Prefeitura 25 px, Câmara 22 px (regra do cabeçalho "cheio");
  2. os cartões de atalho: na Câmara, ícone em cima, borda superior na cor do órgão e sem sombra; na Prefeitura, ícone ao lado e sombra.
- **Feito:**
  - nome do cabeçalho com 22 px em tela grande para os dois órgãos (21 px até 1366 e 25 px no celular, como já era);
  - cartões de atalho no padrão da Câmara para os dois;
  - na Prefeitura os cartões continuam sobre a foto: sobreposição ajustada para −94 px no computador e −80 px no celular (55% do cartão sobre a foto, como aprovado antes);
  - portal.css v=23.
- **Conferência** na prévia com cópia dos bancos (removida com `rm -fv`):
  - nome e cartões idênticos nos dois portais em 1920, 1366 e 390;
  - sem rolagem horizontal; axe sem violações em 8 combinações.
  - Capturas em `Docs/avaliacao-visual-prefeitura/`.
- **Testes:** as 15 suítes deram ERROS: 0 / tudo ok no banco de TESTE; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar (sem migração de banco).

### Implantação do visual da Prefeitura no padrão da Câmara (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 19h36 UTC.
- **Build e testes:** as 15 suítes com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida:** `up -d` de app e worker; app saudável. Sem migração. Disco em 72%.
- **Conferência no domínio** (`Docs/avaliacao-visual-prefeitura/implantado/`):
  - Prefeitura e Câmara idênticas no nome do cabeçalho (22 px em 1920, 21 em 1366, 25 no celular) e nos cartões de atalho (280×171 px, ícone em cima, borda superior de 4 px, sem sombra);
  - na Prefeitura, 55% do cartão sobre a foto; sem rolagem horizontal;
  - portal.css v=23 servido; portais 200, console 303 (login); logs sem erro.
- `visual-prefeitura` mesclado em `main` com a tag `visual-prefeitura`.

## Anexos nos comunicados (10/11/2026, branch `anexos-comunicados`, nada aplicado na VPS)
- **Pedido:** poder anexar arquivos (PNG, JPG, PDF etc.) a editais, comunicados, avisos e convites.
- **Feito:**
  - **Migração `022_orgao_anexos.sql`** (banco de cada órgão): tabela `comunicado_anexos`, ligada ao comunicado; se o comunicado for apagado, os anexos vão junto.
  - **`app/anexos.py`:**
    - formatos aceitos: PDF, PNG, JPG, WEBP, DOCX, XLSX, ODT, ODS e CSV;
    - tipo conferido pelo CONTEÚDO (um PDF disfarçado de .png é gravado como PDF; um executável com extensão .pdf é recusado);
    - recusados com explicação: Office com macro, .doc/.xls antigos, ZIP, executável, HTML disfarçado de CSV, arquivo vazio e acima de 20 MB;
    - no máximo 15 anexos por comunicado;
    - arquivos em `DADOS_DIR/<órgão>/anexos/` com nome interno aleatório (o nome original fica guardado);
    - cada anexo exige uma descrição curta ("o que é o arquivo"), usada no link e como texto alternativo da imagem.
  - **Painel → Comunicados → editar:** quadro "Arquivos anexos" com lista (miniatura das imagens, tipo, tamanho, quem enviou, Remover) e formulário "Anexar arquivo".
    - Na tela de novo comunicado, aviso para salvar antes.
    - A lista do painel ganhou a coluna "Anexos".
    - Envio e remoção vão para a auditoria. Aviso de LGPD (não anexar CPF completo nem dados pessoais).
  - **Portal:**
    - página do comunicado com a seção "Arquivos (N)": imagens em miniatura com texto alternativo, e todos os arquivos em lista com tipo e tamanho;
    - PDF e imagem abrem no navegador; documentos e planilhas são baixados com nome legível;
    - a lista de comunicados mostra "N arquivo(s)".
  - **Rota `/anexo/<arquivo>`:**
    - só entrega anexo de comunicado publicado e visível (no período eleitoral segue a mesma regra do comunicado); no painel do próprio órgão, permite a pré-visualização do rascunho;
    - nome validado (sem truques de caminho), cabeçalho `nosniff`.
- **Conferência** (ambiente de TESTE, removido com `rm -fv`):
  - comunicado-exemplo com PDF, imagem e planilha enviados pelo painel e publicados;
  - axe sem violações no painel e no portal; sem rolagem horizontal em 390 px.
  - Capturas em `Docs/avaliacao-anexos-comunicados/`.
- **Teste novo:** `tests/teste_anexos.py` (detecção e recusas, envio, auditoria, rascunho × publicado, tipo e nome do download, caminhos inválidos, remoção do arquivo, remoção só do próprio comunicado, sem login).
- **Testes:** as 16 suítes (15 de antes + `teste_anexos`) deram ERROS: 0 / tudo ok no banco de TESTE; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar. **Tem migração** (022, banco de cada órgão): aplicar `provision atualizar` logo depois de subir o app e antes de reiniciar o worker (lição da implantação da agenda).

### Implantação dos anexos nos comunicados (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 21h13 UTC.
- **Build e testes:** as 16 suítes com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida na ordem certa** (lição da implantação anterior): `up -d app` → `provision atualizar` (aplicou a `022_orgao_anexos.sql` em bd_pm_bora e bd_cm_bora) → `up -d worker`. Worker sem nenhum erro. Disco em 75%.
- **Conferência no domínio:**
  - tabela `comunicado_anexos` criada nos dois órgãos (vazia);
  - /comunicados 200; `/anexo/` inexistente 404; caminho malicioso recusado (400);
  - portal.css v=24 servido; portais 200, console 303 (login); logs sem erro.
- `anexos-comunicados` mesclado em `main` com a tag `anexos-comunicados`.
- **Para o usuário:** em Painel → Comunicados → editar, usar o quadro "Arquivos anexos". Os arquivos aparecem no portal quando o comunicado é publicado.

## Modelo multi-órgão — etapa 1: modelo neutro e cadastro completo (10/11/2026, branch `modelo-neutro`, nada aplicado na VPS)
- **Pedido:** usar o piloto como modelo para outros órgãos. O cadastro no console monta portal e painel a partir dos dados do órgão (IBGE, sistema da transparência), sem nada de órgão fixo no código. Análise e etapas aprovadas: começar pela etapa 1.
- **Feito:**
  - **Dados do piloto fora do código:** `app/seeds/piloto_bora.json` (identidade, imagens, textos do Conheça, integrações, conteúdos-exemplo, lei do Diário), lido só por `provision init/atualizar` para os órgãos do piloto.
    - Removidos do código: `IBGE_BORA`, `DOMINIO_PM/CM`, a URL do Fiorilli, o CNPJ, o "Portais de Borá" e o User-Agent "PortaisBora".
    - Nome da plataforma e User-Agent configuráveis (`NOME_PLATAFORMA`, `USER_AGENT`), com padrão neutro ("Portais Municipais").
    - A descoberta de fontes agora recebe o órgão (`python -m app.coletores.descoberta SLUG`).
    - A lei do Diário (Lei 910/2026) saiu dos textos: vem da configuração do Diário do órgão. O piloto continua com ela pelo arquivo de dados; um órgão novo vê texto genérico até informar a lei.
  - **Cadastro completo no console (`Órgãos → Cadastrar órgão`):**
    - tipo; código IBGE com "Buscar no IBGE", que preenche município e UF e sugere nome, identificador e município no TCESP;
    - CNPJ (com dígitos verificadores); cor; domínio; e-mail do administrador; contatos;
    - sistema da transparência: Fiorilli (endereço da API e código da entidade; recebedora, para a Câmara) ou "ainda sem integração";
    - módulos opcionais.
    - O IBGE confirma município e UF ao cadastrar; sem resposta, valem os digitados.
  - **Montagem automática** (`app/cadastro.py`):
    - identidade (nome, nome curto, "Estado de …", cor, contatos, "Conheça <município>");
    - integrações: Siconfi pelo IBGE (poder E/L); PNCP pelo CNPJ (Prefeitura); TCESP (Prefeitura de SP); Fiorilli conforme o cadastro; painel de indicadores (IBGE, CNES, INEP, IEG-M);
    - menus, página inicial e ligação Câmara ↔ Prefeitura pelo mesmo IBGE.
  - **Senha inicial única por órgão:**
    - aleatória, com 16 caracteres;
    - mostrada UMA vez na tela "Órgão criado" (sem cache), sem ir para o registro do console; só o hash fica guardado;
    - troca obrigatória e segundo fator no primeiro acesso.
  - **Ajustes para órgão recém-criado:** bloco "Conheça" oculto enquanto não tiver conteúdo; contato da sede sem separador sobrando; cabeçalho `Cache-Control` sem duplicar.
- **Conferência:**
  - Ambiente de TESTE: cadastro pelo navegador de uma Prefeitura fictícia, com portal no ar sem "Borá" e sem "910", axe sem violações e sem rolagem em 390 px.
  - Prévia com cópia dos bancos: o piloto ficou igual ao do ar em 12 páginas. A única mudança é a redação da lei do Diário ("Lei Municipal nº 910/2026").
  - Capturas em `Docs/avaliacao-modelo-neutro/`.
- **Teste novo:** `tests/teste_cadastro_orgao.py`:
  - código sem dados do piloto;
  - validações;
  - Prefeitura e Câmara fictícias de SP e Prefeitura fictícia de MG sem sistema;
  - integrações, identidade, senha única, login e troca de senha do administrador;
  - portal sem Borá; piloto intacto.
- **Implantação:** sem migração de banco, mas é preciso rodar `provision atualizar` (grava a lei do Diário do piloto na configuração) logo depois de subir o app, antes do worker.
- **Testes:** as 17 suítes (16 de antes + `teste_cadastro_orgao`) deram ERROS: 0 / tudo ok no banco de TESTE; nenhum volume solto. O `teste_fluxos` cadastrava com o formulário antigo (sem o e-mail do administrador): atualizado para o cadastro completo.
- **Onde parou:** aguardando aprovação para implantar. Na subida: `up -d app` → `provision atualizar` → `up -d worker`.

### Implantação da etapa 1 do modelo multi-órgão (10/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 23h20 UTC.
- **Build e testes:** as 17 suítes com a imagem nova deram ERROS: 0 / tudo ok. Nenhum volume solto.
- **Subida na ordem certa:** `up -d app` → `provision atualizar` (gravou a lei e a base legal do Diário do piloto na configuração do bd_pm_bora) → `up -d worker`. Worker sem erros. Disco em 75%.
- **Conferência no domínio:**
  - /diario de Borá com "Lei Municipal nº 910/2026" e a base legal completa;
  - console com o formulário novo (console.js 200); o login do console mostra "Portais Municipais — plataforma" (antes "Portais de Borá"; ajustável por `NOME_PLATAFORMA` no .env);
  - portais 200, console 303 (login); logs sem erro.
- `modelo-neutro` mesclado em `main` com a tag `modelo-neutro`.
- **Próximas etapas (a combinar):**
  - 2: ativar domínio, certificado e nginx pelo console;
  - 3: Diário configurável por órgão (decreto e horários);
  - 4: adaptadores de outros sistemas da transparência.

## Modelo multi-órgão — etapa 2: publicar domínio pelo console (10/11/2026, branch `ativacao-dominio`, nada aplicado na VPS)
- **Desenho e decisões:** `Docs/ETAPA2-ATIVACAO-DOMINIO.md`. D1–D4 aprovadas:
  - gravar `portal-orgaos.conf` e `portal-comum.inc` na pasta do nginx do hotspot e recarregá-lo;
  - instalar o timer do systemd;
  - corrigir a recarga depois da renovação;
  - teste real com o registro A `teste-ativacao.conectatech.tech`, criado pelo usuário.
- **Achado (já existia):** ninguém recarregava o nginx depois da renovação automática dos certificados. Vale para todos os sites da VPS; os do piloto vencem ~05/02/2027.
- **Feito:**
  - **Migração `023_plataforma_ativacoes.sql`:** fila `ativacoes` e `orgaos.vhost_ativo`.
  - **`app/ativacao.py`:**
    - verificação de DNS (o domínio precisa apontar só para a VPS);
    - fila de pedidos;
    - geração do `portal-orgaos.conf` (um par de blocos 80/443 por órgão publicado);
    - comandos para o ativador: `pendentes`, `validar`, `vhost`, `passo`, `concluir`.
  - **`deploy/ativador.sh`** (root, a cada minuto via `portal-ativador.timer`). Lista fechada de ações, para cada pedido:
    1. revalida o pedido e o DNS;
    2. recusa domínio que já esteja em outro site da VPS;
    3. pede o certificado (certbot webroot, `--keep-until-expiring`);
    4. gera o arquivo de forma atômica;
    5. roda `nginx -t` (se recusar, volta o anterior e não recarrega) e recarrega;
    6. confere o HTTPS; se não responder, retira de novo.
    - "Tirar do ar" retira o domínio e guarda o certificado.
    - Recarrega o nginx quando algum certificado foi renovado.
    - Trava contra execução dupla; registro em `logs/ativador.log`.
    - Modo `--teste DOMINIO` (com `DRY_RUN=1` só ensaia o certificado).
  - **Console → órgão → "Domínio e publicação":**
    - DNS ao vivo e instrução do registro A;
    - botão "Publicar domínio" (só com o DNS certo) e "Tirar do ar";
    - passos do pedido e resultado.
    - Os domínios do piloto ficam fora: continuam no `portal-bora.conf`.
  - A tela "Órgão criado" passou a orientar o uso do botão.
- **Testes novos:**
  - `tests/teste_ativacao.py` (DNS simulado): console, fila, vhost, recusas, piloto fora, sem login;
  - `tests/teste_ativador.sh`: o ativador real com docker, certbot, nginx e curl simulados, em 23 verificações (sucesso, domínio de outro sistema, nginx -t recusado com volta do anterior, sem certificado, HTTPS mudo, DNS revalidado, retirada, renovação, modo de teste, ensaio e trava).
- **DNS de teste:** em 10/11 à noite, `teste-ativacao.conectatech.tech` ainda não resolvia; o usuário vai criar o registro.
- **Testes:** as 18 suítes (17 de antes + `teste_ativacao`) deram ERROS: 0 / tudo ok no banco de TESTE, e `teste_ativador.sh` deu tudo ok; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar. **Tem migração** (023) e **instalação no sistema** (timer do systemd). Ordem:
  1. `up -d app` → `provision atualizar` → `up -d worker`;
  2. copiar as unidades para `/etc/systemd/system`, `daemon-reload`, `enable --now portal-ativador.timer`;
  3. com o DNS de teste no ar: `DRY_RUN=1 ativador.sh --teste teste-ativacao.conectatech.tech` e depois o teste real.

### Implantação da etapa 2 (10/11/2026, aprovada: "Aprovo a implantação" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 23h45 UTC.
- **Build e testes:** as 18 suítes com a imagem nova deram ERROS: 0 / tudo ok; `teste_ativador.sh` tudo ok; nenhum volume solto.
- **Subida:** `up -d app` → `provision atualizar` (aplicou a `023_plataforma_ativacoes.sql`) → `up -d worker`. Worker sem erros.
- **Instalação no sistema** (comandos mostrados antes):
  - `install` das unidades em `/etc/systemd/system`;
  - `systemctl daemon-reload`;
  - `systemctl enable --now portal-ativador.timer`.
- **Conferência:**
  - timer ativo, a cada minuto;
  - primeira execução com sucesso: só criou a marca de renovação em `/var/lib/portal-ativador`; **nenhum arquivo do nginx criado nem recarga** (fila vazia);
  - portais do piloto e sites do hotspot respondendo normalmente; logs sem erro.
- **Pendente:** teste real de certificado com `teste-ativacao.conectatech.tech`. Em 10/11 às 23h55 UTC o DNS ainda não resolvia. Quando resolver:
  1. `DRY_RUN=1 deploy/ativador.sh --teste teste-ativacao.conectatech.tech` (ensaio);
  2. o teste real (publica, confere o HTTPS e retira).
- `ativacao-dominio` mesclado em `main` com a tag `ativacao-dominio`.

### Teste real da etapa 2 e ajuste do ativador (10–11/11/2026)
- DNS de teste criado pelo usuário: `teste-ativacao.conectatech.tech` → 76.13.167.181 (confirmado no 8.8.8.8 e no 1.1.1.1).
- **Ensaio** (`DRY_RUN=1 ativador.sh --teste …`): Let's Encrypt validou o domínio; nada publicado.
- **1º teste real:**
  - certificado emitido (válido até 08/02/2027);
  - domínio publicado com `nginx -t` aceito;
  - **conferência do HTTPS falhou**: o curl recebeu o certificado de outro site. O ativador retirou o domínio, como previsto. Os outros sites não foram afetados.
  - **Causa:** a recarga do nginx é gradual; a conferência foi feita no mesmo instante e caiu num processo antigo.
- **Ajuste (aprovado: "Sim, ajustar e repetir"):** a conferência do HTTPS tenta até 5 vezes, a cada 2 segundos (`TENTATIVAS`/`ESPERA`). Ensaio simulado com dois casos novos: HTTPS lento (publica na 3ª tentativa) e HTTPS que nunca responde (retira).
- **2º teste real:** 1ª tentativa sem sucesso, 2ª com certificado válido. Domínio de teste retirado no fim (`portal-orgaos.conf` só com o cabeçalho). Portais e sites do hotspot normais.
- O certificado de teste ficou guardado; o registro DNS de teste pode ser apagado quando quiser.
- `ajuste-ativador` mesclado em `main` com a tag `ativacao-dominio-ok`.

## Modelo multi-órgão — etapa 3: Diário Oficial configurável por órgão (11/11/2026, branch `diario-configuravel`, nada aplicado na VPS)
- **Antes:** os horários do Diário (corte 16h, alerta 16h30, publicação automática 17h) eram globais (.env) e os textos repetiam "16h" fixo. O decreto de Borá só aparecia na base legal.
- **Feito:**
  - **Regras por órgão** (`diario.regras`), na configuração `diario` do órgão:
    - lei, decreto, base legal (vazia = montada com a lei e o decreto) e os três horários;
    - sem horários próprios, valem os do .env (16h, 16h30 e 17h), os mesmos de antes.
  - **Usam as regras do órgão:**
    - a rotina do worker (edição "sem atos" no corte, alerta, publicação automática);
    - a data prevista do ato (`data_alvo`);
    - a tela do Diário e a mensagem de envio;
    - a base legal;
    - o portal (/diario);
    - a tela de remessas da Câmara, que usa o corte da Prefeitura de destino.
  - **Painel → Diário → "Signatários, calendário e lei" → "Lei, decreto e horários":**
    - campos de lei, decreto, base legal e horários (corte, alerta, publicação), com validação: ordem corte → alerta → publicação, entre 6h e 23h;
    - opção "usar os horários padrão";
    - mudança registrada na auditoria (antes → depois).
  - **Piloto:** o decreto ("Decreto de 25/03/2026") entrou no arquivo de dados e é gravado pelo `provision atualizar`, sem mudar os horários.
- **Conferência:**
  - ambiente de TESTE: horários 14h/14h30/15h salvos pelo navegador; ordem errada recusada; portal com "a partir das 14h"; axe sem violações;
  - prévia com cópia dos bancos: as 12 páginas do piloto **idênticas** ao ar; Borá segue com 16h, 16h30 e 17h, a lei e o decreto.
  - Capturas em `Docs/avaliacao-diario-regras/`.
- **Teste novo:** `tests/teste_diario_regras.py`:
  - padrão e piloto; recusas; horários próprios; auditoria; data da edição antes e depois do corte;
  - base legal montada; textos do painel, do portal e da Câmara;
  - rotina do worker gerando a edição "sem atos" às 14h01 e publicando às 15h01;
  - volta ao padrão; sem login.
- **Testes:** as 19 suítes (18 de antes + `teste_diario_regras`) deram ERROS: 0 / tudo ok no banco de TESTE, e `teste_ativador.sh` deu tudo ok; nenhum volume solto.
- **Onde parou:** aguardando aprovação para implantar. Sem migração de banco; precisa de `provision atualizar` (grava o decreto do piloto). Ordem: `up -d app` → `provision atualizar` → `up -d worker`.

### Implantação da etapa 3 (11/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 00h34 UTC.
- **Build e testes:** as 19 suítes com a imagem nova deram ERROS: 0 / tudo ok; nenhum volume solto.
- **Subida:** `up -d app` → `provision atualizar` (gravou o decreto do piloto) → `up -d worker`. Worker sem erros.
- **Conferência:**
  - Borá com 16h, 16h30 e 17h (sem horários próprios), "Lei Municipal nº 910/2026" e "Decreto de 25/03/2026";
  - /diario com "a partir das 16h" e a base legal de sempre;
  - portais 200, console 303 (login); timer do ativador ativo; logs sem erro.
- `diario-configuravel` mesclado em `main` com a tag `diario-configuravel`.
- **Próxima etapa do modelo:** 4, adaptadores de outros sistemas da transparência. Depende de saber quais sistemas os próximos órgãos usam.

### Etapa 4 do modelo multi-órgão: coletor GOVBR (11/11/2026, ramo `govbr-coletor`)
- **Pedido:** coletor para a GOVBR, tendo a Prefeitura de Regente Feijó (TransparênciaBR / Pronim TB) como exemplo. No painel, mostrar os parâmetros da consulta, a periodicidade e como cada tela é montada. Lutécia usa Fiorilli, que já é atendida.
- **Análise (só leitura, sem login, sem captcha):**
  - a GOVBR não tem API JSON pública (`/pronimtb/api/` responde 404; a API citada no JS é um servidor interno);
  - a saída em formato de máquina é "Exportar Dados": `geraxml.asp?item=N&banco=…&exercicio=…&dataInicial=AAAAMMDD&dataFinal=AAAAMMDD&unidadeGestora=-1` devolve o link de um ZIP com XML (ISO-8859-1);
  - o código do banco muda a cada ano e é lido na própria tela;
  - Prefeitura, Câmara e fundo vêm no mesmo arquivo; cada órgão filtra pela unidade gestora;
  - "Salários por colaborador" tem reCAPTCHA e fica de fora; ordem cronológica não tem exportação; o lançamento das receitas não tem dados.
- **Feito:**
  - `app/coletores/govbr.py`: cada base é descrita uma vez (item, arquivo, filtro, período e coluna ← campo do XML); o coletor executa essa descrição e a tela mostra a mesma.
    - Bases: receitas, despesas por unidade, empenhos, diárias, restos a pagar, licitações, contratos, pessoal e transferências.
  - Execução completa (ano inteiro) uma vez a cada 24 h; nas demais, só os últimos meses (parâmetro de 1 a 3). Empenhos/diárias e licitações/contratos baixam o arquivo uma vez só.
  - Regras confirmadas no ensaio real:
    - dotação inicial vem em janeiro e "DotacaoAtualizada" é a variação do mês;
    - restos a pagar vêm em movimentos e são somados por empenho;
    - a folha vale para a competência mais recente que todas as entidades já publicaram;
    - concessão e recebimento do mesmo repasse contam uma vez.
  - LGPD:
    - CPF nunca é gravado;
    - na folha, descontos e líquido não são lidos;
    - pessoa física fica fora dos restos a pagar;
    - a amostra da tela não traz descontos, líquido nem documentos.
  - Segurança: limite de tamanho do ZIP e do XML; XML com DOCTYPE/ENTITY recusado; arquivo de outro exercício recusado.
  - Painel → Integrações → "Portal da transparência (GOVBR)":
    - agenda (padrão a cada 3 h, entre 6h e 22h; mínimo de 1 h);
    - "Como a consulta é montada", com endereço, parâmetros e arquivo;
    - parâmetros editáveis: endereço, unidade gestora, bases, meses relidos, entidades de pessoal e recebedora;
    - novo bloco **"Como cada tela do portal é montada"**: rota, tabela, arquivo, período, filtro, regra e a tabela coluna no portal ← campo do XML ← regra;
    - lista do que fica de fora e por quê.
  - Console: opção GOVBR no cadastro de órgão. Prefeitura: todas as bases, unidade "PREFEITURA". Câmara: transferências, recebedora "PODER LEGISLATIVO".
  - Transparência: "Fonte:" mostra só o sistema que o órgão usa. O piloto continua com "Fiorilli".
  - "Em números" da página inicial aceita receita da GOVBR.
  - Migração `024_plataforma_fontes_govbr.sql` (fonte `govbr` na lista permitida).
- **Ensaio real (modo de teste, nada gravado) no portal de Regente Feijó:**
  - todos os pedidos com HTTP 200;
  - dotação atualizada R$ 277,4 mi ≥ empenhado R$ 216,0 mi;
  - folha de 09/2026 com as 3 entidades;
  - transferências do duodécimo lidas.
- **Testes:**
  - `tests/teste_govbr.py` usa um portal simulado com dados fictícios marcados como exemplo;
  - as 20 suítes e `teste_ativador.sh` passaram com o código montado;
  - capturas em `Docs/avaliacao-govbr/` (1366 e 390 px, axe sem violações, sem rolagem lateral).
- **Onde parou:** aguardando aprovação para implantar. Tem migração; ordem: `up -d app` → `provision atualizar` → `up -d worker`.

### Implantação da etapa 4 (11/11/2026, aprovada: "Aprovo os 6 passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 10h43 UTC.
- **Build e testes:** as 20 suítes e `teste_ativador.sh` passaram com a imagem nova. Os volumes soltos são de outros projetos da VPS, de junho/2026; não foram tocados.
- **Subida:** `up -d app` → `provision atualizar` (migração `024_plataforma_fontes_govbr.sql` aplicada; `govbr` na lista de fontes) → `up -d worker` (sem reinícios nem erros) → `image prune`.
- **Conferência:**
  - portais 200; console 303 (login); timer do ativador ativo;
  - o piloto continua com "Fonte: Sistema contábil da Prefeitura (Fiorilli)", sem GOVBR.
- `govbr-coletor` mesclado em `main` com a tag `govbr-coletor`.
- **Para usar:** cadastrar o órgão no console com o sistema "GOVBR" e o endereço do portal (…/pronimtb/). Depois, em Integrações → GOVBR, conferir a unidade gestora e as entidades de pessoal, e "Testar consulta".

### GOVBR: API de dados abertos ou XML, escolhido por base (11/11/2026, ramo `govbr-api`)
- **Pedido:** Pato Branco/PR usa GOVBR e tem API registrada. Manter os dois procedimentos: sem API, XML; com API, API. A escolha fica no gestor/admin.
- **Análise (só leitura):**
  - a API de dados abertos fica em `https://<municipio>.cidade360.cloud/dadosabertos/`, com Swagger em `/dadosabertos/swagger`, pública, sem chave;
  - cobre só **receitas**, **despesas**, **folha** e **servidores**;
  - Regente Feijó não tem a API (404).
- **Situação da API de Pato Branco hoje:**
  - receitas funcionam e trazem a previsão (o XML não traz), mas em algumas descrições a letra “o” some (“Imp st s”) — defeito do lado da GOVBR;
  - despesas respondem HTTP 200 com erro do banco deles (“Invalid column name 'nr_CGCCPF'”);
  - folha funciona (traz CPF, que é descartado);
  - o XML de Pato Branco também funciona.
- **Feito:**
  - Integrações → GOVBR ganhou:
    - “Endereço da API de dados abertos (opcional)”, “Entidade na API” e “Entidades de pessoal na API”;
    - **“Como buscar cada base”** para receitas, empenhos, diárias e pessoal, com as opções **Automático** (API; se falhar, XML), **Só API** e **Só XML**;
    - as demais bases vêm sempre do XML, e a tela explica por quê.
  - No automático, se a API falhar (inclusive com erro disfarçado de HTTP 200 ou formato desconhecido), a base vem do XML nessa execução, relendo o ano inteiro para não misturar os dois caminhos. A “Última execução” diz o caminho: “via API”, “via XML” ou “API falhou (…); usado o XML”.
  - “Só API” sem resposta registra a falha e mantém os dados anteriores.
  - Unidade gestora que não existe na API: o erro lista as que a API oferece.
  - “Como cada tela do portal é montada” mostra, por base:
    - o caminho escolhido;
    - a rota da API;
    - a coluna “Campo da API” ao lado do “Campo do XML”.
  - LGPD: CPF, descontos e líquido da API de pessoal são descartados antes de qualquer gravação e não aparecem nas amostras; a matrícula passa a ser guardada.
  - Console: campo opcional “GOVBR: API de dados abertos” no cadastro de órgão.
  - **Correção encontrada no ensaio:** em Pato Branco, todos os empenhos vêm com `QuantidadeDiasDiarias = 0.0000`, e todos viravam diárias. Agora só contam empenhos com dias > 0, objetivo de viagem ou natureza de diária (3.3.90.14/15). Em 11/2026 ficaram 15 diárias de 345 empenhos.
- **Ensaio real em Pato Branco (modo de teste, nada gravado):**
  - receitas pela API (previsão R$ 656,9 mi);
  - despesas: a API falhou e o automático usou o XML;
  - folha de 10/2026 pela API, com 200 servidores, matrícula e sem CPF;
  - licitações pelo XML;
  - todas as requisições com HTTP 200.
- **Testes:**
  - `tests/teste_govbr.py` ganhou a parte da API simulada: JSON dentro de string, erro com HTTP 200, paginação, só API, só XML, unidade inexistente, LGPD da folha e tela;
  - as 20 suítes e `teste_ativador.sh` passaram com o código montado.
- **Capturas** em `Docs/avaliacao-govbr-api/` (1366 e 390 px, axe sem violações).
- **Onde parou:** aguardando aprovação para implantar. Sem migração; não precisa de `provision atualizar`.

### Implantação da escolha API/XML da GOVBR (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 12h01 UTC.
- **Build e testes:** as 20 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `up -d worker` → `image prune`. Sem migração. App e worker sem reinícios nem erros no log.
- **Conferência:** portais 200; console 303 (login); timer do ativador ativo; o piloto continua com "Fonte: Sistema contábil da Prefeitura (Fiorilli)".
- `govbr-api` mesclado em `main` com a tag `govbr-api`.
- **Para usar em Pato Branco:**
  - cadastrar o órgão no console com sistema "GOVBR", portal `…/pronimtb/` e API `…/dadosabertos/`;
  - em Integrações → GOVBR, usar a unidade gestora "MUNICIPIO DE PATO BRANCO" (é o nome que a API e o XML usam);
  - deixar no automático ou escolher por base, e clicar em "Testar consulta".
- **Avisar a GOVBR:**
  - a rota de despesas da API de Pato Branco devolve erro do banco deles;
  - as descrições das receitas perdem a letra "o".

### Separação gestão × portais — análise e etapa A1: licença assinada (11/11/2026, ramo `separacao-a1-licenca`)
- **Análise** em `Docs/ANALISE-SEPARACAO-VPS.md`. A gestão fica na VPS atual; portais e painéis vão para uma VPS nova (o "nó"). O nó busca licenças assinadas na gestão; a gestão nunca acessa o nó.
  - O plano muda três decisões do `Docs/CLAUDE.md` (dois PostgreSQL, nginx próprio no nó, uma VPS a mais) e depende da confirmação do usuário antes das etapas B a E.
- **Usuário:** "inicie, é somente piloto pode reiniciar a qualquer momento" (etapa A aceita).
- **A1 feito:**
  - `PAPEL` no .env: `tudo` (padrão, igual a antes), `gestao` ou `no`.
  - `app/licenca.py`:
    - par Ed25519 da gestão, com a privada cifrada no banco de controle (chave derivada da SECRET_KEY);
    - documento por órgão: domínio, banco, tipo, módulos contratados, contrato e "válida até" (15 dias, `LICENCA_VALIDADE_DIAS`).
  - **Papel `tudo`:** o documento é montado na hora, sem cache, e o resultado é idêntico ao de antes.
  - **Papel `no`:** vale só a licença do cache com assinatura conferida.
    - licença vencida → carência (só o obrigatório; portal e transparência seguem no ar);
    - licença adulterada → recusada.
  - `modulos_do_orgao` e Funcionalidades leem a licença.
  - O roteamento por domínio no nó usa as licenças.
  - O nó não serve o console, e a gestão sozinha não serve portais.
  - Worker do nó: busca as licenças a cada 5 min, e a falha fica registrada.
  - Console:
    - "Nós e licenças": chave pública e impressão digital; cadastro de nó com o token mostrado uma vez (a gestão guarda o hash); troca de token com confirmação;
    - página do órgão: "Hospedagem e licença" (onde está hospedado, quando o nó buscou, o que está contratado).
  - API `GET /api/no/licencas` (gestão; só com o token do nó).
  - Migração `025_plataforma_licencas.sql` (`licenca_chaves`, `nos`, `orgaos.no_id`, `licencas_emitidas`, `licencas_cache`). O `provision atualizar` cria o par de chaves e mostra só a impressão digital.
- **Testes:**
  - `tests/teste_licenca.py`: papel "tudo" igual ao código antigo (inclusive mudança direta no banco); assinatura e adulteração; token uma vez; API 401; nó simulado (busca, gestão fora do ar, vencida → carência, adulterada, licença antiga não sobrescreve); papel "gestao";
  - as 21 suítes e `teste_ativador.sh` passaram com o código montado;
  - prévia com cópia dos bancos: as 12 páginas do piloto **idênticas** ao ar.
- **Onde parou:** aguardando aprovação para implantar A1. Tem migração. Ordem: `up -d app` → `provision atualizar` → `up -d worker`.

### Implantação da etapa A1 — licença assinada (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 14h47 UTC.
- **Build e testes:** as 21 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `provision atualizar` (migração 025 aplicada; par de chaves da gestão criado, impressão `fd7846e9e9f4a934`) → `up -d worker` → `image prune`. Sem reinícios nem erros no log.
- **Conferência:**
  - portais, transparência, Diário e login do painel 200; console 303 (login);
  - `/api/no/licencas` sem token: 401;
  - módulos do piloto iguais (Prefeitura com Diário e Painel; Câmara com integração e emendas);
  - nenhum nó cadastrado; timer do ativador ativo.
- `separacao-a1-licenca` mesclado em `main` com a tag `separacao-a1`.
- **Próximo:** A2 — banco local do nó (tabelas operacionais saem do banco de controle).

### Separação gestão × portais — etapa A2: banco local do nó (11/11/2026, ramo `separacao-a2-local`)
- **Usuário:** "Sim, etapa A2".
- **Feito:**
  - `db.LOCAL`: banco das tabelas operacionais. No papel `tudo`/`gestao` é o próprio banco de controle (como sempre); no papel `no` é o banco local do nó (`NO_BANCO`, padrão `no_local`).
    - Tabelas: fontes, coletas, consultas (amostras, testes, histórico), credenciais, dados públicos, indicadores públicos, pares e registro de remessas, tentativas de login, cache de licenças e aparência do login.
    - 58 consultas passaram a usar `db.LOCAL`; as que tocam o cadastro de órgãos, contratos e módulos continuam no controle.
  - `app/orgaos.py`: o portal, o painel e o worker leem os órgãos por ele — no controle (papel `tudo`) ou nas licenças assinadas (papel `no`). Foram trocadas as 11 leituras diretas da tabela `orgaos` fora do console (worker, remessas, painel, Diário, importação, legislação da Câmara).
  - A licença leva também o plano e a cor do órgão.
  - `app/migrations_local/001_local.sql`: esquema do banco local, igual ao do controle e sem chave estrangeira para `orgaos`. O teste confere coluna por coluna.
  - `provision atualizar` no papel `no`: cria e atualiza o banco local e os bancos dos órgãos das licenças, sem tocar no controle.
  - Tentativas de login: as do painel dos órgãos vão para o banco local; as do console, para o controle.
  - `app/no_local.py`, ferramenta da virada:
    - `exportar NOME_DO_NO arquivo.zip` (gestão), só com as linhas dos órgãos do nó e permissão 600;
    - `importar arquivo.zip` (nó), numa transação só, conferindo SHA-256 de cada tabela, colunas e contagem — qualquer diferença desfaz tudo;
    - `conferir arquivo.zip`.
- **Testes:**
  - `tests/teste_no_local.py`:
    - esquema igual nas 13 tabelas;
    - exportação só do nó;
    - arquivo alterado e contagem errada recusados, com nada gravado;
    - nó simulado com banco local real: portal, transparência, Diário, dados abertos, Câmara, painel com login 2FA e integrações, worker com as mesmas fontes, coleta e tentativa de login gravadas no banco local, remessa Câmara → Prefeitura e provision do nó;
  - as 22 suítes e `teste_ativador.sh` passaram com o código montado;
  - prévia com cópia dos bancos: as 12 páginas do piloto **idênticas** ao ar, e o worker vê as mesmas 16 fontes ativas.
- **Implantação:** sem migração no banco de controle e sem `provision atualizar` (o banco local só nasce no nó). Ordem: `up -d app` → `up -d worker`.
- **Onde parou:** aguardando aprovação para implantar A2.

### Implantação da etapa A2 — banco local do nó (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 15h36 UTC.
- **Build e testes:** as 22 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `up -d worker` → `image prune` (sem migração no controle). Sem reinícios nem erros no log.
- **Conferência:**
  - portais, transparência, Diário e login dos dois painéis 200; console 303 (login); API de licenças sem token 401;
  - worker com as mesmas 16 fontes ativas; banco local = `plataforma` (papel "tudo"), órgãos pm-bora e cm-bora;
  - timer do ativador ativo.
- `separacao-a2-local` mesclado em `main` com a tag `separacao-a2`.
- **Próximo:** A3 — fila de ordens (o console deixa de escrever direto nos bancos dos órgãos).

### Separação gestão × portais — etapa A3: fila de ordens (11/11/2026, ramo `separacao-a3-ordens`)
- **Usuário:** "Sim, etapa A3".
- **Feito:**
  - `app/ordens.py`: o console não escreve mais direto nos bancos dos órgãos; registra uma **ordem** de uma lista fechada:
    - `criar_orgao`: banco do órgão, esquema, identidade, integrações, menus, layout e administrador. Leva só o **hash** da senha inicial; a senha em claro aparece uma vez no console;
    - `credencial`: gravar ou apagar credencial de fonte, sempre **cifrada** (mesma `CHAVE_CREDENCIAIS` na gestão e no nó).
  - **Órgão nesta VPS (papel "tudo"):** a ordem é executada na hora, no mesmo pedido, como antes.
  - **Órgão num nó:** a ordem fica na fila.
    - o nó busca em `GET /api/no/ordens` (token), confere a **assinatura** da gestão (cobre id, nó, tipo e conteúdo) e executa **uma vez só** (`ordens_feitas` no banco local);
    - o nó devolve o resultado em `POST /api/no/ordens/{id}`; se a gestão estiver fora do ar, informa depois sem executar de novo;
    - ordem adulterada e tipo fora da lista são recusados.
  - `provision.registrar_orgao` foi separado em `registrar_controle` (gestão: órgão, contrato, módulos) e `preparar_orgao` (quem hospeda). O piloto continua pelo caminho de sempre.
  - **Console:**
    - cadastro de órgão com "Hospedagem" (esta VPS ou um nó), mostrada só quando há nós cadastrados;
    - página do órgão com as últimas ordens;
    - "Nós e licenças" com as ordens na fila e com erro;
    - credencial gravada ou apagada vai, cifrada, para cada nó;
    - o editor de layout do console recusa órgão hospedado em nó (o ajuste é no painel do órgão).
  - Worker do nó: busca as ordens a cada minuto, depois das licenças.
  - Migrações: `026_plataforma_ordens.sql` (controle) e `migrations_local/002_local_ordens.sql` (nó).
- **Ficou para a A4, com o relatório do nó:** publicar o domínio de órgão hospedado em nó, porque precisa que os passos do ativador voltem para o console.
- **Testes:**
  - `tests/teste_ordens.py`:
    - cadastro igual ao de antes nesta VPS, com o login do administrador;
    - órgão no nó: ordem na fila, banco não criado na gestão, API 401 e isolamento entre nós;
    - nó simulado: executa, devolve, não repete, informa depois de queda da gestão, recusa ordem adulterada e tipo fora da lista, serve o portal e aceita o login com a senha mostrada no console;
    - credencial cifrada gravada, decifrada e apagada no nó;
  - as 23 suítes e `teste_ativador.sh` passaram com o código montado;
  - prévia com cópia dos bancos: as 12 páginas do piloto **idênticas** ao ar; 16 fontes ativas; migração 026 aplicada sem erro.
- **Implantação:** tem migração (026). Ordem: `up -d app` → `provision atualizar` → `up -d worker`.
- **Onde parou:** aguardando aprovação para implantar A3.

### Implantação da etapa A3 — fila de ordens (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 16h13 UTC.
- **Build e testes:** as 23 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `provision atualizar` (migração 026 aplicada) → `up -d worker` → `image prune`. O `provision atualizar` rodou uma segunda vez só para conferir a migração na saída; é idempotente e não mudou nada. Sem reinícios nem erros no log.
- **Conferência:**
  - portais, transparência, Diário e login dos dois painéis 200; console 303 (login); API de ordens sem token 401;
  - 16 fontes ativas; tabela de ordens vazia; nenhum nó; timer do ativador ativo.
- `separacao-a3-ordens` mesclado em `main` com a tag `separacao-a3`.
- **Próximo:** A4 — relatório do nó (saúde, coletas e espaço) e publicação de domínio de órgão hospedado em nó, com os passos voltando para o console.

### Separação gestão × portais — etapa A4: relatório do nó e domínio em nó (11/11/2026, ramo `separacao-a4-relatorio`)
- **Usuário:** "Sim, etapa A4".
- **Feito:**
  - `app/relatorio.py`: o nó envia à gestão (`POST /api/no/relatorio`, token), a cada 5 min ou a cada minuto com publicação de domínio em andamento:
    - versão, IP público (`VPS_IP` do .env do nó) e espaço em disco;
    - licença por órgão (válida/até quando), última execução de cada coleta e falhas em 24 h;
    - ordens com erro, domínios publicados e passos das ativações.

    **Sem dados pessoais**; limite de 256 KB.
  - **Domínio de órgão hospedado em nó:**
    - o console confere o DNS contra o **IP do nó** (do relatório), registra o pedido e manda a ordem `dominio`;
    - o nó põe o pedido na fila local, e o mesmo `deploy/ativador.sh` do nó publica: certificado, vhost a partir de `dominios_publicados`, `nginx -t`, recarga e conferência do HTTPS;
    - os passos voltam pelo relatório e atualizam o pedido no console ("no ar", `vhost_ativo`, registro "ativador do nó …");
    - relatório de outro nó não mexe no pedido.
  - **Ativador desta VPS (papel "tudo"):** o vhost e a lista de pendentes só levam órgãos hospedados aqui. Nada muda para o piloto (o vhost gerado é igual ao do ar).
  - **Console:**
    - "Nós e licenças": último relatório, IP, GB livres, versão, falhas de coleta e licença vencida;
    - página do órgão do nó: licença no nó e a tabela das coletas no nó.
  - Migrações: `027_plataforma_relatorio.sql` (controle) e `migrations_local/003_local_ativacoes.sql` (nó).
- **Testes:**
  - `tests/teste_relatorio.py`:
    - sem relatório não há IP do nó (pedido recusado);
    - relatório sem dados pessoais;
    - console mostra relatório e coletas;
    - DNS na gestão recusado e no IP do nó aceito;
    - ativador desta VPS ignora o pedido;
    - nó valida, publica e retira, com os passos no console;
    - relatório de outro nó ignorado; API 401, 413 e 400;
  - as 24 suítes e `teste_ativador.sh` passaram com o código montado;
  - prévia com cópia dos bancos: as 12 páginas **idênticas**; 16 fontes; vhost igual ao do ar.
- **Com a A4, a etapa A (código) fica completa.** As etapas B a E (VPS nova, ensaio, virada) dependem das decisões listadas em `Docs/ANALISE-SEPARACAO-VPS.md` (plano da VPS, validade da licença, nome do nó, janela) e da confirmação das três mudanças de decisão do `Docs/CLAUDE.md`.
- **Implantação:** tem migração (027). Ordem: `up -d app` → `provision atualizar` → `up -d worker`.
- **Onde parou:** aguardando aprovação para implantar A4.

### Implantação da etapa A4 — relatório do nó e domínio em nó (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 17h19 UTC.
- **Build e testes:** as 24 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `provision atualizar` (migração 027 aplicada) → `up -d worker` → `image prune`. Sem reinícios nem erros no log.
- **Conferência:**
  - portais, transparência, Diário e login dos dois painéis 200; console 303 (login);
  - APIs de licenças e de relatório sem token: 401;
  - 16 fontes ativas; vhost gerado pelo ativador sem blocos, igual ao do ar;
  - o timer do ativador rodou com o código novo às 17h30 UTC e saiu com sucesso.
- `separacao-a4-relatorio` mesclado em `main` com a tag `separacao-a4`.
- **Etapa A (código) completa:** licença assinada (A1), banco local do nó (A2), fila de ordens (A3), relatório e domínio em nó (A4). Tudo no papel "tudo", sem mudança para o piloto.
- **Próximo (B a E):** depende do usuário:
  - confirmar as três mudanças de decisão do `Docs/CLAUDE.md`;
  - plano e região da VPS nova;
  - validade da licença sem contato (sugestão: 15 dias);
  - nome do nó;
  - janela da virada;
  - cópia dos segredos (`.env`, chave do nó, certificado do Diário) feita por ele.

### Separação gestão × portais — fase 1: preparo desta VPS antes da VPS nova (11/11/2026, ramo `separacao-f1-preparo`)
- **Usuário:** "finalize o que necessita nessa vps sem derrubar os pilotos instalados, em outro momento vou iniciar a nova vps e informo aki".
- **Feito:**
  - **Domínios do piloto:** nesta VPS, pmbora e cmbora continuam no `portal-bora.conf` (fora do ativador), como antes. Quando estiverem hospedados num nó, o console libera a publicação pelo ativador do nó, como qualquer órgão (necessário na virada).
  - **Backup** (`deploy/backup.sh`): a lista de bancos passa a ser a do próprio servidor PostgreSQL, sem depender do banco de controle, que o nó não tem. Nesta VPS a lista é a mesma de hoje (plataforma, bd_pm_bora, bd_cm_bora); no nó, banco local e bancos dos órgãos. Sem nenhum banco: erro e saída.
- **Testes:** `tests/teste_relatorio.py` ganhou o caso do piloto (bloqueado aqui; liberado e enviado ao nó quando hospedado lá). As 24 suítes e `teste_ativador.sh` passaram com o código montado. Prévia com cópia dos bancos: as 12 páginas **idênticas**.
- **Implantação:** sem migração. O backup do primeiro passo já usa o script novo e serve de conferência. Ordem: `up -d app` → `up -d worker`.
- **Onde parou:** aguardando aprovação para implantar a fase 1. Depois disso, **nada mais falta nesta VPS antes da VPS nova**. O resto (cadastrar o nó, exportar, virada) acontece junto com as fases 2 a 4.

### Implantação da fase 1 — preparo desta VPS (11/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 18h36 UTC, já com o `backup.sh` novo: plataforma, bd_pm_bora, bd_cm_bora, dados e .env, como antes.
- **Build e testes:** as 24 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** às 15h47 (Brasília, antes do horário do Diário) `up -d app` → `up -d worker` → `image prune`. Sem migração, sem reinícios nem erros no log.
- **Conferência:** portais, transparência, Diário e login dos dois painéis 200; console 303 (login); 16 fontes ativas; timer do ativador ativo.
- `separacao-f1-preparo` mesclado em `main` com a tag `separacao-f1`.
- **Nesta VPS não falta mais nada antes da VPS nova.**
- **Próximo:** o usuário vai contratar a VPS nova e avisar. Então seguem as decisões pendentes e as fases 2 (montar o nó), 3 (ensaio), 4 (virada) e 5 (depois). Ver `Docs/ANALISE-SEPARACAO-VPS.md`.

### Instalador do nó de portais (12/11/2026, ramo `separacao-instalador-no`)
- **Usuário:** "ao invés de você fazer, tem como montar um script para rodar e já ir solicitando as informações faltantes, lembrando que uma VPS pode ter mais de um portal rodando nele".
- **Feito (`deploy/no/`):**
  - `instalar.sh` (roda na VPS nova, como root): guiado, idempotente, confirma cada etapa que altera o servidor e nunca mostra segredos (leitura sem eco; `.env` com permissão 600; registro em `logs/instalar-no.log` sem segredos).
    - Etapas: conferência, atualizações/fuso/NTP, Docker oficial, firewall, segredos da gestão, configuração do nó, nginx/certbot, portal, ativador/backup, conferência com a gestão.
    - `--verificar` só confere.
    - **Vários órgãos por nó:** nada por órgão no instalador; cada órgão chega pela licença, ordem e ativador.
    - **VPS compartilhada:** com 80/443 ocupadas por outro sistema, usa o nginx existente (pergunta container, pastas e rede).
  - `exportar_segredos.sh` (VPS da gestão): pacote 600 com o `.env` e `segredos/`, sem exibir nada.
    - **Descoberta:** `SECRET_KEY`, `TOTP_CHAVE`, `CPF_HMAC_CHAVE` e `CHAVE_CREDENCIAIS` precisam ser **iguais** no nó; a `SECRET_KEY` também valida os códigos de recuperação do 2FA e os códigos das edições do Diário. Isso corrige a sugestão anterior de trocar a `SECRET_KEY` no nó.
  - `empacotar.sh` (VPS da gestão): pacote de código de uma tag do git (sem `.env`, segredos, backups nem dados). **Não há repositório remoto**, por isso o pacote.
  - `docker-compose.no.yml`: sobreposição usada pelo nó via `COMPOSE_FILE` no `.env` (rede do nginx do nó; banco inicial `no_local`).
  - `proxy/docker-compose.yml` e `proxy/00-acme.conf`: nginx 1.26 e certbot próprios do nó; porta 80 padrão responde ao desafio do Let's Encrypt de qualquer domínio; renovação a cada 12 h.
  - `LEIA-ME.md`: o passo a passo.
  - `python -m app.relatorio enviar|ver` (usado na conferência do instalador).
  - `.gitignore`: pacotes, `.env.origem`, `.env.anterior-*` e o `conf.d` local do nginx do nó.
- **Testes:**
  - `tests/teste_instalador_no.sh`: instalador num contêiner descartável e sem rede, com docker/apt/systemd simulados e respostas automáticas. Confere:
    - o `.env` (31 itens);
    - segredos fora da tela e do log;
    - a pasta `segredos/` só para root;
    - conf.d, ativador, backup, firewall;
    - segunda rodada mantendo senha do banco e token;
    - VPS compartilhada;
    - recusas de token e chave inválidos.

    A cópia do teste exclui `.env`, segredos e backups da VPS.
  - `docker compose config` do nó (em pasta temporária, `.env` fictício): banco `no_local`, rede `portal-proxy`, alias `portal-web-app`.
  - `nginx -t` com `00-acme.conf`, o trecho comum e um domínio no formato do ativador (certificado de teste): ok.
  - `teste_relatorio` ok.
- **Sem mudança no que está no ar:** os scripts só rodam na VPS nova ou quando chamados; o app não precisa ser reimplantado.

### Console: formulários na largura toda (12/11/2026, ramo `console-largura`)
- **Usuário:** "dentro do gestao os formularios nao estao ocupando 100% do espaco".
- **Causa:** todo formulário `.campos` tem largura máxima de 760 px; no painel dos órgãos isso foi resolvido com `.form-tela`, mas no console não. O cadastro de órgão até tinha `.cadastro-orgao{max-width:none}`, mas a regra `form.campos` vencia; a troca de senha tinha 420 px fixos.
- **Feito:**
  - `main.console` na moldura do console e `.console form.campos{max-width:none}`: os formulários ocupam a caixa toda (1366 px: de 760 para 1028–1062 px).
  - Senha sem os 420 px fixos.
  - "Hospedagem e licença" e "Cadastrar nó": botões em linha comum (`.acoes`), porque a barra fixa cobria a escolha do nó.
  - Chave pública e códigos longos quebram a linha. A lista `dados-senha` vira uma coluna em telas de até 640 px: "Nós e licenças" no celular não rola mais para o lado.
  - CSS `v=15`.
- **Conferência:** medição no ambiente de teste em 1366 e 390 px das telas do órgão, cadastro, nós, credenciais, aparência e senha — nenhuma rolagem lateral. Capturas antes/depois em `Docs/avaliacao-console-largura/`. Testes do console (licença, cadastro, painel admin, ativação) ok.
- **Implantação:** só templates e CSS; sem migração. `up -d app` (o worker não muda).

### Implantação: console com formulários na largura toda (12/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 11h41 UTC.
- **Build e testes:** as 24 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** só o app (`up -d --no-deps app`), às 08h50 de Brasília; o worker não mudou e seguiu rodando. Sem reinícios nem erros no log.
- **Conferência:** portais e painéis 200; console 303 (login) e tela de login 200 com `admin.css?v=15`, com a regra nova servida.
- `console-largura` mesclado em `main` com a tag `console-largura`.

### Convite de primeiro acesso por e-mail e e-mail de saída no console (12/11/2026, ramo `convite-email`)
- **Usuário:**
  - "não deve ser gerado em tela e sim enviado via e-mail cadastrado, pois nem sempre o responsável está junto ao gestor na hora do cadastro";
  - "ao invés de inserir a configuração do e-mail direto no .env crie uma sessão dentro do gestor para configurar o e-mail de saída".
- **Feito:**
  - **Console → E-mail de saída** (`app/email_saida.py`):
    - servidor, porta, segurança (SSL, STARTTLS ou nenhuma), usuário, senha, remetente e nome;
    - a senha fica **cifrada** com a `CHAVE_CREDENCIAIS`, nunca volta para a tela nem para o registro, e vazio mantém a atual;
    - botão "Enviar teste", com o resultado sem segredos;
    - só a gestão envia; os nós não precisam de SMTP.
  - **Cadastro de órgão sem senha na tela** (`app/convites.py`):
    - o administrador recebe um **link de primeiro acesso** (uso único, 7 dias) e, ao abrir, cria a própria senha (12+ caracteres, não previsível) e cadastra o segundo fator no fluxo de sempre;
    - o banco do órgão guarda só o **hash** do link (vai nas ordens `criar_orgao`/`convite`);
    - a gestão guarda o link **cifrado** só até o e-mail sair;
    - o e-mail sai quando a ordem foi executada **e** o domínio do órgão responde. Enquanto isso, a página do órgão mostra o motivo: servidor do órgão, domínio fora do ar, e-mail de saída não configurado ou falha do SMTP (com nova tentativa a cada minuto pelo worker).
  - **Página do órgão → Acesso do administrador:**
    - situação do convite (aguardando, enviado, usado, vencido);
    - "Enviar/Reenviar convite" com confirmação: o link e a senha anteriores deixam de valer;
    - "usado" vem do banco do órgão (nesta VPS) ou do relatório do nó, que leva só **códigos** dos e-mails, sem dado pessoal.
  - **Painel do órgão:** `/admin/primeiro-acesso` (sem cache, sem referer; link inválido, usado ou vencido explicado; registro na auditoria).
  - Migrações `028_plataforma_email.sql` (controle) e `029_orgao_convite.sql` (órgãos).
- **Testes:**
  - `tests/teste_convite.py`:
    - e-mail de saída: validação, senha cifrada e nunca exibida, teste e falha de autenticação;
    - convite: espera o domínio, falha do SMTP e nova tentativa, e-mail com link sem senha;
    - primeiro acesso: senha fraca recusada, segundo fator, link usado e vencido recusados;
    - reenviar invalida a senha anterior; sem e-mail de saída fica aguardando; sem login não reenvia.
  - `apoio.py` com e-mail simulado; cadastro, GOVBR e ordens passaram a entrar pelo convite. O relatório continua sem dado pessoal (corrigido para levar só os códigos).
  - As 25 suítes e `teste_ativador.sh` passaram com o código montado.
  - Capturas em `Docs/avaliacao-convite/` (1366 e 390 px; axe sem violações; sem rolagem lateral).
- **Ainda não feito:** os usuários que o administrador do órgão cria dentro do painel continuam com senha provisória mostrada na tela; pode ser o próximo passo.
- **Implantação:** tem migração (028 e 029). Ordem: `up -d app` → `provision atualizar` → `up -d worker`. Depois, o usuário configura o e-mail de saída no console.
- **Ajuste pedido pelo usuário (12/11/2026):** "o email deve ser enviado mesmo com o dominio nao publicado ainda, e ao tentar fazer a senha e o 2fa, fazer somente se o dominio ja estiver publicado e o painel admin do portal no ar".
  - O e-mail sai **na hora** (só depende do e-mail de saída configurado).
  - O link aponta para a **gestão** (`https://<gestão>/convite?t=…`), que está sempre no ar. A gestão confere:
    - link inválido, substituído, usado ou vencido → explica;
    - convite ainda não gravado por quem hospeda → "ainda está sendo preparado", nada feito;
    - painel do órgão não publicado → "ainda não foi publicado", nada feito, volte depois (mostra até quando o convite vale);
    - painel no ar → encaminha para `https://<órgão>/admin/primeiro-acesso`, onde a senha e o 2º fator são criados.
  - A gestão guarda o hash do link para reconhecê-lo (`convites.token_hash`, na mesma migração 028 ainda não implantada).
  - O e-mail avisa que o painel pode ainda não estar publicado.
  - As 25 suítes e `teste_ativador.sh` passaram de novo com o código montado.

### Implantação: convite por e-mail e e-mail de saída (12/11/2026, aprovada: "Aprovo os passos" + snapshot "existe")
- Snapshot confirmado pelo usuário. Backup às 13h03 UTC.
- **Build e testes:** as 25 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** `up -d app` → `provision atualizar` (migrações 028 no controle e 029 nos dois órgãos) → `up -d worker` → `image prune`. Sem reinícios nem erros no log.
- **Conferência:**
  - portais e logins dos dois painéis 200; login do console 200;
  - `/convite` na gestão e `/admin/primeiro-acesso` no pmbora respondem e explicam o link inválido;
  - tabelas `email_saida` e `convites` criadas (nenhum convite ainda);
  - colunas do convite nos dois órgãos.
- `convite-email` mesclado em `main` com a tag `convite-email`.
- **Falta (usuário):** configurar a conta de envio em Console → E-mail de saída e mandar um teste. Até lá, convites de órgãos novos ficam "aguardando" com o motivo na página do órgão.

### Cadastro de órgão: campos da Câmara e de outro sistema aparecendo para Prefeitura (12/11/2026, ramo `cadastro-campos`)
- **Usuário:** "estou cadastrando um órgão prefeitura e aparece uma indagação de campos relacionados à Câmara, o que são e como preencher".
- **Causa:** o `console.js` esconde os campos com o atributo `hidden`, mas o CSS dos rótulos (`display:flex`) e das grades (`display:grid`) vencia o `hidden`. Por isso apareciam sempre: os campos "Câmara: … recebedor nas transferências" e os blocos Fiorilli e GOVBR, independentemente do tipo e do sistema escolhidos.
- **Correção:** `.cadastro-orgao [hidden]{display:none!important}` (só no formulário de cadastro); CSS `v=16`; `console.js?v=3`.
- **Conferência no navegador** (ambiente de teste), campos que aparecem em cada caso:

  | Tipo | Sistema | UF | Aparece |
  |---|---|---|---|
  | Prefeitura | nenhum | SP | só o TCESP |
  | Prefeitura | Fiorilli | SP | bloco Fiorilli, sem o campo da Câmara |
  | Prefeitura | GOVBR | PR | bloco GOVBR, sem o campo da Câmara e sem o TCESP |
  | Câmara | Fiorilli | SP | bloco Fiorilli com "recebedor nas transferências" |
  | Câmara | GOVBR | SP | bloco GOVBR com "recebedor" |

- **Implantação:** só CSS e telas; reiniciar o app.
- **Ajuste pedido pelo usuário:** "deveria ter um seletor solicitando qual a integração usa e mostrar somente os campos daquela integração… se tivéssemos 10 tipos de integração iria ficar muito poluído".
  - Cada sistema da transparência passa a ter **um bloco** marcado com `data-sistema="<valor do seletor>"`, e o script mostra só o bloco escolhido. Campos só de Câmara: `data-so-tipo="legislativo"`.
  - Sistema novo = opção em `cadastro.SISTEMAS` + um bloco com `data-sistema`; o script não muda.
  - `console.js?v=4`.
  - O teste da GOVBR deixou de depender do número da versão do script (foi o que parou a primeira tentativa de implantação).
  - Conferência no navegador: as cinco combinações iguais à tabela acima. `teste_govbr` ok.

### Implantação: cadastro de órgão com um bloco por sistema (12/11/2026, aprovada: "Aprovo os passos" + snapshot "existe"; depois "ajuste e publique")
- Snapshot confirmado pelo usuário. Backup às 13h37 UTC.
- **Primeira tentativa parada antes do reinício:** `teste_govbr` exigia `console.js?v=2`. Explicado ao usuário, que pediu "ajuste e publique" junto com o bloco por sistema.
- **Build e testes:** as 25 suítes e `teste_ativador.sh` passaram com a imagem nova.
- **Subida:** só o app (`up -d --no-deps app`), às 11h03 de Brasília. Sem reinícios nem erros no log.
- **Conferência:** portais e logins 200; o console serve `admin.css?v=16` (regra do `hidden` no cadastro) e `console.js?v=4` (blocos por `data-sistema`).
- `cadastro-campos` mesclado em `main` com a tag `cadastro-campos`.

### Órgão novo hospedado em nó: correção do worker da gestão (12/11/2026, ramo `orgao-no-local`)
- **Usuário:** cadastrou o órgão `prefbora` (domínio `pmbora.prefbora.cloud`, banco `bd_prefbora`) hospedado no nó `726025036.conectatech.tech`; "o e-mail não chegou".
- **Diagnóstico (só leitura):**
  - o nó nunca contatou a gestão (instalador não rodado ou não concluído) → ordem `criar_orgao` na fila; `bd_prefbora` ainda não existe;
  - o DNS do domínio já aponta para 72.60.250.36;
  - o convite saiu às 11h55 pelo SMTP `mail.bora.sp.gov.br` (aceito pelo servidor; a entrega depende dele: spam, quarentena ou fila).
  - Nome com erro de digitação ("Borã").
  - Perguntado se a ideia é um órgão novo (vazio) ou levar o piloto `pm-bora` com os dados (virada).
- **Problema encontrado:** o worker desta VPS tentava a cada minuto abrir `bd_prefbora` (rotina do Diário), com erro no log.
- **Correção:** no papel `tudo`/`gestao`, `orgaos.todos()` e o roteamento por domínio só consideram órgãos sem nó (`no_id IS NULL`). Os órgãos do nó são tratados pelo próprio nó.
- **Testes:**
  - `teste_ordens`: esta VPS não serve nem trata o órgão do nó; a rotina do Diário não tenta abrir o banco dele;
  - `teste_no_local`: as fontes são lidas antes de os órgãos irem para o nó;
  - as 25 suítes e `teste_ativador.sh` passaram com o código montado.
- **Implantação:** sem migração; reiniciar o app e o worker (o worker reiniciado também descarta a conexão presa ao banco inexistente).

### Instalação de nó pelo console, sem terminal na gestão (12/11/2026, ramo `instalacao-console`, sobre `orgao-no-local`)
- **Usuário:** "preciso que pelo gestão consiga gerar e baixar os pacotes e demais arquivos/componentes necessários a subir o novo portal na outra VPS, sem precisar fazer por código" (e "onde pego esses códigos no gestão, tem algum lugar para backup").
- **Feito (`app/instalacao.py`):** Console → Nós e licenças → **Preparar instalação** (por nó).
  - **Pacote de código:** a versão em produção (a imagem passa a levar `Dockerfile`, `docker-compose.yml`, `requirements.txt` e `deploy/` em `/srv/fonte`); sem segredos; versão em `app/VERSAO` (escrita na implantação, fora do git).
  - **Pacote de segredos:**
    - chaves que precisam ser iguais (lidas do ambiente do app, sem a senha do banco nem as senhas iniciais) e `segredos/`;
    - opcionalmente um **token novo** do nó com o endereço da gestão e a chave pública;
    - **cifrado** (AES-256-CBC, PBKDF2 600 mil iterações, formato `openssl enc`) com a **senha do pacote**, que não é guardada.
  - Para gerar: senha do pacote (2×, 12+ caracteres) + **senha e código do 2FA do gestor** (contam como tentativas de login).
  - **Links de uso único** (60 min) em `https://<gestão>/instalar/<token>`: a VPS nova baixa com `curl`. O pacote de segredos fica no disco só cifrado e é apagado no download ou ao vencer (limpeza pelo worker).
  - A tela mostra os 3 comandos para colar na VPS nova. Tudo vai para o registro do console, sem senha, token ou link.
  - **Instalador:** aceita o pacote `.enc` (pede a senha do pacote e decifra com `openssl`) e usa token, nó, gestão e chave que vierem no pacote, sem perguntar.
  - Migração `030_plataforma_instalacao.sql`.
- **Backup (resposta ao usuário):** esta VPS já faz backup diário às 5h em `/opt/portal_web/backups` (14 dias), mas ele fica dentro da própria VPS. Cópia externa sugerida.
- **Testes:**
  - `tests/teste_instalacao.py`: recusas (senha do pacote curta, senha e 2FA do gestor errados); token novo; registro limpo; código sem `.env` nem segredos; uso único; `openssl` abre com a senha certa e não abre com a errada; conteúdo; vencido e limpeza; sem login; sem fontes;
  - `teste_instalador_no.sh`: pacote cifrado com senha errada e certa, instalador preenchido, senha e token fora da tela e do log;
  - as 26 suítes, `teste_ativador.sh` e o ensaio do instalador passaram com o código montado; tela sem violações no axe.
- **Implantação (junto com `orgao-no-local`):** `app/VERSAO` → build → suítes → conferir o pacote de código na imagem nova → `up -d app` → `provision atualizar` (030) → `up -d worker`.
- **Implantado em 12/11/2026, 12:34–12:50 (Brasília), com aprovação do usuário e snapshot confirmado:**
  - backup às 12:34;
  - `app/VERSAO` = `instalacao-console (e7671e0)`;
  - na imagem nova: o pacote de código sai com 268 arquivos (~2,3 MB), com instalador, `Dockerfile` e `docker-compose.yml`, e sem `.env`, segredos nem backups;
  - as 28 linhas de teste com a imagem: tudo ok;
  - migração 030 aplicada;
  - conferências:
    - gestão → login; pm e cm: 200;
    - `/instalar/x`: 404;
    - `/nos/1/instalar` pede login;
    - `instalacao_links` criada (vazia);
    - worker sem erros do `bd_prefbora`;
    - app e worker sem reinícios.
- **Decisão do usuário (12/11/2026):** o órgão `prefbora` (`pmbora.prefbora.cloud`, `bd_prefbora`, nó 72.60.250.36) é um **órgão novo e vazio**. Não é a mudança do piloto: `pm-bora` e `cm-bora` continuam nesta VPS com os dados, e não há virada para agendar por causa dele.

### Correção do cadastro do órgão pelo console (12/11/2026, ramo `orgao-editar`)
- **Usuário:** "não tem opção de edição do cadastro no órgão, nem no contrato" (para corrigir o nome "Borã" do prefbora).
- **Contrato:** a edição já existia no quadro "Licença" da tela do órgão (número, processo, início, fim e carência → "Salvar dados").
- **Feito:** quadro **Dados do cadastro** na tela do órgão (`POST /orgao/{id}/cadastro`).
  - Nome e cor: valem na gestão (console, e-mails do convite, licença).
  - Enquanto a ordem `criar_orgao` estiver **na fila do nó**, também é possível corrigir a identidade inicial (nome, cor, CNPJ, endereço, telefone, e-mail e horário), que vai junto na ordem. A ordem só é assinada na entrega, então não há conflito. O CNPJ corrigido atualiza também a integração com o PNCP.
  - Depois que o órgão é criado, o que aparece no portal fica com o administrador do órgão (painel → Identidade).
  - Identificador, tipo, município, domínio e banco não mudam por aqui.
  - Validações (nome com 3 a 160 caracteres, cor `#RRGGBB`, CNPJ); "Nada mudou"; registro no console.
- **Testes:** `teste_ordens` cobre as recusas, a correção na gestão e na ordem pendente, o nó criando o órgão já com o nome corrigido e o órgão já criado (sem os campos de identidade). As 26 suítes, `teste_ativador.sh` e o ensaio do instalador passaram com o código montado.
- **Implantação:** sem migração; build → suítes → `up -d app` (o worker não muda, mas a imagem é a mesma: `up -d worker`).
- **Implantado em 12/11/2026, 13:04–13:18 (Brasília), com aprovação do usuário e snapshot confirmado:**
  - backup às 13:04;
  - `app/VERSAO` = `orgao-editar (e0cca30)`;
  - 28 linhas de teste com a imagem: tudo ok;
  - `up -d app` e `up -d worker`;
  - conferências:
    - pm e cm: 200;
    - gestão, `/orgao/3` e `POST /orgao/3/cadastro` sem login → login;
    - sem erros no log;
    - sem reinícios.
  - O prefbora segue com a criação na fila do nó (nome ainda "Borã"), à espera da correção pelo usuário na tela.

### Instalação de nó: rever a tela dos comandos e botão (12/11/2026, ramo `instalacao-revisitar`)
- **Usuário:** "depois de preparada a tela para instalação, se você sair dela não tem mais acesso, tem que gerar novamente; deve ter opção para revisitá-la, e a opção Preparar instalação deve ser um botão e não um link".
- **Feito:**
  - Enquanto os links valem (60 min), a tela **Preparar instalação** do nó mostra de novo os **Pacotes preparados**: comandos, situação de cada pacote (aguardando ou baixado, com hora e IP) e validade.
  - O link fica guardado **cifrado** (chave derivada da `SECRET_KEY`, como no convite), só até ser baixado, vencer ou ser cancelado.
  - A senha do pacote continua sem ser guardada.
  - Gerar redireciona para a tela (atualizar a página não gera de novo).
  - Gerar de novo encerra os links anteriores; o botão **Cancelar estes links** faz o mesmo, apaga o pacote do disco e fica no registro.
  - Para gerar de novo com links válidos, o formulário fica em "Gerar novos pacotes".
  - Em Nós e licenças, **Preparar instalação** virou botão.
  - Migração `031_plataforma_instalacao_rever.sql`: colunas `token_cifrado`, `lote`, `token_novo` e `cancelado_em`.
- **Testes (as 26 suítes, `teste_ativador.sh` e o ensaio do instalador passaram com o código montado).** `teste_instalacao` cobre:
  - tela revista com os mesmos links;
  - link guardado só cifrado;
  - sem login não vê;
  - código baixado e segredos ainda disponíveis;
  - os dois baixados: só o passo do instalador;
  - gerar de novo cancela os anteriores;
  - cancelar: links 404, arquivo e link apagados, registro;
  - botão em Nós e licenças.
- **Implantação:** migração 031; build → suítes → `up -d app` → `provision atualizar` → `up -d worker`.
- **Implantado em 12/11/2026, 13:56–14:10 (Brasília), com aprovação do usuário e snapshot confirmado:**
  - backup às 13:56;
  - `app/VERSAO` = `instalacao-revisitar (e7c69f8)`;
  - 28 linhas de teste com a imagem: tudo ok;
  - migração 031 aplicada (4 colunas);
  - conferências:
    - pm e cm: 200;
    - gestão, `/nos`, `/nos/1/instalar` e cancelar sem login → login;
    - `/instalar/x`: 404;
    - sem erros no log;
    - sem reinícios.

### Cabeçalho da Prefeitura no padrão da Câmara (12/11/2026, ramo `cabecalho-padrao-camara`)
- **Usuário:** "as fontes dos portais da Câmara com o da Prefeitura ainda estão diferentes, quero que utilize o mesmo padrão da Câmara no da Prefeitura, já solicitei isso e não foi aplicado" (pedido de 10/11).
- **Medição dos portais no ar (1366 px):** família, tamanhos e pesos já iguais em todos os elementos comuns (Public Sans, 17 px de base, título do destaque 50 px, títulos de seção 26 px etc.); isso foi feito em `visual-prefeitura`. O que continuava diferente era a **composição do nome no cabeçalho**:
  - Prefeitura: "Prefeitura Municipal de" pequeno e só **"Borá"** em destaque;
  - Câmara: "Poder Legislativo" pequeno e o **nome completo** em destaque.
- **Feito (para todos os órgãos, sem código por órgão):**
  - o cabeçalho usa sempre o padrão da Câmara: linha pequena = prefixo, destaque = nome completo;
  - prefixo padrão da Prefeitura passa a ser **"Poder Executivo"**;
  - `provision atualizar` troca o prefixo antigo padrão ("Prefeitura Municipal de") por "Poder Executivo"; prefixo escolhido pelo órgão não muda;
  - o nome curto (município) continua nos menus e títulos ("Conheça Borá", "Borá em números", Diário);
  - textos de ajuda do painel → Identidade atualizados.
- **Conferência na prévia (cópia dos bancos):** nas 3 larguras, Prefeitura e Câmara com o mesmo padrão e tamanhos:
  - 1920 px: 13/22 px;
  - 1366 px: 13/21 px;
  - 390 px: 13/25 px, nome em duas linhas nos dois;
  - sem rolagem horizontal.
  Capturas em `Docs/avaliacao-cabecalho/`.
- **Testes:**
  - `teste_cadastro_orgao`: cabeçalho de órgão novo; troca do prefixo antigo; prefixo escolhido mantido;
  - as 28 linhas passaram com o código montado.
- **Implantação:** sem migração SQL; build → suítes → `up -d app` → `provision atualizar` (troca o prefixo do pm-bora) → `up -d worker`.
## 12/11/2026 20:35 — Instalador do nó mais legível (ramo `instalador-no-legivel`, só código; nada alterado na VPS)
Pedido: o script estava complicado e sem comentários; era preciso parar no meio para descobrir os diretórios do nginx; a tela parecia travada nas atualizações.
- `deploy/no/instalar.sh`:
  - comentários em blocos: o que cada etapa faz e por quê; etapas numeradas "N/10";
  - **descoberta do nginx existente pelo Docker** (`descobrir_nginx`):
    - o container que publica 443/80;
    - as pastas montadas em `/etc/nginx/conf.d` e `/etc/letsencrypt`;
    - a rede;
    - o certbot que monta a mesma pasta de certificados.

    Mostra o que encontrou e pede só Enter. Pergunta apenas o que faltar (ex.: nginx fora do Docker). Confere se nginx e certbot compartilham `/var/www/certbot`;
  - **andamento** (`rodar` / `esperar`): nos passos demorados (apt, Docker, imagem, banco, app, provision, worker, nginx próprio), mostra na mesma linha o indicador girando, o tempo decorrido e a última linha do registro; também indica `tail -f logs/instalar-no.log` e o tempo total no fim;
  - esperas de banco e app agora param com mensagem clara depois de 2 minutos (antes seguiam em silêncio).
- Conferido, só leitura, nesta VPS: a descoberta achou `nginx`, `/opt/hotspot/nginx/conf.d`, o volume `hotspot_nginx-certs`, a rede `hotspot_shared-net` e o certbot `certbot` (os mesmos valores usados pelo ativador daqui).
- `tests/teste_instalador_no.sh`: o caso de VPS compartilhada agora confirma os dados descobertos com Enter; novo caso sem descoberta (pergunta um a um). Ensaio: tudo ok.
- `deploy/no/LEIA-ME.md` atualizado.
- Publicação: o instalador é baixado no pacote de código gerado pelo console a partir da imagem em produção; vale para novos pacotes depois do deploy.

## 12/11/2026 21:03 — Publicados juntos: cabeçalho padrão Câmara + instalador do nó legível (aprovado; snapshot confirmado pelo usuário)
- Backup antes: bd_cm_bora, bd_pm_bora, plataforma ok.
- Imagem `cabecalho-padrao-camara+instalador-no-legivel (e042f9f)`. Suítes contra a imagem: 28 linhas, todas sem erro.
- app → `provision atualizar` (pm-bora: identidade completada, prefixo "Poder Executivo"; cm-bora sem mudança) → worker; prune.
- Conferido, só leitura:
  - pmbora 200 com `Poder Executivo` + **Prefeitura Municipal de Borá**;
  - cmbora 200 com `Poder Legislativo` + **Câmara Municipal de Borá**;
  - gestão 303 (login);
  - versão certa; reinícios 0; sem erros no log;
  - o instalador novo está na imagem (`/srv/fonte`), então os pacotes gerados a partir de agora já saem com ele (links gerados antes deste deploy levam o script antigo: gere de novo).

## 12/11/2026 21:40 — Nó em VPS com Dokploy/Traefik e proteções de VPS compartilhada (ramo `proxy-traefik`, só código; nada alterado na VPS)
Pedido: a VPS nova não tem nginx, só o Traefik do Dokploy, e já tem outros serviços no ar. O usuário aprovou o modo Traefik com as proteções.
- **Ativador** (`deploy/ativador.sh`), com `PROXY_MODO=traefik`:
  - grava só `portal-orgaos.yml` na pasta de rotas dinâmicas do Traefik;
  - não usa certbot nem nginx e não faz reload (o Traefik emite e renova o certificado);
  - recusa domínio que já esteja em outra rota (arquivos da pasta e rótulos de containers e serviços);
  - confere o HTTPS por até ~2 min e retira o domínio se falhar.

  O temporário fica fora da pasta do proxy. O modo nginx não mudou.
- **App** (`app/ativacao.py`): `vhost --formato traefik` gera o arquivo em JSON, que também é YAML válido e por isso nunca sai malformado.
  - Tudo leva o prefixo `portal-orgaos-`.
  - Mesmas proteções do `portal-comum.inc`: nosniff, Referrer-Policy, HSTS, envio até 25 MB, compressão e http → https.
- **Instalador** (`deploy/no/instalar.sh`):
  - detecta VPS compartilhada;
  - etapa 2 desligada por padrão; se pedida, segura os pacotes do Docker (`apt-mark hold`), `NEEDRESTART_MODE=l` e não muda o fuso;
  - etapa 4 não liga o ufw por padrão;
  - etapa 7 descobre o Traefik: container, pasta dinâmica (lida do `traefik.yml` ou dos argumentos), rede (exige overlay attachable), entradas 80/443, resolvedor e `watch`. Mostra tudo e pede Enter;
  - drop-in do ativador com `PROXY_MODO` e `TRAEFIK_*`;
  - backup às 02h00 de Brasília também com o servidor em UTC.
- **IP do visitante**: `config.ip_cliente` usa X-Real-IP (nginx e Traefik), senão o último X-Forwarded-For. Antes era o primeiro, que o visitante podia inventar. Vale para login, avaliação, console e licenças.
- Testes:
  - `teste_ativador.sh`: cenários Traefik;
  - `teste_instalador_no.sh`: VPS com Dokploy simulada (descoberta, nada gravado na pasta do Traefik, nenhum reinício, Docker segurado), também sem PyYAML;
  - `teste_ativacao.py`: rotas Traefik e IP.

  Todas as suítes: 28 linhas ok.
- Falta: confirmar os nomes reais na VPS nova (container, pasta, rede, resolvedor), com as 4 saídas só de leitura pedidas. O instalador mostra o que descobriu antes de usar.

## 12/11/2026 21:45 — Publicado `proxy-traefik` (aprovado; snapshot confirmado pelo usuário)
- Backup antes: bd_cm_bora, bd_pm_bora e plataforma ok.
- Imagem `proxy-traefik (32ce6ee)`. Suítes contra a imagem: 28 linhas, todas sem erro.
- Sequência: app → `provision atualizar` (sem mudanças nos órgãos) → worker → prune.
- Conferido, só leitura:
  - pm e cm respondem 200; a gestão responde 303 (login);
  - versão certa; 0 reinícios; sem erros no log;
  - o ativador desta VPS segue no modo nginx (timer ativo, última execução com status 0);
  - o instalador novo (com Traefik) está no pacote de código (`/srv/fonte`).
- Para a VPS nova com Dokploy: gerar os pacotes de novo no console (os links anteriores levam o instalador antigo) e rodar o instalador. Nas etapas 2 e 4, Enter pula. Na etapa 7, escolher o Traefik e conferir os dados descobertos.

## 14/11/2026 15:41 — Nó: certificados do INEP e credenciais de fontes (ramo `credenciais-e-certs-no`, código)
Problemas vistos no nó do prefbora (VPS com Dokploy):
- **INEP:** todas as consultas falhavam com `CERTIFICATE_VERIFY_FAILED`. O instalador gravava `CERTS_DIR` (pasta de certificados do proxy, vazia no modo Traefik) no `.env` do nó. O app lê o `.env` e usava esse mesmo nome para a pasta dos certificados intermediários do INEP (`deploy/certs`), por isso não os encontrava.
- **IEG-M (TCESP):** o teste falhava porque a credencial foi cadastrada em 07/11, antes de o nó existir. O console só a enviava aos nós no momento da gravação, então o nó nunca a recebeu.

Correções:
- **App:** a pasta dos intermediários passa a se chamar `CERTS_INTERMEDIARIOS`, e valor vazio usa o padrão da imagem. `CERTS_DIR` não afeta mais o app.
- **Instalador:** grava `PROXY_CERTS_DIR` no `.env`, lê o nome antigo como reserva e remove `CERTS_DIR` do `.env`. O drop-in do ativador não muda.
- **Console, envio de credenciais:**
  - na consulta de ordens, o nó recebe sozinho, cifradas, as credenciais que ainda não tinha (uma vez por gravação, sem repetir);
  - "Preparar instalação" com token novo põe todas na fila;
  - novo botão "Reenviar aos nós" em Credenciais de fontes.
- **Testes:**
  - `teste_ordens`: nó tardio recebe, não repete, reenvio cifrado;
  - `teste_painel_fontes`: `CERTS_DIR` vazio não esconde os intermediários;
  - `teste_instalador_no`: `.env` sem `CERTS_DIR`;
  - 28 suítes, ativador e instalador ok.
- **Ainda não implantado** (aguarda aprovação). O nó do prefbora só recebe as correções com pacote novo. Até lá, os contornos:
  - no nó: `sed -i '/^CERTS_DIR=/d' .env && docker compose up -d app worker`;
  - na gestão: gravar de novo a credencial do IEG-M.

## 14/11/2026 17:01 — Implantação: credenciais-e-certs-no (b2eb825)
- Aprovação do usuário ("Aprovo, existe snapshot").
- Executado: backup (bd_pm_bora, bd_cm_bora e plataforma ok), imagem gerada e 28 suítes ok contra a imagem.
- Reinício adiado para 17h01, depois da janela do Diário; em seguida, `provision atualizar` (sem migração nova) e subida do worker.
- Conferido:
  - pm e cm respondem 200 e a gestão 303;
  - versão certa;
  - o app acha 1 certificado intermediário do INEP;
  - sem erros nos logs.
- prefbora (nó):
  - a credencial do IEG-M chegou ao nó (ordem 8 feita às 13h34), e o diagnóstico no nó deu legível com HTTP 200;
  - o teste do painel não fazia requisição porque, no órgão novo, o IEG-M começa em modo **manual**, o padrão do catálogo; o administrador liga em Painel de indicadores → Município e gestão → IEG-M → Modo de atualização;
  - o INEP no nó continua dependendo do pacote novo ou do contorno no `.env`.

## 15/11/2026 — Ajustes pedidos pelo órgão: notícias, comunicados, álbuns, Conheça e portal oculto (ramo `ajustes-noticias-albuns`, código)
- **Data da notícia e do comunicado:** dois campos opcionais (data e hora) no lugar do `datetime-local`, que o navegador bloqueava quando ficava meio preenchido. Data em branco = momento da aprovação/publicação; hora em branco = 08h00.
- **Texto alternativo opcional** em todas as imagens do painel:
  - capa da notícia, álbuns, perfis do Conheça, vereadores, imagens da identidade e imagens no corpo do texto;
  - vazio = imagem decorativa (`alt=""`); na galeria, usa o título da foto ou "Foto N do álbum …";
  - a migração 032 remove a trava de 5 caracteres no banco (`album_fotos` e `perfil_fotos`).
- **Ponto focal:** no lugar dos dois números, clique na imagem (ou setas do teclado). As prévias dos recortes acompanham na hora, inclusive para a imagem recém-escolhida.
- **Arquivados:** "Todos" deixa de mostrar o que está arquivado em notícias/páginas, comunicados (nova aba "Arquivados") e Carta de Serviços (nova aba "Arquivadas").
- **Tipos de comunicado e categorias de álbum:** lista editável (adicionar, renomear, remover) no lugar do texto separado por vírgulas.
  - Renomear um tipo atualiza os comunicados que o usam; um comunicado antigo mantém o tipo removido.
  - Remover uma categoria deixa os álbuns dela sem categoria.
- **Comunicados no portal:** título à esquerda e etiqueta do tipo à direita.
- **Conheça:**
  - sai do painel a seção "Fotos do bloco", que o portal não usava mais (as fotos ao lado são as dos perfis em destaque);
  - gentílico e fundação/emancipação voltam a aparecer (o bloco mostrava só 6 números; agora até 8);
  - botão "Galeria de fotos" quando há álbum publicado e o bloco da galeria está desligado.
- **Álbuns:**
  - no painel, grade de miniaturas paginada (48 por página), edição de uma foto por vez e envio de até 20 fotos de uma vez;
  - no portal, álbum paginado (40 por página).
- **Bloco novo "Galeria de fotos"** na página inicial. Entra oculto; o órgão liga e posiciona em Página inicial.
- **Portal oculto enquanto é configurado** (Funcionalidades → Visibilidade do portal):
  - quem não entrou no painel do órgão vê "Portal em preparação" (HTTP 503, `noindex`);
  - a equipe vê o portal com uma faixa de aviso;
  - a API pública e o login seguem abertos;
  - o ativador passou a conferir o domínio por `/admin/login`, para não retirar o domínio de um portal oculto.
- **Testes:**
  - nova suíte `tests/teste_ajustes_portal.py`;
  - as suítes antigas que exigiam texto alternativo e "Fotos do bloco" foram atualizadas para a regra nova.
- **Não implantado** (aguarda aprovação).

## 15/11/2026 21:40 — Implantação: ajustes-noticias-albuns (cbfd56f)
- Aprovação do usuário ("Aprovo, existe snapshot").
- Executado: backup (bd_pm_bora, bd_cm_bora e plataforma ok), imagem gerada e 29 suítes ok contra ela.
- Subida às 21h39, fora da janela do Diário, com `provision atualizar`.
- Conferido:
  - migração 032 aplicada nos dois órgãos (sem trava de texto alternativo);
  - bloco "Galeria de fotos" acrescentado oculto;
  - os dois portais continuam publicados (sem `portal_oculto`);
  - pm e cm respondem 200 em / e em /admin/login;
  - a gestão responde 303;
  - versão certa;
  - sem erros nos logs;
  - timer do ativador ativo (agora confere os domínios em /admin/login).

## 15/11/2026 — Vitrine de notícias e comunicados, coluna à direita, previsão do tempo e editor ampliado (código; branch vitrine-tempo-editor)
Pedido do usuário: Comunicados e Notícias no modelo da imagem enviada; telas do admin e páginas de notícias e comunicados em 100% da largura; editor de texto com mais formatação; coluna com as 5 últimas notícias e os 5 últimos comunicados; previsão do tempo no portal.
- **Vitrine na página inicial** (o mesmo desenho para Notícias e Comunicados):
  - destaque com imagem e texto lado a lado;
  - 3 cartões com imagem, data, título e "Continue lendo";
  - lista de títulos e o botão "Todos";
  - cada cartão é um link só;
  - o desenho se ajusta à largura disponível (container query);
  - Comunicados passa a ocupar a largura toda, com "Serviços mais acessados" logo abaixo.
- **Miniatura do comunicado:** vem do 1º anexo em PDF (1ª página, gerada pelo Ghostscript em modo seguro, com tempo-limite) ou imagem.
  - Sem anexo assim, mostra o quadro neutro na cor do portal.
  - A miniatura (`/anexo/<arquivo>/capa`) segue a mesma regra de visibilidade do anexo.
  - Não houve mudança de esquema.
- **Notícias e comunicados em largura total** (página da notícia, página do comunicado e as duas listas), com coluna à direita:
  - previsão do tempo;
  - últimas 5 notícias (some no período eleitoral);
  - últimos 5 comunicados.
  - No celular, a coluna vai para o fim.
- **Previsão do tempo:**
  - nova fonte `tempo` (Open-Meteo, dados abertos CC BY 4.0, sem chave), pelo centro do município informado pelo IBGE (código IBGE do órgão; nada específico de Borá);
  - roda de hora em hora, e Prefeitura e Câmara do mesmo município compartilham a coleta;
  - previsão com mais de 6 h não aparece;
  - novo bloco da página inicial "Previsão do tempo", que entra logo antes de Comunicados;
  - testado o acesso a partir da VPS: o Open-Meteo responde e o INMET não.
  - Migrações:
    - 033 (controle) e `migrations_local/004` (nó) incluem `tempo` na lista de fontes;
    - as migrações 009, 011, 014, 016 e 024 passaram a ter a lista completa, porque são reaplicadas em ordem. Antes faltava `govbr` nelas, o que quebraria a atualização de um nó com fonte GOVBR.
- **Editor de texto** (notícias, comunicados, páginas, Conheça):
  - estilo do parágrafo (Título de seção, Subtítulo, Título menor, Citação);
  - desfazer/refazer;
  - sublinhado, tachado, marca-texto, sobrescrito e subscrito;
  - alinhamento (por classe, nunca `style`);
  - recuo de lista;
  - link com diálogo próprio (Ctrl+K) e botão para remover link;
  - linha divisória;
  - tabela com acrescentar/apagar linha e coluna;
  - imagem centralizada;
  - vídeo do YouTube (vira player youtube-nocookie no portal);
  - ver o código HTML;
  - tela cheia;
  - contagem de palavras.
  - O servidor continua limpando tudo por lista fechada (nh3).
- **Admin em largura total:** as telas com editor (notícia, comunicado etc.) saem do limite de 760 px, com os campos curtos em colunas.
- **Testes:**
  - nova suíte `tests/teste_vitrine_tempo.py` (dados fictícios; a previsão de teste é gravada à mão, sem consulta real);
  - `teste_ajustes8` e `teste_fase8` foram atualizados para a marcação nova;
  - nas capturas (ambiente de teste), o axe (WCAG 2.1 AA) não apontou nada na página inicial, na notícia, no comunicado, nas listas e no editor, e não há rolagem horizontal em 1366 e 390 px.
- **Implantado na gestão em 15/11/2026, 12h31 (Brasília)**, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `acdb02f` no main; backup `deploy/backup.sh` ok (plataforma, bd_pm_bora, bd_cm_bora); versão `vitrine-tempo-editor (acdb02f)`;
  - as 30 suítes passaram contra a imagem nova;
  - `provision atualizar` aplicou a 033 e acrescentou, em pm-bora e cm-bora, a fonte `tempo` e o bloco `tempo` antes de Comunicados;
  - primeira coleta real: pm-bora 25,9 °C agora, 4 dias de previsão; cm-bora reaproveitou a mesma previsão (mesmo município);
  - conferido: as páginas iniciais, /noticias e /comunicados respondem 200 com portal.css v=26, a previsão do tempo e a coluna à direita. A Câmara ainda não tem comunicados cadastrados, por isso o bloco aparece vazio.
- **Falta:** atualizar o nó do prefbora (pacote novo do console e o instalador; na etapa 8, `s`, para a migração local 004).

## 15/11/2026 — Ajuste da vitrine de Comunicados e da faixa do tempo (código; branch ajuste-vitrine-tempo)
Pedido do usuário (após ver no ar): Comunicados no mesmo tamanho e posição de antes, mudando só os alinhamentos como na referência; previsão do tempo em faixa de largura total, mais discreta.
- **Comunicados** volta para a metade da largura, ao lado de "Serviços mais acessados", como era antes. O desenho da referência (destaque com imagem ao lado do texto, 3 cartões, lista) se ajusta à largura da coluna:
  - em coluna estreita, títulos e botões ficam menores e a lista mostra título e data um embaixo do outro;
  - no celular, os cartões viram linhas com miniatura à esquerda.
- **Previsão do tempo:** faixa de uma linha em largura total, sem quadros, com ícones e textos em cinza: agora (temperatura, condição, umidade, vento), os 4 dias (máxima/mínima e chance de chuva) e a fonte (Open-Meteo, CC BY 4.0) com o horário da atualização.
- portal.css v=27. Testes: `teste_vitrine_tempo` ganhou a checagem "Comunicados ao lado de Serviços"; `teste_vitrine_tempo`, `teste_escala`, `teste_ajustes8` e `teste_fase8` passaram. Capturas no ambiente de teste (dados fictícios) em 1366, 1000 e 390 px: sem rolagem horizontal; o axe não apontou nada.
- **Implantado na gestão em 15/11/2026, 12h59 (Brasília)**, com aprovação do usuário ("Aprovo, existe snapshot"): mescla `3217a53`; backup ok (plataforma, bd_pm_bora, bd_cm_bora); versão `ajuste-vitrine-tempo (3217a53)`; as 30 suítes passaram contra a imagem nova; `provision atualizar` sem blocos novos. Conferido: as páginas iniciais da Prefeitura e da Câmara e /comunicados respondem 200, com portal.css v=27, Comunicados ao lado de Serviços e a faixa do tempo nova.
- **Falta:** o nó do prefbora recebe esta versão junto com a anterior (pacote novo do console e o instalador; na etapa 8, `s`).

## 15/11/2026 — Comunicados de volta à lista e previsão do tempo sobre a foto principal (código; branch comunicados-lista-tempo)
Pedido do usuário: o bloco Comunicados devia continuar como era (lista), mudando só o alinhamento e o posicionamento; a previsão do tempo numa faixa logo abaixo do cabeçalho, flutuando sobre a foto principal, só com hoje e amanhã; o restante numa página própria.
- **Comunicados na página inicial:** voltou a ser a lista ao lado de "Serviços mais acessados" (sem destaque nem cartões), em duas colunas (pedido seguinte do usuário): à esquerda o tipo (Comunicado, Aviso…) alinhado à direita; à direita o título e, embaixo, a data; linhas finas entre os itens e o botão "Todos os comunicados" no fim. As miniaturas dos PDFs continuam na página /comunicados.
- **Previsão sobre a foto principal:** faixa translúcida no alto da foto, com agora, Hoje e Amanhã (máxima/mínima e chance de chuva) e o botão "Previsão completa". No celular vai para o alto da foto e quebra em linhas. Sem a foto principal (bloco "hero" desligado), a previsão aparece como faixa discreta no lugar do bloco "Previsão do tempo", também só com hoje e amanhã. Desligar o bloco "Previsão do tempo" tira a faixa da foto.
- **Página /tempo (nova):** agora (temperatura, condição, umidade, vento) e os próximos dias (condição, máxima/mínima, chance e milímetros de chuva), com a fonte (Open-Meteo, CC BY 4.0, centro do município pelo IBGE) e o aviso de que é estimativa (alertas oficiais: Defesa Civil). A coleta passa de 4 para 7 dias.
- A coluna à direita das notícias e comunicados mostra também só hoje e amanhã, com o link para /tempo.
- portal.css v=29. Removida `fase8.vitrine_comunicados` (sem uso).
- Testes: `teste_vitrine_tempo` atualizado (lista de comunicados na página inicial, previsão sobre a foto, só 2 dias, página /tempo, faixa quando não há foto, previsão velha some também da página); passaram `teste_vitrine_tempo`, `teste_escala`, `teste_ajustes8`, `teste_ajustes_portal`, `teste_painel_admin` e `teste_fase8`. Capturas no ambiente de teste (dados fictícios), Prefeitura e Câmara, 1366 e 390 px: sem rolagem horizontal; o axe não apontou nada na página inicial nem em /tempo.
- **Implantado na gestão em 15/11/2026, 13h41** (ver a entrada "Linhas finas na seção Notícias").

## 15/11/2026 — Linhas finas na seção Notícias (código; branch noticias-linhas)
Pedido do usuário: Notícias também separada por linhas finas, inclusive o destaque.
- Linha fina abaixo do destaque, linhas verticais entre os 3 cartões (no espaço entre eles, para os cartões ficarem com a mesma largura) e as linhas da lista, que já existiam. No celular, os cartões viram linhas separadas por linha horizontal.
- portal.css v=30. Capturas no ambiente de teste (dados fictícios) em 1366 e 390 px.
- **Implantado na gestão em 15/11/2026, 13h41 (Brasília)**, junto com comunicados-lista-tempo, com aprovação do usuário ("Aprovo, existe snapshot" e "Sim, implantar juntas"):
  - mesclas `523f433` e `054b62f` no main; backups ok (plataforma, bd_pm_bora, bd_cm_bora) às 13h21 e 13h28; versão `noticias-linhas (054b62f)`;
  - as 30 suítes passaram contra a imagem final; `provision atualizar` sem fontes nem blocos novos;
  - conferido: páginas iniciais da Prefeitura e da Câmara com a previsão sobre a foto e portal.css v=30; Comunicados da Prefeitura em duas colunas; /tempo responde 200 nos dois portais. A página mostra 4 dias até a próxima coleta, que passa a trazer 7.
- **Falta:** o nó do prefbora recebe estas versões pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).

## 15/11/2026 — Diário: órgãos cadastrados, texto formatado com pré-formatação e alinhamento dos campos do painel (código; branch alinhamento-diario-orgaos)
Pedido do usuário: no Diário Oficial o órgão já vem escolhido, de uma lista cadastrada (para ninguém digitar de um jeito diferente ou errado); o texto do ato com formatação e uma pré-formatação automática aplicada documento por documento; corrigir os campos desalinhados (caixas de marcar em Notícias e no Período eleitoral, os "Horários (dias úteis)" do Diário) depois de analisar todos os formulários dos portais.
- **Órgãos do Diário (aba nova "Órgãos"):** nome oficial, sigla, caderno (Executivo/Legislativo), "em uso" e órgão padrão; botão para trazer as secretarias já cadastradas na Carta de Serviços. Renomear corrige só os atos ainda fora de edição. Migração `034_orgao_diario_orgaos.sql` (tabela `diario_orgaos`; `diario_atos.orgao_id` e `diario_atos.html`). Nenhum órgão é criado automaticamente: cada órgão cadastra os seus.
- **Envio do ato:** o órgão é escolhido na lista, agrupada por caderno; o caderno vem do órgão. Já vem escolhido o órgão do último ato que a pessoa enviou; para quem nunca enviou, o padrão. Sem órgão cadastrado: aviso com link e envio recusado. Envio de órgão fora da lista ou fora de uso é recusado.
- **Texto do ato:** editor do painel (sem imagem nem vídeo; tabela, listas, alinhamento, negrito etc. continuam), HTML limpo no servidor; o texto simples sai dele (busca, Legislação, verificação de CPF completo). Botão **Pré-formatar** (`app/diario_formato.py`):
  - título centralizado em negrito e ementa recuada (LC 95/1998);
  - "DECRETA:"/"RESOLVE:" em negrito; CAPÍTULO/SEÇÃO centralizados;
  - "Art. 1º" até o 9º e "Art. 10." em diante, "§ 1º", "Parágrafo único.", incisos "I –", alíneas "a)";
  - local e data e assinatura centralizados.

  Nada é inventado; rodar duas vezes dá o mesmo resultado; "Voltar ao texto anterior" desfaz.
- **PDF da edição:** o texto formatado vai para o PDF (alinhamento, negrito/itálico/sublinhado, listas, tabelas, linha divisória); atos sem formatação (e remessas da Câmara) saem como antes.
- **Alinhamento dos campos:** auditoria automática de todas as telas com formulário (Prefeitura, Câmara e console da gestão, 1366 e 390 px; 124 telas). Problemas achados e corrigidos na regra geral do `admin.css` (v=19), sem remendo tela a tela:
  - caixa de marcar/opção abaixo do texto: a altura mínima dos campos valia para ela;
  - campos lado a lado desnivelados quando os rótulos têm tamanhos diferentes (Horários do Diário, Dados do órgão, Transmissões);
  - linha da tabela de menus vazando;
  - campos sem borda na lista de tipos de comunicado;
  - campos das imagens da identidade e cadastro de feriados com rolagem lateral no celular.

  Depois da correção, nenhuma tela com desalinhamento. A presença das sessões tem rótulo por leitor de tela (aria-label).
- admin.js v=7. Testes: `teste_diario_orgaos` (novo) e os testes do Diário ajustados para escolher o órgão na lista. Capturas no ambiente de teste com dados fictícios.
- **Implantado na gestão em 15/11/2026, 18h20 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `bc93691`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 17h54; versão `alinhamento-diario-orgaos (bc93691)`;
  - as 31 suítes passaram contra a imagem nova (inclusive o instalador, que tinha falhado uma vez na rodada anterior e passou nas duas seguintes);
  - `provision atualizar` aplicou a `034_orgao_diario_orgaos` na Prefeitura e na Câmara; sem fontes nem blocos novos;
  - conferido: portais e login 200; admin.css v=19 com as regras de alinhamento e admin.js com o Pré-formatar; colunas `html` e `orgao_id` criadas; app e worker de pé, sem erros nos logs.
- **Falta (usuário):** cadastrar os órgãos do Diário da Prefeitura (Diário Oficial → Órgãos, ou "Trazer as secretarias cadastradas") antes do próximo envio de ato; até lá o envio mostra o aviso e é recusado.
- **Falta:** o nó do prefbora recebe esta versão pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).

## 15/11/2026 — Aprovação para publicar: política por módulo (código; branch politica-aprovacao)
Pedido do usuário: parametrizar a aprovação. Conforme a política, o conteúdo vai direto ao ar ou passa por autorização; no painel, escolher se publicar exige autorização e quem autoriza. Vale para tudo no portal, exceto o que tem regras próprias (como o Diário Oficial).
- **Tela nova "Aprovação para publicar"** (Administração; só o administrador do órgão): para cada módulo, "Publica direto" ou "Exige aprovação". Com aprovação, quem aprova pode ser definido por perfil (Administrador, Publicador, Editor, Procuradoria) e/ou por pessoa. Há ainda a opção "quem escreveu não aprova o próprio". Aprovação sem ninguém para aprovar é recusada. Cada mudança vai para a auditoria. A política fica na configuração do órgão (`config.aprovacao`), sem código por órgão (`app/aprovacao.py`).
- **Módulos:** Notícias e páginas; Comunicados; Conheça a cidade e Fotos e álbuns (Prefeitura); atos da Câmara no portal (pauta, presença, votação e ata, pautas e pareceres das comissões, contas; só na Câmara).
- **Padrão = o que já acontecia:** notícias, comunicados e atos da Câmara com aprovação de Administrador/Publicador; Conheça e Fotos publicam direto. Nada muda até o administrador mudar.
- **Com aprovação:**
  - quem não aprova envia para aprovação. Tentar publicar direto vira pedido de aprovação;
  - quem aprova publica direto, aprova ou devolve (devolver exige comentário, que o autor vê);
  - quem não aprova altera algo já no ar: o item sai do ar até a nova aprovação (nada entra no ar sem aprovação);
  - foto ou vídeo incluído ou alterado por quem não aprova fica fora do ar até a aprovação do perfil ou álbum;
  - o menu mostra quantos itens esperam aprovação (Comunicados, Conheça e Fotos, além das Notícias).
- **Publica direto:** quem edita publica (botão "Publicar") e corrige o que já está no ar sem tirar do ar.
- **Ficam com regras próprias (aparecem na tela, sem mudar):** Diário Oficial, Carta de Serviços, exceção do período eleitoral (Procuradoria) e moderação das manifestações do cidadão. As travas do período eleitoral valem nos dois modos.
- Comunicados ganharam as situações "Em aprovação" e "Devolvido". Migração `035_orgao_aprovacao.sql` (só colunas e situações novas; nada é apagado). admin.css v=20. Teste novo `teste_aprovacao` (pessoas e conteúdos fictícios).
- Testes: as 32 suítes passaram contra o código (a `teste_aprovacao` também com data simulada). Captura da tela nova no ambiente de teste em 1366 e 390 px, sem desalinhamento nem rolagem lateral.
- **Implantado na gestão em 15/11/2026, 21h20 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `e29d6f9`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 21h18; versão `politica-aprovacao (e29d6f9)`;
  - as 32 suítes passaram contra a imagem nova;
  - `provision atualizar` aplicou a `035_orgao_aprovacao` na Prefeitura e na Câmara; sem fontes nem blocos novos;
  - conferido: portais, login, /comunicados e /fotos 200; /admin/aprovacao pede login (303); admin.css v=20; colunas `aguarda_aprovacao` (5 por banco) e situações novas dos comunicados criadas; app e worker de pé, sem erros nos logs.
- A política começa igual ao comportamento anterior; o administrador muda em Administração → Aprovação para publicar.
- **Falta:** o nó do prefbora recebe esta versão pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).

## 16/11/2026 — Rodapé com imagem de fundo, camada de cor e mascote; "Remover imagem" na Identidade (código; branch rodape-mascote)
Pedido: `Docs/PEDIDO-RODAPE-MASCOTE.md`. Esboço aprovado pelo usuário com as decisões: (1) cores atuais como padrão, editáveis pelo painel, sem código; (2) mascote só no rodapé, com tamanho e posição personalizáveis; (3) aplicar a melhor solução para a captura com camada de 60%; (4) "Suspender o mascote no período eleitoral" ligado por padrão.
- **Cor do rodapé no Tema e cores:** campo novo com seletor, contraste na hora e prévia. O padrão continua o de sempre (Prefeitura `#17212B`, Câmara `#16291A`) e "Voltar à cor padrão" desfaz. As faixas do nome e do © acompanham em tons derivados. Cor que deixa texto, títulos, faixa do nome ou faixa do © abaixo de 4,5:1 é recusada. Com a cor padrão o rodapé é idêntico ao anterior: as capturas antes e depois (sem fundo, sem mascote) batem pixel a pixel nas 3 larguras e nos 2 portais.
- **Faixa das colunas em camadas** (só ela; as faixas do nome, das redes e do © não mudam): 0 imagem de fundo (`<img>` decorativa, `loading="lazy"`, WebP 1920 e 960 px com `srcset`, ponto focal); 1 camada da cor do rodapé com transparência (só a camada, nunca os textos); 2 mascote (`pointer-events:none`, `alt=""`, `aria-hidden`); 3 textos. Sem imagem, a cor é sólida.
- **Contraste da camada:** no envio o servidor mede o trecho mais claro da imagem (percentil 95, Pillow). O painel mostra o contraste do pior caso e o mínimo seguro, com "Usar o mínimo seguro"; o servidor recusa salvar abaixo dele. Trocar por imagem mais clara ou mudar a cor sobe a camada sozinha para o mínimo (registrado na auditoria).
- **Mascote só no rodapé:** saiu da faixa do nome. Lado (esquerda/direita), altura de 120 a 320 px (padrão 220), transparência, mostrar no celular (até 140 px, com espaço reservado), exibir sim/não e suspensão no período eleitoral (padrão ligado). Se não couber na área livre abaixo da coluna, reduz sozinho (portal.js). Conferido no navegador: nenhuma sobreposição com texto e todos os links clicáveis em 1920, 1366 e 390 px.
- **Alto contraste, `prefers-contrast: more` e impressão:** sem imagem de fundo e sem mascote, cor sólida.
- **Seção "Rodapé"** em Identidade → Brasão, mascote e fundos: imagem de fundo (enviar, trocar, remover, restaurar), opacidade da camada, controles do mascote e prévia ao vivo (computador/celular) com o resultado do contraste. Sem mascote, os controles ficam desativados com a nota "Envie um mascote".
- **Remover imagem em toda a Identidade** (brasão, mascote, fundos do destaque, do login e do rodapé, foto da sede, fotos do bloco, favicon): pede confirmação e só desvincula da configuração. O arquivo e a biblioteca de mídia ficam. "Restaurar a anterior" aparece enquanto houver anterior (remover ou trocar guarda as 5 últimas). Tudo na auditoria. Fallbacks: sem brasão, só o nome (selo); sem fundo do destaque, do login ou do rodapé, cor sólida; sem favicon, ícone padrão neutro da plataforma (`/static/favicon-padrao.svg`). Imagem cujo arquivo sumiu não vira `<img>` quebrada.
- Corrigido de passagem: erro de script na tela de Tema (o grupo "Largura máxima" não tem seletor de cor).
- Migração `036_orgao_rodape.sql` (só grava os padrões em `config.rodape`, sem sobrescrever). portal.css v=31, portal.js v=7, admin.css v=21, admin.js v=8. Teste novo `teste_rodape` (camadas, lados, sem fundo = cor sólida, bloqueio de contraste, alto contraste, cliques, defeso, remover/restaurar de cada imagem, favicon, arquivo ausente, Câmara, permissão).
- Capturas em `Docs/avaliacao-rodape/` (antes, esboço e depois), nos dois portais, em 1920, 1366 e 390 px: (a) sem fundo e sem mascote; (b) fundo + camada 85% + mascote à esquerda; (c) fundo + camada 60% + mascote à direita com 50%; (d) alto contraste; celular com o mascote ligado; e as telas do painel. Para (c) a foto é a vista aérea escurecida (exemplo de foto noturna): nenhuma foto real do tema passa com 60% (o mínimo delas fica entre 65% e 80%). O bloqueio com a foto original aparece em `painel-rodape-bloqueio-1366.png`. Mascote fictício marcado EXEMPLO. Ambiente de teste com dados fictícios.
- axe (WCAG 2.1 A/AA) na página inicial com fundo e mascote (Prefeitura 1366 e 390, Câmara 1366) e nas telas Imagens e Tema do painel: sem violações.
- Testes: as 33 suítes passaram contra o código; `teste_rodape` e `teste_painel_admin` repetidas depois dos últimos ajustes visuais do painel, também com data simulada. **Não implantado:** aguarda aprovação do usuário (e snapshot).
- **Implantado na gestão em 16/11/2026, 08h10 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `ee263a4`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 08h02; versão `rodape-mascote (ee263a4)`;
  - as 33 suítes passaram contra a imagem nova;
  - `provision atualizar` aplicou a `036_orgao_rodape` na Prefeitura e na Câmara (camada 85%, suspensão no defeso ligada); sem fontes nem blocos novos;
  - conferido: portais, login e favicon padrão 200; portal.css v=31 e portal.js v=7; rodapé com a cor de sempre e camada sólida (sem imagem de fundo); `/admin/identidade/rodape` pede login (303); app e worker de pé, sem erros nos logs;
  - no navegador (só leitura), na Prefeitura: o mascote já enviado passou da faixa do nome para a faixa das colunas (220 px, à esquerda), sem sobrepor texto e com os 23 links clicáveis em 1920 e 1366 px. Captura em `Docs/avaliacao-rodape/depois/producao-pm-1366.png`.
- **Atenção (usuário):** o mascote atual da Prefeitura tem fundo branco opaco e aparece como um quadro branco no rodapé escuro. Opções no painel (Identidade → Brasão, mascote e fundos): enviar o mascote em PNG com fundo transparente, ou desligar "Exibir no rodapé", ou reduzir a altura. Configuração não alterada sem pedido.
- **Falta:** o nó do prefbora recebe esta versão pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).

## 16/11/2026 — Diário: edições de teste no portal, com legenda (código; branch diario-teste-publico)
Pedido do usuário: "publique mesmo o teste, mas com legenda de edição teste - não homologada - sem validade". Antes, a edição de teste nunca aparecia no portal.
- **Diagnóstico (só leitura, produção):** a Prefeitura não tinha nenhuma edição, nem de teste. Há 1 ato aprovado (enviado em 15/11, 17h09, depois do corte) à espera da edição de 16/11. O Diário está em modo teste, e nesse modo a rotina automática não abre edições: a edição precisa ser aberta, fechada, assinada (teste) e publicada pelo painel.
- **Mudança:** a edição de teste publicada aparece na lista do Diário, nos cartões da página inicial, no PDF e na verificação. Sempre traz a legenda **"Edição teste — não homologada — sem validade"** (selo em cada edição e aviso no topo da lista). O PDF traz a mesma legenda na capa e na marca d'água (antes: "SEM VALOR OFICIAL — TESTE").
- **Opção do órgão:** Diário Oficial → Signatários, calendário e lei → "Edições de teste no portal" (padrão: mostrar; registrada na auditoria). Desligada, a edição de teste some da lista, da página inicial, do PDF público e da verificação.
- Nada muda para as edições oficiais. Ao passar para o modo oficial, as edições de teste continuam sendo apagadas (numeração oficial começa do nº 1). portal.css v=32.
- Testes: `teste_fluxos` e `teste_diario_seguranca` atualizados para a regra nova (legenda na lista, na página inicial e na verificação; PDF lido de verdade, com a legenda na capa e na marca d'água; opção desligada esconde tudo, inclusive o PDF; auditoria). As 33 suítes passaram contra o código. Capturas em `Docs/avaliacao-diario-teste/` (ambiente de teste, ato fictício).
- **Implantado na gestão em 16/11/2026, 09h05 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `e2d4e41`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 08h54; versão `diario-teste-publico (e2d4e41)`;
  - as 33 suítes passaram contra a imagem nova; sem migração nova (o `provision atualizar` não aplicou nada);
  - conferido: portais, /diario, /diario/verificar e login 200; portal.css v=32 com o estilo da legenda; opção "mostrar edições de teste" ligada (padrão) na Prefeitura; /admin/diario/config pede login (303); app e worker de pé, sem erros nos logs.
  - /diario ainda mostra "Nenhuma edição": a Prefeitura não tem edição publicada.
- **Falta (usuário):** fazer a edição pelo painel (Diário Oficial: Abrir edição → Fechar → Assinar cada etapa → Publicar). Em modo teste a rotina automática não abre edições. Depois disso, a edição aparece no portal com a legenda.
- **Falta:** o nó do prefbora recebe esta versão pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).

## 16/11/2026 — Caixas de marcar e botões de opção: componente padrão do painel e do console (código; branch caixas-selecao)
Bug relatado pelo usuário em Identidade → Fundo do rodapé: a caixa "Imagem decorativa" herdava `width:100%` dos campos de texto, ficava centralizada e empurrava o rótulo para fora do cartão, uma palavra por linha.
- **Causa:** a regra de largura total dos campos (`.campos-m :is(input,select,textarea)`, e também a borda, a altura mínima e o tamanho de fonte de `.campos-m input`, `form.campos input` e `.inline input`) valia também para checkbox e radio.
- **Correção no componente padrão (admin.css, vale para o painel e o console):**
  - largura, borda, altura e fonte dos campos só valem para texto, select e textarea (`:not([type=checkbox],[type=radio])`);
  - caixa de marcar e botão de opção ficam na mesma linha do texto, alinhados à esquerda, com 18 px e alinhados à primeira linha;
  - o rótulo inteiro é clicável e o texto quebra abaixo de si mesmo, sem sair do cartão;
  - as duas regras antigas de alinhamento foram unificadas.
  - Campo desativado agora parece desativado (fundo cinza).
- **Fundo do rodapé:**
  - "Imagem decorativa" vem antes do texto alternativo, com `<label for>`;
  - marcada, desativa o texto alternativo e mostra a nota "o texto alternativo não é necessário".
- **Todas as imagens da Identidade:** ao escolher o arquivo, a prévia local aparece no quadro (antes "sem imagem"), com o selo "Prévia (não salva)", antes de salvar.
- **Varredura de 132 telas** (Prefeitura, Câmara e console; 1366 e 390 px), com a auditoria de formulários ampliada (rótulo fora do cartão, rótulo espremido). Telas afetadas e corrigidas:
  - Identidade → Fundo do rodapé (Prefeitura e Câmara): caixa esticada e rótulo fora do cartão;
  - Sessão da Câmara → Presença: botões de opção sem `<label>` (só `aria-label`). Ganharam `<label for>` com o texto para leitor de tela e área de toque de 44 px;
  - Sessão da Câmara, em 390 px: o campo "Vídeo" vazava e causava rolagem lateral. Os campos de formulários em linha agora cabem na largura.
- **Achados sem relação com caixas/opções (não alterados):** console → Cadastrar órgão (lista "Tipo" 7 px desnivelada em 1366); Comunicados → configuração em 390 px (linha 8 px desalinhada); Redes sociais em 390 px (campos da tabela passam da largura, dentro da tabela com rolagem).
- admin.css v=22, admin.js v=9. Capturas antes/depois em 1366 e 390 px e relatórios da auditoria em `Docs/avaliacao-caixas-selecao/` (ambiente de teste, dados fictícios).
- **Junto (Diário, pedido do usuário "onde publico a edição do teste"):** o aviso de MODO TESTE da tela Diário Oficial ainda dizia "SEM VALOR OFICIAL — TESTE" e "Nada é publicado no portal", desatualizado desde a versão `diario-teste-publico`. Agora mostra a legenda nova e o passo a passo para o Administrador: Abrir edição de hoje → Fechar e gerar PDF/A → Assinar (cada etapa) → Concluir edição de TESTE. Captura `diario-aviso-modo-teste-1366.png`. Em produção (só leitura), a Prefeitura continua sem nenhuma edição aberta, e `admin@pmbora.conectatech.tech` tem perfil Administrador.
- **Diário: nomes dos botões mais específicos** (pedido do usuário: "Abrir edição de hoje" dava a entender reabrir ou refazer algo). As ações enviadas ao servidor não mudam, só os textos:
  - "Abrir edição de hoje" → **Criar a edição de hoje**; "Abrir edição extra" → **Criar edição extra**;
  - "Fechar e gerar PDF/A" → **Fechar a edição e gerar o PDF (inclui os atos aprovados)**;
  - "Assinar no servidor: …" → **Assinar: …**;
  - "Concluir edição de TESTE" / "Publicar edição" → **Publicar a edição de teste (com a legenda)** / **Publicar a edição**;
  - "Reabrir" → **Desfazer o fechamento (voltar a incluir atos)**.
  - O quadro "Edição em andamento" mostra os **4 passos** (Criar a edição · Fechar e gerar o PDF · Assinar · Publicar) com o passo atual destacado (`aria-current="step"`). As mensagens dizem o passo e o próximo, e a de publicação em teste diz se a edição aparece no portal com a legenda. Capturas dos 4 passos em `Docs/avaliacao-caixas-selecao/diario-passos/`.
- Testes: as 33 suítes passaram contra o código (o `teste_diario_orgaos` confere a regra nova do componente). **Não implantado:** aguarda aprovação do usuário (e snapshot).
- **Implantado na gestão em 16/11/2026, 10h45 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `3ef50c0`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 10h33; versão `caixas-selecao (3ef50c0)`; nenhuma edição do Diário estava em andamento;
  - as 33 suítes passaram contra a imagem nova; sem migração nova;
  - conferido: portais, /diario e login 200; admin.css v=22 com o componente de caixas, os passos do Diário e a presença; admin.js com a prévia local; app e worker de pé, sem erros nos logs.

## 16/11/2026 — Diário: capa nova, miolo em 2 colunas e carimbos laterais das assinaturas (código; branch diario-capa)
Pedido: `Docs/PEDIDO-DIARIO-CAPA.md`. O protótipo citado estava em `Docs/diario-prototipo-2colunas.html`, não em `Docs/referencia/prototipos/`. Decisões do usuário: baixar a Public Sans (OFL, repositório uswds/public-sans) e o pyphen 0.17.0 (PyPI); os Poderes seguem na mesma página.
- **Capa** (`diario_layout.desenhar_capa`, separada do miolo):
  - faixa de identidade na cor do órgão (a escurecida, se o branco não der 4,5:1) com brasão no círculo, órgão · UF, "DIÁRIO OFICIAL", "Eletrônico do Município de …" e a lei de instituição;
  - cartão da edição: nº, "Ano I" em romanos a partir da 1ª edição, data por extenso, dia da semana, páginas e atos com contagens reais, Ordinária/Extra e responsável;
  - "Nesta edição": por Poder, com ementa em até 2 linhas e "pág. N". Continua em "Sumário (continuação)" se não couber;
  - tarja de TESTE; bloco de autenticidade com QR Code (`/diario/verificar?c=CÓDIGO`, que já mostra o resultado); linha institucional com o CNPJ inteiro.
- **Miolo** (2 colunas, 7 mm entre elas, fio fino):
  - **preenchimento sequencial**: a coluna da esquerda enche até o fim e só então a direita; depois, a página seguinte;
  - cabeçalho com fio na cor principal; caixa do Poder (largura total, cor principal); caixas por tipo (Leis, Leis Complementares, Decretos, Portarias, Resoluções, Editais, Licitações e Contratos etc.); atos agrupados por tipo dentro de cada Poder;
  - ato com ementa em itálico recuada 6 mm, corpo em Helvetica 9,5 pt justificado com hifenização em português, assinatura centralizada e registro em 8,5 pt depois de fio pontilhado;
  - título e caixa do tipo nunca ficam sozinhos no pé da coluna;
  - Poderes na mesma página (decisão do usuário): só a última página de um Poder seguido de outro tem as colunas equilibradas, para a caixa do Poder seguinte entrar logo abaixo, na largura total.
- **Quebras de linha do texto de origem** (`diario_texto.py`): as linhas são juntadas em parágrafos, com quebra mantida depois de ponto e dois-pontos e antes de Art., §, Parágrafo, incisos, alíneas e chamadas (RESOLVE:). "Publique-se / e / Cumpra-se." fica numa linha. Assinatura e registro são separados. O texto não muda: comparado na Edição nº 1 (anterior = nova = cadastro). Regra com antes/depois em `Docs/avaliacao-diario/regra-quebras-de-linha.md`. Só há 1 ato real; os outros 2 exemplos são fictícios.
- **Rodapé em todas as páginas:** a linha de sempre e, abaixo, a linha da MP nº 2.200-2/2001 com o endereço de verificação. A marca d'água de teste continua em todas as páginas.
- **Carimbos laterais** (`carimbo_assinatura.py`):
  - **Formato:** são a aparência do próprio campo de assinatura, com um widget por página, criado na mesma atualização em que a assinatura é aplicada. Os cadernos ficam na esquerda, empilhados, de baixo para cima; a assinatura final fica na direita, de cima para baixo.
  - **Dados:** vêm do certificado (titular e AC). A data e a hora são as gravadas na assinatura, porque a sessão do pyHanko usa a hora mostrada.
  - **Fonte:** Public Sans embutida inteira, para manter o PDF/A.
  - **Validação (pyHanko):** todas as assinaturas ficam íntegras, válidas e confiáveis. Para as anteriores, o acréscimo é "preenchimento de formulário" (FORM_FILLING), permitido.
  - **Testado e descartado:** anotações comuns invalidavam a análise das assinaturas anteriores (modificação "não reconhecida").
  - **Ajustes no pyHanko:** dois, aplicados só nessas assinaturas, para aceitar o campo com vários widgets.
  - **Token A3:** a assinatura feita pelo próprio programa do signatário não recebe o carimbo do sistema.
- Testes: `teste_diario_capa` (novo: quebras, preenchimento sequencial, caixas, sumário com continuação, numeração, linha da MP, contagens, ?c= do QR) e `teste_diario_seguranca` (legenda e capa lidas do PDF pelo Ghostscript, carimbos em todas as páginas, assinaturas sem alteração, ?c=).
- **Entrega em `Docs/avaliacao-diario/`:**
  - PDF anterior da Edição nº 1 (cópia de produção, só leitura) e imagens dele;
  - Edição nº 1 TESTE gerada de novo (com o ato real) e assinada, com imagens das 2 páginas;
  - edição de teste com 12 atos fictícios dos dois Poderes (9 páginas: capa, sumário (continuação) e 7 de miolo), assinada pelos dois cadernos e pela final, com imagens de todas as páginas;
  - `validacao-e-texto.json`: comparação do texto e validação pyHanko das 5 assinaturas.
  - Tudo gerado no ambiente de teste, com a cadeia de certificados de TESTE.
- **Não implantado:** aguarda aprovação. A imagem precisa ser reconstruída (pyphen) antes de subir.
- Testes: as 34 suítes passaram contra o código (inclui a nova `teste_diario_capa`). **Não implantado:** aguarda aprovação do usuário (e snapshot).
- **Implantado na gestão em 16/11/2026, 12h01 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `1784f83f`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 11h49; versão `diario-capa (1784f83f)`; imagem reconstruída com o pyphen; nenhuma edição do Diário em andamento;
  - as 34 suítes passaram contra a imagem nova; sem migração nova;
  - conferido: portais, /diario e login 200; `/diario/verificar?c=` mostra o resultado da Edição nº 1; pyphen 0.17.0 e Public Sans carregados no app; app e worker de pé, sem erros nos logs.
  - As edições já publicadas ficam como estão. O novo layout vale para as próximas edições que forem fechadas.
- **Falta (usuário):** validar a regra das quebras (`Docs/avaliacao-diario/regra-quebras-de-linha.md`) e conferir o tipo do ato "Lei 419/2026" (o texto é de Portaria).
- **Falta:** o nó do prefbora recebe esta versão pelo pacote novo do console e o instalador (etapas 8 e 9: `s`).
- **Edição nº 1 de TESTE refeita em produção (16/11/2026, 12h30)**, a pedido do usuário ("altere inclusive na já publicada, é versão teste, não tem validade"; comando aprovado):
  - script `deploy/refazer_edicao_teste.py` (só modo teste; recusa edição oficial). Simulado antes em produção sem gravar e testado de ponta a ponta no ambiente de teste;
  - mantidos número, data, código `9FD6-BC8A-AEDC`, ato e situação; PDF anterior guardado como `diario-2026-11-16-1-TESTE.anterior.pdf`; registrado na auditoria;
  - PDF novo (capa, 2 colunas, linha da MP, carimbos) assinado de novo com os certificados de teste. As 2 assinaturas estão íntegras, válidas e confiáveis, com carimbo do tempo;
  - conferido: /diario/1.pdf entrega o PDF novo (sha256 79c0212b…, igual ao gravado); /diario/verificar?c=9FD6-BC8A-AEDC mostra as assinaturas válidas (cadeia de TESTE) e a legenda. Imagens em `Docs/avaliacao-diario/producao-edicao-1-pagina-*.png`.

## 16/11/2026 — Diário: PDF sempre na versão atual (código; branch diario-pdf-cache)
O usuário não via a Edição nº 1 refeita, embora o servidor já entregasse o PDF novo. O link era sempre o mesmo (`/diario/1.pdf`), o PDF era baixado como anexo com o mesmo nome e não tinha cabeçalho de cache, então o navegador reaproveitava a cópia antiga.
- Links do PDF no portal (lista do Diário, página inicial e verificação) levam a versão: `?v=` com o início do sha256 da edição. Edição refeita ou retificada gera endereço novo.
- O PDF abre no navegador (inline) com `Cache-Control: no-cache` e ETag: sempre confere com o servidor. O PDF baixado no painel para assinar com token também leva a versão e não fica em cache (`no-store`).
- Teste `teste_diario_seguranca` confere o `?v=` e os cabeçalhos.
- Testes: as 34 suítes passaram contra o código. **Não implantado:** aguarda aprovação do usuário (e snapshot).
- **Implantado na gestão em 16/11/2026, 13h15 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, existe snapshot"):
  - mescla `6bd3ec0`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 13h03; versão `diario-pdf-cache (6bd3ec0)`;
  - as 34 suítes passaram contra a imagem nova; sem migração nova;
  - conferido: o link do Diário e da página inicial é `/diario/1.pdf?v=79c0212b002a`; o PDF responde inline, com `Cache-Control: no-cache` e ETag, e é o da Edição nº 1 refeita (234.336 bytes); portais 200; app e worker de pé, sem erros nos logs.

## 16/11/2026 — Limpeza de espaço na VPS (pedido do usuário: "faça a limpeza")
- Antes: disco 36 GB de 48 GB (76%), 12 GB livres.
- Removido, só o que era ferramenta de teste deste projeto:
  - ambiente de teste das capturas (`portal-vit-app`, `portal-vit-db`, rede `portal-vit`) e o volume anônimo do banco de teste (dados fictícios; conferido pela data de criação e pelo conteúdo antes de apagar);
  - imagem do Playwright (3,3 GB; volta a ser baixada, com permissão, quando precisar de captura);
  - cache de build do Docker (0,9 GB).
- Depois: disco 32 GB (67%), **16 GB livres**. Memória disponível 1,9 GB. Portais 200; app, worker e banco de pé.
- Não mexi em imagens nem em volumes de outros sistemas da VPS (pmuinix, wg-config etc.), mesmo os que aparecem como "não usados".
- Ainda pendente: backup fora da VPS (os backups do portal ficam só no disco dela).

## 18/11/2026 — Autoavaliação PNTP da matriz inteira, Prefeitura e Câmara (código; branch pntp-matriz)
Pedido do usuário: "implemente a etapa 6 para ambos os portais/painéis". Antes, a autoavaliação só existia na Câmara, cobria só a dimensão 20 e não tinha percentual.
- Matriz oficial do ciclo 2026, baixada da Atricon com permissão do usuário (`criterios_pntp_2026.zip` e Cartilha PNTP 2026): `app/pntp_matriz_2026.json`.
  - 96 critérios da Prefeitura (12 essenciais, 65 obrigatórios, 19 recomendados) e 83 da Câmara (7, 60, 16). Os totais conferem com a Tabela 1 da cartilha.
  - Para cada critério: classificação e itens de verificação que se aplicam.
- Cálculo (`app/pntp.py`), conforme a Cartilha PNTP 2026, seção III:
  - peso da dimensão (Tabela 2) e peso da classificação (2 / 1,5 / 1);
  - itens 30/30/20/10/10, com rateio quando algum não se aplica; sem disponibilidade, o critério vale zero;
  - níveis da Tabela 3: Diamante, Ouro e Prata exigem 100% dos essenciais; sem eles, "Elevado".
- Medições automáticas (`app/pntp_auto.py`): só o que o portal comprova inteiro, a partir dos dados publicados.
  - Exemplos: acessibilidade, e-SIC, Ouvidoria, Radar, contatos e horário; bases da transparência com atualidade de 30 dias, série dos 3 anos anteriores, exportação e filtros.
  - Na Câmara, a dimensão 20 reaproveita a autoavaliação legislativa que já existia.
  - O resto é marcado pelo controle interno (perfil "Procuradoria / Controle" ou administrador), item a item, com o link da evidência (obrigatório quando atende, como no Avalia). Tabela `pntp_marcacoes`, migração 037.
  - Marcação com mais de 30 dias não conta a atualidade. Critério sem marcação conta zero: nada é dado como atendido sem evidência.
- Painel › Transparência › **Autoavaliação PNTP**, agora nos dois órgãos (`/admin/pntp`):
  - índice estimado e nível;
  - lista dos essenciais que impedem o selo;
  - percentual por dimensão;
  - filtros e a tabela de critérios (itens D/A/S/G/F, nota, como foi avaliado, o que o portal já sabe);
  - formulário de marcação e planilha CSV para apoiar o preenchimento no Avalia.
  - A tela avisa que é estimativa interna e que a nota oficial é a do Avalia, validada pelo Tribunal de Contas.
- Permissões: ver = administrador, publicador (DTIC) e Procuradoria/Controle; marcar = administrador e Procuradoria/Controle. As marcações vão para a auditoria.
- A rota antiga da Câmara (só dimensão 20) foi substituída por esta.
- Teste novo `tests/teste_pntp.py`:
  - quantidades e classes da matriz, pesos, rateio e regra da disponibilidade, índice e níveis;
  - telas dos dois órgãos, medições, marcação (link obrigatório, item que não se aplica, critério automático, 30 dias, apagar), CSV, perfis e separação entre os bancos.
- Testes: as 35 suítes passaram contra o código (inclui a nova `teste_pntp`, conferida também com a data real). **Não implantado:** aguarda aprovação do usuário (e snapshot). A implantação tem a migração 037 (tabela nova, sem alterar as existentes) e não precisa reconstruir dependências.
- **Implantado na gestão em 18/11/2026, 13h19 (Brasília)**, fora da janela do Diário, com aprovação do usuário ("Aprovo, há snapshot"):
  - mescla `b1afcf8`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 13h03; versão `pntp-matriz (b1afcf8)`;
  - as 35 suítes passaram contra a imagem nova; migração 037 aplicada nos dois bancos (tabela `pntp_marcacoes`, vazia);
  - conferido: portais 200 (~0,05 s; a primeira resposta logo após subir levou 3,9 s); `/admin/pntp` sem login redireciona para o login; app e worker de pé, sem erros nos logs.
- **Situação real logo após a implantação** (sem nenhuma marcação; critério sem marcação conta zero):

  | | Índice estimado | Nível | Essenciais atendidos | Medidos pelo portal | Aguardando marcação |
  |---|---|---|---|---|---|
  | Prefeitura | 24,5% | Inicial | 2 de 12 | 34 | 62 |
  | Câmara | 21,8% | Inicial | 2 de 7 | 44 | 39 |

  - Essenciais pendentes, Prefeitura: 3.1, 3.2, 4.1, 4.2, 4.3, 11.5, 11.6, 11.8, 11.9, 11.10.
  - Essenciais pendentes, Câmara: 3.1, 4.1, 4.2, 4.3, 11.5.
- **Falta (usuário/órgãos):** o controle interno marcar os critérios de marcação (com o link da evidência).
- **Falta (nó do prefbora):** receber esta versão pelo pacote novo do console e o instalador.

## 18/11/2026 — Instalador do nó perdia o token e o nome do nó (correção; branch instalador-dados-no)
Relato do usuário: "o script quando gerado está perdendo as informações do nó, token e o nome do nó". Duas causas, que se somavam:
1. **Instalador** (`deploy/no/instalar.sh`, etapa 5): se a VPS já tinha um `.env.origem` de uma instalação anterior (caso do prefbora), o instalador usava esse arquivo e **não abria o pacote novo**. O token e o nome gerados agora no console eram ignorados. Correção:
   - quando há em /root um pacote **mais novo** que o `.env.origem`, o instalador avisa e pergunta "Usar o pacote novo?" (Enter = sim);
   - o `.env.origem` anterior é guardado com data (`.env.origem.anterior-*`, fora do git).
2. **Pacote de segredos** (`app/instalacao.py`): sem a caixa "token novo" marcada (vem desmarcada para nó que já fez contato), o pacote saía **sem o nome do nó, o endereço da gestão e a chave pública**. Correção: esses três dados, que não são segredo, vão sempre. O token do nó continua indo só quando um token novo é gerado (a gestão guarda só o hash do atual). Sem token novo, o instalador mantém o token já gravado no nó.
- A tela "Instalação do nó" no console explica o que o pacote leva.
- Testes:
  - `teste_instalador_no.sh`: reinstalação com pacote novo com token (usa o token e o nome novos), pacote novo sem token (nome novo, token mantido) e pacote novo recusado (mantém o importado). Rodado também contra o instalador antigo: 5 falhas, exatamente o defeito relatado;
  - `teste_instalacao.py`: pacote sem token novo leva nome, gestão e chave pública, e não leva token.
- Testes: as 35 suítes passaram contra o código. **Não implantado:** aguarda aprovação do usuário (e snapshot). Sem migração; a imagem da gestão precisa ser reconstruída (o pacote de código do nó sai da imagem).
- **Implantado na gestão em 18/11/2026, 15h04 (Brasília)**, com aprovação do usuário ("Aprovo, há snapshot" e "suba a atualização"):
  - mescla `24877e8`; backup ok (plataforma, bd_pm_bora, bd_cm_bora) às 14h47; versão `instalador-dados-no (24877e8)`; sem migração;
  - as 34 suítes do app passaram contra a imagem nova. O teste do instalador falhou na primeira rodada; motivo no item abaixo;
  - conferido: a imagem no ar tem o instalador corrigido; gestão 303, portais 200; app e worker de pé, sem erros nos logs.
- **Ocorrência durante a implantação:** os comandos de instalação do nó foram rodados **nesta VPS da gestão**, não na do nó.
  - O que aconteceu:
    - entre 14h20 e 14h51 o pacote de código e o de segredos foram baixados para /root;
    - o código foi extraído por cima de /opt/portal_web e voltou 3 arquivos para a versão anterior à correção. A imagem já tinha sido gerada antes, às 14h47, com a correção;
    - o instalador rodou 4 vezes e parou na etapa 6 (nome do nó inválido, token curto, interrompido).
  - O que não aconteceu: ele **não** gravou o .env (o da gestão continua o de 07/11), pulou atualização, Docker e firewall, e não mexeu no nginx nem nos containers.
  - O que ficou: criou `.env.origem` (cópia das chaves da gestão, permissão 600, fora do git) e copiou a pasta segredos/ do pacote, que tem o mesmo conteúdo da gestão.
  - Os 3 arquivos foram restaurados do commit (iguais aos da imagem) e o teste do instalador passou.
  - Ficaram nesta VPS, para apagar com aprovação: `/root/portal-codigo.tar.gz`, `/root/segredos-no.tar.gz.enc` e `/opt/portal_web/.env.origem`.
- Apagados com aprovação do usuário ("Pode apagar"), às 15h31: `/root/portal-codigo.tar.gz`, `/root/segredos-no.tar.gz.enc` e `/opt/portal_web/.env.origem` (nenhum era usado pela gestão). Gestão e portais seguem no ar.

## 18/11/2026 — Queda da gestão e dos portais (15h38–15h56): instalador do nó rodado na VPS da gestão
- **O que aconteceu:** o pacote do nó (`726025036.conectatech.tech`, gerado às 15h33) foi baixado e o `deploy/no/instalar.sh` rodou **nesta VPS da gestão**, não na do nó. O instalador avisou ".env existe, mas não é de nó" e seguiu:
  - **etapa 7:** gravou um `.env` de nó por cima do da gestão: `PAPEL=no`, senha do banco nova, sem `DOMINIO_PM`/`DOMINIO_CM`, `COMPOSE_FILE` do nó. O original foi guardado como `.env.anterior-20261118183725`;
  - **etapa 8:** recriou db e app com esse `.env`. O banco subiu com a senha nova sobre o volume que usa a antiga, e o provision falhou com `password authentication failed`. O app em modo nó e sem os domínios deixou a gestão em 404 e os portais sem resposta.
- **O que não foi afetado:**
  - volume do banco (`portal_web_pg`, o mesmo) e dados;
  - nginx compartilhado: só o `portal-comum.inc` foi regravado, com conteúdo igual; `nginx -t` ok;
  - ativador, cron, código e os demais sistemas da VPS (casemaster 200, PCA no ar);
  - o pacote não trazia token novo, então o token do nó continua válido.
- **Recuperação (aprovada pelo usuário: "Aprovo, recupere"), 15h56:**
  - `.env` original restaurado (sha256 igual ao backup das 14h47); o gravado por engano foi guardado como `.env.no-gravado-por-engano-20261118`;
  - `.env.origem` apagado; `docker compose up -d db app worker`;
  - pacotes apagados de /root.
- **Conferido:**
  - gestão 303, portais 200, logins da gestão e dos painéis 200, `/transparencia` 200;
  - app em papel "tudo", banco de controle e bancos dos órgãos acessíveis;
  - sem erros nos logs.
- **Falta:**
  - travar o instalador para recusar rodar numa VPS que já é a gestão;
  - apagar `.env.no-gravado-por-engano-20261118` depois de conferido;
  - o nó de teste "asfhaskjhfkas" (criado às 13h18) segue no console.

## 18/11/2026 — Pendências da queda saneadas e trava no instalador do nó (branch instalador-trava-gestao)
Pedido do usuário: "sim, coloque e sane as duas pendências excluindo-os".
- Apagado `.env.no-gravado-por-engano-20261118` (o `.env` de nó gravado por engano na gestão).
- Excluído do console o nó de teste "asfhaskjhfkas" (criado às 13h18, nunca fez contato, sem órgãos), junto com 1 ordem de credencial pendente e 2 links de instalação vencidos. Registrado no log do console.
- **Trava no `deploy/no/instalar.sh`** (etapa 1, antes de qualquer mudança): se a VPS já roda a gestão, o instalador para e avisa "Rode os comandos na VPS do nó, não nesta". Nada é alterado.
  - Considera gestão quando o `.env` existe e não é de nó (PAPEL vazio ou diferente de "no").
  - Ou, sem `.env`, quando o container `portal_web-app-1` roda em outro papel. Sem PAPEL vale "tudo", como na gestão real.
- Tela "Instalação do nó" no console: aviso "Rode estes comandos na VPS do nó (último IP visto), nunca na VPS da gestão".
- Testes:
  - `teste_instalador_no.sh`: gestão com PAPEL=tudo, com PAPEL vazio e só com o container. Nos três casos o instalador para sem alterar o `.env` e sem build, subida, atualização ou firewall;
  - `teste_instalacao.py`: aviso na tela.
- Testes: as 35 suítes passaram contra o código. **Não implantado:** aguarda aprovação do usuário (e snapshot). Sem migração; a imagem da gestão precisa ser reconstruída (o instalador do nó sai da imagem).

## 18/11/2026 — Código no GitHub (pedido do usuário: "suba a versão pro GitHub")
- O projeto ainda não estava no GitHub: não havia remoto, e a conta não tinha repositório dele.
- Antes de enviar, conferi:
  - `.env`, backups, dumps, diagnósticos e pastas de segredos estão fora do git;
  - o `.env.example` só tem valores de exemplo;
  - o `.pem` versionado é o certificado público da AC da RNP;
  - sem tokens, chaves privadas nem CPFs reais (o dos testes é fictício).
- Criado o repositório **privado** https://github.com/anadelson/portal-web.
  - Enviados o `main` (igual ao que está implantado, com os registros) e as 56 tags das implantações.
  - Branch padrão: `main`. O `origin` está configurado neste checkout.
- Ficou só local: o branch `instalador-trava-gestao` (trava do instalador, ainda não implantada), além dos branches antigos de fases já mescladas.

## 18/11/2026 — Autor dos commits trocado em todo o histórico (pedido do usuário)
Pedido: o e-mail institucional e o nome "DTIC Borá" não devem aparecer. Escolha do usuário: histórico todo, com o e-mail `anadelson.bora@gmail.com`; nome `anadelson`, o login do GitHub.
- Backup completo antes: `backups/portal_web-git-antes-autor-20261118.git` (espelho, fora do git).
- Reescritos autor e committer de todos os commits, em todos os branches e nas 56 tags (`git filter-branch`, só os dados de autoria).
  - Conferido: o conteúdo de cada commit, branch e tag é idêntico ao backup, e as relações entre branches e tags não mudaram.
  - O arquivo do usuário `Docs/referencia/prototipos/Main.dc.html` (alteração não versionada) foi guardado e devolvido intacto.
- Enviado ao GitHub com força (`main` e tags). Os 281 commits do `main` no GitHub mostram só `anadelson.bora@gmail.com`.
- Próximos commits neste checkout: `user.name=anadelson`, `user.email=anadelson.bora@gmail.com` (config local do repositório).
- **Os códigos (hashes) dos commits mudaram.** Os citados acima neste arquivo e nas versões em produção são os antigos. Correspondência das implantações:

  | Tag | Antes | Agora |
  |---|---|---|
  | rodape-mascote | ee263a4 | a304ecc |
  | diario-teste-publico | e2d4e41 | 1a9cdb9 |
  | caixas-selecao | 3ef50c0 | c735db2 |
  | diario-capa | 1784f83f | 3b2b467 |
  | diario-pdf-cache | 6bd3ec0 | 7f48860 |
  | pntp-matriz | b1afcf8 | 125f9f2 |
  | instalador-dados-no (em produção) | 24877e8 | 0e8bd9e |
  | main | bb92378 | 84d43f1 |

  As tags mantêm os nomes; para achar uma versão, use a tag.

## 18/11/2026 — Mais de um nó na mesma VPS e mudança de órgão entre nós (branches instancias-no e mover-orgao)
Pedido do usuário: separar Prefeitura e Câmara, que hoje estão no mesmo nó (72.60.250.36), para demonstrar que cada sistema é autônomo. "Faça as 2 etapas."

**Etapa 1 — instâncias** (um segundo nó na mesma VPS, totalmente separado):
- A instância sai do nome da pasta: `/opt/portal_web` é a de sempre (nada muda nela); `/opt/portal_web-<nome>` é uma instância.
- Cada instância tem os seus:
  - containers, banco e volumes (projeto Docker próprio);
  - apelido do app na rede do proxy (`portal-web-app-<nome>`);
  - trecho do nginx (`portal-comum-<nome>.inc`) e arquivo de rotas (`portal-orgaos-<nome>.conf`/`.yml`); no Traefik, nomes com o prefixo `portal-orgaos-<nome>-`;
  - ativador (`portal-ativador-<nome>`, com estado próprio);
  - backup (`/etc/cron.d/portal-backup-<nome>`, 20 minutos depois do outro, com o volume de arquivos da própria instância).
- Instalador:
  - reconhece a instância e usa o nginx da outra instância como nginx existente;
  - busca só o pacote da instância (`segredos-no@<nome>…`);
  - recusa pacote de outra instância.
- Console: o nó ganhou o campo **instância** (migração 038); a tela "Instalação do nó" mostra os comandos com a pasta e os arquivos da instância; o pacote leva a instância.
- Sem instância, tudo fica como antes (a gestão inclusive): conferido pelo `docker compose config`, que continua dando o apelido `portal-web-app`.

**Etapa 2 — mover órgão entre nós** (`deploy/no/mover_orgao.sh` + `app/mover_orgao.py`):
- `exportar SLUG`, no nó de origem:
  - recusa se o domínio ainda estiver publicado;
  - gera `/root/mover-SLUG-….tgz` (permissão 600) com o banco do órgão, a contagem de cada tabela, a pasta de arquivos, as linhas do banco local do órgão e o manifesto com SHA-256.
- `importar ARQ`, no nó de destino:
  - recusa arquivo adulterado e banco ou pasta que já existam;
  - restaura e **confere tabela por tabela**; se não bater, desfaz;
  - copia os arquivos com o dono do app e importa as linhas do banco local.
- `limpar ARQ`, na origem: recusa enquanto o órgão ainda é do nó; pede a confirmação digitada; guarda cópia do banco em `backups/removido-…`; apaga só esse órgão.
- **Inventário assinado:** a gestão entrega ao nó, junto com as licenças, a lista assinada dos órgãos dele, e o nó apaga do cache a licença de quem saiu.
  - Antes, o nó antigo continuaria servindo o órgão até a licença vencer.
  - Inventário de outro nó, antigo (mais de 15 minutos) ou adulterado não apaga nada; nó antigo ignora o campo.
- Console:
  - mudar a hospedagem com o domínio publicado é recusado ("tire do ar antes");
  - a tela do órgão mostra o roteiro de mudança.
- Roteiro passo a passo para a VPS: `Docs/ROTEIRO-SEPARAR-CAMARA.md`.

**Testes:**
- `teste_instalador_no.sh`: segunda instância ao lado da primeira; nada do primeiro nó é alterado; pacote de outra instância é recusado.
- `teste_ativador.sh`: rotas e trecho próprios; recusa de domínio publicado pelo outro nó.
- `teste_ativacao.py`: nomes e apelido por instância.
- `teste_instalacao.py`: campo instância, comandos e pacote.
- `teste_licenca.py`: inventário (esquece / não esquece) e recusa da hospedagem com domínio no ar.
- Novo `teste_mover_orgao.sh`: ensaio real com **dois PostgreSQL** (um por nó). Cobre exportar, recusas, importar com contagens iguais, arquivos e banco local só da Câmara, esquecer pelo inventário, limpar com cópia e Prefeitura intacta.
- Testes: as 36 suítes passaram contra o código (inclui o ensaio novo `teste_mover_orgao`). **Não implantado:** aguarda aprovação do usuário (e snapshot). Implantação na gestão: migração 038 (coluna nova), imagem reconstruída; o branch `mover-orgao` já contém `instancias-no` e a trava do instalador.
- **Implantado na gestão em 18/11/2026, 18h56 (Brasília)**, com aprovação do usuário ("Aprovo, há snapshot"):
  - mescla `dbc1b78` (instâncias de nó, mover órgão entre nós e a trava do instalador); backup ok às 18h43; versão `instancias-mover-orgao (dbc1b78)`;
  - as 36 suítes passaram contra a imagem nova; migração 038 aplicada (coluna `instancia` nos nós; o nó atual ficou na instância padrão);
  - conferido:
    - gestão 303, portais 200, logins da gestão e dos dois painéis 200;
    - a imagem leva o `mover_orgao.sh`, o instalador com a correção do pacote novo e a trava da gestão;
    - o inventário é assinado e conferido com a chave da gestão;
    - o nó `726025036` buscou as licenças às 18h57, depois da implantação, sem problema (a versão atual dele ignora o inventário);
    - casemaster 200; sem erros nos logs.
- **Próximo (usuário, na VPS do nó):** seguir `Docs/ROTEIRO-SEPARAR-CAMARA.md`, a partir do passo 0 (memória) e do passo 1 (atualizar o nó atual).

## 19/11/2026 — Nó da Câmara instalado por cima do nó da Prefeitura; recuperação
- **O que aconteceu (07h27–07h47):**
  - o nó `726025036.camara.conectatech.tech` foi cadastrado **sem instância**;
  - a hospedagem da Câmara foi trocada para ele antes de mover os dados;
  - o pacote dele foi instalado em `/opt/portal_web` na VPS 72.60.250.36, a pasta do nó da Prefeitura. O instalador gravou o token e o nome do nó novo no `.env` dessa pasta;
  - resultado: a instalação passou a ser o nó 3, que só tinha a licença da Câmara, e **a Prefeitura do nó ficou fora do ar das 07h40 às 08h20**. Os dados não foram afetados: os dois bancos ficaram no mesmo PostgreSQL.
- **Recuperação** (aprovada pelo usuário: "aprovo a recuperação"):
  - gestão: nó 3 marcado com a instância `camara`;
  - VPS do nó (usuário): `.env` do nó 1 restaurado (`.env.anterior-20261119074021`; o do nó 3 foi guardado em `.env.no3-por-engano`) e `docker compose up -d app worker`; o nó 1 voltou às 08h20;
  - gestão: hospedagem da Câmara de volta ao nó 1 às 08h21; Câmara de novo no ar às 08h26.
  - Conferido: pmbora.prefbora.cloud/admin e cmbora.prefbora.cloud (início e /admin) respondem 200; a página inicial da Prefeitura responde 503 como antes (portal em preparação).
- O nó 3 continua cadastrado (instância `camara`), sem instalação. Na VPS ficou `/opt/portal_web/.env.no3-por-engano`, com o token do nó 3: apagar depois.

## 19/11/2026 — A gestão comanda o nó: mudança de órgão e nova instância sem terminal (branch gestao-comanda-no)
Pedido do usuário: "melhore essa parte de exportação/instalação, preferencialmente que tudo seja possibilitado ser realizado pela gestão, e que na gestão ao final fique registrado o repositório do nó; melhore os questionamentos do script para que uma pessoa leiga entenda".

**Instalador mais claro e com trava:**
- **Resumo no começo:** o que o programa faz, a pasta do nó, se é instalação nova ou atualização e como responder ([colchetes], s/N, S/n).
- **Explicações em linguagem simples** em cada etapa (o que é, o que fazer).
- **Trava:** se a pasta já é de **outro nó** (nome do pacote diferente do `.env`), para antes de gravar qualquer coisa e explica as duas saídas: dar uma instância ao nó novo, ou apagar o `.env` para trocar de propósito.
- O `.env` passa a registrar a pasta (`NO_PASTA`). O relatório leva a pasta e a instância, e a gestão as mostra em Nós e licenças, com alerta se a pasta relatada diferir do cadastro.

**Console:**
- Pasta de cada nó e opção "Mudar a pasta (instância)".
- Na tela de instalação: "Onde este nó fica" e aviso quando outro nó já usa a mesma pasta.
- O campo instância ficou explícito no cadastro: "preencha se esta VPS já tem outro nó".

**Tudo pela gestão** (sem terminal, entre nós da mesma VPS):
- Tarefas da gestão: ordem assinada "tarefa" → fila do nó (`tarefas_no`) → **ativador do nó (root)** executa → passos e resultado voltam pelo relatório. Lista fechada de tipos: `exportar`, `importar`, `limpar`, `instalar_instancia`. Parâmetros conferidos na gestão, no nó e no ativador; o arquivo de transferência fica em `/var/lib/portal-transferencias` (só root).
- **Mudar de nó pela gestão** (página do órgão): tirar do ar → exportar → importar e conferir → trocar a hospedagem → esperar a licença no destino → publicar → concluída.
  - Depois: "Apagar da origem" (exige digitar o identificador; guarda cópia do banco) ou "Desfazer" (volta tudo).
  - Erro numa etapa: para, explica e não apaga nada.
  - Avança sozinha (worker da gestão a cada minuto e a cada relatório).
- **Instalar sem terminal** (tela de instalação do nó com instância): o gestor escolhe um nó que já roda na mesma VPS e confirma com senha e 2FA. Esse nó cria a pasta `/opt/portal_web-<instância>`, copia o código, prepara a configuração (mesmas chaves, identidade nova, mesmo proxy) e roda o instalador em **modo automático**.
  - O token novo do nó vai cifrado (CHAVE_CREDENCIAIS) e não aparece em tarefa, tela nem log.

**Testes:**
- Novo `teste_mudancas.py`:
  - mudança completa (retirar, exportar, importar, hospedagem, licença, publicar, limpar);
  - erro e encerrar; desfazer;
  - recusas (outra VPS, sem confirmação, segunda mudança, identificador errado);
  - relatório de outro nó ignorado;
  - fila do nó (recusa de parâmetro malicioso, sem token nos pendentes);
  - instalação sem terminal (senha, 2FA, token novo cifrado).
- `teste_ativador.sh`: tarefas executadas, erro com a explicação do script e parâmetro inválido recusado sem executar.
- `teste_instalador_no.sh`: trava de pasta de outro nó, resumo inicial, `NO_PASTA`, instância criada sem terminal (`.env`, ativador e backup próprios, primeiro nó intacto, sem segredos na saída).
- `teste_instalacao.py`: aviso de pasta em uso, mudar instância, pasta do relatório.
- As 37 suítes passaram contra o código. **Não implantado:** aguarda aprovação do usuário (e snapshot). Implantação na gestão: migração 039 (tabelas novas); os nós recebem a versão nova pelo pacote.
- **Implantado na gestão em 19/11/2026, 08h42 (Brasília)**, com aprovação do usuário ("Aprovo, há snapshot"):
  - mescla `7df35ee`; backup ok às 08h27; versão `gestao-comanda-no (7df35ee)`;
  - as 37 suítes passaram contra a imagem nova; migração 039 aplicada (tabelas `tarefas` e `mudancas`, vazias);
  - conferido:
    - gestão 303, portais 200, logins da gestão e dos painéis 200;
    - portais do nó (pmbora/cmbora.prefbora.cloud) no ar;
    - a imagem leva `criar_instancia.sh`, o instalador com o modo automático e o ativador com as tarefas;
    - o nó 1 buscou as licenças às 08h41;
    - casemaster 200; sem erros nos logs.
- **Próximos passos (usuário):**
  1. atualizar o nó 1 pelo pacote (Preparar instalação, sem token novo; na VPS, na pasta `/opt/portal_web`). Só então ele executa tarefas da gestão;
  2. no console, instalar o nó da Câmara sem terminal (Nós e licenças → nó `…camara` → Preparar instalação → "Instalar sem terminal", escolhendo o nó 1);
  3. página da Câmara → "Mudar de nó pela gestão".

## 19/11/2026 — Nó 72.60.250.36 apagado para refazer do zero (pedido do usuário)
Pedido: "como não tem nada publicado em nenhum dos dois, como apago tudo e refaço do zero da forma correta para testar"; confirmação: "pode apagar os dois nós, sem mexer nas outras aplicações".
- **Gestão (08h55):** backup antes (`backups/plataforma-antes-apagar-nos-20261119-1155.dump`). Removidos, numa transação:
  - os órgãos `prefbora` (pmbora.prefbora.cloud) e `cmb-bora` (cmbora.prefbora.cloud), com contratos, módulos, licenças, convites, ordens e coletas;
  - os nós `726025036.conectatech.tech` e `726025036.camara.conectatech.tech`.
  - Ficaram o piloto (`pm-bora`, `cm-bora`) e o console, conferidos 200 depois.
- **VPS do nó (usuário, 08h56):**
  - backup final em `/root/portal-removido-20261119` (bancos `bd_prefbora`, `bd_cmb_bora`, `no_local`, arquivos e `.env`);
  - ativador e backup automático desligados e removidos; `portal-orgaos.yml` tirado da pasta do Traefik (Dokploy);
  - `docker compose down -v` do projeto `portal_web` (containers, volumes e rede dele), imagens do portal removidas, `/opt/portal_web` apagada.
  - Conferido: nada do portal sobrou; os outros 53 containers da VPS seguem de pé.
- **Próximo:** cadastrar os nós `prefeitura` e `camara` com instância; instalar o primeiro pelo terminal e o segundo sem terminal; cadastrar cada órgão já no seu nó.
- **19/11/2026, 09h35 — segunda limpeza para refazer com instância:** o usuário instalou um nó na pasta padrão (`726025036.pmbora…`, Prefeitura `pm-prefbora`, publicada às 09h27) e decidiu refazer com instância. Ele limpou a VPS com os mesmos comandos; eu removi da gestão o órgão `pm-prefbora` e o nó, com backup antes (`backups/plataforma-antes-apagar-no4-…dump`). Piloto e console conferidos 200.
  - Atenção: o backup final foi copiado para a mesma pasta da primeira limpeza (`/root/portal-removido-20261119`), e o `.env` do nó anterior foi sobrescrito por este. Os dumps dos bancos dos dois têm nomes diferentes e ficaram.

## 19/11/2026 — Exclusão de órgão e de nó pela gestão (branch excluir-pela-gestao)
Pedido do usuário: "conseguimos replicar essa limpeza via gestão, se um dia precisarmos excluir algum, e ter o registro somente do backup" → "Sim, implemente".
- **Excluir órgão** (página do órgão, só para órgão hospedado em nó; o piloto desta VPS fica de fora):
  - confirmação: identificador digitado, senha e 2FA;
  - a gestão tira o domínio do ar e manda a tarefa `excluir_orgao`;
  - o nó faz o **backup final** (banco, contagens, arquivos e banco local) em `/var/backups/portal-removidos/AAAAMMDD-HHMM-orgao-SLUG/` (só root) e **confere o SHA-256**; só então apaga banco, arquivos, linhas do banco local e licença;
  - a gestão apaga o cadastro (licença, contratos, módulos, ordens, convites, coletas, mudanças);
  - se o backup falhar, nada é apagado e a exclusão para com a explicação ("Encerrar" em Remoções).
- **Excluir nó** (Nós e licenças → Excluir nó; só nó sem órgãos):
  - confirmação: nome digitado, senha e 2FA;
  - nó que nunca foi instalado sai só do cadastro;
  - nó instalado (tarefa `desinstalar_no`, `deploy/no/desinstalar.sh`): backup final conferido de todos os bancos, dos arquivos e do `.env` em `/var/backups/portal-removidos/…-no-…/`. Depois, ele agenda (`systemd-run`, 90 s, para avisar a gestão antes) a remoção **só do que é dele**: ativador e backup automático da instância, a rota dele no nginx/Traefik, `docker compose down -v`, imagens do projeto e a pasta. O proxy e os outros sistemas e nós da VPS não são tocados;
  - a gestão apaga o cadastro do nó.
- **Remoções** (console, menu novo): registro permanente de cada exclusão.
  - O que era, nó e VPS, quando e por quem.
  - Pasta do backup com arquivos, tamanhos e SHA-256.
  - Histórico e passos do nó.
  - "Apagar este backup": mostra o `rm -rf` para a VPS e registra quando foi apagado.
- Migração 040 (`remocoes`; novos tipos de tarefa). O ativador repassa o resultado (onde ficou o backup) à gestão.
- A tela Nós e licenças ficou tolerante a relatório sem o campo de falhas de coleta.
- Testes:
  - novo `teste_remocoes.py` (recusas, domínio retirado antes, erro no nó sem apagar nada, encerrar, cadastro apagado com registro, backup marcado como apagado, nó com órgão recusado, nó nunca instalado, nó desinstalado);
  - `teste_mover_orgao.sh` com PostgreSQL real: excluir com domínio no ar recusa; excluir faz backup 600/700 e apaga só o órgão; **o backup final restaura com as mesmas contagens**; desinstalar recusa com órgão; backup final conferido; remoção agendada só com os nomes da instância.
- Suítes: as 38 rodaram. O teste simulado do instalador falhou uma vez na bateria, sem mostrar a verificação, e passou em 10 rodadas seguidas depois. As baterias agora mostram as linhas de falha dele para identificar se repetir. **Não implantado:** aguarda aprovação do usuário (e snapshot). Migração 040; os nós recebem a versão nova pelo pacote.
- **Implantado na gestão em 19/11/2026, 10h35 (Brasília)**, com aprovação do usuário ("Aprovo, há snapshot"):
  - mescla `40abab2`; backup ok às 10h17; versão `excluir-pela-gestao (40abab2)`;
  - **as 38 suítes passaram contra a imagem nova**, incluindo o instalador, desta vez sem falha intermitente;
  - migração 040 aplicada (tabela `remocoes`, vazia);
  - conferido: gestão 303, portais 200, logins 200, `/remocoes` sem login redireciona para o login; a imagem leva `desinstalar.sh`; casemaster 200; sem erros nos logs.
  - Nenhum nó cadastrado no momento: o usuário vai recriar os nós com instância.

## 23/11/2026 — Instalações independentes, paridade e e-SIC/Ouvidoria completos (branch integracao-esic-ouvidoria)
Pedido do usuário: relatório colado "Prefeitura e Câmara em instalações independentes, paridade de serviços, e-SIC e Ouvidoria (23/11/2026)", usado como especificação.
- **Integração entre instalações** (commit `cf4e2c8`):
  - a gestão emite um diretório assinado com as licenças: parceiros do município e os tokens dos pares;
  - o nó só aceita o diretório se for dele, recente e mais novo que o guardado;
  - chamadas entre órgãos: endereço interno na mesma instalação, HTTPS com certificado conferido em outra;
  - `GET /api/integracao/ping`;
  - remessa ao Diário, Prefeitura da Câmara e legislação funcionam entre nós;
  - console: renovar chaves e desligar a integração; painel "Órgãos parceiros" com teste de conversa.
- **Paridade** (commit `3bea815`): Diário Oficial e painel de indicadores opcionais também para a Câmara; finanças (Fiorilli) só no Executivo.
- **e-SIC e Ouvidoria**:
  - migração `041_orgao_atendimento.sql`, idempotente; registros antigos ganham prazo calculado;
  - a 019 passou a ter a lista completa de perfis, porque ela roda de novo a cada atualização;
  - perfis novos: "Ouvidoria / SIC" (vê a identidade, junto com o administrador) e "Autoridade de recurso".
- **Portal:**
  - protocolo + código de acesso (só o hash fica no banco); sem o código, a consulta mostra só a situação;
  - complemento, recurso em 1ª/2ª instância e avaliação;
  - denúncia anônima só na Ouvidoria;
  - páginas novas com "Base legal:": `/e-sic/estatisticas` (CSV/JSON), `/e-sic/informacoes-classificadas` (CSV) e `/ouvidoria/relatorio` (CSV/JSON);
  - a página do e-SIC mostra unidade, autoridades, prazos (inclusive recursal), procedimento e norma local.
- **Painel** (`app/admin_atendimento.py`):
  - filtros, histórico com notas internas, setor;
  - prorrogação única (LAI 20+10; Ouvidoria 30+30); complemento único (20 dias, prazo suspenso);
  - resposta com resultado, fundamento obrigatório para negativa ou acesso parcial, CPF completo recusado;
  - decisão de recurso: quem respondeu não decide; quem decidiu a 1ª não decide a 2ª; autoridade configurável;
  - encaminhamento ao parceiro sem a identidade, com protocolo novo no destino e consulta da situação;
  - registro presencial; configuração com SMTP próprio (senha cifrada) e teste; relatório; informações classificadas.
- **E-mails:**
  - ao cidadão em cada passo; à equipe sem dado pessoal, mais um resumo diário dos prazos;
  - envio pelo SMTP do órgão, senão pelo e-mail da plataforma (só na instalação principal), senão esperam na fila;
  - o texto é apagado da fila depois do envio.
- **Worker:** fila a cada minuto; rotina diária a partir das 7h (encerra complementos vencidos e envia o resumo).
- **PNTP automático:** 12.1, 12.3 e 12.5 a 12.9 medidos pela configuração.
- **Testes:** novo `tests/teste_atendimento.py`, só com dados fictícios, em duas partes:
  - fluxos do e-SIC e da Ouvidoria;
  - dois nós simulados com bancos locais separados: diretório, ping, legislação, remessa, encaminhamento, renovação de chaves, integração desligada, diretório adulterado, de outro nó ou antigo.
- **Finanças da Prefeitura no painel da Câmara** (pedido do usuário: publicar os dados da Prefeitura mesmo com contrato só da Câmara, pelo Siconfi ou pelo portal de dados abertos dela):
  - fonte nova `financas_prefeitura`, só da Câmara, cadastrada em modo automático (`app/coletores/financas_prefeitura.py`), de madrugada, uma vez por dia;
  - modo automático: Prefeitura cliente → API pública nova `/painel/api/financas.json` do painel dela (mesma instalação ou outra); senão o portal de dados abertos (se informado); senão o Siconfi;
  - Siconfi: RREO Anexo 1 (receita, previsão, dotação, empenhado, pago) e Anexo 2 (empenhado por função), série por bimestre; portal (Fiorilli VersaoJson): mês a mês e por unidade orçamentária;
  - nunca lê o banco da Prefeitura e nada vai para as tabelas da transparência da Câmara; o resumo fica na configuração da Câmara (`financas_prefeitura`);
  - o bloco aparece como "Dinheiro público da Prefeitura", com o nome da Prefeitura, "não da Câmara", a fonte, o link, o período e a data da consulta;
  - se a fonte falha, o painel mantém o último dado válido e mostra o aviso da falha;
  - configuração em `/admin/integracoes?fonte=financas_prefeitura` (modo, IBGE, API e entidade do portal, link, nome), com teste sem gravar; endereço só https e domínio público; quadro com a situação em `/admin/indicadores` (aba Coleta);
  - a restrição da tabela `fontes` ganhou `financas_prefeitura` em todas as migrações que a refazem (009, 011, 014, 016, 024, 033 e a local 004);
  - conferido sem gravar contra as fontes públicas reais de Borá: Siconfi (5º bimestre de 2026, 12 funções) e portal Fiorilli (totais iguais aos do banco da Prefeitura);
  - teste novo `tests/teste_financas_prefeitura.py` (dados fictícios, sem internet).
- **Não implantado:** aguarda aprovação do usuário ("Aprovo, há snapshot"). Migração 041.
