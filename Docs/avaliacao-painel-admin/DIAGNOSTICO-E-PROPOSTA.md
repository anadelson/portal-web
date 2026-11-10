# Painel administrativo — diagnóstico e proposta (10/11/2026) — PARADA para aprovação

**De onde vieram as capturas:** ambiente de TESTE (banco de teste, usuários de teste), em 1366 e 390 px:
- 27 telas da Prefeitura, 13 da Câmara e 6 do console;
- as duas telas de login.

Arquivos em `antes/`, medidas em `antes/antes-medidas.json`. Nada foi alterado.

## O que está errado (confirmado)

### 1. Cada tela tem um formato
- **Formulário × lista:** em 14 telas o formulário de cadastro vem ANTES da lista; em 8, DEPOIS.
  - Formulário em cima: Comunicados, Página inicial, Diário Oficial, Sessões, Legislaturas, Remessas, Diárias, Redes, Fotos e álbuns.
  - Lista em cima: Conheça, Menus, Usuários, Funcionalidades, Signatários, Monitoramento, Emendas, Dados do município.
- **Só Conteúdos segue o padrão bom:** lista → "Novo" → tela de edição própria.
- **Configurações misturadas com cadastro:** ex.: "Tipos de comunicado" fica embaixo da lista de comunicados.
- **Campos desalinhados:** alguns têm o rótulo ao lado do campo ("Ordem [   ]", "Data e hora da publicação [   ]"); os outros, em cima.
- **Telas enormes:**
  - "Brasão, mascote e fundos": 9 formulários e 3.000 px de altura, cada imagem com o próprio botão Salvar;
  - Menus: 25 formulários e 3.760 px.

### 2. Funções espalhadas (o caso do "Conheça Borá")
| O que aparece no portal | Onde se edita hoje |
|---|---|
| Perfis (lugares, patrimônio, festas) | menu Conteúdo → Conheça Borá |
| Título e texto do bloco "Conheça a cidade" | Identidade → Dados e textos (no meio dos dados do órgão) |
| Números do bloco (IBGE + manuais) | Identidade → Dados do município |
| As 3 fotos do bloco | Identidade → Brasão, mascote e fundos |
| Galeria de fotos e álbuns (/fotos) | Identidade → Fotos e álbuns |

A "Identidade" junta 7 assuntos diferentes: dados do órgão, tema, imagens, favicon, redes, município e fotos.

Outros exemplos:
- o Diário Oficial está em dois itens de menu (Diário e "Signatários e calendário");
- a Carta de Serviços ocupa três itens;
- Participação aparece em lugares diferentes na Prefeitura e na Câmara.

### 3. Leitura difícil
- **Medido depois da escala de hoje:** de 20% a 54% dos textos de cada tela estão abaixo de 14 px.
- **O que fica pequeno:** notas, cabeçalhos de tabela em CAIXA ALTA de 13 px, selos, nomes dos grupos do menu (12 px, caixa alta, espaçado) e a barra com "domínio · banco".
- **Barulho técnico no topo de toda tela:** "pmbora.localhost · banco bd_pm_bora".

### 4. Menu
- **Tamanho:** 22 itens em 9 grupos com nome em caixa alta. Os grupos seguem o "módulo", não a tarefa (ex.: "Legislação" só tem "Importar legislação antiga").
- **Celular:** o menu inteiro aparece antes do conteúdo (2.600 px de altura em 390 px), sem botão "Menu".

### 5. Login
- Nome do órgão repetido duas vezes ("Prefeitura Municipal de Borá" e "Área restrita — Prefeitura Municipal de Borá").
- Brasão pequeno e desalinhado.
- Ajuda em 12 px.
- Não há "Voltar ao portal".
- Fundo liso; a imagem de fundo do login existe, mas não está cadastrada.

## Proposta

### A. Um padrão único de tela (todas as telas de cadastro)
1. **Cabeçalho:** título, uma frase do que a tela faz e, à direita, um botão principal ("+ Novo comunicado").
2. **Lista sempre primeiro:**
   - tabela limpa (texto de 15 px, cabeçalho de 14 px sem caixa alta), situação em selo e ações "Editar" à direita;
   - busca/filtro quando passar de 10 itens;
   - estado vazio com explicação e o botão "Novo".
