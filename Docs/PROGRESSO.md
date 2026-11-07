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

## Onde parou
Código pronto. Aguardando aprovação de: build → testes em banco isolado → implantação + coleta.
