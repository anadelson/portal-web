# Prefeitura e Câmara em instalações independentes, paridade de serviços, e-SIC e Ouvidoria (23/11/2026)

Pedido: permitir instalar os portais da Prefeitura e da Câmara de forma **independente** (cada um com a própria
instalação na VPS), com **os mesmos serviços** disponíveis para os dois, mantendo a **conversa entre os portais** como
se estivessem juntos; e analisar a legislação para oferecer **e-SIC** e **Ouvidoria** completos nos dois órgãos (ou em
outro órgão), com pedido pelo portal, acompanhamento do protocolo pelo cidadão, tratamento pelo órgão e **notificação
por e-mail**.

Branch: `integracao-esic-ouvidoria`. Nada foi aplicado na VPS.

---

## 1. Como estava

**Instalação.** O código já permitia um "nó" por instalação (`PAPEL=no`, `INSTANCIA=camara`, pasta
`/opt/portal_web-camara`, banco e containers próprios) e já trazia o roteiro para mover a Câmara para outro nó
(`Docs/ROTEIRO-SEPARAR-CAMARA.md`). A separação física, portanto, estava resolvida.

**O que quebrava ao separar.** Toda a conversa entre os órgãos supunha os dois no MESMO nó:

| Ponto | Problema com Câmara e Prefeitura em nós diferentes |
|---|---|
| `orgaos.todos()` no nó | Só conhece os órgãos das próprias licenças: o nó da Câmara não "via" a Prefeitura. |
| `remessa.configurar_pares()` | Cada nó gerava o token do par sozinho: os dois lados nunca tinham o mesmo token. |
| `remessa.chamar()` | Chamava sempre `INTERNO_BASE` (127.0.0.1) com o Host do outro órgão: só funciona no mesmo processo. |
| `portal_fase8._leg_prefeitura` | Legislação municipal lida pelo endereço interno: falhava em outro nó. |
| `web.vizinhos()` | Links "Câmara ↔ Prefeitura" no topo e no rodapé sumiam. |

Resultado: remessa ao Diário, legislação na Câmara e links entre os portais paravam ao separar.

**e-SIC e Ouvidoria.** Formulário único, protocolo de 6 caracteres que mostrava a resposta a quem soubesse o número,
prazo calculado na tela, prorrogação sem limite de vezes, situação "recurso" sem fluxo, nenhum e-mail ao cidadão,
nenhum relatório estatístico (a autoavaliação PNTP marcava 12.6 e 12.7 como pendentes) e a identificação do
solicitante visível a qualquer perfil com acesso ao atendimento.

---

## 2. Integração entre instalações (o que mudou)

A **gestão** passou a ser a fonte da verdade das ligações entre órgãos, do mesmo jeito que já era das licenças:

```
GESTÃO (console)                         NÓ A (Prefeitura)                 NÓ B (Câmara)
pares_orgaos: 1 token por sentido   ──►  licenças + DIRETÓRIO assinado ──► licenças + DIRETÓRIO assinado
para cada par do mesmo município         (Câmara está no nó B,             (Prefeitura está no nó A,
                                          tokens dos pares da PM)           tokens dos pares da CM)
                                                   │   HTTPS + HMAC (5 min)    │
                                                   └──────────────────────────┘
```

- `app/integracao.py` (novo):
  - `garantir_pares()` cria os pares de todos os órgãos do mesmo código IBGE.
  - `diretorio_para(no)` monta o diretório que vai junto com as licenças (`/api/no/licencas`). É **assinado com a mesma
    chave Ed25519 das licenças** e leva só nome, tipo, domínio, serviços e hospedagem dos parceiros, mais os tokens
    dos pares que envolvem os órgãos **daquele** nó. Não leva banco nem dado pessoal.
  - `guardar_diretorio()` (nó): confere a assinatura, se é para este nó (`NO_NOME`) e se é recente (15 min). Grava
    `orgaos_parceiros` (migração `migrations_local/006_local_diretorio.sql`) e os tokens.
  - `chamar()`: com o parceiro **na mesma instalação**, usa o endereço interno, como antes; **em outra**, chama o
    domínio público dele em HTTPS, com o certificado conferido. A assinatura HMAC, a janela de 5 minutos e o registro
    em `remessas_log` valem para os dois casos.
  - `GET /api/integracao/ping`: teste de conversa, assinado.
