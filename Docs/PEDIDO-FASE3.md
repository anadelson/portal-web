# Fase 3 — Identidade visual dos portais (protótipo do canvas → piloto)

Cole no Claude Code (troque USUARIO e IP_DA_VPS):

---
Contexto: o piloto dos Portais de Borá está no ar na VPS USUARIO@IP_DA_VPS, código em /opt/portal_web, documentação em /opt/portal_web/Docs.
Domínios: pmbora.conectatech.tech (Prefeitura), cmbora.conectatech.tech (Câmara), gestao.conectatech.tech (console). Painéis em /admin.
Se estiver no meu PC, acesse por ssh -o BatchMode=yes USUARIO@IP_DA_VPS. A pasta local C:\Users\BORA\Documents\portais-bora\referencia tem a referência; se ela ainda não estiver em /opt/portal_web/Docs/referencia, proponha copiar com scp -r (com aprovação).

Leia antes: /opt/portal_web/Docs/CLAUDE.md, /opt/portal_web/CLAUDE.md, /opt/portal_web/README.md, /opt/portal_web/Docs/PROGRESSO.md, /opt/portal_web/Docs/referencia/ESPEC-VISUAL.md. Os arquivos em referencia/prototipos/*.dc.html são a referência visual e de comportamento (formato próprio do canvas: leia como especificação, não copie o formato).

REGRAS
- Um código para todos os órgãos: diferenças só por configuração (tipo do órgão, identidade, blocos). Nada de "if Borá" no código.
- Antes de mudar qualquer coisa: se /opt/portal_web não for repositório git, proponha git init + commit "piloto fase 2" (sem o .env: confira o .gitignore). Trabalhe num branch fase-3 e faça commits pequenos.
- Mudanças no banco só por migração idempotente (novo arquivo em app/migrations) aplicada por um comando "python -m app.provision atualizar" que você vai criar (aplica o esquema do órgão em todos os bancos e adiciona os blocos novos ao layout sem apagar os existentes).
- Antes de cada comando que altere a VPS (build, restart, migração), mostre e espere minha aprovação. Nunca mostre senhas nem o .env.
- Acessibilidade (eMAG/WCAG AA): contraste, foco visível, alt em toda imagem, navegação por teclado, sem informação só por cor.
- Nada inventado como dado real; manter "exemplo" onde for exemplo. Sem fotos de banco de imagens no lugar de vereadores: sem foto oficial, usar iniciais.
- Registre o andamento em /opt/portal_web/Docs/PROGRESSO.md.

ESCOPO
1. Imagens: copie Docs/referencia/imagens para app/static/img (gere versões otimizadas .webp ≤ 250 KB mantendo o original). Créditos das fotos de serviços (CC0) no rodapé.
2. Base dos portais (template e CSS), conforme ESPEC-VISUAL.md:
   - barra utilitária, cabeçalho com brasão, menu, busca, ferramentas de acessibilidade;
   - rodapé em 4 faixas (identidade + Radar + "Avalie este portal"; colunas com ícones; redes + "Voltar ao topo"; © + CNPJ + data de revisão + créditos);
   - fonte Public Sans; tokens de cor por órgão (vem da identidade: cor principal).
3. Prefeitura — página inicial com os blocos do protótipo, todos registrados em app/catalogo.py (BLOCOS e LAYOUT_PADRAO) para o editor de regiões e a página inicial do /admin:
   - hero com vista-aerea + busca; "Acesso direto" sobreposto ao hero;
   - "Serviços mais procurados" com foto e degradê radial no canto inferior direito (campo novo "imagem" no conteúdo: escolha entre as fotos de tema; sem imagem = cartão sem foto);
   - "Conheça Borá" (mosaico) e "Paço Municipal" (texto e fotos editáveis pela identidade/configuração do órgão);
   - "Borá em números": só aparece quando houver dados (vem da Fase 4) — deixe o bloco pronto e oculto se vazio.
4. Câmara — página inicial: hero com foto do prédio + cartão "Próxima sessão" (primeira sessão com data ≥ hoje); vereadores com presidente 2×2 e Mesa em largura total (dois biênios); linha 55%/45% Prestação de contas × Emendas; últimas sessões e projetos.
   Páginas: perfil do vereador, galeria de legislaturas (abas) e "caminho da emenda" no visual do protótipo.
5. Identidade no /admin: upload do brasão, da foto do hero e das fotos do "Conheça" (PNG/JPG/WEBP, máx. 3 MB, texto alternativo obrigatório, crédito/licença), guardados em /srv/dados/<órgão>/midia e servidos por rota própria.
6. Vereadores no /admin da Câmara: lista e edição (apelido, partido, biografia, contato do gabinete) e upload da foto oficial (texto alternativo obrigatório). Sem foto: iniciais.
7. Painel /admin e console: menu lateral com ícones (use os caminhos SVG de const ICON em Docs/referencia/prototipos/Backend.dc.html) e grupos.
8. Teste: crie um banco de TESTE separado (ex.: variáveis de ambiente apontando para bancos teste_*) e rode tests/teste_fluxos.py adaptado; nunca rode testes nos bancos reais. Faça também verificação com curl -s -H "Host: ..." nas páginas principais.
9. Implantação (com aprovação): git commit; docker compose build app worker; docker compose up -d; python -m app.provision atualizar; conferir as páginas nos 3 domínios; docker compose logs --tail 80 app.
10. Atualize PROGRESSO.md e o README.md; me mostre o resumo com o que mudou, o que ficou pendente e como desfazer (git).

CRITÉRIOS DE ACEITE
- As páginas iniciais da Prefeitura e da Câmara seguem o protótipo (estrutura e cores), funcionam no celular (375 px) e no desktop.
- Todas as imagens têm alt; foco visível; contraste AA.
- Os blocos novos aparecem no /admin (página inicial) e no editor de regiões do console.
- Nenhuma regressão: e-SIC, Diário, período eleitoral, login e console continuam funcionando.
---