3. **Criar/editar em tela própria** (`/novo` e `/{id}`), como Conteúdos já faz:
   - rótulo sempre em cima do campo;
   - largura de leitura;
   - barra de ações fixa no rodapé ("Salvar" | "Cancelar" | "Excluir/Tirar do ar");
   - "← Voltar à lista".
4. **Configurações da tela** (ex.: tipos de comunicado, signatários do Diário) numa aba "Configurações" da própria tela, nunca no meio da lista.
5. **Imagens:** uma grade de miniaturas; ao clicar, abre a edição daquela imagem (nada de 9 formulários abertos ao mesmo tempo).

**Sem quebrar nada:**
- os endereços e os envios (POST) atuais continuam valendo;
- as telas novas só reorganizam o que já existe;
- endereço antigo que mudar redireciona para o novo;
- todas as suítes de teste continuam rodando.

### B. Menu por tarefa, com menos grupos (mesmo código para os dois órgãos; itens conforme os módulos contratados)
- **Início:** Visão geral
- **Publicar:** Notícias e páginas · Comunicados · Diário Oficial (Prefeitura: edições, signatários e calendário em abas) / Enviar ao Diário (Câmara) · Legislação antiga (importar)
- **Legislativo** (Câmara): Sessões e votações · Proposições · Comissões · Vereadores e Mesas
- **Cidade** (Prefeitura): **Conheça Borá**, com abas Perfis | Bloco da página inicial (título, texto, 3 fotos) | Números do município · **Fotos e álbuns**
- **Atendimento:** e-SIC e Ouvidoria · Carta de Serviços (Fichas | Secretarias | Monitoramento, em abas) · Avaliação e participação
- **Transparência:** Painel de indicadores (Câmara: + Contas, Diárias, Emendas, PNTP)
- **Aparência do portal:** Página inicial (blocos) · Menus e atalhos · Identidade visual (Tema e cores | Brasão e mascote | Imagens de fundo | Favicon)
- **Administração:** Dados do órgão (nome, contatos, encarregado LGPD, redes sociais) · Usuários e perfis · Funcionalidades · Integrações · Período eleitoral · Registro de ações

Outras mudanças no menu:
- **Grupos:** nome em 13 px, sem caixa alta; o painel lembra quais estão abertos.
- **Celular:** botão "Menu" que abre o menu por cima da tela (foco preso; Esc fecha), como no portal.
- **Topo de toda tela:** "domínio · banco" sai do topo e vai para a Visão geral. No lugar, "Ver portal ↗" e o nome do usuário.

### C. Leitura (ajuste da escala aprovada hoje, só no painel e no console)
| uso | hoje | proposto |
|---|---|---|
| Texto base | 15 px | 16 px |
| Título da tela | 23 px | 24 px |
| Notas e ajudas | 12 px | 14 px |
| Cabeçalho de tabela | 13 px em CAIXA ALTA | 14 px, sem caixa alta |
| Selos e nome dos grupos do menu | 12 px | 13 px, sem caixa alta |
| Campos e botões | 15 px, altura de 40 | 16 px, altura de 44 |

Resultado: **mínimo de 13 px** no painel (só "exemplo" fica em 12), e menos texto: cada tela com uma frase de ajuda curta, sem parágrafos longos em cima.

### D. Login
- Cartão centralizado com o brasão maior, o nome do órgão uma vez só e "Área restrita" como rótulo.
- Campos e botão de 16 px / 48 px.
- Passos "1 · E-mail e senha → 2 · Código do aplicativo" mais claros.
- Ajuda de 14 px e link "← Voltar ao portal".
- Imagem de fundo do órgão quando cadastrada (já existe o campo); sem ela, a cor do tema escurecida.
- Nenhuma mudança na segurança: 2FA, bloqueio por tentativas e mensagens continuam iguais.

### Etapas (cada uma com capturas antes/depois, testes e PARADA antes de implantar)
1. **Etapa 1 — mais visível, menor risco:** menu novo (inclusive no celular), escala de leitura, topo limpo e login.
2. **Etapa 2 — padrão "lista → editar"** em todas as telas de cadastro, mais Conheça e Identidade reorganizados.