- `remessa.py` passou a usar esse módulo. Com isso, a remessa ao Diário funciona entre nós.
- `orgaos.executivo_do`, `web.vizinhos` e a legislação da Câmara enxergam o parceiro de outra instalação.
- **Console → órgão → "Integração com os órgãos do município"**: lista os parceiros, onde cada um está, e permite
  renovar as chaves ou desligar a integração. Os nós recebem a mudança em até 5 minutos.
- **Painel → Administração → "Órgãos parceiros"**: mostra cada parceiro (mesma instalação ou outra), os serviços dele,
  se a integração está ativa, o botão **Testar conversa** e as últimas mensagens trocadas.
- **Compatibilidade:** gestão antiga não manda diretório e nó antigo ignora o campo. Enquanto o nó não recebe um
  diretório, segue com os pares que já tinha.

**Para instalar separado:** siga `Docs/ROTEIRO-SEPARAR-CAMARA.md` (nada mudou nele). Depois do passo 9, abra
**Órgãos parceiros** nos dois painéis e clique em **Testar conversa**.

---

## 3. Paridade de serviços Prefeitura × Câmara

| Serviço | Antes | Agora |
|---|---|---|
| Transparência, e-SIC, Ouvidoria, Dados abertos, Licitações, Carta de Serviços | os dois | os dois (e-SIC e Ouvidoria refeitos, ver seção 5) |
| Notícias, Página em blocos, Período eleitoral, Tema próprio | os dois | os dois |
| **Diário Oficial eletrônico** | só Prefeitura | **os dois** (opcional). A Câmara pode ter Diário próprio, instituído por resolução; a rotina do worker, o menu, o bloco da página inicial e a limpeza do modo teste valem para qualquer órgão com o módulo. Sem Diário próprio, a Câmara segue enviando atos ao caderno Legislativo da Prefeitura. |
| **Painel de indicadores** | só Prefeitura | **os dois** (opcional). Os indicadores são do município (IBGE, CNES, INEP, IEG-M, Siconfi). A série mensal de finanças (Fiorilli) continua só no Executivo. |
| Bloco "Serviços mais procurados" | só Prefeitura | os dois (depende da Carta, que já era dos dois) |
| Transmissões | Câmara (obrigatório) / Prefeitura (opcional "audiências") | igual: é a mesma funcionalidade com nomes de módulo diferentes |
| Vereadores, Sessões, Proposições, Emendas, Integração com a Prefeitura | Câmara | Câmara: são próprios do Legislativo |
| Conheça a cidade, Números da gestão, Publicações oficiais | Prefeitura | Prefeitura: são próprios do Executivo |

---

## 4. Análise da legislação

> Não sou advogado. O quadro abaixo resume as normas federais e a forma como o sistema as atende. Cada órgão precisa
> da **norma local** (lei ou decreto da Prefeitura; resolução ou ato da Mesa da Câmara) que regulamenta a LAI e a
> Ouvidoria, e pode fixar regras próprias dentro desses limites.

### 4.1 Os dois serviços são obrigatórios nos dois Poderes

- **LAI (Lei 12.527/2011)**: vale para os Poderes Executivo e Legislativo de todos os entes, o que obriga Prefeitura e
  Câmara a manter o SIC e a receber pedidos por meio eletrônico. Os critérios 12.1 a 12.9 do PNTP 2026 se aplicam aos
  dois.
- **Lei 13.460/2017 (usuário de serviço público)**: vale para a administração direta e indireta de todos os entes e
  Poderes, inclusive o Legislativo municipal. Já está em vigor para todos os municípios. Cada Poder edita a própria
  norma da Ouvidoria (art. 17).
- **"Outro órgão"** (autarquia, fundação, consórcio): pode usar os mesmos serviços como mais um órgão da plataforma.

### 4.2 Regras aplicadas e onde estão no sistema

