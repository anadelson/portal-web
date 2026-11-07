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

## Transparência com dados reais (Fase 4)
- **Fontes por órgão** na tabela `fontes` (banco `plataforma`): Fiorilli (endereço da API, entidade, bases), PNCP (IBGE, CNPJ), Siconfi (IBGE, RREO, poder do RGF), TCESP (município, anos). `provision atualizar` cadastra os valores padrão; nada fixo no código.
- **Coletores** em `app/coletores/` (`fiorilli`, `pncp`, `siconfi`, `tcesp`, `numeros`, `comum`): 1 requisição/s por fonte, timeout, novas tentativas, upsert por chave natural, registro em `coletas`. Falha de uma fonte não apaga dados: o portal mostra a última coleta válida e avisa.
- **Agenda do worker**: Fiorilli de hora em hora (7h–19h), PNCP a cada 6 h, Siconfi diária, TCESP no dia 20. Manual: `docker compose exec app python -m app.worker uma-vez [fiorilli pncp siconfi tcesp]`.
- **Telas**: `/transparencia` (central), `/transparencia/<base>` com filtros (ano, mês, unidade, credor, texto), paginação, totais, fonte, data e base legal; `/transparencia/<base>.csv|.json`; API `/dados/<base>.json`; documentação em `/dados-abertos`.
  Bases: receitas, despesas, empenhos, licitacoes, contratos, servidores, diarias, transferencias, ordem-cronologica, restos-a-pagar, relatorios-fiscais.
- **Emendas (Câmara)**: cadastro `CadEmendasImpositivas` (pago no cadastro) + execução pelos empenhos com vínculo "Emenda Ver." (empenhado, liquidado, pago e datas), lidos da API pública da Prefeitura, com conferência automática.
- **LGPD**: nenhuma coluna de CPF; dígitos de CPF retirados de nomes; pessoa física sem documento e fora da ordem cronológica e dos restos a pagar; servidores só com nome (ou nome social), cargo, vínculo, lotação, admissão e remuneração bruta.
- **Descoberta das fontes** (só leitura): `docker compose exec -T app python - < app/coletores/descoberta.py` grava amostras sem CPF em `/srv/dados/amostras` (usadas pelos testes offline).

## Câmara completa (Fase 5)
- **Painel da Câmara** (`app/admin_leg.py`): Sessões e votações (pauta → presença → votação nominal → ata → publicação separada), Proposições (tipos, numeração automática, autores, relator, tramitação, PDFs), Comissões (membros, pautas, pareceres), Legislaturas e Mesas, Contas do Prefeito (parecer TCESP, 2/3, decreto), Diárias e verbas, Transmissões (iniciar/encerrar a faixa ao vivo), Participação (Tribuna Livre, opiniões moderadas, avaliação por página), Importar dados antigos (CSV), Autoavaliação PNTP 20.1–20.11.
- **Regras** (`app/legislativo.py`): quórum simples, absoluto ou 2/3; Presidente só desempata na maioria simples; resultado atualiza a tramitação; perfil do vereador soma só sessões publicadas; votos, presenças e atas nunca são pré-preenchidos.
- **Portal** (`app/portal_leg.py`): `/proposicoes`, `/proposicoes/<id>`, `/sessoes/<id>`, `/comissoes`, `/contas`, `/transmissoes`, `/transparencia/diarias-camara`, `/documento/<arquivo>.pdf`, `POST /avaliar`.
- **Importação** (`app/importar.py`, modelos em `Docs/modelos/`): `docker compose exec app python -m app.importar MODELO arquivo.csv --orgao cm-bora` (simula) e `--gravar`. Nada de raspagem do portal antigo.
- **Transmissões** para a Prefeitura: módulo opcional `audiencias` (ligar no console).

## Diário assinado, remessa da Câmara e acesso seguro (Fase 6)
Hoje em **MODO TESTE** (`DIARIO_MODO=teste`): certificados e ACT de teste, marca “SEM VALOR OFICIAL — TESTE”, nada publicado como oficial e rotina automática desligada (`DIARIO_AUTOMATICO_TESTE=0`).

