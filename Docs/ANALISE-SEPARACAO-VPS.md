# Análise: gestão numa VPS, portais e painéis em outra (11/11/2026)

Pedido: manter a **gestão** (`gestao.conectatech.tech`) na VPS atual, levar os **portais e painéis administrativos** dos órgãos para uma VPS nova e amarrar os portais à gestão, com controle de licença (o que está ou não contratado).

---

## 1. Como está hoje

- **Um só app** (FastAPI) atende tudo, escolhendo pelo domínio:
  - console do gestor (`gestao.`);
  - portal e painel de cada órgão (`pmbora.`, `pmbora./admin`, `cmbora.`…).
- Há **um worker** (coletas e a rotina do Diário).
- Há **um PostgreSQL**, com o banco de controle `plataforma` e um banco por órgão (`bd_pm_bora`, `bd_cm_bora`).
- **Portal, painel e worker leem o banco de controle o tempo todo:**

  | Tabela do controle | Para quê |
  |---|---|
  | `orgaos` | descobrir qual órgão é aquele domínio |
  | `contratos`, `orgao_modulos` | o que está contratado (`modulos_do_orgao`) e a fase do contrato (ativa, carência, suspensa) |
  | `fontes`, `coletas`, `consulta_*`, `fontes_historico` | integrações, agenda, testes e histórico |
  | `credenciais_fontes` | chaves do YouTube, Meta e IEG-M (cifradas) |
  | `dados_publicos`, `indicadores_publicos` | dados de IBGE, INEP, CNES e outros |
  | `pares_orgaos`, `remessas_log` | remessas da Câmara para o Diário da Prefeitura |
  | `login_tentativas`, `config_console` | bloqueio de login; tela de login |

- **O console escreve direto nos bancos dos órgãos:**
  - cria o banco no cadastro;
  - cria o administrador inicial;
  - monta o layout da página inicial.
- O **nginx é do projeto hotspot**, e o ativador (timer) publica os domínios dos órgãos nesse nginx.
- **Tamanho:** os bancos somam cerca de 45 MB e os arquivos cerca de 1 MB, então a cópia dos dados leva minutos.
- **VPS atual:** 1 vCPU, 4 GB de RAM e 48 GB de disco (73% em uso), dividida com o hotspot e outros sistemas.

**Conclusão:** não dá para só mudar os containers de máquina. Os portais passariam a depender do banco da gestão pela rede, e uma queda da gestão derrubaria todos os portais. É preciso uma etapa de código antes da mudança.

---

## 2. Arquitetura proposta

```
VPS ATUAL — GESTÃO                                 VPS NOVA — PORTAIS ("nó")
┌──────────────────────────────┐                    ┌──────────────────────────────────────┐
│ console gestao.conectatech    │                    │ portais e painéis de todos os órgãos │
│ banco de controle:            │   ◄── HTTPS ───    │ worker (coletas, Diário)             │
│  cadastro, contratos, módulos,│   o nó PUXA:       │ bancos dos órgãos                    │
│  gestores, log, fila de ordens│   • licenças       │ banco local do nó: fontes, coletas,  │
│ emissor de licenças           │   • ordens         │  credenciais recebidas, dados        │
│  (chave privada Ed25519)      │   e ENVIA:         │  públicos, remessas, cache das       │
│                               │   • relatório      │  licenças                            │
└──────────────────────────────┘                    │ nginx + certbot próprios, ativador   │
                                                    │ certificado de assinatura do Diário  │
                                                    └──────────────────────────────────────┘
```

**A amarração é sempre o nó chamando a gestão.** A gestão não acessa o banco do nó, e o nó não abre porta para comandos de fora. Os três canais:

1. **Licenças assinadas** (a cada 5 min). Um documento por órgão com:
   - domínio, tipo e plano;
   - módulos contratados;
   - contrato: início, fim, carência e suspensão;
   - "válida até".

   A gestão assina com uma chave privada que só ela tem. O nó confere com a chave pública e guarda em cache, e o `modulos_do_orgao` passa a ler esse cache. Mexer no banco do nó não "contrata" módulo, porque a assinatura não confere.
2. **Ordens.** É uma fila com uma lista fechada de ações, no mesmo padrão do ativador que já está no ar:
   - criar órgão;
   - publicar ou tirar domínio;
   - redefinir o administrador;
   - aplicar o layout;
   - atualizar fontes e credenciais.

   O nó executa e devolve o resultado, e o console mostra os passos como já faz hoje com a ativação de domínio.
3. **Relatório do nó** (a cada 5 min): versão, saúde, últimas coletas por órgão e espaço em disco. O console passa a mostrar "nó sem contato há X min".

**Se a gestão cair:**
- os portais continuam funcionando com a última licença válida;
- a licença vale **15 dias** sem contato (sugestão);
- depois disso o órgão entra no comportamento de **carência**, que já existe no código: só ficam os módulos obrigatórios. **Transparência e LAI nunca saem do ar.**

Suspensão e encerramento continuam sendo decididos no console e chegam ao nó pela licença.

**LGPD:** os dados pessoais (cidadãos, solicitantes, servidores) ficam só no nó. Entre as duas VPS trafegam apenas licenças, ordens e o relatório técnico.

---

## 3. Controle de licença: o que já existe e o que muda

- **Já existe:**
  - contratos com vigência, carência e suspensão;
  - catálogo de módulos (obrigatório, do plano, opcional);
  - `orgao_modulos.contratado`;
  - `modulos_do_orgao`, que respeita a fase do contrato.