| Regra | Fonte | No sistema |
|---|---|---|
| Pedido por qualquer meio legítimo, só com identificação e especificação; sem exigir motivo | LAI, art. 10, caput e § 3º | Formulário com nome, e-mail e o que quer; registro no balcão, por telefone ou carta em **Registrar atendimento** |
| Resposta em até 20 dias, prorrogáveis por 10 com justificativa comunicada | LAI, art. 11, §§ 1º e 2º | Prazo calculado e gravado; **uma única** prorrogação, justificativa obrigatória e enviada por e-mail |
| Indicar ou remeter ao órgão que tem a informação, avisando o requerente | LAI, art. 11, § 1º, III | **Encaminhar ao órgão** (parceiro do município, mesma instalação ou outra): novo protocolo no destino e e-mail ao cidadão |
| Negativa com razões e fundamento legal | LAI, art. 11, § 1º, II, e art. 14 | Resultado obrigatório (concedido, parcial, negado, inexistente); negativa sem fundamento é recusada |
| Serviço gratuito | LAI, art. 12 | Nada é cobrado |
| Recurso em 10 dias, decidido em 5 pela autoridade superior | LAI, art. 15 | Recurso pelo portal com o código de acesso; quem respondeu **não pode** decidir; perfil novo **Autoridade de recurso**; 2ª instância opcional, conforme a norma local |
| Relatório estatístico anual de pedidos recebidos, atendidos e indeferidos, com dados genéricos dos solicitantes | LAI, art. 30, III; PNTP 12.7 | `/e-sic/estatisticas`: por ano, com CSV e JSON, por mês, por canal e por tipo de pessoa; sem dado pessoal |
| Rol de informações classificadas e das desclassificadas nos últimos 12 meses | LAI, art. 30, I e II; PNTP 12.8 e 12.9 | `/e-sic/informacoes-classificadas` com CSV; cadastro no painel limitado aos prazos máximos do art. 24 |
| Prazos, recurso, autoridades, unidade responsável e norma local na página do SIC | PNTP 12.1, 12.5 e 12.6 | **e-SIC e Ouvidoria → Configuração** alimenta a página |
| Manifestação com identificação, sem exigências que a inviabilizem e sem exigir motivo | Lei 13.460, art. 10, caput e §§ 1º e 2º | Nome e e-mail; nada de documento |
| Identificação do requerente é informação de acesso restrito | Lei 13.460, art. 10, § 7º; LAI, art. 31 | Nome e e-mail só para Ouvidoria/SIC e administrador. Em denúncia ou com "preservar identidade", só depois de um clique, que fica registrado. No encaminhamento a outro órgão, a identificação **não vai** |
| Resposta em até 30 dias, prorrogáveis uma vez por 30 | Lei 13.460, art. 16 | Prazo e prorrogação única |
| Complementação pedida uma única vez, com prazo suspenso | Decreto federal 9.492/2018 (por analogia; confirmar na norma local) | **Pedir complemento**: 20 dias para o cidadão; sem resposta, o atendimento é encerrado com aviso |
| Denúncia sem identificação | Decreto federal 10.153/2019 e prática da CGU (por analogia; a Lei 13.460 pede identificação) | Só para **denúncia**: sem nome e sem e-mail, com acompanhamento apenas por protocolo e código |
| Relatório anual de gestão: número de manifestações, motivos, pontos recorrentes e providências | Lei 13.460, arts. 14, II, e 15 | `/ouvidoria/relatorio`: números do sistema; análise e providências escritas e publicadas pela equipe |
| Avaliação do serviço pelo usuário | Lei 13.460, art. 23 | Nota de 1 a 5 e "resolveu?" depois da resposta |
| Dados pessoais só para a finalidade, com segurança | LGPD, arts. 6º, 23 e 46 | Nome e e-mail nunca no portal; código de acesso guardado só como hash; resposta com CPF é recusada; e-mail à equipe sem dados do cidadão; no nó separado, os e-mails saem da própria instalação |

### 4.3 Notificação por e-mail

Nenhuma lei exige e-mail, mas a LAI manda **cientificar** o requerente da prorrogação, da remessa e da negativa
(arts. 11 e 14). O sistema manda e-mail ao cidadão no registro (protocolo e código), na prorrogação, no pedido de
complemento, na resposta (com o prazo e a autoridade do recurso), no recurso, na decisão e no encaminhamento. A equipe
recebe aviso de pedido novo, de recurso e um resumo diário dos prazos que vencem em 2 dias, sem dados do cidadão.

**De onde sai o e-mail:**
1. SMTP do **próprio órgão** (Configuração), com senha cifrada pela `CHAVE_CREDENCIAIS`. É o recomendado e o único
   caminho no nó separado, porque os dados do cidadão não passam pela gestão.
2. Com gestão e portal juntos (`PAPEL=tudo`), sem SMTP próprio: o e-mail da plataforma.
3. Sem nenhum dos dois: o aviso espera na fila, sem gastar tentativa, e o painel mostra o alerta.

---

## 5. e-SIC e Ouvidoria: o que mudou

