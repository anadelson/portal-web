# Fase 5 — Câmara completa (processo legislativo, sessões, votação nominal, transmissões e participação)

Base: Fases 3 e 4 implantadas (tags fase-3 e fase-4). Referências: Docs/referencia/ESPEC-VISUAL.md e prototipos/Camara.dc.html, Backend.dc.html (telas "Sessões e votações", "Proposições", "Vereadores e legislaturas", "Transmissões", "Participação", "Autoavaliação PNTP").

REGRAS: as mesmas das fases anteriores (um código para todos os órgãos; git no branch fase-5 com commits pequenos e tag ao final; migrações idempotentes via "python -m app.provision atualizar"; aprovação antes de cada comando que altere a VPS; testes só em banco de TESTE; nunca mostrar senhas/.env; LGPD; acessibilidade AA; nada inventado como dado real; registrar tudo em Docs/PROGRESSO.md).
IMPORTANTE: votos, presenças e atas NUNCA vêm pré-preenchidos nem são inventados: só entram quando a Secretaria registra. O portal atual da Câmara tem reCAPTCHA: NÃO fazer raspagem; dados antigos entram por importação de arquivo exportado pelo fornecedor (Pronim/Cidade360) ou digitação.

ESCOPO
1. Vereadores e legislaturas (painel da Câmara): cadastro completo (se a Fase 3 não fez tudo): legislaturas (número, anos, prefeito, vice), vereadores por legislatura, Mesas por biênio com registro da eleição/posse do 2º biênio (2027–2028), foto oficial e biografia, contatos do gabinete. Galeria de legislaturas no portal (abas) com perfil de cada vereador.
2. Proposições com tramitação: tipos (PL, PLC, PR, PDL, Indicação, Requerimento, Moção, Emenda, Veto), número/ano automáticos por tipo, autores (um ou vários, incluindo Executivo/Comissão), relator, comissões, eventos de tramitação (data, fase, descrição), documentos em PDF (texto, pareceres, autógrafo, lei sancionada) com texto alternativo/descrição, situação. Portal: lista com filtros (tipo, ano, autor, situação, texto) e página de cada proposição com linha do tempo e documentos. Indicações/requerimentos/moções aparecem no perfil do autor.
3. Comissões: cadastro (permanentes/temporárias, membros), pauta e parecer das comissões (PNTP 20.5).
4. Sessões completas: pauta montada a partir das proposições; presença por vereador; VOTAÇÃO NOMINAL por item (Sim, Não, Abstenção, Ausente; presidente vota só no desempate, com aviso); resultado (aprovado/rejeitado) que atualiza a tramitação da proposição; ata (texto + PDF); vídeo vinculado; publicação separada de pauta, presença, votação e ata. Portal: página de cada sessão com tudo isso; perfil do vereador com presença/faltas e votos nominais calculados das sessões publicadas.
5. Julgamento das contas do Prefeito (PNTP 20.8): processo com parecer prévio do TCESP (PDF), parecer da comissão, votação nominal e decreto legislativo.
6. Diárias e verbas dos vereadores (PNTP 20.10): base com beneficiário (vereador/servidor), destino, motivo, período, valor; importação por planilha (modelo CSV em Docs) e exportação CSV/JSON no portal, com base legal.
7. Transmissões: configuração do canal (ID do canal/vídeo YouTube ou URL de player) por órgão; agenda; botão "Iniciar transmissão" no painel liga a faixa "● Ao vivo" e o aviso (uma vez por dia) nos portais; página de transmissões com player embutido (youtube-nocookie), capítulos, gravações vinculadas às sessões, indicação de legendas e Libras. Disponível também para a Prefeitura (audiências) quando o módulo estiver contratado.
8. Participação: inscrição na Tribuna Livre por sessão (dados pessoais só para a Secretaria; deferir/indeferir no painel); opinião sobre projetos com moderação (publica sem dados pessoais; rejeita ofensa ou dado pessoal); resultado do "Avalie este portal" por página.
9. Importação de dados antigos: comando/painel para importar CSV (modelos em Docs/modelos/: legislaturas, vereadores, mesas, proposições, tramitação, sessões, presenças, votos) com validação e relatório de erros; nada de raspagem.
10. Autoavaliação PNTP (dimensão 20) no painel da Câmara: critérios 20.1 a 20.11 calculados a partir dos dados (atendido/parcial/pendente) com link para onde está no portal.
11. Testes (banco de TESTE): fluxo completo proposição → pauta → presença → votação → resultado → tramitação → perfil do vereador; importação CSV; transmissão ao vivo liga/desliga; Tribuna Livre; LGPD (nenhum dado pessoal no portal).
12. Implantação (com aprovação), conferência nos domínios, merge + tag fase-5, PROGRESSO.md e README.md.

CRITÉRIOS DE ACEITE
- Uma proposição de teste percorre todo o caminho e aparece no portal com tramitação, votação nominal e resultado; o perfil de cada vereador mostra presença e votos calculados.
- A autoavaliação PNTP da dimensão 20 mostra a situação real de cada critério.
- Faixa "ao vivo" aparece e some pelos comandos do painel.
- Nenhum voto, presença ou ata inventado; nenhum dado pessoal exposto.
