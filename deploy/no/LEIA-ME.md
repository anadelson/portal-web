# Instalar um nó de portais (VPS nova)

Um **nó** é uma VPS que hospeda portais e painéis de órgãos. A **gestão** (console, contratos e licenças) fica em outra VPS.

Um nó hospeda **quantos órgãos a gestão atribuir a ele**. Não existe configuração por órgão no nó:
- cada órgão chega pela licença assinada;
- o banco de cada órgão é criado por uma ordem da gestão;
- o domínio de cada órgão é publicado pelo ativador do próprio nó, quando pedido no console.

Os passos que alteram uma VPS são feitos por quem administra a VPS.

## Na VPS da gestão (a atual)

1. **Pacote de código**, tirado de uma tag do git, sem segredos:
   ```bash
   bash deploy/no/empacotar.sh
   ```
2. **Pacote de segredos**: o `.env` e a pasta `segredos/`, com permissão 600 e sem exibir nada:
   ```bash
   bash deploy/no/exportar_segredos.sh
   ```
   As chaves `SECRET_KEY`, `TOTP_CHAVE`, `CPF_HMAC_CHAVE` e `CHAVE_CREDENCIAIS` **precisam ser iguais** no nó. Se forem diferentes, deixam de funcionar:
   - o 2FA dos administradores e os códigos de recuperação;
   - o login por CPF;
   - as credenciais das fontes;
   - os códigos das edições do Diário.
3. **Cadastrar o nó no console**, em "Nós e licenças": nome (ex.: `no1.dominio.tld`) → **o token aparece uma vez**. Anote também a **chave pública** mostrada na mesma tela.
4. **Copiar os dois pacotes** para a VPS nova (troque `IP_DO_NO` pelo IP da VPS nova):
   ```bash
   scp pacotes/portal-codigo-*.tar.gz /root/segredos-no-*.tar.gz root@IP_DO_NO:/root/
   ```

## Na VPS nova (como root)

```bash
mkdir -p /opt && tar -xzf /root/portal-codigo-*.tar.gz -C /opt && cd /opt/portal_web
```

```bash
bash deploy/no/instalar.sh
```

O instalador confere o servidor, **pergunta só o que falta** e pede confirmação antes de cada etapa:

1. conferência do servidor (só leitura);
2. atualizações, fuso horário e relógio;
3. Docker, pelo repositório oficial;
4. firewall (SSH, 80 e 443);
5. segredos: lê o pacote da gestão;
6. configuração do nó: endereço da gestão, nome, token (não aparece na tela), chave pública, IP e validade da licença;
7. nginx e certificados:
   - **portas livres**: sobe um nginx e um certbot próprios do nó;
   - **portas ocupadas por outro sistema**: usa o nginx que já existe. O instalador **descobre pelo Docker**:
     - o container que publica a porta 443/80;
     - a pasta conf.d e a pasta dos certificados;
     - a rede;
     - o certbot que usa os mesmos certificados.

     Ele mostra o que encontrou e pede só um Enter para confirmar. Só pergunta o que não achar (por exemplo, um nginx instalado fora do Docker);
8. banco, app e worker (a senha do banco do nó é gerada na hora);
9. ativador (a cada minuto) e backup diário (02h00);
10. conferência com a gestão (licenças e relatório).

Os passos demorados mostram o andamento na mesma linha: o tempo decorrido e a última linha do registro. Para acompanhar os detalhes em outro terminal:

```bash
tail -f /opt/portal_web/logs/instalar-no.log
```

Pode rodar de novo quando quiser: ele mantém a senha do banco, o token e os segredos já gravados.

Para só conferir, sem alterar nada:

```bash
bash deploy/no/instalar.sh --verificar
```

Depois da instalação, apague os pacotes de segredos nas duas VPS:

```bash
rm /root/segredos-no-*.tar.gz
```

## Depois

No console da gestão:
- **Nós e licenças**: o nó aparece com o IP e o relatório.
- **Órgão → Hospedagem e licença**: escolher o nó.

Órgão novo pode ser cadastrado direto no nó (campo "Hospedagem" no cadastro).

A mudança dos pilotos (dados e DNS) é feita no **ensaio** e na **virada**, com aprovação: ver `Docs/ANALISE-SEPARACAO-VPS.md`.

## Testes

```bash
docker run --rm -u 0 --network none -v /opt/portal_web:/codigo:ro portal_web-app bash /codigo/tests/teste_instalador_no.sh
```

Esse comando ensaia o instalador num contêiner descartável, com docker, apt e systemd simulados, e confere:
- o `.env` gerado;
- que nenhum segredo aparece na tela nem no log;
- que rodar de novo mantém a senha do banco, o token e os segredos;
- o caso de VPS compartilhada (portas 80/443 já em uso): descobre e usa o nginx existente, ou pergunta quando não acha;
- as recusas de token e de chave pública inválidos.
