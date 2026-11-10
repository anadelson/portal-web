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