**Segredos** ficam em `/opt/portal_web/segredos/` (pasta 700, arquivos 600, dono uid 1001 = usuário do container), montada **só leitura** em `/srv/segredos`; nunca no git (`.gitignore`) nem no chat. Senhas ficam só no `.env` (600).
```
segredos/a1/      certificados A1 (.p12/.pfx) dos signatários com assinatura no servidor
segredos/icp/     AC Raiz ICP-Brasil (.crt) baixadas do site do ITI (cadeia de confiança da validação)
segredos/act/     certificado de cliente da ACT, se o contrato exigir
segredos/teste/   cadeia de TESTE (python -m app.assinatura gerar-teste)
```

### Sair do modo teste — passo a passo
1. **Certificado A1 do responsável** (e de quem mais assinar no servidor): copiar o `.p12` para `segredos/a1/` (`chown 1001:1001`, `chmod 600`) e pôr a senha no `.env` numa variável própria (ex.: `A1_SENHA_RESPONSAVEL=`). Em **Painel → Diário → Signatários e calendário**, designar cada etapa (Executivo, Legislativo, final) com o **ato de designação**, o provedor (A1, nuvem ou A3/token), o nome do arquivo e o **nome** da variável da senha. Signatários com token (A3) assinam baixando o PDF e enviando de volta pelo painel.
2. **AC Raiz ICP-Brasil**: baixar do ITI os certificados das AC Raiz em uso e salvar em `segredos/icp/`.
3. **ACT (carimbo do tempo)**: com o contrato (Serpro, Prodesp ou outra ACT credenciada), preencher `ACT_URL` e, se houver, `ACT_USUARIO`/`ACT_SENHA` no `.env`. Se a ACT exigir certificado de cliente, a integração precisa ser concluída com a documentação dela.
4. **Certificado em nuvem** (opcional): quando o provedor fornecer API (ex.: CSC), credenciais e fluxo de autorização, implementar o adaptador em `app/assinatura.py` (`ProvedorNuvem`).
5. Trocar `DIARIO_MODO=oficial` no `.env`, apagar as edições de teste (`docker compose exec app python -m app.diario_servico limpar-teste`), reiniciar (`docker compose up -d app worker`) e assinar uma edição real; conferir em https://validar.iti.gov.br/.
6. **Login gov.br**: o órgão solicita a integração ao Login Único informando as URLs de retorno `https://pmbora.conectatech.tech/admin/govbr/retorno`, `https://cmbora.conectatech.tech/admin/govbr/retorno` e `https://gestao.conectatech.tech/govbr/retorno`. Com o `client_id`/`client_secret` recebidos, preencher `GOVBR_CLIENT_ID`, `GOVBR_CLIENT_SECRET`, `GOVBR_AMBIENTE` (staging → producao) e reiniciar. Cada usuário tem o CPF vinculado em **Usuários e perfis** (guardado só como HMAC + 2 últimos dígitos). Nível mínimo: `GOVBR_NIVEL_MINIMO=prata`.

### Acesso
Senha + **segundo fator (aplicativo autenticador)** obrigatório nos painéis e no console, com 10 códigos de recuperação de uso único; 5 erros bloqueiam a conta por 15 min (e a origem, se insistir); sessão expira após 30 min sem uso; o administrador do órgão pode “Refazer 2º fator” e “Desbloquear” em Usuários e perfis. **Não troque `TOTP_CHAVE` depois que as pessoas cadastrarem o autenticador** (os segredos ficam ilegíveis e todos teriam de refazer o cadastro).

## Painel de indicadores (Fase 7, módulo opcional "bi")
- Público:
  - `/painel` (abas Tudo, Dinheiro público, Contratações, Saúde, Educação, Assistência social, Município e gestão);
  - `/painel/<indicador>` (gráfico SVG gerado no servidor com tabela equivalente);
  - downloads `/painel/baixar/<indicador|painel>.csv|json|ods`;
  - API `/painel/api/indicadores.json` e `/painel/api/<indicador>.json`.
