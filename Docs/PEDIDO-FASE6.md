# Fase 6 — Diário Oficial com assinatura ICP-Brasil e carimbo do tempo, remessa da Câmara e login gov.br

Base: Fases 3, 4 e 5 implantadas. Regras legais: Lei Municipal 910/2026 e decreto de 25/03/2026 de Borá; MP 2.200-2/2001; Lei 14.063/2020 (assinatura qualificada obrigatória para chefe de Poder).
REGRAS: as mesmas das fases anteriores (branch fase-6, tag ao final, migrações idempotentes, aprovação antes de cada alteração na VPS, testes só em banco de TESTE, nunca mostrar senhas/.env/chaves, PROGRESSO.md).
SEGREDOS: certificados (.pfx/.p12), senhas de certificado, credenciais da ACT e do gov.br NUNCA no git nem no chat. Ficam em /opt/portal_web/segredos/ (chmod 700, arquivos 600, dono = usuário do container) montado só leitura no container, e as senhas em variáveis do .env. Se algum segredo ainda não existir, construa tudo em MODO TESTE e pare no ponto de configuração, explicando o que falta.

ESCOPO
A) Assinatura e carimbo do tempo
1. Use a biblioteca pyHanko (PAdES) para assinar o PDF da edição: assinatura PAdES com carimbo do tempo RFC 3161 e dados de validação embutidos (LTV), para validar em validar.iti.gov.br.
2. Assinaturas por caderno (Lei 910, art. 7º, § 1º): caderno do Executivo assinado pelo Prefeito ou servidor designado; caderno do Legislativo pelo Presidente da Câmara ou servidor designado; assinatura final da edição pelo setor responsável (decreto, art. 2º, § 2º). Modele "signatários designados" por caderno com o ato de designação (número/data) cadastrado no painel.
3. Provedores de assinatura (interface com adaptadores): (a) certificado A1 (PKCS#12) do responsável, guardado em /opt/portal_web/segredos — implemente completo; (b) certificado em nuvem — adaptador com a interface pronta e documentação do que o provedor precisa fornecer (API, credenciais), sem inventar endpoints; (c) A3/token — fora do servidor: permitir o upload do PDF do caderno já assinado pelo signatário no computador dele, validando a assinatura antes de aceitar.
4. Carimbo do tempo: configuração da ACT (URL RFC 3161, usuário/senha ou certificado de cliente) por variável de ambiente; até o contrato (Serpro/Prodesp ou outra ACT credenciada), MODO TESTE com uma TSA de teste e marca d'água "SEM VALOR OFICIAL — TESTE" em todas as páginas, nunca publicado no portal oficial.
5. Página pública de verificação: ao digitar o código, mostra edição, SHA-256, signatários, data/hora do carimbo e situação da validação; link para validar.iti.gov.br.
6. PDF/A-2b para arquivo permanente (Lei 910, art. 8º; decreto, art. 5º, VI) — gere ou converta, mantendo a assinatura válida (assinar depois de converter).
B) Regras de operação do Diário (Lei 910 e decreto)
7. Calendário: feriados e dias sem expediente cadastrados pelo setor responsável; sem edição em fins de semana e feriados; ponto facultativo conta como dia útil.
8. Horários: envio até 16h; após o corte, os atos vão para a próxima edição ou para extra; publicação automática pelo worker a partir das 16h (ex.: 17h) somente se a edição estiver assinada; alerta ao responsável se às 16h30 ainda não houver assinatura.
9. Edição "SEM ATOS OFICIAIS A SEREM PUBLICADOS NESTA DATA" gerada, assinada e publicada automaticamente em dia útil sem atos.
10. Edição extra (mesmo número + letra A–Z), retificação (nova publicação apontando para o ato original), invalidação de edição por ato do Prefeito com comunicado de indisponibilidade no portal e prorrogação de prazos registrada.
11. Capa conforme a Lei 910, art. 6º (brasão, título, lei de instituição, data, número, nome do responsável).
C) Remessa da Câmara para o caderno Legislativo
12. No painel da Câmara: "Enviar ao Diário" (atos da Mesa, resoluções, decretos legislativos, extratos) cria a remessa no Diário da Prefeitura por uma API interna entre órgãos (token por par de órgãos guardado na plataforma, assinado e com registro), com retorno de situação (recebido, aprovado, publicado com nº da edição e página). A Câmara nunca acessa o banco da Prefeitura.
D) Login gov.br e segundo fator
13. Login Único gov.br (OpenID Connect) para os painéis /admin dos órgãos e para o console: configuração por variáveis (client_id, client_secret, URLs de retorno dos 3 domínios), exigir nível prata ou ouro; vínculo do usuário pelo CPF guardado só como hash (HMAC com chave secreta) + 2 últimos dígitos; o CPF completo nunca é gravado.
14. Enquanto a integração gov.br não estiver liberada (exige solicitação do órgão ao gov.br), manter e-mail + senha com SEGUNDO FATOR TOTP obrigatório (aplicativo autenticador) e códigos de recuperação; console do gestor sempre com segundo fator.
15. Endurecimento: limite de tentativas de login, bloqueio temporário, sessão com expiração por inatividade, cabeçalhos de segurança (CSP, frame-ancestors), cookies Secure/HttpOnly/SameSite, registro de acesso no log de auditoria.
E) Testes e implantação
16. Testes (banco de TESTE): assinatura A1 de teste (certificado autoassinado gerado só para teste), carimbo em modo teste, validação da assinatura com pyHanko, edição sem atos automática, extra com letra, retificação, remessa Câmara→Prefeitura, login com TOTP, bloqueio por tentativas.
17. Implantação (com aprovação), conferência, merge + tag fase-6, PROGRESSO.md e README.md (incluindo o passo a passo para instalar o certificado real, configurar a ACT e o gov.br quando os contratos saírem).

CRITÉRIOS DE ACEITE
- Em MODO TESTE, uma edição completa sai assinada (PAdES + carimbo de teste) com marca "SEM VALOR OFICIAL" e a página de verificação mostra signatários e carimbo; nada em modo teste é publicado como oficial.
- Com certificado e ACT reais configurados, a edição valida em validar.iti.gov.br.
- Dia útil sem atos gera a edição "sem atos"; publicação só acontece com edição assinada.
- A Câmara envia um ato e vê o número da edição e a página em que foi publicado.
- Painéis exigem segundo fator (ou gov.br quando configurado); nenhum CPF completo gravado.

O QUE O ÓRGÃO PRECISA PROVIDENCIAR (para sair do modo teste)
- Certificado ICP-Brasil do responsável pela edição (A1 para assinatura automática) e dos signatários dos cadernos (nuvem ou A3).
- Contrato com uma ACT credenciada (ex.: Serpro, Prodesp) com URL e credenciais RFC 3161.
- Atos de designação dos signatários (Prefeito e Presidente da Câmara).
- Solicitação de integração ao Login Único gov.br, com as URLs de retorno dos domínios.