- **Muda:**
  - a gestão vira a **única fonte da verdade**, e o nó só lê a licença assinada;
  - o console ganha "licença entregue em…", "nó sem contato há…" e "reenviar agora";
  - o painel do órgão (Funcionalidades) mostra contratado ou não contratado e a data da licença.
- **Opcional:** limite de órgãos por nó, se você quiser vender ou hospedar por nó no futuro.

---

## 4. Etapas

### Etapa A: código (sem mexer em infraestrutura)
- Configuração nova `PAPEL = tudo | gestao | no`. Com `tudo`, o padrão, tudo funciona **exatamente como hoje**.
- **A1:** emissor e verificador de licença (Ed25519), API `/api/no/licencas` na gestão e cache no nó. `modulos_do_orgao` e o roteamento por domínio passam a ler o cache.
- **A2:** "banco local do nó", com as tabelas operacionais que hoje estão no controle (fontes, coletas, consultas, credenciais, dados públicos, remessas, tentativas de login). Uma migração copia os dados.
- **A3:** fila de ordens com o agente do nó. O console deixa de escrever direto nos bancos dos órgãos e passa a enfileirar ordens.
- **A4:** relatório do nó e as telas novas do console.
- **Testes:**
  - todas as suítes;
  - teste novo de gestão fora do ar: o portal segue com a licença em cache e, depois da validade, entra em carência sem derrubar a transparência;
  - teste de licença adulterada, que deve ser recusada.
- **Implantação na VPS atual em `PAPEL=tudo`:** nada muda para os portais, e eu confiro com a comparação das 12 páginas do piloto.

### Etapa B: VPS nova
- Plano sugerido: 2 vCPU, 4 GB de RAM, 40 a 80 GB de SSD, Ubuntu LTS, mesma região da atual, com snapshot do provedor.
- Docker, firewall (80 e 443 abertos; SSH restrito), nginx e certbot próprios (sem depender do hotspot) e o ativador.
- Segredos copiados **por você**, nunca pelo chat nem pelo git:
  - `.env`;
  - chave do nó;
  - certificado de assinatura do Diário.
- Backup diário com cópia fora da VPS.

### Etapa C: ensaio na VPS nova
- Cópia dos bancos e arquivos, com domínios de teste (ex.: `teste-pmbora.conectatech.tech`).
- Conferir:
  - as 12 páginas do piloto;
  - o Diário (assinatura);
  - o login com 2FA;
  - as coletas;
  - a licença chegando da gestão;
  - o comportamento com a gestão desligada.

### Etapa D: virada (janela de cerca de 30 min, longe do horário do Diário, 16h às 17h)
1. Baixar o TTL do DNS de `pmbora` e `cmbora` para 300 s, 24 h antes.
2. Snapshot das duas VPS.
3. Painel dos órgãos em modo manutenção (o portal público segue no ar).
4. Cópia final dos bancos e arquivos para a VPS nova.
5. Copiar os certificados atuais desses domínios para a VPS nova, sem janela de emissão. As renovações passam a ser lá.
6. Trocar os registros A de `pmbora` e `cmbora` para o IP novo.
7. Durante a propagação, o nginx da VPS antiga encaminha esses domínios para a nova, então ninguém cai.
8. Conferir e tirar a manutenção.

### Etapa E: depois
- Por 7 dias a cópia antiga fica parada, mas guardada. Para voltar atrás, basta voltar o DNS.
- Depois, apagar os bancos dos órgãos da VPS antiga (com a sua confirmação). O ativador e o timer saem da VPS antiga, e lá fica só a gestão.

**Volta atrás em cada etapa:**
- A: voltar a tag anterior.
- B e C: nada no ar foi tocado.
- D: voltar os registros A e reabrir o painel antigo.

---

## 5. Riscos e cuidados

- **Diário Oficial:** não virar perto das 16h às 17h; o certificado de assinatura precisa estar na VPS nova antes da virada.
- **2FA dos administradores:** vai junto, no banco do órgão; ninguém precisa recadastrar.
- **Sessões:** com a mesma `SECRET_KEY` no nó, quem está logado continua logado; com uma chave nova, todos entram de novo, o que é mais seguro.
- **Credenciais (YouTube, Meta, IEG-M):** saem da gestão já cifradas para a chave do nó. Ninguém as vê, nem eu.
- **Relógio:** as duas VPS precisam de NTP, porque a licença tem validade.
- **Custo:** uma VPS a mais. Em troca, a gestão fica isolada dos portais, e um pico de acesso num portal não afeta o console.

---

## 6. Decisões para você

**Este plano muda três "decisões já tomadas" do `Docs/CLAUDE.md`**, que só mudam com a sua confirmação:
- **Um servidor PostgreSQL:** passam a ser dois, o de controle na gestão e o dos órgãos no nó. Continua um banco por órgão.
- **Proxy e SSL pelo nginx do hotspot:** na VPS nova, os portais usam nginx e certbot próprios. Na atual, a gestão segue no nginx do hotspot.
- **Capacidade no plano atual:** entra uma VPS a mais.

1. Plano e região da VPS nova.
2. Validade da licença sem contato com a gestão (sugestão: 15 dias) e o que acontece depois (sugestão: carência, só módulos obrigatórios).
3. Nome do nó (ex.: `no1.conectatech.tech`), útil para o relatório e para futuros nós.
4. Janela da virada (sugestão: noite ou fim de semana).
5. Confirmação de que você mesmo copia os segredos para a VPS nova.

**Esforço estimado:**
- Etapa A é a maior: algumas sessões de trabalho, com testes.
- Etapas B a E: uma sessão de preparação e a janela de virada.
