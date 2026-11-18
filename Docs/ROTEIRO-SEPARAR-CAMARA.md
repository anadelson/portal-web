# Roteiro — separar a Câmara da Prefeitura no nó 72.60.250.36

Situação de hoje: um nó (`726025036.conectatech.tech`, pasta `/opt/portal_web`) com os dois órgãos.
- Prefeitura: `prefbora`, banco `bd_prefbora`, domínio pmbora.prefbora.cloud.
- Câmara: `cmb-bora`, banco `bd_cmb_bora`, domínio cmbora.prefbora.cloud.

Objetivo: a Câmara passa para um **segundo nó na mesma VPS**, a instância `camara`, em `/opt/portal_web-camara`. Cada nó fica com código, containers, PostgreSQL, ativador, backup, token e licença próprios. A Prefeitura não sai do ar em nenhum momento; a Câmara fica fora por poucos minutos (passos 7 a 11).

Regras deste roteiro:
- Comandos com **VPS do nó** rodam como root em 72.60.250.36. **Nunca na VPS da gestão:** o instalador recusa, mas o roteiro não depende disso.
- Comandos com **console** são feitos em https://gestao.conectatech.tech.
- Até o passo 12, voltar atrás é simples: mudar a hospedagem da Câmara de volta para o nó antigo e publicar o domínio de novo. Os dados continuam no nó antigo.

## 0. Pré-requisitos
1. **Gestão atualizada** com a versão `instancias-no` + `mover-orgao`: implantação feita pelo assistente, com aprovação.
2. **Snapshot da VPS do nó** no painel do provedor.
3. **Memória** — na VPS do nó:
   ```bash
   free -m
   ```
   A coluna "available" precisa ter **pelo menos 1.200 MB**. O segundo nó usa cerca de 1 GB: app 384 MB, worker 256 MB e banco 384 MB.

## 1. Atualizar o nó atual (Prefeitura e Câmara) para a versão nova
Console → Nós e licenças → `726025036.conectatech.tech` → **Preparar instalação**, sem marcar token novo. Depois, na VPS do nó, os comandos que a tela mostrar:
```bash
cd /opt/portal_web && bash deploy/no/instalar.sh
```
Responda **Enter** em tudo; é atualização. Esta versão traz o `deploy/no/mover_orgao.sh` e faz o nó esquecer o órgão que mudar de nó.

## 2. Cadastrar o nó da Câmara
Console → Nós e licenças → **Cadastrar nó**:
- **Nome:** por exemplo `camara-bora.conectatech.tech`.
- **Instância:** `camara`.

## 3. Instalar o nó da Câmara (VPS do nó)
Console → nó novo → **Preparar instalação**, marcando token novo. A tela mostra os comandos já com `/opt/portal_web-camara` e com os arquivos `…@camara…`. Rode-os na VPS do nó.
- O instalador avisa: *instância "camara" (pasta /opt/portal_web-camara)*.
- Na etapa 7 ele encontra o nginx que a Prefeitura já usa: responda **[1] usar o nginx que já existe** e confirme os dados.
- No fim, o nó da Câmara aparece no console com o mesmo IP.

Confira na VPS do nó:
```bash
cd /opt/portal_web-camara && bash deploy/no/instalar.sh --verificar
```

## 4. Tirar o domínio da Câmara do ar (console)
Console → Câmara → Publicação → **Tirar do ar**. Espere de 1 a 3 minutos, até o pedido aparecer como concluído.

## 5. Exportar a Câmara do nó atual (VPS do nó)
```bash
cd /opt/portal_web && bash deploy/no/mover_orgao.sh exportar cmb-bora
```
Gera `/root/mover-cmb-bora-AAAAMMDD-HHMM.tgz`, com permissão 600, contendo o banco, as contagens de cada tabela, os arquivos e as linhas do banco local.

## 6. Importar no nó da Câmara (VPS do nó)
```bash
cd /opt/portal_web-camara && bash deploy/no/mover_orgao.sh importar /root/mover-cmb-bora-AAAAMMDD-HHMM.tgz
```
O script cria o banco, restaura e confere **tabela por tabela** contra a origem. Se qualquer contagem não bater, ele apaga o que criou e para.

## 7. Mudar a hospedagem (console)
Console → Câmara → Hospedagem e licença → **nó `camara-bora…`** → confirmar.
Em até 5 minutos:
- o nó antigo deixa de servir a Câmara;
- o nó novo recebe a licença.

## 8. Publicar o domínio (console)
Console → Câmara → Publicação → **Publicar**. O nó novo gera as rotas `portal-orgaos-camara.conf` e emite ou reaproveita o certificado.

## 9. Conferir
- https://cmbora.prefbora.cloud e o painel `/admin` da Câmara respondem.
- Os dados da Câmara aparecem: vereadores, sessões, notícias, usuários.
- https://pmbora.prefbora.cloud (Prefeitura) continua normal.
- O console mostra os **dois nós** com relatório recente.

## 10. Limpar o nó antigo (VPS do nó), só depois de conferido
```bash
cd /opt/portal_web && bash deploy/no/mover_orgao.sh limpar /root/mover-cmb-bora-AAAAMMDD-HHMM.tgz
```
O script:
- **recusa** se a Câmara ainda for do nó antigo;
- pede para digitar `cmb-bora` como confirmação;
- **guarda uma cópia** do banco em `backups/removido-bd_cmb_bora-….dump`;
- só então apaga o banco, os arquivos e as linhas da Câmara do nó antigo.

Depois:
```bash
rm /root/mover-cmb-bora-*.tgz
```

## Voltar atrás (antes do passo 10)
Console → Câmara → Publicação → Tirar do ar → Hospedagem → nó antigo (`726025036…`) → Publicar. O nó antigo ainda tem tudo da Câmara.
