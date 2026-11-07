# Portais de Borá — piloto (Prefeitura, Câmara e console do gestor)

**Um código só para todos os órgãos.** Prefeitura e Câmara são o mesmo sistema rodando para dois órgãos;
o que os separa é a configuração e o **banco próprio de cada um**. O console do gestor fica no mesmo código,
servido pelo domínio de gestão. Correções e mudanças de lei valem para todos de uma vez.

| Endereço | O que abre |
|---|---|
| `https://gestao.conectatech.tech` | Console do gestor: órgãos, licenças, módulos contratados, layout, coletas |
| `https://pmbora.conectatech.tech` | Portal da Prefeitura de Borá |
| `https://pmbora.conectatech.tech/admin` | Painel administrativo da Prefeitura |
| `https://cmbora.conectatech.tech` | Portal da Câmara Municipal de Borá |
| `https://cmbora.conectatech.tech/admin` | Painel administrativo da Câmara |

## Como funciona
- **Roteamento por domínio** (`app/web.py`): o mesmo aplicativo olha o domínio da requisição e decide se é console, portal ou painel `/admin` — e de qual órgão.
- **Bancos**: `plataforma` (controle: órgãos, contratos, catálogo de módulos, coletas, dados públicos compartilhados) + **um banco por órgão** (`bd_pm_bora`, `bd_cm_bora`), todos no mesmo PostgreSQL.
- **Módulos**: obrigatórios por lei sempre ligados; os do plano o órgão liga/desliga; os opcionais dependem do contrato (console). Licença vencida ou suspensa → só o obrigatório fica no ar.
- **Período eleitoral**: todo conteúdo tem classificação eleitoral; no defeso, publicidade, menção a agente e marca de gestão saem do portal sozinhos (Lei 9.504/1997, art. 73, VI, b).
- **Diário Oficial**: Lei 910/2026 e decreto de 25/03/2026 (cadernos Executivo/Legislativo, edição extra com letra, edição “sem atos”, PDF com código de verificação e SHA-256). **Assinatura ICP-Brasil + carimbo do tempo ficam pendentes** até contratar certificado e ACT (`app/diario.py → assinar_edicao`).

## Estrutura
```
docker-compose.yml   Caddy (SSL automático), app, worker (coletas), PostgreSQL
deploy/Caddyfile     os 3 domínios -> app
deploy/backup.sh     backup diário por banco
app/main.py          aplicação (FastAPI)
app/web.py           roteamento por domínio, sessão, permissões
app/portal.py        portais públicos
app/admin.py         painel /admin de cada órgão
app/console.py       console do gestor
app/diario.py        PDF do Diário Oficial e ponto de assinatura ICP
app/provision.py     cria bancos, esquema e dados iniciais
app/migrations/      SQL da plataforma e do órgão
app/seeds/           dados reais da Câmara (portal da Câmara e Fiorilli, 05–06/11/2026)
app/coletores/       Fiorilli e Siconfi (rodados pelo worker)
tests/               teste de ponta a ponta (usar só em banco de teste)
```

## Instalação na VPS (em /opt/portal_web)
1. DNS: registros **A** de `gestao`, `pmbora` e `cmbora` (em `conectatech.tech`) apontando para o IP da VPS.
2. Portas 80 e 443 livres e liberadas no firewall.
3. Docker e Docker Compose instalados.
4. Copie esta pasta para `/opt/portal_web` e crie o `.env`:
   ```bash
   cd /opt/portal_web && cp .env.example .env
   # troque PG_PASSWORD, SECRET_KEY (openssl rand -hex 32), SENHA_INICIAL_*, EMAIL_SSL
   chmod 600 .env
   ```
5. Suba e provisione:
   ```bash
   docker compose up -d --build
   docker compose exec app python -m app.provision init
   ```
6. Acesse:
   - console: `gestor@gestao.conectatech.tech` + `SENHA_INICIAL_GESTOR`
   - Prefeitura: `admin@pmbora.conectatech.tech` + `SENHA_INICIAL_ADMIN`
   - Câmara: `admin@cmbora.conectatech.tech` + `SENHA_INICIAL_ADMIN`
   Todos trocam a senha no primeiro acesso.
7. Backup: `crontab -e` → `0 2 * * * /opt/portal_web/deploy/backup.sh >> /opt/portal_web/backups/backup.log 2>&1`

Comandos úteis: `docker compose logs -f app`, `docker compose logs -f worker`, `docker compose exec app python -m app.worker uma-vez`.

## Atualizar uma instalação existente (Fase 3 em diante)
```bash
cd /opt/portal_web && ./deploy/backup.sh && docker compose build app worker && docker compose up -d app worker
docker compose exec app python -m app.provision atualizar   # migrações idempotentes + blocos/identidade novos, sem apagar nada
```
Na VPS o HTTPS fica no nginx existente (não no Caddy): ver `Docs/PROGRESSO.md`.

## Identidade visual (Fase 3)
- Tema base em `app/templates/portal/base.html` + `app/static/portal.css` (Public Sans, cores do órgão a partir da identidade, foco amarelo, alto contraste, rodapé em 4 faixas).
- Fotos do tema em `app/static/img` (originais); as `.webp` otimizadas são geradas no build (`python -m app.imagens otimizar`).
- Blocos da página inicial em `app/catalogo.py` (`BLOCOS`, `LAYOUT_PADRAO`); o editor de regiões do console e a página inicial do /admin leem o mesmo catálogo.
- `/admin/identidade`: textos, cores, redes e imagens (brasão, destaque, sede, mosaico) — PNG/JPG/WEBP até 3 MB, texto alternativo obrigatório, guardadas em `/srv/dados/<órgão>/midia` e servidas em `/midia/<arquivo>`.
- `/admin/vereadores` (Câmara): perfil e foto oficial. Sem foto oficial, o portal mostra as iniciais.

## Testes (só em banco de teste)
`tests/teste_fluxos.py` recusa rodar sem `TESTE=1` e com `PG_HOST=db`. Rode num PostgreSQL descartável (comando completo em `Docs/PROGRESSO.md`, Fase 3).

## O que é real e o que é exemplo
- **Real**: vereadores, partidos, votos e Mesas da 13ª à 15ª legislatura; 29 emendas impositivas com a execução de 3 delas; indicações de 2026 e parte de 2025; sessões com data; RGF/despesa com pessoal da Câmara; endereços e contatos.
- **Exemplo (marcado “exemplo”)**: conteúdos da Prefeitura. Fotos oficiais, biografias, atas e presenças não vêm preenchidas.

## Próximas fases (não incluídas no piloto)
- Login gov.br + segundo fator (hoje: e-mail e senha forte).
- Assinatura ICP-Brasil e carimbo do tempo no Diário.
- Remessa de atos da Câmara para o caderno Legislativo do Diário via API entre órgãos.
- Validar a listagem do Fiorilli para emendas e mapear para a tabela `emendas`; demais coletores (PNCP, IBGE, TCESP, despesas, pessoal).
- Telas próprias de transparência (hoje o portal aponta para as fontes oficiais), dados abertos em CSV/JSON.
- Tema próprio (nível 3) sob demanda; editor de layout com arrastar e soltar.
