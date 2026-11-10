# Etapa 2 — ativar domínio pelo console (desenho, 10/11/2026) — PARADA para decisões

## Como é hoje (levantado só lendo)
- **nginx:** o da VPS é o container `nginx` do projeto **hotspot** (outro sistema).
  - Lê `/opt/hotspot/nginx/conf.d/*.conf`.
  - O piloto tem `portal-bora.conf` (3 domínios fixos) + `portal-bora.inc` (proxy para `portal-web-app:8000`).
- **certbot:**
  - Também é do hotspot (container `certbot`, modo webroot `/var/www/certbot`), com certificados no volume `hotspot_nginx-certs`.
  - Renova sozinho a cada 12 h.
- **Porta 80:** o vhost padrão (`default.conf`) já atende `/.well-known/acme-challenge/` para **qualquer** domínio. Dá para emitir o certificado de um domínio novo antes de criar o vhost dele.
- **DNS:** os domínios do piloto apontam para 76.13.167.181 (IP da VPS).
- **Achado: ninguém recarrega o nginx depois da renovação automática.** O certbot renova o arquivo, mas o nginx continua usando o certificado antigo até alguém recarregá-lo. Isso vale para todos os sites da VPS, não só para o piloto. Os certificados do piloto foram emitidos em 07/11/2026 e vencem em ~05/02/2027.

## Desenho proposto
**Princípio:** o app web **nunca** executa comandos na VPS. O console só registra o **pedido**; quem age é um **ativador** separado, com uma lista fechada de ações.

1. **No console (Órgãos → órgão → "Domínio e publicação"):**
   - mostra o domínio, o IP que o DNS devolve **agora** e se ele já aponta para a VPS (verificação ao vivo, só leitura);
   - botão **"Ativar domínio"**, habilitado só quando o DNS aponta para a VPS: grava um pedido na fila (tabela nova `ativacoes`, banco de controle) e registra no log do console;
   - mostra a situação de cada passo: DNS ok → certificado emitido → vhost criado → nginx recarregado → no ar (HTTPS 200), com a mensagem de erro, se houver.
2. **Ativador** (script `deploy/ativador.sh` na VPS, rodado a cada minuto por um timer do systemd, como root). Para cada pedido pendente:
   1. **Revalida tudo:** o domínio passa pela expressão regular, existe na tabela de órgãos, não é de outro sistema da VPS e o DNS aponta para a VPS.
   2. **Emite o certificado:** `docker exec certbot certbot certonly --webroot -w /var/www/certbot -d <domínio> --non-interactive --keep-until-expiring`. Usa a conta do Let's Encrypt que já existe na VPS.
   3. **Gera um único arquivo:** `/opt/hotspot/nginx/conf.d/portal-orgaos.conf`, com um bloco por órgão ativado, todos usando o mesmo `portal-bora.inc` (renomeado para `portal-comum.inc`).
      - O arquivo é refeito inteiro a partir do banco, de forma atômica.
      - O `portal-bora.conf` do piloto **não é mexido**.
   4. **Valida e recarrega:** `docker exec nginx nginx -t`. Só então `docker exec nginx nginx -s reload`. Se a validação falhar, volta o arquivo anterior e marca erro; o nginx nunca recarrega com configuração quebrada.
   5. **Confere de fora:** `https://<domínio>/` responde e o certificado é o novo. Grava a situação "no ar".
3. **Recarga depois da renovação:** o mesmo ativador recarrega o nginx uma vez por dia, **só se algum certificado foi renovado** (data do arquivo mudou). Corrige o achado acima para todos os sites.
4. **Segurança:**
   - o ativador só aceita domínios cadastrados;
   - não aceita domínio que já esteja em outro vhost da VPS (não sobrescreve sites do hotspot ou de outros sistemas);
   - nunca apaga certificados;
   - registra tudo no log do console e em `/opt/portal_web/logs/ativador.log`.
5. **Desativar:** botão "Tirar do ar" remove o bloco do órgão do `portal-orgaos.conf` e recarrega. O certificado fica guardado.

## O que continua manual
- **Apontar o DNS:** registro A do domínio para 76.13.167.181. Quem cuida é o dono do domínio (Hostinger para *.conectatech.tech; o órgão para *.sp.gov.br). O console mostra a instrução e confere sozinho quando passar a apontar.

## Para testar de ponta a ponta
- Emitir certificado de verdade exige um domínio de teste apontando para a VPS, por exemplo `teste-ativacao.conectatech.tech`, com registro A criado na Hostinger.
- Primeiro em modo de ensaio (`--dry-run`, ambiente de testes do Let's Encrypt); depois de verdade.

## Decisões
- D1. Posso gravar um arquivo novo (`portal-orgaos.conf`) e um trecho (`portal-comum.inc`) na pasta do nginx do **hotspot** e recarregar o nginx dele pelo ativador?
- D2. Posso instalar o timer do systemd (`portal-ativador.timer`, a cada minuto) que roda o ativador como root?
- D3. Corrijo a recarga do nginx depois da renovação, que afeta todos os sites da VPS?
- D4. Para o teste de ponta a ponta, você cria um registro A de teste na Hostinger (ex.: `teste-ativacao.conectatech.tech` → 76.13.167.181)?