- **Portal:**
  - `/e-sic` e `/ouvidoria` mostram como funciona, os prazos, a unidade responsável, as autoridades e a norma local;
  - o registro mostra o **protocolo e o código de acesso** (uma única vez na tela, também por e-mail);
  - `/acesso?protocolo=` mostra só a situação. Com o código, mostra o conteúdo, a resposta, o andamento, o complemento,
    o recurso e a avaliação. Protocolos antigos, sem código, seguem como antes.
- **Painel** (`admin_atendimento.py`):
  - filtros: em aberto, vencendo, recursos, concluídos;
  - histórico com notas internas;
  - setor, prorrogação, complemento, resposta com resultado e fundamento;
  - recurso em 1ª e 2ª instância;
  - encaminhamento a órgão parceiro e consulta da situação no destino;
  - registro de atendimento presencial;
  - configuração, relatório da Ouvidoria e informações classificadas.
- **Perfis novos:** *Ouvidoria / SIC* (vê a identificação, configura) e *Autoridade de recurso* (decide recursos).
  Editor e publicador continuam atendendo, mas sem ver nome e e-mail.
- **Worker:** envia a fila de e-mails a cada minuto. Uma vez por dia, encerra os complementos vencidos e manda o
  resumo dos prazos.
- **Autoavaliação PNTP:** os critérios 12.1, 12.3, 12.5 a 12.9 passaram a ser medidos pelo que está configurado.
- **Migração** `041_orgao_atendimento.sql`: idempotente. Os registros antigos ganham prazo calculado.

---

## 6. O que cada órgão precisa fazer

1. **Configuração do e-SIC e da Ouvidoria:**
   - unidade responsável;
   - autoridade de 1ª instância e, se a norma local prever, a de 2ª;
   - nome e endereço da norma local;
   - e-mail da equipe.
2. **E-mail de saída do órgão:** SMTP com o domínio do órgão (ex.: `ouvidoria@camara...`). Depois, use **Enviar
   teste**.
3. **Usuários:** criar quem atende (perfil *Ouvidoria / SIC*) e quem decide recursos (*Autoridade de recurso*). Devem
   ser pessoas diferentes.
4. **Norma local:** se não houver, editar decreto (Prefeitura) ou resolução ou ato da Mesa (Câmara) que regulamente a
   LAI e a Ouvidoria. Pontos que a norma deve definir: autoridades de recurso, 2ª instância, complementação e
   denúncia anônima.
5. **Relatório anual da Ouvidoria:** escrever a análise e as providências e publicar (Lei 13.460, art. 15).
6. **Câmara com Diário próprio:** contratar o módulo no console, editar a resolução de instituição e configurar os
   signatários, como na Prefeitura.

## 7. Implantação (quando aprovada)

1. Snapshot e `deploy/backup.sh`.
2. Gestão: build e `provision atualizar`. Aplica a migração 041 nos bancos dos órgãos daqui e cria os pares.
3. Cada nó: **Preparar instalação** no console e `bash deploy/no/instalar.sh` (atualização). O `provision atualizar`
   aplica `006_local_diretorio.sql` no banco local e a migração 041 nos bancos dos órgãos.
4. Em até 5 minutos cada nó recebe o diretório. Conferir:
   - **Órgãos parceiros → Testar conversa** nos dois painéis;
   - `/e-sic` e `/ouvidoria` nos dois portais;
   - um pedido de teste com e-mail real do órgão.

## 8. Testes

- `tests/teste_atendimento.py` (novo) tem duas partes:
  - **e-SIC e Ouvidoria:** pedido, código, prorrogação, complemento, negativa, recurso em duas instâncias, identidade,
    anônimo, e-mails, relatórios, classificadas, fila, rotina e encaminhamento;
  - **Prefeitura no nó A e Câmara no nó B**, com bancos locais próprios:
    - diretório assinado; adulterado e de outro nó são recusados;
    - links entre os portais;
    - teste de conversa;
    - encaminhamento e consulta da situação;
    - remessa ao Diário e legislação entre os nós;
    - troca de chaves (a antiga é recusada até o nó buscar a nova);
    - integração desligada;
    - diretório antigo ignorado.
- As suítes existentes continuam passando. A única mudança nelas foi em `teste_licenca.py`, que conferia o texto
  exato da mensagem de `puxar()` e agora confere o começo, porque a mensagem pode trazer o diretório.