- Administração: `/admin/indicadores` (catálogo, meta com base legal, destaque na página inicial, lançamento manual com motivo e auditoria, "Coletar agora").
- Fontes por órgão do Executivo, criadas pelo `provision atualizar`:
  - `painel`, `ibge` e `cnes`, ligadas;
  - `mds` e `pni`, desligadas.
  - O worker só coleta se o módulo "bi" estiver contratado e ligado.
  - Dados nacionais ficam em `indicadores_publicos` (banco de controle) pelo código IBGE.
- Sem o módulo, `/painel`, os downloads, a API, a tela administrativa e o bloco da página inicial saem do ar (o bloco volta ao conteúdo da Fase 4).
- Regras: nenhum número estimado pelo portal. Contagens de pessoas abaixo de 5 aparecem como "menos de 5", inclusive nos downloads. Se a fonte falhar, fica no ar o último valor válido com o aviso "dado de <data>".
- IDEB e Saeb vêm das planilhas oficiais do INEP (fonte `inep`): `deploy/certs/` guarda o certificado intermediário público que o servidor do INEP não envia (vence em 19/11/2030; aviso no admin 60 dias antes; ver `deploy/certs/LEIAME.md`).
- IEG-M do TCESP (fonte `iegm`): preencha `IEGM_USUARIO` e `IEGM_SENHA` **só no `.env` da VPS** (acesso anônimo publicado pelo Tribunal; uso autorizado pelo órgão) e ligue o modo automático em `/admin/indicadores` → IEG-M. Consulta sem documentação oficial: se mudar, a coleta falha com aviso e o último valor fica no ar; o lançamento manual é a reserva.
- Ligar o MDS quando a fonte voltar: confirme os nomes dos campos (parâmetro `campos` da fonte `mds`) e ative a fonte no console.

## Testes (só em banco de teste)
`tests/teste_fluxos.py` (fluxos e identidade visual), `tests/teste_diario_seguranca.py` (Diário assinado em modo teste, remessa, 2º fator, bloqueio, gov.br simulado; `DATA_SIMULADA=2026-11-06T10:00`, `SEGREDOS_DIR` temporário), `tests/teste_legislativo.py` (processo legislativo com legislatura e pessoas fictícias, `DATA_SIMULADA=2029-03-10`) , `tests/teste_transparencia.py` (coletores com as amostras, sem internet; LGPD; filtros; CSV/JSON; falha de fonte) `tests/teste_painel.py` (painel de indicadores com respostas gravadas das fontes; `DATA_SIMULADA=2026-11-06T10:00`) e `tests/teste_painel_fontes.py` (INEP e IEG-M com respostas gravadas) recusam rodar sem `TESTE=1` e com `PG_HOST=db`. Rode num PostgreSQL descartável (comando completo em `Docs/PROGRESSO.md`, Fase 3).

## O que é real e o que é exemplo
- **Real**: vereadores, partidos, votos e Mesas da 13ª à 15ª legislatura; 29 emendas impositivas com a execução de 3 delas; indicações de 2026 e parte de 2025; sessões com data; RGF/despesa com pessoal da Câmara; endereços e contatos.
- **Exemplo (marcado “exemplo”)**: conteúdos da Prefeitura. Fotos oficiais, biografias, atas e presenças não vêm preenchidas.

## Próximas fases (não incluídas no piloto)
- Login gov.br + segundo fator (hoje: e-mail e senha forte).
- Assinatura ICP-Brasil e carimbo do tempo no Diário.
- Remessa de atos da Câmara para o caderno Legislativo do Diário via API entre órgãos.
- Coletores ainda não feitos: CNES, IBGE SIDRA/Cidades, IEG-M, MDS, vacinação, YouTube (ao vivo).
- Tema próprio (nível 3) sob demanda; editor de layout com arrastar e soltar.
